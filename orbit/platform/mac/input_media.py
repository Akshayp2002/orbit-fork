"""macOS: dial presses via MPRemoteCommandCenter.

The buds' AVRCP play/pause/next/previous go to the "now playing" app. Orbit
becomes it: registers the commands, sets playbackState = Playing (macOS does not
infer it - developer.apple.com/forums/thread/685333) and loops silence through
AVAudioEngine so it stays the most recent player.

    toggle / play / pause -> CLICK,  next -> DOUBLE,  previous -> TRIPLE

Handlers run on the main thread; Qt's event loop on macOS is the Cocoa run loop,
so blocks dispatched there are serviced.
"""
from __future__ import annotations

import logging
import time

from orbit.core.events import Capability, InputEvent, Kind
from orbit.platform.base import Emit, InputSource

log = logging.getLogger("orbit.media")
SESSION_TITLE = "Orbit Dial"


class MacMediaButtonSource(InputSource):
    name = "mpremote"
    capabilities = frozenset({Capability.CLICKS})

    def __init__(self):
        self._emit: Emit | None = None
        self._engine = None
        self._node = None
        self._buffer = None
        self._handlers = []          # keep blocks alive
        self._last_assert = 0.0

    def start(self, emit):
        from MediaPlayer import (MPMediaItemPropertyArtist, MPMediaItemPropertyTitle,
                                 MPNowPlayingInfoCenter, MPRemoteCommandCenter)

        self._emit = emit
        cc = MPRemoteCommandCenter.sharedCommandCenter()
        for cmd, kind in ((cc.togglePlayPauseCommand(), Kind.CLICK), (cc.playCommand(), Kind.CLICK),
                          (cc.pauseCommand(), Kind.CLICK), (cc.nextTrackCommand(), Kind.DOUBLE),
                          (cc.previousTrackCommand(), Kind.TRIPLE)):
            h = self._handler(kind)
            self._handlers.append(h)
            cmd.setEnabled_(True)
            cmd.addTargetWithHandler_(h)
        MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(
            {MPMediaItemPropertyTitle: SESSION_TITLE, MPMediaItemPropertyArtist: "dial input"})
        self._start_silence()
        self.reassert()
        log.info("now-playing session active")

    def _handler(self, kind):
        def h(event):
            if self._emit:
                self._emit(InputEvent(kind, 0, self.name))
            return 0          # MPRemoteCommandHandlerStatusSuccess
        return h

    def _start_silence(self):
        from AVFoundation import AVAudioEngine, AVAudioPCMBuffer, AVAudioPlayerNode

        eng = AVAudioEngine.alloc().init()
        node = AVAudioPlayerNode.alloc().init()
        eng.attachNode_(node)
        fmt = eng.mainMixerNode().outputFormatForBus_(0)
        eng.connect_to_format_(node, eng.mainMixerNode(), fmt)
        frames = int(fmt.sampleRate() / 10) or 4800
        buf = AVAudioPCMBuffer.alloc().initWithPCMFormat_frameCapacity_(fmt, frames)
        buf.setFrameLength_(frames)                  # zero-filled = silence
        ok, err = eng.startAndReturnError_(None)
        if not ok:
            log.warning("silent audio engine failed to start: %s", err)
            return
        node.scheduleBuffer_atTime_options_completionHandler_(buf, None, 1, None)  # 1 = Loops
        node.play()
        self._engine, self._node, self._buffer = eng, node, buf

    def reassert(self):
        """Become the now-playing app again (another player may have taken over)."""
        from MediaPlayer import MPNowPlayingInfoCenter, MPNowPlayingPlaybackStatePlaying

        MPNowPlayingInfoCenter.defaultCenter().setPlaybackState_(MPNowPlayingPlaybackStatePlaying)
        if self._engine is not None and not self._engine.isRunning():
            self._engine.startAndReturnError_(None)
            self._node.play()
        self._last_assert = time.monotonic()

    def observe(self, ev):
        # the wheel is about to need presses: make sure they'll come to us
        if ev.kind in (Kind.ROTATE, Kind.DOUBLE) and time.monotonic() - self._last_assert > 2.0:
            self._last_assert = time.monotonic()
            from PyObjCTools import AppHelper
            AppHelper.callAfter(self._safe_reassert)     # observe() runs on source threads

    def _safe_reassert(self):
        try:
            self.reassert()
        except Exception:
            log.exception("reassert failed")

    def stop(self):
        try:
            from MediaPlayer import MPNowPlayingInfoCenter
            MPNowPlayingInfoCenter.defaultCenter().setPlaybackState_(3)   # stopped
            if self._engine is not None:
                self._engine.stop()
        except Exception:
            pass
