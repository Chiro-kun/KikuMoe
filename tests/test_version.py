from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from core.constants import APP_VERSION
from scripts.sync_version import parse_numeric_tuple, read_version_yml


def test_app_version_matches_version_yml():
    """Verify APP_VERSION loaded at runtime matches version.yml exactly."""
    expected = read_version_yml()
    assert APP_VERSION == expected


def test_sync_version_check_cli():
    """Verify that scripts/sync_version.py --check passes on the repo."""
    repo_root = Path(__file__).resolve().parent.parent
    cmd = [sys.executable, str(repo_root / "scripts" / "sync_version.py"), "--check"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"sync_version.py --check failed:\n{res.stdout}\n{res.stderr}"


def test_parse_numeric_tuple():
    """Verify semver to 4-tuple conversion for PE version headers."""
    assert parse_numeric_tuple("2.0.0-beta4") == (2, 0, 0, 4)
    assert parse_numeric_tuple("2.0.0") == (2, 0, 0, 0)
    assert parse_numeric_tuple("1.11.2.3") == (1, 11, 2, 3)
