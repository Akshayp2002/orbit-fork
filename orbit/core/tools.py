"""Tools: the "mode" the dial is in.

Surface-Dial model: the wheel picks a tool, then rotate/press act on that tool
until another one is picked. One-shot wheel items ("action" type) run once and
leave the current tool active.

Add a new tool type by subclassing Tool and registering it in TOOL_TYPES.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from orbit.core import actions
from orbit.core.actions import Action
from orbit.core.motion import SpinTracker

if TYPE_CHECKING:
    from orbit.core.engine import Engine


@dataclass
class Hud:
    """What the HUD should show after an interaction."""
    icon: str
    title: str
    detail: str = ""
    progress: float | None = None   # 0..1 shows a bar, None hides it
    direction: int = 0              # last rotation direction, drives the tick animation


class Tool:
    sticky = True                 # False -> one-shot wheel item
    rotation_passthrough = False  # True -> dial keeps its native rotation effect (volume)

    def __init__(self, tid: str, cfg: dict):
        self.id = tid
        self.label = cfg.get("label", tid.title())
        self.icon = cfg.get("icon", "circle")
        self.cfg = cfg
        self._gesture = {g: actions.parse(cfg[g]) for g in ("click", "double", "triple") if g in cfg}

    # --- lifecycle ---
    def enter(self, e: "Engine") -> None: ...
    def leave(self, e: "Engine") -> None: ...
    def tick(self, e: "Engine", now: float) -> None: ...

    # --- input ---
    def rotate(self, e: "Engine", delta: int) -> Hud | None:
        return None

    def gesture(self, e: "Engine", name: str) -> Hud | None | bool:
        """Return False when the tool does not handle this gesture (engine falls back)."""
        a = self._gesture.get(name)
        if a is None:
            return False
        a(e)
        return Hud(self.icon, self.label, self.cfg.get(f"detail_{name}", str(a)))

    def hud(self, e: "Engine") -> Hud:
        return Hud(self.icon, self.label)

    def to_item(self) -> dict:
        return {"id": self.id, "label": self.label, "icon": self.icon, "sticky": self.sticky}


class VolumeTool(Tool):
    """Rotation stays native volume; we only show it."""
    rotation_passthrough = True

    def rotate(self, e, delta):
        return self.hud(e, delta)

    def hud(self, e, direction=0):
        lvl = e.rotation_level()
        pct = "" if lvl is None else f"{round(lvl * 100)}%"
        return Hud(self.icon, self.label, pct, lvl, direction)


class KeysTool(Tool):
    """Generic: each detent fires rotate_cw / rotate_ccw. Covers scroll, zoom, undo, brush size..."""

    def __init__(self, tid, cfg):
        super().__init__(tid, cfg)
        self.cw = actions.parse(cfg.get("rotate_cw"))
        self.ccw = actions.parse(cfg.get("rotate_ccw"))
        self.detail_cw = cfg.get("detail_cw", "")
        self.detail_ccw = cfg.get("detail_ccw", "")
        self.accel = cfg.get("accel", False)
        # accel: false | true (max 3x) | number (max gain)
        self.max_gain = 3.0 if self.accel is True else float(self.accel or 1)
        self.spin = SpinTracker()

    def rotate(self, e, delta):
        """Fast spins go further, slow clicks stay exact (iPod / MX wheel behaviour)."""
        a = self.cw if delta > 0 else self.ccw
        self.spin.update(delta)
        g = self.spin.gain(self.max_gain)
        n = abs(delta) * g + ((g - 1) if self.spin.catch_up else 0)
        for _ in range(round(n)):
            a(e)
        return Hud(self.icon, self.label, self.detail_cw if delta > 0 else self.detail_ccw, None, 1 if delta > 0 else -1)


class SmoothScrollTool(Tool):
    """Scroll with intent: each detent is an impulse, delivered as fine-grained wheel
    steps at ~120 Hz, so motion stays continuous between the buds' sparse reports.

    Speed is a smoothed estimate, not a per-gap verdict: the buds report at most one
    step every ~0.3 s and drop the clicks in between, so normal turning lands anywhere
    in 0.3-0.8 s and neighbouring gaps differ by chance. Judging each gap alone swung
    the distance per click 2x <-> 8x and read as jumpy (Mac test, Oct 2026). Now speed
    eases toward the turning rate (EMA), the gain curve is gentle, and the top gain
    (~3x) only makes up for the clicks the buds drop. Reversing brakes at once.
    """
    FRAME_S = 1 / 120
    MIN_UNITS = 8                    # smallest wheel delta sent (1 notch = 120 units)
    FAST_GAP = 0.35                  # reports this close: turning faster than the buds report
    SLOW_GAP = 0.90                  # this far apart: deliberate single clicks
    SMOOTH = 0.35                    # how quickly the speed estimate follows the turning

    def __init__(self, tid, cfg):
        super().__init__(tid, cfg)
        self.base = float(cfg.get("notches_per_detent", 1.0))
        self.max_gain = float(cfg.get("max_gain", 4.5))
        glide = float(cfg.get("glide_ms", 300)) / 1000          # momentum decay time constant
        self.momentum_k = 0.8 if glide > 0 else 0.0
        self.glide = max(glide, 1e-3)
        self.ease = max(float(cfg.get("ease_ms", 90)) / 1000, 1e-3)  # how fast an impulse is delivered
        self.horizontal = bool(cfg.get("horizontal", False))
        self._lock = threading.Lock()
        self._pending = 0.0     # notches still to deliver from impulses
        self._vel = 0.0         # notches/s of momentum
        self._carry = 0.0       # sub-MIN_UNITS remainder
        self._dir = 0
        self._out = None
        self._run = False
        self._gen = 0
        self._t = 0.0
        self.speed = 0.0        # 0 = careful clicks .. 1 = faster than the buds can report

    def enter(self, e):
        self._out = e.out
        if not self._run:
            self._run = True
            self._gen += 1
            threading.Thread(target=self._loop, args=(self._gen,), name="smooth-scroll", daemon=True).start()

    def leave(self, e):
        self._run = False
        with self._lock:
            self._pending = self._vel = self._carry = 0.0

    def rotate(self, e, delta):
        if not self._run:
            self.enter(e)
        d = 1 if delta > 0 else -1
        now = time.monotonic()
        gap, self._t = now - self._t, now
        raw = min(1.0, max(0.0, (self.SLOW_GAP - gap) / (self.SLOW_GAP - self.FAST_GAP)))
        if d != self._dir:
            self.speed = 0.0                 # a turn-back is a correction: exact
        else:
            self.speed += self.SMOOTH * (raw - self.speed)
        g = 1 + (self.max_gain - 1) * self.speed ** 2
        impulse = d * self.base * abs(delta) * g
        with self._lock:
            if d != self._dir:            # brake: kill everything going the other way
                self._pending = self._vel = self._carry = 0.0
            self._dir = d
            self._pending += impulse
            # glide only builds with sustained speed
            self._vel += impulse * self.speed ** 2 * self.momentum_k
        detail = "down" if d > 0 else "up"
        if self.speed > 0.5:
            detail += " · fast"
        return Hud(self.icon, self.label, detail, None, d)

    def _loop(self, gen):
        last = time.perf_counter()
        while self._run and gen == self._gen:   # a newer loop replaces this one
            time.sleep(self.FRAME_S)
            now = time.perf_counter()
            dt, last = now - last, now
            with self._lock:
                take = self._pending * (1 - math.exp(-dt / self.ease))
                self._pending -= take
                glide = self._vel * dt
                self._vel *= math.exp(-dt / self.glide)
                if abs(self._vel) < 0.05:
                    self._vel = 0.0
                units = (take + glide) * 120 + self._carry
                send = int(units / self.MIN_UNITS) * self.MIN_UNITS
                self._carry = units - send
            if send and self._out:
                self._out.scroll(send / 120, horizontal=self.horizontal)


class BrightnessTool(Tool):
    """Display brightness. Each detent moves `step`%, fast spins further. Monitor
    writes are slow (DDC/CI ~100 ms), so a writer thread always sends only the
    newest target: a fast spin never queues up stale writes."""

    def __init__(self, tid, cfg):
        super().__init__(tid, cfg)
        self.step = float(cfg.get("step", 5))
        self.max_gain = float(cfg.get("max_gain", 3))
        self.spin = SpinTracker()
        self._level: float | None = None
        self._target: float | None = None
        self._cv = threading.Condition()
        self._out = None
        self._writer = False
        self._last_sync = 0.0

    def enter(self, e):
        self._out = e.out
        if not self._writer:
            self._writer = True
            threading.Thread(target=self._write_loop, name="brightness", daemon=True).start()
        threading.Thread(target=self._sync, daemon=True).start()

    def _sync(self):
        """Read the real level (the user may have moved Twinkle Tray's slider)."""
        lvl = self._out.brightness_get() if self._out else None
        with self._cv:
            if lvl is not None and self._target is None:
                self._level = lvl
            self._last_sync = time.monotonic()

    def rotate(self, e, delta):
        if self._out is None:
            self.enter(e)
        if self._level is None:
            self._sync()                       # first use: one blocking read (~150 ms)
        if self._level is None:
            return Hud(self.icon, self.label, "not available")
        self.spin.update(delta)
        change = delta * self.step * self.spin.gain(self.max_gain)
        with self._cv:
            self._level = min(100.0, max(0.0, self._level + change))
            self._target = self._level
            self._cv.notify()
        return Hud(self.icon, self.label, f"{round(self._level)}%", self._level / 100, 1 if delta > 0 else -1)

    def hud(self, e):
        if self._level is None:
            return Hud(self.icon, self.label)
        return Hud(self.icon, self.label, f"{round(self._level)}%", self._level / 100)

    def _write_loop(self):
        while True:
            with self._cv:
                while self._target is None:
                    self._cv.wait()
                value, self._target = self._target, None
            try:
                self._out.brightness_set(value)
            except Exception:
                pass


class WindowSwitcherTool(Tool):
    """Rotate = walk the native Alt+Tab (mac: Cmd+Tab) list; press or pause = land there."""

    def __init__(self, tid, cfg):
        super().__init__(tid, cfg)
        self.commit_after = cfg.get("commit_after_ms", 900) / 1000
        self.modifier = cfg.get("modifier", "alt")
        self._open = False
        self._last = 0.0

    def rotate(self, e, delta):
        if not self._open:
            e.out.key_down(self.modifier)
            self._open = True
        for _ in range(abs(delta)):
            e.out.keys("tab" if delta > 0 else "shift+tab")
        self._last = time.monotonic()
        return None  # the OS switcher is the feedback

    def _commit(self, e):
        if self._open:
            e.out.key_up(self.modifier)
            self._open = False

    def gesture(self, e, name):
        if name == "click" and self._open:
            self._commit(e)
            return None
        return super().gesture(e, name)

    def tick(self, e, now):
        if self._open and now - self._last > self.commit_after:
            self._commit(e)

    def leave(self, e):
        self._commit(e)


class ActionItem(Tool):
    """One-shot wheel entry: runs `run` when selected, tool stays as it was."""
    sticky = False

    def __init__(self, tid, cfg):
        super().__init__(tid, cfg)
        self.run = actions.parse(cfg.get("run"))

    def fire(self, e) -> Hud:
        self.run(e)
        return Hud(self.icon, self.label, "done")


TOOL_TYPES: dict[str, type[Tool]] = {
    "volume": VolumeTool,
    "keys": KeysTool,
    "smooth_scroll": SmoothScrollTool,
    "brightness": BrightnessTool,
    "window_switcher": WindowSwitcherTool,
    "action": ActionItem,
}


def build(tid: str, cfg: dict) -> Tool:
    t = cfg.get("type", "keys")
    if t not in TOOL_TYPES:
        raise ValueError(f"tool '{tid}': unknown type '{t}' (known: {', '.join(TOOL_TYPES)})")
    return TOOL_TYPES[t](tid, cfg)
