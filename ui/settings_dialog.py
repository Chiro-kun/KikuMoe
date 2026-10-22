"""
SettingsDialog / Integrated Settings Panel for KikuMoe 2.0.0
Features:
- 60 FPS SlidingStackedWidget using direct widget geometry translation (zero flash)
- Custom vector BackToPlayerButton ('< Player') with click bounce animation
- SettingsCategoryBar with 60 FPS horizontal sliding pill (matching J-POP | K-POP switch)
- Custom-painted GlassComboBox with 13px DemiBold text and styled popup list
- Preserved _host_window reference so Developer Console opens reliably when embedded
"""

import os
import sys
from typing import List, Optional

from PyQt6.QtCore import (
    QElapsedTimer,
    QPoint,
    QPointF,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
)
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from core.constants import (
    APP_SETTINGS,
    KEY_AUDIO_BACKEND,
    KEY_AUDIO_DEVICE_INDEX,
    KEY_AUTOPLAY,
    KEY_CHANNEL,
    KEY_DEV_CONSOLE_ENABLED,
    KEY_DEV_CONSOLE_SHOW_DEV,
    KEY_FORMAT,
    KEY_LANG,
    KEY_LIBVLC_PATH,
    KEY_NETWORK_CACHING,
    KEY_SESSION_TIMER_ENABLED,
    KEY_SLEEP_STOP_ON_END,
    KEY_TRAY_ENABLED,
    KEY_TRAY_HIDE_ON_MINIMIZE,
    KEY_TRAY_NOTIFICATIONS,
    ORG_NAME,
)
from core.i18n import I18n
from core.logger import silence_stderr
from ui.about_dialog import AboutWidget
from ui.custom_titlebar import CustomTitleBar, install_size_grip
from ui.themes.cyber_moe import PALETTE, get_cyber_moe_stylesheet
from ui.windows_titlebar import apply_windows_titlebar_dark_mode

_IS_WIN32 = sys.platform == "win32"


class SlidingStackedWidget(QStackedWidget):
    """
    QStackedWidget with 60 FPS time-based slide + crossfade transitions using
    pre-rendered HiDPI QPixmap snapshots.
    - Eliminates transparent tab overlap (outgoing and incoming snapshots slide
      side-by-side without overlapping, while smoothly fading opacity).
    - Hides live child widgets during the 190ms transition so QStackedLayout
      never fights widget positions or flashes an unstyled UI skeleton.
    """

    DURATION_MS = 190.0

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(14)
        self._anim_timer.timeout.connect(self._tick_slide)
        self._elapsed = QElapsedTimer()
        self._progress: float = 1.0
        self._pm_from: Optional[QPixmap] = None
        self._pm_to: Optional[QPixmap] = None
        self._w_from: Optional[QWidget] = None
        self._w_to: Optional[QWidget] = None
        self._target_index: int = 0
        self._direction: int = 1

    @staticmethod
    def _activate_layouts(widget: QWidget) -> None:
        lay = widget.layout()
        if lay is not None:
            lay.activate()
        for child in widget.findChildren(QWidget):
            c_lay = child.layout()
            if c_lay is not None:
                c_lay.activate()

    def _render_snapshot(self, widget: QWidget) -> QPixmap:
        w = max(1, self.width())
        h = max(1, self.height())
        widget.ensurePolished()
        if widget.size() != self.size():
            widget.setGeometry(0, 0, w, h)
        self._activate_layouts(widget)

        dpr = float(self.devicePixelRatioF()) if hasattr(self, "devicePixelRatioF") else 1.0
        dpr = max(1.0, dpr)
        pm = QPixmap(max(1, int(round(w * dpr))), max(1, int(round(h * dpr))))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        widget.render(
            painter,
            QPoint(0, 0),
            QRegion(),
            QWidget.RenderFlag.DrawChildren,
        )
        painter.end()
        return pm

    def finish_active_slide(self) -> None:
        """Immediately complete any running slide transition."""
        if self._anim_timer.isActive() or self._pm_from is not None or self._pm_to is not None:
            self._anim_timer.stop()
            self._pm_from = None
            self._pm_to = None
            self._progress = 1.0
            if self._w_from is not None:
                self._w_from.move(0, 0)
            if self._w_to is not None:
                self._w_to.move(0, 0)
            super().setCurrentIndex(self._target_index)
            cur = self.widget(self._target_index)
            if cur is not None:
                cur.move(0, 0)
                cur.setVisible(True)
            self._w_from = None
            self._w_to = None
            self.update()

    def slide_to_index(self, new_index: int, direction: Optional[int] = None) -> None:
        self.finish_active_slide()
        old_index = self.currentIndex()
        if new_index == old_index or not (0 <= new_index < self.count()):
            return

        if not self.isVisible() or self.width() <= 10 or self.height() <= 10:
            super().setCurrentIndex(new_index)
            return

        if direction is None:
            direction = 1 if new_index > old_index else -1

        w_from = self.widget(old_index)
        w_to = self.widget(new_index)
        if w_from is None or w_to is None:
            super().setCurrentIndex(new_index)
            return

        self._w_from = w_from
        self._w_to = w_to
        self._target_index = new_index
        self._direction = 1 if direction >= 0 else -1
        self._progress = 0.0

        # Capture crisp HiDPI snapshots of both outgoing and incoming pages
        self._pm_from = self._render_snapshot(w_from)
        self._pm_to = self._render_snapshot(w_to)

        # Hide live outgoing widget during transition so only the GPU pixmaps are composited
        w_from.setVisible(False)
        w_to.setVisible(False)

        self._elapsed.start()
        self._anim_timer.start()
        self.update()

    def _tick_slide(self) -> None:
        elapsed = float(self._elapsed.elapsed())
        t = min(1.0, max(0.0, elapsed / self.DURATION_MS))
        self._progress = t
        if t >= 1.0:
            self.finish_active_slide()
        else:
            self.update()

    def paintEvent(self, a0) -> None:
        super().paintEvent(a0)
        if self._pm_from is None or self._pm_to is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = float(self.width())
        t = self._progress
        # Cubic-out easing
        ease = 1.0 - ((1.0 - t) ** 3)
        d = float(self._direction)

        # Non-overlapping side-by-side slide with smooth opacity crossfade
        x_from = -d * w * ease
        x_to = d * w * (1.0 - ease)

        alpha_from = max(0.0, min(1.0, (1.0 - ease) ** 1.35))
        alpha_to = max(0.0, min(1.0, 0.25 + 0.75 * ease))

        if alpha_from > 0.01:
            painter.setOpacity(alpha_from)
            painter.drawPixmap(QPointF(x_from, 0.0), self._pm_from)

        painter.setOpacity(alpha_to)
        painter.drawPixmap(QPointF(x_to, 0.0), self._pm_to)
        painter.end()


class BackToPlayerButton(QPushButton):
    """
    Custom vector '< Player' pill button with anti-aliased chevron icon
    and 60 FPS click bounce animation.
    """

    def __init__(self, text: str = "Player", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self._hover = False
        self._pressed = False
        self._scale = 1.0
        self._anim_step = 0
        self.setFixedSize(88, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)

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
            self._scale = 0.88
            self._anim_timer.start()
            self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(e)

    def _tick_anim(self) -> None:
        scales = [0.88, 0.94, 1.04, 1.01, 1.0]
        if 0 < self._anim_step <= len(scales):
            self._scale = scales[self._anim_step - 1]
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

        painter.translate(cx, cy)
        painter.scale(self._scale, self._scale)
        painter.translate(-cx, -cy)

        if self._hover or self._pressed:
            bg = QColor(236, 24, 108, 48 if self._pressed else 30)
            border = QColor(PALETTE["accent"])
            fg = QColor("#ffffff")
            icon_col = QColor(PALETTE["accent_hover"])
        else:
            bg = QColor(255, 255, 255, 16)
            border = QColor(255, 255, 255, 36)
            fg = QColor("#e2e6f5")
            icon_col = QColor(PALETTE["accent_hover"])

        rect = QRectF(1.0, 1.0, w - 2.0, h - 2.0)
        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.1))
        painter.drawRoundedRect(rect, (h - 2.0) / 2.0, (h - 2.0) / 2.0)

        pen = QPen(icon_col, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        chev = QPainterPath()
        ix = 16.0
        chev.moveTo(QPointF(ix + 2.5, cy - 4.5))
        chev.lineTo(QPointF(ix - 2.5, cy))
        chev.lineTo(QPointF(ix + 2.5, cy + 4.5))
        painter.drawPath(chev)

        font = QFont(self.font())
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(fg)
        painter.drawText(
            QRectF(24.0, 0.0, w - 28.0, h),
            Qt.AlignmentFlag.AlignCenter,
            self.text(),
        )
        painter.end()


class GlassComboDelegate(QStyledItemDelegate):
    """
    Delegate for GlassComboBox popup items ensuring consistent row heights (>= 28px)
    across all platforms and font metrics, eliminating vertical text overlapping.
    """

    def sizeHint(self, option, index) -> QSize:
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), max(sh.height(), 28))


class GlassComboBox(QComboBox):
    """
    Custom-painted QComboBox that renders a dark glass capsule with crisp 12px
    Medium text and a vector chevron indicator, plus a styled QListView popup.
    Prevents sticky focus/selection state when closing the popup or switching tabs.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._hover = False
        self._popup_open = False
        self.setFixedHeight(30)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        list_view = QListView(self)
        list_view.setUniformItemSizes(True)
        list_view.setItemDelegate(GlassComboDelegate(list_view))

        font = QFont()
        font.setFamilies(["Segoe UI", "Inter", "Cantarell", "Ubuntu", "DejaVu Sans", "sans-serif"])
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Medium)
        self.setFont(font)
        list_view.setFont(font)
        list_view.setStyleSheet(
            f"""
            QListView {{
                background-color: #151826;
                border: 1px solid rgba(236, 24, 108, 0.55);
                border-radius: 8px;
                color: #f4f6fd;
                font-size: 12px;
                font-weight: 500;
                selection-background-color: {PALETTE["accent"]};
                selection-color: #ffffff;
                padding: 4px;
                outline: none;
            }}
            QListView::item {{
                min-height: 28px;
                padding: 3px 10px;
                border-radius: 5px;
            }}
            QListView::item:hover, QListView::item:selected {{
                background-color: {PALETTE["accent"]};
                color: #ffffff;
            }}
            """
        )

        self.setView(list_view)

        popup = list_view.window()
        if popup is not None:
            popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            popup.setWindowFlags(
                Qt.WindowType.Popup
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.NoDropShadowWindowHint
            )
            popup.setStyleSheet(
                "QComboBoxPrivateContainer { background-color: transparent; border: none; }"
            )

    def reset_visual_state(self) -> None:
        """Clear any popup/hover/focus state so the dropdown never stays highlighted."""
        if self._popup_open:
            super().hidePopup()
        self._popup_open = False
        self._hover = False
        self.clearFocus()
        self.update()

    def showPopup(self) -> None:
        self._popup_open = True
        self.update()
        view = self.view()
        if view is not None:
            popup = view.window()
            if popup is not None:
                popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                popup.setWindowFlags(
                    Qt.WindowType.Popup
                    | Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.NoDropShadowWindowHint
                )
                popup.setStyleSheet(
                    "QComboBoxPrivateContainer { background-color: transparent; border: none; }"
                )
        super().showPopup()

    def hidePopup(self) -> None:
        self._popup_open = False
        self._hover = False
        self.clearFocus()
        self.update()
        super().hidePopup()

    def enterEvent(self, a0) -> None:
        self._hover = True
        self.update()
        super().enterEvent(a0)

    def leaveEvent(self, a0) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(a0)

    def focusOutEvent(self, e) -> None:
        self._hover = False
        self._popup_open = False
        self.update()
        super().focusOutEvent(e)

    def paintEvent(self, e) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)

        if self._hover and not self._popup_open and not self.underMouse():
            self._hover = False

        if self._hover or self._popup_open:
            bg = QColor(236, 24, 108, 30)
            border = QColor(PALETTE["accent"])
            chev_col = QColor(PALETTE["accent_hover"])
        else:
            bg = QColor(255, 255, 255, 16)
            border = QColor(255, 255, 255, 38)
            chev_col = QColor("#a6adc4")

        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.1))
        painter.drawRoundedRect(rect, 9.0, 9.0)

        # Draw crisp 12px Medium current item text
        font = QFont(self.font())
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(QColor("#f4f6fd"))

        text_rect = QRectF(11.0, 0.0, w - 34.0, h)
        fm = QFontMetrics(font)
        elided = fm.elidedText(
            self.currentText(), Qt.TextElideMode.ElideRight, int(text_rect.width())
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )

        # Draw anti-aliased vector chevron 'v' on the right
        cx = w - 15.0
        cy = h / 2.0 + 0.5
        pen = QPen(chev_col, 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(QPointF(cx - 3.8, cy - 1.8))
        path.lineTo(QPointF(cx, cy + 2.0))
        path.lineTo(QPointF(cx + 3.8, cy - 1.8))
        painter.drawPath(path)
        painter.end()


class AnimatedToggleSwitch(QCheckBox):
    """
    Full-row QCheckBox replacement that renders the label on the left and a
    60 FPS sliding pill toggle switch on the right.
    - Unchecked (Inactive): neutral monochrome dark glass track & gray knob
    - Checked (Active): vibrant magenta track (#ec186c) & white knob
    """

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self._hover = False
        self._progress = 1.0 if self.isChecked() else 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)
        self.toggled.connect(self._on_toggled)

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._progress = 1.0 if checked else 0.0
        self.update()

    def _on_toggled(self, checked: bool) -> None:
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def _tick_anim(self) -> None:
        target = 1.0 if self.isChecked() else 0.0
        diff = target - self._progress
        if abs(diff) < 0.06:
            self._progress = target
            self._anim_timer.stop()
        else:
            self._progress += diff * 0.34
        self.update()

    def enterEvent(self, a0) -> None:
        self._hover = True
        self.update()
        super().enterEvent(a0)

    def leaveEvent(self, a0) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(a0)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        enabled = self.isEnabled()
        p = self._progress

        # 1. Subtle row hover highlight
        if self._hover and enabled:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 10))
            painter.drawRoundedRect(QRectF(0.0, 1.0, w, h - 2.0), 8.0, 8.0)

        # 2. Left Text Label (larger readable font)
        text_col = QColor("#f2f4fc" if (self.isChecked() or self._hover) else "#ced4e6")
        if not enabled:
            text_col.setAlpha(95)
        painter.setPen(text_col)
        font = QFont(self.font())
        font.setPixelSize(12 if w < 350 else 13)
        font.setWeight(QFont.Weight.DemiBold if self.isChecked() else QFont.Weight.Medium)
        painter.setFont(font)

        sw_w = 42.0
        sw_h = 22.0
        sw_x = w - sw_w - 2.0
        sw_y = (h - sw_h) / 2.0

        text_rect = QRectF(4.0, 0.0, sw_x - 10.0, h)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
            self.text(),
        )

        # 3. Right Sliding Pill Switch Track
        track_rect = QRectF(sw_x, sw_y, sw_w, sw_h)
        radius = sw_h / 2.0

        r_bg = int(28 + (236 - 28) * p)
        g_bg = int(32 + (24 - 32) * p)
        b_bg = int(48 + (108 - 48) * p)
        a_bg = int(195 + (255 - 195) * p)
        if not enabled:
            a_bg = int(a_bg * 0.45)

        track_col = QColor(r_bg, g_bg, b_bg, a_bg)
        if p > 0.5:
            border_col = QColor("#ff4797" if self._hover else PALETTE["accent"])
        else:
            border_col = QColor(255, 255, 255, 65 if self._hover else 34)
        if not enabled:
            border_col.setAlpha(30)

        painter.setBrush(track_col)
        painter.setPen(QPen(border_col, 1.1))
        painter.drawRoundedRect(track_rect, radius, radius)

        # 4. Sliding Knob Circle
        knob_d = sw_h - 6.0
        knob_min_x = sw_x + 3.0
        knob_max_x = sw_x + sw_w - knob_d - 3.0
        knob_x = knob_min_x + (knob_max_x - knob_min_x) * p
        knob_y = sw_y + 3.0

        if p > 0.5:
            knob_col = QColor("#ffffff")
        else:
            knob_col = QColor("#cfd5e8" if self._hover else "#8c93aa")
        if not enabled:
            knob_col.setAlpha(90)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_col)
        painter.drawEllipse(QRectF(knob_x, knob_y, knob_d, knob_d))
        painter.end()


class SettingsCategoryBar(QWidget):
    """
    3-Tab Segmented Pill Bar with the exact same 60 FPS horizontal sliding pill
    animation (_anim_pos) as the main window's J-POP | K-POP SegmentedSwitch!
    """

    tab_changed = pyqtSignal(int)

    def __init__(self, labels: List[str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._labels = labels
        self._selected = 0
        self._anim_pos = 0.0
        self._hover_idx = -1
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        self._slide_timer = QTimer(self)
        self._slide_timer.setInterval(16)
        self._slide_timer.timeout.connect(self._tick_slide)

    def _tick_slide(self) -> None:
        target = float(self._selected)
        diff = target - self._anim_pos
        if abs(diff) < 0.02:
            self._anim_pos = target
            self._slide_timer.stop()
        else:
            self._anim_pos += diff * 0.32
        self.update()

    def set_labels(self, labels: List[str]) -> None:
        self._labels = labels
        self.update()

    def set_selected(self, idx: int, animated: bool = True) -> None:
        if 0 <= idx < len(self._labels):
            self._selected = idx
            if not animated:
                self._anim_pos = float(idx)
                self._slide_timer.stop()
            else:
                self._slide_timer.start()
            self.update()

    def mouseMoveEvent(self, e) -> None:
        n = max(1, len(self._labels))
        seg_w = self.width() / float(n)
        idx = int(e.position().x() // seg_w)
        idx = max(0, min(n - 1, idx))
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, a0) -> None:
        self._hover_idx = -1
        self.update()
        super().leaveEvent(a0)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self._labels:
            n = len(self._labels)
            seg_w = self.width() / float(n)
            idx = int(e.position().x() // seg_w)
            idx = max(0, min(n - 1, idx))
            if idx != self._selected:
                self._selected = idx
                self._slide_timer.start()
                self.tab_changed.emit(idx)
                self.update()
        super().mousePressEvent(e)

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        radius = h / 2.0
        n = max(1, len(self._labels))
        seg_w = w / float(n)

        # 1. Outer dark glass track
        track_path = QPainterPath()
        track_path.addRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), radius, radius)
        painter.fillPath(track_path, QColor(18, 21, 34, 240))
        painter.setPen(QPen(QColor(255, 255, 255, 34), 1.0))
        painter.drawPath(track_path)

        # 2. Subtle hover highlight on non-active segment
        if 0 <= self._hover_idx < n and self._hover_idx != self._selected:
            hover_rect = QRectF(self._hover_idx * seg_w + 2.5, 2.5, seg_w - 5.0, h - 5.0)
            hover_path = QPainterPath()
            hover_path.addRoundedRect(hover_rect, radius - 2.5, radius - 2.5)
            painter.fillPath(hover_path, QColor(255, 255, 255, 16))

        # 3. Animated Sliding Active Indicator Pill (exact match with J-POP | K-POP switch)
        pad = 2.5
        pill_w = seg_w - pad * 2.0
        pill_h = h - pad * 2.0
        pill_x = self._anim_pos * seg_w + pad
        pill_y = pad
        pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h)

        grad = QLinearGradient(pill_x, pill_y, pill_x, pill_y + pill_h)
        grad.setColorAt(0.0, QColor(PALETTE["accent_hover"]))
        grad.setColorAt(1.0, QColor(PALETTE["accent"]))
        painter.setBrush(grad)
        painter.setPen(QPen(QColor(255, 255, 255, 65), 1.0))
        painter.drawRoundedRect(pill_rect, pill_h / 2.0, pill_h / 2.0)

        # 4. Segment labels (12px bold font)
        font = QFont(self.font())
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)

        for i, label in enumerate(self._labels):
            s_rect = QRectF(i * seg_w, 0.0, seg_w, h)
            if i == self._selected:
                painter.setPen(QColor("#ffffff"))
            elif i == self._hover_idx:
                painter.setPen(QColor("#e2e6f5"))
            else:
                painter.setPen(QColor("#9ea4ba"))
            painter.drawText(s_rect, Qt.AlignmentFlag.AlignCenter, label)

        painter.end()


class SettingsDialog(QDialog):
    settings_changed = pyqtSignal()

    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._host_window = parent
        self._embedded = embedded
        self._devices_populated = False
        self.setObjectName("settingsEmbeddedPanel" if embedded else "settingsDialogRoot")

        if embedded:
            self.setWindowFlags(Qt.WindowType.Widget)
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        else:
            self.setModal(False)
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
            self.setMinimumSize(460, 500)
            self.resize(480, 545)

        self.settings = QSettings(ORG_NAME, APP_SETTINGS)
        self.i18n = I18n(self.settings.value(KEY_LANG, "it"))
        self.setWindowTitle(self.i18n.t("settings_title"))

        self._apply_dialog_stylesheet()

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        if not embedded:
            app_icon = getattr(parent, "_icon_app", None) if parent is not None else None
            self._title_bar: Optional[CustomTitleBar] = CustomTitleBar(self, icon=app_icon)
            self._title_bar._btn_min.setVisible(False)
            self._title_bar._btn_max.setVisible(False)
            self._title_bar._ver_badge.setText(self.i18n.t("settings_title").upper())
            outer_layout.addWidget(self._title_bar)
            install_size_grip(self)
        else:
            self._title_bar = None

        # Inner Content Area
        body_layout = QVBoxLayout()
        if embedded:
            body_layout.setContentsMargins(12, 10, 12, 10)
            body_layout.setSpacing(8)
        else:
            body_layout.setContentsMargins(16, 12, 16, 14)
            body_layout.setSpacing(10)

        # Embedded Panel Header Row: [< Player]  IMPOSTAZIONI
        is_it = self.i18n.lang == "it"
        if embedded:
            hdr_row = QHBoxLayout()
            hdr_row.setContentsMargins(2, 0, 2, 2)
            hdr_row.setSpacing(8)

            self.btn_back = BackToPlayerButton("Player", self)
            self.btn_back.clicked.connect(self.reject)
            hdr_row.addWidget(self.btn_back)

            hdr_row.addStretch(1)
            self.panel_title_lbl = QLabel(self.i18n.t("settings_title").upper())
            self.panel_title_lbl.setStyleSheet(
                "color: #ffffff; font-size: 13px; font-weight: 800; letter-spacing: 1.5px;"
                " background: transparent; border: none;"
            )
            hdr_row.addWidget(self.panel_title_lbl)
            hdr_row.addStretch(1)

            balancer = QWidget()
            balancer.setFixedWidth(88)
            hdr_row.addWidget(balancer)
            body_layout.addLayout(hdr_row)

        # Top 4-Tab Segmented Switcher
        tab_labels = [
            self.i18n.t("settings_tab_general"),
            self.i18n.t("settings_tab_audio"),
            self.i18n.t("settings_tab_advanced"),
            self.i18n.t("settings_tab_info"),
        ]
        self.category_bar = SettingsCategoryBar(tab_labels, self)
        body_layout.addWidget(self.category_bar)

        # Sliding Stacked Pages
        self.pages = SlidingStackedWidget(self)
        self.category_bar.tab_changed.connect(self._on_tab_changed)

        combo_w = 165 if embedded else 200

        # ==================== PAGE 0: GENERALE & RIPRODUZIONE ====================
        page_gen = QWidget()
        gen_layout = QVBoxLayout(page_gen)
        gen_layout.setContentsMargins(0, 2, 0, 2)
        gen_layout.setSpacing(8)

        card_prefs, prefs_lay = self._make_card(
            "PREFERENZE RADIO" if is_it else "RADIO PREFERENCES"
        )

        self.cmb_lang = GlassComboBox()
        self.cmb_lang.addItems(["Italiano", "English"])
        self.cmb_lang.setCurrentIndex(0 if self.settings.value(KEY_LANG, "it") == "it" else 1)
        self.cmb_lang.setFixedWidth(combo_w)
        prefs_lay.addLayout(self._make_field_row(self.i18n.t("settings_language"), self.cmb_lang))

        self.cmb_channel = GlassComboBox()
        self.cmb_channel.addItems(["J-POP", "K-POP"])
        self.cmb_channel.setCurrentText(self.settings.value(KEY_CHANNEL, "J-POP"))
        self.cmb_channel.setFixedWidth(combo_w)
        prefs_lay.addLayout(self._make_field_row(self.i18n.t("settings_channel"), self.cmb_channel))

        gen_layout.addWidget(card_prefs)

        card_play, play_lay = self._make_card(
            "COMPORTAMENTO RIPRODUZIONE" if is_it else "PLAYBACK BEHAVIOR"
        )

        self.chk_autoplay = AnimatedToggleSwitch(self.i18n.t("settings_autoplay"))
        self.chk_autoplay.setChecked(self.settings.value(KEY_AUTOPLAY, "false") == "true")
        self.chk_autoplay.setToolTip(self.i18n.t("settings_autoplay_tip"))
        play_lay.addWidget(self.chk_autoplay)

        self.chk_sleep_stop = AnimatedToggleSwitch(self.i18n.t("settings_sleep_stop_on_end"))
        self.chk_sleep_stop.setChecked(self.settings.value(KEY_SLEEP_STOP_ON_END, "true") == "true")
        play_lay.addWidget(self.chk_sleep_stop)

        self.chk_session_timer = AnimatedToggleSwitch(self.i18n.t("settings_session_timer_enable"))
        self.chk_session_timer.setToolTip(self.i18n.t("settings_session_timer_tip"))
        self.chk_session_timer.setChecked(
            self.settings.value(KEY_SESSION_TIMER_ENABLED, "true") == "true"
        )
        play_lay.addWidget(self.chk_session_timer)

        gen_layout.addWidget(card_play)
        gen_layout.addStretch(1)
        self.pages.addWidget(page_gen)

        # ==================== PAGE 1: AUDIO & STREAM ====================
        page_audio = QWidget()
        audio_layout = QVBoxLayout(page_audio)
        audio_layout.setContentsMargins(0, 2, 0, 2)
        audio_layout.setSpacing(8)

        card_engine, eng_lay = self._make_card(
            "MOTORE AUDIO & USCITA" if is_it else "AUDIO ENGINE & OUTPUT"
        )

        self.cmb_format = GlassComboBox()
        self.cmb_format.addItems(["Vorbis", "Opus", "MP3"])
        self.cmb_format.setCurrentText(self.settings.value(KEY_FORMAT, "Vorbis"))
        self.cmb_format.setFixedWidth(combo_w)
        eng_lay.addLayout(self._make_field_row(self.i18n.t("settings_format"), self.cmb_format))

        self.cmb_audio_backend = GlassComboBox()
        self.cmb_audio_backend.addItem(self.i18n.t("settings_audio_backend_auto"), userData="auto")
        self.cmb_audio_backend.addItem(
            self.i18n.t("settings_audio_backend_ffmpeg"), userData="ffmpeg"
        )
        self.cmb_audio_backend.addItem(self.i18n.t("settings_audio_backend_mpv"), userData="mpv")
        self.cmb_audio_backend.addItem(self.i18n.t("settings_audio_backend_vlc"), userData="vlc")
        saved_backend = self.settings.value(KEY_AUDIO_BACKEND, "auto")
        for i in range(self.cmb_audio_backend.count()):
            if self.cmb_audio_backend.itemData(i) == saved_backend:
                self.cmb_audio_backend.setCurrentIndex(i)
                break
        self.cmb_audio_backend.setFixedWidth(combo_w)
        eng_lay.addLayout(
            self._make_field_row(self.i18n.t("settings_audio_backend"), self.cmb_audio_backend)
        )

        lab_audio = QLabel(self.i18n.t("settings_audio_output"))
        lab_audio.setObjectName("settingsFieldLabel")
        eng_lay.addWidget(lab_audio)

        audio_dev_row = QHBoxLayout()
        audio_dev_row.setContentsMargins(0, 0, 0, 0)
        audio_dev_row.setSpacing(6)
        self.cmb_audio_device = GlassComboBox()
        self.cmb_audio_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cmb_audio_device.addItem(self.i18n.t("settings_audio_default"), userData=None)
        audio_dev_row.addWidget(self.cmb_audio_device, 1)

        self.btn_audio_refresh = QPushButton(self.i18n.t("settings_audio_refresh"))
        self.btn_audio_refresh.setObjectName("secondaryGlassBtn")
        self.btn_audio_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_audio_refresh.clicked.connect(self._populate_audio_devices)
        audio_dev_row.addWidget(self.btn_audio_refresh)
        eng_lay.addLayout(audio_dev_row)

        audio_layout.addWidget(card_engine)

        card_net, net_lay = self._make_card(
            "BUFFER DI RETE & LIBVLC" if is_it else "NETWORK BUFFER & LIBVLC"
        )

        nc_row = QHBoxLayout()
        nc_row.setContentsMargins(0, 0, 0, 0)
        nc_row.setSpacing(6)
        lab_nc = QLabel(self.i18n.t("settings_network_caching"))
        lab_nc.setObjectName("settingsFieldLabel")
        nc_row.addWidget(lab_nc)
        nc_row.addStretch(1)

        btn_nc_minus = QPushButton("−")
        btn_nc_minus.setObjectName("stepperBtn")
        btn_nc_minus.setFixedSize(28, 28)
        btn_nc_minus.setCursor(Qt.CursorShape.PointingHandCursor)

        self.spin_network_caching = QSpinBox()
        self.spin_network_caching.setRange(100, 5000)
        self.spin_network_caching.setSingleStep(100)
        self.spin_network_caching.setSuffix(" ms")
        self.spin_network_caching.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin_network_caching.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_network_caching.setFixedSize(96, 28)
        try:
            self.spin_network_caching.setValue(int(self.settings.value(KEY_NETWORK_CACHING, 1000)))
        except Exception:
            self.spin_network_caching.setValue(1000)

        btn_nc_plus = QPushButton("+")
        btn_nc_plus.setObjectName("stepperBtn")
        btn_nc_plus.setFixedSize(28, 28)
        btn_nc_plus.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_nc_minus.clicked.connect(
            lambda: self.spin_network_caching.setValue(
                max(100, self.spin_network_caching.value() - 100)
            )
        )
        btn_nc_plus.clicked.connect(
            lambda: self.spin_network_caching.setValue(
                min(5000, self.spin_network_caching.value() + 100)
            )
        )

        nc_row.addWidget(btn_nc_minus)
        nc_row.addWidget(self.spin_network_caching)
        nc_row.addWidget(btn_nc_plus)
        net_lay.addLayout(nc_row)

        lab_path = QLabel(self.i18n.t("settings_vlc_path"))
        lab_path.setObjectName("settingsFieldLabel")
        net_lay.addWidget(lab_path)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.setSpacing(6)
        self.txt_vlc_path = QLineEdit(self.settings.value(KEY_LIBVLC_PATH, ""))
        self.txt_vlc_path.setPlaceholderText("Auto / System PATH")
        path_row.addWidget(self.txt_vlc_path, 1)

        self.btn_browse = QPushButton(self.i18n.t("settings_browse"))
        self.btn_browse.setObjectName("secondaryGlassBtn")
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self._browse_vlc_path)
        path_row.addWidget(self.btn_browse)
        net_lay.addLayout(path_row)

        audio_layout.addWidget(card_net)
        audio_layout.addStretch(1)
        self.pages.addWidget(page_audio)

        # ==================== PAGE 2: TRAY & CONSOLE ====================
        page_sys = QWidget()
        sys_layout = QVBoxLayout(page_sys)
        sys_layout.setContentsMargins(0, 2, 0, 2)
        sys_layout.setSpacing(8)

        card_tray, tray_lay = self._make_card("SYSTEM TRAY")

        self.chk_tray_enabled = AnimatedToggleSwitch(self.i18n.t("settings_tray_enable"))
        self.chk_tray_enabled.setChecked(self.settings.value(KEY_TRAY_ENABLED, "true") == "true")
        tray_lay.addWidget(self.chk_tray_enabled)

        self.chk_tray_hide_on_minimize = AnimatedToggleSwitch(
            self.i18n.t("settings_tray_hide_on_minimize")
        )
        self.chk_tray_hide_on_minimize.setChecked(
            self.settings.value(KEY_TRAY_HIDE_ON_MINIMIZE, "true") == "true"
        )
        self.chk_tray_hide_on_minimize.setEnabled(self.chk_tray_enabled.isChecked())
        self.chk_tray_enabled.stateChanged.connect(
            lambda _s: self.chk_tray_hide_on_minimize.setEnabled(self.chk_tray_enabled.isChecked())
        )
        tray_lay.addWidget(self.chk_tray_hide_on_minimize)

        self.chk_tray_notifications = AnimatedToggleSwitch(
            self.i18n.t("settings_tray_notifications")
        )
        self.chk_tray_notifications.setChecked(
            self.settings.value(KEY_TRAY_NOTIFICATIONS, "true") == "true"
        )
        tray_lay.addWidget(self.chk_tray_notifications)

        sys_layout.addWidget(card_tray)

        card_dev, dev_lay = self._make_card(
            "CONSOLE SVILUPPATORE" if is_it else "DEVELOPER CONSOLE"
        )

        dev_top_row = QHBoxLayout()
        dev_top_row.setContentsMargins(0, 0, 0, 0)
        dev_top_row.setSpacing(6)
        self.chk_dev_console = AnimatedToggleSwitch(self.i18n.t("settings_dev_console"))
        self.chk_dev_console.setChecked(
            self.settings.value(KEY_DEV_CONSOLE_ENABLED, "false") == "true"
        )
        dev_top_row.addWidget(self.chk_dev_console, 1)

        self.btn_open_console = QPushButton(self.i18n.t("dev_console_button"))
        self.btn_open_console.setObjectName("secondaryGlassBtn")
        self.btn_open_console.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_console.setEnabled(True)
        self.btn_open_console.clicked.connect(self._on_open_console)
        dev_top_row.addWidget(self.btn_open_console)
        dev_lay.addLayout(dev_top_row)

        self.chk_dev_show_dev = AnimatedToggleSwitch(self.i18n.t("settings_dev_console_show_dev"))
        self.chk_dev_show_dev.setChecked(
            self.settings.value(KEY_DEV_CONSOLE_SHOW_DEV, "false") == "true"
        )
        self.chk_dev_show_dev.setEnabled(self.chk_dev_console.isChecked())
        self.chk_dev_console.stateChanged.connect(
            lambda _s: self.chk_dev_show_dev.setEnabled(self.chk_dev_console.isChecked())
        )
        dev_lay.addWidget(self.chk_dev_show_dev)

        sys_layout.addWidget(card_dev)
        sys_layout.addStretch(1)
        self.pages.addWidget(page_sys)

        # ==================== PAGE 3: INFO & CREDITI ====================
        page_about = QWidget()
        about_lay = QVBoxLayout(page_about)
        about_lay.setContentsMargins(0, 2, 0, 2)
        about_lay.setSpacing(8)

        backend_name = "Auto"
        if parent is not None and hasattr(parent, "player") and parent.player is not None:
            backend_name = getattr(
                parent.player,
                "BACKEND_NAME",
                type(parent.player).__name__.replace("Player", ""),
            )
        self.about_widget = AboutWidget(
            page_about,
            i18n=self.i18n,
            backend_name=backend_name,
        )
        about_lay.addWidget(self.about_widget)
        self.pages.addWidget(page_about)

        body_layout.addWidget(self.pages, 1)

        # Bottom Action Deck (Annulla | Applica | OK)
        footer_frame = QFrame()
        footer_frame.setObjectName("settingsFooterDeck")
        btn_row = QHBoxLayout(footer_frame)
        btn_row.setContentsMargins(10, 7, 10, 7)
        btn_row.setSpacing(8)

        self.btn_cancel = QPushButton(self.i18n.t("settings_cancel"))
        self.btn_cancel.setObjectName("neutralActionBtn")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setFixedHeight(30)

        self.btn_apply = QPushButton(self.i18n.t("settings_apply"))
        self.btn_apply.setObjectName("secondaryGlassBtn")
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.setFixedHeight(30)

        self.btn_ok = QPushButton(self.i18n.t("settings_ok"))
        self.btn_ok.setObjectName("primaryActionBtn")
        self.btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ok.setFixedHeight(30)

        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply.clicked.connect(self._on_apply)

        btn_row.addWidget(self.btn_cancel, 1)
        btn_row.addWidget(self.btn_apply, 1)
        btn_row.addWidget(self.btn_ok, 1)
        body_layout.addWidget(footer_frame)

        outer_layout.addLayout(body_layout, 1)
        QTimer.singleShot(140, self._ensure_devices_populated)

    def _ensure_devices_populated(self) -> None:
        if not self._devices_populated:
            self._devices_populated = True
            self._populate_audio_devices()

    def set_tab(self, idx: int, animated: bool = False) -> None:
        """Programmatically switch to tab index (0=General, 1=Audio, 2=Advanced, 3=Info)."""
        if hasattr(self, "category_bar") and hasattr(self, "pages"):
            self.category_bar.set_selected(idx, animated=animated)
            if not animated:
                self.pages.setCurrentIndex(idx)
            else:
                self._on_tab_changed(idx)

    def _on_tab_changed(self, idx: int) -> None:
        for cmb in self.findChildren(GlassComboBox):
            cmb.reset_visual_state()
        self.pages.slide_to_index(idx)
        if idx == 1 and not self._devices_populated:
            QTimer.singleShot(210, self._ensure_devices_populated)

    def reload_from_settings(self) -> None:
        """Fast non-blocking reload of widget values from QSettings."""
        self.settings.sync()
        lang = str(self.settings.value(KEY_LANG, "it"))
        self.i18n.set_lang(lang)
        self.cmb_lang.setCurrentIndex(0 if lang == "it" else 1)
        self.cmb_channel.setCurrentText(str(self.settings.value(KEY_CHANNEL, "J-POP")))
        self.cmb_format.setCurrentText(str(self.settings.value(KEY_FORMAT, "Vorbis")))
        saved_backend = self.settings.value(KEY_AUDIO_BACKEND, "auto")
        for i in range(self.cmb_audio_backend.count()):
            if self.cmb_audio_backend.itemData(i) == saved_backend:
                self.cmb_audio_backend.setCurrentIndex(i)
                break
        self.chk_autoplay.setChecked(self.settings.value(KEY_AUTOPLAY, "false") == "true")
        self.chk_sleep_stop.setChecked(self.settings.value(KEY_SLEEP_STOP_ON_END, "true") == "true")
        self.chk_session_timer.setChecked(
            self.settings.value(KEY_SESSION_TIMER_ENABLED, "true") == "true"
        )
        self.chk_tray_enabled.setChecked(self.settings.value(KEY_TRAY_ENABLED, "true") == "true")
        self.chk_tray_hide_on_minimize.setChecked(
            self.settings.value(KEY_TRAY_HIDE_ON_MINIMIZE, "true") == "true"
        )
        self.chk_tray_notifications.setChecked(
            self.settings.value(KEY_TRAY_NOTIFICATIONS, "true") == "true"
        )
        self.chk_dev_console.setChecked(
            self.settings.value(KEY_DEV_CONSOLE_ENABLED, "false") == "true"
        )
        self.chk_dev_show_dev.setChecked(
            self.settings.value(KEY_DEV_CONSOLE_SHOW_DEV, "false") == "true"
        )
        if not self._devices_populated:
            QTimer.singleShot(250, self._ensure_devices_populated)
        tab_labels = [
            self.i18n.t("settings_tab_general"),
            self.i18n.t("settings_tab_audio"),
            self.i18n.t("settings_tab_advanced"),
            self.i18n.t("settings_tab_info"),
        ]
        self.category_bar.set_labels(tab_labels)
        if hasattr(self, "about_widget"):
            self.about_widget.set_i18n(self.i18n)
            if self._host_window is not None and hasattr(self._host_window, "player"):
                be = (
                    getattr(
                        self._host_window.player,
                        "BACKEND_NAME",
                        type(self._host_window.player).__name__.replace("Player", ""),
                    )
                    if self._host_window.player
                    else "Auto"
                )
                self.about_widget.set_backend_name(be)

    @staticmethod
    def _make_card(section_title: str):
        card = QFrame()
        card.setObjectName("settingsCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(13, 10, 13, 11)
        lay.setSpacing(7)

        hdr = QLabel(section_title)
        hdr.setObjectName("settingsSectionHeader")
        lay.addWidget(hdr)
        return card, lay

    @staticmethod
    def _make_field_row(label_text: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        lbl = QLabel(label_text)
        lbl.setObjectName("settingsFieldLabel")
        row.addWidget(lbl)
        row.addStretch(1)
        row.addWidget(widget)
        return row

    def _sync_backdrop_from_parent(self) -> None:
        pass

    def _apply_dialog_stylesheet(self) -> None:
        base_qss = get_cyber_moe_stylesheet(PALETTE["accent"])
        extra_qss = f"""
        QDialog#settingsDialogRoot {{
            background-color: #0c0e17;
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 12px;
        }}
        QDialog#settingsEmbeddedPanel {{
            background-color: rgba(12, 14, 22, 0.96);
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 16px;
        }}
        QFrame#settingsCard {{
            background-color: #151826;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-top: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 13px;
        }}
        QFrame#settingsFooterDeck {{
            background-color: #131624;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 12px;
        }}
        QLabel#settingsSectionHeader {{
            color: {PALETTE["accent_hover"]};
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 1.1px;
            background: transparent;
            border: none;
            padding-bottom: 2px;
        }}
        QLabel#settingsFieldLabel {{
            color: #e4e8f6;
            font-size: 13px;
            font-weight: 600;
            background: transparent;
            border: none;
            padding-left: 2px;
        }}
        QLineEdit, QSpinBox {{
            background-color: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 8px;
            padding: 4px 10px;
            color: #f4f6fd;
            font-size: 13px;
            font-weight: 600;
            min-height: 22px;
        }}
        QLineEdit:hover, QSpinBox:hover,
        QLineEdit:focus, QSpinBox:focus {{
            border-color: {PALETTE["accent"]};
            background-color: rgba(236, 24, 108, 0.12);
        }}
        QPushButton#primaryActionBtn {{
            background-color: {PALETTE["accent"]};
            color: #ffffff;
            border: none;
            border-radius: 9px;
            padding: 0px 10px;
            font-size: 12px;
            font-weight: 700;
        }}
        QPushButton#primaryActionBtn:hover {{
            background-color: {PALETTE["accent_hover"]};
        }}
        QPushButton#primaryActionBtn:pressed {{
            background-color: {PALETTE["accent_pressed"]};
        }}
        QPushButton#secondaryGlassBtn {{
            background-color: rgba(255, 255, 255, 0.07);
            color: #e4e8f6;
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 9px;
            padding: 4px 11px;
            font-size: 12px;
            font-weight: 700;
        }}
        QPushButton#secondaryGlassBtn:hover {{
            background-color: rgba(236, 24, 108, 0.22);
            border-color: {PALETTE["accent"]};
            color: #ffffff;
        }}
        QPushButton#neutralActionBtn {{
            background-color: rgba(255, 255, 255, 0.04);
            color: #a6adc4;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 9px;
            padding: 0px 10px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#neutralActionBtn:hover {{
            background-color: rgba(255, 255, 255, 0.10);
            color: #ffffff;
        }}
        QPushButton#stepperBtn {{
            background-color: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 8px;
            padding: 0px;
            font-size: 14px;
            font-weight: 700;
            color: #d0d5e8;
        }}
        QPushButton#stepperBtn:hover {{
            background-color: rgba(236, 24, 108, 0.25);
            border-color: {PALETTE["accent"]};
            color: #ffffff;
        }}
        """
        self.setStyleSheet(base_qss + extra_qss)

    def _browse_vlc_path(self):
        start_dir = self.txt_vlc_path.text().strip() or self.settings.value(KEY_LIBVLC_PATH, None)
        if not start_dir:
            start_dir = "C:/" if _IS_WIN32 else os.path.expanduser("~")
        chosen = QFileDialog.getExistingDirectory(
            self, self.i18n.t("libvlc_choose_title"), start_dir
        )
        if chosen:
            self.txt_vlc_path.setText(chosen)

    def _on_apply(self):
        """Salva i valori senza chiudere il pannello."""
        self._save_settings()
        try:
            self.settings_changed.emit()
        except Exception:
            pass

    def _on_ok(self):
        """Salva i valori e chiude il pannello."""
        self._save_settings()
        self.accept()

    def _on_open_console(self):
        try:
            self._save_settings()
            host = self._host_window or self.window()
            if host and hasattr(host, "open_dev_console"):
                try:
                    host.open_dev_console(host)
                except TypeError:
                    host.open_dev_console()
        except Exception:
            pass

    def _save_settings(self):
        """Logica comune per salvare le impostazioni."""
        self.settings.setValue(KEY_AUTOPLAY, "true" if self.chk_autoplay.isChecked() else "false")
        self.settings.setValue(
            KEY_SLEEP_STOP_ON_END, "true" if self.chk_sleep_stop.isChecked() else "false"
        )
        self.settings.setValue(
            KEY_SESSION_TIMER_ENABLED, "true" if self.chk_session_timer.isChecked() else "false"
        )
        self.settings.setValue(
            KEY_DEV_CONSOLE_ENABLED, "true" if self.chk_dev_console.isChecked() else "false"
        )
        self.settings.setValue(
            KEY_DEV_CONSOLE_SHOW_DEV, "true" if self.chk_dev_show_dev.isChecked() else "false"
        )
        self.settings.setValue(KEY_LANG, "it" if self.cmb_lang.currentIndex() == 0 else "en")
        self.settings.setValue(KEY_CHANNEL, self.cmb_channel.currentText())
        self.settings.setValue(KEY_FORMAT, self.cmb_format.currentText())
        path = self.txt_vlc_path.text().strip()
        self.settings.setValue(KEY_LIBVLC_PATH, path if path else "")
        self.settings.setValue(KEY_NETWORK_CACHING, int(self.spin_network_caching.value()))
        self.settings.setValue(
            KEY_TRAY_ENABLED, "true" if self.chk_tray_enabled.isChecked() else "false"
        )
        self.settings.setValue(
            KEY_TRAY_HIDE_ON_MINIMIZE,
            "true" if self.chk_tray_hide_on_minimize.isChecked() else "false",
        )
        self.settings.setValue(
            KEY_TRAY_NOTIFICATIONS, "true" if self.chk_tray_notifications.isChecked() else "false"
        )
        try:
            self.settings.setValue(
                KEY_AUDIO_BACKEND, self.cmb_audio_backend.currentData() or "auto"
            )
        except Exception:
            pass
        try:
            idx_data = self.cmb_audio_device.currentData()
            if idx_data is None:
                self.settings.setValue(KEY_AUDIO_DEVICE_INDEX, "")
            else:
                self.settings.setValue(KEY_AUDIO_DEVICE_INDEX, int(idx_data))
        except Exception:
            pass

    def showEvent(self, event):
        try:
            super().showEvent(event)
        except Exception:
            pass
        if not self._embedded:
            try:
                self._apply_windows_titlebar_dark_mode(True)
            except Exception:
                pass
            if not self._devices_populated:
                self._devices_populated = True
                QTimer.singleShot(50, self._populate_audio_devices)

    def _apply_windows_titlebar_dark_mode(self, enable: bool) -> None:
        try:
            apply_windows_titlebar_dark_mode(self, enable)
        except Exception:
            pass

    _PA_API_TAGS = {
        8: "ALSA",
        18: "PipeWire/Pulse",
        12: "JACK",
        2: "MME",
        13: "WASAPI",
        1: "DirectSound",
    }

    def _populate_audio_devices(self) -> None:
        try:
            import pyaudio
        except Exception:
            pyaudio = None
        try:
            for i in range(self.cmb_audio_device.count() - 1, 0, -1):
                self.cmb_audio_device.removeItem(i)
        except Exception:
            pass
        if pyaudio is None:
            return
        pa = None
        try:
            with silence_stderr():
                pa = pyaudio.PyAudio()
            api_type_map: dict = {}
            try:
                for api_idx in range(pa.get_host_api_count()):
                    ai = pa.get_host_api_info_by_index(api_idx)
                    if isinstance(ai, dict):
                        api_type_map[api_idx] = ai.get("type", -1)
            except Exception:
                pass

            device_count = pa.get_device_count() if hasattr(pa, "get_device_count") else 0
            for i in range(device_count):
                try:
                    info = pa.get_device_info_by_index(i)
                except Exception:
                    info = None
                if not isinstance(info, dict):
                    continue
                max_output = int(info.get("maxOutputChannels", 0))
                name = str(info.get("name", f"Device {i}"))
                if max_output > 0:
                    if not _IS_WIN32:
                        api_idx = info.get("hostApi", -1)
                        api_type = api_type_map.get(api_idx, -1)
                        tag = self._PA_API_TAGS.get(api_type, "")
                        label = f"[{tag}] {name} (#{i})" if tag else f"{name} (#{i})"
                    else:
                        label = f"{name} (#{i})"
                    self.cmb_audio_device.addItem(label, i)
            persisted = self.settings.value(KEY_AUDIO_DEVICE_INDEX, "")
            if persisted != "" and persisted is not None:
                try:
                    persisted = int(persisted)
                    for combo_idx in range(self.cmb_audio_device.count()):
                        if self.cmb_audio_device.itemData(combo_idx) == persisted:
                            self.cmb_audio_device.setCurrentIndex(combo_idx)
                            break
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            try:
                if pa is not None and hasattr(pa, "terminate"):
                    pa.terminate()
            except Exception:
                pass
