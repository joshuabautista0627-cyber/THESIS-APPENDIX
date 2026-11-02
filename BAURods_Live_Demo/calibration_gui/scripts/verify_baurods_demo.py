"""Compare complete recorded-video streams with the archived feature store and frozen batch code."""
import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import time

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from baurods_demo.model import OpticalModel
from baurods_demo.setup import DEFAULTS, SAMPLE
from baurods_demo.sources import Replay
from scripts.live_sensor_common import PROJECT_ROOT, sha256_file


def feature_store():
    portable = PROJECT_ROOT / "verification_inputs"
    if (portable / "2026-08-08_170958_044598_1_R5_TEST7.parquet").is_file():
        return portable
    root = Path("analysis_outputs/live_sensor_manual_only/feature_store/feature-store-fa2500440adab6ca/sessions/archive_id=manual")
    for base in [PROJECT_ROOT, PROJECT_ROOT.parent / "thesis_appendix_package/github_repository/SOFTWARE_CALIBRATION/calibration_gui"]:
        try:
            if (base / root / "2026-08-08_170958_044598_1_R5_TEST7.parquet").is_file():
                return base / root
        except PermissionError:
            continue  # Some OneDrive workspaces keep only the packaged mirror hydrated.
    return PROJECT_ROOT / root


def compare(folder, store, model, reference):
    source = json.loads((folder / "source.json").read_text())
    path = folder / "session_video.mp4"
    if sha256_file(path) != source["video_sha256"]:
        raise ValueError(f"Clip hash differs from prepared source: {folder}")
    path_ref = store / (source["session_id"] + ".parquet")
    columns = ["session_id", "frame_id", "video_frame_index", "capture_monotonic_relative_s"]
    columns += [name for name in pq.read_schema(path_ref).names if name.startswith("roi")]
    archive = pd.read_parquet(path_ref, columns=columns).sort_values("video_frame_index")
    replay = Replay(path, model.layout)
    rows, results, latency = [], [], []
    model.predictor.reset()
    try:
        replay.open()
        while (frame := replay.read()) is not None:
            start = time.perf_counter()
            row = model.feature_row(frame.image, replay.baselines[frame.baseline_key], source["session_id"], frame.t)
            results.append(model.predict(row))
            latency.append((time.perf_counter() - start) * 1000)
            rows.append(dict(row, frame_id=frame.number))
    finally:
        replay.close()
    fresh = pd.DataFrame(rows)
    assert len(fresh) == len(archive) == len(results)
    np.testing.assert_array_equal(fresh.frame_id, archive.frame_id)
    np.testing.assert_allclose(fresh.capture_monotonic_relative_s, archive.capture_monotonic_relative_s, atol=1e-12, rtol=0)
    keys = [col for col in fresh if col.startswith("roi")]
    a, b = fresh[keys].to_numpy(float), archive[keys].to_numpy(float)
    np.testing.assert_allclose(a, b, rtol=0, atol=1e-10, equal_nan=True)
    floors = model.specs["contact"]["floors"]
    ref_packs = reference.optical_features(archive, np.array(floors))
    new_packs = reference.optical_features(fresh, np.array(floors))
    checks = {}
    for task, spec in model.specs.items():
        fit = spec["loaded_members"][0]
        pack = fit["config"]["features"]
        x, y = new_packs[pack], ref_packs[pack]
        np.testing.assert_allclose(x, y, atol=1e-10, rtol=0)
        values = reference.scores(fit["model"], fit["scaler"].transform(y), task, fit["config"]["family"])
        values = reference.causal_ema(values, archive.session_id.to_numpy(), archive.capture_monotonic_relative_s.to_numpy(),
                                     spec["choice"]["tau"]).astype(np.float32).astype(float)
        actual = np.asarray([r["contact_score" if task == "contact" else "localization_scores"] for r in results])
        np.testing.assert_allclose(actual, values, rtol=0, atol=1e-7)
        expected = values >= spec["choice"]["threshold"] if task == "contact" else fit["model"].classes_[values.argmax(axis=1)]
        np.testing.assert_array_equal([r[task] for r in results], expected)
        checks[task] = dict(features=x.shape[1], feature_max_abs=float(np.max(np.abs(x-y))),
                            score_max_abs=float(np.max(np.abs(actual-values))), matching_labels=len(expected))
    print(json.dumps(dict(recording=source["session_id"], frames=len(fresh), optical_columns=len(keys),
                          optical_max_abs=float(np.nanmax(np.abs(a-b))), models=checks,
                          active_frames=sum(r["contact"] for r in results),
                          highlighted_R=sorted({r["localization"] for r in results if r["contact"]}),
                          median_processing_ms=round(statistics.median(latency), 2),
                          p95_processing_ms=round(float(np.percentile(latency, 95)), 2)), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-store", type=Path, help="Directory containing the original per-session manual Parquets")
    args = parser.parse_args()
    settings = json.loads(DEFAULTS.read_text())
    model = OpticalModel(settings)
    path = PROJECT_ROOT / settings["model_run"] / "source_snapshot/scripts/tune_manual_models.py"
    spec = importlib.util.spec_from_file_location("frozen_tuning_reference", path)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for clip in ("center_press", "unloaded"):
        compare(SAMPLE / clip, args.feature_store or feature_store(), model, reference)


if __name__ == "__main__":
    main()
