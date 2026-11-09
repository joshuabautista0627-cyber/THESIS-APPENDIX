"""Compare displayed taxels with raw model outputs on replay and optional numeric camera traces."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from baurods_demo.model import OpticalModel
from baurods_demo.multi_press import MultiPress
from baurods_demo.multi_rise import MultiRise
from baurods_demo.optical_rois import RISE_MODES, SPOT_MODES
from baurods_demo.optical_change import NOISE_KEY, RESET_GAP_S, OpticalChange, noise_thresholds
from baurods_demo.rod_response import PROFILE_KEY, RodResponse, unloaded_profile
from baurods_demo.runtime import FrameAnalysis, View
from baurods_demo.setup import DEFAULTS, SAMPLE
from baurods_demo.sources import Replay


def trace_report(path, mode):
    if mode in SPOT_MODES:
        raise ValueError("Bright-spot measurement requires pixels; use a recorded video with a matching unloaded profile")
    combined = mode in {"rod_response", "rapid_tap", "multi_press", *RISE_MODES}
    frame = pd.read_csv(path)
    phase = frame["phase"] if "phase" in frame else frame["part"]
    times = frame["capture_monotonic_relative_s" if "capture_monotonic_relative_s" in frame else "t"].to_numpy()
    means = frame[[f"roi{i}_raw_v_mean" for i in range(1, 10)]].to_numpy()
    cal = phase.eq("baseline").to_numpy()
    if cal.any():
        if cal.all() or not np.array_equal(np.flatnonzero(cal), np.arange(cal.sum())):
            raise ValueError("Expected a contiguous unloaded calibration prefix and subsequent test rows")
        reference = means[cal].mean(axis=0)
        noise = noise_thresholds(times[cal], means[cal])
        if combined:
            profile = unloaded_profile(means[cal])
            reference, noise = profile["mean_v_center"], profile["noise_v"]
    else:
        # The native GUI trace starts at READY. Read that run's own unloaded calibration.
        key = json.loads((path.parent/"source.json").read_text())["baseline"]
        if not re.fullmatch(r"baseline-[a-zA-Z0-9_-]+", key):
            raise ValueError("Invalid trace baseline ID")
        baseline = json.loads((path.parents[2]/"calibrations"/key/"baseline_summary.json").read_text())
        if not baseline["valid"] or baseline["baseline_id"] != key:
            raise ValueError("Incompatible trace baseline")
        reference = [r["mean_v"] for r in baseline["rois"]]
        noise = baseline["camera_settings"][NOISE_KEY]
        if combined and PROFILE_KEY in baseline["camera_settings"]:
            profile = baseline["camera_settings"][PROFILE_KEY]
            reference, noise = profile["mean_v_center"], profile["noise_v"]
    detector = MultiRise() if mode == "multi_v_rise" else MultiPress() if mode == "multi_press" else (
        RodResponse(use_tap_rate=mode == "rapid_tap") if combined else OpticalChange(mode))
    active, raw = Counter(), Counter()
    transitions, last = [], ()
    for i in np.flatnonzero(~cal):
        reading = detector.update(times[i], means[i], reference, np.asarray(noise)*.7 if mode == "multi_v_rise" else noise)
        contact = bool(frame.raw_contact.iloc[i])
        if contact:
            raw[int(frame.raw_taxel.iloc[i])] += 1
        displayed = reading.rois if contact else ()
        active.update(displayed)
        if displayed != last:
            transitions.append(dict(source_time_s=round(times[i], 3), phase=phase.iloc[i],
                                    roi=displayed[0] if len(displayed) == 1 else None, rois=displayed))
            last = displayed
    return dict(source=str(path), tested_frames=int((~cal).sum()), raw_contact_taxels=raw,
                displayed_taxels=active, transitions=transitions)


def video_report(path, model, mode="v_rise", cues=()):
    source = Replay(path, model.layout)
    model.predictor.reset()
    raw, displayed = Counter(), Counter()
    transitions, last = [], ()
    contact_counts = Counter()
    total = valid = 0
    expected = None
    peak_rates = {}
    previous = None
    if cues:
        trace = pd.read_csv(path.parent / "predictions.csv")
        expected = trace[(trace.record_type == "frame") & (trace.valid == 1)].set_index("frame_id")
        if not expected.index.is_unique:
            raise ValueError("Duplicate frame IDs in the recorded prediction log")
    try:
        info = source.open()
        with ThreadPoolExecutor(1) as pool:
            analysis = FrameAnalysis(model, source, info, path.parent, pool, mode)
            while (f := source.read()) is not None:
                total += 1
                status, detail, pred = analysis.analyze(f)
                if pred is None:
                    continue
                valid += 1
                state = View(status, detail, f, result=pred, change=analysis.change)
                if expected is not None:
                    before = expected.loc[f.number]
                    if (pred["contact"] != before.raw_contact or pred["localization"] != before.raw_taxel
                            or not np.isclose(pred["contact_score"], before.contact_decision_score, rtol=0, atol=1e-7)):
                        raise ValueError(f"Raw model parity failed on frame {f.number}")
                if pred["contact"]:
                    raw[pred["localization"]] += 1
                displayed.update(state.active_rois)
                contact_counts[len(state.active_rois)] += 1
                if cues:
                    phase = next((e["phase"] for e in reversed(cues) if e["frame"] <= f.number), "setup")
                    means = np.asarray(analysis.optical)
                    if previous is not None and previous[0] == analysis.epoch and 0 < f.t - previous[1] <= RESET_GAP_S:
                        rates = (means - previous[2]) / (f.t - previous[1])
                        rates -= np.median(rates)
                        k = int(np.argmax(np.abs(rates)))
                        if phase not in peak_rates or abs(rates[k]) > abs(peak_rates[phase]["local_v_per_s"]):
                            peak_rates[phase] = dict(roi=k+1, local_v_per_s=float(rates[k]), source_s=f.t)
                    previous = analysis.epoch, f.t, means
                    if state.active_rois != last:
                        transitions.append(dict(frame=f.number, source_s=round(f.t, 3), phase=phase, roi=state.active,
                                                rois=state.active_rois))
                        last = state.active_rois
    finally:
        source.close()
    report = dict(source=str(path), mode=mode, tested_frames=total, valid_frames=valid,
                  raw_contact_taxels=raw, displayed_taxels=displayed, frames_by_contact_count=contact_counts)
    if expected is not None:
        if len(expected) != valid:
            raise ValueError("Valid frame count differs from the recorded session")
        report.update(raw_parity_frames=valid, transitions=transitions, strongest_local_frame_rate_by_cue=peak_rates)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trace", type=Path, action="append", default=[], help="Also test a captured numeric idle or press trial")
    p.add_argument("--mode", choices=["v_drop", "v_rise", "rod_response", "rapid_tap", "multi_press", *sorted(RISE_MODES)],
                   help="Use this display rule for every input")
    p.add_argument("--guided-check", type=Path, action="append", default=[], help="Light-check folder; repeat for multiple runs")
    p.add_argument("--output", type=Path, help="Save the numerical verification result as JSON")
    args = p.parse_args()
    model = OpticalModel(json.loads(DEFAULTS.read_text()))
    reports = [video_report(SAMPLE / key / "session_video.mp4", model, args.mode or "v_rise")
               for key in ("center_press", "unloaded")]
    reports.extend(trace_report(path, args.mode or "v_drop") for path in args.trace)
    for folder in args.guided_check:
        meta = json.loads((folder / "check.json").read_text())
        session = folder / "sessions" / Path(meta["session"]).name
        check = video_report(session / "session_video.avi", model, args.mode or meta.get("rule", "rod_response"), meta["cues"])
        check["operator_confirmed"] = meta["confirmed"]
        reports.append(check)
    result = json.dumps(reports, indent=2)
    if args.output:
        args.output.write_text(result + "\n", encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
