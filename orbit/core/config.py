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
        "triple": "last_tool",
        "open_wheel": ["double", "hold"],
        "open_wheel_fallback": "triple",
    },
    "wheel": {"items": [], "dismiss_after_ms": 6000, "duck_volume": 0.5, "accel": 1},
    "ui": {"hud_ms": 1400, "scale": 1.0, "accent": "#7C9CFF", "hide_os_volume_flyout": True,
           "appearance": "dark"},
    "tools": {},
    "claude": {"shortcut": "ctrl+alt+v"},
}

APPEARANCES = ("system", "dark", "light")
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
    # packaged app (PyInstaller): ship the default, copy it where the user can edit it
    bundled = Path(getattr(sys, "_MEIPASS", "")) / "config.toml"
    if bundled.exists():
        dest = user_config_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(bundled.read_bytes())
        return dest
    raise FileNotFoundError("no config.toml found (looked in --config, user dir, project dir)")


PLATFORM_KEYS = {"win32": "windows", "darwin": "mac", "linux": "linux"}


def current_platform() -> str:
    return PLATFORM_KEYS.get(sys.platform, sys.platform)


def apply_platform(cfg: dict, platform: str | None = None) -> dict:
    """Merge [platforms.<name>] over the shared config, e.g. Cmd instead of Ctrl on mac.
    A tool or gesture set there replaces individual keys, not the whole table."""
    platform = platform or current_platform()
    overrides = cfg.pop("platforms", {})
    return _merge(cfg, overrides.get(platform, {}))


def load(explicit: str | None = None, platform: str | None = None,
         user_settings: dict | None = None) -> tuple[dict, Path]:
    """`user_settings`: the Settings window's choices (orbit.core.settings), layered last."""
    path = find(explicit)
    with path.open("rb") as f:
        cfg = apply_platform(_merge(DEFAULTS, tomllib.load(f)), platform)
    if user_settings:
        from orbit.core import settings
        cfg = settings.apply(cfg, user_settings)
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
    if cfg["ui"].get("appearance") not in APPEARANCES:
        raise ValueError(f"config: ui.appearance must be one of {list(APPEARANCES)}")
    dt = cfg.get("default_tool")
    if dt and dt not in cfg["tools"]:
        raise ValueError(f"config: default_tool '{dt}' is not a tool")
    names = {"click", "double", "triple", "hold"}
    g_cfg = cfg["gestures"]
    opens = g_cfg.get("open_wheel", [])
    opens = [opens] if isinstance(opens, str) else opens
    bad = [o for o in [*opens, g_cfg.get("open_wheel_fallback", "triple")] if o not in names]
    if bad:
        raise ValueError(f"config: gestures.open_wheel must use {sorted(names)}, got {bad}")
    for g, a in g_cfg.items():
        if g not in ("open_wheel", "open_wheel_fallback"):
            actions.parse(a)
