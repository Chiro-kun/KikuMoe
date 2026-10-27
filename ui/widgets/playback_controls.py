"""
PlaybackControls widget for KikuMoe 2.0.0
Sculpted Frosted-Glass Control Deck with 60 FPS click bounce & ripple animations.
Follows the strict visual rule:
- Inactive buttons = neutral monochrome (no color)
- Active buttons = vibrant accent colored
"""

from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ui.themes.cyber_moe import PALETTE


class AnimatedVectorButton(QPushButton):
    """Base button providing 60 FPS tactile click bounce and expanding ripple animation."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._hover = False
        self._pressed = False
        self._anim_scale = 1.0
        self._ripple_progress = 0.0
        self._anim_step = 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim_timer = QTimer(self)
        self._anim_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_click_anim)

    def enterEvent(self, a0) -> None:
        self._hover = True
        self.update()
        super().enterEvent(a0)

    def leaveEvent(self, a0) -> None:
        self._hover = False
        self._pressed = False
        self.update()
        super().leaveEvent(a0)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._anim_step = 1
            self._anim_scale = 0.85
            self._ripple_progress = 0.1
            self._anim_timer.start()
            self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(e)

    def _tick_click_anim(self) -> None:
        scales = [0.85, 0.91, 0.98, 1.05, 1.07, 1.04, 1.02, 1.00, 1.00, 1.00]
        if 0 < self._anim_step <= len(scales):
            self._anim_scale = scales[self._anim_step - 1]
            self._ripple_progress = self._anim_step / float(len(scales))
            self._anim_step += 1
            self.update()
        else:
            self._anim_scale = 1.0
            self._ripple_progress = 0.0
            self._anim_timer.stop()
            self.update()

    def _apply_scale_and_ripple(
        self, painter: QPainter, cx: float, cy: float, base_r: float, ripple_col: QColor
    ) -> None:
        if 0.0 < self._ripple_progress < 1.0:
            alpha = int(125 * (1.0 - self._ripple_progress))
            rc = QColor(ripple_col)
            rc.setAlpha(max(0, alpha))
            painter.setPen(QPen(rc, 1.8))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            rr = base_r * (0.75 + 0.42 * self._ripple_progress)
            painter.drawEllipse(QPointF(cx, cy), rr, rr)

        painter.translate(cx, cy)
        painter.scale(self._anim_scale, self._anim_scale)
        painter.translate(-cx, -cy)


class HeroPlayButton(AnimatedVectorButton):
    """
    62x62px sculpted Hero Play/Pause button:
    - Active (playing): vibrant neon magenta gradient + outer glow ring
    - Inactive (stopped/paused): neutral dark glass disc (lights up on hover)
    """

    def __init__(self, parent: Optional[QWidget] = None, size: int = 62):
        super().__init__(parent)
        self._size = size
        self._is_playing = False
        self._is_paused = False
        self._accent = QColor(PALETTE["accent"])
        self._accent_hover = QColor(PALETTE["accent_hover"])
        self._accent_pressed = QColor(PALETTE["accent_pressed"])
        self.setFixedSize(self._size, self._size)

    def set_playing_state(self, is_playing: bool, is_paused: bool = False) -> None:
        if self._is_playing != is_playing or self._is_paused != is_paused:
            self._is_playing = is_playing
            self._is_paused = is_paused
            self.update()

    def set_accent_color(self, color_str: str) -> None:
        self._accent = QColor(color_str)
        self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0
        active = self._is_playing and not self._is_paused

        self._apply_scale_and_ripple(painter, cx, cy, (w / 2.0) - 4.0, self._accent_hover)

        # 1. Soft Outer Radial Glow (only when active or hovered)
        if active or self._hover:
            glow_r = w / 2.0
            glow = QRadialGradient(QPointF(cx, cy), glow_r)
            c_glow = QColor(self._accent)
            c_glow.setAlpha(105 if active else 55)
            glow.setColorAt(0.45, c_glow)
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # 2. Decorative Outer Halo Ring
        outer_ring_r = (w / 2.0) - 2.0
        if active:
            ring_col = QColor(self._accent_hover)
            ring_col.setAlpha(165)
        elif self._hover:
            ring_col = QColor(255, 255, 255, 85)
        else:
            ring_col = QColor(255, 255, 255, 32)
        painter.setPen(QPen(ring_col, 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), outer_ring_r, outer_ring_r)

        # 3. Inner Sculpted Disc (Colored when active, Neutral dark glass when inactive)
        disc_r = (w / 2.0) - 6.5
        grad = QLinearGradient(cx, cy - disc_r, cx, cy + disc_r)
        if active:
            if self._pressed:
                grad.setColorAt(0.0, self._accent_pressed)
                grad.setColorAt(1.0, QColor("#8a0a3d"))
            else:
                grad.setColorAt(0.0, self._accent_hover)
                grad.setColorAt(1.0, QColor("#ba0e52"))
            rim_col = QColor(255, 255, 255, 80)
            icon_col = QColor("#ffffff")
        else:
            if self._hover:
                grad.setColorAt(0.0, QColor(48, 53, 76, 240))
                grad.setColorAt(1.0, QColor(28, 32, 48, 240))
                rim_col = QColor(255, 255, 255, 70)
                icon_col = QColor("#ffffff")
            else:
                grad.setColorAt(0.0, QColor(34, 38, 56, 230))
                grad.setColorAt(1.0, QColor(20, 23, 36, 230))
                rim_col = QColor(255, 255, 255, 38)
                icon_col = QColor("#9ca3b8")

        painter.setPen(QPen(rim_col, 1.0))
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(QPointF(cx, cy), disc_r, disc_r)

        # 4. Play / Pause Icon
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(icon_col)
        if active:
            bar_w = 4.6
            bar_h = 16.0
            gap = 5.0
            left_x = cx - gap / 2.0 - bar_w
            right_x = cx + gap / 2.0
            top_y = cy - bar_h / 2.0
            painter.drawRoundedRect(QRectF(left_x, top_y, bar_w, bar_h), 2.0, 2.0)
            painter.drawRoundedRect(QRectF(right_x, top_y, bar_w, bar_h), 2.0, 2.0)
        else:
            tri_w = 14.5
            tri_h = 16.5
            offset_x = 2.0
            p1 = QPointF(cx - tri_w / 2.0 + offset_x, cy - tri_h / 2.0)
            p2 = QPointF(cx - tri_w / 2.0 + offset_x, cy + tri_h / 2.0)
            p3 = QPointF(cx + tri_w / 2.0 + offset_x, cy)
            painter.drawPolygon(QPolygonF([p1, p2, p3]))

        painter.end()


class StopButton(AnimatedVectorButton):
    """
    42x42px circular Stop button:
    - At rest: monochrome neutral gray (brighter icon when stream is playing, dim when stopped)
    - On hover / press: vibrant magenta highlight
    """

    def __init__(self, parent: Optional[QWidget] = None, size: int = 42):
        super().__init__(parent)
        self._active = False
        self.setFixedSize(size, size)

    def set_active(self, active: bool) -> None:
        if self._active != active:
            self._active = active
            self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0
        r = (w / 2.0) - 2.0

        self._apply_scale_and_ripple(painter, cx, cy, r, QColor(PALETTE["accent"]))

        if self._hover or self._pressed:
            bg = QColor(236, 24, 108, 45 if self._pressed else 30)
            border = QColor(236, 24, 108, 150)
            icon_col = QColor("#ffffff")
        else:
            bg = QColor(255, 255, 255, 12)
            border = QColor(255, 255, 255, 24)
            icon_col = QColor("#b0b7cc" if self._active else "#6e748a")

        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.0))
        painter.drawEllipse(QPointF(cx, cy), r, r)

        sq = 11.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(icon_col)
        painter.drawRoundedRect(QRectF(cx - sq / 2.0, cy - sq / 2.0, sq, sq), 2.5, 2.5)
        painter.end()


class ForceStopButton(AnimatedVectorButton):
    """
    36x36px circular Force Reset button:
    - At rest: monochrome neutral gray (no color)
    - On hover / press: vibrant magenta highlight
    """

    def __init__(self, parent: Optional[QWidget] = None, size: int = 36):
        super().__init__(parent)
        self._active = False
        self.setFixedSize(size, size)

    def set_active(self, active: bool) -> None:
        if self._active != active:
            self._active = active
            self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0
        r = (w / 2.0) - 2.0

        self._apply_scale_and_ripple(painter, cx, cy, r, QColor(PALETTE["accent"]))

        if self._hover or self._pressed:
            bg = QColor(236, 24, 108, 45 if self._pressed else 30)
            border = QColor(236, 24, 108, 150)
            bolt_col = QColor("#ffffff")
        else:
            bg = QColor(255, 255, 255, 12)
            border = QColor(255, 255, 255, 24)
            bolt_col = QColor("#b0b7cc" if self._active else "#6e748a")

        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.0))
        painter.drawEllipse(QPointF(cx, cy), r, r)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bolt_col)
        bolt = QPolygonF(
            [
                QPointF(cx + 1.5, cy - 7.0),
                QPointF(cx - 4.5, cy + 0.8),
                QPointF(cx - 0.3, cy + 0.8),
                QPointF(cx - 1.8, cy + 7.0),
                QPointF(cx + 4.5, cy - 0.8),
                QPointF(cx + 0.3, cy - 0.8),
            ]
        )
        painter.drawPolygon(bolt)
        painter.end()


class SleepButton(AnimatedVectorButton):
    """
    42px circular button (or 88px pill when countdown is active):
    - Active (ONLY when sleep timer countdown is running): colored magenta moon & border
    - Inactive (when timer is off): monochrome neutral gray
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._active = False
        self._drawer_open = True
        self._countdown_text = ""
        self.setFixedSize(42, 42)

    def set_drawer_open(self, is_open: bool) -> None:
        if self._drawer_open != is_open:
            self._drawer_open = is_open
            self.update()

    def set_countdown(self, active: bool, text: str = "") -> None:
        self._active = active
        self._countdown_text = text
        if active and text:
            self.setFixedSize(88, 42)
        else:
            self.setFixedSize(42, 42)
        self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cx_btn = w / 2.0
        cy = h / 2.0
        radius = (h - 3.0) / 2.0
        rect = QRectF(1.5, 1.5, w - 3.0, h - 3.0)
        is_colored = self._active

        self._apply_scale_and_ripple(painter, cx_btn, cy, radius, QColor(PALETTE["accent"]))

        if is_colored:
            bg = QColor(236, 24, 108, 52 if self._hover else 36)
            border = QColor(PALETTE["accent"])
            icon_col = QColor("#ffffff" if self._hover else PALETTE["accent_hover"])
        elif self._hover or self._pressed:
            bg = QColor(236, 24, 108, 28)
            border = QColor(236, 24, 108, 120)
            icon_col = QColor("#ffffff")
        else:
            bg = QColor(255, 255, 255, 12)
            border = QColor(255, 255, 255, 24)
            icon_col = QColor("#9ea4ba" if self._drawer_open else "#6e748a")

        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(rect, radius, radius)

        cx = 18.0 if (self._active and self._countdown_text) else w / 2.0
        r_outer = 6.5
        outer_path = QPainterPath()
        outer_path.addEllipse(QPointF(cx, cy), r_outer, r_outer)

        cut_path = QPainterPath()
        cut_path.addEllipse(QPointF(cx + 3.2, cy - 2.2), r_outer * 0.88, r_outer * 0.88)

        moon_path = outer_path.subtracted(cut_path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(icon_col)
        painter.drawPath(moon_path)

        if self._active and self._countdown_text:
            painter.setPen(QColor("#ffffff"))
            font = QFont(self.font())
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            text_rect = QRectF(30.0, 0.0, w - 36.0, h)
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignCenter,
                self._countdown_text,
            )

        painter.end()


class AutoplayPillButton(AnimatedVectorButton):
    """
    48x36px sculpted LED toggle pill button ('AUTO'):
    - Active (checked): colored magenta border, green/magenta dot, bright text
    - Inactive (unchecked): monochrome neutral gray
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(48, 36)

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0
        rect = QRectF(1.5, 1.5, w - 3.0, h - 3.0)
        radius = (h - 3.0) / 2.0
        checked = self.isChecked()

        self._apply_scale_and_ripple(painter, cx, cy, radius, QColor(PALETTE["accent"]))

        if checked:
            bg = QColor(236, 24, 108, 48 if self._hover else 34)
            border = QColor(PALETTE["accent"])
            text_col = QColor("#ffffff")
            dot_col = QColor(PALETTE["accent_hover"])
        else:
            bg = QColor(255, 255, 255, 22 if self._hover else 10)
            border = QColor(255, 255, 255, 48 if self._hover else 22)
            text_col = QColor("#c4c9dc" if self._hover else "#6e748a")
            dot_col = QColor("#6e748a")

        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(rect, radius, radius)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot_col)
        painter.drawEllipse(QPointF(11.0, cy), 2.4, 2.4)

        font = QFont(self.font())
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(text_col)
        painter.drawText(
            QRectF(15.0, 0.0, w - 18.0, h),
            Qt.AlignmentFlag.AlignCenter,
            "AUTO",
        )
        painter.end()


class SpeakerButton(AnimatedVectorButton):
    """
    Dynamic Speaker Button with optically centered speaker + sound wave geometry:
    - At rest: neutral monochrome (crisp silver when unmuted, dim gray when muted)
    - On hover / press: vibrant magenta highlight
    """

    def __init__(self, parent: Optional[QWidget] = None, size: int = 32):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._volume = 60
        self._muted = False

    def set_volume_state(self, volume: int, muted: bool) -> None:
        self._volume = volume
        self._muted = muted
        self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0
        r = (w / 2.0) - 1.5
        is_active = not self._muted and self._volume > 0

        self._apply_scale_and_ripple(painter, cx, cy, r, QColor(PALETTE["accent"]))

        if self._hover or self._pressed:
            bg = QColor(236, 24, 108, 42 if self._pressed else 26)
            border = QColor(236, 24, 108, 145)
            color = QColor("#ffffff")
        else:
            bg = QColor(255, 255, 255, 12)
            border = QColor(255, 255, 255, 24)
            color = QColor("#b8bfd4" if is_active else "#64687d")

        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.0))
        painter.drawEllipse(QPointF(cx, cy), r, r)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)

        # Shift speaker + waves by dx so total visual bounding box is centered on cx
        dx = -2.2 if (is_active and self._volume >= 50) else -1.2
        scx = cx + dx

        # Speaker horn body
        painter.drawRoundedRect(QRectF(scx - 5.8, cy - 2.6, 3.0, 5.2), 0.9, 0.9)
        poly = QPolygonF(
            [
                QPointF(scx - 3.4, cy - 2.6),
                QPointF(scx + 0.6, cy - 6.0),
                QPointF(scx + 0.6, cy + 6.0),
                QPointF(scx - 3.4, cy + 2.6),
            ]
        )
        painter.drawPolygon(poly)

        # Sound waves or Mute X
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        if not is_active:
            painter.drawLine(QPointF(scx + 3.0, cy - 2.6), QPointF(scx + 6.6, cy + 2.6))
            painter.drawLine(QPointF(scx + 6.6, cy - 2.6), QPointF(scx + 3.0, cy + 2.6))
        else:
            painter.drawArc(QRectF(scx - 1.2, cy - 4.2, 6.8, 8.4), -55 * 16, 110 * 16)
            if self._volume >= 50:
                painter.drawArc(QRectF(scx + 1.0, cy - 6.6, 9.2, 13.2), -55 * 16, 110 * 16)

        painter.end()


class PlaybackControls(QFrame):
    play_clicked = pyqtSignal()
    pause_resume_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    force_stop_clicked = pyqtSignal()
    sleep_toggle_clicked = pyqtSignal()
    volume_changed = pyqtSignal(int)
    mute_toggled = pyqtSignal(bool)
    autoplay_toggled = pyqtSignal(bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("consoleDeck")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._is_playing = False
        self._is_paused = False
        self._is_muted = False
        self._volume = 60

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)

        # 1. Sculpted Transport Deck: [Force ⚡]  [Stop ⏹]  ( HERO PLAY )  [Sleep 🌙]  [● AUTO]
        transport_row = QHBoxLayout()
        transport_row.setContentsMargins(0, 0, 0, 0)
        transport_row.setSpacing(12)

        self.btn_force_stop = ForceStopButton(size=36)
        self.btn_force_stop.setToolTip("Force Reset Audio")
        self.btn_force_stop.clicked.connect(self.force_stop_clicked.emit)

        self.btn_stop = StopButton(size=42)
        self.btn_stop.setToolTip("Stop (S)")
        self.btn_stop.clicked.connect(self.stop_clicked.emit)
        self.btn_stop.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_stop.customContextMenuRequested.connect(self._show_stop_context_menu)

        self.hero_play = HeroPlayButton(size=62)
        self.hero_play.setToolTip("Play / Pause (Space)")
        self.hero_play.clicked.connect(self._on_hero_clicked)

        self.btn_sleep = SleepButton()
        self.btn_sleep.setToolTip("Sleep Timer")
        self.btn_sleep.clicked.connect(self.sleep_toggle_clicked.emit)

        self.btn_autoplay = AutoplayPillButton()
        self.btn_autoplay.setToolTip("Autoplay")
        self.btn_autoplay.toggled.connect(self._on_autoplay_pill_toggled)

        # Keep hidden QCheckBox for full backward compatibility
        self.chk_autoplay = QCheckBox("Autoplay")
        self.chk_autoplay.setVisible(False)
        self.chk_autoplay.toggled.connect(self._on_chk_autoplay_toggled)

        transport_row.addStretch(1)
        transport_row.addWidget(self.btn_force_stop)
        transport_row.addWidget(self.btn_stop)
        transport_row.addSpacing(6)
        transport_row.addWidget(self.hero_play)
        transport_row.addSpacing(6)
        transport_row.addWidget(self.btn_sleep)
        transport_row.addWidget(self.btn_autoplay)
        transport_row.addStretch(1)

        root.addLayout(transport_row)

        # 2. Full-Width Volume Row: [Speaker] [-------- Slider --------] [ 60% ]
        vol_row = QHBoxLayout()
        vol_row.setContentsMargins(2, 0, 2, 0)
        vol_row.setSpacing(10)

        self.speaker_btn = SpeakerButton(size=32)
        self.speaker_btn.setCheckable(True)
        self.speaker_btn.setToolTip("Mute / Unmute (M)")
        self.speaker_btn.clicked.connect(self._on_speaker_clicked)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(60)
        self.volume_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.volume_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.volume_slider.valueChanged.connect(self._on_slider_changed)

        self.volume_label = QLabel("60%")
        self.volume_label.setObjectName("timeDisplayLabel")
        self.volume_label.setFixedSize(44, 24)
        self.volume_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.volume_label.setStyleSheet(
            "background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.12);"
            " border-radius: 7px; padding: 2px 4px; color: #e2e6f3;"
            " font-size: 11px; font-weight: 700;"
        )

        vol_row.addWidget(self.speaker_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        vol_row.addWidget(self.volume_slider, 1, Qt.AlignmentFlag.AlignVCenter)
        vol_row.addWidget(self.volume_label, 0, Qt.AlignmentFlag.AlignVCenter)

        root.addLayout(vol_row)

    def _show_stop_context_menu(self, pos) -> None:
        menu = QMenu(self)
        act_force = menu.addAction("Force Stop / Reset Audio")
        action = menu.exec(self.btn_stop.mapToGlobal(pos))
        if action == act_force:
            self.force_stop_clicked.emit()

    def _on_hero_clicked(self) -> None:
        if not self._is_playing and not self._is_paused:
            self.play_clicked.emit()
        else:
            self.pause_resume_clicked.emit()

    def _on_speaker_clicked(self) -> None:
        self._is_muted = not self._is_muted
        self.speaker_btn.setChecked(self._is_muted)
        self.speaker_btn.set_volume_state(self.volume_slider.value(), self._is_muted)
        self.mute_toggled.emit(self._is_muted)

    def _on_slider_changed(self, value: int) -> None:
        self._volume = value
        self.volume_label.setText(f"{value}%")
        self.speaker_btn.set_volume_state(value, self._is_muted)
        self.volume_changed.emit(value)

    def set_playing_state(self, is_playing: bool, is_paused: bool = False) -> None:
        self._is_playing = is_playing
        self._is_paused = is_paused
        stream_active = is_playing and not is_paused
        self.hero_play.set_playing_state(is_playing, is_paused)
        self.btn_stop.set_active(stream_active)
        self.btn_force_stop.set_active(stream_active)

    def set_volume(self, value: int) -> None:
        self._volume = value
        self.volume_slider.setValue(value)
        self.volume_label.setText(f"{value}%")
        self.speaker_btn.set_volume_state(value, self._is_muted)

    def set_muted(self, muted: bool) -> None:
        self._is_muted = muted
        self.speaker_btn.setChecked(muted)
        self.speaker_btn.set_volume_state(self.volume_slider.value(), muted)

    def set_sleep_countdown(self, active: bool, remaining_sec: int = 0) -> None:
        if active and remaining_sec > 0:
            m, s = divmod(max(0, remaining_sec), 60)
            self.btn_sleep.set_countdown(True, f"{m:02d}:{s:02d}")
        else:
            self.btn_sleep.set_countdown(False, "")

    def set_sleep_active(self, active: bool, text: str = "") -> None:
        self.btn_sleep.set_countdown(active, text)

    def set_sleep_drawer_open(self, is_open: bool) -> None:
        self.btn_sleep.set_drawer_open(is_open)

    def set_autoplay(self, enabled: bool) -> None:
        self.chk_autoplay.blockSignals(True)
        self.chk_autoplay.setChecked(enabled)
        self.chk_autoplay.blockSignals(False)
        self.btn_autoplay.blockSignals(True)
        self.btn_autoplay.setChecked(enabled)
        self.btn_autoplay.blockSignals(False)
        self.btn_autoplay.update()

    def set_autoplay_text(self, text: str) -> None:
        self.chk_autoplay.setText(text)
        self.btn_autoplay.setToolTip(text)

    def _on_autoplay_pill_toggled(self, checked: bool) -> None:
        self.chk_autoplay.blockSignals(True)
        self.chk_autoplay.setChecked(checked)
        self.chk_autoplay.blockSignals(False)
        self.autoplay_toggled.emit(checked)

    def _on_chk_autoplay_toggled(self, checked: bool) -> None:
        self.btn_autoplay.blockSignals(True)
        self.btn_autoplay.setChecked(checked)
        self.btn_autoplay.blockSignals(False)
        self.btn_autoplay.update()
        self.autoplay_toggled.emit(checked)
