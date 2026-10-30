"""
AmbientCoverCard, FullBleedCanvas, LiveEqualizerBadge, and AnimatedTrackLabel
widgets for KikuMoe 2.0.0.
Features:
- FullBleedCanvas: 60 FPS crossfading full-window blurred artwork / nebula backdrop
- AmbientCoverCard: 60 FPS crossfade + subtle zoom-in cover transition & halo color lerp
- AnimatedTrackLabel: 60 FPS vertical slide + crossfade when song title/artist changes
- LiveEqualizerBadge: animated 4-bar ON AIR spectrum pill
"""

import math
from typing import List, Optional, Tuple

from PyQt6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from core.audio_analyzer import AudioSpectrumAnalyzer
from ui.themes.cyber_moe import PALETTE, accent_qcolor, surface_qcolor


def _lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
    )


class FullBleedCanvas(QWidget):
    """
    Root canvas widget that renders the current album cover heavily blurred
    across the entire window with an atmospheric dark glass vignette, or a
    rich Cyber-Moe multi-radial nebula backdrop when no cover is loaded.
    Crossfades smoothly at 60 FPS whenever the cover changes.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._blurred_source: Optional[QPixmap] = None
        self._prev_blurred: Optional[QPixmap] = None
        self._ambient_color: QColor = QColor(PALETTE["accent"])
        self._prev_ambient_color: QColor = QColor(PALETTE["accent"])
        self._current_key: Optional[int] = None
        self._fade_progress: float = 1.0
        self._cached_frame: Optional[QPixmap] = None
        self._cached_frame_key: Optional[tuple] = None

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)
        self._fade_timer.timeout.connect(self._tick_fade)

    def _invalidate_cache(self) -> None:
        self._cached_frame = None
        self._cached_frame_key = None

    def resizeEvent(self, a0) -> None:
        self._invalidate_cache()
        super().resizeEvent(a0)

    def _make_blurred(self, pixmap: Optional[QPixmap]) -> Optional[QPixmap]:
        if pixmap is None or pixmap.isNull():
            return None
        p1 = pixmap.scaled(
            36,
            36,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        p2 = p1.scaled(
            18,
            18,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        p3 = p2.scaled(
            64,
            64,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        return p3.scaled(
            24,
            24,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def set_backdrop(
        self, pixmap: Optional[QPixmap], ambient_color: Optional[QColor] = None
    ) -> None:
        new_key = pixmap.cacheKey() if (pixmap is not None and not pixmap.isNull()) else None
        new_amb = QColor(ambient_color) if ambient_color is not None else QColor(PALETTE["accent"])

        if new_key == self._current_key and self._blurred_source is not None:
            if self._ambient_color != new_amb:
                self._ambient_color = new_amb
                self._invalidate_cache()
            self.update()
            return
        if new_key is None and self._current_key is None:
            if self._ambient_color != new_amb:
                self._ambient_color = new_amb
                self._invalidate_cache()
            self.update()
            return

        self._invalidate_cache()
        # Snapshot current state for 60 FPS crossfade
        self._prev_blurred = self._blurred_source
        self._prev_ambient_color = _lerp_color(
            self._prev_ambient_color, self._ambient_color, self._fade_progress
        )
        self._current_key = new_key
        self._ambient_color = new_amb
        self._blurred_source = self._make_blurred(pixmap)

        if self.isVisible():
            self._fade_progress = 0.0
            if not self._fade_timer.isActive():
                self._fade_timer.start()
        else:
            self._fade_progress = 1.0
        self.update()

    def _tick_fade(self) -> None:
        self._fade_progress = min(1.0, self._fade_progress + 0.05)
        if self._fade_progress >= 1.0:
            self._fade_progress = 1.0
            self._prev_blurred = None
            self._fade_timer.stop()
        self.update()

    def _draw_backdrop_layer(
        self, painter: QPainter, blurred: Optional[QPixmap], w: float, h: float, opacity: float
    ) -> None:
        if opacity <= 0.005:
            return
        painter.save()
        painter.setOpacity(opacity)
        if blurred is not None and not blurred.isNull():
            scaled = blurred.scaled(
                int(w),
                int(h),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x_off = (scaled.width() - int(w)) // 2
            y_off = (scaled.height() - int(h)) // 2
            painter.drawPixmap(0, 0, scaled, x_off, y_off, int(w), int(h))

            overlay = QLinearGradient(0, 0, 0, h)
            overlay.setColorAt(0.0, surface_qcolor(90, "bg_canvas"))
            overlay.setColorAt(0.22, surface_qcolor(130, "bg_canvas"))
            overlay.setColorAt(0.55, surface_qcolor(175, "bg_canvas"))
            overlay.setColorAt(0.80, surface_qcolor(220, "bg_canvas"))
            overlay.setColorAt(1.0, surface_qcolor(245, "bg_canvas"))
            painter.fillRect(self.rect(), overlay)
        else:
            g1 = QRadialGradient(QPointF(w * 0.5, h * 0.28), w * 0.70)
            g1.setColorAt(0.0, accent_qcolor(52))
            g1.setColorAt(0.55, accent_qcolor(24, "accent_deep"))
            g1.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(self.rect(), g1)

            g2 = QRadialGradient(QPointF(w * 0.15, h * 0.12), w * 0.55)
            g2.setColorAt(0.0, surface_qcolor(36, "nebula_secondary"))
            g2.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(self.rect(), g2)
        painter.restore()

    def refresh_theme(self) -> None:
        if self._current_key is None:
            self._ambient_color = QColor(PALETTE["accent"])
            self._prev_ambient_color = QColor(PALETTE["accent"])
        self._invalidate_cache()
        self.update()

    def _render_canvas_contents(self, painter: QPainter, w: float, h: float, is_max: bool) -> None:
        corner_r = 0.0 if is_max else 12.0
        target_rect = QRectF(0.0, 0.0, w, h)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), corner_r, corner_r)
        painter.setClipPath(clip_path)

        # Base dark theme canvas fill
        painter.fillRect(target_rect, QColor(PALETTE["bg_canvas"]))

        ease = 1.0 - ((1.0 - self._fade_progress) ** 3)
        if self._fade_progress < 1.0:
            self._draw_backdrop_layer(painter, self._prev_blurred, w, h, 1.0 - ease)
            self._draw_backdrop_layer(painter, self._blurred_source, w, h, ease)
        else:
            self._draw_backdrop_layer(painter, self._blurred_source, w, h, 1.0)

        # Ambient accent top-stage spotlight (smoothly lerped)
        cur_amb = _lerp_color(self._prev_ambient_color, self._ambient_color, ease)
        spot = QRadialGradient(QPointF(w * 0.5, h * 0.26), w * 0.55)
        c_spot = QColor(cur_amb)
        c_spot.setAlpha(42)
        spot.setColorAt(0.0, c_spot)
        spot.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(target_rect, spot)

        # Crisp 1px rounded window border (Windows 11 style)
        if not is_max:
            painter.setClipping(False)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 42), 1.0))
            painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), corner_r, corner_r)

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        w = float(self.width())
        h = float(self.height())
        if w <= 0.0 or h <= 0.0:
            painter.end()
            return

        win = self.window()
        is_max = bool(win and win.isMaximized())

        if self._fade_progress < 1.0:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self._render_canvas_contents(painter, w, h, is_max)
            painter.end()
            return

        dpr = float(self.devicePixelRatioF()) if hasattr(self, "devicePixelRatioF") else 1.0
        dpr = max(1.0, dpr)
        state_key = (
            int(w),
            int(h),
            round(dpr, 2),
            is_max,
            PALETTE.get("theme_id"),
            PALETTE.get("accent"),
            self._current_key,
            self._ambient_color.rgba(),
        )
        if self._cached_frame is None or self._cached_frame_key != state_key:
            frame = QPixmap(max(1, int(round(w * dpr))), max(1, int(round(h * dpr))))
            frame.setDevicePixelRatio(dpr)
            frame.fill(Qt.GlobalColor.transparent)
            fp = QPainter(frame)
            fp.setRenderHint(QPainter.RenderHint.Antialiasing)
            fp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self._render_canvas_contents(fp, w, h, is_max)
            fp.end()
            self._cached_frame = frame
            self._cached_frame_key = state_key

        painter.drawPixmap(0, 0, self._cached_frame)
        painter.end()


class LiveEqualizerBadge(QWidget):
    """
    Compact HUD pill badge showing 'LIVE' status and a 4-bar animated equalizer
    that dances when the radio stream is playing.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(78, 24)
        self._playing = False
        self._phase = 0.0
        self._accent = QColor(PALETTE["accent"])

        self._timer = QTimer(self)
        self._timer.setInterval(65)
        self._timer.timeout.connect(self._tick)

    def set_playing(self, playing: bool) -> None:
        if self._playing != playing:
            self._playing = playing
            if playing:
                self._timer.start()
            else:
                self._timer.stop()
            self.update()

    def _tick(self) -> None:
        self._phase += 0.42
        self.update()

    def refresh_theme(self) -> None:
        self._accent = QColor(PALETTE["accent"])
        self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(1.0, 1.0, w - 2.0, h - 2.0)

        if self._playing:
            bg = accent_qcolor(220, "accent_deeper")
            border = accent_qcolor(165)
            bar_col = QColor(PALETTE["accent_hover"])
            text_col = QColor("#ffffff")
            label = "ON AIR"
        else:
            bg = surface_qcolor(205, "bg_pill_idle")
            border = QColor(255, 255, 255, 38)
            bar_col = QColor("#8e95ab")
            text_col = QColor(PALETTE["text_secondary"])
            label = "LIVE"

        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(rect, 11.0, 11.0)

        # 4 equalizer bars on the left side of the pill
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bar_col)
        base_x = 10.0
        cy = h / 2.0
        freqs = [1.0, 1.45, 0.85, 1.25]
        offsets = [0.0, 1.2, 2.5, 0.7]
        for i in range(4):
            if self._playing:
                amp = 0.35 + 0.65 * abs(math.sin(self._phase * freqs[i] + offsets[i]))
                bar_h = max(3.0, 11.0 * amp)
            else:
                bar_h = 3.0 if i % 2 == 0 else 5.0
            bx = base_x + i * 4.0
            painter.drawRoundedRect(QRectF(bx, cy - bar_h / 2.0, 2.3, bar_h), 1.1, 1.1)

        # Label text on the right
        font = QFont(self.font())
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(text_col)
        painter.drawText(
            QRectF(27.0, 0.0, w - 31.0, h),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )
        painter.end()


class AnimatedTrackLabel(QLabel):
    """
    QLabel subclass that performs a smooth 60 FPS vertical slide-up + crossfade
    whenever its text changes to a new track title or artist.
    Supports an optional attached dropdown chevron button positioned right next to the title text,
    interactive hover capsule glow, and click emission to trigger track actions.
    """

    clicked = pyqtSignal()

    def __init__(
        self,
        text: str = "",
        font_px: int = 16,
        font_weight: int = 800,
        text_color: str = "#ffffff",
        interactive: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        self._font_px = font_px
        self._font_weight = font_weight
        self._text_color = QColor(text_color)
        self._prev_text: str = text
        self._anim_progress: float = 1.0
        self._chevron_btn: Optional[QWidget] = None
        self._hovered: bool = False
        self._menu_active: bool = False
        self._interactive: bool = interactive
        self._hover_group: Optional["TrackHoverGroup"] = None  # noqa: UP037

        self.setFixedHeight(max(22, font_px + 8))
        self.setMinimumWidth(0)
        if self._interactive:
            self.setMouseTracking(True)

        self._elapsed = QElapsedTimer()
        self._anim_timer = QTimer(self)
        self._anim_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)

    def set_text_color(self, color: str) -> None:
        self._text_color = QColor(color)
        self.update()

    def attach_chevron_button(self, btn: QWidget) -> None:
        """Attach a dropdown chevron button positioned at the end of the title text."""
        self._interactive = True
        self.setMouseTracking(True)
        self._chevron_btn = btn
        btn.setParent(self)
        self._update_chevron_position()

    def sizeHint(self) -> QSize:
        return QSize(100, max(22, self._font_px + 8))

    def minimumSizeHint(self) -> QSize:
        return QSize(20, max(22, self._font_px + 8))

    def get_capsule_rect(self) -> Optional[QRectF]:
        """Calculates precise symmetrical cyber-glass capsule around centered text + chevron."""
        if not self._interactive:
            return None
        txt = (self.text() or "").strip()
        if not txt or txt in ("–", "-"):
            return None
        w = float(self.width())
        h = float(self.height())
        if w <= 10 or h <= 10:
            return None

        font = QFont(self.font())
        font.setPixelSize(self._font_px)
        font.setWeight(QFont.Weight(self._font_weight))
        fm = QFontMetrics(font)

        has_btn = bool(self._chevron_btn and self._chevron_btn.isVisible())
        btn_w = float(self._chevron_btn.width()) if (has_btn and self._chevron_btn) else 0.0
        reserve_w = (btn_w + 6.0) if has_btn else 0.0

        usable_w = max(20, int(w - 12.0 - reserve_w * 2.0))
        elided_txt = fm.elidedText(txt, Qt.TextElideMode.ElideRight, usable_w)
        text_w = float(fm.horizontalAdvance(elided_txt))

        text_x = 6.0 + (w - 12.0 - text_w) / 2.0
        capsule_x = text_x - 8.0
        capsule_w = text_w + (btn_w + 19.0 if has_btn else 16.0)
        return QRectF(capsule_x, 1.0, capsule_w, h - 2.0)

    def set_menu_active(self, active: bool) -> None:
        """Keep capsule illuminated while dropdown context menu is open."""
        if self._menu_active != active:
            self._menu_active = active
            self.update()
            if self._hover_group is not None:
                self._hover_group.refresh_hover()

    def is_menu_active(self) -> bool:
        return self._menu_active

    def set_hovered(self, hovered: bool) -> None:
        """Synchronize hover capsule state with child chevron button."""
        if not self._interactive:
            return
        if self._hovered != hovered:
            self._hovered = hovered
            if self._chevron_btn and hasattr(self._chevron_btn, "set_hovered"):
                self._chevron_btn.set_hovered(hovered)
            self.update()
            if self._hover_group is not None:
                self._hover_group.set_hovered(hovered)

    def enterEvent(self, event: object) -> None:
        super().enterEvent(event)  # type: ignore[arg-type]

    def leaveEvent(self, a0: object) -> None:
        if self._interactive:
            if not self._menu_active:
                if self._hover_group is not None:
                    QTimer.singleShot(0, self._hover_group.refresh_pointer)
                elif self._chevron_btn and self._chevron_btn.underMouse():
                    pass
                else:
                    self.set_hovered(False)
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(a0)  # type: ignore[arg-type]

    def mouseMoveEvent(self, ev: object) -> None:
        if self._interactive and isinstance(ev, QMouseEvent):
            rect = self.get_capsule_rect()
            if rect is not None and rect.contains(ev.position()):
                self.set_hovered(True)
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                if not self._menu_active:
                    self.set_hovered(False)
                self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(ev)  # type: ignore[arg-type]

    def mousePressEvent(self, ev: object) -> None:
        if (
            self._interactive
            and isinstance(ev, QMouseEvent)
            and ev.button() == Qt.MouseButton.LeftButton
        ):
            rect = self.get_capsule_rect()
            if rect is not None and rect.contains(ev.position()):
                if self._hover_group is not None:
                    self._hover_group.animate_click()
                self.clicked.emit()
                return
        super().mousePressEvent(ev)  # type: ignore[arg-type]

    def setText(self, a0: Optional[str]) -> None:
        new_txt = a0 or ""
        old_txt = self.text()
        if new_txt == old_txt:
            return
        self._prev_text = old_txt
        super().setText(new_txt)
        self._update_chevron_position()
        if self._hover_group is not None:
            self._hover_group.update()
        if self.isVisible():
            self._anim_progress = 0.0
            self._elapsed.start()
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        else:
            self._anim_progress = 1.0
        self.update()

    def resizeEvent(self, a0: object) -> None:
        super().resizeEvent(a0)  # type: ignore[arg-type]
        self._update_chevron_position()

    def _update_chevron_position(self) -> None:
        if self._chevron_btn is None:
            return
        w = float(self.width())
        h = float(self.height())
        if w <= 10 or h <= 10:
            return
        txt = (self.text() or "").strip()
        if not txt or txt in ("–", "-"):
            self._chevron_btn.setVisible(False)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        font = QFont(self.font())
        font.setPixelSize(self._font_px)
        font.setWeight(QFont.Weight(self._font_weight))
        fm = QFontMetrics(font)

        btn_w = float(self._chevron_btn.width())
        btn_h = float(self._chevron_btn.height())
        reserve_w = btn_w + 6.0

        max_text_w = max(20.0, w - 12.0 - reserve_w * 2.0)
        elided_txt = fm.elidedText(txt, Qt.TextElideMode.ElideRight, int(max_text_w))
        text_w = float(fm.horizontalAdvance(elided_txt))

        text_x = 6.0 + (w - 12.0 - text_w) / 2.0
        text_end_x = text_x + text_w

        btn_x = int(text_end_x + 3.0)
        btn_y = int((h - btn_h) / 2.0)
        self._chevron_btn.move(btn_x, btn_y)
        self._chevron_btn.setVisible(True)

    def _tick_anim(self) -> None:
        elapsed = float(self._elapsed.elapsed())
        duration = 200.0
        t = min(1.0, max(0.0, elapsed / duration))
        self._anim_progress = t
        if t >= 1.0:
            self._anim_progress = 1.0
            self._anim_timer.stop()
        self.update()

    def paintEvent(self, a0: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = float(self.width())
        h = float(self.height())
        font = QFont(self.font())
        font.setPixelSize(self._font_px)
        font.setWeight(QFont.Weight(self._font_weight))
        painter.setFont(font)
        fm = QFontMetrics(font)

        reserve_w = (
            (float(self._chevron_btn.width()) + 6.0)
            if (self._chevron_btn and self._chevron_btn.isVisible())
            else 0.0
        )
        usable_w = max(20, int(w - 12.0 - reserve_w * 2.0))

        in_elided = fm.elidedText(self.text(), Qt.TextElideMode.ElideRight, usable_w)

        # Sleek cyber-glass hover capsule when user points at title / chevron
        rect = self.get_capsule_rect() if self._interactive else None
        if self._hover_group is None and (self._hovered or self._menu_active) and rect is not None:
            painter.setBrush(QColor(255, 255, 255, 14))
            painter.setPen(QPen(accent_qcolor(90), 1.0))
            painter.drawRoundedRect(rect, 6.0, 6.0)

        if self._hover_group is not None:
            scale = self._hover_group.click_scale
            painter.translate(w / 2.0, h / 2.0)
            painter.scale(scale, scale)
            painter.translate(-w / 2.0, -h / 2.0)

        ease = 1.0 - ((1.0 - self._anim_progress) ** 3)

        # Outgoing text sliding up & fading out
        if self._anim_progress < 1.0 and self._prev_text:
            out_col = QColor(self._text_color)
            out_col.setAlpha(int(255 * (1.0 - ease)))
            painter.setPen(out_col)
            out_elided = fm.elidedText(self._prev_text, Qt.TextElideMode.ElideRight, usable_w)
            y_out = -7.0 * ease
            painter.drawText(
                QRectF(6.0, y_out, w - 12.0, h),
                Qt.AlignmentFlag.AlignCenter,
                out_elided,
            )

        # Incoming text sliding up from below & fading in
        is_lit = (self._hovered or self._menu_active) and self._interactive
        in_col = QColor("#ffffff" if is_lit else self._text_color)
        in_col.setAlpha(int(255 * ease))
        painter.setPen(in_col)
        y_in = 8.0 * (1.0 - ease)
        painter.drawText(
            QRectF(6.0, y_in, w - 12.0, h),
            Qt.AlignmentFlag.AlignCenter,
            in_elided,
        )
        painter.end()


class TrackHoverGroup(QWidget):
    """Paint one connected, animated highlight behind the track metadata."""

    def __init__(self, title: AnimatedTrackLabel, artist: AnimatedTrackLabel):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.title = title
        self.artist = artist
        self._hovered = False
        self._opacity = 0.0
        self.click_scale = 1.0
        self._click_step = 0
        self._click_timer = QTimer(self)
        self._click_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._click_timer.setInterval(16)
        self._click_timer.timeout.connect(self._tick_click)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._set_opacity)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for label in (title, artist):
            label._hover_group = self
            layout.addWidget(label)
        self.setMouseTracking(True)

    def _set_opacity(self, value: float) -> None:
        self._opacity = float(value)
        self.update()

    def animate_click(self) -> None:
        """Give the whole highlight a small tactile bounce without delaying the menu."""
        self.click_scale = 0.94
        self._click_step = 0
        self._click_timer.start()
        self._update_click_visuals()

    def _tick_click(self) -> None:
        scales = (0.96, 0.98, 1.0, 1.015, 1.01, 1.0)
        self.click_scale = scales[self._click_step]
        self._click_step += 1
        if self._click_step == len(scales):
            self._click_timer.stop()
        self._update_click_visuals()

    def _update_click_visuals(self) -> None:
        self.update()
        self.title.update()
        self.artist.update()
        if self.title._chevron_btn is not None:
            self.title._chevron_btn.update()

    def set_hovered(self, hovered: bool) -> None:
        self._hovered = hovered
        for label in (self.title, self.artist):
            if label._hovered != hovered:
                label.set_hovered(hovered)
        self.refresh_hover()

    def refresh_hover(self) -> None:
        target = 1.0 if self._hovered or self.title.is_menu_active() else 0.0
        if (
            self._animation.endValue() == target
            and self._animation.state() == self._animation.State.Running
        ):
            return
        self._animation.stop()
        self._animation.setStartValue(self._opacity)
        self._animation.setEndValue(target)
        self._animation.start()
        self.update()

    def _shape(self) -> QPainterPath:
        path = QPainterPath()
        if self.title.get_capsule_rect() is None:
            return path
        rects = []
        for label in (self.title, self.artist):
            rect = label.get_capsule_rect()
            if rect is not None:
                rect.translate(float(label.x()), float(label.y()))
                rects.append(rect)
                part = QPainterPath()
                part.addRoundedRect(rect, 6.0, 6.0)
                path = path.united(part)
        if len(rects) == 2:
            left = max(rects[0].left(), rects[1].left())
            right = min(rects[0].right(), rects[1].right())
            if right > left:
                bridge = QPainterPath()
                bridge.addRect(
                    QRectF(
                        left,
                        rects[0].center().y(),
                        right - left,
                        rects[1].center().y() - rects[0].center().y(),
                    )
                )
                path = path.united(bridge)
        return path

    def refresh_pointer(self) -> None:
        self.set_hovered(self._shape().contains(QPointF(self.mapFromGlobal(QCursor.pos()))))

    def mouseMoveEvent(self, a0: Optional[QMouseEvent]) -> None:
        if a0 is not None:
            self.set_hovered(self._shape().contains(a0.position()))
        super().mouseMoveEvent(a0)

    def leaveEvent(self, a0: object) -> None:
        QTimer.singleShot(0, self.refresh_pointer)
        super().leaveEvent(a0)  # type: ignore[arg-type]

    def paintEvent(self, a0: object) -> None:
        if self._opacity <= 0.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)
        painter.translate(self.width() / 2.0, self.height() / 2.0)
        painter.scale(self.click_scale, self.click_scale)
        painter.translate(-self.width() / 2.0, -self.height() / 2.0)
        painter.setBrush(QColor(255, 255, 255, 14))
        painter.setPen(QPen(accent_qcolor(90), 1.0))
        painter.drawPath(self._shape())
        painter.end()


def _distance_to_rounded_rect(theta: float, width: float, height: float, r: float) -> float:
    """Distanza dal centro al perimetro di un rettangolo arrotondato ad angolo theta."""
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    hw = width / 2.0
    hh = height / 2.0
    tx = hw / abs(cos_t) if abs(cos_t) > 1e-6 else 1e9
    ty = hh / abs(sin_t) if abs(sin_t) > 1e-6 else 1e9
    t_box = min(tx, ty)

    px = t_box * abs(cos_t)
    py = t_box * abs(sin_t)

    dx = px - (hw - r)
    dy = py - (hh - r)
    if dx > 0 and dy > 0:
        xc = hw - r
        yc = hh - r
        b = -2.0 * (abs(cos_t) * xc + abs(sin_t) * yc)
        c_quad = xc * xc + yc * yc - r * r
        disc = b * b - 4.0 * c_quad
        if disc >= 0:
            return (-b + math.sqrt(disc)) / 2.0
    return t_box


class AmbientCoverCard(QWidget):
    """
    Hero album cover card with frosted glass frame, dynamic ambient halo,
    and 60 FPS crossfade + subtle zoom-in animation whenever the cover changes
    (e.g. from vinyl placeholder to cover, between songs, or switching channels).
    """

    def __init__(self, parent: Optional[QWidget] = None, cover_size: int = 200):
        super().__init__(parent)
        self._cover_size = cover_size
        self._cover_pixmap: Optional[QPixmap] = None
        self._current_key: Optional[int] = None
        self._cached_rounded_cover: Optional[QPixmap] = None
        self._prev_rounded_cover: Optional[QPixmap] = None
        self._ambient_color: QColor = QColor(PALETTE["accent"])
        self._prev_ambient_color: QColor = QColor(PALETTE["accent"])
        self._corner_radius = 16.0
        self._fade_progress: float = 1.0

        # Audio-reactive conformal fluid neon wave visualizer
        self._analyzer: AudioSpectrumAnalyzer = AudioSpectrumAnalyzer()
        self._visualizer_enabled: bool = False
        self._is_playing: bool = False
        self._num_wave_points = 64
        self._spectrum_bars: List[float] = [0.0] * self._num_wave_points
        self._bass_energy: float = 0.0
        self._phase: float = 0.0

        # Precompute wave angular directions and base contour distances
        self._wave_thetas: List[float] = [
            i * 2.0 * math.pi / self._num_wave_points - math.pi / 2.0
            for i in range(self._num_wave_points)
        ]
        self._wave_cos: List[float] = [math.cos(t) for t in self._wave_thetas]
        self._wave_sin: List[float] = [math.sin(t) for t in self._wave_thetas]
        self._base_contour: List[float] = []
        self._recompute_base_contour()

        self.setFixedHeight(self._cover_size + 56)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)
        self._fade_timer.timeout.connect(self._tick_fade)

        self._viz_timer = QTimer(self)
        self._viz_timer.setInterval(16)
        self._viz_timer.timeout.connect(self._tick_visualizer)

    def _recompute_base_contour(self) -> None:
        """Precalcola la distanza dal centro al bordo della cornice per ogni punto angolare."""
        frame_w = self._cover_size + 12.0
        frame_h = self._cover_size + 12.0
        frame_r = self._corner_radius + 5.0
        self._base_contour = [
            _distance_to_rounded_rect(t, frame_w, frame_h, frame_r) for t in self._wave_thetas
        ]

    @property
    def ambient_color(self) -> QColor:
        return self._ambient_color

    def set_cover_size(self, size: int) -> None:
        self._cover_size = size
        self.setFixedHeight(self._cover_size + 56)
        self._recompute_base_contour()
        self._cached_rounded_cover = None
        self._prev_rounded_cover = None
        self.update()

    def feed_pcm(self, data: bytes) -> None:
        """Invia i chunk PCM audio decodificati all'analizzatore di spettro."""
        if self._visualizer_enabled:
            self._analyzer.feed_pcm(data)

    def set_visualizer_enabled(self, enabled: bool) -> None:
        """Abilita o disabilita il visualizzatore a onda fluida attorno alla cover."""
        self._visualizer_enabled = bool(enabled)
        if not self._visualizer_enabled:
            self._spectrum_bars = [0.0] * self._num_wave_points
            self._bass_energy = 0.0
            if not self._fade_timer.isActive():
                self._viz_timer.stop()
        elif not self._viz_timer.isActive():
            self._viz_timer.start()
        self.update()

    def is_visualizer_enabled(self) -> bool:
        return self._visualizer_enabled

    def set_playing(self, playing: bool) -> None:
        """Notifica lo stato di riproduzione per sincronizzare l'animazione o il decadimento."""
        self._is_playing = bool(playing)
        self._analyzer.set_playing(playing)
        if self._visualizer_enabled and not self._viz_timer.isActive():
            self._viz_timer.start()

    def _tick_visualizer(self) -> None:
        if self._is_playing:
            self._phase += 0.06
            mags, bass = self._analyzer.get_spectrum(32)
            # Distribuzione simmetrica lungo il perimetro dell'onda:
            # Sub-bass/cassa in basso (indice 32), medi ai lati (16 e 48), acuti in alto (0 e 63)
            bars = [0.0] * self._num_wave_points
            for i in range(self._num_wave_points):
                dist_from_bottom = abs(32 - i)
                band_idx = min(31, dist_from_bottom)
                bars[i] = mags[band_idx]
            self._spectrum_bars = bars
            self._bass_energy = bass
        else:
            # Stato inattivo/riposo: respiro calmo a bassa velocità, decadimento morbido delle barre
            self._phase += 0.02
            self._bass_energy *= 0.88
            if self._bass_energy < 0.001:
                self._bass_energy = 0.0
            for i in range(self._num_wave_points):
                if self._spectrum_bars[i] > 0.001:
                    self._spectrum_bars[i] *= 0.88
                else:
                    self._spectrum_bars[i] = 0.0
            if not self._visualizer_enabled:
                if not self._fade_timer.isActive():
                    self._viz_timer.stop()
        self.update()

    def _get_wave_gradient_colors(self, cur_amb: QColor) -> Tuple[QColor, QColor, QColor, QColor]:
        """
        Deriva una palette cyberpunk a 4 stop (evidenziazione, primario, secondario, shimmer)
        perfettamente intonata al tema attivo o al colore dominante dell'album.
        """
        h = cur_amb.hsvHue()
        s = cur_amb.hsvSaturation()
        v = cur_amb.value()
        if h < 0:
            h = 338

        is_cyber_moe = PALETTE.get("theme_id") in (None, "cyber_moe")
        if is_cyber_moe and (self._cover_pixmap is None or abs(h - 338) < 15):
            c_high = QColor("#ff4088")
            c_prim = QColor(PALETTE.get("accent", "#ec186c"))
            c_sec = QColor("#a855f7")
            c_shim = QColor("#00d2ff")
            return c_high, c_prim, c_sec, c_shim

        c_high = QColor.fromHsv(
            (h - 10) % 360,
            min(255, max(180, int(s * 1.1))),
            min(255, max(230, int(v * 1.18))),
        )
        c_prim = QColor(cur_amb)
        c_sec = QColor.fromHsv(
            (h + 42) % 360,
            min(255, max(190, s)),
            min(255, max(195, v)),
        )
        c_shim = QColor.fromHsv(
            (h + 85) % 360,
            min(255, max(160, int(s * 0.85))),
            255,
        )
        return c_high, c_prim, c_sec, c_shim

    def _build_wave_path(
        self,
        center: QPointF,
        extra_offset: float,
        amp_scale: float,
        phase_shift: float = 0.0,
    ) -> QPainterPath:
        """Costruisce una spline chiusa fluida attorno alla sagoma arrotondata della cover."""
        pts: List[QPointF] = []
        n = self._num_wave_points

        # Margine verticale e orizzontale disponibili per evitare clipping sui bordi del widget
        vert_margin = max(12.0, (float(self.height()) - (self._cover_size + 12.0)) / 2.0)
        max_allowed_dy = max(6.0, vert_margin - 5.5)

        horiz_margin = max(12.0, (float(self.width()) - (self._cover_size + 12.0)) / 2.0)
        max_allowed_dx = max(6.0, horiz_margin - 5.5)

        base_amp_x = min(max_allowed_dx * 0.70, max(20.0, self._cover_size * 0.15)) * amp_scale
        base_amp_y = min(max_allowed_dy * 0.65, max(7.0, self._cover_size * 0.055)) * amp_scale

        for i in range(n):
            mag = self._spectrum_bars[i]
            theta = self._wave_thetas[i]
            ambient_ripple = math.sin(self._phase * 2.0 + theta * 3.0 + phase_shift) * (
                1.0 + 1.8 * self._bass_energy
            )
            # Esclusione clipping: l'ondulazione in X e Y resta sempre entro i limiti del widget
            wave_dx = mag * base_amp_x + ambient_ripple * 1.0
            total_dx = min(max_allowed_dx, extra_offset + wave_dx)
            dx = (self._base_contour[i] + total_dx) * self._wave_cos[i]

            wave_dy = mag * base_amp_y + ambient_ripple * 0.55
            total_dy = min(max_allowed_dy, extra_offset + wave_dy)
            dy = (self._base_contour[i] + total_dy) * self._wave_sin[i]
            pts.append(QPointF(center.x() + dx, center.y() + dy))

        path = QPainterPath()
        path.moveTo(pts[0])
        for i in range(n):
            p_curr = pts[i]
            p_next = pts[(i + 1) % n]
            mid = QPointF((p_curr.x() + p_next.x()) / 2.0, (p_curr.y() + p_next.y()) / 2.0)
            path.quadTo(p_curr, mid)
        path.closeSubpath()
        return path

    def set_cover(self, pixmap: Optional[QPixmap]) -> None:
        new_key = pixmap.cacheKey() if (pixmap is not None and not pixmap.isNull()) else None
        if new_key == self._current_key and self._cached_rounded_cover is not None:
            return

        # Snapshot previous rendered cover & ambient color for smooth 60 FPS crossfade
        if self._cached_rounded_cover is None:
            self._cached_rounded_cover = self._render_rounded_cover(self._cover_size)
        self._prev_rounded_cover = self._cached_rounded_cover
        self._prev_ambient_color = _lerp_color(
            self._prev_ambient_color, self._ambient_color, self._fade_progress
        )

        self._current_key = new_key
        self._cover_pixmap = pixmap
        self._cached_rounded_cover = self._render_rounded_cover(self._cover_size)

        if pixmap and not pixmap.isNull():
            self._ambient_color = self._extract_dominant_color(pixmap)
        else:
            self._ambient_color = QColor(PALETTE["accent"])

        if self.isVisible():
            self._fade_progress = 0.0
            if not self._fade_timer.isActive():
                self._fade_timer.start()
        else:
            self._fade_progress = 1.0
            self._prev_rounded_cover = None
        self.update()

    def _tick_fade(self) -> None:
        self._fade_progress = min(1.0, self._fade_progress + 0.055)
        if self._fade_progress >= 1.0:
            self._fade_progress = 1.0
            self._prev_rounded_cover = None
            self._fade_timer.stop()
        self.update()

    def _extract_dominant_color(self, pixmap: QPixmap) -> QColor:
        """Extract a vibrant accent color from the artwork for the ambient halo."""
        try:
            img = pixmap.toImage().scaled(
                16,
                16,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            r_total, g_total, b_total, count = 0, 0, 0, 0
            for x in range(img.width()):
                for y in range(img.height()):
                    c = img.pixelColor(x, y)
                    if 40 < c.lightness() < 220:
                        r_total += c.red()
                        g_total += c.green()
                        b_total += c.blue()
                        count += 1
            if count > 0:
                avg = QColor(r_total // count, g_total // count, b_total // count)
                h = max(0, avg.hsvHue())
                s = max(0, avg.hsvSaturation())
                v = max(0, avg.value())
                return QColor.fromHsv(h, min(255, max(135, int(s * 1.25))), max(155, v))
        except Exception:
            pass
        return QColor(PALETTE["accent"])

    def refresh_theme(self) -> None:
        if self._cover_pixmap is None or self._cover_pixmap.isNull():
            self._cached_rounded_cover = None
            self._prev_rounded_cover = None
            self._ambient_color = QColor(PALETTE["accent"])
            self._prev_ambient_color = QColor(PALETTE["accent"])
        self.update()

    def _render_rounded_cover(self, target_size: int) -> QPixmap:
        """Renders either the rounded cover art or a sleek vinyl disc placeholder."""
        canvas = QPixmap(target_size, target_size)
        canvas.fill(Qt.GlobalColor.transparent)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(
            QRectF(0, 0, target_size, target_size),
            self._corner_radius,
            self._corner_radius,
        )
        painter.setClipPath(clip_path)

        if self._cover_pixmap and not self._cover_pixmap.isNull():
            scaled = self._cover_pixmap.scaled(
                target_size,
                target_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x_off = (scaled.width() - target_size) // 2
            y_off = (scaled.height() - target_size) // 2
            painter.drawPixmap(0, 0, scaled, x_off, y_off, target_size, target_size)
        else:
            # Elegant Vinyl Disc Placeholder
            grad = QLinearGradient(0, 0, target_size, target_size)
            grad.setColorAt(0.0, QColor("#1a1d2a"))
            grad.setColorAt(1.0, QColor("#0d0f16"))
            painter.fillRect(0, 0, target_size, target_size, grad)

            cx = target_size / 2.0
            cy = target_size / 2.0

            # Vinyl groove rings
            groove_pen = QPen(QColor(255, 255, 255, 16))
            groove_pen.setWidthF(1.0)
            painter.setPen(groove_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            for r in [0.43, 0.38, 0.33, 0.28, 0.23]:
                radius = target_size * r
                painter.drawEllipse(QPointF(cx, cy), radius, radius)

            # Diagonal vinyl sheen reflection
            sheen = QLinearGradient(0, 0, target_size, target_size)
            sheen.setColorAt(0.0, QColor(255, 255, 255, 0))
            sheen.setColorAt(0.46, QColor(255, 255, 255, 0))
            sheen.setColorAt(0.50, QColor(255, 255, 255, 18))
            sheen.setColorAt(0.54, QColor(255, 255, 255, 0))
            sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(sheen))
            painter.drawEllipse(QPointF(cx, cy), target_size * 0.44, target_size * 0.44)

            # Center Vinyl Label (Accent Tint)
            label_grad = QRadialGradient(QPointF(cx, cy), target_size * 0.18)
            label_grad.setColorAt(0.0, QColor(PALETTE["accent_deeper"]))
            label_grad.setColorAt(0.85, QColor(PALETTE["accent"]))
            label_grad.setColorAt(1.0, QColor(PALETTE["accent_deep"]))

            painter.setBrush(QBrush(label_grad))
            painter.drawEllipse(QPointF(cx, cy), target_size * 0.16, target_size * 0.16)

            # Outer ring around label
            painter.setPen(QPen(QColor(255, 255, 255, 45), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), target_size * 0.16, target_size * 0.16)

            # Spindle hole
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#0d0f15"))
            painter.drawEllipse(QPointF(cx, cy), target_size * 0.045, target_size * 0.045)

        painter.end()
        return canvas

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = self.width()
        h = self.height()
        side = self._cover_size

        cover_x = (w - side) // 2
        cover_y = (h - side) // 2
        ease = 1.0 - ((1.0 - self._fade_progress) ** 3)

        # 1. Rich Dynamic Ambient Halo behind artwork (audio-reactive & color-interpolated)
        cur_amb = _lerp_color(self._prev_ambient_color, self._ambient_color, ease)
        bass_boost = (self._bass_energy * 32.0) if self._visualizer_enabled else 0.0
        glow_radius = max(side * 0.85, 155.0) + bass_boost
        glow_x = min(glow_radius, max(1.0, w / 2.0 - 1.0))
        glow_y = min(glow_radius, max(1.0, h / 2.0 - 1.0))
        center = QPointF(w / 2.0, h / 2.0)
        rad_grad = QRadialGradient(QPointF(0.0, 0.0), 1.0)

        alpha_boost = int(50 * self._bass_energy) if self._visualizer_enabled else 0
        glow_col = QColor(cur_amb)
        glow_col.setAlpha(min(255, 95 + alpha_boost))
        rad_grad.setColorAt(0.0, glow_col)
        glow_mid = QColor(cur_amb)
        glow_mid.setAlpha(min(255, 42 + alpha_boost // 2))
        rad_grad.setColorAt(0.58, glow_mid)
        rad_grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.save()
        painter.translate(center)
        painter.scale(glow_x, glow_y)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(rad_grad))
        painter.drawEllipse(QPointF(0.0, 0.0), 1.0, 1.0)
        painter.restore()

        # 2. Audio-Reactive Conformal Fluid Neon Wave with Multi-Stop Cyber Gradient
        if self._visualizer_enabled:
            c_high, c_prim, c_sec, c_shim = self._get_wave_gradient_colors(cur_amb)

            wave_primary = self._build_wave_path(
                center, extra_offset=4.0, amp_scale=1.15, phase_shift=0.0
            )

            # Translucent radial glow fill behind primary wave
            fill_grad = QRadialGradient(center, side * 0.78)
            f_col1 = QColor(c_prim)
            f_col1.setAlpha(min(55, int(22 + 45 * self._bass_energy)))
            f_col2 = QColor(c_sec)
            f_col2.setAlpha(min(35, int(15 + 25 * self._bass_energy)))
            f_col3 = QColor(c_shim)
            f_col3.setAlpha(8)
            fill_grad.setColorAt(0.0, f_col1)
            fill_grad.setColorAt(0.65, f_col2)
            fill_grad.setColorAt(1.0, f_col3)

            painter.setBrush(QBrush(fill_grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(wave_primary)

            # Secondary resonant echo wave with cyber gradient
            wave_echo = self._build_wave_path(
                center, extra_offset=1.5, amp_scale=0.55, phase_shift=1.4
            )
            echo_grad = QLinearGradient(cover_x, cover_y, cover_x + side, cover_y + side)
            e1 = QColor(c_high)
            e1.setAlpha(115)
            e2 = QColor(c_sec)
            e2.setAlpha(95)
            e3 = QColor(c_shim)
            e3.setAlpha(110)
            echo_grad.setColorAt(0.0, e1)
            echo_grad.setColorAt(0.60, e2)
            echo_grad.setColorAt(1.0, e3)

            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QBrush(echo_grad), 1.8))
            painter.drawPath(wave_echo)

            # Primary wave outer bloom pass with multi-stop linear gradient
            bloom_grad = QLinearGradient(
                cover_x - 20, cover_y - 10, cover_x + side + 20, cover_y + side + 10
            )
            alpha_bloom = min(255, int(120 + 85 * self._bass_energy))
            b1 = QColor(c_high)
            b1.setAlpha(alpha_bloom)
            b2 = QColor(c_prim)
            b2.setAlpha(alpha_bloom)
            b3 = QColor(c_sec)
            b3.setAlpha(alpha_bloom)
            b4 = QColor(c_shim)
            b4.setAlpha(alpha_bloom)

            bloom_grad.setColorAt(0.0, b1)
            bloom_grad.setColorAt(0.38, b2)
            bloom_grad.setColorAt(0.72, b3)
            bloom_grad.setColorAt(1.0, b4)

            bloom_pen = QPen(
                QBrush(bloom_grad),
                5.2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
            painter.setPen(bloom_pen)
            painter.drawPath(wave_primary)

            # Primary wave core neon line with white-to-pastels gradient
            core_grad = QLinearGradient(cover_x - 10, cover_y, cover_x + side + 10, cover_y + side)
            core_grad.setColorAt(0.0, QColor("#ffffff"))
            core_grad.setColorAt(0.35, QColor("#ffeef6"))
            core_grad.setColorAt(0.70, QColor("#f3e8ff"))
            core_grad.setColorAt(1.0, QColor("#e0f7ff"))

            core_pen = QPen(
                QBrush(core_grad),
                2.2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
            painter.setPen(core_pen)
            painter.drawPath(wave_primary)

        # 3. Outer Frosted Glass Frame Pedestal around the cover
        frame_rect = QRectF(cover_x - 6, cover_y - 6, side + 12, side + 12)
        frame_path = QPainterPath()
        frame_path.addRoundedRect(frame_rect, self._corner_radius + 5, self._corner_radius + 5)
        painter.setBrush(QColor(255, 255, 255, 10))
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1.0))
        painter.drawPath(frame_path)

        # 4. Deep Drop Shadow under cover
        shadow_rect = QRectF(cover_x + 1, cover_y + 4, side - 2, side)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, self._corner_radius + 1, self._corner_radius + 1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 125))
        painter.drawPath(shadow_path)

        # 5. Draw Rounded Cover Art with 60 FPS Crossfade + Subtle Scale-In
        if self._cached_rounded_cover is None or self._cached_rounded_cover.width() != side:
            self._cached_rounded_cover = self._render_rounded_cover(side)

        cover_clip = QPainterPath()
        cover_clip.addRoundedRect(
            QRectF(cover_x, cover_y, side, side),
            self._corner_radius,
            self._corner_radius,
        )
        painter.save()
        painter.setClipPath(cover_clip)

        if self._fade_progress < 1.0 and self._prev_rounded_cover is not None:
            painter.setOpacity(1.0 - ease)
            painter.drawPixmap(cover_x, cover_y, self._prev_rounded_cover)

            # Incoming cover fades in with a subtle 0.94 -> 1.0 zoom-in
            scale = 0.94 + 0.06 * ease
            painter.setOpacity(ease)
            painter.translate(center)
            painter.scale(scale, scale)
            painter.translate(-center)
            painter.drawPixmap(cover_x, cover_y, self._cached_rounded_cover)
        else:
            painter.drawPixmap(cover_x, cover_y, self._cached_rounded_cover)

        painter.restore()

        # 6. Inner Specular Rim Outline
        border_path = QPainterPath()
        border_path.addRoundedRect(
            QRectF(cover_x + 0.5, cover_y + 0.5, side - 1, side - 1),
            self._corner_radius,
            self._corner_radius,
        )
        painter.setPen(QPen(QColor(255, 255, 255, 48), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(border_path)

        painter.end()
