from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QProgressBar, QShortcut,
    QSystemTrayIcon, QMenu, QAction, QStyle, QDialog
)
from PyQt5.QtCore import pyqtSignal, Qt, QSettings, QTimer
from PyQt5.QtGui import QKeySequence, QIcon
import os
import sys
from i18n import I18n
from ws_client import NowPlayingWS
from player_vlc import PlayerVLC
from config import STREAMS
from settings import SettingsDialog

# App identity
APP_NAME = "KikuMoe"
APP_VERSION = "1.0"
APP_TITLE = f"{APP_NAME} {APP_VERSION}"

class ListenMoePlayer(QWidget):
    status_changed = pyqtSignal(str)
    now_playing_changed = pyqtSignal(str)
    buffering_progress = pyqtSignal(int)
    buffering_visible = pyqtSignal(bool)

    def __init__(self):
        super().__init__()

        # settings
        self.settings = QSettings('KikuMoe', 'ListenMoePlayer')

        # i18n
        saved_lang = self.settings.value('lang', 'it')
        self.i18n = I18n(saved_lang if saved_lang in ('it', 'en') else 'it')
        self._lang_map = {"Italiano": 'it', "English": 'en'}

        self.setWindowTitle(APP_TITLE)
        self.resize(600, 420)
        self.setMinimumSize(500, 380)
        self.layout = QVBoxLayout()

        # Header + Now playing
        self.label = QLabel(self.i18n.t('header').format(channel='J-POP', format='Vorbis'))
        self.status_label = QLabel("")
        self.now_playing_label = QLabel(f"{self.i18n.t('now_playing_prefix')} –")
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.status_label)
        self.layout.addWidget(self.now_playing_label)

        # Stream info (Channel + Format) - non editable
        sel_row = QHBoxLayout()
        self.channel_label = QLabel(self.i18n.t('channel_label'))
        self.channel_value = QLabel(self.settings.value('channel', 'J-POP'))
        self.format_label = QLabel(self.i18n.t('format_label'))
        self.format_value = QLabel(self.settings.value('format', 'Vorbis'))
        sel_row.addWidget(self.channel_label)
        sel_row.addWidget(self.channel_value)
        sel_row.addWidget(self.format_label)
        sel_row.addWidget(self.format_value)
        self.layout.addLayout(sel_row)

        # Barra superiore: solo pulsante Impostazioni
        top_row = QHBoxLayout()
        # Icone SVG (app)
        try:
            base_dir = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
            self._icon_play = QIcon(os.path.join(base_dir, 'icons', 'app_play.svg'))
            self._icon_stop = QIcon(os.path.join(base_dir, 'icons', 'app_stop.svg'))
            self._icon_status_ok = QIcon(os.path.join(base_dir, 'icons', 'status_ok.svg'))
            self._icon_status_bad = QIcon(os.path.join(base_dir, 'icons', 'status_error.svg'))
            # Imposta icona finestra di default
            if not self._icon_stop.isNull():
                self.setWindowIcon(self._icon_stop)
        except Exception:
            pass
        # Pulsante Impostazioni
        self.settings_button = QPushButton(self.i18n.t('settings_button'))
        self.settings_button.clicked.connect(self.open_settings)
        top_row.addStretch(1)
        top_row.addWidget(self.settings_button)
        self.layout.addLayout(top_row)

        # Indicatore stato VLC (icona + testo)
        status_row = QHBoxLayout()
        self.vlc_status_icon = QLabel()
        self.vlc_status_icon.setFixedSize(10, 10)
        self.vlc_status_icon.setStyleSheet("background-color: #c62828; border-radius: 5px;")
        self.vlc_status = QLabel(self.i18n.t('vlc_not_found'))
        status_row.addWidget(self.vlc_status_icon)
        status_row.addWidget(self.vlc_status)
        status_row.addStretch(1)
        self.layout.addLayout(status_row)

        # Buffering progress bar
        self.buffer_bar = QProgressBar()
        self.buffer_bar.setRange(0, 100)
        self.buffer_bar.setVisible(False)
        self.layout.addWidget(self.buffer_bar)

        # Controls
        self.play_button = QPushButton(self.i18n.t('play'))
        self.pause_button = QPushButton(self.i18n.t('pause'))  # toggle
        self.stop_button = QPushButton(self.i18n.t('stop'))

        vol_row = QHBoxLayout()
        self.volume_label = QLabel(self.i18n.t('volume'))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self.settings.value('volume', 80)))
        self.mute_button = QPushButton(self.i18n.t('mute'))
        self.mute_button.setCheckable(True)
        self.mute_button.setChecked(self.settings.value('mute', 'false') == 'true')
        vol_row.addWidget(self.volume_label)
        vol_row.addWidget(self.volume_slider)
        vol_row.addWidget(self.mute_button)

        self.layout.addWidget(self.play_button)
        self.layout.addWidget(self.pause_button)
        self.layout.addWidget(self.stop_button)
        self.layout.addLayout(vol_row)
        self.setLayout(self.layout)

        # Shortcuts
        self.pause_shortcut = QShortcut(QKeySequence("Space"), self)
        self.pause_shortcut.setContext(Qt.ApplicationShortcut)
        self.pause_shortcut.activated.connect(self.pause_resume)
        # Shortcut Stop (S)
        self.stop_shortcut = QShortcut(QKeySequence("S"), self)
        self.stop_shortcut.setContext(Qt.ApplicationShortcut)
        self.stop_shortcut.activated.connect(self.stop_stream)
        # Shortcut Mute (M)
        self.mute_shortcut = QShortcut(QKeySequence("M"), self)
        self.mute_shortcut.setContext(Qt.ApplicationShortcut)
        self.mute_shortcut.activated.connect(self.toggle_mute_shortcut)

        # Signals/UI connections
        self.play_button.clicked.connect(self.play_stream)
        self.pause_button.clicked.connect(self.pause_resume)
        self.stop_button.clicked.connect(self.stop_stream)
        self.volume_slider.valueChanged.connect(self.volume_changed)
        self.mute_button.toggled.connect(self.mute_toggled)
        self.status_changed.connect(self.status_label.setText)
        self.now_playing_changed.connect(self.now_playing_label.setText)
        self.buffering_progress.connect(self.buffer_bar.setValue)
        self.buffering_visible.connect(self.buffer_bar.setVisible)
        # self.channel_combo.currentIndexChanged.connect(self.on_stream_selection_changed)
        # self.format_combo.currentIndexChanged.connect(self.on_stream_selection_changed)
        # Restore saved channel/format (non più necessario: usiamo QSettings direttamente)
        # saved_channel = self.settings.value('channel', 'J-POP')
        # saved_format = self.settings.value('format', 'Vorbis')
        # Canale/Formato sono mostrati come testo (self.channel_value/self.format_value)
        # self.channel_combo.setCurrentIndex(0 if saved_channel == 'J-POP' else 1)
        # self.format_combo.setCurrentIndex(0 if saved_format == 'Vorbis' else 1)
        # Restore saved language selector index (UI removed)
        # lang_index = 0 if (saved_lang == 'it') else 1
        # self.lang_combo.setCurrentIndex(lang_index)

        # Player wrapper with optional libvlc path
        libvlc_path = self.settings.value('libvlc_path', None)
        self.player = PlayerVLC(on_event=self._on_player_event, libvlc_path=libvlc_path)
        if not self.player.is_ready():
            # Show a clear message explaining what to do
            self.status_changed.emit(self.i18n.t('libvlc_not_ready'))
        self.player.set_volume(self.volume_slider.value())
        self.player.set_mute(self.mute_button.isChecked())
        # Aggiorna indicatore stato VLC all'avvio
        self.update_vlc_status_label()
        # Remove VLC status/details UI updates on main window
        # self.update_vlc_details()

        # Track cache for i18n rerender
        self._current_title = None
        self._current_artist = None

        # WebSocket wrapper
        self.ws = NowPlayingWS(
            on_now_playing=self._on_now_playing,
            on_error_text=self._on_ws_error_text,
            on_closed_text=self._on_ws_closed_text,
        )
        self.ws.start()

        # System Tray Icon e menu
        try:
            self._tray_enabled = (self.settings.value('tray_enabled', 'true') == 'true')
            if self._tray_enabled:
                self.tray = QSystemTrayIcon(self)
                self.update_tray_icon()
                self.tray_menu = QMenu(self)
                self.action_show = QAction(self.i18n.t('tray_show'), self, triggered=lambda: (self.showNormal(), self.activateWindow()))
                self.action_hide = QAction(self.i18n.t('tray_hide'), self, triggered=self.hide)
                self.action_play_pause = QAction(self.i18n.t('tray_play_pause'), self, triggered=self.pause_resume)
                self.action_stop = QAction(self.i18n.t('tray_stop'), self, triggered=self.stop_stream)
                self.action_mute = QAction(self.i18n.t('tray_unmute') if self.mute_button.isChecked() else self.i18n.t('tray_mute'), self, triggered=self.toggle_mute_shortcut)
                self.action_quit = QAction(self.i18n.t('tray_quit'), self, triggered=QApplication.instance().quit)
                self.tray_menu.addAction(self.action_show)
                self.tray_menu.addAction(self.action_hide)
                self.tray_menu.addSeparator()
                self.tray_menu.addAction(self.action_play_pause)
                self.tray_menu.addAction(self.action_stop)
                self.tray_menu.addAction(self.action_mute)
                self.tray_menu.addSeparator()
                self.tray_menu.addAction(self.action_quit)
                self.tray.setContextMenu(self.tray_menu)
                self.tray.setToolTip(self.i18n.t('app_title'))
                self.tray.activated.connect(self._on_tray_activated)
                self.tray.show()
        except Exception:
            pass

        # Autoplay on startup
        try:
            if self.settings.value('autoplay', 'false') == 'true':
                QTimer.singleShot(0, self.play_stream)
        except Exception:
            pass

        self.update_header_label()

    # ------------------- i18n -------------------
    def on_lang_changed(self, idx: int):
        display = self.lang_combo.currentText()
        self.i18n.set_lang(self._lang_map.get(display, 'it'))
        # persist language code
        self.settings.setValue('lang', self.i18n.lang)
        self.apply_translations()

    def apply_translations(self):
        # Mantieni titolo costante
        self.setWindowTitle(APP_TITLE)
        self.channel_label.setText(self.i18n.t('channel_label'))
        self.format_label.setText(self.i18n.t('format_label'))
        self.play_button.setText(self.i18n.t('play'))
        self.pause_button.setText(self.i18n.t('pause'))
        self.stop_button.setText(self.i18n.t('stop'))
        self.volume_label.setText(self.i18n.t('volume'))
        self.mute_button.setText(self.i18n.t('unmute') if self.mute_button.isChecked() else self.i18n.t('mute'))
        if hasattr(self, 'settings_button'):
            self.settings_button.setText(self.i18n.t('settings_button'))
        self.update_header_label()
        self.update_now_playing_label()
        self.update_tray_texts()
        self.update_vlc_status_label()

    def open_settings(self):
        try:
            # Salva stato precedente
            was_playing = bool(self.player and self.player.is_playing())
            prev_channel = self.settings.value('channel', 'J-POP')
            prev_format = self.settings.value('format', 'Vorbis')
            prev_path = self.player.get_configured_path()
            prev_tray_enabled = (self.settings.value('tray_enabled', 'true') == 'true')
            dlg = SettingsDialog(self)
            if dlg.exec_() == QDialog.Accepted:
                # Lingua
                lang = self.settings.value('lang', 'it')
                self.i18n.set_lang('it' if lang not in ('it','en') else lang)
                self.apply_translations()
                # Aggiorna header e valori visivi canale/formato da QSettings
                self.update_header_label()
                if hasattr(self, 'channel_value'):
                    self.channel_value.setText(self.settings.value('channel', 'J-POP'))
                if hasattr(self, 'format_value'):
                    self.format_value.setText(self.settings.value('format', 'Vorbis'))
                # Percorso VLC
                new_path = self.settings.value('libvlc_path', '') or None
                path_changed = (prev_path != new_path)
                if path_changed:
                    if not self.player.reinitialize(new_path):
                        self.status_changed.emit(self.i18n.t('libvlc_not_ready'))
                # Tray enable/disable come da prima
                new_tray_enabled = (self.settings.value('tray_enabled', 'true') == 'true')
                if new_tray_enabled and (not hasattr(self, 'tray') or self.tray is None):
                    try:
                        self._tray_enabled = True
                        self.tray = QSystemTrayIcon(self)
                        self.update_tray_icon()
                        self.tray_menu = QMenu(self)
                        self.action_show = QAction(self.i18n.t('tray_show'), self, triggered=lambda: (self.showNormal(), self.activateWindow()))
                        self.action_hide = QAction(self.i18n.t('tray_hide'), self, triggered=self.hide)
                        self.action_play_pause = QAction(self.i18n.t('tray_play_pause'), self, triggered=self.pause_resume)
                        self.action_stop = QAction(self.i18n.t('tray_stop'), self, triggered=self.stop_stream)
                        self.action_mute = QAction(self.i18n.t('tray_unmute') if self.mute_button.isChecked() else self.i18n.t('tray_mute'), self, triggered=self.toggle_mute_shortcut)
                        self.action_quit = QAction(self.i18n.t('tray_quit'), self, triggered=QApplication.instance().quit)
                        self.tray_menu.addAction(self.action_show)
                        self.tray_menu.addAction(self.action_hide)
                        self.tray_menu.addSeparator()
                        self.tray_menu.addAction(self.action_play_pause)
                        self.tray_menu.addAction(self.action_stop)
                        self.tray_menu.addAction(self.action_mute)
                        self.tray_menu.addSeparator()
                        self.tray_menu.addAction(self.action_quit)
                        self.tray.setContextMenu(self.tray_menu)
                        self.tray.setToolTip(self.i18n.t('app_title'))
                        self.tray.activated.connect(self._on_tray_activated)
                        self.tray.show()
                    except Exception:
                        pass
                elif (not new_tray_enabled) and hasattr(self, 'tray') and self.tray is not None:
                    try:
                        self.tray.hide()
                        self.tray.deleteLater()
                        self.tray = None
                    except Exception:
                        pass
                self.update_tray_texts()
                self.update_tray_icon()
                self.update_vlc_status_label()
                # Autoriavvio se servono cambiamenti
                new_channel = self.settings.value('channel', 'J-POP')
                new_format = self.settings.value('format', 'Vorbis')
                selection_changed = (new_channel != prev_channel) or (new_format != prev_format)
                if was_playing and (selection_changed or path_changed):
                    self.status_changed.emit(self.t('status_restarting'))
                    self.stop_stream()
                    QTimer.singleShot(50, self.play_stream)
        except Exception:
            pass

    def t(self, key: str, **kwargs) -> str:
        return self.i18n.t(key, **kwargs)

    def get_selected_stream_url(self) -> str:
        channel = self.settings.value('channel', 'J-POP')
        fmt = self.settings.value('format', 'Vorbis')
        return STREAMS.get(channel, {}).get(fmt, STREAMS["J-POP"]["Vorbis"])

    def update_header_label(self):
        channel = self.settings.value('channel', 'J-POP')
        fmt = self.settings.value('format', 'Vorbis')
        self.label.setText(self.t('header').format(channel=channel, format=fmt))
        if hasattr(self, 'channel_value'):
            self.channel_value.setText(channel)
        if hasattr(self, 'format_value'):
            self.format_value.setText(fmt)

    def update_now_playing_label(self):
        title = self._current_title or '–'
        artist = self._current_artist or ''
        prefix = self.t('now_playing_prefix')
        text = f"{prefix} {title}" + (f" — {artist}" if artist and title != '–' else "")
        self.now_playing_changed.emit(text)

    def update_vlc_status_label(self):
        try:
            is_ok = bool(self.player and self.player.is_ready())
            text = self.t('vlc_present') if is_ok else self.t('vlc_not_found')
            color = "#2e7d32" if is_ok else "#c62828"
            self.vlc_status.setText(text)
            self.vlc_status.setStyleSheet(f"color: {color}; font-weight: bold;")
            self.vlc_status.setVisible(True)
            try:
                icon = self._icon_status_ok if is_ok else self._icon_status_bad
                if icon and not icon.isNull():
                    self.vlc_status_icon.setStyleSheet("")
                    self.vlc_status_icon.setPixmap(icon.pixmap(10, 10))
                else:
                    self.vlc_status_icon.clear()
                    self.vlc_status_icon.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
            except Exception:
                self.vlc_status_icon.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
            self.vlc_status_icon.setToolTip(self.i18n.t('libvlc_hint'))
            self.vlc_status.setToolTip(self.i18n.t('libvlc_hint'))
        except Exception:
            pass

    def update_vlc_details(self):
        # Disabilitato: dettagli VLC non mostrati nella finestra principale
        return

    def on_stream_selection_changed(self):
        self.update_header_label()
        if self.player.is_playing():
            try:
                self.player.play_url(self.get_selected_stream_url())
                self.player.set_volume(self.volume_slider.value())
                self.player.set_mute(self.mute_button.isChecked())
            except Exception:
                pass

    # ------------------- Configurazione VLC -------------------
    def choose_libvlc_path(self):
        # Non più utilizzato: il percorso di libVLC si imposta dalle Impostazioni
        return

    # ------------------- Player controls -------------------
    def volume_changed(self, value: int):
        self.player.set_volume(int(value))
        self.settings.setValue('volume', int(value))

    def mute_toggled(self, checked: bool):
        self.player.set_mute(bool(checked))
        self.mute_button.setText(self.t('unmute') if checked else self.t('mute'))
        self.settings.setValue('mute', 'true' if checked else 'false')
        # Aggiorna testo azione tray per mute
        try:
            if hasattr(self, 'action_mute'):
                self.action_mute.setText(self.i18n.t('tray_unmute') if checked else self.i18n.t('tray_mute'))
        except Exception:
            pass

    def pause_resume(self):
        try:
            if not self.player.is_playing():
                # Se non sta riproducendo nulla, avvia subito lo stream corrente
                self.play_stream()
            else:
                # Altrimenti metti in pausa/riprendi
                self.player.pause_toggle()
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def toggle_mute_shortcut(self):
        # Simula il click del pulsante per mantenere la UI e le impostazioni in sync
        try:
            self.mute_button.toggle()
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def _on_player_event(self, code: str, value):
        if code == 'opening':
            self.status_changed.emit(self.t('status_opening'))
            self.buffering_visible.emit(True)
            self.buffering_progress.emit(0)
            QTimer.singleShot(0, self.update_tray_icon)
        elif code == 'buffering':
            if value is not None:
                self.buffering_visible.emit(True)
                self.buffering_progress.emit(int(value))
                self.status_changed.emit(self.t('status_buffering_pct', pct=int(value)))
            else:
                self.buffering_visible.emit(True)
                self.status_changed.emit(self.t('status_buffering'))
        elif code == 'playing':
            self.status_changed.emit(self.t('status_playing'))
            self.buffering_visible.emit(False)
            QTimer.singleShot(0, self.update_vlc_status_label)
            QTimer.singleShot(0, self.update_tray_icon)
        elif code == 'paused':
            self.status_changed.emit(self.t('status_paused'))
            QTimer.singleShot(0, self.update_tray_icon)
        elif code == 'stopped':
            self.status_changed.emit(self.t('status_stopped'))
            self.buffering_visible.emit(False)
            QTimer.singleShot(0, self.update_tray_icon)
        elif code == 'ended':
            self.status_changed.emit(self.t('status_ended'))
            self.buffering_visible.emit(False)
            QTimer.singleShot(0, self.update_tray_icon)
        elif code == 'libvlc_init_failed':
            self.status_changed.emit(self.t('libvlc_init_failed'))
            self.buffering_visible.emit(False)
            QTimer.singleShot(0, self.update_vlc_status_label)
            QTimer.singleShot(0, self.update_tray_icon)
        elif code == 'error':
            # Fallback generic error
            self.status_changed.emit(self.t('status_error'))
            self.buffering_visible.emit(False)
            QTimer.singleShot(0, self.update_tray_icon)

    # ------------------- Playback -------------------
    def play_stream(self):
        try:
            if not self.player.is_ready():
                saved_path = self.settings.value('libvlc_path', None)
                if not self.player.reinitialize(saved_path):
                    self.status_changed.emit(self.t('libvlc_not_ready'))
                    self.update_vlc_status_label()
                    return
            self.status_changed.emit(self.t('status_opening'))
            self.player.play_url(self.get_selected_stream_url())
            self.player.set_volume(self.volume_slider.value())
            self.player.set_mute(self.mute_button.isChecked())
            # Aggiorna indicatore stato VLC
            self.update_vlc_status_label()
            self.update_tray_icon()
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def stop_stream(self):
        try:
            self.player.stop()
            self.status_changed.emit(self.t('status_stopped'))
            self.update_tray_icon()
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    # ------------------- Tray helpers -------------------
    def _on_tray_activated(self, reason):
        try:
            if reason == QSystemTrayIcon.Trigger:
                if self.isHidden():
                    self.showNormal()
                    self.activateWindow()
                else:
                    self.hide()
        except Exception:
            pass

    def update_tray_texts(self):
        try:
            if hasattr(self, 'action_show'):
                self.action_show.setText(self.i18n.t('tray_show'))
            if hasattr(self, 'action_hide'):
                self.action_hide.setText(self.i18n.t('tray_hide'))
            if hasattr(self, 'action_play_pause'):
                self.action_play_pause.setText(self.i18n.t('tray_play_pause'))
            if hasattr(self, 'action_stop'):
                self.action_stop.setText(self.i18n.t('tray_stop'))
            if hasattr(self, 'action_mute'):
                self.action_mute.setText(self.i18n.t('tray_unmute') if self.mute_button.isChecked() else self.i18n.t('tray_mute'))
            if hasattr(self, 'action_quit'):
                self.action_quit.setText(self.i18n.t('tray_quit'))
            if hasattr(self, 'tray'):
                self.tray.setToolTip(self.i18n.t('app_title'))
        except Exception:
            pass

    def update_tray_icon(self):
        try:
            if not hasattr(self, 'tray') or self.tray is None:
                return
            icon = None
            # Usa icone SVG personalizzate se disponibili, altrimenti fallback a icone di sistema
            try:
                if self.player and self.player.is_playing():
                    icon = self._icon_play if hasattr(self, '_icon_play') else None
                else:
                    icon = self._icon_stop if hasattr(self, '_icon_stop') else None
            except Exception:
                icon = None
            if not icon or icon.isNull():
                style = self.style()
                icon = style.standardIcon(QStyle.SP_MediaPlay if (self.player and self.player.is_playing()) else QStyle.SP_MediaStop)
            self.tray.setIcon(icon)
            # Aggiorna anche l'icona della finestra
            try:
                self.setWindowIcon(icon)
            except Exception:
                pass
        except Exception:
            pass

    # ------------------- WebSocket callbacks -------------------
    def _on_now_playing(self, title: str, artist: str):
        self._current_title = title or self.t('unknown')
        self._current_artist = artist or ''
        QTimer.singleShot(0, self.update_now_playing_label)
        # Tray notification
        try:
            if hasattr(self, 'tray') and self.tray and (self.settings.value('tray_notifications', 'true') == 'true') and (self.settings.value('tray_enabled', 'true') == 'true'):
                msg_title = self.i18n.t('now_playing_prefix')
                body = f"{self._current_title}" + (f" — {self._current_artist}" if self._current_artist else "")
                self.tray.showMessage(msg_title, body, QSystemTrayIcon.Information, 3000)
        except Exception:
            pass

    def _on_ws_error_text(self, error_text: str):
        self.now_playing_changed.emit(self.t('ws_error_prefix') + error_text)

    def _on_ws_closed_text(self, _):
        self.now_playing_changed.emit(self.t('ws_closed_reconnect'))

    # ------------------- Window -------------------
    def closeEvent(self, event):
        try:
            self.stop_stream()
        except Exception:
            pass
        try:
            self.ws.shutdown()
        except Exception:
            pass
        event.accept()


if __name__ == "__main__":
    app = QApplication([])
    window = ListenMoePlayer()
    window.show()
    try:
        app.exec_()
    except KeyboardInterrupt:
        try:
            window.close()
        except Exception:
            pass
        pass