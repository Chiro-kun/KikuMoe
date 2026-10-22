"""
SegmentedSwitch and SettingsIconButton widgets for KikuMoe 2.0.0
Includes smooth 60 FPS sliding pill animation and tactile click bounce + ripple.
"""

import math
from typing import List, Optional

from PyQt6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QPushButton, QWidget

from ui.themes.cyber_moe import PALETTE


class SegmentedSwitch(QWidget):
    selection_changed = pyqtSignal(str)

    def __init__(
        self,
        items: List[str],
        default_index: int = 0,
        parent: Optional[QWidget] = None,
        height: int = 28,
    ):
        super().__init__(parent)
        self._items = items
        self._current_index = max(0, min(default_index, len(items) - 1))
        self._anim_pos = float(self._current_index)
        self._anim_start_pos = float(self._current_index)
        self._hover_index = -1
        self._height = height
        self._accent = QColor(PALETTE["accent"])

        self.setFixedHeight(self._height)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._slide_elapsed = QElapsedTimer()
        self._slide_timer = QTimer(self)
        self._slide_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._slide_timer.setInterval(16)
        self._slide_timer.timeout.connect(self._tick_slide)

    def _tick_slide(self) -> None:
        target = float(self._current_index)
        elapsed = float(self._slide_elapsed.elapsed())
        duration = 180.0
        t = min(1.0, max(0.0, elapsed / duration))
        ease = 1.0 - ((1.0 - t) ** 3)
        self._anim_pos = self._anim_start_pos + (target - self._anim_start_pos) * ease
        if t >= 1.0:
            self._anim_pos = target
            self._slide_timer.stop()
        self.update()

    def set_items(self, items: List[str]) -> None:
        self._items = items
        self._current_index = min(self._current_index, max(0, len(items) - 1))
        self._anim_pos = float(self._current_index)
        self._anim_start_pos = float(self._current_index)
        self.update()

    def set_selected(self, text: str) -> None:
        if text in self._items:
            idx = self._items.index(text)
            if idx != self._current_index:
                self._current_index = idx
                self._anim_start_pos = self._anim_pos
                self._slide_elapsed.start()
                self._slide_timer.start()
                self.update()

    def current_selection(self) -> str:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]
        return ""

    def set_accent_color(self, color_str: str) -> None:
        self._accent = QColor(color_str)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and len(self._items) > 0:
            item_width = self.width() / len(self._items)
            clicked_idx = int(event.position().x() // item_width)
            if 0 <= clicked_idx < len(self._items) and clicked_idx != self._current_index:
                self._current_index = clicked_idx
                self._anim_start_pos = self._anim_pos
                self._slide_elapsed.start()
                self._slide_timer.start()
                self.update()
                self.selection_changed.emit(self._items[clicked_idx])
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if len(self._items) > 0:
            item_width = self.width() / len(self._items)
            hover_idx = int(event.position().x() // item_width)
            if hover_idx != self._hover_index:
                self._hover_index = hover_idx
                self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, a0) -> None:
        self._hover_index = -1
        self.update()
        super().leaveEvent(a0)

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        radius = h / 2.0
        n_items = len(self._items)
        if n_items == 0:
            return

        item_w = w / n_items

        # 1. Background Track (Dark frosted glass pill container for high contrast)
        track_path = QPainterPath()
        track_path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), radius, radius)
        painter.fillPath(track_path, QColor(14, 16, 26, 205))
        painter.setPen(QColor(255, 255, 255, 34))
        painter.drawPath(track_path)

        # 2. Hover Highlight
        if 0 <= self._hover_index < n_items and self._hover_index != self._current_index:
            hover_rect = QRectF(self._hover_index * item_w + 2, 2, item_w - 4, h - 4)
            hover_path = QPainterPath()
            hover_path.addRoundedRect(hover_rect, radius - 2, radius - 2)
            painter.fillPath(hover_path, QColor(255, 255, 255, 16))

        # 3. Animated Sliding Active Indicator Pill
        active_rect = QRectF(self._anim_pos * item_w + 2, 2, item_w - 4, h - 4)
        active_path = QPainterPath()
        active_path.addRoundedRect(active_rect, radius - 2, radius - 2)
        painter.fillPath(active_path, self._accent)

        # 4. Text Labels
        font = QFont(self.font())
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        for i, text in enumerate(self._items):
            cell_rect = QRectF(i * item_w, 0, item_w, h)
            if i == self._current_index:
                painter.setPen(QColor("#ffffff"))
            elif i == self._hover_index:
                painter.setPen(QColor("#e2e5f0"))
            else:
                painter.setPen(QColor("#b0b6ca"))

            painter.drawText(cell_rect, Qt.AlignmentFlag.AlignCenter, text)

        painter.end()


class SettingsIconButton(QPushButton):
    """Sleek pill button with a custom vector gear icon and click bounce animation."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._hovered = False
        self._active = False
        self._scale = 1.0
        self._angle_offset = 0.0
        self._anim_step = 0
        self.setFixedSize(30, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim_timer = QTimer(self)
        self._anim_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)

    def set_active(self, active: bool) -> None:
        if self._active != active:
            self._active = active
            self.update()

    def is_active(self) -> bool:
        return self._active

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, a0) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(a0)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._anim_step = 1
            self._scale = 0.84
            self._anim_timer.start()
            self.update()
        super().mousePressEvent(e)

    def _tick_anim(self) -> None:
        scales = [0.86, 0.90, 0.95, 1.01, 1.04, 1.03, 1.01, 1.00]
        if 0 < self._anim_step <= len(scales):
            self._scale = scales[self._anim_step - 1]
            self._angle_offset += 5.5
            self._anim_step += 1
            self.update()
        else:
            self._scale = 1.0
            self._anim_timer.stop()
            self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        cx, cy = w / 2.0, h / 2.0

        painter.translate(cx, cy)
        painter.scale(self._scale, self._scale)
        painter.translate(-cx, -cy)

        # Active = vibrant magenta; Inactive = neutral dark glass (lights up on hover)
        if self._active:
            bg = QColor(PALETTE["accent_hover"] if self._hovered else PALETTE["accent"])
            border = QColor(255, 255, 255, 110)
            fg = QColor("#ffffff")
        elif self._hovered:
            bg = QColor(236, 24, 108, 45)
            border = QColor(PALETTE["accent"])
            fg = QColor("#ffffff")
        else:
            bg = QColor(14, 16, 26, 200)
            border = QColor(255, 255, 255, 34)
            fg = QColor("#c4c9dc")
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(1.0, 1.0, w - 2.0, h - 2.0), 9.0, 9.0)

        # Vector Gear Icon
        pen = QPen(fg, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for i in range(8):
            angle = math.radians(i * 45 + self._angle_offset)
            r1, r2 = 4.5, 6.8
            p1 = QPointF(cx + r1 * math.cos(angle), cy + r1 * math.sin(angle))
            p2 = QPointF(cx + r2 * math.cos(angle), cy + r2 * math.sin(angle))
            painter.drawLine(p1, p2)

        painter.drawEllipse(QPointF(cx, cy), 4.3, 4.3)
        painter.end()
