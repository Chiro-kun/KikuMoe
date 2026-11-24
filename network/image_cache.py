"""In-memory and bounded disk cover art cache shared between MainWindow, popovers, and MPRIS."""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import threading
import urllib.parse
from collections import OrderedDict
from pathlib import Path
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
_MAX_DISK_COVER_ENTRIES: Final[int] = 24
_CACHE_LOCK = threading.RLock()
_PIXMAP_CACHE: OrderedDict[str, QPixmap] = OrderedDict()
_COVER_FILE_CACHE: OrderedDict[str, Path] = OrderedDict()


def normalize_cover_url(cover_ref: str | None) -> str | None:
    """Normalize a station cover reference or URL against the HTTPS host whitelist."""
    try:
        if not isinstance(cover_ref, str):
            return None
        value = cover_ref.strip()
        if not value:
            return None

        low = value.lower()
        if (
            low.startswith(("http://", "file://", "\\\\", "//"))
            or "\\" in value
            or (len(value) >= 2 and value[1] == ":")
            or (value.startswith("/") and not low.startswith("/covers/"))
        ):
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


def get_cover_cache_dir() -> Path:
    """Return the user-writable disk cache directory for MPRIS/SMTC local cover files."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        return Path(base) / "KikuMoe" / "art_cache"
    xdg_cache = (os.environ.get("XDG_CACHE_HOME") or "").strip()
    if xdg_cache:
        return Path(xdg_cache) / "kikumoe" / "mpris_art"
    try:
        return Path.home() / ".cache" / "kikumoe" / "mpris_art"
    except Exception:
        return Path(tempfile.gettempdir()) / "kikumoe_mpris_art"


def _cover_cache_stem(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def _detect_raw_image_ext(raw: bytes | None) -> tuple[str | None, bool]:
    """Return (extension, is_universal_mpris_format) from image magic bytes."""
    if not raw or len(raw) < 12:
        return None, False
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", True
    if raw.startswith(b"\xff\xd8\xff"):
        return ".jpg", True
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp", False
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return ".gif", False
    return None, False


def _prune_cover_cache_dir(cache_dir: Path, keep_path: Path | None = None) -> None:
    try:
        files = [
            p
            for p in cache_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".webp", ".gif"}
        ]
        if len(files) <= _MAX_DISK_COVER_ENTRIES:
            return
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in files[_MAX_DISK_COVER_ENTRIES:]:
            if keep_path is not None and stale == keep_path:
                continue
            try:
                stale.unlink(missing_ok=True)
            except OSError:
                pass
    except OSError:
        pass


def store_cover_file(
    url_or_ref: str | None,
    raw: bytes | None = None,
    pixmap: QPixmap | None = None,
) -> str | None:
    """Persist cover art as a local PNG/JPG file and return its file:// URI for MPRIS/SMTC.

    Raw JPEG/PNG payloads are written directly for speed; WebP and other formats are
    transcoded to PNG when a decoded QPixmap is available so GTK/GdkPixbuf-based Linux
    MPRIS widgets without WebP loaders can always display the artwork.
    """
    if not url_or_ref:
        return None
    key = normalize_cover_url(url_or_ref) or url_or_ref.strip()
    if not key:
        return None

    raw_ext, is_universal = _detect_raw_image_ext(raw)
    has_valid_pixmap = pixmap is not None and not pixmap.isNull()
    if is_universal and raw_ext and raw is not None:
        ext = raw_ext
        use_raw = True
    elif has_valid_pixmap:
        ext = ".png"
        use_raw = False
    elif raw_ext and raw is not None:
        ext = raw_ext
        use_raw = True
    else:
        return None

    try:
        cache_dir = get_cover_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        stem = _cover_cache_stem(key)
        target = cache_dir / f"{stem}{ext}"

        if not (target.is_file() and target.stat().st_size > 0):
            tmp_path = cache_dir / f".{stem}.{os.getpid()}.{threading.get_ident()}.tmp"
            try:
                if use_raw and raw is not None:
                    with open(tmp_path, "wb") as f:
                        f.write(raw)
                elif pixmap is not None:
                    if not pixmap.save(str(tmp_path), "PNG"):
                        return None
                os.replace(tmp_path, target)
            finally:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except OSError:
                        pass
        else:
            try:
                os.utime(target, None)
            except OSError:
                pass

        _prune_cover_cache_dir(cache_dir, keep_path=target)
        with _CACHE_LOCK:
            if key in _COVER_FILE_CACHE:
                _COVER_FILE_CACHE.move_to_end(key)
            _COVER_FILE_CACHE[key] = target
            while len(_COVER_FILE_CACHE) > _MAX_CACHE_ENTRIES:
                _COVER_FILE_CACHE.popitem(last=False)
        return target.resolve().as_uri()
    except OSError:
        return None


def get_cached_cover_file_uri(url_or_ref: str | None) -> str | None:
    """Return a verified local file:// URI for a previously cached cover, if present on disk."""
    if not url_or_ref:
        return None
    raw_key = url_or_ref.strip()
    if not raw_key:
        return None
    norm_key = normalize_cover_url(raw_key)
    candidates = [c for c in (norm_key, raw_key) if c]

    with _CACHE_LOCK:
        for candidate in candidates:
            path = _COVER_FILE_CACHE.get(candidate)
            if path is not None:
                if path.is_file() and path.stat().st_size > 0:
                    _COVER_FILE_CACHE.move_to_end(candidate)
                    return path.resolve().as_uri()
                _COVER_FILE_CACHE.pop(candidate, None)

    try:
        cache_dir = get_cover_cache_dir()
        if not cache_dir.is_dir():
            return None
        for candidate in candidates:
            stem = _cover_cache_stem(candidate)
            for ext in (".png", ".jpg", ".webp", ".gif"):
                disk_path = cache_dir / f"{stem}{ext}"
                if disk_path.is_file() and disk_path.stat().st_size > 0:
                    with _CACHE_LOCK:
                        _COVER_FILE_CACHE[candidate] = disk_path
                    return disk_path.resolve().as_uri()
    except OSError:
        return None
    return None


def clear_cached_cover_files(delete_files: bool = False) -> None:
    """Clear the in-memory cover file URI map and optionally remove cached files on disk."""
    with _CACHE_LOCK:
        paths = list(_COVER_FILE_CACHE.values())
        _COVER_FILE_CACHE.clear()
    if delete_files:
        for p in paths:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
