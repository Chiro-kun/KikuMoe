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
from typing import Optional

from PyQt6.QtCore import QElapsedTimer, QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QLabel, QWidget

from ui.themes.cyber_moe import PALETTE


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

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)
        self._fade_timer.timeout.connect(self._tick_fade)

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
            self._ambient_color = new_amb
            self.update()
            return
        if new_key is None and self._current_key is None:
            self._ambient_color = new_amb
            self.update()
            return

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
            overlay.setColorAt(0.0, QColor(10, 11, 18, 90))
            overlay.setColorAt(0.22, QColor(10, 11, 18, 130))
            overlay.setColorAt(0.55, QColor(10, 11, 18, 175))
            overlay.setColorAt(0.80, QColor(9, 10, 17, 220))
            overlay.setColorAt(1.0, QColor(8, 9, 15, 245))
            painter.fillRect(self.rect(), overlay)
        else:
            g1 = QRadialGradient(QPointF(w * 0.5, h * 0.28), w * 0.70)
            g1.setColorAt(0.0, QColor(236, 24, 108, 52))
            g1.setColorAt(0.55, QColor(130, 20, 90, 24))
            g1.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(self.rect(), g1)

            g2 = QRadialGradient(QPointF(w * 0.15, h * 0.12), w * 0.55)
            g2.setColorAt(0.0, QColor(110, 50, 220, 36))
            g2.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(self.rect(), g2)
        painter.restore()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = float(self.width())
        h = float(self.height())
        win = self.window()
        is_max = bool(win and win.isMaximized())
        corner_r = 0.0 if is_max else 12.0

        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), corner_r, corner_r)
        painter.setClipPath(clip_path)

        # Base dark obsidian fill
        painter.fillRect(self.rect(), QColor("#0b0c14"))

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
        painter.fillRect(self.rect(), spot)

        # Crisp 1px rounded window border (Windows 11 style)
        if not is_max:
            painter.setClipping(False)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 42), 1.0))
            painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), corner_r, corner_r)

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

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(1.0, 1.0, w - 2.0, h - 2.0)

        if self._playing:
            bg = QColor(42, 12, 30, 220)
            border = QColor(236, 24, 108, 160)
            bar_col = QColor("#ff3b8d")
            text_col = QColor("#ffffff")
            label = "ON AIR"
        else:
            bg = QColor(14, 16, 26, 205)
            border = QColor(255, 255, 255, 38)
            bar_col = QColor("#8e95ab")
            text_col = QColor("#c8cee0")
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
    Supports an optional attached dropdown chevron button positioned right next to the title text.
    """

    def __init__(
        self,
        text: str = "",
        font_px: int = 16,
        font_weight: int = 800,
        text_color: str = "#ffffff",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        self._font_px = font_px
        self._font_weight = font_weight
        self._text_color = QColor(text_color)
        self._prev_text: str = text
        self._anim_progress: float = 1.0
        self._chevron_btn: Optional[QWidget] = None

        self.setFixedHeight(max(22, font_px + 8))
        self.setMinimumWidth(0)

        self._elapsed = QElapsedTimer()
        self._anim_timer = QTimer(self)
        self._anim_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)

    def attach_chevron_button(self, btn: QWidget) -> None:
        """Attach a dropdown chevron button positioned at the end of the title text."""
        self._chevron_btn = btn
        btn.setParent(self)
        self._update_chevron_position()

    def sizeHint(self) -> QSize:
        return QSize(100, max(22, self._font_px + 8))

    def minimumSizeHint(self) -> QSize:
        return QSize(20, max(22, self._font_px + 8))

    def setText(self, a0: Optional[str]) -> None:
        new_txt = a0 or ""
        old_txt = self.text()
        if new_txt == old_txt:
            return
        self._prev_text = old_txt
        super().setText(new_txt)
        self._update_chevron_position()
        if self.isVisible():
            self._anim_progress = 0.0
            self._elapsed.start()
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        else:
            self._anim_progress = 1.0
        self.update()

    def resizeEvent(self, a0) -> None:
        super().resizeEvent(a0)
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

    def paintEvent(self, a0) -> None:
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
        in_col = QColor(self._text_color)
        in_col.setAlpha(int(255 * ease))
        painter.setPen(in_col)
        in_elided = fm.elidedText(self.text(), Qt.TextElideMode.ElideRight, usable_w)
        y_in = 8.0 * (1.0 - ease)
        painter.drawText(
            QRectF(6.0, y_in, w - 12.0, h),
            Qt.AlignmentFlag.AlignCenter,
            in_elided,
        )
        painter.end()


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

        self.setFixedHeight(self._cover_size + 26)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)
        self._fade_timer.timeout.connect(self._tick_fade)

    @property
    def ambient_color(self) -> QColor:
        return self._ambient_color

    def set_cover_size(self, size: int) -> None:
        self._cover_size = size
        self.setFixedHeight(self._cover_size + 26)
        self._cached_rounded_cover = None
        self._prev_rounded_cover = None
        self.update()

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

            # Center Vinyl Label (Magenta Tint)
            label_grad = QRadialGradient(QPointF(cx, cy), target_size * 0.18)
            label_grad.setColorAt(0.0, QColor("#2a1220"))
            label_grad.setColorAt(0.85, QColor(PALETTE["accent"]))
            label_grad.setColorAt(1.0, QColor("#8f0c40"))

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

        # 1. Rich Dynamic Ambient Halo behind the artwork (smoothly color-interpolated)
        cur_amb = _lerp_color(self._prev_ambient_color, self._ambient_color, ease)
        glow_radius = max(side * 0.85, 155.0)
        center = QPointF(w / 2.0, h / 2.0)
        rad_grad = QRadialGradient(center, glow_radius)

        glow_col = QColor(cur_amb)
        glow_col.setAlpha(95)
        rad_grad.setColorAt(0.0, glow_col)
        glow_mid = QColor(cur_amb)
        glow_mid.setAlpha(42)
        rad_grad.setColorAt(0.58, glow_mid)
        rad_grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(rad_grad))
        painter.drawEllipse(center, glow_radius, glow_radius)

        # 2. Outer Frosted Glass Frame Pedestal around the cover
        frame_rect = QRectF(cover_x - 6, cover_y - 6, side + 12, side + 12)
        frame_path = QPainterPath()
        frame_path.addRoundedRect(frame_rect, self._corner_radius + 5, self._corner_radius + 5)
        painter.setBrush(QColor(255, 255, 255, 10))
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1.0))
        painter.drawPath(frame_path)

        # 3. Deep Drop Shadow under cover
        shadow_rect = QRectF(cover_x + 1, cover_y + 4, side - 2, side)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, self._corner_radius + 1, self._corner_radius + 1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 125))
        painter.drawPath(shadow_path)

        # 4. Draw Rounded Cover Art with 60 FPS Crossfade + Subtle Scale-In
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

        # 5. Inner Specular Rim Outline
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
