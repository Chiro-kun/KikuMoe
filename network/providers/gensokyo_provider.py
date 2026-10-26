"""Gensokyo Radio metadata polling provider."""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from typing import Any

from core.constants import APP_VERSION
from network.providers.base_provider import (
    BaseMetadataProvider,
    ErrorCallback,
    NowPlayingCallback,
    StatusCallback,
)

logger = logging.getLogger("kikumoe.providers.gensokyo")

GENSOKYO_API_URL = "https://gensokyoradio.net/api/station/playing/"
GENSOKYO_CDN_ART_BASE = "https://cdn.gensokyoradio.net/images/albums/500/"


class GensokyoProvider(BaseMetadataProvider):
    """Metadata provider polling the Gensokyo Radio JSON station API."""

    def __init__(
        self,
        on_now_playing: NowPlayingCallback,
        on_error_text: ErrorCallback,
        on_status_text: StatusCallback | None = None,
        poll_interval: float = 10.0,
    ) -> None:
        super().__init__(
            station_id="gensokyo",
            on_now_playing=on_now_playing,
            on_error_text=on_error_text,
            on_status_text=on_status_text,
        )
        self.poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_song_id: Any | None = None

    def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_worker, name="GensokyoPollWorker", daemon=True
        )
        self._thread.start()
        logger.info("Started Gensokyo Radio metadata polling worker")

    def stop(self) -> None:
        self._is_running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=1.5)
            except Exception:
                pass
        self._thread = None
        logger.info("Stopped Gensokyo Radio metadata polling worker")

    def _poll_worker(self) -> None:
        # Immediate first fetch on startup
        self._fetch_and_dispatch()

        while not self._stop_event.is_set():
            # Wait for next poll interval or stop signal
            if self._stop_event.wait(timeout=self.poll_interval):
                break
            self._fetch_and_dispatch()

    def _fetch_and_dispatch(self) -> None:
        if self._stop_event.is_set():
            return
        try:
            req = urllib.request.Request(
                GENSOKYO_API_URL,
                headers={"User-Agent": f"KikuMoe/{APP_VERSION} (Touhou Music Client)"},
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            self._parse_and_emit(data)
        except Exception as e:
            logger.debug("Gensokyo metadata fetch error: %s", e)
            if self.on_status_text:
                self.on_status_text(f"Gensokyo API sync: {e}")

    def _parse_and_emit(self, data: dict[str, Any]) -> None:
        song_info = data.get("SONGINFO", {})
        song_times = data.get("SONGTIMES", {})
        song_data = data.get("SONGDATA", {})
        misc = data.get("MISC", {})

        song_id = song_data.get("SONGID")
        title = (song_info.get("TITLE") or "").strip()
        if not title:
            return

        artist = (song_info.get("ARTIST") or "").strip()
        circle = (song_info.get("CIRCLE") or "").strip()
        if circle and artist and circle != artist:
            display_artist = f"{circle} · {artist}"
        else:
            display_artist = circle or artist or "Touhou Project"

        duration = song_times.get("DURATION")
        duration_sec = int(duration) if duration is not None and int(duration) > 0 else 0

        song_start = song_times.get("SONGSTART")
        start_ts: float | None = None
        if song_start is not None:
            try:
                start_ts = float(song_start)
            except (ValueError, TypeError):
                start_ts = None

        if start_ts is None:
            played = song_times.get("PLAYED", 0)
            start_ts = time.time() - float(played or 0)

        art_file = (misc.get("ALBUMART") or "").strip()
        if art_file:
            art_url: str | None = f"{GENSOKYO_CDN_ART_BASE}{art_file}"
        else:
            art_url = None

        # Check if song changed or first update
        if song_id != self._last_song_id:
            self._last_song_id = song_id
            logger.debug(
                "Gensokyo track changed: %s - %s (dur=%ss)", display_artist, title, duration_sec
            )

        self.on_now_playing(title, display_artist, duration_sec, start_ts, art_url)
