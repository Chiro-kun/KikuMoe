"""Cyber-Moe Local Music Selector Prompt Dialog for KikuMoe.

Modal prompt presented when switching to local music mode with an empty queue,
allowing quick selection of music directories, audio files, or opening the queue manager.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QFont,
)
from PyQt6.QtWidgets import (
    QDialog,
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
from ui.dialog_animations import CyberMoeDialogAnimationMixin
from ui.native_file_dialog import get_existing_directory, get_open_file_names
from ui.themes.cyber_moe import PALETTE
from ui.vector_icons import get_folder_icon, get_music_note_icon, get_queue_icon
from ui.windows_titlebar import apply_windows_titlebar_dark_mode


class LocalMusicPromptDialog(CyberMoeDialogAnimationMixin, QDialog):
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
        # True while this dialog itself is adding tracks (avoids double-handling
        # the queue_updated signal); True once tracks_loaded has been emitted.
        self._self_loading = False
        self._tracks_emitted = False

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

        # Tracks may also be added from elsewhere (e.g. the queue manager opened
        # via "Manage Queue"): close the prompt as soon as the queue is filled.
        self.playlist_mgr.queue_updated.connect(self._on_queue_updated)

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
        self.btn_folder = QPushButton(f"  {self.i18n.t('local_select_folder')}")
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.setFixedHeight(36)
        self.btn_folder.setIcon(get_folder_icon(16, "#FFFFFF"))
        self.btn_folder.setIconSize(QSize(16, 16))
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
        self.btn_files = QPushButton(f"  {self.i18n.t('local_select_files')}")
        self.btn_files.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_files.setFixedHeight(34)
        self.btn_files.setIcon(get_music_note_icon(16, PALETTE["accent"]))
        self.btn_files.setIconSize(QSize(16, 16))
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
        self.btn_queue = QPushButton(f"  {self.i18n.t('local_open_queue')}")
        self.btn_queue.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_queue.setFixedHeight(28)
        self.btn_queue.setIcon(get_queue_icon(14, PALETTE["text_muted"]))
        self.btn_queue.setIconSize(QSize(14, 14))
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

    def _finish_with_tracks(self) -> None:
        """Emit tracks_loaded exactly once and close the prompt."""
        if self._tracks_emitted:
            return
        count = len(self.playlist_mgr.tracks)
        if count <= 0:
            return
        self._tracks_emitted = True
        self.tracks_loaded.emit(count)
        self.accept()

    def _on_queue_updated(self) -> None:
        """Close the prompt when tracks are added from outside this dialog."""
        if self._self_loading or self._tracks_emitted:
            return
        if not self.isVisible() or getattr(self, "_is_closing", False):
            return
        # Deferred: LocalPlaylistManager emits queue_updated *before* selecting the
        # first track, so the receiver of tracks_loaded would find no current track.
        QTimer.singleShot(0, self._finish_with_tracks)

    def _on_select_folder(self) -> None:
        folder = get_existing_directory(
            self,
            self.i18n.t("local_add_folder"),
            self.playlist_mgr.get_initial_picker_dir(),
        )
        if folder:
            add_async = getattr(self.playlist_mgr, "add_folder_async", None)
            if callable(add_async):
                add_async(
                    folder, on_done=lambda count: self._finish_with_tracks() if count > 0 else None
                )
                return
            self._self_loading = True
            try:
                count = self.playlist_mgr.add_folder(folder)
            finally:
                self._self_loading = False
            if count > 0:
                self._finish_with_tracks()

    def _on_select_files(self) -> None:
        filters = self.i18n.t("local_audio_files_filter")
        files, _ = get_open_file_names(
            self,
            self.i18n.t("local_add_files"),
            self.playlist_mgr.get_initial_picker_dir(),
            filters,
        )
        if files:
            add_async = getattr(self.playlist_mgr, "add_files_async", None)
            if callable(add_async):
                add_async(
                    files, on_done=lambda count: self._finish_with_tracks() if count > 0 else None
                )
                return
            self._self_loading = True
            try:
                count = self.playlist_mgr.add_files(files)
            finally:
                self._self_loading = False
            if count > 0:
                self._finish_with_tracks()

    def _on_open_queue(self) -> None:
        # Keep the prompt open: it closes by itself (via queue_updated) once the
        # user adds tracks from the queue manager, or manually via its close button.
        self.open_queue_requested.emit()

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
        folders_to_add: list[str] = []
        for url in urls:
            path_str = url.toLocalFile()
            if not path_str:
                continue
            p = Path(path_str)
            if p.is_dir():
                folders_to_add.append(str(p))
            elif p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                files_to_add.append(str(p))

        add_folder_async = getattr(self.playlist_mgr, "add_folder_async", None)
        add_files_async = getattr(self.playlist_mgr, "add_files_async", None)
        if callable(add_folder_async) and callable(add_files_async):
            for folder in folders_to_add:
                add_folder_async(
                    folder,
                    on_done=lambda count: self._finish_with_tracks() if count > 0 else None,
                )
            if files_to_add:
                add_files_async(
                    files_to_add,
                    on_done=lambda count: self._finish_with_tracks() if count > 0 else None,
                )
            a0.acceptProposedAction()
            return

        self._self_loading = True
        try:
            for folder in folders_to_add:
                self.playlist_mgr.add_folder(folder)
            if files_to_add:
                self.playlist_mgr.add_files(files_to_add)
        finally:
            self._self_loading = False

        if len(self.playlist_mgr.tracks) > 0:
            self._finish_with_tracks()
        else:
            a0.acceptProposedAction()
