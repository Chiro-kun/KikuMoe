"""Cyber-Moe Close Confirmation Dialog for KikuMoe."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
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
        self.setFixedSize(430, 205)

        self.i18n = i18n or (getattr(parent, "i18n", None) if parent else None) or I18n("it")
        self.setWindowTitle(self.i18n.t("close_dialog_title"))

        self.action: str = "cancel"  # "tray" | "quit" | "cancel"
        self.remember: bool = False

        self._apply_dialog_stylesheet()

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # 1. Custom Cyber-Moe Titlebar
        app_icon = icon or (getattr(parent, "_icon_app", None) if parent else None)
        self._title_bar = CustomTitleBar(self, icon=app_icon)
        self._title_bar._btn_min.setVisible(False)
        self._title_bar._btn_max.setVisible(False)
        self._title_bar._ver_badge.setText("CONFIRM")
        # Ensure titlebar close button cancels
        self._title_bar._btn_close.clicked.disconnect()
        self._title_bar._btn_close.clicked.connect(self._on_cancel)
        outer_layout.addWidget(self._title_bar)

        # 2. Body Container
        body_widget = QWidget(self)
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(20, 16, 20, 18)
        body_layout.setSpacing(14)

        # Text prompt
        self.prompt_label = QLabel(self.i18n.t("close_dialog_text"))
        self.prompt_label.setWordWrap(True)
        self.prompt_label.setStyleSheet(
            "color: #f1f5f9; font-size: 13px; font-weight: 600; line-height: 1.4;"
        )
        body_layout.addWidget(self.prompt_label)

        # Checkbox: Remember Choice
        self.cb_remember = QCheckBox(self.i18n.t("close_remember"))
        self.cb_remember.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_remember.setStyleSheet("font-size: 12px; color: #94a3b8;")
        body_layout.addWidget(self.cb_remember)

        # Buttons row
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.setSpacing(10)

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

        body_layout.addLayout(btn_layout)
        outer_layout.addWidget(body_widget, 1)

        try:
            apply_windows_titlebar_dark_mode(self, True)
        except Exception:
            pass

    def _on_tray(self) -> None:
        self.action = "tray"
        self.remember = self.cb_remember.isChecked()
        self.accept()

    def _on_quit(self) -> None:
        self.action = "quit"
        self.remember = self.cb_remember.isChecked()
        self.accept()

    def _on_cancel(self) -> None:
        self.action = "cancel"
        self.remember = False
        self.reject()

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
        QPushButton#primaryButton {{
            background-color: {accent};
            color: #ffffff;
            border: none;
            border-radius: 8px;
            padding: 7px 16px;
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
            background-color: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.35);
            color: #fca5a5;
            border-radius: 8px;
            padding: 7px 16px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#dangerButton:hover {{
            background-color: rgba(239, 68, 68, 0.28);
            border: 1px solid rgba(239, 68, 68, 0.65);
            color: #ffffff;
        }}
        QPushButton#dangerButton:pressed {{
            background-color: rgba(239, 68, 68, 0.40);
        }}
        QPushButton#cancelButton {{
            background-color: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.12);
            color: #94a3b8;
            border-radius: 8px;
            padding: 7px 14px;
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
