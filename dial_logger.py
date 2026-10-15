"""Log everything the CMF Buds Pro 2 dial sends to this PC.

Watches two channels:
  1. Key events (media / volume keys arrive as virtual keys via Bluetooth AVRCP -> HID)
  2. System volume changes (absolute volume sync changes volume without any key event)

Run, then turn / press / hold the dial. Ctrl+C to stop. Log also saved to dial_log.txt.
"""
import ctypes
import ctypes.wintypes as wt
import threading
import time
from datetime import datetime
from pathlib import Path

from pycaw.pycaw import AudioUtilities

LOG = Path(__file__).with_name("dial_log.txt")

VK_NAMES = {
    0xAD: "VOLUME_MUTE", 0xAE: "VOLUME_DOWN", 0xAF: "VOLUME_UP",
    0xB0: "MEDIA_NEXT", 0xB1: "MEDIA_PREV", 0xB2: "MEDIA_STOP", 0xB3: "MEDIA_PLAY_PAUSE",
    0xFA: "PLAY", 0xFB: "ZOOM",
}
WM_NAMES = {0x100: "down", 0x101: "up", 0x104: "sysdown", 0x105: "sysup"}


def log(msg):
    line = f"{datetime.now():%H:%M:%S.%f}"[:-3] + "  " + msg
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------- channel 1: low-level keyboard hook ----------
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


user32 = ctypes.WinDLL("user32", use_last_error=True)
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t


@HOOKPROC
def hook(n, wparam, lparam):
    if n == 0:
        k = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        name = VK_NAMES.get(k.vkCode)
        if name:  # only log media/volume keys, ignore normal typing
            log(f"KEY  {name:<17} {WM_NAMES.get(wparam, wparam)}  scan={k.scanCode} flags={k.flags:#x}")
    return user32.CallNextHookEx(None, n, wparam, lparam)


# ---------- channel 2: system volume polling ----------
def watch_volume():
    import comtypes
    comtypes.CoInitialize()
    last = None
    while True:
        try:
            ep = AudioUtilities.GetSpeakers().EndpointVolume
            dev = AudioUtilities.GetSpeakers().FriendlyName
            cur = (round(ep.GetMasterVolumeLevelScalar() * 100), bool(ep.GetMute()), dev)
        except Exception as e:
            cur = ("err", str(e))
        if cur != last:
            if last is not None:
                log(f"VOL  {cur}")
            last = cur
        time.sleep(0.03)


# ---------- channel 3: be the active media app, catch play/pause/next/prev ----------
def make_silence(path):
    import wave
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000 * 5)


def start_media_session():
    from winrt.windows.foundation import Uri
    from winrt.windows.media import (MediaPlaybackStatus,
                                     SystemMediaTransportControlsButton as B)
    from winrt.windows.media.core import MediaSource
    from winrt.windows.media.playback import MediaPlayer

    silence = Path(__file__).with_name("silence.wav")
    if not silence.exists():
        make_silence(silence)

    player = MediaPlayer()
    player.command_manager.is_enabled = False  # we handle buttons ourselves
    smtc = player.system_media_transport_controls
    for attr in ("is_enabled", "is_play_enabled", "is_pause_enabled",
                 "is_next_enabled", "is_previous_enabled", "is_stop_enabled"):
        setattr(smtc, attr, True)
    smtc.playback_status = MediaPlaybackStatus.PLAYING
    from winrt.windows.media import MediaPlaybackType
    du = smtc.display_updater
    du.type = MediaPlaybackType.MUSIC
    du.music_properties.title = "CMF Dial"
    du.update()

    names = {v: k for k, v in vars(B).items() if not k.startswith("_") and isinstance(v, int)}

    def on_button(sender, args):
        log(f"SMTC {names.get(args.button, args.button)}")

    smtc.add_button_pressed(on_button)
    player.source = MediaSource.create_from_uri(Uri(silence.resolve().as_uri()))
    player.is_looping_enabled = True
    player.play()
    log("SMTC media session active (silent loop)")
    return player, smtc  # keep references alive


# ---------- channel 4: audio device events (hold = voice assistant may open HFP mic link) ----------
def start_device_watch():
    import warnings
    from pycaw.callbacks import MMNotificationClient
    warnings.filterwarnings("ignore")
    names = {d.id: d.FriendlyName for d in AudioUtilities.GetAllDevices()}

    def nm(dev_id):
        return names.get(dev_id, dev_id)

    class Client(MMNotificationClient):
        def on_device_state_changed(self, dev_id, new_state, new_state_id):
            log(f"DEV  state {nm(dev_id)} -> {new_state}")

        def on_default_device_changed(self, flow, flow_id, role, role_id, dev_id):
            log(f"DEV  default {flow}/{role} -> {nm(dev_id)}")

        def on_device_added(self, dev_id):
            log(f"DEV  added {nm(dev_id)}")

        def on_device_removed(self, dev_id):
            log(f"DEV  removed {nm(dev_id)}")

        def on_property_value_changed(self, dev_id, key, fmtid, pid):
            log(f"DEV  prop {nm(dev_id)} {fmtid} pid={pid}")

    client = Client()
    AudioUtilities.GetDeviceEnumerator().RegisterEndpointNotificationCallback(client)
    log("device watch active")
    return client


# ---------- channel 5: new processes (hold might make Windows launch an assistant) ----------
def watch_processes():
    import psutil
    seen = set(psutil.pids())
    while True:
        now = set(psutil.pids())
        for pid in now - seen:
            try:
                log(f"PROC started {psutil.Process(pid).name()} pid={pid}")
            except psutil.Error:
                pass
        seen = now
        time.sleep(0.2)


if __name__ == "__main__":
    log("---- logger start ----")
    _media = start_media_session()
    _devs = start_device_watch()
    threading.Thread(target=watch_processes, daemon=True).start()
    threading.Thread(target=watch_volume, daemon=True).start()
    h = user32.SetWindowsHookExW(13, hook, None, 0)  # WH_KEYBOARD_LL
    if not h:
        raise ctypes.WinError(ctypes.get_last_error())
    msg = wt.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except KeyboardInterrupt:
        pass
