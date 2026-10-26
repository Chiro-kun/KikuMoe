"""Cyber-Pill Station Selector and Glass Menu for KikuMoe.

Provides a centered, sleek, dark cyber-glass pill button in the HUD header
that opens a custom popover menu for switching radio stations and channels.
Rendered via QPainter for pixel-perfect antialiasing without child widget bounding boxes.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QMenu,
    QWidget,
)

from core.config import STATIONS, get_station_config
from core.constants import (
    DEFAULT_STATION,
    STATION_LISTENMOE,
)
from ui.themes.cyber_moe import PALETTE


class StationGlassMenu(QMenu):
    """Custom styled glass popover menu for radio stations."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        accent = PALETTE.get("accent", "#EC186C")
        border_subtle = PALETTE.get("border_subtle", "rgba(255, 255, 255, 0.10)")

        self.setStyleSheet(
            f"""
            QMenu {{
                background-color: #141624;
                border: 1px solid rgba(236, 24, 108, 0.40);
                border-radius: 10px;
                padding: 6px 4px;
            }}
            QMenu::item {{
                padding: 7px 24px 7px 12px;
                border-radius: 6px;
                color: #F1F3F9;
                font-size: 11px;
                font-weight: 500;
                margin: 2px 4px;
            }}
            QMenu::item:selected {{
                background-color: rgba(236, 24, 108, 0.30);
                color: #FFFFFF;
            }}
            QMenu::item:checked {{
                font-weight: 700;
                color: {accent};
            }}
            QMenu::separator {{
                height: 1px;
                background: {border_subtle};
                margin: 4px 8px;
            }}
            """
        )


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
        self._menu: StationGlassMenu | None = None

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
        menu = StationGlassMenu(self)
        self._menu = menu

        # 1. LISTEN.moe channels
        cfg_listen = STATIONS.get(STATION_LISTENMOE, {})
        icon_listen = QIcon(self._get_icon_pixmap(str(cfg_listen.get("icon", "listen.png"))))
        for ch in cfg_listen.get("channels", ["J-POP", "K-POP"]):
            act = QAction(icon_listen, f"LISTEN.moe · {ch}", menu)
            act.setCheckable(True)
            act.setChecked(
                self._current_station == STATION_LISTENMOE and self._current_channel == ch
            )
            act.setData((STATION_LISTENMOE, ch))
            menu.addAction(act)

        menu.addSeparator()

        # 2. Other stations catalog
        for st_id, st_cfg in STATIONS.items():
            if st_id == STATION_LISTENMOE:
                continue
            icon = QIcon(self._get_icon_pixmap(str(st_cfg.get("icon", "listen.png"))))
            act = QAction(icon, str(st_cfg.get("name", st_id)), menu)
            act.setCheckable(True)
            act.setChecked(self._current_station == st_id)
            act.setData((st_id, "J-POP"))
            menu.addAction(act)

        # Popup positioning directly beneath the pill button
        menu_pos = self.mapToGlobal(QPoint(0, self.height() + 4))
        selected = menu.exec(menu_pos)

        if selected:
            data = selected.data()
            if isinstance(data, tuple) and len(data) == 2:
                target_st, target_ch = data
                self.station_selected.emit(str(target_st), str(target_ch))
