#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Download static ffmpeg if missing on Linux for self-contained audio playback
LINUX_FFMPEG="$PROJECT_ROOT/packaging/linux/ffmpeg"
if [[ ! -f "$LINUX_FFMPEG" ]]; then
    echo "Downloading static ffmpeg for self-contained Linux build..."
    mkdir -p "$PROJECT_ROOT/packaging/linux"
    FFMPEG_URL="https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
    TMP_FFMPEG_DIR="$(mktemp -d)"
    if command -v curl &>/dev/null; then
        curl -fsSL "$FFMPEG_URL" -o "$TMP_FFMPEG_DIR/ffmpeg.tar.xz" || true
    elif command -v wget &>/dev/null; then
        wget -q -O "$TMP_FFMPEG_DIR/ffmpeg.tar.xz" "$FFMPEG_URL" || true
    fi
    if [[ -f "$TMP_FFMPEG_DIR/ffmpeg.tar.xz" ]]; then
        tar -xf "$TMP_FFMPEG_DIR/ffmpeg.tar.xz" -C "$TMP_FFMPEG_DIR" --wildcards '*/bin/ffmpeg' || true
        find "$TMP_FFMPEG_DIR" -name ffmpeg -type f -exec cp {} "$LINUX_FFMPEG" \;
        chmod +x "$LINUX_FFMPEG" || true
        echo "ffmpeg installed to $LINUX_FFMPEG"
    fi
    rm -rf "$TMP_FFMPEG_DIR"
fi

echo "Installing dependencies via Poetry..."
poetry install --with dev

echo "Running: poetry run python -m PyInstaller --noconfirm --clean kikumoe.spec"
cd "$PROJECT_ROOT"
poetry run python -m PyInstaller --noconfirm --clean kikumoe.spec

if [[ -f "$LINUX_FFMPEG" ]]; then
    cp "$LINUX_FFMPEG" "$PROJECT_ROOT/dist/ffmpeg"
    chmod +x "$PROJECT_ROOT/dist/ffmpeg" || true
fi

VERSION="$(grep -oP '(?<=version:\s).+' "$PROJECT_ROOT/version.yml" | tr -d '[:space:]' || echo '2.0.0-beta2')"
echo "Done. Output:"
echo "  dist/KikuMoe-${VERSION}"
