import logging
import sys
from typing import Optional

_DEFAULT_FORMAT = '[%(levelname)s] %(message)s'


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


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a configured logger that logs to stdout at DEBUG level by default.
    It avoids adding duplicate handlers on repeated calls.
    """
    lname = name or 'KikuMoe'
    logger = logging.getLogger(lname)
    if not logger.handlers:
        handler = logging.StreamHandler(_SafeTextStream(sys.stdout))
        formatter = logging.Formatter(_DEFAULT_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger
