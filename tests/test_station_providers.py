"""Unit tests for multi-station definitions and metadata providers."""

from __future__ import annotations

from core.config import STATIONS, get_station_config, get_station_stream_url
from network.providers.anison_provider import AnisonProvider
from network.providers.gensokyo_provider import GensokyoProvider
from network.providers.neuro21_provider import Neuro21Provider
from network.providers.truckersfm_provider import TruckersFMProvider
from network.station_manager import StationManager


def test_station_definitions_integrity():
    """Verify all defined stations contain required metadata, formats, and valid streams."""
    expected_stations = ["listenmoe", "gensokyo", "anison", "neuro21", "truckersfm"]
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
    assert gensokyo_256 == "https://stream.gensokyoradio.net/3/"

    gensokyo_128 = get_station_stream_url("gensokyo", fmt="MP3 128k")
    assert gensokyo_128 == "https://stream.gensokyoradio.net/1/"

    # 3. ANISON.FM
    anison_url = get_station_stream_url("anison", fmt="MP3 320k")
    assert anison_url == "https://pool.anison.fm/AniSonFM(320)"

    # 4. Neuro 21
    neuro_mp3 = get_station_stream_url("neuro21", fmt="MP3 320k")
    assert neuro_mp3 == "https://radio.twinskaraoke.com/listen/neuro_21/radio.mp3"

    neuro_opus = get_station_stream_url("neuro21", fmt="Opus 128k")
    assert neuro_opus == "https://radio.twinskaraoke.com/listen/neuro_21/radio.ogg"

    # 5. TruckersFM
    truckers_320 = get_station_stream_url("truckersfm", fmt="MP3 320k")
    assert truckers_320 == "https://live.truckers.fm/"

    truckers_128 = get_station_stream_url("truckersfm", fmt="MP3 128k")
    assert truckers_128 == "https://live.truckers.fm/radio-128"

    truckers_64 = get_station_stream_url("truckersfm", fmt="AAC 64k")
    assert truckers_64 == "https://live.truckers.fm/radio-64"

    # 6. Fallback on invalid station or format
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
    assert start_epoch == 1793042846.0
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
    assert mgr.get_stream_url(fmt="MP3 256k") == "https://stream.gensokyoradio.net/3/"

    # Switch to ANISON
    changed2 = mgr.set_station("anison")
    assert changed2 is True
    assert mgr.current_station_id == "anison"
    assert mgr.get_stream_url() == "https://pool.anison.fm/AniSonFM(320)"

    # Switch to Neuro 21
    changed3 = mgr.set_station("neuro21")
    assert changed3 is True
    assert mgr.current_station_id == "neuro21"
    assert mgr.get_stream_url() == "https://radio.twinskaraoke.com/listen/neuro_21/radio.mp3"
    assert isinstance(mgr._active_provider, Neuro21Provider)

    # Switch to TruckersFM
    changed4 = mgr.set_station("truckersfm")
    assert changed4 is True
    assert mgr.current_station_id == "truckersfm"
    assert mgr.get_stream_url() == "https://live.truckers.fm/"
    assert isinstance(mgr._active_provider, TruckersFMProvider)

    # Clean shutdown
    mgr.stop()
    assert mgr._active_provider is None


def test_neuro21_metadata_parsing():
    """Verify Neuro21Provider accurately extracts AzuraCast track info, end epoch, and artwork."""
    received = []

    def mock_on_now_playing(title, artist, duration, start_epoch, art_url):
        received.append((title, artist, duration, start_epoch, art_url))

    provider = Neuro21Provider(
        on_now_playing=mock_on_now_playing,
        on_error_text=lambda _: None,
    )

    sample_data = {
        "station": {"id": 1, "name": "Neuro 21"},
        "now_playing": {
            "elapsed": 100,
            "remaining": 79,
            "sh_id": 9999,
            "played_at": 1793050000,
            "duration": 179,
            "song": {
                "id": "abc123",
                "text": "MARINA - Oh No! (Neuro)",
                "artist": "MARINA",
                "title": "Oh No! (Neuro)",
                "art": "https://radio.twinskaraoke.com/api/station/neuro_21/art/9115408a.jpg",
            },
        },
    }

    provider._parse_and_emit(sample_data)

    assert len(received) == 1
    title, artist, duration, start_epoch, art_url = received[0]
    assert title == "Oh No! (Neuro)"
    assert artist == "MARINA"
    assert duration == 179
    assert start_epoch == 1793050000 + 179  # expected track end timestamp
    assert art_url == "https://radio.twinskaraoke.com/api/station/neuro_21/art/9115408a.jpg"


def test_truckersfm_radiocloud_parsing():
    """Verify TruckersFMProvider parses RadioCloud current song API with Spotify CDN artwork."""
    received = []

    def mock_on_now_playing(title, artist, duration, start_epoch, art_url):
        received.append((title, artist, duration, start_epoch, art_url))

    provider = TruckersFMProvider(
        on_now_playing=mock_on_now_playing,
        on_error_text=lambda _: None,
    )

    sample_data = {
        "status": "success",
        "data": {
            "playback_id": 896494,
            "id": 1357,
            "artist": "Calvin Harris, Ellie Goulding",
            "title": "Outside",
            "album_art": "https://i.scdn.co/image/ab67616d00001e02063c048e9ef6bd021b744756",
            "link": "https://open.spotify.com/track/7MmG8p0F9N3C4AXdK6o6Eb",
            "played_at": 1793050614,
        },
    }

    success = provider._parse_and_emit_radiocloud(sample_data)
    assert success is True
    assert len(received) == 1

    title, artist, duration, start_epoch, art_url = received[0]
    assert title == "Outside"
    assert artist == "Calvin Harris, Ellie Goulding"
    assert duration == 0  # Live stream counter mode
    assert start_epoch == 1793050614.0
    assert art_url == "https://i.scdn.co/image/ab67616d00001e02063c048e9ef6bd021b744756"


def test_truckersfm_icecast_fallback_parsing():
    """Verify TruckersFMProvider parses native Icecast JSON fallback."""
    received = []

    def mock_on_now_playing(title, artist, duration, start_epoch, art_url):
        received.append((title, artist, duration, start_epoch, art_url))

    provider = TruckersFMProvider(
        on_now_playing=mock_on_now_playing,
        on_error_text=lambda _: None,
    )

    sample_icecast = {
        "icestats": {
            "source": [
                {
                    "mount": "/radio-128",
                    "title": "Olivia Rodrigo, Chappell Roan - expectations",
                    "ice-bitrate": 128,
                },
                {
                    "mount": "/radio",
                    "title": "Olivia Rodrigo, Chappell Roan - expectations",
                    "ice-bitrate": 320,
                },
            ]
        }
    }

    success = provider._parse_and_emit_icecast(sample_icecast)
    assert success is True
    assert len(received) == 1

    title, artist, duration, start_epoch, art_url = received[0]
    assert title == "expectations"
    assert artist == "Olivia Rodrigo, Chappell Roan"
    assert duration == 0
    assert art_url is None


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
        # Default is listenmoe, station_pill shows LISTEN.moe · J-POP
        player.set_radio_provider("listenmoe", "J-POP")
        assert player._current_radio_provider == "listenmoe"
        assert "LISTEN.moe" in player.station_pill.get_display_title()
        assert "J-POP" in player.station_pill.get_display_title()
        assert "listen.moe" in player.get_selected_stream_url()

        # Switch to Gensokyo: station_pill updates title
        player.set_radio_provider("gensokyo")
        assert player._current_radio_provider == "gensokyo"
        assert "Gensokyo Radio" in player.station_pill.get_display_title()
        assert "gensokyoradio.net" in player.get_selected_stream_url()

        # Switch to ANISON: station_pill updates title
        player.set_radio_provider("anison")
        assert player._current_radio_provider == "anison"
        assert "ANISON.FM" in player.station_pill.get_display_title()
        assert "anison.fm" in player.get_selected_stream_url()
    finally:
        player.deleteLater()


def test_station_pill_button_state():
    from PyQt6.QtWidgets import QApplication

    from ui.widgets.station_pill import StationPillButton

    _ = QApplication.instance() or QApplication(["pytest"])
    pill = StationPillButton(initial_station="listenmoe", initial_channel="J-POP")
    assert "LISTEN.moe" in pill.get_display_title()
    assert "J-POP" in pill.get_display_title()

    # Update to K-POP
    pill.update_state("listenmoe", "K-POP")
    assert "K-POP" in pill.get_display_title()

    # Update to Gensokyo Radio
    pill.update_state("gensokyo")
    assert pill.get_current_station() == "gensokyo"
    assert "Gensokyo Radio" in pill.get_display_title()

    # Update to ANISON.FM
    pill.update_state("anison")
    assert pill.get_current_station() == "anison"
    assert "ANISON.FM" in pill.get_display_title()
    pill.deleteLater()


def test_station_popover_animations():
    """Verify StationGlassPopover and StationPillButton animations (drop-in, fade, chevron)."""
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    from ui.widgets.station_pill import StationPillButton

    _ = QApplication.instance() or QApplication(["pytest"])
    pill = StationPillButton(initial_station="listenmoe", initial_channel="J-POP")
    pill.resize(180, 28)
    pill.show()

    assert pill.get_chevron_angle() == 0.0

    # Open menu and trigger drop-in/fade-in animation
    pill._show_station_menu()
    assert pill._popover is not None
    popover = pill._popover

    # Allow entrance animation to complete
    QTest.qWait(250)
    assert popover.windowOpacity() >= 0.99
    assert pill.get_chevron_angle() >= 170.0

    # Trigger close animation
    selected: list[tuple[str, str]] = []
    popover.animate_close(callback=lambda: selected.append(("listenmoe", "K-POP")))
    QTest.qWait(350)

    assert selected == [("listenmoe", "K-POP")]
    assert pill.get_chevron_angle() <= 5.0

    pill.deleteLater()


def test_station_providers_deduplicate_now_playing_events():
    """Verify that station polling providers do not spam redundant now_playing events."""
    from network.providers.anison_provider import AnisonProvider
    from network.providers.gensokyo_provider import GensokyoProvider

    g_events = []
    g_prov = GensokyoProvider(
        on_now_playing=lambda *args: g_events.append(args), on_error_text=lambda _: None
    )

    sample_g = {
        "SONGINFO": {"TITLE": "Song A", "ARTIST": "Artist A", "CIRCLE": "Circle A"},
        "SONGTIMES": {"DURATION": 200, "SONGEND": 1793040000},
        "SONGDATA": {"SONGID": 12345},
        "MISC": {"ALBUMART": "art.jpg"},
    }

    # Initial poll
    g_prov._parse_and_emit(sample_g)
    assert len(g_events) == 1

    # Second poll with same song: MUST NOT emit
    g_prov._parse_and_emit(sample_g)
    assert len(g_events) == 1

    # Third poll with new song: MUST emit
    sample_g2 = dict(sample_g)
    sample_g2["SONGDATA"] = {"SONGID": 12346}
    sample_g2["SONGINFO"] = {"TITLE": "Song B", "ARTIST": "Artist B", "CIRCLE": "Circle B"}
    g_prov._parse_and_emit(sample_g2)
    assert len(g_events) == 2

    # ANISON dedup test
    a_events = []
    a_prov = AnisonProvider(
        on_now_playing=lambda *args: a_events.append(args), on_error_text=lambda _: None
    )
    sample_a = {"full_duration": 180, "duration": 90, "on_air": "Anime - Song 1"}

    a_prov._parse_and_emit(sample_a)
    assert len(a_events) == 1

    # Second poll with same on_air text: MUST NOT emit
    a_prov._parse_and_emit(sample_a)
    assert len(a_events) == 1

    # Third poll with changed on_air text: MUST emit
    sample_a2 = {"full_duration": 210, "duration": 200, "on_air": "Anime 2 - Song 2"}
    a_prov._parse_and_emit(sample_a2)
    assert len(a_events) == 2

    # NEURO 21 dedup test
    n_events = []
    n_prov = Neuro21Provider(
        on_now_playing=lambda *args: n_events.append(args), on_error_text=lambda _: None
    )
    sample_n = {
        "now_playing": {
            "duration": 200,
            "played_at": 1793050000,
            "song": {"id": "song_1", "title": "Synth Track", "artist": "Neuro"},
        }
    }
    n_prov._parse_and_emit(sample_n)
    assert len(n_events) == 1
    # Duplicate poll
    n_prov._parse_and_emit(sample_n)
    assert len(n_events) == 1
    # Changed song
    sample_n2 = {
        "now_playing": {
            "duration": 180,
            "played_at": 1793050200,
            "song": {"id": "song_2", "title": "Cyber Track", "artist": "Neuro"},
        }
    }
    n_prov._parse_and_emit(sample_n2)
    assert len(n_events) == 2

    # TRUCKERSFM dedup test (RadioCloud & Icecast)
    t_events = []
    t_prov = TruckersFMProvider(
        on_now_playing=lambda *args: t_events.append(args), on_error_text=lambda _: None
    )
    sample_t = {
        "status": "success",
        "data": {"id": 101, "title": "Drive 1", "artist": "Artist 1", "played_at": 1793050000},
    }
    t_prov._parse_and_emit_radiocloud(sample_t)
    assert len(t_events) == 1
    # Duplicate poll
    t_prov._parse_and_emit_radiocloud(sample_t)
    assert len(t_events) == 1
    # Changed song
    sample_t2 = {
        "status": "success",
        "data": {"id": 102, "title": "Drive 2", "artist": "Artist 2", "played_at": 1793050200},
    }
    t_prov._parse_and_emit_radiocloud(sample_t2)
    assert len(t_events) == 2
