"""Dial presses, read as media commands.

Bluetooth AVRCP play/pause/next/previous never reach the keyboard path on
Windows; they go straight to the *current* media session (SMTC). So we become a
media session ourselves: a MediaPlayer looping silence with our own
SystemMediaTransportControls. Buttons then land in our handler:

    PLAY / PAUSE -> CLICK,  NEXT -> DOUBLE,  PREVIOUS -> TRIPLE
    (that matches the Nothing X setup: press, double, triple press)

Guard: when another player (Spotify, a browser tab) starts playing, Windows may
make it current and our presses vanish. We watch the session manager and
re-assert ourselves by restarting our silent playback.

The real player is still reachable: Output.media() forwards commands to it.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import wave
from pathlib import Path

from orbit.core.events import Capability, InputEvent, Kind
from orbit.platform.base import Emit, InputSource

log = logging.getLogger("orbit.media")

SESSION_TITLE = "Orbit Dial"
BUTTON_MAP = {"PLAY": Kind.CLICK, "PAUSE": Kind.CLICK, "NEXT": Kind.DOUBLE, "PREVIOUS": Kind.TRIPLE}


def _silence(path: Path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
            w.writeframes(b"\x00\x00" * 8000 * 10)


class MediaButtonSource(InputSource):
    name = "smtc"
    capabilities = frozenset({Capability.CLICKS})

    def __init__(self, cache_dir: Path, map_overrides: dict | None = None):
        self.cache_dir = cache_dir
        self.map = dict(BUTTON_MAP)
        for k, v in (map_overrides or {}).items():
            self.map[k.upper()] = Kind(v)
        self._emit: Emit | None = None
        self._player = None
        self._smtc = None
        self._tokens = []
        self._mgr = None
        self.own_aumid: str | None = None

    def start(self, emit):
        from winrt.windows.foundation import Uri
        from winrt.windows.media import (MediaPlaybackStatus, MediaPlaybackType,
                                         SystemMediaTransportControlsButton as B)
        from winrt.windows.media.core import MediaSource
        from winrt.windows.media.playback import MediaPlayer

        self._emit = emit
        silence = self.cache_dir / "silence.wav"
        _silence(silence)

        p = MediaPlayer()
        p.command_manager.is_enabled = False
        p.volume = 0.0
        s = p.system_media_transport_controls
        for attr in ("is_enabled", "is_play_enabled", "is_pause_enabled", "is_next_enabled",
                     "is_previous_enabled", "is_stop_enabled"):
            setattr(s, attr, True)
        du = s.display_updater
        du.type = MediaPlaybackType.MUSIC
        du.music_properties.title = SESSION_TITLE
        du.music_properties.artist = "dial input"
        du.update()
        s.playback_status = MediaPlaybackStatus.PLAYING

        names = {v: k for k, v in vars(B).items() if not k.startswith("_") and isinstance(v, int)}

        def on_button(_s, args):
            kind = self.map.get(names.get(args.button, ""))
            if kind and self._emit:
                self._emit(InputEvent(kind, 0, self.name))

        self._tokens.append(s.add_button_pressed(on_button))
        p.source = MediaSource.create_from_uri(Uri(silence.resolve().as_uri()))
        p.is_looping_enabled = True
        p.play()
        self._player, self._smtc = p, s
        threading.Thread(target=self._guard, name="smtc-guard", daemon=True).start()
        log.info("media session active")

    def stop(self):
        if self._player:
            self._player.pause()

    def reassert(self):
        """Make our session the most recent player again."""
        from winrt.windows.media import MediaPlaybackStatus
        if not self._player:
            return
        self._smtc.playback_status = MediaPlaybackStatus.PAUSED
        self._player.pause()
        self._player.play()
        self._smtc.playback_status = MediaPlaybackStatus.PLAYING

    def _guard(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M

        async def run():
            self._mgr = await M.request_async()
            await asyncio.sleep(0.5)
            await self._learn_own_aumid()

            def changed(*_):
                cur = self._mgr.get_current_session()
                aumid = cur.source_app_user_model_id if cur else None
                if aumid and self.own_aumid and aumid != self.own_aumid:
                    log.info("media focus taken by %s — reasserting", aumid)
                    threading.Timer(0.4, self.reassert).start()

            self._mgr.add_current_session_changed(changed)
            while True:
                await asyncio.sleep(3600)

        try:
            asyncio.run(run())
        except Exception:
            log.exception("media guard stopped")

    async def _learn_own_aumid(self):
        for sess in self._mgr.get_sessions():
            props = await sess.try_get_media_properties_async()
            if props and props.title == SESSION_TITLE:
                self.own_aumid = sess.source_app_user_model_id
                log.info("own media session id: %s", self.own_aumid)
                break
        cur = self._mgr.get_current_session()
        if cur and self.own_aumid and cur.source_app_user_model_id != self.own_aumid:
            log.info("%s holds media focus at startup — reasserting", cur.source_app_user_model_id)
            self.reassert()
