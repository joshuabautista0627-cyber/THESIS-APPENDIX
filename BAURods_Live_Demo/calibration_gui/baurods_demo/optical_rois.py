"""Editable optical regions; the thesis model retains its original geometry."""
import cv2
import numpy as np

from core.models import ROI
from processing.roi_manager import ROILayout
from .rod_response import unloaded_profile

SIGNAL_PROFILE_KEY = "optical_regions_v1"
RISE_MODES = {"multi_v_rise", "multi_spot", "multi_slide"}
SPOT_MODES = {"multi_spot", "multi_slide"}


def layout_values(layout):
    return [dict(roi_id=r.roi_id, x=r.x, y=r.y, width=r.width, height=r.height) for r in layout.rois]


def optical_layout(values, fallback):
    if values is None:
        return fallback
    if not isinstance(values, list) or len(values) != 9:
        raise ValueError("Provide exactly nine optical ROI rectangles")
    fields = ("roi_id", "x", "y", "width", "height")
    rois = []
    for row in values:
        if not isinstance(row, dict) or any(type(row.get(k)) is not int for k in fields):
            raise ValueError("ROI numbers and coordinates must be integers")
        rois.append(ROI(**{k: row[k] for k in fields}))
    layout = ROILayout.create(rois, 480, 640, rotation_degrees=90, mirror_horizontal=True)
    if any(r.width < 8 or r.height < 8 for r in layout.rois):
        raise ValueError("Each ROI must be at least 8 × 8 pixels")
    if layout.validation.overlap_pairs:
        raise ValueError("ROIs must not overlap; one light spot must belong to one rod")
    return layout


def signal_values(image, rois):
    """Mean V and spatially denoised brightest-5% V, both in 0–255 levels."""
    value = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 2]
    means, spots = [], []
    for r in rois:
        crop = value[r.y:r.y+r.height, r.x:r.x+r.width]
        means.append(float(crop.mean()))
        # A single hot pixel cannot survive the spatial median filter.
        smooth = cv2.medianBlur(crop, 3).ravel()
        count = max(4, int(np.ceil(smooth.size*.05)))
        spots.append(float(np.partition(smooth, smooth.size-count)[-count:].mean()))
    return np.asarray(means), np.asarray(spots)


def signal_profile(frames, layout):
    values = [signal_values(f.image, layout.rois) for f in frames]
    mean, spot = (np.asarray([v[k] for v in values]) for k in (0, 1))
    profiles = {name: unloaded_profile(samples) for name, samples in (("mean", mean), ("spot", spot))}
    # Independent rise decisions confirm modest signals across multiple frames.
    # Their 3.5-MAD noise estimate is stored separately from the old rules' 5-MAD profile.
    for profile in profiles.values():
        profile["rise_noise_v"] = (np.asarray(profile["noise_v"])*.7).tolist()
    return dict(layout_id=layout.roi_layout_id, **profiles)
