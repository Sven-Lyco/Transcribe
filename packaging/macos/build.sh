#!/bin/bash
# Baut Transcribe.app und ein DMG für Macs mit Apple Silicon (macOS 14+).
#
# Aufruf (aus beliebigem Ordner): packaging/macos/build.sh
# Ergebnis: dist/Transcribe.app und dist/Transcribe-<Version>-arm64.dmg
set -euo pipefail

cd "$(dirname "$0")/../.."
PKG=packaging/macos
BUILD=build
DIST=dist
VENV=$BUILD/venv

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
    echo "Die App lässt sich nur auf einem Mac mit Apple Silicon bauen."
    exit 1
fi

VERSION=$(sed -n 's/^VERSION = "\(.*\)".*/\1/p' transcribe.py)
echo "==> Transcribe $VERSION"

# Python 3.12 oder neuer (PYTHON=... überschreibt die Auswahl)
PYTHON=${PYTHON:-}
if [ -z "$PYTHON" ]; then
    for candidate in python3.14 python3.13 python3.12 python3; do
        if command -v "$candidate" &>/dev/null \
            && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 12))' &>/dev/null; then
            PYTHON=$candidate
            break
        fi
    done
fi
if [ -z "$PYTHON" ]; then
    echo "Python 3.12 oder neuer nicht gefunden."
    exit 1
fi

echo "==> Abhängigkeiten ($("$PYTHON" --version))"
[ -x "$VENV/bin/python" ] || "$PYTHON" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --disable-pip-version-check -r $PKG/requirements.txt
"$VENV/bin/pip" install --quiet --disable-pip-version-check --no-deps -r $PKG/requirements-nodeps.txt

echo "==> FFmpeg (nur Audio, LGPL)"
$PKG/build_ffmpeg.sh "$BUILD/ffmpeg" > "$BUILD/ffmpeg-build.log" 2>&1 \
    || { tail -30 "$BUILD/ffmpeg-build.log"; exit 1; }

echo "==> Icon"
"$VENV/bin/python" $PKG/make_icon.py "$BUILD/icon.icns"

echo "==> App"
rm -rf "$DIST/Transcribe" "$DIST/Transcribe.app"
"$VENV/bin/pyinstaller" --noconfirm --clean --log-level WARN \
    --distpath "$DIST" --workpath "$BUILD/pyinstaller" $PKG/Transcribe.spec
rm -rf "$DIST/Transcribe"  # Zwischenstand von COLLECT, die App liegt in Transcribe.app

# Ohne Apple-Developer-Account nur ad-hoc signiert (auf Apple Silicon Pflicht).
# Beim ersten Öffnen muss die App deshalb einmal unter Datenschutz & Sicherheit erlaubt werden.
codesign --force --deep --sign - "$DIST/Transcribe.app"

echo "==> DMG"
DMG="$DIST/Transcribe-$VERSION-arm64.dmg"
STAGE="$BUILD/dmg"
rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R "$DIST/Transcribe.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname "Transcribe $VERSION" -srcfolder "$STAGE" -format ULFO -ov "$DMG"

echo "==> Fertig"
du -sh "$DIST/Transcribe.app" "$DMG"
