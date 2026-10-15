"""Turn-speed sensing tuned to the CMF dial.

The buds report at most ~3 detents/s (gaps >= ~0.3 s) and fold faster spins
into a single +/-2 report. So "speed" here is the gap since the previous
detent plus how many quick detents in a row went the same way (intent).
"""
from __future__ import annotations

import math
import time

FAST_GAP = 0.30    # at or under this gap the spin counts as full speed
SLOW_GAP = 0.65    # at or over this gap it's a deliberate single click
STREAK_FULL = 4    # quick detents in a row before gain reaches its max


class SpinTracker:
    def __init__(self):
        self._t = 0.0
        self._dir = 0
        self.streak = 0
        self.intensity = 0.0   # 0 = slow click, 1 = flat-out spin

    def update(self, delta: int, now: float | None = None) -> float:
        """Feed one rotate event; returns intensity 0..1."""
        now = time.monotonic() if now is None else now
        gap = now - self._t
        self._t = now
        d = 1 if delta > 0 else -1
        if d != self._dir or gap > SLOW_GAP:
            self.streak = 0
        self._dir = d
        speed = min(1.0, max(0.0, (SLOW_GAP - gap) / (SLOW_GAP - FAST_GAP)))
        if abs(delta) >= 2:            # firmware folded a fast spin into one report
            speed = 1.0
        if speed > 0:
            self.streak += 1
        self.intensity = speed * min(1.0, self.streak / STREAK_FULL)
        return self.intensity

    def gain(self, max_gain: float) -> float:
        """1 for careful clicks, rising smoothly to max_gain for a sustained fast spin."""
        return 1.0 + (max_gain - 1.0) * math.pow(self.intensity, 1.5)
