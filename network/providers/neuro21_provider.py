"""Neuro 21 metadata polling provider."""

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

logger = logging.getLogger("kikumoe.providers.neuro21")

NEURO21_API_URL = "https://radio.twinskaraoke.com/api/nowplaying/neuro_21"


class Neuro21Provider(BaseMetadataProvider):
    """Metadata provider polling the Neuro 21 AzuraCast station API."""

    def __init__(
        self,
        on_now_playing: NowPlayingCallback,
        on_error_text: ErrorCallback,
        on_status_text: StatusCallback | None = None,
        poll_interval: float = 10.0,
    ) -> None:
        super().__init__(
            station_id="neuro21",
            on_now_playing=on_now_playing,
            on_error_text=on_error_text,
            on_status_text=on_status_text,
        )
        self.poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_song_id: Any | None = None
        self._last_track_sig: str | None = None

    def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_worker, name="Neuro21PollWorker", daemon=True
        )
        self._thread.start()
        logger.info("Started Neuro 21 metadata polling worker")

    def stop(self) -> None:
        self._is_running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=1.5)
            except Exception:
                pass
        self._thread = None
        logger.info("Stopped Neuro 21 metadata polling worker")

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
                NEURO21_API_URL,
                headers={"User-Agent": f"KikuMoe/{APP_VERSION} (Neuro 21 Client)"},
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            self._parse_and_emit(data)
        except Exception as e:
            logger.debug("Neuro 21 metadata fetch error: %s", e)
            if self.on_status_text:
                self.on_status_text(f"Neuro 21 API sync: {e}")

    def _parse_and_emit(self, data: dict[str, Any]) -> None:
        np = data.get("now_playing") or {}
        song = np.get("song") or {}

        title = str(song.get("title") or song.get("text") or "").strip()
        if not title:
            return

        artist = str(song.get("artist") or "Neuro 21").strip()
        if not artist:
            artist = "Neuro 21"

        duration = np.get("duration")
        duration_sec = int(duration) if duration is not None and int(duration) > 0 else 0

        # Calculate expected track end epoch
        end_ts: float | None = None
        played_at = np.get("played_at")
        if played_at is not None and duration_sec > 0:
            try:
                end_ts = float(played_at) + duration_sec
            except (ValueError, TypeError):
                end_ts = None

        if end_ts is None:
            remaining = np.get("remaining")
            if remaining is not None:
                try:
                    end_ts = time.time() + float(remaining)
                except (ValueError, TypeError):
                    end_ts = None

        art = str(song.get("art") or "").strip()
        art_url: str | None = art if art and art.startswith("http") else None

        # Deduplication against song ID and track signature
        song_id = song.get("id") or np.get("sh_id")
        track_sig = f"{artist} - {title}"
        track_changed = False

        if song_id is not None:
            if song_id != self._last_song_id:
                self._last_song_id = song_id
                self._last_track_sig = track_sig
                track_changed = True
        elif track_sig != self._last_track_sig:
            self._last_track_sig = track_sig
            track_changed = True

        if track_changed:
            logger.debug("Neuro 21 track changed: %s - %s (dur=%ss)", artist, title, duration_sec)
            self.on_now_playing(title, artist, duration_sec, end_ts, art_url)
