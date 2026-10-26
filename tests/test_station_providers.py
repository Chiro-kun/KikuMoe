"""Unit tests for multi-station definitions and metadata providers."""

from __future__ import annotations

from core.config import STATIONS, get_station_config, get_station_stream_url
from network.providers.anison_provider import AnisonProvider
from network.providers.gensokyo_provider import GensokyoProvider
from network.station_manager import StationManager


def test_station_definitions_integrity():
    """Verify all defined stations contain required metadata, formats, and valid streams."""
    expected_stations = ["listenmoe", "gensokyo", "anison"]
    for s_id in expected_stations:
        assert s_id in STATIONS
        cfg = get_station_config(s_id)
        assert cfg["id"] == s_id
        assert "name" in cfg and len(cfg["name"]) > 0
        assert "icon" in cfg
        assert "streams" in cfg
        assert isinstance(cfg["formats"], list) and len(cfg["formats"]) > 0


def test_station_stream_url_resolution():
    """Verify stream URL resolution for different stations and quality formats."""
    # 1. LISTEN.moe J-POP & K-POP
    jpop_mp3 = get_station_stream_url("listenmoe", channel="J-POP", fmt="MP3")
    assert jpop_mp3 == "https://listen.moe/fallback"

    jpop_vorbis = get_station_stream_url("listenmoe", channel="J-POP", fmt="Vorbis")
    assert jpop_vorbis == "https://listen.moe/stream"

    kpop_opus = get_station_stream_url("listenmoe", channel="K-POP", fmt="Opus")
    assert kpop_opus == "https://listen.moe/kpop/opus"

    # 2. Gensokyo Radio
    gensokyo_256 = get_station_stream_url("gensokyo", fmt="MP3 256k")
    assert gensokyo_256 == "https://stream.gensokyoradio.net/3"

    gensokyo_128 = get_station_stream_url("gensokyo", fmt="MP3 128k")
    assert gensokyo_128 == "https://stream.gensokyoradio.net/1"

    # 3. ANISON.FM
    anison_url = get_station_stream_url("anison", fmt="MP3 320k")
    assert anison_url == "https://pool.anison.fm/AniSonFM(320)"

    # 4. Fallback on invalid station or format
    fallback_url = get_station_stream_url("nonexistent_radio", fmt="InvalidFormat")
    assert fallback_url.startswith("http")


def test_gensokyo_metadata_parsing():
    """Verify GensokyoProvider accurately extracts track info, durations, and album artwork."""
    received = []

    def mock_on_now_playing(title, artist, duration, start_epoch, art_url):
        received.append((title, artist, duration, start_epoch, art_url))

    provider = GensokyoProvider(
        on_now_playing=mock_on_now_playing,
        on_error_text=lambda _: None,
    )

    sample_data = {
        "SERVERINFO": {"STATUS": "OK"},
        "SONGINFO": {
            "TITLE": "科学世紀の少女達の郷愁",
            "ARTIST": "まさみティー",
            "ALBUM": "ゴツまさ倶楽部",
            "YEAR": "2010",
            "CIRCLE": "O-LIFE.JP",
        },
        "SONGTIMES": {
            "DURATION": 254,
            "PLAYED": 87,
            "REMAINING": 167,
            "SONGSTART": 1793042592,
            "SONGEND": 1793042846,
        },
        "SONGDATA": {"SONGID": 114872},
        "MISC": {"ALBUMART": "_24bbe897ec.jpg"},
    }

    provider._parse_and_emit(sample_data)

    assert len(received) == 1
    title, artist, duration, start_epoch, art_url = received[0]
    assert title == "科学世紀の少女達の郷愁"
    assert "まさみティー" in artist
    assert "O-LIFE.JP" in artist
    assert duration == 254
    assert start_epoch == 1793042592.0
    assert art_url == "https://cdn.gensokyoradio.net/images/albums/500/_24bbe897ec.jpg"


def test_anison_metadata_parsing():
    """Verify AnisonProvider sanitizes HTML, extracts anime/artist and title, and parses posters."""
    received = []

    def mock_on_now_playing(title, artist, duration, start_epoch, art_url):
        received.append((title, artist, duration, start_epoch, art_url))

    provider = AnisonProvider(
        on_now_playing=mock_on_now_playing,
        on_error_text=lambda _: None,
    )

    sample_data = {
        "duration": 71,
        "full_duration": 230,
        "listeners": "182",
        "on_air": (
            "В эфире: <span class='current_track'>"
            "<a href='http://anison.fm/catalog/656/Psycho-pass' "
            "class='anime_link' target='_blank'>Psycho-pass</a>"
            " &#151; Enigmatic Feeling</span>"
        ),
    }

    provider._parse_and_emit(sample_data)

    assert len(received) == 1
    title, artist, duration, start_epoch, art_url = received[0]
    assert title == "Enigmatic Feeling"
    assert artist == "Psycho-pass"
    assert duration == 230
    assert start_epoch is not None
    assert art_url == "https://anison.fm/resources/poster/300/656.jpg"


def test_station_manager_orchestration():
    """Verify StationManager switches active station providers and resolves URLs correctly."""
    events = []

    def mock_now_playing(t, a, d, s, c):
        events.append((t, a))

    mgr = StationManager(
        on_now_playing=mock_now_playing,
        on_error_text=lambda _: None,
        initial_station="listenmoe",
        initial_channel="J-POP",
    )

    assert mgr.current_station_id == "listenmoe"
    assert mgr.get_stream_url(fmt="MP3") == "https://listen.moe/fallback"

    # Switch to Gensokyo
    changed = mgr.set_station("gensokyo")
    assert changed is True
    assert mgr.current_station_id == "gensokyo"
    assert mgr.get_stream_url(fmt="MP3 256k") == "https://stream.gensokyoradio.net/3"

    # Switch to ANISON
    changed2 = mgr.set_station("anison")
    assert changed2 is True
    assert mgr.current_station_id == "anison"
    assert mgr.get_stream_url() == "https://pool.anison.fm/AniSonFM(320)"

    # Clean shutdown
    mgr.stop()
    assert mgr._active_provider is None


def test_station_ui_integration(monkeypatch):
    """Verify MainWindow updates station selector and channel switch visibility."""
    import os

    from PyQt6.QtWidgets import QApplication

    from ui.main_window import ListenMoePlayer

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    _ = QApplication.instance() or QApplication(["pytest"])

    # Avoid starting background sound daemon threads or full audio initialization in test
    monkeypatch.setattr(ListenMoePlayer, "_sync_clock_with_server", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_audio_backend", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_websocket", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_tray", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_extra_logic", lambda self: None)

    player = ListenMoePlayer()
    try:
        # Default is listenmoe, channel_switch should be shown (not hidden)
        player.set_radio_provider("listenmoe")
        assert player._current_radio_provider == "listenmoe"
        assert player.channel_switch.isHidden() is False
        assert "listen.moe" in player.get_selected_stream_url()

        # Switch to Gensokyo: channel_switch should be hidden
        player.set_radio_provider("gensokyo")
        assert player._current_radio_provider == "gensokyo"
        assert player.channel_switch.isHidden() is True
        assert "gensokyoradio.net" in player.get_selected_stream_url()

        # Switch to ANISON: channel_switch should be hidden
        player.set_radio_provider("anison")
        assert player._current_radio_provider == "anison"
        assert player.channel_switch.isHidden() is True
        assert "anison.fm" in player.get_selected_stream_url()
    finally:
        player.deleteLater()
