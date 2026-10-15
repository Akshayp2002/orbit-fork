#!/usr/bin/env bash
# Build dist/Orbit.app: a menu-bar agent (no Dock icon) with a stable bundle id.
#
#   pip install -r requirements.txt pyinstaller && bash packaging/mac/build_app.sh
#
# Signing: macOS ties the Accessibility grant to the signature. An ad-hoc signature
# changes with every build, so the grant is lost on each rebuild. Sign with a stable
# identity to keep it:
#   - ORBIT_SIGN_ID="Developer ID Application: ..." (or any code-signing identity), or
#   - a self-signed code-signing certificate named "Orbit Dev" in the login keychain
#     (Keychain Access > Certificate Assistant > Create a Certificate..., Name: Orbit Dev,
#     Identity Type: Self Signed Root, Certificate Type: Code Signing).
# With neither, the build is ad-hoc signed. For distribution use a Developer ID and
# notarize (docs/research-macos.md section 6).
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
SIGN_ID="${ORBIT_SIGN_ID:-}"
if [ -z "$SIGN_ID" ] && security find-identity -v -p codesigning 2>/dev/null | grep -q '"Orbit Dev"'; then
  SIGN_ID="Orbit Dev"
fi
if [ -n "$SIGN_ID" ]; then
  codesign --force --deep --sign "$SIGN_ID" dist/Orbit.app
  echo "built dist/Orbit.app (signed: $SIGN_ID; the Accessibility grant survives rebuilds)"
else
  codesign --force --deep --sign - dist/Orbit.app
  echo "built dist/Orbit.app (ad-hoc signed: re-grant Accessibility after each rebuild)"
fi
