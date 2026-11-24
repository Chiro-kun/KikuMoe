"""Custom vector history icon button for KikuMoe top HUD."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QPushButton, QWidget

from ui.themes.cyber_moe import PALETTE, accent_qcolor, surface_qcolor


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

    def mousePressEvent(self, e: QMouseEvent | None) -> None:
        if e is not None and e.button() == Qt.MouseButton.LeftButton:
            self._anim_step = 1
            self._scale = 0.84
            self._anim_timer.start()
            self.update()
        super().mousePressEvent(e)

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
            custom_accent = getattr(self, "_custom_accent", None)
            if self._hovered:
                act_col = (
                    QColor(custom_accent).lighter(118).name()
                    if custom_accent
                    else PALETTE.get("accent_hover", "#FF3388")
                )
            else:
                act_col = custom_accent or PALETTE.get("accent", "#EC186C")
            bg = QColor(act_col)
            border = QColor(255, 255, 255, 110)
            fg = QColor(PALETTE.get("on_accent", "#ffffff"))
        elif self._hovered:
            bg = accent_qcolor(45)
            border = QColor(PALETTE.get("accent", "#EC186C"))
            fg = QColor("#ffffff")
        else:
            bg = surface_qcolor(200, "bg_pill_idle")
            border = QColor(255, 255, 255, 22)
            fg = QColor(200, 208, 225)

        r = QRectF(1.0, 1.0, w - 2.0, h - 2.0)
        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(r, 6.0, 6.0)

        self._draw_icon(painter, cx, cy, fg)
        painter.end()

    def _draw_icon(self, painter, cx, cy, fg):
        # Vector History Clock Icon
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


class LyricsButton(HistoryIconButton):
    """Lyrics toggle matching the history and settings buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.toggled.connect(self.set_active)
        self._accent = PALETTE["accent"]
        self._custom_accent: str | None = None

    def set_accent_color(self, color_str: str) -> None:
        self._accent = color_str
        if color_str.strip().lower() == PALETTE["accent"].lower():
            self._custom_accent = None
        else:
            self._custom_accent = color_str
        self.update()

    def refresh_theme(self) -> None:
        self._custom_accent = None
        self._accent = PALETTE["accent"]
        self.update()

    def _draw_icon(self, painter, cx, cy, fg):
        painter.setPen(QPen(fg, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(cx - 5, cy - 4), QPointF(cx + 5, cy - 4))
        painter.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))
        painter.drawLine(QPointF(cx - 5, cy + 4), QPointF(cx + 2, cy + 4))


class SleepIconButton(LyricsButton):
    """Sleep timer drawer toggle matching the top HUD icon buttons."""

    def _draw_icon(self, painter, cx, cy, fg):
        outer = QPainterPath()
        outer.addEllipse(QPointF(cx + 0.5, cy), 5.8, 5.8)
        cutout = QPainterPath()
        cutout.addEllipse(QPointF(cx + 3.2, cy - 2.0), 4.8, 4.8)
        crescent = outer.subtracted(cutout)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fg)
        painter.drawPath(crescent)


class EqualizerIconButton(HistoryIconButton):
    """Equalizer popover trigger with 3-slider vector glyph and active-EQ indicator."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._eq_enabled = False
        self._custom_accent: str | None = None

    def set_eq_enabled(self, enabled: bool) -> None:
        val = bool(enabled)
        if self._eq_enabled != val:
            self._eq_enabled = val
            self.update()

    def is_eq_enabled(self) -> bool:
        return self._eq_enabled

    def refresh_theme(self) -> None:
        self._custom_accent = None
        self.update()

    def _draw_icon(self, painter, cx, cy, fg):
        # 3 vertical equalizer tracks with circular fader knobs
        xs = (cx - 4.5, cx, cx + 4.5)
        knob_ys = (cy + 1.8, cy - 2.4, cy + 0.6)
        top_y = cy - 5.2
        bot_y = cy + 5.2

        track_pen = QPen(fg, 1.45, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        for x in xs:
            painter.drawLine(QPointF(x, top_y), QPointF(x, bot_y))

        # Knob color: highlight with accent when EQ is enabled and popover is closed
        if self._eq_enabled and not self._active:
            knob_col = QColor(PALETTE.get("accent_hover", "#FF3388"))
        else:
            knob_col = fg

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_col)
        for x, ky in zip(xs, knob_ys):
            painter.drawEllipse(QPointF(x, ky), 1.9, 1.9)

        # Small corner status dot when EQ is enabled and popover is closed
        if self._eq_enabled and not self._active:
            painter.setBrush(QColor(PALETTE.get("accent", "#EC186C")))
            painter.drawEllipse(QPointF(float(self.width()) - 5.0, 5.0), 2.1, 2.1)
