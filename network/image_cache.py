"""In-memory cover art QPixmap cache shared between MainWindow and UI popovers."""

from __future__ import annotations

import threading
import urllib.parse
from collections import OrderedDict
from typing import Final

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

ALLOWED_COVER_HOSTS: Final[frozenset[str]] = frozenset(
    {
        "cdn.listen.moe",
        "listen.moe",
        "cdn.gensokyoradio.net",
        "gensokyoradio.net",
        "anison.fm",
        "pool.anison.fm",
        "radio.twinskaraoke.com",
        "twinskaraoke.com",
        "truckers.fm",
        "cdn.truckers.fm",
        "i.scdn.co",
        "scdn.co",
    }
)

_MAX_CACHE_ENTRIES: Final[int] = 64
_CACHE_LOCK = threading.RLock()
_PIXMAP_CACHE: OrderedDict[str, QPixmap] = OrderedDict()


def normalize_cover_url(cover_ref: str | None) -> str | None:
    """Normalize a station cover reference or URL against the HTTPS host whitelist."""
    try:
        if not isinstance(cover_ref, str):
            return None
        value = cover_ref.strip()
        if not value:
            return None

        low = value.lower()
        if low.startswith("http://"):
            return None

        if low.startswith("https://"):
            raw_url = value
        else:
            clean_val = value.lstrip("/")
            if clean_val.lower().startswith("covers/"):
                clean_val = clean_val[7:]
            raw_url = f"https://cdn.listen.moe/covers/{clean_val}"

        parts = urllib.parse.urlsplit(raw_url)
        if parts.scheme.lower() != "https" or not parts.netloc:
            return None

        host = (parts.hostname or "").lower()
        if not host or host not in ALLOWED_COVER_HOSTS:
            return None

        if parts.port not in (None, 443):
            return None

        safe_path = urllib.parse.quote(parts.path, safe="/%")
        return urllib.parse.urlunsplit(
            ("https", parts.netloc, safe_path, parts.query, parts.fragment)
        )
    except Exception:
        return None


def store_cached_pixmap(url_or_ref: str | None, pixmap: QPixmap | None) -> None:
    """Store a decoded cover art QPixmap in the bounded in-memory LRU cache."""
    if not url_or_ref or pixmap is None or pixmap.isNull():
        return
    key = normalize_cover_url(url_or_ref) or url_or_ref.strip()
    if not key:
        return
    with _CACHE_LOCK:
        if key in _PIXMAP_CACHE:
            _PIXMAP_CACHE.move_to_end(key)
        _PIXMAP_CACHE[key] = pixmap
        while len(_PIXMAP_CACHE) > _MAX_CACHE_ENTRIES:
            _PIXMAP_CACHE.popitem(last=False)


def get_cached_pixmap(url_or_ref: str | None) -> QPixmap | None:
    """Retrieve a cached cover art QPixmap by raw reference or normalized URL."""
    if not url_or_ref or QApplication.instance() is None:
        return None
    raw_key = url_or_ref.strip()
    if not raw_key:
        return None
    norm_key = normalize_cover_url(raw_key)
    with _CACHE_LOCK:
        for candidate in (norm_key, raw_key):
            if candidate and candidate in _PIXMAP_CACHE:
                pm = _PIXMAP_CACHE[candidate]
                if not pm.isNull():
                    _PIXMAP_CACHE.move_to_end(candidate)
                    return pm
                _PIXMAP_CACHE.pop(candidate, None)
    return None


def clear_cached_pixmaps() -> None:
    """Clear all cached cover art QPixmaps."""
    with _CACHE_LOCK:
        _PIXMAP_CACHE.clear()
