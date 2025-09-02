import vlc
from typing import Callable, Optional


class PlayerVLC:
    """
    Thin wrapper around python-vlc MediaPlayer that:
    - Encapsulates VLC instance/player creation
    - Exposes simple controls (play_url, stop, pause_toggle, set_volume, set_mute)
    - Maps VLC events to simple codes and forwards them to an on_event callback
    """

    def __init__(self, on_event: Optional[Callable[[str, Optional[int]], None]] = None):
        self._instance = vlc.Instance()
        self._player = self._instance.media_player_new()
        self._media = None
        self._on_event = on_event

        try:
            em = self._player.event_manager()
            em.event_attach(vlc.EventType.MediaPlayerOpening, self._handle_event)
            em.event_attach(vlc.EventType.MediaPlayerBuffering, self._handle_event)
            em.event_attach(vlc.EventType.MediaPlayerPlaying, self._handle_event)
            em.event_attach(vlc.EventType.MediaPlayerPaused, self._handle_event)
            em.event_attach(vlc.EventType.MediaPlayerStopped, self._handle_event)
            em.event_attach(vlc.EventType.MediaPlayerEndReached, self._handle_event)
            em.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._handle_event)
        except Exception:
            # Event hookup failure should not break basic playback
            pass

    # ------------- Controls -------------
    def play_url(self, url: str):
        try:
            self._media = self._instance.media_new(url)
            self._player.set_media(self._media)
            self._player.play()
        except Exception:
            if self._on_event:
                self._on_event('error', None)

    def stop(self):
        try:
            self._player.stop()
        except Exception:
            pass

    def pause_toggle(self):
        try:
            self._player.pause()
        except Exception:
            pass

    def set_volume(self, value: int):
        try:
            self._player.audio_set_volume(int(value))
        except Exception:
            pass

    def set_mute(self, mute: bool):
        try:
            self._player.audio_set_mute(bool(mute))
        except Exception:
            pass

    def is_playing(self) -> bool:
        try:
            st = self._player.get_state()
            return st in (vlc.State.Playing, vlc.State.Buffering, vlc.State.Opening)
        except Exception:
            return False

    # ------------- Event handling -------------
    def _handle_event(self, event):
        if not self._on_event:
            return
        et = event.type
        if et == vlc.EventType.MediaPlayerOpening:
            self._on_event('opening', None)
        elif et == vlc.EventType.MediaPlayerBuffering:
            pct = None
            try:
                pct = getattr(getattr(event, 'u', None), 'new_cache', None)
                if pct is not None:
                    pct = int(pct)
            except Exception:
                pct = None
            self._on_event('buffering', pct)
        elif et == vlc.EventType.MediaPlayerPlaying:
            self._on_event('playing', None)
        elif et == vlc.EventType.MediaPlayerPaused:
            self._on_event('paused', None)
        elif et == vlc.EventType.MediaPlayerStopped:
            self._on_event('stopped', None)
        elif et == vlc.EventType.MediaPlayerEndReached:
            self._on_event('ended', None)
        elif et == vlc.EventType.MediaPlayerEncounteredError:
            self._on_event('error', None)

    # ------------- Expose underlying when needed -------------
    @property
    def raw_player(self):
        return self._player