"""Independent positive light responses with per-ROI noise and release hysteresis."""
import numpy as np

from .optical_change import MultiReading, OpticalReading, RESET_GAP_S, localized
from .tap_rate import TapRate


class MultiRise:
    def __init__(self, minimum_v=0., *, spot=False, sustained=False):
        if not np.isfinite(minimum_v) or minimum_v < 0:
            raise ValueError("Invalid minimum optical step")
        self.floor = minimum_v or (.8 if spot else .12)
        self.spot = spot
        self.sustained = sustained
        self.reset()

    def reset(self):
        self.last_time = None
        self.rate = TapRate(self.floor)
        self.active = np.zeros(9, bool)
        self.armed = np.zeros(9, bool)
        self.quiet_since = np.full(9, np.nan)
        self.pending_since = np.full(9, np.nan)
        self.started = np.full(9, -np.inf)
        self.peak = np.zeros(9)

    def update(self, timestamp, mean_v, unloaded, noise):
        v, b, noise = (np.asarray(x, dtype=float) for x in (mean_v, unloaded, noise))
        if (any(x.shape != (9,) or not np.isfinite(x).all() for x in (v, b, noise))
                or not np.isfinite(timestamp) or np.any(noise < 0)):
            raise ValueError("Expected nine finite signals, nonnegative noise and a capture timestamp")
        if self.last_time is not None and not 0 < timestamp-self.last_time <= RESET_GAP_S:
            self.reset()
        self.last_time = timestamp
        edge = self.rate.sample(timestamp, v)
        threshold = np.maximum(self.floor, noise)
        delta = v-b
        rise = localized(delta)
        lit = b >= np.maximum(self.floor, 2*noise)
        if lit.sum() >= 5:
            gain = np.median(v[lit]/np.maximum(b[lit], .01))
            rise = np.minimum(rise, v-b*gain)
        # Arming is local: a dimming neighbor cannot disable this rod's rise detector.
        shadow = lit & (v < .4*b)
        quiet = (np.abs(delta-np.median(delta)) <= threshold) & ~shadow
        self.quiet_since[~quiet] = np.nan
        self.quiet_since[quiet & np.isnan(self.quiet_since)] = timestamp
        self.armed[shadow] = False
        self.armed |= quiet & (timestamp-self.quiet_since >= .15)

        self.peak = np.maximum(self.peak, np.where(self.active, rise, 0.))
        # Sliding follows the remaining light level, including a lower plateau after
        # an initial flash. A peak-relative release would cause repeated dropouts.
        off_threshold = .6*threshold if self.sustained else np.maximum(.4*threshold, .2*self.peak)
        hold = (rise > off_threshold) | (timestamp-self.started < .18)
        released = self.active & ~hold
        self.active &= hold
        self.armed[released] = False
        self.quiet_since[released] = np.nan
        candidate = np.zeros(9, bool)
        if self.sustained:
            candidate = ~self.active & ~released & (rise >= threshold)
        elif edge is not None:
            step = localized(v-edge.before)
            candidate = (self.armed & ~self.active & ~released & (rise >= threshold)
                         & (step >= .7*threshold) & (step/edge.seconds >= threshold))
        self.pending_since[~candidate] = np.nan
        self.pending_since[candidate & np.isnan(self.pending_since)] = timestamp
        if self.sustained:
            onset = candidate & (timestamp-self.pending_since >= .20)
        else:
            onset = candidate & ((rise >= 2*threshold) | (timestamp-self.pending_since >= .06))
        if np.count_nonzero(self.active | onset) > 4:
            self.reset()
            return MultiReading((), "Broad light change · waiting for the array to settle")
        self.active |= onset
        self.started[onset] = timestamp
        self.peak[onset] = rise[onset]
        readings = tuple(OpticalReading(int(k)+1, float(max(0., rise[k])), float(threshold[k]),
                         "Sustained light" if self.sustained else "Local bright spot" if self.spot else "Local V rise", "rise",
                         float(edge.rates[k]) if edge is not None else None)
                         for k in np.flatnonzero(self.active))
        detail = ("Tracking sustained light independently" if readings else "Watching for sustained light above unloaded") if self.sustained else (
            "Independent light rises" if readings else "Watching each ROI for a local light rise")
        return MultiReading(readings, detail)
