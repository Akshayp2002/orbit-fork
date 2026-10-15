"""Dial rotation, read through the buds' volume.

Each dial click changes the buds' volume by one step, and Windows applies it to
the buds' render endpoint. We get an IAudioEndpointVolumeCallback per change and
turn the difference into clicks.

What the real-device trace taught us (see git history for the timeline):

  * The step size is not fixed. One session showed 1/16 steps, another 1/15
    (40.0 -> 46.7 -> 53.3). So the step is learned from the reports, and any
    change of at least ~a third of a step in one direction counts as a click:
    a reverse click is never rounded away to zero.
  * After we set the level ourselves (recenter / duck), the buds may re-send their
    *old* level once before taking ours. Counting that as turning produced phantom
    multi-click jumps. A report equal to the level from just before our set is
    stale: it is ignored and our level is re-applied.
  * Recenter targets sit on the learned grid so the next click is a clean step.

Passthrough off ("consume"): when the user stops turning we put the level back,
tagged with our event-context GUID so we can tell our changes from the dial's.
Near either end we recenter at once, or the buds stop reporting in that direction.
Keyboard volume keys (2%) and slider drags are below the click threshold.
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
trace = logging.getLogger("orbit.trace")   # step-by-step timeline for latency debugging
warnings.filterwarnings("ignore", module="pycaw")

DEFAULT_STEP = 1 / 16       # first guess; learned from real clicks
CLICK_MIN = 0.35            # fraction of a step that counts as a click (2% keyboard steps don't)
RECENTER_IDLE_S = 0.9       # quiet time before we restore the level
EDGE_STEPS = 2              # recenter at once when this close to either end
MAX_CLICKS = 3              # the buds fold at most ~2 clicks into one report
STALE_S = 0.8              # window after our own set in which the buds may echo their old level
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
        self._stopped = threading.Event()
        self._passthrough = True
        self._bound: dict[str, tuple] = {}     # dev_id -> (AudioDevice, callback)
        self._baseline: dict[str, float] = {}  # last level seen per device
        self._from_dial: dict[str, bool] = {}  # was that last level a dial report (vs our set)?
        self._step = DEFAULT_STEP
        self._home: float | None = None
        self._last_move = 0.0
        self._last_dial = 0.0
        self._need_recenter = False
        self._need_rebind = True
        self._dev_cb = None
        self._saved: float | None = None       # real listening level while ducked
        self._apply: float | None = None       # level the worker should set now
        self._reapply: float | None = None     # same, forced, after a stale echo
        # our most recent set: (time, level before it, level we set, re-applies left)
        self._last_set = (0.0, None, None, 0)

    # ---------------------------------------------------------------- API
    def start(self, emit):
        self._emit = emit
        threading.Thread(target=self._worker, name="volume-worker", daemon=True).start()

    def stop(self):
        self.set_duck(None)          # never leave the user at half volume
        self._stop.set()
        self._wake.set()
        self._stopped.wait(1.0)

    def set_duck(self, factor):
        """factor (e.g. 0.5): lower the level while the wheel is open, so click blips are soft.
        None: restore the real level."""
        with self._lock:
            if factor:
                if self._saved is None:
                    lvl = self._any_level()
                    if lvl is None:
                        return
                    self._saved = lvl
                n = round(1 / self._step)
                ducked = max(round(self._saved * factor * n), EDGE_STEPS) / n
                self._home = min(ducked, self._snap_home(self._saved))
                self._apply = self._home
            else:
                if self._saved is None:
                    return
                self._apply = self._saved
                self._home = self._snap_home(self._saved)
                self._saved = None
        self._wake.set()

    def set_passthrough(self, on):
        with self._lock:
            if on == self._passthrough:
                return
            self._passthrough = on
            if not on:
                lvl = self._any_level()
                if lvl is not None:
                    self._home = self._snap_home(lvl)
                    self._need_recenter = True
        self._wake.set()

    def level(self):
        return self._saved if self._saved is not None else self._any_level()

    def last_activity(self) -> float:
        """monotonic time of the last click or our own set (both pop the OS volume flyout)."""
        return max(self._last_dial, self._last_set[0])

    def describe(self):
        names = [d.FriendlyName for d, _ in self._bound.values()]
        return f"{self.name} on {names or 'no device yet'}"

    # ---------------------------------------------------------------- internals
    def _any_level(self):
        for lvl in self._baseline.values():
            return lvl
        return None

    def _snap_home(self, lvl):
        """Nearest grid point, kept EDGE_STEPS+1 clicks away from both ends."""
        n = max(round(1 / self._step), 2 * EDGE_STEPS + 3)   # the buds' scale has a whole number of steps
        k = min(max(round(lvl * n), EDGE_STEPS + 1), n - EDGE_STEPS - 1)
        return k / n

    def _rebind_soon(self):
        self._need_rebind = True
        self._wake.set()

    def _on_change(self, dev_id, vol, ctx):
        ours = ctx == OUR_CONTEXT
        trace.debug("win  vol=%5.1f %s", vol * 100, "ours" if ours else "")
        now = time.monotonic()
        with self._lock:
            if ours:
                self._baseline[dev_id] = vol
                self._from_dial[dev_id] = False
                return
            prev = self._baseline.get(dev_id)
            if prev is None:
                self._baseline[dev_id] = vol
                return
            step = self._step
            d = vol - prev

            # Until the buds confirm our last set, they may still be on their old level: they
            # re-send it (stale echo) or report a click relative to it. Measure from there.
            t_set, before, target, retries = self._last_set
            if before is not None and now - t_set < STALE_S:
                if abs(vol - target) < CLICK_MIN * step:
                    self._last_set = (t_set, None, target, 0)        # buds took our level
                else:
                    d = vol - before
                    self._last_set = (t_set, vol, target, max(retries - 1, 0))
                    if retries > 0:
                        self._reapply = target                       # push ours again
                        self._wake.set()
                    if abs(d) < CLICK_MIN * step:
                        trace.debug("     stale echo of %.1f ignored, re-applying %.1f", vol * 100, target * 100)
                        return
                    trace.debug("     click before buds took our set: measured from %.1f", before * 100)

            self._baseline[dev_id] = vol
            if abs(d) < CLICK_MIN * step:
                self._from_dial[dev_id] = True
                return                                   # echo of our own level, or a keyboard nudge

            # floor(+0.3) instead of round: a single click from an off-grid level (e.g. 1.67
            # steps after a recenter) stays 1, a real folded double (2.1 steps) stays 2.
            # Capped so no glitch can ever become a burst.
            clicks = min(MAX_CLICKS, max(1, int(abs(d) / step + 0.3)))
            delta = clicks if d > 0 else -clicks
            # learn the real step from clean single clicks between two dial reports
            if self._from_dial.get(dev_id) and clicks == 1 and 0.03 < abs(d) < 0.15:
                self._step = 0.5 * step + 0.5 * abs(d)
            self._from_dial[dev_id] = True

            self._last_move = self._last_dial = now
            if not self._passthrough:
                k = round(vol / self._step)
                if k <= EDGE_STEPS or k >= round(1 / self._step) - EDGE_STEPS:
                    self._last_move = 0.0                # at an end: recenter now
                self._need_recenter = True
        trace.debug("     delta=%+d (step %.2f%%)", delta, self._step * 100)
        if self._emit:
            self._emit(InputEvent(Kind.ROTATE, delta, self.name))
        self._wake.set()

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

    def _set_level(self, level, why, force=False):
        """Set the level on every bound device, remembering what it was for the stale filter."""
        before = self._any_level()
        if not force and before is not None and abs(before - level) < 1e-3:
            return
        trace.debug("set  vol=%5.1f (%s)", level * 100, why)
        with self._lock:
            if not force:   # a re-apply keeps the original "before" and retry budget
                self._last_set = (time.monotonic(), before, level, 2)
        for dev, _ in list(self._bound.values()):
            try:
                dev.EndpointVolume.SetMasterVolumeLevelScalar(level, ctypes.byref(OUR_CONTEXT))
            except Exception:
                log.exception("set level failed")

    def _recenter(self):
        with self._lock:
            home, self._need_recenter = self._home, False
            if self._passthrough or home is None:
                return
        self._set_level(home, "recenter")

    def _worker(self):
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        self._dev_cb = _DevCb(self)
        AudioUtilities.GetDeviceEnumerator().RegisterEndpointNotificationCallback(self._dev_cb)
        while True:
            with self._lock:
                target, self._apply = self._apply, None
                again, self._reapply = self._reapply, None
            if target is not None:
                self._set_level(target, "duck/restore")
            if again is not None:
                self._set_level(again, "re-apply after stale echo", force=True)
            if self._stop.is_set():
                break
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
        self._stopped.set()
