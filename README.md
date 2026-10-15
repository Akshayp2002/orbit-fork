# Orbit — a dial + wheel menu for CMF Buds Pro 2

The case dial on the CMF Buds Pro 2 becomes a Surface-Dial-style controller:
**double-press** to open a wheel, **turn** to pick a tool, **press** to use it. After
that, turning and pressing drive the chosen tool (volume, scroll, zoom,
window switcher, undo, desktops, tabs...). Everything is set in `config.toml`.

## Run

```
pip install -r requirements.txt
python -m orbit              # asks for admin (only needed for press-and-hold)
python -m orbit --no-elevate # no admin: everything works, hold just isn't read
python -m orbit --dev        # also accept test events: python -m orbit.inject hold
```

A tray icon gives: Show wheel, Open config, Open log, Restart, Quit.
Log: `%LOCALAPPDATA%\Orbit\orbit.log`.

## How to use the dial

| Gesture | Tool active (default) | Wheel open |
|---|---|---|
| Turn | drives the tool (Volume: volume; Scroll: scrolls...) | moves the highlight, one item per click, wraps |
| Press | tool's click, else play/pause | **select** |
| Double press | **open wheel** | close, no change |
| Triple press | back to the previous tool (Volume: next track) | close, no change |
| Hold (admin) | opens Claude Quick Entry (`ctrl+alt+v`, set the same key in Claude's settings), centres it on your screen, starts Windows voice typing into it | close, no change |
| Wait 5 s | — | keeps the highlighted tool (one-shot actions never fire on timeout) |

An on-screen tag shows the active tool and its value whenever you use the dial,
then fades out. While the wheel is open your audio drops to half, so each click's
volume blip stays soft; it comes back when you select or cancel. (The tone you hear
per click is the buds' own firmware, not Orbit.)

## How the dial reaches the PC (reverse-engineered)

| Gesture | Arrives as | Read by |
|---|---|---|
| Turn | Bluetooth AVRCP absolute volume, 1/16 per click | `IAudioEndpointVolumeCallback` on the buds' output |
| Press / double / triple | AVRCP play-pause / next / previous | our own media session (SMTC) |
| Hold | HFP `AT+BVRA=1` (start voice recognition) | raw Bluetooth packets via ETW (admin) |

Turning is "borrowed" from volume. When the active tool isn't Volume, Orbit puts
the volume back 0.35 s after you stop turning, so your listening level doesn't drift.

## Code map

```
orbit/
  core/            no OS or UI code — portable
    events.py      InputEvent + capabilities (rotate, clicks, hold, press/release)
    engine.py      the state machine (tool mode / wheel mode)
    tools.py       tool types: volume, keys, window_switcher, action
    actions.py     "keys:ctrl+z" style action strings
    config.py      TOML load + validation
  platform/
    base.py        InputSource / RotationSource / Output contracts
    windows/       input_volume, input_media, input_bt (+ etw), output
    mac/           plan + stub
    dev.py         UDP test input
  ui/
    qtui.py        engine -> Qt bridge, overlay window setup
    qml/Overlay.qml  wheel + HUD, all animation
tests/             engine tests with fakes (python -m pytest -q)
```

**Add a tool type:** subclass `Tool` in `tools.py`, register it in `TOOL_TYPES`.
**Add an input (e.g. real press/release):** add a `Decoder` in `input_bt.py`, or a
new `InputSource` that emits `Kind.PRESS` / `Kind.RELEASE` and declares
`Capability.PRESS_RELEASE`. The engine then turns on press-and-turn quick-select
on its own (press, turn, release to commit), with no other changes.
**Port to mac:** implement `platform/mac` (plan is in its `__init__.py`).

Design research: [docs/research.md](docs/research.md).
