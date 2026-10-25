from __future__ import annotations

import collections
import contextlib
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_DEFAULT_FORMAT = "[%(levelname)s] %(message)s"
_DEFAULT_LEVEL = logging.INFO

_debug_enabled = False
_created_loggers: list = []
_startup_debug = False
_startup_set = False
_logger_created_hooks: list = []

_RECENT_LOGS_MAX = 1000
_recent_logs: collections.deque[str] = collections.deque(maxlen=_RECENT_LOGS_MAX)


class _RingBufferHandler(logging.Handler):
    """In-memory handler buffering recent log records so UI/DevConsole can inspect past logs."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            _recent_logs.append(msg)
        except Exception:
            pass


_ring_handler = _RingBufferHandler()
_ring_handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
_ring_handler.setLevel(logging.DEBUG)


def get_recent_logs() -> list[str]:
    """Return a list of recent log lines captured since application launch."""
    return list(_recent_logs)


def get_log_dir() -> str:
    """Return the platform-specific directory where KikuMoe stores logs and data.
    Falls back to current directory or tempdir if the standard path is unwritable."""
    import tempfile

    candidates = []
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            candidates.append(os.path.join(local_app_data, "KikuMoe"))
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME", "")
        if xdg_data:
            candidates.append(os.path.join(xdg_data, "KikuMoe"))
        else:
            candidates.append(os.path.join(os.path.expanduser("~"), ".local", "share", "KikuMoe"))

    candidates.append(os.path.abspath("."))
    candidates.append(tempfile.gettempdir())

    for dir_path in candidates:
        try:
            os.makedirs(dir_path, exist_ok=True)
            test_file = os.path.join(dir_path, ".kikumoe_write_test")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(test_file)
            return dir_path
        except Exception:
            continue

    return os.path.abspath(".")


def get_log_file_path() -> str:
    """Return the absolute path to the main application log file."""
    return os.path.join(get_log_dir(), "kikumoe.log")


_file_handler: RotatingFileHandler | None = None


def _get_shared_file_handler() -> RotatingFileHandler | None:
    global _file_handler
    if _file_handler is None:
        try:
            log_path = get_log_file_path()
            _file_handler = RotatingFileHandler(
                log_path, maxBytes=1024 * 1024, backupCount=2, encoding="utf-8"
            )
            file_fmt = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            _file_handler.setFormatter(file_fmt)
            _file_handler.setLevel(logging.DEBUG if _debug_enabled else _DEFAULT_LEVEL)
        except Exception:
            _file_handler = None
    return _file_handler


class _SafeTextStream:
    """Proxy stream that avoids UnicodeEncodeError on Windows cp1252 terminals."""

    def __init__(self, stream):
        self._stream = stream

    def write(self, text: str) -> int:
        if self._stream is None:
            return len(text)
        try:
            return int(self._stream.write(text))
        except UnicodeEncodeError:
            encoding = getattr(self._stream, "encoding", None) or "utf-8"
            safe = text.encode(encoding, errors="backslashreplace").decode(
                encoding, errors="ignore"
            )
            return int(self._stream.write(safe))

    def flush(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.flush()
        except Exception:
            pass

    def isatty(self) -> bool:
        if self._stream is None:
            return False
        try:
            return bool(self._stream.isatty())
        except Exception:
            return False

    @property
    def encoding(self):
        return getattr(self._stream, "encoding", None)


@contextlib.contextmanager
def silence_stderr():
    """Temporarily redirect C-level stderr (fd 2) to /dev/null.

    Use this around PyAudio/libVLC initialisation to suppress the flood of
    ALSA/JACK/libVLC probe messages emitted directly by the C library.  Those
    messages bypass Python's logging and cannot be filtered any other way.

    No-op when debug mode is active (see set_debug()), so that --debug exposes
    all C-level output alongside the Python DEBUG traces.

    Example::

        with silence_stderr():
            pa = pyaudio.PyAudio()
    """
    if _debug_enabled:
        yield
        return

    saved_fd = None
    devnull_fd = None
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        saved_fd = os.dup(2)
        os.dup2(devnull_fd, 2)
    except Exception:
        # If redirection setup fails (e.g. fd 2 not available or closed in GUI/Windows),
        # proceed without silencing.
        if devnull_fd is not None:
            try:
                os.close(devnull_fd)
            except Exception:
                pass
        yield
        return
    else:
        try:
            os.close(devnull_fd)
        except Exception:
            pass

    try:
        yield
    finally:
        if saved_fd is not None:
            try:
                os.dup2(saved_fd, 2)
                os.close(saved_fd)
            except Exception:
                pass


def set_debug(enabled: bool) -> None:
    """Enable or disable DEBUG-level output for all KikuMoe loggers.

    Call this before creating any player or UI objects (i.e. right at startup,
    before ListenMoePlayer() is instantiated) so that every subsequent
    get_logger() call picks up the correct level.  Already-created loggers are
    updated in-place as well.
    """
    global _debug_enabled, _startup_debug, _startup_set
    _debug_enabled = bool(enabled)
    if not _startup_set:
        _startup_debug = _debug_enabled
        _startup_set = True
    level = logging.DEBUG if _debug_enabled else _DEFAULT_LEVEL
    if _file_handler is not None:
        try:
            _file_handler.setLevel(level)
        except Exception:
            pass
    for lg in _created_loggers:
        try:
            lg.setLevel(level)
        except Exception:
            pass


def is_debug() -> bool:
    """Return True if debug mode is currently active."""
    return _debug_enabled


def set_logger_level(level: int) -> None:
    """Set the logging level dynamically for all created and future KikuMoe loggers."""
    global _debug_enabled, _DEFAULT_LEVEL
    _debug_enabled = level <= logging.DEBUG
    _DEFAULT_LEVEL = level
    if _file_handler is not None:
        try:
            _file_handler.setLevel(level)
        except Exception:
            pass
    for lg in _created_loggers:
        try:
            lg.setLevel(level)
        except Exception:
            pass


def restore_default_level() -> None:
    """Restore the logging level to the startup configuration."""
    global _DEFAULT_LEVEL
    _DEFAULT_LEVEL = logging.DEBUG if _startup_debug else logging.INFO
    set_debug(_startup_debug)


def register_logger_hook(hook) -> None:
    """Register a callback invoked whenever a new logger is configured via get_logger()."""
    if hook not in _logger_created_hooks:
        _logger_created_hooks.append(hook)


def unregister_logger_hook(hook) -> None:
    """Unregister a logger creation callback."""
    if hook in _logger_created_hooks:
        _logger_created_hooks.remove(hook)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a configured logger writing to stdout and persistent log file.

    The effective level is DEBUG when debug mode is active (see set_debug()),
    and INFO otherwise.  Duplicate handlers are never added on repeated calls.
    """
    lname = name or "KikuMoe"
    logger = logging.getLogger(lname)
    if not logger.handlers:
        handler = logging.StreamHandler(_SafeTextStream(sys.stdout))
        formatter = logging.Formatter(_DEFAULT_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        fh = _get_shared_file_handler()
        if fh is not None and fh not in logger.handlers:
            logger.addHandler(fh)

        if _ring_handler not in logger.handlers:
            logger.addHandler(_ring_handler)

        logger.setLevel(logging.DEBUG if _debug_enabled else _DEFAULT_LEVEL)
        logger.propagate = False
        _created_loggers.append(logger)
        for hook in list(_logger_created_hooks):
            try:
                hook(logger)
            except Exception:
                pass
    return logger
