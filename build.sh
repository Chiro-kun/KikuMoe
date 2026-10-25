#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Fetch static ffmpeg if missing on Linux for self-contained audio playback
LINUX_FFMPEG="$PROJECT_ROOT/packaging/linux/ffmpeg"
if [[ ! -x "$LINUX_FFMPEG" ]]; then
    bash "$PROJECT_ROOT/packaging/linux/fetch-ffmpeg.sh" "$LINUX_FFMPEG"
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
