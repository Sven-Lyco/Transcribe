#!/bin/bash
# Baut ein minimales FFmpeg (ffmpeg + ffprobe) nur zum Dekodieren von Audio für die Mac-App.
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

PREFIX="$(mkdir -p "$1" && cd "$1" && pwd)"
if [ -x "$PREFIX/bin/ffmpeg" ] && "$PREFIX/bin/ffmpeg" -version | grep -q "ffmpeg version $FFMPEG_VERSION "; then
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

# Nur, was Whisper braucht: gängige Audioformate lesen und als 16-kHz-PCM ausgeben
./configure \
    --prefix="$PREFIX" \
    --extra-cflags="-mmacosx-version-min=14.0" \
    --extra-ldflags="-mmacosx-version-min=14.0" \
    --disable-everything \
    --disable-autodetect \
    --disable-doc \
    --disable-debug \
    --disable-network \
    --disable-ffplay \
    --disable-avdevice \
    --disable-swscale \
    --enable-protocol=file,pipe \
    --enable-demuxer=ogg,mov,matroska,mp3,wav,flac,aac,aiff,caf \
    --enable-parser=opus,vorbis,aac,mpegaudio,flac \
    --enable-decoder=opus,vorbis,aac,mp3,mp3float,flac,alac,pcm_s16le,pcm_s16be,pcm_s24le,pcm_s32le,pcm_f32le,pcm_u8 \
    --enable-encoder=pcm_s16le \
    --enable-muxer=pcm_s16le,wav \
    --enable-filter=aresample,aformat,anull,atrim

make -j"$(sysctl -n hw.ncpu)"
make install

"$PREFIX/bin/ffmpeg" -hide_banner -version | head -1
