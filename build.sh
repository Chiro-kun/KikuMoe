#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"
PYTHON="$([ -f "$VENV_PYTHON" ] && echo "$VENV_PYTHON" || echo "python3")"

echo "Using Python: $PYTHON"
echo "Installing build/runtime requirements..."
"$PYTHON" -m pip install --upgrade pyinstaller pyinstaller-hooks-contrib
"$PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt"

# Fast sanity check
"$PYTHON" -c "import PyQt5, websocket; print('build-env-ok')"

SPEC_PATH="$PROJECT_ROOT/kikumoe.spec"
echo "Running: $PYTHON -m PyInstaller --noconfirm --clean $SPEC_PATH"
"$PYTHON" -m PyInstaller --noconfirm --clean "$SPEC_PATH"

echo "Done. Output:"
echo "  dist/KikuMoe-1.9.0"
