"""Cyber-Pill Station Selector and Glass Menu for KikuMoe.

Provides a centered, sleek, glassmorphic pill button in the HUD header
that opens a custom popover menu for switching radio stations and channels.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QCursor, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
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
                background-color: #151724;
                border: 1px solid rgba(236, 24, 108, 0.35);
                border-radius: 12px;
                padding: 6px 4px;
            }}
            QMenu::item {{
                padding: 7px 24px 7px 12px;
                border-radius: 7px;
                color: #F1F3F9;
                font-size: 11px;
                font-weight: 500;
                margin: 2px 4px;
            }}
            QMenu::item:selected {{
                background-color: rgba(236, 24, 108, 0.28);
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


class StationPillButton(QFrame):
    """Sleek Cyber-Pill button displayed centrally in the HUD top bar."""

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

        self._accent = PALETTE.get("accent", "#EC186C")
        self._hovered = False
        self._menu: StationGlassMenu | None = None

        self.setFixedHeight(28)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip("Cambia stazione radio")

        # Layout: [Icon 16x16] [Spacing] [Title Label] [Spacing] [Chevron]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(6)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(16, 16)
        self._icon_label.setScaledContents(True)

        self._title_label = QLabel()
        font = QFont()
        font.setPointSize(10)
        font.setWeight(QFont.Weight.DemiBold)
        self._title_label.setFont(font)
        self._title_label.setStyleSheet("color: #FFFFFF; background: transparent;")

        self._chevron_label = QLabel("▾")
        chevron_font = QFont()
        chevron_font.setPointSize(9)
        self._chevron_label.setFont(chevron_font)
        self._chevron_label.setStyleSheet(
            "color: rgba(255, 255, 255, 0.60); background: transparent;"
        )

        layout.addWidget(self._icon_label)
        layout.addWidget(self._title_label)
        layout.addWidget(self._chevron_label)

        self._update_appearance()

    def update_state(self, station_id: str, channel: str | None = None) -> None:
        """Updates the active station and channel label/icon."""
        self._current_station = (station_id or DEFAULT_STATION).lower().strip()
        if channel:
            self._current_channel = channel.strip()
        self._update_appearance()

    def get_current_station(self) -> str:
        return self._current_station

    def get_current_channel(self) -> str:
        return self._current_channel

    def get_display_title(self) -> str:
        return self._title_label.text()

    def _get_icon_pixmap(self, filename: str) -> QPixmap:
        if self._icon_dir and filename:
            path = os.path.join(self._icon_dir, filename)
            if os.path.isfile(path):
                pm = QPixmap(path)
                if not pm.isNull():
                    return pm
        # Fallback 16x16 transparent pixmap
        pm = QPixmap(16, 16)
        pm.fill(Qt.GlobalColor.transparent)
        return pm

    def _update_appearance(self) -> None:
        cfg = get_station_config(self._current_station)
        icon_file = cfg.get("icon", "listen.png")

        if self._current_station == STATION_LISTENMOE:
            title = f"LISTEN.moe · {self._current_channel}"
        else:
            title = cfg.get("name", self._current_station)

        self._title_label.setText(title)
        pix = self._get_icon_pixmap(icon_file)
        self._icon_label.setPixmap(
            pix.scaled(
                16,
                16,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        bg = "rgba(255, 255, 255, 0.14)" if self._hovered else "rgba(255, 255, 255, 0.07)"
        border = (
            "1px solid rgba(236, 24, 108, 0.55)"
            if self._hovered
            else "1px solid rgba(255, 255, 255, 0.12)"
        )
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {bg};
                border: {border};
                border-radius: 14px;
            }}
            """
        )

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._chevron_label.setStyleSheet("color: #FFFFFF; background: transparent;")
        self._update_appearance()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._chevron_label.setStyleSheet(
            "color: rgba(255, 255, 255, 0.60); background: transparent;"
        )
        self._update_appearance()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._show_station_menu()
        super().mousePressEvent(event)

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
