"""
Crisp, anti-aliased vector icon generators for KikuMoe.
Renders official brand and UI action icons (Spotify, YouTube, Apple Music, Copy, History, Chevron)
into QIcon and QPixmap without relying on inconsistent system Unicode emojis.
"""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtSvg import QSvgRenderer

# Official brand SVG definitions
_SPOTIFY_SVG = QByteArray(
    b'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    b'<path fill="#1ED760" d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0z"/>'
    b'<path fill="#0b0e14" d="M17.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/>'  # noqa: E501
    b"</svg>"
)

_YOUTUBE_SVG = QByteArray(
    b'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    b'<path fill="#FF0000" d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814z"/>'  # noqa: E501
    b'<path fill="#FFFFFF" d="M9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>'
    b"</svg>"
)

_APPLE_MUSIC_SVG = QByteArray(
    b'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    b"<defs>"
    b'<linearGradient id="apple_grad" x1="0" y1="0" x2="1" y2="1">'
    b'<stop offset="0%" stop-color="#FA2D48"/>'
    b'<stop offset="100%" stop-color="#FA5570"/>'
    b"</linearGradient>"
    b"</defs>"
    b'<rect width="24" height="24" rx="5.5" fill="url(#apple_grad)"/>'
    b'<path fill="#FFFFFF" d="M17.15 4.35c-.32-.1-.7-.03-.95.18l-6.8 5.67c-.25.21-.4.52-.4.85v5.82c-.52-.35-1.18-.54-1.9-.52-1.71.05-3.1 1.34-3.1 2.87 0 1.58 1.48 2.86 3.3 2.78 1.63-.07 2.95-1.28 3.1-2.73V11.2l5.7-4.75v5.6c-.52-.35-1.18-.54-1.9-.52-1.71.05-3.1 1.34-3.1 2.87 0 1.58 1.48 2.86 3.3 2.78 1.63-.07 2.95-1.28 3.1-2.73V4.9c0-.25-.09-.45-.25-.55z"/>'  # noqa: E501
    b"</svg>"
)

# Cached SVG renderers
_RENDERER_SPOTIFY: QSvgRenderer | None = None
_RENDERER_YOUTUBE: QSvgRenderer | None = None
_RENDERER_APPLE_MUSIC: QSvgRenderer | None = None


def _render_svg(svg_data: QByteArray, size: int) -> QPixmap:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer = QSvgRenderer(svg_data)
    renderer.render(p, QRectF(0.0, 0.0, float(size), float(size)))
    p.end()
    return QPixmap.fromImage(img)


def get_spotify_pixmap(size: int = 16) -> QPixmap:
    """Generate official Spotify green disc with brand-accurate sound waves."""
    return _render_svg(_SPOTIFY_SVG, size)


def get_spotify_icon(size: int = 16) -> QIcon:
    return QIcon(get_spotify_pixmap(size))


def get_youtube_pixmap(size: int = 16) -> QPixmap:
    """Generate official YouTube red badge with centered play triangle."""
    return _render_svg(_YOUTUBE_SVG, size)


def get_youtube_icon(size: int = 16) -> QIcon:
    return QIcon(get_youtube_pixmap(size))


def get_apple_music_pixmap(size: int = 16) -> QPixmap:
    """Generate official Apple Music gradient badge with musical notes."""
    return _render_svg(_APPLE_MUSIC_SVG, size)


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
    cx, cy = s / 2.0, s / 2.0 + 1.5
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
    hw = s * 0.22
    hh = s * 0.13
    path.moveTo(cx - hw, cy - hh)
    path.lineTo(cx, cy + hh)
    path.lineTo(cx + hw, cy - hh)
    p.drawPath(path)
    p.end()
    return QPixmap.fromImage(img)


def get_chevron_down_icon(size: int = 16, color: str = "#94a3b8") -> QIcon:
    return QIcon(get_chevron_down_pixmap(size, color))
