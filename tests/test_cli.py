from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from core.constants import APP_NAME, APP_VERSION
from KikuMoe import main


def test_cli_version_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["KikuMoe.py", "--version"])
    exit_code = main()
    assert exit_code == 0
    captured = capsys.readouterr()
    assert f"{APP_NAME} {APP_VERSION}" in captured.out


def test_cli_short_version_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["KikuMoe.py", "-v"])
    exit_code = main()
    assert exit_code == 0
    captured = capsys.readouterr()
    assert f"{APP_NAME} {APP_VERSION}" in captured.out
