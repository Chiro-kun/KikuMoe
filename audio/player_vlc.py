from __future__ import annotations
from typing import Optional, Callable
import os
import sys

from core.constants import APP_NAME, APP_VERSION, ORG_NAME, APP_SETTINGS, KEY_AUDIO_DEVICE_INDEX
from core.logger import get_logger

_IS_WIN32 = sys.platform == "win32"

try:
    import vlc
except Exception:
    vlc = None  # type: ignore


class PlayerVLC:
    def __init__(self, libvlc_path: Optional[str] = None, on_event: Optional[Callable[[str, Optional[int]], None]] = None, network_caching_ms: Optional[int] = None) -> None:
        self._vlc_path = libvlc_path
        self._on_event = on_event
        self._network_caching_ms: Optional[int] = int(network_caching_ms) if network_caching_ms is not None else None
        self.instance: Optional['vlc.Instance'] = None
        self.player: Optional['vlc.MediaPlayer'] = None
        self._muted: bool = False
        self._volume: int = 100
        self._ready: bool = False
        self.log = get_logger('PlayerVLC')
        # Build dynamic User-Agent similar to ffmpeg backend
        try:
            self._user_agent = f"{APP_NAME}/{APP_VERSION}"
        except Exception:
            self._user_agent = "KikuMoe/1.9.0"
        self._init_vlc()

    def _init_vlc(self) -> None:
        self._ready = False
        if vlc is None:
            return
        # Setup plugin path if provided
        if self._vlc_path and os.path.isdir(self._vlc_path):
            try:
                if _IS_WIN32:
                    os.add_dll_directory(self._vlc_path)
                else:
                    plugins_path = os.path.join(self._vlc_path, "plugins")
                    if os.path.isdir(plugins_path):
                        os.environ["VLC_PLUGIN_PATH"] = plugins_path
            except Exception:
                pass
        try:
            # Build instance options (e.g., network caching)
            inst_opts = []
            if self._network_caching_ms is not None:
                try:
                    nc = max(0, int(self._network_caching_ms))
                    inst_opts.append(f"--network-caching={nc}")
                except Exception:
                    pass
            # Add options to reduce verbose output and improve stream handling
            inst_opts.extend([
                "--intf", "dummy",  # No interface
                "--quiet",  # Reduce output
                "--no-video-title-show",  # No video title
                "--no-stats",  # No statistics
                "--no-plugins-cache",  # No plugins cache
                "--http-reconnect",  # Reconnect on HTTP errors
                "--http-continuous",  # Continuous HTTP streaming
                "--live-caching=1000",  # Small live caching for smooth playback
            ])
            # On Linux, route audio through PulseAudio (covers PipeWire via pipewire-pulse).
            # This ensures VLC uses PipeWire when pipewire-pulse is active.
            if not _IS_WIN32:
                inst_opts.append("--aout=pulse")
            # Set HTTP User-Agent globally for VLC instance
            try:
                if getattr(self, "_user_agent", None):
                    inst_opts.append(f"--http-user-agent={self._user_agent}")
            except Exception:
                pass
            self.instance = vlc.Instance(inst_opts)
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
            # Apply explicit device selection (Linux/pulse only, best-effort)
            self._apply_linux_audio_device()
        except Exception:
            self.instance = None
            self.player = None
            self._ready = False

    def _get_stored_device_name(self) -> Optional[str]:
        """Return the human-readable PortAudio name of the user-configured output device,
        or None when the setting is absent or unresolvable."""
        try:
            from PyQt6.QtCore import QSettings
            settings = QSettings(ORG_NAME, APP_SETTINGS)
            val = settings.value(KEY_AUDIO_DEVICE_INDEX, '')
            if val in (None, ''):
                return None
            import pyaudio
            pa = pyaudio.PyAudio()
            try:
                info = pa.get_device_info_by_index(int(val))
                return str(info.get('name', '')) if isinstance(info, dict) else None
            finally:
                pa.terminate()
        except Exception:
            return None

    def _apply_linux_audio_device(self) -> None:
        """On Linux with --aout=pulse, enumerate VLC audio output devices and select
        the one whose description best matches the stored PortAudio device name."""
        if _IS_WIN32 or not self.is_ready():
            return
        device_name = self._get_stored_device_name()
        if not device_name:
            return
        try:
            assert self.player is not None
            devices = self.player.audio_output_device_enum()
            if not devices:
                return
            needle = device_name.lower()
            dev = devices
            while dev:
                try:
                    desc = dev.description
                    dev_id = dev.device
                    if isinstance(desc, bytes):
                        desc = desc.decode(errors='ignore')
                    if isinstance(dev_id, bytes):
                        dev_id = dev_id.decode(errors='ignore')
                    desc_lc = str(desc).lower()
                    if needle in desc_lc or desc_lc in needle:
                        self.player.audio_output_device_set(None, dev_id)
                        self.log.debug("[VLC] audio output device set to: %s (%s)", dev_id, desc)
                        return
                except Exception:
                    pass
                try:
                    dev = dev.next
                except Exception:
                    break
        except Exception as e:
            self.log.debug("[VLC] _apply_linux_audio_device error: %s", e)

    def is_ready(self) -> bool:
        return bool(self._ready and self.instance is not None and self.player is not None)

    def reinitialize(self, libvlc_path: Optional[str], network_caching_ms: Optional[int] = None) -> bool:
        self._vlc_path = libvlc_path
        if network_caching_ms is not None:
            try:
                self._network_caching_ms = int(network_caching_ms)
            except Exception:
                pass
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
            # Force stop current stream
            self.player.stop()
            # Clear media to force connection close
            self.player.set_media(None)
            # Wait for cleanup
            import time
            time.sleep(0.3)
            # Create and set new media
            media = self.instance.media_new(url)
            # Also set per-media user agent to be extra sure
            try:
                if getattr(self, "_user_agent", None):
                    media.add_option(f":http-user-agent={self._user_agent}")
            except Exception:
                pass
            self.player.set_media(media)
            self._apply_linux_audio_device()
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
            # Stop and clear media
            self.player.stop()
            self.player.set_media(None)
            # Force cleanup of any remaining connections
            self.force_kill_all_vlc()
            self._emit('stopped', None)
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

    # -------- Dettagli/diagnostica VLC --------
    def get_version(self) -> Optional[str]:
        """Return libVLC version string if available, otherwise None."""
        if vlc is None:
            return None
        try:
            ver = vlc.libvlc_get_version()  # type: ignore[attr-defined]
            if isinstance(ver, bytes):
                ver = ver.decode(errors='ignore')
            return str(ver)
        except Exception:
            return None

    def get_configured_path(self) -> Optional[str]:
        """Return configured libvlc path (folder) or None if using system/PATH."""
        return self._vlc_path

    def force_kill_all_vlc(self) -> None:
        """Force kill all VLC processes as last resort."""
        try:
            import subprocess
            if _IS_WIN32:
                subprocess.run(["taskkill", "/f", "/im", "vlc.exe"],
                               capture_output=True, check=False,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                subprocess.run(["taskkill", "/f", "/im", "libvlc.dll"],
                               capture_output=True, check=False,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.run(["pkill", "-f", "vlc"], capture_output=True, check=False)
                subprocess.run(["pkill", "-f", "libvlc"], capture_output=True, check=False)
        except Exception:
            pass

    def force_cleanup(self) -> None:
        """Force cleanup of current media and connections."""
        if not self.is_ready():
            return
        try:
            # Force cleanup
            assert self.player is not None
            self.player.stop()
            self.player.set_media(None)
            import time
            time.sleep(0.2)
            # Force kill any remaining VLC processes
            self.force_kill_all_vlc()
        except Exception:
            pass

    def _force_complete_cleanup(self) -> None:
        """Force complete cleanup by recreating VLC instance."""
        try:
            # Save current volume and mute state
            current_volume = self._volume
            current_mute = self._muted
            
            # Stop and release current player
            if self.player:
                try:
                    self.player.stop()
                    self.player.set_media(None)
                except Exception:
                    pass
            
            # Release the instance completely
            if self.instance:
                try:
                    self.instance.release()
                except Exception:
                    pass
            
            # Clear references
            self.player = None
            self.instance = None
            self._ready = False
            
            # Wait longer for complete cleanup
            import time
            time.sleep(0.5)
            
            # Reinitialize VLC
            self._init_vlc()
            
            # Restore volume and mute state
            if self.is_ready():
                self.set_volume(current_volume)
                self.set_mute(current_mute)
        except Exception:
            pass
