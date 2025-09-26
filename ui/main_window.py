from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QProgressBar, QShortcut, QSpinBox,
    QDialog, QMessageBox, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, Qt, QSettings, QTimer, QSize, QEvent
from PyQt5.QtGui import QKeySequence, QIcon, QPixmap, QPainter, QColor
from typing import Optional
import sys
import os
import time
import re
from i18n import I18n
from ws_client import NowPlayingWS
from player_ffmpeg import PlayerFFmpeg
from player_vlc import PlayerVLC
from config import STREAMS
from ui.settings_dialog import SettingsDialog
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
    KEY_TRAY_HIDE_ON_MINIMIZE,
    KEY_LIBVLC_PATH,
    KEY_NETWORK_CACHING,
    KEY_DARK_MODE,
    KEY_SLEEP_MINUTES,
    KEY_SLEEP_STOP_ON_END,
    KEY_DEV_CONSOLE_ENABLED,
    KEY_SESSION_TIMER_ENABLED,
    KEY_AUDIO_DEVICE_INDEX,
    KEY_DEV_CONSOLE_SHOW_DEV,
)
import threading
from logger import get_logger
from now_playing import compute_display_mmss
from ui.tray_manager import TrayManager
from ui.dev_console import DevConsole

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
    # Delayed play signal to ensure timers are created from UI thread
    schedule_play = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self._playback_lock = threading.Lock()

        # Connect cross-thread delayed play to UI slot
        try:
            self.schedule_play.connect(self._schedule_play_stream)
        except Exception:
            pass

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
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(8)

        # Header + Now playing
        self.label = QLabel(self.i18n.t('header').format(channel='J-POP', format='Vorbis'))
        self.label.setObjectName('headerLabel')
        self.label.setStyleSheet('font-size: 16px; font-weight: 600;')
        self.status_label = QLabel("")
        self.now_playing_label = QLabel(f"{self.i18n.t('now_playing_prefix')} –")
        self.now_playing_label.setObjectName('nowPlayingLabel')
        self.now_playing_label.setStyleSheet('font-size: 14px; font-weight: 500;')
        self._layout.addWidget(self.label)
        self._layout.addWidget(self.status_label)
        self.session_label = QLabel("")
        self._layout.addWidget(self.session_label)
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
            base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(__file__)))
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
        vol_row.setSpacing(8)
        self.volume_label = QLabel(self.i18n.t('volume'))
        self.volume_slider = QSlider()
        # QSlider default è orizzontale: evitiamo chiamate che i type-stub possono segnalare
        # (riduce falsi positivi di Pylance mantenendo comportamento runtime)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self.settings.value(KEY_VOLUME, 80)))
        # Miglioramenti UX per lo slider del volume
        try:
            self.volume_slider.setOrientation(Qt.Horizontal)
            self.volume_slider.setTickPosition(QSlider.TicksBelow)
            self.volume_slider.setTickInterval(10)
            self.volume_slider.setSingleStep(1)
            self.volume_slider.setPageStep(5)
            self.volume_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.volume_slider.setMinimumWidth(160)
            self.volume_slider.setToolTip(f"{int(self.volume_slider.value())}%")
        except Exception:
            pass
        # Etichetta percentuale accanto allo slider
        try:
            self.volume_value_label = QLabel(f"{int(self.volume_slider.value())}%")
        except Exception:
            self.volume_value_label = QLabel("-")
        self.mute_button = QPushButton(self.i18n.t('mute'))
        self.mute_button.setCheckable(True)
        self.mute_button.setChecked(self._get_bool(KEY_MUTE, False))
        vol_row.addWidget(self.volume_label)
        vol_row.addWidget(self.volume_slider)
        vol_row.addWidget(self.volume_value_label)
        vol_row.addWidget(self.mute_button)

        self._layout.addWidget(self.play_button)
        self._layout.addWidget(self.pause_button)
        self._layout.addWidget(self.stop_button)
        self._layout.addWidget(self.force_stop_button)
        self._layout.addLayout(vol_row)
        # Imposta icone e tooltip dei pulsanti principali
        try:
            # Play: preferisci l'icona bundled, altrimenti fallback al sistema
            if hasattr(self, '_icon_play') and not self._icon_play.isNull():
                self.play_button.setIcon(self._icon_play)
            else:
                self.play_button.setIcon(self.style().standardIcon(self.style().SP_MediaPlay))
            # Pause: icona di sistema
            self.pause_button.setIcon(self.style().standardIcon(self.style().SP_MediaPause))
            self.pause_button.setStyleSheet("")
            self.pause_button.setIcon(self._tint_icon(self.pause_button.icon(), QColor("#f39c12"), self.pause_button.iconSize()))
            self.pause_button.setObjectName('pauseButton')
            self.pause_button.setStyleSheet("")
            # Stop: forza icona standard "quadrato"
            self.stop_button.setIcon(self.style().standardIcon(self.style().SP_MediaStop))
            self.stop_button.setStyleSheet("")
            self.stop_button.setIcon(self._tint_icon(self.stop_button.icon(), QColor("#e53935"), self.stop_button.iconSize()))
            self.stop_button.setObjectName('stopButton')
            self.stop_button.setStyleSheet("")
            # Mute: icona in base allo stato attuale
            self.mute_button.setIcon(
                self.style().standardIcon(self.style().SP_MediaVolumeMuted)
                if self.mute_button.isChecked() else
                self.style().standardIcon(self.style().SP_MediaVolume)
            )
            # Tooltip localizzati
            self.play_button.setToolTip(self.i18n.t('tt_play'))
            self.pause_button.setToolTip(self.i18n.t('tt_pause'))
            self.stop_button.setToolTip(self.i18n.t('tt_stop'))
            self.mute_button.setToolTip(self.i18n.t('tt_unmute') if self.mute_button.isChecked() else self.i18n.t('tt_mute'))
        except Exception:
            pass

        # Sleep Timer row
        sleep_row = QHBoxLayout()
        sleep_row.setSpacing(8)
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
        self.play_button.clicked.connect(self._tray_toggle_play_pause)
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
        # Session timer runtime
        self._session_seconds: int = 0
        self._session_timer: Optional[QTimer] = QTimer(self)
        try:
            self._session_timer.setInterval(1000)
            self._session_timer.timeout.connect(self._on_session_tick)
            enabled = self._get_bool(KEY_SESSION_TIMER_ENABLED, True)
            # Do not auto-start timer here; it starts when playback begins
            if self._session_timer.isActive():
                self._session_timer.stop()
            if hasattr(self, 'session_label'):
                self.session_label.setVisible(bool(enabled))
        except Exception:
            pass
        self._update_session_label()
        # Initialize Dev Console helper
        try:
            self.dev_console = DevConsole(self, translator=self.i18n, logger=self.log)
            try:
                self.dev_console.set_show_dev(self._get_bool(KEY_DEV_CONSOLE_SHOW_DEV, False))
            except Exception:
                pass
        except Exception:
            self.dev_console = None

        # Ensure DevConsole logging is active if enabled in settings
        try:
            if self._get_bool(KEY_DEV_CONSOLE_ENABLED, False) and self.dev_console:
                self.dev_console.activate_logging()
        except Exception:
            pass

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
        # Stato UI di pausa per sincronizzare la tray in modo affidabile
        self._ui_paused: bool = False

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
            self.tray_mgr = TrayManager(
                self,
                self.i18n,
                on_show_window=self.showNormal,
                on_open_settings=self.open_settings,
                on_change_channel=self._tray_change_channel,
                on_change_format=self._tray_change_format,
                on_toggle_play_pause=self._tray_toggle_play_pause,
                on_stop_stream=self.stop_stream,
                on_toggle_mute=self.toggle_mute_shortcut,
            )
            # inizializza icona/tooltip coerenti
            tooltip = None
            try:
                header = self.i18n.t('header').format(channel=self.settings.value(KEY_CHANNEL, 'J-POP'), format=self.settings.value(KEY_FORMAT, 'Vorbis'))
                now = self.now_playing_label.text() if hasattr(self, 'now_playing_label') else ''
                tooltip = f"{header}\n{now}" if now else header
            except Exception:
                pass
            self.tray_mgr.ensure_tray_enabled(self._tray_enabled, window_icon=self.windowIcon(), tooltip=tooltip)
            # Applica tema iniziale
            try:
                self.apply_theme()
            except Exception:
                pass
            # Aggiorna i testi delle azioni della tray in base allo stato corrente (con override UI pausa)
            try:
                has_player = hasattr(self, 'player') and self.player is not None
                real_playing = bool(self.player.is_playing()) if has_player else False
                real_paused = bool(getattr(self.player, 'is_paused', lambda: False)()) if has_player else False
                ui_paused = bool(getattr(self, '_ui_paused', False))
                eff_paused = bool(ui_paused or real_paused)
                eff_playing = bool(real_playing and not eff_paused)
                is_muted = bool(getattr(self.player, 'get_mute', lambda: self._get_bool(KEY_MUTE, False))()) if has_player else bool(self._get_bool(KEY_MUTE, False))
                if hasattr(self, 'tray_mgr') and self.tray_mgr:
                    self.tray_mgr.update_controls_state(eff_playing, eff_paused, is_muted)
            except Exception:
                pass
        except Exception:
            pass

    def _tray_toggle_play_pause(self) -> None:
        try:
            has_player = hasattr(self, 'player') and self.player is not None
            is_playing = False
            is_paused = False
            if has_player:
                try:
                    is_playing = bool(self.player.is_playing())
                except Exception:
                    is_playing = False
                try:
                    is_paused = bool(getattr(self.player, 'is_paused', lambda: False)())
                except Exception:
                    is_paused = False
            if has_player and (is_playing or is_paused):
                self.pause_resume()
            else:
                self.play_stream()
        except Exception:
            pass

    def apply_translations(self):
        # Mantieni o aggiorna titolo finestra in base al Now Playing
        try:
            title = getattr(self, '_current_title', '') or ''
            self.setWindowTitle(f"{APP_TITLE} — {title}" if title else APP_TITLE)
        except Exception:
            pass
        self.channel_label.setText(self.i18n.t('channel_label'))
        self.format_label.setText(self.i18n.t('format_label'))
        self.play_button.setText(self.i18n.t('play'))
        self.pause_button.setText(self.i18n.t('pause'))
        self.stop_button.setText(self.i18n.t('stop'))
        self.volume_label.setText(self.i18n.t('volume'))
        self.mute_button.setText(self.i18n.t('unmute') if self.mute_button.isChecked() else self.i18n.t('mute'))
        # Aggiorna tooltip dei controlli
        try:
            self.play_button.setToolTip(self.i18n.t('tt_play'))
            self.pause_button.setToolTip(self.i18n.t('tt_pause'))
            self.stop_button.setToolTip(self.i18n.t('tt_stop'))
            self.mute_button.setToolTip(self.i18n.t('tt_unmute') if self.mute_button.isChecked() else self.i18n.t('tt_mute'))
        except Exception:
            pass
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
        self.update_vlc_status_label()
        try:
            enabled = self._get_bool(KEY_SESSION_TIMER_ENABLED, True)
            if hasattr(self, 'session_label'):
                self.session_label.setVisible(bool(enabled))
        except Exception:
            pass
        self._update_session_label()
        self.update_tray_texts()
        # Update dev console dialog texts if open
        try:
            if hasattr(self, 'dev_console') and self.dev_console and self.dev_console.is_open():
                try:
                    self.dev_console.set_translator(self.i18n)
                    self.dev_console.refresh_texts()
                except Exception:
                    pass
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
                    QLabel#headerLabel { font-size: 16px; font-weight: 600; color: #ffffff; }
                    QLabel#nowPlayingLabel { font-size: 14px; font-weight: 500; color: #e0e0e0; }
                    QPushButton { background-color: #1e1e1e; color: #e0e0e0; border: 1px solid #333; padding: 6px 10px; border-radius: 4px; }
                    QPushButton:hover { background-color: #2a2a2a; }
                    QPushButton:disabled { background-color: #1a1a1a; color: #777; border-color: #2a2a2a; }
                    QLineEdit, QSpinBox, QComboBox { background-color: #1a1a1a; color: #e0e0e0; border: 1px solid #333; border-radius: 4px; padding: 4px; }
                    QMenu { background-color: #121212; color: #e0e0e0; border: 1px solid #333; }
                    QToolTip { background-color: #2a2a2a; color: #ffffff; border: 1px solid #444; }
                    QProgressBar { background-color: #1a1a1a; border: 1px solid #333; color: #e0e0e0; border-radius: 4px; text-align: center; }
                    QProgressBar::chunk { background-color: #3a86ff; border-radius: 4px; }
                    QSlider::groove:horizontal { height: 6px; background: #333; border-radius: 3px; }
                    QSlider::handle:horizontal { background: #e0e0e0; width: 12px; margin: -4px 0; border-radius: 6px; }
                    """
                )
            else:
                app.setStyleSheet("")
            # Apply dark titlebar on Windows
            try:
                self._apply_windows_titlebar_dark_mode(dark)
            except Exception:
                pass
            try:
                if hasattr(self, 'dev_console') and self.dev_console and self.dev_console.is_open():
                    self.dev_console.apply_theme(dark)
            except Exception:
                pass
        except Exception:
            pass

    def _apply_windows_titlebar_dark_mode(self, enable: bool) -> None:
        try:
            import sys
            if sys.platform != 'win32':
                return
            hwnd = int(self.winId()) if hasattr(self, 'winId') else None
            if not hwnd:
                return
            import ctypes
            value = ctypes.c_int(1 if enable else 0)
            # Windows 10 1903+ (DWMWA_USE_IMMERSIVE_DARK_MODE = 20)
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            except Exception:
                pass
            # Windows 10 1809 (DWMWA_USE_IMMERSIVE_DARK_MODE = 19)
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
            except Exception:
                pass
        except Exception:
            pass

    def _tint_icon(self, icon: QIcon, color: QColor, size: QSize) -> QIcon:
        try:
            if icon is None or icon.isNull():
                return icon
            if not size or size.isEmpty():
                size = QSize(16, 16)
            src = icon.pixmap(size)
            if src.isNull():
                return icon
            dst = QPixmap(src.size())
            dst.fill(Qt.transparent)
            painter = QPainter(dst)
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.drawPixmap(0, 0, src)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(dst.rect(), color)
            painter.end()
            return QIcon(dst)
        except Exception:
            return icon

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
            # Mantieni o aggiorna titolo finestra in base al Now Playing
            try:
                title = getattr(self, '_current_title', '') or ''
                self.setWindowTitle(f"{APP_TITLE} — {title}" if title else APP_TITLE)
            except Exception:
                pass
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
            prev_audio_idx = self.settings.value(KEY_AUDIO_DEVICE_INDEX, '')
            dlg = SettingsDialog(self)
            try:
                self._apply_prev_audio_idx = prev_audio_idx
                def _on_apply_from_dialog():
                    try:
                        new_audio_idx = self.settings.value(KEY_AUDIO_DEVICE_INDEX, '')
                        if new_audio_idx != getattr(self, '_apply_prev_audio_idx', ''):
                            if was_playing:
                                try:
                                    self._skip_session_reset_once = True
                                except Exception:
                                    pass
                                try:
                                    self.stop_stream(reset_session=False)
                                except Exception:
                                    pass
                                try:
                                    time.sleep(0.2)
                                except Exception:
                                    pass
                                try:
                                    self.play_stream()
                                except Exception:
                                    pass
                                try:
                                    if self._get_bool(KEY_TRAY_NOTIFICATIONS, True) and self._get_bool(KEY_TRAY_ENABLED, True):
                                        self.notify_tray.emit("Listen.moe", "Audio riavviato: il timer di sessione continua")
                                except Exception:
                                    pass
                            self._apply_prev_audio_idx = new_audio_idx
                    except Exception:
                        pass
                try:
                    dlg.settings_changed.connect(_on_apply_from_dialog)
                    # Also update DevConsole [DEV] filter live on settings_changed
                    try:
                        def _on_settings_changed_apply_filter():
                            try:
                                if hasattr(self, 'dev_console') and self.dev_console:
                                    self.dev_console.set_show_dev(self._get_bool(KEY_DEV_CONSOLE_SHOW_DEV, False))
                            except Exception:
                                pass
                        dlg.settings_changed.connect(_on_settings_changed_apply_filter)
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception:
                pass
            def _on_dialog_accepted():
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
                # Se canale o formato sono cambiati, riavvia WS/stream ma mantieni il Now Playing finché non arriva un nuovo evento
                try:
                    new_channel = self.settings.value(KEY_CHANNEL, 'J-POP')
                    new_format = self.settings.value(KEY_FORMAT, 'Vorbis')
                    if new_channel != prev_channel or new_format != prev_format:
                        # Mantieni il Now Playing corrente; il WS invierà il nuovo titolo a breve
                        # Riavvia WS se è cambiato il canale
                        if new_channel != prev_channel:
                            try:
                                self._restart_ws_for_channel(new_channel)
                            except Exception:
                                pass
                        self._restart_stream_after_channel_format_change()
                        # Aggiorna tooltip/menu della tray
                        try:
                            self.update_tray_texts()
                            self.tray_icon_refresh.emit()
                        except Exception:
                            pass
                except Exception:
                    pass
                # Se il dispositivo audio è cambiato, riavvia il playback per applicarlo
                try:
                    new_audio_idx = self.settings.value(KEY_AUDIO_DEVICE_INDEX, '')
                    if new_audio_idx != prev_audio_idx:
                        if was_playing:
                            try:
                                self._skip_session_reset_once = True
                            except Exception:
                                pass
                            try:
                                self.stop_stream(reset_session=False)
                            except Exception:
                                pass
                            try:
                                time.sleep(0.2)
                            except Exception:
                                pass
                            try:
                                self.play_stream()
                            except Exception:
                                pass
                            try:
                                if self._get_bool(KEY_TRAY_NOTIFICATIONS, True) and self._get_bool(KEY_TRAY_ENABLED, True):
                                    self.notify_tray.emit("Listen.moe", "Audio riavviato: il timer di sessione continua")
                            except Exception:
                                pass
                except Exception:
                    pass
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
                # Session timer enable/disable may have changed
                try:
                    new_session_enabled = self._get_bool(KEY_SESSION_TIMER_ENABLED, True)
                except Exception:
                    new_session_enabled = True
                try:
                    if new_session_enabled:
                        # If playback is already active, start the session timer now
                        try:
                            if hasattr(self, 'player') and self.player and self.player.is_playing():
                                if self._session_timer and not self._session_timer.isActive():
                                    self._session_timer.start()
                        except Exception:
                            pass
                        if hasattr(self, 'session_label'):
                            self.session_label.show()
                    else:
                        if self._session_timer and self._session_timer.isActive():
                            self._session_timer.stop()
                        if hasattr(self, 'session_label'):
                            self.session_label.hide()
                    self._update_session_label()
                    self.update_tray_texts()
                except Exception:
                    pass
                # Dev console enable/disable may have changed
                new_dev_console = self._get_bool(KEY_DEV_CONSOLE_ENABLED, False)
                if new_dev_console != prev_dev_console:
                    try:
                        if not new_dev_console:
                            if hasattr(self, 'dev_console') and self.dev_console:
                                try:
                                    self.dev_console.deactivate_logging()
                                except Exception:
                                    pass
                                # Non chiudere la UI della console: consenti all'utente di aprirla/vederla anche se il logging di background è disattivato
                                # (prima: self.dev_console.close())
                        else:
                            if hasattr(self, 'dev_console') and self.dev_console:
                                try:
                                    self.dev_console.set_show_dev(self._get_bool(KEY_DEV_CONSOLE_SHOW_DEV, False))
                                except Exception:
                                    pass
                                try:
                                    self.dev_console.activate_logging()
                                except Exception:
                                    pass
                    except Exception:
                        pass
            # collega e mostra non-modale
            try:
                dlg.accepted.connect(_on_dialog_accepted)
            except Exception:
                pass
            try:
                dlg.show()
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
            # Ensure settings are synced, but always allow opening the console on user action
            try:
                self.settings.sync()
            except Exception:
                pass
            # KEY_DEV_CONSOLE_ENABLED controls background logging; opening the UI is always allowed
            if not hasattr(self, 'dev_console') or self.dev_console is None:
                try:
                    self.dev_console = DevConsole(self, translator=self.i18n, logger=self.log)
                except Exception:
                    return
            # Ensure the [DEV] filter is up-to-date with settings
            try:
                if hasattr(self, 'dev_console') and self.dev_console:
                    self.dev_console.set_show_dev(self._get_bool(KEY_DEV_CONSOLE_SHOW_DEV, False))
            except Exception:
                pass
            if self.dev_console.is_open():
                try:
                    self.dev_console.raise_window()
                except Exception:
                    pass
                return
            try:
                self.dev_console.open(parent_widget or self)
                try:
                    dark = self._get_bool(KEY_DARK_MODE, False)
                except Exception:
                    dark = False
                try:
                    self.dev_console.apply_theme(dark)
                except Exception:
                    pass
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
        """Restituisce l'URL del gateway WebSocket corretto in base al canale."""
        try:
            ch = (channel or '').strip().upper()
            if ch == 'K-POP' or 'K-POP' in ch:
                return "wss://listen.moe/kpop/gateway_v2"
            return "wss://listen.moe/gateway_v2"
        except Exception:
            return "wss://listen.moe/gateway_v2"

    def _restart_ws_for_channel(self, channel: str) -> None:
        """Riavvia il client WebSocket puntando al gateway corretto per il canale specificato."""
        try:
            # Arresta il WS corrente
            try:
                if hasattr(self, 'ws') and self.ws:
                    self.ws.shutdown()
            except Exception:
                pass
            # Crea e avvia un nuovo WS sul gateway del canale
            try:
                self.ws = NowPlayingWS(
                    on_now_playing=self._on_now_playing,
                    on_error_text=self._on_ws_error_text,
                    on_closed_text=self._on_ws_closed_text,
                    ws_url=self._get_ws_url_for_channel(channel),
                )
                self.ws.start()
            except Exception:
                pass
        except Exception:
            pass

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

    def _format_hhmmss(self, total_seconds: int) -> str:
        try:
            s = max(0, int(total_seconds))
            h, rem = divmod(s, 3600)
            m, sec = divmod(rem, 60)
            if h > 0:
                return f"{h}:{m:02d}:{sec:02d}"
            return f"{m}:{sec:02d}"
        except Exception:
            return "0:00"

    def _update_session_label(self) -> None:
        try:
            t = self._format_hhmmss(getattr(self, '_session_seconds', 0))
            if hasattr(self, 'i18n') and hasattr(self, 'session_label'):
                self.session_label.setText(self.i18n.t('session_timer', time=t))
        except Exception:
            pass

    def _on_session_tick(self) -> None:
        try:
            self._session_seconds = getattr(self, '_session_seconds', 0) + 1
            self._update_session_label()
            try:
                self.update_tray_texts()
            except Exception:
                pass
        except Exception:
            pass

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

    def _on_player_event(self, code: str, value: Optional[int] = None) -> None:
        """Gestisce gli eventi del backend (FFmpeg/VLC) aggiornando lo stato UI."""
        try:
            c = (str(code).lower() if code is not None else '')
        except Exception:
            c = ''
        try:
            if c == 'opening':
                # Mostra buffering indeterminato in fase di apertura
                try:
                    self.status_changed.emit(self.t('status_opening'))
                except Exception:
                    pass
                try:
                    self.buffering_visible.emit(True)
                    self.buffering_indeterminate.emit(True)
                except Exception:
                    pass
                try:
                    self.backend_status_refresh.emit()
                except Exception:
                    pass
                return

            if c == 'buffering':
                # Mostra buffering (determinato se percentuale disponibile)
                try:
                    self.status_changed.emit(self.t('status_buffering'))
                except Exception:
                    pass
                try:
                    self.buffering_visible.emit(True)
                    if isinstance(value, int) and 0 <= value <= 100:
                        self.buffering_indeterminate.emit(False)
                        self.buffering_progress.emit(int(value))
                    else:
                        self.buffering_indeterminate.emit(True)
                except Exception:
                    pass
                return

            if c == 'playing':
                try:
                    self.status_changed.emit(self.t('status_playing'))
                except Exception:
                    pass
                try:
                    self.buffering_visible.emit(False)
                    self.buffering_indeterminate.emit(False)
                except Exception:
                    pass
                # Ensure session timer is running when playback starts
                try:
                    if self._get_bool(KEY_SESSION_TIMER_ENABLED, True):
                        if self._session_timer and not self._session_timer.isActive():
                            self._session_timer.start()
                        if hasattr(self, 'session_label'):
                            self.session_label.show()
                        self._update_session_label()
                        self.update_tray_texts()
                except Exception:
                    pass
                try:
                    self.tray_icon_refresh.emit()
                except Exception:
                    pass
                # Aggiorna lo stato dei controlli tray (rispetta override pausa UI)
                try:
                    has_player = hasattr(self, 'player') and self.player is not None
                    real_playing = bool(self.player.is_playing()) if has_player else False
                    real_paused = bool(getattr(self.player, 'is_paused', lambda: False)()) if has_player else False
                    ui_paused = bool(getattr(self, '_ui_paused', False))
                    eff_paused = bool(ui_paused or real_paused)
                    eff_playing = bool(real_playing and not eff_paused)
                    is_muted = bool(getattr(self.player, 'get_mute', lambda: False)())
                    if hasattr(self, 'tray_mgr') and self.tray_mgr:
                        self.tray_mgr.update_controls_state(eff_playing, eff_paused, is_muted)
                except Exception:
                    pass
                return

            if c == 'paused':
                try:
                    self.status_changed.emit(self.t('status_paused'))
                except Exception:
                    pass
                # Stop timer on pause (without reset)
                try:
                    if self._get_bool(KEY_SESSION_TIMER_ENABLED, True):
                        if self._session_timer and self._session_timer.isActive():
                            self._session_timer.stop()
                        if hasattr(self, 'session_label'):
                            self.session_label.show()
                        self._update_session_label()
                        self.update_tray_texts()
                except Exception:
                    pass
                # Aggiorna lo stato dei controlli tray
                try:
                    self._ui_paused = True
                    is_muted = bool(getattr(self.player, 'get_mute', lambda: False)())
                    if hasattr(self, 'tray_mgr') and self.tray_mgr:
                        self.tray_mgr.update_controls_state(False, True, is_muted)
                except Exception:
                    pass
                return

            if c in ('stopped', 'ended'):
                # Se il flusso è terminato naturalmente, prepara un riavvio interno preservando il timer
                if c == 'ended':
                    try:
                        self._skip_session_reset_once = True
                    except Exception:
                        pass
                try:
                    self.status_changed.emit(self.t('status_stopped'))
                except Exception:
                    pass
                try:
                    self.buffering_visible.emit(False)
                    self.buffering_indeterminate.emit(False)
                except Exception:
                    pass
                # Stop e reset del timer di sessione (salvo riavvii interni)
                try:
                    if self._get_bool(KEY_SESSION_TIMER_ENABLED, True):
                        if bool(getattr(self, '_skip_session_reset_once', False)):
                            # Riavvio interno: preserva il timer e non azzerare i secondi
                            try:
                                self._skip_session_reset_once = False
                            except Exception:
                                pass
                            if hasattr(self, 'session_label'):
                                self.session_label.show()
                            self._update_session_label()
                            self.update_tray_texts()
                        else:
                            if self._session_timer and self._session_timer.isActive():
                                self._session_timer.stop()
                            self._session_seconds = 0
                            if hasattr(self, 'session_label'):
                                self.session_label.show()
                            self._update_session_label()
                            self.update_tray_texts()
                except Exception:
                    pass
                try:
                    self.tray_icon_refresh.emit()
                except Exception:
                    pass
                # Aggiorna lo stato dei controlli tray
                try:
                    self._ui_paused = False
                    is_muted = bool(getattr(self.player, 'get_mute', lambda: False)())
                    if hasattr(self, 'tray_mgr') and self.tray_mgr:
                        self.tray_mgr.update_controls_state(False, False, is_muted)
                except Exception:
                    pass
                # Auto-riconnessione solo su 'ended' (non su 'stopped')
                try:
                    if c == 'ended':
                        self.schedule_play.emit(1000)
                except Exception:
                    pass
                # Notifica tray del riavvio automatico (timer di sessione preservato)
                try:
                    if c == 'ended':
                        self.notify_tray.emit("Listen.moe", "Audio riavviato: il timer di sessione continua")
                except Exception:
                    pass
                return

            if c in ('error', 'libvlc_init_failed'):
                try:
                    self.status_changed.emit(self.t('status_error'))
                except Exception:
                    pass
                try:
                    self.buffering_visible.emit(False)
                    self.buffering_indeterminate.emit(False)
                except Exception:
                    pass
                try:
                    self.backend_status_refresh.emit()
                except Exception:
                    pass
                # Auto-riconnessione in caso di errore (evita reset sessione)
                try:
                    self._skip_session_reset_once = True
                except Exception:
                    pass
                try:
                    self.schedule_play.emit(1200)
                except Exception:
                    pass
                # Notifica tray del riavvio automatico dopo errore (timer di sessione preservato)
                try:
                    self.notify_tray.emit("Listen.moe", "Audio riavviato: il timer di sessione continua")
                except Exception:
                    pass
                return
        except Exception:
            try:
                self.status_changed.emit(self.t('status_error'))
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
            session_enabled = self._get_bool(KEY_SESSION_TIMER_ENABLED, True)
            session = self.session_label.text() if session_enabled and hasattr(self, 'session_label') else ''
            if now and session:
                tooltip = f"{header}\n{now}\n{session}"
            elif now:
                tooltip = f"{header}\n{now}"
            elif session:
                tooltip = f"{header}\n{session}"
            else:
                tooltip = header
            self.tray_mgr.update_tooltip(tooltip)
        except Exception:
            pass

    def _notify_tray(self, title: str, body: str) -> None:
        try:
            # Rispetta impostazioni utente
            if not self._get_bool(KEY_TRAY_ENABLED, True) or not self._get_bool(KEY_TRAY_NOTIFICATIONS, True):
                return
        except Exception:
            pass
        # Assicura che la tray sia inizializzata secondo il flag corrente
        try:
            self._ensure_tray(self._get_bool(KEY_TRAY_ENABLED, True))
        except Exception:
            pass
        # Mostra la notifica tramite TrayManager
        try:
            if hasattr(self, 'tray_mgr') and self.tray_mgr is not None:
                self.tray_mgr.show_message(title or '', body or '')
        except Exception:
            pass

    def _ensure_tray(self, enabled: bool) -> None:
        try:
            self._tray_enabled = bool(enabled)
            # Ensure tray manager exists
            if not hasattr(self, 'tray_mgr') or self.tray_mgr is None:
                try:
                    self.tray_mgr = TrayManager(
                        self,
                        self.i18n,
                        on_show_window=self.showNormal,
                        on_open_settings=self.open_settings,
                        on_change_channel=self._tray_change_channel,
                        on_change_format=self._tray_change_format,
                        on_toggle_play_pause=self._tray_toggle_play_pause,
                        on_stop_stream=self.stop_stream,
                        on_toggle_mute=self.toggle_mute_shortcut,
                    )
                except Exception:
                    return
            # Compose tooltip from current UI state
            try:
                header = self.i18n.t('header').format(
                    channel=self.settings.value(KEY_CHANNEL, 'J-POP'),
                    format=self.settings.value(KEY_FORMAT, 'Vorbis')
                )
            except Exception:
                header = APP_TITLE
            now = self.now_playing_label.text() if hasattr(self, 'now_playing_label') else ''
            session_enabled = self._get_bool(KEY_SESSION_TIMER_ENABLED, True)
            session = self.session_label.text() if session_enabled and hasattr(self, 'session_label') else ''
            if now and session:
                tooltip = f"{header}\n{now}\n{session}"
            elif now:
                tooltip = f"{header}\n{now}"
            elif session:
                tooltip = f"{header}\n{session}"
            else:
                tooltip = header
            # Apply visibility/icon/tooltip
            try:
                self.tray_mgr.ensure_tray_enabled(self._tray_enabled, window_icon=self.windowIcon(), tooltip=tooltip)
            except Exception:
                pass
            # Aggiorna stato dei controlli in base allo stato corrente (con override UI pausa)
            try:
                has_player = hasattr(self, 'player') and self.player is not None
                is_playing = bool(self.player.is_playing()) if has_player else False
                is_paused = bool(getattr(self.player, 'is_paused', lambda: False)()) if has_player else False
                ui_paused = bool(getattr(self, '_ui_paused', False))
                eff_paused = bool(ui_paused or is_paused)
                eff_playing = bool(is_playing and not eff_paused)
                is_muted = bool(getattr(self.player, 'get_mute', lambda: self._get_bool(KEY_MUTE, False))()) if has_player else bool(self._get_bool(KEY_MUTE, False))
                if hasattr(self, 'tray_mgr') and self.tray_mgr:
                    self.tray_mgr.update_controls_state(eff_playing, eff_paused, is_muted)
            except Exception:
                pass
        except Exception:
            pass

    def update_tray_icon(self) -> None:
        try:
            if not hasattr(self, 'tray_mgr') or self.tray_mgr is None:
                return
            # Update tray visibility/icon/tooltip based on current state
            try:
                header = self.label.text() if hasattr(self, 'label') else APP_TITLE
            except Exception:
                header = APP_TITLE
            now = self.now_playing_label.text() if hasattr(self, 'now_playing_label') else ''
            session_enabled = self._get_bool(KEY_SESSION_TIMER_ENABLED, True)
            session = self.session_label.text() if session_enabled and hasattr(self, 'session_label') else ''
            if now and session:
                tooltip = f"{header}\n{now}\n{session}"
            elif now:
                tooltip = f"{header}\n{now}"
            elif session:
                tooltip = f"{header}\n{session}"
            else:
                tooltip = header
            self.tray_mgr.ensure_tray_enabled(self._tray_enabled, window_icon=self.windowIcon(), tooltip=tooltip)
        except Exception:
            pass

    def _tray_change_channel(self, channel: str) -> None:
        try:
            # Aggiorna impostazione
            try:
                self.settings.setValue(KEY_CHANNEL, channel)
            except Exception:
                pass
            # Aggiorna intestazione/tray
            try:
                self.update_header_label()
            except Exception:
                pass
            try:
                self.update_tray_texts()
            except Exception:
                pass
            # Riavvia il WS per il nuovo canale
            try:
                self._restart_ws_for_channel(channel)
            except Exception:
                pass
            # Riavvia stream se già in riproduzione
            self._restart_stream_after_channel_format_change()
        except Exception:
            pass

    def _tray_change_format(self, fmt: str) -> None:
        try:
            # Aggiorna impostazione
            try:
                self.settings.setValue(KEY_FORMAT, fmt)
            except Exception:
                pass
            # Aggiorna intestazione/tray
            try:
                self.update_header_label()
            except Exception:
                pass
            try:
                self.update_tray_texts()
            except Exception:
                pass
            # Riavvia stream se già in riproduzione
            self._restart_stream_after_channel_format_change()
        except Exception:
            pass

    def _restart_stream_after_channel_format_change(self) -> None:
        try:
            was_playing = False
            try:
                was_playing = bool(self.player and self.player.is_playing())
            except Exception:
                was_playing = False
            if was_playing:
                try:
                    self._skip_session_reset_once = True
                except Exception:
                    pass
                try:
                    self.stop_stream(reset_session=False)
                except Exception:
                    pass
                # Piccolo delay per lasciare tempo al backend di fermarsi
                try:
                    self.schedule_play.emit(200)
                except Exception:
                    # Fallback sincrono
                    self.play_stream()
                try:
                    if self._get_bool(KEY_TRAY_NOTIFICATIONS, True) and self._get_bool(KEY_TRAY_ENABLED, True):
                        self.notify_tray.emit("Listen.moe", "Audio riavviato: il timer di sessione continua")
                except Exception:
                    pass
            else:
                # Se non stava riproducendo, aggiorna comunque icona/tooltip
                try:
                    self.tray_icon_refresh.emit()
                except Exception:
                    pass
        except Exception:
            pass

    # ------------------- Backend status -------------------
    def _schedule_play_stream(self, delay_ms: int) -> None:
        """UI-thread slot to (re)start the stream after a delay."""
        try:
            QTimer.singleShot(int(delay_ms), self.play_stream)
        except Exception:
            try:
                self.play_stream()
            except Exception:
                pass

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
                    # Sanitizza URL prima di log e play
                    try:
                        m = re.search(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&()*+,;=%]+", url or "")
                        safe_url = (m.group(0) if m else (url or "").strip()).rstrip(".,;!?)]}'\" \t\r\n")
                        if safe_url.lower().endswith('/mp3.') or safe_url.lower().endswith('.mp3.'):
                            safe_url = safe_url[:-1]
                    except Exception:
                        safe_url = url
                    self.log.info(f"[UI] play_stream url={safe_url}")
                except Exception:
                    safe_url = url
                self.status_changed.emit(self.t('status_opening') if hasattr(self, 't') else 'Opening...')
                ok = self.player.play_url(safe_url)
                if not ok:
                    # Fallback: prova formato alternativo per lo stesso canale
                    try:
                        channel = self.settings.value(KEY_CHANNEL, 'J-POP')
                        cur_fmt = self.settings.value(KEY_FORMAT, 'Vorbis')
                        alt_fmt = 'MP3' if cur_fmt == 'Vorbis' else 'Vorbis'
                        alt_url = STREAMS.get(channel, {}).get(alt_fmt)
                        if alt_url:
                            try:
                                m2 = re.search(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&()*+,;=%]+", alt_url or "")
                                alt_safe = (m2.group(0) if m2 else (alt_url or "").strip()).rstrip(".,;!?)]}'\" \t\r\n")
                                if alt_safe.lower().endswith('/mp3.') or alt_safe.lower().endswith('.mp3.'):
                                    alt_safe = alt_safe[:-1]
                                self.log.info(f"[UI] primary play failed, trying fallback format {alt_fmt}: {alt_safe}")
                            except Exception:
                                alt_safe = alt_url
                            ok = self.player.play_url(alt_safe)
                    except Exception:
                        pass
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
                    # Start session timer on play if enabled
                    try:
                        if self._get_bool(KEY_SESSION_TIMER_ENABLED, True):
                            # Do not reset automatically; keep cumulative during session unless stopped
                            if self._session_timer and not self._session_timer.isActive():
                                self._session_timer.start()
                            if hasattr(self, 'session_label'):
                                self.session_label.show()
                            self._update_session_label()
                            self.update_tray_texts()
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
                # Aggiorna subito lo stato UI di pausa e la tray (pre-toggle)
                try:
                    new_paused = not bool(getattr(self, '_ui_paused', False))
                    self._ui_paused = new_paused
                    is_muted = bool(getattr(self.player, 'get_mute', lambda: False)())
                    if hasattr(self, 'tray_mgr') and self.tray_mgr:
                        print(f"[MAIN] pause_resume(pre-toggle): new_paused={new_paused}, sending playing={not new_paused}, paused={new_paused}, is_muted={is_muted}")
                        self.tray_mgr.update_controls_state(not new_paused, new_paused, is_muted)
                except Exception:
                    pass
                # Esegui il toggle del backend
                self.player.pause_toggle()
                # Gestisci il session timer e aggiorna solo il tooltip
                try:
                    if self._get_bool(KEY_SESSION_TIMER_ENABLED, True):
                        if self._session_timer and self._session_timer.isActive():
                            self._session_timer.stop()
                        if hasattr(self, 'session_label'):
                            self.session_label.show()  # keep visible, showing frozen time
                        self._update_session_label()
                        self.update_tray_texts()  # aggiorna tooltip
                except Exception:
                    pass
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def stop_stream(self, reset_session: bool = True) -> None:
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
                # Stop and optionally reset session timer on stop if enabled
                try:
                    if self._get_bool(KEY_SESSION_TIMER_ENABLED, True):
                        if reset_session:
                            if self._session_timer and self._session_timer.isActive():
                                self._session_timer.stop()
                            self._session_seconds = 0
                            if hasattr(self, 'session_label'):
                                self.session_label.show()  # show 0:00 if enabled
                            self._update_session_label()
                            self.update_tray_texts()
                        else:
                            # Preserve session timer during internal restarts (device/channel changes)
                            # Keep label visible and refresh tooltip without resetting seconds
                            if hasattr(self, 'session_label'):
                                self.session_label.show()
                            self._update_session_label()
                            self.update_tray_texts()
                except Exception:
                    pass
                # Aggiorna controlli tray dopo stop
                try:
                    is_muted = bool(getattr(self.player, 'get_mute', lambda: False)())
                    if hasattr(self, 'tray_mgr') and self.tray_mgr:
                        self.tray_mgr.update_controls_state(False, False, is_muted)
                except Exception:
                    pass
                try:
                    # Aggiorna titolo finestra: preserva il Now Playing durante riavvii interni
                    if reset_session:
                        base = APP_TITLE
                        self.setWindowTitle(base)
                    else:
                        # Mantieni il titolo corrente se disponibile, altrimenti fallback a base
                        try:
                            title = getattr(self, '_current_title', '') or ''
                        except Exception:
                            title = ''
                        if title:
                            self.setWindowTitle(f"{APP_TITLE} — {title}")
                        else:
                            self.setWindowTitle(APP_TITLE)
                except Exception:
                    pass
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def volume_changed(self, value: int) -> None:
        try:
            self.player.set_volume(int(value))
            self.settings.setValue(KEY_VOLUME, int(value))
            # Aggiorna UI volume
            try:
                if hasattr(self, 'volume_value_label'):
                    self.volume_value_label.setText(f"{int(value)}%")
                if hasattr(self, 'volume_slider'):
                    self.volume_slider.setToolTip(f"{int(value)}%")
            except Exception:
                pass
            try:
                self.log.info(f"[UI] volume_changed -> {int(value)}")
            except Exception:
                pass
        except Exception:
            pass

    def mute_toggled(self, checked: bool) -> None:
        try:
            self.settings.setValue(KEY_MUTE, 'true' if checked else 'false')
        except Exception:
            pass
        try:
            self.mute_button.setText(self.i18n.t('unmute') if checked else self.i18n.t('mute'))
            # Update tooltip and icon according to state
            try:
                self.mute_button.setToolTip(self.i18n.t('tt_unmute') if checked else self.i18n.t('tt_mute'))
                self.mute_button.setIcon(
                    self.style().standardIcon(self.style().SP_MediaVolumeMuted)
                    if checked else self.style().standardIcon(self.style().SP_MediaVolume)
                )
            except Exception:
                pass
        except Exception:
            pass
        try:
            if hasattr(self, 'player') and self.player:
                self.player.set_mute(checked)
        except Exception:
            pass
        # Aggiorna testi azioni tray (Muto/Unmute e Play/Pausa) rispettando lo stato UI di pausa
        try:
            has_player = hasattr(self, 'player') and self.player is not None
            is_playing = bool(self.player.is_playing()) if has_player else False
            is_paused = bool(getattr(self.player, 'is_paused', lambda: False)()) if has_player else False
            ui_paused = bool(getattr(self, '_ui_paused', False))
            eff_paused = bool(ui_paused or is_paused)
            eff_playing = bool(is_playing and not eff_paused)
            if hasattr(self, 'tray_mgr') and self.tray_mgr:
                self.tray_mgr.update_controls_state(eff_playing, eff_paused, bool(checked))
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
                        # Forza titlebar scura su Windows per il QMessageBox
                        try:
                            import sys
                            if sys.platform == 'win32' and hasattr(msg, 'winId'):
                                import ctypes
                                hwnd = int(msg.winId())
                                value = ctypes.c_int(1 if (self.settings.value(KEY_DARK_MODE, 'false') == 'true') else 0)
                                try:
                                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
                                except Exception:
                                    pass
                                try:
                                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
                                except Exception:
                                    pass
                        except Exception:
                            pass
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
        # Stop and reset session timer when forcing stop
        try:
            if self._get_bool(KEY_SESSION_TIMER_ENABLED, True):
                if hasattr(self, '_session_timer') and self._session_timer and self._session_timer.isActive():
                    self._session_timer.stop()
                self._session_seconds = 0
                if hasattr(self, 'session_label'):
                    self.session_label.show()
                self._update_session_label()
                self.update_tray_texts()
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        # Chiudi DevConsole e disattiva la cattura logging
        try:
            if hasattr(self, 'dev_console') and self.dev_console:
                try:
                    self.dev_console.deactivate_logging()
                except Exception:
                    pass
                try:
                    self.dev_console.close()
                except Exception:
                    pass
        except Exception:
            pass
        # Stoppa e resetta session timer
        try:
            if hasattr(self, '_session_timer') and self._session_timer:
                self._session_timer.stop()
            self._session_seconds = 0
        except Exception:
            pass
        # Accetta la chiusura della finestra
        try:
            event.accept()
        except Exception:
            pass

    def showEvent(self, event) -> None:
        try:
            super().showEvent(event)
        except Exception:
            pass
        try:
            dark = self._get_bool(KEY_DARK_MODE, False)
            self._apply_windows_titlebar_dark_mode(dark)
        except Exception:
            pass

    def changeEvent(self, event) -> None:
        try:
            if event.type() == QEvent.WindowStateChange:
                if self.isMinimized() and self._get_bool(KEY_TRAY_ENABLED, True) and self._get_bool(KEY_TRAY_HIDE_ON_MINIMIZE, True):
                    try:
                        self.hide()
                    except Exception:
                        pass
                    try:
                        event.accept()
                    except Exception:
                        pass
                    return
        except Exception:
            pass
        try:
            super().changeEvent(event)
        except Exception:
            pass

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
            session_enabled = self._get_bool(KEY_SESSION_TIMER_ENABLED, True)
            session = self.session_label.text() if session_enabled and hasattr(self, 'session_label') else ''
            if now and session:
                tooltip = f"{header}\n{now}\n{session}"
            elif now:
                tooltip = f"{header}\n{now}"
            elif session:
                tooltip = f"{header}\n{session}"
            else:
                tooltip = header
            self.tray_mgr.update_tooltip(tooltip)
        except Exception:
            pass

    def _ensure_tray(self, enabled: bool) -> None:
        try:
            self._tray_enabled = bool(enabled)
            # Ensure tray manager exists
            if not hasattr(self, 'tray_mgr') or self.tray_mgr is None:
                try:
                    self.tray_mgr = TrayManager(
                        self,
                        self.i18n,
                        on_show_window=self.showNormal,
                        on_open_settings=self.open_settings,
                        on_change_channel=self._tray_change_channel,
                        on_change_format=self._tray_change_format,
                        on_toggle_play_pause=self._tray_toggle_play_pause,
                        on_stop_stream=self.stop_stream,
                        on_toggle_mute=self.toggle_mute_shortcut,
                    )
                except Exception:
                    return
            # Compose tooltip from current UI state
            try:
                header = self.i18n.t('header').format(
                    channel=self.settings.value(KEY_CHANNEL, 'J-POP'),
                    format=self.settings.value(KEY_FORMAT, 'Vorbis')
                )
            except Exception:
                header = APP_TITLE
            now = self.now_playing_label.text() if hasattr(self, 'now_playing_label') else ''
            session_enabled = self._get_bool(KEY_SESSION_TIMER_ENABLED, True)
            session = self.session_label.text() if session_enabled and hasattr(self, 'session_label') else ''
            if now and session:
                tooltip = f"{header}\n{now}\n{session}"
            elif now:
                tooltip = f"{header}\n{now}"
            elif session:
                tooltip = f"{header}\n{session}"
            else:
                tooltip = header
            # Apply visibility/icon/tooltip
            try:
                self.tray_mgr.ensure_tray_enabled(self._tray_enabled, window_icon=self.windowIcon(), tooltip=tooltip)
            except Exception:
                pass
            # Aggiorna anche i testi delle azioni della tray in base allo stato corrente (con override UI pausa)
            try:
                has_player = hasattr(self, 'player') and self.player is not None
                real_playing = bool(self.player.is_playing()) if has_player else False
                real_paused = bool(getattr(self.player, 'is_paused', lambda: False)()) if has_player else False
                ui_paused = bool(getattr(self, '_ui_paused', False))
                eff_paused = bool(ui_paused or real_paused)
                eff_playing = bool(real_playing and not eff_paused)
                is_muted = bool(getattr(self.player, 'get_mute', lambda: self._get_bool(KEY_MUTE, False))()) if has_player else bool(self._get_bool(KEY_MUTE, False))
                if hasattr(self, 'tray_mgr') and self.tray_mgr:
                    self.tray_mgr.update_controls_state(eff_playing, eff_paused, is_muted)
            except Exception:
                pass
        except Exception:
            pass

    def update_tray_icon(self) -> None:
        try:
            if not hasattr(self, 'tray_mgr') or self.tray_mgr is None:
                return
            # Update tray visibility/icon/tooltip based on current state
            try:
                header = self.label.text() if hasattr(self, 'label') else APP_TITLE
            except Exception:
                header = APP_TITLE
            now = self.now_playing_label.text() if hasattr(self, 'now_playing_label') else ''
            session_enabled = self._get_bool(KEY_SESSION_TIMER_ENABLED, True)
            session = self.session_label.text() if session_enabled and hasattr(self, 'session_label') else ''
            if now and session:
                tooltip = f"{header}\n{now}\n{session}"
            elif now:
                tooltip = f"{header}\n{now}"
            elif session:
                tooltip = f"{header}\n{session}"
            else:
                tooltip = header
            self.tray_mgr.ensure_tray_enabled(self._tray_enabled, window_icon=self.windowIcon(), tooltip=tooltip)
        except Exception:
            pass

    def _tray_change_channel(self, channel: str) -> None:
        try:
            # Aggiorna impostazione
            try:
                self.settings.setValue(KEY_CHANNEL, channel)
            except Exception:
                pass
            # Aggiorna intestazione/tray
            try:
                self.update_header_label()
            except Exception:
                pass
            try:
                self.update_tray_texts()
            except Exception:
                pass
            # Riavvia il WS per il nuovo canale
            try:
                self._restart_ws_for_channel(channel)
            except Exception:
                pass
            # Riavvia stream se già in riproduzione
            self._restart_stream_after_channel_format_change()
        except Exception:
            pass

    def _tray_change_format(self, fmt: str) -> None:
        try:
            # Aggiorna impostazione
            try:
                self.settings.setValue(KEY_FORMAT, fmt)
            except Exception:
                pass
            # Aggiorna intestazione/tray
            try:
                self.update_header_label()
            except Exception:
                pass
            try:
                self.update_tray_texts()
            except Exception:
                pass
            # Riavvia stream se già in riproduzione
            self._restart_stream_after_channel_format_change()
        except Exception:
            pass

    def _restart_stream_after_channel_format_change(self) -> None:
        try:
            was_playing = False
            try:
                was_playing = bool(self.player and self.player.is_playing())
            except Exception:
                was_playing = False
            if was_playing:
                # Preserva il timer di sessione e non azzerarlo
                try:
                    self._skip_session_reset_once = True
                except Exception:
                    pass
                try:
                    self.stop_stream(reset_session=False)
                except Exception:
                    pass
                # Piccolo delay per lasciare tempo al backend di fermarsi
                try:
                    self.schedule_play.emit(200)
                except Exception:
                    # Fallback sincrono
                    try:
                        self.play_stream()
                    except Exception:
                        pass
                # Notifica tray del riavvio (timer preservato)
                try:
                    if self._get_bool(KEY_TRAY_NOTIFICATIONS, True) and self._get_bool(KEY_TRAY_ENABLED, True):
                        self.notify_tray.emit("Listen.moe", "Audio riavviato: il timer di sessione continua")
                except Exception:
                    pass
            else:
                # Se non stava riproducendo, aggiorna comunque icona/tooltip
                try:
                    self.tray_icon_refresh.emit()
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