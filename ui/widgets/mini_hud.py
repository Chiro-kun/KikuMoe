"""Compact controls for the existing player window."""

from typing import Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ui.themes.cyber_moe import PALETTE


class MarqueeLabel(QWidget):
    def __init__(self, color: str, bold: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._text = ""
        self._color = QColor(color)
        self._offset = 0
        self._pause = 40
        self.setFixedHeight(18)
        self.setMinimumWidth(0)
        font = QFont("Segoe UI")
        font.setPixelSize(12 if bold else 11)
        font.setBold(bold)
        self.setFont(font)
        self._timer = QTimer(self)
        self._timer.setInterval(35)
        self._timer.timeout.connect(self._tick)

    def set_text(self, text: str) -> None:
        if self._text == text:
            return
        self._text = text
        self._offset = 0
        self._pause = 40
        self.setToolTip(text)
        self._timer.start()
        self.update()

    def _tick(self) -> None:
        if not self.isVisible() or self.fontMetrics().horizontalAdvance(self._text) <= self.width():
            self._offset = 0
            self._timer.stop()
        elif self._pause:
            self._pause -= 1
        else:
            self._offset += 1
            if self._offset > self.fontMetrics().horizontalAdvance(self._text) + 32:
                self._offset = 0
                self._pause = 40
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._timer.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._offset = 0
        self._pause = 40
        self._timer.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self.font())
        painter.setPen(self._color)
        width = self.fontMetrics().horizontalAdvance(self._text)
        painter.drawText(
            QRectF(-self._offset, 0, width + 2, self.height()),
            Qt.AlignmentFlag.AlignVCenter,
            self._text,
        )
        if self._offset:
            painter.drawText(
                QRectF(width + 32 - self._offset, 0, width + 2, self.height()),
                Qt.AlignmentFlag.AlignVCenter,
                self._text,
            )


class MiniIconButton(QPushButton):
    def __init__(self, kind: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(27, 27)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(kind == "pin")

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(PALETTE["accent"] if self.isChecked() else "#25293a")
        if self.isDown():
            bg = QColor(PALETTE["accent_pressed"])
        elif self.underMouse():
            bg = QColor(PALETTE["accent_hover"])
        p.setBrush(bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(1, 1, 25, 25), 7, 7)
        p.setPen(
            QPen(
                QColor("#ffffff"),
                1.6,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        if self.kind in ("play", "pause"):
            if self.kind == "pause":
                p.drawLine(QPointF(10, 8), QPointF(10, 19))
                p.drawLine(QPointF(17, 8), QPointF(17, 19))
            else:
                path = QPainterPath()
                path.moveTo(10, 8)
                path.lineTo(19, 13.5)
                path.lineTo(10, 19)
                path.closeSubpath()
                p.setBrush(QColor("#ffffff"))
                p.drawPath(path)
        elif self.kind in ("restore", "mini"):
            p.drawRoundedRect(QRectF(7, 8, 13, 11), 1, 1)
            if self.kind == "restore":
                p.drawLine(QPointF(8, 11), QPointF(19, 11))
            else:
                p.drawLine(QPointF(10, 16), QPointF(17, 16))
        elif self.kind == "pin":
            p.drawLine(QPointF(10, 8), QPointF(18, 8))
            p.drawLine(QPointF(11, 8), QPointF(11, 14))
            p.drawLine(QPointF(17, 8), QPointF(17, 14))
            p.drawLine(QPointF(9, 15), QPointF(19, 15))
            p.drawLine(QPointF(14, 15), QPointF(14, 20))
        else:
            p.drawLine(QPointF(9, 9), QPointF(18, 18))
            p.drawLine(QPointF(18, 9), QPointF(9, 18))


class MiniHud(QWidget):
    restore_requested = pyqtSignal()
    play_requested = pyqtSignal()
    pin_changed = pyqtSignal(bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("miniHud")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(
            f"QWidget#miniHud {{ background: #121523; border: 1px solid {PALETTE['border_card']}; "
            "border-radius: 12px; }"
            "QSlider::groove:horizontal { height: 4px; background: #35394d; border-radius: 2px; }"
            f"QSlider::sub-page:horizontal {{ background: {PALETTE['accent']}; "
            "border-radius: 2px; }"
            "QSlider::handle:horizontal { background: white; width: 10px; margin: -4px 0; "
            f"border: 2px solid {PALETTE['accent']}; border-radius: 6px; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(9)
        self.cover = QLabel()
        self.cover.setFixedSize(58, 58)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet("background: #25293a; border-radius: 8px;")
        layout.addWidget(self.cover)
        details = QVBoxLayout()
        details.setSpacing(1)
        self.title = MarqueeLabel("#ffffff", True)
        self.artist = MarqueeLabel("#a0a5b8")
        details.addWidget(self.title)
        details.addWidget(self.artist)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedHeight(18)
        self.volume.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        details.addWidget(self.volume)
        self.volume_popup = QLabel(self)
        self.volume_popup.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.volume_popup.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.volume_popup.setStyleSheet(
            f"background: {PALETTE['bg_surface_elevated']}; color: {PALETTE['text_primary']}; "
            f"border: 1px solid {PALETTE['accent']}; border-radius: 6px; "
            "font-size: 11px; font-weight: 700; padding: 3px 7px;"
        )
        self.volume_popup.hide()
        self._volume_opacity = QGraphicsOpacityEffect(self.volume_popup)
        self.volume_popup.setGraphicsEffect(self._volume_opacity)
        self._volume_animation = QPropertyAnimation(self._volume_opacity, b"opacity", self)
        self._volume_animation.setDuration(160)
        self._volume_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._volume_animation.finished.connect(self._finish_volume_animation)
        self._volume_timer = QTimer(self)
        self._volume_timer.setSingleShot(True)
        self._volume_timer.timeout.connect(self._hide_volume_popup)
        self.volume.valueChanged.connect(self._show_volume_popup)
        layout.addLayout(details, 1)
        controls = QVBoxLayout()
        controls.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(4)
        self.pin_button = MiniIconButton("pin")
        self.restore_button = MiniIconButton("restore")
        top.addWidget(self.pin_button)
        top.addWidget(self.restore_button)
        controls.addLayout(top)
        bottom = QHBoxLayout()
        bottom.setSpacing(4)
        self.play_button = MiniIconButton("play")
        self.close_button = MiniIconButton("close")
        bottom.addWidget(self.play_button)
        bottom.addWidget(self.close_button)
        controls.addLayout(bottom)
        layout.addLayout(controls)
        self.pin_button.toggled.connect(self.pin_changed)
        self.restore_button.clicked.connect(self.restore_requested)
        self.play_button.clicked.connect(self.play_requested)
        self.close_button.clicked.connect(self._close_window)
        self._drag_offset: Optional[QPoint] = None

    def _close_window(self) -> None:
        window = self.window()
        if window is not None:
            window.close()

    def _show_volume_popup(self, value: int) -> None:
        if not self.isVisible():
            return
        self.volume_popup.setText(f"{value}%")
        self.volume_popup.adjustSize()
        slider_pos = self.volume.mapTo(self, QPoint(0, 0))
        usable_width = max(0, self.volume.width() - 14)
        center_x = slider_pos.x() + 7 + round(usable_width * value / 100)
        x = max(
            2,
            min(
                self.width() - self.volume_popup.width() - 2,
                center_x - self.volume_popup.width() // 2,
            ),
        )
        y = max(2, slider_pos.y() - self.volume_popup.height() - 2)
        self.volume_popup.move(x, y)
        was_hidden = self.volume_popup.isHidden()
        self._volume_animation.stop()
        self._volume_timer.stop()
        self.volume_popup.show()
        self.volume_popup.raise_()
        self._volume_animation.setStartValue(0.0 if was_hidden else self._volume_opacity.opacity())
        self._volume_animation.setEndValue(1.0)
        self._volume_animation.start()
        self._volume_timer.start(1200)

    def _hide_volume_popup(self) -> None:
        self._volume_animation.stop()
        self._volume_animation.setStartValue(self._volume_opacity.opacity())
        self._volume_animation.setEndValue(0.0)
        self._volume_animation.start()

    def _finish_volume_animation(self) -> None:
        if self._volume_opacity.opacity() <= 0.0:
            self.volume_popup.hide()

    def hideEvent(self, event) -> None:
        self._volume_timer.stop()
        self._volume_animation.stop()
        self.volume_popup.hide()
        super().hideEvent(event)

    def set_cover(self, pixmap: Optional[QPixmap]) -> None:
        if pixmap is None or pixmap.isNull():
            self.cover.clear()
            return
        size = 58.0
        dpr = max(1.0, self.cover.devicePixelRatioF())
        rounded = QPixmap(round(size * dpr), round(size * dpr))
        rounded.setDevicePixelRatio(dpr)
        rounded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, size, size), 8, 8)
        painter.setClipPath(clip)
        side = float(min(pixmap.width(), pixmap.height()))
        source = QRectF((pixmap.width() - side) / 2, (pixmap.height() - side) / 2, side, side)
        painter.drawPixmap(QRectF(0, 0, size, size), pixmap, source)
        painter.end()
        self.cover.setPixmap(rounded)

    def mousePressEvent(self, event: Optional[QMouseEvent]) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            if window is not None:
                handle = window.windowHandle()
                if handle is not None and handle.startSystemMove():
                    return
                self._drag_offset = (
                    event.globalPosition().toPoint() - window.frameGeometry().topLeft()
                )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Optional[QMouseEvent]) -> None:
        if event is not None and event.buttons() & Qt.MouseButton.LeftButton and self._drag_offset:
            window = self.window()
            if window is not None:
                window.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)
