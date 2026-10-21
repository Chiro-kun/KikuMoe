#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing dependencies via Poetry..."
poetry install --with dev

echo "Running: poetry run python -m PyInstaller --noconfirm --clean kikumoe.spec"
cd "$PROJECT_ROOT"
poetry run python -m PyInstaller --noconfirm --clean kikumoe.spec

VERSION="$(grep -oP '(?<=version:\s).+' "$PROJECT_ROOT/version.yml" | tr -d '[:space:]' || echo '2.0.0-beta1')"
echo "Done. Output:"
echo "  dist/KikuMoe-${VERSION}"
