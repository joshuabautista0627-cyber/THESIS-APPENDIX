"""Bind the two thesis families to their original fitted artifacts and optical inputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from core.live_sensor_contracts import LIVE_LAYOUT_ID, RAW_FRAME_SIZE, load_canonical_live_layout
from processing.feature_extraction import extract_roi_features
from scripts.build_optical_force_dataset import _feature_payload, _load_baseline, _orient_quantitative_frame
from scripts.live_sensor_common import PROJECT_ROOT, sha256_file
from scripts.predict_tuned_manual import StreamingResearchPredictor


# Trust anchors for the existing final refit. Only these two pickles are deserialized.
MANIFEST_SHA = "9bd0a028f474c3491acc515659f9ab59524edc8adba6c86d41f8afe862372e20"
SELECTIONS_SHA = "6324437ad6ad20d6a7f76d5d82dd549a5a9b12d59e761e59c688330882c6da14"
FAMILIES = {
    "contact": ("RBF SVC", "con_022", "shape", 90, SVC, [0, 1]),
    "localization": ("Logistic regression", "loc_036", "invariant", 117, LogisticRegression, list(range(1, 10))),
}


def checked_json(path, digest):
    # The original Windows export hashed CRLF JSON; Git can check it out as LF.
    data = Path(path).read_bytes()
    windows_text = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if digest not in {hashlib.sha256(data).hexdigest(), hashlib.sha256(windows_text).hexdigest()}:
        raise ValueError(f"Checksum mismatch in final tuning file: {path}")
    return json.loads(data)


def load_selected(run: Path):
    if sklearn.__version__ != "1.9.0":
        raise ValueError(f"Models require scikit-learn 1.9.0, found {sklearn.__version__}. Install the analysis lock.")
    models = run / "models"
    manifest = checked_json(models / "manifest.json", MANIFEST_SHA)
    choices = checked_json(run / "final_selections.json", SELECTIONS_SHA)
    selected, identity = {}, {}
    for task, (family, candidate, pack, width, estimator, labels) in FAMILIES.items():
        spec = checked_json(models / f"{task}.json", manifest["files"][f"{task}.json"])
        choice = choices[task][f"Tuned {family}"]
        filename = f"{task}_{candidate}.joblib"
        member = next((m for m in spec["members"] if m["file"] == filename), None)
        if choice["id"] != candidate or member is None or member["choice"] != choice:
            raise ValueError(f"{task}: exported member does not match the final family selection")
        path = models / filename
        digest = sha256_file(path)
        if digest != manifest["files"][filename] or digest != member["sha256"]:
            raise ValueError(f"Model checksum mismatch: {path}")
        fit = joblib.load(path)
        cfg, model, scaler = fit["config"], fit["model"], fit["scaler"]
        if (cfg["id"], cfg["family"], cfg["features"]) != (candidate, family, pack):
            raise ValueError(f"Incompatible fitted configuration in {path}")
        if not isinstance(scaler, StandardScaler) or not isinstance(model, estimator):
            raise ValueError(f"Incompatible scaler or classifier in {path}")
        if scaler.n_features_in_ != width or model.n_features_in_ != width or list(model.classes_) != labels:
            raise ValueError(f"{filename}: expected {width} features and classes {labels}")
        selected[task] = dict(spec, choice=choice, members=[member], loaded_members=[fit])
        identity[task] = dict(path=str(path.resolve()), sha256=digest, **cfg, dimension=width,
                              classes=labels, tau_s=choice["tau"], floors=spec["floors"])
        if task == "contact":
            identity[task]["threshold"] = choice["threshold"]
    return selected, identity


def oriented_image(frame, *, live=False):
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("Expected an unannotated uint8 BGR image")
    if live and frame.shape[1::-1] != RAW_FRAME_SIZE:
        raise ValueError(f"Camera returned {frame.shape[1]}×{frame.shape[0]}. Select 640×480 in the camera driver.")
    image, status = _orient_quantitative_frame(frame)
    if image is None:
        raise ValueError(f"Incompatible replay geometry ({status}). Use the original acquisition video.")
    return image


def archived_baseline(directory, layout):
    baseline = _load_baseline(directory / "baseline_summary.json", directory / "baseline_data.npz", LIVE_LAYOUT_ID)
    for roi, record in zip(layout.rois, baseline.roi_baselines, strict=True):
        for a in (record.median_v_image, record.mean_v_image):
            if a.shape != (roi.height, roi.width) or not np.isfinite(a).all() or a.min() < 0 or a.max() > 255:
                raise ValueError(f"Invalid archived baseline image for ROI {roi.roi_id}")
    return baseline


class OpticalModel:
    def __init__(self, settings):
        self.layout = load_canonical_live_layout(PROJECT_ROOT / settings["roi_layout"])
        self.specs, self.identity = load_selected(PROJECT_ROOT / settings["model_run"])
        self.predictor = StreamingResearchPredictor(self.specs)

    def feature_row(self, image, baseline, session, timestamp):
        payload = _feature_payload(extract_roi_features(image, self.layout.rois, baseline))
        return dict(payload, session_id=session, capture_monotonic_relative_s=timestamp)

    def predict(self, row):
        return self.predictor.predict_one(pd.DataFrame([row]), include_class_scores=True)
