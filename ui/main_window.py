import email.utils
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Dict, Optional, Set

from PyQt6.QtCore import (
    QEvent,
    QPointF,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from audio.player_ffmpeg import PlayerFFmpeg
from audio.player_mpv import PlayerMPV
from audio.player_vlc import PlayerVLC
from core.config import STREAMS
from core.constants import (
    APP_SETTINGS,
    APP_TITLE,
    KEY_AUDIO_BACKEND,
    KEY_AUDIO_DEVICE_INDEX,
    KEY_AUTOPLAY,
    KEY_CHANNEL,
    KEY_CLOSE_TO_TRAY,
    KEY_DEV_CONSOLE_ENABLED,
    KEY_DEV_CONSOLE_SHOW_DEV,
    KEY_DONT_ASK_ON_CLOSE,
    KEY_FORMAT,
    KEY_LANG,
    KEY_LIBVLC_PATH,
    KEY_MUTE,
    KEY_NETWORK_CACHING,
    KEY_SESSION_TIMER_ENABLED,
    KEY_SLEEP_MINUTES,
    KEY_SLEEP_STOP_ON_END,
    KEY_TRAY_ENABLED,
    KEY_TRAY_HIDE_ON_MINIMIZE,
    KEY_TRAY_NOTIFICATIONS,
    KEY_VOLUME,
    KEY_WINDOW_GEOMETRY,
    ORG_NAME,
)
from core.i18n import I18n
from core.logger import get_logger
from network.ws_client import NowPlayingWS
from ui.custom_titlebar import CustomTitleBar, install_size_grip
from ui.dev_console import DevConsole
from ui.settings_dialog import SettingsDialog, SlidingStackedWidget
from ui.themes.cyber_moe import PALETTE, get_cyber_moe_stylesheet
from ui.tray_manager import TrayManager
from ui.widgets.ambient_cover import (
    AmbientCoverCard,
    AnimatedTrackLabel,
    FullBleedCanvas,
    LiveEqualizerBadge,
)
from ui.widgets.playback_controls import PlaybackControls
from ui.widgets.segmented_switch import SegmentedSwitch, SettingsIconButton
from ui.widgets.sleep_timer_widget import SleepTimerWidget
from ui.widgets.status_footer import StatusFooter
from ui.windows_titlebar import apply_windows_titlebar_dark_mode

_IS_WIN32 = sys.platform == "win32"


# Custom Progress Bar with Scrubber Playhead, Gradient Fill & 60 FPS Play/Buffer Animation
class SmoothProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._max = 100
        self._accent_color = QColor(PALETTE["accent"])
        self._buffering_active = False
        self._buffering_indeterminate = False
        self._buffering_percent = 0
        self._launch_progress = 1.0
        self._pulse_ring = 1.0
        self._shimmer_phase = 0.0
        self._display_ratio: Optional[float] = None

        self.setFixedHeight(16)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)

    def setAccentColor(self, color_str):
        self._accent_color = QColor(color_str)
        self.update()

    def setMaximum(self, val):
        self._max = max(1, val)
        self.update()

    def setValue(self, val):
        if self._value != val:
            old_ratio = max(0.0, min(1.0, self._value / max(1, self._max)))
            self._value = val
            new_ratio = max(0.0, min(1.0, self._value / max(1, self._max)))
            # Smoothly glide when the track position jumps (e.g. song or channel change)
            if abs(new_ratio - old_ratio) > 0.03 and self.isVisible():
                if self._display_ratio is None:
                    self._display_ratio = old_ratio
                if not self._anim_timer.isActive():
                    self._anim_timer.start()
            else:
                self._display_ratio = new_ratio
            self.update()

    def value(self):
        return self._value

    def trigger_play_launch(self) -> None:
        """Trigger a 60 FPS sweep & glow pulse when Play is clicked."""
        self._launch_progress = 0.0
        self._pulse_ring = 0.0
        if not self._anim_timer.isActive():
            self._anim_timer.start()
        self.update()

    def set_buffering_active(self, active: bool) -> None:
        self._buffering_active = bool(active)
        if self._buffering_active:
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        self.update()

    def set_buffering_indeterminate(self, indeterminate: bool) -> None:
        self._buffering_indeterminate = bool(indeterminate)
        if self._buffering_indeterminate and self._buffering_active:
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        self.update()

    def set_buffering_percent(self, percent: int) -> None:
        self._buffering_percent = max(0, min(100, int(percent)))
        self.update()

    def _tick_anim(self) -> None:
        still_running = False
        if self._launch_progress < 1.0:
            self._launch_progress = min(1.0, self._launch_progress + 0.055)
            still_running = True
        if self._pulse_ring < 1.0:
            self._pulse_ring = min(1.0, self._pulse_ring + 0.045)
            still_running = True
        if self._buffering_active:
            self._shimmer_phase = (self._shimmer_phase + 0.032) % 1.0
            still_running = True
        if self._display_ratio is not None:
            target_r = max(0.0, min(1.0, self._value / max(1, self._max)))
            diff_r = target_r - self._display_ratio
            if abs(diff_r) > 0.004:
                self._display_ratio += diff_r * 0.26
                still_running = True
            else:
                self._display_ratio = target_r

        if not still_running:
            self._anim_timer.stop()
        self.update()

    def paintEvent(self, a0):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        track_h = 6.5
        track_r = track_h / 2.0
        track_y = (h - track_h) / 2.0
        margin_x = 7.0
        usable_w = max(1.0, w - 2 * margin_x)

        # 1. Background track (slightly larger dark glass groove with subtle border)
        track_rect = QRectF(margin_x, track_y, usable_w, track_h)
        painter.setBrush(QColor(255, 255, 255, 36))
        painter.setPen(QPen(QColor(255, 255, 255, 22), 0.8))
        painter.drawRoundedRect(track_rect, track_r, track_r)

        # Cubic-out easing for Play launch animation
        launch_ease = 1.0 - ((1.0 - self._launch_progress) ** 3)

        # 2. Buffering / Opening Shimmer Wave inside the main progress bar
        if self._buffering_active and (
            self._buffering_indeterminate or self._buffering_percent <= 0
        ):
            comet_w = max(44.0, usable_w * 0.34)
            travel = usable_w + comet_w
            cx = margin_x - comet_w + (self._shimmer_phase * travel)

            painter.save()
            clip_path = QPainterPath()
            clip_path.addRoundedRect(track_rect, track_r, track_r)
            painter.setClipPath(clip_path)

            grad = QLinearGradient(cx, 0.0, cx + comet_w, 0.0)
            c0 = QColor(self._accent_color)
            c0.setAlpha(0)
            c1 = QColor("#ff529a")
            c1.setAlpha(235)
            c2 = QColor(self._accent_color)
            c2.setAlpha(0)
            grad.setColorAt(0.0, c0)
            grad.setColorAt(0.5, c1)
            grad.setColorAt(1.0, c2)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawRect(QRectF(cx, track_y, comet_w, track_h))
            painter.restore()
            painter.end()
            return

        # 3. Determinate Progress Fill & Scrubber Playhead Dot
        if self._max > 0:
            if self._buffering_active and self._buffering_percent > 0:
                raw_ratio = max(0.0, min(1.0, self._buffering_percent / 100.0))
            elif self._display_ratio is not None:
                raw_ratio = max(0.0, min(1.0, self._display_ratio))
            else:
                raw_ratio = max(0.0, min(1.0, self._value / self._max))

            ratio = raw_ratio * launch_ease
            fill_w = ratio * usable_w
            if fill_w > 0:
                grad = QLinearGradient(margin_x, 0, margin_x + fill_w, 0)
                grad.setColorAt(0.0, self._accent_color)
                grad.setColorAt(0.7, QColor("#ff3d8b"))
                grad.setColorAt(1.0, QColor("#ff7eb6"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(grad)
                painter.drawRoundedRect(
                    QRectF(margin_x, track_y, fill_w, track_h), track_r, track_r
                )

                # Launch shimmer highlight sweeping along the filled bar
                if self._launch_progress < 1.0:
                    sheen_x = margin_x + fill_w * launch_ease
                    sheen_grad = QLinearGradient(sheen_x - 28.0, 0, sheen_x + 8.0, 0)
                    sheen_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
                    sheen_grad.setColorAt(
                        0.7, QColor(255, 255, 255, int(140 * (1.0 - self._launch_progress)))
                    )
                    sheen_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
                    painter.setBrush(sheen_grad)
                    painter.drawRoundedRect(
                        QRectF(margin_x, track_y, fill_w, track_h), track_r, track_r
                    )

            dot_x = margin_x + fill_w
            dot_y = h / 2.0

            # Expanding pulse ring when Play is clicked
            if self._pulse_ring < 1.0:
                ring_r = 5.4 + 7.5 * self._pulse_ring
                ring_col = QColor(self._accent_color)
                ring_col.setAlpha(int(170 * (1.0 - self._pulse_ring)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(ring_col, 1.8))
                painter.drawEllipse(QPointF(dot_x, dot_y), ring_r, ring_r)

            # Soft ambient halo around playhead dot
            halo_col = QColor(self._accent_color)
            halo_col.setAlpha(68)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo_col)
            painter.drawEllipse(QPointF(dot_x, dot_y), 7.2, 7.2)

            # Scrubber playhead dot
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(self._accent_color, 2.2))
            painter.drawEllipse(QPointF(dot_x, dot_y), 5.2, 5.2)
        painter.end()


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
    # Album cover bytes downloaded by background thread
    cover_data_ready = pyqtSignal(str, bytes)
    # Marshal websocket metadata updates to the UI thread
    now_playing_event = pyqtSignal(str, str, object, object, object)

    def __init__(self) -> None:
        super().__init__()
        # State variables
        self._playback_lock = threading.Lock()
        self._ui_paused: bool = False
        self._current_title: Optional[str] = None
        self._current_artist: Optional[str] = None
        self._current_duration_seconds: Optional[int] = None
        self._current_start_epoch: Optional[float] = None
        self._current_cover_ref: Optional[str] = None
        self._current_cover_url: Optional[str] = None
        self._cover_cache: Dict[str, QPixmap] = {}
        self._cover_download_lock = threading.Lock()
        self._cover_download_inflight: Set[str] = set()
        self._session_seconds = 0
        self._sleep_remaining_sec = 0
        self._sleep_fadeout_sec = 15
        self._sleep_saved_volume: Optional[int] = None
        self._clock_sync_offset = 0.0  # Difference between server time and local CPU clock
        self._retry_count = 0
        self._max_retries = 10
        self._retry_pending = False

        # 1. Start initialization sequence
        self._init_settings_and_i18n()
        self._init_icons()
        self._init_ui_base()
        self._init_header_section()
        self._init_meta_section()
        self._init_controls_section()
        self._init_progress_section()
        self._init_sleep_timer_section()
        self._init_footer_section()
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
        saved_lang = self.settings.value(KEY_LANG, "it")
        self.i18n = I18n(saved_lang if saved_lang in ("it", "en") else "it")
        self._lang_map = {"Italiano": "it", "English": "en"}
        self.log = get_logger("KikuMoe")
        self._sync_clock_with_server()

    def _sync_clock_with_server(self):
        """Fetches the current server time from LISTEN.moe to calculate clock skew."""
        try:
            # We use a HEAD request to the main page which is faster
            # and guaranteed to have a Date header
            req = urllib.request.Request("https://listen.moe/", method="HEAD")
            with urllib.request.urlopen(req, timeout=5) as res:
                server_date_str = res.headers.get("Date")
                if server_date_str:
                    server_dt = email.utils.parsedate_to_datetime(server_date_str)
                    # Convert both to UTC for comparison
                    if server_dt.tzinfo is None:
                        server_dt = server_dt.replace(tzinfo=timezone.utc)
                    else:
                        server_dt = server_dt.astimezone(timezone.utc)

                    local_dt = datetime.now(timezone.utc)
                    self._clock_sync_offset = (server_dt - local_dt).total_seconds()
                    self.log.info(
                        f"[UI] Clock sync performed. Server offset: {self._clock_sync_offset:+.2f}s"
                    )
        except Exception as e:
            self.log.warning(f"[UI] Clock sync failed: {str(e)}. Using local clock.")
            self._clock_sync_offset = 0.0

    def _init_icons(self):
        """Load and prepare application icons for window and tray."""
        try:
            icon_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons")
            style = self.style() or QApplication.style()
            sp = QStyle.StandardPixmap

            # Loader helper considering fallback to standard icons
            def get_icon(name, std_fallback):
                path = os.path.join(icon_dir, name)
                icon = QIcon(path)
                if icon.isNull():
                    return style.standardIcon(std_fallback) if style is not None else QIcon()
                return icon

            self._icon_play_raw = get_icon("app_play.png", sp.SP_MediaPlay)
            self._icon_pause_raw = get_icon("app_pause.png", sp.SP_MediaPause)
            self._icon_stop_raw = get_icon("app_stop.png", sp.SP_MediaStop)
            self._icon_mute_raw = get_icon("app_mute.png", sp.SP_MediaVolumeMuted)
            self._icon_unmute_raw = get_icon("app_unmute.png", sp.SP_MediaVolume)
            self._icon_settings_raw = get_icon("app_settings.png", sp.SP_FileDialogDetailedView)
            self._icon_force_stop_raw = get_icon("app_force_stop.png", sp.SP_BrowserStop)
            self._icon_channel_raw = get_icon("app_channel.png", sp.SP_DriveNetIcon)
            self._icon_codec_raw = get_icon("app_codec.png", sp.SP_FileIcon)
            self._icon_quit_raw = get_icon("app_quit.png", sp.SP_DialogCloseButton)
            self._icon_app_raw = get_icon("Kikumoe - no txt.png", sp.SP_ComputerIcon)

            # Initial assignment
            self._icon_play = self._icon_play_raw
            self._icon_pause = self._icon_pause_raw
            self._icon_stop = self._icon_stop_raw
            self._icon_mute = self._icon_mute_raw
            self._icon_unmute = self._icon_unmute_raw
            self._icon_settings = self._icon_settings_raw
            self._icon_force_stop = self._icon_force_stop_raw
            self._icon_channel = self._icon_channel_raw
            self._icon_codec = self._icon_codec_raw
            self._icon_quit = self._icon_quit_raw
            self._icon_app = self._icon_app_raw
            self._icon_app_tray = self._make_tray_icon(self._icon_app_raw)

        except Exception as e:
            self.log.error(f"[UI] Error loading icons: {str(e)}")
            style = self.style() or QApplication.style()
            sp = QStyle.StandardPixmap
            self._icon_play = style.standardIcon(sp.SP_MediaPlay) if style is not None else QIcon()
            self._icon_stop = style.standardIcon(sp.SP_MediaStop) if style is not None else QIcon()
            self._icon_pause = (
                style.standardIcon(sp.SP_MediaPause) if style is not None else QIcon()
            )
            self._icon_mute = (
                style.standardIcon(sp.SP_MediaVolumeMuted) if style is not None else QIcon()
            )
            self._icon_unmute = (
                style.standardIcon(sp.SP_MediaVolume) if style is not None else QIcon()
            )
            self._icon_settings = (
                style.standardIcon(sp.SP_FileDialogDetailedView) if style is not None else QIcon()
            )
            self._icon_force_stop = (
                style.standardIcon(sp.SP_BrowserStop) if style is not None else QIcon()
            )
            self._icon_channel = (
                style.standardIcon(sp.SP_DriveNetIcon) if style is not None else QIcon()
            )
            self._icon_codec = style.standardIcon(sp.SP_FileIcon) if style is not None else QIcon()
            self._icon_quit = (
                style.standardIcon(sp.SP_DialogCloseButton) if style is not None else QIcon()
            )
            self._icon_app = (
                style.standardIcon(sp.SP_ComputerIcon) if style is not None else QIcon()
            )
            self._icon_app_tray = self._icon_app

    def _init_ui_base(self):
        """
        Sets up the basic window properties such as title, icon, geometry, and main layout.
        Also initializes the custom title bar behavior (if applicable).
        """
        # Use custom Cyber-Moe title bar with logo on all platforms (Windows & Linux)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        fixed_w, fixed_h = 405, 660
        self.setMinimumSize(380, 520)
        self.resize(fixed_w, fixed_h)
        self.setObjectName("mainWindowRoot")
        self._apply_window_title("")
        try:
            if hasattr(self, "_icon_app") and not self._icon_app.isNull():
                self.setWindowIcon(self._icon_app)
        except Exception:
            pass
        try:
            geom = self.settings.value(KEY_WINDOW_GEOMETRY)
            if geom:
                self.restoreGeometry(geom)
                if self.height() < fixed_h:
                    self.resize(self.width(), fixed_h)
            else:
                self.resize(fixed_w, fixed_h)

            # --- Branding Colors ---
            self.COLOR_ACCENT = PALETTE["accent"]
        except Exception:
            self.resize(fixed_w, fixed_h)

        # Root layout: no margins so title bar and header can be edge-to-edge
        self._root_layout = QVBoxLayout()
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self.setLayout(self._root_layout)

        # Full-bleed dynamic blurred cover canvas (covers the entire window including title bar)
        self._content_widget = FullBleedCanvas()
        self._content_widget.setObjectName("mainWindowRoot")
        self._canvas_outer_layout = QVBoxLayout(self._content_widget)
        self._canvas_outer_layout.setContentsMargins(0, 0, 0, 0)
        self._canvas_outer_layout.setSpacing(0)

        # Custom Cyber-Moe Translucent Title Bar inside the blurred canvas
        self._title_bar = CustomTitleBar(self, icon=getattr(self, "_icon_app", None))
        self._canvas_outer_layout.addWidget(self._title_bar)

        self._body_container = QWidget()
        self._outer_body_layout = QVBoxLayout(self._body_container)
        self._outer_body_layout.setContentsMargins(16, 10, 16, 10)
        self._outer_body_layout.setSpacing(7)

        self._view_stack = SlidingStackedWidget()
        self._player_stage = QWidget()
        self._layout = QVBoxLayout(self._player_stage)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(7)
        self._view_stack.addWidget(self._player_stage)

        self._canvas_outer_layout.addWidget(self._body_container, 1)

        self._root_layout.addWidget(self._content_widget)
        install_size_grip(self)

    def _init_header_section(self):
        """
        Creates and adds the station sub-header, framed artwork showcase, and track stage.
        The J-POP / K-POP switch is only visible when the active station is 'listenmoe'.
        """
        self._current_radio_provider = "listenmoe"

        # 1. Sub-Header HUD Bar: [LIVE Badge] <--> [J-POP | K-POP] <--> [Settings]
        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        top_bar_layout.setSpacing(6)

        left_wing = QWidget()
        left_wing.setFixedWidth(86)
        left_wing_layout = QHBoxLayout(left_wing)
        left_wing_layout.setContentsMargins(0, 0, 0, 0)
        left_wing_layout.setSpacing(0)

        self.live_badge = LiveEqualizerBadge()
        left_wing_layout.addWidget(self.live_badge)
        left_wing_layout.addStretch(1)

        # Keep brand_label attribute for backward compatibility (displayed in CustomTitleBar)
        self.brand_label = QLabel("KIKUMOE")
        self.brand_label.setVisible(False)

        saved_channel = str(self.settings.value(KEY_CHANNEL, "J-POP"))
        self.channel_switch = SegmentedSwitch(
            items=["J-POP", "K-POP"],
            default_index=1 if saved_channel == "K-POP" else 0,
            height=28,
        )
        self.channel_switch.setFixedWidth(134)
        self.channel_switch.selection_changed.connect(self._on_channel_switch_changed)
        self.channel_switch.setVisible(self._current_radio_provider == "listenmoe")

        right_wing = QWidget()
        right_wing.setFixedWidth(86)
        right_wing_layout = QHBoxLayout(right_wing)
        right_wing_layout.setContentsMargins(0, 0, 0, 0)
        right_wing_layout.setSpacing(0)

        self.settings_button = SettingsIconButton()
        self.settings_button.setToolTip(self.i18n.t("settings_button"))
        self.settings_button.clicked.connect(self.open_settings)

        right_wing_layout.addStretch(1)
        right_wing_layout.addWidget(self.settings_button)

        top_bar_layout.addWidget(left_wing)
        top_bar_layout.addStretch(1)
        top_bar_layout.addWidget(self.channel_switch)
        top_bar_layout.addStretch(1)
        top_bar_layout.addWidget(right_wing)
        self._outer_body_layout.addWidget(top_bar)
        self._outer_body_layout.addWidget(self._view_stack, 1)

        # Backward compatibility placeholders
        self.settings_header_bar = top_bar
        self.label = QLabel(self.i18n.t("header").format(channel="J-POP", format="Vorbis"))
        self.label.setVisible(False)
        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        self.sleep_label = QLabel("")
        self.sleep_label.setVisible(False)

        # 2. Central Artwork Hero Showcase
        self._album_cover_size = 196
        self.ambient_cover = AmbientCoverCard(cover_size=self._album_cover_size)
        self._layout.addWidget(self.ambient_cover)

        # Hidden legacy compatibility labels
        self.hero_card = QWidget()
        self.hero_card.setVisible(False)
        self.album_cover_label = QLabel("")
        self.album_cover_label.setVisible(False)
        self.media_ambient_block = QWidget()
        self.media_ambient_block.setVisible(False)
        self.media_ambient_bg = QLabel("")
        self.media_ambient_bg.setVisible(False)

        # 3. Track Info (Title & Artist with fixed vertical policy so no vertical stretch)
        track_box = QVBoxLayout()
        track_box.setContentsMargins(6, 2, 6, 0)
        track_box.setSpacing(2)

        self.now_playing_title = AnimatedTrackLabel(
            "–", font_px=16, font_weight=800, text_color="#ffffff"
        )
        self.now_playing_title.setObjectName("songTitleLabel")
        self.now_playing_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.now_playing_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.now_playing_artist = AnimatedTrackLabel(
            "", font_px=13, font_weight=600, text_color="#c8cee0"
        )
        self.now_playing_artist.setObjectName("songArtistLabel")
        self.now_playing_artist.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.now_playing_artist.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        track_box.addWidget(self.now_playing_title)
        track_box.addWidget(self.now_playing_artist)
        self._layout.addLayout(track_box)

        # Legacy label
        self.now_playing_label = QLabel("–")
        self.now_playing_label.setVisible(False)

        # 4. Scrubber Progress bar & dual-timestamp HUD row
        prog_box = QVBoxLayout()
        prog_box.setContentsMargins(6, 2, 6, 2)
        prog_box.setSpacing(1)

        self.song_progress = SmoothProgressBar()
        self.song_progress.setVisible(True)
        self.song_progress.setObjectName("songProgressBar")
        prog_box.addWidget(self.song_progress)

        time_row = QHBoxLayout()
        time_row.setContentsMargins(4, 0, 4, 0)
        self.song_time_left_spacer = QLabel("")
        self.song_time_left_spacer.setVisible(False)

        self.song_elapsed_label = QLabel("0:00")
        self.song_elapsed_label.setObjectName("timeDisplayLabel")
        self.song_elapsed_label.setStyleSheet("color: #ff4797; font-size: 11px; font-weight: 700;")
        self.song_elapsed_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )

        self.stream_tag_label = QLabel("LISTEN.MOE · STREAM")
        self.stream_tag_label.setObjectName("sectionTitleLabel")
        self.stream_tag_label.setStyleSheet(
            "font-size: 9px; letter-spacing: 1.5px; color: rgba(255, 255, 255, 0.38);"
        )
        self.stream_tag_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stream_tag_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.song_time_label = QLabel("--:--")
        self.song_time_label.setObjectName("timeDisplayLabel")
        self.song_time_label.setStyleSheet("color: #c4c9dc; font-size: 11px; font-weight: 700;")
        self.song_time_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.song_time_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        time_row.addWidget(self.song_elapsed_label)
        time_row.addWidget(self.stream_tag_label, 1)
        time_row.addWidget(self.song_time_label)
        prog_box.addLayout(time_row)

        self._layout.addLayout(prog_box)

        # Connections for signals that update these labels
        try:
            self.now_playing_changed.connect(self._on_now_playing_text_changed)
            self.status_changed.connect(self._set_status_text)
            self.label_refresh.connect(self.update_now_playing_label)
            self.cover_data_ready.connect(self._on_album_cover_data_ready)
            self.now_playing_event.connect(self._on_now_playing)
        except Exception:
            pass
        self._set_album_cover_pixmap(None)

    def _init_meta_section(self):
        """Preserves channel and format attributes for backwards compatibility."""
        self.channel_label = QLabel(self.i18n.t("channel_label"))
        self.channel_label.setVisible(False)
        self.channel_value = QLabel(str(self.settings.value(KEY_CHANNEL, "J-POP")))
        self.channel_value.setVisible(False)
        self.format_label = QLabel(self.i18n.t("format_label"))
        self.format_label.setVisible(False)
        self.format_value = QLabel(str(self.settings.value(KEY_FORMAT, "Vorbis")))
        self.format_value.setVisible(False)

    def _init_controls_section(self):
        """
        Sets up modern Cyber-Moe PlaybackControls with hero circular play button,
        stop, force stop, volume slider, dynamic speaker icon and autoplay.
        """
        self.playback_controls = PlaybackControls()

        # Wire PlaybackControls signals
        self.playback_controls.play_clicked.connect(self.play_stream)
        self.playback_controls.pause_resume_clicked.connect(self.pause_resume)
        self.playback_controls.stop_clicked.connect(self.stop_stream)
        self.playback_controls.force_stop_clicked.connect(self.force_stop_all)
        self.playback_controls.sleep_toggle_clicked.connect(self._on_sleep_toggle_clicked)
        self.playback_controls.volume_changed.connect(self.change_volume)
        self.playback_controls.mute_toggled.connect(self.toggle_mute)
        self.playback_controls.autoplay_toggled.connect(self._on_autoplay_toggled)

        # Backward compatibility references
        self.play_button = self.playback_controls.hero_play
        self.pause_button = self.playback_controls.hero_play
        self.stop_button = self.playback_controls.btn_stop
        self.force_stop_button = self.playback_controls.btn_force_stop
        self.volume_slider = self.playback_controls.volume_slider
        self.mute_button = self.playback_controls.speaker_btn
        self.volume_value_label = self.playback_controls.volume_label
        self.volume_label = QLabel("")
        self.volume_label.setVisible(False)
        self.autoplay_checkbox = self.playback_controls.chk_autoplay

        # Load initial values
        saved_vol = self.settings.value(KEY_VOLUME, 60)
        try:
            self.playback_controls.set_volume(int(saved_vol))
        except Exception:
            self.playback_controls.set_volume(60)

        self.playback_controls.set_autoplay(self._get_bool(KEY_AUTOPLAY, False))
        self.playback_controls.set_autoplay_text(self.i18n.t("settings_autoplay"))

        self._layout.addWidget(self.playback_controls)

    def _init_progress_section(self):
        """
        Routes buffering and opening visual feedback directly to SmoothProgressBar
        (self.song_progress), keeping self.buffer_bar hidden off-layout only for
        backward attribute compatibility.
        """
        self.buffer_bar = QProgressBar()
        self.buffer_bar.setRange(0, 100)
        self.buffer_bar.setVisible(False)

        try:
            self.buffering_progress.connect(self.song_progress.set_buffering_percent)
            self.buffering_visible.connect(self.song_progress.set_buffering_active)
            self.buffering_indeterminate.connect(self.song_progress.set_buffering_indeterminate)
        except Exception:
            pass

    def _init_sleep_timer_section(self):
        """Initializes modern SleepTimerWidget with chip presets and live countdown."""
        self.sleep_timer_widget = SleepTimerWidget()
        self.sleep_timer_widget.start_requested.connect(self._on_sleep_start_requested)
        self.sleep_timer_widget.cancel_requested.connect(self.sleep_cancel_clicked)
        self.sleep_timer_widget.btn_close.clicked.connect(self._sync_window_height_for_sleep_drawer)

        # Backward compatibility attributes
        self.spin_sleep = self.sleep_timer_widget.spin_minutes
        self.btn_sleep_start = self.sleep_timer_widget.btn_start
        self.btn_sleep_cancel = self.sleep_timer_widget.btn_cancel
        self.sleep_title = self.sleep_timer_widget.title_label
        self.sleep_minutes_label = QLabel("")
        self.sleep_minutes_label.setVisible(False)

        try:
            self.sleep_timer_widget.set_minutes(int(self.settings.value(KEY_SLEEP_MINUTES, 30)))
        except Exception:
            self.sleep_timer_widget.set_minutes(30)

        self._layout.addWidget(self.sleep_timer_widget)

    def _init_footer_section(self):
        """Initializes the StatusFooter showing audio backend, codec, and session timer."""
        self.status_footer = StatusFooter()
        self.footer_bar = self.status_footer
        self.session_label = self.status_footer.session_label
        self.session_label.setText(self.i18n.t("session_timer", time="00:00"))

        fmt = str(self.settings.value(KEY_FORMAT, "Vorbis"))
        self.status_footer.set_format(fmt)

        self._layout.addWidget(self.status_footer)

    def _create_player(self, on_event):
        """
        Instantiates the audio backend according to KEY_AUDIO_BACKEND setting.
        'auto'   → tries FFmpeg → MPV → VLC in order.
        'ffmpeg' → only FFmpeg.
        'mpv'    → only MPV.
        'vlc'    → only VLC.
        Returns the created player (may not be ready if the chosen backend is unavailable).
        """
        backend = self.settings.value(KEY_AUDIO_BACKEND, "auto")
        libvlc_path = self.settings.value(KEY_LIBVLC_PATH, "") or None
        try:
            network_caching = int(self.settings.value(KEY_NETWORK_CACHING, 1000))
        except Exception:
            network_caching = 1000

        if backend == "ffmpeg":
            self.log.info("[BACKEND] Using FFmpeg (user setting).")
            player = PlayerFFmpeg(on_event=on_event)
            if not player.is_ready():
                self.log.error(
                    "[BACKEND] FFmpeg selected but unavailable: %s",
                    player.get_init_error() or "pyaudio / ffmpeg not ready",
                )
            return player
        if backend == "mpv":
            self.log.info("[BACKEND] Using MPV (user setting).")
            player = PlayerMPV(on_event=on_event)
            if player.is_ready():
                self.log.info("[BACKEND] MPV backend ready.")
            else:
                self.log.error(
                    "[BACKEND] MPV selected but unavailable: %s",
                    player.get_init_error() or "libmpv did not initialize",
                )
            return player
        if backend == "vlc":
            self.log.info("[BACKEND] Using VLC (user setting).")
            player = PlayerVLC(
                on_event=on_event, libvlc_path=libvlc_path, network_caching_ms=network_caching
            )
            if not player.is_ready():
                self.log.error(
                    "[BACKEND] VLC selected but unavailable: %s",
                    player.get_init_error() or "libvlc not ready",
                )
            return player

        # 'auto': FFmpeg → MPV → VLC
        player = PlayerFFmpeg(on_event=on_event)
        ffmpeg_err = None
        if not player.is_ready():
            ffmpeg_err = getattr(player, "get_init_error", lambda: None)()
            self.log.info(f"[BACKEND] FFmpeg not available ({ffmpeg_err}), trying MPV.")
            player = PlayerMPV(on_event=on_event)
        mpv_err = None
        if not player.is_ready():
            mpv_err = getattr(player, "get_init_error", lambda: None)()
            self.log.info(f"[BACKEND] MPV not available ({mpv_err}), using VLC fallback.")
            player = PlayerVLC(
                on_event=on_event, libvlc_path=libvlc_path, network_caching_ms=network_caching
            )
        if not player.is_ready():
            vlc_err = getattr(player, "get_init_error", lambda: None)()
            self.log.error(
                "[BACKEND] All audio backends failed to initialize! FFmpeg: %s | MPV: %s | VLC: %s",
                ffmpeg_err or "unavailable",
                mpv_err or "unavailable",
                vlc_err or "unavailable",
            )
        return player

    def _init_audio_backend(self):
        """
        Identifies and initializes the available audio backend.
        Respects the KEY_AUDIO_BACKEND setting; defaults to auto (FFmpeg → MPV → VLC).
        Also synchronizes initial volume and mute states.
        """
        self.player = self._create_player(on_event=self._on_player_event)

        if not getattr(self.player, "is_ready", lambda: False)():
            err = getattr(self.player, "get_init_error", lambda: None)()
            self.log.warning("[BACKEND] Audio backend is not ready at startup: %s", err)
            self.status_changed.emit(self.t("status_no_backend"))

        # Set initial audio state
        try:
            self.player.set_volume(self.volume_slider.value())
            is_muted = self._get_bool(KEY_MUTE, False)
            if hasattr(self, "playback_controls"):
                self.playback_controls.set_muted(is_muted)
            else:
                self.mute_button.setChecked(is_muted)
            self.player.set_mute(is_muted)
            self.mute_button.setText(self.i18n.t("unmute") if is_muted else self.i18n.t("mute"))
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
        self.song_tick_timer.setTimerType(Qt.TimerType.PreciseTimer)
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
        init_channel = self.settings.value(KEY_CHANNEL, "J-POP")
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
                self,
                self.i18n,
                on_show_window=self.showNormal,
                on_open_settings=self.open_settings,
                on_change_channel=self._tray_change_channel,
                on_change_format=self._tray_change_format,
                on_toggle_play_pause=self._tray_toggle_play_pause,
                on_stop_stream=self.stop_stream,
                on_force_stop=self.force_stop_all,
                on_toggle_mute=self.toggle_mute_shortcut,
            )
            self.tray_mgr.ensure_tray_enabled(self._tray_enabled, window_icon=self._get_tray_icon())
            self.tray_icon_refresh.connect(self.update_tray_icon)
        except Exception:
            pass

    def _init_extra_logic(self):
        """Final UI polish and logic hooks (Theme, Autoplay, Global Shortcuts)."""
        try:
            self.apply_theme()
            self.apply_translations()
            min_h = max(660, self.minimumSizeHint().height())
            if self.height() < min_h:
                self.resize(max(380, self.width()), min_h)
            self.backend_status_refresh.connect(self.update_vlc_status_label)

            # Autoplay
            if self._get_bool(KEY_AUTOPLAY, False):
                QTimer.singleShot(1000, self.play_stream)

            # Global Keyboard Shortcuts (Class scope)
            QShortcut(QKeySequence(Qt.Key.Key_Up), self).activated.connect(self._vol_up)
            QShortcut(QKeySequence(Qt.Key.Key_Down), self).activated.connect(self._vol_down)
            QShortcut(QKeySequence(Qt.Key.Key_Plus), self).activated.connect(self._vol_up)
            QShortcut(QKeySequence(Qt.Key.Key_Minus), self).activated.connect(self._vol_down)
            QShortcut(QKeySequence("="), self).activated.connect(self._vol_up)

            # Legacy/Specific Shortcuts
            QShortcut(QKeySequence("Space"), self).activated.connect(self.pause_resume)
            QShortcut(QKeySequence("S"), self).activated.connect(self.stop_stream)
            QShortcut(QKeySequence("M"), self).activated.connect(self.toggle_mute_shortcut)
        except Exception:
            pass

    # ------------------- Volume Helpers -------------------

    def _build_window_title(self, song_title: Optional[str] = None) -> str:
        """Compose the window title."""
        base = APP_TITLE
        song = (song_title or "").strip()
        return f"{base} — {song}" if song else base

    def _apply_window_title(self, song_title: Optional[str] = None) -> None:
        try:
            title = self._build_window_title(song_title)
            self.setWindowTitle(title)
            title_bar = getattr(self, "_title_bar", None)
            if title_bar is not None:
                title_bar.set_title(title)
        except Exception:
            pass

    def _vol_up(self) -> None:
        """Aumenta il volume di 5%."""
        try:
            if hasattr(self, "volume_slider"):
                val = self.volume_slider.value()
                self.volume_slider.setValue(min(100, val + 5))
        except Exception:
            pass

    def _vol_down(self) -> None:
        """Diminuisce il volume di 5%."""
        try:
            if hasattr(self, "volume_slider"):
                val = self.volume_slider.value()
                self.volume_slider.setValue(max(0, val - 5))
        except Exception:
            pass

    # ------------------- Event & Signal Handlers -------------------

    # 1. Qt Window & Lifecycle Events
    def closeEvent(self, a0) -> None:
        event = a0
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
            msg.setWindowTitle(self.i18n.t("close_dialog_title"))
            msg.setText(self.i18n.t("close_dialog_text"))
            msg.setIcon(QMessageBox.Icon.Question)

            tray_btn = msg.addButton(
                self.i18n.t("close_option_tray"), QMessageBox.ButtonRole.AcceptRole
            )
            msg.addButton(self.i18n.t("close_option_quit"), QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = msg.addButton(
                self.i18n.t("settings_cancel"), QMessageBox.ButtonRole.RejectRole
            )
            msg.setEscapeButton(cancel_btn)

            cb = QCheckBox(self.i18n.t("close_remember"))
            msg.setCheckBox(cb)

            self._make_frameless_msg(msg)
            try:
                apply_windows_titlebar_dark_mode(msg, True)
            except Exception:
                pass

            msg.exec()
            clicked = msg.clickedButton()
            if clicked is None or clicked == cancel_btn:
                # User cancelled close action (Cancel button, Esc, or window X on the dialog)
                event.ignore()
                return

            remember = cb.isChecked()
            choice_tray = clicked == tray_btn

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
            if hasattr(self, "dev_console") and self.dev_console:
                self.dev_console.deactivate_logging()
                self.dev_console.close()
            if hasattr(self, "_session_timer") and self._session_timer:
                self._session_timer.stop()
            if hasattr(self, "player") and self.player:
                self.player.stop()
            if hasattr(self, "ws") and self.ws:
                ws_stop = getattr(self.ws, "stop", None) or getattr(self.ws, "shutdown", None)
                if callable(ws_stop):
                    ws_stop()
        except Exception:
            pass

    def showEvent(self, a0) -> None:
        event = a0
        try:
            super().showEvent(event)
            self._apply_windows_titlebar_dark_mode(True)
            self._apply_window_title(getattr(self, "_current_title", "") or "")
            try:
                current_pm = (
                    self.album_cover_label.pixmap() if hasattr(self, "album_cover_label") else None
                )
                self._update_media_ambient_background(
                    current_pm if isinstance(current_pm, QPixmap) else None
                )
            except Exception:
                pass
        except Exception:
            pass

    def changeEvent(self, a0) -> None:
        event = a0
        try:
            if event.type() == QEvent.Type.WindowStateChange:
                title_bar = getattr(self, "_title_bar", None)
                if title_bar is not None:
                    title_bar.sync_maximize_button()
                if (
                    self.isMinimized()
                    and self._get_bool(KEY_TRAY_ENABLED, True)
                    and self._get_bool(KEY_TRAY_HIDE_ON_MINIMIZE, True)
                ):
                    self.hide()
                    event.accept()
                    return
            super().changeEvent(event)
        except Exception:
            pass

    # 2. Player Backend & Audio Events
    def _on_player_event(self, code: str, value: Optional[int] = None) -> None:
        """Gestisce gli eventi del backend (FFmpeg/VLC) aggiornando lo stato UI."""
        try:
            c = str(code).lower() if code is not None else ""
            if c == "opening":
                self.status_changed.emit(self.t("status_opening"))
                self.buffering_visible.emit(True)
                self.buffering_indeterminate.emit(True)
                self.backend_status_refresh.emit()
            elif c == "buffering":
                if isinstance(value, int) and value >= 100:
                    self.buffering_visible.emit(False)
                    self.buffering_indeterminate.emit(False)
                    self.status_changed.emit(self.t("status_playing"))
                else:
                    self.status_changed.emit(self.t("status_buffering"))
                    self.buffering_visible.emit(True)
                    if isinstance(value, int) and 0 <= value < 100:
                        self.buffering_indeterminate.emit(False)
                        self.buffering_progress.emit(int(value))
                    else:
                        self.buffering_indeterminate.emit(True)
            elif c == "playing":
                self._retry_count = 0
                self.status_changed.emit(self.t("status_playing"))
                self.buffering_visible.emit(False)
                self.buffering_indeterminate.emit(False)
                self._ui_paused = False
                if self._get_bool(KEY_SESSION_TIMER_ENABLED, True):
                    if self._session_timer and not self._session_timer.isActive():
                        self._session_timer.start()
                self.tray_icon_refresh.emit()
                self._update_tray_controls()
            elif c == "paused":
                self.status_changed.emit(self.t("status_paused"))
                if self._session_timer and self._session_timer.isActive():
                    self._session_timer.stop()
                self._ui_paused = True
                self._update_tray_controls()
            elif c in ("stopped", "ended"):
                self.status_changed.emit(self.t("status_stopped"))
                self.buffering_visible.emit(False)
                if c == "ended":
                    self._skip_session_reset_once = True
                    if getattr(self, "_ui_paused", False):
                        try:
                            self.log.info(
                                "[UI] Ignored 'ended' event because player is intentionally paused."
                            )
                        except Exception:
                            pass
                    elif not getattr(self, "_retry_pending", False):
                        self._retry_pending = True
                        self.schedule_play.emit(1000)
                        # Optionally only notify on unexpected end if not already retrying
                        if getattr(self, "_retry_count", 0) == 0:
                            self.notify_tray.emit(
                                "Listen.moe", "Audio riavviato: il timer di sessione continua"
                            )
                else:
                    # Reset on explicit stop (unless skip flag is set)
                    if not getattr(self, "_skip_session_reset_once", False):
                        if self._session_timer:
                            self._session_timer.stop()
                        self._session_seconds = 0
                        self.log.info("[UI] session_timer reset due to explicit stop")
                    # Clear the skip flag after use (regardless of whether it was used)
                    self._skip_session_reset_once = False
                self._update_session_label()
                self._ui_paused = False
                self._update_tray_controls()
            elif c in ("error", "libvlc_init_failed"):
                # Se il backend audio non e' pronto, non e' un errore di rete transitorio:
                # non ritentare.
                if (
                    hasattr(self, "player")
                    and self.player is not None
                    and not getattr(self.player, "is_ready", lambda: True)()
                ):
                    self.status_changed.emit(self.t("status_no_backend"))
                    self.buffering_visible.emit(False)
                    self._retry_pending = False
                    self._refresh_play_button_text(False)
                    return

                self.status_changed.emit(self.t("status_error"))
                self.buffering_visible.emit(False)
                self._skip_session_reset_once = True

                if not getattr(self, "_retry_pending", False):
                    self._retry_count += 1
                    if self._retry_count <= self._max_retries:
                        self._retry_pending = True
                        # Exponential backoff: 1.2s * 1.5 ^ retry_count (cap at 30s)
                        delay = int(min(30000, 1200 * (1.5**self._retry_count)))
                        self.schedule_play.emit(delay)
                        self.log.info(
                            f"[UI] Playback restart scheduled in {delay}ms"
                            f" (retry {self._retry_count})"
                        )
                        # Only notify on the first failure to avoid toast spam
                        if self._retry_count == 1:
                            self.notify_tray.emit("Listen.moe", self.t("status_restarting"))
                    else:
                        self.log.error(
                            f"[UI] Maximum retries ({self._retry_count}) reached. Giving up."
                        )
                        # Always notify when we stop permanently
                        self.notify_tray.emit(
                            "Listen.moe", "Errore persistente: ricarica interrotta."
                        )
            self._refresh_play_button_text()
        except Exception:
            pass

    def _schedule_play_stream(self, delay_ms: int) -> None:
        """Slot per avviare lo stream dopo un delay (thread-safe UI call)."""
        try:
            QTimer.singleShot(int(delay_ms), lambda: self.play_stream(is_retry=True))
        except Exception:
            self.play_stream(is_retry=True)

    # 3. WebSocket & Metadata Events
    def _on_now_playing(
        self,
        title: str,
        artist: str,
        duration: Optional[int] = None,
        start_ts: Optional[float] = None,
        album_cover: Optional[str] = None,
    ):
        # WebSocket callback arrives from a worker thread: marshal to UI thread first.
        try:
            if QThread.currentThread() != self.thread():
                self.now_playing_event.emit(title, artist, duration, start_ts, album_cover)
                return
        except Exception:
            pass
        try:
            try:
                self.log.debug(
                    f"[DEV] Metadata received: title={title}, dur={duration}, "
                    f"start_ts={start_ts}, cover={album_cover}"
                )
            except Exception:
                pass

            self._current_title = title or self.i18n.t("unknown")
            self._current_artist = artist or ""
            # Support dur=0 as a valid state (Live/Unknown) instead of resetting to None
            self._current_duration_seconds = (
                int(duration) if duration is not None and int(duration) >= 0 else None
            )
            self._current_start_epoch = float(start_ts) if start_ts is not None else None
            self._current_cover_ref = (
                album_cover if isinstance(album_cover, str) and album_cover.strip() else None
            )

            # --- Song Progress Bar Sync ---
            if hasattr(self, "song_progress"):
                # Only show and set progress bar if we have a valid, positive duration
                if (
                    self._current_duration_seconds is not None
                    and self._current_duration_seconds > 0
                ):
                    # Multiplier (1000) for sub-second smoothness
                    self.song_progress.setMaximum(int(self._current_duration_seconds * 1000))

                    # Calculate initial progress instead of resetting to 0
                    if self._current_start_epoch is not None:
                        import time

                        now = time.time() + self._clock_sync_offset
                        # LISTEN.moe 'startTime' is actually the expected END time of the track
                        remaining = self._current_start_epoch - now
                        elapsed = max(0, self._current_duration_seconds - remaining)
                        self.song_progress.setValue(
                            int(min(elapsed, self._current_duration_seconds) * 1000)
                        )
                    else:
                        self.song_progress.setValue(0)

                    self.song_progress.show()
                else:
                    self.song_progress.setValue(0)
                    self.song_progress.show()

            self.label_refresh.emit()
            if self._get_bool(KEY_TRAY_NOTIFICATIONS, True) and self._get_bool(
                KEY_TRAY_ENABLED, True
            ):
                msg_title = self.i18n.t("now_playing_prefix")
                body = f"{self._current_title}" + (
                    f" — {self._current_artist}" if self._current_artist else ""
                )
                self.notify_tray.emit(msg_title, body)
            self.backend_status_refresh.emit()
        except Exception:
            pass

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

    def set_radio_provider(self, provider: str) -> None:
        """Show the J-POP / K-POP switch only when the 'listenmoe' radio is selected."""
        self._current_radio_provider = (provider or "").strip().lower()
        if hasattr(self, "channel_switch"):
            self.channel_switch.setVisible(self._current_radio_provider == "listenmoe")

    def _on_channel_switch_changed(self, new_channel: str) -> None:
        try:
            self._apply_tray_stream_setting_change(KEY_CHANNEL, new_channel, ws_channel=new_channel)
            if hasattr(self, "channel_value"):
                self.channel_value.setText(new_channel)
        except Exception:
            pass

    def _on_sleep_start_requested(self, minutes: int) -> None:
        try:
            if hasattr(self, "spin_sleep"):
                self.spin_sleep.setValue(minutes)
            self.sleep_start_clicked()
            if hasattr(self, "sleep_timer_widget"):
                self.sleep_timer_widget.set_active_countdown(self._sleep_remaining_sec)
        except Exception:
            pass

    def _sync_window_height_for_sleep_drawer(self) -> None:
        try:
            if hasattr(self, "sleep_timer_widget"):
                is_open = self.sleep_timer_widget.isVisible()
                if hasattr(self, "playback_controls"):
                    self.playback_controls.set_sleep_drawer_open(is_open)
                extra = 95 if is_open else 0
                base_h = 530 + CustomTitleBar.HEIGHT
                target_h = max(base_h + extra, self.minimumSizeHint().height())
                self.resize(self.width(), target_h)
        except Exception:
            pass

    def _on_sleep_toggle_clicked(self) -> None:
        try:
            if hasattr(self, "sleep_timer_widget"):
                self.sleep_timer_widget.toggle_visible()
                self._sync_window_height_for_sleep_drawer()
        except Exception:
            pass

    def _on_now_playing_text_changed(self, text: str) -> None:
        if hasattr(self, "now_playing_label"):
            self.now_playing_label.setText(text)
        title = self._current_title or self.t("unknown")
        artist = self._current_artist or ""
        if hasattr(self, "now_playing_title"):
            self.now_playing_title.setText(title)
        if hasattr(self, "now_playing_artist"):
            self.now_playing_artist.setText(artist)

    # 4. Timer & Tray Action Events
    def _on_session_tick(self) -> None:
        try:
            self._session_seconds += 1
            self._update_session_label()
            self.update_tray_texts()
        except Exception:
            pass

    def _update_session_label(self) -> None:
        try:
            if hasattr(self, "session_label"):
                enabled = self._get_bool(KEY_SESSION_TIMER_ENABLED, True)
                display_seconds = self._session_seconds if enabled else 0
                t = "00:00" if int(display_seconds) <= 0 else self._format_hhmmss(display_seconds)
                self.session_label.setText(self.i18n.t("session_timer", time=t))
                self.session_label.setVisible(True)
        except Exception:
            pass

    def _apply_session_timer_running_state(self, running: bool) -> None:
        """Apply session timer state and refresh session/tray labels."""
        try:
            if self._get_bool(KEY_SESSION_TIMER_ENABLED, True):
                if running:
                    if self._session_timer and not self._session_timer.isActive():
                        self._session_timer.start()
                else:
                    if self._session_timer and self._session_timer.isActive():
                        self._session_timer.stop()
            else:
                if self._session_timer and self._session_timer.isActive():
                    self._session_timer.stop()
            if hasattr(self, "session_label"):
                self.session_label.show()
            self._update_session_label()
            self.update_tray_texts()
        except Exception:
            pass

    def _on_song_tick(self) -> None:
        """Updates the song progress bar every second based on start timestamp."""
        try:
            import time

            now = time.time()
            epoch = getattr(self, "_current_start_epoch", None)
            dur = getattr(self, "_current_duration_seconds", None)

            if epoch is None or dur is None:
                return

            if dur <= 0:
                # Live stream or unknown duration: ticker is alive but doesn't update bar
                now_int = int(now)
                if now_int != getattr(self, "_last_live_log", 0) and now_int % 30 == 0:
                    self._last_live_log = now_int
                    self.log.debug(f"[DEV] Song ticker: LIVE MODE (title={self._current_title})")
                return

            # Use synced clock: now + clock_sync_offset
            now_synced = now + getattr(self, "_clock_sync_offset", 0)

            # epoch is actually the END time of the track
            remaining_raw = epoch - now_synced
            elapsed_raw = dur - remaining_raw

            # --- Progress Bar (Fluid 50ms update) ---
            # Use milliseconds for the internal bar value
            effective_ms = int(max(0, min(elapsed_raw, dur)) * 1000)
            self.song_progress.setValue(effective_ms)

            # --- Label Update (Optimized 1s update) ---
            current_int_sec = int(elapsed_raw)
            if current_int_sec != getattr(self, "_last_integer_second", -1):
                self._last_integer_second = current_int_sec

                # Diagnostic log for [DEV] filters (every 5s)
                if current_int_sec % 5 == 0:
                    self.log.debug(
                        f"[DEV] Song ticker: elapsed={current_int_sec}s "
                        f"(skewed), dur={dur}s, offset={getattr(self, '_clock_sync_offset', 0):.1f}"
                    )

                # Update the [M:SS] text in the metadata label every second
                self.update_now_playing_label()
        except Exception:
            pass

    def _sleep_tick(self) -> None:
        try:
            if self._sleep_remaining_sec <= 0:
                if self._sleep_timer:
                    self._sleep_timer.stop()
                if hasattr(self, "sleep_label"):
                    self.sleep_label.setText("")
                    self.sleep_label.setVisible(False)
                if hasattr(self, "sleep_timer_widget"):
                    self.sleep_timer_widget.set_inactive()
                if hasattr(self, "playback_controls"):
                    self.playback_controls.set_sleep_active(False)
                if self._get_bool(KEY_SLEEP_STOP_ON_END, True):
                    self.stop_stream()
                return
            self._sleep_remaining_sec -= 1
            if hasattr(self, "sleep_timer_widget"):
                self.sleep_timer_widget.set_active_countdown(self._sleep_remaining_sec)
            if hasattr(self, "playback_controls"):
                m, s = divmod(max(0, self._sleep_remaining_sec), 60)
                self.playback_controls.set_sleep_active(True, f"{m:02d}:{s:02d}")
            if (
                self._sleep_saved_volume is not None
                and self._sleep_remaining_sec <= self._sleep_fadeout_sec
            ):
                new_vol = max(
                    0,
                    int(
                        self._sleep_saved_volume
                        * self._sleep_remaining_sec
                        / max(1, self._sleep_fadeout_sec)
                    ),
                )
                if hasattr(self, "volume_slider"):
                    self.volume_slider.setValue(new_vol)
            if hasattr(self, "sleep_label"):
                self.sleep_label.setText(
                    self.t("sleep_remaining", time=self._format_mmss(self._sleep_remaining_sec))
                )
                self.sleep_label.setVisible(True)
        except Exception:
            pass

    def _tray_toggle_play_pause(self) -> None:
        """Handler for tray icon play/pause command."""
        try:
            has_player = hasattr(self, "player") and self.player is not None
            is_playing = bool(self.player.is_playing()) if has_player else False
            is_paused = (
                bool(getattr(self.player, "is_paused", lambda: False)()) if has_player else False
            )

            if has_player and (is_playing or is_paused):
                self.pause_resume()
            else:
                self.play_stream()
        except Exception:
            pass

    def _update_tray_controls(self) -> None:
        """Utility per aggiornare i controlli della tray in base allo stato del player."""
        try:
            if hasattr(self, "tray_mgr") and self.tray_mgr:
                is_playing = bool(self.player.is_playing())
                is_paused = (
                    bool(getattr(self.player, "is_paused", lambda: False)()) or self._ui_paused
                )
                is_muted = (
                    bool(self.player.get_mute()) if hasattr(self.player, "get_mute") else False
                )
                self.tray_mgr.update_controls_state(
                    is_playing and not is_paused, is_paused, is_muted
                )
        except Exception:
            pass

    def _refresh_play_button_text(self, force_playing: Optional[bool] = None) -> None:
        """Set the Play button text from playback state or an explicit override."""
        try:
            if not hasattr(self, "play_button"):
                return
            if force_playing is None:
                is_playing = False
                is_paused = bool(getattr(self, "_ui_paused", False))
                try:
                    if hasattr(self, "player") and self.player is not None:
                        is_playing = bool(self.player.is_playing())
                        is_paused = is_paused or bool(
                            getattr(self.player, "is_paused", lambda: False)()
                        )
                except Exception:
                    pass
                force_playing = is_playing and not is_paused
            self.play_button.setText(
                self.i18n.t("play_active") if force_playing else self.i18n.t("play")
            )
            if hasattr(self, "playback_controls"):
                self.playback_controls.set_playing_state(
                    is_playing=force_playing,
                    is_paused=bool(getattr(self, "_ui_paused", False)),
                )
            if hasattr(self, "live_badge"):
                self.live_badge.set_playing(bool(force_playing))
        except Exception:
            pass

    def apply_translations(self):
        # Mantieni o aggiorna titolo finestra in base al Now Playing
        try:
            title = getattr(self, "_current_title", "") or ""
            self._apply_window_title(title)
        except Exception:
            pass
        self.channel_label.setText(self.i18n.t("channel_label"))
        self.format_label.setText(self.i18n.t("format_label"))
        self._refresh_play_button_text()
        self.pause_button.setText(self.i18n.t("pause"))
        self.stop_button.setText(self.i18n.t("stop"))
        self.volume_label.setText(self.i18n.t("volume"))
        self.mute_button.setText(
            self.i18n.t("unmute") if self.mute_button.isChecked() else self.i18n.t("mute")
        )
        # Aggiorna tooltip dei controlli
        try:
            self.play_button.setToolTip(self.i18n.t("tt_play"))
            self.pause_button.setToolTip(self.i18n.t("tt_pause"))
            self.stop_button.setToolTip(self.i18n.t("tt_stop"))
            self.mute_button.setToolTip(
                self.i18n.t("tt_unmute") if self.mute_button.isChecked() else self.i18n.t("tt_mute")
            )
        except Exception:
            pass
        if hasattr(self, "settings_button"):
            self.settings_button.setToolTip(self.i18n.t("settings_button"))
        # Sleep UI texts
        if hasattr(self, "sleep_timer_widget"):
            self.sleep_timer_widget.apply_translations(
                title=self.i18n.t("sleep_timer"),
                start_btn=self.i18n.t("sleep_start"),
                cancel_btn=self.i18n.t("sleep_cancel"),
            )
        if hasattr(self, "sleep_title"):
            self.sleep_title.setText(self.i18n.t("sleep_timer"))
        if hasattr(self, "sleep_minutes_label"):
            self.sleep_minutes_label.setText(self.i18n.t("sleep_minutes"))
        if hasattr(self, "btn_sleep_start"):
            self.btn_sleep_start.setText(self.i18n.t("sleep_start"))
        if hasattr(self, "btn_sleep_cancel"):
            self.btn_sleep_cancel.setText(self.i18n.t("sleep_cancel"))
        self.update_header_label()
        self.update_now_playing_label()
        self.update_vlc_status_label()
        self._update_session_label()
        self.update_tray_texts()
        if hasattr(self, "autoplay_checkbox"):
            self.autoplay_checkbox.setText(self.i18n.t("settings_autoplay"))
        if hasattr(self, "playback_controls"):
            self.playback_controls.set_autoplay_text(self.i18n.t("settings_autoplay"))
        # Update dev console dialog texts if open
        try:
            if hasattr(self, "dev_console") and self.dev_console and self.dev_console.is_open():
                try:
                    self.dev_console.set_translator(self.i18n)
                    self.dev_console.refresh_texts()
                except Exception:
                    pass
        except Exception:
            pass

    def apply_theme(self) -> None:
        try:
            dark = True
            accent = getattr(self, "COLOR_ACCENT", PALETTE["accent"])
            app = QApplication.instance()
            if not isinstance(app, QApplication):
                return
            app.setStyleSheet(get_cyber_moe_stylesheet(accent))

            if hasattr(self, "playback_controls"):
                self.playback_controls.hero_play.set_accent_color(accent)
            if hasattr(self, "channel_switch"):
                self.channel_switch.set_accent_color(accent)

            # --- Icon Dynamic Tinting ---
            # All icons now use the accent color (Magenta) for consistent branding
            icon_color = QColor(accent)

            # Use smaller icons for the top menu to facilitate edge alignment
            sz_small = QSize(18, 18)
            sz_std = QSize(24, 24)

            self._icon_play = self._tint_icon(self._icon_play_raw, icon_color, sz_std)
            self._icon_pause = self._tint_icon(self._icon_pause_raw, icon_color, sz_std)
            self._icon_stop = self._tint_icon(self._icon_stop_raw, icon_color, sz_std)
            self._icon_mute = self._tint_icon(self._icon_mute_raw, icon_color, sz_std)
            self._icon_unmute = self._tint_icon(self._icon_unmute_raw, icon_color, sz_std)
            self._icon_force_stop = self._tint_icon(self._icon_force_stop_raw, icon_color, sz_std)
            self._icon_channel = self._tint_icon(self._icon_channel_raw, icon_color, sz_small)
            self._icon_codec = self._tint_icon(self._icon_codec_raw, icon_color, sz_small)
            self._icon_quit = self._tint_icon(self._icon_quit_raw, icon_color, sz_std)
            # Branding: Use original colors for the logo, ensured square to prevent stretching
            self._icon_app = self._make_icon_square(self._icon_app_raw)
            # Tray-specific icon: fit the full logo in a square while maximizing visible area
            self._icon_app_tray = self._make_tray_icon(self._icon_app_raw)
            # Skip settings icon as requested (text-only for cleaner alignment)
            # self._icon_settings = self._tint_icon(self._icon_settings_raw, icon_color, sz_small)

            # Update metadata icon labels with the new tinted icons
            if hasattr(self, "channel_icon_label"):
                self.channel_icon_label.setPixmap(self._icon_channel.pixmap(16, 16))
            if hasattr(self, "format_icon_label"):
                self.format_icon_label.setPixmap(self._icon_codec.pixmap(16, 16))

            try:
                self.setWindowIcon(self._icon_app)
                if getattr(self, "_title_bar", None) is not None:
                    self._title_bar.set_icon(self._icon_app)
            except Exception:
                pass

            # Synchronize icons with TrayManager
            if hasattr(self, "tray_mgr") and self.tray_mgr:
                self.tray_mgr.update_icon(self._get_tray_icon())
                self.tray_mgr.update_controls_icons(
                    {
                        "play": self._icon_play,
                        "pause": self._icon_pause,
                        "stop": self._icon_stop,
                        "mute": self._icon_mute,
                        "unmute": self._icon_unmute,
                        "force_stop": self._icon_force_stop,
                        "channel": self._icon_channel,
                        "codec": self._icon_codec,
                        "quit": self._icon_quit,
                    }
                )
                # Refresh tray menu state to apply icons immediately
                try:
                    self._update_tray_controls()
                except Exception:
                    pass

            # Synchronize custom progress bar color
            if hasattr(self, "song_progress"):
                self.song_progress.setAccentColor(accent)

            try:
                self._set_album_cover_pixmap(self._cover_cache.get(self._current_cover_url or ""))
            except Exception:
                self._set_album_cover_pixmap(None)

            # Apply dark titlebar on Windows
            try:
                self._apply_windows_titlebar_dark_mode(dark)
            except Exception:
                pass
            try:
                if hasattr(self, "dev_console") and self.dev_console and self.dev_console.is_open():
                    self.dev_console.apply_theme(dark)
            except Exception:
                pass
        except Exception:
            pass

    def _apply_windows_titlebar_dark_mode(self, enable: bool) -> None:
        try:
            apply_windows_titlebar_dark_mode(self, enable)
        except Exception:
            pass

    @staticmethod
    def _make_frameless_msg(msg: QMessageBox) -> None:
        """Remove compositor decorations from a QMessageBox and add a visible border."""
        if not _IS_WIN32:
            msg.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
            msg.setStyleSheet("QDialog { background-color: #121212; border: 1px solid #3a3a3a; }")

    def _tint_icon(self, icon: QIcon, color: QColor, size: QSize) -> QIcon:
        try:
            if icon is None or icon.isNull():
                return icon
            if size is None or size.isEmpty():
                size = QSize(16, 16)
            src = icon.pixmap(size)
            if src.isNull():
                return icon
            dst = QPixmap(src.size())
            dst.fill(Qt.GlobalColor.transparent)
            painter = QPainter()
            if painter.begin(dst):
                try:
                    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                    painter.drawPixmap(0, 0, src)
                    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                    painter.fillRect(dst.rect(), color)
                finally:
                    painter.end()
            return QIcon(dst)
        except Exception:
            return icon

    _ALLOWED_COVER_HOSTS = frozenset({"cdn.listen.moe", "listen.moe"})

    def _normalize_album_cover_url(self, cover_ref: Optional[str]) -> Optional[str]:
        try:
            if not isinstance(cover_ref, str):
                return None
            value = cover_ref.strip()
            if not value:
                return None

            low = value.lower()
            if low.startswith("http://"):
                # Rifiuta esplicitamente endpoint HTTP in chiaro
                return None

            if low.startswith("https://"):
                raw_url = value
            else:
                clean_val = value.lstrip("/")
                if clean_val.lower().startswith("covers/"):
                    clean_val = clean_val[7:]
                raw_url = f"https://cdn.listen.moe/covers/{clean_val}"

            parts = urllib.parse.urlsplit(raw_url)
            if parts.scheme.lower() != "https" or not parts.netloc:
                return None

            host = (parts.hostname or "").lower()
            if not host or host not in ListenMoePlayer._ALLOWED_COVER_HOSTS:
                return None

            if parts.port not in (None, 443):
                return None

            # Encode non-ASCII and unsafe chars in path (preserve '/' and already-encoded '%xx')
            safe_path = urllib.parse.quote(parts.path, safe="/%")
            return urllib.parse.urlunsplit(
                ("https", parts.netloc, safe_path, parts.query, parts.fragment)
            )
        except Exception:
            return None

    def _request_album_cover(self, cover_ref: Optional[str]) -> None:
        try:
            cover_url = self._normalize_album_cover_url(cover_ref)
            if cover_url == self._current_cover_url:
                return
            self._current_cover_url = cover_url

            if not cover_url:
                self._set_album_cover_pixmap(None)
                return

            cached = self._cover_cache.get(cover_url)
            if cached is not None and not cached.isNull():
                self._set_album_cover_pixmap(cached)
                return

            with self._cover_download_lock:
                if cover_url in self._cover_download_inflight:
                    return
                self._cover_download_inflight.add(cover_url)

            worker = threading.Thread(
                target=self._download_album_cover_worker, args=(cover_url,), daemon=True
            )
            worker.start()
        except Exception:
            pass

    def _download_album_cover_worker(self, cover_url: str) -> None:
        raw = b""
        try:
            parts = urllib.parse.urlsplit(cover_url)
            host = (parts.hostname or "").lower()
            if parts.scheme.lower() != "https" or host not in self._ALLOWED_COVER_HOSTS:
                return
            if parts.port not in (None, 443):
                return
            req = urllib.request.Request(cover_url, headers={"User-Agent": "KikuMoe/2.0.0-beta1"})
            with urllib.request.urlopen(req, timeout=8) as res:
                chunk = res.read((4 * 1024 * 1024) + 1)
                if isinstance(chunk, (bytes, bytearray)) and 0 < len(chunk) <= (4 * 1024 * 1024):
                    raw = bytes(chunk)
        except Exception:
            pass
        finally:
            try:
                with self._cover_download_lock:
                    self._cover_download_inflight.discard(cover_url)
            except Exception:
                pass
        try:
            self.cover_data_ready.emit(cover_url, raw)
        except Exception:
            pass

    def _on_album_cover_data_ready(self, cover_url: str, raw: bytes) -> None:
        try:
            if not raw:
                if cover_url and cover_url == self._current_cover_url:
                    self._set_album_cover_pixmap(None)
                return

            pixmap = QPixmap()
            if not pixmap.loadFromData(raw):
                if cover_url and cover_url == self._current_cover_url:
                    self._set_album_cover_pixmap(None)
                return

            self._cover_cache[cover_url] = pixmap
            if len(self._cover_cache) > 64:
                oldest_key = next(iter(self._cover_cache))
                if oldest_key != cover_url:
                    self._cover_cache.pop(oldest_key, None)

            if cover_url and cover_url == self._current_cover_url:
                self._set_album_cover_pixmap(pixmap)
        except Exception:
            pass

    def _update_media_ambient_background(self, pixmap: Optional[QPixmap]) -> None:
        """Build a subtle blurred background behind cover/title based on current album art."""
        try:
            if not hasattr(self, "media_ambient_bg"):
                return

            block = getattr(self, "media_ambient_block", None)
            target_w = int(block.width()) if block is not None else 0
            target_h = int(block.height()) if block is not None else 0
            if target_w <= 0:
                target_w = max(320, int(self.width()) - 16)
            if target_h <= 0:
                target_h = max(220, int(getattr(self, "_album_cover_size", 190)) + 56)

            if pixmap is None or pixmap.isNull():
                fallback = QPixmap(target_w, target_h)
                fallback.fill(QColor("#151515"))
                self.media_ambient_bg.setPixmap(fallback)
                return

            # Fast soft blur: shrink aggressively then upscale back.
            source = pixmap.scaled(
                max(96, target_w // 2),
                max(96, target_h // 2),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            tiny = source.scaled(
                max(24, target_w // 20),
                max(24, target_h // 20),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            blurred = tiny.scaled(
                target_w,
                target_h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            canvas = QPixmap(target_w, target_h)
            canvas.fill(Qt.GlobalColor.transparent)
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(0, 0, blurred)
            # Dark overlay keeps controls/text readable.
            painter.fillRect(canvas.rect(), QColor(12, 12, 12, 190))
            painter.end()

            self.media_ambient_bg.setPixmap(canvas)
        except Exception:
            pass

    def _set_album_cover_pixmap(self, pixmap: Optional[QPixmap]) -> None:
        try:
            if hasattr(self, "ambient_cover"):
                self.ambient_cover.set_cover(pixmap)
            if hasattr(self, "_content_widget") and isinstance(
                self._content_widget, FullBleedCanvas
            ):
                amb_col = (
                    self.ambient_cover.ambient_color if hasattr(self, "ambient_cover") else None
                )
                self._content_widget.set_backdrop(pixmap, amb_col)
            if hasattr(self, "_settings_dlg") and self._settings_dlg is not None:
                try:
                    self._settings_dlg._sync_backdrop_from_parent()
                except Exception:
                    pass

            if not hasattr(self, "album_cover_label"):
                return

            side = max(96, int(getattr(self, "_album_cover_size", 190)))
            target_size = QSize(side, side)

            if pixmap is None or pixmap.isNull():
                canvas = QPixmap(target_size)
                canvas.fill(QColor("#101010"))

                fallback_pm = None
                try:
                    if (
                        hasattr(self, "_icon_app")
                        and self._icon_app is not None
                        and not self._icon_app.isNull()
                    ):
                        fallback_pm = self._icon_app.pixmap(int(side * 0.68), int(side * 0.68))
                except Exception:
                    fallback_pm = None

                if fallback_pm is not None and not fallback_pm.isNull():
                    painter = QPainter(canvas)
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    x = (side - fallback_pm.width()) // 2
                    y = (side - fallback_pm.height()) // 2
                    painter.drawPixmap(x, y, fallback_pm)
                    painter.end()
                self.album_cover_label.setPixmap(canvas)
                self._update_media_ambient_background(None)
                return

            fitted = pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            if fitted.isNull():
                return

            if fitted.width() != side or fitted.height() != side:
                x = max(0, (fitted.width() - side) // 2)
                y = max(0, (fitted.height() - side) // 2)
                fitted = fitted.copy(x, y, side, side)

            self.album_cover_label.setPixmap(fitted)
            self._update_media_ambient_background(fitted)
        except Exception:
            pass

    def _make_tray_icon(self, icon: QIcon) -> QIcon:
        """Build a tray-friendly square icon that stays large without cropping."""
        try:
            if icon is None or icon.isNull():
                return icon

            source_pm = None
            try:
                sizes = icon.availableSizes()
                if sizes:
                    best = max(sizes, key=lambda s: int(s.width()) * int(s.height()))
                    source_pm = icon.pixmap(best)
            except Exception:
                source_pm = None

            if source_pm is None or source_pm.isNull():
                source_pm = icon.pixmap(512, 512)
            if source_pm.isNull():
                return icon
            source_pm.setDevicePixelRatio(1.0)

            trimmed = self._trim_transparent_margins(source_pm, alpha_threshold=8)
            if trimmed is not None and not trimmed.isNull():
                trimmed.setDevicePixelRatio(1.0)
                source_pm = trimmed

            tray_icon = QIcon()
            fill_ratio = 0.95
            for sz in (16, 20, 24, 32, 48, 64):
                target_side = max(1, int(round(sz * fill_ratio)))
                fitted = source_pm.scaled(
                    target_side,
                    target_side,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if fitted.isNull():
                    continue
                fitted.setDevicePixelRatio(1.0)
                canvas = QPixmap(sz, sz)
                canvas.fill(Qt.GlobalColor.transparent)
                painter = QPainter()
                if painter.begin(canvas):
                    try:
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                        x = (sz - fitted.width()) // 2
                        y = (sz - fitted.height()) // 2
                        painter.drawPixmap(x, y, fitted)
                    finally:
                        painter.end()
                if not canvas.isNull():
                    tray_icon.addPixmap(canvas)

            return tray_icon if not tray_icon.isNull() else icon
        except Exception:
            return icon

    def _trim_transparent_margins(self, pixmap: QPixmap, alpha_threshold: int = 0) -> QPixmap:
        """Trim outer transparent pixels so tiny tray sizes keep more visible content."""
        try:
            if pixmap is None or pixmap.isNull():
                return pixmap
            pixmap.setDevicePixelRatio(1.0)
            img = pixmap.toImage()
            if img.isNull():
                return pixmap

            w, h = img.width(), img.height()
            if w <= 0 or h <= 0:
                return pixmap

            def row_has_alpha(y: int, x0: int, x1: int) -> bool:
                for xx in range(x0, x1):
                    if img.pixelColor(xx, y).alpha() > alpha_threshold:
                        return True
                return False

            def col_has_alpha(x: int, y0: int, y1: int) -> bool:
                for yy in range(y0, y1):
                    if img.pixelColor(x, yy).alpha() > alpha_threshold:
                        return True
                return False

            top = 0
            while top < h and not row_has_alpha(top, 0, w):
                top += 1
            if top >= h:
                return pixmap

            bottom = h - 1
            while bottom >= top and not row_has_alpha(bottom, 0, w):
                bottom -= 1

            left = 0
            while left < w and not col_has_alpha(left, top, bottom + 1):
                left += 1

            right = w - 1
            while right >= left and not col_has_alpha(right, top, bottom + 1):
                right -= 1

            rect_w = right - left + 1
            rect_h = bottom - top + 1
            if rect_w <= 0 or rect_h <= 0:
                return pixmap
            if rect_w == w and rect_h == h:
                return pixmap
            cropped = pixmap.copy(left, top, rect_w, rect_h)
            cropped.setDevicePixelRatio(1.0)
            return cropped
        except Exception:
            return pixmap

    def _make_icon_square(self, icon: QIcon, size: int = 512) -> QIcon:
        """Adds transparent padding to non-square icons to prevent stretching,
        after cropping existing transparent whitespace to maximize visible area."""
        try:
            if icon.isNull():
                return icon
            # Use a large base pixmap to preserve quality
            pixmap = icon.pixmap(size, size)
            if pixmap.isNull():
                return icon
            pixmap.setDevicePixelRatio(1.0)

            # --- Autocrop transparent whitespace ---
            try:
                cropped = self._trim_transparent_margins(pixmap, alpha_threshold=8)
                if cropped is not None and not cropped.isNull():
                    pixmap = cropped
                    pixmap.setDevicePixelRatio(1.0)
            except Exception:
                pass

            w, h = pixmap.width(), pixmap.height()
            if w == h:
                return QIcon(pixmap)

            # Create a square transparent canvas based on the largest dimension
            max_side = max(w, h)
            square_pm = QPixmap(max_side, max_side)
            square_pm.fill(Qt.GlobalColor.transparent)

            # Center the original (now cropped) pixmap onto the square canvas
            painter = QPainter(square_pm)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            x = (max_side - w) // 2
            y = (max_side - h) // 2
            painter.drawPixmap(x, y, pixmap)
            painter.end()

            return QIcon(square_pm)
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
            channel = self.settings.value(KEY_CHANNEL, "J-POP")
            fmt = self.settings.value(KEY_FORMAT, "Vorbis")
            # Aggiorna intestazione principale
            self.label.setText(self.i18n.t("header").format(channel=channel, format=fmt))
            # Aggiorna etichette statiche dei valori
            if hasattr(self, "channel_value"):
                self.channel_value.setText(channel)
            if hasattr(self, "format_value"):
                self.format_value.setText(fmt)
            if hasattr(self, "status_footer"):
                self.status_footer.set_format(str(fmt))
            if hasattr(self, "channel_switch"):
                self.channel_switch.set_selected(str(channel))
            # Mantieni o aggiorna titolo finestra in base al Now Playing
            try:
                title = getattr(self, "_current_title", "") or ""
                self._apply_window_title(title)
            except Exception:
                pass
        except Exception:
            pass

    def _close_embedded_settings(self) -> None:
        try:
            if hasattr(self, "settings_button"):
                self.settings_button.set_active(False)
            if hasattr(self, "_view_stack"):
                self._view_stack.slide_to_index(0, direction=-1)
        except Exception:
            pass

    def open_settings(self):
        try:
            # Toggle off with smooth slide-out if embedded settings panel is already open
            if hasattr(self, "_view_stack") and self._view_stack.currentIndex() == 1:
                self._close_embedded_settings()
                return

            # Ensure main window is visible if triggered from system tray
            if not self.isVisible():
                self.showNormal()

            # Salva stato precedente
            was_playing = bool(self.player and self.player.is_playing())
            prev_channel = self.settings.value(KEY_CHANNEL, "J-POP")
            prev_format = self.settings.value(KEY_FORMAT, "Vorbis")
            prev_path = self.player.get_configured_path()
            prev_backend = self.settings.value(KEY_AUDIO_BACKEND, "auto")
            prev_tray_enabled = self._get_bool(KEY_TRAY_ENABLED, True)
            try:
                prev_nc = int(self.settings.value(KEY_NETWORK_CACHING, 1000))
            except Exception:
                prev_nc = 1000
            prev_dev_console = self._get_bool(KEY_DEV_CONSOLE_ENABLED, False)
            prev_audio_idx = self.settings.value(KEY_AUDIO_DEVICE_INDEX, "")

            # Reuse persistent embedded panel so opening is instantaneous & 60 FPS
            if not hasattr(self, "_settings_dlg") or self._settings_dlg is None:
                dlg = SettingsDialog(self, embedded=True)
                self._settings_dlg = dlg
                self._view_stack.addWidget(dlg)
            else:
                dlg = self._settings_dlg
                dlg.reload_from_settings()
                try:
                    dlg.accepted.disconnect()
                    dlg.rejected.disconnect()
                    dlg.settings_changed.disconnect()
                except Exception:
                    pass
            try:
                self._apply_prev_audio_idx = prev_audio_idx

                def _on_apply_from_dialog():
                    try:
                        new_audio_idx = self.settings.value(KEY_AUDIO_DEVICE_INDEX, "")
                        if new_audio_idx != getattr(self, "_apply_prev_audio_idx", ""):
                            if was_playing:
                                self._restart_playback_with_session_persistence(
                                    notification_body=(
                                        "Audio riavviato: il timer di sessione continua"
                                    )
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
                                if hasattr(self, "dev_console") and self.dev_console:
                                    self.dev_console.set_show_dev(
                                        self._get_bool(KEY_DEV_CONSOLE_SHOW_DEV, False)
                                    )
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
                lang = self.settings.value(KEY_LANG, "it")
                self.i18n.set_lang("it" if lang not in ("it", "en") else lang)
                self.apply_translations()
                # Aggiorna header e valori visivi canale/formato da QSettings
                self.update_header_label()
                if hasattr(self, "channel_value"):
                    self.channel_value.setText(self.settings.value(KEY_CHANNEL, "J-POP"))
                if hasattr(self, "format_value"):
                    self.format_value.setText(self.settings.value(KEY_FORMAT, "Vorbis"))
                # Se canale o formato sono cambiati, riavvia WS/stream
                # ma mantieni il Now Playing finché non arriva un nuovo evento
                try:
                    new_channel = self.settings.value(KEY_CHANNEL, "J-POP")
                    new_format = self.settings.value(KEY_FORMAT, "Vorbis")
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
                    new_audio_idx = self.settings.value(KEY_AUDIO_DEVICE_INDEX, "")
                    if new_audio_idx != prev_audio_idx:
                        if was_playing:
                            self._restart_playback_with_session_persistence(
                                notification_body="Audio riavviato: il timer di sessione continua"
                            )
                except Exception:
                    pass
                # Percorso VLC / backend
                new_path = self.settings.value(KEY_LIBVLC_PATH, "") or None
                new_backend = self.settings.value(KEY_AUDIO_BACKEND, "auto")
                path_changed = prev_path != new_path
                backend_changed = prev_backend != new_backend
                # Theme (light mode removed, keep dark mode always applied)
                self.apply_theme()
                # Ricalibra network caching status
                self.update_vlc_status_label()
                # Se backend/path è cambiato o network-caching è variato sensibile, riavvia
                try:
                    new_nc = int(self.settings.value(KEY_NETWORK_CACHING, 1000))
                except Exception:
                    new_nc = 1000
                if backend_changed or path_changed or new_nc != prev_nc:
                    self.status_changed.emit(self.t("status_restarting"))
                    time.sleep(0.5)
                    # Recreate player with new settings
                    try:
                        self.player.stop()
                    except Exception:
                        pass
                    try:
                        self.player = self._create_player(on_event=self._on_player_event)
                    except Exception:
                        self.player = PlayerVLC(
                            on_event=self._on_player_event,
                            libvlc_path=new_path,
                            network_caching_ms=new_nc,
                        )
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
                            if hasattr(self, "player") and self.player and self.player.is_playing():
                                if self._session_timer and not self._session_timer.isActive():
                                    self._session_timer.start()
                        except Exception:
                            pass
                    else:
                        if self._session_timer and self._session_timer.isActive():
                            self._session_timer.stop()
                    if hasattr(self, "session_label"):
                        self.session_label.show()
                    self._update_session_label()
                    self.update_tray_texts()
                except Exception:
                    pass
                # Dev console enable/disable may have changed
                new_dev_console = self._get_bool(KEY_DEV_CONSOLE_ENABLED, False)
                if new_dev_console != prev_dev_console:
                    try:
                        if not new_dev_console:
                            if hasattr(self, "dev_console") and self.dev_console:
                                try:
                                    self.dev_console.deactivate_logging()
                                except Exception:
                                    pass
                                # Non chiudere la UI della console: consenti all'utente
                                # di aprirla/vederla anche se il logging di background è disattivato
                                # (prima: self.dev_console.close())
                        else:
                            if hasattr(self, "dev_console") and self.dev_console:
                                try:
                                    self.dev_console.set_show_dev(
                                        self._get_bool(KEY_DEV_CONSOLE_SHOW_DEV, False)
                                    )
                                except Exception:
                                    pass
                                try:
                                    self.dev_console.activate_logging()
                                except Exception:
                                    pass
                    except Exception:
                        pass

            # Collega e mostra nel pannello integrato della home
            def _on_ok_embedded():
                _on_dialog_accepted()
                self._close_embedded_settings()

            try:
                dlg.accepted.connect(_on_ok_embedded)
                dlg.rejected.connect(self._close_embedded_settings)
                dlg.settings_changed.connect(_on_dialog_accepted)
            except Exception:
                pass
            try:
                if hasattr(self, "settings_button"):
                    self.settings_button.set_active(True)
                self._view_stack.slide_to_index(1, direction=1)
            except Exception:
                pass
        except Exception:
            pass

    def t(self, key: str, **kwargs) -> str:
        try:
            return str(self.i18n.t(key, **kwargs))
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
            if not hasattr(self, "dev_console") or self.dev_console is None:
                try:
                    self.dev_console = DevConsole(self, translator=self.i18n, logger=self.log)
                except Exception:
                    return
            # Ensure the [DEV] filter is up-to-date with settings
            try:
                if hasattr(self, "dev_console") and self.dev_console:
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
                    self.dev_console.apply_theme(True)
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass

    # Sleep timer logic
    def sleep_start_clicked(self) -> None:
        try:
            minutes = int(self.spin_sleep.value()) if hasattr(self, "spin_sleep") else 0
            if minutes <= 0:
                minutes = 1
            self.settings.setValue(KEY_SLEEP_MINUTES, int(minutes))
            self._sleep_remaining_sec = int(minutes * 60)
            self._sleep_fadeout_sec = (
                min(30, max(10, int(0.2 * self._sleep_remaining_sec)))
                if self._sleep_remaining_sec > 60
                else min(15, self._sleep_remaining_sec)
            )
            self._sleep_saved_volume = (
                int(self.volume_slider.value()) if hasattr(self, "volume_slider") else 80
            )
            try:
                if self._sleep_timer and not self._sleep_timer.isActive():
                    self._sleep_timer.start()
                elif self._sleep_timer:
                    # restart
                    self._sleep_timer.stop()
                    self._sleep_timer.start()
            except Exception:
                pass
            if hasattr(self, "sleep_label"):
                self.sleep_label.setText(
                    self.t("sleep_remaining", time=self._format_mmss(self._sleep_remaining_sec))
                )
                self.sleep_label.setVisible(True)
            if hasattr(self, "sleep_timer_widget"):
                self.sleep_timer_widget.set_active_countdown(self._sleep_remaining_sec)
            if hasattr(self, "playback_controls"):
                m, s = divmod(max(0, self._sleep_remaining_sec), 60)
                self.playback_controls.set_sleep_active(True, f"{m:02d}:{s:02d}")
        except Exception:
            pass

    def sleep_cancel_clicked(self) -> None:
        try:
            if self._sleep_timer and self._sleep_timer.isActive():
                self._sleep_timer.stop()
            # restore volume if we had saved it
            if self._sleep_saved_volume is not None and hasattr(self, "volume_slider"):
                try:
                    self.volume_slider.setValue(int(self._sleep_saved_volume))
                except Exception:
                    pass
            self._sleep_remaining_sec = 0
            self._sleep_saved_volume = None
            if hasattr(self, "sleep_label"):
                self.sleep_label.setText("")
                self.sleep_label.setVisible(False)
            if hasattr(self, "sleep_timer_widget"):
                self.sleep_timer_widget.set_inactive()
            if hasattr(self, "playback_controls"):
                self.playback_controls.set_sleep_active(False)
        except Exception:
            pass

    def _get_ws_url_for_channel(self, channel: str):
        """Restituisce l'URL del gateway WebSocket corretto in base al canale."""
        try:
            ch = (channel or "").strip().upper()
            if ch == "K-POP" or "K-POP" in ch:
                return "wss://listen.moe/kpop/gateway_v2"
            return "wss://listen.moe/gateway_v2"
        except Exception:
            return "wss://listen.moe/gateway_v2"

    def _restart_ws_for_channel(self, channel: str) -> None:
        """Riavvia il client WebSocket puntando al gateway corretto per il canale specificato."""
        try:
            # Arresta il WS corrente
            try:
                if hasattr(self, "ws") and self.ws:
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
            channel = self.settings.value(KEY_CHANNEL, "J-POP")
            fmt = self.settings.value(KEY_FORMAT, "Vorbis")
            urls = STREAMS.get(channel)
            if isinstance(urls, dict):
                url = urls.get(fmt)
                if url:
                    return url
                # fallback: prova Vorbis, altrimenti il primo disponibile
                url = urls.get("Vorbis") or (next(iter(urls.values())) if urls else None)
                if url:
                    return url
            # fallback globale noto
            jpop = STREAMS.get("J-POP", {})
            return jpop.get("Vorbis") or (
                next(iter(jpop.values())) if jpop else "https://listen.moe/stream"
            )
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

    def _set_status_text(self, text: str) -> None:
        try:
            value = str(text or "").strip()
            if hasattr(self, "status_label"):
                self.status_label.setText(value)
                # Keep status text available internally but never show it above the album cover.
                self.status_label.setVisible(False)
        except Exception:
            pass

    def update_now_playing_label(self):
        try:
            self._request_album_cover(self._current_cover_ref)
        except Exception:
            pass
        title = self._current_title or self.t("unknown")
        artist = self._current_artist or ""
        text = f"<b>{title}</b>" + (f" — {artist}" if artist and title != "–" else "")
        # Append remaining or total duration
        time_text = "--:--"
        try:
            if getattr(self, "_current_duration_seconds", None) == 0:
                time_text = self.t("live_mode")
            elif self._current_duration_seconds and int(self._current_duration_seconds) > 0:
                # Prefer remaining time only if start timestamp is plausible;
                # otherwise show total duration
                mmss = None
                try:
                    dur = int(self._current_duration_seconds)
                except Exception:
                    dur = None
                if dur and self._current_start_epoch is not None:
                    try:
                        import time

                        now = time.time() + getattr(self, "_clock_sync_offset", 0)
                        # _current_start_epoch is the absolute UTC end time of the song
                        remaining = self._current_start_epoch - now
                        elapsed = dur - remaining
                    except Exception:
                        elapsed = None
                    # Use remaining only when elapsed is within plausible range
                    # (+/- 60s slack for clock skew)
                    if elapsed is not None and -60 <= elapsed <= dur + 60:
                        # If PC clock is behind (elapsed < 0), remaining shouldn't exceed dur
                        remaining = dur - max(0, elapsed)
                        if remaining < 0:
                            remaining = 0
                        mmss = self._format_mmss(remaining)
                        if hasattr(self, "song_elapsed_label"):
                            self.song_elapsed_label.setText(
                                self._format_mmss(int(max(0, min(elapsed, dur))))
                            )
                    else:
                        # Fallback to total duration to avoid misleading or extreme values
                        mmss = self._format_mmss(dur)
                        if hasattr(self, "song_elapsed_label"):
                            self.song_elapsed_label.setText("0:00")
                elif dur:
                    mmss = self._format_mmss(dur)
                    if hasattr(self, "song_elapsed_label"):
                        self.song_elapsed_label.setText("0:00")
                if mmss:
                    time_text = mmss
        except Exception:
            pass
        try:
            if hasattr(self, "song_time_label"):
                self.song_time_label.setText(time_text)
        except Exception:
            pass
        if hasattr(self, "now_playing_title"):
            self.now_playing_title.setText(title)
        if hasattr(self, "now_playing_artist"):
            self.now_playing_artist.setText(artist)
        self.now_playing_changed.emit(text)
        # Update window title too
        try:
            self._apply_window_title(title)
        except Exception:
            pass

    def _restart_playback_with_session_persistence(
        self, notification_body: Optional[str] = None
    ) -> None:
        """Helper to restart playback while preserving session timer, emitting notification."""
        try:
            self._skip_session_reset_once = True
            self.stop_stream(reset_session=False)
            # Small delay to ensure backend has released resources
            QTimer.singleShot(200, self.play_stream)

            if (
                notification_body
                and self._get_bool(KEY_TRAY_NOTIFICATIONS, True)
                and self._get_bool(KEY_TRAY_ENABLED, True)
            ):
                self.notify_tray.emit("Listen.moe", notification_body)
        except Exception:
            # Fallback if async timer fails
            try:
                self.play_stream()
            except Exception:
                pass

    # ------------------- Tray helpers (static) -------------------
    def update_tray_texts(self) -> None:
        try:
            if not hasattr(self, "tray_mgr") or self.tray_mgr is None:
                return
            self.tray_mgr.update_tooltip(self._get_tray_tooltip())
        except Exception:
            pass

    def _get_tray_tooltip(self) -> str:
        """Centralized logic to compose the tray tooltip from current state."""
        try:
            # Header
            try:
                header = self.i18n.t("header").format(
                    channel=self.settings.value(KEY_CHANNEL, "J-POP"),
                    format=self.settings.value(KEY_FORMAT, "Vorbis"),
                )
            except Exception:
                if hasattr(self, "label"):
                    header = self.label.text()
                else:
                    header = APP_TITLE

            # Now Playing
            now = ""
            if hasattr(self, "now_playing_label"):
                text = self.now_playing_label.text()
                # Remove HTML tags for tooltip if present (simplified check)
                now = re.sub(r"<[^>]+>", "", text)

            # Session
            session_enabled = self._get_bool(KEY_SESSION_TIMER_ENABLED, True)
            session = ""
            if session_enabled and hasattr(self, "session_label"):
                session = self.session_label.text()

            # Join parts
            parts = [header]
            if now:
                parts.append(now)
            if session:
                parts.append(session)
            return "\n".join(parts)
        except Exception:
            return APP_TITLE

    def _notify_tray(self, title: str, body: str) -> None:
        try:
            # Rispetta impostazioni utente
            if not self._get_bool(KEY_TRAY_ENABLED, True) or not self._get_bool(
                KEY_TRAY_NOTIFICATIONS, True
            ):
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
            if hasattr(self, "tray_mgr") and self.tray_mgr is not None:
                self.tray_mgr.show_message(title or "", body or "")
        except Exception:
            pass

    def _get_tray_icon(self) -> QIcon:
        try:
            if (
                hasattr(self, "_icon_app_tray")
                and self._icon_app_tray is not None
                and not self._icon_app_tray.isNull()
            ):
                return self._icon_app_tray  # type: ignore[no-any-return]
        except Exception:
            pass
        try:
            if (
                hasattr(self, "_icon_app")
                and self._icon_app is not None
                and not self._icon_app.isNull()
            ):
                return self._icon_app  # type: ignore[no-any-return]
        except Exception:
            pass
        try:
            return self.windowIcon()
        except Exception:
            return QIcon()

    def _ensure_tray(self, enabled: bool) -> None:
        try:
            self._tray_enabled = bool(enabled)
            # Ensure tray manager exists
            if not hasattr(self, "tray_mgr") or self.tray_mgr is None:
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
                self.tray_mgr.ensure_tray_enabled(
                    self._tray_enabled,
                    window_icon=self._get_tray_icon(),
                    tooltip=self._get_tray_tooltip(),
                )
            except Exception:
                pass
            # Aggiorna stato dei controlli in base allo stato corrente (con override UI pausa)
            try:
                self._update_tray_controls()
            except Exception:
                pass
        except Exception:
            pass

    def update_tray_icon(self) -> None:
        try:
            if not hasattr(self, "tray_mgr") or self.tray_mgr is None:
                return
            # Update tray visibility/icon/tooltip based on current state
            self.tray_mgr.ensure_tray_enabled(
                self._tray_enabled,
                window_icon=self._get_tray_icon(),
                tooltip=self._get_tray_tooltip(),
            )
        except Exception:
            pass

    def _tray_change_channel(self, channel: str) -> None:
        try:
            self._apply_tray_stream_setting_change(KEY_CHANNEL, channel, ws_channel=channel)
        except Exception:
            pass

    def _tray_change_format(self, fmt: str) -> None:
        try:
            self._apply_tray_stream_setting_change(KEY_FORMAT, fmt)
        except Exception:
            pass

    def _apply_tray_stream_setting_change(
        self, key: str, value: str, ws_channel: Optional[str] = None
    ) -> None:
        """Shared flow for tray changes that affect stream/channel/format."""
        try:
            try:
                self.settings.setValue(key, value)
            except Exception:
                pass
            try:
                self.update_header_label()
            except Exception:
                pass
            try:
                self.update_tray_texts()
            except Exception:
                pass
            if ws_channel is not None:
                try:
                    self._restart_ws_for_channel(ws_channel)
                except Exception:
                    pass
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
                self.vlc_status_icon.setStyleSheet(  # type: ignore[attr-defined]
                    "background-color: #2e7d32; border-radius: 5px;"
                    if ok
                    else "background-color: #c62828; border-radius: 5px;"
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
                self.vlc_status.setText(self.i18n.t("vlc_not_found"))  # type: ignore[attr-defined]
            else:
                self.vlc_status.setText(txt or "Audio backend OK")  # type: ignore[attr-defined]
            if hasattr(self, "status_footer"):
                backend_name = "Audio"
                if hasattr(self, "player") and self.player is not None:
                    backend_name = getattr(
                        self.player,
                        "BACKEND_NAME",
                        type(self.player).__name__.replace("Player", ""),
                    )
                self.status_footer.set_backend_status(backend_name, is_ready=ok)
                fmt = str(self.settings.value(KEY_FORMAT, "Vorbis"))
                self.status_footer.set_format(fmt)
        except Exception:
            pass

    # ------------------- Player controls -------------------
    def play_stream(self, is_retry: bool = False, *args) -> None:
        try:
            self._retry_pending = False
            if is_retry and getattr(self, "_retry_count", 0) > self._max_retries:
                return
            if not is_retry:
                self._retry_count = 0
            with self._playback_lock:
                # Determine URL and check backend readiness
                url = None
                try:
                    url = self.get_selected_stream_url()
                except Exception:
                    url = None
                if not hasattr(self, "player") or self.player is None or not url:
                    try:
                        self.log.info("[UI] play_stream aborted: no player backend or url")
                    except Exception:
                        pass
                    self.status_changed.emit(self.t("status_error"))
                    return
                if not getattr(self.player, "is_ready", lambda: False)():
                    init_err = getattr(self.player, "get_init_error", lambda: "sconosciuto")()
                    self.log.error(
                        "[UI] play_stream aborted: backend %s is not ready: %s",
                        type(self.player).__name__,
                        init_err,
                    )
                    self.status_changed.emit(self.t("status_no_backend"))
                    self._retry_pending = False
                    self._refresh_play_button_text(False)
                    return
                try:
                    self.log.info(f"[UI] play_stream clicked; backend={type(self.player).__name__}")
                    self.log.info(
                        "[UI] %s diagnostics: ready=%s; init_error=%s",
                        type(self.player).__name__,
                        self.player.is_ready(),
                        getattr(self.player, "get_init_error", lambda: None)(),
                    )
                    # Sanitizza URL prima di log e play
                    try:
                        m = re.search(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&()*+,;=%]+", url or "")
                        safe_url = (m.group(0) if m else (url or "").strip()).rstrip(
                            ".,;!?)]}'\" \t\r\n"
                        )
                        if safe_url.lower().endswith("/mp3.") or safe_url.lower().endswith(".mp3."):
                            safe_url = safe_url[:-1]
                    except Exception:
                        safe_url = url
                    self.log.info(f"[UI] play_stream url={safe_url}")
                except Exception:
                    safe_url = url
                self.status_changed.emit(
                    self.t("status_opening") if hasattr(self, "t") else "Opening..."
                )
                try:
                    if hasattr(self, "song_progress"):
                        self.song_progress.trigger_play_launch()
                except Exception:
                    pass
                # Preserva il timer se stiamo già riproducendo
                # (es. cambio URL o click Riproduci mentre attivo)
                try:
                    if (
                        self.player.is_playing()
                        or getattr(self.player, "is_paused", lambda: False)()
                    ):
                        self._skip_session_reset_once = True
                except Exception:
                    pass
                ok = self.player.play_url(safe_url)
                if not ok:
                    # Fallback: prova formato alternativo per lo stesso canale
                    try:
                        channel = self.settings.value(KEY_CHANNEL, "J-POP")
                        cur_fmt = self.settings.value(KEY_FORMAT, "Vorbis")
                        alt_fmt = "MP3" if cur_fmt == "Vorbis" else "Vorbis"
                        alt_url = STREAMS.get(channel, {}).get(alt_fmt)
                        if alt_url:
                            try:
                                m2 = re.search(
                                    r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&()*+,;=%]+", alt_url or ""
                                )
                                alt_safe = (m2.group(0) if m2 else (alt_url or "").strip()).rstrip(
                                    ".,;!?)]}'\" \t\r\n"
                                )
                                if alt_safe.lower().endswith("/mp3.") or alt_safe.lower().endswith(
                                    ".mp3."
                                ):
                                    alt_safe = alt_safe[:-1]
                                self.log.info(
                                    f"[UI] primary play failed, trying fallback "
                                    f"format {alt_fmt}: {alt_safe}"
                                )
                            except Exception:
                                alt_safe = alt_url
                            ok = self.player.play_url(alt_safe)
                    except Exception:
                        pass
                if not ok:
                    self.status_changed.emit(self.t("status_error"))
                    try:
                        self.log.info("[UI] play_stream failed")
                    except Exception:
                        pass
                    self._refresh_play_button_text(False)
                else:
                    try:
                        if hasattr(self, "_icon_app") and not self._icon_app.isNull():
                            self.setWindowIcon(self._icon_app)
                    except Exception:
                        pass
                    self._refresh_play_button_text(True)
                    self.tray_icon_refresh.emit()
                    try:
                        self.log.info("[UI] play_stream started")
                    except Exception:
                        pass
                    # Start session timer on play if enabled
                    try:
                        # Do not reset automatically; keep cumulative during session unless stopped
                        self._apply_session_timer_running_state(True)
                    except Exception:
                        pass
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def pause_resume(self) -> None:
        try:
            needs_play = False
            with self._playback_lock:
                try:
                    self.log.info("[UI] pause_resume clicked")
                except Exception:
                    pass
                # Aggiorna subito lo stato UI di pausa e la tray (pre-toggle)
                try:
                    new_paused = not bool(getattr(self, "_ui_paused", False))
                    self._ui_paused = new_paused
                    is_muted = bool(getattr(self.player, "get_mute", lambda: False)())
                    if hasattr(self, "tray_mgr") and self.tray_mgr:
                        self.log.debug(
                            "[UI] pause_resume(pre-toggle): new_paused=%s, is_muted=%s",
                            new_paused,
                            is_muted,
                        )
                        self.tray_mgr.update_controls_state(not new_paused, new_paused, is_muted)
                except Exception:
                    pass

                if not new_paused:
                    try:
                        is_playing = getattr(self.player, "is_playing", lambda: False)()
                        is_paused_backend = getattr(self.player, "is_paused", lambda: False)()
                        if not is_playing and not is_paused_backend:
                            needs_play = True
                    except Exception:
                        pass

                if not needs_play:
                    # Esegui il toggle del backend
                    self.player.pause_toggle()

                # Gestisci il session timer e aggiorna solo il tooltip
                try:
                    self._apply_session_timer_running_state(not new_paused)
                except Exception:
                    pass
                self._refresh_play_button_text(not new_paused)

            if needs_play:
                try:
                    self.log.info("[UI] Backend stopped during pause, restarting stream.")
                except Exception:
                    pass
                self.play_stream()
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def stop_stream(self, reset_session: bool = True) -> None:
        try:
            self._retry_count = 0
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
                    self.status_changed.emit(self.t("status_stopped"))
                except Exception:
                    pass
                try:
                    if hasattr(self, "_icon_app") and not self._icon_app.isNull():
                        self.setWindowIcon(self._icon_app)
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
                            if hasattr(self, "session_label"):
                                self.session_label.show()  # show 0:00 if enabled
                            self._update_session_label()
                            self.update_tray_texts()
                        else:
                            # Preserve session timer during internal restarts
                            # (device/channel changes)
                            # Keep label visible and refresh tooltip without resetting seconds
                            if hasattr(self, "session_label"):
                                self.session_label.show()
                            self._update_session_label()
                            self.update_tray_texts()
                except Exception:
                    pass
                # Aggiorna controlli tray dopo stop
                try:
                    is_muted = bool(getattr(self.player, "get_mute", lambda: False)())
                    if hasattr(self, "tray_mgr") and self.tray_mgr:
                        self.tray_mgr.update_controls_state(False, False, is_muted)
                except Exception:
                    pass
                try:
                    # Aggiorna titolo finestra: preserva il Now Playing durante riavvii interni
                    if reset_session:
                        self._apply_window_title("")
                    else:
                        # Mantieni il titolo corrente se disponibile, altrimenti fallback a base
                        try:
                            title = getattr(self, "_current_title", "") or ""
                        except Exception:
                            title = ""
                        self._apply_window_title(title)
                except Exception:
                    pass
                self._refresh_play_button_text(False)
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def change_volume(self, value: int) -> None:
        try:
            self.player.set_volume(int(value))
            self.settings.setValue(KEY_VOLUME, int(value))
            # Aggiorna UI volume
            try:
                if hasattr(self, "volume_value_label"):
                    self.volume_value_label.setText(f"{int(value)}%")
                if hasattr(self, "volume_slider"):
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
            self.settings.setValue(KEY_MUTE, "true" if checked else "false")
        except Exception:
            pass
        try:
            if hasattr(self, "playback_controls"):
                self.playback_controls.set_muted(checked)
            self.mute_button.setText(self.i18n.t("unmute") if checked else self.i18n.t("mute"))
            self.mute_button.setToolTip(
                self.i18n.t("tt_unmute") if checked else self.i18n.t("tt_mute")
            )
        except Exception:
            pass
        try:
            if hasattr(self, "player") and self.player:
                self.player.set_mute(checked)
        except Exception:
            pass
        # Aggiorna testi azioni tray (Muto/Unmute e Play/Pausa) rispettando lo stato UI di pausa
        try:
            self._update_tray_controls()
        except Exception:
            pass

        # Salvaguardia: se abbiamo appena disattivato il muto ma il volume è 0,
        # proponi ripristino a 60%
        try:
            if not checked:
                try:
                    vol = (
                        int(self.volume_slider.value())
                        if hasattr(self, "volume_slider")
                        else int(self.player.get_volume())
                    )
                except Exception:
                    vol = 0
                if vol <= 0:
                    try:
                        msg = QMessageBox(self)
                        msg.setWindowTitle(self.i18n.t("volume_zero_title"))
                        msg.setText(self.i18n.t("volume_zero_text"))
                        restore_btn = msg.addButton(
                            self.i18n.t("restore"), QMessageBox.ButtonRole.AcceptRole
                        )
                        msg.addButton(
                            self.i18n.t("settings_cancel"), QMessageBox.ButtonRole.RejectRole
                        )
                        msg.setIcon(QMessageBox.Icon.Question)
                        self._make_frameless_msg(msg)
                        try:
                            apply_windows_titlebar_dark_mode(msg, True)
                        except Exception:
                            pass
                        msg.exec()
                        if msg.clickedButton() == restore_btn:
                            if hasattr(self, "volume_slider"):
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
            if hasattr(self, "playback_controls"):
                self.playback_controls._on_speaker_clicked()
            else:
                self.mute_button.toggle()
        except Exception:
            pass

    def _on_autoplay_toggled(self, checked: bool) -> None:
        try:
            self.settings.setValue(KEY_AUTOPLAY, "true" if checked else "false")
            self.log.info(f"[UI] autoplay toggled -> {checked}")
        except Exception:
            pass

    def force_stop_all(self) -> None:
        try:
            self.log.info("[UI] FORCE STOP clicked")
        except Exception:
            pass
        try:
            if hasattr(self, "player") and self.player:
                self.player.force_cleanup()
        except Exception:
            pass
        # Stop and reset session timer when forcing stop
        try:
            if self._get_bool(KEY_SESSION_TIMER_ENABLED, True):
                if (
                    hasattr(self, "_session_timer")
                    and self._session_timer
                    and self._session_timer.isActive()
                ):
                    self._session_timer.stop()
                self._session_seconds = 0
                if hasattr(self, "session_label"):
                    self.session_label.show()
                self._update_session_label()
                self.update_tray_texts()
        except Exception:
            pass
