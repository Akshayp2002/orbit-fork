# Orbit — a dial + wheel menu for CMF Buds Pro 2

The case dial on the CMF Buds Pro 2 becomes a Surface-Dial-style controller on
**Windows, macOS and Android**: **double-press** to open a wheel, **turn** to pick a
tool, **press** to use it. After that, turning and pressing drive the chosen tool
(volume, brightness, scroll, zoom, app/window switcher, undo, tabs, ...).

| | Windows | macOS | Android |
|---|---|---|---|
| Code | `orbit/` (Python) | `orbit/` (Python) | `android/` (Kotlin) |
| Turn | ✅ verified with the buds | built, CI-tested, **needs a Mac + buds** | built, emulator-tested, **needs a phone + buds** |
| Press / double / triple | ✅ verified | built (MPRemoteCommandCenter) | ✅ emulator (same path as the buds) |
| Hold | ✅ (admin) → Claude dictation | not observable on macOS | ✅ emulator (VOICE_COMMAND) → Claude |
| Wheel + HUD | ✅ | built (Qt, same QML) | ✅ emulator |

## Gestures (all platforms)

| Gesture | Tool active | Wheel open |
|---|---|---|
| Turn | drives the tool | moves the highlight, one item per click, wraps |
| Press | tool's click, else play/pause on your music app | **select** |
| Double press | **open wheel** | close, no change |
| Triple press | back to the previous tool (Volume: next track) | close, no change |
| Hold | Windows: Claude Quick Entry + voice typing · Android: open Claude · macOS: — | close, no change |
| Wait 5 s | — | keeps the highlighted tool (one-shot actions never fire on timeout) |

Fast spins go further (scroll, brightness); careful single clicks stay exact; turning
back is always one precise step. While the wheel is open your audio drops to half so
each click's volume blip stays soft. (The tone per click is the buds' firmware.)

## Windows

```
pip install -r requirements.txt
python -m orbit              # asks for admin (only needed for press-and-hold)
python -m orbit --no-elevate # everything except hold
python -m orbit --dev        # also accept test events: python -m orbit.inject double
```
Tray icon: Show wheel, Open config, Open log, Restart, Quit; toggle "Hide Windows volume
bar". Log: `%LOCALAPPDATA%\Orbit\orbit.log`. Brightness drives Twinkle Tray if installed.

## macOS

```
pip install -r requirements.txt       # pulls the PyObjC frameworks on macOS
python -m orbit
```
1. Pair the buds and make them the output device.
2. Grant **Accessibility** when prompted (System Settings → Privacy & Security →
   Accessibility → enable the app you launched Orbit from), then restart Orbit.
   Without it, keys and scrolling are silently dropped.
3. The first time a press is forwarded to Spotify/Music, allow the Automation prompt.

Shortcuts are remapped for macOS in `config.toml` → `[platforms.mac]` (Cmd instead of
Ctrl, Cmd+Tab app switcher, Spaces). Brightness: built-in display via DisplayServices,
external monitors via [`m1ddc`](https://github.com/waydabber/m1ddc) if on PATH.
Known limits: the system volume HUD may flash per click (no public way to hide it);
hold isn't available. First-run checklist: [docs/research-macos.md](docs/research-macos.md#test-checklist-first-session-on-a-mac-with-the-buds).

## Android

Install the APK (CI artifact `orbit-android-debug`, or `cd android && ./gradlew assembleDebug`),
open **Orbit**, and work through the checklist:
1. Notifications · 2. Accessibility (draws the wheel, performs actions — if the switch
is greyed out: App info → ⋮ → Allow restricted settings) · 3. Notification access (so a
press still plays/pauses your music app) · 4. Press-and-hold: tap, pick **Orbit →
Always** · 5. Modify system settings (Brightness tool).

Android tools: Volume, Brightness, Scroll (held virtual finger, no fling), Apps (turn
through recent apps, press or pause to switch), Zoom (magnification), Torch, and
one-shot Screenshot and Claude. Known limits: the system volume panel flashes per click
(the Bluetooth stack requests it); a hold is detected at most about once per 5 s.

## How the dial reaches the host (reverse-engineered)

| Gesture | Over Bluetooth | Windows | macOS | Android |
|---|---|---|---|---|
| Turn | AVRCP absolute volume (1/15–1/16 per click, ≤ ~3/s) | endpoint volume callback | CoreAudio VirtualMainVolume | 40 ms poll of STREAM_MUSIC |
| Press ×1/2/3 | AVRCP play-pause / next / previous | own SMTC session | own now-playing session | own MediaSession |
| Hold | HFP `AT+BVRA=1` (or `=0`, the buds toggle) | raw HCI via ETW (admin) | — | VOICE_COMMAND intent |

Turning is borrowed from volume, so `orbit/core/volume_dial.py` (and its Kotlin port)
learns the click size, treats any change in a direction as at least one click, filters
the buds' stale reports after Orbit resets the level, and restores the level 0.9 s after
you stop turning. Tests replay real traces recorded with the buds.

## Code map

```
orbit/                     desktop app (Python, Qt Quick UI)
  core/                    no OS or UI code: events, engine, tools, actions, config,
                           volume_dial (click detection), motion (spin speed)
  platform/windows/        volume, media session, Bluetooth ETW, flyout hiding, output
  platform/mac/            CoreAudio (ctypes), MPRemoteCommandCenter, Quartz output, overlay
  ui/                      qtui.py bridge, qml/ (two small windows: wheel, HUD), icons/
android/app/src/main/kotlin/app/orbit/dial/
  core/                    Kotlin ports: VolumeDial, SpinTracker, Engine, Tools
  OrbitAccessibilityService, OrbitMediaService, OverlayController/OverlayUi,
  HoldTrampolineActivity, MainActivity (setup)
tests/                     desktop tests (python -m pytest -q)
tools/                     render_overlay.py (offscreen render check), mac_smoke.py,
                           bt_diag.py, svg_to_vector.py
docs/                      research.md (interaction design), research-macos.md, research-android.md
```

CI (`.github/workflows`): Windows + macOS unit tests, offscreen overlay render, macOS API
smoke test; Android unit tests + debug APK.

Icons: [Lucide](https://lucide.dev) (ISC).
