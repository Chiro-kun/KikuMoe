"""Cyber-Glass Session Song History Popover card for KikuMoe."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QKeyEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from core.i18n import I18n
from core.quick_search import copy_to_clipboard, search_spotify, search_youtube
from core.song_history import SongHistoryEntry, SongHistoryManager
from ui.vector_icons import get_copy_icon, get_spotify_icon, get_youtube_icon


class _ElidedLabel(QLabel):
    """QLabel that smoothly elides overflowing text with '...'."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def setText(self, text: str | None) -> None:
        self._full_text = text or ""
        super().setText(text or "")
        self.update()

    def paintEvent(self, a0: object) -> None:
        painter = QPainter(self)
        fm = self.fontMetrics()
        elided = fm.elidedText(self._full_text, Qt.TextElideMode.ElideRight, self.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        painter.drawText(self.rect(), int(self.alignment()), elided)
        painter.end()


class _TrackThumbnail(QLabel):
    """Small 34x34 rounded cover art thumbnail with fallback."""

    def __init__(self, art_url: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(34, 34)
        self.setStyleSheet("background: transparent; border: none;")
        self._pixmap: QPixmap | None = None

        if art_url:
            self._load_art(art_url)

    def _load_art(self, art_url: str) -> None:
        # Check if local file or image cached
        try:
            from network.image_cache import get_cached_pixmap

            cached = get_cached_pixmap(art_url)
            if cached and not cached.isNull():
                self._pixmap = cached
                self.update()
                return
        except Exception:
            pass

    def paintEvent(self, a0: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0.5, 0.5, 33.0, 33.0)

        if self._pixmap and not self._pixmap.isNull():
            # Draw rounded cropped image
            painter.setBrush(QColor(18, 20, 32))
            painter.setPen(QPen(QColor(255, 255, 255, 25), 1.0))
            painter.drawRoundedRect(rect, 6.0, 6.0)

            scaled = self._pixmap.scaled(
                34,
                34,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Center crop
            cx = (scaled.width() - 34) // 2
            cy = (scaled.height() - 34) // 2
            cropped = scaled.copy(cx, cy, 34, 34)

            # Paint with clip path
            painter.save()
            from PyQt6.QtGui import QPainterPath

            path = QPainterPath()
            path.addRoundedRect(rect, 6.0, 6.0)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, cropped)
            painter.restore()
        else:
            # Fallback Cyber-Moe stylized note thumbnail
            painter.setBrush(QColor(236, 24, 108, 30))
            painter.setPen(QPen(QColor(236, 24, 108, 70), 1.0))
            painter.drawRoundedRect(rect, 6.0, 6.0)

            accent = QColor("#EC186C")
            pen = QPen(accent, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            # Music note glyph
            painter.drawLine(QPointF(14.0, 20.0), QPointF(14.0, 11.0))
            painter.drawLine(QPointF(14.0, 11.0), QPointF(21.0, 9.0))
            painter.drawLine(QPointF(21.0, 9.0), QPointF(21.0, 18.0))
            painter.setBrush(QColor("#EC186C"))
            painter.drawEllipse(QPointF(12.5, 20.0), 2.5, 2.0)
            painter.drawEllipse(QPointF(19.5, 18.0), 2.5, 2.0)

        painter.end()


class SongHistoryRowWidget(QWidget):
    """Row displaying a single song entry with thumbnail, titles, and quick action buttons."""

    def __init__(
        self,
        entry: SongHistoryEntry,
        i18n: I18n,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.entry = entry
        self.i18n = i18n
        self._hovered = False
        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # 1. Artwork Thumbnail
        self.thumb = _TrackThumbnail(entry.art_url, self)
        layout.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignVCenter)

        # 2. Text Column (Title & Artist/Station)
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self.lbl_title = _ElidedLabel(entry.title or "Unknown Track", self)
        self.lbl_title.setStyleSheet(
            "color: #ffffff; font-size: 12px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(self.lbl_title)

        sub_info = f"{entry.artist}" if entry.artist else ""
        if entry.station_name:
            sub_info = f"{sub_info} · {entry.station_name}" if sub_info else entry.station_name

        self.lbl_artist = _ElidedLabel(sub_info, self)
        self.lbl_artist.setStyleSheet(
            "color: #94a3b8; font-size: 11px; font-weight: 400; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(self.lbl_artist)
        layout.addLayout(text_col, 1)

        # 3. Timestamp
        self.lbl_time = QLabel(entry.display_time)
        self.lbl_time.setStyleSheet(
            "color: #64748b; font-size: 10px; font-weight: 500; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self.lbl_time, 0, Qt.AlignmentFlag.AlignVCenter)

        # 4. Quick Action Buttons (Spotify, YouTube, Copy)
        actions_box = QHBoxLayout()
        actions_box.setContentsMargins(0, 0, 0, 0)
        actions_box.setSpacing(4)

        # Spotify Button
        self.btn_spotify = QPushButton(self)
        self.btn_spotify.setIcon(get_spotify_icon(14))
        self.btn_spotify.setIconSize(QSize(14, 14))
        self.btn_spotify.setFixedSize(24, 24)
        self.btn_spotify.setToolTip(self.i18n.t("search_spotify"))
        self.btn_spotify.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_spotify.setStyleSheet(
            "QPushButton { background: rgba(30, 215, 96, 0.12); "
            "border: 1px solid rgba(30, 215, 96, 0.32); border-radius: 6px; padding: 0; }\n"
            "QPushButton:hover { background: rgba(30, 215, 96, 0.28); "
            "border-color: rgba(30, 215, 96, 0.65); }"
        )
        self.btn_spotify.clicked.connect(lambda: search_spotify(entry.title, entry.artist))
        actions_box.addWidget(self.btn_spotify)

        # YouTube Button
        self.btn_youtube = QPushButton(self)
        self.btn_youtube.setIcon(get_youtube_icon(14))
        self.btn_youtube.setIconSize(QSize(14, 14))
        self.btn_youtube.setFixedSize(24, 24)
        self.btn_youtube.setToolTip(self.i18n.t("search_youtube"))
        self.btn_youtube.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_youtube.setStyleSheet(
            "QPushButton { background: rgba(255, 0, 0, 0.12); "
            "border: 1px solid rgba(255, 0, 0, 0.32); border-radius: 6px; padding: 0; }\n"
            "QPushButton:hover { background: rgba(255, 0, 0, 0.28); "
            "border-color: rgba(255, 0, 0, 0.65); }"
        )
        self.btn_youtube.clicked.connect(lambda: search_youtube(entry.title, entry.artist))
        actions_box.addWidget(self.btn_youtube)

        # Copy Button
        self.btn_copy = QPushButton(self)
        self.btn_copy.setIcon(get_copy_icon(14))
        self.btn_copy.setIconSize(QSize(14, 14))
        self.btn_copy.setFixedSize(24, 24)
        self.btn_copy.setToolTip(self.i18n.t("copy_formatted"))
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setStyleSheet(
            "QPushButton { background: rgba(255, 255, 255, 0.06); "
            "border: 1px solid rgba(255, 255, 255, 0.18); border-radius: 6px; padding: 0; }\n"
            "QPushButton:hover { background: rgba(255, 255, 255, 0.18); "
            "border-color: rgba(255, 255, 255, 0.45); }"
        )
        self.btn_copy.clicked.connect(self._on_copy_clicked)
        actions_box.addWidget(self.btn_copy)

        layout.addLayout(actions_box)

    def _on_copy_clicked(self) -> None:
        copy_to_clipboard(self.entry.formatted_title)
        QToolTip.showText(
            self.btn_copy.mapToGlobal(QPoint(0, self.btn_copy.height())),
            self.i18n.t("copied_feedback"),
            self.btn_copy,
        )

    def enterEvent(self, event: object) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)  # type: ignore[arg-type]

    def leaveEvent(self, a0: object) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(a0)  # type: ignore[arg-type]

    def paintEvent(self, a0: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(2.0, 2.0, float(self.width()) - 4.0, float(self.height()) - 4.0)

        if self._hovered:
            painter.setBrush(QColor(236, 24, 108, 22))
            painter.setPen(QPen(QColor(236, 24, 108, 60), 1.0))
            painter.drawRoundedRect(rect, 8.0, 8.0)
        else:
            painter.setBrush(QColor(255, 255, 255, 4))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 8.0, 8.0)

        painter.end()


class SongHistoryPopover(QWidget):
    """Frameless translucent Cyber-Glass popover displaying session song history."""

    closed = pyqtSignal()

    def __init__(
        self,
        history_manager: SongHistoryManager,
        parent: QWidget | None = None,
        i18n: I18n | None = None,
    ) -> None:
        flags = (
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.history_manager = history_manager
        self.i18n = i18n or (getattr(parent, "i18n", None) if parent else None) or I18n("it")

        self._anim_group: QParallelAnimationGroup | None = None
        self._is_closing = False
        self._closed_emitted = False

        self.setFixedSize(390, 420)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.setSpacing(6)

        # 1. Header Bar: Title + Count Badge + Clear Button
        header_row = QHBoxLayout()
        header_row.setContentsMargins(6, 4, 6, 4)
        header_row.setSpacing(8)

        self.lbl_header = QLabel(self.i18n.t("history_title"))
        self.lbl_header.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        header_row.addWidget(self.lbl_header)

        self.badge_count = QLabel("")
        self.badge_count.setStyleSheet(
            "color: #ff5ca8; background: rgba(236, 24, 108, 0.18); "
            "border: 1px solid rgba(236, 24, 108, 0.4); border-radius: 9px; "
            "padding: 1px 7px; font-size: 10px; font-weight: 600;"
        )
        header_row.addWidget(self.badge_count)
        header_row.addStretch(1)

        self.btn_clear = QPushButton(self.i18n.t("history_clear"))
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setStyleSheet(
            "QPushButton { background: rgba(255, 255, 255, 0.06); color: #94a3b8; "
            "border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; "
            "padding: 3px 9px; font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { background: rgba(225, 29, 72, 0.22); color: #fda4af; "
            "border-color: rgba(225, 29, 72, 0.5); }"
        )
        self.btn_clear.clicked.connect(self._on_clear_clicked)
        header_row.addWidget(self.btn_clear)
        outer_layout.addLayout(header_row)

        # Subtle separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); margin: 0 4px;")
        outer_layout.addWidget(sep)

        # 2. Scroll Area containing track list
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }"
            "QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.18); "
            "border-radius: 3px; min-height: 20px; }"
            "QScrollBar::handle:vertical:hover { background: rgba(236, 24, 108, 0.6); }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(2, 4, 2, 4)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch(1)

        self.scroll_area.setWidget(self.list_container)
        outer_layout.addWidget(self.scroll_area, 1)

        # Connect history updates
        self.history_manager.entry_added.connect(self._refresh_list)
        self.history_manager.history_cleared.connect(self._refresh_list)

        self._refresh_list()

    def _refresh_list(self) -> None:
        """Repopulate the scrollable list from the history manager."""
        # Clear existing items
        while self.list_layout.count() > 0:
            item = self.list_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()

        entries = self.history_manager.get_entries()
        count = len(entries)
        self.badge_count.setText(f"{count}")
        self.btn_clear.setEnabled(count > 0)

        if count == 0:
            # Empty state
            empty_lbl = QLabel(self.i18n.t("history_empty"))
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setWordWrap(True)
            empty_lbl.setStyleSheet(
                "color: #64748b; font-size: 12px; font-weight: 500; padding: 40px 16px; "
                "background: transparent; border: none;"
            )
            self.list_layout.addWidget(empty_lbl)
            self.list_layout.addStretch(1)
            return

        for entry in entries:
            row = SongHistoryRowWidget(entry, self.i18n, self.list_container)
            self.list_layout.addWidget(row)

        self.list_layout.addStretch(1)

    def _on_clear_clicked(self) -> None:
        self.history_manager.clear()

    def open_at(self, target_pos: QPoint) -> None:
        """Position and smoothly animate popover entrance."""
        self._is_closing = False
        self._closed_emitted = False

        self._refresh_list()

        start_pos = QPoint(target_pos.x(), target_pos.y() - 10)
        self.move(start_pos)
        self.setWindowOpacity(0.0)
        self.show()

        if self._anim_group and self._anim_group.state() == QParallelAnimationGroup.State.Running:
            self._anim_group.stop()

        group = QParallelAnimationGroup(self)

        anim_pos = QPropertyAnimation(self, b"pos", group)
        anim_pos.setDuration(190)
        anim_pos.setStartValue(start_pos)
        anim_pos.setEndValue(target_pos)
        anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

        anim_op = QPropertyAnimation(self, b"windowOpacity", group)
        anim_op.setDuration(180)
        anim_op.setStartValue(0.0)
        anim_op.setEndValue(1.0)
        anim_op.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_group = group
        group.start()

    def _animate_exit(self, callback: Callable[[], None] | None = None) -> None:
        """Smooth slide-up & fade exit animation."""
        if self._is_closing:
            return
        self._is_closing = True

        if not self.isVisible():
            if not self._closed_emitted:
                self._closed_emitted = True
                self.closed.emit()
            if callback:
                callback()
            return

        if self._anim_group and self._anim_group.state() == QParallelAnimationGroup.State.Running:
            self._anim_group.stop()

        group = QParallelAnimationGroup(self)

        anim_pos = QPropertyAnimation(self, b"pos", group)
        anim_pos.setDuration(120)
        anim_pos.setStartValue(self.pos())
        anim_pos.setEndValue(QPoint(self.x(), self.y() - 8))
        anim_pos.setEasingCurve(QEasingCurve.Type.InCubic)

        anim_op = QPropertyAnimation(self, b"windowOpacity", group)
        anim_op.setDuration(120)
        anim_op.setStartValue(self.windowOpacity())
        anim_op.setEndValue(0.0)
        anim_op.setEasingCurve(QEasingCurve.Type.InCubic)

        def _finish() -> None:
            self.close()
            if not self._closed_emitted:
                self._closed_emitted = True
                self.closed.emit()
            if callback:
                callback()

        group.finished.connect(_finish)
        self._anim_group = group
        group.start()

    def hideEvent(self, a0: object) -> None:
        if not self._closed_emitted:
            self._closed_emitted = True
            self.closed.emit()
        super().hideEvent(a0)  # type: ignore[arg-type]

    def keyPressEvent(self, a0: QKeyEvent | None) -> None:
        if a0 is not None and a0.key() == Qt.Key.Key_Escape:
            self._animate_exit()
            return
        super().keyPressEvent(a0)

    def paintEvent(self, a0: object) -> None:
        """Draw sleek Cyber-Moe glass surface with antialiasing."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0.5, 0.5, float(self.width()) - 1.0, float(self.height()) - 1.0)

        # Dark glass fill
        painter.setBrush(QColor(12, 14, 23, 245))
        # Illuminated border with accent tint
        painter.setPen(QPen(QColor(236, 24, 108, 90), 1.0))
        painter.drawRoundedRect(rect, 12.0, 12.0)

        painter.end()
