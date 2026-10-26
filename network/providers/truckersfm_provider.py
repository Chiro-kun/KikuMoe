"""TruckersFM metadata polling provider."""

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

logger = logging.getLogger("kikumoe.providers.truckersfm")

TRUCKERSFM_API_URL = "https://truckers.fm/api/radiocloud/song/current"
TRUCKERSFM_ICECAST_URL = "https://live.truckers.fm/status-json.xsl"


class TruckersFMProvider(BaseMetadataProvider):
    """Metadata provider polling TruckersFM's RadioCloud API with Icecast fallback."""

    def __init__(
        self,
        on_now_playing: NowPlayingCallback,
        on_error_text: ErrorCallback,
        on_status_text: StatusCallback | None = None,
        poll_interval: float = 10.0,
    ) -> None:
        super().__init__(
            station_id="truckersfm",
            on_now_playing=on_now_playing,
            on_error_text=on_error_text,
            on_status_text=on_status_text,
        )
        self.poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_playback_id: Any | None = None
        self._last_track_sig: str | None = None

    def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_worker, name="TruckersFMPollWorker", daemon=True
        )
        self._thread.start()
        logger.info("Started TruckersFM metadata polling worker")

    def stop(self) -> None:
        self._is_running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=1.5)
            except Exception:
                pass
        self._thread = None
        logger.info("Stopped TruckersFM metadata polling worker")

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

        headers = {"User-Agent": f"KikuMoe/{APP_VERSION} (TruckersFM Radio Client)"}

        # 1. Primary: RadioCloud REST API (rich metadata + album art)
        try:
            req = urllib.request.Request(TRUCKERSFM_API_URL, headers=headers)
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if self._parse_and_emit_radiocloud(data):
                return
        except Exception as e:
            logger.debug("TruckersFM primary API failed, falling back to Icecast: %s", e)

        if self._stop_event.is_set():
            return

        # 2. Fallback: Native Icecast JSON status endpoint
        try:
            req_ice = urllib.request.Request(TRUCKERSFM_ICECAST_URL, headers=headers)
            with urllib.request.urlopen(req_ice, timeout=6.0) as resp:
                ice_data = json.loads(resp.read().decode("utf-8"))
            self._parse_and_emit_icecast(ice_data)
        except Exception as e:
            logger.debug("TruckersFM Icecast fallback failed: %s", e)
            if self.on_status_text:
                self.on_status_text(f"TruckersFM API sync: {e}")

    def _parse_and_emit_radiocloud(self, data: dict[str, Any]) -> bool:
        if str(data.get("status")).lower() != "success":
            return False

        song_data = data.get("data")
        if not isinstance(song_data, dict):
            return False

        title = str(song_data.get("title") or "").strip()
        if not title:
            return False

        artist = str(song_data.get("artist") or "TruckersFM").strip()
        if not artist:
            artist = "TruckersFM"

        art = str(song_data.get("album_art") or "").strip()
        art_url: str | None = art if art and art.startswith("http") else None

        playback_id = song_data.get("playback_id") or song_data.get("id")
        played_at = song_data.get("played_at")

        start_ts: float | None = None
        if played_at is not None:
            try:
                start_ts = float(played_at)
            except (ValueError, TypeError):
                start_ts = None
        if start_ts is None:
            start_ts = time.time()

        track_sig = f"{artist} - {title}"
        track_changed = False

        if playback_id is not None:
            if playback_id != self._last_playback_id:
                self._last_playback_id = playback_id
                self._last_track_sig = track_sig
                track_changed = True
        elif track_sig != self._last_track_sig:
            self._last_track_sig = track_sig
            track_changed = True

        if track_changed:
            logger.debug("TruckersFM track changed (radiocloud): %s - %s", artist, title)
            # Duration is 0 for live continuous streams (triggers live counter in KikuMoe)
            self.on_now_playing(title, artist, 0, start_ts, art_url)

        return True

    def _parse_and_emit_icecast(self, data: dict[str, Any]) -> bool:
        icestats = data.get("icestats") or {}
        source_field = icestats.get("source")

        sources: list[dict[str, Any]] = []
        if isinstance(source_field, list):
            sources = [s for s in source_field if isinstance(s, dict)]
        elif isinstance(source_field, dict):
            sources = [source_field]

        if not sources:
            return False

        # Prefer '/radio' (main 320k stream) or first stream with non-empty title
        selected: dict[str, Any] | None = None
        for s in sources:
            if str(s.get("mount", "")).strip() == "/radio" and s.get("title"):
                selected = s
                break

        if selected is None:
            for s in sources:
                if str(s.get("title", "")).strip():
                    selected = s
                    break

        if selected is None:
            return False

        raw_title = str(selected.get("title") or "").strip()
        if not raw_title:
            return False

        # Icecast format is typically "Artist - Title"
        if " - " in raw_title:
            parts = raw_title.split(" - ", 1)
            artist = parts[0].strip() or "TruckersFM"
            title = parts[1].strip() or raw_title
        else:
            artist = "TruckersFM"
            title = raw_title

        start_ts = time.time()
        track_sig = f"{artist} - {title}"

        if track_sig != self._last_track_sig:
            self._last_track_sig = track_sig
            logger.debug("TruckersFM track changed (icecast): %s - %s", artist, title)
            self.on_now_playing(title, artist, 0, start_ts, None)

        return True
