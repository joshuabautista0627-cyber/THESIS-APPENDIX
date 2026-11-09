"""Bounded acquisition, causal inference and independently polled presentation."""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
import queue
import threading
import time
from uuid import uuid4

from processing.baseline import BaselineContext, capture_baseline, save_baseline
from scripts.live_sensor_common import PROJECT_ROOT, atomic_write_json
from services.camera_service import CameraConnectionError
from .model import OpticalModel
from .optical_change import MODE_LABELS, NOISE_KEY, MultiReading, OpticalChange, OpticalReading, mean_v_samples, noise_thresholds
from .multi_press import MultiPress
from .multi_rise import MultiRise
from .optical_rois import RISE_MODES, SPOT_MODES, SIGNAL_PROFILE_KEY, layout_values, optical_layout, signal_profile, signal_values
from .rod_response import PROFILE_KEY, RodResponse, unloaded_profile
from .recording import SessionRecorder
from .setup import OUTPUT, ROI_ORDER, effective_mapping
from .sources import Camera, Frame, LIVE, Replay

STALE_S = 0.5
WARMUP_S = 3.0
BASELINE_S = 3.0
MIN_FRAMES = 20


@dataclass(frozen=True)
class View:
    status: str = "STOPPED"
    detail: str = "Choose an input and press Start."
    frame: Frame | None = None
    arrived: float = 0.
    result: dict | None = None
    baseline: str = "Required"
    capture_hz: float = 0.
    inference_hz: float = 0.
    ms: float = 0.
    mapping: dict | None = None
    optical: tuple = ()
    change: OpticalReading | MultiReading | None = None

    @property
    def cells(self):
        return tuple(self.mapping["cells"]) if self.mapping else ROI_ORDER

    @property
    def active_rois(self):
        if not self.result or not self.result["contact"]:
            return ()
        return self.change.rois if self.change is not None else (self.result["localization"],)

    @property
    def active(self):
        """Legacy scalar output is defined only for exactly one active rod."""
        rois = self.active_rois
        return rois[0] if len(rois) == 1 else None

    def age_ms(self):
        return 1000 * max(0., time.monotonic() - self.arrived) if self.arrived else 0.

    def fresh(self):
        if (self.frame is not None or self.status == "ACQUIRING") and self.age_ms() >= STALE_S * 1000:
            return replace(self, status="STALE INPUT", detail="Waiting for a fresh frame.", result=None)
        return self


def rate(stamps):
    return (len(stamps) - 1) / (stamps[-1] - stamps[0]) if len(stamps) > 1 and stamps[-1] > stamps[0] else 0.


class FrameAnalysis:
    """Own exactly one baseline and one model history for the current stream."""
    def __init__(self, model, source, info, output, pool, display_mode="models", minimum_v_step=0., regions=None):
        self.model, self.source, self.info = model, source, info
        self.output, self.pool = output, pool
        self.session = uuid4().hex
        self.baseline = self.pending = self.collect = None
        self.override = False
        self.epoch = 0
        self.source_epoch = None
        self.first_t = None
        self.optical = ()
        if display_mode not in MODE_LABELS:
            raise ValueError(f"Unknown display mode: {display_mode}")
        self.display_mode = display_mode
        self.regions = regions or optical_layout(info.get("optical_rois"), model.layout)
        self.detector = None
        if display_mode in RISE_MODES:
            self.detector = MultiRise(minimum_v_step, spot=display_mode in SPOT_MODES, sustained=display_mode == "multi_slide")
        elif display_mode == "multi_press":
            self.detector = MultiPress(minimum_v_step)
        elif display_mode in {"rod_response", "rapid_tap"}:
            self.detector = RodResponse(minimum_v_step, use_tap_rate=display_mode == "rapid_tap")
        elif display_mode != "models":
            self.detector = OpticalChange(display_mode, minimum_v_step)
        self.change = None

    def reset_history(self):
        self.model.predictor.reset()
        if self.detector:
            self.detector.reset()
        self.change = None
        self.epoch += 1

    def request_baseline(self):
        self.reset_history()
        self.baseline = None
        self.override = True
        self.collect = []
        self.pending = None

    def _fit_baseline(self, frames):
        layout = self.model.layout
        context = BaselineContext(self.info["device"], self.info["backend"], 480, 640,
                                  self.info["controls"], layout.roi_layout_id,
                                  {"minimum_saturation_for_h": 10, "active_delta_v_threshold": 10,
                                   "rotation_degrees_clockwise": 90, "mirror_horizontal": True})
        baseline = capture_baseline([f.image for f in frames], layout.rois, context=context)
        samples = mean_v_samples(frames, layout.rois)
        baseline.camera_settings[NOISE_KEY] = noise_thresholds([f.t for f in frames], samples)
        baseline.camera_settings[PROFILE_KEY] = unloaded_profile(samples)
        baseline.camera_settings[SIGNAL_PROFILE_KEY] = signal_profile(frames, self.regions)
        folder = self.output / "calibrations" / baseline.baseline_id
        save_baseline(baseline, folder / "baseline_summary.json", folder / "baseline_data.npz")
        return baseline

    def analyze(self, frame):
        self.optical = ()
        self.change = None
        if self.first_t is None:
            self.first_t = frame.t
        if not self.override and not self.source.live:
            archived = self.source.baselines.get(frame.baseline_key)
            if archived is not self.baseline or frame.epoch != self.source_epoch:
                self.reset_history()
            self.baseline, self.source_epoch = archived, frame.epoch
        if self.source.live and frame.t - self.first_t < WARMUP_S:
            remaining = WARMUP_S - (frame.t - self.first_t)
            hint = "Baseline armed. Keep the array unloaded." if self.collect is not None else "Let the camera settle."
            return "WARMING UP", f"{remaining:.1f} s · {hint}", None
        if self.pending is not None:
            if not self.pending.done():
                return "CALIBRATING", "Computing the per-pixel unloaded baseline.", None
            self.baseline = self.pending.result()
            self.pending = None
        if self.collect is not None:
            if not self.collect:
                self.baseline_start = frame.t
            self.collect.append(frame)
            elapsed = frame.t - self.baseline_start
            count = len(self.collect)
            if elapsed >= BASELINE_S and count >= MIN_FRAMES:
                self.pending = self.pool.submit(self._fit_baseline, self.collect)
                self.collect = None
            elif count >= 360:
                raise ValueError("Baseline capture exceeded 360 frames without three seconds of valid timestamps")
            return "CALIBRATING", f"Keep unloaded · {min(elapsed, BASELINE_S):.1f}/{BASELINE_S:.0f} s · {count} frames", None
        if self.baseline is None:
            return "CALIBRATION REQUIRED", "Release all taxels, then capture the unloaded baseline.", None
        row = self.model.feature_row(frame.image, self.baseline, self.session, frame.t)
        self.optical = tuple(row[f"roi{i}_positive_delta_mean"] for i in ROI_ORDER)
        r = self.model.predict(row)
        if self.detector:
            self.optical = tuple(row[f"roi{i}_raw_v_mean"] for i in ROI_ORDER)
            center = [roi.mean_v for roi in self.baseline.roi_baselines]
            noise = self.baseline.camera_settings.get(NOISE_KEY, (0.,) * 9)
            if self.display_mode in {"rod_response", "rapid_tap", "multi_press", *RISE_MODES} and PROFILE_KEY in self.baseline.camera_settings:
                profile = self.baseline.camera_settings[PROFILE_KEY]
                center, noise = profile["mean_v_center"], profile["noise_v"]
            custom = self.regions.roi_layout_id != self.model.layout.roi_layout_id
            saved = self.baseline.camera_settings.get(SIGNAL_PROFILE_KEY)
            compatible = saved and saved.get("layout_id") == self.regions.roi_layout_id
            if (custom or self.display_mode in SPOT_MODES) and not compatible:
                self.optical = ()
                return "CALIBRATION REQUIRED", "Capture an unloaded baseline for these optical ROIs and this method.", None
            if custom or self.display_mode in RISE_MODES:
                mean, spot = signal_values(frame.image, self.regions.rois)
                self.optical = tuple(spot if self.display_mode in SPOT_MODES else mean)
                if compatible:
                    profile = saved["spot" if self.display_mode in SPOT_MODES else "mean"]
                    center = profile["mean_v_center"]
                    noise = profile["rise_noise_v" if self.display_mode in RISE_MODES else "noise_v"]
                elif self.display_mode in RISE_MODES:
                    noise = [x*.7 for x in noise]
            self.change = self.detector.update(frame.t, self.optical, center, noise)
            if not self.change.rois:
                return "NO CONFIRMED CONTACT", self.change.detail, r
            names = ", ".join(f"R{i}" for i in self.change.rois)
            if not r["contact"]:
                return "OPTICAL CHANGE ONLY", f"Optical {names} · SVC reports no contact", r
            return "CONTACT DETECTED", f"Optical {names} · SVC positive", r
        if r["contact"]:
            return "CONTACT DETECTED", f"Predicted taxel R{r['localization']}", r
        return "NO CONTACT DETECTED", "Ready for a single-taxel press.", r


class Session:
    def __init__(self, settings, mode, *, record=False, output=OUTPUT, source_factory=None):
        self.settings, self.mode = deepcopy(settings), mode
        self.output, self.record = Path(output), record
        self.source_factory = source_factory
        self.state = View(status="STARTING", detail="Checking the fitted pipelines.")
        self.info, self.models, self.record_path = {}, {}, None
        self.revision, self.request_time = 0, 0.
        self.lock = threading.Lock()
        self.cancel, self.done = threading.Event(), threading.Event()
        self.files_closed = threading.Event()
        self.opened, self.reader_done = threading.Event(), threading.Event()
        self.replay_consumed = threading.Event()
        self.pending = queue.Queue(maxsize=6)
        self.worker = threading.Thread(target=self._run, name="BAURods inference", daemon=True)

    def start(self):
        self.worker.start()

    def view(self):
        with self.lock:
            return self.state.fresh()

    def stop(self, status="STOPPED", detail="Acquisition stopped."):
        self._end(status, detail)

    def _end(self, status, detail):
        with self.lock:
            if not self.cancel.is_set():
                self.state = replace(self.state, status=status, detail=str(detail), result=None, frame=None,
                                     baseline="Inactive", arrived=0.)
                self.cancel.set()

    def request_baseline(self):
        with self.lock:
            if not self.cancel.is_set():
                self.revision += 1
                self.request_time = time.monotonic()
                self.state = replace(self.state, status="CALIBRATING", detail="Keep the array unloaded.",
                                     baseline="Capturing", result=None)

    def _acquire(self, source):
        stamps = deque(maxlen=24)
        previous_source = previous_wall = None
        try:
            if self.cancel.is_set():
                return
            self.info = source.open()
            self.opened.set()
            while not self.cancel.is_set() and not self.ready.wait(.05):
                pass
            while not self.cancel.is_set():
                frame = source.read()
                if frame is None:  # Only a clean file EOF is returned as None.
                    break
                now = time.monotonic()
                if not source.live:
                    due = now if previous_source is None else previous_wall + (frame.t - previous_source)
                    if self.cancel.wait(max(0., due - now)):
                        break
                    now = time.monotonic()
                    previous_source, previous_wall = frame.t, now
                stamps.append(now)
                item = frame, now, rate(stamps)
                if source.live:
                    try:
                        self.pending.put_nowait(item)
                    except queue.Full:
                        raise RuntimeError("Inference queue full. Stream stopped to preserve frame history. Restart after reducing CPU load.")
                else:
                    # File playback may slow down on a busy laptop. It never drops or
                    # bursts through capture history to catch up with the wall clock.
                    self.replay_consumed.clear()
                    self.pending.put_nowait(item)
                    while not self.cancel.is_set() and not self.replay_consumed.wait(.04):
                        pass
        except (ConnectionError, CameraConnectionError) as exc:
            self._end("CAMERA DISCONNECTED", exc)
        except Exception as exc:
            self._end("INPUT ERROR", exc)
        finally:
            try:
                source.close()
            finally:
                self.reader_done.set()
                self.opened.set()

    def _run(self):
        recorder = reader = None
        stage = "MODEL ERROR"
        try:
            model = OpticalModel(self.settings)
            self.models = model.identity
            if self.cancel.is_set():
                return
            if self.source_factory:
                source = self.source_factory(self.settings, model.layout)
            elif self.mode == LIVE:
                source = Camera(self.settings, model.layout)
            else:
                source = Replay(PROJECT_ROOT / self.settings["replay"], model.layout)
            self.ready = threading.Event()
            reader = threading.Thread(target=self._acquire, args=(source,), name="BAURods acquisition", daemon=True)
            reader.start()
            while not self.opened.wait(.05):
                if self.cancel.is_set():
                    return
            if self.cancel.is_set():
                return
            stage = "SETUP ERROR"
            values = self.settings.get("optical_rois") if source.live else self.info.get("optical_rois")
            regions = optical_layout(values, model.layout)
            if self.settings.get("display_mode", "models") == "models":
                regions = model.layout
            self.info.update(optical_rois=layout_values(regions), optical_layout_id=regions.roi_layout_id)
            mapping = effective_mapping(self.settings, self.info)
            atomic_write_json(self.output / "last_acquisition.json", dict(acquisition=self.info, models=self.models,
                              roi_layout=model.layout.to_dict(), optical_roi_layout=regions.to_dict(), physical_mapping=mapping,
                              display_mode=self.settings.get("display_mode", "models"),
                              minimum_v_step=self.settings.get("minimum_v_step", 0.)))
            if self.record:
                stage = "RECORDING ERROR"
                recorded_settings = dict(self.settings, optical_rois=layout_values(regions))
                recorder = SessionRecorder(self.output, recorded_settings, model, self.info, mapping)
                self.record_path = recorder.path
            stage = "PROCESSING ERROR"
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="BAURods baseline") as pool:
                analysis = FrameAnalysis(model, source, self.info, self.output, pool,
                                         self.settings.get("display_mode", "models"),
                                         self.settings.get("minimum_v_step", 0.), regions)
                with self.lock:
                    if not self.cancel.is_set():
                        self.state = View(status="ACQUIRING", detail="Waiting for the first frame.", arrived=time.monotonic())
                self.ready.set()
                self._consume(analysis, mapping, recorder)
        except Exception as exc:
            self._end(stage, f"{type(exc).__name__}: {exc}")
        finally:
            self.cancel.set()
            try:
                if recorder:
                    try:
                        recorder.event(self.state.status, self.state.detail)
                    finally:
                        recorder.close(self.state.status)
            except Exception as exc:
                with self.lock:
                    self.state = View(status="RECORDING ERROR", detail=str(exc))
            finally:
                self.files_closed.set()
                if reader:
                    reader.join()
                self.done.set()

    def _consume(self, analysis, mapping, recorder):
        revision, stale = 0, False
        inference_times = deque(maxlen=24)
        while not self.cancel.is_set():
            try:
                frame, arrived, capture_hz = self.pending.get(timeout=.04)
            except queue.Empty:
                if self.reader_done.is_set():
                    self._end("REPLAY COMPLETE", "Press Start to play the recording again.")
                    return
                if not stale and self.view().status == "STALE INPUT":
                    stale = True
                    if analysis.source.live:
                        analysis.reset_history()
                    if analysis.collect is not None:
                        analysis.collect.clear()
                    if recorder:
                        recorder.event("STALE INPUT", "Frame freshness exceeded 500 ms")
                continue
            with self.lock:
                current, requested = self.revision, self.request_time
            if current != revision:
                analysis.request_baseline()
                inference_times.clear()
                revision = current
            start = time.monotonic()
            if arrived < requested:
                status, detail, result = "CALIBRATING", "Frame preceded calibration request.", None
            else:
                status, detail, result = analysis.analyze(frame)
            finished = time.monotonic()
            if result is not None:
                inference_times.append(finished)
            state = View(status, detail, frame, arrived, result,
                         analysis.baseline.baseline_id if analysis.baseline else "Required",
                         capture_hz, rate(inference_times), 1000 * (finished - start), mapping, analysis.optical, analysis.change)
            with self.lock:
                if self.cancel.is_set():
                    state = replace(state, status=self.state.status, detail=self.state.detail, result=None)
                elif self.revision != revision:
                    state = replace(state, status="CALIBRATING", detail="Baseline reset.", result=None)
                else:
                    self.state = state = state.fresh()
            stale = state.status == "STALE INPUT"
            if stale and analysis.source.live:
                analysis.reset_history()
            if recorder:
                recorder.frame(frame, state, analysis.baseline, analysis.epoch)
            if not analysis.source.live:
                self.replay_consumed.set()
