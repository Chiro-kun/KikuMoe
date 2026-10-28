"""Custom client-side title bar (CSD) for KikuMoe 2.0.0.

Draws a sleek Cyber-Moe dark glass title bar with a high-contrast HiDPI-safe
KikuMoe logo badge, brand title, version badge, and custom vector
minimize / maximize / close buttons. Works on Windows, Wayland, and X11.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizeGrip, QWidget

from core.constants import APP_VERSION
from ui.themes.cyber_moe import PALETTE, accent_qcolor

_TITLE_BAR_HEIGHT = 38
_BTN_SIZE = QSize(42, _TITLE_BAR_HEIGHT)


class _WinCtrlButton(QPushButton):
    """Custom vector window control button (minimize, maximize, close) with click animation."""

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = kind  # "min", "max", "restore", "close"
        self._hover = False
        self._scale = 1.0
        self._anim_step = 0
        self.setFixedSize(_BTN_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)

    def set_kind(self, kind: str) -> None:
        self._kind = kind
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, a0) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(a0)

    def mousePressEvent(self, e) -> None:
        if e is not None and e.button() == Qt.MouseButton.LeftButton:
            self._anim_step = 1
            self._scale = 0.82
            self._anim_timer.start()
            self.update()
        super().mousePressEvent(e)

    def _tick_anim(self) -> None:
        frames = [0.82, 0.90, 0.98, 1.04, 1.02, 1.0]
        if 0 < self._anim_step <= len(frames):
            self._scale = frames[self._anim_step - 1]
            self._anim_step += 1
            self.update()
        else:
            self._scale = 1.0
            self._anim_timer.stop()
            self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0

        if self._hover:
            if self._kind == "close":
                painter.fillRect(self.rect(), QColor(232, 17, 35, 220))
            else:
                painter.fillRect(self.rect(), QColor(255, 255, 255, 22))

        painter.translate(cx, cy)
        painter.scale(self._scale, self._scale)
        painter.translate(-cx, -cy)

        fg = QColor("#ffffff") if self._hover else QColor("#a6adc4")
        pen = QPen(fg, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if self._kind == "min":
            painter.drawLine(QPointF(cx - 5.5, cy), QPointF(cx + 5.5, cy))
        elif self._kind == "max":
            painter.drawRoundedRect(QRectF(cx - 5.0, cy - 5.0, 10.0, 10.0), 1.5, 1.5)
        elif self._kind == "restore":
            painter.drawRoundedRect(QRectF(cx - 3.5, cy - 5.5, 8.0, 8.0), 1.2, 1.2)
            painter.drawRoundedRect(QRectF(cx - 5.5, cy - 3.5, 8.0, 8.0), 1.2, 1.2)
        elif self._kind == "close":
            painter.drawLine(QPointF(cx - 5.0, cy - 5.0), QPointF(cx + 5.0, cy + 5.0))
            painter.drawLine(QPointF(cx + 5.0, cy - 5.0), QPointF(cx - 5.0, cy + 5.0))

        painter.end()


class _TitleBarLogoBadge(QLabel):
    """
    HiDPI-safe, high-contrast KikuMoe brand icon widget for the title bar.
    - Loads the pristine high-res logo and uses Qt's area-averaging SmoothTransformation
      to downscale directly to physical device pixels (avoiding QPainter 2x2 bilinear aliasing).
    - Smoothly color-grades the dark crimson (#be1b55) into luminous neon sakura (#ff4294)
      while preserving 100% of the anti-aliased edges around the white inner sakura blossom.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(QSize(30, _TITLE_BAR_HEIGHT))
        self._hi_contrast_master: QImage | None = None
        self._cached_scaled: QImage | None = None
        self._cached_dpr: float = 0.0

    def set_icon(self, icon: QIcon | None) -> None:
        self._cached_scaled = None
        src_img: QImage | None = None

        # Prefer loading the pristine master directly to avoid intermediate QIcon resampling
        try:
            master_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "icons", "Kikumoe - no txt.png"
            )
            if os.path.exists(master_path):
                loaded = QImage(master_path)
                if not loaded.isNull():
                    src_img = loaded.convertToFormat(QImage.Format.Format_ARGB32)
        except Exception:
            src_img = None

        if src_img is None and icon is not None and not icon.isNull():
            pm = icon.pixmap(QSize(512, 512))
            if not pm.isNull():
                src_img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)

        if src_img is None or src_img.isNull():
            self._hi_contrast_master = None
            self.update()
            return

        src_img.setDevicePixelRatio(1.0)

        # Downscale to 256px width using area-averaging SmoothTransformation before color grading
        img = src_img.scaledToWidth(256, Qt.TransformationMode.SmoothTransformation)
        img.setDevicePixelRatio(1.0)

        # Auto-crop transparent margins
        w, h = img.width(), img.height()
        top, bottom, left, right = 0, h - 1, 0, w - 1

        while top < h and all(img.pixelColor(x, top).alpha() <= 8 for x in range(w)):
            top += 1
        while bottom > top and all(img.pixelColor(x, bottom).alpha() <= 8 for x in range(w)):
            bottom -= 1
        while left < w and all(
            img.pixelColor(left, y).alpha() <= 8 for y in range(top, bottom + 1)
        ):
            left += 1
        while right > left and all(
            img.pixelColor(right, y).alpha() <= 8 for y in range(top, bottom + 1)
        ):
            right -= 1

        if right >= left and bottom >= top:
            img = img.copy(left, top, right - left + 1, bottom - top + 1)

        cw, ch = img.width(), img.height()
        # Smooth continuous color-grading: preserve anti-aliased transitions to the white center
        # and subtle petal contour shading while boosting #be1b55 -> vibrant #ff4294
        for y in range(ch):
            y_lift = 1.04 - 0.08 * (y / max(1, ch))
            for x in range(cw):
                c = img.pixelColor(x, y)
                a = c.alpha()
                if a <= 2:
                    continue
                r, g = c.red(), c.green()
                # Smooth whiteness blend factor (in #be1b55 g=27; in white center g=255)
                t_white = max(0.0, min(1.0, (g - 28.0) / (248.0 - 28.0)))
                # Subtle petal shadow preservation (in #be1b55 r=190; petal shadows r~95..165)
                t_shade = max(0.48, min(1.0, r / 188.0))

                pr = min(255.0, 255.0 * t_shade * y_lift)
                pg = min(255.0, 68.0 * t_shade * y_lift)
                pb = min(255.0, 150.0 * t_shade * y_lift)

                out_r = int(round(pr + (255.0 - pr) * t_white))
                out_g = int(round(pg + (255.0 - pg) * t_white))
                out_b = int(round(pb + (255.0 - pb) * t_white))
                img.setPixelColor(x, y, QColor(out_r, out_g, out_b, a))

        self._hi_contrast_master = img
        self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0

        # Subtle ambient radial glow behind the logo so it stands out on any dark surface
        glow = QRadialGradient(QPointF(cx, cy), 15.0)
        glow.setColorAt(0.0, QColor(255, 72, 152, 58))
        glow.setColorAt(0.65, QColor(255, 72, 152, 18))
        glow.setColorAt(1.0, QColor(255, 72, 152, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), 15.0, 14.0)

        if self._hi_contrast_master is not None and not self._hi_contrast_master.isNull():
            dpr = float(self.devicePixelRatioF()) if hasattr(self, "devicePixelRatioF") else 1.0
            dpr = max(1.0, dpr)
            target_logical_w = 27.0
            phys_w = max(1, int(round(target_logical_w * dpr)))

            if (
                self._cached_scaled is None
                or self._cached_scaled.isNull()
                or abs(self._cached_dpr - dpr) > 0.01
                or self._cached_scaled.width() != phys_w
            ):
                scaled = self._hi_contrast_master.scaledToWidth(
                    phys_w,
                    Qt.TransformationMode.SmoothTransformation,
                )
                scaled.setDevicePixelRatio(dpr)
                self._cached_scaled = scaled
                self._cached_dpr = dpr

            dw = float(self._cached_scaled.width()) / dpr
            dh = float(self._cached_scaled.height()) / dpr
            x0 = cx - dw / 2.0
            y0 = cy - dh / 2.0 - 0.5
            painter.drawImage(QPointF(x0, y0), self._cached_scaled)
        else:
            pen = QPen(QColor("#ff4797"), 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.arcMoveTo(QRectF(cx - 9.0, cy - 8.0, 18.0, 16.0), 0)
            path.arcTo(QRectF(cx - 9.0, cy - 8.0, 18.0, 16.0), 0, 180)
            painter.drawPath(path)

        painter.end()


class _BrandTitleLabel(QLabel):
    """Custom-painted brand wordmark ('KIKUMOE') optically centered on the titlebar midline."""

    def __init__(self, text: str = "KIKUMOE", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFixedHeight(_TITLE_BAR_HEIGHT)
        font = QFont("Segoe UI")
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.ExtraBold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.4)
        self._brand_font = font
        fm = QFontMetricsF(self._brand_font)
        tight = fm.tightBoundingRect(text)
        self.setFixedWidth(int(tight.width()) + 4)

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        painter.setFont(self._brand_font)
        painter.setPen(QColor("#ffffff"))

        fm = QFontMetricsF(self._brand_font)
        tight = fm.tightBoundingRect(self.text())
        cy = float(self.height()) / 2.0
        tx = -tight.left()
        baseline_y = cy - (tight.top() + tight.bottom()) / 2.0
        painter.drawText(QPointF(tx, baseline_y), self.text())
        painter.end()


class _VersionBadgeLabel(QLabel):
    """Custom-painted version pill badge ('2.0.0-beta2') vertically and horizontally centered."""

    def __init__(self, text: str = APP_VERSION, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFixedHeight(_TITLE_BAR_HEIGHT)
        font = QFont("Segoe UI")
        font.setPixelSize(10)
        font.setWeight(QFont.Weight.Bold)
        self._badge_font = font
        fm = QFontMetricsF(self._badge_font)
        tight = fm.tightBoundingRect(text)
        pill_w = int(tight.width()) + 16
        self.setFixedWidth(max(66, pill_w))

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = float(self.width())
        h = float(self.height())
        cy = h / 2.0

        pill_h = 18.0
        pill_rect = QRectF(0.5, cy - pill_h / 2.0, w - 1.0, pill_h)

        bg_grad = QLinearGradient(pill_rect.topLeft(), pill_rect.bottomLeft())
        bg_grad.setColorAt(0.0, accent_qcolor(72))
        bg_grad.setColorAt(1.0, accent_qcolor(48))
        painter.setBrush(bg_grad)
        painter.setPen(QPen(accent_qcolor(135, "accent_hover"), 1.0))
        painter.drawRoundedRect(pill_rect, 5.5, 5.5)

        painter.setFont(self._badge_font)
        painter.setPen(QColor(PALETTE["text_accent"]))

        fm = QFontMetricsF(self._badge_font)
        tight = fm.tightBoundingRect(self.text())
        tx = (w - tight.width()) / 2.0 - tight.left()
        baseline_y = cy - (tight.top() + tight.bottom()) / 2.0
        painter.drawText(QPointF(tx, baseline_y), self.text())
        painter.end()


class CustomTitleBar(QFrame):
    """Cyber-Moe CSD title bar: [Logo] KIKUMOE [2.0.0-beta2] · [—] [□] [×]."""

    HEIGHT = _TITLE_BAR_HEIGHT

    def __init__(
        self,
        window: QWidget,
        icon: QIcon | None = None,
        title: str | None = None,
    ) -> None:
        super().__init__(window)
        self._window = window
        self.setObjectName("customTitleBar")
        self.setFixedHeight(self.HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(8)

        # 1. High-Contrast, HiDPI-Safe App Logo (30x38, centered at cy=19.0)
        self._icon_label = _TitleBarLogoBadge(self)
        self._icon_label.setObjectName("titleBarIcon")
        self._icon_label.set_icon(icon)
        layout.addWidget(self._icon_label)

        # 2. Brand Wordmark + Version Badge (both optically centered at cy=19.0)
        self._brand_label = _BrandTitleLabel("KIKUMOE", self)
        layout.addWidget(self._brand_label)

        self._ver_badge = _VersionBadgeLabel(APP_VERSION, self)
        layout.addWidget(self._ver_badge)

        # 3. Custom/Dialog Title Label
        self._title_label = QLabel(title or "", self)
        self._title_label.setObjectName("titleBarTitle")
        self._title_label.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none; padding-left: 2px;"
        )
        self._title_label.setVisible(bool(title))
        layout.addWidget(self._title_label)

        if title:
            self._brand_label.setVisible(False)
            self._ver_badge.setVisible(False)

        layout.addStretch(1)

        # 4. Window Control Buttons
        self._btn_min = _WinCtrlButton("min", self)
        self._btn_min.setToolTip("Minimizza")

        self._btn_max = _WinCtrlButton("max", self)
        self._btn_max.setToolTip("Ingrandisci")

        self._btn_close = _WinCtrlButton("close", self)
        self._btn_close.setToolTip("Chiudi")

        layout.addWidget(self._btn_min)
        layout.addWidget(self._btn_max)
        layout.addWidget(self._btn_close)

        self._btn_min.clicked.connect(window.showMinimized)
        self._btn_max.clicked.connect(self._toggle_maximize)
        self._btn_close.clicked.connect(window.close)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        self.setStyleSheet(
            "QFrame#customTitleBar {"
            f" background-color: {PALETTE['bg_titlebar']};"
            " border-top-left-radius: 12px;"
            " border-top-right-radius: 12px;"
            " border-bottom: 1px solid rgba(255, 255, 255, 0.13);"
            "}"
        )
        self._ver_badge.update()
        self.update()

    def set_icon(self, icon: QIcon | None) -> None:
        self._icon_label.set_icon(icon)

    def set_dialog_title(self, title: str | None) -> None:
        """Set a custom window/dialog title. If None, revert to brand mark and version badge."""
        if title:
            self._brand_label.setVisible(False)
            self._ver_badge.setVisible(False)
            self._title_label.setText(title)
            self._title_label.setVisible(True)
        else:
            self._title_label.setVisible(False)
            self._brand_label.setVisible(True)
            self._ver_badge.setVisible(True)

    def set_title(self, title: str) -> None:
        """Keep internal label updated for compatibility without displaying song title in header."""
        if not self._title_label.isVisible():
            self._title_label.setText("")

    def sync_maximize_button(self) -> None:
        if self._window.isMaximized():
            self._btn_max.set_kind("restore")
            self._btn_max.setToolTip("Ripristina")
        else:
            self._btn_max.set_kind("max")
            self._btn_max.setToolTip("Ingrandisci")

    def mousePressEvent(self, a0) -> None:
        if a0 is not None and a0.button() == Qt.MouseButton.LeftButton:
            wh = self._window.windowHandle()
            if wh is not None and wh.startSystemMove():
                return
            self._drag_offset = (
                a0.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, a0) -> None:
        if (
            a0 is not None
            and a0.buttons() & Qt.MouseButton.LeftButton
            and hasattr(self, "_drag_offset")
        ):
            self._window.move(a0.globalPosition().toPoint() - self._drag_offset)

    def mouseDoubleClickEvent(self, a0) -> None:
        if a0 is not None and a0.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()

    def _toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()


class _GripPositioner(QObject):
    """Event filter that keeps a QSizeGrip anchored to its window's bottom-right."""

    def __init__(self, window: QWidget, grip: QSizeGrip) -> None:
        super().__init__(window)
        self._grip = grip
        window.installEventFilter(self)
        self._reposition(window)

    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        if a1 and a1.type() == QEvent.Type.Resize and isinstance(a0, QWidget):
            self._reposition(a0)
        return False

    def _reposition(self, window: QWidget) -> None:
        g = self._grip
        g.move(window.width() - g.width(), window.height() - g.height())


def install_size_grip(window: QWidget) -> None:
    grip = QSizeGrip(window)
    grip.setFixedSize(QSize(16, 16))
    grip.show()
    _GripPositioner(window, grip)
