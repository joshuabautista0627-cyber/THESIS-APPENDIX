"""Single-rod optical response, measured against the unloaded array and a quiet live reference."""
from collections import deque
from dataclasses import replace

import numpy as np

from .optical_change import HISTORY_S, OpticalReading, RESET_GAP_S, localized
from .tap_rate import TapRate


PROFILE_KEY = "rod_response_unloaded_v1"
ARM_S = .15
BLACK_CONFIRM_S = .20
BRIGHT_CONFIRM_S = .12


def unloaded_profile(values):
    """Robust center and noise from the same unloaded frames used for optical calibration."""
    values = np.asarray(values, dtype=float)
    center = np.median(values, axis=0)
    local = values - center
    local -= np.median(local, axis=1, keepdims=True)
    mad = np.median(np.abs(local - np.median(local, axis=0)), axis=0)
    return {"mean_v_center": center.tolist(), "noise_v": (5 * 1.4826 * mad).tolist()}


class RodResponse:
    def __init__(self, minimum_v=0., *, use_tap_rate=False):
        if not np.isfinite(minimum_v) or minimum_v < 0:
            raise ValueError("Invalid minimum optical step")
        self.bright_floor = minimum_v or .6
        self.dark_floor = minimum_v or 2.
        self.tap_minimum = minimum_v if use_tap_rate else None
        self.reset()

    def reset(self):
        self.tap_rate = TapRate(self.tap_minimum) if self.tap_minimum is not None else None
        self.last_time = None
        self.reference = None
        self.history = deque(maxlen=256)
        self.quiet_since = np.full(9, np.nan)
        self.bright_armed = np.zeros(9, dtype=bool)
        self.dark_armed = np.zeros(9, dtype=bool)
        self.pending = None
        self.pending_since = 0.
        self.active = None
        self.kind = ""
        self.peak = 0.

    def _stable(self, timestamp, kind, k, duration):
        if self.pending != (kind, k):
            self.pending, self.pending_since = (kind, k), timestamp
        return timestamp - self.pending_since >= duration

    def update(self, timestamp, mean_v, unloaded, noise):
        v, b, noise = (np.asarray(x, dtype=float) for x in (mean_v, unloaded, noise))
        if (any(x.shape != (9,) or not np.isfinite(x).all() for x in (v, b, noise))
                or not np.isfinite(timestamp)):
            raise ValueError("Expected nine finite ROI values and an ordered optical timestamp")
        if self.last_time is not None and not 0 < timestamp-self.last_time <= RESET_GAP_S:
            self.reset()
        self.last_time = timestamp
        rate_edge = self.tap_rate.sample(timestamp, v) if self.tap_rate else None
        reading = self._classify(timestamp, v, b, noise, rate_edge)
        if rate_edge is not None and reading.roi is not None:
            return replace(reading, rate_v_s=float(rate_edge.rates[reading.roi-1]))
        return reading

    def _classify(self, timestamp, v, b, noise, rate_edge):
        while self.history and timestamp - self.history[0][0] > HISTORY_S:
            self.history.popleft()
        previous = [sample for _, sample in self.history]
        self.history.append((timestamp, v.copy()))
        threshold = np.maximum(self.bright_floor, noise)
        delta = v - b
        local = delta - np.median(delta)
        if self.reference is None:
            # A common codec/driver offset can separate recorded pixels from the
            # calibration. Freeze it so the reference cannot follow an approaching hand.
            self.reference = b + np.median(delta)
        # Reject both a common additive offset and multiplicative illumination changes.
        reference_lit = self.reference >= 2.
        if np.count_nonzero(reference_lit) >= 3:
            scene_gain = np.median(v[reference_lit] / self.reference[reference_lit])
            local = np.minimum(local, v - self.reference * scene_gain)
        rise = np.minimum(v - self.reference, local)
        lit = b >= self.dark_floor
        relative = v / np.maximum(b, 1.)
        gain = np.median(relative[lit]) if np.count_nonzero(lit) >= 5 else 1.
        remaining = relative / np.clip(gain, .05, 1.)
        shadow = lit & (remaining < .60)
        stable_scene = not shadow.any()
        quiet = (np.abs(local) <= .5 * threshold) & (np.abs(v - self.reference) <= threshold) & stable_scene
        self.quiet_since[~quiet] = np.nan
        self.quiet_since[quiet & np.isnan(self.quiet_since)] = timestamp
        if not stable_scene:
            self.bright_armed.fill(False)
        self.bright_armed |= quiet & (timestamp - self.quiet_since >= ARM_S)
        self.dark_armed |= lit & (relative >= .6) & (gain > .25)
        visible_neighbors = np.count_nonzero(lit & (relative > .35)) >= 2

        if self.tap_rate and self.active is None:
            faint = self.tap_rate.faint_drop(timestamp, v, b, self.dark_floor, rate_edge)
            if faint is not None:
                self.bright_armed.fill(False)
                self.quiet_since.fill(np.nan)
                self.pending = None
                return faint
        elif self.tap_rate:
            self.tap_rate.clear_drop()

        if self.active is not None:
            k = self.active
            if self.kind == "drop":
                if remaining[k] < .40 and visible_neighbors:
                    return OpticalReading(k+1, -delta[k], self.dark_floor, "Rod remains dark", "drop")
                self.dark_armed[k] = False
                self.bright_armed[k] = False
                self.quiet_since[k] = np.nan
            else:
                self.peak = max(self.peak, rise[k])
                if rise[k] > max(.45 * threshold[k], .25 * self.peak) and stable_scene:
                    return OpticalReading(k+1, rise[k], threshold[k], "Rod remains brighter than unloaded", "rise")
            self.active = self.pending = None
            return OpticalReading(None, 0., threshold[k], "Released")

        # Near-black rods must have been visibly lit since the last reset. Rank by
        # the fraction of their own unloaded V remaining; shadows on brighter neighbors
        # can produce a larger absolute drop while the pressed rod is the one that goes out.
        dark = (self.dark_armed & lit & (remaining <= .06) & (-delta >= self.dark_floor)
                & visible_neighbors)
        if dark.any():
            darkest = np.min(remaining[dark])
            near_floor = dark & (remaining <= darkest + .025)
            loss = np.where(near_floor, -delta, 0.)
            k = int(np.argmax(loss))
            if loss[k] < 1.25 * np.partition(loss, -2)[-2]:
                self.pending = None
                return OpticalReading(None, -delta[k], self.dark_floor, "Two rod tips are equally dark")
            if self._stable(timestamp, "drop", k, BLACK_CONFIRM_S):
                self.active, self.kind = k, "drop"
                return OpticalReading(k+1, -delta[k], self.dark_floor, "Rod extinguished", "drop")
            return OpticalReading(None, -delta[k], self.dark_floor, "Checking which tip stays dark")
        # A recovery from shadow needs to settle near unloaded before another bright
        # event can start. This prevents a release flash from becoming the next press.
        edge = localized(v - np.median(previous, axis=0)) if len(previous) >= 2 else np.zeros(9)
        flash = (edge >= threshold) & (local >= .5 * threshold) & (v - self.reference >= .3 * threshold)
        if rate_edge is not None:
            _, rates, dt = rate_edge
            local_rate = localized(rates)
            fast_rise = ((local_rate >= 4. * threshold) & (local_rate * dt >= threshold)
                         & (local >= .5 * threshold) & (v - self.reference >= .3 * threshold))
            edge = np.maximum(edge, np.where(fast_rise, local_rate * dt, 0.))
            flash |= fast_rise
        strength = np.maximum(rise, np.where(flash, edge, 0.))
        candidates = np.where(self.bright_armed & ((rise >= threshold) | flash), strength, 0.)
        k = int(np.argmax(candidates))
        # A recovering rod still competes optically even if it cannot start a new press.
        # Otherwise a smaller change in its neighbor could be assigned to that neighbor.
        competing = strength.copy()
        competing[k] = 0.
        if candidates[k] and candidates[k] >= 1.35 * competing.max():
            if flash[k] or self._stable(timestamp, "rise", k, BRIGHT_CONFIRM_S) or rise[k] >= 2 * threshold[k]:
                self.active, self.kind, self.peak = k, "rise", rise[k]
                detail = "Rapid local V rise" if rate_edge is not None and fast_rise[k] else "Rod brightened above unloaded"
                return OpticalReading(k+1, strength[k], threshold[k], detail, "rise")
            return OpticalReading(None, rise[k], threshold[k], "Confirming a local light increase")
        self.pending = None
        k = int(np.argmax(rise))
        return OpticalReading(None, rise[k], threshold[k], "Waiting for a distinct rod response")
