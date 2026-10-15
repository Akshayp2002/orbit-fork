"""Turn an output-volume level stream into dial clicks. Platform independent.

The CMF dial (and most earbud dials) has no channel of its own: each click
nudges the buds' volume one step and the OS reports the new level. A platform
backend feeds every level change here; this class decides how many clicks it
was, and puts the level back when the active tool doesn't want volume to move.

What the real-device traces taught us (Windows, Oct 2026):

  * The step size isn't fixed (1/16 one session, 1/15 the next), so it is
    learned, and any change of at least CLICK_MIN of a step counts as a click.
    A reverse click right after a recenter must never round away to zero.
  * After we set the level ourselves the buds can still sit on their old level:
    they re-send it (stale echo) or report a click relative to it. Until they
    confirm ours, reports are measured from their old level, and ours is re-sent.
  * Recenter targets sit on the buds' own grid so the next click is a clean step.
  * The buds report at most ~3 times a second and may fold two clicks into one.

Backend contract:
    get_level() -> float | None        current level 0..1
    set_level(level: float)            set it; the backend reports the resulting
                                       change back with ours=True
    thread_init()                      optional, called once on the worker thread
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Protocol

from orbit.core.events import InputEvent, Kind

log = logging.getLogger("orbit.dial")
trace = logging.getLogger("orbit.trace")

DEFAULT_STEP = 1 / 16       # first guess; learned from real clicks
CLICK_MIN = 0.35            # fraction of a step that counts as a click (2% keyboard nudges don't)
MAX_CLICKS = 3              # the buds fold at most ~2 clicks into one report
RECENTER_IDLE_S = 0.9       # quiet time before we restore the level
EDGE_STEPS = 2              # recenter at once when this close to either end
STALE_S = 0.8               # window after our own set in which the buds may lag behind


class LevelBackend(Protocol):
    def get_level(self) -> float | None: ...
    def set_level(self, level: float) -> None: ...


class VolumeDial:
    def __init__(self, backend: LevelBackend, emit: Callable[[InputEvent], None], source: str = "volume-dial"):
        self.backend = backend
        self.emit = emit
        self.source = source
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._stopped = threading.Event()
        self._passthrough = True
        self._level: float | None = None       # last level seen
        self._from_dial = False                # was that a dial report (vs our set)?
        self.step = DEFAULT_STEP
        self._home: float | None = None
        self._last_move = 0.0
        self._last_dial = 0.0
        self._need_recenter = False
        self._saved: float | None = None       # real listening level while ducked
        self._apply: float | None = None       # level the worker should set
        self._reapply: float | None = None     # same, forced, after the buds lagged
        self._last_set = (0.0, None, None, 0)  # (time, buds' level before, our level, re-sends left)

    # ---------------------------------------------------------------- lifecycle
    def start(self):
        self._level = self.backend.get_level()
        threading.Thread(target=self._worker, name=f"{self.source}-worker", daemon=True).start()

    def stop(self):
        self.set_duck(None)                    # never leave the user ducked
        self._stop.set()
        self._wake.set()
        self._stopped.wait(1.0)

    def rebase(self):
        """Device (re)connected: forget history, read the level fresh."""
        with self._lock:
            self._level = self.backend.get_level()
            self._from_dial = False
            self._last_set = (0.0, None, None, 0)

    # ---------------------------------------------------------------- engine-facing
    def set_passthrough(self, on: bool):
        with self._lock:
            if on == self._passthrough:
                return
            self._passthrough = on
            if not on and self._level is not None:
                self._home = self._snap_home(self._level)
                self._need_recenter = True
        self._wake.set()

    def set_duck(self, factor: float | None):
        with self._lock:
            if factor:
                if self._saved is None:
                    if self._level is None:
                        return
                    self._saved = self._level
                n = self._grid()
                ducked = max(round(self._saved * factor * n), EDGE_STEPS) / n
                self._home = min(ducked, self._snap_home(self._saved))
                self._apply = self._home
            else:
                if self._saved is None:
                    return
                self._apply = self._saved
                self._home = self._snap_home(self._saved)
                self._saved = None
        self._wake.set()

    def level(self) -> float | None:
        return self._saved if self._saved is not None else self._level

    def last_activity(self) -> float:
        """monotonic time of the last click or our own set."""
        return max(self._last_dial, self._last_set[0])

    # ---------------------------------------------------------------- backend-facing
    def on_level(self, level: float, ours: bool, now: float | None = None):
        """Every level change, from any thread."""
        now = time.monotonic() if now is None else now
        trace.debug("lvl  %5.1f %s", level * 100, "ours" if ours else "")
        with self._lock:
            if ours:
                self._level = level
                self._from_dial = False
                return
            prev = self._level
            if prev is None:
                self._level = level
                return
            step = self.step
            d = level - prev

            t_set, before, target, retries = self._last_set
            if before is not None and now - t_set < STALE_S:
                if abs(level - target) < CLICK_MIN * step:
                    self._last_set = (t_set, None, target, 0)          # buds took our level
                else:
                    d = level - before                                 # still on their old level
                    self._last_set = (t_set, level, target, max(retries - 1, 0))
                    if retries > 0:
                        self._reapply = target
                        self._wake.set()
                    if abs(d) < CLICK_MIN * step:
                        trace.debug("     stale echo ignored, re-sending %.1f", target * 100)
                        return
                    trace.debug("     click before buds took our level: measured from %.1f", before * 100)

            self._level = level
            if abs(d) < CLICK_MIN * step:
                self._from_dial = True
                return                                                 # echo of ours, or a keyboard nudge

            # floor(+0.3), not round: one click from an off-grid level (1.67 steps) stays 1,
            # a folded double (2.1 steps) stays 2. Capped so a glitch never becomes a burst.
            clicks = min(MAX_CLICKS, max(1, int(abs(d) / step + 0.3)))
            delta = clicks if d > 0 else -clicks
            if self._from_dial and clicks == 1 and 0.03 < abs(d) < 0.15:
                self.step = 0.5 * step + 0.5 * abs(d)
            self._from_dial = True

            self._last_move = self._last_dial = now
            if not self._passthrough:
                k = round(level * self._grid())
                if k <= EDGE_STEPS or k >= self._grid() - EDGE_STEPS:
                    self._last_move = 0.0                              # at an end: recenter now
                self._need_recenter = True
        trace.debug("     delta=%+d (step %.2f%%)", delta, self.step * 100)
        self.emit(InputEvent(Kind.ROTATE, delta, self.source))
        self._wake.set()

    # ---------------------------------------------------------------- internals
    def _grid(self) -> int:
        return max(round(1 / self.step), 2 * EDGE_STEPS + 3)

    def _snap_home(self, lvl: float) -> float:
        """Nearest point on the buds' grid, EDGE_STEPS+1 clicks away from both ends."""
        n = self._grid()
        k = min(max(round(lvl * n), EDGE_STEPS + 1), n - EDGE_STEPS - 1)
        return k / n

    def _set(self, level: float, why: str, force: bool = False):
        with self._lock:
            before = self._level
            if not force and before is not None and abs(before - level) < 1e-3:
                return
            if not force:
                self._last_set = (time.monotonic(), before, level, 2)
        trace.debug("set  %5.1f (%s)", level * 100, why)
        try:
            self.backend.set_level(level)
        except Exception:
            log.exception("set level failed")

    def _worker(self):
        init = getattr(self.backend, "thread_init", None)
        if init:
            init()
        while True:
            with self._lock:
                target, self._apply = self._apply, None
                again, self._reapply = self._reapply, None
            if target is not None:
                self._set(target, "duck/restore")
            if again is not None:
                self._set(again, "re-send after buds lagged", force=True)
            if self._stop.is_set():
                break
            if self._need_recenter:
                wait = RECENTER_IDLE_S - (time.monotonic() - self._last_move)
                if wait <= 0:
                    with self._lock:
                        home, self._need_recenter = self._home, False
                        skip = self._passthrough or home is None
                    if not skip:
                        self._set(home, "recenter")
                    continue
                self._wake.wait(wait)
            else:
                self._wake.wait(1.0)
            self._wake.clear()
        self._stopped.set()
