#!/bin/sh
# Build the Windows installer and the Linux AppImage from this folder.
set -eu
cd "$(dirname "$0")"
rm -rf extension AppDir
mkdir -p extension
cp ../manifest.json ../popup.html ../popup.js ../popup.css ../README.md extension/
cp -R ../src ../icons extension/
# The installer writes installed.html itself. Leave tests and node_modules out.
rm -rf extension/src/*.test.js

GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -o ../dist/Grok-Voice-Reader-Setup.exe .
CGO_ENABLED=0 go build -o /tmp/grok-voice-reader-install .

mkdir -p AppDir
cp /tmp/grok-voice-reader-install AppDir/AppRun
chmod +x AppDir/AppRun
cp ../icons/icon128.png AppDir/grok-voice-reader.png
cat > AppDir/grok-voice-reader.desktop << 'EOF'
[Desktop Entry]
Name=Grok Voice Reader
Exec=AppRun
Icon=grok-voice-reader
Type=Application
Categories=Utility;
EOF

if [ ! -x /tmp/appimagetool ]; then
  curl -fsSL -o /tmp/appimagetool "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x /tmp/appimagetool
fi
mkdir -p ../dist
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 /tmp/appimagetool AppDir ../dist/Grok-Voice-Reader-x86_64.AppImage
echo "Built ../dist/Grok-Voice-Reader-Setup.exe and ../dist/Grok-Voice-Reader-x86_64.AppImage"
