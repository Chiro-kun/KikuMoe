"""Unit tests for Phase 3: Session Song History and Quick Search."""

from __future__ import annotations

import time

import pytest
from PyQt6.QtWidgets import QApplication

from core.i18n import I18n
from core.quick_search import (
    _build_search_query,
    copy_to_clipboard,
    is_spotify_installed,
    search_apple_music,
    search_spotify,
    search_youtube,
    search_youtube_music,
)
from core.song_history import SongHistoryEntry, SongHistoryManager
from ui.history_popover import SongHistoryPopover
from ui.widgets.history_button import HistoryIconButton


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest"])
    return app


def test_song_history_entry_formatting():
    """Verify SongHistoryEntry formatting helpers."""
    e1 = SongHistoryEntry(
        title="Bad Apple!!",
        artist="nomico",
        station_id="gensokyo",
        station_name="Gensokyo Radio",
        timestamp=time.time(),
    )
    assert e1.formatted_title == "nomico - Bad Apple!!"
    assert ":" in e1.display_time

    # Empty artist
    e2 = SongHistoryEntry(
        title="Solo Title",
        artist="",
        station_id="listenmoe",
        station_name="LISTEN.moe",
        timestamp=time.time(),
    )
    assert e2.formatted_title == "Solo Title"


def test_song_history_manager_deduplication():
    """Verify consecutive duplicate tracks are ignored while distinct ones are recorded."""
    mgr = SongHistoryManager(max_entries=5)
    added_signals = []
    mgr.entry_added.connect(lambda e: added_signals.append(e))

    # Add first track
    e1 = mgr.add_entry("Connect", "ClariS", "anison", "ANISON.FM")
    assert e1 is not None
    assert mgr.count() == 1
    assert len(added_signals) == 1

    # Add duplicate immediately (same title, artist, station)
    dup = mgr.add_entry("connect", "claris", "anison", "ANISON.FM")
    assert dup is None
    assert mgr.count() == 1
    assert len(added_signals) == 1

    # Add different track
    e2 = mgr.add_entry("Gurenge", "LiSA", "anison", "ANISON.FM")
    assert e2 is not None
    assert mgr.count() == 2
    assert len(added_signals) == 2
    assert mgr.get_entries()[0].title == "Gurenge"

    # Add first track again (now allowed because not consecutive)
    e3 = mgr.add_entry("Connect", "ClariS", "anison", "ANISON.FM")
    assert e3 is not None
    assert mgr.count() == 3


def test_song_history_manager_max_entries():
    """Verify ring buffer enforces max_entries limit."""
    mgr = SongHistoryManager(max_entries=10)
    for i in range(15):
        mgr.add_entry(f"Title {i}", f"Artist {i}")

    assert mgr.count() == 10
    entries = mgr.get_entries()
    assert entries[0].title == "Title 14"
    assert entries[-1].title == "Title 5"

    # Test clear
    cleared = []
    mgr.history_cleared.connect(lambda: cleared.append(True))
    mgr.clear()
    assert mgr.count() == 0
    assert len(cleared) == 1


def test_quick_search_query_builder():
    """Verify query builder handles artist and title combinations."""
    assert _build_search_query("Title", "Artist") == "Artist Title"
    assert _build_search_query("Title", "") == "Title"
    assert _build_search_query("", "Artist") == "Artist"
    assert _build_search_query("", "") == ""


def test_quick_search_handlers(monkeypatch):
    """Verify quick search functions invoke openUrl with properly encoded queries."""
    from PyQt6.QtGui import QDesktopServices

    opened_urls = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toString()) or True,
    )

    search_youtube("Bad Apple!!", "nomico")
    assert len(opened_urls) == 1
    assert "youtube.com/results?search_query=" in opened_urls[0]
    assert "Bad Apple" in opened_urls[0]

    search_youtube_music("Connect", "ClariS")
    assert "music.youtube.com/search?q=" in opened_urls[1]
    assert "ClariS" in opened_urls[1]

    search_apple_music("Song Title", "Artist")
    assert "music.apple.com/search?term=" in opened_urls[2]

    # Spotify (without desktop app)
    monkeypatch.setattr("core.quick_search.is_spotify_installed", lambda: False)
    search_spotify("Song", "Artist")
    assert "open.spotify.com/search/" in opened_urls[3]

    # Spotify (with desktop app)
    monkeypatch.setattr("core.quick_search.is_spotify_installed", lambda: True)
    search_spotify("Song", "Artist")
    assert "spotify:search:" in opened_urls[4]


def test_spotify_installed_detection():
    """Verify is_spotify_installed returns boolean without crashing."""
    res = is_spotify_installed()
    assert isinstance(res, bool)


def test_clipboard_copy(qapp, monkeypatch):
    """Verify copy_to_clipboard copies text to QClipboard."""
    from unittest.mock import MagicMock

    mock_clip = MagicMock()
    monkeypatch.setattr(QApplication, "clipboard", lambda: mock_clip)
    res = copy_to_clipboard("KikuMoe Test Clipboard String")
    assert res is True
    mock_clip.setText.assert_called_once_with("KikuMoe Test Clipboard String")


def test_history_icon_button(qapp):
    """Verify HistoryIconButton click and state changes."""
    btn = HistoryIconButton()
    assert btn.width() == 30
    assert btn.height() == 28
    assert btn.is_active() is False

    btn.set_active(True)
    assert btn.is_active() is True
    btn.set_active(False)
    assert btn.is_active() is False


def test_song_history_popover_empty_and_populated(qapp):
    """Verify SongHistoryPopover rendering and item population."""
    mgr = SongHistoryManager(max_entries=20)
    i18n = I18n("it")
    popover = SongHistoryPopover(history_manager=mgr, i18n=i18n)

    # Empty state check
    assert popover.badge_count.text() == "0"
    assert popover.btn_clear.isEnabled() is False

    # Add items
    mgr.add_entry("Track A", "Artist A", "gensokyo", "Gensokyo Radio")
    mgr.add_entry("Track B", "Artist B", "anison", "ANISON.FM")

    assert popover.badge_count.text() == "2"
    assert popover.btn_clear.isEnabled() is True

    # Clear clicked
    popover.btn_clear.click()
    assert mgr.count() == 0
    assert popover.badge_count.text() == "0"
