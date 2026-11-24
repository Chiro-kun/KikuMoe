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


def test_mpris_properties_and_commands(qapp, monkeypatch):
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
    properties = {prop.name for prop in player.introspect().properties}
    assert "Shuffle" not in properties
    assert {"PlaybackStatus", "Metadata", "Volume", "CanControl"} <= properties
    changes = []
    monkeypatch.setattr(player, "emit_properties_changed", changes.append)
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
    assert changes[-1]["PlaybackStatus"] == "Playing"
    assert changes[-1]["Metadata"]["xesam:title"].value == "Song"
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


def test_system_media_preserves_local_file_cover_uri_for_mpris_and_smtc(tmp_path, monkeypatch):
    from core.constants import STATION_LOCAL
    from ui import main_window

    cover_file = tmp_path / "kikumoe_cover_test.png"
    cover_file.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    file_uri = cover_file.as_uri()

    sent = []
    fake_window = SimpleNamespace(
        system_media=SimpleNamespace(update=sent.append),
        player=SimpleNamespace(
            is_playing=lambda: True,
            is_paused=lambda: False,
            get_mute=lambda: False,
            get_time=lambda: 12.0,
        ),
        _ui_paused=False,
        _current_title="Local Track",
        _current_artist="Local Artist",
        _current_radio_provider=STATION_LOCAL,
        _current_start_epoch=100.0,
        _current_duration_seconds=180,
        _clock_sync_offset=0,
        _current_cover_ref=file_uri,
        _is_local_mode=lambda: True,
        _normalize_album_cover_url=lambda ref: (
            main_window.ListenMoePlayer._normalize_album_cover_url(None, ref)
        ),
        _media_last_state=MediaState(),
        i18n=SimpleNamespace(t=lambda key: key),
        volume_slider=SimpleNamespace(value=lambda: 50),
        log=logging.getLogger("test.media"),
    )
    fake_window._resolve_system_media_cover_url = lambda ref: (
        main_window.ListenMoePlayer._resolve_system_media_cover_url(fake_window, ref)
    )

    monkeypatch.setattr(main_window, "_IS_WIN32", False)
    main_window.ListenMoePlayer._sync_system_media(fake_window)
    assert sent[-1].cover_url == file_uri

    # Nonexistent file URI or plain HTTP URL must still be rejected.
    fake_window._current_cover_ref = (tmp_path / "missing.png").as_uri()
    main_window.ListenMoePlayer._sync_system_media(fake_window)
    assert sent[-1].cover_url == ""

    fake_window._current_cover_ref = "http://example.com/cover.png"
    main_window.ListenMoePlayer._sync_system_media(fake_window)
    assert sent[-1].cover_url == ""


def test_windows_media_bridge_reads_local_file_cover_into_stream(qapp, tmp_path):
    cover_file = tmp_path / "local_cover.png"
    cover_bytes = b"\x89PNG\r\n\x1a\nlocaldata"
    cover_file.write_bytes(cover_bytes)
    file_uri = cover_file.as_uri()

    written = []
    uri_calls = []
    stream_calls = []

    class FakeMemStream:
        def __init__(self):
            self.seek_pos = None

        def seek(self, pos):
            self.seek_pos = pos

    class FakeWriter:
        def __init__(self, mem):
            self.mem = mem
            self.detached = False

        def write_bytes(self, data):
            written.append(bytes(data))

        def store_async(self):
            return SimpleNamespace(status=1)

        def detach_stream(self):
            self.detached = True

    class FakeRef:
        @staticmethod
        def create_from_stream(mem):
            stream_calls.append(mem)
            return ("stream_ref", mem)

        @staticmethod
        def create_from_uri(uri):
            uri_calls.append(uri)
            return ("uri_ref", uri)

    class FakeUpdater:
        def __init__(self):
            self.music_properties = SimpleNamespace()
            self.thumbnail = None
            self.updated = 0

        def clear_all(self):
            self.thumbnail = None

        def update(self):
            self.updated += 1

    updater = FakeUpdater()
    controls = SimpleNamespace(display_updater=updater, playback_status=None)
    streams = SimpleNamespace(
        InMemoryRandomAccessStream=FakeMemStream,
        DataWriter=FakeWriter,
        RandomAccessStreamReference=FakeRef,
    )
    foundation = SimpleNamespace(Uri=lambda u: f"Uri({u})")
    media = SimpleNamespace(
        MediaPlaybackStatus=SimpleNamespace(PLAYING=1, PAUSED=2, STOPPED=3),
        MediaPlaybackType=SimpleNamespace(MUSIC=1),
    )

    bridge = WindowsMediaBridge(logging.getLogger("test.smtc.local"))
    bridge.controls = controls
    bridge._modules = (foundation, media, SimpleNamespace(), streams)

    bridge.update(
        MediaState(
            status="Playing",
            title="Local Song",
            artist="Local Artist",
            station="Local Music",
            cover_url=file_uri,
        )
    )
    assert written == [cover_bytes]
    assert len(stream_calls) == 1
    assert stream_calls[0].seek_pos == 0
    assert updater.thumbnail[0] == "stream_ref"
    assert uri_calls == []

    bridge.update(
        MediaState(
            status="Playing",
            title="Remote Song",
            artist="Remote Artist",
            station="LISTEN.moe",
            cover_url="https://cdn.listen.moe/covers/test.png",
        )
    )
    assert updater.thumbnail == ("uri_ref", "Uri(https://cdn.listen.moe/covers/test.png)")


def test_pause_resume_starts_playback_when_backend_stopped_even_if_ui_paused():
    import threading
    from types import SimpleNamespace

    from ui import main_window

    calls: list[str] = []
    timer_states: list[bool] = []
    button_states: list[bool] = []

    window = SimpleNamespace(
        _playback_lock=threading.RLock(),
        _ui_paused=True,
        player=SimpleNamespace(
            is_playing=lambda: False,
            is_paused=lambda: False,
            pause_toggle=lambda: calls.append("pause_toggle"),
        ),
        play_stream=lambda: calls.append("play_stream"),
        _apply_session_timer_running_state=lambda running: timer_states.append(bool(running)),
        _refresh_play_button_text=lambda active: button_states.append(bool(active)),
        _sync_system_media=lambda: calls.append("sync"),
        log=SimpleNamespace(debug=lambda *_a, **_kw: None, info=lambda *_a, **_kw: None),
    )

    main_window.ListenMoePlayer.pause_resume(window)

    assert window._ui_paused is False
    assert "play_stream" in calls
    assert "pause_toggle" not in calls
    assert timer_states == []
    assert button_states == []


def test_mpris_pause_and_resume_keeps_state_synced_and_recovers_after_end():
    import threading
    from types import SimpleNamespace

    from core.constants import STATION_LOCAL
    from ui import main_window

    state = {"playing": True, "paused": False, "play_stream_calls": 0, "pause_toggle_calls": 0}
    timer_states: list[bool] = []
    button_states: list[bool] = []

    def toggle_backend():
        state["pause_toggle_calls"] += 1
        if state["playing"]:
            state["paused"] = not state["paused"]

    def start_backend():
        state["play_stream_calls"] += 1
        state["playing"] = True
        state["paused"] = False

    fake_service = SimpleNamespace(updates=[], update=lambda s: fake_service.updates.append(s))

    window = SimpleNamespace(
        _playback_lock=threading.RLock(),
        _ui_paused=False,
        current_station=STATION_LOCAL,
        _current_title="Local Song",
        _current_artist="Local Artist",
        _current_album="Local Album",
        _current_cover_ref=None,
        _current_duration_seconds=120.0,
        _current_start_epoch=None,
        _media_last_state=SimpleNamespace(status="Stopped", position_us=0),
        _user_intent_playing=True,
        i18n=SimpleNamespace(t=lambda k, **kw: k),
        volume_slider=SimpleNamespace(value=lambda: 80),
        player=SimpleNamespace(
            is_playing=lambda: state["playing"],
            is_paused=lambda: state["paused"],
            pause_toggle=toggle_backend,
            get_time=lambda: 12.5 if state["playing"] else 0.0,
            get_duration=lambda: 120.0,
            get_mute=lambda: False,
        ),
        system_media=fake_service,
        _resolve_system_media_cover_url=lambda _ref: None,
        _apply_session_timer_running_state=lambda running: timer_states.append(bool(running)),
        _refresh_play_button_text=lambda active: button_states.append(bool(active)),
        log=SimpleNamespace(
            debug=lambda *_a, **_kw: None,
            info=lambda *_a, **_kw: None,
            warning=lambda *_a, **_kw: None,
        ),
    )
    window.play_stream = lambda: start_backend()
    window._sync_system_media = lambda: main_window.ListenMoePlayer._sync_system_media(window)
    window.pause_resume = lambda: main_window.ListenMoePlayer.pause_resume(window)
    window._tray_toggle_play_pause = lambda: main_window.ListenMoePlayer._tray_toggle_play_pause(
        window
    )

    # Pause from MPRIS
    main_window.ListenMoePlayer._on_system_media_command(window, "pause")
    window._sync_system_media()
    assert state["paused"] is True
    assert window._ui_paused is True
    assert timer_states[-1] is False
    assert button_states[-1] is False
    assert fake_service.updates[-1].status == "Paused"

    # Resume from MPRIS
    main_window.ListenMoePlayer._on_system_media_command(window, "play")
    window._sync_system_media()
    assert state["paused"] is False
    assert window._ui_paused is False
    assert timer_states[-1] is True
    assert button_states[-1] is True
    assert fake_service.updates[-1].status == "Playing"

    # Simulate backend stopped/ended cleanly; pressing play/toggle restarts instead of no-op
    state["playing"] = False
    state["paused"] = False
    window._ui_paused = False
    window._sync_system_media()
    assert fake_service.updates[-1].status == "Stopped"

    # Even if a stale _ui_paused=True lingered while backend is stopped, toggle recovers
    window._ui_paused = True
    main_window.ListenMoePlayer._on_system_media_command(window, "toggle")
    window._sync_system_media()
    assert state["play_stream_calls"] == 1
    assert state["playing"] is True
    assert state["paused"] is False
    assert window._ui_paused is False
    assert fake_service.updates[-1].status == "Playing"


def test_linux_mpris_caches_remote_radio_cover_as_local_file_uri(qapp, tmp_path, monkeypatch):
    from pathlib import Path

    from PyQt6.QtCore import QBuffer, QIODevice
    from PyQt6.QtGui import QColor, QImage, QPixmap

    from core.constants import STATION_LISTENMOE
    from network import image_cache
    from ui import main_window

    cache_dir = tmp_path / "mpris_art"
    monkeypatch.setattr(image_cache, "get_cover_cache_dir", lambda: cache_dir)
    image_cache.clear_cached_pixmaps()
    image_cache.clear_cached_cover_files()

    img = QImage(16, 16, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ec186c"))
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    png_bytes = bytes(buf.data())

    cover_url = "https://cdn.listen.moe/covers/mpris_test_cover.png"
    sent = []
    fake_win = SimpleNamespace(
        system_media=SimpleNamespace(update=sent.append),
        player=SimpleNamespace(
            is_playing=lambda: True,
            is_paused=lambda: False,
            get_mute=lambda: False,
        ),
        _ui_paused=False,
        _current_title="MPRIS Song",
        _current_artist="MPRIS Artist",
        _current_radio_provider=STATION_LISTENMOE,
        _current_start_epoch=1000.0,
        _current_duration_seconds=180,
        _clock_sync_offset=0,
        _current_cover_ref="mpris_test_cover.png",
        _current_cover_url=cover_url,
        _is_local_mode=lambda: False,
        _normalize_album_cover_url=lambda ref: (
            main_window.ListenMoePlayer._normalize_album_cover_url(None, ref)
        ),
        _set_album_cover_pixmap=lambda _pix: None,
        _media_last_state=MediaState(),
        i18n=SimpleNamespace(t=lambda key: key),
        volume_slider=SimpleNamespace(value=lambda: 60),
        log=logging.getLogger("test.media.linux_cover"),
    )
    fake_win._resolve_system_media_cover_url = lambda ref: (
        main_window.ListenMoePlayer._resolve_system_media_cover_url(fake_win, ref)
    )
    fake_win._sync_system_media = lambda: main_window.ListenMoePlayer._sync_system_media(fake_win)

    monkeypatch.setattr(main_window, "_IS_WIN32", False)
    monkeypatch.setattr(main_window, "_IS_LINUX", True)

    # Before download finishes, falls back to normalized HTTPS URL
    fake_win._sync_system_media()
    assert sent[-1].cover_url == cover_url

    # Once cover bytes finish downloading, saved locally as file:// and synced immediately to MPRIS
    main_window.ListenMoePlayer._on_album_cover_data_ready(fake_win, cover_url, png_bytes)
    assert sent[-1].cover_url.startswith("file://")
    cached_path = Path(sent[-1].cover_url.replace("file:///", "").replace("file://", ""))
    # Verify via image_cache lookup and on-disk file existence
    cached_uri = image_cache.get_cached_cover_file_uri(cover_url)
    assert cached_uri == sent[-1].cover_url
    assert cached_uri is not None and cached_uri.endswith(".png")
    assert any(
        p.suffix == ".png" and p.stat().st_size == len(png_bytes) for p in cache_dir.iterdir()
    )
    assert cached_path.name.endswith(".png")

    # WebP payload is transcoded to PNG when a QPixmap is supplied for universal Linux MPRIS support
    webp_url = "https://cdn.listen.moe/covers/mpris_webp_cover.webp"
    webp_uri = image_cache.store_cover_file(
        webp_url, raw=b"RIFF\x00\x00\x00\x00WEBPxxxx", pixmap=QPixmap.fromImage(img)
    )
    assert webp_uri is not None and webp_uri.startswith("file://") and webp_uri.endswith(".png")

    # On Windows, remote radio covers remain HTTPS URLs
    monkeypatch.setattr(main_window, "_IS_LINUX", False)
    assert fake_win._resolve_system_media_cover_url("mpris_test_cover.png") == cover_url

    image_cache.clear_cached_pixmaps()
    image_cache.clear_cached_cover_files(delete_files=True)


def test_local_track_embedded_cover_publishes_file_uri_to_system_media(qapp, tmp_path, monkeypatch):
    from PyQt6.QtCore import QBuffer, QIODevice
    from PyQt6.QtGui import QColor, QImage

    from core.constants import STATION_LOCAL
    from core.local_metadata import LocalTrackInfo
    from network import image_cache
    from ui import main_window

    cache_dir = tmp_path / "local_mpris_art"
    monkeypatch.setattr(image_cache, "get_cover_cache_dir", lambda: cache_dir)
    image_cache.clear_cached_pixmaps()
    image_cache.clear_cached_cover_files()

    img = QImage(16, 16, QImage.Format.Format_ARGB32)
    img.fill(QColor("#38bdf8"))
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    png_bytes = bytes(buf.data())

    sent = []
    fake_win = SimpleNamespace(
        system_media=SimpleNamespace(update=sent.append),
        player=SimpleNamespace(
            is_playing=lambda: True,
            is_paused=lambda: False,
            get_mute=lambda: False,
            get_time=lambda: 5.0,
        ),
        _ui_paused=False,
        _current_title="",
        _current_artist="",
        _current_radio_provider=STATION_LOCAL,
        _current_start_epoch=None,
        _current_duration_seconds=None,
        _clock_sync_offset=0,
        _current_cover_ref=None,
        _current_cover_url=None,
        _current_cover_bytes_digest=None,
        _current_local_cover_sig=None,
        _current_cover_pixmap=None,
        _is_local_mode=lambda: True,
        _normalize_album_cover_url=lambda ref: (
            main_window.ListenMoePlayer._normalize_album_cover_url(None, ref)
        ),
        _set_album_cover_pixmap=lambda pix: setattr(fake_win, "_current_cover_pixmap", pix),
        _media_last_state=MediaState(),
        song_progress=SimpleNamespace(
            set_seekable=lambda _v: None,
            set_live_mode=lambda _v: None,
            setMaximum=lambda _v: None,
            setValue=lambda _v: None,
        ),
        local_playlist=SimpleNamespace(current_index=0, tracks=[object(), object()], repeat_mode=0),
        playback_controls=SimpleNamespace(set_nav_enabled=lambda _p, _n: None),
        lyrics_button=SimpleNamespace(isChecked=lambda: False),
        label_refresh=SimpleNamespace(emit=lambda: None),
        _sync_mini_hud=lambda: None,
        update_tray_texts=lambda: None,
        i18n=SimpleNamespace(t=lambda key: key),
        volume_slider=SimpleNamespace(value=lambda: 70),
        log=logging.getLogger("test.media.local_embedded"),
    )
    fake_win._resolve_system_media_cover_url = lambda ref: (
        main_window.ListenMoePlayer._resolve_system_media_cover_url(fake_win, ref)
    )
    fake_win._sync_system_media = lambda: main_window.ListenMoePlayer._sync_system_media(fake_win)

    monkeypatch.setattr(main_window, "_IS_WIN32", False)
    monkeypatch.setattr(main_window, "_IS_LINUX", True)

    track1 = LocalTrackInfo(
        file_path=str(tmp_path / "01.mp3"),
        title="Track One",
        artist="Album Artist",
        duration_seconds=150.0,
        cover_bytes=png_bytes,
        cover_mime="image/png",
    )
    main_window.ListenMoePlayer._on_local_track_changed(fake_win, track1)
    assert fake_win._current_cover_ref is not None
    assert fake_win._current_cover_ref.startswith("file://")
    assert sent[-1].cover_url == fake_win._current_cover_ref

    # Second track with identical embedded cover still keeps the valid file:// URI
    track2 = LocalTrackInfo(
        file_path=str(tmp_path / "02.mp3"),
        title="Track Two",
        artist="Album Artist",
        duration_seconds=160.0,
        cover_bytes=png_bytes,
        cover_mime="image/png",
    )
    main_window.ListenMoePlayer._on_local_track_changed(fake_win, track2)
    assert sent[-1].title == "Track Two"
    assert sent[-1].cover_url == fake_win._current_cover_ref

    image_cache.clear_cached_pixmaps()
    image_cache.clear_cached_cover_files(delete_files=True)
