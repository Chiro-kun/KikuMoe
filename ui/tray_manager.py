from __future__ import annotations

import os
from typing import Callable

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidgetAction,
)

from core.constants import (
    DEFAULT_STATION,
    KEY_CHANNEL,
    KEY_FORMAT,
    KEY_STATION,
    STATION_ANISON,
    STATION_GENSOKYO,
    STATION_LISTENMOE,
    STATION_NEURO21,
    STATION_TRUCKERSFM,
)
from ui.themes.cyber_moe import PALETTE
from ui.vector_icons import (
    get_channel_icon,
    get_codec_icon,
    get_history_icon,
    get_info_icon,
    get_pause_icon,
    get_play_icon,
    get_power_quit_icon,
    get_settings_icon,
    get_station_icon,
    get_stop_icon,
    get_volume_icon,
    get_window_icon,
)


def _make_rounded_pixmap(source: QPixmap, size: int = 46, radius: int = 8) -> QPixmap:
    """Renders a smooth, anti-aliased square pixmap with rounded corners."""
    target = QPixmap(size, size)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(0.0, 0.0, float(size), float(size), float(radius), float(radius))
    painter.setClipPath(path)
    scaled = source.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter.drawPixmap(x, y, scaled)
    painter.end()
    return target


class TrayNowPlayingCard(QFrame):
    """
    Sleek Cyber-Glass card shown at the very top of the system tray menu.
    Displays:
    - Rounded cover art thumbnail (with smooth anti-aliasing and fallback)
    - Station badge pill (e.g. LISTEN.MOE, GENSOKYO RADIO)
    - Session timer pill (e.g. 00:00)
    - Track title (bold, bright white, elided)
    - Artist name (muted slate, elided)
    - Inline glass media action buttons: [Play/Pause], [Stop], [Mute], [History]
    - Subtle "Open KikuMoe ↗" hint label
    Clicking anywhere on the card body (outside buttons) raises the main window
    and dismisses the context menu.
    """

    def __init__(
        self,
        parent: QFrame | None = None,
        menu: QMenu | None = None,
        i18n: object | None = None,
        on_show_window: Callable | None = None,
        on_toggle_play_pause: Callable | None = None,
        on_stop_stream: Callable | None = None,
        on_toggle_mute: Callable | None = None,
        on_history: Callable | None = None,
    ) -> None:
        super().__init__(parent)
        self._menu = menu
        self._i18n = i18n
        self._on_show_window = on_show_window
        self._on_toggle_play_pause = on_toggle_play_pause
        self._on_stop_stream = on_stop_stream
        self._on_toggle_mute = on_toggle_mute
        self._on_history = on_history

        self._raw_title: str = ""
        self._raw_artist: str = ""
        self._raw_station: str = ""
        self._raw_session: str = ""
        self._cover_pixmap: QPixmap | None = None
        self._is_playing: bool = False
        self._is_paused: bool = False
        self._is_muted: bool = False

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(276)

        self._setup_ui()
        self.refresh_theme()

    def _t(self, key: str, fallback: str) -> str:
        if self._i18n is not None and hasattr(self._i18n, "t"):
            try:
                res = self._i18n.t(key)
                if res:
                    return str(res)
            except Exception:
                pass
        return fallback

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Top row: Artwork + Metadata column
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)

        # Cover thumbnail (46x46 px)
        self._cover_lbl = QLabel(self)
        self._cover_lbl.setFixedSize(46, 46)
        self._cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(self._cover_lbl)

        # Metadata column
        meta_col = QVBoxLayout()
        meta_col.setContentsMargins(0, 0, 0, 0)
        meta_col.setSpacing(2)

        # Pill row (Station badge + Session elapsed)
        pill_row = QHBoxLayout()
        pill_row.setContentsMargins(0, 0, 0, 0)
        pill_row.setSpacing(6)

        self._badge_station = QLabel("LISTEN.MOE", self)
        pill_row.addWidget(self._badge_station)

        self._lbl_session = QLabel("00:00", self)
        self._lbl_session.setStyleSheet("color: #8E95A5; font-size: 10px; font-weight: 500;")
        pill_row.addWidget(self._lbl_session)
        pill_row.addStretch()
        meta_col.addLayout(pill_row)

        # Title label
        self._lbl_title = QLabel("KikuMoe", self)
        self._lbl_title.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold;")
        meta_col.addWidget(self._lbl_title)

        # Artist label
        self._lbl_artist = QLabel(self._t("tray_no_track", "Nessun brano in riproduzione"), self)
        self._lbl_artist.setStyleSheet("color: #94A3B8; font-size: 11px;")
        meta_col.addWidget(self._lbl_artist)

        top_row.addLayout(meta_col)
        main_layout.addLayout(top_row)

        # Quick inline action buttons row
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 2, 0, 0)
        btn_row.setSpacing(6)

        accent = PALETTE.get("accent", "#EC186C")

        # Play / Pause button
        self._btn_play = QToolButton(self)
        self._btn_play.setFixedSize(30, 26)
        self._btn_play.setIcon(get_play_icon(14, accent))
        self._btn_play.setToolTip(self._t("play", "Riproduci"))
        if self._on_toggle_play_pause:
            cb_play = self._on_toggle_play_pause
            self._btn_play.clicked.connect(lambda: cb_play())
        btn_row.addWidget(self._btn_play)

        # Stop button
        self._btn_stop = QToolButton(self)
        self._btn_stop.setFixedSize(30, 26)
        self._btn_stop.setIcon(get_stop_icon(13, accent))
        self._btn_stop.setToolTip(self._t("stop", "Stop"))
        if self._on_stop_stream:
            cb_stop = self._on_stop_stream
            self._btn_stop.clicked.connect(lambda: cb_stop())
        btn_row.addWidget(self._btn_stop)

        # Mute button
        self._btn_mute = QToolButton(self)
        self._btn_mute.setFixedSize(30, 26)
        self._btn_mute.setIcon(get_volume_icon(14, "#CBD5E1", muted=False))
        self._btn_mute.setToolTip(self._t("mute", "Muto"))
        if self._on_toggle_mute:
            cb_mute = self._on_toggle_mute
            self._btn_mute.clicked.connect(lambda: cb_mute())
        btn_row.addWidget(self._btn_mute)

        # History button
        self._btn_history = QToolButton(self)
        self._btn_history.setFixedSize(30, 26)
        self._btn_history.setIcon(get_history_icon(14, "#CBD5E1"))
        self._btn_history.setToolTip(self._t("history_button", "Cronologia brani..."))
        if self._on_history:
            cb_hist = self._on_history
            self._btn_history.clicked.connect(lambda: self._trigger_history(cb_hist))
        btn_row.addWidget(self._btn_history)

        btn_row.addStretch()

        # Hint label
        hint_text = self._t("tray_open_app", "Apri KikuMoe ↗")
        self._lbl_hint = QLabel(hint_text, self)
        self._lbl_hint.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 500;")
        btn_row.addWidget(self._lbl_hint)

        main_layout.addLayout(btn_row)

        # Set initial default fallback thumbnail
        self.set_cover_pixmap(None)

    def _trigger_history(self, cb: Callable) -> None:
        try:
            cb()
        finally:
            if self._menu is not None:
                self._menu.close()

    def mouseReleaseEvent(self, a0) -> None:
        if a0 and a0.button() == Qt.MouseButton.LeftButton:
            if self._on_show_window:
                self._on_show_window()
            if self._menu is not None:
                self._menu.close()
        super().mouseReleaseEvent(a0)

    def set_track_info(
        self,
        title: str = "",
        artist: str = "",
        station: str = "",
        session: str = "",
    ) -> None:
        """Updates track metadata and elides text cleanly to prevent overflow."""
        self._raw_title = title or ""
        self._raw_artist = artist or ""
        self._raw_station = station or ""
        self._raw_session = session or ""

        # Update station badge
        st_clean = (self._raw_station or "LISTEN.MOE").upper()
        self._badge_station.setText(st_clean)

        # Update session timer / status
        sess_clean = self._raw_session
        if sess_clean.lower().startswith("sessione:"):
            sess_clean = sess_clean.split(":", 1)[1].strip()
        elif sess_clean.lower().startswith("session:"):
            sess_clean = sess_clean.split(":", 1)[1].strip()
        self._lbl_session.setText(sess_clean or "00:00")
        self._lbl_session.setVisible(bool(sess_clean))

        # Title & Artist with auto-elide
        available_width = 176
        fm_title = QFontMetrics(self._lbl_title.font())
        display_title = (
            fm_title.elidedText(self._raw_title, Qt.TextElideMode.ElideRight, available_width)
            if self._raw_title
            else "KikuMoe"
        )
        self._lbl_title.setText(display_title)
        self._lbl_title.setToolTip(self._raw_title if self._raw_title else "KikuMoe")

        fm_artist = QFontMetrics(self._lbl_artist.font())
        display_artist = (
            fm_artist.elidedText(self._raw_artist, Qt.TextElideMode.ElideRight, available_width)
            if self._raw_artist
            else self._t("tray_no_track", "Nessun brano in riproduzione")
        )
        self._lbl_artist.setText(display_artist)
        self._lbl_artist.setToolTip(self._raw_artist if self._raw_artist else "")

    def set_cover_pixmap(self, pixmap: QPixmap | None) -> None:
        """Sets smooth rounded artwork or falls back to KikuMoe brand icon."""
        self._cover_pixmap = pixmap
        size = 46
        radius = 8

        if pixmap is not None and not pixmap.isNull():
            rounded = _make_rounded_pixmap(pixmap, size=size, radius=radius)
            self._cover_lbl.setPixmap(rounded)
            return

        # Fallback icon
        fallback_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "icons",
            "Kikumoe - no txt.png",
        )
        if os.path.exists(fallback_path):
            src_pm = QPixmap(fallback_path)
            if not src_pm.isNull():
                rounded = _make_rounded_pixmap(src_pm, size=size, radius=radius)
                self._cover_lbl.setPixmap(rounded)
                return

        # Blank rounded fallback canvas if file missing
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)
        p = QPainter(canvas)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(size), float(size), float(radius), float(radius))
        p.fillPath(path, QColor("#1E2235"))
        p.end()
        self._cover_lbl.setPixmap(canvas)

    def update_controls_state(
        self,
        is_playing: bool,
        is_paused: bool,
        is_muted: bool,
    ) -> None:
        """Updates inline button states and icons."""
        self._is_playing = is_playing
        self._is_paused = is_paused
        self._is_muted = is_muted

        accent = PALETTE.get("accent", "#EC186C")
        effective_playing = bool(is_playing and not is_paused)

        if effective_playing:
            self._btn_play.setIcon(get_pause_icon(14, accent))
            self._btn_play.setToolTip(self._t("pause", "Pausa"))
        else:
            self._btn_play.setIcon(get_play_icon(14, accent))
            self._btn_play.setToolTip(self._t("play", "Riproduci"))

        self._btn_stop.setIcon(get_stop_icon(13, accent))

        if is_muted:
            self._btn_mute.setIcon(get_volume_icon(14, "#FF4B6E", muted=True))
            self._btn_mute.setToolTip(self._t("tray_unmute", "Riattiva audio"))
        else:
            self._btn_mute.setIcon(get_volume_icon(14, "#CBD5E1", muted=False))
            self._btn_mute.setToolTip(self._t("tray_mute", "Muto"))

    def refresh_theme(self) -> None:
        """Synchronizes colors and borders with the active Cyber-Moe palette."""
        accent = PALETTE.get("accent", "#EC186C")
        border = PALETTE.get("border_card", "rgba(255, 255, 255, 0.12)")

        self.setStyleSheet(
            f"TrayNowPlayingCard {{ "
            f"  background-color: rgba(255, 255, 255, 0.04); "
            f"  border: 1px solid {border}; "
            f"  border-radius: 10px; "
            f"  margin: 4px; "
            f"}} "
            f"TrayNowPlayingCard:hover {{ "
            f"  background-color: rgba(255, 255, 255, 0.07); "
            f"  border: 1px solid rgba(255, 255, 255, 0.18); "
            f"}}"
        )

        self._cover_lbl.setStyleSheet(
            "border-radius: 8px; background-color: rgba(255, 255, 255, 0.06); "
            "border: 1px solid rgba(255, 255, 255, 0.1);"
        )

        self._badge_station.setStyleSheet(
            f"background-color: rgba(236, 24, 108, 0.22); color: {accent}; "
            "border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: bold; "
            "letter-spacing: 0.5px;"
        )

        btn_style = (
            "QToolButton { background-color: rgba(255, 255, 255, 0.06); "
            "border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; } "
            "QToolButton:hover { background-color: rgba(255, 255, 255, 0.15); "
            "border: 1px solid rgba(255, 255, 255, 0.22); } "
            "QToolButton:pressed { background-color: rgba(255, 255, 255, 0.25); }"
        )
        for b in [self._btn_play, self._btn_stop, self._btn_mute, self._btn_history]:
            b.setStyleSheet(btn_style)

        # Refresh button icons
        self.update_controls_state(self._is_playing, self._is_paused, self._is_muted)
        self._btn_history.setIcon(get_history_icon(14, "#CBD5E1"))


class TrayManager(QObject):
    """
    Incapsula la gestione del QSystemTrayIcon: creazione, menu con Now Playing card,
    visibilità, tooltip, icona e notifiche. Fornisce metodi sicuri con try/except
    per garantire stabilità assoluta.
    """

    def __init__(
        self,
        parent,
        i18n,
        on_show_window: Callable | None = None,
        on_quit: Callable | None = None,
        on_open_settings: Callable | None = None,
        on_change_station: Callable[[str], None] | None = None,
        on_change_channel: Callable[[str], None] | None = None,
        on_change_format: Callable[[str], None] | None = None,
        on_toggle_play_pause: Callable | None = None,
        on_stop_stream: Callable | None = None,
        on_force_stop: Callable | None = None,
        on_toggle_mute: Callable | None = None,
        on_about: Callable | None = None,
    ):
        super().__init__(parent)
        self._parent = parent
        self._i18n = i18n
        self._tray: QSystemTrayIcon | None = None
        self._on_show_window = on_show_window

        def default_quit():
            app = QApplication.instance()
            if app is not None:
                app.quit()

        self._on_quit = on_quit or default_quit
        self._on_open_settings = on_open_settings
        self._on_change_station = on_change_station
        self._on_change_channel = on_change_channel
        self._on_change_format = on_change_format
        self._station_actions: dict[str, QAction] = {}
        self._grp_station: QActionGroup | None = None
        self._act_st: QAction | None = None
        self._on_toggle_play_pause = on_toggle_play_pause
        self._on_stop_stream = on_stop_stream
        self._on_force_stop = on_force_stop
        self._on_toggle_mute = on_toggle_mute
        self._on_about = on_about

        # Now Playing Header Card
        self._card: TrayNowPlayingCard | None = None
        self._card_action: QWidgetAction | None = None

        # Azioni informative backward-compatible
        self._act_info_now: QAction | None = None
        self._act_info_session: QAction | None = None
        self._sep_info: QAction | None = None

        # Azioni di controllo riproduzione
        self._act_play_pause: QAction | None = None
        self._act_stop: QAction | None = None
        self._act_force_stop: QAction | None = None
        self._act_mute: QAction | None = None
        self._act_quit: QAction | None = None
        self._act_settings: QAction | None = None
        self._act_about: QAction | None = None
        self._act_history: QAction | None = None
        self._act_show: QAction | None = None
        self._act_ch: QAction | None = None
        self._act_fmt: QAction | None = None
        self._channel_actions: dict[str, QAction] = {}
        self._format_actions: dict[str, QAction] = {}
        self._grp_channel: QActionGroup | None = None
        self._grp_format: QActionGroup | None = None

        # Intestazioni e separatori di sezione
        self._act_hdr_playback: QAction | None = None
        self._sep_playback_end: QAction | None = None
        self._act_hdr_window: QAction | None = None
        self._sep_window_end: QAction | None = None
        self._act_hdr_prefs: QAction | None = None

        # Icone per i controlli
        self._icons: dict = {}

    def _t(self, key: str, fallback: str) -> str:
        if self._i18n is not None and hasattr(self._i18n, "t"):
            try:
                res = self._i18n.t(key)
                if res:
                    return str(res)
            except Exception:
                pass
        return fallback

    def ensure_tray_enabled(
        self,
        enabled: bool,
        window_icon: QIcon | None = None,
        tooltip: str | None = None,
    ) -> None:
        try:
            if enabled:
                if self._tray is None:
                    icon = window_icon or (
                        self._parent.windowIcon()
                        if hasattr(self._parent, "windowIcon")
                        else QIcon()
                    )
                    self._tray = QSystemTrayIcon(icon, self._parent)
                    menu = QMenu()
                    try:
                        menu.setSeparatorsCollapsible(False)
                    except Exception:
                        pass

                    self._apply_menu_stylesheet(menu)

                    # Font per intestazioni di sezione (maiuscole, bold, letter-spaced)
                    header_font = QFont(menu.font())
                    header_font.setPointSize(9)
                    header_font.setBold(True)
                    header_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)

                    # 1. Now Playing Cyber-Glass Header Card
                    self._card = TrayNowPlayingCard(
                        parent=None,
                        menu=menu,
                        i18n=self._i18n,
                        on_show_window=self._handle_show_window,
                        on_toggle_play_pause=self._on_toggle_play_pause,
                        on_stop_stream=self._on_stop_stream,
                        on_toggle_mute=self._on_toggle_mute,
                        on_history=(
                            self._parent.toggle_history_popover
                            if hasattr(self._parent, "toggle_history_popover")
                            else None
                        ),
                    )
                    self._card_action = QWidgetAction(menu)
                    self._card_action.setDefaultWidget(self._card)
                    menu.addAction(self._card_action)

                    # Backward-compatible dummy hidden actions
                    self._act_info_now = QAction("", self._parent)
                    self._act_info_now.setVisible(False)
                    self._act_info_session = QAction("", self._parent)
                    self._act_info_session.setVisible(False)

                    menu.addSeparator()

                    # 2. Sezione: RIPRODUZIONE
                    txt_hdr_play = self._t("tray_section_playback", "Riproduzione").upper()
                    self._act_hdr_playback = QAction(txt_hdr_play, self._parent)
                    self._act_hdr_playback.setEnabled(False)
                    self._act_hdr_playback.setFont(header_font)
                    menu.addAction(self._act_hdr_playback)

                    accent = PALETTE.get("accent", "#EC186C")
                    text_sec = PALETTE.get("text_secondary", "#CBD5E1")

                    # Play / Pause
                    txt_play_pause = self._t("tray_play_pause", "Play/Pausa")
                    act_play_pause = QAction(txt_play_pause, self._parent)
                    act_play_pause.setIcon(get_play_icon(16, accent))
                    if self._on_toggle_play_pause:
                        cb_play = self._on_toggle_play_pause
                        act_play_pause.triggered.connect(lambda: cb_play())
                    menu.addAction(act_play_pause)
                    self._act_play_pause = act_play_pause

                    # Stop
                    txt_stop = self._t("tray_stop", "Stop")
                    act_stop = QAction(txt_stop, self._parent)
                    act_stop.setIcon(get_stop_icon(16, accent))
                    if self._on_stop_stream:
                        act_stop.triggered.connect(self._on_stop_stream)
                    menu.addAction(act_stop)
                    self._act_stop = act_stop

                    # Muto
                    txt_mute = self._t("tray_mute", "Muto")
                    act_mute = QAction(txt_mute, self._parent)
                    act_mute.setIcon(get_volume_icon(16, text_sec))
                    if self._on_toggle_mute:
                        act_mute.triggered.connect(self._on_toggle_mute)
                    menu.addAction(act_mute)
                    self._act_mute = act_mute

                    # Cronologia brani
                    txt_history = self._t("history_button", "Cronologia brani")
                    act_history = QAction(f"{txt_history}...", self._parent)
                    act_history.setIcon(get_history_icon(16, text_sec))
                    if hasattr(self._parent, "toggle_history_popover"):
                        act_history.triggered.connect(self._parent.toggle_history_popover)
                    menu.addAction(act_history)
                    self._act_history = act_history

                    self._sep_playback_end = menu.addSeparator()

                    # 3. Sezione: FINESTRA
                    txt_hdr_window = self._t("tray_section_window", "Finestra").upper()
                    self._act_hdr_window = QAction(txt_hdr_window, self._parent)
                    self._act_hdr_window.setEnabled(False)
                    self._act_hdr_window.setFont(header_font)
                    menu.addAction(self._act_hdr_window)

                    # Mostra finestra
                    txt_show = self._t("tray_show", "Mostra finestra")
                    act_show = QAction(txt_show, self._parent)
                    act_show.setIcon(get_window_icon(16, text_sec))
                    act_show.triggered.connect(self._handle_show_window)
                    menu.addAction(act_show)
                    self._act_show = act_show

                    # Impostazioni
                    txt_settings = self._t("settings_button", "Impostazioni")
                    act_settings = QAction(txt_settings, self._parent)
                    act_settings.setIcon(get_settings_icon(16, text_sec))
                    if self._on_open_settings:
                        cb_settings = self._on_open_settings
                        act_settings.triggered.connect(lambda: cb_settings())
                    menu.addAction(act_settings)
                    self._act_settings = act_settings

                    # Informazioni su KikuMoe...
                    txt_about = self._t("tray_about", "Informazioni su KikuMoe...")
                    act_about = QAction(txt_about, self._parent)
                    act_about.setIcon(get_info_icon(16, text_sec))
                    if self._on_about:
                        cb_about = self._on_about
                        act_about.triggered.connect(lambda: cb_about())
                    menu.addAction(act_about)
                    self._act_about = act_about

                    self._sep_window_end = menu.addSeparator()

                    # 4. Sezione: PREFERENZE
                    txt_hdr_prefs = self._t("tray_section_preferences", "Preferenze").upper()
                    self._act_hdr_prefs = QAction(txt_hdr_prefs, self._parent)
                    self._act_hdr_prefs.setEnabled(False)
                    self._act_hdr_prefs.setFont(header_font)
                    menu.addAction(self._act_hdr_prefs)

                    # Sottomenu Stazione
                    txt_station = self._t("tray_station", "Stazione")
                    sub_station = QMenu(txt_station, self._parent)
                    self._apply_menu_stylesheet(sub_station)
                    grp_station = QActionGroup(self._parent)
                    grp_station.setExclusive(True)
                    self._grp_station = grp_station
                    self._station_actions.clear()
                    try:
                        current_station = str(
                            self._parent.settings.value(KEY_STATION, DEFAULT_STATION)
                        )
                    except Exception:
                        current_station = DEFAULT_STATION
                    station_items = [
                        ("LISTEN.moe", STATION_LISTENMOE),
                        ("Gensokyo Radio", STATION_GENSOKYO),
                        ("ANISON.FM", STATION_ANISON),
                        ("Neuro 21", STATION_NEURO21),
                        ("TruckersFM", STATION_TRUCKERSFM),
                    ]
                    for name, s_id in station_items:
                        acts = QAction(name, self._parent)
                        acts.setCheckable(True)
                        acts.setChecked(current_station.lower() == s_id.lower())
                        if self._on_change_station:
                            acts.triggered.connect(
                                lambda checked, v=s_id: (
                                    checked
                                    and self._on_change_station
                                    and self._on_change_station(v)
                                )
                            )
                        grp_station.addAction(acts)
                        sub_station.addAction(acts)
                        self._station_actions[s_id] = acts
                    act_st = menu.addMenu(sub_station)
                    self._act_st = act_st
                    if self._act_st is not None:
                        self._act_st.setIcon(get_station_icon(16, text_sec))
                    try:
                        sub_station.aboutToShow.connect(self.sync_stream_settings)
                    except Exception:
                        pass

                    # Sottomenu Canale
                    txt_channel = self._t("tray_channel", "Canale")
                    sub_channel = QMenu(txt_channel, self._parent)
                    self._apply_menu_stylesheet(sub_channel)
                    grp_channel = QActionGroup(self._parent)
                    grp_channel.setExclusive(True)
                    self._grp_channel = grp_channel
                    self._channel_actions.clear()
                    try:
                        current_channel = self._parent.settings.value(KEY_CHANNEL, "J-POP")
                    except Exception:
                        current_channel = "J-POP"
                    for ch in ["J-POP", "K-POP"]:
                        act = QAction(ch, self._parent)
                        act.setCheckable(True)
                        act.setChecked(str(current_channel).strip().upper() == ch.strip().upper())
                        if self._on_change_channel:
                            act.triggered.connect(
                                lambda checked, v=ch: (
                                    checked
                                    and self._on_change_channel
                                    and self._on_change_channel(v)
                                )
                            )
                        grp_channel.addAction(act)
                        sub_channel.addAction(act)
                        self._channel_actions[ch] = act
                    act_ch = menu.addMenu(sub_channel)
                    self._act_ch = act_ch
                    if self._act_ch is not None:
                        self._act_ch.setIcon(get_channel_icon(16, text_sec))
                    try:
                        sub_channel.aboutToShow.connect(self.sync_stream_settings)
                    except Exception:
                        pass

                    # Sottomenu Formato
                    txt_format = self._t("tray_format", "Formato (codec)")
                    sub_format = QMenu(txt_format, self._parent)
                    self._apply_menu_stylesheet(sub_format)
                    grp_format = QActionGroup(self._parent)
                    grp_format.setExclusive(True)
                    self._grp_format = grp_format
                    self._format_actions.clear()
                    try:
                        current_format = self._parent.settings.value(KEY_FORMAT, "Vorbis")
                    except Exception:
                        current_format = "Vorbis"
                    for fmt in ["Vorbis", "Opus", "MP3"]:
                        actf = QAction(fmt, self._parent)
                        actf.setCheckable(True)
                        actf.setChecked(str(current_format).strip().upper() == fmt.strip().upper())
                        if self._on_change_format:
                            actf.triggered.connect(
                                lambda checked, v=fmt: (
                                    checked and self._on_change_format and self._on_change_format(v)
                                )
                            )
                        grp_format.addAction(actf)
                        sub_format.addAction(actf)
                        self._format_actions[fmt] = actf
                    act_fmt = menu.addMenu(sub_format)
                    self._act_fmt = act_fmt
                    if self._act_fmt is not None:
                        self._act_fmt.setIcon(get_codec_icon(16, text_sec))
                    try:
                        sub_format.aboutToShow.connect(self.sync_stream_settings)
                    except Exception:
                        pass

                    # 5. Esci
                    menu.addSeparator()
                    txt_quit = self._t("tray_quit", "Esci")
                    self._act_quit = QAction(txt_quit, self._parent)
                    self._act_quit.setIcon(get_power_quit_icon(16, "#FF4B6E"))
                    if self._on_quit is not None:
                        self._act_quit.triggered.connect(self._on_quit)
                    menu.addAction(self._act_quit)

                    self._tray.setContextMenu(menu)
                    menu.aboutToShow.connect(self._nudge_menu_left)
                    try:
                        menu.aboutToShow.connect(self.sync_stream_settings)
                    except Exception:
                        pass
                    if tooltip:
                        self.update_tooltip(tooltip)
                    self.sync_stream_settings()
                    self._tray.setVisible(True)
                else:
                    self._tray.setVisible(True)
                    if window_icon is not None:
                        self.update_icon(window_icon)
                    if tooltip is not None:
                        self.update_tooltip(tooltip)
                    self.sync_stream_settings()
            else:
                if self._tray is not None:
                    try:
                        self._tray.setVisible(False)
                    except Exception:
                        pass
        except Exception:
            pass

    def _handle_show_window(self) -> None:
        """Restores the main window to the front and activates it."""
        try:
            if self._on_show_window:
                self._on_show_window()
            if hasattr(self._parent, "raise_"):
                self._parent.raise_()
            if hasattr(self._parent, "activateWindow"):
                self._parent.activateWindow()
        except Exception:
            pass

    def set_cover_pixmap(self, pixmap: QPixmap | None) -> None:
        """Forwards album cover art thumbnail to the Now Playing Card."""
        try:
            if self._card is not None:
                self._card.set_cover_pixmap(pixmap)
        except Exception:
            pass

    def sync_stream_settings(
        self,
        channel: str | None = None,
        fmt: str | None = None,
        station: str | None = None,
    ) -> None:
        """Synchronizes the checked state of stream/channel/format actions."""
        try:
            if channel is None:
                try:
                    channel = str(self._parent.settings.value(KEY_CHANNEL, "J-POP"))
                except Exception:
                    channel = "J-POP"
            if fmt is None:
                try:
                    fmt = str(self._parent.settings.value(KEY_FORMAT, "Vorbis"))
                except Exception:
                    fmt = "Vorbis"

            target_channel = str(channel).strip().upper()
            for ch_key, act in self._channel_actions.items():
                should_check = ch_key.strip().upper() == target_channel
                if act.isChecked() != should_check:
                    act.blockSignals(True)
                    act.setChecked(should_check)
                    act.blockSignals(False)

            target_fmt = str(fmt).strip().upper()
            for fmt_key, actf in self._format_actions.items():
                should_check = fmt_key.strip().upper() == target_fmt
                if actf.isChecked() != should_check:
                    actf.blockSignals(True)
                    actf.setChecked(should_check)
                    actf.blockSignals(False)

            if station is None:
                try:
                    station = str(self._parent.settings.value(KEY_STATION, DEFAULT_STATION))
                except Exception:
                    station = DEFAULT_STATION
            target_station = str(station).strip().lower()
            for st_key, acts in self._station_actions.items():
                should_check = st_key.strip().lower() == target_station
                if acts.isChecked() != should_check:
                    acts.blockSignals(True)
                    acts.setChecked(should_check)
                    acts.blockSignals(False)
        except Exception:
            pass

    def update_icon(self, icon: QIcon) -> None:
        try:
            if self._tray is not None and icon is not None:
                self._tray.setIcon(icon)
        except Exception:
            pass

    def update_tooltip(self, text: str) -> None:
        """Updates the system tray tooltip and extracts now playing metadata for the header card."""
        try:
            if self._tray is None or text is None:
                return

            self._tray.setToolTip(text)

            # Extract header, now playing, and session lines
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            info_now = lines[1] if len(lines) > 1 else ""
            info_session = lines[2] if len(lines) > 2 else ""

            # Directly extract title and artist if available on parent
            title = getattr(self._parent, "_current_title", "")
            artist = getattr(self._parent, "_current_artist", "")
            if not title and info_now:
                for sep in [" — ", " – ", " - "]:
                    if sep in info_now:
                        p = info_now.split(sep, 1)
                        title, artist = p[0].strip(), p[1].strip()
                        break
                if not title:
                    title = info_now

            # Extract station name
            station = getattr(self._parent, "station_name", "")
            if not station and hasattr(self._parent, "settings"):
                try:
                    station = str(self._parent.settings.value(KEY_STATION, DEFAULT_STATION))
                except Exception:
                    station = DEFAULT_STATION

            # Update the header card
            if self._card is not None:
                self._card.set_track_info(
                    title=title,
                    artist=artist,
                    station=station,
                    session=info_session,
                )

            # Update backward-compatible hidden actions
            if self._act_info_now is not None:
                self._act_info_now.setText(info_now or "")
            if self._act_info_session is not None:
                self._act_info_session.setText(info_session or "")

        except Exception:
            pass

    def update_controls_icons(self, icons: dict) -> None:
        """Preserved for backward-compatibility while ensuring crisp vector icon fidelity."""
        try:
            self._icons = icons
            self.refresh_theme()
        except Exception:
            pass

    def update_controls_state(self, is_playing: bool, is_paused: bool, is_muted: bool) -> None:
        """Aggiorna testi e icone vettoriali dei controlli in base allo stato corrente."""
        try:
            accent = PALETTE.get("accent", "#EC186C")
            text_sec = PALETTE.get("text_secondary", "#CBD5E1")

            ui_paused = bool(getattr(self._parent, "_ui_paused", False))
            effective_paused = bool(is_paused or ui_paused)
            effective_playing = bool(is_playing and not effective_paused)

            if self._card is not None:
                self._card.update_controls_state(is_playing, effective_paused, is_muted)

            if self._act_play_pause is not None:
                txt = (
                    self._t("pause", "Pausa") if effective_playing else self._t("play", "Riproduci")
                )
                self._act_play_pause.setText(txt)
                self._act_play_pause.setIcon(
                    get_pause_icon(16, accent) if effective_playing else get_play_icon(16, accent)
                )

            if self._act_stop is not None:
                self._act_stop.setIcon(get_stop_icon(16, accent))

            if self._act_mute is not None:
                txtm = (
                    self._t("tray_unmute", "Riattiva audio")
                    if is_muted
                    else self._t("tray_mute", "Muto")
                )
                self._act_mute.setText(txtm)
                self._act_mute.setIcon(
                    get_volume_icon(16, "#FF4B6E", muted=True)
                    if is_muted
                    else get_volume_icon(16, text_sec, muted=False)
                )

        except Exception:
            pass

    def show_message(self, title: str, body: str) -> None:
        try:
            if self._tray is not None:
                self._tray.showMessage(title or "", body or "")
        except Exception:
            pass

    def _apply_menu_stylesheet(self, menu: QMenu) -> None:
        try:
            sep_rgba = PALETTE.get("border_card", "rgba(255, 255, 255, 0.12)")
            hover_rgba = PALETTE.get("accent_menu_hover", "rgba(236, 24, 108, 0.25)")
            bg_pop = PALETTE.get("bg_popover", "#141624")
            text_pri = PALETTE.get("text_primary", "#ffffff")
            text_mut = PALETTE.get("text_muted", "#8E95A5")
            menu.setStyleSheet(
                f"""
                QMenu {{
                    background-color: {bg_pop};
                    border: 1px solid {sep_rgba};
                    border-radius: 10px;
                    padding: 4px 0px;
                    spacing: 2px;
                }}
                QMenu::item {{
                    padding: 6px 28px 6px 10px;
                    border-radius: 6px;
                    margin: 1px 6px;
                    color: {text_pri};
                    font-size: 13px;
                }}
                QMenu::icon {{
                    padding-right: 4px;
                }}
                QMenu::item:enabled:selected {{
                    background-color: {hover_rgba};
                    color: #ffffff;
                }}
                QMenu::item:disabled {{
                    color: {text_mut};
                    background-color: transparent;
                }}
                QMenu::separator {{
                    height: 1px;
                    background-color: {sep_rgba};
                    margin: 6px 12px;
                }}
                """
            )
        except Exception:
            pass

    def refresh_theme(self) -> None:
        """Refreshes menu styling, Now Playing Card, and vector icons with the active theme."""
        try:
            accent = PALETTE.get("accent", "#EC186C")
            text_sec = PALETTE.get("text_secondary", "#CBD5E1")

            if self._tray is not None:
                menu = self._tray.contextMenu()
                if menu is not None:
                    self._apply_menu_stylesheet(menu)
                    for sub in menu.findChildren(QMenu):
                        self._apply_menu_stylesheet(sub)

            if self._card is not None:
                self._card.refresh_theme()

            if self._act_stop is not None:
                self._act_stop.setIcon(get_stop_icon(16, accent))
            if self._act_history is not None:
                self._act_history.setIcon(get_history_icon(16, text_sec))
            if self._act_show is not None:
                self._act_show.setIcon(get_window_icon(16, text_sec))
            if self._act_settings is not None:
                self._act_settings.setIcon(get_settings_icon(16, text_sec))
            if self._act_about is not None:
                self._act_about.setIcon(get_info_icon(16, text_sec))
            if self._act_st is not None:
                self._act_st.setIcon(get_station_icon(16, text_sec))
            if self._act_ch is not None:
                self._act_ch.setIcon(get_channel_icon(16, text_sec))
            if self._act_fmt is not None:
                self._act_fmt.setIcon(get_codec_icon(16, text_sec))
            if self._act_quit is not None:
                self._act_quit.setIcon(get_power_quit_icon(16, "#FF4B6E"))

        except Exception:
            pass

    def has_tray(self) -> bool:
        return self._tray is not None

    def _nudge_menu_left(self):
        """Sposta il menu della tray a sinistra per evitare overflow dei sottomenu."""
        try:
            if self._tray is not None:
                menu = self._tray.contextMenu()
                if menu:
                    QTimer.singleShot(0, lambda: self._do_nudge(menu))
        except Exception:
            pass

    def _do_nudge(self, menu):
        try:
            pos = menu.pos()
            screen = QApplication.screenAt(pos)
            if screen:
                screen_right = screen.availableGeometry().right()
                menu_right = pos.x() + menu.width()
                submenu_width = 160
                if menu_right + submenu_width > screen_right:
                    shift = (menu_right + submenu_width) - screen_right + 8
                    menu.move(pos.x() - shift, pos.y())
        except Exception:
            pass
