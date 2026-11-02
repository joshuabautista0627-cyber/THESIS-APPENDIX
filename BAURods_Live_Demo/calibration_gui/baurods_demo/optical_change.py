"""Causal optical confirmation for the presentation display, independent of model fitting."""
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np


MODE_LABELS = {"models": "Trained models", "rapid_tap": "SVC + rapid V tap", "rod_response": "SVC + rod response",
               "v_rise": "SVC + local V rise", "v_drop": "SVC + local V drop"}
DEFAULT_STEP = {"v_rise": 0.6, "v_drop": 2.0}  # Mean HSV-V digital levels across one ROI.
HISTORY_S = 0.45
RESET_GAP_S = 0.30
MAX_HOLD_S = 4.0
DARK_CONFIRM_S = 0.14
DARK_EDGE_MEMORY_S = 0.65
DARK_ON_REMAINING = 0.15
DARK_OFF_REMAINING = 0.40
NOISE_KEY = "optical_change_noise_v1"


def localized(delta):
    """Require a signed change in the ROI itself and beyond the array-wide change."""
    return np.minimum(delta, delta - np.median(delta))


def mean_v_samples(frames, rois):
    """Return the nine ROI mean values for each operator-supplied unloaded frame."""
    values = []
    for frame in frames:
        v = cv2.cvtColor(frame.image, cv2.COLOR_BGR2HSV)[:, :, 2]
        values.append([v[r.y:r.y+r.height, r.x:r.x+r.width].mean() for r in rois])
    return np.asarray(values)


def measure_noise(frames, rois):
    return noise_thresholds([f.t for f in frames], mean_v_samples(frames, rois))


def noise_thresholds(times, values):
    times, values = np.asarray(times), np.asarray(values)
    noise = []
    for i, t in enumerate(times):
        previous = values[:i][times[:i] >= t - HISTORY_S]
        if len(previous) >= 2:
            delta = values[i] - np.median(previous, axis=0)
            noise.append(np.abs(delta - np.median(delta)))
    # The scalar operator floor still applies when a very slow camera supplies few neighbors.
    return (2 * np.quantile(noise, .95, axis=0) if noise else np.zeros(9)).tolist()


@dataclass(frozen=True)
class OpticalReading:
    roi: int | None
    change_v: float
    threshold_v: float
    detail: str
    direction: str = ""
    rate_v_s: float | None = None


class OpticalChange:
    """Arm on a local edge, hold only while displaced, clear on recovery or timeout."""
    def __init__(self, mode, minimum_v=0.0):
        if mode not in DEFAULT_STEP or not np.isfinite(minimum_v) or minimum_v < 0:
            raise ValueError("Invalid optical change mode or minimum V step")
        self.sign = 1 if mode == "v_rise" else -1
        self.minimum = minimum_v or DEFAULT_STEP[mode]
        self.history = deque(maxlen=256)
        self.reset()

    def reset(self):
        self.history.clear()
        self.active = self.pending = None
        self.start = self.peak = 0.
        self.pending_since = 0.
        self.edge_until = np.full(9, -np.inf)
        self.reference = None
        self.last_time = None

    def _hold(self, timestamp, level, threshold, recovered=False):
        k = self.active
        self.peak = max(self.peak, level)
        if recovered or level <= max(.4 * threshold, .3 * self.peak):
            self.reset()
            return OpticalReading(None, level, threshold, "Released")
        if timestamp - self.start >= MAX_HOLD_S:
            return OpticalReading(None, level, threshold, "Sustained change · release to rearm")
        return OpticalReading(k + 1, level, threshold, "Local change sustained")

    def _darkening(self, timestamp, values, unloaded, thresholds, previous):
        lit = unloaded >= 2.
        if np.count_nonzero(lit) < 5:
            self.reset()
            return OpticalReading(None, 0., self.minimum, "Too little unloaded light for darkening mode")
        remaining = values / np.maximum(unloaded, 1.)
        gain = np.median(remaining[lit])
        if gain < .25:
            self.reset()
            return OpticalReading(None, 0., self.minimum, "Array-wide dimming")
        remaining /= min(1., gain)
        loss = localized(unloaded - values)
        if self.active is not None:
            k = self.active
            return self._hold(timestamp, loss[k], thresholds[k], remaining[k] >= DARK_OFF_REMAINING)
        if len(previous) < 2:
            return OpticalReading(None, 0., self.minimum, "Listening for a new optical edge")
        # An approaching finger can shadow a neighbor first. The edge opens a short
        # observation window. Assign the ROI from the sustained local loss inside it.
        edge = localized(np.median(previous, axis=0) - values)
        self.edge_until[edge >= .5 * thresholds] = timestamp + DARK_EDGE_MEMORY_S
        eligible = lit & (self.edge_until >= timestamp) & (remaining <= DARK_ON_REMAINING) & (loss >= thresholds)
        if not np.any(eligible):
            self.pending = None
            k = int(np.argmax(loss))
            return OpticalReading(None, loss[k], thresholds[k], "Waiting for a strong local V drop")
        candidates = np.where(eligible, loss, 0.)
        k = int(np.argmax(candidates))
        if loss[k] < 1.25 * np.partition(candidates, -2)[-2]:
            self.pending = None
            return OpticalReading(None, loss[k], thresholds[k], "Competing dark ROIs")
        if self.pending != k:
            self.pending, self.pending_since = k, timestamp
        if timestamp - self.pending_since < DARK_CONFIRM_S:
            return OpticalReading(None, loss[k], thresholds[k], "Confirming sustained darkening")
        self.active, self.pending, self.start, self.peak = k, None, timestamp, loss[k]
        return OpticalReading(k + 1, loss[k], thresholds[k], "Sustained local V drop")

    def update(self, timestamp, mean_v, unloaded, noise):
        values = np.asarray(mean_v, dtype=float)
        thresholds = np.maximum(self.minimum, np.asarray(noise, dtype=float))
        unloaded = np.asarray(unloaded, dtype=float)
        if (any(v.shape != (9,) or not np.isfinite(v).all() for v in (values, thresholds, unloaded))
                or not np.isfinite(timestamp)):
            raise ValueError("Optical confirmation requires nine finite ROI values and a capture timestamp")
        if self.last_time is not None and (timestamp <= self.last_time or timestamp - self.last_time > RESET_GAP_S):
            self.reset()
        self.last_time = timestamp
        while self.history and timestamp - self.history[0][0] > HISTORY_S:
            self.history.popleft()
        previous = [v for _, v in self.history]
        self.history.append((timestamp, values.copy()))
        if self.sign < 0:
            return self._darkening(timestamp, values, unloaded, thresholds, previous)
        if self.active is not None:
            k = self.active
            return self._hold(timestamp, localized(values - self.reference)[k], thresholds[k])
        if len(previous) < 2:
            return OpticalReading(None, 0., self.minimum, "Listening for a new optical edge")
        reference = np.median(previous, axis=0)
        edge = localized(values - reference)
        k = int(np.argmax(edge))
        step = float(edge[k])
        # Also require displacement from the unloaded spatial pattern. Global codec or
        # illumination offsets cancel here. A return to unloaded alone cannot arm a press.
        displacement = values - unloaded
        displacement -= np.median(displacement)
        if step < thresholds[k] or displacement[k] < .5 * thresholds[k]:
            return OpticalReading(None, step, thresholds[k], "No local change above threshold")
        if step < 1.35 * np.partition(edge, -2)[-2]:
            return OpticalReading(None, step, thresholds[k], "Multiple ROIs changed together")
        self.reference = reference
        self.active, self.start, self.peak = k, timestamp, step
        return OpticalReading(k + 1, step, thresholds[k], "Local optical edge")
