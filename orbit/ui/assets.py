"""Icons (font glyphs) and generated tick sounds."""
from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

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


def _tone(path: Path, freq: float, ms: float, vol: float):
    rate = 44100
    n = int(rate * ms / 1000)
    frames = bytearray()
    for i in range(n):
        t = i / rate
        env = math.exp(-t * 900 / ms)              # fast exponential decay = "tick"
        s = math.sin(2 * math.pi * freq * t) * env * vol
        frames += struct.pack("<h", int(s * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(bytes(frames))


def ensure_sounds(cache: Path) -> dict[str, Path]:
    cache.mkdir(parents=True, exist_ok=True)
    spec = {"tick": (2200, 18, 0.22), "wrap": (1500, 26, 0.26), "select": (880, 70, 0.30),
            "open": (660, 60, 0.18), "close": (520, 60, 0.15)}
    out = {}
    for name, (f, ms, v) in spec.items():
        p = cache / f"{name}.wav"
        if not p.exists():
            _tone(p, f, ms, v)
        out[name] = p
    return out
