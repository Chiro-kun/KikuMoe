from __future__ import annotations
from typing import Optional, Callable
import os

try:
    import vlc
except Exception:
    vlc = None  # type: ignore


class PlayerVLC:
    def __init__(self, libvlc_path: Optional[str] = None, on_event: Optional[Callable[[str, Optional[int]], None]] = None) -> None:
        self._vlc_path = libvlc_path
        self._on_event = on_event
        self.instance: Optional['vlc.Instance'] = None
        self.player: Optional['vlc.MediaPlayer'] = None
        self._muted: bool = False
        self._volume: int = 100
        self._ready: bool = False
        self._init_vlc()

    def _init_vlc(self) -> None:
        self._ready = False
        if vlc is None:
            return
        # Setup plugin path if provided
        if self._vlc_path and os.path.isdir(self._vlc_path):
            try:
                os.add_dll_directory(self._vlc_path)
            except Exception:
                pass
        try:
            self.instance = vlc.Instance()
            self.player = self.instance.media_player_new()
            # Hook events for UI feedback
            try:
                em = self.player.event_manager()
                em.event_attach(vlc.EventType.MediaPlayerOpening, self._handle_event)
                em.event_attach(vlc.EventType.MediaPlayerBuffering, self._handle_event)
                em.event_attach(vlc.EventType.MediaPlayerPlaying, self._handle_event)
                em.event_attach(vlc.EventType.MediaPlayerPaused, self._handle_event)
                em.event_attach(vlc.EventType.MediaPlayerStopped, self._handle_event)
                em.event_attach(vlc.EventType.MediaPlayerEndReached, self._handle_event)
                em.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._handle_event)
            except Exception:
                pass
            # Apply last known audio state
            self.player.audio_set_volume(self._volume)
            self.player.audio_set_mute(self._muted)
            self._ready = True
        except Exception:
            self.instance = None
            self.player = None
            self._ready = False

    def is_ready(self) -> bool:
        return bool(self._ready and self.instance is not None and self.player is not None)

    def reinitialize(self, libvlc_path: Optional[str]) -> bool:
        self._vlc_path = libvlc_path
        self._init_vlc()
        return self.is_ready()

    def _emit(self, code: str, value: Optional[int] = None) -> None:
        if self._on_event:
            try:
                self._on_event(code, value)
            except Exception:
                pass

    def play_url(self, url: str) -> bool:
        if not self.is_ready():
            # Keep backward compatibility with UI error handling
            self._emit('libvlc_init_failed', None)
            # Also emit as generic error with code for older handlers, if any
            self._emit('error', None)
            return False
        try:
            assert self.instance is not None and self.player is not None
            media = self.instance.media_new(url)
            self.player.set_media(media)
            self.player.play()
            return True
        except Exception:
            self._emit('error', None)
            return False

    def stop(self) -> None:
        if not self.is_ready():
            self._emit('libvlc_init_failed', None)
            return
        try:
            assert self.player is not None
            self.player.stop()
        except Exception:
            self._emit('error', None)

    def pause_toggle(self) -> None:
        if not self.is_ready():
            self._emit('libvlc_init_failed', None)
            return
        try:
            assert self.player is not None
            self.player.pause()
        except Exception:
            self._emit('error', None)

    def set_volume(self, vol: int) -> None:
        self._volume = max(0, min(100, int(vol)))
        if not self.is_ready():
            return
        try:
            assert self.player is not None
            self.player.audio_set_volume(self._volume)
        except Exception:
            self._emit('error', None)

    def set_mute(self, mute: bool) -> None:
        self._muted = bool(mute)
        if not self.is_ready():
            return
        try:
            assert self.player is not None
            self.player.audio_set_mute(self._muted)
        except Exception:
            self._emit('error', None)

    def get_volume(self) -> int:
        return self._volume

    def get_mute(self) -> bool:
        return self._muted

    def is_playing(self) -> bool:
        if not self.is_ready():
            return False
        try:
            st = self.player.get_state()
            return st in (vlc.State.Playing, vlc.State.Buffering, vlc.State.Opening)
        except Exception:
            return False

    # VLC event handler
    def _handle_event(self, event):
        if vlc is None:
            return
        et = event.type
        if et == vlc.EventType.MediaPlayerOpening:
            self._emit('opening', None)
        elif et == vlc.EventType.MediaPlayerBuffering:
            # Try to extract percentage
            pct = None
            try:
                pct = int(getattr(getattr(event, 'u', None), 'new_cache', 0))
            except Exception:
                pct = None
            self._emit('buffering', pct)
        elif et == vlc.EventType.MediaPlayerPlaying:
            self._emit('playing', None)
        elif et == vlc.EventType.MediaPlayerPaused:
            self._emit('paused', None)
        elif et == vlc.EventType.MediaPlayerStopped:
            self._emit('stopped', None)
        elif et == vlc.EventType.MediaPlayerEndReached:
            self._emit('ended', None)
        elif et == vlc.EventType.MediaPlayerEncounteredError:
            self._emit('error', None)