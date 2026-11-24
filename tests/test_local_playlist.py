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
    assert not dlg.btn_folder.icon().isNull()
    assert not dlg.btn_files.icon().isNull()
    assert not dlg.btn_queue.icon().isNull()
    assert dlg._title_bar._ver_badge.text() == "MUSICA LOCALE"
    assert dlg._title_bar._ver_badge.width() >= 90  # dynamically sized to prevent text overflow

    opened = []
    dlg.open_queue_requested.connect(lambda: opened.append(True))
    dlg._on_open_queue()
    assert len(opened) == 1
    dlg.close()


def test_local_prompt_stays_open_when_opening_queue(tmp_path):
    """'Manage Queue' must not close the prompt; adding tracks elsewhere closes it once."""
    from PyQt6.QtWidgets import QApplication

    from ui.widgets.local_prompt_dialog import LocalMusicPromptDialog

    _app = QApplication.instance() or QApplication([])

    mgr = LocalPlaylistManager()
    dlg = LocalMusicPromptDialog(mgr)
    dlg.show()
    _app.processEvents()

    loaded: list[int] = []
    dlg.tracks_loaded.connect(loaded.append)

    dlg._on_open_queue()
    _app.processEvents()
    assert dlg.isVisible()
    assert loaded == []

    # Simulate the queue manager adding tracks to the shared playlist
    song = tmp_path / "song.mp3"
    song.write_bytes(b"")
    assert mgr.add_files([str(song)]) == 1
    assert loaded == []  # deferred until the playlist has selected its current track
    _app.processEvents()
    assert loaded == [1]
    assert mgr.get_current_track() is not None
    assert not dlg.isVisible()

    # Further queue updates must not re-emit
    mgr.queue_updated.emit()
    assert loaded == [1]
    dlg.close()


def test_local_prompt_self_loading_emits_once(tmp_path):
    from PyQt6.QtWidgets import QApplication

    from ui.widgets.local_prompt_dialog import LocalMusicPromptDialog

    _app = QApplication.instance() or QApplication([])

    mgr = LocalPlaylistManager()
    dlg = LocalMusicPromptDialog(mgr)
    dlg.show()
    _app.processEvents()

    loaded: list[int] = []
    dlg.tracks_loaded.connect(loaded.append)

    song = tmp_path / "song.mp3"
    song.write_bytes(b"")
    dlg._self_loading = True
    mgr.add_files([str(song)])
    dlg._self_loading = False
    assert loaded == []  # queue_updated ignored while the dialog loads tracks itself
    dlg._finish_with_tracks()
    dlg._finish_with_tracks()
    assert loaded == [1]
    dlg.close()


def test_dialog_entrance_and_exit_animations():
    from PyQt6.QtWidgets import QApplication

    from ui.widgets.local_prompt_dialog import LocalMusicPromptDialog

    _app = QApplication.instance() or QApplication([])
    mgr = LocalPlaylistManager()
    dlg = LocalMusicPromptDialog(mgr)

    dlg.show()
    assert hasattr(dlg, "_animate_dialog_entrance")
    assert hasattr(dlg, "_animate_dialog_exit")
    assert dlg._entrance_animated is True

    # Test exit callback execution
    closed = []
    dlg._animate_dialog_exit(lambda: closed.append(True))
    if dlg._anim_group is not None:
        dlg._anim_group.setCurrentTime(dlg._anim_group.totalDuration())
    _app.processEvents()
    assert len(closed) == 1
    dlg.close()


def test_version_badge_dynamic_sizing():
    from PyQt6.QtGui import QFontMetricsF
    from PyQt6.QtWidgets import QApplication

    from ui.custom_titlebar import _VersionBadgeLabel

    _app = QApplication.instance() or QApplication([])

    badge = _VersionBadgeLabel("v2.0")
    w1 = badge.width()

    badge.setText("MUSICA LOCALE")
    w2 = badge.width()
    fm = QFontMetricsF(badge._badge_font)
    text_w = fm.horizontalAdvance("MUSICA LOCALE")
    assert w2 > w1
    assert w2 >= int(text_w) + 16  # Must fully contain the text with side padding

    badge.setText("A")
    assert badge.width() == 56  # Minimum width constraint respected


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


def test_shortcuts_trigger_button_animations():
    from PyQt6.QtWidgets import QApplication, QLabel, QWidget

    from ui.main_window import ListenMoePlayer
    from ui.widgets.playback_controls import PlaybackControls
    from ui.widgets.segmented_switch import SettingsIconButton

    _app = QApplication.instance() or QApplication([])

    controls = PlaybackControls()
    for btn in (
        controls.hero_play,
        controls.btn_stop,
        controls.speaker_btn,
        controls.btn_next,
        controls.btn_prev,
        controls.btn_queue,
    ):
        assert btn._anim_step == 0
        btn.trigger_click_animation()
        assert btn._anim_step == 1
        assert btn._anim_timer.isActive()
        btn._anim_timer.stop()

    settings_btn = SettingsIconButton()
    assert settings_btn._anim_step == 0
    settings_btn.trigger_click_animation()
    assert settings_btn._anim_step == 1
    assert settings_btn._anim_timer.isActive()
    settings_btn._anim_timer.stop()

    host = QWidget()
    triggered: list[bool] = []
    shortcut = ListenMoePlayer._register_shortcut(
        host,
        "Space",
        lambda: triggered.append(True),
        button_getter=lambda: controls.hero_play,
    )
    controls.hero_play._anim_step = 0
    shortcut.activated.emit()
    assert triggered == [True]
    assert controls.hero_play._anim_step == 1
    controls.hero_play._anim_timer.stop()
    controls.close()
    settings_btn.close()
    host.close()
    assert QLabel is not None


def test_local_mode_updates_elapsed_and_remaining_labels():
    import time
    from types import SimpleNamespace

    from PyQt6.QtWidgets import QApplication, QLabel

    from core.i18n import I18n
    from ui.main_window import ListenMoePlayer

    _app = QApplication.instance() or QApplication([])

    pos = {"t": 45.0}
    fake_player = SimpleNamespace(get_time=lambda: pos["t"])
    fake = SimpleNamespace(
        player=fake_player,
        i18n=I18n("it"),
        t=lambda k: k,
        _current_title="Local Song",
        _current_artist="Local Artist",
        _current_cover_ref=None,
        _current_duration_seconds=180,
        _current_start_epoch=time.time(),
        _clock_sync_offset=0.0,
        song_elapsed_label=QLabel("0:00"),
        song_time_label=QLabel("--:--"),
        now_playing_title=QLabel(),
        now_playing_artist=QLabel(),
        now_playing_changed=SimpleNamespace(emit=lambda _t: None),
        _is_local_mode=lambda: True,
        _format_mmss=lambda s: ListenMoePlayer._format_mmss(None, s),
        _apply_window_title=lambda _t: None,
        _request_album_cover=lambda _c: None,
    )
    fake._get_local_playback_seconds = lambda: ListenMoePlayer._get_local_playback_seconds(fake)

    ListenMoePlayer.update_now_playing_label(fake)
    assert fake.song_elapsed_label.text() == "0:45"
    assert fake.song_time_label.text() == "2:15"

    pos["t"] = 120.0
    ListenMoePlayer.update_now_playing_label(fake)
    assert fake.song_elapsed_label.text() == "2:00"
    assert fake.song_time_label.text() == "1:00"


def test_app_icon_is_square_and_non_stretched():
    from pathlib import Path
    from types import SimpleNamespace

    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    from ui.main_window import ListenMoePlayer

    _app = QApplication.instance() or QApplication([])

    icon_path = Path(__file__).resolve().parent.parent / "icons" / "Kikumoe - no txt.png"
    raw_icon = QIcon(str(icon_path))
    assert not raw_icon.isNull()

    helper = SimpleNamespace()
    helper._trim_transparent_margins = lambda pm, alpha_threshold=0: (
        ListenMoePlayer._trim_transparent_margins(helper, pm, alpha_threshold)
    )
    helper._build_square_icon = lambda ic, sizes, fill_ratio=1.0: (
        ListenMoePlayer._build_square_icon(helper, ic, sizes, fill_ratio)
    )
    squared = ListenMoePlayer._make_icon_square(helper, raw_icon)
    assert not squared.isNull()

    for sz in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        pm = squared.pixmap(sz, sz)
        assert pm.size() == QSize(sz, sz)


def test_seek_bar_click_emits_once_and_updates_immediately():
    from types import SimpleNamespace

    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication

    from ui.main_window import ListenMoePlayer, SmoothProgressBar
    from ui.widgets.mini_hud import MiniTrackProgress

    _app = QApplication.instance() or QApplication([])

    for bar in (SmoothProgressBar(), MiniTrackProgress()):
        bar.resize(200, 16)
        if hasattr(bar, "setRange"):
            bar.setRange(0, 1000)
        else:
            bar.setMaximum(1000)
        bar.set_seekable(True)

        emitted: list[float] = []
        bar.seek_requested.connect(emitted.append)

        press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(100.0, 8.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release_same = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(100.0, 8.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        bar.mousePressEvent(press)
        bar.mouseReleaseEvent(release_same)
        assert len(emitted) == 1

        move = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(160.0, 8.0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release_drag = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(160.0, 8.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        bar.mousePressEvent(press)
        bar.mouseMoveEvent(move)
        assert len(emitted) == 2
        bar.mouseReleaseEvent(release_drag)
        assert len(emitted) == 3
        assert emitted[-1] > emitted[0]

    # Verify _apply_local_seek holds target against stale async backend timestamps briefly
    pos = {"t": 12.0}
    seek_calls: list[float] = []
    bar = SmoothProgressBar()
    bar.setMaximum(180_000)
    fake = SimpleNamespace(
        player=SimpleNamespace(
            seek=lambda s: seek_calls.append(s),
            get_time=lambda: pos["t"],
        ),
        song_progress=bar,
        lyrics_panel=SimpleNamespace(set_position=lambda _s: None),
        song_elapsed_label=SimpleNamespace(setText=lambda _t: None),
        song_time_label=SimpleNamespace(setText=lambda _t: None),
        _current_duration_seconds=180,
        _format_mmss=lambda s: ListenMoePlayer._format_mmss(None, s),
        log=SimpleNamespace(warning=lambda *a, **kw: None),
    )
    ListenMoePlayer._apply_local_seek(fake, 72.0, duration_sec=180)
    assert seek_calls == [72.0]
    assert ListenMoePlayer._get_local_playback_seconds(fake) == 72.0
    pos["t"] = 72.5
    assert ListenMoePlayer._get_local_playback_seconds(fake) == 72.5


def test_picker_defaults_to_music_folder_on_first_run(tmp_path: Path, monkeypatch):
    from PyQt6.QtCore import QSettings, QStandardPaths
    from PyQt6.QtWidgets import QApplication, QFileDialog

    import core.local_playlist as lp_mod
    from ui.local_queue_dialog import LocalQueueDialog
    from ui.widgets.local_prompt_dialog import LocalMusicPromptDialog

    _app = QApplication.instance() or QApplication([])

    music_dir = tmp_path / "Music"
    music_dir.mkdir()
    albums_dir = tmp_path / "Albums"
    albums_dir.mkdir()
    song = albums_dir / "track.mp3"
    song.write_bytes(b"\x00" * 64)

    settings = QSettings(str(tmp_path / "local.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(lp_mod, "QSettings", lambda *args: settings)
    monkeypatch.setattr(
        lp_mod.QStandardPaths,
        "writableLocation",
        lambda loc: str(music_dir) if loc == QStandardPaths.StandardLocation.MusicLocation else "",
    )

    mgr = LocalPlaylistManager()
    assert mgr.get_initial_picker_dir() == str(music_dir)

    opened_dirs: list[str] = []

    def fake_open_files(parent, caption="", directory="", filter="", *args, **kwargs):
        opened_dirs.append(directory)
        return [], ""

    def fake_existing_dir(parent, caption="", directory="", *args, **kwargs):
        opened_dirs.append(directory)
        return ""

    monkeypatch.setattr(QFileDialog, "getOpenFileNames", fake_open_files)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", fake_existing_dir)

    queue_dlg = LocalQueueDialog(mgr)
    prompt_dlg = LocalMusicPromptDialog(mgr)
    try:
        queue_dlg._on_add_files_clicked()
        queue_dlg._on_add_folder_clicked()
        prompt_dlg._on_select_files()
        prompt_dlg._on_select_folder()
        assert opened_dirs == [str(music_dir)] * 4

        # Adding files remembers that directory; missing dirs fall back cleanly to Music
        mgr.add_files([str(song)])
        assert mgr.get_initial_picker_dir() == str(albums_dir.resolve())

        settings.setValue("local_last_dir", str(tmp_path / "deleted_folder"))
        assert mgr.get_initial_picker_dir() == str(music_dir)
    finally:
        queue_dlg.close()
        prompt_dlg.close()


def test_local_queue_dialog_shows_thumbnails_and_no_text_overlap(tmp_path: Path, monkeypatch):
    from PyQt6.QtCore import QBuffer, QIODevice, QSettings
    from PyQt6.QtGui import QColor, QImage
    from PyQt6.QtWidgets import QApplication

    import core.local_playlist as lp_mod
    from core.local_metadata import extract_track_metadata
    from ui.local_queue_dialog import LocalQueueDialog, TrackItemWidget, _QueueItemDelegate

    _app = QApplication.instance() or QApplication([])

    settings = QSettings(str(tmp_path / "queue_thumb.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(lp_mod, "QSettings", lambda *args: settings)

    # Create valid 48x48 PNG bytes in memory
    img = QImage(48, 48, QImage.Format.Format_ARGB32)
    img.fill(QColor(236, 24, 108))
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    png_bytes = buf.data().data()

    album_dir = tmp_path / "album"
    album_dir.mkdir()
    (album_dir / "cover.png").write_bytes(png_bytes)
    wav_file = album_dir / "Artist Name - Sidecar Song.wav"
    wav_file.write_bytes(b"RIFF" + b"\x00" * 40)

    extracted = extract_track_metadata(str(wav_file))
    assert extracted.cover_bytes == png_bytes

    mgr = LocalPlaylistManager()
    mgr.clear()
    mgr._tracks = [
        extracted,
        LocalTrackInfo(
            file_path="no_cover.mp3",
            title="Fallback Track",
            artist="Fallback Artist",
            cover_bytes=None,
        ),
    ]
    mgr._current_index = 0

    dlg = LocalQueueDialog(mgr)
    try:
        dlg.show()
        _app.processEvents()
        assert isinstance(dlg.list_widget.itemDelegate(), _QueueItemDelegate)
        assert dlg.list_widget.count() == 2
        item0 = dlg.list_widget.item(0)
        item1 = dlg.list_widget.item(1)
        assert item0 is not None
        assert item1 is not None
        assert "Sidecar Song" in item0.text()

        row0 = dlg.list_widget.itemWidget(item0)
        row1 = dlg.list_widget.itemWidget(item1)
        assert isinstance(row0, TrackItemWidget)
        assert isinstance(row1, TrackItemWidget)
        assert row0.thumb.width() == 48
        assert row0.thumb.height() == 48
        assert row0.thumb.has_cover_art() is True
        assert row1.thumb.has_cover_art() is False
        assert len(dlg._thumb_cache) == 1
        assert row0.thumb.x() >= row0.idx_label.x() + row0.idx_label.width()

        # Issue #81: frameless container fills the dialog with no outer gutter and
        # the close button hover background follows the rounded top-right corner.
        assert dlg._content_frame.geometry() == dlg.rect()
        close_btn = dlg.titlebar._btn_close
        close_btn._hover = True
        close_btn.update()
        _app.processEvents()
        btn_img = close_btn.grab().toImage()
        assert btn_img.pixelColor(btn_img.width() - 1, 0).alpha() == 0
        assert btn_img.pixelColor(btn_img.width() // 2, btn_img.height() // 2).alpha() > 0
    finally:
        dlg.close()


def test_request_album_cover_does_not_reload_unchanged_local_file(tmp_path: Path):
    from types import SimpleNamespace
    from typing import Any

    from PyQt6.QtCore import QBuffer, QIODevice
    from PyQt6.QtGui import QColor, QImage
    from PyQt6.QtWidgets import QApplication

    from network.image_cache import normalize_cover_url
    from network.providers.local_provider import LocalProvider
    from ui.main_window import ListenMoePlayer

    _app = QApplication.instance() or QApplication([])

    def make_png(color: QColor) -> bytes:
        img = QImage(32, 32, QImage.Format.Format_ARGB32)
        img.fill(color)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        return bytes(buf.data().data())

    png_a = make_png(QColor(236, 24, 108))
    png_b = make_png(QColor(80, 180, 255))

    cover_path = tmp_path / "cover.png"
    cover_path.write_bytes(png_a)
    cover_uri = cover_path.as_uri()

    applied: list[object] = []
    fake: Any = SimpleNamespace(
        _current_cover_url=None,
        _current_cover_bytes_digest=None,
        _current_local_cover_sig=None,
        _cover_cache={},
        _normalize_album_cover_url=normalize_cover_url,
        _set_album_cover_pixmap=lambda pm: applied.append(pm),
    )

    # Repeated 1s timer polls for the exact same local cover must not re-apply the pixmap.
    ListenMoePlayer._request_album_cover(fake, cover_uri)
    ListenMoePlayer._request_album_cover(fake, cover_uri)
    ListenMoePlayer._request_album_cover(fake, cover_uri)
    assert len(applied) == 1

    # LocalProvider emits a file URI for the exact same bytes already loaded by bytes digest:
    # must skip re-decoding and keep the active pixmap intact.
    cover_copy = tmp_path / "copy.png"
    cover_copy.write_bytes(png_a)
    ListenMoePlayer._request_album_cover(fake, cover_copy.as_uri())
    assert len(applied) == 1

    # Different cover bytes MUST update cleanly.
    cover_b = tmp_path / "cover_b.png"
    cover_b.write_bytes(png_b)
    ListenMoePlayer._request_album_cover(fake, cover_b.as_uri())
    assert len(applied) == 2

    # LocalProvider reuses URI for identical bytes and changes URI + cleans up old file on new art.
    emitted: list[str | None] = []
    provider = LocalProvider(
        on_now_playing=lambda _t, _a, _d, _s, c: emitted.append(c),
        on_error_text=lambda _e: None,
    )
    provider._is_running = True
    t1 = LocalTrackInfo(file_path="a.mp3", cover_bytes=png_a, cover_mime="image/png")
    t2 = LocalTrackInfo(file_path="b.mp3", cover_bytes=png_a, cover_mime="image/png")
    t3 = LocalTrackInfo(file_path="c.mp3", cover_bytes=png_b, cover_mime="image/png")
    provider._on_track_changed(t1)
    first_cache = provider._cover_cache_file
    assert first_cache is not None and first_cache.exists()
    provider._on_track_changed(t2)
    assert emitted[0] == emitted[1]
    provider._on_track_changed(t3)
    assert emitted[2] != emitted[0]
    assert not first_cache.exists()
    if provider._cover_cache_file is not None:
        provider._cover_cache_file.unlink(missing_ok=True)


def test_history_indices_remapped_on_remove_and_move(tmp_path: Path, monkeypatch):
    """Verify remove_track and move_track keep _history indices pointing to the right tracks."""
    from PyQt6.QtCore import QSettings

    import core.local_playlist as lp_mod

    settings = QSettings(str(tmp_path / "hist_remap.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(lp_mod, "QSettings", lambda *args: settings)

    files = []
    for i in range(4):
        p = tmp_path / f"t{i}.mp3"
        p.write_bytes(b"ID3" + bytes([3, 0, 0, 0, 0, 0, 0]))
        files.append(str(p))

    mgr = LocalPlaylistManager()
    mgr.add_files(files)
    # Play 0 -> 2 -> 3
    mgr.play_index(0)
    mgr.play_index(2)
    mgr.play_index(3)

    # Remove track 1 (between 0 and 2): old indices 2 and 3 become 1 and 2
    assert mgr.remove_track(1) is True
    assert mgr.current_index == 2
    prev = mgr.previous_track()
    assert prev is not None and Path(prev.file_path).name == "t2.mp3"

    # Move track 0 ("t0.mp3") to index 2: history pointing to "t0.mp3" must follow it to index 2
    assert mgr.move_track(0, 2) is True
    prev2 = mgr.previous_track()
    assert prev2 is not None and Path(prev2.file_path).name == "t0.mp3"
    assert mgr.current_index == 2


def test_remote_station_blocks_local_and_unc_cover_paths(tmp_path: Path):
    """Verify remote stations never resolve local file paths or UNC shares for cover art."""
    from types import SimpleNamespace
    from typing import Any

    from network.image_cache import normalize_cover_url
    from ui.main_window import ListenMoePlayer

    local_img = tmp_path / "secret.png"
    local_img.write_bytes(b"\x89PNG\r\n\x1a\n")

    applied: list[object] = []
    remote_fake: Any = SimpleNamespace(
        _current_radio_provider="listenmoe",
        _current_cover_url="sentinel",
        _current_cover_bytes_digest=None,
        _current_local_cover_sig=None,
        _cover_cache={},
        _normalize_album_cover_url=normalize_cover_url,
        _set_album_cover_pixmap=lambda pm: applied.append(pm),
    )

    # Remote station receiving a local path, POSIX path, or UNC path must treat it as invalid
    ListenMoePlayer._request_album_cover(remote_fake, str(local_img))
    assert applied == [None]
    assert normalize_cover_url("/tmp/secret.png") is None
    assert normalize_cover_url("/covers/sample.png") == "https://cdn.listen.moe/covers/sample.png"
    assert ListenMoePlayer._resolve_system_media_cover_url(remote_fake, local_img.as_uri()) == ""

    # Even in local mode, UNC paths and remote file:// hosts must be rejected before os.path.isfile
    assert ListenMoePlayer._resolve_local_cover_file(r"\\attacker-host\share\a.png") is None
    assert ListenMoePlayer._resolve_local_cover_file("file://attacker-host/share/a.png") is None
