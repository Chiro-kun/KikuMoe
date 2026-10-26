#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Fetch or build static ffmpeg if missing on Linux for self-contained audio playback
LINUX_FFMPEG="$PROJECT_ROOT/packaging/linux/ffmpeg"
if [[ ! -x "$LINUX_FFMPEG" ]]; then
    if [[ "${USE_MINIMAL_FFMPEG:-1}" == "1" ]] && command -v gcc &>/dev/null && command -v make &>/dev/null; then
        bash "$PROJECT_ROOT/packaging/linux/build-minimal-ffmpeg.sh" "$LINUX_FFMPEG"
    else
        bash "$PROJECT_ROOT/packaging/linux/fetch-ffmpeg.sh" "$LINUX_FFMPEG"
    fi
fi

echo "Installing dependencies via Poetry..."
poetry install --only main,build

echo "Running: poetry run python -m PyInstaller --noconfirm --clean kikumoe.spec"
poetry run python -m PyInstaller --noconfirm --clean kikumoe.spec

if [[ -f "$LINUX_FFMPEG" && -d "$PROJECT_ROOT/dist/KikuMoe" ]]; then
    cp "$LINUX_FFMPEG" "$PROJECT_ROOT/dist/KikuMoe/ffmpeg"
    chmod +x "$PROJECT_ROOT/dist/KikuMoe/ffmpeg"
fi

if [[ -d "$PROJECT_ROOT/dist/KikuMoe" && $(command -v du 2>/dev/null) ]]; then
    echo ""
    echo "=== Top 15 Largest Files in dist/KikuMoe ==="
    find "$PROJECT_ROOT/dist/KikuMoe" -type f -exec du -h {} + | sort -rh | head -15 || true
    echo "==========================================="
    echo ""
fi

VERSION="$(sed -nE 's/^version:[[:space:]]*"?([^"[:space:]]+)"?.*/\1/p' "$PROJECT_ROOT/version.yml" | head -1)"
echo "Done. Output:"
echo "  dist/KikuMoe/KikuMoe (v${VERSION:-2.0.0-beta3})"
