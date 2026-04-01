import logging
import sys
from typing import Optional

_DEFAULT_FORMAT = '[%(levelname)s] %(message)s'


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a configured logger that logs to stdout at DEBUG level by default.
    It avoids adding duplicate handlers on repeated calls.
    """
    lname = name or 'KikuMoe'
    logger = logging.getLogger(lname)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(_DEFAULT_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger