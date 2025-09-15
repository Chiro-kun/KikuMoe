from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QProgressBar, QShortcut,
    QSystemTrayIcon, QMenu, QAction, QActionGroup, QStyle, QDialog
)
from PyQt5.QtCore import pyqtSignal, Qt, QSettings, QTimer
from PyQt5.QtGui import QKeySequence, QIcon
from typing import Optional
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
    # New signals to marshal calls to UI thread safely
    label_refresh = pyqtSignal()
    tray_icon_refresh = pyqtSignal()
    backend_status_refresh = pyqtSignal()
    notify_tray = pyqtSignal(str, str)

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
        # New cross-thread safe connections
        self.label_refresh.connect(self.update_now_playing_label)
        self.tray_icon_refresh.connect(self.update_tray_icon)
        self.backend_status_refresh.connect(self.update_vlc_status_label)
        self.notify_tray.connect(self._notify_tray)
        
        # Player wrapper - try ffmpeg first, fallback to VLC
        try:
            self.player = PlayerFFmpeg(on_event=getattr(self, '_on_player_event', None))
            if not self.player.is_ready():
                # Fallback to VLC if ffmpeg player not available
                libvlc_path = self.settings.value(KEY_LIBVLC_PATH, None)
                try:
                    network_caching = int(self.settings.value(KEY_NETWORK_CACHING, 1000))
                except Exception:
                    network_caching = 1000
                self.player = PlayerVLC(on_event=getattr(self, '_on_player_event', None), libvlc_path=libvlc_path, network_caching_ms=network_caching)
        except Exception:
            # Fallback to VLC
            libvlc_path = self.settings.value(KEY_LIBVLC_PATH, None)
            try:
                network_caching = int(self.settings.value(KEY_NETWORK_CACHING, 1000))
            except Exception:
                network_caching = 1000
            self.player = PlayerVLC(on_event=getattr(self, '_on_player_event', None), libvlc_path=libvlc_path, network_caching_ms=network_caching)
        
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
        self._current_duration_seconds: Optional[int] = None
        self._current_start_epoch: Optional[float] = None
        # Create progress timer in UI thread and keep it available
        self._progress_timer: Optional[QTimer] = QTimer(self)
        try:
            self._progress_timer.setInterval(1000)
            self._progress_timer.timeout.connect(self.update_now_playing_label)
            self._progress_timer.start()
        except Exception:
            pass

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

    def update_header_label(self):
        try:
            channel = self.settings.value(KEY_CHANNEL, 'J-POP')
            fmt = self.settings.value(KEY_FORMAT, 'Vorbis')
            # Aggiorna intestazione principale
            self.label.setText(self.i18n.t('header').format(channel=channel, format=fmt))
            # Aggiorna etichette statiche dei valori
            if hasattr(self, 'channel_value'):
                self.channel_value.setText(channel)
            if hasattr(self, 'format_value'):
                self.format_value.setText(fmt)
            # Mantieni titolo finestra fisso
            self.setWindowTitle(APP_TITLE)
        except Exception:
            pass

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

    def _get_ws_url_for_channel(self, channel: str):
        # Al momento il gateway WS è unico per canali J-POP/K-POP.
        # Manteniamo un helper per futura estensibilità o URL differenziati.
        try:
            return "wss://listen.moe/gateway_v2"
        except Exception:
            return "wss://listen.moe/gateway_v2"

    def get_selected_stream_url(self) -> str:
        """Restituisce l'URL dello stream in base a canale e formato nelle impostazioni."""
        try:
            channel = self.settings.value(KEY_CHANNEL, 'J-POP')
            fmt = self.settings.value(KEY_FORMAT, 'Vorbis')
            urls = STREAMS.get(channel)
            if isinstance(urls, dict):
                url = urls.get(fmt)
                if url:
                    return url
                # fallback: prova Vorbis, altrimenti il primo disponibile
                url = urls.get('Vorbis') or (next(iter(urls.values())) if urls else None)
                if url:
                    return url
            # fallback globale noto
            jpop = STREAMS.get('J-POP', {})
            return jpop.get('Vorbis') or (next(iter(jpop.values())) if jpop else "https://listen.moe/stream")
        except Exception:
            return "https://listen.moe/stream"

    def _get_bool(self, key: str, default: bool) -> bool:
        try:
            val = self.settings.value(key, default)
            if isinstance(val, bool):
                return val
            if isinstance(val, int):
                return bool(val)
            if isinstance(val, str):
                v = val.strip().lower()
                if v in ("1", "true", "yes", "on"):
                    return True
                if v in ("0", "false", "no", "off"):
                    return False
                # fallback: any non-empty string is True
                return len(v) > 0
            return bool(val) if val is not None else default
        except Exception:
            return default

    def _format_mmss(self, seconds: int) -> str:
        """Format seconds as M:SS, capped at 0 if negative."""
        try:
            total = int(seconds)
            if total < 0:
                total = 0
            m, s = divmod(total, 60)
            return f"{m}:{s:02d}"
        except Exception:
            return ""

    def update_now_playing_label(self):
        title = self._current_title or self.t('unknown')
        artist = self._current_artist or ''
        prefix = self.t('now_playing_prefix')
        text = f"{prefix} {title}" + (f" — {artist}" if artist and title != '–' else "")
        # Append remaining or total duration
        try:
            if self._current_duration_seconds and int(self._current_duration_seconds) > 0:
                # If we have start time, show remaining; else show total
                remaining = None
                if self._current_start_epoch is not None:
                    import time
                    elapsed = int(time.time() - int(self._current_start_epoch))
                    if elapsed < 0:
                        elapsed = 0
                    remaining_calc = int(self._current_duration_seconds) - elapsed
                    if remaining_calc < 0:
                        remaining_calc = 0
                    remaining = remaining_calc
                if remaining is not None:
                    mmss = self._format_mmss(remaining)
                else:
                    mmss = self._format_mmss(int(self._current_duration_seconds))
                if mmss:
                    text += f" [{mmss}]"
        except Exception:
            pass
        self.now_playing_changed.emit(text)
        # Update window title too
        try:
            base = APP_TITLE
            self.setWindowTitle(f"{base} — {title}")
        except Exception:
            pass

    def _on_now_playing(self, title: str, artist: str, duration: Optional[int] = None, start_ts: Optional[float] = None):
        self._current_title = title or self.t('unknown')
        self._current_artist = artist or ''
        try:
            self._current_duration_seconds = int(duration) if duration is not None else None
            if self._current_duration_seconds is not None and self._current_duration_seconds <= 0:
                self._current_duration_seconds = None
        except Exception:
            self._current_duration_seconds = None
        # store start time
        try:
            self._current_start_epoch = float(start_ts) if start_ts is not None else None
        except Exception:
            self._current_start_epoch = None
        # Ask UI to update label safely
        try:
            self.label_refresh.emit()
        except Exception:
            pass
        # Tray notification unchanged (static) but invoked on UI thread via signal
        try:
            notify_enabled = (self._get_bool(KEY_TRAY_NOTIFICATIONS, True) and self._get_bool(KEY_TRAY_ENABLED, True))
            if notify_enabled:
                msg_title = self.i18n.t('now_playing_prefix')
                body = f"{self._current_title}" + (f" — {self._current_artist}" if self._current_artist else "")
                try:
                    if self._current_duration_seconds and int(self._current_duration_seconds) > 0:
                        mmss = self._format_mmss(int(self._current_duration_seconds))
                        if mmss:
                            body += f" [{mmss}]"
                except Exception:
                    pass
                self.notify_tray.emit(msg_title, body)
        except Exception:
            pass

    def _notify_tray(self, msg_title: str, body: str) -> None:
        try:
            tray = getattr(self, 'tray', None)
            if not tray:
                return
            tray.showMessage(msg_title, body)
        except Exception:
            pass

    # ------------------- Player events (from backends) -------------------
    def _on_player_event(self, code: str, value: Optional[int] = None) -> None:
        try:
            c = (code or '').lower()
        except Exception:
            c = str(code).lower() if code is not None else ''
        try:
            if c == 'opening':
                self.status_changed.emit(self.t('status_opening'))
                self.buffering_visible.emit(True)
                self.buffering_progress.emit(0)
            elif c == 'buffering':
                self.buffering_visible.emit(True)
                pct = None
                try:
                    pct = int(value) if value is not None else None
                except Exception:
                    pct = None
                if pct is not None:
                    self.buffering_progress.emit(max(0, min(100, pct)))
                    try:
                        self.status_changed.emit(self.i18n.t('status_buffering_pct').format(pct=pct))
                    except Exception:
                        self.status_changed.emit(self.t('status_buffering'))
                else:
                    self.status_changed.emit(self.t('status_buffering'))
            elif c == 'playing':
                self.buffering_visible.emit(False)
                self.status_changed.emit(self.t('status_playing'))
                self.tray_icon_refresh.emit()
            elif c == 'paused':
                self.status_changed.emit(self.t('status_paused'))
            elif c == 'stopped':
                self.buffering_visible.emit(False)
                self.status_changed.emit(self.t('status_stopped'))
                self.tray_icon_refresh.emit()
            elif c == 'ended':
                self.status_changed.emit(self.t('status_ended'))
            elif c == 'libvlc_init_failed':
                self.backend_status_refresh.emit()
                try:
                    self.status_changed.emit(self.i18n.t('vlc_not_found'))
                except Exception:
                    self.status_changed.emit(self.t('status_error'))
            elif c == 'error':
                self.buffering_visible.emit(False)
                self.status_changed.emit(self.t('status_error'))
            else:
                # Unknown code, no-op
                pass
        except Exception:
            # Defensive: never raise from callback
            try:
                self.status_changed.emit(self.t('status_error'))
            except Exception:
                pass
        # Update backend status indicator opportunistically
        try:
            self.backend_status_refresh.emit()
        except Exception:
            pass

    # ------------------- WebSocket text handlers -------------------
    def _on_ws_error_text(self, text: str) -> None:
        try:
            self.status_changed.emit(str(text))
        except Exception:
            pass

    def _on_ws_closed_text(self, text: str) -> None:
        try:
            self.status_changed.emit(str(text))
        except Exception:
            pass

    # ------------------- Tray helpers (static) -------------------
    def update_tray_texts(self) -> None:
        try:
            tray = getattr(self, 'tray', None)
            if not tray:
                return
            # Tooltip statico: solo header e now playing attuale, senza stato dinamico
            header = self.label.text() if hasattr(self, 'label') else APP_TITLE
            now = self.now_playing_label.text() if hasattr(self, 'now_playing_label') else ''
            tray.setToolTip(f"{header}\n{now}" if now else header)
        except Exception:
            pass

    def update_tray_icon(self) -> None:
        try:
            tray = getattr(self, 'tray', None)
            if not tray:
                return
            # Icona statica: usa l'icona della finestra corrente
            tray.setIcon(self.windowIcon())
        except Exception:
            pass

    def _ensure_tray(self, enabled: bool) -> None:
        try:
            if enabled:
                if not hasattr(self, 'tray') or self.tray is None:
                    self.tray = QSystemTrayIcon(self.windowIcon(), self)
                    menu = QMenu()
                    act_show = QAction(self.i18n.t('show_window'), self)
                    act_show.triggered.connect(self.show)
                    menu.addAction(act_show)
                    act_quit = QAction(self.i18n.t('quit') if hasattr(self.i18n, 't') else 'Quit', self)
                    act_quit.triggered.connect(QApplication.instance().quit)
                    menu.addAction(act_quit)
                    self.tray.setContextMenu(menu)
                    self.tray.setVisible(True)
                else:
                    self.tray.setVisible(True)
                self.update_tray_icon()
                self.update_tray_texts()
            else:
                if hasattr(self, 'tray') and self.tray:
                    try:
                        self.tray.setVisible(False)
                    except Exception:
                        pass
        except Exception:
            pass

    # ------------------- Backend status -------------------
    def update_vlc_status_label(self) -> None:
        try:
            ok = bool(self.player and self.player.is_ready())
            # Aggiorna pallino colore
            try:
                self.vlc_status_icon.setStyleSheet(
                    "background-color: #2e7d32; border-radius: 5px;" if ok else
                    "background-color: #c62828; border-radius: 5px;"
                )
            except Exception:
                pass
            # Testo: se disponibile versione, mostralo
            txt = None
            try:
                ver = self.player.get_version()
                if ver:
                    txt = f"{ver}"
            except Exception:
                txt = None
            if not ok:
                self.vlc_status.setText(self.i18n.t('vlc_not_found'))
            else:
                self.vlc_status.setText(txt or "Audio backend OK")
        except Exception:
            pass

    # ------------------- Player controls -------------------
    def play_stream(self) -> None:
        try:
            with self._playback_lock:
                url = self.get_selected_stream_url()
                self.status_changed.emit(self.t('status_connecting') if hasattr(self, 't') else 'Connecting...')
                ok = self.player.play_url(url)
                if not ok:
                    self.status_changed.emit(self.t('status_error'))
                else:
                    try:
                        if hasattr(self, '_icon_play') and not self._icon_play.isNull():
                            self.setWindowIcon(self._icon_play)
                    except Exception:
                        pass
                    self.tray_icon_refresh.emit()
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def pause_resume(self) -> None:
        try:
            with self._playback_lock:
                self.player.pause_toggle()
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def volume_changed(self, value: int) -> None:
        try:
            self.player.set_volume(int(value))
            self.settings.setValue(KEY_VOLUME, int(value))
        except Exception:
            pass

    def mute_toggled(self, checked: bool) -> None:
        try:
            self.player.set_mute(bool(checked))
            try:
                self.mute_button.setText(self.i18n.t('unmute') if checked else self.i18n.t('mute'))
            except Exception:
                pass
            self.settings.setValue(KEY_MUTE, bool(checked))
        except Exception:
            pass

    def toggle_mute_shortcut(self) -> None:
        try:
            self.mute_button.setChecked(not self.mute_button.isChecked())
        except Exception:
            pass

    def force_stop_all(self) -> None:
        try:
            self.player.force_cleanup()
            self.status_changed.emit(self.t('status_force_stop') if hasattr(self, 't') else 'Force stop executed')
            self.tray_icon_refresh.emit()
        except Exception:
            pass

    def stop_stream(self):
        try:
            print("[DEBUG] stop_stream: called")
            with self._playback_lock:
                self.player.stop()
                self.status_changed.emit(self.t('status_stopped'))
                self.tray_icon_refresh.emit()
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")
        
        # Reset window title (timer keeps running in UI thread)
        try:
            self.setWindowTitle(APP_TITLE)
        except Exception:
            pass

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