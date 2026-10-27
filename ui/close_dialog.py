"""Cyber-Moe Close Confirmation Dialog for KikuMoe."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
)
from PyQt6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QShowEvent,
)
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import I18n
from ui.custom_titlebar import CustomTitleBar
from ui.themes.cyber_moe import PALETTE, get_cyber_moe_stylesheet
from ui.windows_titlebar import apply_windows_titlebar_dark_mode


class DialogIconBadge(QWidget):
    """Refined cyber-glass badge rendering a glowing power/exit symbol with symmetry."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(36, 36)

    def paintEvent(self, a0: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Glowing translucent squircle background with Cyber glass gradient
        rect = QRectF(1.0, 1.0, 34.0, 34.0)
        grad = QLinearGradient(0.0, 0.0, 0.0, 36.0)
        grad.setColorAt(0.0, QColor(236, 24, 108, 38))
        grad.setColorAt(1.0, QColor(236, 24, 108, 16))
        painter.setBrush(grad)
        painter.setPen(QPen(QColor(255, 71, 151, 85), 1.0))
        painter.drawRoundedRect(rect, 9.0, 9.0)

        # 2. Perfectly symmetric power / standby emblem
        pen = QPen(QColor("#ff4797"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        arc_rect = QRectF(11.0, 12.0, 14.0, 14.0)
        painter.drawArc(arc_rect, int(55 * 16), int(-290 * 16))
        painter.drawLine(QPointF(18.0, 9.0), QPointF(18.0, 16.5))
        painter.end()


class RememberCheckBox(QCheckBox):
    """Compact checkbox with an animated vector checkmark."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(24)
        self._progress = 0.0
        self._hovered = False
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._set_progress)
        self.toggled.connect(self._animate_toggle)

    def sizeHint(self) -> QSize:
        font = QFont(self.font())
        font.setPixelSize(12)
        return QSize(26 + QFontMetrics(font).horizontalAdvance(self.text()), 24)

    def _set_progress(self, value: float) -> None:
        self._progress = float(value)
        self.update()

    def _animate_toggle(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._progress)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(0.5, (self.height() - 18.0) / 2.0, 17.0, 17.0)
        painter.setBrush(QColor("#25293a"))
        focused = self._hovered or self.hasFocus()
        painter.setPen(QPen(QColor(PALETTE["accent"] if focused else "#4a5066")))
        painter.drawRoundedRect(rect, 5, 5)
        if self._progress > 0:
            color = QColor(PALETTE["accent"])
            color.setAlphaF(self._progress)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 5, 5)
            painter.setPen(
                QPen(
                    QColor("#ffffff"),
                    1.8,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            path = QPainterPath()
            x, y = rect.x(), rect.y()
            path.moveTo(x + 4.0, y + 8.8)
            t = min(1.0, self._progress * 2.0)
            path.lineTo(x + 4.0 + 3.0 * t, y + 8.8 + 3.0 * t)
            if self._progress > 0.5:
                t = (self._progress - 0.5) * 2.0
                path.lineTo(x + 7.0 + 6.0 * t, y + 11.8 - 6.0 * t)
            painter.drawPath(path)
        font = QFont(self.font())
        font.setPixelSize(12)
        painter.setFont(font)
        painter.setPen(QColor("#e2e8f0" if self._hovered else "#94a3b8"))
        painter.drawText(
            QRectF(26, 0, max(0, self.width() - 26), self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text(),
        )
        painter.end()


class CloseConfirmDialog(QDialog):
    """Cyber-Moe styled modal dialog asking to minimize to tray or quit the application."""

    def __init__(
        self,
        parent: QWidget | None = None,
        i18n: I18n | None = None,
        icon: QIcon | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("closeConfirmDialogRoot")
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(430)

        self.i18n = i18n or (getattr(parent, "i18n", None) if parent else None) or I18n("it")
        title_text = self.i18n.t("close_dialog_title")
        self.setWindowTitle(title_text)

        self.action: str = "cancel"  # "tray" | "quit" | "cancel"
        self.remember: bool = False
        self._anim_group: QParallelAnimationGroup | None = None
        self._entrance_animated: bool = False
        self._is_closing: bool = False

        self._apply_dialog_stylesheet()

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # 1. Custom Cyber-Moe Titlebar displaying dialog title ("Chiudere l'app?")
        app_icon = icon or (getattr(parent, "_icon_app", None) if parent else None)
        self._title_bar = CustomTitleBar(self, icon=app_icon, title=title_text)
        self._title_bar._btn_min.setVisible(False)
        self._title_bar._btn_max.setVisible(False)
        self.title_lbl = self._title_bar._title_label

        # Re-wire titlebar close button to trigger cancel
        try:
            self._title_bar._btn_close.clicked.disconnect()
        except Exception:
            pass
        self._title_bar._btn_close.clicked.connect(self._on_cancel)
        outer_layout.addWidget(self._title_bar)

        # 2. Main Body Container
        body_widget = QWidget(self)
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(18, 16, 18, 12)
        body_layout.setSpacing(10)

        # Header Row: Symmetrical Icon badge + Prompt Description
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(14)

        self.badge = DialogIconBadge(body_widget)
        header_row.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignCenter)

        prompt_text = self.i18n.t("close_dialog_text")
        self.prompt_label = QLabel(prompt_text)
        self.prompt_label.setWordWrap(True)
        self.prompt_label.setStyleSheet(
            "color: #e2e8f0; font-size: 13px; font-weight: 500; line-height: 1.4; "
            "background: transparent; border: none;"
        )
        header_row.addWidget(self.prompt_label, 1, Qt.AlignmentFlag.AlignVCenter)
        body_layout.addLayout(header_row)

        # Checkbox: Remember Choice (aligned directly under the text column)
        self.cb_remember = RememberCheckBox(self.i18n.t("close_remember"))
        checkbox_row = QHBoxLayout()
        checkbox_row.setContentsMargins(50, 0, 0, 0)
        checkbox_row.addWidget(self.cb_remember, 0, Qt.AlignmentFlag.AlignLeft)
        checkbox_row.addStretch(1)
        body_layout.addLayout(checkbox_row)
        outer_layout.addWidget(body_widget, 1)

        # 3. Action Buttons Footer Bar
        footer_frame = QFrame(self)
        footer_frame.setObjectName("dialogFooter")
        btn_layout = QHBoxLayout(footer_frame)
        btn_layout.setContentsMargins(18, 8, 18, 10)
        btn_layout.setSpacing(8)

        self.btn_cancel = QPushButton(self.i18n.t("settings_cancel"))
        self.btn_cancel.setObjectName("cancelButton")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.btn_cancel)

        btn_layout.addStretch(1)

        self.btn_quit = QPushButton(self.i18n.t("close_option_quit"))
        self.btn_quit.setObjectName("dangerButton")
        self.btn_quit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quit.clicked.connect(self._on_quit)
        btn_layout.addWidget(self.btn_quit)

        self.btn_tray = QPushButton(self.i18n.t("close_option_tray"))
        self.btn_tray.setObjectName("primaryButton")
        self.btn_tray.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tray.clicked.connect(self._on_tray)
        btn_layout.addWidget(self.btn_tray)

        outer_layout.addWidget(footer_frame)

        # Dynamic safe height (>= 186px) preventing Windows WM / Qt geometry collision
        final_h = max(186, self.sizeHint().height())
        self.setFixedSize(430, final_h)

        try:
            apply_windows_titlebar_dark_mode(self, True)
        except Exception:
            pass

    def showEvent(self, a0: QShowEvent | None) -> None:
        super().showEvent(a0)
        self._animate_entrance()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        painter.setBrush(QColor(PALETTE["bg_main"]))
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
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

    def _on_tray(self) -> None:
        self.action = "tray"
        self.remember = self.cb_remember.isChecked()
        self._animate_exit(super().accept)

    def _on_quit(self) -> None:
        self.action = "quit"
        self.remember = self.cb_remember.isChecked()
        self._animate_exit(super().accept)

    def _on_cancel(self) -> None:
        self.action = "cancel"
        self.remember = False
        self._animate_exit(super().reject)

    def keyPressEvent(self, a0: QKeyEvent | None) -> None:
        if a0 is not None:
            if a0.key() == Qt.Key.Key_Escape:
                self._on_cancel()
                return
            if a0.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._on_tray()
                return
        super().keyPressEvent(a0)

    def _apply_dialog_stylesheet(self) -> None:
        accent = PALETTE.get("accent", "#EC186C")
        hover_accent = PALETTE.get("accent_hover", "#FF3388")
        pressed_accent = PALETTE.get("accent_pressed", "#C40C54")
        base_qss = get_cyber_moe_stylesheet(accent)

        extra_qss = f"""
        QDialog#closeConfirmDialogRoot {{
            background: transparent;
            border: none;
        }}
        QFrame#dialogFooter {{
            background-color: rgba(14, 17, 27, 0.70);
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            border-bottom-left-radius: 12px;
            border-bottom-right-radius: 12px;
        }}
        QPushButton#primaryButton {{
            background-color: {accent};
            color: #ffffff;
            border: none;
            border-radius: 8px;
            padding: 6px 16px;
            font-size: 12px;
            font-weight: 700;
        }}
        QPushButton#primaryButton:hover {{
            background-color: {hover_accent};
        }}
        QPushButton#primaryButton:pressed {{
            background-color: {pressed_accent};
        }}
        QPushButton#dangerButton {{
            background-color: rgba(225, 29, 72, 0.14);
            border: 1px solid rgba(225, 29, 72, 0.35);
            color: #fda4af;
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#dangerButton:hover {{
            background-color: rgba(225, 29, 72, 0.26);
            border: 1px solid rgba(225, 29, 72, 0.65);
            color: #ffffff;
        }}
        QPushButton#dangerButton:pressed {{
            background-color: rgba(225, 29, 72, 0.38);
        }}
        QPushButton#cancelButton {{
            background-color: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.12);
            color: #94a3b8;
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 500;
        }}
        QPushButton#cancelButton:hover {{
            background-color: rgba(255, 255, 255, 0.10);
            border: 1px solid rgba(255, 255, 255, 0.25);
            color: #ffffff;
        }}
        QPushButton#cancelButton:pressed {{
            background-color: rgba(255, 255, 255, 0.03);
        }}
        """
        self.setStyleSheet(base_qss + "\n" + extra_qss)
