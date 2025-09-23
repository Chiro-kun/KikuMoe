from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QApplication, QActionGroup, QWidgetAction, QFrame
from PyQt5.QtGui import QIcon, QFont, QPalette
from PyQt5.QtCore import QObject
from typing import Optional, Callable
from constants import KEY_CHANNEL, KEY_FORMAT

class TrayManager(QObject):
    """
    Incapsula la gestione del QSystemTrayIcon: creazione, menu, visibilità,
    tooltip, icona e notifiche. Fornisce metodi sicuri con try/except per
    evitare crash dell'app a causa della tray.
    """
    def __init__(self, parent, i18n, on_show_window: Optional[Callable] = None, on_quit: Optional[Callable] = None, on_open_settings: Optional[Callable] = None,
                 on_change_channel: Optional[Callable[[str], None]] = None,
                 on_change_format: Optional[Callable[[str], None]] = None,
                 on_toggle_play_pause: Optional[Callable] = None,
                 on_stop_stream: Optional[Callable] = None,
                 on_toggle_mute: Optional[Callable] = None):
        super().__init__(parent)
        self._parent = parent
        self._i18n = i18n
        self._tray: Optional[QSystemTrayIcon] = None
        self._on_show_window = on_show_window
        self._on_quit = on_quit or (lambda: (QApplication.instance() and QApplication.instance().quit()))
        self._on_open_settings = on_open_settings
        self._on_change_channel = on_change_channel
        self._on_change_format = on_change_format
        self._on_toggle_play_pause = on_toggle_play_pause
        self._on_stop_stream = on_stop_stream
        self._on_toggle_mute = on_toggle_mute
        # Azioni informative in cima al menu
        self._act_info_now: Optional[QAction] = None
        self._act_info_session: Optional[QAction] = None
        self._sep_info: Optional[QAction] = None
        # Azioni di controllo riproduzione
        self._act_play_pause: Optional[QAction] = None
        self._act_stop: Optional[QAction] = None
        self._act_mute: Optional[QAction] = None
        # Intestazioni e separatori di sezione
        self._act_hdr_playback: Optional[QAction] = None
        self._sep_playback_end: Optional[QAction] = None
        self._act_hdr_window: Optional[QAction] = None
        self._sep_window_end: Optional[QAction] = None
        self._act_hdr_prefs: Optional[QAction] = None

    def ensure_tray_enabled(self, enabled: bool, window_icon: Optional[QIcon] = None, tooltip: Optional[str] = None) -> None:
        try:
            if enabled:
                if self._tray is None:
                    icon = window_icon or (self._parent.windowIcon() if hasattr(self._parent, 'windowIcon') else QIcon())
                    self._tray = QSystemTrayIcon(icon, self._parent)
                    menu = QMenu()
                    try:
                        menu.setSeparatorsCollapsible(False)
                    except Exception:
                        pass
                    # Effetto hover per evidenziare le voci selezionabili nel menu, con colore dei titoli adattato al tema
                    try:
                        pal = menu.palette()
                        txt_col = pal.color(QPalette.WindowText)
                        bg_col = pal.color(QPalette.Window)
                        lightness = bg_col.lightness() if hasattr(bg_col, 'lightness') else bg_col.value()
                        # Aumenta il contrasto dei separatori: più alto in dark mode
                        alpha = 0.42 if lightness < 128 else 0.20
                        sep_rgba = "rgba(128, 128, 128, 0.65)"
                        hover_rgba = "rgba(0, 120, 215, 0.20)"
                        menu.setStyleSheet(
                            f"""
                            QMenu::item {{ padding: 6px 24px; }}
                            QMenu::item:enabled:selected {{ background-color: {hover_rgba}; }}
                            QMenu::item:disabled {{ background-color: transparent; }}
                            QMenu::separator {{ height: 2px; background: {sep_rgba}; margin: 6px 8px; }}
                            """
                        )
                    except Exception:
                        pass
                    # Font per intestazioni: leggermente più grande e in grassetto
                    try:
                        base_font = menu.font()
                        header_font = QFont(base_font)
                        # Preferisci il point size se disponibile, altrimenti pixel size
                        if base_font.pointSize() > 0:
                            header_font.setPointSize(base_font.pointSize() + 1)
                        elif base_font.pixelSize() > 0:
                            header_font.setPixelSize(base_font.pixelSize() + 2)
                        else:
                            header_font.setPointSize(11)
                        header_font.setBold(True)
                    except Exception:
                        header_font = QFont()
                        header_font.setPointSize(11)
                        header_font.setBold(True)
                    # Prime due righe informative: Now Playing e Sessione (se attiva)
                    lines = tooltip.splitlines() if tooltip else []
                    info_now = lines[1] if len(lines) > 1 else ''
                    info_session = lines[2] if len(lines) > 2 else ''
                    self._act_info_now = QAction(info_now or '', self._parent)
                    self._act_info_now.setEnabled(False)
                    self._act_info_now.setVisible(bool(info_now))
                    menu.addAction(self._act_info_now)
                    self._act_info_session = QAction(info_session or '', self._parent)
                    self._act_info_session.setEnabled(False)
                    self._act_info_session.setVisible(bool(info_session))
                    menu.addAction(self._act_info_session)
                    self._sep_info = menu.addSeparator()
                    self._sep_info.setVisible(bool(info_now or info_session))
                    
                    # Sezione: Playback (intestazione)
                    try:
                        txt_hdr_play = self._i18n.t('tray_section_playback') if hasattr(self._i18n, 't') else 'Riproduzione'
                        if not txt_hdr_play:
                            txt_hdr_play = 'Riproduzione'
                    except Exception:
                        txt_hdr_play = 'Riproduzione'
                    # Intestazione come QAction disabilitata (più compatibile con alcuni menù di tray su Windows)
                    self._act_hdr_playback = QAction(txt_hdr_play, self._parent)
                    self._act_hdr_playback.setEnabled(False)
                    self._act_hdr_playback.setFont(header_font)
                    menu.addAction(self._act_hdr_playback)
                    
                    # Controlli di playback: Play/Pausa, Stop, Muto
                    try:
                        txt_play_pause = self._i18n.t('tray_play_pause') if hasattr(self._i18n, 't') else 'Play/Pausa'
                    except Exception:
                        txt_play_pause = 'Play/Pausa'
                    act_play_pause = QAction(txt_play_pause, self._parent)
                    if self._on_toggle_play_pause:
                        act_play_pause.triggered.connect(lambda: self._on_toggle_play_pause())
                    menu.addAction(act_play_pause)
                    self._act_play_pause = act_play_pause
                    # Stop
                    try:
                        txt_stop = self._i18n.t('tray_stop') if hasattr(self._i18n, 't') else 'Stop'
                    except Exception:
                        txt_stop = 'Stop'
                    act_stop = QAction(txt_stop, self._parent)
                    if self._on_stop_stream:
                        act_stop.triggered.connect(self._on_stop_stream)
                    menu.addAction(act_stop)
                    self._act_stop = act_stop
                    # Muto / Riattiva audio (testo aggiornato dinamicamente altrove)
                    try:
                        txt_mute = self._i18n.t('tray_mute') if hasattr(self._i18n, 't') else 'Muto'
                    except Exception:
                        txt_mute = 'Muto'
                    act_mute = QAction(txt_mute, self._parent)
                    if self._on_toggle_mute:
                        act_mute.triggered.connect(self._on_toggle_mute)
                    menu.addAction(act_mute)
                    self._act_mute = act_mute
                    
                    # Separatore fine sezione Playback
                    self._sep_playback_end = menu.addSeparator()
                    
                    # Sezione: Window (intestazione)
                    try:
                        txt_hdr_window = self._i18n.t('tray_section_window') if hasattr(self._i18n, 't') else 'Finestra'
                        if not txt_hdr_window:
                            txt_hdr_window = 'Finestra'
                    except Exception:
                        txt_hdr_window = 'Finestra'
                    self._act_hdr_window = QAction(txt_hdr_window, self._parent)
                    self._act_hdr_window.setEnabled(False)
                    self._act_hdr_window.setFont(header_font)
                    menu.addAction(self._act_hdr_window)
                    
                    try:
                        txt_show = self._i18n.t('tray_show') if hasattr(self._i18n, 't') else 'Mostra finestra'
                    except Exception:
                        txt_show = 'Mostra finestra'
                    act_show = QAction(txt_show, self._parent)
                    if self._on_show_window:
                        act_show.triggered.connect(self._on_show_window)
                    menu.addAction(act_show)
                    
                    # Apri Impostazioni
                    try:
                        txt_settings = self._i18n.t('settings_button') if hasattr(self._i18n, 't') else 'Impostazioni'
                    except Exception:
                        txt_settings = 'Impostazioni'
                    act_settings = QAction(txt_settings, self._parent)
                    if self._on_open_settings:
                        act_settings.triggered.connect(lambda: self._on_open_settings())
                    # Separatore fine sezione Window
                    self._sep_window_end = menu.addSeparator()
                    # Sezione: Preferences (intestazione)
                    try:
                        txt_hdr_prefs = self._i18n.t('tray_section_preferences') if hasattr(self._i18n, 't') else 'Preferenze'
                        if not txt_hdr_prefs:
                            txt_hdr_prefs = 'Preferenze'
                    except Exception:
                        txt_hdr_prefs = 'Preferenze'
                    self._act_hdr_prefs = QAction(txt_hdr_prefs, self._parent)
                    self._act_hdr_prefs.setEnabled(False)
                    self._act_hdr_prefs.setFont(header_font)
                    menu.addAction(self._act_hdr_prefs)
                    
                    # Canale (J-POP/K-POP)
                    try:
                        txt_channel = self._i18n.t('tray_channel') if hasattr(self._i18n, 't') else 'Canale'
                    except Exception:
                        txt_channel = 'Canale'
                    sub_channel = QMenu(txt_channel, self._parent)
                    grp_channel = QActionGroup(self._parent)
                    grp_channel.setExclusive(True)
                    try:
                        current_channel = self._parent.settings.value(KEY_CHANNEL, 'J-POP')
                    except Exception:
                        current_channel = 'J-POP'
                    for ch in ['J-POP', 'K-POP']:
                        act = QAction(ch, self._parent)
                        act.setCheckable(True)
                        act.setChecked(str(current_channel) == ch)
                        if self._on_change_channel:
                            act.triggered.connect(lambda checked, v=ch: (checked and self._on_change_channel and self._on_change_channel(v)))
                        grp_channel.addAction(act)
                        sub_channel.addAction(act)
                    menu.addMenu(sub_channel)
                    
                    # Formato (Vorbis/MP3)
                    try:
                        txt_format = self._i18n.t('tray_format') if hasattr(self._i18n, 't') else 'Formato/Codec'
                    except Exception:
                        txt_format = 'Formato/Codec'
                    sub_format = QMenu(txt_format, self._parent)
                    grp_format = QActionGroup(self._parent)
                    grp_format.setExclusive(True)
                    try:
                        current_format = self._parent.settings.value(KEY_FORMAT, 'Vorbis')
                    except Exception:
                        current_format = 'Vorbis'
                    for fmt in ['Vorbis', 'MP3']:
                        actf = QAction(fmt, self._parent)
                        actf.setCheckable(True)
                        actf.setChecked(str(current_format) == fmt)
                        if self._on_change_format:
                            actf.triggered.connect(lambda checked, v=fmt: (checked and self._on_change_format and self._on_change_format(v)))
                        grp_format.addAction(actf)
                        sub_format.addAction(actf)
                    menu.addMenu(sub_format)
                    
                    # Esci
                    try:
                        txt_quit = self._i18n.t('tray_quit') if hasattr(self._i18n, 't') else 'Esci'
                    except Exception:
                        txt_quit = 'Esci'
                    menu.addSeparator()
                    act_quit = QAction(txt_quit, self._parent)
                    if self._on_quit:
                        act_quit.triggered.connect(self._on_quit)
                    menu.addAction(act_quit)
                    
                    self._tray.setContextMenu(menu)
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
                        info_now = lines[1] if len(lines) > 1 else ''
                        info_session = lines[2] if len(lines) > 2 else ''
                        # Aggiorna/crea azione Now Playing
                        if self._act_info_now is None:
                            self._act_info_now = QAction(info_now or '', self._parent)
                            self._act_info_now.setEnabled(False)
                            first_action = menu.actions()[0] if menu.actions() else None
                            if first_action is not None:
                                menu.insertAction(first_action, self._act_info_now)
                            else:
                                menu.addAction(self._act_info_now)
                        else:
                            self._act_info_now.setText(info_now or '')
                        self._act_info_now.setVisible(bool(info_now))
                        # Aggiorna/crea azione Sessione
                        if self._act_info_session is None:
                            self._act_info_session = QAction(info_session or '', self._parent)
                            self._act_info_session.setEnabled(False)
                            # Inserisci subito dopo Now Playing
                            after = self._act_info_now
                            if after:
                                menu.insertAction(after, self._act_info_session)
                            else:
                                menu.addAction(self._act_info_session)
                        else:
                            self._act_info_session.setText(info_session or '')
                        self._act_info_session.setVisible(bool(info_session))
                        # Separatore visibile solo se c'è almeno una riga informativa
                        if self._sep_info is None:
                            self._sep_info = menu.addSeparator()
                        self._sep_info.setVisible(bool(info_now or info_session))
                except Exception:
                    pass
        except Exception:
            pass

    def update_controls_state(self, is_playing: bool, is_paused: bool, is_muted: bool) -> None:
        """Aggiorna i testi delle azioni di controllo (Play/Pausa e Muto) in base allo stato corrente."""
        try:
            if self._act_play_pause is not None:
                try:
                    # Applica override UI pausa se presente sul parent
                    ui_paused = bool(getattr(self._parent, '_ui_paused', False))
                    effective_paused = bool(is_paused or ui_paused)
                    effective_playing = bool(is_playing and not effective_paused)
                    txt = self._i18n.t('pause') if effective_playing else self._i18n.t('play')
                except Exception:
                    ui_paused = bool(getattr(self._parent, '_ui_paused', False))
                    effective_paused = bool(is_paused or ui_paused)
                    effective_playing = bool(is_playing and not effective_paused)
                    txt = 'Pause' if effective_playing else 'Play'
                self._act_play_pause.setText(txt)
                try:
                    print(f"[TRAY] update_controls_state: playing={is_playing}, paused={is_paused}, ui_paused={ui_paused} -> effective_playing={effective_playing}, effective_paused={effective_paused} -> set Play/Pause text='{txt}'")
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if self._act_mute is not None:
                try:
                    txtm = self._i18n.t('tray_unmute') if is_muted else self._i18n.t('tray_mute')
                except Exception:
                    txtm = 'Unmute' if is_muted else 'Mute'
                self._act_mute.setText(txtm)
                try:
                    print(f"[TRAY] update_controls_state: muted={is_muted} -> set Mute text='{txtm}'")
                except Exception:
                    pass
        except Exception:
            pass

    def show_message(self, title: str, body: str) -> None:
        try:
            if self._tray is not None:
                self._tray.showMessage(title or '', body or '')
        except Exception:
            pass

    def has_tray(self) -> bool:
        return self._tray is not None