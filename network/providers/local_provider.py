"""Metadata provider for local music playback in KikuMoe.

Bridges the LocalPlaylistManager to the now-playing pipeline, generating
track metadata, temporary cover art assets, and timeline notifications.
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path

from core.constants import STATION_LOCAL
from core.local_metadata import LocalTrackInfo
from core.local_playlist import LocalPlaylistManager
from network.providers.base_provider import (
    BaseMetadataProvider,
    ErrorCallback,
    NowPlayingCallback,
    StatusCallback,
)

logger = logging.getLogger("kikumoe.local_provider")


class LocalProvider(BaseMetadataProvider):
    """Metadata provider driven by LocalPlaylistManager."""

    def __init__(
        self,
        on_now_playing: NowPlayingCallback,
        on_error_text: ErrorCallback,
        on_status_text: StatusCallback | None = None,
        playlist_manager: LocalPlaylistManager | None = None,
    ) -> None:
        super().__init__(
            station_id=STATION_LOCAL,
            on_now_playing=on_now_playing,
            on_error_text=on_error_text,
            on_status_text=on_status_text,
        )
        self.playlist_manager = playlist_manager
        self._cover_cache_file: Path | None = None

        if self.playlist_manager is not None:
            self.playlist_manager.track_changed.connect(self._on_track_changed)

    def start(self) -> None:
        self._is_running = True
        if self.on_status_text:
            self.on_status_text("Locale")
        if self.playlist_manager is not None:
            current = self.playlist_manager.get_current_track()
            if current:
                self._on_track_changed(current)

    def stop(self) -> None:
        self._is_running = False

    def _on_track_changed(self, track: LocalTrackInfo | None) -> None:
        if not self._is_running or track is None:
            return

        cover_path_str: str | None = None
        if track.cover_bytes:
            try:
                suffix = ".png" if track.cover_mime == "image/png" else ".jpg"
                if self._cover_cache_file is None:
                    tmp = tempfile.NamedTemporaryFile(
                        delete=False, suffix=suffix, prefix="kikumoe_cover_"
                    )
                    tmp.close()
                    self._cover_cache_file = Path(tmp.name)
                self._cover_cache_file.write_bytes(track.cover_bytes)
                cover_path_str = self._cover_cache_file.as_uri()
            except Exception as e:
                logger.debug("Failed caching local cover image: %s", e)

        self.on_now_playing(
            track.display_title(),
            track.display_artist(),
            int(track.duration_seconds) if track.duration_seconds > 0 else None,
            time.time(),
            cover_path_str,
        )
