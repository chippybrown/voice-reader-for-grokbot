#!/bin/sh
# Wrap the PyInstaller binary in an AppImage. Run from the repo root
# after dist/grokbot-voice exists.
set -eu
cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
APP="AppDir"
rm -rf "$APP"
mkdir -p "$APP/usr/bin"
cp "$ROOT/dist/grokbot-voice" "$APP/usr/bin/grokbot-voice"
chmod +x "$APP/usr/bin/grokbot-voice"
cp "$ROOT/assets/icon.png" "$APP/grokbot-voice.png"
cat > "$APP/grokbot-voice.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=Grokbot Voice
Comment=Read Grok Bot replies aloud
Exec=grokbot-voice
Icon=grokbot-voice
Categories=Audio;Utility;
Terminal=false
EOF
cat > "$APP/AppRun" << 'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/grokbot-voice" "$@"
EOF
chmod +x "$APP/AppRun"
TOOL="${APPIMAGETOOL:-appimagetool}"
if [ ! -x "$TOOL" ] && [ -x /tmp/appimagetool ]; then
  TOOL=/tmp/appimagetool
fi
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APP" "$ROOT/dist/Grokbot-Voice-x86_64.AppImage"
chmod +x "$ROOT/dist/Grokbot-Voice-x86_64.AppImage"
