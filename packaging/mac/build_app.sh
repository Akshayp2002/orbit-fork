#!/usr/bin/env bash
# Build dist/Orbit.app: a menu-bar agent (no Dock icon) with a stable bundle id, so
# macOS remembers the Accessibility grant. Ad-hoc signed; for distribution sign with a
# Developer ID and notarize (see docs/research-macos.md section 6).
#
#   pip install -r requirements.txt pyinstaller && bash packaging/mac/build_app.sh
set -euo pipefail
cd "$(dirname "$0")/../.."

python -m PyInstaller --noconfirm --windowed --name Orbit \
  --osx-bundle-identifier app.orbit.dial \
  --add-data "orbit/ui/qml:orbit/ui/qml" \
  --add-data "orbit/ui/icons:orbit/ui/icons" \
  --add-data "config.toml:." \
  --hidden-import orbit.platform.mac \
  --hidden-import orbit.platform.mac.input_volume \
  --hidden-import orbit.platform.mac.input_media \
  --hidden-import orbit.platform.mac.output \
  --hidden-import orbit.platform.mac.overlay \
  --hidden-import orbit.ui.settings_window \
  packaging/orbit_main.py

PLIST=dist/Orbit.app/Contents/Info.plist
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 13.0" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSAppleEventsUsageDescription string 'Orbit forwards play/pause/next from the dial to your music app.'" "$PLIST"
codesign --force --deep --sign - dist/Orbit.app
echo "built dist/Orbit.app"
