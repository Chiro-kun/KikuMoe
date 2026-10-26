"""Custom vector history icon button for KikuMoe top HUD."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QPushButton, QWidget

from ui.themes.cyber_moe import PALETTE


class HistoryIconButton(QPushButton):
    """Sleek pill button with a custom vector song history clock icon and click bounce animation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hovered = False
        self._active = False
        self._scale = 1.0
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

    def enterEvent(self, event: object) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)  # type: ignore[arg-type]

    def leaveEvent(self, a0: object) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(a0)  # type: ignore[arg-type]

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None and a0.button() == Qt.MouseButton.LeftButton:
            self._anim_step = 1
            self._scale = 0.84
            self._anim_timer.start()
            self.update()
        super().mousePressEvent(a0)

    def _tick_anim(self) -> None:
        scales = [0.86, 0.90, 0.95, 1.01, 1.04, 1.03, 1.01, 1.00]
        if 0 < self._anim_step <= len(scales):
            self._scale = scales[self._anim_step - 1]
            self._anim_step += 1
            self.update()
        else:
            self._scale = 1.0
            self._anim_timer.stop()
            self.update()

    def paintEvent(self, a0: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        cx, cy = w / 2.0, h / 2.0

        painter.translate(cx, cy)
        painter.scale(self._scale, self._scale)
        painter.translate(-cx, -cy)

        # 1. Background squircle styling matching Cyber-Moe HUD
        if self._active:
            act_col = (
                PALETTE.get("accent_hover", "#FF3388")
                if self._hovered
                else PALETTE.get("accent", "#EC186C")
            )
            bg = QColor(act_col)
            border = QColor(255, 255, 255, 110)
            fg = QColor("#ffffff")
        elif self._hovered:
            bg = QColor(236, 24, 108, 45)
            border = QColor(PALETTE.get("accent", "#EC186C"))
            fg = QColor("#ffffff")
        else:
            bg = QColor(14, 16, 26, 200)
            border = QColor(255, 255, 255, 22)
            fg = QColor(200, 208, 225)

        r = QRectF(1.0, 1.0, w - 2.0, h - 2.0)
        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(r, 6.0, 6.0)

        # 2. Vector History Clock Icon
        pen = QPen(fg, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        clock_radius = 5.5
        clock_rect = QRectF(
            cx - clock_radius,
            cy - clock_radius,
            clock_radius * 2.0,
            clock_radius * 2.0,
        )
        painter.drawEllipse(clock_rect)

        # Clock hands: hour hand up (12:00), minute hand right (3:00)
        painter.drawLine(QPointF(cx, cy), QPointF(cx, cy - 3.2))
        painter.drawLine(QPointF(cx, cy), QPointF(cx + 2.8, cy))

        # Center pivot dot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fg)
        painter.drawEllipse(QPointF(cx, cy), 1.0, 1.0)

        painter.end()
