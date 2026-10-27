"""Cyber-Pill Station Selector and Glass Popover for KikuMoe.

Provides a centered, sleek, dark cyber-glass pill button in the HUD header
that opens an antialiased, perfectly centered popover card for switching stations and channels.
Features inline channel chips for multi-channel stations (e.g. LISTEN.moe J-POP / K-POP)
without repeating station entries or truncating text.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Callable

from PyQt6.QtCore import (  # type: ignore[attr-defined]
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.config import STATIONS, get_station_config
from core.constants import (
    DEFAULT_STATION,
    STATION_LISTENMOE,
)
from ui.themes.cyber_moe import PALETTE

_IS_LINUX = sys.platform.startswith("linux")


class ChannelChip(QPushButton):
    """Mini pill chip for selecting a subchannel (e.g. J-POP / K-POP) inside a station row."""

    def __init__(self, channel: str, is_active: bool, parent: QWidget | None = None) -> None:
        super().__init__(channel, parent)
        self.channel = channel
        self.is_active = is_active
        self._hovered = False

        self.setFixedHeight(22)
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        self.setFont(font)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

    def set_active(self, active: bool) -> None:
        self.is_active = active
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
        if self.is_active:
            bg = "#EC186C"
            fg = "#FFFFFF"
            border = "1px solid #EC186C"
            hover_bg = "#FD3585"
            pressed_bg = "#C70E55"
        elif self._hovered:
            bg = "rgba(255, 255, 255, 0.18)"
            fg = "#FFFFFF"
            border = "1px solid rgba(255, 255, 255, 0.40)"
            hover_bg = "rgba(255, 255, 255, 0.22)"
            pressed_bg = "rgba(236, 24, 108, 0.35)"
        else:
            bg = "rgba(255, 255, 255, 0.08)"
            fg = "#B0B7C9"
            border = "1px solid rgba(255, 255, 255, 0.12)"
            hover_bg = "rgba(255, 255, 255, 0.18)"
            pressed_bg = "rgba(236, 24, 108, 0.35)"

        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: {border};
                border-radius: 11px;
                padding: 0 8px;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: {pressed_bg};
            }}
            """
        )


class StationRowWithChannels(QWidget):
    """Station row that features inline channel chips on the right."""

    channel_selected = pyqtSignal(str, str)  # (station_id, channel)

    def __init__(
        self,
        station_id: str,
        name: str,
        channels: list[str],
        current_station: str,
        current_channel: str,
        icon_pm: QPixmap,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.station_id = station_id
        self.is_current_station = current_station == station_id
        self.current_channel = current_channel
        self._hovered = False

        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        # Left clickable container (Icon + Name)
        self._left_btn = QPushButton(self)
        self._left_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        left_layout = QHBoxLayout(self._left_btn)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(16, 16)
        icon_lbl.setScaledContents(True)
        icon_lbl.setPixmap(icon_pm)
        icon_lbl.setStyleSheet("background: transparent; border: none;")

        title_lbl = QLabel(name)
        font = QFont()
        font.setPointSize(9)
        font.setBold(self.is_current_station)
        title_lbl.setFont(font)
        fg_col = "#EC186C" if self.is_current_station else "#E6EAF8"
        title_lbl.setStyleSheet(f"color: {fg_col}; background: transparent; border: none;")

        left_layout.addWidget(icon_lbl)
        left_layout.addWidget(title_lbl)
        left_layout.addStretch(1)

        self._left_btn.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self._left_btn.clicked.connect(
            lambda _: self.channel_selected.emit(self.station_id, self.current_channel or "J-POP")
        )

        layout.addWidget(self._left_btn, 1)

        # Inline Channel Chips
        for ch in channels:
            is_active = self.is_current_station and (self.current_channel == ch)
            chip = ChannelChip(ch, is_active, self)
            chip.clicked.connect(lambda _, c=ch: self.channel_selected.emit(self.station_id, c))
            layout.addWidget(chip)


class SimpleStationRow(QPushButton):
    """Clean row for stations without subchannels."""

    def __init__(
        self,
        station_id: str,
        title: str,
        icon_pm: QPixmap,
        is_selected: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.station_id = station_id
        self.is_selected = is_selected
        self._hovered = False

        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

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
        elif self.is_selected:
            bg = "rgba(255, 255, 255, 0.05)"
        else:
            bg = "transparent"

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
    native Windows QMenu black corner artifacts. Features smooth entrance
    drop-in and exit fade animations.
    """

    station_selected = pyqtSignal(str, str)  # (station_id, channel)
    closed = pyqtSignal()

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

        self._anim_group: QParallelAnimationGroup | None = None
        self._is_closing = False
        self._closed_emitted = False

        self.setFixedWidth(240)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(2)

        # 1. Multi-channel stations (e.g. LISTEN.moe with J-POP / K-POP)
        cfg_listen = STATIONS.get(STATION_LISTENMOE, {})
        pm_listen = self._get_icon_pm(str(cfg_listen.get("icon", "listen.png")))
        channels_listen = list(cfg_listen.get("channels", ["J-POP", "K-POP"]))
        row_listen = StationRowWithChannels(
            station_id=STATION_LISTENMOE,
            name="LISTEN.moe",
            channels=channels_listen,
            current_station=current_station,
            current_channel=current_channel,
            icon_pm=pm_listen,
            parent=self,
        )
        row_listen.channel_selected.connect(self._on_select)
        main_layout.addWidget(row_listen)

        # Subtle separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); margin: 3px 6px;")
        main_layout.addWidget(sep)

        # 2. Other stations (Gensokyo, ANISON, etc.)
        for st_id, st_cfg in STATIONS.items():
            if st_id == STATION_LISTENMOE:
                continue
            has_channels = bool(st_cfg.get("has_channels", False))
            channels = list(st_cfg.get("channels", []))
            pm = self._get_icon_pm(str(st_cfg.get("icon", "listen.png")))
            name = str(st_cfg.get("name", st_id))

            if has_channels and channels:
                row_multi = StationRowWithChannels(
                    station_id=st_id,
                    name=name,
                    channels=channels,
                    current_station=current_station,
                    current_channel=current_channel,
                    icon_pm=pm,
                    parent=self,
                )
                row_multi.channel_selected.connect(self._on_select)
                main_layout.addWidget(row_multi)
            else:
                is_sel = current_station == st_id
                row_simple = SimpleStationRow(
                    station_id=st_id,
                    title=name,
                    icon_pm=pm,
                    is_selected=is_sel,
                    parent=self,
                )
                row_simple.clicked.connect(lambda _, s=st_id: self._on_select(s, "J-POP"))
                main_layout.addWidget(row_simple)

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

    def _on_select(self, station_id: str, channel: str) -> None:
        if self._is_closing:
            return
        self.animate_close()
        self.station_selected.emit(station_id, channel)

    def show_at(self, center_x: int, y: int) -> None:
        """Position and show popover centered at center_x with drop-in and fade animation."""
        self.adjustSize()
        w = self.width()
        target_x = center_x - (w // 2)
        target_y = y
        screen = QGuiApplication.screenAt(QPoint(center_x, y)) or QGuiApplication.primaryScreen()
        if screen is not None:
            bounds = screen.availableGeometry()
            target_x = max(bounds.left(), min(target_x, bounds.right() - w + 1))
            target_y = max(bounds.top(), min(target_y, bounds.bottom() - self.height() + 1))
        if _IS_LINUX:
            self.move(target_x, target_y)
            self.setWindowOpacity(1.0)
            self.show()
            return
        start_y = target_y - 10

        self.move(target_x, start_y)
        self.setWindowOpacity(0.0)
        self.show()

        if self._anim_group and self._anim_group.state() == QParallelAnimationGroup.State.Running:
            self._anim_group.stop()

        group = QParallelAnimationGroup(self)
        anim_pos = QPropertyAnimation(self, b"pos", group)
        anim_pos.setDuration(190)
        anim_pos.setStartValue(QPoint(target_x, start_y))
        anim_pos.setEndValue(QPoint(target_x, target_y))
        anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

        anim_op = QPropertyAnimation(self, b"windowOpacity", group)
        anim_op.setDuration(180)
        anim_op.setStartValue(0.0)
        anim_op.setEndValue(1.0)
        anim_op.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_group = group
        group.start()

    def animate_close(self, callback: Callable[[], None] | None = None) -> None:
        """Smoothly fade out and slide up before closing."""
        if self._is_closing:
            return
        self._is_closing = True

        if _IS_LINUX:
            self.close()
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
            if callback:
                callback()

        group.finished.connect(_finish)
        self._anim_group = group
        group.start()

    def _emit_closed(self) -> None:
        if not self._closed_emitted:
            self._closed_emitted = True
            self.closed.emit()

    def hideEvent(self, event) -> None:
        self._emit_closed()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._emit_closed()
        super().closeEvent(event)

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
        self._chevron_angle: float = 0.0
        self._chevron_anim: QPropertyAnimation | None = None
        self._menu_open: bool = False
        self._last_close_time: float = 0.0

        self._height = 28
        self.setFixedHeight(self._height)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setToolTip("Cambia stazione radio")
        self._pixmap_cache: dict[str, QPixmap] = {}
        self.setFixedWidth(self.sizeHint().width())

    def get_chevron_angle(self) -> float:
        return self._chevron_angle

    def set_chevron_angle(self, val: float) -> None:
        self._chevron_angle = val
        self.update()

    chevron_angle = pyqtProperty(float, get_chevron_angle, set_chevron_angle)

    def _animate_chevron(self, target_angle: float) -> None:
        if self._chevron_anim and self._chevron_anim.state() == QPropertyAnimation.State.Running:
            self._chevron_anim.stop()
        anim = QPropertyAnimation(self, b"chevron_angle")
        anim.setDuration(180)
        anim.setStartValue(self._chevron_angle)
        anim.setEndValue(target_angle)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._chevron_anim = anim
        anim.start()

    def update_state(self, station_id: str, channel: str | None = None) -> None:
        """Updates the active station and channel label/icon."""
        self._current_station = (station_id or DEFAULT_STATION).lower().strip()
        if channel:
            self._current_channel = channel.strip()
        self.setFixedWidth(self.sizeHint().width())
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
        # Symmetrical pill: 11 (left) + 16 (icon) + 7 (gap)
        # + text_w + 8 (gap) + 7 (chevron) + 11 (right)
        total_w = 11 + 16 + 7 + text_w + 8 + 7 + 11
        return QSize(total_w, self._height)

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
        if self._pressed or self._menu_open:
            bg = QColor(24, 26, 40, 245)
            border = self._accent
            fg = QColor("#ffffff")
            chevron_col = self._accent
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
        pad = 11.0
        gap_icon_text = 7.0
        gap_text_chev = 8.0

        cfg = get_station_config(self._current_station)
        icon_file = str(cfg.get("icon", "listen.png"))
        pix = self._get_icon_pixmap(icon_file)
        icon_x = pad
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
        text_x = icon_x + 16.0 + gap_icon_text
        text_y = (h + fm.ascent() - fm.descent()) / 2.0
        painter.drawText(QPointF(text_x, text_y), title)

        # 4. Smooth animated vector chevron (rotates 0° -> 180° when open)
        chev_center_x = text_x + text_w + gap_text_chev + 3.5
        chev_center_y = h / 2.0
        painter.save()
        painter.translate(chev_center_x, chev_center_y)
        painter.rotate(self._chevron_angle)
        pen = QPen(
            chevron_col,
            1.6,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(pen)
        chev_path = QPainterPath()
        chev_path.moveTo(-3.5, -1.8)
        chev_path.lineTo(0.0, 2.2)
        chev_path.lineTo(3.5, -1.8)
        painter.drawPath(chev_path)
        painter.restore()

        painter.end()

    def _show_station_menu(self) -> None:
        if time.monotonic() - self._last_close_time < 0.25:
            return

        if self._menu_open and self._popover is not None and self._popover.isVisible():
            self._popover.animate_close()
            return

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
        self._menu_open = True
        self._animate_chevron(180.0)
        self.update()

        popover.station_selected.connect(self._on_popover_station_selected)
        popover.closed.connect(lambda: self._on_popover_closed(popover))
        popover.show_at(center_x=center_x, y=target_y)

    def _on_popover_closed(self, popover: StationGlassPopover) -> None:
        if self._popover is not popover:
            return
        self._popover = None
        popover.deleteLater()
        self._menu_open = False
        self._last_close_time = time.monotonic()
        self._animate_chevron(0.0)
        self.update()

    def _on_popover_station_selected(self, station_id: str, channel: str) -> None:
        self.station_selected.emit(station_id, channel)
