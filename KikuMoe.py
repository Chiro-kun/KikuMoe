from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QProgressBar, QShortcut,
    QSystemTrayIcon, QMenu, QAction, QActionGroup, QStyle, QDialog
)
from PyQt5.QtCore import pyqtSignal, Qt, QSettings, QTimer
from PyQt5.QtGui import QKeySequence, QIcon
import os
import sys
import re
from i18n import I18n
from ws_client import NowPlayingWS
from player_ffmpeg import PlayerFFmpeg
from player_vlc import PlayerVLC
from config import STREAMS
from settings import SettingsDialog
from constants import (
    APP_TITLE,
    ORG_NAME,
    APP_SETTINGS,
    KEY_LANG,
    KEY_VOLUME,
    KEY_MUTE,
    KEY_CHANNEL,
    KEY_FORMAT,
    KEY_AUTOPLAY,
    KEY_TRAY_ENABLED,
    KEY_TRAY_NOTIFICATIONS,
    KEY_LIBVLC_PATH,
    KEY_NETWORK_CACHING,
)
import threading

class ListenMoePlayer(QWidget):
    status_changed = pyqtSignal(str)
    now_playing_changed = pyqtSignal(str)
    buffering_progress = pyqtSignal(int)
    buffering_visible = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._playback_lock = threading.Lock()

        # settings
        self.settings = QSettings(ORG_NAME, APP_SETTINGS)

        # i18n
        saved_lang = self.settings.value(KEY_LANG, 'it')
        self.i18n = I18n(saved_lang if saved_lang in ('it', 'en') else 'it')
        self._lang_map = {"Italiano": 'it', "English": 'en'}

        self.setWindowTitle(APP_TITLE)
        # Riduci leggermente la dimensione iniziale della finestra
        self.resize(480, 390)
        self.setMinimumSize(500, 380)
        # uso _layout per non sovrascrivere QWidget.layout()
        self._layout = QVBoxLayout()

        # Header + Now playing
        self.label = QLabel(self.i18n.t('header').format(channel='J-POP', format='Vorbis'))
        self.status_label = QLabel("")
        self.now_playing_label = QLabel(f"{self.i18n.t('now_playing_prefix')} –")
        self._layout.addWidget(self.label)
        self._layout.addWidget(self.status_label)
        self._layout.addWidget(self.now_playing_label)

        # Stream info (Channel + Format) - non editable
        sel_row = QHBoxLayout()
        self.channel_label = QLabel(self.i18n.t('channel_label'))
        self.channel_value = QLabel(self.settings.value(KEY_CHANNEL, 'J-POP'))
        self.format_label = QLabel(self.i18n.t('format_label'))
        self.format_value = QLabel(self.settings.value(KEY_FORMAT, 'Vorbis'))
        sel_row.addWidget(self.channel_label)
        sel_row.addWidget(self.channel_value)
        sel_row.addWidget(self.format_label)
        sel_row.addWidget(self.format_value)
        self._layout.addLayout(sel_row)

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
        self._layout.addLayout(top_row)

        # Indicatore stato VLC (icona + testo)
        status_row = QHBoxLayout()
        self.vlc_status_icon = QLabel()
        self.vlc_status_icon.setFixedSize(10, 10)
        self.vlc_status_icon.setStyleSheet("background-color: #c62828; border-radius: 5px;")
        self.vlc_status = QLabel(self.i18n.t('vlc_not_found'))
        status_row.addWidget(self.vlc_status_icon)
        status_row.addWidget(self.vlc_status)
        status_row.addStretch(1)
        self._layout.addLayout(status_row)

        # Buffering progress bar
        self.buffer_bar = QProgressBar()
        self.buffer_bar.setRange(0, 100)
        self.buffer_bar.setVisible(False)
        self._layout.addWidget(self.buffer_bar)

        # Controls
        self.play_button = QPushButton(self.i18n.t('play'))
        self.pause_button = QPushButton(self.i18n.t('pause'))  # toggle
        self.stop_button = QPushButton(self.i18n.t('stop'))
        self.force_stop_button = QPushButton("FORCE STOP")  # Emergency stop

        vol_row = QHBoxLayout()
        self.volume_label = QLabel(self.i18n.t('volume'))
        self.volume_slider = QSlider()
        # QSlider default è orizzontale: evitiamo chiamate che i type-stub possono segnalare
        # (riduce falsi positivi di Pylance mantenendo comportamento runtime)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self.settings.value(KEY_VOLUME, 80)))
        self.mute_button = QPushButton(self.i18n.t('mute'))
        self.mute_button.setCheckable(True)
        self.mute_button.setChecked(self._get_bool(KEY_MUTE, False))
        vol_row.addWidget(self.volume_label)
        vol_row.addWidget(self.volume_slider)
        vol_row.addWidget(self.mute_button)

        self._layout.addWidget(self.play_button)
        self._layout.addWidget(self.pause_button)
        self._layout.addWidget(self.stop_button)
        self._layout.addWidget(self.force_stop_button)
        self._layout.addLayout(vol_row)
        self.setLayout(self._layout)

        # Shortcuts
        # Shortcuts (omettiamo setContext per evitare warning statici dei type-stub)
        self.pause_shortcut = QShortcut(QKeySequence("Space"), self)
        self.pause_shortcut.activated.connect(self.pause_resume)
        # Shortcut Stop (S)
        self.stop_shortcut = QShortcut(QKeySequence("S"), self)
        # omit setContext to avoid type-checker warnings
        self.stop_shortcut.activated.connect(self.stop_stream)
        # Shortcut Mute (M)
        self.mute_shortcut = QShortcut(QKeySequence("M"), self)
        # omit setContext to avoid type-checker warnings
        self.mute_shortcut.activated.connect(self.toggle_mute_shortcut)

        # Signals/UI connections
        self.play_button.clicked.connect(self.play_stream)
        self.pause_button.clicked.connect(self.pause_resume)
        self.stop_button.clicked.connect(self.stop_stream)
        self.force_stop_button.clicked.connect(self.force_stop_all)
        self.volume_slider.valueChanged.connect(self.volume_changed)
        self.mute_button.toggled.connect(self.mute_toggled)
        self.status_changed.connect(self.status_label.setText)
        self.now_playing_changed.connect(self.now_playing_label.setText)
        self.buffering_progress.connect(self.buffer_bar.setValue)
        self.buffering_visible.connect(self.buffer_bar.setVisible)
        
        # Player wrapper - try ffmpeg first, fallback to VLC
        try:
            self.player = PlayerFFmpeg(on_event=self._on_player_event)
            if not self.player.is_ready():
                # Fallback to VLC if ffmpeg player not available
                libvlc_path = self.settings.value(KEY_LIBVLC_PATH, None)
                try:
                    network_caching = int(self.settings.value(KEY_NETWORK_CACHING, 1000))
                except Exception:
                    network_caching = 1000
                self.player = PlayerVLC(on_event=self._on_player_event, libvlc_path=libvlc_path, network_caching_ms=network_caching)
        except Exception:
            # Fallback to VLC
            libvlc_path = self.settings.value(KEY_LIBVLC_PATH, None)
            try:
                network_caching = int(self.settings.value(KEY_NETWORK_CACHING, 1000))
            except Exception:
                network_caching = 1000
            self.player = PlayerVLC(on_event=self._on_player_event, libvlc_path=libvlc_path, network_caching_ms=network_caching)
        
        if not self.player.is_ready():
            # Show a clear message explaining what to do
            self.status_changed.emit(self.i18n.t('libvlc_not_ready'))
        self.player.set_volume(self.volume_slider.value())
        self.player.set_mute(self.mute_button.isChecked())
        # Aggiorna indicatore stato VLC all'avvio
        self.update_vlc_status_label()
        
        # Track cache for i18n rerender
        self._current_title = None
        self._current_artist = None

        # WebSocket wrapper
        init_channel = self.settings.value(KEY_CHANNEL, 'J-POP')
        self.ws = NowPlayingWS(
            on_now_playing=self._on_now_playing,
            on_error_text=self._on_ws_error_text,
            on_closed_text=self._on_ws_closed_text,
            ws_url=self._get_ws_url_for_channel(init_channel),
        )
        self.ws.start()

        # System Tray Icon e menu
        try:
            self._tray_enabled = self._get_bool(KEY_TRAY_ENABLED, True)
            self._ensure_tray(self._tray_enabled)
        except Exception:
            pass

        # Autoplay on startup
        try:
            if self._get_bool(KEY_AUTOPLAY, False):
                QTimer.singleShot(0, self.play_stream)
        except Exception:
            pass

        self.update_header_label()

    # ------------------- i18n -------------------
    def on_lang_changed(self, idx: int):
        # Legge e applica la lingua da QSettings (widget lingua rimosso)
        lang = self.settings.value(KEY_LANG, 'it')
        self.i18n.set_lang('it' if lang not in ('it', 'en') else lang)
        self.settings.setValue(KEY_LANG, self.i18n.lang)
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
            prev_channel = self.settings.value(KEY_CHANNEL, 'J-POP')
            prev_format = self.settings.value(KEY_FORMAT, 'Vorbis')
            prev_path = self.player.get_configured_path()
            prev_tray_enabled = self._get_bool(KEY_TRAY_ENABLED, True)
            try:
                prev_nc = int(self.settings.value(KEY_NETWORK_CACHING, 1000))
            except Exception:
                prev_nc = 1000
            dlg = SettingsDialog(self)
            if dlg.exec_() == QDialog.Accepted:
                # Lingua
                lang = self.settings.value(KEY_LANG, 'it')
                self.i18n.set_lang('it' if lang not in ('it','en') else lang)
                self.apply_translations()
                # Aggiorna header e valori visivi canale/formato da QSettings
                self.update_header_label()
                if hasattr(self, 'channel_value'):
                    self.channel_value.setText(self.settings.value(KEY_CHANNEL, 'J-POP'))
                if hasattr(self, 'format_value'):
                    self.format_value.setText(self.settings.value(KEY_FORMAT, 'Vorbis'))
                # Percorso VLC
                new_path = self.settings.value(KEY_LIBVLC_PATH, '') or None
                path_changed = (prev_path != new_path)
                try:
                    new_nc = int(self.settings.value(KEY_NETWORK_CACHING, 1000))
                except Exception:
                    new_nc = 1000
                nc_changed = (new_nc != prev_nc)
                if path_changed or nc_changed:
                    if not self.player.reinitialize(new_path, network_caching_ms=new_nc):
                        self.status_changed.emit(self.i18n.t('libvlc_not_ready'))
                # Tray enable/disable come da prima
                new_tray_enabled = self._get_bool(KEY_TRAY_ENABLED, True)
                self._ensure_tray(new_tray_enabled)
                self.update_tray_texts()
                self.update_tray_icon()
                self.update_vlc_status_label()
                # Autoriavvio se servono cambiamenti
                new_channel = self.settings.value(KEY_CHANNEL, 'J-POP')
                new_format = self.settings.value(KEY_FORMAT, 'Vorbis')
                selection_changed = (new_channel != prev_channel) or (new_format != prev_format)
                # Se cambia il canale, riavvia anche il WebSocket verso l'endpoint corretto
                if new_channel != prev_channel:
                    # ... (riavvio websocket) ...
                    pass
                # SOLO se serve, ferma e riavvia lo stream
                if was_playing and (selection_changed or path_changed or nc_changed):
                    self.status_changed.emit(self.t('status_restarting'))
                    self.stop_stream()
                    import time
                    time.sleep(0.5)
                    self.player.force_cleanup()
                    QTimer.singleShot(100, self.play_stream)
        except Exception:
            pass

    def t(self, key: str, **kwargs) -> str:
        return self.i18n.t(key, **kwargs)

    def _get_bool(self, key: str, default: bool = True) -> bool:
        """Return boolean from QSettings handling str/bool/int variants."""
        try:
            val = self.settings.value(key, None)
            if val is None:
                return bool(default)
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return bool(int(val))
            s = str(val).strip().lower()
            if s in ('1', 'true', 'yes', 'on'):
                return True
            if s in ('0', 'false', 'no', 'off'):
                return False
        except Exception:
            pass
        return bool(default)

    def get_selected_stream_url(self) -> str:
        channel = self.settings.value(KEY_CHANNEL, 'J-POP')
        fmt = self.settings.value(KEY_FORMAT, 'Vorbis')
        return STREAMS.get(channel, {}).get(fmt, STREAMS["J-POP"]["Vorbis"])

    def _get_ws_url_for_channel(self, channel: str) -> str:
        try:
            if str(channel).upper().startswith('K'):
                return 'wss://listen.moe/kpop/gateway_v2'
        except Exception:
            pass
        return 'wss://listen.moe/gateway_v2'

    def update_header_label(self):
        channel = self.settings.value(KEY_CHANNEL, 'J-POP')
        fmt = self.settings.value(KEY_FORMAT, 'Vorbis')
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
                # Stop completely before switching streams
                self.stop_stream()
                # Wait a moment for complete stop
                import time
                time.sleep(0.5)
                # Force cleanup to ensure no connections remain
                self.player.force_cleanup()
                # Start new stream
                self.play_stream()
            except Exception:
                pass

    # ------------------- Configurazione VLC -------------------
    def choose_libvlc_path(self):
        # Non più utilizzato: il percorso di libVLC si imposta dalle Impostazioni
        return

    # ------------------- Player controls -------------------
    def volume_changed(self, value: int):
        self.player.set_volume(int(value))
        self.settings.setValue(KEY_VOLUME, int(value))

    def mute_toggled(self, checked: bool):
        self.player.set_mute(bool(checked))
        self.mute_button.setText(self.t('unmute') if checked else self.t('mute'))
        self.settings.setValue(KEY_MUTE, 'true' if checked else 'false')
        # Aggiorna testo azione tray per mute
        try:
            if hasattr(self, 'action_mute'):
                self.action_mute.setText(self.i18n.t('tray_unmute') if checked else self.i18n.t('tray_mute'))
                self._update_tray_action_icons()
        except Exception:
            pass

    def pause_resume(self):
        try:
            # Se è in pausa (supportato dal backend ffmpeg), riprendi
            if hasattr(self.player, 'is_paused') and self.player.is_paused():
                self.player.pause_toggle()
                return
            # Se sta riproducendo, fai toggle pausa
            if self.player.is_playing():
                self.player.pause_toggle()
                return
            # Altrimenti, se non sta riproducendo, avvia lo stream
            self.play_stream()
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
            with self._playback_lock:
                if not self.player.is_ready():
                    return
                # Non impostare 'opening' se è in pausa: in quel caso si fa toggle
                if hasattr(self.player, 'is_paused') and self.player.is_paused():
                    print("[DEBUG] play_stream: player is paused, resuming instead of opening new stream")
                    self.player.pause_toggle()
                    # Allinea UI e tray
                    self.player.set_volume(self.volume_slider.value())
                    self.player.set_mute(self.mute_button.isChecked())
                    self.update_vlc_status_label()
                    self.update_tray_icon()
                    self.status_changed.emit(self.t('status_playing'))
                    return
                # Se è già in riproduzione, non mostrare 'apertura'
                if self.player.is_playing():
                    print("[DEBUG] play_stream: player is already playing, no re-open.")
                    # Sincronizza UI e stato
                    self.player.set_volume(self.volume_slider.value())
                    self.player.set_mute(self.mute_button.isChecked())
                    self.update_vlc_status_label()
                    self.update_tray_icon()
                    self.status_changed.emit(self.t('status_playing'))
                    return
                # Solo qui stiamo veramente aprendo un nuovo stream
                self.status_changed.emit(self.t('status_opening'))
                raw_url = self.get_selected_stream_url()
                # Sanitize URL robusta: prova prima ad estrarre direttamente da raw, poi fallback a filtro/regex
                pattern = r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&()*+,;=%]+"
                m_raw = re.search(pattern, raw_url)
                if m_raw:
                    safe_url = m_raw.group(0)
                else:
                    filtered = ''.join(ch for ch in raw_url if (ch.isalnum() or ch in "-._~:/?#[]@!$&()*+,;=%"))
                    m_f = re.search(pattern, filtered)
                    safe_url = m_f.group(0) if m_f else filtered.strip()
                print(f"[DEBUG] play_stream: sanitized url before play: {safe_url!r} from raw: {raw_url!r}")
                self.player.play_url(safe_url)
                # Allinea UI e tray dopo l'avvio
                self.player.set_volume(self.volume_slider.value())
                self.player.set_mute(self.mute_button.isChecked())
                self.update_vlc_status_label()
                self.update_tray_icon()
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def stop_stream(self):
        try:
            print("[DEBUG] stop_stream: called")
            with self._playback_lock:
                self.player.stop()
                self.status_changed.emit(self.t('status_stopped'))
                self.update_tray_icon()
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")
    
    def force_stop_all(self):
        """Emergency stop - force kill all VLC processes."""
        try:
            self.player.force_kill_all_vlc()
            self.status_changed.emit("Force stopped all VLC processes")
            self.update_tray_icon()
        except Exception as e:
            self.status_changed.emit(f"Force stop error: {e}")

    # ------------------- Tray helpers -------------------
    def _create_tray(self):
        try:
            self.tray = QSystemTrayIcon(self)
            self.update_tray_icon()
            self.tray_menu = QMenu(self)
            # Create actions without using constructor overloads that type-checkers flag
            self.action_show = QAction(self.i18n.t('tray_show'), self)
            self.action_show.triggered.connect(self._tray_show)
            self.action_hide = QAction(self.i18n.t('tray_hide'), self)
            self.action_hide.triggered.connect(self.hide)
            self.action_play_pause = QAction(self.i18n.t('tray_play_pause'), self)
            self.action_play_pause.triggered.connect(self.pause_resume)
            self.action_stop = QAction(self.i18n.t('tray_stop'), self)
            self.action_stop.triggered.connect(self.stop_stream)
            self.action_mute = QAction(self.i18n.t('tray_unmute') if self.mute_button.isChecked() else self.i18n.t('tray_mute'), self)
            self.action_mute.triggered.connect(self.toggle_mute_shortcut)
            self.action_quit = QAction(self.i18n.t('tray_quit'), self)
            try:
                app_quit = getattr(QApplication.instance(), "quit", None)
                if callable(app_quit):
                    def _tray_quit_slot():
                        app_quit()
                        return None
                    self.action_quit.triggered.connect(_tray_quit_slot)
            except Exception:
                pass

            # Sottomenu Canale
            self.menu_channel = QMenu(self.i18n.t('tray_channel'), self.tray_menu)
            self.channel_group = QActionGroup(self)
            self.channel_group.setExclusive(True)
            self.action_channel_jpop = QAction("J-POP", self)
            self.action_channel_jpop.setCheckable(True)
            self.action_channel_kpop = QAction("K-POP", self)
            self.action_channel_kpop.setCheckable(True)
            self.channel_group.addAction(self.action_channel_jpop)
            self.channel_group.addAction(self.action_channel_kpop)
            self.menu_channel.addAction(self.action_channel_jpop)
            self.menu_channel.addAction(self.action_channel_kpop)
            # use small named functions instead of lambdas to keep slot type simple for Pylance
            def _tray_select_jpop() -> None:
                try:
                    self._on_tray_channel_select("J-POP")
                except Exception:
                    pass

            def _tray_select_kpop() -> None:
                try:
                    self._on_tray_channel_select("K-POP")
                except Exception:
                    pass

            self.action_channel_jpop.triggered.connect(_tray_select_jpop)
            self.action_channel_kpop.triggered.connect(_tray_select_kpop)

            # Sottomenu Formato (codec)
            self.menu_format = QMenu(self.i18n.t('tray_format'), self.tray_menu)
            self.format_group = QActionGroup(self)
            self.format_group.setExclusive(True)
            self.action_format_vorbis = QAction("Vorbis", self)
            self.action_format_vorbis.setCheckable(True)
            self.action_format_mp3 = QAction("MP3", self)
            self.action_format_mp3.setCheckable(True)
            self.format_group.addAction(self.action_format_vorbis)
            self.format_group.addAction(self.action_format_mp3)
            self.menu_format.addAction(self.action_format_vorbis)
            self.menu_format.addAction(self.action_format_mp3)
            def _tray_select_vorbis() -> None:
                try:
                    self._on_tray_format_select("Vorbis")
                except Exception:
                    pass

            def _tray_select_mp3() -> None:
                try:
                    self._on_tray_format_select("MP3")
                except Exception:
                    pass

            self.action_format_vorbis.triggered.connect(_tray_select_vorbis)
            self.action_format_mp3.triggered.connect(_tray_select_mp3)

            # Monta menu
            self.tray_menu.addAction(self.action_show)
            self.tray_menu.addAction(self.action_hide)
            self.tray_menu.addSeparator()
            self.tray_menu.addMenu(self.menu_channel)
            self.tray_menu.addMenu(self.menu_format)
            self.tray_menu.addSeparator()
            self.tray_menu.addAction(self.action_play_pause)
            self.tray_menu.addAction(self.action_stop)
            self.tray_menu.addAction(self.action_mute)
            self.tray_menu.addSeparator()
            self.tray_menu.addAction(self.action_quit)

            self.tray.setContextMenu(self.tray_menu)
            try:
                if hasattr(self, 'tray') and self.tray:
                    self.tray.setToolTip(APP_TITLE)
            except Exception:
                pass
            self.tray.activated.connect(self._on_tray_activated)
            self.tray.show()

            # Stato iniziale check sottomenu
            self._update_tray_stream_checks()
            # Aggiorna icone dopo la costruzione del menu
            self._update_tray_action_icons()
        except Exception:
            pass

    def _tray_show(self) -> None:
        # metodo separato per compatibilità con i type-stub (evita lambda che ritorna tuple)
        try:
            self.showNormal()
            self.activateWindow()
        except Exception:
            pass

    def _destroy_tray(self):
        try:
            if hasattr(self, 'tray') and self.tray is not None:
                self.tray.hide()
                self.tray.deleteLater()
                self.tray = None
        except Exception:
            pass

    def _ensure_tray(self, enabled: bool):
        if enabled and (not hasattr(self, 'tray') or self.tray is None):
            self._create_tray()
        elif (not enabled) and hasattr(self, 'tray') and self.tray is not None:
            self._destroy_tray()
    def _on_tray_activated(self, reason):
        try:
            if reason == getattr(QSystemTrayIcon, 'Trigger', reason):
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
            if hasattr(self, 'menu_channel'):
                self.menu_channel.setTitle(self.i18n.t('tray_channel'))
            if hasattr(self, 'menu_format'):
                self.menu_format.setTitle(self.i18n.t('tray_format'))
            # guard self.tray to avoid "possibly None" diagnostics
            tray = getattr(self, 'tray', None)
            if tray:
                try:
                    tray.setToolTip(APP_TITLE)
                except Exception:
                    pass
            # Aggiorna check su cambio lingua
            self._update_tray_stream_checks()
            # Aggiorna icone su cambio lingua/stato
            self._update_tray_action_icons()
        except Exception:
            pass

    def _update_tray_stream_checks(self):
         try:
             ch = self.settings.value(KEY_CHANNEL, 'J-POP')
             fmt = self.settings.value(KEY_FORMAT, 'Vorbis')
             if hasattr(self, 'action_channel_jpop'):
                 is_j = str(ch).upper().startswith('J')
                 self.action_channel_jpop.setChecked(is_j)
                 try:
                     icon_ok = self._icon_status_ok if hasattr(self, '_icon_status_ok') else None
                     self.action_channel_jpop.setIcon(icon_ok if (icon_ok and is_j) else QIcon())
                 except Exception:
                     pass
             if hasattr(self, 'action_channel_kpop'):
                 is_k = str(ch).upper().startswith('K')
                 self.action_channel_kpop.setChecked(is_k)
                 try:
                     icon_ok = self._icon_status_ok if hasattr(self, '_icon_status_ok') else None
                     self.action_channel_kpop.setIcon(icon_ok if (icon_ok and is_k) else QIcon())
                 except Exception:
                     pass
             if hasattr(self, 'action_format_vorbis'):
                 is_v = (fmt == 'Vorbis')
                 self.action_format_vorbis.setChecked(is_v)
                 try:
                     icon_ok = self._icon_status_ok if hasattr(self, '_icon_status_ok') else None
                     self.action_format_vorbis.setIcon(icon_ok if (icon_ok and is_v) else QIcon())
                 except Exception:
                     pass
             if hasattr(self, 'action_format_mp3'):
                 is_m = (fmt == 'MP3')
                 self.action_format_mp3.setChecked(is_m)
                 try:
                     icon_ok = self._icon_status_ok if hasattr(self, '_icon_status_ok') else None
                     self.action_format_mp3.setIcon(icon_ok if (icon_ok and is_m) else QIcon())
                 except Exception:
                     pass
         except Exception:
             pass

    def _tray_notify_selection(self):
        try:
            tray = getattr(self, 'tray', None)
            if not tray:
                return
            if not (self._get_bool(KEY_TRAY_NOTIFICATIONS, True) and self._get_bool(KEY_TRAY_ENABLED, True)):
                return
            ch = self.settings.value(KEY_CHANNEL, 'J-POP')
            fmt = self.settings.value(KEY_FORMAT, 'Vorbis')
            title = APP_TITLE
            body = f"{self.i18n.t('channel_label')} {ch} — {self.i18n.t('format_label')} {fmt}"
            try:
                tray.showMessage(title, body)
            except Exception:
                pass
        except Exception:
            pass

    # Handlers invoked from tray menu (were missing and caused crashes)
    def _on_tray_channel_select(self, channel: str) -> None:
        try:
            # Persist selection
            self.settings.setValue(KEY_CHANNEL, channel)
            # Update UI & tray checks
            self._update_tray_stream_checks()
            self.update_header_label()
            # Notify via tray
            self._tray_notify_selection()
            # If currently playing, trigger a safe restart
            try:
                if self.player and self.player.is_playing():
                    # use QTimer to avoid blocking the tray callback stack
                    QTimer.singleShot(50, self.on_stream_selection_changed)
            except Exception:
                pass
        except Exception:
            pass

    def _on_tray_format_select(self, fmt: str) -> None:
        try:
            # Persist selection
            self.settings.setValue(KEY_FORMAT, fmt)
            # Update UI & tray checks
            self._update_tray_stream_checks()
            self.update_header_label()
            # Notify via tray
            self._tray_notify_selection()
            # If currently playing, trigger a safe restart
            try:
                if self.player and self.player.is_playing():
                    QTimer.singleShot(50, self.on_stream_selection_changed)
            except Exception:
                pass
        except Exception:
            pass

    # Minimal tray icon updater used in several places
    def update_tray_icon(self) -> None:
        try:
            tray = getattr(self, 'tray', None)
            if not tray:
                return
            # Prefer play icon when playing, stop icon otherwise (fallback guarded)
            icon = None
            try:
                icon = self._icon_play if (self.player and self.player.is_playing()) else self._icon_stop
            except Exception:
                icon = getattr(self, '_icon_stop', None)
            if icon and not icon.isNull():
                tray.setIcon(icon)
        except Exception:
            pass

    def _update_tray_action_icons(self) -> None:
        try:
            # Update a few common action icons if available (no crash if absent)
            icon_play = getattr(self, '_icon_play', None)
            icon_stop = getattr(self, '_icon_stop', None)
            icon_ok = getattr(self, '_icon_status_ok', None)
            if hasattr(self, 'action_play_pause') and icon_play and not icon_play.isNull():
                try:
                    self.action_play_pause.setIcon(icon_play)
                except Exception:
                    pass
            if hasattr(self, 'action_stop') and icon_stop and not icon_stop.isNull():
                try:
                    self.action_stop.setIcon(icon_stop)
                except Exception:
                    pass
            # Decorative check icons for channel/format actions
            try:
                if hasattr(self, 'action_channel_jpop') and icon_ok:
                    self.action_channel_jpop.setIcon(icon_ok if self.action_channel_jpop.isChecked() else QIcon())
                if hasattr(self, 'action_channel_kpop') and icon_ok:
                    self.action_channel_kpop.setIcon(icon_ok if self.action_channel_kpop.isChecked() else QIcon())
                if hasattr(self, 'action_format_vorbis') and icon_ok:
                    self.action_format_vorbis.setIcon(icon_ok if self.action_format_vorbis.isChecked() else QIcon())
                if hasattr(self, 'action_format_mp3') and icon_ok:
                    self.action_format_mp3.setIcon(icon_ok if self.action_format_mp3.isChecked() else QIcon())
            except Exception:
                pass
        except Exception:
            pass

    def _on_now_playing(self, title: str, artist: str):
        self._current_title = title or self.t('unknown')
        self._current_artist = artist or ''
        QTimer.singleShot(0, self.update_now_playing_label)
        # Tray notification: schedule on main (GUI) thread to avoid crashes from WS thread
        try:
            # prepare strings now (safe to compute in WS thread)
            msg_title = self.i18n.t('now_playing_prefix')
            body = f"{self._current_title}" + (f" — {self._current_artist}" if self._current_artist else "")
            notify_enabled = (self._get_bool(KEY_TRAY_NOTIFICATIONS, True) and self._get_bool(KEY_TRAY_ENABLED, True))
            if not notify_enabled:
                return

            # Use QTimer.singleShot(0, ...) so the actual tray API runs on the Qt main thread
            def _do_notify(msg_title=msg_title, body=body):
                try:
                    tray = getattr(self, 'tray', None)
                    if not tray:
                        return
                    try:
                        tray.showMessage(msg_title, body)
                    except Exception:
                        pass
                except Exception:
                    pass

            QTimer.singleShot(0, _do_notify)
        except Exception:
            pass

    def _on_ws_error_text(self, error_text: str):
        self.now_playing_changed.emit(self.t('ws_error_prefix') + error_text)

    def _on_ws_closed_text(self, _):
        self.now_playing_changed.emit(self.t('ws_closed_reconnect'))

    # ------------------- Window -------------------
    def closeEvent(self, a0):
        # usare nome a0 per compatibilità con gli stub Qt e Pylance
        try:
            try:
                self.stop_stream()
            except Exception:
                pass
        except Exception:
            pass
        try:
            if hasattr(self, 'ws') and self.ws:
                try:
                    self.ws.shutdown()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if a0 is not None and hasattr(a0, 'accept'):
                a0.accept()
        except Exception:
            # fallback: se non è un QCloseEvent, ignoriamo
            pass


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