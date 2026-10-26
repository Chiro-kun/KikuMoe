"""Station Manager for KikuMoe.

Orchestrates the active radio station metadata provider, sub-channel switching,
and stream URL resolution across LISTEN.moe, Gensokyo Radio, and ANISON.FM.
"""

from __future__ import annotations

import logging

from core.config import get_station_config, get_station_stream_url
from core.constants import DEFAULT_STATION, STATION_ANISON, STATION_GENSOKYO
from network.providers.anison_provider import AnisonProvider
from network.providers.base_provider import (
    BaseMetadataProvider,
    ErrorCallback,
    NowPlayingCallback,
    StatusCallback,
)
from network.providers.gensokyo_provider import GensokyoProvider
from network.providers.listenmoe_provider import ListenMoeProvider

logger = logging.getLogger("kikumoe.station_manager")


class StationManager:
    """Coordinates station metadata streaming and active stream endpoints."""

    def __init__(
        self,
        on_now_playing: NowPlayingCallback,
        on_error_text: ErrorCallback,
        on_status_text: StatusCallback | None = None,
        initial_station: str = DEFAULT_STATION,
        initial_channel: str = "J-POP",
    ) -> None:
        self.on_now_playing = on_now_playing
        self.on_error_text = on_error_text
        self.on_status_text = on_status_text

        self._current_station_id: str = (initial_station or DEFAULT_STATION).lower().strip()
        self._current_channel: str = (initial_channel or "J-POP").strip()
        self._active_provider: BaseMetadataProvider | None = None

    @property
    def current_station_id(self) -> str:
        return self._current_station_id

    @property
    def current_channel(self) -> str:
        return self._current_channel

    def get_station_info(self) -> dict:
        return get_station_config(self._current_station_id)

    def get_stream_url(self, fmt: str | None = None) -> str:
        """Returns the streaming audio URL for the currently selected station and format."""
        return get_station_stream_url(
            station_id=self._current_station_id,
            channel=self._current_channel,
            fmt=fmt,
        )

    def start(self) -> None:
        """Starts the metadata provider for the active station."""
        self._activate_provider()

    def stop(self) -> None:
        """Stops and cleans up the active metadata provider."""
        if self._active_provider:
            try:
                self._active_provider.stop()
            except Exception as e:
                logger.debug("Error stopping active provider: %s", e)
            self._active_provider = None

    def set_station(self, station_id: str) -> bool:
        """Switches to a different radio station.

        Returns True if the station changed, False if already active.
        """
        clean_id = (station_id or DEFAULT_STATION).lower().strip()
        if (
            clean_id == self._current_station_id
            and self._active_provider
            and self._active_provider.is_running
        ):
            return False

        logger.info("Switching station from '%s' to '%s'", self._current_station_id, clean_id)
        self.stop()
        self._current_station_id = clean_id
        self._activate_provider()
        return True

    def set_channel(self, channel: str) -> None:
        """Updates the active sub-channel (e.g. J-POP / K-POP for LISTEN.moe)."""
        self._current_channel = (channel or "J-POP").strip()
        if self._active_provider and hasattr(self._active_provider, "set_channel"):
            self._active_provider.set_channel(self._current_channel)

    def _activate_provider(self) -> None:
        station_id = self._current_station_id

        if station_id == STATION_GENSOKYO:
            self._active_provider = GensokyoProvider(
                on_now_playing=self.on_now_playing,
                on_error_text=self.on_error_text,
                on_status_text=self.on_status_text,
            )
        elif station_id == STATION_ANISON:
            self._active_provider = AnisonProvider(
                on_now_playing=self.on_now_playing,
                on_error_text=self.on_error_text,
                on_status_text=self.on_status_text,
            )
        else:
            # Default: LISTEN.moe
            self._active_provider = ListenMoeProvider(
                on_now_playing=self.on_now_playing,
                on_error_text=self.on_error_text,
                on_status_text=self.on_status_text,
                channel=self._current_channel,
            )

        try:
            self._active_provider.start()
        except Exception as e:
            logger.error("Failed to start provider for '%s': %s", station_id, e)
            self.on_error_text(f"Station {station_id} error: {e}")
