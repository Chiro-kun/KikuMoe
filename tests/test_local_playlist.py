"""Unit tests for core/local_playlist.py."""

from __future__ import annotations

from pathlib import Path

from core.constants import REPEAT_ALL, REPEAT_OFF, REPEAT_ONE
from core.local_metadata import LocalTrackInfo
from core.local_playlist import LocalPlaylistManager


def test_playlist_empty_state():
    mgr = LocalPlaylistManager()
    mgr.clear()
    assert mgr.count() == 0
    assert mgr.is_empty() is True
    assert mgr.get_current_track() is None
    assert mgr.next_track() is None
    assert mgr.previous_track() is None


def test_playlist_add_and_navigation(tmp_path: Path):
    mgr = LocalPlaylistManager()
    mgr.clear()

    # Create dummy supported files
    f1 = tmp_path / "song1.mp3"
    f1.write_bytes(b"\x00" * 100)
    f2 = tmp_path / "song2.flac"
    f2.write_bytes(b"fLaC" + b"\x00" * 100)
    f3 = tmp_path / "song3.wav"
    f3.write_bytes(b"RIFF" + b"\x00" * 100)

    added = mgr.add_files([str(f1), str(f2), str(f3)])
    assert added == 3
    assert mgr.count() == 3
    assert mgr.current_index == 0

    # Test sequential Next
    mgr.set_repeat_mode(REPEAT_ALL)
    mgr.set_shuffle(False)

    t2 = mgr.next_track()
    assert t2 is not None
    assert mgr.current_index == 1

    t3 = mgr.next_track()
    assert t3 is not None
    assert mgr.current_index == 2

    # Loop back to start
    t1 = mgr.next_track()
    assert t1 is not None
    assert mgr.current_index == 0


def test_playlist_repeat_one():
    mgr = LocalPlaylistManager()
    mgr.clear()
    mgr._tracks = [
        LocalTrackInfo(file_path="t1.mp3", title="Track 1"),
        LocalTrackInfo(file_path="t2.mp3", title="Track 2"),
    ]
    mgr.play_index(0)
    mgr.set_repeat_mode(REPEAT_ONE)

    t = mgr.next_track()
    assert t is not None
    assert t.title == "Track 1"
    assert mgr.current_index == 0


def test_playlist_repeat_off():
    mgr = LocalPlaylistManager()
    mgr.clear()
    mgr._tracks = [
        LocalTrackInfo(file_path="t1.mp3", title="Track 1"),
        LocalTrackInfo(file_path="t2.mp3", title="Track 2"),
    ]
    mgr.play_index(1)
    mgr.set_repeat_mode(REPEAT_OFF)
    mgr.set_shuffle(False)

    ended_called = []
    mgr.playback_ended.connect(lambda: ended_called.append(True))

    res = mgr.next_track()
    assert res is None
    assert len(ended_called) == 1


def test_playlist_remove_and_move():
    mgr = LocalPlaylistManager()
    mgr.clear()
    mgr._tracks = [
        LocalTrackInfo(file_path="t1.mp3", title="Track 1"),
        LocalTrackInfo(file_path="t2.mp3", title="Track 2"),
        LocalTrackInfo(file_path="t3.mp3", title="Track 3"),
    ]
    mgr.play_index(1)  # Track 2

    # Move Track 1 to index 2: [Track 2, Track 3, Track 1]
    assert mgr.move_track(0, 2) is True
    assert mgr.tracks[0].title == "Track 2"
    assert mgr.tracks[2].title == "Track 1"
    assert mgr.current_index == 0  # should track current song

    # Remove Track 3 (at index 1)
    assert mgr.remove_track(1) is True
    assert mgr.count() == 2
    assert mgr.tracks[0].title == "Track 2"
    assert mgr.tracks[1].title == "Track 1"


def test_local_provider_pipeline():
    from network.providers.local_provider import LocalProvider

    events = []
    statuses = []

    mgr = LocalPlaylistManager()
    mgr.clear()
    mgr._tracks = [
        LocalTrackInfo(
            file_path="t1.mp3",
            title="Local Song",
            artist="Artist X",
            duration_seconds=180.0,
            cover_bytes=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            cover_mime="image/png",
        ),
    ]
    mgr.play_index(0)

    provider = LocalProvider(
        on_now_playing=lambda t, a, d, s, c: events.append((t, a, d, s, c)),
        on_error_text=lambda err: None,
        on_status_text=lambda st: statuses.append(st),
        playlist_manager=mgr,
    )
    provider.start()
    assert len(statuses) >= 1
    assert len(events) >= 1
    assert events[0][0] == "Local Song"
    assert events[0][1] == "Artist X"
    assert events[0][2] == 180
    assert events[0][4] is not None
    assert events[0][4].startswith("file://")
    provider.stop()


def test_local_queue_dialog_creation_and_search():
    from PyQt6.QtWidgets import QApplication

    from ui.local_queue_dialog import LocalQueueDialog

    _app = QApplication.instance() or QApplication([])

    mgr = LocalPlaylistManager()
    mgr.clear()
    mgr._tracks = [
        LocalTrackInfo(
            file_path="anime.mp3",
            title="A Cruel Angel's Thesis",
            artist="Yoko Takahashi",
        ),
        LocalTrackInfo(
            file_path="pop.mp3",
            title="Pretender",
            artist="Official HIGE DANdism",
        ),
    ]

    dlg = LocalQueueDialog(mgr)

    assert dlg.list_widget.count() == 2

    # Test filtering search
    dlg.search_box.setText("Cruel")
    assert dlg.list_widget.count() == 1
    assert "Cruel" in dlg.list_widget.item(0).text()

    dlg.search_box.setText("NonExistent")
    assert dlg.list_widget.count() == 0

    dlg.search_box.clear()
    assert dlg.list_widget.count() == 2
    dlg.close()


def test_local_queue_empty_state_toggle():
    from PyQt6.QtWidgets import QApplication

    from ui.local_queue_dialog import LocalQueueDialog

    _app = QApplication.instance() or QApplication([])

    mgr = LocalPlaylistManager()
    mgr.clear()

    dlg = LocalQueueDialog(mgr)
    dlg.show()
    assert not dlg.empty_widget.isHidden()
    assert dlg.list_widget.isHidden()

    mgr._tracks = [
        LocalTrackInfo(file_path="t1.mp3", title="T1"),
    ]
    dlg._refresh_queue()
    assert dlg.empty_widget.isHidden()
    assert not dlg.list_widget.isHidden()
    dlg.close()


def test_local_prompt_dialog_creation_and_signals():
    from PyQt6.QtWidgets import QApplication

    from ui.widgets.local_prompt_dialog import LocalMusicPromptDialog

    _app = QApplication.instance() or QApplication([])

    mgr = LocalPlaylistManager()
    dlg = LocalMusicPromptDialog(mgr)

    assert dlg.playlist_mgr is mgr
    assert dlg.btn_folder is not None
    assert dlg.btn_files is not None
    assert dlg.btn_queue is not None

    opened = []
    dlg.open_queue_requested.connect(lambda: opened.append(True))
    dlg._on_open_queue()
    assert len(opened) == 1
    dlg.close()


def test_config_get_station_stream_url_local():
    from core.config import get_station_stream_url

    assert get_station_stream_url("local") == ""
    assert get_station_stream_url("LOCAL", "J-POP", "Vorbis") == ""


def test_simple_station_row_mouse_transparency():
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWidgets import QApplication

    from ui.widgets.station_pill import SimpleStationRow

    _app = QApplication.instance() or QApplication([])
    row = SimpleStationRow("local", "Musica Locale", QPixmap(16, 16), False)

    assert row._icon_lbl.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) is True
    assert row._title_lbl.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) is True


def test_track_label_click_in_local_empty_mode():
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication

    from ui.widgets.ambient_cover import AnimatedTrackLabel, TrackHoverGroup

    _app = QApplication.instance() or QApplication([])

    title = AnimatedTrackLabel("–", interactive=True)
    artist = AnimatedTrackLabel("Coda vuota", interactive=True)
    title.resize(200, 26)
    artist.resize(200, 26)
    group = TrackHoverGroup(title, artist)

    title_clicked = []
    artist_clicked = []
    group_clicked = []

    title.clicked.connect(lambda: title_clicked.append(True))
    artist.clicked.connect(lambda: artist_clicked.append(True))
    group.clicked.connect(lambda: group_clicked.append(True))

    # Simulate mouse press on artist label inside capsule
    capsule = artist.get_capsule_rect()
    pt = capsule.center() if capsule is not None else QPointF(10.0, 10.0)
    press_ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        pt,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    artist.mousePressEvent(press_ev)
    assert len(artist_clicked) == 1

    # Simulate mouse press on title label (rect is None because "–", should still emit)
    title.mousePressEvent(press_ev)
    assert len(title_clicked) == 1

    # Simulate mouse press on hover group
    group.mousePressEvent(press_ev)
    assert len(group_clicked) == 1


