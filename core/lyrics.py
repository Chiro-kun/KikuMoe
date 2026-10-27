"""LRCLIB lookup and timestamped lyric parsing."""

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from urllib.parse import urlencode

from PyQt6.QtCore import QObject, pyqtSignal

from core.constants import APP_VERSION, URL_FORGEJO
from core.ssl_compat import get_ssl_context

_TIME = re.compile(r"\[(\d+):(\d{1,2}(?:\.\d+)?)\]")
logger = logging.getLogger("kikumoe.lyrics")


def parse_lrc(text):
    lines = []
    for line in (text or "").splitlines():
        matches = list(_TIME.finditer(line))
        if not matches:
            continue
        lyric = _TIME.sub("", line).strip()
        for match in matches:
            lines.append((int(match.group(1)) * 60 + float(match.group(2)), lyric))
    return sorted(lines, key=lambda item: item[0])


def _similarity(a, b):
    def normalize(value):
        return " ".join(re.findall(r"\w+", str(value or "").casefold()))

    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def select_match(records, title, artist, duration):
    best, best_score = None, 0.0
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
            difference = 0
        if duration and record.get("duration") and difference > 15:
            continue
        score = title_score + artist_score + (0.1 if record.get("syncedLyrics") else 0)
        if score > best_score:
            best, best_score = record, score
    return best


class LyricsProvider(QObject):
    """Perform sequential LRCLIB lookups off the UI thread, ignoring stale results."""

    finished = pyqtSignal(object, str)
    _result = pyqtSignal(int, object, object, str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.generation = 0
        self.cache = {}
        self.retry_after = 0.0
        self._lock = threading.Lock()
        self._pending = None
        self._worker = None
        self._last_request = 0.0
        self._result.connect(self._deliver)

    def cancel(self):
        self.generation += 1
        with self._lock:
            self._pending = None

    def search(self, title, artist, duration=0):
        self.cancel()
        title, artist = str(title or "").strip(), str(artist or "").strip()
        if not title or not artist or title in ("–", "-"):
            self.finished.emit(None, "missing")
            return
        key = (title, artist, int(duration or 0))
        if key in self.cache:
            self.finished.emit(self.cache[key], "ok")
            return
        if time.monotonic() < self.retry_after:
            self.finished.emit(None, "error")
            return
        params = {"track_name": title, "artist_name": artist}
        if 0 < (duration or 0) <= 3600:
            params["duration"] = int(duration)
        with self._lock:
            self._pending = (params, key, self.generation)
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="LyricsLookup", daemon=True)
                self._worker.start()

    def _request(self, endpoint, params):
        delay = 0.3 - (time.monotonic() - self._last_request)
        if delay > 0:
            time.sleep(delay)
        self._last_request = time.monotonic()
        url = "https://lrclib.net/api/" + endpoint + "?" + urlencode(params)
        request = urllib.request.Request(
            url, headers={"User-Agent": f"KikuMoe/{APP_VERSION} ({URL_FORGEJO})"}
        )
        with urllib.request.urlopen(request, timeout=8, context=get_ssl_context()) as response:
            return json.loads(response.read(2_000_000).decode("utf-8"))

    def _lookup(self, params, key, generation):
        try:
            try:
                data = self._request("get", params)
                record = data if isinstance(data, dict) else None
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
                try:
                    delay = max(1, int(exc.headers.get("Retry-After", "60")))
                except (TypeError, ValueError):
                    delay = 60
                logger.warning("LRCLIB returned HTTP %s; retry in %s seconds", exc.code, delay)
                return None, "error", time.monotonic() + delay
            logger.warning("LRCLIB request failed: HTTP %s", exc.code)
            return None, "error", 0.0
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            logger.warning("LRCLIB request failed: %s", exc)
            return None, "error", 0.0

    def _run(self):
        while True:
            with self._lock:
                job, self._pending = self._pending, None
                if job is None:
                    self._worker = None
                    return
            params, key, generation = job
            if time.monotonic() < self.retry_after:
                record, status, retry_after = None, "error", self.retry_after
            else:
                try:
                    record, status, retry_after = self._lookup(params, key, generation)
                except Exception:
                    logger.exception("Unexpected LRCLIB lookup error")
                    record, status, retry_after = None, "error", 0.0
            self.retry_after = max(self.retry_after, retry_after)
            try:
                self._result.emit(generation, key, record, status, retry_after)
            except RuntimeError:
                return

    def _deliver(self, generation, key, record, status, retry_after):
        self.retry_after = max(self.retry_after, retry_after)
        if generation != self.generation:
            return
        if record is not None:
            if len(self.cache) >= 100:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = record
        self.finished.emit(record, status)
