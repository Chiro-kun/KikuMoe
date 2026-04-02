from __future__ import annotations

import locale
import sys
from typing import Any, Callable

from core.constants import APP_NAME, APP_VERSION
from core.logger import get_logger

_IS_WIN32 = sys.platform == "win32"

# MPV end-file reason integers (MPV_END_FILE_REASON_*)
_MPV_END_STOP = 2
_MPV_END_QUIT = 3
_MPV_END_ERROR = 4

try:
    import mpv
except Exception:
    mpv = None  # type: ignore


class PlayerMPV:
    def __init__(self, on_event: Callable[[str, int | None], None] | None = None) -> None:
        self._on_event = on_event
        self._muted: bool = False
        self._volume: int = 100
        self._ready: bool = False
        self._player: Any | None = None
        # Set when stop()/force_cleanup() is called so the end-file callback
        # doesn't mis-classify the resulting event as a natural 'ended'.
        self._stopping: bool = False
        self.log = get_logger("PlayerMPV")
        try:
            self._user_agent = f"{APP_NAME}/{APP_VERSION}"
        except Exception:
            self._user_agent = "KikuMoe/1.9.0"
        self._init_mpv()

    def _init_mpv(self) -> None:
        self._ready = False
        if mpv is None:
            return
        try:
            # libmpv requires LC_NUMERIC="C"; set it before creating the instance
            # to avoid the "Non-C locale detected" warning and segfault.
            locale.setlocale(locale.LC_NUMERIC, "C")
        except Exception:
            pass
        try:
            self._player = mpv.MPV(
                vid="no",
                terminal=False,
                quiet=True,
                user_agent=self._user_agent,
            )
            self._player.volume = float(self._volume)
            self._player.mute = self._muted

            @self._player.event_callback("start-file")
            def _on_start(event):
                self._stopping = False
                self._emit("opening", None)

            @self._player.event_callback("file-loaded")
            def _on_loaded(event):
                self._emit("playing", None)

            @self._player.event_callback("end-file")
            def _on_end(event):
                # If stop()/force_cleanup() set the flag, absorb this event —
                # 'stopped' was already emitted by the calling method.
                if self._stopping:
                    self._stopping = False
                    return

                # Determine reason: event.reason is an int in libmpv
                # (MPV_END_FILE_REASON_STOP=2, QUIT=3, ERROR=4, EOF=0/1).
                # Guard against string/enum forms in future python-mpv versions.
                reason = getattr(event, "reason", None)
                try:
                    reason_int = int(reason)
                except Exception:
                    reason_int = -1
                reason_str = str(reason).lower()

                if (
                    reason_int in (_MPV_END_STOP, _MPV_END_QUIT)
                    or "stop" in reason_str
                    or "quit" in reason_str
                ):
                    self._emit("stopped", None)
                elif reason_int == _MPV_END_ERROR or "error" in reason_str:
                    self._emit("error", None)
                else:
                    self._emit("ended", None)

            @self._player.property_observer("cache-buffering-state")
            def _on_cache(name, value):
                if value is not None:
                    try:
                        self._emit("buffering", int(value))
                    except Exception:
                        pass

            self._ready = True
        except Exception as e:
            self.log.debug("[DEBUG] PlayerMPV: init failed: %s", e)
            self._player = None
            self._ready = False

    def is_ready(self) -> bool:
        return bool(self._ready and self._player is not None)

    def reinitialize(
        self, libvlc_path: str | None = None, network_caching_ms: int | None = None
    ) -> bool:
        return self.is_ready()

    def _emit(self, code: str, value: int | None = None) -> None:
        if self._on_event:
            try:
                self._on_event(code, value)
            except Exception:
                pass

    def play_url(self, url: str) -> bool:
        if not self.is_ready():
            self._emit("error", None)
            return False
        try:
            assert self._player is not None
            self._stopping = False
            self._player.play(url)
            return True
        except Exception:
            self._emit("error", None)
            return False

    def stop(self) -> None:
        if not self.is_ready():
            return
        assert self._player is not None
        # Only set the flag when there's actually something playing/paused;
        # if MPV is already idle no end-file event will fire and the flag
        # would linger, suppressing the next natural 'ended'.
        try:
            idle = bool(getattr(self._player, "idle_active", True))
            self._stopping = not idle
        except Exception:
            self._stopping = False
        try:
            self._player.stop()
        except Exception:
            self._stopping = False
        self._emit("stopped", None)

    def pause_toggle(self) -> None:
        if not self.is_ready():
            return
        try:
            assert self._player is not None
            self._player.pause = not bool(self._player.pause)
            if self._player.pause:
                self._emit("paused", None)
            else:
                self._emit("playing", None)
        except Exception:
            self._emit("error", None)

    def set_volume(self, vol: int) -> None:
        self._volume = max(0, min(100, int(vol)))
        if not self.is_ready():
            return
        try:
            assert self._player is not None
            self._player.volume = float(self._volume)
        except Exception:
            pass

    def set_mute(self, mute: bool) -> None:
        self._muted = bool(mute)
        if not self.is_ready():
            return
        try:
            assert self._player is not None
            self._player.mute = self._muted
        except Exception:
            pass

    def get_volume(self) -> int:
        return self._volume

    def get_mute(self) -> bool:
        return self._muted

    def is_playing(self) -> bool:
        if not self.is_ready():
            return False
        try:
            assert self._player is not None
            idle = bool(getattr(self._player, "idle_active", True))
            paused = bool(getattr(self._player, "pause", True))
            return not idle and not paused
        except Exception:
            return False

    def is_paused(self) -> bool:
        if not self.is_ready():
            return False
        try:
            assert self._player is not None
            idle = bool(getattr(self._player, "idle_active", True))
            paused = bool(getattr(self._player, "pause", False))
            return not idle and paused
        except Exception:
            return False

    def get_version(self) -> str | None:
        if mpv is None or not self.is_ready():
            return None
        try:
            assert self._player is not None
            ver = self._player.mpv_version
            return str(ver) if ver else None
        except Exception:
            return None

    def get_configured_path(self) -> str | None:
        return None

    def force_cleanup(self) -> None:
        if not self.is_ready():
            return
        assert self._player is not None
        try:
            idle = bool(getattr(self._player, "idle_active", True))
            self._stopping = not idle
        except Exception:
            self._stopping = False
        try:
            self._player.stop()
        except Exception:
            self._stopping = False
