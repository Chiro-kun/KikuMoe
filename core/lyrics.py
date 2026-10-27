"""LRCLIB lookup and timestamped lyric parsing."""

import json
import re
from difflib import SequenceMatcher
from urllib.parse import urlencode

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from core.constants import APP_VERSION, URL_FORGEJO

_TIME = re.compile(r"\[(\d+):(\d{1,2}(?:\.\d+)?)\]")


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
    """Single in-flight, cancellable LRCLIB lookup; results always delivered on Qt's thread."""

    finished = pyqtSignal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.reply = None
        self.generation = 0
        self.cache = {}
        self.retry_after = 0.0

    def cancel(self):
        self.generation += 1
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.abort()

    def search(self, title, artist, duration=0):
        import time

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
        self._request("get", params, key, self.generation)

    def _request(self, endpoint, params, key, generation):
        url = "https://lrclib.net/api/" + endpoint + "?" + urlencode(params)
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", f"KikuMoe/{APP_VERSION} ({URL_FORGEJO})".encode())
        request.setTransferTimeout(8000)
        reply = self.manager.get(request)
        self.reply = reply
        reply.finished.connect(lambda: self._completed(reply, endpoint, key, generation))

    def _completed(self, reply, endpoint, key, generation):
        import time

        if self.reply is reply:
            self.reply = None
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        body = bytes(reply.readAll())
        error = reply.error()
        retry = bytes(reply.rawHeader(b"Retry-After"))
        reply.deleteLater()
        if generation != self.generation:
            return
        if status in (429, 503):
            try:
                self.retry_after = time.monotonic() + max(1, int(retry))
            except ValueError:
                self.retry_after = time.monotonic() + 60
            self.finished.emit(None, "error")
            return
        if endpoint == "get" and status == 404:
            params = {"track_name": key[0], "artist_name": key[1]}
            QTimer.singleShot(300, lambda: self._fallback(params, key, generation))
            return
        if error != QNetworkReply.NetworkError.NoError or status != 200:
            self.finished.emit(None, "error")
            return
        try:
            data = json.loads(body.decode("utf-8"))
            record = data if endpoint == "get" and isinstance(data, dict) else None
            if endpoint == "search" and isinstance(data, list):
                record = select_match(data, *key)
        except (ValueError, UnicodeDecodeError):
            self.finished.emit(None, "error")
            return
        if record is not None:
            if len(self.cache) >= 100:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = record
        self.finished.emit(record, "ok" if record else "missing")

    def _fallback(self, params, key, generation):
        if generation == self.generation:
            self._request("search", params, key, generation)
