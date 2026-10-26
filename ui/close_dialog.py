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
    Qt,
)
from PyQt6.QtGui import (
    QCloseEvent,
    QColor,
    QIcon,
    QKeyEvent,
    QLinearGradient,
    QPainter,
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
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(430, 180)

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
        self.cb_remember = QCheckBox(self.i18n.t("close_remember"))
        self.cb_remember.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_remember.setStyleSheet(
            "QCheckBox { font-size: 12px; color: #94a3b8; spacing: 8px; "
            "margin-left: 50px; background: transparent; }\n"
            "QCheckBox:hover { color: #e2e8f0; }"
        )
        body_layout.addWidget(self.cb_remember)
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

        try:
            apply_windows_titlebar_dark_mode(self, True)
        except Exception:
            pass

    def showEvent(self, a0: QShowEvent | None) -> None:
        super().showEvent(a0)
        self._animate_entrance()

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
            background-color: #0c0e17;
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 12px;
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
