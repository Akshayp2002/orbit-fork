"""Action strings -> callables.

An action is written in config as "kind:argument", or a list of them run in order:

    keys:ctrl+z          tap a key combo
    scroll:3 / scroll:-3 vertical wheel notches (+ = down)
    hscroll:3            horizontal wheel notches (+ = right)
    media:play_pause     play_pause | next | previous | stop (sent to the real player)
    launch:notepad.exe   open app / file / URL
    open_wheel           open the wheel menu
    tool:<id>            switch the active tool
    last_tool            flip back to the previous tool
    none                 do nothing

Engine-level kinds (open_wheel, tool:) are resolved by the engine, everything
else goes straight to the platform Output.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from orbit.core.engine import Engine


@dataclass(frozen=True)
class Action:
    spec: str
    run: Callable[["Engine"], None]

    def __call__(self, engine: "Engine") -> None:
        self.run(engine)

    def __str__(self):
        return self.spec


NOOP = Action("none", lambda e: None)


def _one(spec: str) -> Action:
    spec = spec.strip()
    kind, _, arg = spec.partition(":")
    kind, arg = kind.strip().lower(), arg.strip()

    if kind in ("", "none"):
        return NOOP
    if kind == "keys":
        return Action(spec, lambda e: e.out.keys(arg))
    if kind in ("scroll", "hscroll"):
        n = float(arg or 1)
        return Action(spec, lambda e: e.out.scroll(n, horizontal=kind == "hscroll"))
    if kind == "media":
        return Action(spec, lambda e: e.out.media(arg))
    if kind == "launch":
        return Action(spec, lambda e: e.out.launch(arg))
    if kind == "open_wheel":
        return Action(spec, lambda e: e.open_wheel())
    if kind == "tool":
        return Action(spec, lambda e: e.set_tool(arg))
    if kind == "last_tool":
        return Action(spec, lambda e: e.last_tool())
    raise ValueError(f"Unknown action kind '{kind}' in '{spec}'")


def parse(spec: str | list[str] | None) -> Action:
    if spec is None:
        return NOOP
    if isinstance(spec, str):
        return _one(spec)
    parts = [_one(s) for s in spec]
    return Action(" ; ".join(map(str, parts)), lambda e: [p(e) for p in parts])
