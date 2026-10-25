#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build-minimal-ffmpeg.sh — Compile a minimal, audio-only static FFmpeg binary
#
# Supported streams: Vorbis (Ogg), Opus (Ogg), MP3, AAC, FLAC over HTTP/HTTPS.
# Output formats: PCM s16le raw audio.
# Target footprint: ~5-7 MB (compared to 140 MB full static build).
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

TARGET="${1:-$REPO_ROOT/packaging/linux/ffmpeg}"
FFMPEG_VERSION="7.1"
FFMPEG_SRC_URL="https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz"
FFMPEG_SRC_SHA256="40973d44970dbc83ef302b0609f2e74982be2d85916dd2ee7472d30678a7abe6"

# Idempotency check: if valid executable already exists, skip unless FORCE_BUILD=1
if [[ -f "$TARGET" && -x "$TARGET" && "${FORCE_BUILD:-0}" != "1" ]]; then
    echo "[build-minimal-ffmpeg] Executable already exists at $TARGET. Skipping build."
    exit 0
fi

echo "[build-minimal-ffmpeg] Building minimal audio-only FFmpeg v${FFMPEG_VERSION}..."

TMP_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

# Download and verify source tarball
echo "[build-minimal-ffmpeg] Downloading FFmpeg source from $FFMPEG_SRC_URL..."
if command -v curl &>/dev/null; then
    curl -fsSL "$FFMPEG_SRC_URL" -o "$TMP_DIR/ffmpeg.tar.xz"
elif command -v wget &>/dev/null; then
    wget -q -O "$TMP_DIR/ffmpeg.tar.xz" "$FFMPEG_SRC_URL"
else
    echo "ERROR: Neither curl nor wget found in PATH." >&2
    exit 1
fi

echo "[build-minimal-ffmpeg] Verifying source SHA256 checksum..."
echo "${FFMPEG_SRC_SHA256}  ${TMP_DIR}/ffmpeg.tar.xz" | sha256sum -c -

echo "[build-minimal-ffmpeg] Extracting source..."
tar -xf "$TMP_DIR/ffmpeg.tar.xz" -C "$TMP_DIR"
SRC_DIR="$TMP_DIR/ffmpeg-${FFMPEG_VERSION}"

cd "$SRC_DIR"

echo "[build-minimal-ffmpeg] Configuring minimal audio-only features..."
./configure \
    --prefix="$TMP_DIR/dist" \
    --disable-everything \
    --disable-doc \
    --disable-debug \
    --disable-shared \
    --enable-static \
    --enable-small \
    --enable-pthreads \
    --enable-network \
    --disable-x86asm \
    --disable-ffplay \
    --disable-ffprobe \
    --disable-avdevice \
    --disable-swscale \
    --disable-postproc \
    --enable-protocol=file,http,https,tcp,tls \
    --enable-demuxer=ogg,mp3,aac,flac \
    --enable-decoder=vorbis,opus,mp3,mp3float,aac,flac \
    --enable-parser=vorbis,opus,mpegaudio,aac,flac \
    --enable-encoder=pcm_s16le \
    --enable-muxer=s16le,null \
    --enable-filter=aresample,aformat \
    --enable-openssl \
    --pkg-config-flags="--static" \
    --extra-cflags="-O3"

echo "[build-minimal-ffmpeg] Compiling ffmpeg executable..."
NPROC="$(nproc 2>/dev/null || echo 2)"
make -j"$NPROC" ffmpeg

if command -v strip &>/dev/null; then
    echo "[build-minimal-ffmpeg] Stripping binary symbols..."
    strip --strip-unneeded ffmpeg
fi

# Install to target
mkdir -p "$(dirname "$TARGET")"
cp ffmpeg "$TARGET"
chmod 755 "$TARGET"

echo "[build-minimal-ffmpeg] Successfully built minimal FFmpeg at $TARGET"
if command -v du &>/dev/null; then
    echo "[build-minimal-ffmpeg] Binary size: $(du -h "$TARGET" | cut -f1)"
fi

# Quick validation
echo "[build-minimal-ffmpeg] Verifying binary execution..."
"$TARGET" -version | head -2

