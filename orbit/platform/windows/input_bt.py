"""Dial events sniffed from raw Bluetooth packets (ETW, admin only).

Windows logs every HCI packet to the Microsoft-Windows-BTH-BTHPORT provider.
We scan each one with a list of decoders. Today:

    AT+BVRA=1   hands-free "start voice recognition"  -> HOLD

To add press/release later (e.g. once the vendor RFCOMM/GATT channel is mapped,
or AVRCP PASS THROUGH press/release bits), write another Decoder and add it to
DECODERS, and add Capability.PRESS_RELEASE to `capabilities`. Nothing else in
the app has to change.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from orbit.core.events import Capability, InputEvent, Kind
from orbit.platform.base import Emit, InputSource
from orbit.platform.windows import etw

log = logging.getLogger("orbit.bt")

BTHPORT = uuid.UUID("8a1f9517-3a8c-4a9e-a018-4f17a200f277")


@dataclass
class Decoder:
    name: str
    match: Callable[[bytes], bool]
    kind: Kind
    debounce_s: float = 0.8   # one packet can be logged more than once


DECODERS = [
    Decoder("hfp-voice-recognition", lambda d: b"AT+BVRA=1" in d, Kind.HOLD),
]


class BluetoothPacketSource(InputSource):
    name = "bt-etw"
    capabilities = frozenset({Capability.HOLD})

    def __init__(self, decoders: list[Decoder] | None = None):
        self.decoders = decoders or DECODERS
        self._emit: Emit | None = None
        self._last: dict[str, float] = {}
        self._session: etw.EtwSession | None = None

    @property
    def available(self):
        return etw.is_admin()

    def start(self, emit):
        self._emit = emit
        if not self.available:
            log.warning("not admin — press-and-hold detection off")
            return
        self._session = etw.EtwSession("OrbitDialBT", BTHPORT, self._on_payload)
        self._session.start()
        log.info("bluetooth packet sniffer active (%d decoders)", len(self.decoders))

    def stop(self):
        if self._session:
            self._session.stop()

    def _on_payload(self, data: bytes):
        now = time.monotonic()
        for d in self.decoders:
            if d.match(data):
                if now - self._last.get(d.name, 0) < d.debounce_s:
                    continue
                self._last[d.name] = now
                log.debug("decoded %s", d.name)
                if self._emit:
                    self._emit(InputEvent(d.kind, 0, self.name))
