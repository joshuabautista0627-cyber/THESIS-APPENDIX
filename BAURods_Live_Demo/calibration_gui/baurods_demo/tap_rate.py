"""Short-window, capture-time V rates for local flashes and faint rod tips."""
from collections import deque
from typing import NamedTuple

import numpy as np

from .optical_change import OpticalReading


class VEdge(NamedTuple):
    before: np.ndarray
    rates: np.ndarray
    seconds: float


class TapRate:
    def __init__(self, minimum_v):
        self.minimum_v = minimum_v or .45
        self.history = deque(maxlen=256)
        self.clear_drop()

    def clear_drop(self):
        self.candidate = None
        self.confirmed = False

    def sample(self, t, v):
        """Compare the current frame with the median of samples 0.20–0.60 s earlier."""
        while self.history and t - self.history[0][0] > .60:
            self.history.popleft()
        before = [(s, a) for s, a in self.history if t - s >= .20]
        self.history.append((t, v.copy()))
        if len(before) < 2:
            return None
        times, values = zip(*before)
        reference = np.median(values, axis=0)
        dt = t - np.median(times)
        rates = (v - reference) / dt
        return VEdge(reference, rates, dt)

    def faint_drop(self, t, v, unloaded, dark_floor, edge):
        """Freeze the pre-edge scene while checking that just one faint tip goes out."""
        if self.candidate is not None:
            k, start, before = self.candidate
            lit = before >= self.minimum_v
            fraction = v / np.maximum(before, .1)
            gain = np.median(fraction[lit])
            # A second extinguished tip makes attribution ambiguous. A scene-wide
            # loss of light also invalidates the edge.
            other_dark = lit & (fraction <= .20 * gain)
            other_dark[k] = False
            limit = .40 if self.confirmed else .12
            if gain >= .55 and not other_dark.any() and fraction[k] <= limit * gain:
                if t - start >= .20:
                    self.confirmed = True
                    return OpticalReading(k+1, before[k]-v[k], self.minimum_v,
                                          "Rapid local V fall confirmed at a faint tip", "drop")
                return OpticalReading(None, before[k]-v[k], self.minimum_v, "Checking whether one faint tip stays dark")
            was_confirmed = self.confirmed
            self.clear_drop()
            if was_confirmed:
                return OpticalReading(None, 0., self.minimum_v, "Released")
        if edge is None:
            return None
        before, rates, dt = edge
        lit = before >= self.minimum_v
        if np.count_nonzero(lit) < 5:
            return None
        fraction = v / np.maximum(before, .1)
        gain = np.median(fraction[lit])
        if gain < .55:
            return None
        nearly_out = lit & (fraction <= .20 * gain)
        if np.count_nonzero(nearly_out) != 1:
            return None
        k = int(np.argmax(nearly_out))
        # A shrinking median window must not turn two already-dark tips into a
        # new one-tip event. There must still be a recent fall at this tip.
        recent_peak = max(a[k] for s, a in self.history if t - s <= .30)
        if recent_peak - v[k] < .20 * self.minimum_v:
            return None
        relative_speed = -rates[k] / before[k] + np.median(rates[lit] / before[lit])
        # Reject an additive lighting change too, including clipping near zero.
        expected = np.clip(before + np.median(v - before), 0., 255.)
        residual = np.abs(v - expected)
        common_offset = max(residual[k], np.median(residual[lit])) <= .15 * self.minimum_v
        if (unloaded[k] < dark_floor and fraction[k] <= .10 * gain
                and -rates[k] * dt >= self.minimum_v and not common_offset
                and relative_speed >= 1.):
            self.candidate = k, t, before
            return OpticalReading(None, before[k]-v[k], self.minimum_v, "Checking whether one faint tip stays dark")
        return None
