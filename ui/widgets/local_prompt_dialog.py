"""Cyber-Moe Local Music Selector Prompt Dialog for KikuMoe.

Modal prompt presented when switching to local music mode with an empty queue,
allowing quick selection of music directories, audio files, or opening the queue manager.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QFont,
)
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import I18n
from core.local_playlist import (
    SUPPORTED_AUDIO_EXTENSIONS,
    LocalPlaylistManager,
)
from ui.custom_titlebar import CustomTitleBar
from ui.themes.cyber_moe import PALETTE
from ui.vector_icons import get_music_note_icon
from ui.windows_titlebar import apply_windows_titlebar_dark_mode


class LocalMusicPromptDialog(QDialog):
    """Frameless Cyber-Moe modal prompting user to select local music files or folder."""

    tracks_loaded = pyqtSignal(int)
    open_queue_requested = pyqtSignal()

    def __init__(
        self,
        playlist_mgr: LocalPlaylistManager,
        parent: QWidget | None = None,
        i18n: I18n | None = None,
    ) -> None:
        super().__init__(parent)
        self.playlist_mgr = playlist_mgr
        self.i18n = i18n or I18n("it")

        self.setObjectName("localPromptDialogRoot")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(440, 360)
        self.setAcceptDrops(True)

        app_icon = getattr(parent, "_icon_app", None) if parent is not None else None
        self._title_bar = CustomTitleBar(self, icon=app_icon)
        self._title_bar._btn_min.setVisible(False)
        self._title_bar._btn_max.setVisible(False)
        self._title_bar.set_badge_text(self.i18n.t("local_prompt_title").upper())

        self._init_ui()
        apply_windows_titlebar_dark_mode(self, True)

    def _init_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Container frame with border and background
        self._content_frame = QFrame(self)
        self._content_frame.setObjectName("localPromptContentFrame")
        self._content_frame.setStyleSheet(
            f"QFrame#localPromptContentFrame {{"
            f"  background-color: {PALETTE['bg_surface']};"
            f"  border: 1px solid {PALETTE['border_card']};"
            "  border-radius: 12px;"
            "}"
        )

        frame_layout = QVBoxLayout(self._content_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        # Title bar
        frame_layout.addWidget(self._title_bar)

        # Main Body
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 16, 28, 24)
        body_layout.setSpacing(12)
        body_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Badge / Icon
        icon_badge = QLabel()
        icon_badge.setFixedSize(54, 54)
        icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_badge.setPixmap(get_music_note_icon(28).pixmap(28, 28))
        icon_badge.setStyleSheet(
            f"background-color: rgba(236, 24, 108, 0.12);"
            f"border: 1px solid {PALETTE['accent']};"
            "border-radius: 27px;"
        )
        body_layout.addWidget(icon_badge, 0, Qt.AlignmentFlag.AlignCenter)

        # Title
        title_lbl = QLabel(self.i18n.t("local_prompt_title"))
        font_title = QFont()
        font_title.setPointSize(14)
        font_title.setBold(True)
        title_lbl.setFont(font_title)
        title_lbl.setStyleSheet(f"color: {PALETTE['text_primary']}; font-weight: bold;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body_layout.addWidget(title_lbl)

        # Subtitle
        sub_lbl = QLabel(self.i18n.t("local_prompt_subtitle"))
        sub_lbl.setWordWrap(True)
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setStyleSheet(
            f"color: {PALETTE['text_secondary']}; font-size: 12px; line-height: 1.4;"
        )
        body_layout.addWidget(sub_lbl)

        body_layout.addSpacing(6)

        # Buttons Stack
        btn_box = QVBoxLayout()
        btn_box.setSpacing(8)

        # Folder button (Primary)
        self.btn_folder = QPushButton(self.i18n.t("local_select_folder"))
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.setFixedHeight(36)
        self.btn_folder.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {PALETTE['accent']};"
            "  color: #FFFFFF;"
            "  border: none;"
            "  border-radius: 8px;"
            "  font-size: 12px;"
            "  font-weight: bold;"
            "  padding: 0 16px;"
            "}"
            f"QPushButton:hover {{"
            f"  background-color: {PALETTE['accent_hover']};"
            "}"
            f"QPushButton:pressed {{"
            f"  background-color: {PALETTE['accent_pressed']};"
            "}"
        )
        self.btn_folder.clicked.connect(self._on_select_folder)
        btn_box.addWidget(self.btn_folder)

        # Files button (Secondary)
        self.btn_files = QPushButton(self.i18n.t("local_select_files"))
        self.btn_files.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_files.setFixedHeight(34)
        self.btn_files.setStyleSheet(
            "QPushButton {"
            "  background-color: rgba(255, 255, 255, 0.08);"
            f"  border: 1px solid {PALETTE['border_card']};"
            f"  color: {PALETTE['text_primary']};"
            "  border-radius: 8px;"
            "  font-size: 12px;"
            "  font-weight: 600;"
            "  padding: 0 16px;"
            "}"
            "QPushButton:hover {"
            "  background-color: rgba(255, 255, 255, 0.14);"
            f"  border-color: {PALETTE['accent']};"
            "  color: #FFFFFF;"
            "}"
            "QPushButton:pressed {"
            "  background-color: rgba(255, 255, 255, 0.20);"
            "}"
        )
        self.btn_files.clicked.connect(self._on_select_files)
        btn_box.addWidget(self.btn_files)

        # Open Queue Manager (Tertiary / Ghost)
        self.btn_queue = QPushButton(self.i18n.t("local_open_queue"))
        self.btn_queue.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_queue.setFixedHeight(28)
        self.btn_queue.setStyleSheet(
            "QPushButton {"
            "  background: transparent;"
            "  border: none;"
            f"  color: {PALETTE['text_muted']};"
            "  font-size: 11px;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover {"
            f"  color: {PALETTE['accent']};"
            "  text-decoration: underline;"
            "}"
        )
        self.btn_queue.clicked.connect(self._on_open_queue)
        btn_box.addWidget(self.btn_queue)

        body_layout.addLayout(btn_box)
        frame_layout.addWidget(body, 1)
        outer_layout.addWidget(self._content_frame)

    def _on_select_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self.i18n.t("local_add_folder"),
            "",
        )
        if folder:
            count = self.playlist_mgr.add_folder(folder)
            if count > 0:
                self.tracks_loaded.emit(count)
                self.accept()

    def _on_select_files(self) -> None:
        filters = "Audio Files (*.mp3 *.flac *.ogg *.opus *.m4a *.aac *.wav);;All Files (*.*)"
        files, _ = QFileDialog.getOpenFileNames(
            self,
            self.i18n.t("local_add_files"),
            "",
            filters,
        )
        if files:
            count = self.playlist_mgr.add_files(files)
            if count > 0:
                self.tracks_loaded.emit(count)
                self.accept()

    def _on_open_queue(self) -> None:
        self.open_queue_requested.emit()
        self.reject()

    def dragEnterEvent(self, a0: QDragEnterEvent | None) -> None:
        if a0 is None:
            return
        mime = a0.mimeData()
        if mime is not None and mime.hasUrls():
            a0.acceptProposedAction()
        else:
            a0.ignore()

    def dropEvent(self, a0: QDropEvent | None) -> None:
        if a0 is None:
            return
        mime = a0.mimeData()
        if mime is None:
            return
        urls = mime.urls()
        files_to_add: list[str] = []
        for url in urls:
            path_str = url.toLocalFile()
            if not path_str:
                continue
            p = Path(path_str)
            if p.is_dir():
                self.playlist_mgr.add_folder(str(p))
            elif p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                files_to_add.append(str(p))

        if files_to_add:
            self.playlist_mgr.add_files(files_to_add)

        count = len(self.playlist_mgr.tracks)
        if count > 0:
            self.tracks_loaded.emit(count)
            self.accept()
        else:
            a0.acceptProposedAction()
