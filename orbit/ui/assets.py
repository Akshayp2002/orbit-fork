"""Icons (font glyphs)."""
from __future__ import annotations

import sys

# Segoe Fluent Icons (Windows 11) code points. Config may also give a raw glyph.
GLYPHS = {
    "volume": "", "mute": "", "windows": "", "scroll": "",
    "zoom": "", "undo": "", "redo": "", "desktops": "",
    "tabs": "", "mic": "", "play": "", "settings": "",
    "camera": "", "lock": "", "brightness": "", "edit": "",
    "search": "", "app": "", "star": "", "bolt": "",
}
ICON_FONT = "Segoe Fluent Icons" if sys.platform == "win32" else ""


def glyph(icon: str, label: str) -> str:
    if icon in GLYPHS and ICON_FONT:
        return GLYPHS[icon]
    if len(icon) == 1:
        return icon
    return (label or "?")[:1].upper()

