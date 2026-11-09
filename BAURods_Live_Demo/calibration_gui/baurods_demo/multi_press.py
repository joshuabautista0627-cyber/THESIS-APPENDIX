"""Experimental independent rod responses with a majority lighting reference."""
import numpy as np

from .optical_change import MultiReading, OpticalReading, RESET_GAP_S, localized
from .rod_response import ARM_S, BLACK_CONFIRM_S, BRIGHT_CONFIRM_S
from .tap_rate import TapRate


class MultiPress:
    def __init__(self, minimum_v=0.):
        if not np.isfinite(minimum_v) or minimum_v < 0:
            raise ValueError("Invalid minimum optical step")
        self.bright_floor = minimum_v or .6
        self.dark_floor = minimum_v or .45
        self.reset()

    def reset(self):
        self.last_time = self.reference = None
        self.rate = TapRate(self.dark_floor)
        self.bright = np.zeros(9, dtype=bool)
        self.dark = np.zeros(9, dtype=bool)
        self.bright_armed = np.zeros(9, dtype=bool)
        self.dark_armed = np.zeros(9, dtype=bool)
        self.quiet_since = np.full(9, np.nan)
        self.bright_since = np.full(9, np.nan)
        self.dark_since = np.full(9, np.nan)
        self.edge_until = np.full(9, -np.inf)
        self.peak = np.zeros(9)

    def update(self, timestamp, mean_v, unloaded, noise):
        v, b, noise = (np.asarray(a, dtype=float) for a in (mean_v, unloaded, noise))
        if (any(a.shape != (9,) or not np.isfinite(a).all() for a in (v, b, noise))
                or not np.isfinite(timestamp)):
            raise ValueError("Expected nine finite ROI values and a capture timestamp")
        if self.last_time is not None and not 0 < timestamp-self.last_time <= RESET_GAP_S:
            self.reset()
        self.last_time = timestamp
        edge = self.rate.sample(timestamp, v)
        if self.reference is None:
            self.reference = np.maximum(0., b + np.median(v-b))
        ref = self.reference
        bright_threshold = np.maximum(self.bright_floor, noise)
        dark_threshold = np.maximum(self.dark_floor, .5 * noise)
        lit = b >= self.dark_floor
        relative = v / np.maximum(b, .1)
        gain = np.median(relative[lit]) if lit.sum() >= 5 else 1.
        remaining = relative / max(gain, .05)
        delta = v-ref
        rise = localized(delta)
        if lit.sum() >= 5:
            rise = np.minimum(rise, v-ref*gain)
        loss = localized(b-v)
        visible = np.count_nonzero(lit & (relative >= .35)) >= 2
        # An unlit unloaded rod can still produce a positive light pulse.
        # Only a previously visible rod needs to recover from shadow before arming.
        recovered = ~lit | (remaining >= .6)
        quiet = ((np.abs(delta-np.median(delta)) <= .5*bright_threshold)
                 & (np.abs(delta) <= bright_threshold) & recovered)
        self.quiet_since[~quiet] = np.nan
        self.quiet_since[quiet & np.isnan(self.quiet_since)] = timestamp
        self.bright_armed[~recovered] = False
        if np.count_nonzero(lit & (remaining < .6)) >= 3:
            self.bright_armed.fill(False)
            self.quiet_since.fill(np.nan)
        self.bright_armed |= quiet & (timestamp-self.quiet_since >= ARM_S)
        self.dark_armed |= lit & (remaining >= .6) & (gain > .25)

        self.peak = np.maximum(self.peak, np.where(self.bright, rise, 0.))
        bright_hold = rise > np.maximum(.45*bright_threshold, .25*self.peak)
        dark_hold = (remaining < .40) & visible & (gain > .25)
        released = (self.bright & ~bright_hold) | (self.dark & ~dark_hold)
        self.bright &= bright_hold
        self.dark &= dark_hold
        self.bright_armed[released] = self.dark_armed[released] = False
        self.quiet_since[released] = np.nan
        self.edge_until[released] = -np.inf

        flash = np.zeros(9, dtype=bool)
        if edge is not None:
            local_fall = localized(-edge.rates) * edge.seconds
            falling = (local_fall >= .5*dark_threshold) & (edge.before-v >= .5*dark_threshold)
            self.edge_until[falling & ~released] = timestamp + .65
            local_rise = localized(edge.rates)
            flash = (local_rise >= 2*bright_threshold) & (local_rise*edge.seconds >= bright_threshold)
        idle = ~(self.bright | self.dark | released)
        dark_candidate = (idle & self.dark_armed & visible & (gain > .25)
                          & (self.edge_until >= timestamp) & (remaining <= .06)
                          & (loss >= dark_threshold))
        bright_candidate = idle & self.bright_armed & flash & (rise >= bright_threshold)
        self.dark_since[~dark_candidate] = np.nan
        self.dark_since[dark_candidate & np.isnan(self.dark_since)] = timestamp
        new_dark = dark_candidate & (timestamp-self.dark_since >= BLACK_CONFIRM_S)
        self.bright_since[~bright_candidate] = np.nan
        self.bright_since[bright_candidate & np.isnan(self.bright_since)] = timestamp
        # Confirm weaker pulses across frames; a strong flash can be brief.
        new_bright = bright_candidate & ((rise >= 3*bright_threshold)
                                        | (timestamp-self.bright_since >= BRIGHT_CONFIRM_S))
        self.dark |= new_dark
        self.bright |= new_bright
        self.peak[new_bright] = rise[new_bright]
        active = self.bright | self.dark
        # Five unaffected rods are needed to distinguish scene lighting from presses.
        if active.sum() > 4:
            self.reset()
            return MultiReading((), "Shared lighting change · release all rods and retry")
        readings = []
        for k in np.flatnonzero(active):
            direction = "drop" if self.dark[k] else "rise"
            readings.append(OpticalReading(int(k)+1, float(loss[k] if self.dark[k] else rise[k]),
                            float(dark_threshold[k] if self.dark[k] else bright_threshold[k]),
                            "Independent rod response", direction, float(edge.rates[k]) if edge else None))
        detail = "Tracking each rod independently" if readings else "Ready for 2–4 rods · experimental multi-press"
        return MultiReading(tuple(readings), detail)
