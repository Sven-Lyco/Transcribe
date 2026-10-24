#!/bin/bash
# Baut ein minimales FFmpeg (ffmpeg + ffprobe) für die Mac-App: Audio dekodieren für Whisper und
# eine kleine M4A-Abspielkopie für den Player im Verlauf erzeugen.
#
# Ohne externe Bibliotheken und ohne GPL-Teile, also rein LGPL. Die FFmpeg-Builds aus PyAV oder
# Homebrew enthalten x264/x265 (GPL) und wären für die Weitergabe in der App ungeeignet.
#
# Aufruf: packaging/macos/build_ffmpeg.sh <Zielordner>   ->   <Zielordner>/bin/ffmpeg, ffprobe
set -euo pipefail

FFMPEG_VERSION="8.1.3"
# Prüfsumme des Tarballs, dessen GPG-Signatur (FFmpeg release signing key
# FCF9 86EA 15E6 E293 A564 4F10 B432 2F04 D676 58D8) geprüft wurde
FFMPEG_SHA256="7138d28c96d9d3e3af4ee3d8cad72741f8ffb40da90c1112235dea3ecd3178a3"

# Nur, was gebraucht wird: gängige Audioformate lesen, als 16-kHz-PCM für Whisper ausgeben
# und als AAC/M4A zum Abspielen speichern
CONFIGURE_OPTIONS=(
    --extra-cflags="-mmacosx-version-min=14.0"
    --extra-ldflags="-mmacosx-version-min=14.0"
    --disable-everything
    --disable-autodetect
    --disable-doc
    --disable-debug
    --disable-network
    --disable-ffplay
    --disable-avdevice
    --disable-swscale
    --enable-protocol=file,pipe
    --enable-demuxer=ogg,mov,matroska,mp3,wav,flac,aac,aiff,caf
    --enable-parser=opus,vorbis,aac,mpegaudio,flac
    --enable-decoder=opus,vorbis,aac,mp3,mp3float,flac,alac,pcm_s16le,pcm_s16be,pcm_s24le,pcm_s32le,pcm_f32le,pcm_u8
    --enable-encoder=pcm_s16le,aac
    --enable-muxer=pcm_s16le,wav,ipod
    --enable-filter=aresample,aformat,anull,atrim
)

PREFIX="$(mkdir -p "$1" && cd "$1" && pwd)"
# Neu bauen, sobald sich Version oder Optionen ändern oder der Lizenztext fehlt (ältere Builds)
BUILD_ID="$(echo "$FFMPEG_VERSION ${CONFIGURE_OPTIONS[*]}" | shasum -a 256 | cut -c1-16)"
if [ -x "$PREFIX/bin/ffmpeg" ] && [ -f "$PREFIX/COPYING.LGPLv2.1" ] \
    && [ "$(cat "$PREFIX/.build-config" 2>/dev/null)" = "$BUILD_ID" ]; then
    echo "FFmpeg $FFMPEG_VERSION schon gebaut: $PREFIX/bin"
    exit 0
fi

SRC_DIR="$(dirname "$PREFIX")/ffmpeg-src"
TARBALL="$SRC_DIR/ffmpeg-$FFMPEG_VERSION.tar.xz"
mkdir -p "$SRC_DIR"
if [ ! -f "$TARBALL" ]; then
    curl -sSfL -o "$TARBALL" "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz"
fi
echo "$FFMPEG_SHA256  $TARBALL" | shasum -a 256 -c -

rm -rf "$SRC_DIR/ffmpeg-$FFMPEG_VERSION"
tar -xf "$TARBALL" -C "$SRC_DIR"
cd "$SRC_DIR/ffmpeg-$FFMPEG_VERSION"

./configure --prefix="$PREFIX" "${CONFIGURE_OPTIONS[@]}"
make -j"$(sysctl -n hw.ncpu)"
make install
# Die LGPL verlangt den Lizenztext neben dem Programm (collect_licenses.py übernimmt ihn in die App)
cp COPYING.LGPLv2.1 LICENSE.md "$PREFIX/"
echo "$BUILD_ID" > "$PREFIX/.build-config"

"$PREFIX/bin/ffmpeg" -hide_banner -version | head -1
