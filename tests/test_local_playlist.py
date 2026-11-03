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
