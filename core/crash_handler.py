from __future__ import annotations

import faulthandler
import logging
import os
import platform
import sys
import threading
import traceback
from collections.abc import Callable
from datetime import datetime
from types import TracebackType
from typing import IO, Any

from core.constants import APP_VERSION
from core.logger import get_log_dir, get_recent_logs, is_debug, log_to_file_only

_MAX_CRASH_LOG_SIZE = 512 * 1024  # 512 KB
_RECENT_LOGS_TAIL = 25

_CRASH_LOCK = threading.RLock()
_hook_guard = threading.local()

_installed = False
_faulthandler_file: IO[str] | None = None
_faulthandler_requested = False
_prev_sys_excepthook: (
    Callable[[type[BaseException], BaseException, TracebackType | None], Any] | None
) = None
_prev_threading_excepthook: Callable[[threading.ExceptHookArgs], Any] | None = None
_qt_handler_installed = False
_prev_qt_handler: Callable[[Any, Any, str | None], None] | None = None


def get_crash_log_path() -> str:
    """Return the absolute path to KikuMoe's persistent crash log file."""
    return os.path.join(get_log_dir(), "crash.log")


def _suspend_faulthandler() -> bool:
    """Disable faulthandler and close its open file handle so rotation is safe on Windows."""
    global _faulthandler_file
    was_active = _faulthandler_file is not None
    if was_active:
        try:
            faulthandler.disable()
        except Exception:
            pass
        try:
            assert _faulthandler_file is not None
            _faulthandler_file.flush()
            _faulthandler_file.close()
        except Exception:
            pass
        _faulthandler_file = None
    return was_active


def _resume_faulthandler(log_path: str) -> None:
    """Open ``log_path`` and enable ``faulthandler`` for fatal C-level signals."""
    global _faulthandler_file
    if not _faulthandler_requested or _faulthandler_file is not None:
        return
    fh: IO[str] | None = None
    try:
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        fh = open(log_path, "a", encoding="utf-8")
        faulthandler.enable(file=fh, all_threads=True)
        _faulthandler_file = fh
    except Exception:
        if fh is not None:
            try:
                fh.close()
            except Exception:
                pass
        _faulthandler_file = None


def _rotate_crash_log(log_path: str, max_bytes: int = _MAX_CRASH_LOG_SIZE) -> None:
    """Rotate ``log_path`` to ``<log_path>.1`` when it exceeds ``max_bytes``."""
    try:
        if os.path.isfile(log_path) and os.path.getsize(log_path) >= max_bytes:
            backup_path = f"{log_path}.1"
            try:
                os.replace(log_path, backup_path)
            except Exception:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.truncate(0)
    except Exception:
        pass


def _format_header(source: str, extra: str = "") -> str:
    timestamp = datetime.now().isoformat(sep=" ", timespec="seconds")
    lines = [
        f"\n=== KikuMoe Crash [{timestamp}] ===",
        f"Version: {APP_VERSION} | Python: {platform.python_version()} | OS: {platform.platform()}",
        f"Source: {source}",
    ]
    if extra:
        lines.append(extra)
    return "\n".join(lines) + "\n"


def _format_recent_logs(limit: int = _RECENT_LOGS_TAIL) -> str:
    try:
        recent = get_recent_logs()[-limit:]
    except Exception:
        recent = []
    if not recent:
        return ""
    return f"--- Recent Logs (last {len(recent)}) ---\n" + "\n".join(recent) + "\n"


def write_crash_report(
    source: str,
    body: str,
    extra: str = "",
    *,
    include_recent_logs: bool = True,
    max_bytes: int = _MAX_CRASH_LOG_SIZE,
) -> str:
    """Append a structured crash report to ``crash.log`` and return its path."""
    with _CRASH_LOCK:
        log_path = get_crash_log_path()
        try:
            os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        except Exception:
            pass

        need_rotation = False
        try:
            need_rotation = os.path.isfile(log_path) and os.path.getsize(log_path) >= max_bytes
        except Exception:
            need_rotation = False

        suspended = False
        if need_rotation:
            suspended = _suspend_faulthandler()
            _rotate_crash_log(log_path, max_bytes=max_bytes)

        try:
            header = _format_header(source=source, extra=extra)
            normalized_body = body if body.endswith("\n") else body + "\n"
            recent_block = _format_recent_logs() if include_recent_logs else ""
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(header)
                f.write(normalized_body)
                if recent_block:
                    f.write(recent_block)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            if suspended:
                _resume_faulthandler(log_path)

        return log_path


def write_crash_exc_info(
    exc_type: type[BaseException],
    exc_value: BaseException | None,
    exc_tb: TracebackType | None,
    *,
    source: str = "main",
    thread_name: str | None = None,
) -> str:
    """Format an exception tuple and append it to ``crash.log``."""
    try:
        formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    except Exception:
        formatted = f"{exc_type.__name__}: {exc_value}\n"
    extra = f"Thread: {thread_name}" if thread_name else ""
    return write_crash_report(source=source, body=formatted, extra=extra)


def write_crash_log(
    exc: BaseException,
    *,
    source: str = "main",
    thread_name: str | None = None,
) -> str:
    """Format a raised ``BaseException`` instance and append it to ``crash.log``."""
    return write_crash_exc_info(
        type(exc),
        exc,
        exc.__traceback__,
        source=source,
        thread_name=thread_name,
    )


def _handle_sys_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
) -> None:
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        if _prev_sys_excepthook is not None:
            _prev_sys_excepthook(exc_type, exc_value, exc_tb)
        return

    if not getattr(_hook_guard, "active", False):
        _hook_guard.active = True
        try:
            log_path = write_crash_exc_info(
                exc_type,
                exc_value,
                exc_tb,
                source="sys.excepthook",
                thread_name=threading.current_thread().name,
            )
            log_to_file_only(
                logging.CRITICAL,
                "CrashHandler",
                f"Uncaught exception ({exc_type.__name__}: {exc_value}); details in {log_path}",
            )
        except Exception:
            pass
        finally:
            _hook_guard.active = False

    if _prev_sys_excepthook is not None:
        try:
            _prev_sys_excepthook(exc_type, exc_value, exc_tb)
        except Exception:
            pass


def _handle_threading_exception(args: threading.ExceptHookArgs) -> None:
    if issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
        if _prev_threading_excepthook is not None:
            _prev_threading_excepthook(args)
        return

    if not getattr(_hook_guard, "active", False):
        _hook_guard.active = True
        try:
            thread_name = args.thread.name if args.thread is not None else "unknown"
            log_path = write_crash_exc_info(
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
                source="threading.excepthook",
                thread_name=thread_name,
            )
            log_to_file_only(
                logging.CRITICAL,
                "CrashHandler",
                f"Uncaught thread exception in '{thread_name}' "
                f"({args.exc_type.__name__}: {args.exc_value}); details in {log_path}",
            )
        except Exception:
            pass
        finally:
            _hook_guard.active = False

    if _prev_threading_excepthook is not None:
        try:
            _prev_threading_excepthook(args)
        except Exception:
            pass


def _format_qt_context(context: Any) -> str:
    if context is None:
        return ""
    parts: list[str] = []
    category = getattr(context, "category", None)
    if category and category != "default":
        parts.append(f"category={category}")
    ctx_file = getattr(context, "file", None)
    ctx_line = getattr(context, "line", 0)
    ctx_func = getattr(context, "function", None)
    if ctx_file:
        parts.append(f"{ctx_file}:{ctx_line}")
    if ctx_func:
        parts.append(f"in {ctx_func}")
    return " | ".join(parts)


def _write_stderr_safe(text: str) -> None:
    try:
        if sys.stderr is not None:
            sys.stderr.write(text)
            sys.stderr.flush()
    except Exception:
        pass


def _qt_message_handler(msg_type: Any, context: Any, message: str | None) -> None:
    if getattr(_hook_guard, "qt_active", False):
        return
    _hook_guard.qt_active = True
    try:
        from PyQt6.QtCore import QtMsgType

        text = message or ""
        loc = _format_qt_context(context)
        formatted = f"{text} ({loc})" if loc else text

        if msg_type == QtMsgType.QtFatalMsg:
            write_crash_report(
                source="qt.fatal",
                body=f"QtFatalMsg: {text}\n",
                extra=f"Context: {loc}" if loc else "",
            )
            log_to_file_only(logging.CRITICAL, "Qt", formatted)
        elif msg_type == QtMsgType.QtCriticalMsg:
            log_to_file_only(logging.ERROR, "Qt", formatted)
        elif msg_type == QtMsgType.QtWarningMsg:
            if is_debug():
                log_to_file_only(logging.WARNING, "Qt", formatted)
        elif is_debug():
            log_to_file_only(logging.DEBUG, "Qt", formatted)

        if _prev_qt_handler is not None:
            _prev_qt_handler(msg_type, context, message)
        elif (
            msg_type in (QtMsgType.QtFatalMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtWarningMsg)
            or is_debug()
        ):
            _write_stderr_safe(f"[Qt:{getattr(msg_type, 'name', msg_type)}] {formatted}\n")
    except Exception:
        pass
    finally:
        _hook_guard.qt_active = False


def install_crash_handlers(
    *,
    enable_faulthandler: bool = True,
    enable_qt_handler: bool = True,
) -> str:
    """Install process-wide Python, thread, Qt, and native signal crash handlers.

    Captures:
    - Native fatal signals (``SIGSEGV``, ``SIGABRT``, ``SIGFPE``, ``SIGBUS``, ``SIGILL``)
      via ``faulthandler.enable(..., all_threads=True)``.
    - Uncaught Python exceptions on the main thread and inside PyQt callbacks via
      ``sys.excepthook``.
    - Uncaught Python exceptions inside background ``threading.Thread`` instances via
      ``threading.excepthook``.
    - Qt fatal messages (``QtFatalMsg``) and critical/debug Qt diagnostics via
      ``qInstallMessageHandler`` without re-entering Qt signals.

    Safe to call more than once; returns the crash log path.
    """
    global _installed, _faulthandler_requested
    global _prev_sys_excepthook, _prev_threading_excepthook
    global _qt_handler_installed, _prev_qt_handler

    with _CRASH_LOCK:
        log_path = get_crash_log_path()
        if _installed:
            return log_path

        try:
            os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        except Exception:
            pass

        _rotate_crash_log(log_path)

        _faulthandler_requested = bool(enable_faulthandler)
        if _faulthandler_requested:
            _resume_faulthandler(log_path)

        _prev_sys_excepthook = sys.excepthook
        sys.excepthook = _handle_sys_exception

        _prev_threading_excepthook = threading.excepthook
        threading.excepthook = _handle_threading_exception

        if enable_qt_handler:
            try:
                from PyQt6.QtCore import qInstallMessageHandler

                _prev_qt_handler = qInstallMessageHandler(_qt_message_handler)
                _qt_handler_installed = True
            except Exception:
                _qt_handler_installed = False
                _prev_qt_handler = None

        _installed = True
        return log_path


def uninstall_crash_handlers() -> None:
    """Restore previously installed exception/Qt handlers and close ``faulthandler``."""
    global _installed, _faulthandler_requested
    global _prev_sys_excepthook, _prev_threading_excepthook
    global _qt_handler_installed, _prev_qt_handler

    with _CRASH_LOCK:
        _faulthandler_requested = False
        _suspend_faulthandler()

        if _prev_sys_excepthook is not None:
            sys.excepthook = _prev_sys_excepthook
            _prev_sys_excepthook = None

        if _prev_threading_excepthook is not None:
            threading.excepthook = _prev_threading_excepthook
            _prev_threading_excepthook = None

        if _qt_handler_installed:
            try:
                from PyQt6.QtCore import qInstallMessageHandler

                qInstallMessageHandler(_prev_qt_handler)
            except Exception:
                pass
            _qt_handler_installed = False
            _prev_qt_handler = None

        _installed = False
