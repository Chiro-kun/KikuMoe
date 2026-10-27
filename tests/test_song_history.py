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


def test_vector_icons(qapp):
    """Verify vector icon and pixmap generators render cleanly at requested dimensions."""
    from ui.vector_icons import (
        get_apple_music_icon,
        get_apple_music_pixmap,
        get_chevron_down_icon,
        get_chevron_down_pixmap,
        get_copy_icon,
        get_copy_pixmap,
        get_history_icon,
        get_history_pixmap,
        get_spotify_icon,
        get_spotify_pixmap,
        get_youtube_icon,
        get_youtube_pixmap,
    )

    for sz in (14, 16, 24):
        # Spotify
        sp_pm = get_spotify_pixmap(sz)
        assert not sp_pm.isNull()
        assert sp_pm.width() == sz
        assert not get_spotify_icon(sz).isNull()

        # YouTube
        yt_pm = get_youtube_pixmap(sz)
        assert not yt_pm.isNull()
        assert yt_pm.width() == sz
        assert not get_youtube_icon(sz).isNull()

        # Apple Music
        am_pm = get_apple_music_pixmap(sz)
        assert not am_pm.isNull()
        assert am_pm.width() == sz
        assert not get_apple_music_icon(sz).isNull()

        # Copy
        cp_pm = get_copy_pixmap(sz)
        assert not cp_pm.isNull()
        assert cp_pm.width() == sz
        assert not get_copy_icon(sz).isNull()

        # History
        hi_pm = get_history_pixmap(sz)
        assert not hi_pm.isNull()
        assert hi_pm.width() == sz
        assert not get_history_icon(sz).isNull()

        # Chevron
        cv_pm = get_chevron_down_pixmap(sz)
        assert not cv_pm.isNull()
        assert cv_pm.width() == sz
        assert not get_chevron_down_icon(sz).isNull()


def test_track_menu_chevron_button(qapp):
    """Verify TrackMenuChevronButton properties and state toggling."""
    from ui.widgets.track_menu_button import TrackMenuChevronButton

    btn = TrackMenuChevronButton()
    assert btn.width() == 18
    assert btn.height() == 22
    assert btn.is_active() is False

    btn.set_active(True)
    assert btn.is_active() is True
    btn.set_active(False)
    assert btn.is_active() is False


def test_animated_track_label_click_and_hover(qapp):
    """Verify AnimatedTrackLabel hit-testing, clicked emission, and hover sync."""
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent

    from ui.widgets.ambient_cover import AnimatedTrackLabel
    from ui.widgets.track_menu_button import TrackMenuChevronButton

    lbl = AnimatedTrackLabel("Whole World Is Watching", interactive=True)
    lbl.resize(800, 26)
    btn = TrackMenuChevronButton()
    lbl.attach_chevron_button(btn)

    capsule = lbl.get_capsule_rect()
    assert capsule is not None

    clicks = []
    lbl.clicked.connect(lambda: clicks.append(True))

    # 1. Click outside capsule (e.g. at x=10 in empty margin) -> ignored
    ev_outside = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(10.0, 10.0),
        QPointF(10.0, 10.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    lbl.mousePressEvent(ev_outside)
    assert len(clicks) == 0

    # 2. Click inside capsule -> emits clicked
    ev_inside = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        capsule.center(),
        capsule.center(),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    lbl.mousePressEvent(ev_inside)
    assert len(clicks) == 1

    # 3. Non-interactive label (like artist row) -> never emits clicked, ignores hover
    artist_lbl = AnimatedTrackLabel("Artist Name", interactive=False)
    artist_lbl.resize(400, 26)
    artist_clicks = []
    artist_lbl.clicked.connect(lambda: artist_clicks.append(True))
    artist_lbl.mousePressEvent(ev_inside)
    assert len(artist_clicks) == 0
    assert artist_lbl.get_capsule_rect() is None

    # Hover sync
    lbl.set_hovered(True)
    assert btn._hovered is True
    lbl.set_hovered(False)
    assert btn._hovered is False

    # Menu active retention
    lbl.set_menu_active(True)
    assert lbl.is_menu_active() is True
    lbl.leaveEvent(None)
    # When menu is active, hover is retained
    lbl.set_menu_active(False)


def test_track_hover_group_connects_rows_and_syncs_state(qapp):
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QVBoxLayout, QWidget

    from ui.widgets.ambient_cover import AnimatedTrackLabel, TrackHoverGroup

    title = AnimatedTrackLabel("A considerably longer song title", interactive=True)
    artist = AnimatedTrackLabel("Artist", interactive=True)
    group = TrackHoverGroup(title, artist)
    group.resize(400, 46)
    group.show()
    qapp.processEvents()
    title_rect = title.get_capsule_rect()
    artist_rect = artist.get_capsule_rect()
    assert title_rect.width() > artist_rect.width()
    shape = group._shape()
    assert shape.contains(QPointF(200, title.height()))
    assert not shape.contains(QPointF(10, title.height()))

    artist.set_hovered(True)
    assert title._hovered and artist._hovered
    clicks = []
    artist.clicked.connect(lambda: clicks.append(True))
    point = artist_rect.center()
    artist.mousePressEvent(
        QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            point,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    assert clicks == [True]
    assert group.click_scale < 1.0
    for _ in range(6):
        group._tick_click()
    assert group.click_scale == 1.0
    assert not group._click_timer.isActive()
    title.set_menu_active(True)
    artist.set_hovered(False)
    assert group._animation.endValue() == 1.0
    title.set_menu_active(False)
    assert group._animation.endValue() == 0.0
    title.setText("–")
    assert group._shape().isEmpty()
    group.close()

    # Extra vertical space in the main layout must not separate the two rows.
    parent = QWidget()
    layout = QVBoxLayout(parent)
    layout.addWidget(group)
    parent.resize(400, 200)
    parent.show()
    qapp.processEvents()
    assert group.height() == title.height() + artist.height()
    assert artist.y() == title.y() + title.height()
    parent.close()


def test_animated_track_label_chevron_positioning(qapp):
    """Verify AnimatedTrackLabel positions attached chevron button next to title text."""
    from ui.widgets.ambient_cover import AnimatedTrackLabel
    from ui.widgets.track_menu_button import TrackMenuChevronButton

    lbl = AnimatedTrackLabel("–")
    lbl.resize(400, 26)
    btn = TrackMenuChevronButton()
    lbl.attach_chevron_button(btn)

    # Idle track: chevron hidden
    assert btn.isHidden() is True

    # Active track: chevron becomes visible
    lbl.setText("Last Surprise (Evil)")
    assert btn.isHidden() is False
    assert btn.x() > 0
    assert btn.x() < lbl.width()

    # Very long track: chevron stays within label bounds
    lbl.setText("Super Long Track Title That Exceeds The Geometry Margins Completely")
    assert btn.isHidden() is False
    assert btn.x() + btn.width() <= lbl.width()


def test_song_history_popover_buttons_use_vector_icons(qapp):
    """Verify history popover track rows use crisp vector icons without Unicode emojis."""
    from ui.history_popover import SongHistoryRowWidget

    entry = SongHistoryEntry(
        title="Bad Apple!!",
        artist="nomico",
        station_id="gensokyo",
        station_name="Gensokyo Radio",
        timestamp=time.time(),
    )
    i18n = I18n("it")
    row = SongHistoryRowWidget(entry, i18n=i18n)

    # Verify buttons have icons and no emoji text
    assert not row.btn_spotify.icon().isNull()
    assert row.btn_spotify.text() == ""

    assert not row.btn_youtube.icon().isNull()
    assert row.btn_youtube.text() == ""

    assert not row.btn_copy.icon().isNull()
    assert row.btn_copy.text() == ""
