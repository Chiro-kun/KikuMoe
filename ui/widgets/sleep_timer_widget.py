"""
SleepTimerWidget for KikuMoe 2.0.0
Sleek inline panel for the sleep timer with:
- 60 FPS card activation/deactivation wave & border glow animation when clicking Avvia or Annulla
- Spring-animated countdown badge with pulsing live indicator
- Tactile 60 FPS click-bounce & ripple on preset chips, steppers, and Avvia / Annulla buttons
"""

from typing import Dict, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.themes.cyber_moe import PALETTE, accent_qcolor, surface_qcolor


class _AnimatedSleepBtn(QPushButton):
    """QPushButton with 60 FPS click-bounce scale and expanding ripple overlay."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self._scale = 1.0
        self._anim_step = 0
        self._ripple = 1.0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)

    def trigger_bounce(self) -> None:
        self._anim_step = 1
        self._scale = 0.88
        self._ripple = 0.12
        if not self._anim_timer.isActive():
            self._anim_timer.start()
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.trigger_bounce()
        super().mousePressEvent(e)

    def _tick_anim(self) -> None:
        scales = [0.88, 0.93, 1.05, 1.02, 1.0]
        still_running = False
        if 0 < self._anim_step <= len(scales):
            self._scale = scales[self._anim_step - 1]
            self._anim_step += 1
            still_running = True
        else:
            self._scale = 1.0
            self._anim_step = 0

        if self._ripple < 1.0:
            self._ripple = min(1.0, self._ripple + 0.14)
            still_running = True

        if not still_running:
            self._anim_timer.stop()
        self.update()

    def paintEvent(self, a0) -> None:
        super().paintEvent(a0)
        if self._ripple < 1.0:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            w = float(self.width())
            h = float(self.height())
            alpha = int(115 * (1.0 - self._ripple))
            painter.setBrush(QColor(255, 255, 255, alpha))
            painter.setPen(Qt.PenStyle.NoPen)
            rx = (w / 2.0) * (0.35 + 0.65 * self._ripple)
            ry = (h / 2.0) * (0.35 + 0.65 * self._ripple)
            painter.drawRoundedRect(
                QRectF(w / 2.0 - rx, h / 2.0 - ry, rx * 2.0, ry * 2.0),
                ry,
                ry,
            )
            painter.end()


class _AnimatedCountdownBadge(QLabel):
    """Countdown pill badge that spring-scales when activated and pulses softly."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("", parent)
        self._scale = 1.0
        self._pulse_phase = 0.0
        self._step = 0
        self.setFixedSize(64, 20)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def animate_show(self) -> None:
        self._step = 1
        self._scale = 0.55
        self.setVisible(True)
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def _tick(self) -> None:
        scales = [0.55, 0.78, 0.96, 1.09, 1.04, 1.0]
        if 0 < self._step <= len(scales):
            self._scale = scales[self._step - 1]
            self._step += 1
        else:
            self._scale = 1.0
            self._step = 0
            self._timer.stop()
        self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        h = float(self.height())

        painter.translate(w / 2.0, h / 2.0)
        painter.scale(self._scale, self._scale)
        painter.translate(-w / 2.0, -h / 2.0)

        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        grad = QLinearGradient(0.0, 0.0, w, 0.0)
        grad.setColorAt(0.0, QColor(PALETTE["accent"]))
        grad.setColorAt(1.0, QColor(PALETTE["accent_hover"]))
        painter.setBrush(grad)
        painter.setPen(QPen(QColor(255, 255, 255, 65), 1.0))
        painter.drawRoundedRect(rect, 9.5, 9.5)

        # Live indicator dot on the left of the badge
        on_col = QColor(PALETTE["on_accent"])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(on_col)
        painter.drawEllipse(QPointF(10.0, h / 2.0), 2.4, 2.4)

        font = QFont("Segoe UI")
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(on_col)
        painter.drawText(
            QRectF(15.0, 0.0, w - 18.0, h),
            Qt.AlignmentFlag.AlignCenter,
            self.text(),
        )
        painter.end()


class SleepTimerWidget(QFrame):
    start_requested = pyqtSignal(int)
    cancel_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("sleepTimerCard")
        self._is_active = False
        self._active_progress = 0.0  # 0.0 = inactive, 1.0 = active
        self._wave_progress = 1.0  # 0.0 -> 1.0 sweep on start/cancel
        self._wave_dir = 1  # +1 = start wave, -1 = cancel wave

        self._card_anim_timer = QTimer(self)
        self._card_anim_timer.setInterval(16)
        self._card_anim_timer.timeout.connect(self._tick_card_anim)

        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(12, 8, 12, 9)
        card_layout.setSpacing(6)

        # Header Row: Title + Countdown Badge + Close (x)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)

        self.title_label = QLabel("SLEEP TIMER")
        self.title_label.setObjectName("sectionTitleLabel")
        self.title_label.setStyleSheet(
            "font-size: 10px; font-weight: 700; letter-spacing: 1px; color: #9aa1b8;"
            " background: transparent; border: none;"
        )

        self.badge_countdown = _AnimatedCountdownBadge(self)
        self.badge_countdown.setObjectName("timeDisplayLabel")
        self.badge_countdown.setVisible(False)

        self.btn_close = _AnimatedSleepBtn("×")
        self.btn_close.setObjectName("pillButton")
        self.btn_close.setFixedSize(21, 21)
        self.btn_close.setStyleSheet(
            "padding: 0px; border-radius: 10px; font-size: 13px; font-weight: 700;"
        )
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(lambda: self.setVisible(False))

        header_row.addWidget(self.title_label)
        header_row.addStretch(1)
        header_row.addWidget(self.badge_countdown)
        header_row.addWidget(self.btn_close)
        card_layout.addLayout(header_row)

        # Row 1: Medium-Sized Quick Preset Chips (15 min, 30 min, 45 min, 60 min)
        chips_row = QHBoxLayout()
        chips_row.setContentsMargins(0, 0, 0, 0)
        chips_row.setSpacing(6)

        self._chip_map: Dict[int, QPushButton] = {}
        self.btn_chip_15 = _AnimatedSleepBtn("15 min")
        self.btn_chip_30 = _AnimatedSleepBtn("30 min")
        self.btn_chip_45 = _AnimatedSleepBtn("45 min")
        self.btn_chip_60 = _AnimatedSleepBtn("60 min")

        for mins, chip in (
            (15, self.btn_chip_15),
            (30, self.btn_chip_30),
            (45, self.btn_chip_45),
            (60, self.btn_chip_60),
        ):
            self._chip_map[mins] = chip
            chip.setObjectName("pillButton")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFixedHeight(24)
            chips_row.addWidget(chip, 1)

        self.btn_chip_15.clicked.connect(lambda: self._set_spin_and_start(15))
        self.btn_chip_30.clicked.connect(lambda: self._set_spin_and_start(30))
        self.btn_chip_45.clicked.connect(lambda: self._set_spin_and_start(45))
        self.btn_chip_60.clicked.connect(lambda: self._set_spin_and_start(60))
        card_layout.addLayout(chips_row)

        # Row 2: Stepper [- 30 min +] + Balanced Start / Cancel Buttons
        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(6)

        self.btn_minus = _AnimatedSleepBtn("−")
        self.btn_minus.setFixedSize(26, 25)
        self.btn_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_minus.clicked.connect(
            lambda: self.spin_minutes.setValue(max(1, self.spin_minutes.value() - 5))
        )

        self.spin_minutes = QSpinBox()
        self.spin_minutes.setRange(1, 480)
        self.spin_minutes.setValue(30)
        self.spin_minutes.setSuffix(" min")
        self.spin_minutes.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin_minutes.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_minutes.setFixedSize(74, 25)
        self.spin_minutes.setStyleSheet(
            "QSpinBox { background-color: rgba(255, 255, 255, 0.06);"
            " border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 9px;"
            " padding: 0px 4px; font-size: 11px; font-weight: 700; color: #ffffff; }"
        )
        self.spin_minutes.setToolTip("Custom minutes")
        self.spin_minutes.valueChanged.connect(self._refresh_chip_styles)

        self.btn_plus = _AnimatedSleepBtn("+")
        self.btn_plus.setFixedSize(26, 25)
        self.btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_plus.clicked.connect(
            lambda: self.spin_minutes.setValue(min(480, self.spin_minutes.value() + 5))
        )
        self._apply_step_button_styles()

        self.btn_start = _AnimatedSleepBtn("Start")
        self.btn_start.setObjectName("primaryButton")
        self.btn_start.setFixedSize(92, 25)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self._on_start_clicked)

        self.btn_cancel = _AnimatedSleepBtn("Cancel")
        self.btn_cancel.setObjectName("pillButton")
        self.btn_cancel.setFixedSize(92, 25)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        self.btn_cancel.setEnabled(False)

        controls_row.addWidget(self.btn_minus)
        controls_row.addWidget(self.spin_minutes)
        controls_row.addWidget(self.btn_plus)
        controls_row.addStretch(1)
        controls_row.addWidget(self.btn_start)
        controls_row.addWidget(self.btn_cancel)

        card_layout.addLayout(controls_row)

        self._refresh_action_button_styles()
        self._refresh_chip_styles()
        self.setVisible(True)

    def _trigger_card_wave(self, direction: int) -> None:
        self._wave_dir = direction
        self._wave_progress = 0.0
        if not self._card_anim_timer.isActive():
            self._card_anim_timer.start()
        self.update()

    def _tick_card_anim(self) -> None:
        still_running = False
        target = 1.0 if self._is_active else 0.0
        diff = target - self._active_progress
        if abs(diff) > 0.03:
            self._active_progress += diff * 0.28
            still_running = True
        else:
            self._active_progress = target

        if self._wave_progress < 1.0:
            self._wave_progress = min(1.0, self._wave_progress + 0.065)
            still_running = True

        if not still_running:
            self._card_anim_timer.stop()
        self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        p = self._active_progress

        # 1. Base dark glass card + interpolated active accent ambient glow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(surface_qcolor(195, "bg_surface"))
        painter.drawRoundedRect(rect, 14.0, 14.0)

        if p > 0.01:
            glow_grad = QLinearGradient(0.0, 0.0, w, h)
            glow_grad.setColorAt(0.0, accent_qcolor(int(34 * p)))
            glow_grad.setColorAt(0.6, accent_qcolor(int(12 * p)))
            glow_grad.setColorAt(1.0, surface_qcolor(0, "bg_surface"))
            painter.setBrush(glow_grad)
            painter.drawRoundedRect(rect, 14.0, 14.0)

        # 2. Travelling energy wave when clicking Start (+1) or Cancel (-1)
        if self._wave_progress < 1.0:
            ease = 1.0 - ((1.0 - self._wave_progress) ** 3)
            wave_w = w * 0.45
            if self._wave_dir >= 0:
                wx = -wave_w + ease * (w + wave_w)
                wave_col = accent_qcolor(int(90 * (1.0 - self._wave_progress)))
            else:
                wx = w - ease * (w + wave_w)
                wave_col = QColor(180, 195, 230, int(75 * (1.0 - self._wave_progress)))

            w_grad = QLinearGradient(wx, 0.0, wx + wave_w, 0.0)
            c_zero = QColor(wave_col)
            c_zero.setAlpha(0)
            w_grad.setColorAt(0.0, c_zero)
            w_grad.setColorAt(0.5, wave_col)
            w_grad.setColorAt(1.0, c_zero)
            painter.setBrush(w_grad)
            painter.drawRoundedRect(rect, 14.0, 14.0)

        # 3. Animated Card Border (neutral glass -> glowing accent when active)
        act_col = QColor(PALETTE["accent"])
        r = int(255 + (act_col.red() - 255) * p)
        g = int(255 + (act_col.green() - 255) * p)
        b = int(255 + (act_col.blue() - 255) * p)
        a = int(36 + (145 - 36) * p)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(r, g, b, a), 1.1 + 0.3 * p))
        painter.drawRoundedRect(rect, 14.0, 14.0)
        painter.end()

    def _apply_step_button_styles(self) -> None:
        step_btn_style = (
            "QPushButton { background-color: rgba(255, 255, 255, 0.06);"
            " border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 9px;"
            " padding: 0px; font-size: 14px; font-weight: 700; color: #d0d5e8; }"
            f" QPushButton:hover {{ background-color: {PALETTE['accent_menu_hover']};"
            f" border-color: {PALETTE['accent']}; color: #ffffff; }}"
            f" QPushButton:pressed {{ background-color: {PALETTE['accent_glow']}; }}"
        )
        self.btn_minus.setStyleSheet(step_btn_style)
        self.btn_plus.setStyleSheet(step_btn_style)

    def _refresh_chip_styles(self) -> None:
        current_val = self.spin_minutes.value()
        for mins, chip in self._chip_map.items():
            if self._is_active and mins == current_val:
                chip.setStyleSheet(
                    f"QPushButton {{ background-color: {PALETTE['station_selected_hover']};"
                    f" border: 1px solid {PALETTE['accent']}; border-radius: 11px;"
                    " padding: 0px 6px; font-size: 11px; font-weight: 700; color: #ffffff; }"
                )
            else:
                chip.setStyleSheet(
                    "QPushButton { background-color: rgba(255, 255, 255, 0.05);"
                    " border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 11px;"
                    " padding: 0px 6px; font-size: 11px; font-weight: 600; color: #9ea4ba; }"
                    f" QPushButton:hover {{ background-color: {PALETTE['station_selected_bg']};"
                    f" border-color: {PALETTE['accent']}; color: #ffffff; }}"
                )

    def _refresh_action_button_styles(self) -> None:
        active_colored_style = (
            f"QPushButton {{ background-color: {PALETTE['accent']}; color: {PALETTE['on_accent']};"
            " border: none; border-radius: 12px; padding: 0px 10px;"
            " font-size: 11px; font-weight: 700; }"
            f" QPushButton:hover {{ background-color: {PALETTE['accent_hover']}; }}"
            f" QPushButton:pressed {{ background-color: {PALETTE['accent_pressed']}; }}"
        )
        disabled_neutral_style = (
            "QPushButton { background-color: rgba(255, 255, 255, 0.04);"
            " border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px;"
            " padding: 0px 10px; font-size: 11px; font-weight: 600; color: #5b6073; }"
        )
        if self._is_active:
            self.btn_start.setStyleSheet(disabled_neutral_style)
            self.btn_cancel.setStyleSheet(active_colored_style)
        else:
            self.btn_start.setStyleSheet(active_colored_style)
            self.btn_cancel.setStyleSheet(disabled_neutral_style)

    def toggle_visible(self) -> None:
        self.setVisible(not self.isVisible())

    def _set_spin_and_start(self, minutes: int) -> None:
        self.spin_minutes.setValue(minutes)
        self.start_requested.emit(minutes)

    def _on_start_clicked(self) -> None:
        self.start_requested.emit(self.spin_minutes.value())

    def _on_cancel_clicked(self) -> None:
        self.cancel_requested.emit()

    def set_active_countdown(self, remaining_sec: int) -> None:
        was_active = self._is_active
        self._is_active = True
        m, s = divmod(max(0, remaining_sec), 60)
        self.badge_countdown.setText(f"{m:02d}:{s:02d}")
        if not was_active:
            self.badge_countdown.animate_show()
            self._trigger_card_wave(1)
            self.btn_cancel.trigger_bounce()
        else:
            self.badge_countdown.setVisible(True)
            self.badge_countdown.update()
        self.btn_cancel.setEnabled(True)
        self.btn_start.setEnabled(False)
        self._refresh_action_button_styles()
        self._refresh_chip_styles()

    def set_inactive(self) -> None:
        was_active = self._is_active
        self._is_active = False
        self.badge_countdown.setVisible(False)
        self.btn_cancel.setEnabled(False)
        self.btn_start.setEnabled(True)
        self._refresh_action_button_styles()
        self._refresh_chip_styles()
        if was_active:
            self._trigger_card_wave(-1)
            self.btn_start.trigger_bounce()
        else:
            self._active_progress = 0.0
            self.update()

    def set_minutes(self, minutes: int) -> None:
        self.spin_minutes.setValue(max(1, min(480, minutes)))

    def get_minutes(self) -> int:
        return self.spin_minutes.value()

    def apply_translations(self, title: str, start_btn: str, cancel_btn: str) -> None:
        self.title_label.setText(title.upper())
        self.btn_start.setText(start_btn)
        self.btn_cancel.setText(cancel_btn)

    def refresh_theme(self) -> None:
        self._apply_step_button_styles()
        self._refresh_action_button_styles()
        self._refresh_chip_styles()
        self.badge_countdown.update()
        self.update()
