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
import threading
from typing import Any, List, Optional, Tuple

from PyQt6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
    QResizeEvent,
    QShowEvent,
)
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from core.config import STATIONS, get_station_config, get_station_display_name
from core.constants import (
    APP_SETTINGS,
    APP_VERSION,
    DEFAULT_ACCENT_COLOR,
    DEFAULT_AMBIENT_MODE_ENABLED,
    DEFAULT_DYNAMIC_VOLUME_APPS,
    DEFAULT_DYNAMIC_VOLUME_ENABLED,
    DEFAULT_DYNAMIC_VOLUME_LEVEL,
    DEFAULT_DYNAMIC_VOLUME_MODE,
    DEFAULT_LYRICS_PROVIDER,
    DEFAULT_STATION,
    DEFAULT_THEME,
    DEFAULT_VISUALIZER_ENABLED,
    KEY_AMBIENT_MODE_ENABLED,
    KEY_AUDIO_BACKEND,
    KEY_AUDIO_DEVICE_INDEX,
    KEY_AUTOPLAY,
    KEY_BETTERLYRICS_API_KEY,
    KEY_CHANNEL,
    KEY_CUSTOM_ACCENT,
    KEY_CUSTOM_ACCENT_ENABLED,
    KEY_DEV_CONSOLE_ENABLED,
    KEY_DEV_CONSOLE_SHOW_DEV,
    KEY_DISCORD_CLIENT_ID,
    KEY_DISCORD_RPC_ENABLED,
    KEY_DYNAMIC_VOLUME_APPS,
    KEY_DYNAMIC_VOLUME_ENABLED,
    KEY_DYNAMIC_VOLUME_LEVEL,
    KEY_DYNAMIC_VOLUME_MODE,
    KEY_FORMAT,
    KEY_LANG,
    KEY_LIBVLC_PATH,
    KEY_LYRICS_PROVIDER,
    KEY_NETWORK_CACHING,
    KEY_SESSION_TIMER_ENABLED,
    KEY_SHOW_SLEEP_TIMER,
    KEY_SLEEP_STOP_ON_END,
    KEY_STATION,
    KEY_THEME,
    KEY_TRAY_ENABLED,
    KEY_TRAY_HIDE_ON_MINIMIZE,
    KEY_TRAY_NOTIFICATIONS,
    KEY_UPDATE_CHANNEL,
    KEY_UPDATE_CHECK_ON_STARTUP,
    KEY_VISUALIZER_ENABLED,
    LYRICS_PROVIDER_AUTO,
    LYRICS_PROVIDER_BETTERLYRICS,
    LYRICS_PROVIDER_BETTERLYRICS_FIRST,
    LYRICS_PROVIDER_LRCLIB,
    ORG_NAME,
    UPDATE_CHANNEL_BETA,
    UPDATE_CHANNEL_STABLE,
)
from core.dynamic_volume import (
    DYNAMIC_MODE_ANY_OPEN,
    DYNAMIC_MODE_FOREGROUND,
    list_suggested_running_apps,
    parse_app_list,
)
from core.i18n import I18n
from core.logger import PORTAUDIO_LOCK, silence_stderr
from core.updater import UpdateCheckWorker
from ui.about_dialog import AboutWidget
from ui.color_picker_dialog import AccentColorPickerDialog
from ui.custom_titlebar import CustomTitleBar, install_size_grip
from ui.native_file_dialog import get_existing_directory
from ui.themes.cyber_moe import (
    PALETTE,
    THEME_ORDER,
    THEME_PRESETS,
    accent_qcolor,
    apply_theme_palette,
    get_cyber_moe_stylesheet,
    get_preset_default_accent,
    is_valid_hex_color,
    normalize_hex_color,
    resolve_theme_and_accent,
    surface_qcolor,
)
from ui.update_dialog import UpdateDialog
from ui.vector_icons import (
    get_apps_icon,
    get_folder_icon,
    get_minus_icon,
    get_plus_icon,
    get_refresh_icon,
    get_update_icon,
)
from ui.windows_titlebar import apply_windows_titlebar_dark_mode

_IS_WIN32 = sys.platform == "win32"
_CACHED_AUDIO_DEVICES: Optional[List[Tuple[str, int]]] = None


class SlidingStackedWidget(QStackedWidget):
    """
    QStackedWidget with 60 FPS time-based slide + crossfade transitions using
    pre-rendered HiDPI QPixmap snapshots.
    - Eliminates transparent tab overlap (outgoing and incoming snapshots slide
      side-by-side without overlapping, while smoothly fading opacity).
    - Hides live child widgets during the 190ms transition so QStackedLayout
      never fights widget positions or flashes an unstyled UI skeleton.
    """

    DURATION_MS = 210.0

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._anim_timer = QTimer(self)
        self._anim_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._anim_timer.setInterval(16)
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
        if self._pm_from is None or self._pm_to is None:
            super().paintEvent(a0)
            return

        painter = QPainter(self)
        w = float(self.width())
        t = self._progress
        # Smooth cubic-out easing
        ease = 1.0 - ((1.0 - t) ** 3)
        d = float(self._direction)

        # Non-overlapping side-by-side slide with smooth opacity crossfade
        # Integer pixel coordinates ensure hardware blit and prevent subpixel jitter
        x_from = int(round(-d * w * ease))
        x_to = int(round(d * w * (1.0 - ease)))

        alpha_from = max(0.0, min(1.0, (1.0 - ease) ** 1.35))
        alpha_to = max(0.0, min(1.0, 0.25 + 0.75 * ease))

        if alpha_from > 0.01:
            painter.setOpacity(alpha_from)
            painter.drawPixmap(QPoint(x_from, 0), self._pm_from)

        painter.setOpacity(alpha_to)
        painter.drawPixmap(QPoint(x_to, 0), self._pm_to)
        painter.end()


class BackToPlayerButton(QPushButton):
    """
    Custom vector '< Player' pill button with anti-aliased chevron icon,
    smooth hover chevron nudge, and tactile press state without clipping or glitching.
    """

    def __init__(self, text: str = "Player", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self._hover = False
        self._pressed = False
        self._chevron_offset = 0.0
        self._target_offset = 0.0
        self.setFixedSize(88, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)

    def reset_state(self) -> None:
        """Resets button to pristine idle state for clean snapshot transitions."""
        self._hover = False
        self._pressed = False
        self._chevron_offset = 0.0
        self._target_offset = 0.0
        if self._anim_timer.isActive():
            self._anim_timer.stop()
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self._target_offset = -2.2
        if not self._anim_timer.isActive():
            self._anim_timer.start()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, a0) -> None:
        self._hover = False
        self._pressed = False
        self._target_offset = 0.0
        if not self._anim_timer.isActive():
            self._anim_timer.start()
        self.update()
        super().leaveEvent(a0)

    def mousePressEvent(self, e) -> None:
        if e is not None and e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._target_offset = -3.2
            if not self._anim_timer.isActive():
                self._anim_timer.start()
            self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._pressed = False
        self._target_offset = -2.2 if self._hover else 0.0
        if not self._anim_timer.isActive():
            self._anim_timer.start()
        self.update()
        super().mouseReleaseEvent(e)

    def hideEvent(self, a0) -> None:
        self.reset_state()
        super().hideEvent(a0)

    def _tick_anim(self) -> None:
        diff = self._target_offset - self._chevron_offset
        if abs(diff) < 0.15:
            self._chevron_offset = self._target_offset
            self._anim_timer.stop()
        else:
            self._chevron_offset += diff * 0.35
        self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cy = h / 2.0

        if self._hover or self._pressed:
            bg = accent_qcolor(48 if self._pressed else 30)
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
        ix = 16.0 + self._chevron_offset
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
            QRectF(22.0, 0.0, w - 26.0, h),
            Qt.AlignmentFlag.AlignCenter,
            self.text(),
        )
        painter.end()


class GlassComboDelegate(QStyledItemDelegate):
    """
    Delegate for GlassComboBox popup items ensuring consistent row heights (>= 30px)
    and clean focus-free painting so selected vs hovered states remain distinct.
    """

    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, opt, index)

    def sizeHint(self, option, index) -> QSize:
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), max(sh.height(), 30))


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
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(1)

        list_view = QListView(self)
        list_view.setUniformItemSizes(True)
        list_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        list_view.setTextElideMode(Qt.TextElideMode.ElideNone)
        list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_view.setItemDelegate(GlassComboDelegate(list_view))

        font = QFont()
        font.setFamilies(["Segoe UI", "Inter", "Cantarell", "Ubuntu", "DejaVu Sans", "sans-serif"])
        font.setPointSize(9)
        font.setWeight(QFont.Weight.Medium)
        self.setFont(font)
        list_view.setFont(font)
        self._list_view = list_view
        self._apply_list_view_style()

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

    def _apply_list_view_style(self) -> None:
        if not hasattr(self, "_list_view") or self._list_view is None:
            return
        self._list_view.setStyleSheet(
            f"""
            QListView {{
                background-color: {PALETTE["bg_popover"]};
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 10px;
                color: {PALETTE["text_primary"]};
                font-size: 9pt;
                font-weight: 500;
                selection-background-color: transparent;
                selection-color: #ffffff;
                padding: 5px;
                outline: none;
            }}
            QListView::item {{
                min-height: 30px;
                padding: 4px 12px;
                border-radius: 7px;
                border: 1px solid transparent;
                margin: 1px 0px;
                color: {PALETTE["text_secondary"]};
            }}
            QListView::item:hover {{
                background-color: rgba(255, 255, 255, 0.09);
                border: 1px solid rgba(255, 255, 255, 0.16);
                color: #ffffff;
            }}
            QListView::item:selected {{
                background-color: {PALETTE["accent_soft"]};
                border: 1px solid {PALETTE["accent"]};
                color: #ffffff;
                font-weight: 600;
            }}
            QListView::item:selected:hover {{
                background-color: {PALETTE["accent_menu_hover"]};
                border: 1px solid {PALETTE["accent_hover"]};
                color: #ffffff;
            }}
            """
        )

    def refresh_theme(self) -> None:
        self._apply_list_view_style()
        self.update()

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
            fm = view.fontMetrics()
            max_item_w = 0
            for i in range(self.count()):
                w_item = fm.horizontalAdvance(self.itemText(i))
                if w_item > max_item_w:
                    max_item_w = w_item
            needed_w = max(self.width(), min(360, max_item_w + 42))
            view.setMinimumWidth(needed_w)
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

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

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
            bg = accent_qcolor(30)
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

    def sizeHint(self) -> QSize:
        return QSize(200, 38)

    def minimumSizeHint(self) -> QSize:
        return QSize(120, 38)

    def setChecked(self, a0: bool) -> None:
        super().setChecked(a0)
        self._progress = 1.0 if a0 else 0.0
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

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

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
        font.setWeight(QFont.Weight.DemiBold)
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

        act_col = QColor(PALETTE["accent"])
        r_bg = int(28 + (act_col.red() - 28) * p)
        g_bg = int(32 + (act_col.green() - 32) * p)
        b_bg = int(48 + (act_col.blue() - 48) * p)
        a_bg = int(195 + (255 - 195) * p)
        if not enabled:
            a_bg = int(a_bg * 0.45)

        track_col = QColor(r_bg, g_bg, b_bg, a_bg)
        if p > 0.5:
            border_col = QColor(PALETTE["accent_hover"] if self._hover else PALETTE["accent"])
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
            knob_col = QColor(PALETTE["on_accent"])
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
        self._anim_start_pos = 0.0
        self._hover_idx = -1
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        self._slide_elapsed = QElapsedTimer()
        self._slide_timer = QTimer(self)
        self._slide_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._slide_timer.setInterval(16)
        self._slide_timer.timeout.connect(self._tick_slide)

    def _tick_slide(self) -> None:
        target = float(self._selected)
        elapsed = float(self._slide_elapsed.elapsed())
        duration = 180.0
        t = min(1.0, max(0.0, elapsed / duration))
        ease = 1.0 - ((1.0 - t) ** 3)
        self._anim_pos = self._anim_start_pos + (target - self._anim_start_pos) * ease
        if t >= 1.0:
            self._anim_pos = target
            self._slide_timer.stop()
        self.update()

    def set_labels(self, labels: List[str]) -> None:
        self._labels = labels
        self.update()

    def set_selected(self, idx: int, animated: bool = True) -> None:
        if 0 <= idx < len(self._labels):
            self._selected = idx
            if not animated:
                self._anim_pos = float(idx)
                self._anim_start_pos = float(idx)
                self._slide_timer.stop()
            else:
                self._anim_start_pos = self._anim_pos
                self._slide_elapsed.start()
                self._slide_timer.start()
            self.update()

    def mouseMoveEvent(self, a0) -> None:
        if a0 is not None:
            n = max(1, len(self._labels))
            seg_w = self.width() / float(n)
            idx = int(a0.position().x() // seg_w)
            idx = max(0, min(n - 1, idx))
            if idx != self._hover_idx:
                self._hover_idx = idx
                self.update()
        super().mouseMoveEvent(a0)

    def leaveEvent(self, a0) -> None:
        self._hover_idx = -1
        self.update()
        super().leaveEvent(a0)

    def mousePressEvent(self, a0) -> None:
        if a0 is not None and a0.button() == Qt.MouseButton.LeftButton and self._labels:
            n = len(self._labels)
            seg_w = self.width() / float(n)
            idx = int(a0.position().x() // seg_w)
            idx = max(0, min(n - 1, idx))
            if idx != self._selected:
                self._selected = idx
                self._anim_start_pos = self._anim_pos
                self._slide_elapsed.start()
                self._slide_timer.start()
                self.tab_changed.emit(idx)
                self.update()
        super().mousePressEvent(a0)

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
        painter.fillPath(track_path, surface_qcolor(240, "bg_pill_idle"))
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
                painter.setPen(QColor(PALETTE["on_accent"]))
            elif i == self._hover_idx:
                painter.setPen(QColor("#e2e6f5"))
            else:
                painter.setPen(QColor("#9ea4ba"))
            painter.drawText(s_rect, Qt.AlignmentFlag.AlignCenter, label)

        painter.end()


class AccentColorSwatchButton(QPushButton):
    """
    Sleek Cyber-Moe capsule button displaying a glowing color swatch circle
    and uppercase '#RRGGBB' hex code. Clicking opens QColorDialog.
    """

    color_changed = pyqtSignal(str)

    def __init__(
        self,
        initial_color: str = DEFAULT_ACCENT_COLOR,
        dialog_title: Optional[str] = None,
        i18n: Optional[I18n] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._color = normalize_hex_color(initial_color)
        self._i18n = i18n
        self._dialog_title = dialog_title or (
            i18n.t("settings_custom_accent_dialog_title")
            if i18n is not None
            else "Select Accent Color"
        )
        self._hover = False
        self._pressed = False
        self.setFixedSize(112, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._open_picker)

    def color(self) -> str:
        return self._color

    def set_color(self, color_hex: str, emit_signal: bool = False) -> None:
        norm = normalize_hex_color(color_hex, self._color)
        changed = norm != self._color
        self._color = norm
        self.update()
        if changed and emit_signal:
            self.color_changed.emit(self._color)

    def set_dialog_title(self, title: str) -> None:
        self._dialog_title = title

    def _open_picker(self) -> None:
        host = self.window()
        i18n = self._i18n or getattr(host, "i18n", None)
        icon = getattr(host, "_icon_app", None) or (host.windowIcon() if host else None)
        chosen = AccentColorPickerDialog.get_color(
            initial_color=self._color,
            parent=host,
            title=self._dialog_title,
            i18n=i18n,
            icon=icon,
        )
        if chosen:
            self.set_color(chosen, emit_signal=True)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, a0) -> None:
        self._hover = False
        self._pressed = False
        self.update()
        super().leaveEvent(a0)

    def mousePressEvent(self, e) -> None:
        if e is not None and e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(e)

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        swatch_col = QColor(self._color)

        if self._hover or self._pressed:
            bg = QColor(swatch_col)
            bg.setAlpha(46 if self._pressed else 30)
            border = QColor(swatch_col)
        else:
            bg = QColor(255, 255, 255, 16)
            border = QColor(255, 255, 255, 38)

        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.1))
        painter.drawRoundedRect(rect, 9.0, 9.0)

        # Glowing color swatch circle
        cy = h / 2.0
        cx = 16.0
        halo = QColor(swatch_col)
        halo.setAlpha(80)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(cx, cy), 9.0, 9.0)

        painter.setBrush(swatch_col)
        painter.setPen(QPen(QColor(255, 255, 255, 150), 1.1))
        painter.drawEllipse(QPointF(cx, cy), 6.5, 6.5)

        # Crisp uppercase hex text
        font = QFont("Consolas")
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(PALETTE["text_primary"]))
        painter.drawText(
            QRectF(28.0, 0.0, w - 34.0, h),
            Qt.AlignmentFlag.AlignCenter,
            self._color.upper(),
        )
        painter.end()


class SettingsDialog(QDialog):
    settings_changed = pyqtSignal()
    _audio_devices_ready = pyqtSignal(object)

    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._host_window = parent
        self._embedded = embedded
        self._devices_populated = False
        self._enumerating_devices = False
        self._is_closed = False
        self._reloading_settings = False
        self._theme_preview_dirty = False
        self._applied_qss_key: Optional[Tuple[Optional[str], Optional[str], bool]] = None
        self._applied_toast_qss_key: Optional[Tuple[Optional[str], Optional[str]]] = None
        self._loaded_station: Optional[str] = None
        self._loaded_backend_name: Optional[str] = None
        self._audio_devices_ready.connect(self._on_audio_devices_enumerated)
        self._device_enum_timer = QTimer(self)
        self._device_enum_timer.setSingleShot(True)
        self._device_enum_timer.timeout.connect(self._ensure_devices_populated)
        self.setObjectName("settingsEmbeddedPanel" if embedded else "settingsDialogRoot")

        if embedded:
            self.setWindowFlags(Qt.WindowType.Widget)
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        else:
            self.setModal(False)
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
            self.setMinimumSize(460, 520)
            self.resize(480, 580)

        self.settings = QSettings(ORG_NAME, APP_SETTINGS)
        self.i18n = I18n(self.settings.value(KEY_LANG, "it"))
        self._loaded_lang: Optional[str] = self.i18n.lang
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
        if embedded:
            hdr_row = QHBoxLayout()
            hdr_row.setContentsMargins(2, 0, 2, 2)
            hdr_row.setSpacing(8)

            self.btn_back = BackToPlayerButton(self.i18n.t("settings_back_to_player"), self)
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
        gen_layout.setContentsMargins(0, 2, 4, 12)
        gen_layout.setSpacing(8)

        card_prefs, prefs_lay = self._make_card(self.i18n.t("settings_radio_prefs_section"))
        self._card_prefs_hdr = self._layout_first_widget(prefs_lay)

        self.cmb_lang = GlassComboBox()
        self.cmb_lang.addItems(["Italiano", "English"])
        self.cmb_lang.setCurrentIndex(0 if self.settings.value(KEY_LANG, "it") == "it" else 1)
        self.cmb_lang.setFixedWidth(combo_w)
        lang_row = self._make_field_row(self.i18n.t("settings_language"), self.cmb_lang)
        self._lbl_lang = self._layout_first_widget(lang_row)
        prefs_lay.addLayout(lang_row)

        self.cmb_station = GlassComboBox()
        for sid in STATIONS:
            self.cmb_station.addItem(get_station_display_name(sid, self.i18n), userData=sid)
        saved_station = str(self.settings.value(KEY_STATION, DEFAULT_STATION))
        for i in range(self.cmb_station.count()):
            if self.cmb_station.itemData(i) == saved_station:
                self.cmb_station.setCurrentIndex(i)
                break
        self.cmb_station.setFixedWidth(combo_w)
        station_row = self._make_field_row(self.i18n.t("settings_station"), self.cmb_station)
        self._lbl_station = self._layout_first_widget(station_row)
        prefs_lay.addLayout(station_row)

        self.cmb_channel = GlassComboBox()
        self.cmb_channel.addItems(["J-POP", "K-POP"])
        self.cmb_channel.setCurrentText(self.settings.value(KEY_CHANNEL, "J-POP"))
        self.cmb_channel.setFixedWidth(combo_w)
        channel_row = self._make_field_row(self.i18n.t("settings_channel"), self.cmb_channel)
        self._lbl_channel = self._layout_first_widget(channel_row)
        prefs_lay.addLayout(channel_row)

        gen_layout.addWidget(card_prefs)

        # ==================== APPEARANCE & THEME CARD (Phase 8) ====================
        card_theme, theme_lay = self._make_card(self.i18n.t("settings_appearance_section"))
        theme_hdr_item = theme_lay.itemAt(0)
        self._card_theme_hdr = theme_hdr_item.widget() if theme_hdr_item is not None else None

        self.cmb_theme = GlassComboBox()
        saved_theme = str(self.settings.value(KEY_THEME, DEFAULT_THEME)).strip().lower()
        if saved_theme not in THEME_PRESETS:
            saved_theme = DEFAULT_THEME
        for idx_t, tid in enumerate(THEME_ORDER):
            self.cmb_theme.addItem(self.i18n.t(THEME_PRESETS[tid]["i18n_key"]), userData=tid)
            if tid == saved_theme:
                self.cmb_theme.setCurrentIndex(idx_t)
        self.cmb_theme.setFixedWidth(combo_w)
        theme_row_lay = self._make_field_row(self.i18n.t("settings_theme"), self.cmb_theme)
        theme_lbl_item = theme_row_lay.itemAt(0)
        self.lbl_theme = theme_lbl_item.widget() if theme_lbl_item is not None else None
        theme_lay.addLayout(theme_row_lay)

        self.chk_custom_accent = AnimatedToggleSwitch(self.i18n.t("settings_custom_accent_enable"))
        self.chk_custom_accent.setChecked(
            self.settings.value(KEY_CUSTOM_ACCENT_ENABLED, "false") == "true"
        )
        theme_lay.addWidget(self.chk_custom_accent)

        raw_saved_accent = str(self.settings.value(KEY_CUSTOM_ACCENT, "") or "").strip()
        self._has_user_custom_accent = is_valid_hex_color(raw_saved_accent)
        initial_swatch_hex = (
            normalize_hex_color(raw_saved_accent)
            if self._has_user_custom_accent
            else get_preset_default_accent(saved_theme)
        )

        self.custom_accent_row = QWidget()
        accent_row_lay = QHBoxLayout(self.custom_accent_row)
        accent_row_lay.setContentsMargins(0, 0, 0, 0)
        accent_row_lay.setSpacing(6)
        self.lbl_custom_accent = QLabel(self.i18n.t("settings_custom_accent_color"))
        self.lbl_custom_accent.setObjectName("settingsFieldLabel")
        accent_row_lay.addWidget(self.lbl_custom_accent)
        accent_row_lay.addStretch(1)

        self.btn_accent_swatch = AccentColorSwatchButton(
            initial_color=initial_swatch_hex,
            dialog_title=self.i18n.t("settings_custom_accent_dialog_title"),
            i18n=self.i18n,
            parent=self.custom_accent_row,
        )
        self.btn_accent_swatch.setToolTip(self.i18n.t("settings_custom_accent_pick"))
        accent_row_lay.addWidget(self.btn_accent_swatch)

        self.btn_accent_reset = QPushButton(self.i18n.t("settings_custom_accent_reset"))
        self.btn_accent_reset.setObjectName("secondaryGlassBtn")
        self.btn_accent_reset.setFixedHeight(30)
        self.btn_accent_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_accent_reset.setToolTip(self.i18n.t("settings_custom_accent_reset_tip"))
        accent_row_lay.addWidget(self.btn_accent_reset)

        self.custom_accent_row.setVisible(self.chk_custom_accent.isChecked())
        theme_lay.addWidget(self.custom_accent_row)

        self.chk_ambient_mode = AnimatedToggleSwitch(self.i18n.t("settings_ambient_mode"))
        def_amb = "true" if DEFAULT_AMBIENT_MODE_ENABLED else "false"
        self.chk_ambient_mode.setChecked(
            self.settings.value(KEY_AMBIENT_MODE_ENABLED, def_amb) == "true"
        )
        self.chk_ambient_mode.setToolTip(self.i18n.t("settings_ambient_mode_tip"))
        theme_lay.addWidget(self.chk_ambient_mode)

        self.chk_visualizer = AnimatedToggleSwitch(self.i18n.t("settings_visualizer"))
        def_viz = "true" if DEFAULT_VISUALIZER_ENABLED else "false"
        self.chk_visualizer.setChecked(
            self.settings.value(KEY_VISUALIZER_ENABLED, def_viz) == "true"
        )
        self.chk_visualizer.setToolTip(self.i18n.t("settings_visualizer_tip"))
        theme_lay.addWidget(self.chk_visualizer)

        self.cmb_theme.currentIndexChanged.connect(self._on_theme_combo_changed)
        self.chk_custom_accent.toggled.connect(self._on_custom_accent_toggled)
        self.chk_ambient_mode.toggled.connect(self._on_ambient_mode_toggled)
        self.chk_visualizer.toggled.connect(self._on_visualizer_toggled)
        self.btn_accent_swatch.color_changed.connect(self._on_custom_accent_color_changed)
        self.btn_accent_reset.clicked.connect(self._on_reset_custom_accent)

        gen_layout.addWidget(card_theme)

        card_play, play_lay = self._make_card(self.i18n.t("settings_playback_section"))
        play_hdr_item = play_lay.itemAt(0)
        self._card_play_hdr = play_hdr_item.widget() if play_hdr_item is not None else None

        self.chk_autoplay = AnimatedToggleSwitch(self.i18n.t("settings_autoplay"))
        self.chk_autoplay.setChecked(self.settings.value(KEY_AUTOPLAY, "false") == "true")
        self.chk_autoplay.setToolTip(self.i18n.t("settings_autoplay_tip"))
        play_lay.addWidget(self.chk_autoplay)

        self.chk_discord_rpc = AnimatedToggleSwitch(self.i18n.t("settings_discord_rpc"))
        self.chk_discord_rpc.setChecked(
            self.settings.value(KEY_DISCORD_RPC_ENABLED, "false") == "true"
        )
        play_lay.addWidget(self.chk_discord_rpc)
        self.txt_discord_client_id = QLineEdit(
            str(self.settings.value(KEY_DISCORD_CLIENT_ID, "") or "").strip()
        )
        self.txt_discord_client_id.setPlaceholderText(
            self.i18n.t("settings_discord_id_placeholder")
        )
        self.txt_discord_client_id.setFixedWidth(combo_w)
        self.txt_discord_client_id.setFixedHeight(30)
        self.discord_id_row = QWidget()
        self.discord_id_row.setFixedHeight(36)
        discord_id_layout = self._make_field_row(
            self.i18n.t("settings_discord_id"), self.txt_discord_client_id
        )
        discord_label_item = discord_id_layout.itemAt(0)
        self.discord_id_label = discord_label_item.widget() if discord_label_item else None
        self.discord_id_row.setLayout(discord_id_layout)
        self.discord_id_row.setVisible(self.chk_discord_rpc.isChecked())
        self.chk_discord_rpc.toggled.connect(self.discord_id_row.setVisible)
        play_lay.addWidget(self.discord_id_row)

        self.chk_show_sleep_timer = AnimatedToggleSwitch(self.i18n.t("settings_show_sleep_timer"))
        self.chk_show_sleep_timer.setToolTip(self.i18n.t("settings_show_sleep_timer_tip"))
        self.chk_show_sleep_timer.setChecked(
            self.settings.value(KEY_SHOW_SLEEP_TIMER, "true") == "true"
        )
        play_lay.addWidget(self.chk_show_sleep_timer)

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

        card_lyrics, lyrics_lay = self._make_card(self.i18n.t("settings_lyrics_section"))
        self._card_lyrics_hdr = self._layout_first_widget(lyrics_lay)

        self._lyrics_provider_items = (
            (LYRICS_PROVIDER_AUTO, "settings_lyrics_provider_auto"),
            (LYRICS_PROVIDER_BETTERLYRICS_FIRST, "settings_lyrics_provider_bl_first"),
            (LYRICS_PROVIDER_LRCLIB, "settings_lyrics_provider_lrclib"),
            (LYRICS_PROVIDER_BETTERLYRICS, "settings_lyrics_provider_betterlyrics"),
        )
        self.cmb_lyrics_provider = GlassComboBox()
        for pid, p_key in self._lyrics_provider_items:
            self.cmb_lyrics_provider.addItem(self.i18n.t(p_key), userData=pid)
        saved_lyrics_provider = str(
            self.settings.value(KEY_LYRICS_PROVIDER, DEFAULT_LYRICS_PROVIDER)
            or DEFAULT_LYRICS_PROVIDER
        )
        for i in range(self.cmb_lyrics_provider.count()):
            if self.cmb_lyrics_provider.itemData(i) == saved_lyrics_provider:
                self.cmb_lyrics_provider.setCurrentIndex(i)
                break
        self.cmb_lyrics_provider.setFixedWidth(combo_w)
        lyrics_prov_row = self._make_field_row(
            self.i18n.t("settings_lyrics_provider"), self.cmb_lyrics_provider
        )
        self._lbl_lyrics_provider = self._layout_first_widget(lyrics_prov_row)
        lyrics_lay.addLayout(lyrics_prov_row)

        self.txt_betterlyrics_api_key = QLineEdit(
            str(self.settings.value(KEY_BETTERLYRICS_API_KEY, "") or "").strip()
        )
        self.txt_betterlyrics_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_betterlyrics_api_key.setPlaceholderText(
            self.i18n.t("settings_betterlyrics_api_key_placeholder")
        )
        self.txt_betterlyrics_api_key.setToolTip(self.i18n.t("settings_betterlyrics_api_key_tip"))
        self.txt_betterlyrics_api_key.setFixedWidth(combo_w)
        self.txt_betterlyrics_api_key.setFixedHeight(30)
        self.betterlyrics_key_row = QWidget()
        self.betterlyrics_key_row.setFixedHeight(36)
        bl_key_layout = self._make_field_row(
            self.i18n.t("settings_betterlyrics_api_key"), self.txt_betterlyrics_api_key
        )
        self._lbl_betterlyrics_api_key = self._layout_first_widget(bl_key_layout)
        self.betterlyrics_key_row.setLayout(bl_key_layout)
        self.betterlyrics_key_row.setVisible(
            self.cmb_lyrics_provider.currentData() != LYRICS_PROVIDER_LRCLIB
        )
        self.cmb_lyrics_provider.currentIndexChanged.connect(
            lambda _idx: self.betterlyrics_key_row.setVisible(
                self.cmb_lyrics_provider.currentData() != LYRICS_PROVIDER_LRCLIB
            )
        )
        lyrics_lay.addWidget(self.betterlyrics_key_row)

        gen_layout.addWidget(card_lyrics)
        gen_layout.addStretch(1)
        self._add_settings_page(page_gen)

        # ==================== PAGE 1: AUDIO & STREAM ====================
        page_audio = QWidget()
        audio_layout = QVBoxLayout(page_audio)
        audio_layout.setContentsMargins(0, 2, 4, 12)
        audio_layout.setSpacing(8)

        card_engine, eng_lay = self._make_card(self.i18n.t("settings_audio_engine_section"))
        self._card_engine_hdr = self._layout_first_widget(eng_lay)

        self.cmb_format = GlassComboBox()
        self.cmb_format.addItems(["Vorbis", "Opus", "MP3"])
        self.cmb_format.setCurrentText(self.settings.value(KEY_FORMAT, "Vorbis"))
        self.cmb_format.setFixedWidth(combo_w)
        fmt_row = self._make_field_row(self.i18n.t("settings_format"), self.cmb_format)
        self._lbl_format = self._layout_first_widget(fmt_row)
        eng_lay.addLayout(fmt_row)

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
        backend_row = self._make_field_row(
            self.i18n.t("settings_audio_backend"), self.cmb_audio_backend
        )
        self._lbl_audio_backend = self._layout_first_widget(backend_row)
        eng_lay.addLayout(backend_row)

        self._lbl_audio_output = QLabel(self.i18n.t("settings_audio_output"))
        self._lbl_audio_output.setObjectName("settingsFieldLabel")
        eng_lay.addWidget(self._lbl_audio_output)

        audio_dev_row = QHBoxLayout()
        audio_dev_row.setContentsMargins(0, 0, 0, 0)
        audio_dev_row.setSpacing(6)
        self.cmb_audio_device = GlassComboBox()
        self.cmb_audio_device.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.cmb_audio_device.setMinimumContentsLength(1)
        self.cmb_audio_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cmb_audio_device.addItem(self.i18n.t("settings_audio_default"), userData=None)
        audio_dev_row.addWidget(self.cmb_audio_device, 1)

        self.btn_audio_refresh = QPushButton(self.i18n.t("settings_audio_refresh"))
        self.btn_audio_refresh.setObjectName("secondaryGlassBtn")
        self.btn_audio_refresh.setIcon(get_refresh_icon(14))
        self.btn_audio_refresh.setIconSize(QSize(14, 14))
        self.btn_audio_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_audio_refresh.clicked.connect(
            lambda: self._populate_audio_devices(async_mode=True, force_refresh=True)
        )
        audio_dev_row.addWidget(self.btn_audio_refresh)
        eng_lay.addLayout(audio_dev_row)

        self.btn_force_audio_reset = QPushButton(self.i18n.t("settings_force_reset_audio_btn"))
        self.btn_force_audio_reset.setObjectName("secondaryGlassBtn")
        self.btn_force_audio_reset.setFixedWidth(combo_w)
        self.btn_force_audio_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_force_audio_reset.setToolTip(self.i18n.t("settings_force_reset_audio_tip"))
        self.btn_force_audio_reset.clicked.connect(self._on_force_audio_reset_clicked)
        force_reset_row = self._make_field_row(
            self.i18n.t("tt_force_stop"), self.btn_force_audio_reset
        )
        self._lbl_force_audio_reset = self._layout_first_widget(force_reset_row)
        eng_lay.addLayout(force_reset_row)

        audio_layout.addWidget(card_engine)

        card_dynvol, dyn_lay = self._make_card(self.i18n.t("settings_dynamic_volume_section"))
        self._card_dynvol_hdr = self._layout_first_widget(dyn_lay)

        self.chk_dynamic_volume = AnimatedToggleSwitch(
            self.i18n.t("settings_dynamic_volume_enable")
        )
        def_dyn_on = "true" if DEFAULT_DYNAMIC_VOLUME_ENABLED else "false"
        self.chk_dynamic_volume.setChecked(
            self.settings.value(KEY_DYNAMIC_VOLUME_ENABLED, def_dyn_on) == "true"
        )
        self.chk_dynamic_volume.setToolTip(self.i18n.t("settings_dynamic_volume_tip"))
        dyn_lay.addWidget(self.chk_dynamic_volume)

        self.dynvol_options_box = QWidget()
        dyn_opts_lay = QVBoxLayout(self.dynvol_options_box)
        dyn_opts_lay.setContentsMargins(0, 4, 0, 2)
        dyn_opts_lay.setSpacing(6)

        self.cmb_dynamic_volume_mode = GlassComboBox()
        self.cmb_dynamic_volume_mode.addItem(
            self.i18n.t("settings_dynamic_volume_mode_any"), userData=DYNAMIC_MODE_ANY_OPEN
        )
        self.cmb_dynamic_volume_mode.addItem(
            self.i18n.t("settings_dynamic_volume_mode_fg"), userData=DYNAMIC_MODE_FOREGROUND
        )
        saved_dyn_mode = str(
            self.settings.value(KEY_DYNAMIC_VOLUME_MODE, DEFAULT_DYNAMIC_VOLUME_MODE)
            or DEFAULT_DYNAMIC_VOLUME_MODE
        )
        for i in range(self.cmb_dynamic_volume_mode.count()):
            if self.cmb_dynamic_volume_mode.itemData(i) == saved_dyn_mode:
                self.cmb_dynamic_volume_mode.setCurrentIndex(i)
                break
        self.cmb_dynamic_volume_mode.setFixedWidth(combo_w)
        dyn_mode_row = self._make_field_row(
            self.i18n.t("settings_dynamic_volume_mode"), self.cmb_dynamic_volume_mode
        )
        self._lbl_dynvol_mode = self._layout_first_widget(dyn_mode_row)
        dyn_opts_lay.addLayout(dyn_mode_row)

        self.spin_dynamic_volume_level = QSpinBox()
        self.spin_dynamic_volume_level.setRange(5, 90)
        self.spin_dynamic_volume_level.setSingleStep(5)
        self.spin_dynamic_volume_level.setSuffix("%")
        self.spin_dynamic_volume_level.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin_dynamic_volume_level.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_dynamic_volume_level.setFixedSize(76, 28)
        self.spin_dynamic_volume_level.setToolTip(self.i18n.t("settings_dynamic_volume_level_tip"))
        try:
            saved_dyn_lvl = int(
                self.settings.value(KEY_DYNAMIC_VOLUME_LEVEL, DEFAULT_DYNAMIC_VOLUME_LEVEL)
            )
        except (TypeError, ValueError):
            saved_dyn_lvl = DEFAULT_DYNAMIC_VOLUME_LEVEL
        self.spin_dynamic_volume_level.setValue(max(5, min(90, saved_dyn_lvl)))

        self.btn_dynvol_minus = QPushButton()
        self.btn_dynvol_minus.setObjectName("stepperBtn")
        self.btn_dynvol_minus.setFixedSize(28, 28)
        self.btn_dynvol_minus.setIcon(get_minus_icon(13))
        self.btn_dynvol_minus.setIconSize(QSize(13, 13))
        self.btn_dynvol_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dynvol_minus.clicked.connect(
            lambda: self.spin_dynamic_volume_level.setValue(
                max(5, self.spin_dynamic_volume_level.value() - 5)
            )
        )

        self.btn_dynvol_plus = QPushButton()
        self.btn_dynvol_plus.setObjectName("stepperBtn")
        self.btn_dynvol_plus.setFixedSize(28, 28)
        self.btn_dynvol_plus.setIcon(get_plus_icon(13))
        self.btn_dynvol_plus.setIconSize(QSize(13, 13))
        self.btn_dynvol_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dynvol_plus.clicked.connect(
            lambda: self.spin_dynamic_volume_level.setValue(
                min(90, self.spin_dynamic_volume_level.value() + 5)
            )
        )

        dyn_lvl_row = QHBoxLayout()
        dyn_lvl_row.setContentsMargins(0, 0, 0, 0)
        dyn_lvl_row.setSpacing(6)
        self._lbl_dynvol_level = QLabel(self.i18n.t("settings_dynamic_volume_level"))
        self._lbl_dynvol_level.setObjectName("settingsFieldLabel")
        dyn_lvl_row.addWidget(self._lbl_dynvol_level)
        dyn_lvl_row.addStretch(1)
        dyn_lvl_row.addWidget(self.btn_dynvol_minus)
        dyn_lvl_row.addWidget(self.spin_dynamic_volume_level)
        dyn_lvl_row.addWidget(self.btn_dynvol_plus)
        dyn_opts_lay.addLayout(dyn_lvl_row)

        self._lbl_dynvol_apps = QLabel(self.i18n.t("settings_dynamic_volume_apps"))
        self._lbl_dynvol_apps.setObjectName("settingsFieldLabel")
        dyn_opts_lay.addWidget(self._lbl_dynvol_apps)

        dyn_apps_row = QHBoxLayout()
        dyn_apps_row.setContentsMargins(0, 0, 0, 0)
        dyn_apps_row.setSpacing(6)
        self.txt_dynamic_volume_apps = QLineEdit(
            str(
                self.settings.value(KEY_DYNAMIC_VOLUME_APPS, DEFAULT_DYNAMIC_VOLUME_APPS)
                or DEFAULT_DYNAMIC_VOLUME_APPS
            ).strip()
        )
        self.txt_dynamic_volume_apps.setPlaceholderText(
            self.i18n.t("settings_dynamic_volume_apps_placeholder")
        )
        self.txt_dynamic_volume_apps.setToolTip(self.i18n.t("settings_dynamic_volume_apps_tip"))
        self.txt_dynamic_volume_apps.setFixedHeight(32)
        dyn_apps_row.addWidget(self.txt_dynamic_volume_apps, 1)

        self.btn_pick_dynamic_app = QPushButton(self.i18n.t("settings_dynamic_volume_pick_app"))
        self.btn_pick_dynamic_app.setObjectName("secondaryGlassBtn")
        self.btn_pick_dynamic_app.setIcon(get_apps_icon(14))
        self.btn_pick_dynamic_app.setIconSize(QSize(14, 14))
        self.btn_pick_dynamic_app.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pick_dynamic_app.clicked.connect(self._on_pick_dynamic_app_clicked)
        dyn_apps_row.addWidget(self.btn_pick_dynamic_app)
        dyn_opts_lay.addLayout(dyn_apps_row)

        self._dynvol_anim: Optional[QVariantAnimation] = None
        self._dynvol_opacity: Optional[QGraphicsOpacityEffect] = None
        self._set_dynvol_options_expanded(self.chk_dynamic_volume.isChecked(), animate=False)
        self.chk_dynamic_volume.toggled.connect(
            lambda checked: self._set_dynvol_options_expanded(checked, animate=True)
        )
        dyn_lay.addWidget(self.dynvol_options_box)

        audio_layout.addWidget(card_dynvol)

        card_net, net_lay = self._make_card(self.i18n.t("settings_network_libvlc_section"))
        net_hdr_item = net_lay.itemAt(0)
        self._card_net_hdr = net_hdr_item.widget() if net_hdr_item is not None else None

        nc_row = QHBoxLayout()
        nc_row.setContentsMargins(0, 0, 0, 0)
        nc_row.setSpacing(6)
        self._lbl_network_caching = QLabel(self.i18n.t("settings_network_caching"))
        self._lbl_network_caching.setObjectName("settingsFieldLabel")
        nc_row.addWidget(self._lbl_network_caching)
        nc_row.addStretch(1)

        btn_nc_minus = QPushButton()
        btn_nc_minus.setObjectName("stepperBtn")
        btn_nc_minus.setFixedSize(28, 28)
        btn_nc_minus.setIcon(get_minus_icon(13))
        btn_nc_minus.setIconSize(QSize(13, 13))
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

        btn_nc_plus = QPushButton()
        btn_nc_plus.setObjectName("stepperBtn")
        btn_nc_plus.setFixedSize(28, 28)
        btn_nc_plus.setIcon(get_plus_icon(13))
        btn_nc_plus.setIconSize(QSize(13, 13))
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

        self._lbl_vlc_path = QLabel(self.i18n.t("settings_vlc_path"))
        self._lbl_vlc_path.setObjectName("settingsFieldLabel")
        net_lay.addWidget(self._lbl_vlc_path)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.setSpacing(6)
        self.txt_vlc_path = QLineEdit(self.settings.value(KEY_LIBVLC_PATH, ""))
        self.txt_vlc_path.setPlaceholderText(self.i18n.t("settings_vlc_path_placeholder"))
        self.txt_vlc_path.setFixedHeight(32)
        path_row.addWidget(self.txt_vlc_path, 1)

        self.btn_browse = QPushButton(self.i18n.t("settings_browse"))
        self.btn_browse.setObjectName("secondaryGlassBtn")
        self.btn_browse.setIcon(get_folder_icon(14, "#e2e6f3"))
        self.btn_browse.setIconSize(QSize(14, 14))
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self._browse_vlc_path)
        path_row.addWidget(self.btn_browse)
        net_lay.addLayout(path_row)

        audio_layout.addWidget(card_net)
        audio_layout.addStretch(1)
        self._add_settings_page(page_audio)

        # ==================== PAGE 2: TRAY & CONSOLE ====================
        page_sys = QWidget()
        sys_layout = QVBoxLayout(page_sys)
        sys_layout.setContentsMargins(0, 2, 4, 12)
        sys_layout.setSpacing(8)

        card_tray, tray_lay = self._make_card(self.i18n.t("settings_tray_section"))
        tray_hdr_item = tray_lay.itemAt(0)
        self._card_tray_hdr = tray_hdr_item.widget() if tray_hdr_item is not None else None

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

        card_dev, dev_lay = self._make_card(self.i18n.t("settings_dev_console_section"))
        dev_hdr_item = dev_lay.itemAt(0)
        self._card_dev_hdr = dev_hdr_item.widget() if dev_hdr_item is not None else None

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

        card_updates, updates_lay = self._make_card(self.i18n.t("updates_section"))
        updates_hdr_item = updates_lay.itemAt(0)
        self._card_updates_hdr = updates_hdr_item.widget() if updates_hdr_item is not None else None

        self.chk_update_startup = AnimatedToggleSwitch(self.i18n.t("updates_startup_check"))
        self.chk_update_startup.setToolTip(self.i18n.t("updates_startup_check_tip"))
        self.chk_update_startup.setChecked(
            self.settings.value(KEY_UPDATE_CHECK_ON_STARTUP, "true") == "true"
        )
        updates_lay.addWidget(self.chk_update_startup)

        self.cmb_update_channel = GlassComboBox()
        self.cmb_update_channel.addItem(
            self.i18n.t("updates_channel_stable"), userData=UPDATE_CHANNEL_STABLE
        )
        self.cmb_update_channel.addItem(
            self.i18n.t("updates_channel_beta"), userData=UPDATE_CHANNEL_BETA
        )
        default_channel = (
            UPDATE_CHANNEL_BETA
            if ("-" in APP_VERSION or "beta" in APP_VERSION.lower())
            else UPDATE_CHANNEL_STABLE
        )
        saved_channel = (
            str(self.settings.value(KEY_UPDATE_CHANNEL, default_channel)).strip().lower()
        )
        if saved_channel == UPDATE_CHANNEL_STABLE:
            self.cmb_update_channel.setCurrentIndex(0)
        else:
            self.cmb_update_channel.setCurrentIndex(1)
        self.cmb_update_channel.setFixedWidth(combo_w)
        update_ch_row = self._make_field_row(
            self.i18n.t("updates_channel_label"), self.cmb_update_channel
        )
        self._lbl_update_channel = self._layout_first_widget(update_ch_row)
        updates_lay.addLayout(update_ch_row)

        btn_update_row = QHBoxLayout()
        btn_update_row.setContentsMargins(0, 4, 0, 0)
        btn_update_row.setSpacing(6)
        self.btn_check_updates = QPushButton(self.i18n.t("updates_check_now"))
        self.btn_check_updates.setObjectName("secondaryGlassBtn")
        self.btn_check_updates.setIcon(get_update_icon(14))
        self.btn_check_updates.setFixedHeight(30)
        self.btn_check_updates.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check_updates.clicked.connect(self._on_check_updates)
        btn_update_row.addWidget(self.btn_check_updates)
        btn_update_row.addStretch(1)
        updates_lay.addLayout(btn_update_row)

        sys_layout.addWidget(card_updates)
        sys_layout.addStretch(1)
        self._add_settings_page(page_sys)

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
        self._add_settings_page(page_about)

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
        self._apply_toast = QLabel(self)
        self._apply_toast.setObjectName("settingsApplyToast")
        self._apply_toast.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._apply_toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_toast_stylesheet()
        self._apply_toast.hide()
        self._toast_effect = QGraphicsOpacityEffect(self._apply_toast)
        self._apply_toast.setGraphicsEffect(self._toast_effect)
        self._toast_animation = QPropertyAnimation(self._toast_effect, b"opacity", self)
        self._toast_animation.setDuration(180)
        self._toast_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._toast_animation.finished.connect(self._on_toast_animation_finished)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._hide_apply_toast)
        if hasattr(self, "cmb_station"):
            self.cmb_station.currentIndexChanged.connect(self._on_settings_station_changed)
            self._on_settings_station_changed()
        self._applied_values = self._settings_values()

    def _ensure_devices_populated(self) -> None:
        if self._is_closed or self._devices_populated or self._enumerating_devices:
            return
        if not self.isVisible():
            return
        # Delay enumeration while either the host view stack or internal tabs are sliding
        host_stack = getattr(self._host_window, "_view_stack", None) or getattr(
            self.parent(), "_view_stack", None
        )
        host_sliding = bool(
            host_stack is not None
            and getattr(host_stack, "_anim_timer", None)
            and host_stack._anim_timer.isActive()
        )
        tabs_sliding = bool(
            hasattr(self, "pages")
            and getattr(self.pages, "_anim_timer", None)
            and self.pages._anim_timer.isActive()
        )
        if host_sliding or tabs_sliding:
            self._device_enum_timer.start(120)
            return
        self._populate_audio_devices(async_mode=True)

    @staticmethod
    def _layout_first_widget(layout: Any) -> Optional[QWidget]:
        """Safely return the first widget inside a Qt layout, or ``None``."""
        item = layout.itemAt(0)
        return item.widget() if item is not None else None

    def _add_settings_page(self, page: QWidget) -> None:
        """Let each settings page scroll independently when space is limited."""
        scroll = QScrollArea()
        scroll.setObjectName("settingsPageScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumSize(0, 0)
        scroll.setWidget(page)
        self.pages.addWidget(scroll)

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
        if idx == 1 and not self._devices_populated and not self._enumerating_devices:
            self._device_enum_timer.start(210)

    def _on_settings_station_changed(self) -> None:
        station_id = str(self.cmb_station.currentData() or DEFAULT_STATION)
        self._loaded_station = station_id
        cfg = get_station_config(station_id)
        has_channels = cfg.get("has_channels", False)
        if hasattr(self, "cmb_channel"):
            self.cmb_channel.setEnabled(has_channels)

        if hasattr(self, "cmb_format"):
            current_fmt = self.cmb_format.currentText()
            formats = cfg.get("formats", ["Vorbis", "Opus", "MP3"])
            self.cmb_format.blockSignals(True)
            self.cmb_format.clear()
            self.cmb_format.addItems(formats)
            if current_fmt in formats:
                self.cmb_format.setCurrentText(current_fmt)
            else:
                self.cmb_format.setCurrentText(cfg.get("default_format", formats[0]))
            self.cmb_format.blockSignals(False)

    def _on_theme_combo_changed(self, _idx: int = 0) -> None:
        if self._reloading_settings:
            return
        tid = str(self.cmb_theme.currentData() or DEFAULT_THEME)
        if not self.chk_custom_accent.isChecked() and not self._has_user_custom_accent:
            self.btn_accent_swatch.set_color(get_preset_default_accent(tid), emit_signal=False)
        self._preview_current_theme()

    def _on_custom_accent_toggled(self, checked: bool) -> None:
        self.custom_accent_row.setVisible(checked)
        if self._reloading_settings:
            return
        self._preview_current_theme()

    def _on_ambient_mode_toggled(self, checked: bool) -> None:
        if self._reloading_settings:
            return
        self.settings.setValue(KEY_AMBIENT_MODE_ENABLED, "true" if checked else "false")
        host = self._host_window or self.window()
        content_widget = getattr(host, "_content_widget", None)
        set_ambient = getattr(content_widget, "set_ambient_enabled", None)
        if callable(set_ambient):
            set_ambient(checked)
        self.settings_changed.emit()

    def _on_visualizer_toggled(self, checked: bool) -> None:
        self.settings.setValue(KEY_VISUALIZER_ENABLED, "true" if checked else "false")
        host = self._host_window or self.window()
        ambient_cover = getattr(host, "ambient_cover", None)
        set_viz = getattr(ambient_cover, "set_visualizer_enabled", None)
        if callable(set_viz):
            set_viz(checked)
        self.settings_changed.emit()

    def _on_custom_accent_color_changed(self, _hex_color: str) -> None:
        if self._reloading_settings:
            return
        self._has_user_custom_accent = True
        self._preview_current_theme()

    def _on_reset_custom_accent(self) -> None:
        tid = str(self.cmb_theme.currentData() or DEFAULT_THEME)
        self._has_user_custom_accent = False
        self.btn_accent_swatch.set_color(get_preset_default_accent(tid), emit_signal=False)
        if not self._reloading_settings:
            self._preview_current_theme()

    def _preview_current_theme(self) -> None:
        if self._reloading_settings:
            return
        theme_id = str(self.cmb_theme.currentData() or DEFAULT_THEME)
        use_custom = self.chk_custom_accent.isChecked()
        custom_hex = self.btn_accent_swatch.color() if use_custom else None
        target_state = resolve_theme_and_accent(theme_id, custom_hex)
        self._theme_preview_dirty = True

        if PALETTE.get("theme_id") == target_state[0] and PALETTE.get("accent") == target_state[1]:
            return

        host = self._host_window
        if host is not None and hasattr(host, "apply_theme"):
            host.apply_theme(
                theme_id=theme_id,
                custom_accent=custom_hex,
                use_custom_accent=use_custom,
            )
            if getattr(host, "_settings_dlg", None) is not self:
                self.refresh_theme()
        else:
            apply_theme_palette(theme_id=theme_id, custom_accent=custom_hex)
            app = QApplication.instance()
            if isinstance(app, QApplication):
                new_qss = get_cyber_moe_stylesheet()
                if app.styleSheet() != new_qss:
                    app.setStyleSheet(new_qss)
            self.refresh_theme()

    def _restore_persisted_theme(self) -> None:
        if not getattr(self, "_theme_preview_dirty", False):
            return
        self._theme_preview_dirty = False
        host = self._host_window
        if host is not None and hasattr(host, "apply_theme"):
            host.apply_theme()
            if getattr(host, "_settings_dlg", None) is not self:
                self.refresh_theme()
        else:
            saved_theme = str(self.settings.value(KEY_THEME, DEFAULT_THEME)).strip().lower()
            saved_custom_on = self.settings.value(KEY_CUSTOM_ACCENT_ENABLED, "false") == "true"
            saved_accent = str(self.settings.value(KEY_CUSTOM_ACCENT, "") or "").strip()
            target_state = resolve_theme_and_accent(
                saved_theme, saved_accent if saved_custom_on else None
            )
            if (
                PALETTE.get("theme_id") == target_state[0]
                and PALETTE.get("accent") == target_state[1]
            ):
                return
            apply_theme_palette(
                theme_id=saved_theme,
                custom_accent=saved_accent if saved_custom_on else None,
            )
            app = QApplication.instance()
            if isinstance(app, QApplication):
                new_qss = get_cyber_moe_stylesheet()
                if app.styleSheet() != new_qss:
                    app.setStyleSheet(new_qss)
            self.refresh_theme()

    def _apply_toast_stylesheet(self) -> None:
        if hasattr(self, "_apply_toast") and self._apply_toast is not None:
            toast_key = (PALETTE.get("theme_id"), PALETTE.get("accent"))
            if getattr(self, "_applied_toast_qss_key", None) == toast_key:
                return
            self._applied_toast_qss_key = toast_key
            self._apply_toast.setStyleSheet(
                f"QLabel#settingsApplyToast {{ background: {PALETTE['bg_surface_elevated']}; "
                f"color: {PALETTE['text_primary']}; border: 1px solid {PALETTE['accent']}; "
                "border-radius: 12px; padding: 10px 18px; font-size: 13px; font-weight: 600; }"
            )

    def refresh_theme(self) -> None:
        self._apply_dialog_stylesheet()
        self._apply_toast_stylesheet()
        if self._title_bar is not None:
            self._title_bar.refresh_theme()
        for cmb in self.findChildren(GlassComboBox):
            cmb.refresh_theme()
        for sw in self.findChildren(AnimatedToggleSwitch):
            sw.update()
        if hasattr(self, "category_bar"):
            self.category_bar.update()
        if hasattr(self, "btn_accent_swatch"):
            self.btn_accent_swatch.update()
        if hasattr(self, "btn_back"):
            self.btn_back.update()
        if hasattr(self, "about_widget"):
            self.about_widget.refresh_theme()
        self.update()

    def reload_from_settings(self) -> None:
        """Fast diff-based non-blocking reload of widget values from QSettings."""
        self._is_closed = False
        self._reloading_settings = True
        self._theme_preview_dirty = False
        try:
            lang = str(self.settings.value(KEY_LANG, "it"))
            lang_changed = lang != getattr(self, "_loaded_lang", None)
            if lang_changed:
                self._loaded_lang = lang
                self.i18n.set_lang(lang)
                self.setWindowTitle(self.i18n.t("settings_title"))
                if self._title_bar is not None:
                    self._title_bar.retranslate(self.i18n)
                    self._title_bar._ver_badge.setText(self.i18n.t("settings_title").upper())
                if hasattr(self, "btn_back"):
                    self.btn_back.setText(self.i18n.t("settings_back_to_player"))
                if hasattr(self, "panel_title_lbl"):
                    self.panel_title_lbl.setText(self.i18n.t("settings_title").upper())

                for hdr_attr, key in (
                    ("_card_prefs_hdr", "settings_radio_prefs_section"),
                    ("_card_theme_hdr", "settings_appearance_section"),
                    ("_card_play_hdr", "settings_playback_section"),
                    ("_card_engine_hdr", "settings_audio_engine_section"),
                    ("_card_dynvol_hdr", "settings_dynamic_volume_section"),
                    ("_card_net_hdr", "settings_network_libvlc_section"),
                    ("_card_tray_hdr", "settings_tray_section"),
                    ("_card_dev_hdr", "settings_dev_console_section"),
                    ("_card_updates_hdr", "updates_section"),
                    ("_card_lyrics_hdr", "settings_lyrics_section"),
                ):
                    hdr_w = getattr(self, hdr_attr, None)
                    if isinstance(hdr_w, QLabel):
                        hdr_w.setText(self.i18n.t(key))

                for lbl_attr, key in (
                    ("_lbl_lang", "settings_language"),
                    ("_lbl_station", "settings_station"),
                    ("_lbl_channel", "settings_channel"),
                    ("lbl_theme", "settings_theme"),
                    ("lbl_custom_accent", "settings_custom_accent_color"),
                    ("discord_id_label", "settings_discord_id"),
                    ("_lbl_format", "settings_format"),
                    ("_lbl_audio_backend", "settings_audio_backend"),
                    ("_lbl_audio_output", "settings_audio_output"),
                    ("_lbl_dynvol_mode", "settings_dynamic_volume_mode"),
                    ("_lbl_dynvol_level", "settings_dynamic_volume_level"),
                    ("_lbl_dynvol_apps", "settings_dynamic_volume_apps"),
                    ("_lbl_network_caching", "settings_network_caching"),
                    ("_lbl_vlc_path", "settings_vlc_path"),
                    ("_lbl_update_channel", "updates_channel_label"),
                    ("_lbl_lyrics_provider", "settings_lyrics_provider"),
                    ("_lbl_betterlyrics_api_key", "settings_betterlyrics_api_key"),
                ):
                    lbl_w = getattr(self, lbl_attr, None)
                    if isinstance(lbl_w, QLabel):
                        lbl_w.setText(self.i18n.t(key))

                for i, tid in enumerate(THEME_ORDER):
                    if i < self.cmb_theme.count():
                        self.cmb_theme.setItemText(i, self.i18n.t(THEME_PRESETS[tid]["i18n_key"]))
                for i in range(self.cmb_station.count()):
                    sid = str(self.cmb_station.itemData(i) or "")
                    if sid:
                        self.cmb_station.setItemText(i, get_station_display_name(sid, self.i18n))
                self.chk_custom_accent.setText(self.i18n.t("settings_custom_accent_enable"))
                self.btn_accent_swatch.setToolTip(self.i18n.t("settings_custom_accent_pick"))
                self.btn_accent_swatch.set_dialog_title(
                    self.i18n.t("settings_custom_accent_dialog_title")
                )
                self.btn_accent_reset.setText(self.i18n.t("settings_custom_accent_reset"))
                self.btn_accent_reset.setToolTip(self.i18n.t("settings_custom_accent_reset_tip"))
                self.chk_ambient_mode.setText(self.i18n.t("settings_ambient_mode"))
                self.chk_ambient_mode.setToolTip(self.i18n.t("settings_ambient_mode_tip"))
                self.chk_visualizer.setText(self.i18n.t("settings_visualizer"))
                self.chk_visualizer.setToolTip(self.i18n.t("settings_visualizer_tip"))

                self.chk_autoplay.setText(self.i18n.t("settings_autoplay"))
                self.chk_autoplay.setToolTip(self.i18n.t("settings_autoplay_tip"))
                self.chk_discord_rpc.setText(self.i18n.t("settings_discord_rpc"))
                self.txt_discord_client_id.setPlaceholderText(
                    self.i18n.t("settings_discord_id_placeholder")
                )
                self.chk_show_sleep_timer.setText(self.i18n.t("settings_show_sleep_timer"))
                self.chk_show_sleep_timer.setToolTip(self.i18n.t("settings_show_sleep_timer_tip"))
                self.chk_sleep_stop.setText(self.i18n.t("settings_sleep_stop_on_end"))
                self.chk_session_timer.setText(self.i18n.t("settings_session_timer_enable"))
                self.chk_session_timer.setToolTip(self.i18n.t("settings_session_timer_tip"))
                for i, (_pid, p_key) in enumerate(self._lyrics_provider_items):
                    if i < self.cmb_lyrics_provider.count():
                        self.cmb_lyrics_provider.setItemText(i, self.i18n.t(p_key))
                self.txt_betterlyrics_api_key.setPlaceholderText(
                    self.i18n.t("settings_betterlyrics_api_key_placeholder")
                )
                self.txt_betterlyrics_api_key.setToolTip(
                    self.i18n.t("settings_betterlyrics_api_key_tip")
                )

                for i, backend_key in enumerate(
                    (
                        "settings_audio_backend_auto",
                        "settings_audio_backend_ffmpeg",
                        "settings_audio_backend_mpv",
                        "settings_audio_backend_vlc",
                    )
                ):
                    if i < self.cmb_audio_backend.count():
                        self.cmb_audio_backend.setItemText(i, self.i18n.t(backend_key))
                if self.cmb_audio_device.count() > 0 and self.cmb_audio_device.itemData(0) is None:
                    self.cmb_audio_device.setItemText(0, self.i18n.t("settings_audio_default"))
                self.btn_audio_refresh.setText(self.i18n.t("settings_audio_refresh"))
                if isinstance(self._lbl_force_audio_reset, QLabel):
                    self._lbl_force_audio_reset.setText(self.i18n.t("tt_force_stop"))
                self.btn_force_audio_reset.setText(self.i18n.t("settings_force_reset_audio_btn"))
                self.btn_force_audio_reset.setToolTip(self.i18n.t("settings_force_reset_audio_tip"))
                if hasattr(self, "chk_dynamic_volume"):
                    self.chk_dynamic_volume.setText(self.i18n.t("settings_dynamic_volume_enable"))
                    self.chk_dynamic_volume.setToolTip(self.i18n.t("settings_dynamic_volume_tip"))
                    for i, mode_key in enumerate(
                        ("settings_dynamic_volume_mode_any", "settings_dynamic_volume_mode_fg")
                    ):
                        if i < self.cmb_dynamic_volume_mode.count():
                            self.cmb_dynamic_volume_mode.setItemText(i, self.i18n.t(mode_key))
                    self.spin_dynamic_volume_level.setToolTip(
                        self.i18n.t("settings_dynamic_volume_level_tip")
                    )
                    self.txt_dynamic_volume_apps.setPlaceholderText(
                        self.i18n.t("settings_dynamic_volume_apps_placeholder")
                    )
                    self.txt_dynamic_volume_apps.setToolTip(
                        self.i18n.t("settings_dynamic_volume_apps_tip")
                    )
                    self.btn_pick_dynamic_app.setText(
                        self.i18n.t("settings_dynamic_volume_pick_app")
                    )
                self.txt_vlc_path.setPlaceholderText(self.i18n.t("settings_vlc_path_placeholder"))
                self.btn_browse.setText(self.i18n.t("settings_browse"))

                self.chk_tray_enabled.setText(self.i18n.t("settings_tray_enable"))
                self.chk_tray_hide_on_minimize.setText(
                    self.i18n.t("settings_tray_hide_on_minimize")
                )
                self.chk_tray_notifications.setText(self.i18n.t("settings_tray_notifications"))
                self.chk_dev_console.setText(self.i18n.t("settings_dev_console"))
                self.btn_open_console.setText(self.i18n.t("dev_console_button"))
                self.chk_dev_show_dev.setText(self.i18n.t("settings_dev_console_show_dev"))

                self.chk_update_startup.setText(self.i18n.t("updates_startup_check"))
                self.chk_update_startup.setToolTip(self.i18n.t("updates_startup_check_tip"))
                for i, ch_key in enumerate(("updates_channel_stable", "updates_channel_beta")):
                    if i < self.cmb_update_channel.count():
                        self.cmb_update_channel.setItemText(i, self.i18n.t(ch_key))
                self.btn_check_updates.setText(self.i18n.t("updates_check_now"))

                self.btn_cancel.setText(self.i18n.t("settings_cancel"))
                self.btn_apply.setText(self.i18n.t("settings_apply"))
                self.btn_ok.setText(self.i18n.t("settings_ok"))

                tab_labels = [
                    self.i18n.t("settings_tab_general"),
                    self.i18n.t("settings_tab_audio"),
                    self.i18n.t("settings_tab_advanced"),
                    self.i18n.t("settings_tab_info"),
                ]
                self.category_bar.set_labels(tab_labels)
                if hasattr(self, "about_widget"):
                    self.about_widget.set_i18n(self.i18n)

            saved_theme = str(self.settings.value(KEY_THEME, DEFAULT_THEME)).strip().lower()
            if saved_theme not in THEME_PRESETS:
                saved_theme = DEFAULT_THEME
            for i in range(self.cmb_theme.count()):
                if self.cmb_theme.itemData(i) == saved_theme:
                    if self.cmb_theme.currentIndex() != i:
                        self.cmb_theme.setCurrentIndex(i)
                    break
            custom_on = self.settings.value(KEY_CUSTOM_ACCENT_ENABLED, "false") == "true"
            if self.chk_custom_accent.isChecked() != custom_on:
                self.chk_custom_accent.setChecked(custom_on)
            self.custom_accent_row.setVisible(custom_on)
            raw_saved_accent = str(self.settings.value(KEY_CUSTOM_ACCENT, "") or "").strip()
            self._has_user_custom_accent = is_valid_hex_color(raw_saved_accent)
            swatch_hex = (
                normalize_hex_color(raw_saved_accent)
                if self._has_user_custom_accent
                else get_preset_default_accent(saved_theme)
            )
            self.btn_accent_swatch.set_color(swatch_hex, emit_signal=False)
            def_amb = "true" if DEFAULT_AMBIENT_MODE_ENABLED else "false"
            self.chk_ambient_mode.setChecked(
                self.settings.value(KEY_AMBIENT_MODE_ENABLED, def_amb) == "true"
            )
            if hasattr(self, "chk_visualizer"):
                def_vis = "true" if DEFAULT_VISUALIZER_ENABLED else "false"
                self.chk_visualizer.blockSignals(True)
                self.chk_visualizer.setChecked(
                    self.settings.value(KEY_VISUALIZER_ENABLED, def_vis) == "true"
                )
                self.chk_visualizer.blockSignals(False)

            target_lang_idx = 0 if lang == "it" else 1
            if self.cmb_lang.currentIndex() != target_lang_idx:
                self.cmb_lang.setCurrentIndex(target_lang_idx)
            saved_station = str(self.settings.value(KEY_STATION, DEFAULT_STATION))
            for i in range(self.cmb_station.count()):
                if self.cmb_station.itemData(i) == saved_station:
                    if self.cmb_station.currentIndex() != i:
                        self.cmb_station.setCurrentIndex(i)
                    break
            if saved_station != getattr(self, "_loaded_station", None):
                self._on_settings_station_changed()
            self.cmb_channel.setCurrentText(str(self.settings.value(KEY_CHANNEL, "J-POP")))
            self.cmb_format.setCurrentText(str(self.settings.value(KEY_FORMAT, "Vorbis")))
            self.txt_vlc_path.setText(str(self.settings.value(KEY_LIBVLC_PATH, "") or ""))
            try:
                self.spin_network_caching.setValue(
                    int(self.settings.value(KEY_NETWORK_CACHING, 1000))
                )
            except (TypeError, ValueError):
                self.spin_network_caching.setValue(1000)
            if self._devices_populated:
                saved_device = self.settings.value(KEY_AUDIO_DEVICE_INDEX, "")
                try:
                    device_index = self.cmb_audio_device.findData(int(saved_device))
                except (TypeError, ValueError):
                    device_index = 0
                self.cmb_audio_device.setCurrentIndex(max(0, device_index))
            saved_backend = self.settings.value(KEY_AUDIO_BACKEND, "auto")
            for i in range(self.cmb_audio_backend.count()):
                if self.cmb_audio_backend.itemData(i) == saved_backend:
                    if self.cmb_audio_backend.currentIndex() != i:
                        self.cmb_audio_backend.setCurrentIndex(i)
                    break
            if hasattr(self, "chk_dynamic_volume"):
                def_dyn_on = "true" if DEFAULT_DYNAMIC_VOLUME_ENABLED else "false"
                dyn_on = self.settings.value(KEY_DYNAMIC_VOLUME_ENABLED, def_dyn_on) == "true"
                self.chk_dynamic_volume.blockSignals(True)
                self.chk_dynamic_volume.setChecked(dyn_on)
                self.chk_dynamic_volume.blockSignals(False)
                self._set_dynvol_options_expanded(dyn_on, animate=False)
                saved_dyn_mode = str(
                    self.settings.value(KEY_DYNAMIC_VOLUME_MODE, DEFAULT_DYNAMIC_VOLUME_MODE)
                    or DEFAULT_DYNAMIC_VOLUME_MODE
                )
                for i in range(self.cmb_dynamic_volume_mode.count()):
                    if self.cmb_dynamic_volume_mode.itemData(i) == saved_dyn_mode:
                        if self.cmb_dynamic_volume_mode.currentIndex() != i:
                            self.cmb_dynamic_volume_mode.setCurrentIndex(i)
                        break
                try:
                    saved_dyn_lvl = int(
                        self.settings.value(KEY_DYNAMIC_VOLUME_LEVEL, DEFAULT_DYNAMIC_VOLUME_LEVEL)
                    )
                except (TypeError, ValueError):
                    saved_dyn_lvl = DEFAULT_DYNAMIC_VOLUME_LEVEL
                self.spin_dynamic_volume_level.setValue(max(5, min(90, saved_dyn_lvl)))
                self.txt_dynamic_volume_apps.setText(
                    str(
                        self.settings.value(KEY_DYNAMIC_VOLUME_APPS, DEFAULT_DYNAMIC_VOLUME_APPS)
                        or DEFAULT_DYNAMIC_VOLUME_APPS
                    ).strip()
                )
            self.chk_autoplay.setChecked(self.settings.value(KEY_AUTOPLAY, "false") == "true")
            self.chk_discord_rpc.setChecked(
                self.settings.value(KEY_DISCORD_RPC_ENABLED, "false") == "true"
            )
            self.txt_discord_client_id.setText(str(self.settings.value(KEY_DISCORD_CLIENT_ID, "")))
            self.chk_show_sleep_timer.setChecked(
                self.settings.value(KEY_SHOW_SLEEP_TIMER, "true") == "true"
            )
            self.chk_sleep_stop.setChecked(
                self.settings.value(KEY_SLEEP_STOP_ON_END, "true") == "true"
            )
            self.chk_session_timer.setChecked(
                self.settings.value(KEY_SESSION_TIMER_ENABLED, "true") == "true"
            )
            if hasattr(self, "cmb_lyrics_provider"):
                saved_lp = str(
                    self.settings.value(KEY_LYRICS_PROVIDER, DEFAULT_LYRICS_PROVIDER)
                    or DEFAULT_LYRICS_PROVIDER
                )
                for i in range(self.cmb_lyrics_provider.count()):
                    if self.cmb_lyrics_provider.itemData(i) == saved_lp:
                        if self.cmb_lyrics_provider.currentIndex() != i:
                            self.cmb_lyrics_provider.setCurrentIndex(i)
                        break
                self.txt_betterlyrics_api_key.setText(
                    str(self.settings.value(KEY_BETTERLYRICS_API_KEY, "") or "").strip()
                )
                self.betterlyrics_key_row.setVisible(
                    self.cmb_lyrics_provider.currentData() != LYRICS_PROVIDER_LRCLIB
                )
            self.chk_tray_enabled.setChecked(
                self.settings.value(KEY_TRAY_ENABLED, "true") == "true"
            )
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
            if hasattr(self, "chk_update_startup"):
                self.chk_update_startup.setChecked(
                    self.settings.value(KEY_UPDATE_CHECK_ON_STARTUP, "true") == "true"
                )
            if hasattr(self, "cmb_update_channel"):
                default_channel = (
                    UPDATE_CHANNEL_BETA
                    if ("-" in APP_VERSION or "beta" in APP_VERSION.lower())
                    else UPDATE_CHANNEL_STABLE
                )
                saved_upd_ch = (
                    str(self.settings.value(KEY_UPDATE_CHANNEL, default_channel)).strip().lower()
                )
                for i in range(self.cmb_update_channel.count()):
                    if self.cmb_update_channel.itemData(i) == saved_upd_ch:
                        if self.cmb_update_channel.currentIndex() != i:
                            self.cmb_update_channel.setCurrentIndex(i)
                        break
            if not self._devices_populated and not self._enumerating_devices:
                self._device_enum_timer.start(250)
            if (
                hasattr(self, "about_widget")
                and self._host_window is not None
                and hasattr(self._host_window, "player")
            ):
                be = (
                    getattr(
                        self._host_window.player,
                        "BACKEND_NAME",
                        type(self._host_window.player).__name__.replace("Player", ""),
                    )
                    if self._host_window.player
                    else "Auto"
                )
                if be != getattr(self, "_loaded_backend_name", None):
                    self._loaded_backend_name = be
                    self.about_widget.set_backend_name(be)
        finally:
            self._reloading_settings = False
        self._applied_values = self._settings_values()

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
        app = QApplication.instance()
        include_base = not (
            self._embedded and isinstance(app, QApplication) and bool(app.styleSheet())
        )
        qss_key = (PALETTE.get("theme_id"), PALETTE.get("accent"), include_base)
        if getattr(self, "_applied_qss_key", None) == qss_key:
            return
        self._applied_qss_key = qss_key

        extra_qss = f"""
        QDialog#settingsDialogRoot {{
            background-color: {PALETTE["bg_dialog"]};
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 12px;
        }}
        QDialog#settingsEmbeddedPanel {{
            background-color: {PALETTE["bg_embedded_panel"]};
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 16px;
        }}
        QFrame#settingsCard {{
            background-color: {PALETTE["bg_surface"]};
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-top: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 13px;
        }}
        QScrollArea#settingsPageScroll, QScrollArea#settingsPageScroll > QWidget > QWidget {{
            background: transparent;
            border: none;
        }}
        QFrame#settingsFooterDeck {{
            background-color: {PALETTE["bg_footer"]};
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
            color: {PALETTE["text_primary"]};
            font-size: 13px;
            font-weight: 500;
            background: transparent;
            border: none;
            padding-left: 2px;
        }}
        QLineEdit {{
            background-color: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 8px;
            padding: 4px 10px;
            color: {PALETTE["text_primary"]};
            font-size: 13px;
            font-weight: 600;
            min-height: 22px;
        }}
        QSpinBox {{
            background-color: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 8px;
            padding: 2px 4px;
            color: {PALETTE["text_primary"]};
            font-size: 13px;
            font-weight: 600;
            min-height: 22px;
        }}
        QLineEdit:hover, QSpinBox:hover,
        QLineEdit:focus, QSpinBox:focus {{
            border-color: {PALETTE["accent"]};
            background-color: {PALETTE["accent_focus_bg"]};
        }}
        QPushButton#primaryActionBtn {{
            background-color: {PALETTE["accent"]};
            color: {PALETTE["on_accent"]};
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
            color: {PALETTE["text_primary"]};
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 9px;
            padding: 4px 11px;
            font-size: 12px;
            font-weight: 700;
        }}
        QPushButton#secondaryGlassBtn:hover {{
            background-color: {PALETTE["accent_soft"]};
            border-color: {PALETTE["accent"]};
            color: #ffffff;
        }}
        QPushButton#neutralActionBtn {{
            background-color: rgba(255, 255, 255, 0.04);
            color: {PALETTE["text_secondary"]};
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
            background-color: {PALETTE["accent_menu_hover"]};
            border-color: {PALETTE["accent"]};
            color: #ffffff;
        }}
        """
        full_qss = (
            get_cyber_moe_stylesheet(PALETTE["accent"]) + extra_qss if include_base else extra_qss
        )
        self.setStyleSheet(full_qss)

    def _browse_vlc_path(self):
        start_dir = self.txt_vlc_path.text().strip() or self.settings.value(KEY_LIBVLC_PATH, None)
        if not start_dir:
            start_dir = "C:/" if _IS_WIN32 else os.path.expanduser("~")
        chosen = get_existing_directory(self, self.i18n.t("libvlc_choose_title"), start_dir)
        if chosen:
            self.txt_vlc_path.setText(chosen)

    def _on_check_updates(self) -> None:
        self.btn_check_updates.setEnabled(False)
        self.btn_check_updates.setText(self.i18n.t("updates_checking"))

        channel = self.cmb_update_channel.currentData() or UPDATE_CHANNEL_BETA
        self._update_worker = UpdateCheckWorker(
            current_version=APP_VERSION,
            channel=channel,
            parent=self,
        )

        def _on_found(release):
            self.btn_check_updates.setEnabled(True)
            self.btn_check_updates.setText(self.i18n.t("updates_check_now"))
            dlg = UpdateDialog(release, parent=self.window(), i18n=self.i18n)
            dlg.exec()

        def _on_up_to_date(_v):
            self.btn_check_updates.setEnabled(True)
            self.btn_check_updates.setText(self.i18n.t("updates_check_now"))
            self._show_apply_toast("updates_up_to_date")

        def _on_failed(err):
            self.btn_check_updates.setEnabled(True)
            self.btn_check_updates.setText(self.i18n.t("updates_check_now"))
            self._show_apply_toast("updates_error")

        self._update_worker.update_available.connect(_on_found)
        self._update_worker.up_to_date.connect(_on_up_to_date)
        self._update_worker.check_failed.connect(_on_failed)
        self._update_worker.start()

    def _on_apply(self):
        """Salva i valori senza chiudere il pannello."""
        values = self._settings_values()
        if values == self._applied_values:
            self._show_apply_toast("settings_unchanged")
            return
        self._save_settings()
        self._applied_values = values
        try:
            self.settings_changed.emit()
        except Exception:
            pass
        self._show_apply_toast("settings_saved")

    def _settings_values(self) -> dict:
        return {
            "theme": self.cmb_theme.currentData() or DEFAULT_THEME,
            "custom_accent_enabled": self.chk_custom_accent.isChecked(),
            "custom_accent": self.btn_accent_swatch.color(),
            "ambient_mode": (
                self.chk_ambient_mode.isChecked() if hasattr(self, "chk_ambient_mode") else True
            ),
            "visualizer": (
                self.chk_visualizer.isChecked() if hasattr(self, "chk_visualizer") else True
            ),
            "autoplay": self.chk_autoplay.isChecked(),
            "discord_rpc": self.chk_discord_rpc.isChecked(),
            "discord_id": self.txt_discord_client_id.text().strip(),
            "show_sleep_timer": self.chk_show_sleep_timer.isChecked(),
            "sleep_stop": self.chk_sleep_stop.isChecked(),
            "session_timer": self.chk_session_timer.isChecked(),
            "lyrics_provider": (
                self.cmb_lyrics_provider.currentData() or DEFAULT_LYRICS_PROVIDER
                if hasattr(self, "cmb_lyrics_provider")
                else DEFAULT_LYRICS_PROVIDER
            ),
            "betterlyrics_api_key": (
                self.txt_betterlyrics_api_key.text().strip()
                if hasattr(self, "txt_betterlyrics_api_key")
                else ""
            ),
            "dev_console": self.chk_dev_console.isChecked(),
            "dev_show": self.chk_dev_show_dev.isChecked(),
            "language": self.cmb_lang.currentIndex(),
            "station": self.cmb_station.currentData() or DEFAULT_STATION,
            "channel": self.cmb_channel.currentText(),
            "format": self.cmb_format.currentText(),
            "vlc_path": self.txt_vlc_path.text().strip(),
            "network_caching": self.spin_network_caching.value(),
            "tray": self.chk_tray_enabled.isChecked(),
            "tray_hide": self.chk_tray_hide_on_minimize.isChecked(),
            "tray_notifications": self.chk_tray_notifications.isChecked(),
            "audio_backend": self.cmb_audio_backend.currentData() or "auto",
            "audio_device": self.cmb_audio_device.currentData(),
            "dynamic_volume_enabled": (
                self.chk_dynamic_volume.isChecked()
                if hasattr(self, "chk_dynamic_volume")
                else DEFAULT_DYNAMIC_VOLUME_ENABLED
            ),
            "dynamic_volume_mode": (
                self.cmb_dynamic_volume_mode.currentData()
                if hasattr(self, "cmb_dynamic_volume_mode")
                else DEFAULT_DYNAMIC_VOLUME_MODE
            ),
            "dynamic_volume_level": (
                self.spin_dynamic_volume_level.value()
                if hasattr(self, "spin_dynamic_volume_level")
                else DEFAULT_DYNAMIC_VOLUME_LEVEL
            ),
            "dynamic_volume_apps": (
                self.txt_dynamic_volume_apps.text().strip()
                if hasattr(self, "txt_dynamic_volume_apps")
                else DEFAULT_DYNAMIC_VOLUME_APPS
            ),
            "update_startup": (
                self.chk_update_startup.isChecked() if hasattr(self, "chk_update_startup") else True
            ),
            "update_channel": (
                self.cmb_update_channel.currentData()
                if hasattr(self, "cmb_update_channel")
                else UPDATE_CHANNEL_BETA
            ),
        }

    def _position_apply_toast(self) -> None:
        self._apply_toast.move(
            (self.width() - self._apply_toast.width()) // 2,
            (self.height() - self._apply_toast.height()) // 2,
        )

    def _show_apply_toast(self, message_key: str) -> None:
        lang = "it" if self.cmb_lang.currentIndex() == 0 else "en"
        self._apply_toast.setText(I18n(lang).t(message_key))
        self._apply_toast.adjustSize()
        self._position_apply_toast()
        self._toast_timer.stop()
        self._toast_animation.stop()
        self._toast_effect.setOpacity(0.0)
        self._apply_toast.show()
        self._apply_toast.raise_()
        self._toast_animation.setStartValue(0.0)
        self._toast_animation.setEndValue(1.0)
        self._toast_animation.start()
        self._toast_timer.start(1800)

    def _hide_apply_toast(self) -> None:
        self._toast_animation.stop()
        self._toast_animation.setStartValue(self._toast_effect.opacity())
        self._toast_animation.setEndValue(0.0)
        self._toast_animation.start()

    def _on_toast_animation_finished(self) -> None:
        if self._toast_effect.opacity() <= 0.0:
            self._apply_toast.hide()

    def resizeEvent(self, a0: Optional[QResizeEvent]) -> None:
        super().resizeEvent(a0)
        if hasattr(self, "_apply_toast"):
            self._position_apply_toast()

    def _on_ok(self):
        """Salva i valori e chiude il pannello."""
        self._save_settings()
        self.accept()

    def accept(self) -> None:
        self._device_enum_timer.stop()
        self._accepted_close = True
        if hasattr(self, "btn_back"):
            self.btn_back.reset_state()
        if self._embedded:
            self.accepted.emit()
        else:
            super().accept()

    def reject(self) -> None:
        self._device_enum_timer.stop()
        self._restore_persisted_theme()
        if hasattr(self, "btn_back"):
            self.btn_back.reset_state()
        if self._embedded:
            self.rejected.emit()
        else:
            super().reject()

    def closeEvent(self, a0: Optional[QCloseEvent]) -> None:
        self._is_closed = True
        self._device_enum_timer.stop()
        if hasattr(self, "btn_back"):
            self.btn_back.reset_state()
        if not getattr(self, "_accepted_close", False):
            self._restore_persisted_theme()
        self._accepted_close = False
        if self._embedded:
            if a0 is not None:
                a0.accept()
            self.hide()
            return
        super().closeEvent(a0)

    def _set_dynvol_options_expanded(self, expanded: bool, animate: bool = True) -> None:
        if not hasattr(self, "dynvol_options_box"):
            return
        box = self.dynvol_options_box
        prev_anim = getattr(self, "_dynvol_anim", None)
        if prev_anim is not None:
            try:
                prev_anim.stop()
                prev_anim.deleteLater()
            except Exception:
                pass
            self._dynvol_anim = None

        lay = box.layout()
        target_h = lay.sizeHint().height() if lay is not None else box.sizeHint().height()
        target_h = max(target_h, box.sizeHint().height(), 134)

        if not animate:
            box.setGraphicsEffect(None)
            self._dynvol_opacity = None
            box.setMaximumHeight(16777215 if expanded else 0)
            box.setVisible(expanded)
            return

        effect = box.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(box)
            box.setGraphicsEffect(effect)
        self._dynvol_opacity = effect

        if expanded:
            start_h = box.height() if box.isVisible() else 0
            box.setMaximumHeight(start_h)
            effect.setOpacity(0.0 if start_h == 0 else effect.opacity())
            box.setVisible(True)
            start_p, end_p = 0.0, 1.0
        else:
            start_h = box.height() if box.isVisible() else target_h
            box.setMaximumHeight(start_h)
            effect.setOpacity(1.0)
            start_p, end_p = 1.0, 0.0

        anim = QVariantAnimation(self)
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(start_p)
        anim.setEndValue(end_p)

        def _on_step(val: object) -> None:
            p = float(val) if isinstance(val, (int, float)) else 1.0
            box.setMaximumHeight(max(0, int(round(target_h * p))))
            effect.setOpacity(max(0.0, min(1.0, p)))

        def _on_done() -> None:
            self._dynvol_anim = None
            box.setGraphicsEffect(None)
            self._dynvol_opacity = None
            if expanded:
                box.setMaximumHeight(16777215)
                box.setVisible(True)
            else:
                box.setMaximumHeight(0)
                box.setVisible(False)

        anim.valueChanged.connect(_on_step)
        anim.finished.connect(_on_done)
        self._dynvol_anim = anim
        anim.start()

    def _on_pick_dynamic_app_clicked(self) -> None:
        if not hasattr(self, "txt_dynamic_volume_apps") or not hasattr(
            self, "btn_pick_dynamic_app"
        ):
            return
        prev_popup = getattr(self, "_dynamic_app_popup", None)
        if prev_popup is not None:
            try:
                prev_popup.close()
                prev_popup.deleteLater()
            except Exception:
                pass

        existing = parse_app_list(self.txt_dynamic_volume_apps.text())
        candidates = list_suggested_running_apps(exclude_names=existing)

        popup = QFrame(
            self,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup_lay = QVBoxLayout(popup)
        popup_lay.setContentsMargins(0, 0, 0, 0)
        popup_lay.setSpacing(0)

        list_w = QListWidget(popup)
        list_w.setObjectName("dynamicAppPickerList")
        list_w.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        list_w.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_w.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        list_w.setTextElideMode(Qt.TextElideMode.ElideRight)
        list_w.setUniformItemSizes(True)
        list_w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        list_w.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {PALETTE["bg_popover"]};
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 10px;
                padding: 5px;
                color: {PALETTE["text_primary"]};
                font-size: 9pt;
                font-weight: 500;
                outline: none;
            }}
            QListWidget::item {{
                min-height: 28px;
                padding: 3px 12px;
                border-radius: 7px;
                border: 1px solid transparent;
                color: {PALETTE["text_secondary"]};
            }}
            QListWidget::item:hover {{
                background-color: rgba(255, 255, 255, 0.09);
                border: 1px solid rgba(255, 255, 255, 0.16);
                color: #ffffff;
            }}
            QListWidget::item:disabled {{
                color: {PALETTE["text_muted"]};
                background: transparent;
                border-color: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 4px 2px 4px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.22);
                border-radius: 3px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(255, 255, 255, 0.36);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                height: 0px;
                background: transparent;
            }}
            """
        )

        if not candidates:
            empty_item = QListWidgetItem(self.i18n.t("settings_dynamic_volume_no_apps"))
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            empty_item.setSizeHint(QSize(0, 32))
            list_w.addItem(empty_item)
        else:
            for app_name in candidates:
                item = QListWidgetItem(app_name)
                item.setData(Qt.ItemDataRole.UserRole, app_name)
                item.setSizeHint(QSize(0, 30))
                list_w.addItem(item)

        def _pick_item(clicked_item: QListWidgetItem) -> None:
            if not (clicked_item.flags() & Qt.ItemFlag.ItemIsEnabled):
                return
            picked = str(clicked_item.data(Qt.ItemDataRole.UserRole) or "").strip()
            if picked:
                cur_existing = parse_app_list(self.txt_dynamic_volume_apps.text())
                updated = parse_app_list(
                    f"{self.txt_dynamic_volume_apps.text()}, {picked}" if cur_existing else picked
                )
                self.txt_dynamic_volume_apps.setText(", ".join(updated))
            popup.close()

        list_w.itemClicked.connect(_pick_item)
        popup_lay.addWidget(list_w)

        row_count = max(1, list_w.count())
        max_popup_h = 236
        content_h = row_count * (32 if not candidates else 30) + 12
        popup_h = min(max_popup_h, max(44, content_h))
        popup_w = max(230, min(320, self.btn_pick_dynamic_app.width() + 56))
        popup.resize(popup_w, popup_h)

        anchor = self.btn_pick_dynamic_app.mapToGlobal(
            QPoint(0, self.btn_pick_dynamic_app.height())
        )
        pos_x = anchor.x() + self.btn_pick_dynamic_app.width() - popup_w
        pos_y = anchor.y() + 4
        screen = self.btn_pick_dynamic_app.screen() or QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            if pos_y + popup_h > avail.bottom():
                above_y = self.btn_pick_dynamic_app.mapToGlobal(QPoint(0, 0)).y() - popup_h - 4
                if above_y >= avail.top():
                    pos_y = above_y
            pos_x = max(avail.left() + 4, min(pos_x, avail.right() - popup_w - 4))
            pos_y = max(avail.top() + 4, min(pos_y, avail.bottom() - popup_h - 4))

        self._dynamic_app_popup = popup
        popup.move(pos_x, pos_y)
        popup.show()

    def _on_force_audio_reset_clicked(self) -> None:
        host = self._host_window or self.window()
        if host is not None:
            reset_fn = getattr(host, "force_stop_all", None)
            if callable(reset_fn):
                reset_fn()
        self._show_apply_toast("settings_force_reset_audio_done")

    def _on_open_console(self):
        try:
            self._save_settings()
            host = self._host_window or self.window()
            if host is not None:
                open_console = getattr(host, "open_dev_console", None)
                if callable(open_console):
                    try:
                        open_console(host)
                    except TypeError:
                        open_console()
        except Exception:
            pass

    def _save_settings(self):
        """Logica comune per salvare le impostazioni."""
        self.settings.setValue(KEY_THEME, self.cmb_theme.currentData() or DEFAULT_THEME)
        self.settings.setValue(
            KEY_CUSTOM_ACCENT_ENABLED,
            "true" if self.chk_custom_accent.isChecked() else "false",
        )
        self.settings.setValue(KEY_CUSTOM_ACCENT, self.btn_accent_swatch.color())
        if hasattr(self, "chk_ambient_mode"):
            self.settings.setValue(
                KEY_AMBIENT_MODE_ENABLED, "true" if self.chk_ambient_mode.isChecked() else "false"
            )
        if hasattr(self, "chk_visualizer"):
            self.settings.setValue(
                KEY_VISUALIZER_ENABLED, "true" if self.chk_visualizer.isChecked() else "false"
            )
        self.settings.setValue(KEY_AUTOPLAY, "true" if self.chk_autoplay.isChecked() else "false")
        self.settings.setValue(
            KEY_DISCORD_RPC_ENABLED, "true" if self.chk_discord_rpc.isChecked() else "false"
        )
        self.settings.setValue(KEY_DISCORD_CLIENT_ID, self.txt_discord_client_id.text().strip())
        self.settings.setValue(
            KEY_SHOW_SLEEP_TIMER, "true" if self.chk_show_sleep_timer.isChecked() else "false"
        )
        self.settings.setValue(
            KEY_SLEEP_STOP_ON_END, "true" if self.chk_sleep_stop.isChecked() else "false"
        )
        self.settings.setValue(
            KEY_SESSION_TIMER_ENABLED, "true" if self.chk_session_timer.isChecked() else "false"
        )
        if hasattr(self, "cmb_lyrics_provider"):
            self.settings.setValue(
                KEY_LYRICS_PROVIDER,
                self.cmb_lyrics_provider.currentData() or DEFAULT_LYRICS_PROVIDER,
            )
            self.settings.setValue(
                KEY_BETTERLYRICS_API_KEY,
                self.txt_betterlyrics_api_key.text().strip(),
            )
        self.settings.setValue(
            KEY_DEV_CONSOLE_ENABLED, "true" if self.chk_dev_console.isChecked() else "false"
        )
        self.settings.setValue(
            KEY_DEV_CONSOLE_SHOW_DEV, "true" if self.chk_dev_show_dev.isChecked() else "false"
        )
        self.settings.setValue(KEY_LANG, "it" if self.cmb_lang.currentIndex() == 0 else "en")
        if hasattr(self, "cmb_station"):
            self.settings.setValue(KEY_STATION, self.cmb_station.currentData() or DEFAULT_STATION)
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
        if hasattr(self, "chk_update_startup"):
            self.settings.setValue(
                KEY_UPDATE_CHECK_ON_STARTUP,
                "true" if self.chk_update_startup.isChecked() else "false",
            )
        if hasattr(self, "cmb_update_channel"):
            self.settings.setValue(
                KEY_UPDATE_CHANNEL,
                self.cmb_update_channel.currentData() or UPDATE_CHANNEL_STABLE,
            )
        try:
            self.settings.setValue(
                KEY_AUDIO_BACKEND, self.cmb_audio_backend.currentData() or "auto"
            )
        except Exception:
            pass
        if hasattr(self, "chk_dynamic_volume"):
            self.settings.setValue(
                KEY_DYNAMIC_VOLUME_ENABLED,
                "true" if self.chk_dynamic_volume.isChecked() else "false",
            )
            self.settings.setValue(
                KEY_DYNAMIC_VOLUME_MODE,
                self.cmb_dynamic_volume_mode.currentData() or DEFAULT_DYNAMIC_VOLUME_MODE,
            )
            self.settings.setValue(
                KEY_DYNAMIC_VOLUME_LEVEL,
                int(self.spin_dynamic_volume_level.value()),
            )
            self.settings.setValue(
                KEY_DYNAMIC_VOLUME_APPS,
                self.txt_dynamic_volume_apps.text().strip(),
            )
        try:
            if self._devices_populated:
                idx_data = self.cmb_audio_device.currentData()
                if idx_data is None:
                    self.settings.setValue(KEY_AUDIO_DEVICE_INDEX, "")
                else:
                    self.settings.setValue(KEY_AUDIO_DEVICE_INDEX, int(idx_data))
        except Exception:
            pass
        self._applied_values = self._settings_values()
        self._preview_current_theme()
        self._theme_preview_dirty = False

    def showEvent(self, a0: Optional[QShowEvent]) -> None:
        self._is_closed = False
        try:
            super().showEvent(a0)
        except Exception:
            pass
        if not self._embedded:
            try:
                self._apply_windows_titlebar_dark_mode(True)
            except Exception:
                pass
        if not self._devices_populated and not self._enumerating_devices:
            self._device_enum_timer.start(240 if self._embedded else 80)

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

    @classmethod
    def _collect_pyaudio_devices(cls, force_refresh: bool = False) -> List[Tuple[str, int]]:
        """Enumerate output audio devices thread-safely under PORTAUDIO_LOCK with caching."""
        global _CACHED_AUDIO_DEVICES
        with PORTAUDIO_LOCK:
            if not force_refresh and _CACHED_AUDIO_DEVICES is not None:
                return list(_CACHED_AUDIO_DEVICES)
            try:
                import pyaudio
            except Exception:
                return []
            devices: List[Tuple[str, int]] = []
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
                            tag = cls._PA_API_TAGS.get(api_type, "")
                            label = f"[{tag}] {name} (#{i})" if tag else f"{name} (#{i})"
                        else:
                            label = f"{name} (#{i})"
                        devices.append((label, i))
            except Exception:
                pass
            finally:
                try:
                    if pa is not None and hasattr(pa, "terminate"):
                        with silence_stderr():
                            pa.terminate()
                except Exception:
                    pass
            _CACHED_AUDIO_DEVICES = list(devices)
            return devices

    def _on_audio_devices_enumerated(self, devices: object) -> None:
        self._enumerating_devices = False
        if self._is_closed or not hasattr(self, "cmb_audio_device"):
            return
        was_unpopulated = not self._devices_populated
        try:
            self.cmb_audio_device.blockSignals(True)
            for i in range(self.cmb_audio_device.count() - 1, 0, -1):
                self.cmb_audio_device.removeItem(i)
            if isinstance(devices, list):
                for item in devices:
                    if isinstance(item, tuple) and len(item) == 2:
                        label, idx = item
                        self.cmb_audio_device.addItem(str(label), int(idx))
            persisted = self.settings.value(KEY_AUDIO_DEVICE_INDEX, "")
            if persisted != "" and persisted is not None:
                try:
                    persisted_int = int(persisted)
                    for combo_idx in range(self.cmb_audio_device.count()):
                        if self.cmb_audio_device.itemData(combo_idx) == persisted_int:
                            self.cmb_audio_device.setCurrentIndex(combo_idx)
                            break
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            try:
                self.cmb_audio_device.blockSignals(False)
            except Exception:
                pass
        self._devices_populated = True
        if was_unpopulated and hasattr(self, "_applied_values"):
            self._applied_values["audio_device"] = self.cmb_audio_device.currentData()

    def _populate_audio_devices(
        self, async_mode: bool = False, force_refresh: bool = False
    ) -> None:
        if self._is_closed or self._enumerating_devices:
            return
        if not force_refresh and _CACHED_AUDIO_DEVICES is not None:
            self._on_audio_devices_enumerated(list(_CACHED_AUDIO_DEVICES))
            return
        if not async_mode:
            self._on_audio_devices_enumerated(
                self._collect_pyaudio_devices(force_refresh=force_refresh)
            )
            return
        self._enumerating_devices = True

        def _worker() -> None:
            res = self._collect_pyaudio_devices(force_refresh=force_refresh)
            if getattr(self, "_is_closed", False):
                return
            try:
                self._audio_devices_ready.emit(res)
            except RuntimeError:
                pass

        threading.Thread(target=_worker, name="KikuMoeAudioEnum", daemon=True).start()
