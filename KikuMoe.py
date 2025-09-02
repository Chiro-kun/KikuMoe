from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QComboBox, QProgressBar, QShortcut
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QKeySequence
import vlc

from i18n import I18n
from ws_client import NowPlayingWS


class ListenMoePlayer(QWidget):
    status_changed = pyqtSignal(str)
    now_playing_changed = pyqtSignal(str)
    buffering_progress = pyqtSignal(int)
    buffering_visible = pyqtSignal(bool)

    def __init__(self):
        super().__init__()

        # i18n
        self.i18n = I18n('it')
        self._lang_map = {"Italiano": 'it', "English": 'en'}

        self.setWindowTitle(self.i18n.t('app_title'))
        self.layout = QVBoxLayout()

        # Header + Now playing
        self.label = QLabel(self.i18n.t('header').format(channel='J-POP', format='Vorbis'))
        self.status_label = QLabel("")
        self.now_playing_label = QLabel(f"{self.i18n.t('now_playing_prefix')} –")
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.status_label)
        self.layout.addWidget(self.now_playing_label)

        # Stream selectors (Channel + Format)
        sel_row = QHBoxLayout()
        self.channel_label = QLabel(self.i18n.t('channel_label'))
        self.channel_combo = QComboBox()
        self.channel_combo.addItems(["J-POP", "K-POP"])
        self.format_label = QLabel(self.i18n.t('format_label'))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Vorbis", "MP3"])  # Vorbis consigliato; MP3 per compatibilità
        sel_row.addWidget(self.channel_label)
        sel_row.addWidget(self.channel_combo)
        sel_row.addWidget(self.format_label)
        sel_row.addWidget(self.format_combo)
        self.layout.addLayout(sel_row)

        # Language selector
        lang_row = QHBoxLayout()
        self.lang_label = QLabel(self.i18n.t('language_label'))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Italiano", "English"])
        self.lang_combo.setCurrentIndex(0)
        lang_row.addWidget(self.lang_label)
        lang_row.addWidget(self.lang_combo)
        self.layout.addLayout(lang_row)

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
        self.volume_slider.setValue(80)
        self.mute_button = QPushButton(self.i18n.t('mute'))
        self.mute_button.setCheckable(True)
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
        self.pause_shortcut.activated.connect(self.pause_resume)

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
        self.channel_combo.currentIndexChanged.connect(self.on_stream_selection_changed)
        self.format_combo.currentIndexChanged.connect(self.on_stream_selection_changed)
        self.lang_combo.currentIndexChanged.connect(self.on_lang_changed)

        # VLC setup
        self.vlc_instance = vlc.Instance()
        self.player = self.vlc_instance.media_player_new()
        self.media = None

        # Attach VLC events to reflect state changes
        try:
            self._em = self.player.event_manager()
            for et in (
                vlc.EventType.MediaPlayerOpening,
                vlc.EventType.MediaPlayerBuffering,
                vlc.EventType.MediaPlayerPlaying,
                vlc.EventType.MediaPlayerPaused,
                vlc.EventType.MediaPlayerStopped,
                vlc.EventType.MediaPlayerEndReached,
                vlc.EventType.MediaPlayerEncounteredError,
            ):
                self._em.event_attach(et, self._on_vlc_event)
        except Exception:
            pass

        # Initialize volume/mute from UI
        self.player.audio_set_volume(self.volume_slider.value())
        self.player.audio_set_mute(False)

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

        self.update_header_label()

    # ------------------- i18n -------------------
    def on_lang_changed(self, idx: int):
        display = self.lang_combo.currentText()
        self.i18n.set_lang(self._lang_map.get(display, 'it'))
        self.apply_translations()

    def apply_translations(self):
        self.setWindowTitle(self.i18n.t('app_title'))
        self.channel_label.setText(self.i18n.t('channel_label'))
        self.format_label.setText(self.i18n.t('format_label'))
        self.lang_label.setText(self.i18n.t('language_label'))
        self.play_button.setText(self.i18n.t('play'))
        self.pause_button.setText(self.i18n.t('pause'))
        self.stop_button.setText(self.i18n.t('stop'))
        self.volume_label.setText(self.i18n.t('volume'))
        self.mute_button.setText(self.i18n.t('unmute') if self.mute_button.isChecked() else self.i18n.t('mute'))
        self.update_header_label()
        self.update_now_playing_label()

    # ------------------- Helpers -------------------
    def t(self, key: str, **kwargs) -> str:
        return self.i18n.t(key, **kwargs)

    def get_selected_stream_url(self) -> str:
        channel = self.channel_combo.currentText()
        fmt = self.format_combo.currentText()
        streams = {
            "J-POP": {
                "Vorbis": "https://listen.moe/stream",
                "MP3": "https://listen.moe/stream/mp3",
            },
            "K-POP": {
                "Vorbis": "https://listen.moe/kpop/stream",
                "MP3": "https://listen.moe/kpop/stream/mp3",
            },
        }
        return streams.get(channel, {}).get(fmt, "https://listen.moe/stream")

    def update_header_label(self):
        channel = self.channel_combo.currentText()
        fmt = self.format_combo.currentText()
        self.label.setText(self.t('header').format(channel=channel, format=fmt))

    def update_now_playing_label(self):
        title = self._current_title or '–'
        artist = self._current_artist or ''
        prefix = self.t('now_playing_prefix')
        text = f"{prefix} {title}" + (f" — {artist}" if artist and title != '–' else "")
        self.now_playing_changed.emit(text)

    def on_stream_selection_changed(self):
        self.update_header_label()
        try:
            state = self.player.get_state()
            is_playing = state in (vlc.State.Playing, vlc.State.Buffering, vlc.State.Opening)
        except Exception:
            is_playing = False
        if is_playing:
            try:
                self.media = self.vlc_instance.media_new(self.get_selected_stream_url())
                self.player.set_media(self.media)
                self.player.audio_set_volume(self.volume_slider.value())
                self.player.audio_set_mute(self.mute_button.isChecked())
                self.player.play()
            except Exception:
                pass

    # ------------------- VLC controls -------------------
    def volume_changed(self, value: int):
        try:
            self.player.audio_set_volume(int(value))
        except Exception:
            pass

    def mute_toggled(self, checked: bool):
        try:
            self.player.audio_set_mute(bool(checked))
            self.mute_button.setText(self.t('unmute') if checked else self.t('mute'))
        except Exception:
            pass

    def pause_resume(self):
        try:
            self.player.pause()
        except Exception:
            pass

    def _on_vlc_event(self, event):
        et = event.type
        if et == vlc.EventType.MediaPlayerOpening:
            self.status_changed.emit(self.t('status_opening'))
            self.buffering_visible.emit(True)
            self.buffering_progress.emit(0)
        elif et == vlc.EventType.MediaPlayerBuffering:
            pct = None
            try:
                pct = getattr(getattr(event, 'u', None), 'new_cache', None)
            except Exception:
                pct = None
            if pct is not None:
                self.buffering_visible.emit(True)
                try:
                    self.buffering_progress.emit(int(pct))
                except Exception:
                    self.buffering_progress.emit(0)
                self.status_changed.emit(self.t('status_buffering_pct', pct=int(pct)))
            else:
                self.buffering_visible.emit(True)
                self.status_changed.emit(self.t('status_buffering'))
        elif et == vlc.EventType.MediaPlayerPlaying:
            self.status_changed.emit(self.t('status_playing'))
            self.buffering_visible.emit(False)
        elif et == vlc.EventType.MediaPlayerPaused:
            self.status_changed.emit(self.t('status_paused'))
        elif et == vlc.EventType.MediaPlayerStopped:
            self.status_changed.emit(self.t('status_stopped'))
            self.buffering_visible.emit(False)
        elif et == vlc.EventType.MediaPlayerEndReached:
            self.status_changed.emit(self.t('status_ended'))
            self.buffering_visible.emit(False)
        elif et == vlc.EventType.MediaPlayerEncounteredError:
            self.status_changed.emit(self.t('status_error'))
            self.buffering_visible.emit(False)

    # ------------------- WebSocket callbacks -------------------
    def _on_now_playing(self, title: str, artist: str):
        self._current_title = title or self.t('unknown')
        self._current_artist = artist or ''
        self.update_now_playing_label()

    def _on_ws_error_text(self, error_text: str):
        self.now_playing_changed.emit(self.t('ws_error_prefix') + error_text)

    def _on_ws_closed_text(self, _):
        self.now_playing_changed.emit(self.t('ws_closed_reconnect'))

    # ------------------- Playback (VLC) -------------------
    def play_stream(self):
        try:
            self.status_changed.emit(self.t('status_opening'))
            self.media = self.vlc_instance.media_new(self.get_selected_stream_url())
            self.player.set_media(self.media)
            self.player.audio_set_volume(self.volume_slider.value())
            self.player.audio_set_mute(self.mute_button.isChecked())
            self.player.play()
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def stop_stream(self):
        try:
            self.player.stop()
            self.status_changed.emit(self.t('status_stopped'))
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

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