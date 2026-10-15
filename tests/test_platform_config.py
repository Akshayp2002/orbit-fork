"""Per-platform config overrides and macOS key parsing (pure, runs anywhere)."""
import pytest

from orbit.core import config as config_mod
from orbit.platform.mac import keys as K


def test_mac_overrides_merge_key_by_key():
    cfg, _ = config_mod.load(platform="mac")
    zoom = cfg["tools"]["zoom"]
    assert zoom["rotate_cw"] == "keys:cmd+equals"          # overridden
    assert zoom["label"] == "Zoom" and zoom["type"] == "keys"  # kept from shared table
    assert cfg["tools"]["switcher"]["modifier"] == "cmd"
    assert cfg["gestures"]["hold"] == "none"
    assert "platforms" not in cfg


def test_windows_keeps_shared_values():
    cfg, _ = config_mod.load(platform="windows")
    assert cfg["tools"]["zoom"]["rotate_cw"] == "keys:ctrl+plus"
    assert cfg["tools"]["switcher"].get("modifier", "alt") == "alt"


def test_mac_combo_parsing():
    mods, flags, main = K.parse("cmd+shift+z")
    assert mods == [K.KEYCODES["cmd"], K.KEYCODES["shift"]]
    assert flags == K.FLAGS["cmd"] | K.FLAGS["shift"]
    assert main == 0x06


def test_windows_names_alias_on_mac():
    assert K.parse("win+tab")[1] == K.FLAGS["cmd"]
    assert K.keycode("option") == K.KEYCODES["alt"]


def test_every_mac_override_combo_is_valid():
    cfg, _ = config_mod.load(platform="mac")
    specs = []
    for t in cfg["tools"].values():
        for k in ("rotate_cw", "rotate_ccw", "click", "double", "triple", "run"):
            v = t.get(k)
            specs += v if isinstance(v, list) else [v] if v else []
    for s in specs:
        if s.startswith("keys:"):
            K.parse(s[5:])                                   # raises on unknown keys


def test_bad_mac_combo_rejected():
    with pytest.raises(ValueError):
        K.parse("hyper+z")
