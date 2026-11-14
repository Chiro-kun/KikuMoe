"""Concurrency, thread-safety, and rapid-station-switch tests for issue #84."""

from __future__ import annotations

import threading
import time
import types
from typing import Any

from PyQt6.QtWidgets import QApplication

from audio.player_ffmpeg import PlayerFFmpeg
from audio.player_mpv import _MPV_END_ERROR, _MPV_END_STOP, PlayerMPV
from audio.player_vlc import PlayerVLC
from core.local_playlist import LocalPlaylistManager
from network.providers.anison_provider import AnisonProvider
from network.providers.gensokyo_provider import GensokyoProvider
from network.providers.local_provider import LocalProvider
from network.providers.neuro21_provider import Neuro21Provider
from network.providers.truckersfm_provider import TruckersFMProvider
from network.station_manager import StationManager
from network.ws_client import NowPlayingWS


def test_player_event_marshals_off_ui_thread_to_main_thread(monkeypatch):
    """_on_player_event called from a C/audio worker thread must marshal onto the Qt UI thread."""
    from ui.main_window import ListenMoePlayer

    app = QApplication.instance() or QApplication(["pytest"])

    monkeypatch.setattr(ListenMoePlayer, "_sync_clock_with_server", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_audio_backend", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_websocket", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_tray", lambda self: None)
    monkeypatch.setattr(
        ListenMoePlayer, "_init_system_media", lambda self: setattr(self, "system_media", None)
    )
    monkeypatch.setattr(ListenMoePlayer, "_init_extra_logic", lambda self: None)

    win = ListenMoePlayer()
    win.player_event.connect(win._on_player_event)
    win.player = types.SimpleNamespace(
        is_ready=lambda: True,
        is_playing=lambda: True,
        is_paused=lambda: False,
        get_mute=lambda: False,
    )

    observed_threads: list[str] = []
    orig_refresh = win._refresh_play_button_text

    def spy_refresh(*args, **kwargs):
        observed_threads.append(threading.current_thread().name)
        return orig_refresh(*args, **kwargs)

    monkeypatch.setattr(win, "_refresh_play_button_text", spy_refresh)
    monkeypatch.setattr(
        win,
        "_update_tray_controls",
        lambda: observed_threads.append(threading.current_thread().name),
    )
    monkeypatch.setattr(
        win,
        "_update_session_label",
        lambda: observed_threads.append(threading.current_thread().name),
    )

    errors: list[BaseException] = []

    def bg_worker():
        try:
            for code, val in (
                ("opening", None),
                ("buffering", 40),
                ("playing", None),
                ("paused", None),
                ("error", None),
                ("stopped", None),
            ):
                win._on_player_event(code, val)
        except BaseException as exc:
            errors.append(exc)

    try:
        t = threading.Thread(target=bg_worker, name="FakeAudioWorkerThread")
        t.start()
        t.join(timeout=2.0)
        assert not errors
        # Before processEvents, UI methods must NOT have run on FakeAudioWorkerThread
        assert "FakeAudioWorkerThread" not in observed_threads

        app.processEvents()
        assert observed_threads
        assert all(name == threading.main_thread().name for name in observed_threads)
    finally:
        win._cleanup_before_close()
        win.deleteLater()
        app.processEvents()


def test_rapid_station_switch_cancels_stale_timers_and_local_prompt(monkeypatch):
    """Switching away from empty local or errored stream cancels pending single-shot timers."""
    from ui.main_window import ListenMoePlayer

    app = QApplication.instance() or QApplication(["pytest"])

    monkeypatch.setattr(ListenMoePlayer, "_sync_clock_with_server", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_audio_backend", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_websocket", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_tray", lambda self: None)
    monkeypatch.setattr(
        ListenMoePlayer, "_init_system_media", lambda self: setattr(self, "system_media", None)
    )
    monkeypatch.setattr(ListenMoePlayer, "_init_extra_logic", lambda self: None)

    win = ListenMoePlayer()
    orig_station = win.settings.value("station", None)
    orig_channel = win.settings.value("channel", None)
    win.player = types.SimpleNamespace(
        is_ready=lambda: True,
        is_playing=lambda: False,
        is_paused=lambda: False,
        get_mute=lambda: False,
        stop=lambda: None,
        play_url=lambda _u: True,
    )
    win.station_mgr = types.SimpleNamespace(
        current_station_id="listenmoe",
        _active_provider=None,
        set_station=lambda sid: setattr(win.station_mgr, "current_station_id", sid) or True,
        set_channel=lambda _ch: None,
        stop=lambda: None,
    )

    prompt_calls: list[str] = []
    monkeypatch.setattr(win, "prompt_select_local_music", lambda: prompt_calls.append("prompted"))
    monkeypatch.setattr(win.local_playlist, "is_empty", lambda: True)
    monkeypatch.setattr(win.local_playlist, "get_current_track", lambda: None)

    try:
        win.set_radio_provider("local")
        assert win._local_prompt_timer.isActive()

        # Rapidly switch away within 10ms before the 100ms timer fires
        win.set_radio_provider("listenmoe", "J-POP")
        assert not win._local_prompt_timer.isActive()

        # Simulate error retry scheduled then cancelled by another switch and by close cleanup
        win._schedule_play_stream(50)
        assert win._retry_timer.isActive()
        win.set_radio_provider("gensokyo")
        assert not win._retry_timer.isActive()

        deadline = time.monotonic() + 0.18
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)

        assert prompt_calls == []
    finally:
        if orig_station is not None:
            win.settings.setValue("station", orig_station)
        if orig_channel is not None:
            win.settings.setValue("channel", orig_channel)
        win._cleanup_before_close()
        win.deleteLater()
        app.processEvents()


def test_station_manager_suppresses_stale_callbacks_on_rapid_switch(monkeypatch):
    """Late callbacks from superseded providers must never leak after switching stations."""
    captured_providers: list[Any] = []

    class DummyProvider:
        def __init__(self, station_id, on_now_playing, on_error_text, on_status_text=None, **_kw):
            self.station_id = station_id
            self.on_now_playing = on_now_playing
            self.on_error_text = on_error_text
            self.on_status_text = on_status_text
            self._is_running = False
            self.stopped_count = 0
            captured_providers.append(self)

        @property
        def is_running(self):
            return self._is_running

        def start(self):
            self._is_running = True

        def stop(self):
            self._is_running = False
            self.stopped_count += 1

        def set_channel(self, _ch):
            pass

    for mod_attr in (
        "network.station_manager.ListenMoeProvider",
        "network.station_manager.GensokyoProvider",
        "network.station_manager.AnisonProvider",
        "network.station_manager.Neuro21Provider",
        "network.station_manager.TruckersFMProvider",
    ):
        monkeypatch.setattr(
            mod_attr,
            lambda *_a, _cls=DummyProvider, **kw: _cls("stub", **kw),
        )

    received_np: list[tuple[str, str]] = []
    received_err: list[str] = []
    received_status: list[str] = []

    mgr = StationManager(
        on_now_playing=lambda t, a, *_rest: received_np.append((t, a)),
        on_error_text=lambda txt: received_err.append(txt),
        on_status_text=lambda txt: received_status.append(txt),
        initial_station="listenmoe",
    )
    mgr.start()

    for st in ("gensokyo", "anison", "neuro21", "truckersfm"):
        mgr.set_station(st)

    assert len(captured_providers) == 5
    old_first, old_mid, current = (
        captured_providers[0],
        captured_providers[2],
        captured_providers[-1],
    )

    # Fire stale callbacks from earlier superseded providers
    old_first.on_now_playing("Stale Title 1", "Stale Artist 1", 120, None, None)
    old_first.on_error_text("Stale Error 1")
    old_mid.on_now_playing("Stale Title 2", "Stale Artist 2", 120, None, None)
    if old_mid.on_status_text:
        old_mid.on_status_text("Stale Status")

    assert received_np == []
    assert received_err == []
    assert received_status == []

    # Only the currently active provider's callbacks pass through
    current.on_now_playing("Live Title", "Live Artist", 180, None, None)
    assert received_np == [("Live Title", "Live Artist")]
    mgr.stop()


def test_polling_providers_ignore_late_http_response_after_stop(monkeypatch):
    """Polling providers must discard in-flight HTTP payloads if stopped before urlopen returns."""
    providers = [
        GensokyoProvider(
            on_now_playing=lambda *_: calls.append("np"), on_error_text=lambda _: None
        ),
        AnisonProvider(on_now_playing=lambda *_: calls.append("np"), on_error_text=lambda _: None),
        Neuro21Provider(on_now_playing=lambda *_: calls.append("np"), on_error_text=lambda _: None),
        TruckersFMProvider(
            on_now_playing=lambda *_: calls.append("np"), on_error_text=lambda _: None
        ),
    ]
    calls: list[str] = []

    for prov in providers:
        prov._is_running = True
        prov._stop_event.clear()

        class FakeResp:
            def __enter__(self):
                # Provider stops right while HTTP response completes
                prov._stop_event.set()
                prov._is_running = False
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return (
                    b'{"status":"success","data":{"title":"X"},"on_air":"A - B",'
                    b'"SONGINFO":{"TITLE":"S"},"now_playing":{"song":{"title":"N"}}}'
                )

        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: FakeResp())
        prov._fetch_and_dispatch()

    assert calls == []


def test_local_provider_disconnects_signal_on_stop():
    """Repeated switches into/out of LocalProvider must not leak track_changed connections."""
    _ = QApplication.instance() or QApplication(["pytest"])
    pl = LocalPlaylistManager()
    calls: list[str] = []

    p1 = LocalProvider(
        on_now_playing=lambda title, *_r: calls.append(f"p1:{title}"),
        on_error_text=lambda _: None,
        playlist_manager=pl,
    )
    p1.start()
    p1.stop()

    # Stopped LocalProvider should no longer emit or stay connected on playlist signal
    assert p1._signal_connected is False


def test_ws_client_shutdown_blocks_late_callbacks_and_timers():
    """NowPlayingWS.shutdown() prevents late timer spawns or callbacks after teardown."""
    received: list[str] = []
    ws = NowPlayingWS(
        on_now_playing=lambda t, *_: received.append(f"np:{t}"),
        on_error_text=lambda e: received.append(f"err:{e}"),
        on_closed_text=lambda c: received.append(f"closed:{c}"),
    )
    ws.ws_heartbeat_interval_ms = 50
    ws.shutdown()
    assert ws.ws_should_reconnect is False
    ws._schedule_heartbeat()
    assert ws.ws_heartbeat_timer is None
    assert received == []


def test_player_ffmpeg_rapid_play_url_isolates_sessions_and_serializes_audio_stream(monkeypatch):
    """Rapid play_url() calls must never close an active PyAudio stream while write() runs."""
    monkeypatch.setattr(PlayerFFmpeg, "_init_audio", lambda self: None)
    monkeypatch.setattr(PlayerFFmpeg, "_check_ffmpeg", lambda self: True)

    events: list[str] = []
    player = PlayerFFmpeg(on_event=lambda c, _v: events.append(c))
    player._ready = True
    player._pyaudio_instance = object()

    stream_lock = threading.Lock()
    streams: list[Any] = []
    concurrent_close_during_write = False
    old_write_entered = threading.Event()
    release_old_write = threading.Event()

    class GuardedStream:
        def __init__(self, idx: int):
            self.idx = idx
            self.closed = False
            self.in_write = 0
            self.write_count = 0

        def is_active(self):
            return not self.closed

        def start_stream(self):
            pass

        def write(self, data, **kwargs):
            nonlocal concurrent_close_during_write
            if self.closed:
                concurrent_close_during_write = True
            self.in_write += 1
            try:
                self.write_count += 1
                if self.idx == 0 and self.write_count == 1:
                    old_write_entered.set()
                    release_old_write.wait(timeout=0.3)
            finally:
                self.in_write -= 1

        def stop_stream(self):
            nonlocal concurrent_close_during_write
            if self.in_write > 0:
                concurrent_close_during_write = True

        def close(self):
            nonlocal concurrent_close_during_write
            if self.in_write > 0:
                concurrent_close_during_write = True
            self.closed = True

    def fake_open(_self, _dev):
        with stream_lock:
            s = GuardedStream(len(streams))
            streams.append(s)
            return s, 48000

    class FakeProc:
        def __init__(self):
            self.pid = 4242
            self.killed = threading.Event()
            self._reads = 0
            self.stdout = self
            self.stderr = types.SimpleNamespace(read=lambda: b"")

        def read(self, n):
            if self.killed.is_set():
                return b""
            self._reads += 1
            if self._reads <= 8:
                return b"\x01\x00" * (n // 2)
            time.sleep(0.01)
            return b""

        def close(self):
            self.killed.set()

        def poll(self):
            return -9 if self.killed.is_set() else None

        def terminate(self):
            self.killed.set()

        def kill(self):
            self.killed.set()

        def wait(self, timeout=None):
            return -9

    monkeypatch.setattr(PlayerFFmpeg, "_open_pyaudio_stream", fake_open)
    monkeypatch.setattr("audio.player_ffmpeg.subprocess.Popen", lambda *a, **kw: FakeProc())

    try:
        assert player.play_url("https://listen.moe/stream") is True
        assert old_write_entered.wait(timeout=2.0)

        # Rapidly switch several stations without waiting for the previous worker's slow write
        for url in (
            "https://listen.moe/kpop/stream",
            "https://stream.gensokyoradio.net/3/",
            "https://pool.anison.fm/AniSonFM(320)",
            "https://live.truckers.fm/",
        ):
            assert player.play_url(url) is True
        release_old_write.set()
        time.sleep(0.15)
        player.stop()

        assert concurrent_close_during_write is False
        assert all(s.closed for s in streams)
    finally:
        release_old_write.set()
        player.force_cleanup()


def test_player_mpv_end_file_reason_and_switch_suppression(monkeypatch):
    """PlayerMPV inspects event.data.reason, sets ytdl=False, and drops stale teardown."""
    created_kwargs: list[dict[str, Any]] = []
    callbacks: dict[str, Any] = {}

    class FakeMpvInstance:
        def __init__(self, **kwargs):
            created_kwargs.append(kwargs)
            self.volume = 100
            self.mute = False
            self.pause = False
            self.idle_active = True
            self.mpv_version = "mpv fake"
            self.played_urls: list[str] = []

        def event_callback(self, name):
            def deco(fn):
                callbacks[name] = fn
                return fn

            return deco

        def property_observer(self, name):
            def deco(fn):
                callbacks[f"prop:{name}"] = fn
                return fn

            return deco

        def play(self, url):
            self.idle_active = False
            self.played_urls.append(url)

        def stop(self):
            self.idle_active = True

    fake_mod = types.SimpleNamespace(MPV=FakeMpvInstance)
    monkeypatch.setattr("audio.player_mpv.mpv", fake_mod)
    monkeypatch.setattr("audio.player_mpv._IS_WIN32", True)

    events: list[tuple[str, int | None]] = []
    p = PlayerMPV(on_event=lambda c, v: events.append((c, v)))
    assert p.is_ready()
    assert created_kwargs[0]["ytdl"] is False

    # Normal playback error via python-mpv MpvEvent (reason on event.data, NOT event.reason)
    p.play_url("https://listen.moe/stream")
    callbacks["start-file"](types.SimpleNamespace())
    callbacks["end-file"](types.SimpleNamespace(data=types.SimpleNamespace(reason=_MPV_END_ERROR)))
    assert ("error", None) in events

    # Replacing an active stream sets _switching=True until next start-file
    events.clear()
    p._player.idle_active = False
    p.play_url("https://live.truckers.fm/")
    assert p._switching is True
    callbacks["end-file"](types.SimpleNamespace(data=types.SimpleNamespace(reason=_MPV_END_STOP)))
    assert events == []  # Absorbed stale teardown STOP
    callbacks["start-file"](types.SimpleNamespace())
    assert p._switching is False
    assert events == [("opening", None)]


def test_player_vlc_suppresses_stale_events_and_detaches_on_cleanup(monkeypatch):
    """PlayerVLC absorbs async teardown events across switches and detaches on force_cleanup."""
    detached: list[Any] = []
    released_dev_lists: list[Any] = []

    class FakeEventType:
        MediaPlayerOpening = "opening"
        MediaPlayerBuffering = "buffering"
        MediaPlayerPlaying = "playing"
        MediaPlayerPaused = "paused"
        MediaPlayerStopped = "stopped"
        MediaPlayerEndReached = "ended"
        MediaPlayerEncounteredError = "error"

    class FakeState:
        Playing = 3
        Buffering = 2
        Opening = 1
        Paused = 4
        Stopped = 5

    class FakeEventManager:
        def event_attach(self, *_a):
            pass

        def event_detach(self, et):
            detached.append(et)

    class FakeMedia:
        def add_option(self, _opt):
            pass

    class FakeMediaPlayer:
        def __init__(self):
            self._em = FakeEventManager()
            self._state = FakeState.Stopped

        def event_manager(self):
            return self._em

        def audio_set_volume(self, _v):
            pass

        def audio_set_mute(self, _m):
            pass

        def get_state(self):
            return self._state

        def set_media(self, _m):
            pass

        def play(self):
            self._state = FakeState.Opening
            return 0

        def stop(self):
            self._state = FakeState.Stopped

        def release(self):
            pass

    class FakeInstance:
        def media_player_new(self):
            return FakeMediaPlayer()

        def media_new(self, _url):
            return FakeMedia()

        def media_new_path(self, _path):
            return FakeMedia()

        def release(self):
            pass

    fake_vlc = types.SimpleNamespace(
        Instance=lambda _opts: FakeInstance(),
        EventType=FakeEventType,
        State=FakeState,
        libvlc_audio_output_device_list_release=lambda d: released_dev_lists.append(d),
    )
    monkeypatch.setattr("audio.player_vlc.vlc", fake_vlc)
    monkeypatch.setattr("audio.player_vlc._found_libvlc", "/usr/lib/libvlc.so")

    events: list[str] = []
    p = PlayerVLC(on_event=lambda c, _v: events.append(c))
    assert p.is_ready()

    p.play_url("https://listen.moe/stream")
    assert p._switching is False
    # Simulate active stream replaced rapidly by second station
    p.player._state = FakeState.Playing
    p.play_url("https://live.truckers.fm/")
    assert p._switching is True

    # Stale async events arriving from old stopped media must be absorbed
    p._handle_event(types.SimpleNamespace(type=FakeEventType.MediaPlayerEncounteredError))
    p._handle_event(types.SimpleNamespace(type=FakeEventType.MediaPlayerStopped))
    assert events == []

    # Once new media opens, events flow normally
    p._handle_event(types.SimpleNamespace(type=FakeEventType.MediaPlayerOpening))
    assert p._switching is False
    assert events == ["opening"]

    p.force_cleanup()
    assert len(detached) == 7
