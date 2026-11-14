import threading
import time
from urllib.error import HTTPError

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
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
    started, release = threading.Event(), threading.Event()

    def request(endpoint, params):
        calls.append((endpoint, params))
        if params["track_name"] == "Song":
            started.set()
            release.wait(2)
        return {"plainLyrics": params["track_name"]}

    monkeypatch.setattr(provider, "_request", request)
    provider.finished.connect(lambda record, status: results.append((record, status)))
    provider.search("Song", "Artist", 200)
    assert started.wait(2)
    provider.search("New", "Artist", 180)
    release.set()
    deadline = time.monotonic() + 3
    while not results and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert results == [({"plainLyrics": "New"}, "ok")]
    assert len(calls) == 2
    provider.search("New", "Artist", 180)
    assert results[-1] == ({"plainLyrics": "New"}, "ok")
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
    panel.show_record({"syncedLyrics": "[00:01.00]One"}, "Plain", "Timing unavailable")
    assert not panel.lines
    assert panel.labels[0].text() == "Timing unavailable"
    assert panel.labels[1].text() == "One"
    panel.close()


def test_synced_lyrics_center_and_animate_through_line_changes(qapp):
    panel = LyricsPanel()
    panel.resize(320, 222)
    panel.show()
    assert panel.scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    panel.show_record(
        {"syncedLyrics": "\n".join(f"[00:{n:02}.00]Line {n}" for n in range(1, 9))}, "Plain"
    )
    qapp.processEvents()
    assert panel.labels[0].alignment() & Qt.AlignmentFlag.AlignHCenter
    panel.set_position(1)
    QTest.qWait(450)
    first = panel.labels[0]
    assert first._color.name() == panel._accent
    assert (
        abs(
            first.mapTo(panel.scroll.viewport(), first.rect().center()).y()
            - panel.scroll.viewport().height() // 2
        )
        < 5
    )
    panel.set_position(8)
    QTest.qWait(450)
    last = panel.labels[-1]
    assert last._color.name() == panel._accent
    assert first._color.alpha() == 165
    assert (
        abs(
            last.mapTo(panel.scroll.viewport(), last.rect().center()).y()
            - panel.scroll.viewport().height() // 2
        )
        < 5
    )
    panel.close()


def test_lookup_falls_back_after_404_and_honors_retry_after(qapp, monkeypatch):
    provider = LyricsProvider()
    calls = []

    def request(endpoint, params):
        calls.append(endpoint)
        if endpoint == "get":
            raise HTTPError("https://lrclib.net", 404, "Not found", {}, None)
        return [{"trackName": "Song", "artistName": "Artist", "duration": 200}]

    monkeypatch.setattr(provider, "_request", request)
    record, status, retry = provider._lookup({}, ("Song", "Artist", 200), provider.generation)
    assert calls == ["get", "search"]
    assert status == "ok" and record["trackName"] == "Song" and retry == 0

    def rate_limited(endpoint, params):
        raise HTTPError("https://lrclib.net", 429, "Rate limited", {"Retry-After": "30"}, None)

    monkeypatch.setattr(provider, "_request", rate_limited)
    record, status, retry = provider._lookup({}, ("Song", "Artist", 200), provider.generation)
    assert record is None and status == "error"
    assert retry >= time.monotonic() + 29


def test_lyrics_panel_responsive_scaling_and_recenter(qapp):
    panel = LyricsPanel()
    panel.resize(480, LyricsPanel.BASE_HEIGHT)
    panel.show()
    panel.show_record(
        {"syncedLyrics": "\n".join(f"[00:{n:02}.00]Lyric line {n}" for n in range(1, 10))},
        "Plain",
    )
    panel.set_position(5)
    QTest.qWait(400)

    assert panel._font_px == LyricsPanel.BASE_FONT_PX
    assert panel.height() == LyricsPanel.BASE_HEIGHT
    assert f"font-size: {LyricsPanel.BASE_FONT_PX}px" in panel.labels[0].styleSheet()

    # Scale up to hero / fullscreen proportion
    panel.set_responsive_scale(1.0)
    QTest.qWait(420)
    assert panel._font_px == LyricsPanel.HERO_FONT_PX
    assert panel.height() == LyricsPanel.HERO_HEIGHT
    assert panel.content_layout.spacing() == 13
    assert all(
        f"font-size: {LyricsPanel.HERO_FONT_PX}px" in lbl.styleSheet() for lbl in panel.labels
    )
    active_lbl = panel.labels[panel.active]
    assert (
        abs(
            active_lbl.mapTo(panel.scroll.viewport(), active_lbl.rect().center()).y()
            - panel.scroll.viewport().height() // 2
        )
        < 5
    )

    # New track loaded while scaled must inherit hero font size
    panel.show_record({"plainLyrics": "New track words"}, "Plain")
    assert all(
        f"font-size: {LyricsPanel.HERO_FONT_PX}px" in lbl.styleSheet() for lbl in panel.labels
    )

    # Scale back to compact
    panel.set_responsive_scale(0.0)
    assert panel._font_px == LyricsPanel.BASE_FONT_PX
    assert panel.height() == LyricsPanel.BASE_HEIGHT
    assert panel.content_layout.spacing() == 9
    panel.close()
