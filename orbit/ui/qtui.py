"""Qt Quick overlay: implements the engine's UI protocol.

One frameless, transparent, click-through, never-focused window per show,
placed on the screen under the cursor. QML does all drawing and animation.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot, Property
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from orbit.core.tools import Hud
from orbit.ui import assets

log = logging.getLogger("orbit.ui")
QML = Path(__file__).with_name("qml") / "Overlay.qml"


class Bridge(QObject):
    wheelOpened = Signal("QVariantList", int)
    wheelMoved = Signal(int, int)
    wheelCommitted = Signal(int)
    wheelCancelled = Signal()
    hudShown = Signal(str, str, str, float, int)   # glyph, title, detail, progress(-1 none), direction
    placed = Signal(int, int, int, int)

    def __init__(self, cfg: dict):
        super().__init__()
        self._cfg = cfg

    @Property(str, constant=True)
    def accent(self):
        return self._cfg["ui"]["accent"]

    @Property(float, constant=True)
    def uiScale(self):
        return float(self._cfg["ui"]["scale"])

    @Property(int, constant=True)
    def hudMs(self):
        return int(self._cfg["ui"]["hud_ms"])

    @Property(str, constant=True)
    def iconFont(self):
        return assets.ICON_FONT


class QtUI:
    """Engine-facing adapter."""

    def __init__(self, cfg: dict):
        self.bridge = Bridge(cfg)
        self.qml = QQmlApplicationEngine()
        self.qml.rootContext().setContextProperty("orbit", self.bridge)
        self.qml.load(QUrl.fromLocalFile(str(QML)))
        if not self.qml.rootObjects():
            raise RuntimeError("Overlay.qml failed to load")
        self.window = self.qml.rootObjects()[0]
        if sys.platform == "win32":
            self._win_noactivate()

    def _win_noactivate(self):
        import ctypes
        hwnd = int(self.window.winId())
        GWL_EXSTYLE = -20
        u = ctypes.windll.user32
        u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        style = u.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        # NOACTIVATE | TOOLWINDOW | TRANSPARENT | LAYERED | TOPMOST
        u.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | 0x08000000 | 0x80 | 0x20 | 0x80000 | 0x8)

    def _place(self):
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = scr.geometry()
        self.bridge.placed.emit(g.x(), g.y(), g.width(), g.height())

    # ---- UI protocol
    def wheel_open(self, items, index):
        self._place()
        payload = [dict(i, glyph=assets.glyph(i["icon"], i["label"])) for i in items]
        self.bridge.wheelOpened.emit(payload, index)

    def wheel_move(self, index, direction):
        self.bridge.wheelMoved.emit(index, direction)

    def wheel_commit(self, index):
        self.bridge.wheelCommitted.emit(index)

    def wheel_cancel(self):
        self.bridge.wheelCancelled.emit()

    def hud(self, h: Hud):
        self._place()
        self.bridge.hudShown.emit(assets.glyph(h.icon, h.title), h.title, h.detail,
                                  -1.0 if h.progress is None else float(h.progress), h.direction)
