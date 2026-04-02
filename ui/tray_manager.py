from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QFont, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


from core.constants import KEY_CHANNEL, KEY_FORMAT


class TrayManager(QObject):
    """
    Incapsula la gestione del QSystemTrayIcon: creazione, menu, visibilità,
    tooltip, icona e notifiche. Fornisce metodi sicuri con try/except per
    evitare crash dell'app a causa della tray.
    """

    def __init__(
        self,
        parent,
        i18n,
        on_show_window: Optional[Callable] = None,
        on_quit: Optional[Callable] = None,
        on_open_settings: Optional[Callable] = None,
        on_change_channel: Optional[Callable[[str], None]] = None,
        on_change_format: Optional[Callable[[str], None]] = None,
        on_toggle_play_pause: Optional[Callable] = None,
        on_stop_stream: Optional[Callable] = None,
        on_force_stop: Optional[Callable] = None,
        on_toggle_mute: Optional[Callable] = None,
    ):
        super().__init__(parent)
        self._parent = parent
        self._i18n = i18n
        self._tray: Optional[QSystemTrayIcon] = None
        self._on_show_window = on_show_window

        def default_quit():
            app = QApplication.instance()
            if app is not None:
                app.quit()

        self._on_quit = on_quit or default_quit
        self._on_open_settings = on_open_settings
        self._on_change_channel = on_change_channel
        self._on_change_format = on_change_format
        self._on_toggle_play_pause = on_toggle_play_pause
        self._on_stop_stream = on_stop_stream
        self._on_force_stop = on_force_stop
        self._on_toggle_mute = on_toggle_mute
        # Azioni informative in cima al menu
        self._act_info_now: Optional[QAction] = None
        self._act_info_session: Optional[QAction] = None
        self._sep_info: Optional[QAction] = None
        # Azioni di controllo riproduzione
        self._act_play_pause: Optional[QAction] = None
        self._act_stop: Optional[QAction] = None
        self._act_force_stop: Optional[QAction] = None
        self._act_mute: Optional[QAction] = None
        self._act_quit: Optional[QAction] = None
        self._act_ch: Optional[QAction] = None
        self._act_fmt: Optional[QAction] = None
        # Intestazioni e separatori di sezione
        self._act_hdr_playback: Optional[QAction] = None
        self._sep_playback_end: Optional[QAction] = None
        self._act_hdr_window: Optional[QAction] = None
        self._sep_window_end: Optional[QAction] = None
        self._act_hdr_prefs: Optional[QAction] = None
        # Icone per i controlli
        self._icons: dict = {}

    def ensure_tray_enabled(
        self, enabled: bool, window_icon: Optional[QIcon] = None, tooltip: Optional[str] = None
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
                    # Effetto hover per evidenziare le voci selezionabili nel menu,
                    # con colore dei titoli adattato al tema
                    try:
                        sep_rgba = "rgba(255, 255, 255, 0.12)"
                        hover_rgba = "rgba(194, 24, 91, 0.25)"
                        menu.setStyleSheet(
                            f"""
                            QMenu {{
                                background-color: #1a1a1a;
                                border: 1px solid #333333;
                                padding: 6px 0px;
                                spacing: 4px;
                            }}
                            QMenu::item {{
                                padding: 6px 32px 6px 8px;
                                border-radius: 4px;
                                margin: 1px 6px;
                                color: #e0e0e0;
                                font-size: 13px;
                            }}
                            QMenu::icon {{
                                padding-right: 2px;
                            }}
                            QMenu::item:enabled:selected {{
                                background-color: {hover_rgba};
                                color: #ffffff;
                            }}
                            QMenu::item:disabled {{
                                color: #666666;
                                background-color: transparent;
                            }}
                            QMenu::separator {{
                                height: 1px;
                                background-color: {sep_rgba};
                                margin: 8px 14px;
                            }}
                            """
                        )
                    except Exception:
                        pass
                    # Font per intestazioni: leggermente più grande e in grassetto
                    try:
                        base_font = menu.font()
                        header_font = QFont(base_font)
                        # Standard text with bold for headers instead of increased size
                        header_font.setBold(True)
                        header_font.setPointSize(
                            base_font.pointSize() if base_font.pointSize() > 0 else 10
                        )
                    except Exception:
                        header_font = QFont()
                        header_font.setPointSize(11)
                        header_font.setBold(True)
                    # Prime due righe informative: Now Playing e Sessione (se attiva)
                    lines = tooltip.splitlines() if tooltip else []
                    info_now = lines[1] if len(lines) > 1 else ""
                    info_session = lines[2] if len(lines) > 2 else ""
                    self._act_info_now = QAction(info_now or "", self._parent)
                    self._act_info_now.setEnabled(False)
                    self._act_info_now.setVisible(bool(info_now))
                    menu.addAction(self._act_info_now)
                    self._act_info_session = QAction(info_session or "", self._parent)
                    self._act_info_session.setEnabled(False)
                    self._act_info_session.setVisible(bool(info_session))
                    menu.addAction(self._act_info_session)
                    self._sep_info = menu.addSeparator()
                    if self._sep_info is not None:
                        self._sep_info.setVisible(bool(info_now or info_session))

                    # Sezione: Playback (intestazione)
                    try:
                        txt_hdr_play = (
                            self._i18n.t("tray_section_playback")
                            if hasattr(self._i18n, "t")
                            else "Riproduzione"
                        )
                        if not txt_hdr_play:
                            txt_hdr_play = "Riproduzione"
                    except Exception:
                        txt_hdr_play = "Riproduzione"
                    # Intestazione come QAction disabilitata
                    # (più compatibile con alcuni menù di tray su Windows)
                    self._act_hdr_playback = QAction(txt_hdr_play, self._parent)
                    self._act_hdr_playback.setEnabled(False)
                    self._act_hdr_playback.setFont(header_font)
                    menu.addAction(self._act_hdr_playback)

                    # Controlli di playback: Play/Pausa, Stop, Muto
                    try:
                        txt_play_pause = (
                            self._i18n.t("tray_play_pause")
                            if hasattr(self._i18n, "t")
                            else "Play/Pausa"
                        )
                    except Exception:
                        txt_play_pause = "Play/Pausa"
                    act_play_pause = QAction(txt_play_pause, self._parent)
                    if self._on_toggle_play_pause:
                        cb_play = self._on_toggle_play_pause
                        act_play_pause.triggered.connect(lambda: cb_play())
                    menu.addAction(act_play_pause)
                    self._act_play_pause = act_play_pause
                    # Stop
                    try:
                        txt_stop = self._i18n.t("tray_stop") if hasattr(self._i18n, "t") else "Stop"
                    except Exception:
                        txt_stop = "Stop"
                    act_stop = QAction(txt_stop, self._parent)
                    if self._on_stop_stream:
                        act_stop.triggered.connect(self._on_stop_stream)
                    menu.addAction(act_stop)
                    self._act_stop = act_stop
                    # Muto / Riattiva audio (testo aggiornato dinamicamente altrove)
                    try:
                        txt_mute = self._i18n.t("tray_mute") if hasattr(self._i18n, "t") else "Muto"
                    except Exception:
                        txt_mute = "Muto"
                    act_mute = QAction(txt_mute, self._parent)
                    if self._on_toggle_mute:
                        act_mute.triggered.connect(self._on_toggle_mute)
                    menu.addAction(act_mute)
                    self._act_mute = act_mute

                    # Separatore fine sezione Playback
                    self._sep_playback_end = menu.addSeparator()

                    # Sezione: Window (intestazione)
                    try:
                        txt_hdr_window = (
                            self._i18n.t("tray_section_window")
                            if hasattr(self._i18n, "t")
                            else "Finestra"
                        )
                        if not txt_hdr_window:
                            txt_hdr_window = "Finestra"
                    except Exception:
                        txt_hdr_window = "Finestra"
                    self._act_hdr_window = QAction(txt_hdr_window, self._parent)
                    self._act_hdr_window.setEnabled(False)
                    self._act_hdr_window.setFont(header_font)
                    menu.addAction(self._act_hdr_window)

                    try:
                        txt_show = (
                            self._i18n.t("tray_show")
                            if hasattr(self._i18n, "t")
                            else "Mostra finestra"
                        )
                    except Exception:
                        txt_show = "Mostra finestra"
                    act_show = QAction(txt_show, self._parent)
                    if self._on_show_window:
                        act_show.triggered.connect(self._on_show_window)
                    menu.addAction(act_show)

                    # Apri Impostazioni
                    try:
                        txt_settings = (
                            self._i18n.t("settings_button")
                            if hasattr(self._i18n, "t")
                            else "Impostazioni"
                        )
                    except Exception:
                        txt_settings = "Impostazioni"
                    act_settings = QAction(txt_settings, self._parent)
                    if self._on_open_settings:
                        cb_settings = self._on_open_settings
                        act_settings.triggered.connect(lambda: cb_settings())
                    # Separatore fine sezione Window
                    self._sep_window_end = menu.addSeparator()
                    # Sezione: Preferences (intestazione)
                    try:
                        txt_hdr_prefs = (
                            self._i18n.t("tray_section_preferences")
                            if hasattr(self._i18n, "t")
                            else "Preferenze"
                        )
                        if not txt_hdr_prefs:
                            txt_hdr_prefs = "Preferenze"
                    except Exception:
                        txt_hdr_prefs = "Preferenze"
                    self._act_hdr_prefs = QAction(txt_hdr_prefs, self._parent)
                    self._act_hdr_prefs.setEnabled(False)
                    self._act_hdr_prefs.setFont(header_font)
                    menu.addAction(self._act_hdr_prefs)

                    # Canale (J-POP/K-POP)
                    try:
                        txt_channel = (
                            self._i18n.t("tray_channel") if hasattr(self._i18n, "t") else "Canale"
                        )
                    except Exception:
                        txt_channel = "Canale"
                    sub_channel = QMenu(txt_channel, self._parent)
                    grp_channel = QActionGroup(self._parent)
                    grp_channel.setExclusive(True)
                    try:
                        current_channel = self._parent.settings.value(KEY_CHANNEL, "J-POP")
                    except Exception:
                        current_channel = "J-POP"
                    for ch in ["J-POP", "K-POP"]:
                        act = QAction(ch, self._parent)
                        act.setCheckable(True)
                        act.setChecked(str(current_channel) == ch)
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
                    act_ch = menu.addMenu(sub_channel)
                    self._act_ch = act_ch
                    if "channel" in self._icons and self._act_ch is not None:
                        self._act_ch.setIcon(self._icons["channel"])

                    # Formato (Vorbis/MP3)
                    try:
                        txt_format = (
                            self._i18n.t("tray_format")
                            if hasattr(self._i18n, "t")
                            else "Formato/Codec"
                        )
                    except Exception:
                        txt_format = "Formato/Codec"
                    sub_format = QMenu(txt_format, self._parent)
                    grp_format = QActionGroup(self._parent)
                    grp_format.setExclusive(True)
                    try:
                        current_format = self._parent.settings.value(KEY_FORMAT, "Vorbis")
                    except Exception:
                        current_format = "Vorbis"
                    for fmt in ["Vorbis", "MP3"]:
                        actf = QAction(fmt, self._parent)
                        actf.setCheckable(True)
                        actf.setChecked(str(current_format) == fmt)
                        if self._on_change_format:
                            actf.triggered.connect(
                                lambda checked, v=fmt: (
                                    checked and self._on_change_format and self._on_change_format(v)
                                )
                            )
                        grp_format.addAction(actf)
                        sub_format.addAction(actf)
                    act_fmt = menu.addMenu(sub_format)
                    self._act_fmt = act_fmt
                    if "codec" in self._icons and self._act_fmt is not None:
                        self._act_fmt.setIcon(self._icons["codec"])

                    # Esci
                    try:
                        txt_quit = self._i18n.t("tray_quit") if hasattr(self._i18n, "t") else "Esci"
                    except Exception:
                        txt_quit = "Esci"
                    menu.addSeparator()
                    self._act_quit = QAction(txt_quit, self._parent)
                    if "quit" in self._icons:
                        self._act_quit.setIcon(self._icons["quit"])
                    if self._on_quit is not None:
                        self._act_quit.triggered.connect(self._on_quit)
                    menu.addAction(self._act_quit)

                    self._tray.setContextMenu(menu)
                    # Sposta il menu a sinistra per evitare che i sottomenu escano dallo schermo
                    menu.aboutToShow.connect(self._nudge_menu_left)
                    if tooltip:
                        self.update_tooltip(tooltip)
                    self._tray.setVisible(True)
                else:
                    # già creato: assicurati sia visibile e aggiornato
                    self._tray.setVisible(True)
                    if window_icon is not None:
                        self.update_icon(window_icon)
                    if tooltip is not None:
                        self.update_tooltip(tooltip)
            else:
                if self._tray is not None:
                    try:
                        self._tray.setVisible(False)
                    except Exception:
                        pass
        except Exception:
            pass

    def update_icon(self, icon: QIcon) -> None:
        try:
            if self._tray is not None and icon is not None:
                self._tray.setIcon(icon)
        except Exception:
            pass

    def update_tooltip(self, text: str) -> None:
        try:
            if self._tray is not None and text is not None:
                self._tray.setToolTip(text)
                try:
                    menu = self._tray.contextMenu()
                    if menu is not None:
                        lines = text.splitlines() if text else []
                        info_now = lines[1] if len(lines) > 1 else ""
                        info_session = lines[2] if len(lines) > 2 else ""
                        # Aggiorna/crea azione Now Playing
                        if self._act_info_now is None:
                            self._act_info_now = QAction(info_now or "", self._parent)
                            self._act_info_now.setEnabled(False)
                            first_action = menu.actions()[0] if menu.actions() else None
                            if first_action is not None:
                                menu.insertAction(first_action, self._act_info_now)
                            else:
                                menu.addAction(self._act_info_now)
                        else:
                            self._act_info_now.setText(info_now or "")
                        self._act_info_now.setVisible(bool(info_now))
                        # Aggiorna/crea azione Sessione
                        if self._act_info_session is None:
                            self._act_info_session = QAction(info_session or "", self._parent)
                            self._act_info_session.setEnabled(False)
                            # Inserisci subito dopo Now Playing
                            after = self._act_info_now
                            if after:
                                menu.insertAction(after, self._act_info_session)
                            else:
                                menu.addAction(self._act_info_session)
                        else:
                            self._act_info_session.setText(info_session or "")
                        self._act_info_session.setVisible(bool(info_session))
                        # Separatore visibile solo se c'è almeno una riga informativa
                        if self._sep_info is None:
                            self._sep_info = menu.addSeparator()
                        if self._sep_info is not None:
                            self._sep_info.setVisible(bool(info_now or info_session))
                except Exception:
                    pass
        except Exception:
            pass

    def update_controls_icons(self, icons: dict) -> None:
        """Aggiorna i riferimenti alle icone caricate e tintate."""
        try:
            self._icons = icons
            # Forza aggiornamento immediato icone se visibili
            if "stop" in icons and self._act_stop:
                self._act_stop.setIcon(icons["stop"])
            if "force_stop" in icons and self._act_force_stop:
                self._act_force_stop.setIcon(icons["force_stop"])
            if "channel" in icons and self._act_ch:
                self._act_ch.setIcon(icons["channel"])
            if "codec" in icons and self._act_fmt:
                self._act_fmt.setIcon(icons["codec"])
            if "quit" in icons and self._act_quit:
                self._act_quit.setIcon(icons["quit"])
        except Exception:
            pass

    def update_controls_state(self, is_playing: bool, is_paused: bool, is_muted: bool) -> None:
        """Aggiorna i testi delle azioni di controllo in base allo stato corrente."""
        try:
            if self._act_play_pause is not None:
                try:
                    # Applica override UI pausa se presente sul parent
                    ui_paused = bool(getattr(self._parent, "_ui_paused", False))
                    effective_paused = bool(is_paused or ui_paused)
                    effective_playing = bool(is_playing and not effective_paused)
                    txt = self._i18n.t("pause") if effective_playing else self._i18n.t("play")
                except Exception:
                    ui_paused = bool(getattr(self._parent, "_ui_paused", False))
                    effective_paused = bool(is_paused or ui_paused)
                    effective_playing = bool(is_playing and not effective_paused)
                    txt = "Pause" if effective_playing else "Play"
                self._act_play_pause.setText(txt)
                if "play" in self._icons and "pause" in self._icons:
                    self._act_play_pause.setIcon(
                        self._icons["pause"] if effective_playing else self._icons["play"]
                    )

        except Exception:
            pass
        try:
            if self._act_mute is not None:
                try:
                    txtm = self._i18n.t("tray_unmute") if is_muted else self._i18n.t("tray_mute")
                except Exception:
                    txtm = "Unmute" if is_muted else "Mute"
                self._act_mute.setText(txtm)
                if "mute" in self._icons and "unmute" in self._icons:
                    self._act_mute.setIcon(
                        self._icons["mute"] if is_muted else self._icons["unmute"]
                    )

        except Exception:
            pass

    def show_message(self, title: str, body: str) -> None:
        try:
            if self._tray is not None:
                self._tray.showMessage(title or "", body or "")
        except Exception:
            pass

    def has_tray(self) -> bool:
        return self._tray is not None

    def _nudge_menu_left(self):
        """Sposta il menu della tray a sinistra per evitare overflow dei sottomenu."""
        try:
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
                # Se il menu + sottomenu potrebbe uscire, sposta a sinistra
                submenu_width = 150  # larghezza stimata dei sottomenu
                if menu_right + submenu_width > screen_right:
                    shift = (menu_right + submenu_width) - screen_right + 8
                    menu.move(pos.x() - shift, pos.y())
        except Exception:
            pass
