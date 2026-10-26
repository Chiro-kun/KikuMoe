"""
Crisp, anti-aliased vector icon generators for KikuMoe.
Renders brand and UI action icons (Spotify, YouTube, Apple Music, Copy, History, Chevron)
into QIcon and QPixmap without relying on inconsistent system Unicode emojis.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)


def get_spotify_pixmap(size: int = 16) -> QPixmap:
    """Generate crisp Spotify green disc with rotated curved audio waves."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = float(size)
    # Spotify green circle (#1ED760)
    p.setBrush(QColor("#1ED760"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(1.0, 1.0, s - 2.0, s - 2.0))

    # Dark sound waves rotated -14 degrees
    p.save()
    p.translate(s / 2.0, s / 2.0)
    p.rotate(-14.0)
    p.translate(-s / 2.0, -s / 2.0)

    p.setBrush(Qt.BrushStyle.NoBrush)
    pen = QPen(
        QColor("#0b0e14"),
        max(1.1, 1.8 * (s / 24.0)),
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
    )
    p.setPen(pen)
    p.drawArc(
        QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.50),
        int(42 * 16),
        int(96 * 16),
    )

    pen.setWidthF(max(1.0, 1.5 * (s / 24.0)))
    p.setPen(pen)
    p.drawArc(
        QRectF(s * 0.27, s * 0.36, s * 0.46, s * 0.44),
        int(42 * 16),
        int(96 * 16),
    )

    pen.setWidthF(max(0.9, 1.3 * (s / 24.0)))
    p.setPen(pen)
    p.drawArc(
        QRectF(s * 0.32, s * 0.50, s * 0.36, s * 0.38),
        int(42 * 16),
        int(96 * 16),
    )

    p.restore()
    p.end()
    return QPixmap.fromImage(img)


def get_spotify_icon(size: int = 16) -> QIcon:
    return QIcon(get_spotify_pixmap(size))


def get_youtube_pixmap(size: int = 16) -> QPixmap:
    """Generate YouTube red rounded badge with centered white play triangle."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = float(size)
    # Red badge
    rect = QRectF(1.0, s * 0.18, s - 2.0, s * 0.64)
    p.setBrush(QColor("#FF0000"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(rect, s * 0.18, s * 0.18)

    # Centered white play triangle
    path = QPainterPath()
    tx = s * 0.40
    ty = s * 0.34
    tw = s * 0.26
    th = s * 0.32
    path.moveTo(tx, ty)
    path.lineTo(tx + tw, ty + th / 2.0)
    path.lineTo(tx, ty + th)
    path.closeSubpath()

    p.setBrush(QColor("#FFFFFF"))
    p.drawPath(path)
    p.end()
    return QPixmap.fromImage(img)


def get_youtube_icon(size: int = 16) -> QIcon:
    return QIcon(get_youtube_pixmap(size))


def get_apple_music_pixmap(size: int = 16) -> QPixmap:
    """Generate Apple Music magenta-gradient badge with white paired musical notes."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = float(size)
    grad = QLinearGradient(0, 0, s, s)
    grad.setColorAt(0.0, QColor("#FA2D48"))
    grad.setColorAt(1.0, QColor("#FA5570"))
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(1.0, 1.0, s - 2.0, s - 2.0), s * 0.22, s * 0.22)

    # Paired notes beam & stems
    pen = QPen(
        QColor("#FFFFFF"),
        max(1.1, 1.8 * (s / 24.0)),
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
    )
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.34, s * 0.68), QPointF(s * 0.34, s * 0.30))
    p.drawLine(QPointF(s * 0.34, s * 0.30), QPointF(s * 0.68, s * 0.22))
    p.drawLine(QPointF(s * 0.68, s * 0.22), QPointF(s * 0.68, s * 0.60))

    p.setBrush(QColor("#FFFFFF"))
    p.drawEllipse(QPointF(s * 0.28, s * 0.68), s * 0.09, s * 0.07)
    p.drawEllipse(QPointF(s * 0.62, s * 0.60), s * 0.09, s * 0.07)
    p.end()
    return QPixmap.fromImage(img)


def get_apple_music_icon(size: int = 16) -> QIcon:
    return QIcon(get_apple_music_pixmap(size))


def get_copy_pixmap(size: int = 16, stroke_color: str = "#CBD5E1") -> QPixmap:
    """Generate dual overlapping sheet copy icon."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = float(size)
    pen = QPen(
        QColor(stroke_color),
        max(1.0, 1.5 * (s / 24.0)),
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
    )
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    # Back document
    p.drawRoundedRect(QRectF(s * 0.32, s * 0.16, s * 0.48, s * 0.52), 2.0, 2.0)
    # Front document
    p.setBrush(QColor("#0e111b"))
    p.drawRoundedRect(QRectF(s * 0.18, s * 0.30, s * 0.48, s * 0.52), 2.0, 2.0)
    p.end()
    return QPixmap.fromImage(img)


def get_copy_icon(size: int = 16, stroke_color: str = "#CBD5E1") -> QIcon:
    return QIcon(get_copy_pixmap(size, stroke_color))


def get_history_pixmap(size: int = 16, color: str = "#ec186c") -> QPixmap:
    """Generate clock history icon."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = float(size)
    cx, cy = s / 2.0, s / 2.0
    pen = QPen(
        QColor(color),
        max(1.1, 1.6 * (s / 24.0)),
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
    )
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    r = s * 0.38
    p.drawEllipse(QRectF(cx - r, cy - r, r * 2.0, r * 2.0))
    p.drawLine(QPointF(cx, cy), QPointF(cx, cy - r * 0.55))
    p.drawLine(QPointF(cx, cy), QPointF(cx + r * 0.48, cy))
    p.end()
    return QPixmap.fromImage(img)


def get_history_icon(size: int = 16, color: str = "#ec186c") -> QIcon:
    return QIcon(get_history_pixmap(size, color))


def get_chevron_down_pixmap(size: int = 16, color: str = "#94a3b8") -> QPixmap:
    """Generate downward chevron vector icon."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = float(size)
    cx, cy = s / 2.0, s / 2.0
    pen = QPen(
        QColor(color),
        max(1.1, 1.6 * (s / 16.0)),
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
    )
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    path = QPainterPath()
    hw = s * 0.24
    hh = s * 0.14
    path.moveTo(cx - hw, cy - hh)
    path.lineTo(cx, cy + hh)
    path.lineTo(cx + hw, cy - hh)
    p.drawPath(path)
    p.end()
    return QPixmap.fromImage(img)


def get_chevron_down_icon(size: int = 16, color: str = "#94a3b8") -> QIcon:
    return QIcon(get_chevron_down_pixmap(size, color))
