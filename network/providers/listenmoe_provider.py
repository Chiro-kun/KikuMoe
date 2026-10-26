"""LISTEN.moe WebSocket metadata provider."""

from __future__ import annotations

import logging

from network.providers.base_provider import (
    BaseMetadataProvider,
    ErrorCallback,
    NowPlayingCallback,
    StatusCallback,
)
from network.ws_client import NowPlayingWS

logger = logging.getLogger("kikumoe.providers.listenmoe")


class ListenMoeProvider(BaseMetadataProvider):
    """Metadata provider connecting to LISTEN.moe WebSocket gateway."""

    def __init__(
        self,
        on_now_playing: NowPlayingCallback,
        on_error_text: ErrorCallback,
        on_status_text: StatusCallback | None = None,
        channel: str = "J-POP",
    ) -> None:
        super().__init__(
            station_id="listenmoe",
            on_now_playing=on_now_playing,
            on_error_text=on_error_text,
            on_status_text=on_status_text,
        )
        self._current_channel: str = channel or "J-POP"
        self._ws: NowPlayingWS | None = None

    @staticmethod
    def get_ws_url_for_channel(channel: str) -> str:
        ch = (channel or "").strip().upper()
        if "K-POP" in ch:
            return "wss://listen.moe/kpop/gateway_v2"
        return "wss://listen.moe/gateway_v2"

    def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        self._connect_ws()

    def _connect_ws(self) -> None:
        try:
            self._ws = NowPlayingWS(
                on_now_playing=self.on_now_playing,
                on_error_text=self.on_error_text,
                on_closed_text=self.on_status_text or (lambda _: None),
                ws_url=self.get_ws_url_for_channel(self._current_channel),
            )
            self._ws.start()
        except Exception as e:
            logger.error("Failed to start LISTEN.moe WebSocket: %s", e)
            self.on_error_text(f"LISTEN.moe connection error: {e}")

    def stop(self) -> None:
        self._is_running = False
        if self._ws:
            try:
                self._ws.shutdown()
            except Exception as e:
                logger.debug("Error shutting down LISTEN.moe WS: %s", e)
            self._ws = None

    def set_channel(self, channel: str) -> None:
        new_ch = (channel or "J-POP").strip().upper()
        if new_ch == self._current_channel and self._is_running:
            return
        self._current_channel = new_ch
        if self._is_running:
            # Reconnect WS to new channel gateway
            if self._ws:
                try:
                    self._ws.shutdown()
                except Exception:
                    pass
                self._ws = None
            self._connect_ws()
