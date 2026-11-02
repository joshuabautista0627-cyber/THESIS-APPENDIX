"""Lossless, unannotated replay plus an append-only model/validity trace."""
import csv
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2

from processing.baseline import save_baseline
from scripts.live_sensor_common import atomic_write_json, utc_now_iso
from .setup import ROI_ORDER

TIMING = ["frame_id", "source_time_s", "wall_clock_iso", "baseline_id", "history_epoch"]
FIELDS = ["record_type", *TIMING, "logged_utc", "status", "valid", "detail", "raw_contact",
          "contact_decision_score", "raw_taxel", *[f"localization_score_R{i}" for i in ROI_ORDER],
          "displayed_contact", "displayed_taxel", "displayed_grid_position", "grid_view",
          "processing_ms", "frame_age_ms", "capture_hz", "inference_hz", "display_mode",
          "optical_roi", "local_change_v", "change_threshold_v", "optical_state", "optical_direction", "optical_v_per_s"]


class SessionRecorder:
    def __init__(self, output, settings, model, acquisition, mapping):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = Path(output) / "sessions" / f"{stamp}_{uuid4().hex[:8]}"
        self.path.mkdir(parents=True)
        self.meta = dict(started_utc=utc_now_iso(), status="OPEN", configuration=settings,
                         acquisition=acquisition, models=model.identity, physical_mapping=mapping,
                         video="lossless FFV1; unannotated oriented BGR; use timestamps.csv for playback",
                         presentation_filter=settings.get("display_mode", "models"), frames=0)
        self.video = self.log_stream = self.clock_stream = None
        self.baselines = set()
        try:
            atomic_write_json(self.path / "roi_layout.json", model.layout.to_dict())
            atomic_write_json(self.path / "session.json", self.meta)
            self.video = cv2.VideoWriter(str(self.path / "session_video.avi"),
                                         cv2.VideoWriter_fourcc(*"FFV1"), 30, (480, 640))
            if not self.video.isOpened():
                raise OSError("FFV1 lossless recording unavailable. Disable recording or install the pinned OpenCV build.")
            self.log_stream = (self.path / "predictions.csv").open("x", newline="", encoding="utf-8")
            self.clock_stream = (self.path / "timestamps.csv").open("x", newline="", encoding="utf-8")
            self.log = csv.DictWriter(self.log_stream, fieldnames=FIELDS)
            self.clock = csv.DictWriter(self.clock_stream, fieldnames=TIMING)
            self.log.writeheader()
            self.clock.writeheader()
        except Exception:
            self.close("RECORDING ERROR")
            raise

    def frame(self, frame, state, baseline, epoch):
        key = baseline.baseline_id if baseline is not None and state.result else ""
        if key and key not in self.baselines:
            folder = self.path / "baselines" / key
            save_baseline(baseline, folder / "baseline_summary.json", folder / "baseline_data.npz")
            self.baselines.add(key)
        timing = dict(zip(TIMING, (frame.number, frame.t, frame.utc, key, epoch), strict=True))
        self.video.write(frame.image)
        self.clock.writerow(timing)
        row = dict(**timing, record_type="frame", logged_utc=utc_now_iso(), status=state.status,
                   valid=int(state.result is not None), detail=state.detail, processing_ms=state.ms,
                   frame_age_ms=state.age_ms(), capture_hz=state.capture_hz, inference_hz=state.inference_hz,
                   display_mode=self.meta["presentation_filter"])
        if state.result:
            r = state.result
            row.update(raw_contact=r["contact"], contact_decision_score=r["contact_score"], raw_taxel=r["localization"],
                       displayed_contact=int(state.active is not None), displayed_taxel=state.active or "",
                       displayed_grid_position=(state.cells.index(state.active) + 1 if state.active else ""),
                       grid_view="verified physical" if state.mapping else "trained ROI order")
            row.update({f"localization_score_R{i}": x for i, x in zip(ROI_ORDER, r["localization_scores"], strict=True)})
            if state.change is not None:
                row.update(optical_roi=state.change.roi or "", local_change_v=state.change.change_v,
                           change_threshold_v=state.change.threshold_v, optical_state=state.change.detail,
                           optical_v_per_s=state.change.rate_v_s,
                           optical_direction=state.change.direction or
                           ({"v_rise": "rise", "v_drop": "drop"}.get(row["display_mode"], "") if state.change.roi else ""))
        self.log.writerow(row)
        self.meta["frames"] += 1
        if self.meta["frames"] % 10 == 0:
            self.log_stream.flush()
            self.clock_stream.flush()

    def event(self, status, detail):
        self.log.writerow(dict(record_type="event", logged_utc=utc_now_iso(), status=status, detail=detail, valid=0))
        self.log_stream.flush()

    def close(self, status):
        if self.video is not None:
            self.video.release()
        for stream in (self.log_stream, self.clock_stream):
            if stream:
                stream.close()
        self.meta.update(status=status, ended_utc=utc_now_iso())
        atomic_write_json(self.path / "session.json", self.meta)
