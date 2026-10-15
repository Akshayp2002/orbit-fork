"""Dial rotation, read through Bluetooth absolute volume.

The CMF dial sends AVRCP absolute-volume changes: one detent = 1/16 of the range.
Windows applies them to the buds' render endpoint. We get an
IAudioEndpointVolumeCallback per change and turn the difference into detents.

Passthrough off ("consume"): after the user stops turning, we put the volume
back where it was, tagged with our own event-context GUID so we ignore the echo.
If the level gets near the ends mid-spin we recenter immediately, otherwise the
buds stop reporting at 0 / 100 and the dial would feel dead in one direction.

Small changes (keyboard volume keys = 2%, slider drags) are below half a detent
and are ignored on their own.
"""
from __future__ import annotations

import ctypes
import logging
import threading
import time
import uuid
import warnings

import comtypes
from pycaw.callbacks import AudioEndpointVolumeCallback, MMNotificationClient
from pycaw.pycaw import AudioUtilities

from orbit.core.events import Capability, InputEvent, Kind
from orbit.platform.base import Emit, RotationSource

log = logging.getLogger("orbit.volume")
warnings.filterwarnings("ignore", module="pycaw")

STEPS = 16                 # AVRCP absolute volume detents across 0..100%
RECENTER_IDLE_S = 0.9      # quiet time before we restore the level (slow wheel browsing stays clear of it)
SETTLE_S = 0.3             # after a recenter the buds may echo a stale level then correct it...
COALESCE_S = 0.04          # ...so in that window, detents are summed over 40 ms and a -2/+2 pair cancels
EDGE_STEPS = 2             # recenter immediately when within this many detents of an end
OUR_CONTEXT = comtypes.GUID("{" + str(uuid.UUID("5f0c2a1e-6d3b-4c9a-9a47-0b1e7a1d1a11")) + "}")


class _VolCb(AudioEndpointVolumeCallback):
    def __init__(self, owner, dev_id):
        super().__init__()
        self.owner, self.dev_id = owner, dev_id

    def on_notify(self, new_volume, new_mute, event_context, channels, channel_volumes):
        self.owner._on_change(self.dev_id, new_volume, event_context.contents)


class _DevCb(MMNotificationClient):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def on_device_state_changed(self, *a):
        self.owner._rebind_soon()

    def on_device_added(self, *a):
        self.owner._rebind_soon()

    def on_device_removed(self, *a):
        self.owner._rebind_soon()

    def on_default_device_changed(self, *a): ...
    def on_property_value_changed(self, *a): ...


class VolumeRotationSource(RotationSource):
    name = "avrcp-volume"
    capabilities = frozenset({Capability.ROTATE})

    def __init__(self, match: str):
        self.match = match.lower()
        self._emit: Emit | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._passthrough = True
        self._bound: dict[str, tuple] = {}   # dev_id -> (AudioDevice, callback)
        self._baseline: dict[str, float] = {}
        self._home: float | None = None
        self._last_move = 0.0
        self._need_recenter = False
        self._need_rebind = True
        self._dev_cb = None
        self._recentered_at = 0.0
        self._last_dial = 0.0
        self._pending = 0
        self._flush_timer: threading.Timer | None = None

    # ---------------------------------------------------------------- API
    def start(self, emit):
        self._emit = emit
        threading.Thread(target=self._worker, name="volume-worker", daemon=True).start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def set_passthrough(self, on):
        with self._lock:
            if on == self._passthrough:
                return
            self._passthrough = on
            if not on:
                lvl = self._any_level()
                if lvl is not None:
                    self._home = self._clamp_home(lvl)
                    self._need_recenter = True
        self._wake.set()

    def level(self):
        return self._any_level()

    def last_activity(self) -> float:
        """monotonic time of the last dial detent or our own recenter (both pop the OS volume flyout)."""
        return max(self._last_dial, self._recentered_at)

    def describe(self):
        names = [d.FriendlyName for d, _ in self._bound.values()]
        return f"{self.name} on {names or 'no device yet'}"

    # ---------------------------------------------------------------- internals
    def _any_level(self):
        for dev_id, lvl in self._baseline.items():
            return lvl
        return None

    @staticmethod
    def _clamp_home(lvl):
        s = min(max(round(lvl * STEPS), EDGE_STEPS + 1), STEPS - EDGE_STEPS - 1)
        return s / STEPS

    def _rebind_soon(self):
        self._need_rebind = True
        self._wake.set()

    def _on_change(self, dev_id, vol, ctx):
        if ctx == OUR_CONTEXT:
            with self._lock:
                self._baseline[dev_id] = vol
            return
        with self._lock:
            prev = self._baseline.get(dev_id)
            self._baseline[dev_id] = vol
            if prev is None:
                return
            delta = round((vol - prev) * STEPS)
            if delta == 0:
                return
            self._last_move = self._last_dial = time.monotonic()
            if not self._passthrough:
                s = round(vol * STEPS)
                if s <= EDGE_STEPS or s >= STEPS - EDGE_STEPS:
                    self._last_move = 0.0      # recenter right away
                self._need_recenter = True
            settling = time.monotonic() - self._recentered_at < SETTLE_S
            if settling:
                self._pending += delta
                if self._flush_timer is None:
                    self._flush_timer = threading.Timer(COALESCE_S, self._flush)
                    self._flush_timer.start()
        if not settling:
            self._send(delta)
        self._wake.set()

    def _flush(self):
        with self._lock:
            delta, self._pending, self._flush_timer = self._pending, 0, None
        if delta:
            self._send(delta)

    def _send(self, delta):
        if self._emit:
            self._emit(InputEvent(Kind.ROTATE, delta, self.name))

    def _bind(self):
        for dev, cb in self._bound.values():
            try:
                dev.EndpointVolume.UnregisterControlChangeNotify(cb)
            except Exception:
                pass
        self._bound.clear()
        enum = AudioUtilities.GetDeviceEnumerator()
        coll = enum.EnumAudioEndpoints(0, 1)  # eRender, DEVICE_STATE_ACTIVE
        for i in range(coll.GetCount()):
            dev = AudioUtilities.CreateDevice(coll.Item(i))
            name = dev.FriendlyName or ""
            if self.match not in name.lower():
                continue
            cb = _VolCb(self, dev.id)
            dev.EndpointVolume.RegisterControlChangeNotify(cb)
            self._bound[dev.id] = (dev, cb)
            self._baseline[dev.id] = dev.EndpointVolume.GetMasterVolumeLevelScalar()
            log.info("rotation bound to '%s' (level %.0f%%)", name, self._baseline[dev.id] * 100)
        if not self._bound:
            log.warning("no active audio output matching '%s' — dial rotation unavailable until it connects", self.match)

    def _recenter(self):
        with self._lock:
            home, self._need_recenter = self._home, False
            if self._passthrough or home is None:
                return
        for dev_id, (dev, _) in self._bound.items():
            if abs(self._baseline.get(dev_id, home) - home) > 1e-3:
                self._recentered_at = time.monotonic()
                dev.EndpointVolume.SetMasterVolumeLevelScalar(home, ctypes.byref(OUR_CONTEXT))

    def _worker(self):
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        self._dev_cb = _DevCb(self)
        AudioUtilities.GetDeviceEnumerator().RegisterEndpointNotificationCallback(self._dev_cb)
        while not self._stop.is_set():
            if self._need_rebind:
                self._need_rebind = False
                time.sleep(0.3)  # let the driver settle after connect
                try:
                    self._bind()
                except Exception:
                    log.exception("bind failed")
            if self._need_recenter:
                wait = RECENTER_IDLE_S - (time.monotonic() - self._last_move)
                if wait <= 0:
                    try:
                        self._recenter()
                    except Exception:
                        log.exception("recenter failed")
                    continue
                self._wake.wait(wait)
            else:
                self._wake.wait(1.0)
            self._wake.clear()
