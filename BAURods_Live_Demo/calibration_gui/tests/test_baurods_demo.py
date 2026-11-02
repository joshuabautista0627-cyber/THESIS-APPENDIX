"""Defense-demo acceptance checks using real clips and an injected USB interruption."""
import csv
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PySide6.QtWidgets import QApplication

from baurods_demo.model import OpticalModel, load_selected, oriented_image
from baurods_demo.light_check import LightCheckWindow
from baurods_demo.optical_change import NOISE_KEY, OpticalChange
from baurods_demo.recording import SessionRecorder
from baurods_demo.rod_response import PROFILE_KEY, RodResponse, unloaded_profile
from baurods_demo.runtime import FrameAnalysis, Session, View
from baurods_demo.setup import (DEFAULTS, SAMPLE, check_mapping, effective_mapping, load_setup,
                               save_setup, verified_mapping)
from baurods_demo.sources import Frame, LIVE, REPLAY, Replay
from baurods_demo.window import Window
from baurods_demo.widgets import MappingDialog
from scripts.live_sensor_common import PROJECT_ROOT

CLIP = SAMPLE / "center_press/session_video.mp4"


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.settings = json.loads(DEFAULTS.read_text())
        cls.model = OpticalModel(cls.settings)

    def wait_until(self, predicate, seconds=5):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.008)
        self.fail("Timed out waiting for the expected state")

    def test_geometry_and_all_nine_mappings(self):
        layout = self.model.layout
        raw = np.zeros((480, 640, 3), np.uint8)
        for r in layout.rois:
            raw[r.x:r.x+r.width, r.y:r.y+r.height] = r.roi_id
        oriented = oriented_image(raw, live=True)
        for r in layout.rois:
            self.assertTrue(np.all(oriented[r.y:r.y+r.height, r.x:r.x+r.width] == r.roi_id))
        np.testing.assert_array_equal(oriented_image(oriented), oriented)
        for invalid in [None, raw.astype(float), raw[:100], oriented]:
            with self.assertRaises(ValueError):
                oriented_image(invalid, live=True)
        mirror = [3, 2, 1, 6, 5, 4, 9, 8, 7]
        m = verified_mapping(mirror, "DirectShow:2")
        settings = dict(self.settings, physical_mapping=m)
        with tempfile.TemporaryDirectory() as folder:
            save_setup(settings, folder)
            loaded = load_setup(folder)
            self.assertEqual(effective_mapping(loaded, dict(mode=LIVE, device="DirectShow:2"))["cells"], mirror)
            self.assertIsNone(effective_mapping(loaded, dict(mode=LIVE, device="DirectShow:0")))
            self.assertIsNone(effective_mapping(loaded, dict(mode=REPLAY)))
        v = View(mapping=m)
        for i, r in enumerate(mirror):
            active = replace(v, result={"contact": 1, "localization": r})
            self.assertEqual(active.cells.index(active.active), i)
            self.assertIsNone(replace(active, result={"contact": 0, "localization": r}).active)
        for invalid in [[1]*9, [2, 1, 3, 4, 5, 6, 7, 8, 9]]:
            with self.assertRaises(ValueError):
                check_mapping(invalid)

    def test_missing_incompatible_models_and_invalid_geometry_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            s = Session(dict(self.settings, model_run=folder), REPLAY, output=folder)
            s.start()
            self.assertTrue(s.done.wait(6))
            self.assertEqual(s.view().status, "MODEL ERROR")
            self.assertIsNone(s.view().active)
            self.assertIn("manifest.json", s.view().detail)
        with patch("baurods_demo.model.joblib.load") as load:
            fit = dict(self.model.specs["contact"]["loaded_members"][0])
            import copy
            fit["scaler"] = copy.deepcopy(fit["scaler"])
            fit["scaler"].n_features_in_ = 89
            load.return_value = fit
            with self.assertRaisesRegex(ValueError, "expected 90"):
                load_selected(PROJECT_ROOT / self.settings["model_run"])
        clock_rows = "frame_id,source_time_s\n0,0.2\n1,0.1\n"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "timestamps.csv"
            path.write_text(clock_rows)
            with self.assertRaisesRegex(ValueError, "timestamp"):
                Replay._read_clock(path)

    def test_mapping_wizard_requires_nine_observations(self):
        saved = []
        dialog = MappingDialog(None, self.model.layout, lambda cells: saved.append(cells) or True)
        dialog.fresh = True
        dialog.accept_observation()
        self.assertEqual(dialog.observations, [])
        order = [7, 4, 1, 8, 5, 2, 9, 6, 3]
        for i in order:
            dialog.observed.setCurrentIndex(i)
            dialog.accept_observation()
            if len(dialog.observations) == 1:
                dialog.observed.setCurrentIndex(i)
                dialog.accept_observation()
                self.assertEqual(len(dialog.observations), 1)
        self.assertEqual(saved, [])
        dialog.accept_observation()
        self.assertEqual(saved, [tuple(order)])

    def test_live_calibration_warmup_and_recapture(self):
        with tempfile.TemporaryDirectory() as temp, ThreadPoolExecutor(1) as pool:
            class LiveSource:
                live = True
            model = self.model
            model.predictor.reset()
            a = FrameAnalysis(model, LiveSource(), dict(device="fixture", backend="fixture", controls={}), Path(temp), pool)
            image = np.zeros((640, 480, 3), np.uint8)
            def feed(t, value=0):
                return a.analyze(Frame(round(t*100), t, image + value, ""))
            self.assertEqual(feed(0)[0], "WARMING UP")
            self.assertEqual(feed(3.1)[0], "CALIBRATION REQUIRED")
            a.request_baseline()
            for i in range(25):
                self.assertEqual(feed(3.2+i/8, i%2)[0], "CALIBRATING")
            a.pending.result(timeout=10)
            _, _, result = feed(6.4)
            self.assertIsNotNone(result)
            self.assertEqual(a.baseline.roi_baselines[0].valid_frame_count, 25)
            self.assertEqual(a.baseline.camera_settings[NOISE_KEY], [0.] * 9)
            self.assertEqual(a.baseline.camera_settings[PROFILE_KEY]["mean_v_center"], [0.] * 9)
            self.assertTrue(np.all(a.baseline.roi_baselines[0].median_v_image == 0))
            self.assertTrue((Path(temp)/"calibrations"/a.baseline.baseline_id/"baseline_summary.json").is_file())
            a.request_baseline()
            self.assertIsNone(a.baseline)
            self.assertIsNone(model.predictor.timestamp)
            self.assertIsNone(feed(6.5)[2])

    def test_local_edge_selects_all_nine_without_relabeling_raw_predictions(self):
        idle = np.full(9, 40.)
        for mode, step in [("v_rise", 4), ("v_drop", -38)]:
            for i in range(9):
                detector = OpticalChange(mode)
                changed = idle.copy()
                changed[i] += step
                def feed(t, values):
                    return detector.update(t, values, idle, np.zeros(9))
                for t in (0, .07, .14, .21):
                    self.assertIsNone(feed(t, idle).roi)
                first = feed(.28, changed)
                self.assertEqual(first.roi, None if mode == "v_drop" else i+1)
                feed(.35, changed)
                feed(.42, changed)
                reading = feed(.49, changed)
                self.assertEqual(reading.roi, i+1)
                state = View(change=reading, result={"localization": 9, "contact": 1})
                self.assertEqual(state.active, i+1)
                self.assertEqual(state.result["localization"], 9)
                self.assertIsNone(replace(state, result={"localization": 9, "contact": 0}).active)
                self.assertIsNone(feed(.56, idle).roi)
                self.assertIsNone(feed(1.1, changed).roi)

    def test_static_glare_global_light_ambiguity_and_timeout(self):
        ref = np.full(9, 20.)
        x = ref.copy()
        x[-2:] += 35
        detector = OpticalChange("v_rise")
        def feed(t, data):
            return detector.update(t, data, ref, np.zeros(9))
        for i in range(20):
            self.assertIsNone(feed(.1*i, x + (10 if i >= 10 else 0)).roi)
        detector.reset()
        for t in (0, .1, .2, .3):
            feed(t, ref)
        tied = ref.copy()
        tied[:2] += 3
        self.assertIsNone(feed(.4, tied).roi)
        one = ref.copy()
        one[5] += 5
        self.assertEqual(feed(.5, one).roi, 6)
        for i in range(6, 51):
            last = feed(i/10, one)
        self.assertIsNone(last.roi)
        self.assertIn("release", last.detail)
        self.assertIsNone(feed(5.1, ref).roi)

    def test_approach_shadow_waits_for_sustained_roi_and_ignores_release_motion(self):
        b = np.full(9, 10.)
        gate = OpticalChange("v_drop")
        seen = []
        for i in range(30):
            v = b.copy()
            if i == 7:             # A neighbor goes dark one frame before the real press.
                v[8] = .5
            if 8 <= i < 18:
                v[8], v[7] = 3., .3
            if 20 <= i <= 29:      # Broad partial shadows after release.
                v[2], v[8] = 3.5, 3.
            seen.append(gate.update(i/15, v, b, np.zeros(9)).roi)
        self.assertEqual(set(seen), {None, 8})
        self.assertIsNone(seen[7])
        self.assertTrue(all(k is None for k in seen[18:]))

    def test_restore_recorded_display_rule_preserves_live_preference(self):
        with tempfile.TemporaryDirectory() as temp:
            save_setup(dict(self.settings, display_mode="v_drop", minimum_v_step=2.), temp)
            folder = Path(temp)
            (folder/"session.json").write_text(json.dumps(dict(configuration=dict(display_mode="v_rise", minimum_v_step=.8))))
            w = Window(output=temp, replay=folder/"session_video.avi")
            self.assertEqual((w.rule.currentData(), w.minimum_v_step), ("v_rise", .8))
            w.mode.setCurrentText(LIVE)
            self.assertEqual((w.rule.currentData(), w.minimum_v_step), ("v_drop", 2.))
            w.close()

    def test_rod_response_accepts_slow_brightening_and_uses_current_light_to_release(self):
        base = np.full(9, 20.)
        for roi in range(1, 10):
            det = RodResponse()
            seen = []
            # Every short interval rises less than the original 0.6-V edge threshold.
            levels = [0.]*8 + [i*.035 for i in range(35)] + [1.225]*110 + [0.]
            for i, added in enumerate(levels):
                values = base.copy()
                values[roi-1] += added
                reading = det.update(i*.05, values, base, np.zeros(9))
                seen.append(reading.roi)
                if reading.roi is not None:
                    self.assertEqual(reading.direction, "rise")
                    self.assertIsNone(View(change=reading, result={"contact": 0, "localization": 9}).active)
            self.assertEqual(set(seen), {None, roi})
            self.assertEqual(seen[-10:-1], [roi]*9)
            self.assertIsNone(seen[-1])
            values[roi-1] += 2
            self.assertIsNone(det.update(12., values, base, np.zeros(9)).roi)

    def test_rod_response_separates_a_black_tip_from_dimmer_neighbors(self):
        ref = np.array([9., 12., 15., 11.5, 16., 12., 7., 9., 10.])
        det = RodResponse()
        seen = []
        for i in range(52):
            values = ref.copy()
            if 12 <= i < 32:
                # R8 loses more V in absolute terms than R7, but still transmits light.
                values *= [.81, .77, .68, .53, .18, .11, 0., .035, .14]
            reading = det.update(i/15, values, ref, np.zeros(9))
            seen.append(reading.roi)
            if reading.roi:
                self.assertEqual(reading.direction, "drop")
        self.assertEqual(set(seen), {None, 7})
        self.assertTrue(all(v is None for v in seen[32:]))

    def test_rod_response_rejects_common_lighting_and_unstable_calibration_prefix(self):
        b = np.arange(1, 10, dtype=float)*4
        calibration = np.tile(b, (45, 1))
        calibration[:4, 8] -= 9
        profile = unloaded_profile(calibration)
        np.testing.assert_array_equal(profile["mean_v_center"], b)
        np.testing.assert_array_equal(profile["noise_v"], np.zeros(9))
        for transform in (lambda x: x*1.5, lambda x: x+5., lambda x: x*.02):
            d = RodResponse()
            for i in range(40):
                v = b if i < 8 or i > 29 else transform(b)
                self.assertIsNone(d.update(i/15, v, b, np.zeros(9)).roi)

    def test_rapid_v_tap_confirms_faint_rods_and_rearms_after_release(self):
        base = np.array([3., 3.2, 2.8, 2.4, 2.6, 1.6, 1.4, 1.2, .7])
        noise = np.zeros(9)
        for hz in (10, 15, 25):
            for k in (6, 7, 8):
                detector = RodResponse(use_tap_rate=True)
                readings = []
                for i in range(4 * hz):
                    v = base.copy()
                    if hz <= i < 2 * hz:
                        v[k] = .005
                    elif i == 3 * hz:
                        v[k] += 2.
                    readings.append(detector.update(i/hz, v, base, noise))
                self.assertEqual({r.roi for r in readings[hz:2*hz]}, {None, k+1})
                self.assertEqual(readings[2*hz-1].direction, "drop")
                self.assertTrue(all(r.roi is None for r in readings[2*hz:3*hz]))
                flash = readings[3*hz]
                self.assertEqual((flash.roi, flash.direction, flash.detail), (k+1, "rise", "Rapid local V rise"))
                self.assertGreater(flash.rate_v_s, 0.)
                self.assertIsNone(View(result={"contact": 0}, change=flash).active)

    def test_rapid_v_tap_rejects_lighting_ambiguity_gaps_and_subthreshold_steps(self):
        b = np.array([3., 3.2, 2.8, 2.4, 2.6, 1.6, 1.4, 1.2, .7])
        near_black = b.copy()
        near_black[8] = .01
        two_rods = near_black.copy()
        two_rods[7] = .01
        for changed, floor, gap in [(two_rods, 0., 0.), (b*.03, 0., 0.), (b+4., 0., 0.),
                                    (np.maximum(0., b-.7), 0., 0.), (near_black, 1., 0.),
                                    (near_black, 0., .45)]:
            detector = RodResponse(floor, use_tap_rate=True)
            for i in range(35):
                t = i/15 + (gap if i >= 15 else 0.)
                self.assertIsNone(detector.update(t, b if i < 15 else changed, b, np.zeros(9)).roi)

    def test_reopenable_check_waits_for_start_and_records_operator_cues(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_setup(dict(self.settings, display_mode="v_drop", camera_index=3), tmp)
            s = Mock()
            s.cancel, s.done = threading.Event(), threading.Event()
            s.info, s.models, s.record_path, s.record = {}, {}, Path(tmp)/"sessions"/"trial", True
            s.view.return_value = View()
            s.stop.side_effect = lambda: (s.cancel.set(), s.done.set())
            factory = Mock(return_value=s)
            w = LightCheckWindow(output=tmp, session_factory=factory)
            w.timer.stop()
            w.cue_timer.stop()
            w.show()
            self.assertIsNone(w.session)
            self.assertEqual(w.rule.currentData(), "rapid_tap")
            w.check_button.click()
            self.assertTrue(factory.call_args.kwargs["record"])
            frame = Frame(63, 4.2, np.zeros((640, 480, 3), np.uint8), "")
            s.view.return_value = View(status="CALIBRATION REQUIRED", frame=frame)
            w.tick()
            s.request_baseline.assert_called_once()
            s.view.return_value = View(frame=frame, result={"contact": 0, "localization": 7, "contact_score": .1})
            elapsed = 0.
            for phase, duration, _ in w.plan:
                w.origin = time.monotonic() - elapsed - .02
                w.tick()
                self.assertEqual(w.events[-1]["phase"], phase)
                elapsed += duration
            w.origin = time.monotonic() - elapsed - .02
            w.tick()
            self.assertEqual(w.stage, "finished")
            w.check_button.click()
            record = json.loads((w.output/"check.json").read_text())
            self.assertTrue(record["confirmed"])
            self.assertEqual(len(record["cues"]), len(w.plan)+1)
            self.assertFalse(w.isVisible())
            demo = w.demo_window
            self.assertTrue(demo.isVisible() and demo.start_button.isVisible() and demo.record.isVisible())
            self.assertTrue(demo.start_button.isEnabled())
            self.assertIsNone(demo.session)
            self.assertEqual((demo.output, demo.rule.currentData(), demo.index.value()), (Path(tmp), "v_drop", 3))
            demo.close()

    def test_uncertain_light_check_waits_for_camera_release_before_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = LightCheckWindow(output=tmp)
            w.show()
            s = Mock()
            s.cancel, s.done = threading.Event(), threading.Event()
            s.view.return_value, s.info, s.models, s.record_path = View(), {}, {}, None
            s.stop.side_effect = s.cancel.set
            w.session, w.stage = s, "finished"
            w.demo_button.click()
            self.assertTrue(s.cancel.is_set() and w.isVisible())
            self.assertIsNone(w.demo_window)
            self.assertFalse(json.loads((w.output/"check.json").read_text())["confirmed"])
            s.done.set()
            w.tick()
            demo = w.demo_window
            self.assertTrue(demo.isVisible())
            w.tick()
            self.assertIs(w.demo_window, demo)
            demo.close()

    def test_optical_record_and_replay_keeps_raw_and_displayed_taxels_separate(self):
        self.check_optical_round_trip("v_rise", 15)

    def test_rapid_tap_recording_restores_display_rule_and_signed_rates(self):
        self.check_optical_round_trip("rapid_tap", 12)

    def check_optical_round_trip(self, mode, displayed_frames):
        settings = dict(self.settings, display_mode=mode)
        with tempfile.TemporaryDirectory() as folder, ThreadPoolExecutor(1) as pool:
            recorded = None
            for take in range(2):
                source = Replay(CLIP if take == 0 else recorded / "session_video.avi", self.model.layout)
                writer = None
                actual = []
                try:
                    info = source.open()
                    analysis = FrameAnalysis(self.model, source, info, Path(folder), pool, mode)
                    if take == 0:
                        writer = SessionRecorder(folder, settings, self.model, info, None)
                        recorded = writer.path
                    while (frame := source.read()) is not None:
                        status, detail, raw = analysis.analyze(frame)
                        state = View(status, detail, frame, time.monotonic(), raw, change=analysis.change)
                        actual.append((raw["contact"], raw["localization"], state.active, state.change.rate_v_s))
                        if writer:
                            writer.frame(frame, state, analysis.baseline, analysis.epoch)
                finally:
                    source.close()
                    if writer:
                        writer.close("REPLAY COMPLETE")
                if take == 0:
                    original = actual
                else:
                    self.assertEqual(actual, original)
            with (recorded/"predictions.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(sum(row["raw_contact"] == "1" for row in rows), 79)
            self.assertEqual(sum(row["displayed_contact"] == "1" for row in rows), displayed_frames)
            self.assertEqual({row["displayed_taxel"] for row in rows}, {"", "5"})
            self.assertTrue(all(row["display_mode"] == mode and row["optical_state"] for row in rows))
            if mode == "rapid_tap":
                self.assertTrue(any(float(row["optical_v_per_s"]) > 0 for row in rows if row["optical_v_per_s"]))
                window = Window(output=folder, replay=recorded/"session_video.avi")
                self.assertEqual(window.rule.currentData(), mode)
                window.close()

    def test_stall_disconnect_and_immediate_stop(self):
        unblock = threading.Event()
        class Stalled(Replay):
            def open(self):
                import cv2
                info = super().open()
                # A real press frame with a positive cold-start SVC decision.
                self.capture.set(cv2.CAP_PROP_POS_FRAMES, 94)
                self.index = 94
                return info

            def read(self):
                if self.index > 94:
                    unblock.wait(5)
                    raise ConnectionError("test cable disconnected")
                return super().read()
        with tempfile.TemporaryDirectory() as folder:
            s = Session(self.settings, REPLAY, output=folder, record=True,
                        source_factory=lambda _, layout: Stalled(CLIP, layout))
            s.start()
            try:
                self.wait_until(lambda: s.view().active is not None)
                self.wait_until(lambda: s.view().status == "STALE INPUT", 2)
                self.assertIsNone(s.view().active)
                time.sleep(.09)  # allow the worker's independent watchdog to log the transition
            finally:
                unblock.set()
            self.assertTrue(s.done.wait(4))
            self.assertEqual(s.view().status, "CAMERA DISCONNECTED")
            self.assertIsNone(s.view().active)
            with (s.record_path/"predictions.csv").open() as f:
                states = [row["status"] for row in csv.DictReader(f)]
            self.assertIn("STALE INPUT", states)
            self.assertEqual(states[-1], "CAMERA DISCONNECTED")

    def test_replay_gui_export_reopen_and_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            w = Window(output=folder, replay=CLIP)
            w.resize(1024, 690)
            w.show()
            w.record.setChecked(True)
            w.start_button.click()
            s = w.session
            states = set()
            highlights = set()
            ticks = []
            def observe():
                ticks.append(time.monotonic())
                states.add(w.status.text())
                active = [cell.text() for cell in w.taxels if cell.property("active")]
                self.assertLessEqual(len(active), 1)
                if active:
                    self.assertEqual(w.status.text(), "CONTACT DETECTED")
                    highlights.update(active)
                return s.done.is_set()
            try:
                self.wait_until(observe, 40)
                w.refresh()
                self.assertEqual(w.status.text(), "REPLAY COMPLETE", s.view().detail)
                self.assertIn("R5", highlights)
                self.assertIn("NO CONTACT DETECTED", states)
                self.assertFalse(any(c.property("active") for c in w.taxels))
                self.assertLess(max(np.diff(ticks)), .5)
                path = s.record_path
                with (path/"predictions.csv").open() as f:
                    rows = [row for row in csv.DictReader(f) if row["record_type"] == "frame"]
                self.assertEqual(len(rows), 160)
                self.assertEqual(sum(row["displayed_taxel"] != "" for row in rows), 79)
                self.assertTrue(all(row["raw_taxel"] and row["contact_decision_score"] for row in rows))
                self.assertTrue(all(row["displayed_taxel"] == (row["raw_taxel"] if row["raw_contact"] == "1" else "") for row in rows))
                self.assertEqual(json.loads((path/"session.json").read_text())["status"], "REPLAY COMPLETE")
                # Round-trip the actual FFV1 output, per-frame clocks and per-baseline archives.
                copy, original = Replay(path/"session_video.avi", self.model.layout), Replay(CLIP, self.model.layout)
                self.model.predictor.reset()
                try:
                    copy.open()
                    original.open()
                    for row in rows:
                        a, b = copy.read(), original.read()
                        self.assertEqual((a.number, a.t, a.baseline_key), (b.number, b.t, b.baseline_key))
                        np.testing.assert_array_equal(a.image, b.image)
                        r = self.model.predict(self.model.feature_row(a.image, copy.baselines[a.baseline_key], "roundtrip", a.t))
                        self.assertEqual((r["contact"], r["localization"], r["contact_score"]),
                                         (int(row["raw_contact"]), int(row["raw_taxel"]), float(row["contact_decision_score"])))
                    self.assertIsNone(copy.read())
                finally:
                    copy.close()
                    original.close()
                w.record.setChecked(False)
                w.start_button.click()
                self.wait_until(lambda: w.session.view().result is not None)
                w.capture_baseline()
                self.assertIsNone(w.session.view().result)
                w.fullscreen()
                self.assertTrue(w.isFullScreen())
                w.leave_fullscreen()
                w.stop_button.click()
                self.assertEqual(w.status.text(), "STOPPED")
                self.assertFalse(any(c.property("active") for c in w.taxels))
                self.assertTrue(w.session.done.wait(4))
                print(f"GUI: {len(ticks)} event-loop probes, longest interval {1000*max(np.diff(ticks)):.0f} ms")
            finally:
                w.close()
                if w.session:
                    w.session.done.wait(5)


if __name__ == "__main__":
    unittest.main()
