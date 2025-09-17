from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QProgressBar, QShortcut, QSpinBox,
    QSystemTrayIcon, QMenu, QAction, QActionGroup, QStyle, QDialog, QMessageBox, QTextEdit
)
from PyQt5.QtCore import pyqtSignal, Qt, QSettings, QTimer, QObject, pyqtSlot
from PyQt5.QtGui import QKeySequence, QIcon, QTextCursor, QTextOption
from typing import Optional
import os
import sys
import re
import builtins
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
    KEY_DARK_MODE,
    KEY_SLEEP_MINUTES,
    KEY_SLEEP_STOP_ON_END,
    KEY_DEV_CONSOLE_ENABLED,
)
import threading
from logger import get_logger
from now_playing import compute_display_mmss
from tray_manager import TrayManager

class _QtStream(QObject):
    text_emitted = pyqtSignal(str)

    def __init__(self, append_fn):
        super().__init__()
        try:
            # Usa sempre una connessione queue-ata per garantire che l'aggiornamento UI avvenga nel thread principale
            self.text_emitted.connect(append_fn, Qt.QueuedConnection)
        except Exception:
            pass

    def write(self, s):
        try:
            if s:
                self.text_emitted.emit(str(s))
        except Exception:
            pass

    def flush(self):
        pass

    def isatty(self):
        return False

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
    # Control QProgressBar range (determinate vs indeterminate)
    buffering_indeterminate = pyqtSignal(bool)

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
        self.resize(480, 430)
        self.setMinimumSize(500, 400)
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
        self.top_row = QHBoxLayout()
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
        self.top_row.addStretch(1)
        # Dev console disponibile solo nella finestra Impostazioni: niente bottone o scorciatoia nella top bar
        try:
            self._dev_console_enabled = self._get_bool(KEY_DEV_CONSOLE_ENABLED, False)
        except Exception:
            self._dev_console_enabled = False
        self.top_row.addWidget(self.settings_button)
        self._layout.addLayout(self.top_row)

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

        # Sleep Timer row
        sleep_row = QHBoxLayout()
        self.sleep_title = QLabel(self.i18n.t('sleep_timer'))
        self.sleep_minutes_label = QLabel(self.i18n.t('sleep_minutes'))
        self.spin_sleep = QSpinBox()
        self.spin_sleep.setRange(1, 300)
        try:
            default_sleep = int(self.settings.value(KEY_SLEEP_MINUTES, 30))
        except Exception:
            default_sleep = 30
        self.spin_sleep.setValue(default_sleep)
        self.btn_sleep_start = QPushButton(self.i18n.t('sleep_start'))
        self.btn_sleep_cancel = QPushButton(self.i18n.t('sleep_cancel'))
        self.btn_sleep_start.clicked.connect(self.sleep_start_clicked)
        self.btn_sleep_cancel.clicked.connect(self.sleep_cancel_clicked)
        sleep_row.addWidget(self.sleep_title)
        sleep_row.addStretch(1)
        sleep_row.addWidget(self.sleep_minutes_label)
        sleep_row.addWidget(self.spin_sleep)
        sleep_row.addWidget(self.btn_sleep_start)
        sleep_row.addWidget(self.btn_sleep_cancel)
        self._layout.addLayout(sleep_row)
        self.sleep_label = QLabel("")
        self._layout.addWidget(self.sleep_label)

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
        # Reconnect buffering and cross-thread UI signals
        try:
            self.buffering_progress.connect(self.buffer_bar.setValue)
            self.buffering_visible.connect(self.buffer_bar.setVisible)
            self.buffering_indeterminate.connect(self._set_buffer_bar_indeterminate)
            self.label_refresh.connect(self.update_now_playing_label)
            self.tray_icon_refresh.connect(self.update_tray_icon)
            self.backend_status_refresh.connect(self.update_vlc_status_label)
            self.notify_tray.connect(self._notify_tray)
        except Exception:
            pass

        # Initialize logger
        self.log = get_logger('KikuMoe')

        # Sleep timer runtime
        self._sleep_timer: Optional[QTimer] = QTimer(self)
        try:
            self._sleep_timer.setInterval(1000)
            self._sleep_timer.timeout.connect(self._sleep_tick)
        except Exception:
            pass
        self._sleep_remaining_sec: int = 0
        self._sleep_fadeout_sec: int = 15
        self._sleep_saved_volume: Optional[int] = None

        # Initialize audio backend
        libvlc_path = self.settings.value(KEY_LIBVLC_PATH, '') or None
        try:
            network_caching = int(self.settings.value(KEY_NETWORK_CACHING, 1000))
        except Exception:
            network_caching = 1000
        try:
            # PlayerFFmpeg non accetta network_caching_ms nel costruttore
            self.player = PlayerFFmpeg(on_event=getattr(self, '_on_player_event', None))
        except Exception:
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
            # crea tray manager e applica stato iniziale
            self.tray_mgr = TrayManager(self, self.i18n, on_show_window=self.show, on_open_settings=self.open_settings)
            # inizializza icona/tooltip coerenti
            tooltip = None
            try:
                header = self.i18n.t('header').format(channel=self.settings.value(KEY_CHANNEL, 'J-POP'), format=self.settings.value(KEY_FORMAT, 'Vorbis'))
                now = self.now_playing_label.text() if hasattr(self, 'now_playing_label') else ''
                tooltip = f"{header}\n{now}" if now else header
            except Exception:
                pass
            self.tray_mgr.ensure_tray_enabled(self._tray_enabled, window_icon=self.windowIcon(), tooltip=tooltip)
        except Exception:
            pass

        # Autoplay on startup
        try:
            if self._get_bool(KEY_AUTOPLAY, False):
                QTimer.singleShot(0, self.play_stream)
        except Exception:
            pass

        self.update_header_label()
        # Apply theme (dark/light)
        try:
            self.apply_theme()
        except Exception:
            pass

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
        # Sleep UI texts
        if hasattr(self, 'sleep_title'):
            self.sleep_title.setText(self.i18n.t('sleep_timer'))
        if hasattr(self, 'sleep_minutes_label'):
            self.sleep_minutes_label.setText(self.i18n.t('sleep_minutes'))
        if hasattr(self, 'btn_sleep_start'):
            self.btn_sleep_start.setText(self.i18n.t('sleep_start'))
        if hasattr(self, 'btn_sleep_cancel'):
            self.btn_sleep_cancel.setText(self.i18n.t('sleep_cancel'))
        self.update_header_label()
        self.update_now_playing_label()
        self.update_tray_texts()
        self.update_vlc_status_label()
        # Update dev console dialog texts if open
        try:
            if hasattr(self, '_console_dialog') and self._console_dialog:
                self._console_dialog.setWindowTitle(self.i18n.t('dev_console_title'))
                if hasattr(self, '_console_btn_clear'):
                    self._console_btn_clear.setText(self.i18n.t('dev_console_clear'))
                if hasattr(self, '_console_btn_copy'):
                    self._console_btn_copy.setText(self.i18n.t('dev_console_copy'))
        except Exception:
            pass

    def apply_theme(self) -> None:
        try:
            dark = self._get_bool(KEY_DARK_MODE, False)
            app = QApplication.instance()
            if not app:
                return
            if dark:
                app.setStyleSheet(
                    """
                    QWidget { background-color: #121212; color: #e0e0e0; }
                    QPushButton { background-color: #1e1e1e; color: #e0e0e0; border: 1px solid #333; padding: 6px; }
                    QPushButton:hover { background-color: #2a2a2a; }
                    QLineEdit, QSpinBox { background-color: #1a1a1a; color: #e0e0e0; border: 1px solid #333; }
                    QComboBox { background-color: #1a1a1a; color: #e0e0e0; border: 1px solid #333; }
                    QMenu { background-color: #121212; color: #e0e0e0; }
                    QProgressBar { background-color: #1a1a1a; border: 1px solid #333; color: #e0e0e0; }
                    QProgressBar::chunk { background-color: #3a86ff; }
                    QSlider::groove:horizontal { height: 6px; background: #333; }
                    QSlider::handle:horizontal { background: #ddd; width: 12px; margin: -4px 0; border-radius: 6px; }
                    """
                )
            else:
                app.setStyleSheet("")
        except Exception:
            pass

    def _set_buffer_bar_indeterminate(self, active: bool) -> None:
        try:
            if active:
                self.buffer_bar.setRange(0, 0)
            else:
                self.buffer_bar.setRange(0, 100)
        except Exception:
            pass

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
            prev_dark = self._get_bool(KEY_DARK_MODE, False)
            prev_dev_console = self._get_bool(KEY_DEV_CONSOLE_ENABLED, False)
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
                # Theme
                new_dark = self._get_bool(KEY_DARK_MODE, False)
                if new_dark != prev_dark:
                    self.apply_theme()
                # Ricalibra network caching status
                self.update_vlc_status_label()
                # Se backend/path è cambiato o network-caching è variato sensibile, riavvia
                try:
                    new_nc = int(self.settings.value(KEY_NETWORK_CACHING, 1000))
                except Exception:
                    new_nc = 1000
                if path_changed or new_nc != prev_nc:
                    self.status_changed.emit(self.t('status_restarting'))
                    import time
                    time.sleep(0.5)
                    # Recreate player with new settings
                    try:
                        self.player.stop()
                    except Exception:
                        pass
                    try:
                        self.player = PlayerFFmpeg(on_event=getattr(self, '_on_player_event', None))
                    except Exception:
                        self.player = PlayerVLC(on_event=getattr(self, '_on_player_event', None), libvlc_path=new_path, network_caching_ms=new_nc)
                    self.player.set_volume(self.volume_slider.value())
                    self.player.set_mute(self.mute_button.isChecked())
                    self.update_vlc_status_label()
                # Tray visibility may have changed
                new_tray_enabled = self._get_bool(KEY_TRAY_ENABLED, True)
                if new_tray_enabled != prev_tray_enabled:
                    self._ensure_tray(new_tray_enabled)
                # Dev console enable/disable may have changed
                new_dev_console = self._get_bool(KEY_DEV_CONSOLE_ENABLED, False)
                if new_dev_console != prev_dev_console:
                    try:
                        if not new_dev_console:
                            if hasattr(self, '_console_dialog') and self._console_dialog:
                                try:
                                    self._console_dialog.close()
                                except Exception:
                                    pass
                                self._restore_std_streams()
                    except Exception:
                        pass
        except Exception:
            pass

    def t(self, key: str, **kwargs) -> str:
        try:
            return self.i18n.t(key, **kwargs)
        except Exception:
            return key

    def open_dev_console(self, parent_widget=None):
        try:
            # Open only if enabled in settings (but allow explicit call from Settings dialog)
            try:
                self.settings.sync()
            except Exception:
                pass
            try:
                invoked_from_settings = parent_widget is not None
            except Exception:
                invoked_from_settings = False
            if not invoked_from_settings:
                if not self._get_bool(KEY_DEV_CONSOLE_ENABLED, False):
                    return
            # If already open, just focus it
            if hasattr(self, '_console_dialog') and getattr(self, '_console_dialog', None):
                try:
                    self._console_dialog.raise_()
                    self._console_dialog.activateWindow()
                except Exception:
                    pass
                return

            # Build console dialog UI
            self._console_dialog = QDialog(self)
            self._console_dialog.setWindowTitle(self.i18n.t('dev_console_title'))
            self._console_dialog.setModal(False)

            v = QVBoxLayout()
            self._console_text = QTextEdit()
            self._console_text.setReadOnly(True)
            self._console_text.setLineWrapMode(QTextEdit.WidgetWidth)
            try:
                self._console_text.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            except Exception:
                pass
            try:
                self._console_text.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
            except Exception:
                pass
            v.addWidget(self._console_text)

            h = QHBoxLayout()
            btn_clear = QPushButton(self.i18n.t('dev_console_clear'))
            btn_copy = QPushButton(self.i18n.t('dev_console_copy'))
            btn_clear.clicked.connect(lambda: self._console_text.clear())
            btn_copy.clicked.connect(lambda: (self._console_text.selectAll(), self._console_text.copy()))
            h.addStretch(1)
            h.addWidget(btn_clear)
            h.addWidget(btn_copy)
            v.addLayout(h)

            self._console_dialog.setLayout(v)

            # Messaggio iniziale per confermare il rendering della console
            try:
                self._console_text.append(">>> Console pronta. I log appariranno qui se la redirezione è attiva.")
            except Exception:
                pass

            # Debug: traccia su stdout reale prima del redirect
            try:
                real_out = getattr(sys, '__stdout__', None) or getattr(self, '_old_stdout', None) or sys.stdout
                if real_out:
                    real_out.write('[DEV] open_dev_console: pre-redirect reached\n')
                    try:
                        real_out.flush()
                    except Exception:
                        pass
            except Exception:
                pass

            # Redirect stdout/stderr to the QTextEdit using a Qt-friendly stream
            try:
                self._old_stdout = sys.stdout
                self._old_stderr = sys.stderr
                self._qt_stream_stdout = _QtStream(self._append_console)
                self._qt_stream_stderr = _QtStream(self._append_console)
                sys.stdout = self._qt_stream_stdout
                sys.stderr = self._qt_stream_stderr
                # Monkeypatch print to ensure capture even if libraries bypass sys.stdout
                self._old_print = getattr(builtins, 'print', None)
                def _console_print(*args, **kwargs):
                    try:
                        sep = kwargs.get('sep', ' ')
                        end = kwargs.get('end', '\n')
                        text = sep.join(str(a) for a in args) + end
                        try:
                            if hasattr(self, '_qt_stream_stdout') and self._qt_stream_stdout:
                                self._qt_stream_stdout.write(text)
                        except Exception:
                            pass
                        try:
                            if self._old_print is not None:
                                file_kw = kwargs.copy()
                                # ensure we mirror to the original stdout, not the redirected one
                                file_kw['file'] = getattr(self, '_old_stdout', None)
                                self._old_print(*args, **file_kw)
                        except Exception:
                            pass
                    except Exception:
                        pass
                try:
                    builtins.print = _console_print
                except Exception:
                    pass
                try:
                    self.log.info('[DEV] Console sviluppatore attivata. Output reindirizzato.')
                except Exception:
                    pass
                QTimer.singleShot(150, lambda: self.log.debug('[DEV] Test timer: console attiva e redirect funzionante?'))
                QTimer.singleShot(300, lambda: self._append_console('[DEV] Test timer (append diretto)\n'))
            except Exception:
                pass
        except Exception:
            pass

    @pyqtSlot(str)
    def _append_console(self, s: str):
        try:
            if not hasattr(self, '_console_text') or self._console_text is None:
                return
            if s is None:
                return
            text = str(s)
            if not text:
                return
            self._console_text.moveCursor(QTextCursor.End)
            self._console_text.insertPlainText(text)
            self._console_text.moveCursor(QTextCursor.End)
        except Exception:
            pass

    def _restore_std_streams(self):
        try:
            # Ripristina print monkeypatch
            try:
                if hasattr(self, '_old_print') and self._old_print is not None:
                    builtins.print = self._old_print
            except Exception:
                pass
            # Restore sys.stdout/sys.stderr if previously redirected
            try:
                if hasattr(self, '_old_stdout') and self._old_stdout:
                    sys.stdout = self._old_stdout
            except Exception:
                pass
            try:
                if hasattr(self, '_old_stderr') and self._old_stderr:
                    sys.stderr = self._old_stderr
            except Exception:
                pass
            self._old_stdout = None
            self._old_stderr = None
            self._qt_stream_stdout = None
            self._qt_stream_stderr = None

            # Cleanup dialog references
            try:
                if hasattr(self, '_console_dialog') and self._console_dialog:
                    try:
                        self._console_dialog.close()
                    except Exception:
                        pass
                    self._console_dialog.deleteLater()
                    self._console_dialog = None
            except Exception:
                pass
        except Exception:
            pass

    # Sleep timer logic
    def sleep_start_clicked(self) -> None:
        try:
            minutes = int(self.spin_sleep.value()) if hasattr(self, 'spin_sleep') else 0
            if minutes <= 0:
                minutes = 1
            self.settings.setValue(KEY_SLEEP_MINUTES, int(minutes))
            self._sleep_remaining_sec = int(minutes * 60)
            self._sleep_fadeout_sec = min(30, max(10, int(0.2 * self._sleep_remaining_sec))) if self._sleep_remaining_sec > 60 else min(15, self._sleep_remaining_sec)
            self._sleep_saved_volume = int(self.volume_slider.value()) if hasattr(self, 'volume_slider') else 80
            try:
                if self._sleep_timer and not self._sleep_timer.isActive():
                    self._sleep_timer.start()
                elif self._sleep_timer:
                    # restart
                    self._sleep_timer.stop()
                    self._sleep_timer.start()
            except Exception:
                pass
            if hasattr(self, 'sleep_label'):
                self.sleep_label.setText(self.t('sleep_remaining', time=self._format_mmss(self._sleep_remaining_sec)))
        except Exception:
            pass

    def sleep_cancel_clicked(self) -> None:
        try:
            if self._sleep_timer and self._sleep_timer.isActive():
                self._sleep_timer.stop()
            # restore volume if we had saved it
            if self._sleep_saved_volume is not None and hasattr(self, 'volume_slider'):
                try:
                    self.volume_slider.setValue(int(self._sleep_saved_volume))
                except Exception:
                    pass
            self._sleep_remaining_sec = 0
            self._sleep_saved_volume = None
            if hasattr(self, 'sleep_label'):
                self.sleep_label.setText("")
        except Exception:
            pass

    def _sleep_tick(self) -> None:
        try:
            if self._sleep_remaining_sec <= 0:
                # Finalize
                if self._sleep_timer and self._sleep_timer.isActive():
                    self._sleep_timer.stop()
                if hasattr(self, 'sleep_label'):
                    self.sleep_label.setText("")
                self._sleep_saved_volume = None
                try:
                    # Stop opzionale a fine Sleep Timer
                    should_stop = self._get_bool(KEY_SLEEP_STOP_ON_END, True)
                    if should_stop:
                        try:
                            self.log.info("[SLEEP] time up -> stopping stream")
                        except Exception:
                            pass
                        self.stop_stream()
                except Exception:
                    pass
                return
            # Decrement
            self._sleep_remaining_sec -= 1
            # Fade-out near the end
            if self._sleep_saved_volume is not None and self._sleep_remaining_sec <= self._sleep_fadeout_sec:
                try:
                    new_vol = max(0, int(self._sleep_saved_volume * self._sleep_remaining_sec / max(1, self._sleep_fadeout_sec)))
                    if hasattr(self, 'volume_slider'):
                        self.volume_slider.setValue(new_vol)
                except Exception:
                    pass
            if hasattr(self, 'sleep_label'):
                try:
                    self.sleep_label.setText(self.t('sleep_remaining', time=self._format_mmss(self._sleep_remaining_sec)))
                except Exception:
                    pass
        except Exception:
            pass

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
                # Prefer remaining time only if start timestamp is plausible; otherwise show total duration
                mmss = None
                try:
                    dur = int(self._current_duration_seconds)
                except Exception:
                    dur = None
                if dur and self._current_start_epoch is not None:
                    import time
                    try:
                        elapsed = int(time.time()) - int(self._current_start_epoch)
                    except Exception:
                        elapsed = None
                    # Use remaining only when 0 <= elapsed <= dur + small slack (handle clock skew)
                    if elapsed is not None and 0 <= elapsed <= dur + 5:
                        remaining = dur - elapsed
                        if remaining < 0:
                            remaining = 0
                        mmss = self._format_mmss(remaining)
                    else:
                        # Fallback to total duration to avoid misleading 0:00
                        mmss = self._format_mmss(dur)
                elif dur:
                    mmss = self._format_mmss(dur)
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
        try:
            self.log.info(f"[WS] now_playing: title={title!r}, artist={artist!r}, duration={duration}, start_ts={start_ts}")
        except Exception:
            pass
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
                    mmss, _ = compute_display_mmss(self._current_duration_seconds, self._current_start_epoch)
                    if mmss and mmss != "--:--":
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
                self.buffering_indeterminate.emit(True)
                self.buffering_visible.emit(True)
                self.buffering_progress.emit(0)
                try:
                    self.log.info('[EVENT] opening')
                except Exception:
                    pass
            elif c == 'buffering':
                # Mostra la barra solo se non abbiamo già completato
                pct = None
                try:
                    pct = int(value) if value is not None else None
                except Exception:
                    pct = None
                if pct is not None:
                    # Passa a modalità determinata e aggiorna progresso
                    self.buffering_indeterminate.emit(False)
                    self.buffering_progress.emit(max(0, min(100, pct)))
                    # Aggiorna stato con percentuale
                    try:
                        self.status_changed.emit(self.i18n.t('status_buffering_pct').format(pct=pct))
                    except Exception:
                        self.status_changed.emit(self.t('status_buffering'))
                    # Se siamo al 100% nascondi subito la barra per evitare flicker
                    if pct >= 100:
                        self.buffering_visible.emit(False)
                    else:
                        self.buffering_visible.emit(True)
                    try:
                        self.log.info(f"[EVENT] buffering {pct}%")
                    except Exception:
                        pass
                else:
                    # Nessun valore percentuale -> modalità indeterminata
                    self.buffering_indeterminate.emit(True)
                    self.buffering_visible.emit(True)
            elif c == 'playing':
                self.buffering_visible.emit(False)
                self.buffering_indeterminate.emit(False)
                self.status_changed.emit(self.t('status_playing'))
                self.tray_icon_refresh.emit()
                try:
                    self.log.info('[EVENT] playing')
                except Exception:
                    pass
            elif c == 'paused':
                # In pausa la barra di buffering non è utile: nascondila
                self.buffering_visible.emit(False)
                self.buffering_indeterminate.emit(False)
                self.status_changed.emit(self.t('status_paused'))
                try:
                    self.log.info("[EVENT] paused")
                except Exception:
                    pass
            elif c == 'stopped':
                self.buffering_visible.emit(False)
                self.buffering_indeterminate.emit(False)
                self.status_changed.emit(self.t('status_stopped'))
                self.tray_icon_refresh.emit()
                try:
                    self.log.info('[EVENT] stopped')
                except Exception:
                    pass
            elif c == 'ended':
                # Fine stream: nascondi la barra
                self.buffering_visible.emit(False)
                self.buffering_indeterminate.emit(False)
                self.status_changed.emit(self.t('status_ended'))
                try:
                    self.log.info('[EVENT] ended')
                except Exception:
                    pass
            elif c == 'libvlc_init_failed':
                self.backend_status_refresh.emit()
                try:
                    self.status_changed.emit(self.i18n.t('vlc_not_found'))
                except Exception:
                    self.status_changed.emit(self.t('status_error'))
                try:
                    self.log.info('[EVENT] libvlc_init_failed')
                except Exception:
                    pass
            elif c == 'error':
                self.buffering_visible.emit(False)
                self.buffering_indeterminate.emit(False)
                self.status_changed.emit(self.t('status_error'))
                try:
                    self.log.info('[EVENT] error')
                except Exception:
                    pass
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
            if not hasattr(self, 'tray_mgr') or self.tray_mgr is None:
                return
            header = self.label.text() if hasattr(self, 'label') else APP_TITLE
            now = self.now_playing_label.text() if hasattr(self, 'now_playing_label') else ''
            tooltip = f"{header}\n{now}" if now else header
            self.tray_mgr.update_tooltip(tooltip)
        except Exception:
            pass

    def update_tray_icon(self) -> None:
        try:
            if not hasattr(self, 'tray_mgr') or self.tray_mgr is None:
                return
            self.tray_mgr.update_icon(self.windowIcon())
        except Exception:
            pass

    def _ensure_tray(self, enabled: bool) -> None:
        try:
            if not hasattr(self, 'tray_mgr') or self.tray_mgr is None:
                self.tray_mgr = TrayManager(self, self.i18n, on_show_window=self.show, on_open_settings=self.open_settings)
            header = self.label.text() if hasattr(self, 'label') else APP_TITLE
            now = self.now_playing_label.text() if hasattr(self, 'now_playing_label') else ''
            tooltip = f"{header}\n{now}" if now else header
            self.tray_mgr.ensure_tray_enabled(enabled, window_icon=self.windowIcon(), tooltip=tooltip)
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
                # Determine URL and check backend readiness
                url = None
                try:
                    url = self.get_selected_stream_url()
                except Exception:
                    url = None
                if not hasattr(self, 'player') or self.player is None or not url:
                    try:
                        self.log.info("[UI] play_stream aborted: no player backend or url")
                    except Exception:
                        pass
                    self.status_changed.emit(self.t('status_error'))
                    return
                try:
                    self.log.info(f"[UI] play_stream clicked; backend={type(self.player).__name__}")
                    self.log.info(f"[UI] play_stream url={url}")
                except Exception:
                    pass
                self.status_changed.emit(self.t('status_connecting') if hasattr(self, 't') else 'Connecting...')
                ok = self.player.play_url(url)
                if not ok:
                    self.status_changed.emit(self.t('status_error'))
                    try:
                        self.log.info("[UI] play_stream failed")
                    except Exception:
                        pass
                else:
                    try:
                        if hasattr(self, '_icon_play') and not self._icon_play.isNull():
                            self.setWindowIcon(self._icon_play)
                    except Exception:
                        pass
                    self.tray_icon_refresh.emit()
                    try:
                        self.log.info("[UI] play_stream started")
                    except Exception:
                        pass
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def pause_resume(self) -> None:
        try:
            with self._playback_lock:
                try:
                    self.log.info("[UI] pause_resume clicked")
                except Exception:
                    pass
                self.player.pause_toggle()
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def stop_stream(self) -> None:
        try:
            try:
                self.log.info("[UI] stop_stream clicked")
            except Exception:
                pass
            with self._playback_lock:
                # Stop backend playback
                try:
                    self.player.stop()
                except Exception:
                    pass
                # Update UI state
                try:
                    self.status_changed.emit(self.t('status_stopped'))
                except Exception:
                    pass
                try:
                    if hasattr(self, '_icon_stop') and not self._icon_stop.isNull():
                        self.setWindowIcon(self._icon_stop)
                except Exception:
                    pass
                try:
                    self.buffering_visible.emit(False)
                    self.buffering_indeterminate.emit(False)
                except Exception:
                    pass
                try:
                    self.tray_icon_refresh.emit()
                except Exception:
                    pass
                try:
                    # reset title
                    base = APP_TITLE
                    self.setWindowTitle(base)
                except Exception:
                    pass
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def volume_changed(self, value: int) -> None:
        try:
            self.player.set_volume(int(value))
            self.settings.setValue(KEY_VOLUME, int(value))
            try:
                self.log.info(f"[UI] volume_changed -> {int(value)}")
            except Exception:
                pass
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
            try:
                self.log.info(f"[UI] mute_toggled -> {bool(checked)}")
            except Exception:
                pass
        except Exception:
            pass

        # Salvaguardia: se abbiamo appena disattivato il muto ma il volume è 0, proponi ripristino a 60%
        try:
            if not checked:
                try:
                    vol = int(self.volume_slider.value()) if hasattr(self, 'volume_slider') else int(self.player.get_volume())
                except Exception:
                    vol = 0
                if vol <= 0:
                    try:
                        msg = QMessageBox(self)
                        msg.setWindowTitle(self.i18n.t('volume_zero_title'))
                        msg.setText(self.i18n.t('volume_zero_text'))
                        restore_btn = msg.addButton(self.i18n.t('restore'), QMessageBox.AcceptRole)
                        cancel_btn = msg.addButton(self.i18n.t('settings_cancel'), QMessageBox.RejectRole)
                        msg.setIcon(QMessageBox.Question)
                        msg.exec_()
                        if msg.clickedButton() == restore_btn:
                            if hasattr(self, 'volume_slider'):
                                self.volume_slider.setValue(60)
                            else:
                                self.player.set_volume(60)
                            try:
                                self.settings.setValue(KEY_VOLUME, 60)
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass

    def toggle_mute_shortcut(self) -> None:
        try:
            self.log.info("[UI] mute shortcut toggled")
        except Exception:
            pass
        try:
            self.mute_button.toggle()
        except Exception:
            pass

    def force_stop_all(self) -> None:
        try:
            self.log.info("[UI] FORCE STOP clicked")
        except Exception:
            pass
        try:
            if hasattr(self, 'player') and self.player:
                self.player.force_cleanup()
        except Exception:
            pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ListenMoePlayer()
    window.show()
    sys.exit(app.exec_())