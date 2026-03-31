from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QProgressBar, QShortcut, QSpinBox,
    QDialog, QMessageBox, QSizePolicy, QCheckBox
)
from PyQt5.QtCore import pyqtSignal, Qt, QSettings, QTimer, QSize, QEvent
from PyQt5.QtGui import QKeySequence, QIcon, QPixmap, QPainter, QColor
from typing import Optional
import os
import time
import re
import ctypes
import sys
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
    KEY_WINDOW_GEOMETRY,
    KEY_DONT_ASK_ON_CLOSE,
    KEY_CLOSE_TO_TRAY
)
import threading
from logger import get_logger
from now_playing import compute_display_mmss
from ui.tray_manager import TrayManager
from ui.dev_console import DevConsole

# Custom Progress Bar for Pixel-Perfect Fluidity
class SmoothProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._max = 100
        self._accent_color = QColor("#c2185b") # Match app default accent color
        self.setFixedHeight(4)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setAccentColor(self, color_str):
        self._accent_color = QColor(color_str)
        self.update()

    def setMaximum(self, val):
        self._max = max(1, val)
        self.update()

    def setValue(self, val):
        if self._value != val:
            self._value = val
            self.update()

    def value(self):
        return self._value

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Background track
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(200, 200, 200, 40)) # Translucent track
        painter.drawRoundedRect(self.rect(), 2, 2)

        # Progress chunk
        if self._max > 0:
            w = (self._value / self._max) * self.width()
            if w > 0:
                painter.setBrush(self._accent_color)
                # Clamp width to widget width
                painter.drawRoundedRect(0, 0, int(min(w, self.width())), self.height(), 2, 2)

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
        # State variables
        self._playback_lock = threading.Lock()
        self._ui_paused: bool = False
        self._current_title = None
        self._current_artist = None
        self._current_duration_seconds = None
        self._current_start_epoch = None
        self._session_seconds = 0
        self._sleep_remaining_sec = 0
        self._sleep_fadeout_sec = 15
        self._sleep_saved_volume = None

        # 1. Start initialization sequence
        self._init_settings_and_i18n()
        self._init_icons()
        self._init_ui_base()
        self._init_header_section()
        self._init_meta_section()
        self._init_controls_section()
        self._init_progress_section()
        self._init_sleep_timer_section()
        self._init_audio_backend()
        self._init_timers_and_console()
        self._init_websocket()
        self._init_tray()
        self._init_extra_logic()

    # ------------------- Initialization Helpers -------------------

    def _init_settings_and_i18n(self):
        """
        Initializes the application settings (QSettings) and the internationalization engine.
        Sets up the language based on stored settings and initializes the logger.
        """
        self.settings = QSettings(ORG_NAME, APP_SETTINGS)
        saved_lang = self.settings.value(KEY_LANG, 'it')
        self.i18n = I18n(saved_lang if saved_lang in ('it', 'en') else 'it')
        self._lang_map = {"Italiano": 'it', "English": 'en'}
        self.log = get_logger('KikuMoe')

    def _init_icons(self):
        """Load and prepare application icons for window and tray."""
        try:
            icon_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons')
            self._icon_play = QIcon(os.path.join(icon_dir, 'app_play.svg'))
            self._icon_stop = QIcon(os.path.join(icon_dir, 'app_stop.svg'))
            if self._icon_stop.isNull():
                self._icon_stop = self.style().standardIcon(self.style().SP_MediaStop)
            if self._icon_play.isNull():
                self._icon_play = self.style().standardIcon(self.style().SP_MediaPlay)
            self._icon_pause = self.style().standardIcon(self.style().SP_MediaPause)
        except Exception:
            self._icon_play = self.style().standardIcon(self.style().SP_MediaPlay)
            self._icon_stop = self.style().standardIcon(self.style().SP_MediaStop)
            self._icon_pause = self.style().standardIcon(self.style().SP_MediaPause)

    def _init_ui_base(self):
        """
        Sets up the basic window properties such as title, icon, geometry, and main layout.
        Also initializes the custom title bar behavior (if applicable).
        """
        self.setWindowTitle(APP_TITLE)
        try:
            if hasattr(self, '_icon_stop') and not self._icon_stop.isNull():
                self.setWindowIcon(self._icon_stop)
        except Exception:
            pass
        try:
            geom = self.settings.value(KEY_WINDOW_GEOMETRY)
            if geom:
                self.restoreGeometry(geom)
            else:
                self.resize(480, 430)
                self.setMinimumSize(500, 400)
            
            # --- Branding Colors ---
            self.COLOR_ACCENT = "#c2185b" # Magenta from KikuMoe Logo
        except Exception:
            self.resize(480, 430)
            self.setMinimumSize(500, 400)

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 16, 16)
        self._layout.setSpacing(8)
        self.setLayout(self._layout)

    def _init_header_section(self):
        """
        Creates and adds the header section components to the UI, including
        the channel logo, source indicators, and current broadcast information.
        """
        self.menu_bar_layout = QHBoxLayout()
        self.menu_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.menu_bar_layout.setSpacing(0)
        
        # Settings button in menu style at the very top (under the app bar)
        self.settings_button = QPushButton(self.i18n.t('settings_button'))
        self.settings_button.setObjectName('menuButton')
        self.settings_button.setFixedHeight(30)
        self.settings_button.clicked.connect(self.open_settings)
        
        self.menu_bar_layout.addWidget(self.settings_button)
        self.menu_bar_layout.addStretch(1)
        self._layout.addLayout(self.menu_bar_layout)

        # Create a sub-layout for the rest of the UI (with 16px left margin)
        # and rebind self._layout so that all subsequent sections are correctly aligned.
        self.main_content_layout = QVBoxLayout()
        self.main_content_layout.setContentsMargins(16, 0, 0, 0)
        self.main_content_layout.setSpacing(8)
        self._layout.addLayout(self.main_content_layout)
        self._layout = self.main_content_layout

        # Header Label (Title)
        self.label = QLabel(self.i18n.t('header').format(channel='J-POP', format='Vorbis'))
        self.label.setObjectName('headerLabel')
        self.label.setStyleSheet('font-size: 16px; font-weight: 600;')
        self._layout.addWidget(self.label)
        
        self.status_label = QLabel("")
        self.status_label.setObjectName('status_label_val')
        self._layout.addWidget(self.status_label)
        
        self.session_label = QLabel("")
        self.session_label.setObjectName('sessionLabel')
        self._layout.addWidget(self.session_label)
        
        self.sleep_label = QLabel("")
        self.sleep_label.setObjectName('sleepLabel')
        self._layout.addWidget(self.sleep_label)
        
        self.now_playing_label = QLabel(f"{self.i18n.t('now_playing_prefix')} –")
        self.now_playing_label.setObjectName('nowPlayingLabel')
        self.now_playing_label.setStyleSheet('font-size: 14px; font-weight: 500;')
        self.now_playing_label.setWordWrap(True)
        self._layout.addWidget(self.now_playing_label)
        
        # Song Progress Bar (Dynamic custom widget for smoothness)
        self.song_progress = SmoothProgressBar()
        self.song_progress.setVisible(False)
        self.song_progress.setObjectName("songProgressBar")
        self._layout.addWidget(self.song_progress)
        
        # Connections for signals that update these labels
        try:
            self.now_playing_changed.connect(self.now_playing_label.setText)
            self.status_changed.connect(self.status_label.setText)
            self.label_refresh.connect(self.update_now_playing_label)
        except Exception:
            pass

    def _init_meta_section(self):
        """Restore Channel and Format information row."""
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 4, 0, 4)
        meta_row.setSpacing(8)
        
        self.channel_label = QLabel(self.i18n.t('channel_label'))
        self.channel_value = QLabel(self.settings.value(KEY_CHANNEL, 'J-POP'))
        self.channel_value.setStyleSheet("font-weight: bold;")
        
        self.format_label = QLabel(self.i18n.t('format_label'))
        self.format_value = QLabel(self.settings.value(KEY_FORMAT, 'Vorbis'))
        self.format_value.setStyleSheet("font-weight: bold;")
        
        meta_row.addWidget(self.channel_label)
        meta_row.addWidget(self.channel_value)
        meta_row.addStretch(1)
        meta_row.addWidget(self.format_label)
        meta_row.addWidget(self.format_value)
        
        self._layout.addLayout(meta_row)

    def _init_controls_section(self):
        """
        Sets up the primary playback controls (Play, Pause, Stop) and the
        volume/mute management widgets.
        """

        # Main Playback Controls
        # Row 1: Play (Priority 1)
        play_row = QHBoxLayout()
        self.play_button = QPushButton(self.i18n.t('play'))
        self.play_button.setFixedHeight(40)
        if hasattr(self, '_icon_play'):
            self.play_button.setIcon(self._icon_play)
        self.play_button.setIconSize(QSize(20, 20))
        self.play_button.clicked.connect(self.play_stream)
        play_row.addWidget(self.play_button)
        self._layout.addLayout(play_row)
        
        # Row 2: Pause and Stop (Priority 2)
        secondary_controls_layout = QHBoxLayout()
        secondary_controls_layout.setSpacing(12)
        
        self.pause_button = QPushButton(self.i18n.t('pause'))
        self.pause_button.setFixedHeight(40)
        if hasattr(self, '_icon_pause'):
            self.pause_button.setIcon(self._icon_pause)
        self.pause_button.setIconSize(QSize(20, 20))
        self.pause_button.clicked.connect(self.pause_resume)

        self.stop_button = QPushButton(self.i18n.t('stop'))
        self.stop_button.setFixedHeight(40)
        if hasattr(self, '_icon_stop'):
            self.stop_button.setIcon(self._icon_stop)
        self.stop_button.setIconSize(QSize(20, 20))
        self.stop_button.clicked.connect(self.stop_stream)
        
        secondary_controls_layout.addWidget(self.pause_button)
        secondary_controls_layout.addWidget(self.stop_button)
        self._layout.addLayout(secondary_controls_layout)

        # Volume Controls
        vol_row = QHBoxLayout()
        self.volume_label = QLabel(self.i18n.t('volume'))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        
        saved_vol = self.settings.value(KEY_VOLUME, 60)
        try:
            self.volume_slider.setValue(int(saved_vol))
        except Exception:
            self.volume_slider.setValue(60)
            
        self.volume_slider.valueChanged.connect(self.change_volume)
        
        self.mute_button = QPushButton(self.i18n.t('mute'))
        self.mute_button.setCheckable(True)
        self.mute_button.setFixedHeight(30)
        icon_mute = self.style().standardIcon(self.style().SP_MediaVolume)
        self.mute_button.setIcon(icon_mute)
        self.mute_button.clicked.connect(self.toggle_mute)
        
        self.volume_value_label = QLabel(f"{saved_vol}%")
        self.volume_value_label.setFixedWidth(40)
        
        # Autoplay Toggle (on main UI)
        self.autoplay_checkbox = QCheckBox(self.i18n.t('settings_autoplay'))
        self.autoplay_checkbox.setChecked(self._get_bool(KEY_AUTOPLAY, False))
        self.autoplay_checkbox.toggled.connect(self._on_autoplay_toggled)
        
        vol_row.addWidget(self.volume_label)
        vol_row.addWidget(self.volume_slider)
        vol_row.addWidget(self.volume_value_label)
        vol_row.addWidget(self.mute_button)
        vol_row.addWidget(self.autoplay_checkbox)
        self._layout.addLayout(vol_row)

        # Emergency "FORCE STOP" button (kept as requested)
        self.force_stop_button = QPushButton("FORCE STOP")
        self.force_stop_button.clicked.connect(self.force_stop_all)
        self._layout.addWidget(self.force_stop_button)

    def _init_progress_section(self):
        """
        Initializes the buffering progress bar and connects visual feedback signals
        from the playback system to UI updates.
        """
        self.buffer_bar = QProgressBar()
        self.buffer_bar.setRange(0, 100)
        self.buffer_bar.setVisible(False)
        self._layout.addWidget(self.buffer_bar)
        
        try:
            self.buffering_progress.connect(self.buffer_bar.setValue)
            self.buffering_visible.connect(self.buffer_bar.setVisible)
            self.buffering_indeterminate.connect(self._set_buffer_bar_indeterminate)
        except Exception:
            pass

    def _init_sleep_timer_section(self):
        """Restore Sleep Timer UI controls."""
        sleep_group_layout = QVBoxLayout()
        sleep_group_layout.setSpacing(4)
        
        title_row = QHBoxLayout()
        self.sleep_title = QLabel(self.i18n.t('sleep_timer'))
        self.sleep_title.setStyleSheet("font-weight: bold; margin-top: 8px;")
        title_row.addWidget(self.sleep_title)
        title_row.addStretch(1)
        sleep_group_layout.addLayout(title_row)
        
        controls_row = QHBoxLayout()
        self.sleep_minutes_label = QLabel(self.i18n.t('sleep_minutes'))
        self.spin_sleep = QSpinBox()
        self.spin_sleep.setRange(1, 480)
        try:
            self.spin_sleep.setValue(int(self.settings.value(KEY_SLEEP_MINUTES, 30)))
        except Exception:
            self.spin_sleep.setValue(30)
        
        self.btn_sleep_start = QPushButton(self.i18n.t('sleep_start'))
        self.btn_sleep_start.clicked.connect(self.sleep_start_clicked)
        
        self.btn_sleep_cancel = QPushButton(self.i18n.t('sleep_cancel'))
        self.btn_sleep_cancel.clicked.connect(self.sleep_cancel_clicked)
        
        controls_row.addWidget(self.sleep_minutes_label)
        controls_row.addWidget(self.spin_sleep)
        controls_row.addWidget(self.btn_sleep_start)
        controls_row.addWidget(self.btn_sleep_cancel)
        
        # Ensure consistent heights for sleeper controls
        for w in (self.spin_sleep, self.btn_sleep_start, self.btn_sleep_cancel):
            w.setFixedHeight(30)
            
        sleep_group_layout.addLayout(controls_row)
        
        self._layout.addLayout(sleep_group_layout)

    def _init_audio_backend(self):
        """
        Identifies and initializes the available audio backend.
        Prioritizes FFmpeg (PyAudio) and falls back to VLC if FFmpeg is unavailable.
        Also synchronizes initial volume and mute states.
        """
        libvlc_path = self.settings.value(KEY_LIBVLC_PATH, '') or None
        try:
            network_caching = int(self.settings.value(KEY_NETWORK_CACHING, 1000))
        except Exception:
            network_caching = 1000
            
        # Try FFmpeg first
        self.player = PlayerFFmpeg(on_event=self._on_player_event)
        if not self.player.is_ready():
            self.log.info("[BACKEND] FFmpeg failed or not found, using VLC fallback.")
            self.player = PlayerVLC(on_event=self._on_player_event, libvlc_path=libvlc_path, network_caching_ms=network_caching)

        # Set initial audio state
        try:
            self.player.set_volume(self.volume_slider.value())
            is_muted = self._get_bool(KEY_MUTE, False)
            self.mute_button.setChecked(is_muted)
            self.player.set_mute(is_muted)
            self.mute_button.setText(self.i18n.t('unmute') if is_muted else self.i18n.t('mute'))
        except Exception:
            pass

    def _init_timers_and_console(self):
        """
        Initializes background timers for session tracking, sleep mode, and UI refresh.
        Also sets up the developer console for real-time logging.
        """
        self._session_seconds = 0
        self._session_timer = QTimer(self)
        self._session_timer.setInterval(1000)
        self._session_timer.timeout.connect(self._on_session_tick)
        
        # Song Progress Ticker (Smoother transitions with 50ms interval)
        self.song_tick_timer = QTimer(self)
        self.song_tick_timer.setTimerType(Qt.PreciseTimer)
        self.song_tick_timer.setInterval(50)
        self.song_tick_timer.timeout.connect(self._on_song_tick)
        self.song_tick_timer.start()
        
        # Track last integer second to avoid redundant label updates
        self._last_integer_second = -1
        
        # Sleep Timer
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setInterval(1000)
        self._sleep_timer.timeout.connect(self._sleep_tick)
        
        # UI Refresh Timer for "Now Playing" and Seek/Progress
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(1000)
        self._progress_timer.timeout.connect(self.update_now_playing_label)
        self._progress_timer.start()

        # Connections for UI signals
        try:
            self.schedule_play.connect(self._schedule_play_stream)
            self.notify_tray.connect(self._notify_tray)
        except Exception:
            pass

        # Dev Console
        try:
            self.dev_console = DevConsole(self, translator=self.i18n, logger=self.log)
            if self._get_bool(KEY_DEV_CONSOLE_ENABLED, False):
                self.dev_console.activate_logging()
        except Exception:
            self.dev_console = None

    def _init_websocket(self):
        """Configura la connessione WebSocket."""
        init_channel = self.settings.value(KEY_CHANNEL, 'J-POP')
        self.ws = NowPlayingWS(
            on_now_playing=self._on_now_playing,
            on_error_text=self._on_ws_error_text,
            on_closed_text=self._on_ws_closed_text,
            ws_url=self._get_ws_url_for_channel(init_channel),
        )
        self.ws.start()

    def _init_tray(self):
        """Initialize system tray manager."""
        try:
            self._tray_enabled = self._get_bool(KEY_TRAY_ENABLED, True)
            self.tray_mgr = TrayManager(
                self, self.i18n,
                on_show_window=self.showNormal,
                on_open_settings=self.open_settings,
                on_change_channel=self._tray_change_channel,
                on_change_format=self._tray_change_format,
                on_toggle_play_pause=self._tray_toggle_play_pause,
                on_stop_stream=self.stop_stream,
                on_toggle_mute=self.toggle_mute_shortcut,
            )
            self.tray_mgr.ensure_tray_enabled(self._tray_enabled, window_icon=self.windowIcon())
            self.tray_icon_refresh.connect(self.update_tray_icon)
        except Exception:
            pass

    def _init_extra_logic(self):
        """Final UI polish and logic hooks (Theme, Autoplay, Global Shortcuts)."""
        try:
            self.apply_theme()
            self.backend_status_refresh.connect(self.update_vlc_status_label)
            
            # Autoplay
            if self._get_bool(KEY_AUTOPLAY, False):
                QTimer.singleShot(1000, self.play_stream)
                
            # Global Keyboard Shortcuts (Class scope)
            QShortcut(QKeySequence(Qt.Key_Up), self, self._vol_up)
            QShortcut(QKeySequence(Qt.Key_Down), self, self._vol_down)
            QShortcut(QKeySequence(Qt.Key_Plus), self, self._vol_up)
            QShortcut(QKeySequence(Qt.Key_Minus), self, self._vol_down)
            QShortcut(QKeySequence("="), self, self._vol_up)
            
            # Legacy/Specific Shortcuts
            QShortcut(QKeySequence("Space"), self, self.pause_resume)
            QShortcut(QKeySequence("S"), self, self.stop_stream)
            QShortcut(QKeySequence("M"), self, self.toggle_mute_shortcut)
        except Exception:
            pass

    # ------------------- Volume Helpers -------------------

    def _vol_up(self) -> None:
        """Aumenta il volume di 5%."""
        try:
            if hasattr(self, 'volume_slider'):
                val = self.volume_slider.value()
                self.volume_slider.setValue(min(100, val + 5))
        except Exception:
            pass

    def _vol_down(self) -> None:
        """Diminuisce il volume di 5%."""
        try:
            if hasattr(self, 'volume_slider'):
                val = self.volume_slider.value()
                self.volume_slider.setValue(max(0, val - 5))
        except Exception:
            pass

    # ------------------- Event & Signal Handlers -------------------

    # 1. Qt Window & Lifecycle Events
    def closeEvent(self, event) -> None:
        """Gestisce la chiusura della finestra con l'opzione Tray vs Esci."""
        try:
            self.settings.setValue(KEY_WINDOW_GEOMETRY, self.saveGeometry())
        except Exception:
            pass

        tray_enabled = self._get_bool(KEY_TRAY_ENABLED, True)
        if not tray_enabled:
            self._cleanup_before_close()
            event.accept()
            return

        dont_ask = self._get_bool(KEY_DONT_ASK_ON_CLOSE, False)
        close_to_tray = self._get_bool(KEY_CLOSE_TO_TRAY, False)

        if dont_ask:
            if close_to_tray:
                self.hide()
                event.ignore()
            else:
                self._cleanup_before_close()
                event.accept()
            return

        try:
            msg = QMessageBox(self)
            msg.setWindowTitle(self.i18n.t('close_dialog_title'))
            msg.setText(self.i18n.t('close_dialog_text'))
            msg.setIcon(QMessageBox.Question)
            
            tray_btn = msg.addButton(self.i18n.t('close_option_tray'), QMessageBox.AcceptRole)
            quit_btn = msg.addButton(self.i18n.t('close_option_quit'), QMessageBox.DestructiveRole)
            
            cb = QCheckBox(self.i18n.t('close_remember'))
            msg.setCheckBox(cb)
            
            try:
                if self._get_bool(KEY_DARK_MODE, False):
                    hwnd = int(msg.winId())
                    val = ctypes.c_int(1)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
            except Exception: pass

            msg.exec_()
            remember = cb.isChecked()
            choice_tray = (msg.clickedButton() == tray_btn)
            
            if remember:
                self.settings.setValue(KEY_DONT_ASK_ON_CLOSE, True)
                self.settings.setValue(KEY_CLOSE_TO_TRAY, choice_tray)
            
            if choice_tray:
                self.hide()
                event.ignore()
            else:
                self._cleanup_before_close()
                event.accept()
        except Exception:
            self._cleanup_before_close()
            event.accept()

    def _cleanup_before_close(self) -> None:
        """Operazioni di pulizia prima dell'uscita definitiva."""
        try:
            if hasattr(self, 'dev_console') and self.dev_console:
                self.dev_console.deactivate_logging()
                self.dev_console.close()
            if hasattr(self, '_session_timer') and self._session_timer:
                self._session_timer.stop()
            if hasattr(self, 'player') and self.player:
                self.player.stop()
            if hasattr(self, 'ws') and self.ws:
                self.ws.stop()
        except Exception: pass

    def showEvent(self, event) -> None:
        try:
            super().showEvent(event)
            self._apply_windows_titlebar_dark_mode(self._get_bool(KEY_DARK_MODE, False))
        except Exception: pass

    def changeEvent(self, event) -> None:
        try:
            if event.type() == QEvent.WindowStateChange:
                if self.isMinimized() and self._get_bool(KEY_TRAY_ENABLED, True) and self._get_bool(KEY_TRAY_HIDE_ON_MINIMIZE, True):
                    self.hide()
                    event.accept()
                    return
            super().changeEvent(event)
        except Exception: pass

    # 2. Player Backend & Audio Events
    def _on_player_event(self, code: str, value: Optional[int] = None) -> None:
        """Gestisce gli eventi del backend (FFmpeg/VLC) aggiornando lo stato UI."""
        try:
            c = (str(code).lower() if code is not None else '')
            if c == 'opening':
                self.status_changed.emit(self.t('status_opening'))
                self.buffering_visible.emit(True)
                self.buffering_indeterminate.emit(True)
                self.backend_status_refresh.emit()
            elif c == 'buffering':
                self.status_changed.emit(self.t('status_buffering'))
                self.buffering_visible.emit(True)
                if isinstance(value, int) and 0 <= value <= 100:
                    self.buffering_indeterminate.emit(False)
                    self.buffering_progress.emit(int(value))
                else:
                    self.buffering_indeterminate.emit(True)
            elif c == 'playing':
                self.status_changed.emit(self.t('status_playing'))
                self.buffering_visible.emit(False)
                self.buffering_indeterminate.emit(False)
                if self._get_bool(KEY_SESSION_TIMER_ENABLED, True):
                    if self._session_timer and not self._session_timer.isActive():
                        self._session_timer.start()
                self.tray_icon_refresh.emit()
                self._update_tray_controls()
            elif c == 'paused':
                self.status_changed.emit(self.t('status_paused'))
                if self._session_timer and self._session_timer.isActive():
                    self._session_timer.stop()
                self._ui_paused = True
                self._update_tray_controls()
            elif c in ('stopped', 'ended'):
                self.status_changed.emit(self.t('status_stopped'))
                self.buffering_visible.emit(False)
                if c == 'ended':
                    self._skip_session_reset_once = True
                    self.schedule_play.emit(1000)
                    self.notify_tray.emit("Listen.moe", "Audio riavviato: il timer di sessione continua")
                else:
                    # Reset on explicit stop (unless skip flag is set)
                    if not getattr(self, '_skip_session_reset_once', False):
                        if self._session_timer: self._session_timer.stop()
                        self._session_seconds = 0
                        self.log.info("[UI] session_timer reset due to explicit stop")
                    # Clear the skip flag after use (regardless of whether it was used)
                    self._skip_session_reset_once = False
                self._update_session_label()
                self._ui_paused = False
                self._update_tray_controls()
                self.tray_icon_refresh.emit()
            elif c in ('error', 'libvlc_init_failed'):
                self.status_changed.emit(self.t('status_error'))
                self.buffering_visible.emit(False)
                self._skip_session_reset_once = True
                self.schedule_play.emit(1200)
                self.notify_tray.emit("Listen.moe", "Errore audio: tentativo di riavvio...")
        except Exception: pass

    def _schedule_play_stream(self, delay_ms: int) -> None:
        """Slot per avviare lo stream dopo un delay (thread-safe UI call)."""
        try: QTimer.singleShot(int(delay_ms), self.play_stream)
        except Exception: self.play_stream()

    # 3. WebSocket & Metadata Events
    def _on_now_playing(self, title: str, artist: str, duration: Optional[int] = None, start_ts: Optional[float] = None):
        try:
            try:
                self.log.debug(f"[DEV] Metadata received: title={title}, dur={duration}, start_ts={start_ts}")
            except Exception: pass
            
            self._current_title = title or self.t('unknown')
            self._current_artist = artist or ''
            self._current_duration_seconds = int(duration) if duration is not None and int(duration) > 0 else None
            self._current_start_epoch = float(start_ts) if start_ts is not None else None
            
            # --- Automatic Skew Compensation ---
            try:
                import time
                if self._current_start_epoch is not None:
                    raw_elapsed = time.time() - self._current_start_epoch
                    # If PC is significantly behind (elapsed is negative), offset it.
                    # We also allow up to 10s of positive skew (for buffering slack).
                    if raw_elapsed < -2:
                        self._skew_offset = abs(raw_elapsed)
                        self.log.info(f"[UI] Automatic skew compensation applied: +{self._skew_offset:.1f}s")
                    else:
                        self._skew_offset = 0
                else:
                    self._skew_offset = 0
            except Exception:
                self._skew_offset = 0
            
            # --- Update Song Progress Bar ---
            if hasattr(self, 'song_progress'):
                if self._current_duration_seconds and self._current_duration_seconds > 0:
                    # Multiplier (1000) for sub-second smoothness
                    self.song_progress.setMaximum(int(self._current_duration_seconds * 1000))
                    self.song_progress.setValue(0)
                    self.song_progress.show()
                else:
                    self.song_progress.hide()
            
            self.label_refresh.emit()
            if self._get_bool(KEY_TRAY_NOTIFICATIONS, True) and self._get_bool(KEY_TRAY_ENABLED, True):
                msg_title = self.i18n.t('now_playing_prefix')
                body = f"{self._current_title}" + (f" — {self._current_artist}" if self._current_artist else "")
                self.notify_tray.emit(msg_title, body)
            self.backend_status_refresh.emit()
        except Exception: pass

    def _on_ws_error_text(self, text: str) -> None:
        try: self.status_changed.emit(str(text))
        except Exception: pass

    def _on_ws_closed_text(self, text: str) -> None:
        try: self.status_changed.emit(str(text))
        except Exception: pass

    # 4. Timer & Tray Action Events
    def _on_session_tick(self) -> None:
        try:
            self._session_seconds += 1
            self._update_session_label()
            self.update_tray_texts()
        except Exception: pass

    def _update_session_label(self) -> None:
        try:
            t = self._format_hhmmss(self._session_seconds)
            if hasattr(self, 'session_label'):
                self.session_label.setText(self.i18n.t('session_timer', time=t))
        except Exception: pass

    def _on_song_tick(self) -> None:
        """Updates the song progress bar every second based on start timestamp."""
        try:
            import time
            now = time.time()
            epoch = getattr(self, '_current_start_epoch', None)
            dur = getattr(self, '_current_duration_seconds', None)
            
            if epoch is None or dur is None:
                # Log once every 10s if metadata is missing to see if ticker is alive
                if int(now) % 10 == 0:
                    self.log.debug("[DEV] Song ticker ALIVE: (waiting for metadata)")
                return
            
            # Apply skew offset to the local clock comparison
            skew = getattr(self, '_skew_offset', 0)
            elapsed_raw = now - epoch + skew
            
            # --- Progress Bar (Fluid 50ms update) ---
            # Use milliseconds for the internal bar value
            effective_ms = int(max(0, min(elapsed_raw, dur)) * 1000)
            self.song_progress.setValue(effective_ms)

            # --- Label Update (Optimized 1s update) ---
            current_int_sec = int(elapsed_raw)
            if current_int_sec != getattr(self, '_last_integer_second', -1):
                self._last_integer_second = current_int_sec
                
                # Diagnostic log for [DEV] filters (every 5s)
                if current_int_sec % 5 == 0:
                    self.log.debug(f"[DEV] Song ticker: elapsed={current_int_sec}s (skewed), dur={dur}s, skew_val={skew:.1f}")

                # Update the [M:SS] text in the metadata label every second
                self.update_now_playing_label()
        except Exception:
            pass

    def _sleep_tick(self) -> None:
        try:
            if self._sleep_remaining_sec <= 0:
                if self._sleep_timer: self._sleep_timer.stop()
                if hasattr(self, 'sleep_label'): self.sleep_label.setText("")
                if self._get_bool(KEY_SLEEP_STOP_ON_END, True): self.stop_stream()
                return
            self._sleep_remaining_sec -= 1
            if self._sleep_saved_volume is not None and self._sleep_remaining_sec <= self._sleep_fadeout_sec:
                new_vol = max(0, int(self._sleep_saved_volume * self._sleep_remaining_sec / max(1, self._sleep_fadeout_sec)))
                if hasattr(self, 'volume_slider'): self.volume_slider.setValue(new_vol)
            if hasattr(self, 'sleep_label'):
                self.sleep_label.setText(self.t('sleep_remaining', time=self._format_mmss(self._sleep_remaining_sec)))
        except Exception: pass

    def _tray_toggle_play_pause(self) -> None:
        """Handler for tray icon play/pause command."""
        try:
            has_player = hasattr(self, 'player') and self.player is not None
            is_playing = bool(self.player.is_playing()) if has_player else False
            is_paused = bool(getattr(self.player, 'is_paused', lambda: False)()) if has_player else False
            
            if has_player and (is_playing or is_paused):
                self.pause_resume()
            else:
                self.play_stream()
        except Exception:
            pass

    def _update_tray_controls(self) -> None:
        """Utility per aggiornare i controlli della tray in base allo stato del player."""
        try:
            if hasattr(self, 'tray_mgr') and self.tray_mgr:
                is_playing = bool(self.player.is_playing())
                is_paused = bool(getattr(self.player, 'is_paused', lambda: False)()) or self._ui_paused
                is_muted = bool(self.player.get_mute()) if hasattr(self.player, 'get_mute') else False
                self.tray_mgr.update_controls_state(is_playing and not is_paused, is_paused, is_muted)
        except Exception: pass

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
        if hasattr(self, 'autoplay_checkbox'):
            self.autoplay_checkbox.setText(self.i18n.t('settings_autoplay'))
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
            accent = getattr(self, 'COLOR_ACCENT', '#c2185b')
            app = QApplication.instance()
            if not app:
                return
            if dark:
                app.setStyleSheet(
                    f"""
                    QWidget {{ background-color: #121212; color: #e0e0e0; }}
                    QLabel#headerLabel {{ font-size: 16px; font-weight: 600; color: #ffffff; }}
                    QLabel#nowPlayingLabel {{ font-size: 14px; font-weight: 500; color: #e0e0e0; }}
                    QPushButton {{ background-color: #1e1e1e; color: #e0e0e0; border: 1px solid #333; padding: 6px 10px; border-radius: 4px; }}
                    QPushButton:hover {{ background-color: #2a2a2a; }}
                    QPushButton#menuButton {{ background-color: transparent; border: none; border-radius: 0; padding: 4px 6px; color: #e0e0e0; font-size: 13px; }}
                    QPushButton#menuButton:hover {{ background-color: {accent}; color: #ffffff; }}
                    QPushButton:disabled {{ background-color: #1a1a1a; color: #777; border-color: #2a2a2a; }}
                    QLineEdit, QSpinBox, QComboBox {{ background-color: #1a1a1a; color: #e0e0e0; border: 1px solid #333; border-radius: 4px; padding: 4px; }}
                    QMenu {{ background-color: #121212; color: #e0e0e0; border: 1px solid #333; }}
                    QToolTip {{ background-color: #2a2a2a; color: #ffffff; border: 1px solid #444; }}
                    QProgressBar {{ background-color: #1a1a1a; border: 1px solid #333; color: #e0e0e0; border-radius: 4px; text-align: center; }}
                    QProgressBar::chunk {{ background-color: {accent}; border-radius: 4px; }}
                    QProgressBar#songProgressBar {{ background-color: #222; border: none; height: 4px; border-radius: 2px; }}
                    QSlider::groove:horizontal {{ height: 6px; background: #333; border-radius: 3px; }}
                    QSlider::handle:horizontal {{ background: {accent}; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }}
                    """
                )
            else:
                app.setStyleSheet("")
            
            # Synchronize custom progress bar color
            if hasattr(self, 'song_progress'):
                self.song_progress.setAccentColor(accent)
            
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
                                self._restart_playback_with_session_persistence(
                                    notification_body="Audio riavviato: il timer di sessione continua"
                                )
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
                            self._restart_playback_with_session_persistence(
                                notification_body="Audio riavviato: il timer di sessione continua"
                            )
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
                        if not self.player.is_ready():
                            self.player = PlayerVLC(on_event=getattr(self, '_on_player_event', None), libvlc_path=new_path, network_caching_ms=new_nc)
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


    def update_now_playing_label(self):
        title = self._current_title or self.t('unknown')
        artist = self._current_artist or ''
        prefix = self.t('now_playing_prefix')
        text = f"{prefix} <b>{title}</b>" + (f" — {artist}" if artist and title != '–' else "")
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
                        skew = int(getattr(self, '_skew_offset', 0))
                        elapsed = int(time.time()) - int(self._current_start_epoch) + skew
                    except Exception:
                        elapsed = None
                    # Use remaining only when elapsed is within plausible range (+/- 60s slack for clock skew)
                    if elapsed is not None and -60 <= elapsed <= dur + 60:
                        # If PC clock is behind (elapsed < 0), remaining shouldn't exceed dur
                        remaining = dur - max(0, elapsed)
                        if remaining < 0:
                            remaining = 0
                        mmss = self._format_mmss(remaining)
                    else:
                        # Fallback to total duration to avoid misleading or extreme values
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

    def _restart_playback_with_session_persistence(self, notification_body: Optional[str] = None) -> None:
        """Helper to restart playback while preserving session timer and showing an optional notification."""
        try:
            self._skip_session_reset_once = True
            self.stop_stream(reset_session=False)
            # Small delay to ensure backend has released resources
            QTimer.singleShot(200, self.play_stream)
            
            if notification_body and self._get_bool(KEY_TRAY_NOTIFICATIONS, True) and self._get_bool(KEY_TRAY_ENABLED, True):
                self.notify_tray.emit("Listen.moe", notification_body)
        except Exception:
            # Fallback if async timer fails
            try: self.play_stream()
            except Exception: pass


    # ------------------- Tray helpers (static) -------------------
    def update_tray_texts(self) -> None:
        try:
            if not hasattr(self, 'tray_mgr') or self.tray_mgr is None:
                return
            self.tray_mgr.update_tooltip(self._get_tray_tooltip())
        except Exception:
            pass

    def _get_tray_tooltip(self) -> str:
        """Centralized logic to compose the tray tooltip from current state."""
        try:
            # Header
            try:
                header = self.i18n.t('header').format(
                    channel=self.settings.value(KEY_CHANNEL, 'J-POP'),
                    format=self.settings.value(KEY_FORMAT, 'Vorbis')
                )
            except Exception:
                if hasattr(self, 'label'):
                    header = self.label.text()
                else:
                    header = APP_TITLE

            # Now Playing
            now = ""
            if hasattr(self, 'now_playing_label'):
                text = self.now_playing_label.text()
                # Remove HTML tags for tooltip if present (simplified check)
                now = re.sub(r'<[^>]+>', '', text)

            # Session
            session_enabled = self._get_bool(KEY_SESSION_TIMER_ENABLED, True)
            session = ""
            if session_enabled and hasattr(self, 'session_label'):
                session = self.session_label.text()

            # Join parts
            parts = [header]
            if now: parts.append(now)
            if session: parts.append(session)
            return "\n".join(parts)
        except Exception:
            return APP_TITLE

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
            # Apply visibility/icon/tooltip
            try:
                self.tray_mgr.ensure_tray_enabled(self._tray_enabled, window_icon=self.windowIcon(), tooltip=self._get_tray_tooltip())
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
            self.tray_mgr.ensure_tray_enabled(self._tray_enabled, window_icon=self.windowIcon(), tooltip=self._get_tray_tooltip())
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
                self._restart_playback_with_session_persistence(
                    notification_body="Audio riavviato: il timer di sessione continua"
                )
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
                # Preserva il timer se stiamo già riproducendo (es. cambio URL o click Riproduci mentre attivo)
                try:
                    if self.player.is_playing() or getattr(self.player, 'is_paused', lambda: False)():
                        self._skip_session_reset_once = True
                except Exception:
                    pass
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
                        self.log.debug("[UI] pause_resume(pre-toggle): new_paused=%s, is_muted=%s", new_paused, is_muted)
                        self.tray_mgr.update_controls_state(not new_paused, new_paused, is_muted)
                except Exception:
                    pass
                # Esegui il toggle del backend
                self.player.pause_toggle()
                # Gestisci il session timer e aggiorna solo il tooltip
                try:
                    if self._get_bool(KEY_SESSION_TIMER_ENABLED, True):
                        if new_paused:
                            if self._session_timer and self._session_timer.isActive():
                                self._session_timer.stop()
                        else:
                            if self._session_timer and not self._session_timer.isActive():
                                self._session_timer.start()
                        if hasattr(self, 'session_label'):
                            self.session_label.show()  # keep visible
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

    def change_volume(self, value: int) -> None:
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

    def toggle_mute(self, checked: bool) -> None:
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

    def _on_autoplay_toggled(self, checked: bool) -> None:
        try:
            self.settings.setValue(KEY_AUTOPLAY, 'true' if checked else 'false')
            self.log.info(f"[UI] autoplay toggled -> {checked}")
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

