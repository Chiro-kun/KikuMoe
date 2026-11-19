"""Cyber-Glass 10-band ISO Audio Equalizer Popover for KikuMoe."""

from __future__ import annotations

import sys
from typing import Callable

from PyQt6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QEvent,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QHideEvent,
    QKeyEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from audio.equalizer import (
    EQ_BAND_LABELS,
    EQ_FREQUENCIES,
    EQ_MAX_DB,
    EQ_MIN_DB,
    EQ_NUM_BANDS,
    EQ_PRESET_CUSTOM,
    EQ_PRESET_ORDER,
    EQ_PRESETS,
    clamp_eq_db,
    normalize_eq_bands,
)
from core.i18n import I18n
from ui.settings_dialog import GlassComboBox
from ui.themes.cyber_moe import PALETTE, accent_qcolor, surface_qcolor

_IS_LINUX = sys.platform.startswith("linux")


class _CompactPillSwitch(QPushButton):
    """Compact 38x20 sliding pill toggle switch with 60 FPS animation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(38, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        self._progress = 0.0
        self._anim_timer = QTimer(self)
        self._anim_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, _checked: bool) -> None:
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def setChecked(self, a0: bool) -> None:
        super().setChecked(a0)
        if not self.isVisible():
            self._progress = 1.0 if a0 else 0.0
            self._anim_timer.stop()
            self.update()
        elif not self._anim_timer.isActive():
            self._anim_timer.start()

    def _tick(self) -> None:
        target = 1.0 if self.isChecked() else 0.0
        diff = target - self._progress
        if abs(diff) <= 0.04:
            self._progress = target
            self._anim_timer.stop()
        else:
            self._progress += diff * 0.30
        self.update()

    def enterEvent(self, event: object) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)  # type: ignore[arg-type]

    def leaveEvent(self, a0: QEvent | None) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(a0)

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        p = self._progress
        radius = h / 2.0

        act = QColor(PALETTE["accent"])
        r_bg = int(28 + (act.red() - 28) * p)
        g_bg = int(32 + (act.green() - 32) * p)
        b_bg = int(48 + (act.blue() - 48) * p)
        a_bg = int(200 + 55 * p)

        border = (
            QColor(PALETTE["accent_hover"] if self._hover else PALETTE["accent"])
            if p > 0.5
            else QColor(255, 255, 255, 70 if self._hover else 34)
        )
        painter.setBrush(QColor(r_bg, g_bg, b_bg, a_bg))
        painter.setPen(QPen(border, 1.1))
        painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), radius, radius)

        knob_d = h - 6.0
        knob_x = 3.0 + (w - knob_d - 6.0) * p
        knob_y = 3.0
        knob_col = (
            QColor(PALETTE["on_accent"])
            if p > 0.5
            else QColor("#d7dcee" if self._hover else "#8c93aa")
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_col)
        painter.drawEllipse(QRectF(knob_x, knob_y, knob_d, knob_d))
        painter.end()


class _EqFaderDeck(QWidget):
    """Interactive Preamp + 10-band ISO fader canvas with smooth spline curve overlay."""

    preamp_changed = pyqtSignal(float)
    band_changed = pyqtSignal(int, float)

    _IDX_NONE = -2
    _IDX_PREAMP = -1

    def __init__(self, i18n: I18n, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self._enabled = False
        self._preamp_db = 0.0
        self._bands_db: list[float] = [0.0] * EQ_NUM_BANDS
        self._display_preamp = 0.0
        self._display_bands: list[float] = [0.0] * EQ_NUM_BANDS
        self._start_preamp = 0.0
        self._start_bands: list[float] = [0.0] * EQ_NUM_BANDS
        self._anim_duration_ms = 190.0
        self._anim_elapsed = QElapsedTimer()
        self._anim_timer = QTimer(self)
        self._anim_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_curve_anim)
        self._hover_idx: int = self._IDX_NONE
        self._drag_idx: int = self._IDX_NONE

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(216)

    def set_i18n(self, i18n: I18n) -> None:
        self.i18n = i18n
        self.update()

    def _start_curve_glide(self, duration_ms: float = 190.0) -> None:
        self._start_preamp = self._display_preamp
        self._start_bands = list(self._display_bands)
        self._anim_duration_ms = max(16.0, float(duration_ms))
        self._anim_elapsed.start()
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def _tick_curve_anim(self) -> None:
        t = min(1.0, max(0.0, float(self._anim_elapsed.elapsed()) / self._anim_duration_ms))
        ease = 1.0 - ((1.0 - t) ** 3)
        self._display_preamp = self._start_preamp + (self._preamp_db - self._start_preamp) * ease
        self._display_bands = [
            s + (dst - s) * ease for s, dst in zip(self._start_bands, self._bands_db)
        ]
        if t >= 1.0:
            self._display_preamp = self._preamp_db
            self._display_bands = list(self._bands_db)
            self._anim_timer.stop()
        self.update()

    def set_values(
        self, enabled: bool, preamp_db: float, bands_db: list[float], animate: bool = False
    ) -> None:
        self._enabled = bool(enabled)
        self._preamp_db = clamp_eq_db(preamp_db)
        self._bands_db = normalize_eq_bands(bands_db)
        if animate and self.isVisible():
            self._start_curve_glide(duration_ms=190.0)
        else:
            self._anim_timer.stop()
            self._display_preamp = self._preamp_db
            self._display_bands = list(self._bands_db)
        self.update()

    def animate_entrance_from_flat(self) -> None:
        """Glide faders smoothly from 0 dB baseline up into the active EQ curve on open."""
        self._display_preamp = 0.0
        self._display_bands = [0.0] * EQ_NUM_BANDS
        if abs(self._preamp_db) >= 0.05 or any(abs(g) >= 0.05 for g in self._bands_db):
            self._start_curve_glide(duration_ms=220.0)
        self.update()

    def _geometry_metrics(self) -> tuple[float, float, float, list[float], float]:
        """Compute (track_top, track_bottom, preamp_x, band_xs, divider_x)."""
        w = float(self.width())
        h = float(self.height())
        track_top = 24.0
        track_bottom = max(track_top + 60.0, h - 26.0)

        left_pad = 30.0  # room for +12 / 0 / -12 scale labels
        right_pad = 12.0
        usable_w = max(120.0, w - left_pad - right_pad)

        # Preamp takes 1 slot, gap takes 0.45 slot, 10 bands take 10 slots
        slot_w = usable_w / 11.45
        preamp_x = left_pad + slot_w * 0.5
        divider_x = left_pad + slot_w * 1.22
        bands_start_x = left_pad + slot_w * 1.45
        band_xs = [bands_start_x + slot_w * (i + 0.5) for i in range(EQ_NUM_BANDS)]
        return track_top, track_bottom, preamp_x, band_xs, divider_x

    def _db_to_y(self, db: float, top: float, bottom: float) -> float:
        clamped = clamp_eq_db(db)
        ratio = (EQ_MAX_DB - clamped) / (EQ_MAX_DB - EQ_MIN_DB)
        return top + ratio * (bottom - top)

    def _y_to_db(self, y: float, top: float, bottom: float, fine: bool = False) -> float:
        span = max(1.0, bottom - top)
        ratio = max(0.0, min(1.0, (y - top) / span))
        raw = EQ_MAX_DB - ratio * (EQ_MAX_DB - EQ_MIN_DB)
        step = 0.1 if fine else 0.5
        snapped = round(raw / step) * step
        return clamp_eq_db(snapped)

    def _hit_test_column(self, x: float) -> int:
        _top, _bot, preamp_x, band_xs, divider_x = self._geometry_metrics()
        if x < divider_x:
            return self._IDX_PREAMP
        best_idx = 0
        best_dist = abs(x - band_xs[0])
        for i in range(1, len(band_xs)):
            d = abs(x - band_xs[i])
            if d < best_dist:
                best_dist = d
                best_idx = i
        return best_idx

    def _apply_column_value(self, col_idx: int, new_db: float) -> None:
        val = clamp_eq_db(new_db)
        if col_idx == self._IDX_PREAMP:
            if abs(val - self._preamp_db) >= 0.05:
                self._anim_timer.stop()
                self._preamp_db = val
                self._display_preamp = val
                self.preamp_changed.emit(val)
                self.update()
        elif 0 <= col_idx < EQ_NUM_BANDS:
            if abs(val - self._bands_db[col_idx]) >= 0.05:
                self._anim_timer.stop()
                self._bands_db[col_idx] = val
                self._display_bands[col_idx] = val
                self.band_changed.emit(col_idx, val)
                self.update()

    def _update_tooltip(self, col_idx: int) -> None:
        if col_idx == self._IDX_PREAMP:
            self.setToolTip(self.i18n.t("eq_preamp_tip", val=self._preamp_db))
        elif 0 <= col_idx < EQ_NUM_BANDS:
            self.setToolTip(
                self.i18n.t(
                    "eq_band_tip",
                    freq=EQ_FREQUENCIES[col_idx],
                    val=self._bands_db[col_idx],
                )
            )
        else:
            self.setToolTip("")

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        pos = a0.position()
        col = self._hit_test_column(pos.x())
        if a0.button() == Qt.MouseButton.RightButton:
            self._apply_column_value(col, 0.0)
            self._update_tooltip(col)
            return
        if a0.button() == Qt.MouseButton.LeftButton:
            self._drag_idx = col
            self._hover_idx = col
            top, bot, *_ = self._geometry_metrics()
            fine = bool(a0.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._apply_column_value(col, self._y_to_db(pos.y(), top, bot, fine=fine))
            self._update_tooltip(col)
            self.update()
            return
        super().mousePressEvent(a0)

    def mouseDoubleClickEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None and a0.button() == Qt.MouseButton.LeftButton:
            col = self._hit_test_column(a0.position().x())
            self._drag_idx = self._IDX_NONE
            self._apply_column_value(col, 0.0)
            self._update_tooltip(col)
            return
        super().mouseDoubleClickEvent(a0)

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        pos = a0.position()
        if self._drag_idx != self._IDX_NONE:
            top, bot, *_ = self._geometry_metrics()
            fine = bool(a0.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._apply_column_value(self._drag_idx, self._y_to_db(pos.y(), top, bot, fine=fine))
            self._update_tooltip(self._drag_idx)
            return
        col = self._hit_test_column(pos.x())
        if col != self._hover_idx:
            self._hover_idx = col
            self._update_tooltip(col)
            self.update()
        super().mouseMoveEvent(a0)

    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None and a0.button() == Qt.MouseButton.LeftButton:
            self._drag_idx = self._IDX_NONE
            self.update()
        super().mouseReleaseEvent(a0)

    def leaveEvent(self, a0: QEvent | None) -> None:
        if self._drag_idx == self._IDX_NONE:
            self._hover_idx = self._IDX_NONE
            self.update()
        super().leaveEvent(a0)

    def wheelEvent(self, a0: QWheelEvent | None) -> None:
        if a0 is None:
            return
        delta = a0.angleDelta().y()
        if delta == 0:
            return
        col = self._hit_test_column(a0.position().x())
        step = 0.5 if delta > 0 else -0.5
        if col == self._IDX_PREAMP:
            self._apply_column_value(col, self._preamp_db + step)
        elif 0 <= col < EQ_NUM_BANDS:
            self._apply_column_value(col, self._bands_db[col] + step)
        self._update_tooltip(col)
        a0.accept()

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        top, bot, preamp_x, band_xs, divider_x = self._geometry_metrics()
        zero_y = self._db_to_y(0.0, top, bot)

        accent = QColor(PALETTE["accent"])
        accent_hover = QColor(PALETTE["accent_hover"])
        active_col = accent_hover if self._enabled else QColor("#64748b")
        fill_base = QColor(accent) if self._enabled else QColor("#475569")

        # 1. Subtle recessed graph panel background
        panel_rect = QRectF(2.0, 2.0, w - 4.0, h - 4.0)
        painter.setBrush(QColor(255, 255, 255, 7))
        painter.setPen(QPen(QColor(255, 255, 255, 16), 1.0))
        painter.drawRoundedRect(panel_rect, 10.0, 10.0)

        # 2. Horizontal dB grid lines & left axis labels (+12, 0, -12)
        scale_font = QFont(self.font())
        scale_font.setPixelSize(9)
        scale_font.setWeight(QFont.Weight.Medium)
        painter.setFont(scale_font)
        for db_val, alpha, show_lbl in (
            (12.0, 18, True),
            (6.0, 11, False),
            (0.0, 42, True),
            (-6.0, 11, False),
            (-12.0, 18, True),
        ):
            gy = self._db_to_y(db_val, top, bot)
            pen_style = Qt.PenStyle.SolidLine if db_val == 0.0 else Qt.PenStyle.DotLine
            painter.setPen(QPen(QColor(255, 255, 255, alpha), 1.0, pen_style))
            painter.drawLine(QPointF(28.0, gy), QPointF(w - 10.0, gy))
            if show_lbl:
                lbl = f"{int(db_val):+d}" if db_val != 0.0 else "0"
                painter.setPen(QColor(148, 163, 184, 175))
                painter.drawText(
                    QRectF(4.0, gy - 7.0, 22.0, 14.0),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    lbl,
                )

        # 3. Vertical separator between Preamp and the 10 ISO bands
        painter.setPen(QPen(QColor(255, 255, 255, 24), 1.0))
        painter.drawLine(QPointF(divider_x, top - 6.0), QPointF(divider_x, bot + 18.0))

        # 4. Smooth cubic spline EQ response curve across the 10 bands
        pts = [
            QPointF(bx, self._db_to_y(g, top, bot)) for bx, g in zip(band_xs, self._display_bands)
        ]
        curve = QPainterPath()
        curve.moveTo(pts[0])
        for i in range(len(pts) - 1):
            p0 = pts[max(0, i - 1)]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[min(len(pts) - 1, i + 2)]
            c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6.0, p1.y() + (p2.y() - p0.y()) / 6.0)
            c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6.0, p2.y() - (p3.y() - p1.y()) / 6.0)
            # Clamp control points inside track bounds to avoid overshoot spikes
            c1.setY(max(top, min(bot, c1.y())))
            c2.setY(max(top, min(bot, c2.y())))
            curve.cubicTo(c1, c2, p2)

        # Fill area between curve and 0 dB line
        fill_path = QPainterPath(curve)
        fill_path.lineTo(QPointF(pts[-1].x(), zero_y))
        fill_path.lineTo(QPointF(pts[0].x(), zero_y))
        fill_path.closeSubpath()

        fill_grad = QLinearGradient(0.0, top, 0.0, bot)
        c_top = QColor(fill_base)
        c_top.setAlpha(68 if self._enabled else 26)
        c_mid = QColor(fill_base)
        c_mid.setAlpha(14 if self._enabled else 8)
        c_bot = QColor(fill_base)
        c_bot.setAlpha(58 if self._enabled else 24)
        fill_grad.setColorAt(0.0, c_top)
        fill_grad.setColorAt(0.5, c_mid)
        fill_grad.setColorAt(1.0, c_bot)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill_grad)
        painter.drawPath(fill_path)

        # Curve stroke
        curve_pen = QPen(active_col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(curve_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(curve)

        # 5. Draw Preamp + 10 band faders, thumbs, top dB value, and bottom labels
        lbl_font = QFont(self.font())
        lbl_font.setPixelSize(10)
        lbl_font.setWeight(QFont.Weight.DemiBold)

        val_font = QFont(self.font())
        val_font.setPixelSize(9)
        val_font.setWeight(QFont.Weight.Bold)

        columns: list[tuple[int, float, float, str]] = [
            (self._IDX_PREAMP, preamp_x, self._display_preamp, self.i18n.t("eq_preamp")),
        ]
        for idx, (bx, g, lbl) in enumerate(zip(band_xs, self._display_bands, EQ_BAND_LABELS)):
            columns.append((idx, bx, g, lbl))

        for col_idx, cx, gain_db, label in columns:
            ky = self._db_to_y(gain_db, top, bot)
            is_active_col = col_idx in (self._drag_idx, self._hover_idx)

            # Vertical slot track
            painter.setPen(
                QPen(QColor(255, 255, 255, 28), 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            painter.drawLine(QPointF(cx, top), QPointF(cx, bot))

            # Active gain fill from 0 dB baseline to thumb
            if abs(gain_db) >= 0.05:
                bar_col = QColor(active_col)
                if col_idx == self._IDX_PREAMP and self._enabled:
                    bar_col = QColor(PALETTE["text_accent"])
                bar_col.setAlpha(210 if self._enabled else 120)
                painter.setPen(QPen(bar_col, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(cx, zero_y), QPointF(cx, ky))

            # Outer glow ring when hovered/dragged
            if is_active_col:
                halo = QColor(active_col)
                halo.setAlpha(75)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(halo)
                painter.drawEllipse(QPointF(cx, ky), 8.5, 8.5)

            # Knob thumb
            knob_r = 5.4 if is_active_col else 4.5
            knob_fill = QColor("#ffffff") if (is_active_col or self._enabled) else QColor("#94a3b8")
            knob_ring = active_col if self._enabled else QColor("#475569")
            painter.setBrush(knob_fill)
            painter.setPen(QPen(knob_ring, 1.8))
            painter.drawEllipse(QPointF(cx, ky), knob_r, knob_r)

            # Top dB readout (always shown on hover/drag, or compactly when non-zero on preamp)
            if is_active_col or (col_idx == self._IDX_PREAMP and abs(gain_db) >= 0.05):
                painter.setFont(val_font)
                painter.setPen(QColor("#ffffff") if is_active_col else QColor(180, 190, 210))
                db_str = f"{gain_db:+.1f}" if abs(gain_db) >= 0.05 else "0.0"
                painter.drawText(
                    QRectF(cx - 18.0, 4.0, 36.0, 14.0),
                    Qt.AlignmentFlag.AlignCenter,
                    db_str,
                )

            # Bottom frequency / Preamp label
            painter.setFont(lbl_font)
            if is_active_col:
                painter.setPen(QColor("#ffffff"))
            elif col_idx == self._IDX_PREAMP:
                painter.setPen(
                    QColor(PALETTE["text_accent"]) if self._enabled else QColor("#94a3b8")
                )
            else:
                painter.setPen(QColor("#9aa4bc"))
            painter.drawText(
                QRectF(cx - 18.0, bot + 6.0, 36.0, 16.0),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

        painter.end()


class EqualizerPopover(QWidget):
    """Frameless translucent Cyber-Glass popover hosting the 10-band ISO Equalizer."""

    eq_changed = pyqtSignal(bool, str, float, list)
    closed = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        i18n: I18n | None = None,
    ) -> None:
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)

        self.i18n = i18n or (getattr(parent, "i18n", None) if parent else None) or I18n("it")

        self._eq_enabled: bool = False
        self._preset_id: str = "flat"
        self._preamp_db: float = 0.0
        self._bands_db: list[float] = [0.0] * EQ_NUM_BANDS
        self._custom_preamp_db: float = 0.0
        self._custom_bands_db: list[float] = [0.0] * EQ_NUM_BANDS
        self._updating_ui: bool = False

        self._anim_group: QParallelAnimationGroup | None = None
        self._blurred_backdrop: QPixmap | None = None
        self._slide_from_bottom: bool = True
        self._anchor_widget: QWidget | None = None
        self._app_filter_installed: bool = False
        self._is_closing = False
        self._closed_emitted = False

        self.setFixedSize(454, 304)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)

        # 1. Header Row: Title + Enable Switch + Preset Combo + Reset Button
        header_row = QHBoxLayout()
        header_row.setContentsMargins(4, 2, 4, 2)
        header_row.setSpacing(8)

        self.lbl_title = QLabel(self.i18n.t("eq_title"))
        self.lbl_title.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        header_row.addWidget(self.lbl_title)

        self.toggle_enabled = _CompactPillSwitch(self)
        self.toggle_enabled.setToolTip(self.i18n.t("eq_enable"))
        self.toggle_enabled.toggled.connect(self._on_toggle_enabled)
        header_row.addWidget(self.toggle_enabled)

        header_row.addStretch(1)

        self.cmb_preset = GlassComboBox(self)
        self.cmb_preset.setFixedSize(148, 28)
        self._populate_presets()
        self.cmb_preset.currentIndexChanged.connect(self._on_preset_index_changed)
        header_row.addWidget(self.cmb_preset)

        self.btn_reset = QPushButton(self.i18n.t("eq_reset"))
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.setToolTip(self.i18n.t("eq_reset_tip"))
        self.btn_reset.setFixedHeight(28)
        self.btn_reset.setStyleSheet(
            "QPushButton { background: rgba(255, 255, 255, 0.06); color: #cbd5e1; "
            "border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 7px; "
            "padding: 2px 10px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: rgba(255, 255, 255, 0.14); color: #ffffff; "
            "border-color: rgba(255, 255, 255, 0.30); }"
        )
        self.btn_reset.clicked.connect(self.reset_flat)
        header_row.addWidget(self.btn_reset)

        outer.addLayout(header_row)

        # 2. Separator
        sep = QFrame(self)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); margin: 0 2px;")
        outer.addWidget(sep)

        # 3. Interactive Fader Deck (Preamp + 10 ISO Bands + Spline Curve)
        self.fader_deck = _EqFaderDeck(self.i18n, self)
        self.fader_deck.preamp_changed.connect(self._on_preamp_dragged)
        self.fader_deck.band_changed.connect(self._on_band_dragged)
        outer.addWidget(self.fader_deck, 1)

    def _populate_presets(self) -> None:
        self._updating_ui = True
        try:
            current_data = self._preset_id
            self.cmb_preset.clear()
            for pid in EQ_PRESET_ORDER:
                self.cmb_preset.addItem(self.i18n.t(f"eq_preset_{pid}"), userData=pid)
            self._select_combo_preset(current_data)
        finally:
            self._updating_ui = False

    def _select_combo_preset(self, preset_id: str) -> None:
        for i in range(self.cmb_preset.count()):
            if self.cmb_preset.itemData(i) == preset_id:
                self.cmb_preset.setCurrentIndex(i)
                return
        self.cmb_preset.setCurrentIndex(0)

    def set_state(
        self,
        enabled: bool,
        preset_id: str,
        preamp_db: float,
        bands_db: list[float],
        custom_preamp_db: float | None = None,
        custom_bands_db: list[float] | None = None,
    ) -> None:
        """Synchronize UI controls from persisted state without emitting eq_changed."""
        self._updating_ui = True
        try:
            self._eq_enabled = bool(enabled)
            pid = str(preset_id or "flat").strip().lower()
            if pid not in EQ_PRESET_ORDER:
                pid = "flat"
            self._preset_id = pid
            self._preamp_db = clamp_eq_db(preamp_db)
            self._bands_db = normalize_eq_bands(bands_db)
            if custom_preamp_db is not None:
                self._custom_preamp_db = clamp_eq_db(custom_preamp_db)
            elif pid == EQ_PRESET_CUSTOM:
                self._custom_preamp_db = self._preamp_db
            if custom_bands_db is not None:
                self._custom_bands_db = normalize_eq_bands(custom_bands_db)
            elif pid == EQ_PRESET_CUSTOM:
                self._custom_bands_db = list(self._bands_db)

            self.toggle_enabled.setChecked(self._eq_enabled)
            self._select_combo_preset(self._preset_id)
            self.fader_deck.set_values(self._eq_enabled, self._preamp_db, self._bands_db)
        finally:
            self._updating_ui = False

    def get_state(self) -> tuple[bool, str, float, list[float]]:
        """Return (enabled, preset_id, preamp_db, bands_db)."""
        return self._eq_enabled, self._preset_id, self._preamp_db, list(self._bands_db)

    def get_custom_state(self) -> tuple[float, list[float]]:
        """Return the last remembered custom (preamp_db, bands_db)."""
        return self._custom_preamp_db, list(self._custom_bands_db)

    def _emit_state(self, animate_curve: bool = False) -> None:
        self.fader_deck.set_values(
            self._eq_enabled, self._preamp_db, self._bands_db, animate=animate_curve
        )
        self.eq_changed.emit(
            self._eq_enabled,
            self._preset_id,
            self._preamp_db,
            list(self._bands_db),
        )

    def _on_toggle_enabled(self, checked: bool) -> None:
        if self._updating_ui:
            return
        self._eq_enabled = bool(checked)
        self._emit_state()

    def select_preset(self, preset_id: str) -> None:
        """Select a built-in preset or 'custom' and emit live EQ update."""
        pid = str(preset_id or "flat").strip().lower()
        if pid not in EQ_PRESET_ORDER:
            return
        self._preset_id = pid
        if pid == EQ_PRESET_CUSTOM:
            self._preamp_db = self._custom_preamp_db
            self._bands_db = list(self._custom_bands_db)
        else:
            pre, bands = EQ_PRESETS[pid]
            self._preamp_db = clamp_eq_db(pre)
            self._bands_db = normalize_eq_bands(bands)
        self._updating_ui = True
        try:
            self._select_combo_preset(pid)
        finally:
            self._updating_ui = False
        self._emit_state(animate_curve=True)

    def _on_preset_index_changed(self, idx: int) -> None:
        if self._updating_ui or idx < 0:
            return
        pid = self.cmb_preset.itemData(idx)
        if isinstance(pid, str):
            self.select_preset(pid)

    def _switch_to_custom(self) -> None:
        self._preset_id = EQ_PRESET_CUSTOM
        self._custom_preamp_db = self._preamp_db
        self._custom_bands_db = list(self._bands_db)
        self._updating_ui = True
        try:
            self._select_combo_preset(EQ_PRESET_CUSTOM)
        finally:
            self._updating_ui = False

    def _on_preamp_dragged(self, new_db: float) -> None:
        self._preamp_db = clamp_eq_db(new_db)
        self._switch_to_custom()
        self._emit_state()

    def _on_band_dragged(self, band_idx: int, new_db: float) -> None:
        if 0 <= band_idx < EQ_NUM_BANDS:
            self._bands_db[band_idx] = clamp_eq_db(new_db)
            self._switch_to_custom()
            self._emit_state()

    def set_preamp(self, new_db: float) -> None:
        """Programmatically adjust preamp (switches to custom preset and emits update)."""
        self._on_preamp_dragged(new_db)

    def set_band_gain(self, band_idx: int, new_db: float) -> None:
        """Programmatically adjust one band (switches to custom preset and emits update)."""
        self._on_band_dragged(band_idx, new_db)

    def set_eq_enabled(self, enabled: bool) -> None:
        """Programmatically toggle EQ on/off and emit update."""
        self.toggle_enabled.setChecked(bool(enabled))
        if self._eq_enabled != bool(enabled):
            self._eq_enabled = bool(enabled)
            self._emit_state()

    def reset_flat(self) -> None:
        """Reset all bands and preamp to 0.0 dB (Flat preset)."""
        self.select_preset("flat")

    def retranslate(self, i18n: I18n) -> None:
        self.i18n = i18n
        self.lbl_title.setText(self.i18n.t("eq_title"))
        self.toggle_enabled.setToolTip(self.i18n.t("eq_enable"))
        self.btn_reset.setText(self.i18n.t("eq_reset"))
        self.btn_reset.setToolTip(self.i18n.t("eq_reset_tip"))
        self._populate_presets()
        self.fader_deck.set_i18n(self.i18n)

    def refresh_theme(self) -> None:
        self.cmb_preset.refresh_theme()
        self.toggle_enabled.update()
        self.fader_deck.update()
        self.update()

    def _install_app_filter(self) -> None:
        if not self._app_filter_installed:
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
                self._app_filter_installed = True

    def _remove_app_filter(self) -> None:
        if self._app_filter_installed:
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
            self._app_filter_installed = False

    def _capture_backdrop(self, global_x: int, global_y: int) -> None:
        """Capture and softly blur the underlying app window for Cyber-Glass depth."""
        self._blurred_backdrop = None
        parent = self.parentWidget()
        if parent is None or not parent.isVisible():
            return
        source = parent.window()
        if source is None:
            return
        local = source.mapFromGlobal(QPoint(global_x, global_y))
        popup_rect = QRect(local, self.size())
        visible = popup_rect.intersected(source.rect())
        if visible.isEmpty():
            return
        ratio = max(1.0, float(source.devicePixelRatioF()))
        snapshot = QPixmap(round(self.width() * ratio), round(self.height() * ratio))
        snapshot.setDevicePixelRatio(ratio)
        snapshot.fill(QColor(PALETTE.get("station_glass_fallback", PALETTE["bg_popover"])))
        painter = QPainter(snapshot)
        painter.drawPixmap(visible.topLeft() - local, source.grab(visible))
        painter.end()
        tiny = snapshot.scaled(
            max(1, snapshot.width() // 14),
            max(1, snapshot.height() // 14),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        blurred = tiny.scaled(
            snapshot.width(),
            snapshot.height(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        blurred.setDevicePixelRatio(ratio)
        self._blurred_backdrop = blurred

    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        if a1 is None or not self.isVisible() or self._is_closing:
            return super().eventFilter(a0, a1)

        etype = a1.type()
        if etype == QEvent.Type.MouseButtonPress and isinstance(a1, QMouseEvent):
            gpos = a1.globalPosition().toPoint()
            if self.frameGeometry().contains(gpos):
                return super().eventFilter(a0, a1)
            # Keep popover open when interacting with the preset dropdown list
            combo_view = self.cmb_preset.view()
            if combo_view is not None:
                combo_popup = combo_view.window()
                if (
                    combo_popup is not None
                    and combo_popup is not self
                    and combo_popup.isVisible()
                    and combo_popup.frameGeometry().contains(gpos)
                ):
                    return super().eventFilter(a0, a1)
            # Let the anchor EQ button toggle cleanly via its own clicked signal
            if self._anchor_widget is not None and self._anchor_widget.isVisible():
                anchor_tl = self._anchor_widget.mapToGlobal(QPoint(0, 0))
                anchor_rect = QRect(anchor_tl, self._anchor_widget.size())
                if anchor_rect.contains(gpos):
                    return super().eventFilter(a0, a1)
            self._animate_exit()
        elif etype == QEvent.Type.ApplicationDeactivate:
            if not getattr(self.cmb_preset, "_popup_open", False):
                self._animate_exit()

        return super().eventFilter(a0, a1)

    def open_at(
        self,
        target_pos: QPoint,
        slide_from_bottom: bool = True,
        anchor_widget: QWidget | None = None,
    ) -> None:
        """Position and smoothly animate popover entrance (slide + fade + curve glide)."""
        self._is_closing = False
        self._closed_emitted = False
        self._slide_from_bottom = bool(slide_from_bottom)
        self._anchor_widget = anchor_widget

        self._capture_backdrop(target_pos.x(), target_pos.y())

        if self._anim_group and self._anim_group.state() == QParallelAnimationGroup.State.Running:
            self._anim_group.stop()

        if _IS_LINUX:
            self.move(target_pos)
            self.setWindowOpacity(1.0)
            self.show()
            self.raise_()
            self.activateWindow()
            self.fader_deck.animate_entrance_from_flat()
            self._install_app_filter()
            return

        offset_y = 14 if self._slide_from_bottom else -14
        start_pos = QPoint(target_pos.x(), target_pos.y() + offset_y)
        self.move(start_pos)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
        self.fader_deck.animate_entrance_from_flat()
        self._install_app_filter()

        group = QParallelAnimationGroup(self)

        anim_pos = QPropertyAnimation(self, b"pos", group)
        anim_pos.setDuration(210)
        anim_pos.setStartValue(start_pos)
        anim_pos.setEndValue(target_pos)
        anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

        anim_op = QPropertyAnimation(self, b"windowOpacity", group)
        anim_op.setDuration(200)
        anim_op.setStartValue(0.0)
        anim_op.setEndValue(1.0)
        anim_op.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_group = group
        group.start()

    def _animate_exit(self, callback: Callable[[], None] | None = None) -> None:
        """Smooth directional slide & fade exit animation."""
        if self._is_closing:
            return
        self._is_closing = True
        self._remove_app_filter()
        if getattr(self.cmb_preset, "_popup_open", False):
            self.cmb_preset.hidePopup()

        if not self.isVisible():
            if not self._closed_emitted:
                self._closed_emitted = True
                self.closed.emit()
            if callback:
                callback()
            return

        if _IS_LINUX:
            self.hide()
            if not self._closed_emitted:
                self._closed_emitted = True
                self.closed.emit()
            if callback:
                callback()
            return

        if self._anim_group and self._anim_group.state() == QParallelAnimationGroup.State.Running:
            self._anim_group.stop()

        group = QParallelAnimationGroup(self)
        offset_y = 12 if self._slide_from_bottom else -12

        anim_pos = QPropertyAnimation(self, b"pos", group)
        anim_pos.setDuration(145)
        anim_pos.setStartValue(self.pos())
        anim_pos.setEndValue(QPoint(self.x(), self.y() + offset_y))
        anim_pos.setEasingCurve(QEasingCurve.Type.InCubic)

        anim_op = QPropertyAnimation(self, b"windowOpacity", group)
        anim_op.setDuration(145)
        anim_op.setStartValue(self.windowOpacity())
        anim_op.setEndValue(0.0)
        anim_op.setEasingCurve(QEasingCurve.Type.InCubic)

        def _finish() -> None:
            self.hide()
            self._is_closing = False
            if not self._closed_emitted:
                self._closed_emitted = True
                self.closed.emit()
            if callback:
                callback()

        group.finished.connect(_finish)
        self._anim_group = group
        group.start()

    def hideEvent(self, a0: QHideEvent | None) -> None:
        self._remove_app_filter()
        if not self._closed_emitted:
            self._closed_emitted = True
            self.closed.emit()
        super().hideEvent(a0)

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        self._remove_app_filter()
        if not self._closed_emitted:
            self._closed_emitted = True
            self.closed.emit()
        super().closeEvent(a0)

    def keyPressEvent(self, a0: QKeyEvent | None) -> None:
        if a0 is not None and a0.key() == Qt.Key.Key_Escape:
            self._animate_exit()
            return
        super().keyPressEvent(a0)

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        """Draw Cyber-Moe frosted dark glass popover frame with blurred backdrop."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0.5, 0.5, float(self.width()) - 1.0, float(self.height()) - 1.0)
        path = QPainterPath()
        path.addRoundedRect(rect, 12.0, 12.0)

        painter.save()
        painter.setClipPath(path)
        if self._blurred_backdrop is not None:
            painter.drawPixmap(QPointF(0.0, 0.0), self._blurred_backdrop)
            painter.fillRect(rect, QColor(PALETTE.get("station_glass_overlay", "#c00c0e18")))
        else:
            painter.fillRect(rect, surface_qcolor(245, "bg_popover"))
        painter.restore()

        painter.setPen(QPen(accent_qcolor(95), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()
