from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QApplication, QActionGroup
from PyQt5.QtGui import QIcon
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
                 on_change_format: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self._parent = parent
        self._i18n = i18n
        self._tray: Optional[QSystemTrayIcon] = None
        self._on_show_window = on_show_window
        self._on_quit = on_quit or (lambda: (QApplication.instance() and QApplication.instance().quit()))
        self._on_open_settings = on_open_settings
        self._on_change_channel = on_change_channel
        self._on_change_format = on_change_format

    def ensure_tray_enabled(self, enabled: bool, window_icon: Optional[QIcon] = None, tooltip: Optional[str] = None) -> None:
        try:
            if enabled:
                if self._tray is None:
                    icon = window_icon or (self._parent.windowIcon() if hasattr(self._parent, 'windowIcon') else QIcon())
                    self._tray = QSystemTrayIcon(icon, self._parent)
                    menu = QMenu()
                    try:
                        txt_show = self._i18n.t('tray_show') if hasattr(self._i18n, 't') else 'Show Window'
                    except Exception:
                        txt_show = 'Show Window'
                    act_show = QAction(txt_show, self._parent)
                    if self._on_show_window:
                        act_show.triggered.connect(self._on_show_window)
                    menu.addAction(act_show)

                    # Apri Impostazioni
                    try:
                        txt_settings = self._i18n.t('settings_button') if hasattr(self._i18n, 't') else 'Settings'
                    except Exception:
                        txt_settings = 'Settings'
                    act_settings = QAction(txt_settings, self._parent)
                    if self._on_open_settings:
                        act_settings.triggered.connect(lambda: self._on_open_settings())
                    menu.addAction(act_settings)

                    # Canale (J-POP/K-POP)
                    try:
                        txt_channel = self._i18n.t('tray_channel') if hasattr(self._i18n, 't') else 'Channel'
                    except Exception:
                        txt_channel = 'Channel'
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
                        txt_format = self._i18n.t('tray_format') if hasattr(self._i18n, 't') else 'Format/Codec'
                    except Exception:
                        txt_format = 'Format/Codec'
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
                        txt_quit = self._i18n.t('tray_quit') if hasattr(self._i18n, 't') else 'Quit'
                    except Exception:
                        txt_quit = 'Quit'
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