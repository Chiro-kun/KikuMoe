"""Global pytest configuration and per-test hang watchdog."""

from __future__ import annotations

import faulthandler
import os
import sys
import threading
from collections.abc import Iterator

import pytest

_DEFAULT_TEST_TIMEOUT_SECONDS = 30.0
# Capture real stdout fd before pytest's fd-level capture redirects fd 1/2
try:
    _REAL_STDOUT_FD: int | None = os.dup(1)
except OSError:
    _REAL_STDOUT_FD = None


@pytest.fixture(autouse=True)
def _per_test_hang_watchdog(request: pytest.FixtureRequest) -> Iterator[None]:
    """Fail fast with a full thread traceback if any individual test hangs."""
    raw = os.environ.get("KIKUMOE_TEST_TIMEOUT", "")
    try:
        timeout = float(raw) if raw else _DEFAULT_TEST_TIMEOUT_SECONDS
    except ValueError:
        timeout = _DEFAULT_TEST_TIMEOUT_SECONDS

    if timeout <= 0:
        yield
        return

    nodeid = request.node.nodeid

    def _on_timeout() -> None:
        msg = f"\n\n[WATCHDOG] Test timed out after {timeout:.1f}s: {nodeid}\n"
        try:
            if _REAL_STDOUT_FD is not None:
                os.write(_REAL_STDOUT_FD, msg.encode("utf-8", errors="replace"))
                faulthandler.dump_traceback(file=_REAL_STDOUT_FD, all_threads=True)
            else:
                out = sys.__stdout__ or sys.stdout
                out.write(msg)
                out.flush()
                faulthandler.dump_traceback(file=out, all_threads=True)
                out.flush()
        except Exception:
            pass
        os._exit(124)

    timer = threading.Timer(timeout, _on_timeout)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
