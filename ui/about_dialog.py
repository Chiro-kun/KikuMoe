"""
Cyber-Moe Credits & System Info Dialog for KikuMoe 2.0.0
Displays author credits, official Forgejo & GitHub repositories,
and runtime system diagnostics with animated action buttons and authentic brand vector icons.
"""

import os
import platform
from typing import Dict, Optional, Tuple

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
    URL_ANISON,
    URL_FORGEJO,
    URL_GENSOKYO,
    URL_GITHUB,
    URL_LISTENMOE,
    URL_NEURO21,
    URL_TELEGRAM,
    URL_TRUCKERSFM,
)
from core.i18n import I18n
from ui.custom_titlebar import CustomTitleBar, install_size_grip
from ui.themes.cyber_moe import PALETTE, accent_qcolor, get_cyber_moe_stylesheet
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
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">\n'
    b'  <g fill="#ffffff">\n'
    b'    <path style="fill-rule:evenodd;clip-rule:evenodd;"\n'
    b'          d="M12,0.296c-6.627,0-12,5.372-12,12c0,5.302,3.438,9.8,8.206,11.387\n'
    b"             c0.6,0.111,0.82-0.26,0.82-0.577c0-0.286-0.011-1.231-0.016-2.234\n"
    b"             c-3.338,0.726-4.043-1.416-4.043-1.416 C4.421,18.069,3.635,17.7,3.635,17.7\n"
    b"             c-1.089-0.745,0.082-0.729,0.082-0.729c1.205,0.085,1.839,1.237,1.839,1.237\n"
    b"             c1.07,1.834,2.807,1.304,3.492,0.997C9.156,18.429,9.467,17.9,9.81,17.6\n"
    b"             c-2.665-0.303-5.467-1.332-5.467-5.93 c0-1.31,0.469-2.381,1.237-3.221\n"
    b"             C5.455,8.146,5.044,6.926,5.696,5.273c0,0,1.008-0.322,3.301,1.23\n"
    b"             C9.954,6.237,10.98,6.104,12,6.099c1.02,0.005,2.047,0.138,3.006,0.404\n"
    b"             c2.29-1.553,3.297-1.23,3.297-1.23 c0.653,1.653,0.242,2.873,0.118,3.176\n"
    b"             c0.769,0.84,1.235,1.911,1.235,3.221c0,4.609-2.807,5.624-5.479,5.921\n"
    b"             c0.43,0.372,0.814,1.103,0.814,2.222c0,1.606-0.014,2.898-0.014,3.293\n"
    b"             c0,0.319,0.216,0.694,0.824,0.576 c4.766-1.589,8.2-6.085,8.2-11.385\n"
    b'             C24,5.669,18.627,0.296,12,0.296z"/>\n'
    b'    <path d="M4.545,17.526c-0.026,0.06-0.12,0.078-0.206,0.037\n'
    b"             c-0.087-0.039-0.136-0.121-0.108-0.18 c0.026-0.061,0.12-0.078,0.207-0.037\n"
    b'             C4.525,17.384,4.575,17.466,4.545,17.526L4.545,17.526z"/>\n'
    b'    <path d="M5.031,18.068c-0.057,0.053-0.169,0.028-0.245-0.055\n'
    b"             c-0.079-0.084-0.093-0.196-0.035-0.249 c0.059-0.053,0.167-0.028,0.246,0.056\n"
    b'             C5.076,17.903,5.091,18.014,5.031,18.068L5.031,18.068z"/>\n'
    b'    <path d="M5.504,18.759c-0.074,0.051-0.194,0.003-0.268-0.103\n'
    b"             c-0.074-0.107-0.074-0.235,0.002-0.286 c0.074-0.051,0.193-0.005,0.268,0.101\n"
    b'             C5.579,18.579,5.579,18.707,5.504,18.759L5.504,18.759z"/>\n'
    b'    <path d="M6.152,19.427c-0.066,0.073-0.206,0.053-0.308-0.046\n'
    b"             c-0.105-0.097-0.134-0.234-0.068-0.307 c0.067-0.073,0.208-0.052,0.311,0.046\n"
    b'             C6.191,19.217,6.222,19.355,6.152,19.427L6.152,19.427z"/>\n'
    b'    <path d="M7.047,19.814c-0.029,0.094-0.164,0.137-0.3,0.097\n'
    b"             C6.611,19.87,6.522,19.76,6.55,19.665 c0.028-0.095,0.164-0.139,0.301-0.096\n"
    b'             C6.986,19.609,7.075,19.719,7.047,19.814L7.047,19.814z"/>\n'
    b'    <path d="M8.029,19.886c0.003,0.099-0.112,0.181-0.255,0.183\n'
    b"             c-0.143,0.003-0.26-0.077-0.261-0.174 c0-0.1,0.113-0.181,0.256-0.184\n"
    b'             C7.912,19.708,8.029,19.788,8.029,19.886L8.029,19.886z"/>\n'
    b'    <path d="M8.943,19.731c0.017,0.096-0.082,0.196-0.224,0.222\n'
    b"             c-0.139,0.026-0.268-0.034-0.286-0.13 c-0.017-0.099,0.084-0.198,0.223-0.224\n"
    b'             C8.797,19.574,8.925,19.632,8.943,19.731L8.943,19.731z"/>\n'
    b"  </g>\n"
    b"</svg>"
)

_TELEGRAM_SVG = QByteArray(
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">\n'
    b'  <circle cx="12" cy="12" r="11.8" fill="#ffffff"/>\n'
    b'  <path fill="#2AABEE" style="fill-rule:evenodd;clip-rule:evenodd;"\n'
    b'        d="M12,0C5.373,0,0,5.373,0,12s5.373,12,12,12s12-5.373,12-12S18.627,0,12,0z\n'
    b"           M17.562,8.161c-0.18,1.897-0.962,6.502-1.359,8.627c-0.168,0.9-0.5,1.201-0.82,1.23\n"
    b"           c-0.697,0.064-1.226-0.461-1.901-0.903 c-1.056-0.692-1.653-1.123-2.678-1.799\n"
    b"           c-1.185-0.781-0.417-1.21,0.258-1.911c0.177-0.184,3.247-2.977,3.307-3.23\n"
    b"           c0.007-0.032,0.015-0.15-0.056-0.212s-0.174-0.041-0.248-0.024\n"
    b"           c-0.106,0.024-1.793,1.139-5.062,3.345 c-0.479,0.329-0.913,0.489-1.302,0.481\n"
    b"           c-0.428-0.009-1.252-0.242-1.865-0.442c-0.751-0.244-1.349-0.374-1.297-0.788\n"
    b"           c0.027-0.216,0.324-0.437,0.892-0.663c3.498-1.524,5.831-2.529,6.998-3.015\n"
    b'           c3.333-1.386,4.025-1.627,4.477-1.635 C17.472,7.214,17.608,7.681,17.562,8.161z"/>\n'
    b"</svg>"
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


_RADIO_ICONS_CACHE: Dict[str, QPixmap] = {}
_APP_LOGO_CACHE: Optional[QPixmap] = None


class AboutActionButton(QPushButton):
    """
    Tactile Cyber-Moe glass action button with:
    - 60 FPS scale bounce on click
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
        self._anim_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)

        # Vector SVG renderers
        self._r_forgejo = QSvgRenderer(_FORGEJO_SVG)
        self._r_github = QSvgRenderer(_GITHUB_SVG)
        self._r_telegram = QSvgRenderer(_TELEGRAM_SVG)
        self._r_copy = QSvgRenderer(_COPY_SVG)
        self._r_check = QSvgRenderer(_CHECK_SVG)

        # High-res brand logos for radios (cached statically across buttons)
        global _RADIO_ICONS_CACHE
        if not _RADIO_ICONS_CACHE:
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            icons_dir = os.path.join(root_dir, "icons")
            icon_files = {
                "listenmoe": "listen.png",
                "gensokyo": "radio_gensokyo.png",
                "anison": "radio_anison.png",
                "neuro21": "radio_neuro21.png",
                "truckersfm": "radio_truckersfm.png",
            }
            for kind, fname in icon_files.items():
                fpath = os.path.join(icons_dir, fname)
                if os.path.isfile(fpath):
                    pix = QPixmap(fpath)
                    if not pix.isNull():
                        _RADIO_ICONS_CACHE[kind] = pix.scaled(
                            16,
                            16,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
        self._pixmaps: Dict[str, QPixmap] = _RADIO_ICONS_CACHE

    def set_icon_kind(self, kind: str) -> None:
        self._icon_kind = kind
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, a0) -> None:
        self._hover = False
        self._pressed = False
        self.update()
        super().leaveEvent(a0)

    def mousePressEvent(self, e) -> None:
        if e is not None and e.button() == Qt.MouseButton.LeftButton:
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
        scales = [0.91, 0.93, 0.96, 1.00, 1.04, 1.05, 1.03, 1.02, 1.01, 1.00]
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
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0

        painter.translate(cx, cy)
        painter.scale(self._scale, self._scale)
        painter.translate(-cx, -cy)

        # Cyber-Moe translucent background and neon accent border on hover
        if self._pressed:
            bg = accent_qcolor(55)
            border = QColor(PALETTE["accent"])
        elif self._hover:
            bg = accent_qcolor(30)
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
            elif self._icon_kind == "telegram":
                self._r_telegram.render(painter, icon_rect)
            elif self._icon_kind in self._pixmaps:
                pix = self._pixmaps[self._icon_kind]
                pw = pix.width()
                ph = pix.height()
                px = int(curr_x + (icon_size - pw) / 2.0)
                py = int((h - ph) / 2.0)
                painter.drawPixmap(px, py, pix)
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
        card_header, header_lay, _ = self._make_card()
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
        self._apply_version_pill_style()
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
        card_credits, credits_lay, self._card_credits_hdr = self._make_card(
            self.i18n.t("about_authors_section")
        )

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
        main_layout.addWidget(card_credits)

        # ================= 3. Repositories & Links Card =================
        card_links, links_lay, self._card_links_hdr = self._make_card(
            self.i18n.t("about_links_section")
        )

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
        btns_row.addWidget(self.btn_forgejo, 1)

        self.btn_github = AboutActionButton(
            "GitHub",
            icon_kind="github",
            is_external=True,
            parent=self,
        )
        self.btn_github.setToolTip(URL_GITHUB)
        self.btn_github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_GITHUB)))
        btns_row.addWidget(self.btn_github, 1)

        self.btn_telegram = AboutActionButton(
            self.i18n.t("about_link_telegram"),
            icon_kind="telegram",
            is_external=True,
            parent=self,
        )
        self.btn_telegram.setToolTip(f"{self.i18n.t('about_link_telegram_tip')}\n{URL_TELEGRAM}")
        self.btn_telegram.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_TELEGRAM)))
        btns_row.addWidget(self.btn_telegram, 1)

        links_lay.addLayout(btns_row)
        main_layout.addWidget(card_links)

        # ================= 4. Powered By / Radio Stations Card =================
        card_powered, powered_lay, self._card_powered_hdr = self._make_card(
            self.i18n.t("about_powered_by_section")
        )

        # Row 1: LISTEN.moe, Gensokyo, Anison
        row_radios_1 = QHBoxLayout()
        row_radios_1.setContentsMargins(0, 0, 0, 0)
        row_radios_1.setSpacing(8)

        self.btn_listenmoe = AboutActionButton(
            self.i18n.t("about_link_listenmoe"),
            icon_kind="listenmoe",
            is_external=True,
            parent=self,
        )
        self.btn_listenmoe.setToolTip(URL_LISTENMOE)
        self.btn_listenmoe.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_LISTENMOE)))
        row_radios_1.addWidget(self.btn_listenmoe, 1)

        self.btn_gensokyo = AboutActionButton(
            self.i18n.t("about_link_gensokyo"),
            icon_kind="gensokyo",
            is_external=True,
            parent=self,
        )
        self.btn_gensokyo.setToolTip(URL_GENSOKYO)
        self.btn_gensokyo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_GENSOKYO)))
        row_radios_1.addWidget(self.btn_gensokyo, 1)

        self.btn_anison = AboutActionButton(
            self.i18n.t("about_link_anison"),
            icon_kind="anison",
            is_external=True,
            parent=self,
        )
        self.btn_anison.setToolTip(URL_ANISON)
        self.btn_anison.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_ANISON)))
        row_radios_1.addWidget(self.btn_anison, 1)
        powered_lay.addLayout(row_radios_1)

        # Dedicated vertical spacer between radio rows
        powered_lay.addSpacing(7)

        # Row 2: Neuro 21, TruckersFM
        row_radios_2 = QHBoxLayout()
        row_radios_2.setContentsMargins(0, 0, 0, 0)
        row_radios_2.setSpacing(8)

        self.btn_neuro21 = AboutActionButton(
            self.i18n.t("about_link_neuro21"),
            icon_kind="neuro21",
            is_external=True,
            parent=self,
        )
        self.btn_neuro21.setToolTip(URL_NEURO21)
        self.btn_neuro21.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_NEURO21)))
        row_radios_2.addWidget(self.btn_neuro21, 1)

        self.btn_truckersfm = AboutActionButton(
            self.i18n.t("about_link_truckersfm"),
            icon_kind="truckersfm",
            is_external=True,
            parent=self,
        )
        self.btn_truckersfm.setToolTip(URL_TRUCKERSFM)
        self.btn_truckersfm.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_TRUCKERSFM)))
        row_radios_2.addWidget(self.btn_truckersfm, 1)
        powered_lay.addLayout(row_radios_2)

        card_powered.setMinimumHeight(114)
        main_layout.addWidget(card_powered)

        # ================= 5. System Diagnostics Card =================
        card_sys, sys_lay, self._card_sys_hdr = self._make_card(self.i18n.t("about_sys_section"))

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

    def _apply_version_pill_style(self) -> None:
        if hasattr(self, "_lbl_version"):
            self._lbl_version.setStyleSheet(
                f"background-color: {PALETTE['accent']}; color: {PALETTE['on_accent']};"
                " font-size: 10px;"
                " font-weight: 800; border-radius: 8px; padding: 1px 7px; letter-spacing: 0.5px;"
            )

    def _apply_widget_stylesheet(self) -> None:
        self.setStyleSheet(f"""
        QFrame#settingsCard {{
            background-color: {PALETTE["bg_surface"]};
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

    def refresh_theme(self) -> None:
        self._apply_widget_stylesheet()
        self._apply_version_pill_style()
        for btn in self.findChildren(AboutActionButton):
            btn.update()
        self.update()

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
        if hasattr(self, "_card_powered_hdr") and isinstance(self._card_powered_hdr, QLabel):
            self._card_powered_hdr.setText(self.i18n.t("about_powered_by_section"))
        if hasattr(self, "_card_sys_hdr") and isinstance(self._card_sys_hdr, QLabel):
            self._card_sys_hdr.setText(self.i18n.t("about_sys_section"))
        self._lbl_backend_key.setText(self.i18n.t("about_sys_backend"))
        self._lbl_python_key.setText(self.i18n.t("about_sys_python"))
        self._lbl_pyqt_key.setText(self.i18n.t("about_sys_pyqt"))
        self._lbl_os_key.setText(self.i18n.t("about_sys_os"))
        self.btn_copy.setText(self.i18n.t("about_copy_sys_info"))
        if hasattr(self, "btn_telegram"):
            self.btn_telegram.setText(self.i18n.t("about_link_telegram"))
            self.btn_telegram.setToolTip(
                f"{self.i18n.t('about_link_telegram_tip')}\n{URL_TELEGRAM}"
            )
        if hasattr(self, "btn_listenmoe"):
            self.btn_listenmoe.setText(self.i18n.t("about_link_listenmoe"))
            self.btn_listenmoe.setToolTip(URL_LISTENMOE)
        if hasattr(self, "btn_gensokyo"):
            self.btn_gensokyo.setText(self.i18n.t("about_link_gensokyo"))
            self.btn_gensokyo.setToolTip(URL_GENSOKYO)
        if hasattr(self, "btn_anison"):
            self.btn_anison.setText(self.i18n.t("about_link_anison"))
            self.btn_anison.setToolTip(URL_ANISON)
        if hasattr(self, "btn_neuro21"):
            self.btn_neuro21.setText(self.i18n.t("about_link_neuro21"))
            self.btn_neuro21.setToolTip(URL_NEURO21)
        if hasattr(self, "btn_truckersfm"):
            self.btn_truckersfm.setText(self.i18n.t("about_link_truckersfm"))
            self.btn_truckersfm.setToolTip(URL_TRUCKERSFM)

    def _load_app_logo(self) -> None:
        global _APP_LOGO_CACHE
        if _APP_LOGO_CACHE is not None and not _APP_LOGO_CACHE.isNull():
            self._logo_lbl.setPixmap(_APP_LOGO_CACHE)
            return

        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(root_dir, "icons", "Kikumoe - no txt.png")
        if os.path.isfile(logo_path):
            pix = QPixmap(logo_path)
            if not pix.isNull():
                _APP_LOGO_CACHE = pix.scaled(
                    44,
                    44,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._logo_lbl.setPixmap(_APP_LOGO_CACHE)
                return
        # Fallback placeholder
        self._logo_lbl.setText("🌸")
        self._logo_lbl.setStyleSheet("font-size: 28px; background: transparent;")

    @staticmethod
    def _make_card(
        section_title: Optional[str] = None,
    ) -> Tuple[QFrame, QVBoxLayout, Optional[QLabel]]:
        card = QFrame()
        card.setObjectName("settingsCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(13, 10, 13, 11)
        lay.setSpacing(7)

        hdr: Optional[QLabel] = None
        if section_title:
            hdr = QLabel(section_title)
            hdr.setObjectName("settingsSectionHeader")
            lay.addWidget(hdr)
        return card, lay, hdr


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
        self.setMinimumSize(450, 560)
        self.resize(470, 610)

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
        if a0 is not None and a0.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(a0)

    def _apply_dialog_stylesheet(self) -> None:
        base_qss = get_cyber_moe_stylesheet(PALETTE["accent"])
        extra_qss = f"""
        QDialog#aboutDialogRoot {{
            background-color: {PALETTE["bg_dialog"]};
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 12px;
        }}
        QFrame#settingsCard {{
            background-color: {PALETTE["bg_surface"]};
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

    def refresh_theme(self) -> None:
        self._apply_dialog_stylesheet()
        if hasattr(self, "_title_bar"):
            self._title_bar.refresh_theme()
        if hasattr(self, "about_widget"):
            self.about_widget.refresh_theme()
        self.update()
