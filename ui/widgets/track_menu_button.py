"""Track menu chevron button attached to the song title for opening Quick Search."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QPushButton, QWidget

from ui.themes.cyber_moe import PALETTE


class TrackMenuChevronButton(QPushButton):
    """
    Subtle cyber-glass dropdown chevron indicator attached to the song title.
    Glows on hover, opens the Quick Search & Actions menu when clicked.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hovered = False
        self._active = False

    def set_active(self, active: bool) -> None:
        if self._active != active:
            self._active = active
            self.update()

    def is_active(self) -> bool:
        return self._active

    def enterEvent(self, event: object) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)  # type: ignore[arg-type]

    def leaveEvent(self, a0: object) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(a0)  # type: ignore[arg-type]

    def paintEvent(self, a0: object) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        if self._active:
            p.setBrush(QColor(236, 24, 108, 55))
            p.setPen(QPen(QColor(PALETTE.get("accent", "#EC186C")), 1.0))
            p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 5, 5)
        elif self._hovered:
            p.setBrush(QColor(255, 255, 255, 30))
            p.setPen(QPen(QColor(255, 255, 255, 65), 1.0))
            p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 5, 5)

        cx, cy = w / 2.0, h / 2.0
        if self._active:
            chev_col = QColor(PALETTE.get("accent", "#EC186C"))
        elif self._hovered:
            chev_col = QColor("#ffffff")
        else:
            chev_col = QColor(160, 172, 195)

        pen = QPen(
            chev_col,
            1.6,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(cx - 3.5, cy - 1.8)
        path.lineTo(cx, cy + 2.2)
        path.lineTo(cx + 3.5, cy - 1.8)
        p.drawPath(path)
        p.end()
