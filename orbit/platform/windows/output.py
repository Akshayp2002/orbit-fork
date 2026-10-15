"""Windows Output: SendInput keys/scroll, media forwarding, launching."""
from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes as wt
import logging
import os
import threading
from orbit.platform.base import Output

log = logging.getLogger("orbit.output")
user32 = ctypes.WinDLL("user32", use_last_error=True)

VK = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "cmd": 0x5B,
    "tab": 0x09, "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "plus": 0xBB, "equals": 0xBB, "minus": 0xBD, "comma": 0xBC, "period": 0xBE, "slash": 0xBF,
    "semicolon": 0xBA, "quote": 0xDE, "backquote": 0xC0, "lbracket": 0xDB, "rbracket": 0xDD,
    "backslash": 0xDC, "printscreen": 0x2C, "capslock": 0x14, "menu": 0x5D,
    "volumeup": 0xAF, "volumedown": 0xAE, "mute": 0xAD,
}
VK.update({f"f{i}": 0x6F + i for i in range(1, 25)})
VK.update({c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz0123456789"})
EXTENDED = {0x5B, 0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28, 0x5D, 0x2C}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _U)]


ORBIT_TAG = 0x0B17D1A1  # dwExtraInfo marker so our own input is recognisable


def _key(vk, up=False):
    i = INPUT(type=1)
    i.u.ki = KEYBDINPUT(vk, 0, (2 if up else 0) | (1 if vk in EXTENDED else 0), 0, ORBIT_TAG)
    return i


def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    if user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)) != len(inputs):
        log.warning("SendInput blocked (err %d) — target may be elevated or secure desktop", ctypes.get_last_error())


def vk_of(name: str) -> int:
    name = name.strip().lower()
    if name not in VK:
        raise ValueError(f"unknown key '{name}'")
    return VK[name]


class WindowsOutput(Output):
    def __init__(self, media_source=None):
        self.media_source = media_source
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, name="media-forward", daemon=True).start()
        self._mgr = None

    # ---------------- keys
    def keys(self, combo):
        vks = [vk_of(k) for k in combo.split("+")] if combo.strip() != "+" else [VK["plus"]]
        _send(*[_key(v) for v in vks], *[_key(v, True) for v in reversed(vks)])

    def key_down(self, key):
        _send(_key(vk_of(key)))

    def key_up(self, key):
        _send(_key(vk_of(key), True))

    # ---------------- scroll
    def scroll(self, notches, horizontal=False):
        i = INPUT(type=0)
        amount = int(-notches * 120) if not horizontal else int(notches * 120)
        i.u.mi = MOUSEINPUT(0, 0, ctypes.c_uint32(amount).value, 0x01000 if horizontal else 0x0800, 0, ORBIT_TAG)
        _send(i)

    # ---------------- media (to the real player, never to ourselves)
    def media(self, command):
        asyncio.run_coroutine_threadsafe(self._media(command), self._loop)

    async def _media(self, command):
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as M,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as S)
        if self._mgr is None:
            self._mgr = await M.request_async()
        own = getattr(self.media_source, "own_aumid", None)
        others = [s for s in self._mgr.get_sessions() if s.source_app_user_model_id != own]
        if not others:
            log.info("media:%s — no other player open", command)
            return
        playing = [s for s in others if s.get_playback_info().playback_status == S.PLAYING]
        target = (playing or others)[0]
        fn = {"play_pause": target.try_toggle_play_pause_async, "next": target.try_skip_next_async,
              "previous": target.try_skip_previous_async, "stop": target.try_stop_async}.get(command)
        if not fn:
            log.error("unknown media command '%s'", command)
            return
        await fn()
        log.info("media:%s -> %s", command, target.source_app_user_model_id)
        if self.media_source and command == "play_pause":
            await asyncio.sleep(0.6)   # the player grabs media focus when it starts; take it back
            self.media_source.reassert()

    # ---------------- launch
    def launch(self, target):
        try:
            os.startfile(target)
        except OSError:
            import subprocess
            subprocess.Popen(target, shell=True)

    def active_window_title(self):
        h = user32.GetForegroundWindow()
        n = user32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, buf, n + 1)
        return buf.value
