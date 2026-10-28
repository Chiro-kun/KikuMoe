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

from ui.themes.cyber_moe import PALETTE

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
    b'<linearGradient id="apple_grad" x1="0%" y1="0%" x2="0%" y2="100%">'
    b'<stop offset="0%" stop-color="#FA5A6A"/>'
    b'<stop offset="100%" stop-color="#E91E45"/>'
    b"</linearGradient>"
    b"</defs>"
    b'<rect width="24" height="24" rx="5.5" fill="url(#apple_grad)"/>'
    b'<path fill="#fff" d="M17.8 4.4a.9.9 0 0 0-.7-.2l-7.4 1.5a.9.9 0 0 0-.7.9v8.2a3.2 3.2 0 0 0-1.5 0c-1.5.3-2.5 1.3-2.4 2.5.1 1.1 1.4 1.8 2.9 1.5 1.5-.3 2.4-1.2 2.4-2.6V9l6-1.2v5.5a3.2 3.2 0 0 0-1.5 0c-1.5.3-2.5 1.3-2.4 2.5.1 1.1 1.4 1.8 2.9 1.5 1.5-.3 2.4-1.2 2.4-2.6V5.1a.9.9 0 0 0-.3-.7z"/>'  # noqa: E501
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
    p.setBrush(QColor(PALETTE.get("bg_popover", "#0e111b")))
    p.drawRoundedRect(QRectF(s * 0.18, s * 0.30, s * 0.48, s * 0.52), 2.0, 2.0)
    p.end()
    return QPixmap.fromImage(img)


def get_copy_icon(size: int = 16, stroke_color: str = "#CBD5E1") -> QIcon:
    return QIcon(get_copy_pixmap(size, stroke_color))


def get_history_pixmap(size: int = 16, color: str | None = None) -> QPixmap:
    """Generate clock history icon."""
    resolved_color = color or PALETTE.get("accent", "#ec186c")
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = float(size)
    cx, cy = s / 2.0, s / 2.0
    pen = QPen(
        QColor(resolved_color),
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


def get_history_icon(size: int = 16, color: str | None = None) -> QIcon:
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


def get_eyedropper_pixmap(size: int = 16, stroke_color: str = "#E2E8F0") -> QPixmap:
    """Generate crisp vector pipette / eyedropper icon."""
    svg = QByteArray(
        f'<svg viewBox="0 0 24 24" fill="none" stroke="{stroke_color}" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<path d="m2 22 1-1h3l9-9"/>'
        '<path d="M3 21v-3l9-9"/>'
        '<path d="m15 6 3.4-3.4a2.1 2.1 0 1 1 3 3L18 9l.4.4a2.1 2.1 0 1 1-3 3l-3.8-3.8'
        'a2.1 2.1 0 1 1 3-3l.4.4Z"/>'
        "</svg>".encode()
    )
    return _render_svg(svg, size)


def get_eyedropper_icon(size: int = 16, stroke_color: str = "#E2E8F0") -> QIcon:
    return QIcon(get_eyedropper_pixmap(size, stroke_color))


def get_check_pixmap(size: int = 16, stroke_color: str = "#00E676") -> QPixmap:
    """Generate crisp vector checkmark icon."""
    svg = QByteArray(
        f'<svg viewBox="0 0 24 24" fill="none" stroke="{stroke_color}" '
        'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<polyline points="20 6 9 17 4 12"/>'
        "</svg>".encode()
    )
    return _render_svg(svg, size)


def get_check_icon(size: int = 16, stroke_color: str = "#00E676") -> QIcon:
    return QIcon(get_check_pixmap(size, stroke_color))


def get_play_pixmap(size: int = 16, color: str | None = None) -> QPixmap:
    """Generate crisp vector play triangle icon."""
    resolved = color or PALETTE.get("accent", "#EC186C")
    svg = QByteArray(
        f'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        f'<polygon points="6 4 20 12 6 20 6 4" fill="{resolved}"/>'
        "</svg>".encode()
    )
    return _render_svg(svg, size)


def get_play_icon(size: int = 16, color: str | None = None) -> QIcon:
    return QIcon(get_play_pixmap(size, color))


def get_pause_pixmap(size: int = 16, color: str | None = None) -> QPixmap:
    """Generate crisp vector pause dual bar icon."""
    resolved = color or PALETTE.get("accent", "#EC186C")
    svg = QByteArray(
        f'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        f'<rect x="6" y="4" width="4" height="16" rx="1.5" fill="{resolved}"/>'
        f'<rect x="14" y="4" width="4" height="16" rx="1.5" fill="{resolved}"/>'
        "</svg>".encode()
    )
    return _render_svg(svg, size)


def get_pause_icon(size: int = 16, color: str | None = None) -> QIcon:
    return QIcon(get_pause_pixmap(size, color))


def get_stop_pixmap(size: int = 16, color: str | None = None) -> QPixmap:
    """Generate crisp vector stop square icon."""
    resolved = color or PALETTE.get("accent", "#EC186C")
    svg = QByteArray(
        f'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
        f'<rect x="5" y="5" width="14" height="14" rx="2.5" fill="{resolved}"/>'
        "</svg>".encode()
    )
    return _render_svg(svg, size)


def get_stop_icon(size: int = 16, color: str | None = None) -> QIcon:
    return QIcon(get_stop_pixmap(size, color))


def get_volume_pixmap(size: int = 16, color: str | None = None, muted: bool = False) -> QPixmap:
    """Generate crisp vector speaker cone icon with active sound waves or muted slash."""
    resolved = color or "#CBD5E1"
    if muted:
        svg = QByteArray(
            f'<svg viewBox="0 0 24 24" fill="none" stroke="{resolved}" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill="{resolved}"/>'
            '<line x1="23" y1="9" x2="17" y2="15"/>'
            '<line x1="17" y1="9" x2="23" y2="15"/>'
            "</svg>".encode()
        )
    else:
        svg = QByteArray(
            f'<svg viewBox="0 0 24 24" fill="none" stroke="{resolved}" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill="{resolved}"/>'
            '<path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>'
            '<path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>'
            "</svg>".encode()
        )
    return _render_svg(svg, size)


def get_volume_icon(size: int = 16, color: str | None = None, muted: bool = False) -> QIcon:
    return QIcon(get_volume_pixmap(size, color, muted=muted))


def get_window_pixmap(size: int = 16, color: str = "#E2E8F0") -> QPixmap:
    """Generate crisp desktop window layout icon."""
    svg = QByteArray(
        f'<svg viewBox="0 0 24 24" fill="none" stroke="{color}" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<rect x="2" y="3" width="20" height="18" rx="2.5"/>'
        '<line x1="2" y1="8" x2="22" y2="8"/>'
        "</svg>".encode()
    )
    return _render_svg(svg, size)


def get_window_icon(size: int = 16, color: str = "#E2E8F0") -> QIcon:
    return QIcon(get_window_pixmap(size, color))


def get_settings_pixmap(size: int = 16, color: str = "#E2E8F0") -> QPixmap:
    """Generate crisp vector gear icon in bright accent/slate (never an invisible dark circle)."""
    svg = QByteArray(
        f'<svg viewBox="0 0 24 24" fill="none" stroke="{color}" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06'
        "a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09"
        "A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06"
        "a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09"
        "A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06"
        "a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09"
        "a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06"
        "a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09"
        'a1.65 1.65 0 0 0-1.51 1z"/>'
        "</svg>".encode()
    )
    return _render_svg(svg, size)


def get_settings_icon(size: int = 16, color: str = "#E2E8F0") -> QIcon:
    return QIcon(get_settings_pixmap(size, color))


def get_info_pixmap(size: int = 16, color: str = "#E2E8F0") -> QPixmap:
    """Generate crisp circular information icon."""
    svg = QByteArray(
        f'<svg viewBox="0 0 24 24" fill="none" stroke="{color}" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="12" y1="16" x2="12" y2="12"/>'
        f'<circle cx="12" cy="8" r="1" fill="{color}"/>'
        "</svg>".encode()
    )
    return _render_svg(svg, size)


def get_info_icon(size: int = 16, color: str = "#E2E8F0") -> QIcon:
    return QIcon(get_info_pixmap(size, color))


def get_station_pixmap(size: int = 16, color: str = "#E2E8F0") -> QPixmap:
    """Generate crisp radio tower / broadcasting waves icon."""
    svg = QByteArray(
        f'<svg viewBox="0 0 24 24" fill="none" stroke="{color}" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<path d="M4.93 19.07a10 10 0 0 1 0-14.14"/>'
        '<path d="M7.76 16.24a6 6 0 0 1 0-8.48"/>'
        '<path d="M16.24 7.76a6 6 0 0 1 0 8.48"/>'
        '<path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>'
        f'<circle cx="12" cy="12" r="1.5" fill="{color}"/>'
        '<path d="M12 14v7"/>'
        "</svg>".encode()
    )
    return _render_svg(svg, size)


def get_station_icon(size: int = 16, color: str = "#E2E8F0") -> QIcon:
    return QIcon(get_station_pixmap(size, color))


def get_channel_pixmap(size: int = 16, color: str = "#E2E8F0") -> QPixmap:
    """Generate crisp musical notes channel icon."""
    svg = QByteArray(
        f'<svg viewBox="0 0 24 24" fill="none" stroke="{color}" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<path d="M9 18V5l12-2v13"/>'
        '<circle cx="6" cy="18" r="3"/>'
        '<circle cx="18" cy="16" r="3"/>'
        "</svg>".encode()
    )
    return _render_svg(svg, size)


def get_channel_icon(size: int = 16, color: str = "#E2E8F0") -> QIcon:
    return QIcon(get_channel_pixmap(size, color))


def get_codec_pixmap(size: int = 16, color: str = "#E2E8F0") -> QPixmap:
    """Generate crisp sound waveform codec icon."""
    svg = QByteArray(
        f'<svg viewBox="0 0 24 24" fill="none" stroke="{color}" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>'
        "</svg>".encode()
    )
    return _render_svg(svg, size)


def get_codec_icon(size: int = 16, color: str = "#E2E8F0") -> QIcon:
    return QIcon(get_codec_pixmap(size, color))


def get_power_quit_pixmap(size: int = 16, color: str = "#FF4B6E") -> QPixmap:
    """Generate crisp standby power emblem quit icon in rose/crimson."""
    svg = QByteArray(
        f'<svg viewBox="0 0 24 24" fill="none" stroke="{color}" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<path d="M18.36 6.64a9 9 0 1 1-12.73 0"/>'
        '<line x1="12" y1="2" x2="12" y2="12"/>'
        "</svg>".encode()
    )
    return _render_svg(svg, size)


def get_power_quit_icon(size: int = 16, color: str = "#FF4B6E") -> QIcon:
    return QIcon(get_power_quit_pixmap(size, color))
