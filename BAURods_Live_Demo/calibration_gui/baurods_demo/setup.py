"""Repeatable setup and operator-verified top-view orientation."""
import json
import math
from pathlib import Path

import numpy as np

from core.live_sensor_contracts import LIVE_LAYOUT_ID
from scripts.live_sensor_common import PROJECT_ROOT, atomic_write_json, utc_now_iso
from .sources import LIVE
from .optical_change import MODE_LABELS

DEFAULTS = PROJECT_ROOT / "config/baurods_demo.json"
OUTPUT = PROJECT_ROOT / "output/baurods_demo"
SAMPLE = PROJECT_ROOT / "assets/baurods_demo_replay"
ROI_ORDER = tuple(range(1, 10))


def load_setup(output=OUTPUT):
    settings = json.loads(DEFAULTS.read_text(encoding="utf-8"))
    saved = Path(output) / "setup.json"
    if saved.is_file():
        overrides = json.loads(saved.read_text(encoding="utf-8"))
        if not isinstance(overrides, dict):
            raise ValueError("Invalid saved demo setup")
        settings.update({k: v for k, v in overrides.items() if k in settings})
    step = settings["minimum_v_step"]
    if (settings["display_mode"] not in MODE_LABELS or not isinstance(step, (int, float))
            or not math.isfinite(step) or not 0 <= step <= 255):
        raise ValueError("Invalid contact display rule or minimum optical step")
    return settings


def save_setup(settings, output=OUTPUT):
    atomic_write_json(Path(output) / "setup.json", settings)


def check_mapping(values):
    cells = tuple(values)
    grid = np.arange(1, 10).reshape(3, 3)
    orientations = {tuple(np.rot90(a, k).ravel()) for a in (grid, grid[:, ::-1]) for k in range(4)}
    if cells not in orientations:
        raise ValueError("The nine ROIs must form one rotation or reflection of the array. Recheck the marks and camera alignment.")
    return cells


def verified_mapping(values, device, layout_id=LIVE_LAYOUT_ID):
    return dict(cells=list(check_mapping(values)), verified_utc=utc_now_iso(),
                device=device, layout_id=layout_id)


def effective_mapping(settings, acquisition):
    m = settings.get("physical_mapping") if acquisition["mode"] == LIVE else acquisition.get("recorded_mapping")
    if not m or m.get("layout_id") != acquisition.get("optical_layout_id", LIVE_LAYOUT_ID) or not m.get("verified_utc"):
        return None
    if acquisition["mode"] == LIVE and m.get("device") != acquisition["device"]:
        return None
    check_mapping(m["cells"])
    return m
