"""App wiring: config -> platform sources/output -> engine <-> Qt UI.

Threading: sources fire from their own threads; the Bus hops every event onto
the Qt main thread, so the engine and UI never need locks.
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from orbit.core import config as config_mod
from orbit.core import settings as user_settings
from orbit.core.engine import Engine
from orbit.core.events import Capability, InputEvent
from orbit.platform import get_platform
from orbit.ui.qtui import QtUI

log = logging.getLogger("orbit")


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else None
    d = Path(base) / "Orbit" if base else Path.home() / ".orbit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_logging(debug: bool):
    fmt = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname).1s %(name)s: %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fh = logging.handlers.RotatingFileHandler(data_dir() / "orbit.log", maxBytes=1_000_000, backupCount=2,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    for noisy in ("comtypes", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if sys.stdout:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)


class Bus(QObject):
    event = Signal(object)

    def post(self, ev: InputEvent):  # any thread
        self.event.emit(ev)


ICONS = Path(__file__).resolve().parent / "ui" / "icons"


def app_icon() -> QIcon:
    """The Orbit mark (rendered by tools/make_icon.py)."""
    return QIcon(str(ICONS / "orbit.png"))


def tray_icon(accent: str) -> QIcon:
    """macOS: a template the menu bar tints for light / dark. Elsewhere: the app icon."""
    if sys.platform == "darwin" and (ICONS / "orbit_tray.png").exists():
        icon = QIcon(str(ICONS / "orbit_tray.png"))
        icon.setIsMask(True)
        return icon
    if (ICONS / "orbit.png").exists():
        return app_icon()
    pm = QPixmap(64, 64)                     # fallback: the old drawn ring
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#15171c"))
    p.drawEllipse(2, 2, 60, 60)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(accent), 6, Qt.SolidLine, Qt.RoundCap))
    p.drawArc(12, 12, 40, 40, 60 * 16, 300 * 16)
    p.end()
    return QIcon(pm)


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="orbit", description="Dial + wheel menu for CMF Buds Pro 2")
    ap.add_argument("--config", help="path to config.toml")
    ap.add_argument("--no-elevate", action="store_true", help="don't ask for admin (press-and-hold stays off)")
    ap.add_argument("--dev", action="store_true", help="accept injected events on udp 127.0.0.1:47800")
    ap.add_argument("--debug", action="store_true")
    return ap.parse_args(argv)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    setup_logging(args.debug)

    plat = get_platform()
    if not plat.is_elevated() and not args.no_elevate:
        log.info("asking for admin (needed to read press-and-hold)")
        if plat.relaunch_elevated(["-m", "orbit", *argv]):
            return 0
        log.warning("elevation declined — continuing without press-and-hold")

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Orbit")
    app.setWindowIcon(app_icon())

    lock = QLockFile(str(data_dir() / "orbit.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        log.error("Orbit is already running")
        return 1

    cfg, cfg_path = config_mod.load(args.config, user_settings=user_settings.load())
    log.info("config: %s (+ %s)", cfg_path, user_settings.path())

    sources = plat.create_sources(cfg)
    if args.dev:
        from orbit.platform.dev import UdpDevSource
        sources.append(UdpDevSource())
    out = plat.create_output(cfg)
    ui = QtUI(cfg)

    # Start sources first so the engine sees what actually works (e.g. falls back to
    # triple-press for the wheel when the hold sniffer can't start).
    bus = Bus()

    def post(ev: InputEvent):
        bus.post(ev)
        for src in sources:
            src.observe(ev)

    for s in sources:
        try:
            s.start(post)
            log.info("source up: %s%s", s.describe(), "" if s.available else " (unavailable)")
        except Exception:
            log.exception("source failed: %s", s.name)
    # The engine is rebuilt in place when settings change; everything holds `live`.
    live = {"engine": Engine(cfg, out, ui, sources)}
    engine = live["engine"]
    bus.event.connect(lambda ev: live["engine"].handle(ev), Qt.QueuedConnection)

    services = plat.create_services(cfg)
    for svc in services:
        try:
            svc.start()
        except Exception:
            log.exception("service failed: %s", type(svc).__name__)

    ticker = QTimer()
    ticker.setInterval(50)
    ticker.timeout.connect(lambda: live["engine"].tick())
    ticker.start()

    # ---- tray
    tray = QSystemTrayIcon(tray_icon(cfg["ui"]["accent"]))
    tray.setToolTip("Orbit — hold the dial to open the wheel")
    menu = QMenu()
    a_cfg = QAction("Open config")
    a_cfg.triggered.connect(lambda: out.launch(str(cfg_path)))
    a_log = QAction("Open log")
    a_log.triggered.connect(lambda: out.launch(str(data_dir() / "orbit.log")))
    a_wheel = QAction("Show wheel")
    a_wheel.triggered.connect(lambda: live["engine"].open_wheel())
    a_settings = QAction("Settings…")

    def apply_settings(new: dict):
        try:
            cfg2, _ = config_mod.load(args.config, user_settings=new)
        except Exception:
            log.exception("settings rejected; keeping the current ones")
            return
        old = live["engine"]
        if old.state.value == "wheel":
            ui.wheel_cancel()
        old.shutdown()
        ui.bridge.set_appearance(cfg2["ui"]["appearance"])
        live["engine"] = Engine(cfg2, out, ui, sources)
        log.info("settings applied — wheel: %s, start: %s, wheel opens with: %s",
                 live["engine"].wheel_ids, live["engine"].tool.id, sorted(live["engine"].open_with))

    windows = []

    def open_settings():
        from orbit.ui.settings_window import SettingsWindow
        if windows and windows[0].isVisible():
            windows[0].raise_()
            windows[0].activateWindow()
            return
        base, _ = config_mod.load(args.config)
        e = live["engine"]
        has_hold = Capability.HOLD in e.caps or Capability.PRESS_RELEASE in e.caps
        w = SettingsWindow(base, user_settings.load(), has_hold, cfg["ui"]["accent"], apply_settings)
        windows[:] = [w]
        w.show()
        w.raise_()
        w.activateWindow()

    a_settings.triggered.connect(open_settings)
    a_restart = QAction("Restart (reload config)")
    a_quit = QAction("Quit")
    a_quit.triggered.connect(app.quit)

    def restart():
        shutdown()  # release the ETW session + lock before the new instance claims them
        import subprocess
        extra = [] if plat.is_elevated() or "--no-elevate" in argv else ["--no-elevate"]
        subprocess.Popen([sys.executable, "-m", "orbit", *extra, *argv],
                         creationflags=0x08000000 if sys.platform == "win32" else 0)
        app.quit()

    a_restart.triggered.connect(restart)

    # live toggles
    toggles = []
    for svc in services:
        if getattr(svc, "toggle_label", None):
            a = QAction(svc.toggle_label)
            a.setCheckable(True)
            a.setChecked(svc.enabled)
            a.toggled.connect(lambda on, s=svc: setattr(s, "enabled", on))
            toggles.append(a)

    for a in (a_wheel, a_settings, a_cfg, a_log, a_restart):
        menu.addAction(a)
    menu.addSeparator()
    for a in toggles:
        menu.addAction(a)
    menu.addSeparator()
    menu.addAction(a_quit)
    tray.setContextMenu(menu)
    tray.show()

    done = []

    def shutdown():
        if done:
            return
        done.append(True)
        live["engine"].shutdown()
        for s in [*sources, *services]:
            try:
                s.stop()
            except Exception:
                pass
        lock.unlock()

    app.aboutToQuit.connect(shutdown)
    log.info("Orbit running — tool: %s, wheel: %s, caps: %s", engine.tool.id, engine.wheel_ids,
             sorted(c.value for c in engine.caps))
    return app.exec()
