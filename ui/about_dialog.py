"""
Cyber-Moe Credits & System Info Dialog for KikuMoe 2.0.0
Displays author credits, official Forgejo & GitHub repositories,
and runtime system diagnostics with animated action buttons and authentic brand vector icons.
"""

import os
import platform
from typing import Optional

from PyQt6.QtCore import PYQT_VERSION_STR, QByteArray, QPointF, QRectF, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtSvg import QSvgRenderer
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

# Vector SVG assets for authentic brand icons and feedback glyphs
_FORGEJO_SVG = QByteArray(
    b"""<svg viewBox="0 0 212 212" xmlns="http://www.w3.org/2000/svg">
  <g transform="translate(6,6)">
    <path d="M58 168 v-98 a50 50 0 0 1 50-50 h20" fill="none" stroke="#ff6600"
          stroke-width="25" stroke-linecap="round" />
    <path d="M58 168 v-30 a50 50 0 0 1 50-50 h20" fill="none" stroke="#d40000"
          stroke-width="25" stroke-linecap="round" />
    <circle cx="142" cy="20" r="18" fill="none" stroke="#ff6600" stroke-width="16" />
    <circle cx="142" cy="88" r="18" fill="none" stroke="#d40000" stroke-width="16" />
    <circle cx="58" cy="180" r="18" fill="none" stroke="#d40000" stroke-width="16" />
  </g>
</svg>"""
)

_GITHUB_SVG = QByteArray(
    b'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">\n'
    b'  <path fill="#ffffff" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504'
    b'.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369'
    b'-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53'
    b'1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22'
    b'-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272'
    b'.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504'
    b'.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028'
    b'1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0'
    b'1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22'
    b'6.484 17.522 2 12 2z"/>\n'
    b'</svg>'
)

_COPY_SVG = QByteArray(
    b"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <path fill="none" stroke="#d0d5ea" stroke-width="2.2" stroke-linecap="round"
        stroke-linejoin="round"
        d="M8 4v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7.242a2 2 0 0 0-.602-1.43L16.08 2.57
           A2 2 0 0 0 14.65 2H10a2 2 0 0 0-2 2z"/>
  <path fill="none" stroke="#d0d5ea" stroke-width="2.2" stroke-linecap="round"
        stroke-linejoin="round" d="M16 4h-2a2 2 0 0 0-2 2v1M4 8v12a2 2 0 0 0 2 2h8"/>
</svg>"""
)

_CHECK_SVG = QByteArray(
    b"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <path fill="none" stroke="#00e676" stroke-width="2.8" stroke-linecap="round"
        stroke-linejoin="round" d="M20 6L9 17l-5-5"/>
</svg>"""
)


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


class AboutActionButton(QPushButton):
    """
    Tactile Cyber-Moe glass action button with:
    - 60 FPS scale bounce on click (0.90 -> 0.94 -> 1.04 -> 1.01 -> 1.00)
    - Smooth hover glow & border illumination
    - Vector SVG / Pixmap brand icon rendered alongside text
    """

    def __init__(
        self,
        text: str = "",
        icon_kind: str = "",
        is_external: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        self._icon_kind = icon_kind
        self._is_external = is_external
        self._hover = False
        self._pressed = False
        self._scale = 1.0
        self._step = 0
        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)

        # Vector SVG renderers
        self._r_forgejo = QSvgRenderer(_FORGEJO_SVG)
        self._r_github = QSvgRenderer(_GITHUB_SVG)
        self._r_copy = QSvgRenderer(_COPY_SVG)
        self._r_check = QSvgRenderer(_CHECK_SVG)

        # High-res sakura headphones icon for LISTEN.moe
        self._listen_pix: Optional[QPixmap] = None
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(root_dir, "icons", "Kikumoe - no txt.png")
        if os.path.isfile(logo_path):
            pix = QPixmap(logo_path)
            if not pix.isNull():
                self._listen_pix = pix.scaled(
                    17,
                    17,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

    def set_icon_kind(self, kind: str) -> None:
        self._icon_kind = kind
        self.update()

    def enterEvent(self, a0) -> None:
        self._hover = True
        self.update()
        super().enterEvent(a0)

    def leaveEvent(self, a0) -> None:
        self._hover = False
        self._pressed = False
        self.update()
        super().leaveEvent(a0)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._step = 1
            self._scale = 0.90
            if not self._anim_timer.isActive():
                self._anim_timer.start()
            self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(e)

    def _tick_anim(self) -> None:
        scales = [0.90, 0.94, 1.04, 1.01, 1.0]
        if 0 < self._step <= len(scales):
            self._scale = scales[self._step - 1]
            self._step += 1
        else:
            self._scale = 1.0
            self._step = 0
            self._anim_timer.stop()
        self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0

        painter.translate(cx, cy)
        painter.scale(self._scale, self._scale)
        painter.translate(-cx, -cy)

        # Cyber-Moe translucent background and neon accent border on hover
        if self._pressed:
            bg = QColor(236, 24, 108, 55)
            border = QColor(PALETTE["accent"])
        elif self._hover:
            bg = QColor(236, 24, 108, 30)
            border = QColor(PALETTE["accent"])
        else:
            bg = QColor(255, 255, 255, 14)
            border = QColor(255, 255, 255, 30)

        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.1))
        painter.drawRoundedRect(rect, 8.0, 8.0)

        # Compute label and icon positioning
        txt = self.text()
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()
        txt_w = fm.horizontalAdvance(txt)
        txt_h = fm.capHeight()

        icon_size = 16.0
        icon_pad = 6.0 if self._icon_kind else 0.0
        ext_w = 9.0 if self._is_external else 0.0

        total_content_w = (
            (icon_size + icon_pad if self._icon_kind else 0)
            + txt_w
            + (4.0 + ext_w if self._is_external else 0)
        )
        start_x = max(6.0, (w - total_content_w) / 2.0)

        # 1. Render Icon
        curr_x = start_x
        if self._icon_kind:
            icon_rect = QRectF(curr_x, (h - icon_size) / 2.0, icon_size, icon_size)
            if self._icon_kind == "forgejo":
                self._r_forgejo.render(painter, icon_rect)
            elif self._icon_kind == "github":
                self._r_github.render(painter, icon_rect)
            elif self._icon_kind == "listenmoe" and self._listen_pix:
                painter.drawPixmap(
                    int(curr_x),
                    int((h - icon_size) / 2.0),
                    int(icon_size),
                    int(icon_size),
                    self._listen_pix,
                )
            elif self._icon_kind == "copy":
                self._r_copy.render(painter, icon_rect)
            elif self._icon_kind == "check":
                self._r_check.render(painter, icon_rect)
            curr_x += icon_size + icon_pad

        # 2. Render Text
        painter.setPen(QColor("#ffffff" if (self._hover or self._pressed) else "#e2e6f5"))
        txt_y = (h + txt_h) / 2.0 - 1.0
        painter.drawText(QPointF(curr_x, txt_y), txt)
        curr_x += txt_w

        # 3. Render External Link Glyph ↗
        if self._is_external:
            pen = QPen(QColor(PALETTE["accent_hover"] if self._hover else "#8c93aa"), 1.3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            chev_x = curr_x + 4.0
            chev_y = (h - 7.0) / 2.0
            path = QPainterPath()
            path.moveTo(chev_x, chev_y + 6.0)
            path.lineTo(chev_x + 6.0, chev_y)
            path.moveTo(chev_x + 2.5, chev_y)
            path.lineTo(chev_x + 6.0, chev_y)
            path.lineTo(chev_x + 6.0, chev_y + 3.5)
            painter.drawPath(path)

        painter.end()


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

        # Tactile animated buttons with official brand icons
        self.btn_forgejo = AboutActionButton(
            "Forgejo",
            icon_kind="forgejo",
            is_external=True,
            parent=self,
        )
        self.btn_forgejo.setToolTip(URL_FORGEJO)
        self.btn_forgejo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_FORGEJO)))
        btns_row.addWidget(self.btn_forgejo)

        self.btn_github = AboutActionButton(
            "GitHub",
            icon_kind="github",
            is_external=True,
            parent=self,
        )
        self.btn_github.setToolTip(URL_GITHUB)
        self.btn_github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_GITHUB)))
        btns_row.addWidget(self.btn_github)

        self.btn_listenmoe = AboutActionButton(
            "LISTEN.moe",
            icon_kind="listenmoe",
            is_external=True,
            parent=self,
        )
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

        # Animated Copy System Info Button
        copy_row = QHBoxLayout()
        copy_row.setContentsMargins(0, 4, 0, 0)
        self.btn_copy = AboutActionButton(
            self.i18n.t("about_copy_sys_info"),
            icon_kind="copy",
            parent=self,
        )
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
        """)

    def _copy_system_info(self) -> None:
        """Copies formatted diagnostics string to the system clipboard with tactile feedback."""
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
        self.btn_copy.set_icon_kind("check")
        self.btn_copy.setText(self.i18n.t("about_copied"))
        self.btn_copy.setEnabled(False)
        QTimer.singleShot(2000, self._reset_copy_btn)

    def _reset_copy_btn(self) -> None:
        self.btn_copy.set_icon_kind("copy")
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
        # Fallback placeholder
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
        """
        self.setStyleSheet(base_qss + extra_qss)
