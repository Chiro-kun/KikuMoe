import contextlib
import logging
import os
import sys
from typing import Optional

_DEFAULT_FORMAT = '[%(levelname)s] %(message)s'
_DEFAULT_LEVEL = logging.INFO

_debug_enabled = False
_created_loggers: list = []


class _SafeTextStream:
    """Proxy stream that avoids UnicodeEncodeError on Windows cp1252 terminals."""

    def __init__(self, stream):
        self._stream = stream

    def write(self, text: str) -> int:
        try:
            return self._stream.write(text)
        except UnicodeEncodeError:
            encoding = getattr(self._stream, "encoding", None) or "utf-8"
            safe = text.encode(encoding, errors="backslashreplace").decode(encoding, errors="ignore")
            return self._stream.write(safe)

    def flush(self) -> None:
        try:
            self._stream.flush()
        except Exception:
            pass

    def isatty(self) -> bool:
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
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        saved_fd = os.dup(2)
        os.dup2(devnull_fd, 2)
        os.close(devnull_fd)
        try:
            yield
        finally:
            os.dup2(saved_fd, 2)
            os.close(saved_fd)
    except Exception:
        yield


def set_debug(enabled: bool) -> None:
    """Enable or disable DEBUG-level output for all KikuMoe loggers.

    Call this before creating any player or UI objects (i.e. right at startup,
    before ListenMoePlayer() is instantiated) so that every subsequent
    get_logger() call picks up the correct level.  Already-created loggers are
    updated in-place as well.
    """
    global _debug_enabled
    _debug_enabled = bool(enabled)
    level = logging.DEBUG if _debug_enabled else _DEFAULT_LEVEL
    for lg in _created_loggers:
        try:
            lg.setLevel(level)
        except Exception:
            pass


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a configured logger writing to stdout.

    The effective level is DEBUG when debug mode is active (see set_debug()),
    and INFO otherwise.  Duplicate handlers are never added on repeated calls.
    """
    lname = name or 'KikuMoe'
    logger = logging.getLogger(lname)
    if not logger.handlers:
        handler = logging.StreamHandler(_SafeTextStream(sys.stdout))
        formatter = logging.Formatter(_DEFAULT_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG if _debug_enabled else _DEFAULT_LEVEL)
        logger.propagate = False
        _created_loggers.append(logger)
    return logger
