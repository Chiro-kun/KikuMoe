"""Windows System Media Transport Controls and media-key fallback."""

import ctypes
import ctypes.wintypes
from typing import Any, Optional, Tuple

from PyQt6.QtCore import QAbstractNativeEventFilter, QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.media_state import MediaState


class MediaKeyFilter(QAbstractNativeEventFilter):
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge

    def nativeEventFilter(self, eventType: Any, message: Any) -> Tuple[bool, Any]:
        if self.bridge.controls is not None or eventType not in (
            b"windows_generic_MSG",
            b"windows_dispatcher_MSG",
        ):
            return False, 0
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message != 0x0319:  # WM_APPCOMMAND
                return False, 0
            command = (int(msg.lParam) >> 16) & 0x0FFF
            action = {
                8: "mute",
                9: "volume_down",
                10: "volume_up",
                13: "stop",
                14: "toggle",
                46: "play",
                47: "pause",
            }.get(command)
            if action:
                self.bridge.command.emit(action)
                return True, 1
        except (ValueError, TypeError, OSError):
            pass
        return False, 0


class WindowsMediaBridge(QObject):
    command = pyqtSignal(str)

    def __init__(self, logger, parent=None):
        super().__init__(parent)
        self.log = logger
        self.controls: Any = None
        self._handle: Any = None
        self._token: Any = None
        self._last_state: Optional[MediaState] = None
        self._modules: Optional[Tuple[Any, Any, Any, Any]] = None
        self._filter = MediaKeyFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)
        try:
            import winrt.windows.foundation as foundation
            import winrt.windows.media as media
            import winrt.windows.media.interop as interop
            import winrt.windows.storage.streams as streams

            self._modules = (foundation, media, interop, streams)
        except (ImportError, OSError) as exc:
            self.log.info("[SMTC] Unavailable; using media-key fallback: %s", exc)

    def bind(self, hwnd):
        if self._modules is None or (self.controls is not None and self._handle == hwnd):
            return
        self._release_controls()
        foundation, media, interop, streams = self._modules
        controls = None
        try:
            controls = interop.get_for_window(int(hwnd))
            controls.is_play_enabled = True
            controls.is_pause_enabled = True
            controls.is_stop_enabled = True
            controls.is_next_enabled = False
            controls.is_previous_enabled = False
            controls.is_enabled = True
            self._token = controls.add_button_pressed(self._on_button)
            self.controls = controls
            self._handle = hwnd
            self._last_state = None
            self.log.info("[SMTC] System media controls connected")
        except Exception as exc:
            if controls is not None:
                try:
                    controls.is_enabled = False
                except Exception:
                    pass
            self.log.debug("[SMTC] Could not initialize; media-key fallback active: %s", exc)

    def _on_button(self, sender, args):
        if self._modules is None or self.controls is None:
            return
        media = self._modules[1]
        actions = {
            media.SystemMediaTransportControlsButton.PLAY: "play",
            media.SystemMediaTransportControlsButton.PAUSE: "pause",
            media.SystemMediaTransportControlsButton.STOP: "stop",
        }
        action = actions.get(args.button)
        if action:
            try:
                self.command.emit(action)
            except RuntimeError:
                pass

    def update(self, state: MediaState):
        if self.controls is None or self._modules is None:
            return
        foundation, media, interop, streams = self._modules
        previous = self._last_state
        try:
            if previous is None or previous.status != state.status:
                self.controls.playback_status = {
                    "Playing": media.MediaPlaybackStatus.PLAYING,
                    "Paused": media.MediaPlaybackStatus.PAUSED,
                    "Stopped": media.MediaPlaybackStatus.STOPPED,
                }[state.status]
            if previous is None or (
                previous.title,
                previous.artist,
                previous.station,
                previous.cover_url,
            ) != (state.title, state.artist, state.station, state.cover_url):
                updater = self.controls.display_updater
                updater.clear_all()
                updater.type = media.MediaPlaybackType.MUSIC
                updater.music_properties.title = state.title or state.station or "KikuMoe"
                updater.music_properties.artist = state.artist
                updater.music_properties.album_title = state.station
                if state.cover_url:
                    try:
                        updater.thumbnail = streams.RandomAccessStreamReference.create_from_uri(
                            foundation.Uri(state.cover_url)
                        )
                    except Exception as exc:
                        self.log.debug("[SMTC] Cover unavailable: %s", exc)
                updater.update()
            self._last_state = state
        except Exception as exc:
            self.log.debug("[SMTC] Failed to update media controls: %s", exc)

    def _release_controls(self):
        controls = self.controls
        self.controls = None
        if controls is not None:
            try:
                if self._token is not None:
                    controls.remove_button_pressed(self._token)
            except Exception:
                pass
            try:
                controls.is_enabled = False
            except Exception:
                pass
        self._token = None
        self._handle = None

    def stop(self):
        self._release_controls()
        app = QApplication.instance()
        if app is not None:
            app.removeNativeEventFilter(self._filter)
