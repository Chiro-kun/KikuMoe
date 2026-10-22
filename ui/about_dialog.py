"""
Cyber-Moe Credits & System Info Dialog for KikuMoe 2.0.0
Displays author credits, official Forgejo & GitHub repositories,
and runtime system diagnostics with copy-to-clipboard functionality.
"""

import os
import platform
from typing import Optional

from PyQt6.QtCore import PYQT_VERSION_STR, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.constants import (
    APP_NAME,
    APP_VERSION,
    AUTHORS,
    LICENSE_NAME,
    URL_FORGEJO,
    URL_GITHUB,
    URL_LISTENMOE,
)
from core.i18n import I18n
from ui.custom_titlebar import CustomTitleBar, install_size_grip
from ui.themes.cyber_moe import PALETTE, get_cyber_moe_stylesheet
from ui.windows_titlebar import apply_windows_titlebar_dark_mode


def get_os_info() -> str:
    """Returns human-friendly OS name and display server info on Linux."""
    system = platform.system()
    release = platform.release()
    if system == "Linux":
        session = os.environ.get("XDG_SESSION_TYPE", "")
        if session:
            return f"Linux {release} ({session.capitalize()})"
        return f"Linux {release}"
    if system == "Windows":
        return f"Windows {release}"
    return f"{system} {release}"


class AboutWidget(QWidget):
    """
    Modular widget displaying KikuMoe identity, author credits,
    official repository links, and system diagnostics inside Cyber-Moe glass cards.
    Can be embedded inside SettingsDialog or hosted in AboutDialog.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        i18n: Optional[I18n] = None,
        backend_name: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.i18n = i18n or I18n("it")
        self._backend_name = backend_name or "Auto"
        self._init_ui()

    def set_backend_name(self, name: str) -> None:
        if name:
            self._backend_name = name
            if hasattr(self, "_lbl_backend_val"):
                self._lbl_backend_val.setText(name)

    def set_i18n(self, i18n: I18n) -> None:
        self.i18n = i18n
        self._refresh_texts()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 2, 0, 2)
        main_layout.setSpacing(8)

        self._apply_widget_stylesheet()

        # ================= 1. Header Card (Brand & Identity) =================
        card_header, header_lay = self._make_card()
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(12)

        # High-res App Logo
        self._logo_lbl = QLabel()
        self._logo_lbl.setFixedSize(46, 46)
        self._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_app_logo()
        header_row.addWidget(self._logo_lbl)

        # App Title & Tagline
        v_title_lay = QVBoxLayout()
        v_title_lay.setContentsMargins(0, 0, 0, 0)
        v_title_lay.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        self._lbl_app_name = QLabel(APP_NAME)
        self._lbl_app_name.setStyleSheet(
            "font-size: 15px; font-weight: 800; color: #ffffff; letter-spacing: 0.8px;"
            " background: transparent; border: none;"
        )
        title_row.addWidget(self._lbl_app_name)

        # Version Pill Badge
        self._lbl_version = QLabel(f"v{APP_VERSION}")
        self._lbl_version.setStyleSheet(
            f"background-color: {PALETTE['accent']}; color: #ffffff; font-size: 10px;"
            " font-weight: 800; border-radius: 8px; padding: 1px 7px; letter-spacing: 0.5px;"
        )
        title_row.addWidget(self._lbl_version)
        title_row.addStretch(1)
        v_title_lay.addLayout(title_row)

        self._lbl_tagline = QLabel(self.i18n.t("about_tagline"))
        self._lbl_tagline.setWordWrap(True)
        self._lbl_tagline.setStyleSheet(
            "font-size: 11px; color: #9ea4ba; font-weight: 500;"
            " background: transparent; border: none;"
        )
        v_title_lay.addWidget(self._lbl_tagline)

        header_row.addLayout(v_title_lay, 1)
        header_lay.addLayout(header_row)
        main_layout.addWidget(card_header)

        # ================= 2. Authors & Credits Card =================
        card_credits, credits_lay = self._make_card(self.i18n.t("about_authors_section"))
        self._card_credits_hdr = credits_lay.itemAt(0).widget()

        # Authors Row
        auth_row = QHBoxLayout()
        auth_row.setContentsMargins(0, 0, 0, 0)
        auth_row.setSpacing(8)
        self._lbl_authors_val = QLabel(f"★  {AUTHORS}")
        self._lbl_authors_val.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #ffffff;"
            " background: transparent; border: none;"
        )
        auth_row.addWidget(self._lbl_authors_val)
        auth_row.addStretch(1)

        self._lbl_license_val = QLabel(LICENSE_NAME)
        self._lbl_license_val.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #a4abc3;"
            " background: rgba(255, 255, 255, 0.06);"
            " border: 1px solid rgba(255, 255, 255, 0.12);"
            " border-radius: 7px; padding: 2px 7px;"
        )
        auth_row.addWidget(self._lbl_license_val)
        credits_lay.addLayout(auth_row)

        # Streaming Attribution Row
        self._lbl_credits_stream = QLabel(self.i18n.t("about_credits_stream"))
        self._lbl_credits_stream.setStyleSheet(
            f"font-size: 11px; font-weight: 500; color: {PALETTE['accent_hover']};"
            " font-style: italic; background: transparent; border: none; padding-top: 2px;"
        )
        credits_lay.addWidget(self._lbl_credits_stream)
        main_layout.addWidget(card_credits)

        # ================= 3. Repositories & Links Card =================
        card_links, links_lay = self._make_card(self.i18n.t("about_links_section"))
        self._card_links_hdr = links_lay.itemAt(0).widget()

        btns_row = QHBoxLayout()
        btns_row.setContentsMargins(0, 2, 0, 2)
        btns_row.setSpacing(8)

        self.btn_forgejo = QPushButton(f"{self.i18n.t('about_link_forgejo')} ↗")
        self.btn_forgejo.setObjectName("secondaryGlassBtn")
        self.btn_forgejo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_forgejo.setFixedHeight(28)
        self.btn_forgejo.setToolTip(URL_FORGEJO)
        self.btn_forgejo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_FORGEJO)))
        btns_row.addWidget(self.btn_forgejo)

        self.btn_github = QPushButton(f"{self.i18n.t('about_link_github')} ↗")
        self.btn_github.setObjectName("secondaryGlassBtn")
        self.btn_github.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_github.setFixedHeight(28)
        self.btn_github.setToolTip(URL_GITHUB)
        self.btn_github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_GITHUB)))
        btns_row.addWidget(self.btn_github)

        self.btn_listenmoe = QPushButton(f"{self.i18n.t('about_link_listenmoe')} ↗")
        self.btn_listenmoe.setObjectName("secondaryGlassBtn")
        self.btn_listenmoe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_listenmoe.setFixedHeight(28)
        self.btn_listenmoe.setToolTip(URL_LISTENMOE)
        self.btn_listenmoe.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_LISTENMOE)))
        btns_row.addWidget(self.btn_listenmoe)

        links_lay.addLayout(btns_row)
        main_layout.addWidget(card_links)

        # ================= 4. System Diagnostics Card =================
        card_sys, sys_lay = self._make_card(self.i18n.t("about_sys_section"))
        self._card_sys_hdr = sys_lay.itemAt(0).widget()

        # Grid-like 2-column info layout
        diag_col_row = QHBoxLayout()
        diag_col_row.setContentsMargins(0, 0, 0, 0)
        diag_col_row.setSpacing(12)

        # Left Column (Backend + Python)
        col_left = QVBoxLayout()
        col_left.setSpacing(4)

        row_be = QHBoxLayout()
        row_be.setSpacing(6)
        self._lbl_backend_key = QLabel(self.i18n.t("about_sys_backend"))
        self._lbl_backend_key.setStyleSheet("color: #8c93aa; font-size: 11px; font-weight: 600;")
        self._lbl_backend_val = QLabel(self._backend_name)
        self._lbl_backend_val.setStyleSheet("color: #e2e6f5; font-size: 11px; font-weight: 700;")
        row_be.addWidget(self._lbl_backend_key)
        row_be.addWidget(self._lbl_backend_val)
        row_be.addStretch(1)
        col_left.addLayout(row_be)

        row_py = QHBoxLayout()
        row_py.setSpacing(6)
        self._lbl_python_key = QLabel(self.i18n.t("about_sys_python"))
        self._lbl_python_key.setStyleSheet("color: #8c93aa; font-size: 11px; font-weight: 600;")
        self._lbl_python_val = QLabel(platform.python_version())
        self._lbl_python_val.setStyleSheet("color: #e2e6f5; font-size: 11px; font-weight: 700;")
        row_py.addWidget(self._lbl_python_key)
        row_py.addWidget(self._lbl_python_val)
        row_py.addStretch(1)
        col_left.addLayout(row_py)

        diag_col_row.addLayout(col_left, 1)

        # Right Column (PyQt + OS)
        col_right = QVBoxLayout()
        col_right.setSpacing(4)

        row_qt = QHBoxLayout()
        row_qt.setSpacing(6)
        self._lbl_pyqt_key = QLabel(self.i18n.t("about_sys_pyqt"))
        self._lbl_pyqt_key.setStyleSheet("color: #8c93aa; font-size: 11px; font-weight: 600;")
        self._lbl_pyqt_val = QLabel(PYQT_VERSION_STR)
        self._lbl_pyqt_val.setStyleSheet("color: #e2e6f5; font-size: 11px; font-weight: 700;")
        row_qt.addWidget(self._lbl_pyqt_key)
        row_qt.addWidget(self._lbl_pyqt_val)
        row_qt.addStretch(1)
        col_right.addLayout(row_qt)

        row_os = QHBoxLayout()
        row_os.setSpacing(6)
        self._lbl_os_key = QLabel(self.i18n.t("about_sys_os"))
        self._lbl_os_key.setStyleSheet("color: #8c93aa; font-size: 11px; font-weight: 600;")
        self._lbl_os_val = QLabel(get_os_info())
        self._lbl_os_val.setStyleSheet("color: #e2e6f5; font-size: 11px; font-weight: 700;")
        row_os.addWidget(self._lbl_os_key)
        row_os.addWidget(self._lbl_os_val)
        row_os.addStretch(1)
        col_right.addLayout(row_os)

        diag_col_row.addLayout(col_right, 1)
        sys_lay.addLayout(diag_col_row)

        # Copy System Info Button
        copy_row = QHBoxLayout()
        copy_row.setContentsMargins(0, 4, 0, 0)
        self.btn_copy = QPushButton(self.i18n.t("about_copy_sys_info"))
        self.btn_copy.setObjectName("secondaryGlassBtn")
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setFixedHeight(28)
        self.btn_copy.clicked.connect(self._copy_system_info)
        copy_row.addWidget(self.btn_copy)
        sys_lay.addLayout(copy_row)

        main_layout.addWidget(card_sys)
        main_layout.addStretch(1)

    def _apply_widget_stylesheet(self) -> None:
        self.setStyleSheet(f"""
        QFrame#settingsCard {{
            background-color: #151826;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-top: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 13px;
        }}
        QLabel#settingsSectionHeader {{
            color: {PALETTE["accent_hover"]};
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 1.1px;
            background: transparent;
            border: none;
            padding-bottom: 2px;
        }}
        QPushButton#secondaryGlassBtn {{
            background-color: rgba(255, 255, 255, 0.07);
            color: #e4e8f6;
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 8px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 700;
        }}
        QPushButton#secondaryGlassBtn:hover {{
            background-color: rgba(236, 24, 108, 0.22);
            border-color: {PALETTE["accent"]};
            color: #ffffff;
        }}
        QPushButton#secondaryGlassBtn:pressed {{
            background-color: rgba(236, 24, 108, 0.35);
        }}
        """)

    def _copy_system_info(self) -> None:
        """Copies formatted diagnostics string to the system clipboard with feedback."""
        info_text = (
            f"{APP_NAME} v{APP_VERSION}\n"
            f"Authors: {AUTHORS}\n"
            f"License: {LICENSE_NAME}\n"
            f"Audio Engine: {self._backend_name}\n"
            f"Python: {platform.python_version()}\n"
            f"PyQt: {PYQT_VERSION_STR}\n"
            f"OS: {get_os_info()}\n"
            f"Forgejo: {URL_FORGEJO}\n"
            f"GitHub: {URL_GITHUB}\n"
        )
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(info_text)
        self.btn_copy.setText(self.i18n.t("about_copied"))
        self.btn_copy.setEnabled(False)
        QTimer.singleShot(2000, self._reset_copy_btn)

    def _reset_copy_btn(self) -> None:
        self.btn_copy.setText(self.i18n.t("about_copy_sys_info"))
        self.btn_copy.setEnabled(True)

    def _refresh_texts(self) -> None:
        self._lbl_tagline.setText(self.i18n.t("about_tagline"))
        if hasattr(self, "_card_credits_hdr") and isinstance(self._card_credits_hdr, QLabel):
            self._card_credits_hdr.setText(self.i18n.t("about_authors_section"))
        if hasattr(self, "_card_links_hdr") and isinstance(self._card_links_hdr, QLabel):
            self._card_links_hdr.setText(self.i18n.t("about_links_section"))
        if hasattr(self, "_card_sys_hdr") and isinstance(self._card_sys_hdr, QLabel):
            self._card_sys_hdr.setText(self.i18n.t("about_sys_section"))
        self._lbl_credits_stream.setText(self.i18n.t("about_credits_stream"))
        self.btn_forgejo.setText(f"{self.i18n.t('about_link_forgejo')} ↗")
        self.btn_github.setText(f"{self.i18n.t('about_link_github')} ↗")
        self.btn_listenmoe.setText(f"{self.i18n.t('about_link_listenmoe')} ↗")
        self._lbl_backend_key.setText(self.i18n.t("about_sys_backend"))
        self._lbl_python_key.setText(self.i18n.t("about_sys_python"))
        self._lbl_pyqt_key.setText(self.i18n.t("about_sys_pyqt"))
        self._lbl_os_key.setText(self.i18n.t("about_sys_os"))
        self.btn_copy.setText(self.i18n.t("about_copy_sys_info"))

    def _load_app_logo(self) -> None:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(root_dir, "icons", "Kikumoe - no txt.png")
        if os.path.isfile(logo_path):
            pix = QPixmap(logo_path)
            if not pix.isNull():
                scaled = pix.scaled(
                    44,
                    44,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._logo_lbl.setPixmap(scaled)
                return
        # Fallback empty / placeholder
        self._logo_lbl.setText("🌸")
        self._logo_lbl.setStyleSheet("font-size: 28px; background: transparent;")

    @staticmethod
    def _make_card(section_title: Optional[str] = None):
        card = QFrame()
        card.setObjectName("settingsCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(13, 10, 13, 11)
        lay.setSpacing(7)

        if section_title:
            hdr = QLabel(section_title)
            hdr.setObjectName("settingsSectionHeader")
            lay.addWidget(hdr)
        return card, lay


class AboutDialog(QDialog):
    """
    Dedicated Cyber-Moe modal/modeless dialog for Credits & Info.
    Can be summoned from the system tray or keyboard shortcuts.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        i18n: Optional[I18n] = None,
        backend_name: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setObjectName("aboutDialogRoot")
        parent_i18n = getattr(parent, "i18n", None) if parent is not None else None
        self.i18n = i18n or parent_i18n or I18n("it")
        self.setWindowTitle(self.i18n.t("about_title"))
        self.setModal(False)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(420, 480)
        self.resize(440, 520)

        self._apply_dialog_stylesheet()

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Custom Cyber-Moe Titlebar with app icon and title
        app_icon = getattr(parent, "_icon_app", None) if parent is not None else None
        self._title_bar = CustomTitleBar(self, icon=app_icon)
        self._title_bar._btn_min.setVisible(False)
        self._title_bar._btn_max.setVisible(False)
        self._title_bar._ver_badge.setText("INFO & CREDITS")
        outer_layout.addWidget(self._title_bar)
        install_size_grip(self)

        # Embedded AboutWidget
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(14, 10, 14, 14)
        body_layout.setSpacing(8)

        self.about_widget = AboutWidget(
            self,
            i18n=self.i18n,
            backend_name=backend_name,
        )
        body_layout.addWidget(self.about_widget, 1)
        outer_layout.addLayout(body_layout)

        try:
            apply_windows_titlebar_dark_mode(self, True)
        except Exception:
            pass

    def keyPressEvent(self, a0) -> None:
        if a0.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(a0)

    def _apply_dialog_stylesheet(self) -> None:
        base_qss = get_cyber_moe_stylesheet(PALETTE["accent"])
        extra_qss = f"""
        QDialog#aboutDialogRoot {{
            background-color: #0c0e17;
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 12px;
        }}
        QFrame#settingsCard {{
            background-color: #151826;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-top: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 13px;
        }}
        QLabel#settingsSectionHeader {{
            color: {PALETTE["accent_hover"]};
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 1.1px;
            background: transparent;
            border: none;
            padding-bottom: 2px;
        }}
        QPushButton#secondaryGlassBtn {{
            background-color: rgba(255, 255, 255, 0.07);
            color: #e4e8f6;
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 8px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 700;
        }}
        QPushButton#secondaryGlassBtn:hover {{
            background-color: rgba(236, 24, 108, 0.22);
            border-color: {PALETTE["accent"]};
            color: #ffffff;
        }}
        QPushButton#secondaryGlassBtn:pressed {{
            background-color: rgba(236, 24, 108, 0.35);
        }}
        """
        self.setStyleSheet(base_qss + extra_qss)
