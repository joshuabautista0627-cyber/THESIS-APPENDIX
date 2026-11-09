"""Compare optical methods on identical pixels and operator-cued camera runs."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

import cv2
import numpy as np
import pandas as pd

from processing.roi_manager import load_roi_layout
from baurods_demo.multi_press import MultiPress
from baurods_demo.multi_rise import MultiRise
from baurods_demo.optical_rois import optical_layout, signal_profile, signal_values
from baurods_demo.sources import Frame


def compare(folder, roi_override=None):
    meta = json.loads((folder/"check.json").read_text())
    note_file = folder/"operator_note.json"
    note = json.loads(note_file.read_text()) if note_file.is_file() else {}
    expected_map = note.get("expected_roi_map", {})
    session = folder/"sessions"/Path(meta["session"]).name
    configuration = json.loads((session/"session.json").read_text())["configuration"]
    layout = optical_layout(roi_override if roi_override is not None else configuration.get("optical_rois"),
                            load_roi_layout(session/"roi_layout.json"))
    log = pd.read_csv(session/"predictions.csv")
    log = log[log.record_type == "frame"].set_index("frame_id")
    clock = pd.read_csv(session/"timestamps.csv")
    calibration = set(log[(log.status == "CALIBRATING") & log.detail.fillna("").str.startswith("Keep unloaded")].index)
    if len(calibration) < 20:
        raise ValueError(f"{folder.name}: need the original unloaded capture frames")
    cap = cv2.VideoCapture(str(session/"session_video.avi"))
    if not cap.isOpened():
        raise OSError("Cannot decode the guided-check recording")
    means, spots, baseline_frames = [], [], []
    try:
        for row in clock.itertuples():
            ok, image = cap.read()
            if not ok:
                raise OSError("Video ended before its recorded timestamps")
            mean, spot = signal_values(image, layout.rois)
            means.append(mean)
            spots.append(spot)
            if row.frame_id in calibration:
                baseline_frames.append(Frame(row.frame_id, row.source_time_s, image, ""))
    finally:
        cap.release()
    profile = signal_profile(baseline_frames, layout)
    methods = {
        "multi_press": (MultiPress(), means, profile["mean"], "noise_v"),
        "multi_v_rise": (MultiRise(), means, profile["mean"], "rise_noise_v"),
        "multi_spot": (MultiRise(spot=True), spots, profile["spot"], "rise_noise_v"),
        "multi_slide": (MultiRise(spot=True, sustained=True), spots, profile["spot"], "rise_noise_v"),
    }
    results = {}
    for name, (detector, signals, calibration_profile, noise_key) in methods.items():
        phases = {}
        for row, values in zip(clock.itertuples(), signals, strict=True):
            before = log.loc[row.frame_id]
            if before.valid != 1:
                continue
            cue = next((e for e in reversed(meta["cues"]) if e["frame"] <= row.frame_id), None)
            if cue is None or cue["phase"] == "end":
                continue
            phase = cue["phase"]
            expected = tuple(map(int, re.findall(r"R([1-9])", phase))) if phase.startswith(("press", "hold", "slide")) else ()
            expected = tuple(sorted(expected_map.get(str(k), k) for k in expected))
            reading = detector.update(row.source_time_s, values, calibration_profile["mean_v_center"], calibration_profile[noise_key])
            active = reading.rois if before.raw_contact == 1 else ()
            counts = phases.setdefault(phase, dict(expected_rois=list(expected), frames=0, exact_set_frames=0,
                                                   extra_roi_frames=0, svc_suppressed_frames=0, active_sets=Counter()))
            counts["frames"] += 1
            counts["active_sets"][str(active)] += 1
            counts["exact_set_frames"] += int(active == expected)
            counts["extra_roi_frames"] += int(bool(set(active)-set(expected)))
            counts["svc_suppressed_frames"] += int(bool(reading.rois) and before.raw_contact != 1)
        results[name] = phases
    return dict(source=str(folder), operator_confirmed=meta["confirmed"], optical_layout_id=layout.roi_layout_id,
                layout_override=roi_override is not None,
                labels="Operator cue windows; these are not frame-exact contact labels or a general accuracy estimate.",
                operator_note=note, baseline_frames=len(baseline_frames), profile=profile, methods=results)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("checks", nargs="+", type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--optical-rois", type=Path, help="Optional nine-rectangle JSON list for retrospective ROI comparison")
    args = p.parse_args()
    rois = json.loads(args.optical_rois.read_text()) if args.optical_rois else None
    results = [compare(folder, rois) for folder in args.checks]
    args.output.write_text(json.dumps(results, indent=2)+"\n", encoding="utf-8")
    for r in results:
        print(Path(r["source"]).name, "confirmed", r["operator_confirmed"])
        for mode, phases in r["methods"].items():
            print(mode, {phase: dict(frames=c["frames"], exact=c["exact_set_frames"], extra=c["extra_roi_frames"])
                         for phase, c in phases.items()})


if __name__ == "__main__":
    main()
