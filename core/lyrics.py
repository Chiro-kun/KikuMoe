"""Synced & plain lyrics lookup (LRCLIB + Better Lyrics) and LRC/TTML/QRC parsing."""

from __future__ import annotations

import html
import json
import logging
import math
import re
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlencode

from PyQt6.QtCore import QObject, pyqtSignal

from core.constants import (
    APP_VERSION,
    DEFAULT_LYRICS_PROVIDER,
    LYRICS_PROVIDER_AUTO,
    LYRICS_PROVIDER_BETTERLYRICS,
    LYRICS_PROVIDER_BETTERLYRICS_FIRST,
    LYRICS_PROVIDER_LRCLIB,
    URL_FORGEJO,
)
from core.ssl_compat import get_ssl_context

_TIME = re.compile(r"\[(\d+):(\d{1,2}(?:\.\d+)?)\]")
_QRC_LINE_HEADER = re.compile(r"^\[(\d+),(\d+)\]")
_QRC_WORD_TOKEN = re.compile(r"\(\d+,\d+\)")
_QRC_CONTENT_ATTR = re.compile(r'LyricContent="([\s\S]*?)"\s*(?:/?>|[a-zA-Z]+=)')
_WHITESPACE_RUN = re.compile(r"\s+")

LRCLIB_API_BASE = "https://lrclib.net/api/"
BETTERLYRICS_API_BASE = "https://api.betterlyrics.org"

_VALID_PROVIDER_MODES = {
    LYRICS_PROVIDER_AUTO,
    LYRICS_PROVIDER_BETTERLYRICS_FIRST,
    LYRICS_PROVIDER_LRCLIB,
    LYRICS_PROVIDER_BETTERLYRICS,
}

logger = logging.getLogger("kikumoe.lyrics")


def _format_lrc_timestamp(seconds: float) -> str:
    """Format a non-negative timestamp in seconds as `[mm:ss.xx]`."""
    total_cs = max(0, round(seconds * 100))
    minutes, cs_rem = divmod(total_cs, 6000)
    return f"[{minutes:02d}:{cs_rem / 100:05.2f}]"


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_lrc(text: str | None) -> list[tuple[float, str]]:
    """Parse LRC text into sorted `(seconds, lyric_line)` tuples."""
    lines: list[tuple[float, str]] = []
    for line in (text or "").splitlines():
        matches = list(_TIME.finditer(line))
        if not matches:
            continue
        lyric = _TIME.sub("", line).strip()
        for match in matches:
            lines.append((int(match.group(1)) * 60 + float(match.group(2)), lyric))
    return sorted(lines, key=lambda item: item[0])


def _lrc_to_plain(lrc_text: str) -> str:
    lines = [text for _, text in parse_lrc(lrc_text) if text]
    return "\n".join(lines)


def parse_ttml_time(value: str | None) -> float | None:
    """Parse TTML timestamp formats (`HH:MM:SS.mmm`, `M:SS.mmm`, `SS.mmm`, `...ms`)."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.lower().endswith("ms"):
            seconds = float(raw[:-2].strip()) / 1000.0
        else:
            if raw.lower().endswith("s"):
                raw = raw[:-1].strip()
            parts = raw.split(":")
            if len(parts) == 3:
                seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                seconds = int(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 1:
                seconds = float(parts[0])
            else:
                return None
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def _has_unsafe_xml_decl(xml_text: str) -> bool:
    lowered = xml_text[:512].lower()
    return "<!doctype" in lowered or "<!entity" in lowered


def ttml_to_lrc(ttml_text: str | None) -> str:
    """Convert a TTML XML lyrics document into line-synced LRC text."""
    raw = str(ttml_text or "").strip()
    if not raw or _has_unsafe_xml_decl(raw):
        return ""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return ""

    body: ET.Element | None = None
    for elem in root.iter():
        if _local_tag(elem.tag) == "body":
            body = elem
            break
    search_root = body if body is not None else root

    timed_lines: list[tuple[float, str]] = []
    for elem in search_root.iter():
        if _local_tag(elem.tag) != "p":
            continue
        begin = parse_ttml_time(elem.attrib.get("begin"))
        if begin is None:
            for child in elem.iter():
                if _local_tag(child.tag) == "span":
                    begin = parse_ttml_time(child.attrib.get("begin"))
                    if begin is not None:
                        break
        if begin is None:
            continue
        line_text = _WHITESPACE_RUN.sub(" ", "".join(elem.itertext())).strip()
        timed_lines.append((begin, line_text))

    if not any(text for _, text in timed_lines):
        return ""
    timed_lines.sort(key=lambda item: item[0])
    return "\n".join(f"{_format_lrc_timestamp(ts)}{text}" for ts, text in timed_lines)


def _extract_qrc_body(qrc_text: str) -> str:
    raw = str(qrc_text or "").strip()
    if not raw or _has_unsafe_xml_decl(raw):
        return ""
    # Extract LyricContent before XML parsing because XML attribute normalization
    # turns raw newlines into spaces.
    match = _QRC_CONTENT_ATTR.search(raw)
    if match:
        return html.unescape(match.group(1))
    try:
        root = ET.fromstring(raw)
        for elem in root.iter():
            content = elem.attrib.get("LyricContent")
            if content:
                return content
    except ET.ParseError:
        pass
    return raw


def qrc_to_lrc(qrc_text: str | None) -> str:
    """Convert QQ QRC XML/body lyrics into line-synced LRC text."""
    body = _extract_qrc_body(str(qrc_text or ""))
    if not body:
        return ""
    timed_lines: list[tuple[float, str]] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        header = _QRC_LINE_HEADER.match(line)
        if not header:
            continue
        start_ms = int(header.group(1))
        rest = line[header.end() :]
        cleaned = _QRC_WORD_TOKEN.sub("", rest)
        cleaned = _WHITESPACE_RUN.sub(" ", cleaned).strip()
        timed_lines.append((start_ms / 1000.0, cleaned))

    if not any(text for _, text in timed_lines):
        return ""
    timed_lines.sort(key=lambda item: item[0])
    return "\n".join(f"{_format_lrc_timestamp(ts)}{text}" for ts, text in timed_lines)


def _similarity(a: Any, b: Any) -> float:
    def normalize(value: Any) -> str:
        return " ".join(re.findall(r"\w+", str(value or "").casefold()))

    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def select_match(
    records: list[Any], title: str, artist: str, duration: float | int
) -> dict[str, Any] | None:
    """Pick the closest LRCLIB search hit matching title, artist, and duration."""
    best: dict[str, Any] | None = None
    best_score = 0.0
    for record in records:
        if not isinstance(record, dict):
            continue
        title_score = _similarity(title, record.get("trackName"))
        artist_score = _similarity(artist, record.get("artistName"))
        if title_score < 0.72 or artist_score < 0.6:
            continue
        try:
            difference = abs(float(record.get("duration") or 0) - float(duration or 0))
        except (TypeError, ValueError):
            difference = 0.0
        if duration and record.get("duration") and difference > 15:
            continue
        score = title_score + artist_score + (0.1 if record.get("syncedLyrics") else 0)
        if score > best_score:
            best, best_score = record, score
    return best


def _extract_retry_after(exc: urllib.error.HTTPError, default: int = 60) -> int:
    try:
        header_val = exc.headers.get("Retry-After") if exc.headers is not None else None
        return max(1, int(header_val or default))
    except (TypeError, ValueError):
        return default


def _has_synced_lyrics(record: dict[str, Any] | None) -> bool:
    if not isinstance(record, dict):
        return False
    if record.get("instrumental"):
        return True
    return bool(parse_lrc(record.get("syncedLyrics")))


def _has_any_lyrics(record: dict[str, Any] | None) -> bool:
    if not isinstance(record, dict):
        return False
    return bool(
        record.get("instrumental")
        or str(record.get("syncedLyrics") or "").strip()
        or str(record.get("plainLyrics") or "").strip()
    )


class LyricsProvider(QObject):
    """Perform sequential lyrics lookups across LRCLIB and Better Lyrics off the UI thread."""

    finished = pyqtSignal(object, str)
    _result = pyqtSignal(int, object, object, str, float, float)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.generation: int = 0
        self.cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self.retry_after: float = 0.0
        self._betterlyrics_retry_after: float = 0.0
        self._betterlyrics_negative_cache: dict[tuple[str, str, int, str], float] = {}
        self.provider_mode: str = DEFAULT_LYRICS_PROVIDER
        self.betterlyrics_api_key: str = ""
        self._lock = threading.Lock()
        self._pending: (
            tuple[dict[str, str | int], tuple[str, str, int], str, int, tuple[Any, ...]] | None
        ) = None
        self._worker: threading.Thread | None = None
        self._last_request: float = 0.0
        self._result.connect(self._deliver)

    def configure(
        self,
        provider_mode: str | None = None,
        betterlyrics_api_key: str | None = None,
    ) -> bool:
        """Update lyrics provider cascade mode and optional Better Lyrics API key."""
        norm_mode = str(provider_mode or DEFAULT_LYRICS_PROVIDER).strip().lower()
        if norm_mode not in _VALID_PROVIDER_MODES:
            norm_mode = DEFAULT_LYRICS_PROVIDER
        norm_key = str(betterlyrics_api_key or "").strip()
        changed = (norm_mode != self.provider_mode) or (norm_key != self.betterlyrics_api_key)
        if changed:
            self.provider_mode = norm_mode
            self.betterlyrics_api_key = norm_key
            self.cache.clear()
            self._betterlyrics_negative_cache.clear()
            self.cancel()
        return changed

    def cancel(self) -> None:
        self.generation += 1
        with self._lock:
            self._pending = None

    def _provider_sequence(self) -> tuple[str, ...]:
        if self.provider_mode == LYRICS_PROVIDER_BETTERLYRICS_FIRST:
            return ("betterlyrics", "lrclib")
        if self.provider_mode == LYRICS_PROVIDER_LRCLIB:
            return ("lrclib",)
        if self.provider_mode == LYRICS_PROVIDER_BETTERLYRICS:
            return ("betterlyrics",)
        return ("lrclib", "betterlyrics")

    def _all_providers_in_backoff(self) -> bool:
        now = time.monotonic()
        seq = self._provider_sequence()
        for name in seq:
            if name == "lrclib" and now >= self.retry_after:
                return False
            if name == "betterlyrics" and now >= self._betterlyrics_retry_after:
                return False
        return True

    def search(
        self,
        title: str,
        artist: str,
        duration: float | int = 0,
        album: str = "",
    ) -> None:
        self.cancel()
        clean_title = str(title or "").strip()
        clean_artist = str(artist or "").strip()
        clean_album = str(album or "").strip()
        if not clean_title or not clean_artist or clean_title in ("–", "-"):
            self.finished.emit(None, "missing")
            return
        dur_int = int(duration or 0)
        lrclib_key = (clean_title, clean_artist, dur_int)
        cache_key = (clean_title, clean_artist, dur_int, clean_album, self.provider_mode)
        if cache_key in self.cache:
            self.finished.emit(self.cache[cache_key], "ok")
            return
        if self._all_providers_in_backoff():
            self.finished.emit(None, "error")
            return
        params: dict[str, str | int] = {"track_name": clean_title, "artist_name": clean_artist}
        if 0 < dur_int <= 3600:
            params["duration"] = dur_int
        with self._lock:
            self._pending = (params, lrclib_key, clean_album, self.generation, cache_key)
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="LyricsLookup", daemon=True)
                self._worker.start()

    def _http_get_json(
        self, url: str, extra_headers: dict[str, str] | None = None
    ) -> tuple[Any, dict[str, str]]:
        delay = 0.3 - (time.monotonic() - self._last_request)
        if delay > 0:
            time.sleep(delay)
        self._last_request = time.monotonic()
        headers = {"User-Agent": f"KikuMoe/{APP_VERSION} ({URL_FORGEJO})"}
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=8, context=get_ssl_context()) as response:
            resp_headers = (
                {k.lower(): v for k, v in response.headers.items()}
                if response.headers is not None
                else {}
            )
            payload = json.loads(response.read(2_000_000).decode("utf-8"))
            return payload, resp_headers

    def _request(self, endpoint: str, params: dict[str, Any]) -> Any:
        url = LRCLIB_API_BASE + endpoint + "?" + urlencode(params)
        payload, _ = self._http_get_json(url)
        return payload

    def _request_betterlyrics(self, endpoint: str, params: dict[str, Any]) -> Any:
        path = endpoint if endpoint.startswith("/") else "/" + endpoint
        url = BETTERLYRICS_API_BASE + path + "?" + urlencode(params)
        extra_headers: dict[str, str] = {}
        if self.betterlyrics_api_key:
            extra_headers["X-API-Key"] = self.betterlyrics_api_key
        payload, headers = self._http_get_json(url, extra_headers=extra_headers or None)
        cache_status = headers.get("x-cache-status", "")
        if cache_status:
            logger.debug("Better Lyrics %s X-Cache-Status=%s", path, cache_status)
        return payload

    def _lookup(
        self, params: dict[str, Any], key: tuple[str, str, int], generation: int
    ) -> tuple[dict[str, Any] | None, str, float]:
        """Query LRCLIB (`get` then fuzzy `search`) and return `(record, status, retry_after)`."""
        try:
            try:
                data = self._request("get", params)
                record: dict[str, Any] | None = data if isinstance(data, dict) else None
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                if generation != self.generation:
                    return None, "cancelled", 0.0
                data = self._request("search", {"track_name": key[0], "artist_name": key[1]})
                record = None
                if isinstance(data, list):
                    record = select_match(data, *key)
            if record is not None and not isinstance(record, dict):
                record = None
            return record, "ok" if record else "missing", 0.0
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503):
                delay = _extract_retry_after(exc)
                logger.warning("LRCLIB returned HTTP %s; retry in %s seconds", exc.code, delay)
                return None, "error", time.monotonic() + delay
            logger.warning("LRCLIB request failed: HTTP %s", exc.code)
            return None, "error", 0.0
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            logger.warning("LRCLIB request failed: %s", exc)
            return None, "error", 0.0

    def _build_betterlyrics_record(
        self,
        endpoint: str,
        data: Any,
        title: str,
        artist: str,
    ) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        synced_lrc = ""
        plain = ""
        provider_tag = "betterlyrics"
        if endpoint == "/getLyrics":
            ttml = data.get("ttml")
            if isinstance(ttml, str) and ttml.strip():
                synced_lrc = ttml_to_lrc(ttml)
                plain = _lrc_to_plain(synced_lrc)
            provider_tag = "betterlyrics_ttml"
        elif endpoint == "/kugou/getLyrics":
            raw_lyrics = data.get("lyrics")
            if isinstance(raw_lyrics, str) and raw_lyrics.strip():
                if parse_lrc(raw_lyrics):
                    synced_lrc = raw_lyrics
                    plain = _lrc_to_plain(raw_lyrics)
                else:
                    plain = raw_lyrics.strip()
            provider_tag = "betterlyrics_kugou"
        elif endpoint == "/qq/getLyrics":
            raw_qrc = data.get("lyrics")
            if isinstance(raw_qrc, str) and raw_qrc.strip():
                synced_lrc = qrc_to_lrc(raw_qrc)
                plain = _lrc_to_plain(synced_lrc)
            provider_tag = "betterlyrics_qq"

        if not synced_lrc and not plain:
            return None
        return {
            "trackName": title,
            "artistName": artist,
            "syncedLyrics": synced_lrc,
            "plainLyrics": plain,
            "instrumental": False,
            "provider": provider_tag,
        }

    def _lookup_betterlyrics(
        self,
        title: str,
        artist: str,
        duration: int,
        album: str,
        generation: int,
    ) -> tuple[dict[str, Any] | None, str, float]:
        """Query Better Lyrics (`/getLyrics`, `/kugou/getLyrics`, `/qq/getLyrics`)."""
        neg_key = (title.casefold(), artist.casefold(), duration, album.casefold())
        neg_exp = self._betterlyrics_negative_cache.get(neg_key, 0.0)
        if neg_exp > time.monotonic():
            return None, "missing", 0.0

        params: dict[str, Any] = {"s": title, "a": artist}
        # Cache entries on api.betterlyrics.org often omit `al`; sending `al`
        # without an API key turns cached hits into 401 cache misses.
        if album and self.betterlyrics_api_key:
            params["al"] = album
        if 0 < duration <= 3600:
            params["d"] = str(duration)

        plain_fallback: dict[str, Any] | None = None
        had_error = False
        had_clean_miss = False
        had_auth_miss = False

        for endpoint in ("/getLyrics", "/kugou/getLyrics", "/qq/getLyrics"):
            if generation != self.generation:
                return None, "cancelled", 0.0
            try:
                data = self._request_betterlyrics(endpoint, params)
                rec = self._build_betterlyrics_record(endpoint, data, title, artist)
                if rec is not None:
                    if _has_synced_lyrics(rec):
                        return rec, "ok", 0.0
                    if plain_fallback is None and _has_any_lyrics(rec):
                        plain_fallback = rec
                else:
                    had_clean_miss = True
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    had_auth_miss = True
                    logger.debug(
                        "Better Lyrics %s returned 401 (cache miss/key required); trying fallback",
                        endpoint,
                    )
                    continue
                if exc.code == 404:
                    had_clean_miss = True
                    continue
                if exc.code == 422:
                    return None, "missing", 0.0
                if exc.code in (429, 503):
                    delay = _extract_retry_after(exc)
                    logger.warning(
                        "Better Lyrics returned HTTP %s; retry in %s seconds", exc.code, delay
                    )
                    return (
                        plain_fallback,
                        "ok" if plain_fallback else "error",
                        (0.0 if plain_fallback else time.monotonic() + delay),
                    )
                had_error = True
                logger.warning("Better Lyrics %s failed: HTTP %s", endpoint, exc.code)
            except (OSError, ValueError, UnicodeDecodeError) as exc:
                had_error = True
                logger.warning("Better Lyrics %s failed: %s", endpoint, exc)

        if plain_fallback is not None:
            return plain_fallback, "ok", 0.0
        if had_auth_miss and not had_error:
            if self.betterlyrics_api_key:
                logger.warning(
                    "Better Lyrics rejected X-API-Key with HTTP 401 for %s - %s", title, artist
                )
            elif self.provider_mode == LYRICS_PROVIDER_BETTERLYRICS:
                logger.info(
                    "Better Lyrics cache miss (HTTP 401; uncached queries require X-API-Key) "
                    "for %s - %s",
                    title,
                    artist,
                )
        if (had_clean_miss or had_auth_miss) and not had_error:
            if len(self._betterlyrics_negative_cache) >= 200:
                self._betterlyrics_negative_cache.pop(next(iter(self._betterlyrics_negative_cache)))
            self._betterlyrics_negative_cache[neg_key] = time.monotonic() + 600.0
            return None, "missing", 0.0
        if had_error:
            return None, "error", 0.0
        return None, "missing", 0.0

    def _lookup_cascade(
        self,
        params: dict[str, Any],
        lrclib_key: tuple[str, str, int],
        album: str,
        generation: int,
    ) -> tuple[dict[str, Any] | None, str, float, float]:
        plain_fallback: dict[str, Any] | None = None
        lrclib_retry = self.retry_after
        bl_retry = self._betterlyrics_retry_after
        had_missing = False
        had_error = False
        now = time.monotonic()

        for provider_name in self._provider_sequence():
            if generation != self.generation:
                return None, "cancelled", lrclib_retry, bl_retry

            if provider_name == "lrclib":
                if now < lrclib_retry:
                    had_error = True
                    continue
                rec, status, retry = self._lookup(params, lrclib_key, generation)
                lrclib_retry = max(lrclib_retry, retry)
            else:
                if now < bl_retry:
                    had_error = True
                    continue
                rec, status, retry = self._lookup_betterlyrics(
                    lrclib_key[0], lrclib_key[1], lrclib_key[2], album, generation
                )
                bl_retry = max(bl_retry, retry)

            if status == "cancelled" or generation != self.generation:
                return None, "cancelled", lrclib_retry, bl_retry
            if status == "ok" and rec is not None:
                if _has_synced_lyrics(rec):
                    return rec, "ok", lrclib_retry, bl_retry
                if plain_fallback is None and _has_any_lyrics(rec):
                    plain_fallback = rec
                else:
                    had_missing = True
            elif status == "missing":
                had_missing = True
            elif status == "error":
                had_error = True

        if plain_fallback is not None:
            return plain_fallback, "ok", lrclib_retry, bl_retry
        if had_missing:
            return None, "missing", lrclib_retry, bl_retry
        if had_error:
            return None, "error", lrclib_retry, bl_retry
        return None, "missing", lrclib_retry, bl_retry

    def _run(self) -> None:
        while True:
            with self._lock:
                job, self._pending = self._pending, None
                if job is None:
                    self._worker = None
                    return
            params, lrclib_key, album, generation, cache_key = job
            if self._all_providers_in_backoff():
                record: dict[str, Any] | None = None
                status = "error"
                lrclib_retry = self.retry_after
                bl_retry = self._betterlyrics_retry_after
            else:
                try:
                    record, status, lrclib_retry, bl_retry = self._lookup_cascade(
                        params, lrclib_key, album, generation
                    )
                except Exception:
                    logger.exception("Unexpected lyrics lookup error")
                    record, status = None, "error"
                    lrclib_retry = self.retry_after
                    bl_retry = self._betterlyrics_retry_after
            self.retry_after = max(self.retry_after, lrclib_retry)
            self._betterlyrics_retry_after = max(self._betterlyrics_retry_after, bl_retry)
            try:
                self._result.emit(generation, cache_key, record, status, lrclib_retry, bl_retry)
            except RuntimeError:
                return

    def _deliver(
        self,
        generation: int,
        cache_key: tuple[Any, ...],
        record: dict[str, Any] | None,
        status: str,
        lrclib_retry: float,
        bl_retry: float,
    ) -> None:
        self.retry_after = max(self.retry_after, lrclib_retry)
        self._betterlyrics_retry_after = max(self._betterlyrics_retry_after, bl_retry)
        if generation != self.generation:
            return
        if record is not None:
            if len(self.cache) >= 100:
                self.cache.pop(next(iter(self.cache)))
            self.cache[cache_key] = record
        self.finished.emit(record, status)
