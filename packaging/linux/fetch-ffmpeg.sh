#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# fetch-ffmpeg.sh — Download, verify, strip and install static FFmpeg for Linux
#
# Usage:
#   [FFMPEG_TAG=...] [FFMPEG_REPO=...] [FFMPEG_VARIANT=...] ./packaging/linux/fetch-ffmpeg.sh [TARGET_PATH]
#
# Default:
#   Repository: BtbN/FFmpeg-Builds (provides both LGPL and GPL static builds)
#   Tag: autobuild-2026-10-22-13-06 (pinned, dated snapshot)
#   Variant: lgpl (or gpl)
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

TARGET="${1:-$REPO_ROOT/packaging/linux/ffmpeg}"
FFMPEG_REPO="${FFMPEG_REPO:-BtbN/FFmpeg-Builds}"
FFMPEG_TAG="${FFMPEG_TAG:-autobuild-2026-10-22-13-06}"
FFMPEG_VARIANT="${FFMPEG_VARIANT:-lgpl}"

# Idempotency check: if valid executable already exists, exit cleanly
if [[ -f "$TARGET" && -x "$TARGET" ]]; then
    echo "[fetch-ffmpeg] FFmpeg executable already exists at $TARGET. Skipping download."
    exit 0
fi

if [[ "$FFMPEG_TAG" == "latest" ]]; then
    echo "ERROR: FFMPEG_TAG must be a pinned release tag (not 'latest')." >&2
    exit 1
fi

echo "[fetch-ffmpeg] Downloading static FFmpeg ($FFMPEG_VARIANT) from $FFMPEG_REPO tag $FFMPEG_TAG..."

TMP_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

# Download checksums.sha256
CHECKSUMS_URL="https://github.com/${FFMPEG_REPO}/releases/download/${FFMPEG_TAG}/checksums.sha256"
echo "[fetch-ffmpeg] Fetching checksums from $CHECKSUMS_URL..."
if command -v curl &>/dev/null; then
    curl -fsSL "$CHECKSUMS_URL" -o "$TMP_DIR/checksums.sha256"
elif command -v wget &>/dev/null; then
    wget -q -O "$TMP_DIR/checksums.sha256" "$CHECKSUMS_URL"
else
    echo "ERROR: Neither curl nor wget found in PATH." >&2
    exit 1
fi

# Locate the static linux64 asset in checksums.sha256
MATCH_LINE="$(grep -E "linux64-${FFMPEG_VARIANT}(\-[0-9.]+)?\.tar\.xz$" "$TMP_DIR/checksums.sha256" | grep -v "shared" | head -1 || true)"

if [[ -z "$MATCH_LINE" ]]; then
    echo "WARNING: Asset matching linux64-${FFMPEG_VARIANT} not found in checksums.sha256. Falling back to gpl..." >&2
    MATCH_LINE="$(grep -E "linux64-gpl(\-[0-9.]+)?\.tar\.xz$" "$TMP_DIR/checksums.sha256" | grep -v "shared" | head -1 || true)"
fi

if [[ -z "$MATCH_LINE" ]]; then
    echo "ERROR: Could not locate a static linux64 FFmpeg asset in $CHECKSUMS_URL." >&2
    cat "$TMP_DIR/checksums.sha256" >&2
    exit 1
fi

EXPECTED_SHA="$(echo "$MATCH_LINE" | awk '{print $1}' | tr -d '\r')"
ASSET_NAME="$(echo "$MATCH_LINE" | awk '{print $2}' | tr -d '\r')"

echo "[fetch-ffmpeg] Selected asset: $ASSET_NAME"
echo "[fetch-ffmpeg] Expected SHA256: $EXPECTED_SHA"

# Download the selected asset archive
ASSET_URL="https://github.com/${FFMPEG_REPO}/releases/download/${FFMPEG_TAG}/${ASSET_NAME}"
echo "[fetch-ffmpeg] Downloading asset from $ASSET_URL..."
if command -v curl &>/dev/null; then
    curl -fsSL "$ASSET_URL" -o "$TMP_DIR/$ASSET_NAME"
elif command -v wget &>/dev/null; then
    wget -q -O "$TMP_DIR/$ASSET_NAME" "$ASSET_URL"
fi

# Verify SHA256 checksum
echo "[fetch-ffmpeg] Verifying SHA256 checksum..."
(cd "$TMP_DIR" && echo "${EXPECTED_SHA}  ${ASSET_NAME}" | sha256sum -c -)

# Extract binary
echo "[fetch-ffmpeg] Extracting ffmpeg executable..."
tar -xf "$TMP_DIR/$ASSET_NAME" -C "$TMP_DIR" --wildcards '*/bin/ffmpeg'

EXTRACTED_BIN="$(find "$TMP_DIR" -type f -name ffmpeg | head -1)"
if [[ -z "$EXTRACTED_BIN" || ! -f "$EXTRACTED_BIN" ]]; then
    echo "ERROR: Extracted ffmpeg binary not found inside archive." >&2
    exit 1
fi

# Strip unneeded symbols to minimize binary size
if command -v strip &>/dev/null; then
    echo "[fetch-ffmpeg] Stripping unneeded symbols with strip --strip-unneeded..."
    strip --strip-unneeded "$EXTRACTED_BIN" || true
fi

# Install to target
mkdir -p "$(dirname "$TARGET")"
cp "$EXTRACTED_BIN" "$TARGET"
chmod 755 "$TARGET"

echo "[fetch-ffmpeg] Successfully installed FFmpeg to $TARGET"
if command -v du &>/dev/null; then
    echo "[fetch-ffmpeg] Final binary size: $(du -h "$TARGET" | cut -f1)"
fi
