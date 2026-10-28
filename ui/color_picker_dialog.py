"""
Modern Cyber-Moe Accent Color Picker Dialog for KikuMoe.

Provides a frameless, high-DPI, GPU/QPainter-accelerated color picker dialog:
- 2D Saturation/Value gradient canvas with high-contrast dual-ring cursor
- Full-spectrum vertical rainbow Hue slider with smooth pill thumb
- Dynamic Before/After comparison pill with one-click restore
- Monospace HEX input with validation and one-click copy feedback
- Crisp non-truncated RGB (0..255) and HSV (H°, S%, V%) numeric spinboxes
- Built-in screen eyedropper with live 9x9 magnified pixel loupe
- Curated 16-color Cyber-Moe / Neon quick palette
- 8 user-customizable saved color slots persisted in QSettings
- Dynamic contrast-aware OK button previewing real UI accent styles
- Smooth Cyber-Glass entrance and exit animations
"""

from __future__ import annotations

from typing import Any, Callable, cast

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSettings,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QCloseEvent,
    QColor,
    QCursor,
    QEnterEvent,
    QFont,
    QGuiApplication,
    QIcon,
    QImage,
    QKeyEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QShowEvent,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.constants import (
    APP_SETTINGS,
    DEFAULT_ACCENT_COLOR,
    KEY_CUSTOM_ACCENT_PALETTE,
    ORG_NAME,
)
from core.i18n import I18n
from ui.custom_titlebar import CustomTitleBar
from ui.themes.cyber_moe import (
    PALETTE,
    derive_accent_tokens,
    get_cyber_moe_stylesheet,
    is_valid_hex_color,
    normalize_hex_color,
)
from ui.vector_icons import (
    get_check_icon,
    get_copy_icon,
    get_eyedropper_icon,
)
from ui.windows_titlebar import apply_windows_titlebar_dark_mode

def _extract_hsv_f(col: QColor) -> tuple[float, float, float]:
    """Extract (h, s, v) as non-optional floats in 0.0..1.0 from QColor."""
    raw_h, raw_s, raw_v, _ = col.getHsvF()
    h = float(raw_h) if raw_h is not None and raw_h >= 0.0 else -1.0
    s = float(raw_s) if raw_s is not None else 0.0
    v = float(raw_v) if raw_v is not None else 0.0
    return max(-1.0, min(1.0, h)), max(0.0, min(1.0, s)), max(0.0, min(1.0, v))


# Curated Cyber-Moe & Neon quick palette swatches (16 colors)
QUICK_PALETTE_COLORS: tuple[str, ...] = (
    # Top 5: KikuMoe Theme Defaults
    "#ec186c",  # Cyber Moe (Default Neon Pink)
    "#ff2a85",  # Midnight AMOLED
    "#ff7eb3",  # Sakura Bloom
    "#00e676",  # Neon Matrix (Acid Green)
    "#00d2ff",  # Ocean Cyan
    # Curated Vibrant Accents
    "#a855f7",  # Electric Purple
    "#6366f1",  # Neon Indigo
    "#38bdf8",  # Sky Blue
    "#14b8a6",  # Cyber Teal
    "#10b981",  # Emerald Mint
    "#84cc16",  # Lime Glow
    "#facc15",  # Cyber Yellow
    "#ff8800",  # Neon Amber
    "#f97316",  # Vivid Orange
    "#f43f5e",  # Rose Crimson
    "#fb7185",  # Soft Coral
)


class SVColorCanvas(QWidget):
    """
    2D Saturation-Value gradient canvas with rounded corners and high-contrast handle.
    x-axis: Saturation (0.0 .. 1.0)
    y-axis: Value (1.0 .. 0.0)
    """

    color_changed = pyqtSignal(float, float)  # (sat, val)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(200, 160)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self._hue: float = 336.0 / 360.0
        self._sat: float = 0.88
        self._val: float = 1.0
        self._dragging: bool = False

    def set_hsv(self, h: float, s: float, v: float) -> None:
        self._hue = max(0.0, min(1.0, float(h)))
        self._sat = max(0.0, min(1.0, float(s)))
        self._val = max(0.0, min(1.0, float(v)))
        self.update()

    def set_hue(self, h: float) -> None:
        self._hue = max(0.0, min(1.0, float(h)))
        self.update()

    def _update_from_pos(self, pos: QPointF) -> None:
        w = max(1.0, float(self.width()))
        h = max(1.0, float(self.height()))
        sat = max(0.0, min(1.0, pos.x() / w))
        val = max(0.0, min(1.0, 1.0 - (pos.y() / h)))
        self._sat = sat
        self._val = val
        self.update()
        self.color_changed.emit(sat, val)

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None and a0.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._update_from_pos(a0.position())
        super().mousePressEvent(a0)

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None and self._dragging:
            self._update_from_pos(a0.position())
        super().mouseMoveEvent(a0)

    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None and a0.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
        super().mouseReleaseEvent(a0)

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0.0, 0.0, w, h)
        radius = 10.0

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.setClipPath(path)

        # 1. Horizontal White -> Pure Hue gradient
        pure_hue = QColor.fromHsvF(self._hue, 1.0, 1.0)
        grad_h = QLinearGradient(0.0, 0.0, w, 0.0)
        grad_h.setColorAt(0.0, QColor(255, 255, 255))
        grad_h.setColorAt(1.0, pure_hue)
        painter.fillRect(rect, grad_h)

        # 2. Vertical Transparent -> Pure Black gradient
        grad_v = QLinearGradient(0.0, 0.0, 0.0, h)
        grad_v.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad_v.setColorAt(1.0, QColor(0, 0, 0, 255))
        painter.fillRect(rect, grad_v)

        # 3. Inner glass border
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        # 4. High-contrast dual-ring cursor
        cx = self._sat * w
        cy = (1.0 - self._val) * h
        current_col = QColor.fromHsvF(self._hue, self._sat, self._val)

        # Outer dark shadow
        painter.setPen(QPen(QColor(0, 0, 0, 160), 2.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), 7.5, 7.5)

        # Inner crisp white ring with color fill
        painter.setPen(QPen(QColor(255, 255, 255, 240), 1.8))
        painter.setBrush(current_col)
        painter.drawEllipse(QPointF(cx, cy), 5.5, 5.5)

        painter.end()


class HueSpectrumSlider(QWidget):
    """
    Vertical 360-degree rainbow spectrum bar with smooth capsule thumb indicator.
    """

    hue_changed = pyqtSignal(float)  # hue in 0.0 .. 1.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(26)
        self.setMinimumHeight(160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self._hue: float = 336.0 / 360.0
        self._dragging: bool = False

    def hue(self) -> float:
        return self._hue

    def set_hue(self, h: float) -> None:
        self._hue = max(0.0, min(1.0, float(h)))
        self.update()

    def _update_from_pos(self, pos: QPointF) -> None:
        pad = 6.0
        usable_h = max(1.0, float(self.height()) - pad * 2.0)
        y = max(0.0, min(usable_h, pos.y() - pad))
        self._hue = y / usable_h
        self.update()
        self.hue_changed.emit(self._hue)

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None and a0.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._update_from_pos(a0.position())
        super().mousePressEvent(a0)

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None and self._dragging:
            self._update_from_pos(a0.position())
        super().mouseMoveEvent(a0)

    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None and a0.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
        super().mouseReleaseEvent(a0)

    def wheelEvent(self, a0: QWheelEvent | None) -> None:
        if a0 is not None:
            delta = a0.angleDelta().y()
            step = (delta / 120.0) * (3.0 / 360.0)
            self._hue = max(0.0, min(1.0, self._hue - step))
            self.update()
            self.hue_changed.emit(self._hue)
            a0.accept()
        else:
            super().wheelEvent(a0)

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0.0, 0.0, w, h)
        radius = 10.0

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.setClipPath(path)

        # 1. 360-degree rainbow spectrum gradient
        grad = QLinearGradient(0.0, 0.0, 0.0, h)
        stops = [
            (0.0, QColor(255, 0, 0)),
            (1.0 / 6.0, QColor(255, 255, 0)),
            (2.0 / 6.0, QColor(0, 255, 0)),
            (3.0 / 6.0, QColor(0, 255, 255)),
            (4.0 / 6.0, QColor(0, 0, 255)),
            (5.0 / 6.0, QColor(255, 0, 255)),
            (1.0, QColor(255, 0, 0)),
        ]
        for pos, col in stops:
            grad.setColorAt(pos, col)
        painter.fillRect(rect, grad)

        # 2. Inner glass border
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        # 3. Smooth pill thumb indicator
        pad = 6.0
        usable_h = h - pad * 2.0
        ty = pad + self._hue * usable_h
        thumb_h = 10.0
        thumb_rect = QRectF(1.5, ty - thumb_h / 2.0, w - 3.0, thumb_h)

        hue_col = QColor.fromHsvF(self._hue, 1.0, 1.0)

        # Outer dark shadow outline
        painter.setPen(QPen(QColor(0, 0, 0, 180), 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(thumb_rect, 5.0, 5.0)

        # Crisp white frame with pure hue fill
        painter.setPen(QPen(QColor(255, 255, 255, 250), 1.6))
        painter.setBrush(hue_col)
        painter.drawRoundedRect(thumb_rect, 4.5, 4.5)

        painter.end()


class ColorCompareSwatch(QWidget):
    """
    Split comparison pill showing [ Initial | New ] color swatches.
    Clicking the initial half restores it.
    """

    restore_requested = pyqtSignal()

    def __init__(
        self,
        initial_color: str,
        current_color: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(72, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._initial = normalize_hex_color(initial_color)
        self._current = normalize_hex_color(current_color)
        self._hover_left = False

    def set_current(self, hex_code: str) -> None:
        self._current = normalize_hex_color(hex_code, self._current)
        self.update()

    def set_initial(self, hex_code: str) -> None:
        self._initial = normalize_hex_color(hex_code, self._initial)
        self.update()

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None and a0.button() == Qt.MouseButton.LeftButton:
            if a0.position().x() < (self.width() / 2.0):
                self.restore_requested.emit()
        super().mousePressEvent(a0)

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None:
            left = a0.position().x() < (self.width() / 2.0)
            if left != self._hover_left:
                self._hover_left = left
                self.update()
        super().mouseMoveEvent(a0)

    def leaveEvent(self, a0: QEvent | None) -> None:
        self._hover_left = False
        self.update()
        super().leaveEvent(a0)

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        radius = 8.0

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.setClipPath(path)

        mid_x = w / 2.0
        rect_left = QRectF(0.0, 0.0, mid_x, h)
        rect_right = QRectF(mid_x, 0.0, w - mid_x, h)

        # Left: Initial color
        painter.fillRect(rect_left, QColor(self._initial))
        if self._hover_left:
            painter.fillRect(rect_left, QColor(255, 255, 255, 45))

        # Right: Current color
        painter.fillRect(rect_right, QColor(self._current))

        # Vertical divider line
        painter.setPen(QPen(QColor(0, 0, 0, 80), 1.2))
        painter.drawLine(QPointF(mid_x, 0.0), QPointF(mid_x, h))

        # Outer glass border
        painter.setPen(QPen(QColor(255, 255, 255, 45), 1.1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

        painter.end()


class _ColorSwatchCell(QPushButton):
    """
    Compact Cyber-Moe swatch cell with hover glow and selection checkmark.
    Supports right-click signal for removable saved slots.
    """

    right_clicked = pyqtSignal()

    def __init__(
        self,
        color_hex: str | None = None,
        is_active: bool = False,
        is_empty_slot: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color = normalize_hex_color(color_hex) if color_hex else None
        self._active = is_active
        self._empty = is_empty_slot
        self._hover = False

    def color(self) -> str | None:
        return self._color

    def set_color_value(self, color_hex: str | None, is_active: bool = False) -> None:
        self._color = normalize_hex_color(color_hex) if color_hex else None
        self._empty = self._color is None
        self._active = is_active
        self.update()

    def set_active(self, active: bool) -> None:
        if self._active != active:
            self._active = active
            self.update()

    def enterEvent(self, event: QEnterEvent | None) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, a0: QEvent | None) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(a0)

    def mousePressEvent(self, e: QMouseEvent | None) -> None:
        if e is not None and e.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
            return
        super().mousePressEvent(e)

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        radius = 6.0

        if self._empty or not self._color:
            # Empty glass slot
            bg = QColor(255, 255, 255, 20 if self._hover else 8)
            border = QColor(255, 255, 255, 55 if self._hover else 26)
            painter.setBrush(bg)
            painter.setPen(
                QPen(
                    border, 1.0, Qt.PenStyle.DashLine if not self._hover else Qt.PenStyle.SolidLine
                )
            )
            painter.drawRoundedRect(rect, radius, radius)

            # Plus hint on hover
            if self._hover:
                painter.setPen(QPen(QColor(255, 255, 255, 180), 1.4))
                cx, cy = w / 2.0, h / 2.0
                painter.drawLine(QPointF(cx - 3.5, cy), QPointF(cx + 3.5, cy))
                painter.drawLine(QPointF(cx, cy - 3.5), QPointF(cx, cy + 3.5))
            painter.end()
            return

        col = QColor(self._color)

        # Hover outer glow
        if self._hover:
            halo = QColor(col)
            halo.setAlpha(70)
            painter.setPen(QPen(halo, 3.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)

        # Color fill
        painter.setBrush(col)
        border_col = QColor(255, 255, 255, 160 if self._active else 45)
        border_width = 1.6 if self._active else 1.0
        painter.setPen(QPen(border_col, border_width))
        painter.drawRoundedRect(rect, radius, radius)

        # Selection checkmark
        if self._active:
            cx, cy = w / 2.0, h / 2.0
            on_accent = derive_accent_tokens(self._color)["on_accent"]
            painter.setPen(
                QPen(
                    QColor(on_accent),
                    1.6,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            path = QPainterPath()
            path.moveTo(cx - 3.5, cy + 0.2)
            path.lineTo(cx - 1.0, cy + 2.8)
            path.lineTo(cx + 3.5, cy - 2.5)
            painter.drawPath(path)

        painter.end()


class _EyedropperLoupe(QWidget):
    """
    Magnified pixel loupe for sampling exact desktop screen colors.
    """

    color_picked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(116, 136)
        self.setMouseTracking(True)
        self._screens_data: list[tuple[QRect, QImage]] = []
        self._current_color: QColor = QColor("#ec186c")
        self._grid_image: QImage | None = None
        self._active: bool = False

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(16)
        self._poll_timer.timeout.connect(self._track_cursor)

    def start_grab(self) -> bool:
        self._screens_data.clear()
        screens = QGuiApplication.screens()
        for sc in screens:
            try:
                geom = sc.geometry()
                pm = sc.grabWindow(cast(Any, 0))
                if not pm.isNull():
                    img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
                    self._screens_data.append((geom, img))
            except Exception:
                continue

        if not self._screens_data:
            return False

        self._active = True
        self.show()
        self._track_cursor()
        self._poll_timer.start()
        try:
            self.grabMouse(Qt.CursorShape.CrossCursor)
            self.grabKeyboard()
        except Exception:
            pass
        return True

    def _track_cursor(self) -> None:
        pos = QCursor.pos()
        target_x = pos.x() + 18
        target_y = pos.y() + 18

        # Clamp inside current screen
        scr = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if scr:
            s_geom = scr.geometry()
            if target_x + self.width() > s_geom.right():
                target_x = pos.x() - self.width() - 14
            if target_y + self.height() > s_geom.bottom():
                target_y = pos.y() - self.height() - 14

        self.move(target_x, target_y)

        # Sample pixel
        for geom, img in self._screens_data:
            if geom.contains(pos):
                rx = (pos.x() - geom.x()) / max(1.0, float(geom.width()))
                ry = (pos.y() - geom.y()) / max(1.0, float(geom.height()))
                px = min(img.width() - 1, max(0, int(rx * img.width())))
                py = min(img.height() - 1, max(0, int(ry * img.height())))
                self._current_color = img.pixelColor(px, py)

                # Extract 9x9 pixel patch for loupe
                patch = img.copy(px - 4, py - 4, 9, 9)
                self._grid_image = patch
                self.update()
                break

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None:
            if a0.button() == Qt.MouseButton.LeftButton:
                hex_col = self._current_color.name().lower()
                self._finish(hex_col)
                return
            if a0.button() == Qt.MouseButton.RightButton:
                self._finish(None)
                return
        super().mousePressEvent(a0)

    def keyPressEvent(self, a0: QKeyEvent | None) -> None:
        if a0 is not None and a0.key() == Qt.Key.Key_Escape:
            self._finish(None)
            return
        super().keyPressEvent(a0)

    def _finish(self, chosen_color: str | None) -> None:
        self._poll_timer.stop()
        try:
            self.releaseMouse()
            self.releaseKeyboard()
        except Exception:
            pass
        self._active = False
        self.close()
        if chosen_color:
            self.color_picked.emit(chosen_color)

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)

        # Translucent glass backing
        painter.setBrush(QColor(18, 22, 34, 235))
        painter.setPen(QPen(QColor(255, 255, 255, 48), 1.2))
        painter.drawRoundedRect(rect, 12.0, 12.0)

        # 1. Magnified 9x9 pixel grid (81x81 px area)
        grid_rect = QRectF(17.5, 12.0, 81.0, 81.0)
        painter.setClipRect(grid_rect)

        if self._grid_image and not self._grid_image.isNull():
            scaled = self._grid_image.scaled(
                81,
                81,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            painter.drawImage(grid_rect.topLeft(), scaled)

        # Grid cell lines
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1.0))
        for i in range(1, 9):
            x = 17.5 + i * 9.0
            painter.drawLine(QPointF(x, 12.0), QPointF(x, 93.0))
            y = 12.0 + i * 9.0
            painter.drawLine(QPointF(17.5, y), QPointF(98.5, y))

        # Center targeted pixel frame (cell 4, 4)
        center_cell = QRectF(17.5 + 4 * 9.0, 12.0 + 4 * 9.0, 9.0, 9.0)
        painter.setPen(QPen(QColor(255, 255, 255, 240), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(center_cell)

        # Pop clip
        painter.setClipping(False)

        # Frame around grid
        painter.setPen(QPen(QColor(255, 255, 255, 70), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(grid_rect.adjusted(-0.5, -0.5, 0.5, 0.5), 4.0, 4.0)

        # 2. Color swatch dot + Hex label
        swatch_rect = QRectF(16.0, 102.0, 16.0, 16.0)
        painter.setBrush(self._current_color)
        painter.setPen(QPen(QColor(255, 255, 255, 120), 1.0))
        painter.drawRoundedRect(swatch_rect, 4.0, 4.0)

        font = QFont("Consolas")
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            QRectF(38.0, 101.0, w - 46.0, 18.0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._current_color.name().upper(),
        )

        painter.end()


class AccentColorPickerDialog(QDialog):
    """
    Bespoke Cyber-Moe modal color picker dialog with 2D SV canvas,
    smooth Hue slider, un-truncated spinboxes, and live preset/saved swatches.
    """

    def __init__(
        self,
        initial_color: str = DEFAULT_ACCENT_COLOR,
        parent: QWidget | None = None,
        title: str | None = None,
        i18n: I18n | None = None,
        icon: QIcon | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("accentColorPickerDialogRoot")
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(440)

        self.i18n = i18n or (getattr(parent, "i18n", None) if parent else None) or I18n("it")
        self._initial_hex = normalize_hex_color(initial_color)
        self._current_hex = self._initial_hex

        # Internal HSV state (0.0 .. 1.0)
        col = QColor(self._initial_hex)
        h, s, v = _extract_hsv_f(col)
        self._h = max(0.0, h if h >= 0.0 else 336.0 / 360.0)
        self._s = s
        self._v = v

        self._syncing_inputs: bool = False
        self._anim_group: QParallelAnimationGroup | None = None
        self._entrance_animated: bool = False
        self._is_closing: bool = False
        self._saved_swatch_buttons: list[_ColorSwatchCell] = []
        self._quick_swatch_buttons: list[_ColorSwatchCell] = []

        title_text = title or self.i18n.t("settings_custom_accent_dialog_title")
        self.setWindowTitle(title_text)

        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        # 1. Custom Title Bar
        app_icon = icon or (getattr(parent, "_icon_app", None) if parent else None)
        self._title_bar = CustomTitleBar(self, icon=app_icon, title=title_text)
        self._title_bar._btn_min.setVisible(False)
        self._title_bar._btn_max.setVisible(False)
        try:
            self._title_bar._btn_close.clicked.disconnect()
        except Exception:
            pass
        self._title_bar._btn_close.clicked.connect(self._on_cancel)
        outer_lay.addWidget(self._title_bar)

        # 2. Main Body Container
        body = QWidget(self)
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(16, 14, 16, 14)
        body_lay.setSpacing(12)

        # Row A: SV Color Canvas + Vertical Hue Slider
        canvas_row = QHBoxLayout()
        canvas_row.setContentsMargins(0, 0, 0, 0)
        canvas_row.setSpacing(10)

        self.sv_canvas = SVColorCanvas(body)
        self.sv_canvas.setFixedHeight(184)
        self.sv_canvas.set_hsv(self._h, self._s, self._v)
        self.sv_canvas.color_changed.connect(self._on_sv_changed)
        canvas_row.addWidget(self.sv_canvas, 1)

        self.hue_slider = HueSpectrumSlider(body)
        self.hue_slider.setFixedHeight(184)
        self.hue_slider.set_hue(self._h)
        self.hue_slider.hue_changed.connect(self._on_hue_slider_changed)
        canvas_row.addWidget(self.hue_slider, 0)
        body_lay.addLayout(canvas_row)

        # Row B: Controls Glass Card (HEX + Eyedropper + RGB/HSV Numeric Grid)
        card_controls = QFrame(body)
        card_controls.setObjectName("pickerControlsCard")
        ctrl_lay = QVBoxLayout(card_controls)
        ctrl_lay.setContentsMargins(12, 10, 12, 10)
        ctrl_lay.setSpacing(9)

        # Top controls subrow: [ Compare Swatch | HEX Input | Copy Button | Eyedropper Button ]
        subrow_top = QHBoxLayout()
        subrow_top.setContentsMargins(0, 0, 0, 0)
        subrow_top.setSpacing(8)

        self.compare_swatch = ColorCompareSwatch(
            self._initial_hex, self._current_hex, card_controls
        )
        self.compare_swatch.setToolTip(
            self.i18n.t("color_picker_restore_initial_tip", hex=self._initial_hex.upper())
        )
        self.compare_swatch.restore_requested.connect(self._restore_initial)
        subrow_top.addWidget(self.compare_swatch)

        lbl_hex = QLabel("HEX")
        lbl_hex.setStyleSheet(
            "color: #94a3b8; font-size: 11px; font-weight: 800; padding-left: 2px;"
        )
        subrow_top.addWidget(lbl_hex)

        self.txt_hex = QLineEdit(self._current_hex.upper(), card_controls)
        self.txt_hex.setFixedSize(94, 30)
        self.txt_hex.setMaxLength(7)
        self.txt_hex.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_hex.setStyleSheet(
            "QLineEdit { font-family: 'Consolas', monospace; font-size: 13px; font-weight: 700; "
            "background-color: rgba(255, 255, 255, 0.08); "
            "border: 1px solid rgba(255, 255, 255, 0.18); "
            "border-radius: 8px; color: #ffffff; padding: 2px 4px; } "
            "QLineEdit:focus { border: 1px solid #ff4294; "
            "background-color: rgba(255, 255, 255, 0.12); }"
        )
        self.txt_hex.textEdited.connect(self._on_hex_text_edited)
        self.txt_hex.editingFinished.connect(self._on_hex_editing_finished)
        subrow_top.addWidget(self.txt_hex)

        self.btn_copy_hex = QPushButton(card_controls)
        self.btn_copy_hex.setFixedSize(30, 30)
        self.btn_copy_hex.setIcon(get_copy_icon(15, "#cbd5e1"))
        self.btn_copy_hex.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_hex.setToolTip(self.i18n.t("color_picker_copy_tip"))
        self.btn_copy_hex.clicked.connect(self._on_copy_hex)
        subrow_top.addWidget(self.btn_copy_hex)

        subrow_top.addStretch(1)

        self.btn_eyedropper = QPushButton(card_controls)
        self.btn_eyedropper.setObjectName("secondaryGlassBtn")
        self.btn_eyedropper.setFixedHeight(30)
        self.btn_eyedropper.setIcon(get_eyedropper_icon(15, "#e2e8f0"))
        self.btn_eyedropper.setText(self.i18n.t("color_picker_eyedropper"))
        self.btn_eyedropper.setToolTip(self.i18n.t("color_picker_eyedropper_tip"))
        self.btn_eyedropper.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_eyedropper.clicked.connect(self._on_open_eyedropper)
        subrow_top.addWidget(self.btn_eyedropper)
        ctrl_lay.addLayout(subrow_top)

        # Bottom controls grid: Non-truncated RGB & HSV spinboxes (3x2 grid)
        grid_num = QGridLayout()
        grid_num.setContentsMargins(0, 0, 0, 0)
        grid_num.setHorizontalSpacing(10)
        grid_num.setVerticalSpacing(6)

        self.spin_r = self._make_spinbox(0, 255, col.red(), self._on_rgb_changed)
        self.spin_g = self._make_spinbox(0, 255, col.green(), self._on_rgb_changed)
        self.spin_b = self._make_spinbox(0, 255, col.blue(), self._on_rgb_changed)

        self.spin_h = self._make_spinbox(
            0, 359, int(round(self._h * 359)), self._on_hsv_spin_changed, suffix="°"
        )
        self.spin_s = self._make_spinbox(
            0, 100, int(round(self._s * 100)), self._on_hsv_spin_changed, suffix="%"
        )
        self.spin_v = self._make_spinbox(
            0, 100, int(round(self._v * 100)), self._on_hsv_spin_changed, suffix="%"
        )

        self._add_grid_cell(grid_num, 0, 0, "R", self.spin_r, self.i18n.t("color_picker_red"))
        self._add_grid_cell(grid_num, 0, 1, "G", self.spin_g, self.i18n.t("color_picker_green"))
        self._add_grid_cell(grid_num, 0, 2, "B", self.spin_b, self.i18n.t("color_picker_blue"))

        self._add_grid_cell(grid_num, 1, 0, "H", self.spin_h, self.i18n.t("color_picker_hue"))
        self._add_grid_cell(grid_num, 1, 1, "S", self.spin_s, self.i18n.t("color_picker_sat"))
        self._add_grid_cell(grid_num, 1, 2, "V", self.spin_v, self.i18n.t("color_picker_val"))

        ctrl_lay.addLayout(grid_num)
        body_lay.addWidget(card_controls)

        # Row C: Quick Curated Palette (16 colors in 2x8 grid)
        lbl_quick = QLabel(self.i18n.t("color_picker_presets"), body)
        lbl_quick.setStyleSheet(
            "color: #94a3b8; font-size: 10px; font-weight: 800; "
            "letter-spacing: 0.9px; background: transparent;"
        )
        body_lay.addWidget(lbl_quick)

        grid_quick = QGridLayout()
        grid_quick.setContentsMargins(0, 0, 0, 0)
        grid_quick.setHorizontalSpacing(6)
        grid_quick.setVerticalSpacing(6)

        for idx, q_hex in enumerate(QUICK_PALETTE_COLORS):
            row = idx // 8
            col_idx = idx % 8
            cell = _ColorSwatchCell(
                color_hex=q_hex, is_active=(q_hex == self._current_hex), parent=body
            )
            cell.setToolTip(q_hex.upper())
            cell.clicked.connect(lambda _c=False, hx=q_hex: self._select_swatch(hx))
            grid_quick.addWidget(cell, row, col_idx)
            self._quick_swatch_buttons.append(cell)
        body_lay.addLayout(grid_quick)

        # Row D: Saved Custom Colors (8 slots persisted in QSettings)
        hdr_saved_row = QHBoxLayout()
        hdr_saved_row.setContentsMargins(0, 0, 0, 0)
        hdr_saved_row.setSpacing(8)

        lbl_saved = QLabel(self.i18n.t("color_picker_saved"), body)
        lbl_saved.setStyleSheet(
            "color: #94a3b8; font-size: 10px; font-weight: 800; "
            "letter-spacing: 0.9px; background: transparent;"
        )
        hdr_saved_row.addWidget(lbl_saved)
        hdr_saved_row.addStretch(1)

        self.btn_save_slot = QPushButton(self.i18n.t("color_picker_save_btn"), body)
        self.btn_save_slot.setObjectName("secondaryGlassBtn")
        self.btn_save_slot.setFixedHeight(22)
        self.btn_save_slot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_slot.setToolTip(self.i18n.t("color_picker_save_tip"))
        self.btn_save_slot.clicked.connect(self._save_current_to_custom_palette)
        hdr_saved_row.addWidget(self.btn_save_slot)
        body_lay.addLayout(hdr_saved_row)

        row_saved = QHBoxLayout()
        row_saved.setContentsMargins(0, 0, 0, 0)
        row_saved.setSpacing(6)

        self._load_saved_palette_slots(row_saved, body)
        body_lay.addLayout(row_saved)

        outer_lay.addWidget(body, 1)

        # 3. Action Footer Bar
        footer = QFrame(self)
        footer.setObjectName("dialogFooter")
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(18, 9, 18, 11)
        footer_lay.setSpacing(10)

        footer_lay.addStretch(1)

        self.btn_cancel = QPushButton(self.i18n.t("settings_cancel"), footer)
        self.btn_cancel.setObjectName("cancelButton")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setMinimumWidth(84)
        self.btn_cancel.clicked.connect(self._on_cancel)
        footer_lay.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton(self.i18n.t("settings_ok"), footer)
        self.btn_ok.setObjectName("primaryButton")
        self.btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ok.setMinimumWidth(92)
        self.btn_ok.clicked.connect(self._on_ok)
        footer_lay.addWidget(self.btn_ok)

        outer_lay.addWidget(footer)

        self._apply_dialog_styles()
        self._update_ok_button_style()

        final_h = max(520, self.sizeHint().height())
        self.setFixedSize(440, final_h)

        try:
            apply_windows_titlebar_dark_mode(self, True)
        except Exception:
            pass

    def _make_spinbox(
        self,
        min_v: int,
        max_v: int,
        val: int,
        slot_fn: Callable[[], None],
        suffix: str = "",
    ) -> QSpinBox:
        sb = QSpinBox()
        sb.setRange(min_v, max_v)
        sb.setValue(val)
        sb.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        sb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb.setFixedHeight(28)
        if suffix:
            sb.setSuffix(suffix)
        sb.setStyleSheet(
            "QSpinBox { font-family: 'Consolas', monospace; font-size: 12px; font-weight: 700; "
            "background-color: rgba(255, 255, 255, 0.06); "
            "border: 1px solid rgba(255, 255, 255, 0.14); "
            "border-radius: 7px; color: #ffffff; padding: 2px 4px; min-width: 60px; } "
            "QSpinBox:focus { border: 1px solid #ff4294; "
            "background-color: rgba(255, 255, 255, 0.11); }"
        )
        sb.valueChanged.connect(slot_fn)
        return sb

    @staticmethod
    def _add_grid_cell(
        layout: QGridLayout,
        row: int,
        col: int,
        label_text: str,
        widget: QWidget,
        tooltip: str = "",
    ) -> None:
        cell_lay = QHBoxLayout()
        cell_lay.setContentsMargins(0, 0, 0, 0)
        cell_lay.setSpacing(6)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(14)
        lbl.setStyleSheet(
            "color: #94a3b8; font-size: 11px; font-weight: 800; background: transparent;"
        )
        if tooltip:
            lbl.setToolTip(tooltip)
            widget.setToolTip(tooltip)
        cell_lay.addWidget(lbl)
        cell_lay.addWidget(widget, 1)
        layout.addLayout(cell_lay, row, col)

    def _apply_dialog_styles(self) -> None:
        accent = PALETTE.get("accent", "#EC186C")
        PALETTE.get("bg_dialog", "#121523")
        bg_surface = PALETTE.get("bg_surface", "#171a29")
        bg_footer = PALETTE.get("bg_footer", "#10131f")
        base_qss = get_cyber_moe_stylesheet(accent)

        extra_qss = f"""
        QDialog#accentColorPickerDialogRoot {{
            background: transparent;
            border: none;
        }}
        QFrame#pickerControlsCard {{
            background-color: {bg_surface};
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-top: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 11px;
        }}
        QFrame#dialogFooter {{
            background-color: {bg_footer};
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            border-bottom-left-radius: 12px;
            border-bottom-right-radius: 12px;
        }}
        QPushButton#cancelButton {{
            background-color: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.12);
            color: #94a3b8;
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#cancelButton:hover {{
            background-color: rgba(255, 255, 255, 0.10);
            border-color: rgba(255, 255, 255, 0.25);
            color: #ffffff;
        }}
        QPushButton#cancelButton:pressed {{
            background-color: rgba(255, 255, 255, 0.03);
        }}
        """
        self.setStyleSheet(base_qss + "\n" + extra_qss)

    def _update_ok_button_style(self) -> None:
        tokens = derive_accent_tokens(self._current_hex)
        act = tokens["accent"]
        hover = tokens["accent_hover"]
        pressed = tokens["accent_pressed"]
        on_accent = tokens["on_accent"]
        self.btn_ok.setStyleSheet(
            f"QPushButton#primaryButton {{ background-color: {act}; color: {on_accent}; "
            "border: none; border-radius: 8px; padding: 6px 18px; "
            "font-size: 12px; font-weight: 700; } "
            f"QPushButton#primaryButton:hover {{ background-color: {hover}; }} "
            f"QPushButton#primaryButton:pressed {{ background-color: {pressed}; }}"
        )

    def _on_sv_changed(self, sat: float, val: float) -> None:
        if self._syncing_inputs:
            return
        self._s = sat
        self._v = val
        col = QColor.fromHsvF(self._h, self._s, self._v)
        self._current_hex = col.name().lower()
        self._sync_all_inputs(origin="sv")

    def _on_hue_slider_changed(self, hue: float) -> None:
        if self._syncing_inputs:
            return
        self._h = hue
        self.sv_canvas.set_hue(hue)
        col = QColor.fromHsvF(self._h, self._s, self._v)
        self._current_hex = col.name().lower()
        self._sync_all_inputs(origin="hue")

    def _on_rgb_changed(self) -> None:
        if self._syncing_inputs:
            return
        r = self.spin_r.value()
        g = self.spin_g.value()
        b = self.spin_b.value()
        col = QColor(r, g, b)
        self._current_hex = col.name().lower()
        h, s, v = _extract_hsv_f(col)
        if h >= 0.0:
            self._h = h
        if v > 0.0:
            self._s = s
        self._v = v
        self._sync_all_inputs(origin="rgb")

    def _on_hsv_spin_changed(self) -> None:
        if self._syncing_inputs:
            return
        self._h = self.spin_h.value() / 359.0
        self._s = self.spin_s.value() / 100.0
        self._v = self.spin_v.value() / 100.0
        col = QColor.fromHsvF(self._h, self._s, self._v)
        self._current_hex = col.name().lower()
        self._sync_all_inputs(origin="hsv_spin")

    def _on_hex_text_edited(self, text: str) -> None:
        clean = text.strip()
        if not clean.startswith("#"):
            clean = "#" + clean
        if is_valid_hex_color(clean) and len(clean) == 7:
            self._current_hex = normalize_hex_color(clean)
            col = QColor(self._current_hex)
            h, s, v = _extract_hsv_f(col)
            if h >= 0.0:
                self._h = h
            if v > 0.0:
                self._s = s
            self._v = v
            self._sync_all_inputs(origin="hex_typed")

    def _on_hex_editing_finished(self) -> None:
        clean = self.txt_hex.text().strip()
        if not clean.startswith("#"):
            clean = "#" + clean
        norm = normalize_hex_color(clean, self._current_hex)
        self.txt_hex.setText(norm.upper())

    def _select_swatch(self, color_hex: str) -> None:
        norm = normalize_hex_color(color_hex)
        self._current_hex = norm
        col = QColor(norm)
        h, s, v = _extract_hsv_f(col)
        if h >= 0.0:
            self._h = h
        if v > 0.0:
            self._s = s
        self._v = v
        self._sync_all_inputs(origin="swatch")

    def _restore_initial(self) -> None:
        self._select_swatch(self._initial_hex)

    def _sync_all_inputs(self, origin: str) -> None:
        self._syncing_inputs = True
        try:
            col = QColor(self._current_hex)

            if origin != "sv":
                self.sv_canvas.set_hsv(self._h, self._s, self._v)
            if origin != "hue":
                self.hue_slider.set_hue(self._h)
            if origin != "hex_typed":
                self.txt_hex.setText(self._current_hex.upper())

            if origin not in ("rgb",):
                self.spin_r.setValue(col.red())
                self.spin_g.setValue(col.green())
                self.spin_b.setValue(col.blue())

            if origin not in ("hsv_spin",):
                self.spin_h.setValue(int(round(self._h * 359)))
                self.spin_s.setValue(int(round(self._s * 100)))
                self.spin_v.setValue(int(round(self._v * 100)))

            self.compare_swatch.set_current(self._current_hex)
            self._update_ok_button_style()

            # Refresh swatch checkmarks
            for cell in self._quick_swatch_buttons:
                cell.set_active(cell.color() == self._current_hex)
            for cell in self._saved_swatch_buttons:
                cell.set_active(cell.color() == self._current_hex)
        finally:
            self._syncing_inputs = False

    def _on_copy_hex(self) -> None:
        app = QApplication.instance()
        if isinstance(app, QApplication):
            clipboard = app.clipboard()
            if clipboard:
                clipboard.setText(self._current_hex.upper())
        self.btn_copy_hex.setIcon(get_check_icon(15, "#00e676"))
        self.btn_copy_hex.setToolTip(self.i18n.t("copied_feedback"))
        QTimer.singleShot(900, lambda: self.btn_copy_hex.setIcon(get_copy_icon(15, "#cbd5e1")))

    def _on_open_eyedropper(self) -> None:
        loupe = _EyedropperLoupe(self)
        loupe.color_picked.connect(self._select_swatch)
        self.hide()

        def _on_loupe_closed() -> None:
            self.show()
            self.raise_()
            self.activateWindow()

        loupe.destroyed.connect(_on_loupe_closed)
        if not loupe.start_grab():
            self.show()

    def _load_saved_palette_slots(self, layout: QHBoxLayout, parent: QWidget) -> None:
        settings = QSettings(ORG_NAME, APP_SETTINGS)
        raw_saved = settings.value(KEY_CUSTOM_ACCENT_PALETTE, "")
        saved_list: list[str] = [
            c.strip().lower() for c in str(raw_saved).split(",") if is_valid_hex_color(c.strip())
        ]
        saved_list = saved_list[:8]

        self._saved_swatch_buttons.clear()
        for idx in range(8):
            slot_hex = saved_list[idx] if idx < len(saved_list) else None
            cell = _ColorSwatchCell(
                color_hex=slot_hex,
                is_active=(slot_hex == self._current_hex),
                is_empty_slot=(slot_hex is None),
                parent=parent,
            )
            if slot_hex:
                cell.setToolTip(self.i18n.t("color_picker_saved_slot_tip", hex=slot_hex.upper()))
            else:
                cell.setToolTip(self.i18n.t("color_picker_empty_slot_tip"))

            def _handle_slot_click(_chk: bool = False, slot_idx: int = idx) -> None:
                curr_slot = self._saved_swatch_buttons[slot_idx]
                if curr_slot.color():
                    self._select_swatch(curr_slot.color() or "")
                else:
                    self._save_color_to_slot(slot_idx, self._current_hex)

            def _handle_slot_right_click(slot_idx: int = idx) -> None:
                self._remove_saved_color_slot(slot_idx)

            cell.clicked.connect(_handle_slot_click)
            cell.right_clicked.connect(_handle_slot_right_click)
            layout.addWidget(cell)
            self._saved_swatch_buttons.append(cell)

    def _save_color_to_slot(self, slot_idx: int, hex_col: str) -> None:
        if 0 <= slot_idx < len(self._saved_swatch_buttons):
            norm = normalize_hex_color(hex_col)
            cell = self._saved_swatch_buttons[slot_idx]
            cell.set_color_value(norm, is_active=(norm == self._current_hex))
            cell.setToolTip(self.i18n.t("color_picker_saved_slot_tip", hex=norm.upper()))
            self._persist_saved_palette()

    def _save_current_to_custom_palette(self) -> None:
        norm = self._current_hex
        # Check if already present
        for idx, cell in enumerate(self._saved_swatch_buttons):
            if cell.color() == norm:
                cell.set_active(True)
                return

        # Find first empty slot
        for idx, cell in enumerate(self._saved_swatch_buttons):
            if cell.color() is None:
                self._save_color_to_slot(idx, norm)
                return

        # If all full, overwrite first slot FIFO
        self._save_color_to_slot(0, norm)

    def _remove_saved_color_slot(self, slot_idx: int) -> None:
        if 0 <= slot_idx < len(self._saved_swatch_buttons):
            cell = self._saved_swatch_buttons[slot_idx]
            cell.set_color_value(None, is_active=False)
            cell.setToolTip(self.i18n.t("color_picker_empty_slot_tip"))
            self._persist_saved_palette()

    def _persist_saved_palette(self) -> None:
        colors = [col for c in self._saved_swatch_buttons if (col := c.color()) is not None]
        settings = QSettings(ORG_NAME, APP_SETTINGS)
        settings.setValue(KEY_CUSTOM_ACCENT_PALETTE, ",".join(colors))

    def selected_color(self) -> str:
        return self._current_hex

    def _on_ok(self) -> None:
        self._animate_exit(super().accept)

    def _on_cancel(self) -> None:
        self._animate_exit(super().reject)

    def showEvent(self, a0: QShowEvent | None) -> None:
        super().showEvent(a0)
        self._animate_entrance()

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        painter.setBrush(QColor(PALETTE.get("bg_dialog", "#121523")))
        painter.setPen(QPen(QColor(255, 255, 255, 42), 1.0))
        painter.drawRoundedRect(rect, 12.0, 12.0)
        painter.end()

    def _animate_entrance(self) -> None:
        if self._entrance_animated:
            return
        self._entrance_animated = True

        target_pos = self.pos()
        start_pos = QPoint(target_pos.x(), target_pos.y() - 10)

        if self._anim_group and self._anim_group.state() == QParallelAnimationGroup.State.Running:
            self._anim_group.stop()

        self.setWindowOpacity(0.0)
        self.move(start_pos)

        group = QParallelAnimationGroup(self)

        anim_pos = QPropertyAnimation(self, b"pos", group)
        anim_pos.setDuration(190)
        anim_pos.setStartValue(start_pos)
        anim_pos.setEndValue(target_pos)
        anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

        anim_op = QPropertyAnimation(self, b"windowOpacity", group)
        anim_op.setDuration(180)
        anim_op.setStartValue(0.0)
        anim_op.setEndValue(1.0)
        anim_op.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _on_entrance_finished() -> None:
            self.setWindowOpacity(1.0)
            self.move(target_pos)

        group.finished.connect(_on_entrance_finished)
        self._anim_group = group
        group.start()

    def _animate_exit(self, callback: Callable[[], None]) -> None:
        if self._is_closing:
            return
        self._is_closing = True

        if not self.isVisible():
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
            callback()

        group.finished.connect(_finish)
        self._anim_group = group
        group.start()

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        if self._is_closing:
            if a0:
                a0.accept()
            return
        if not self.isVisible():
            if a0:
                a0.accept()
            return
        if a0:
            a0.ignore()
        self._on_cancel()

    def keyPressEvent(self, a0: QKeyEvent | None) -> None:
        if a0 is not None:
            if a0.key() == Qt.Key.Key_Escape:
                self._on_cancel()
                return
            if a0.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not self.txt_hex.hasFocus():
                    self._on_ok()
                    return
        super().keyPressEvent(a0)

    @classmethod
    def get_color(
        cls,
        initial_color: str = DEFAULT_ACCENT_COLOR,
        parent: QWidget | None = None,
        title: str | None = None,
        i18n: I18n | None = None,
        icon: QIcon | None = None,
    ) -> str | None:
        dlg = cls(initial_color=initial_color, parent=parent, title=title, i18n=i18n, icon=icon)
        res = dlg.exec()
        if res == QDialog.DialogCode.Accepted:
            return dlg.selected_color()
        return None
