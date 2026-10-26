"""Base class for radio station metadata providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

# (title, artist, duration_seconds, start_epoch_ts, album_art_url)
NowPlayingCallback = Callable[[str, str, Optional[int], Optional[float], Optional[str]], None]
ErrorCallback = Callable[[str], None]
StatusCallback = Callable[[str], None]


class BaseMetadataProvider(ABC):
    """Abstract base class for streaming station metadata providers."""

    def __init__(
        self,
        station_id: str,
        on_now_playing: NowPlayingCallback,
        on_error_text: ErrorCallback,
        on_status_text: StatusCallback | None = None,
    ) -> None:
        self.station_id = station_id
        self.on_now_playing = on_now_playing
        self.on_error_text = on_error_text
        self.on_status_text = on_status_text
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    @abstractmethod
    def start(self) -> None:
        """Starts receiving or polling metadata for the station."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stops background threads/connections and releases resources."""
        pass

    def set_channel(self, channel: str) -> None:
        """Optionally switches sub-channels (e.g. J-POP / K-POP for LISTEN.moe)."""
        pass
