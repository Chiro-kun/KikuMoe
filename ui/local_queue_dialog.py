"""Local playlist and queue manager dialog for KikuMoe.

Frameless Cyber-Moe modal showing the active track queue, search filtering,
shuffle/repeat toggles, drag & drop loading, and instant seeking playback.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QPoint, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.constants import REPEAT_ALL, REPEAT_OFF, REPEAT_ONE
from core.i18n import I18n
from core.local_metadata import LocalTrackInfo
from core.local_playlist import LocalPlaylistManager
from core.now_playing import _format_mmss
from ui.custom_titlebar import CustomTitleBar
from ui.themes.cyber_moe import PALETTE
from ui.vector_icons import (
    get_music_note_icon,
    get_repeat_icon,
    get_shuffle_icon,
)
from ui.windows_titlebar import apply_windows_titlebar_dark_mode

_IS_WIN32 = sys.platform == "win32"


class TrackItemWidget(QWidget):
    """Rich Cyber-Deck item row for a single track in the queue."""

    def __init__(
        self,
        track: LocalTrackInfo,
        index: int,
        is_playing: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.track = track
        self.index = index
        self.is_playing = is_playing

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # Index / Playing indicator
        self.idx_label = QLabel(f"{index + 1:02d}")
        self.idx_label.setFixedWidth(24)
        self.idx_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if is_playing:
            self.idx_label.setText("▶")
            self.idx_label.setStyleSheet(
                f"color: {PALETTE['accent']}; font-weight: bold; font-size: 11px;"
            )
        else:
            self.idx_label.setStyleSheet(
                f"color: {PALETTE['text_muted']}; font-size: 11px; font-weight: 600;"
            )
        layout.addWidget(self.idx_label)

        # Metadata column
        meta_col = QVBoxLayout()
        meta_col.setContentsMargins(0, 0, 0, 0)
        meta_col.setSpacing(2)

        self.title_lbl = QLabel(track.display_title())
        self.title_lbl.setStyleSheet(
            f"color: {PALETTE['accent_hover'] if is_playing else PALETTE['text_primary']}; "
            "font-size: 12px; font-weight: 700;"
        )

        artist_text = track.display_artist()
        if track.album:
            artist_text += f" • {track.album}"
        self.artist_lbl = QLabel(artist_text)
        self.artist_lbl.setStyleSheet(
            f"color: {PALETTE['text_secondary']}; font-size: 10px; font-weight: 500;"
        )

        meta_col.addWidget(self.title_lbl)
        meta_col.addWidget(self.artist_lbl)
        layout.addLayout(meta_col, 1)

        # Duration label
        dur_str = (
            _format_mmss(int(track.duration_seconds)) if track.duration_seconds > 0 else "--:--"
        )
        self.dur_lbl = QLabel(dur_str)
        self.dur_lbl.setStyleSheet(
            f"color: {PALETTE['text_muted']}; font-size: 11px; font-weight: 600;"
        )
        layout.addWidget(self.dur_lbl)


class LocalQueueDialog(QDialog):
    """Cyber-Glass modal dialog managing the local audio playback queue."""

    play_track_requested = pyqtSignal(int)

    def __init__(
        self,
        playlist_manager: LocalPlaylistManager,
        parent: QWidget | None = None,
        i18n: I18n | None = None,
    ) -> None:
        super().__init__(parent)
        self.playlist_mgr = playlist_manager
        if i18n is not None:
            self.i18n = i18n
        elif parent is not None and hasattr(parent, "i18n"):
            self.i18n = getattr(parent, "i18n")
        else:
            self.i18n = I18n("it")

        self.setObjectName("localQueueDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(520, 580)
        self.setMinimumSize(420, 400)

        self._drag_start_pos: QPoint | None = None
        self._filtered_indices: list[int] = []

        self._init_ui()
        self._connect_signals()
        self._refresh_queue()
        apply_windows_titlebar_dark_mode(self, True)

    def _init_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)

        self._content_frame = QFrame(self)
        self._content_frame.setObjectName("queueContentFrame")
        self._content_frame.setStyleSheet(
            f"QFrame#queueContentFrame {{"
            f"  background-color: {PALETTE['bg_surface']};"
            f"  border: 1px solid {PALETTE['border_card']};"
            "  border-radius: 16px;"
            "}"
        )
        frame_layout = QVBoxLayout(self._content_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        # 1. Custom TitleBar
        self.titlebar = CustomTitleBar(self)
        self.titlebar.set_title(self.i18n.t("local_queue_title"))
        self.titlebar._btn_min.setVisible(False)
        self.titlebar._btn_max.setVisible(False)
        frame_layout.addWidget(self.titlebar)

        # 2. Main content area
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)

        # Top Deck: Search Filter + Action Buttons
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Cerca traccia o artista…")
        self.search_box.setStyleSheet(
            f"QLineEdit {{"
            "  background-color: rgba(255, 255, 255, 0.06);"
            f"  border: 1px solid {PALETTE['border_card']};"
            "  border-radius: 8px;"
            f"  color: {PALETTE['text_primary']};"
            "  padding: 6px 10px;"
            "  font-size: 11px;"
            "}"
            f"QLineEdit:focus {{"
            f"  border-color: {PALETTE['accent']};"
            "}"
        )
        self.search_box.textChanged.connect(self._on_search_changed)
        top_row.addWidget(self.search_box, 1)

        self.btn_add_files = QPushButton(self.i18n.t("local_add_files"))
        self.btn_add_files.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_files.setIcon(get_music_note_icon(14))
        self.btn_add_files.setStyleSheet(self._button_style(False))
        self.btn_add_files.clicked.connect(self._on_add_files_clicked)
        top_row.addWidget(self.btn_add_files)

        self.btn_add_folder = QPushButton(self.i18n.t("local_add_folder"))
        self.btn_add_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_folder.setStyleSheet(self._button_style(False))
        self.btn_add_folder.clicked.connect(self._on_add_folder_clicked)
        top_row.addWidget(self.btn_add_folder)

        layout.addLayout(top_row)

        # Queue List Widget
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("queueList")
        self.list_widget.setStyleSheet(
            f"QListWidget#queueList {{"
            f"  background-color: {PALETTE['bg_subtle']};"
            f"  border: 1px solid {PALETTE['border_card']};"
            "  border-radius: 10px;"
            "  outline: none;"
            "}"
            f"QListWidget#queueList::item {{"
            "  padding: 0px;"
            "  border-bottom: 1px solid rgba(255, 255, 255, 0.04);"
            "}"
            f"QListWidget#queueList::item:hover {{"
            f"  background-color: rgba(255, 255, 255, 0.04);"
            "}"
            f"QListWidget#queueList::item:selected {{"
            f"  background-color: rgba(236, 24, 108, 0.12);"
            "}"
        )
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.setAcceptDrops(True)
        layout.addWidget(self.list_widget, 1)

        # Bottom Deck: Stats + Shuffle/Repeat/Clear
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        self.stats_lbl = QLabel("0 brani")
        self.stats_lbl.setStyleSheet(
            f"color: {PALETTE['text_muted']}; font-size: 11px; font-weight: 600;"
        )
        bottom_row.addWidget(self.stats_lbl)
        bottom_row.addStretch(1)

        self.btn_shuffle = QPushButton()
        self.btn_shuffle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_shuffle.setIcon(get_shuffle_icon(14))
        self.btn_shuffle.setText(self.i18n.t("local_shuffle"))
        self.btn_shuffle.setStyleSheet(self._button_style(self.playlist_mgr.shuffle))
        self.btn_shuffle.clicked.connect(self._on_toggle_shuffle)
        bottom_row.addWidget(self.btn_shuffle)

        self.btn_repeat = QPushButton()
        self.btn_repeat.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_repeat.setIcon(get_repeat_icon(14))
        self._update_repeat_text()
        self.btn_repeat.clicked.connect(self._on_cycle_repeat)
        bottom_row.addWidget(self.btn_repeat)

        self.btn_clear = QPushButton(self.i18n.t("local_clear_queue"))
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setStyleSheet(self._button_style(False, danger=True))
        self.btn_clear.clicked.connect(self.playlist_mgr.clear)
        bottom_row.addWidget(self.btn_clear)

        layout.addLayout(bottom_row)
        frame_layout.addWidget(content, 1)
        outer_layout.addWidget(self._content_frame)

    def _button_style(self, active: bool = False, danger: bool = False) -> str:
        if danger:
            bg = "rgba(255, 75, 110, 0.12)"
            border = "rgba(255, 75, 110, 0.35)"
            color = "#FF4B6E"
        elif active:
            bg = "rgba(236, 24, 108, 0.22)"
            border = PALETTE["accent"]
            color = "#ffffff"
        else:
            bg = "rgba(255, 255, 255, 0.06)"
            border = PALETTE["border_card"]
            color = PALETTE["text_primary"]

        return (
            f"QPushButton {{"
            f"  background-color: {bg};"
            f"  border: 1px solid {border};"
            "  border-radius: 8px;"
            f"  color: {color};"
            "  padding: 5px 12px;"
            "  font-size: 11px;"
            "  font-weight: 600;"
            "}"
            f"QPushButton:hover {{"
            f"  border-color: {PALETTE['accent_hover']};"
            "}"
        )

    def _update_repeat_text(self) -> None:
        mode = self.playlist_mgr.repeat_mode
        active = mode != REPEAT_OFF
        if mode == REPEAT_ALL:
            text = self.i18n.t("local_repeat_all")
        elif mode == REPEAT_ONE:
            text = self.i18n.t("local_repeat_one")
        else:
            text = self.i18n.t("local_repeat_off")

        self.btn_repeat.setText(text)
        self.btn_repeat.setStyleSheet(self._button_style(active))

    def _connect_signals(self) -> None:
        self.playlist_mgr.queue_updated.connect(self._refresh_queue)
        self.playlist_mgr.track_changed.connect(self._on_track_changed)
        self.playlist_mgr.mode_changed.connect(self._on_mode_changed)

    def _refresh_queue(self) -> None:
        query = self.search_box.text().strip().lower()
        self.list_widget.clear()
        self._filtered_indices = []

        tracks = self.playlist_mgr.tracks
        curr_idx = self.playlist_mgr.current_index

        for idx, track in enumerate(tracks):
            title = track.display_title().lower()
            artist = track.display_artist().lower()
            album = (track.album or "").lower()

            if query and (query not in title and query not in artist and query not in album):
                continue

            self._filtered_indices.append(idx)
            item = QListWidgetItem(track.display_title())
            item.setSizeHint(QSize(0, 48))
            is_playing = idx == curr_idx
            widget = TrackItemWidget(track, idx, is_playing=is_playing)
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)

        # Update stats
        count = len(tracks)
        tot_sec = int(self.playlist_mgr.total_duration_seconds())
        tot_str = _format_mmss(tot_sec)
        self.stats_lbl.setText(self.i18n.t("local_tracks_summary", count=count, duration=tot_str))

    def _on_search_changed(self, text: str) -> None:
        self._refresh_queue()

    def _on_track_changed(self, track: LocalTrackInfo | None) -> None:
        self._refresh_queue()

    def _on_mode_changed(self, shuffle: bool, repeat_mode: int) -> None:
        self.btn_shuffle.setStyleSheet(self._button_style(shuffle))
        self._update_repeat_text()

    def _on_toggle_shuffle(self) -> None:
        self.playlist_mgr.toggle_shuffle()

    def _on_cycle_repeat(self) -> None:
        self.playlist_mgr.cycle_repeat_mode()

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        row = self.list_widget.row(item)
        if 0 <= row < len(self._filtered_indices):
            actual_idx = self._filtered_indices[row]
            self.playlist_mgr.play_index(actual_idx)
            self.play_track_requested.emit(actual_idx)

    def _on_add_files_clicked(self) -> None:
        filters = "Audio Files (*.mp3 *.flac *.ogg *.opus *.m4a *.aac *.wav);;All Files (*.*)"
        files, _ = QFileDialog.getOpenFileNames(
            self,
            self.i18n.t("local_add_files"),
            "",
            filters,
        )
        if files:
            self.playlist_mgr.add_files(files)

    def _on_add_folder_clicked(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self.i18n.t("local_add_folder"),
        )
        if folder:
            self.playlist_mgr.add_folder(folder)

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        row = self.list_widget.row(item)
        if not (0 <= row < len(self._filtered_indices)):
            return
        actual_idx = self._filtered_indices[row]
        track = self.playlist_mgr.get_track(actual_idx)
        if not track:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{"
            f"  background-color: {PALETTE['bg_surface_elevated']};"
            f"  border: 1px solid {PALETTE['border_card']};"
            "  border-radius: 8px;"
            "  padding: 4px;"
            f"  color: {PALETTE['text_primary']};"
            "}"
            f"QMenu::item:selected {{"
            f"  background-color: {PALETTE['accent']};"
            "  border-radius: 4px;"
            "}"
        )

        act_play = menu.addAction(self.i18n.t("local_play_now"))
        act_open_dir = menu.addAction(self.i18n.t("local_open_directory"))
        menu.addSeparator()
        act_remove = menu.addAction(self.i18n.t("local_remove_track"))

        selected = menu.exec(self.list_widget.mapToGlobal(pos))
        if selected == act_play:
            self.playlist_mgr.play_index(actual_idx)
            self.play_track_requested.emit(actual_idx)
        elif selected == act_open_dir:
            file_path = Path(track.file_path)
            if _IS_WIN32:
                subprocess.Popen(["explorer", "/select,", str(file_path)])
            else:
                subprocess.Popen(["xdg-open", str(file_path.parent)])
        elif selected == act_remove:
            self.playlist_mgr.remove_track(actual_idx)

    # Drag & Drop handling
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        for p in paths:
            path_obj = Path(p)
            if path_obj.is_dir():
                self.playlist_mgr.add_folder(str(path_obj))
            elif path_obj.is_file():
                self.playlist_mgr.add_files([str(path_obj)])
        event.acceptProposedAction()

    # Window Dragging
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_start_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(14, 16, 26, 235))
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 16, 16)
        painter.end()
