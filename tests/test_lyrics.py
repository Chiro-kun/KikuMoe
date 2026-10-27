import pytest
from PyQt6.QtWidgets import QApplication

from core.lyrics import LyricsProvider, parse_lrc, select_match
from ui.widgets.lyrics_panel import LyricsPanel


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_parse_lrc_multiple_timestamps_and_empty_lines():
    assert parse_lrc("[ar:Artist]\n[00:12.50][00:03.1]Hello\n[00:20.00]") == [
        (3.1, "Hello"),
        (12.5, "Hello"),
        (20.0, ""),
    ]


def test_search_rejects_unrelated_tracks_and_wrong_duration():
    records = [
        {"trackName": "Other", "artistName": "Artist", "duration": 200},
        {"trackName": "Song", "artistName": "Artist", "duration": 300},
        {"trackName": "Song", "artistName": "Artist", "duration": 200, "syncedLyrics": "lrc"},
    ]
    assert select_match(records, "Song", "Artist", 200) is records[2]
    assert select_match(records[:2], "Song", "Artist", 200) is None


def test_provider_cancels_stale_fallback_and_reuses_cached_results(qapp, monkeypatch):
    provider = LyricsProvider()
    calls, results = [], []
    monkeypatch.setattr(provider, "_request", lambda *args: calls.append(args))
    provider.finished.connect(lambda record, status: results.append((record, status)))
    provider.search("Song", "Artist", 200)
    old_generation = provider.generation
    provider.search("New", "Artist", 180)
    provider._fallback({}, ("Song", "Artist", 200), old_generation)
    assert len(calls) == 2
    provider.cache[("Song", "Artist", 200)] = {"plainLyrics": "Words"}
    provider.search("Song", "Artist", 200)
    assert results[-1] == ({"plainLyrics": "Words"}, "ok")
    assert len(calls) == 2


def test_panel_tracks_active_line_and_supports_plain_lyrics(qapp):
    panel = LyricsPanel()
    panel.show_record({"syncedLyrics": "[00:01.00]One\n[00:02.00]Two"}, "Plain")
    panel.set_position(1.5)
    assert panel.active == 0
    panel.set_position(2.0)
    assert panel.active == 1
    panel.show_record({"plainLyrics": "Just text"}, "Plain")
    assert not panel.lines
    assert panel.labels[0].text() == "Plain"
    assert panel.labels[1].text() == "Just text"
    panel.close()
