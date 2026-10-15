"""Tools: the "mode" the dial is in.

Surface-Dial model: the wheel picks a tool, then rotate/press act on that tool
until another one is picked. One-shot wheel items ("action" type) run once and
leave the current tool active.

Add a new tool type by subclassing Tool and registering it in TOOL_TYPES.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from orbit.core import actions
from orbit.core.actions import Action

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
        return Hud(self.icon, self.label, str(a))

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
        self._last = 0.0

    def _gain(self) -> int:
        """Fast spins go further, slow turns stay exact (iPod / MX wheel behaviour)."""
        now = time.monotonic()
        dt, self._last = now - self._last, now
        if not self.accel:
            return 1
        return 3 if dt < 0.07 else 2 if dt < 0.14 else 1

    def rotate(self, e, delta):
        a = self.cw if delta > 0 else self.ccw
        for _ in range(abs(delta) * self._gain()):
            a(e)
        return Hud(self.icon, self.label, self.detail_cw if delta > 0 else self.detail_ccw, None, 1 if delta > 0 else -1)


class WindowSwitcherTool(Tool):
    """Rotate = walk the native Alt+Tab list; press or pause = land on that window."""

    def __init__(self, tid, cfg):
        super().__init__(tid, cfg)
        self.commit_after = cfg.get("commit_after_ms", 900) / 1000
        self._open = False
        self._last = 0.0

    def rotate(self, e, delta):
        if not self._open:
            e.out.key_down("alt")
            self._open = True
        for _ in range(abs(delta)):
            e.out.keys("tab" if delta > 0 else "shift+tab")
        self._last = time.monotonic()
        return None  # the OS switcher is the feedback

    def _commit(self, e):
        if self._open:
            e.out.key_up("alt")
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
    "window_switcher": WindowSwitcherTool,
    "action": ActionItem,
}


def build(tid: str, cfg: dict) -> Tool:
    t = cfg.get("type", "keys")
    if t not in TOOL_TYPES:
        raise ValueError(f"tool '{tid}': unknown type '{t}' (known: {', '.join(TOOL_TYPES)})")
    return TOOL_TYPES[t](tid, cfg)
