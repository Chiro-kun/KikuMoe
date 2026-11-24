from __future__ import annotations

import faulthandler
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from core import crash_handler, logger

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def isolated_crash_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect crash/log directory into ``tmp_path`` and always restore handlers."""
    monkeypatch.setattr(crash_handler, "get_log_dir", lambda: str(tmp_path))
    monkeypatch.setattr(logger, "get_log_dir", lambda: str(tmp_path))
    try:
        yield tmp_path
    finally:
        crash_handler.uninstall_crash_handlers()


def test_write_crash_log_includes_metadata_traceback_and_recent_logs(
    isolated_crash_dir: Path,
) -> None:
    log = logger.get_logger("CrashTest")
    log.info("recent-context-marker-42")

    try:
        raise RuntimeError("boom during playback")
    except RuntimeError as exc:
        path = crash_handler.write_crash_log(exc, source="main")

    assert path == os.path.join(str(isolated_crash_dir), "crash.log")
    content = Path(path).read_text(encoding="utf-8")
    assert "=== KikuMoe Crash [" in content
    assert "Source: main" in content
    assert "RuntimeError: boom during playback" in content
    assert "--- Recent Logs" in content
    assert "recent-context-marker-42" in content


def test_sys_excepthook_captures_exception_and_ignores_keyboard_interrupt(
    isolated_crash_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chained: list[type[BaseException]] = []
    monkeypatch.setattr(sys, "excepthook", lambda exc_type, _val, _tb: chained.append(exc_type))

    crash_handler.install_crash_handlers(enable_faulthandler=False, enable_qt_handler=False)

    # KeyboardInterrupt should chain without creating a crash entry.
    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt as exc:
        sys.excepthook(type(exc), exc, exc.__traceback__)

    crash_file = isolated_crash_dir / "crash.log"
    assert not crash_file.exists() or crash_file.read_text(encoding="utf-8") == ""
    assert chained == [KeyboardInterrupt]

    # Real exception should be written and chained.
    try:
        raise ValueError("bad slot state")
    except ValueError as exc:
        sys.excepthook(type(exc), exc, exc.__traceback__)

    content = crash_file.read_text(encoding="utf-8")
    assert "Source: sys.excepthook" in content
    assert "ValueError: bad slot state" in content
    assert chained == [KeyboardInterrupt, ValueError]


def test_threading_excepthook_captures_background_thread_crash(
    isolated_crash_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chained_threads: list[str] = []
    monkeypatch.setattr(
        threading,
        "excepthook",
        lambda args: chained_threads.append(args.thread.name if args.thread else ""),
    )

    crash_handler.install_crash_handlers(enable_faulthandler=False, enable_qt_handler=False)

    def _boom() -> None:
        raise RuntimeError("background audio died")

    t = threading.Thread(target=_boom, name="AudioWorkerTest")
    t.start()
    t.join(timeout=5)

    crash_file = isolated_crash_dir / "crash.log"
    content = crash_file.read_text(encoding="utf-8")
    assert "Source: threading.excepthook" in content
    assert "Thread: AudioWorkerTest" in content
    assert "RuntimeError: background audio died" in content
    assert chained_threads == ["AudioWorkerTest"]


def test_qt_message_handler_logs_fatal_without_reentering_qt(
    isolated_crash_dir: Path,
) -> None:
    from PyQt6.QtCore import QtMsgType

    crash_handler.install_crash_handlers(enable_faulthandler=False, enable_qt_handler=True)

    fake_ctx = SimpleNamespace(
        category="qt.qpa.wayland",
        file="qwaylanddisplay.cpp",
        line=123,
        function="connect",
    )
    crash_handler._qt_message_handler(QtMsgType.QtFatalMsg, fake_ctx, "Wayland display lost")

    crash_file = isolated_crash_dir / "crash.log"
    content = crash_file.read_text(encoding="utf-8")
    assert "Source: qt.fatal" in content
    assert "QtFatalMsg: Wayland display lost" in content
    assert "qwaylanddisplay.cpp:123" in content


def test_faulthandler_enabled_and_rotation_while_active(isolated_crash_dir: Path) -> None:
    log_path = Path(
        crash_handler.install_crash_handlers(enable_faulthandler=True, enable_qt_handler=False)
    )
    assert faulthandler.is_enabled()
    assert crash_handler._faulthandler_file is not None

    # Force rotation while faulthandler keeps crash.log open.
    crash_handler.write_crash_report(source="test", body="A" * 200, max_bytes=100)
    crash_handler.write_crash_report(source="test", body="SECOND_ENTRY\n", max_bytes=100)

    backup = isolated_crash_dir / "crash.log.1"
    assert backup.exists()
    assert "SECOND_ENTRY" in log_path.read_text(encoding="utf-8")
    assert crash_handler._faulthandler_file is not None

    crash_handler.uninstall_crash_handlers()
    assert crash_handler._faulthandler_file is None


def test_faulthandler_captures_native_sigabrt_in_subprocess(tmp_path: Path) -> None:
    env = os.environ.copy()
    if sys.platform == "win32":
        env["LOCALAPPDATA"] = str(tmp_path)
    else:
        env["XDG_DATA_HOME"] = str(tmp_path)

    script = (
        "import signal; "
        "from core.crash_handler import install_crash_handlers; "
        "install_crash_handlers(enable_faulthandler=True, enable_qt_handler=False); "
        "signal.raise_signal(signal.SIGABRT)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode != 0

    crash_file = tmp_path / "KikuMoe" / "crash.log"
    assert crash_file.exists()
    content = crash_file.read_text(encoding="utf-8", errors="replace")
    assert "Fatal Python error: Aborted" in content
