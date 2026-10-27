import ctypes
import ctypes.wintypes
import logging
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.media_state import MediaState
from core.windows_media import MediaKeyFilter, WindowsMediaBridge


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_windows_media_controls_update_and_rebind(qapp):
    actions = []

    class Controls:
        def __init__(self):
            self.display_updater = SimpleNamespace(
                music_properties=SimpleNamespace(),
                clear_all=lambda: None,
                update=lambda: None,
            )
            self.removed = []

        def add_button_pressed(self, handler):
            self.handler = handler
            return 12

        def remove_button_pressed(self, token):
            self.removed.append(token)

    controls = []

    def make_controls(hwnd):
        result = Controls()
        controls.append((hwnd, result))
        return result

    buttons = SimpleNamespace(PLAY=1, PAUSE=2, STOP=3)
    media = SimpleNamespace(
        SystemMediaTransportControlsButton=buttons,
        MediaPlaybackStatus=SimpleNamespace(PLAYING=1, PAUSED=2, STOPPED=3),
        MediaPlaybackType=SimpleNamespace(MUSIC=1),
    )
    bridge = WindowsMediaBridge(logging.getLogger("test.smtc"))
    bridge._modules = (None, media, SimpleNamespace(get_for_window=make_controls), None)
    bridge.command.connect(actions.append)
    bridge.bind(123)
    state = MediaState(status="Playing", title="Song", artist="Artist", station="Station")
    bridge.update(state)
    first = controls[0][1]
    assert first.is_enabled and first.playback_status == 1
    assert first.display_updater.music_properties.title == "Song"
    assert first.display_updater.music_properties.artist == "Artist"
    first.handler(None, SimpleNamespace(button=buttons.PAUSE))
    assert actions == ["pause"]
    bridge.bind(456)
    assert first.removed == [12] and not first.is_enabled
    bridge.update(state)
    assert controls[1][1].display_updater.music_properties.title == "Song"
    bridge.stop()
    assert controls[1][1].removed == [12]


def test_windows_media_key_fallback(qapp):
    class Bridge(QObject):
        command = pyqtSignal(str)
        controls = None

    bridge = Bridge()
    received = []
    bridge.command.connect(received.append)
    native = MediaKeyFilter(bridge)
    msg = ctypes.wintypes.MSG()
    msg.message = 0x0319
    msg.lParam = 14 << 16
    assert native.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg)) == (True, 1)
    assert received == ["toggle"]
    bridge.controls = object()
    assert native.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg)) == (False, 0)


def test_mpris_properties_and_commands(qapp):
    pytest.importorskip("dbus_next")
    from core.mpris import MprisPlayer, MprisRoot

    class Bridge(QObject):
        command = pyqtSignal(str)
        volume = pyqtSignal(float)

    bridge = Bridge()
    actions, volumes = [], []
    bridge.command.connect(actions.append)
    bridge.volume.connect(volumes.append)
    root = MprisRoot(bridge)
    player = MprisPlayer(bridge)
    state = MediaState(
        status="Playing",
        title="Song",
        artist="Artist",
        station="Radio",
        cover_url="https://example.com/cover.png",
        track_id="/me/chiro/kikumoe/track/t123",
        duration_us=180000000,
        position_us=30000000,
        volume=0.4,
    )
    player.update_state(state)
    assert root.Identity == "KikuMoe"
    assert player.PlaybackStatus == "Playing"
    assert player.Metadata["mpris:trackid"].value == state.track_id
    assert player.Metadata["mpris:length"].value == state.duration_us
    assert player.Metadata["xesam:artist"].value == ["Artist"]
    assert player.Position == state.position_us
    assert player.CanSeek is False and player.CanGoNext is False
    player.Pause()
    player.Play()
    player.PlayPause()
    player.Stop()
    root.Raise()
    player.Volume = 0.7
    assert actions == ["pause", "play", "toggle", "stop", "raise"]
    assert volumes == [0.7]


def test_player_publishes_media_state_and_respects_transport_commands(monkeypatch):
    from core.constants import STATION_LISTENMOE
    from ui import main_window

    sent = []
    actions = []
    backend = SimpleNamespace(
        is_playing=lambda: True,
        is_paused=lambda: False,
        get_mute=lambda: False,
    )
    bridge = SimpleNamespace(update=sent.append)
    window = SimpleNamespace(
        system_media=bridge,
        player=backend,
        _ui_paused=False,
        _current_title="Song",
        _current_artist="Artist",
        _current_radio_provider=STATION_LISTENMOE,
        _current_start_epoch=1000.0,
        _current_duration_seconds=200,
        _clock_sync_offset=0,
        _current_cover_ref="cover",
        _normalize_album_cover_url=lambda _: "https://example.com/cover.png",
        _media_last_state=MediaState(),
        i18n=SimpleNamespace(t=lambda key: key),
        volume_slider=SimpleNamespace(value=lambda: 40),
        log=logging.getLogger("test.media"),
        pause_resume=lambda: actions.append("pause_resume"),
        play_stream=lambda: actions.append("play"),
        stop_stream=lambda: actions.append("stop"),
        _tray_toggle_play_pause=lambda: actions.append("toggle"),
        _sync_system_media=lambda: None,
    )
    monkeypatch.setattr(main_window, "_IS_WIN32", False)
    monkeypatch.setattr(main_window.time, "time", lambda: 900.0)
    main_window.ListenMoePlayer._sync_system_media(window)
    assert sent[-1].status == "Playing"
    assert sent[-1].position_us == 100000000
    assert sent[-1].duration_us == 200000000
    assert sent[-1].volume == 0.4
    assert sent[-1].cover_url == "https://example.com/cover.png"
    main_window.ListenMoePlayer._on_system_media_command(window, "pause")
    main_window.ListenMoePlayer._on_system_media_command(window, "play")
    assert actions == ["pause_resume"]  # Play while already playing is a no-op.
    window._ui_paused = True
    monkeypatch.setattr(main_window.time, "time", lambda: 950.0)
    main_window.ListenMoePlayer._sync_system_media(window)
    assert sent[-1].status == "Paused"
    assert sent[-1].position_us == 100000000
    main_window.ListenMoePlayer._on_system_media_command(window, "play")
    main_window.ListenMoePlayer._on_system_media_command(window, "stop")
    assert actions == ["pause_resume", "pause_resume", "stop"]
