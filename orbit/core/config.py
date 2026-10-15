"""Config: TOML file, validated, with defaults filled in."""
from __future__ import annotations

import copy
import os
import sys
import tomllib
from pathlib import Path

DEFAULTS: dict = {
    "device": {"audio_endpoint_match": "CMF Buds Pro 2"},
    "gestures": {
        "click": "media:play_pause",
        "double": "media:next",
        "triple": "media:previous",
        "hold": "open_wheel",
        "open_wheel_fallback": "triple",
    },
    "wheel": {"items": [], "dismiss_after_ms": 6000, "duck_volume": 0.5},
    "ui": {"sound": False, "hud_ms": 1400, "scale": 1.0, "accent": "#7C9CFF", "hide_os_volume_flyout": True},
    "tools": {},
}

PROJECT_CONFIG = Path(__file__).resolve().parents[2] / "config.toml"


def user_config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "Orbit" / "config.toml"


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def find(explicit: str | None) -> Path:
    for p in (Path(explicit) if explicit else None, user_config_path(), PROJECT_CONFIG):
        if p and p.exists():
            return p
    raise FileNotFoundError("no config.toml found (looked in --config, user dir, project dir)")


def load(explicit: str | None = None) -> tuple[dict, Path]:
    path = find(explicit)
    with path.open("rb") as f:
        cfg = _merge(DEFAULTS, tomllib.load(f))
    validate(cfg)
    return cfg, path


def validate(cfg: dict) -> None:
    from orbit.core import actions, tools

    if not cfg["tools"]:
        raise ValueError("config: [tools] is empty")
    for tid, tc in cfg["tools"].items():
        tools.build(tid, tc)  # raises on bad type / bad action strings
    missing = [i for i in cfg["wheel"]["items"] if i not in cfg["tools"]]
    if missing:
        raise ValueError(f"config: wheel.items references unknown tools: {missing}")
    if not cfg["wheel"]["items"]:
        cfg["wheel"]["items"] = list(cfg["tools"])
    if len(cfg["wheel"]["items"]) > 12:
        raise ValueError("config: more than 12 wheel items is unusable on a dial; keep it to 8 or fewer")
    dt = cfg.get("default_tool")
    if dt and dt not in cfg["tools"]:
        raise ValueError(f"config: default_tool '{dt}' is not a tool")
    for g, a in cfg["gestures"].items():
        if g != "open_wheel_fallback":
            actions.parse(a)
