"""Track menu chevron button attached to the song title for opening Quick Search."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
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
        self.setFixedSize(18, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hovered = False
        self._active = False

    def set_active(self, active: bool) -> None:
        if self._active != active:
            self._active = active
            self.update()

    def is_active(self) -> bool:
        return self._active

    def set_hovered(self, hovered: bool) -> None:
        if self._hovered != hovered:
            self._hovered = hovered
            self.update()

    def enterEvent(self, event: object) -> None:
        self.set_hovered(True)
        par = self.parent()
        if par is not None and hasattr(par, "set_hovered"):
            par.set_hovered(True)
        super().enterEvent(event)  # type: ignore[arg-type]

    def leaveEvent(self, a0: object) -> None:
        self.set_hovered(False)
        par = self.parent()
        if par is not None and hasattr(par, "set_hovered"):
            # Avoid clearing parent hover if menu is open or mouse is still inside title capsule
            if not getattr(par, "_menu_active", False):
                if hasattr(par, "get_capsule_rect") and hasattr(par, "mapFromGlobal"):
                    r = par.get_capsule_rect()
                    cur_pos = par.mapFromGlobal(self.cursor().pos())
                    if r is not None and r.contains(QPointF(cur_pos)):
                        super().leaveEvent(a0)  # type: ignore[arg-type]
                        return
                par.set_hovered(False)
        super().leaveEvent(a0)  # type: ignore[arg-type]

    def paintEvent(self, a0: object) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        cx = w / 2.0
        # Vertically aligned with font x-height/baseline
        cy = (h / 2.0) + 2.0

        if self._active:
            chev_col = QColor(PALETTE.get("accent", "#EC186C"))
        elif self._hovered:
            chev_col = QColor("#ffffff")
        else:
            chev_col = QColor(160, 172, 195)

        pen = QPen(
            chev_col,
            1.7,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(cx - 3.2, cy - 2.0)
        path.lineTo(cx, cy + 2.0)
        path.lineTo(cx + 3.2, cy - 2.0)
        p.drawPath(path)
        p.end()
