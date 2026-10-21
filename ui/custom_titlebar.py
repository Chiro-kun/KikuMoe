"""Custom client-side title bar (CSD) for KikuMoe 2.0.0.

Draws a sleek Cyber-Moe dark glass title bar with the KikuMoe logo icon,
brand title, version badge, current song subtitle, and custom vector
minimize / maximize / close buttons. Works on Windows, Wayland, and X11.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizeGrip, QWidget

_TITLE_BAR_HEIGHT = 36
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

    def enterEvent(self, a0) -> None:
        self._hover = True
        self.update()
        super().enterEvent(a0)

    def leaveEvent(self, a0) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(a0)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
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


class CustomTitleBar(QFrame):
    """Cyber-Moe CSD title bar: [Logo] KIKUMOE [2.0] · Song Title · [—] [□] [×]."""

    HEIGHT = _TITLE_BAR_HEIGHT

    def __init__(self, window: QWidget, icon: QIcon | None = None) -> None:
        super().__init__(window)
        self._window = window
        self.setObjectName("customTitleBar")
        self.setFixedHeight(self.HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(7)

        # 1. App Logo Icon (22x22 smooth anti-aliased)
        self._icon_label = QLabel()
        self._icon_label.setObjectName("titleBarIcon")
        self._icon_label.setFixedSize(QSize(22, 22))
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icon and not icon.isNull():
            pm = icon.pixmap(QSize(64, 64))
            if not pm.isNull():
                pm = pm.scaled(
                    20,
                    20,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._icon_label.setPixmap(pm)
        layout.addWidget(self._icon_label)

        # 2. Brand Wordmark + 2.0 Badge
        self._brand_label = QLabel("KIKUMOE")
        self._brand_label.setStyleSheet(
            "color: #ffffff; font-size: 12px; font-weight: 800; letter-spacing: 1.6px;"
            " background: transparent; border: none;"
        )
        layout.addWidget(self._brand_label)

        self._ver_badge = QLabel("2.0.0-beta1")
        self._ver_badge.setFixedHeight(18)
        self._ver_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ver_badge.setStyleSheet(
            "background: rgba(236, 24, 108, 0.25); color: #ff4797;"
            " border: 1px solid rgba(236, 24, 108, 0.50); border-radius: 5px;"
            " padding: 0px 5px; font-size: 9px; font-weight: 700;"
        )
        layout.addWidget(self._ver_badge)

        # 3. Spacer (song title removed from title bar as requested)
        self._title_label = QLabel("")
        self._title_label.setObjectName("titleBarTitle")
        self._title_label.setVisible(False)
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
        self.setStyleSheet(
            "QFrame#customTitleBar {"
            " background-color: rgba(8, 9, 15, 0.54);"
            " border-top-left-radius: 12px;"
            " border-top-right-radius: 12px;"
            " border-bottom: 1px solid rgba(255, 255, 255, 0.13);"
            "}"
        )

    def set_icon(self, icon: QIcon | None) -> None:
        if icon and not icon.isNull():
            pm = icon.pixmap(QSize(64, 64))
            if not pm.isNull():
                pm = pm.scaled(
                    20,
                    20,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._icon_label.setPixmap(pm)

    def set_title(self, title: str) -> None:
        """Keep internal label updated for compatibility without displaying song title in header."""
        self._title_label.setText("")

    def sync_maximize_button(self) -> None:
        if self._window.isMaximized():
            self._btn_max.set_kind("restore")
            self._btn_max.setToolTip("Ripristina")
        else:
            self._btn_max.set_kind("max")
            self._btn_max.setToolTip("Ingrandisci")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle:
                handle.startSystemMove()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
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

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if event and event.type() == QEvent.Type.Resize and isinstance(obj, QWidget):
            self._reposition(obj)
        return False

    def _reposition(self, window: QWidget) -> None:
        g = self._grip
        g.move(window.width() - g.width(), window.height() - g.height())


def install_size_grip(window: QWidget) -> None:
    grip = QSizeGrip(window)
    grip.setFixedSize(QSize(16, 16))
    grip.show()
    _GripPositioner(window, grip)
