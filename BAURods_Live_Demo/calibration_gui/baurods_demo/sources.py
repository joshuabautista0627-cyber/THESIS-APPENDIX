"""One camera owner, or a timestamped quantitative video, per run."""
from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re

import cv2
import numpy as np

from core.live_sensor_contracts import LIVE_LAYOUT_ID
from core.models import CameraConfig
from processing.roi_manager import load_roi_layout
from services.camera_service import OpenCVCameraService
from .model import archived_baseline, oriented_image

LIVE = "LIVE CAMERA"
REPLAY = "RECORDED VIDEO REPLAY"


@dataclass(frozen=True)
class Frame:
    number: int
    t: float
    image: np.ndarray
    utc: str
    baseline_key: str = ""
    epoch: str = ""


class Camera:
    live = True

    def __init__(self, settings, layout):
        self.settings = settings
        self.service = OpenCVCameraService()
        self.baselines = {}
        self.origin = None

    def open(self):
        index = self.settings["camera_index"]
        mode = self.service.connect(CameraConfig(device_index=index), apply_mode=False)
        if (mode.actual_width, mode.actual_height) != (640, 480):
            raise ValueError(f"Camera {index} reports {mode.actual_width}×{mode.actual_height}; set its driver to 640×480.")
        requested = self.settings["camera_controls"]
        if requested:
            for r in self.service.apply_settings(requested):
                if not r.confirmed:
                    raise ValueError(f"{r.property_name}: {r.message} Disable the override or adjust the driver.")
        actual = {c.property_name: c.current_value for c in self.service.detect_capabilities()
                  if c.readable and c.current_value is not None}
        return dict(mode=LIVE, device=f"{mode.backend}:{index}", backend=mode.backend,
                    resolution=[640, 480], clock="host monotonic", controls=actual,
                    requested_controls=requested, source=mode.source_label, scheduled_baselines=False)

    def read(self):
        frame = self.service.read_frame()
        if frame is None:
            raise ConnectionError(self.service.last_error or "Camera stopped returning frames")
        if self.origin is None:
            self.origin = frame.host_monotonic_ns
        return Frame(frame.source_frame_id, (frame.host_monotonic_ns - self.origin) / 1e9,
                     oriented_image(frame.original_bgr, live=True), frame.wall_clock_iso)

    def close(self):
        self.service.disconnect()


class Replay:
    live = False

    def __init__(self, path, layout):
        self.path = Path(path)
        self.layout = layout
        self.capture = None
        self.baselines = {}
        self.timeline = None
        self.fixed_key = ""
        self.index = 0

    def open(self):
        if not self.path.is_file():
            raise FileNotFoundError(f"Replay video not found: {self.path}")
        if self.path.stem.lower() in {"session_original_overlays", "session_processed", "session_motion_magnified"}:
            raise ValueError("This is a presentation video. Select the unannotated session_video instead.")
        self.capture = cv2.VideoCapture(str(self.path))
        if not self.capture.isOpened():
            raise OSError(f"OpenCV could not decode {self.path}")
        prop = self.capture.get
        size = [int(prop(cv2.CAP_PROP_FRAME_WIDTH)), int(prop(cv2.CAP_PROP_FRAME_HEIGHT))]
        self.fps = prop(cv2.CAP_PROP_FPS)
        self.expected_count = int(prop(cv2.CAP_PROP_FRAME_COUNT))
        folder = self.path.parent
        scheduled = False
        clock = "nominal video FPS (estimated timing)"
        camera = {}
        recorded_mapping = None
        recorded_rois = None
        if self.path.stem == "session_video":
            layout_path = folder / "roi_layout.json"
            if layout_path.exists() and load_roi_layout(layout_path).roi_layout_id != LIVE_LAYOUT_ID:
                raise ValueError("Replay ROI layout differs from the trained layout")
            timeline_path = folder / "timestamps.csv"
            if not timeline_path.exists():
                timeline_path = folder / "master_synchronized.csv"
            if timeline_path.exists():
                self.timeline, scheduled = self._read_clock(timeline_path)
                clock = "recorded capture timestamps"
            if scheduled:
                for key in {row[3] for row in self.timeline if row[3]}:
                    if not re.fullmatch(r"baseline-[a-zA-Z0-9_-]+", key):
                        raise ValueError("Invalid baseline identifier in replay timeline")
                    b = archived_baseline(folder / "baselines" / key, self.layout)
                    if b.baseline_id != key:
                        raise ValueError("Replay baseline ID differs from its timeline")
                    self.baselines[key] = b
            elif any((folder / f).exists() for f in ("baseline_data.npz", "baseline_summary.json")):
                b = archived_baseline(folder, self.layout)
                self.fixed_key = b.baseline_id
                self.baselines[b.baseline_id] = b
            if (folder / "camera_settings.json").is_file():
                camera = json.loads((folder / "camera_settings.json").read_text(encoding="utf-8"))
            if (folder / "session.json").is_file():
                recorded = json.loads((folder / "session.json").read_text(encoding="utf-8"))
                recorded_mapping = recorded.get("physical_mapping")
                recorded_rois = recorded.get("configuration", {}).get("optical_rois")
                camera = recorded.get("acquisition", camera)
        if self.timeline is None and not (math.isfinite(self.fps) and self.fps > 0):
            raise ValueError("Replay requires capture timestamps or a valid video frame rate")
        if self.timeline is not None and self.expected_count > 0 and self.expected_count != len(self.timeline):
            raise ValueError(f"Video has {self.expected_count} frames, timing file has {len(self.timeline)} rows")
        return dict(mode=REPLAY, device=str(self.path.resolve()), backend="OpenCV video",
                    source=self.path.name, resolution=size, clock=clock,
                    controls=camera.get("controls", {}), scheduled_baselines=scheduled,
                    recorded_mapping=recorded_mapping, optical_rois=recorded_rois)

    @staticmethod
    def _read_clock(path):
        records = []
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            # Only optical frame IDs and clocks are consumed from an acquisition master.
            legacy = "elapsed_time_s" in fields
            for i, row in enumerate(reader):
                t = float(row["elapsed_time_s" if legacy else "source_time_s"])
                n = int(row["capture_frame_id" if legacy else "frame_id"])
                if not math.isfinite(t) or (records and (t <= records[-1][1] or n <= records[-1][0])):
                    raise ValueError(f"Invalid capture ID or timestamp at video frame {i}")
                records.append((n, t, row.get("wall_clock_iso", ""), row.get("baseline_id", ""), row.get("history_epoch", "")))
        if not records:
            raise ValueError("Empty replay timing file")
        return records, not legacy and "baseline_id" in fields

    def read(self):
        ok, raw = self.capture.read()
        i = self.index
        if not ok:
            expected = len(self.timeline) if self.timeline is not None else self.expected_count
            if i == 0 or (expected > 0 and i != expected):
                raise OSError(f"Replay decode stopped at frame {i} of {expected}")
            return None
        if self.timeline is None:
            n, t, utc, key, epoch = i, i / self.fps, "", self.fixed_key, ""
        else:
            if i >= len(self.timeline):
                raise ValueError("Video outlasted its capture timestamp file")
            n, t, utc, key, epoch = self.timeline[i]
        self.index += 1
        return Frame(n, t, oriented_image(raw), utc, key or self.fixed_key, epoch)

    def close(self):
        if self.capture is not None:
            self.capture.release()
