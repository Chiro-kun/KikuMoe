"""Cyber-Pill Station Selector and Glass Popover for KikuMoe.

Provides a centered, sleek, dark cyber-glass pill button in the HUD header
that opens an antialiased, perfectly centered popover card for switching stations and channels.
Eliminates Qt QMenu Windows black corner artifacts and ensures flawless symmetry.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import STATIONS, get_station_config
from core.constants import (
    DEFAULT_STATION,
    STATION_LISTENMOE,
)
from ui.themes.cyber_moe import PALETTE


class StationPopoverRow(QPushButton):
    """Interactive row inside the station popover with icon, title, and checkmark."""

    def __init__(
        self,
        station_id: str,
        channel: str,
        title: str,
        icon_pm: QPixmap,
        is_selected: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.station_id = station_id
        self.channel = channel
        self.is_selected = is_selected
        self._hovered = False

        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(9)

        # Icon
        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(16, 16)
        self._icon_lbl.setScaledContents(True)
        self._icon_lbl.setPixmap(icon_pm)
        self._icon_lbl.setStyleSheet("background: transparent; border: none;")

        # Title
        self._title_lbl = QLabel(title)
        font = QFont()
        font.setPointSize(9)
        font.setBold(is_selected)
        self._title_lbl.setFont(font)
        color = "#EC186C" if is_selected else "#E6EAF8"
        self._title_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")

        layout.addWidget(self._icon_lbl)
        layout.addWidget(self._title_lbl, 1)

        # Checkmark
        if is_selected:
            self._check_lbl = QLabel("✔")
            self._check_lbl.setStyleSheet(
                "color: #EC186C; font-size: 11px; font-weight: bold; "
                "background: transparent; border: none;"
            )
            layout.addWidget(self._check_lbl)

        self._update_style()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._update_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._update_style()
        super().leaveEvent(event)

    def _update_style(self) -> None:
        if self._hovered:
            bg = "rgba(236, 24, 108, 0.22)"
            txt_color = "#FFFFFF"
        elif self.is_selected:
            bg = "rgba(255, 255, 255, 0.05)"
            txt_color = "#EC186C"
        else:
            bg = "transparent"
            txt_color = "#E6EAF8"

        self._title_lbl.setStyleSheet(f"color: {txt_color}; background: transparent; border: none;")
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {bg};
                border: none;
                border-radius: 6px;
                text-align: left;
            }}
            """
        )


class StationGlassPopover(QWidget):
    """Frameless translucent popover card for radio station selection.

    Rendered with direct QPainter antialiasing, completely eliminating
    native Windows QMenu black corner artifacts.
    """

    station_selected = pyqtSignal(str, str)  # (station_id, channel)

    def __init__(
        self,
        current_station: str,
        current_channel: str,
        parent: QWidget | None = None,
        icon_dir: str | None = None,
    ) -> None:
        flags = (
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.current_station = current_station
        self.current_channel = current_channel
        self.icon_dir = (
            icon_dir
            if icon_dir and os.path.isdir(icon_dir)
            else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "icons")
        )

        self.setFixedWidth(192)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(2)

        # 1. LISTEN.moe channels
        cfg_listen = STATIONS.get(STATION_LISTENMOE, {})
        pm_listen = self._get_icon_pm(str(cfg_listen.get("icon", "listen.png")))
        for ch in cfg_listen.get("channels", ["J-POP", "K-POP"]):
            is_sel = current_station == STATION_LISTENMOE and current_channel == ch
            row = StationPopoverRow(
                station_id=STATION_LISTENMOE,
                channel=ch,
                title=f"LISTEN.moe · {ch}",
                icon_pm=pm_listen,
                is_selected=is_sel,
                parent=self,
            )
            row.clicked.connect(lambda _, c=ch: self._on_row_clicked(STATION_LISTENMOE, c))
            main_layout.addWidget(row)

        # Subtle separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); margin: 3px 6px;")
        main_layout.addWidget(sep)

        # 2. Other stations
        for st_id, st_cfg in STATIONS.items():
            if st_id == STATION_LISTENMOE:
                continue
            pm = self._get_icon_pm(str(st_cfg.get("icon", "listen.png")))
            is_sel = current_station == st_id
            name = str(st_cfg.get("name", st_id))
            row = StationPopoverRow(
                station_id=st_id,
                channel="J-POP",
                title=name,
                icon_pm=pm,
                is_selected=is_sel,
                parent=self,
            )
            row.clicked.connect(lambda _, s=st_id: self._on_row_clicked(s, "J-POP"))
            main_layout.addWidget(row)

    def _get_icon_pm(self, filename: str) -> QPixmap:
        if self.icon_dir and filename:
            p = os.path.join(self.icon_dir, filename)
            if os.path.isfile(p):
                pm = QPixmap(p)
                if not pm.isNull():
                    return pm.scaled(
                        16,
                        16,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
        fallback = QPixmap(16, 16)
        fallback.fill(Qt.GlobalColor.transparent)
        return fallback

    def _on_row_clicked(self, station_id: str, channel: str) -> None:
        self.station_selected.emit(station_id, channel)
        self.close()

    def show_at(self, center_x: int, y: int) -> None:
        """Position and show popover centered at center_x."""
        self.adjustSize()
        w = self.width()
        target_x = max(8, center_x - (w // 2))
        self.move(target_x, y)
        self.show()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)

        # Solid dark cyber-glass with subtle magenta border
        bg = QColor(18, 20, 32, 245)
        border = QColor(236, 24, 108, 120)

        path = QPainterPath()
        path.addRoundedRect(rect, 10.0, 10.0)

        painter.fillPath(path, bg)
        painter.setPen(QPen(border, 1.0))
        painter.drawPath(path)
        painter.end()


class StationPillButton(QWidget):
    """Sleek Cyber-Pill button displayed centrally in the HUD top bar.

    Matches LiveEqualizerBadge and SettingsIconButton with dark solid cyber-glass,
    custom vector rendering, and zero child widget bounding boxes.
    """

    station_selected = pyqtSignal(str, str)  # (station_id, channel)

    def __init__(
        self,
        parent: QWidget | None = None,
        initial_station: str = DEFAULT_STATION,
        initial_channel: str = "J-POP",
        icon_dir: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._current_station = (initial_station or DEFAULT_STATION).lower().strip()
        self._current_channel = (initial_channel or "J-POP").strip()
        self._icon_dir = (
            icon_dir
            if icon_dir and os.path.isdir(icon_dir)
            else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "icons")
        )

        self._accent = QColor(PALETTE.get("accent", "#EC186C"))
        self._hovered = False
        self._pressed = False
        self._popover: StationGlassPopover | None = None

        self._height = 28
        self.setFixedHeight(self._height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setToolTip("Cambia stazione radio")
        self._pixmap_cache: dict[str, QPixmap] = {}

    def update_state(self, station_id: str, channel: str | None = None) -> None:
        """Updates the active station and channel label/icon."""
        self._current_station = (station_id or DEFAULT_STATION).lower().strip()
        if channel:
            self._current_channel = channel.strip()
        self.updateGeometry()
        self.update()

    def get_current_station(self) -> str:
        return self._current_station

    def get_current_channel(self) -> str:
        return self._current_channel

    def get_display_title(self) -> str:
        if self._current_station == STATION_LISTENMOE:
            return f"LISTEN.moe · {self._current_channel}"
        cfg = get_station_config(self._current_station)
        return str(cfg.get("name", self._current_station))

    def sizeHint(self) -> QSize:
        font = QFont(self.font())
        font.setPointSize(9)
        font.setBold(True)
        fm = QFontMetrics(font)
        title = self.get_display_title()
        text_w = fm.horizontalAdvance(title)
        # 12 (left) + 16 (icon) + 7 (gap) + text_w + 6 (gap) + 8 (chevron) + 12 (right)
        total_w = 12 + 16 + 7 + text_w + 6 + 8 + 12
        return QSize(max(130, total_w), self._height)

    def _get_icon_pixmap(self, filename: str) -> QPixmap:
        if filename in self._pixmap_cache:
            return self._pixmap_cache[filename]
        if self._icon_dir and filename:
            path = os.path.join(self._icon_dir, filename)
            if os.path.isfile(path):
                pm = QPixmap(path)
                if not pm.isNull():
                    scaled = pm.scaled(
                        16,
                        16,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._pixmap_cache[filename] = scaled
                    return scaled
        fallback = QPixmap(16, 16)
        fallback.fill(Qt.GlobalColor.transparent)
        return fallback

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
            self._show_station_menu()
            self._pressed = False
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._pressed:
            self._pressed = False
            self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = float(self.width())
        h = float(self.height())
        radius = h / 2.0

        # Colors matching LiveEqualizerBadge and SettingsIconButton
        if self._pressed:
            bg = QColor(28, 14, 26, 245)
            border = self._accent
            fg = QColor("#ffffff")
            chevron_col = QColor("#ffffff")
        elif self._hovered:
            bg = QColor(24, 26, 40, 240)
            border = self._accent
            fg = QColor("#ffffff")
            chevron_col = QColor("#ffffff")
        else:
            # Solid, dark cyber-glass matching LiveEqualizerBadge
            bg = QColor(14, 16, 26, 215)
            border = QColor(255, 255, 255, 36)
            fg = QColor("#e6eaf8")
            chevron_col = QColor(170, 176, 195)

        # 1. Pill Background & Border (zero child bounding boxes)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), radius, radius)
        painter.fillPath(path, bg)
        painter.setPen(QPen(border, 1.0))
        painter.drawPath(path)

        # 2. Icon (16x16)
        cfg = get_station_config(self._current_station)
        icon_file = str(cfg.get("icon", "listen.png"))
        pix = self._get_icon_pixmap(icon_file)
        icon_x = 11.0
        if not pix.isNull():
            icon_y = (h - float(pix.height())) / 2.0
            painter.drawPixmap(int(icon_x), int(icon_y), pix)

        # 3. Title Text
        font = QFont(self.font())
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(fg)

        title = self.get_display_title()
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(title)
        text_x = icon_x + 16.0 + 7.0
        text_y = (h + fm.ascent() - fm.descent()) / 2.0
        painter.drawText(QPointF(text_x, text_y), title)

        # 4. Chevron (▾)
        chevron_font = QFont(self.font())
        chevron_font.setPointSize(8)
        chevron_font.setBold(False)
        painter.setFont(chevron_font)
        painter.setPen(chevron_col)
        chev_fm = painter.fontMetrics()
        chev_x = text_x + text_w + 6.0
        chev_y = (h + chev_fm.ascent() - chev_fm.descent()) / 2.0 - 0.5
        painter.drawText(QPointF(chev_x, chev_y), "▾")

        painter.end()

    def _show_station_menu(self) -> None:
        pill_global_pos = self.mapToGlobal(QPoint(0, 0))
        center_x = pill_global_pos.x() + (self.width() // 2)
        target_y = pill_global_pos.y() + self.height() + 5

        popover = StationGlassPopover(
            current_station=self._current_station,
            current_channel=self._current_channel,
            parent=self.window(),
            icon_dir=self._icon_dir,
        )
        self._popover = popover
        popover.station_selected.connect(self._on_popover_station_selected)
        popover.show_at(center_x=center_x, y=target_y)

    def _on_popover_station_selected(self, station_id: str, channel: str) -> None:
        self.station_selected.emit(station_id, channel)
