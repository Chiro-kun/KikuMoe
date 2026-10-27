"""ANISON.FM metadata polling provider."""

from __future__ import annotations

import html
import json
import logging
import re
import threading
import time
import urllib.request
from typing import Any

from core.constants import APP_VERSION
from network.providers.base_provider import (
    DEFAULT_POLL_INTERVAL,
    BaseMetadataProvider,
    ErrorCallback,
    NowPlayingCallback,
    StatusCallback,
)

logger = logging.getLogger("kikumoe.providers.anison")

ANISON_STATUS_URL = "https://anison.fm/status.php?widget=true&layer=1"
ANISON_POSTER_BASE = "https://anison.fm/resources/poster/300/"


class AnisonProvider(BaseMetadataProvider):
    """Metadata provider polling the ANISON.FM status endpoint."""

    def __init__(
        self,
        on_now_playing: NowPlayingCallback,
        on_error_text: ErrorCallback,
        on_status_text: StatusCallback | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        super().__init__(
            station_id="anison",
            on_now_playing=on_now_playing,
            on_error_text=on_error_text,
            on_status_text=on_status_text,
        )
        self.poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_track_signature: str | None = None

    def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_worker, name="AnisonPollWorker", daemon=True
        )
        self._thread.start()
        logger.info("Started ANISON.FM metadata polling worker")

    def stop(self) -> None:
        self._is_running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=1.5)
            except Exception:
                pass
        self._thread = None
        logger.info("Stopped ANISON.FM metadata polling worker")

    def _poll_worker(self) -> None:
        # Immediate first fetch on startup
        self._fetch_and_dispatch()

        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self.poll_interval):
                break
            self._fetch_and_dispatch()

    def _fetch_and_dispatch(self) -> None:
        if self._stop_event.is_set():
            return
        try:
            req = urllib.request.Request(
                ANISON_STATUS_URL,
                headers={"User-Agent": f"KikuMoe/{APP_VERSION} (Anime Radio Client)"},
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            self._parse_and_emit(data)
        except Exception as e:
            logger.debug("ANISON.FM metadata fetch error: %s", e)
            if self.on_status_text:
                self.on_status_text(f"ANISON.FM API sync: {e}")

    def _parse_and_emit(self, data: dict[str, Any]) -> None:
        raw_on_air = data.get("on_air") or ""
        if not raw_on_air:
            return

        # 1. Check for anime catalog ID in hyperlink for poster cover
        art_url: str | None = None
        catalog_match = re.search(r"catalog/(\d+)", raw_on_air)
        if catalog_match:
            cat_id = catalog_match.group(1)
            art_url = f"{ANISON_POSTER_BASE}{cat_id}.jpg"

        # 2. Clean HTML and entity decodes
        unescaped = html.unescape(raw_on_air)
        # Replace HTML entities or dashes
        unescaped = unescaped.replace("&#151;", "—").replace("&mdash;", "—")
        clean_text = re.sub(r"<[^>]+>", "", unescaped)
        # Strip common prefixes like 'В эфире:' or 'On air:'
        clean_text = re.sub(
            r"^(В\s*эфире|On\s*air)\s*:\s*", "", clean_text, flags=re.IGNORECASE
        ).strip()

        # 3. Parse Artist/Anime and Track Title
        # Delimiters: em-dash (—), en-dash (–), or spaced hyphen ( - )
        delimiters = [" — ", " – ", " - ", "—", "–"]
        artist = "ANISON.FM"
        title = clean_text

        for delim in delimiters:
            if delim in clean_text:
                parts = clean_text.split(delim, 1)
                artist = parts[0].strip() or "ANISON.FM"
                title = parts[1].strip() or clean_text
                break

        # 4. Parse durations & expected end epoch
        # "full_duration": total track seconds
        # "duration": remaining seconds
        full_dur = data.get("full_duration")
        rem_dur = data.get("duration")

        duration_sec = 0
        if full_dur is not None:
            try:
                duration_sec = int(full_dur)
            except (ValueError, TypeError):
                duration_sec = 0

        end_ts: float | None = None
        if duration_sec > 0:
            if rem_dur is not None:
                try:
                    rem_sec = int(rem_dur)
                    end_ts = time.time() + rem_sec
                except (ValueError, TypeError):
                    end_ts = None
            if end_ts is None:
                end_ts = time.time() + duration_sec

        track_sig = f"{artist} - {title}"
        if track_sig != self._last_track_signature:
            self._last_track_signature = track_sig
            logger.debug("ANISON.FM track changed: %s (dur=%ss)", track_sig, duration_sec)
            self.on_now_playing(title, artist, duration_sec, end_ts, art_url)
