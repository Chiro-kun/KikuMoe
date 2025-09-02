from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QComboBox, QProgressBar, QShortcut, QFileDialog, QMessageBox
)
from PyQt5.QtCore import pyqtSignal, Qt, QSettings
from PyQt5.QtGui import QKeySequence
import os

from i18n import I18n
from ws_client import NowPlayingWS
from player_vlc import PlayerVLC
from config import STREAMS

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
        # Add VLC Path button for configurable libvlc
        self.vlc_button = QPushButton(self.i18n.t('libvlc_button'))
        self.vlc_button.clicked.connect(self.choose_libvlc_path)
        # Indicatore stato VLC
        self.vlc_status = QLabel("")
        lang_row.addWidget(self.lang_label)
        lang_row.addWidget(self.lang_combo)
        lang_row.addWidget(self.vlc_button)
        lang_row.addWidget(self.vlc_status)
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

        # Restore saved channel/format
        saved_channel = self.settings.value('channel', 'J-POP')
        saved_format = self.settings.value('format', 'Vorbis')
        self.channel_combo.setCurrentIndex(0 if saved_channel == 'J-POP' else 1)
        self.format_combo.setCurrentIndex(0 if saved_format == 'Vorbis' else 1)
        # Restore saved language selector index
        lang_index = 0 if (saved_lang == 'it') else 1
        self.lang_combo.setCurrentIndex(lang_index)

        # Player wrapper with optional libvlc path
        libvlc_path = self.settings.value('libvlc_path', None)
        self.player = PlayerVLC(on_event=self._on_player_event, libvlc_path=libvlc_path)
        if not self.player.is_ready():
            # Show a clear message explaining what to do
            self.status_changed.emit(self.i18n.t('libvlc_not_ready'))
        self.player.set_volume(self.volume_slider.value())
        self.player.set_mute(self.mute_button.isChecked())
        # Aggiorna indicatore stato VLC
        self.update_vlc_status_label()

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
        # persist language code
        self.settings.setValue('lang', self.i18n.lang)
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
        # Translate VLC path button
        if hasattr(self, 'vlc_button'):
            self.vlc_button.setText(self.i18n.t('libvlc_button'))
        self.update_header_label()
        self.update_now_playing_label()
        # Aggiorna label stato VLC secondo lingua corrente
        if hasattr(self, 'vlc_status'):
            self.update_vlc_status_label()

    # ------------------- Helpers -------------------
    def t(self, key: str, **kwargs) -> str:
        return self.i18n.t(key, **kwargs)

    def get_selected_stream_url(self) -> str:
        channel = self.channel_combo.currentText()
        fmt = self.format_combo.currentText()
        # persist selection
        self.settings.setValue('channel', channel)
        self.settings.setValue('format', fmt)
        return STREAMS.get(channel, {}).get(fmt, STREAMS["J-POP"]["Vorbis"])

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

    def update_vlc_status_label(self):
        try:
            if self.player and self.player.is_ready():
                text = "VLC è presente" if self.i18n.lang == 'it' else "VLC is present"
                color = "#2e7d32"
            else:
                text = "VLC non trovato" if self.i18n.lang == 'it' else "VLC not found"
                color = "#c62828"
            self.vlc_status.setText(text)
            self.vlc_status.setStyleSheet(f"color: {color}; font-weight: bold;")
            self.vlc_status.setVisible(True)
            # Suggerimento su come impostare il percorso
            self.vlc_status.setToolTip(self.i18n.t('libvlc_hint'))
        except Exception:
            pass

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
        start_dir = self.settings.value('libvlc_path', None) or os.path.expandvars(r"C:\\Program Files\\VideoLAN\\VLC")
        chosen = QFileDialog.getExistingDirectory(self, self.i18n.t('libvlc_choose_title'), start_dir)
        if not chosen:
            return
        if self.player.reinitialize(chosen):
            self.settings.setValue('libvlc_path', chosen)
            QMessageBox.information(self, 'VLC', self.i18n.t('libvlc_saved_ok') + '\n' + self.i18n.t('libvlc_hint'))
            self.status_changed.emit("")
            self.update_vlc_status_label()
        else:
            QMessageBox.warning(self, 'VLC', self.i18n.t('libvlc_saved_fail') + '\n' + self.i18n.t('libvlc_hint'))
            self.status_changed.emit(self.i18n.t('libvlc_not_ready'))
            self.update_vlc_status_label()

    # ------------------- Player controls -------------------
    def volume_changed(self, value: int):
        self.player.set_volume(int(value))
        self.settings.setValue('volume', int(value))

    def mute_toggled(self, checked: bool):
        self.player.set_mute(bool(checked))
        self.mute_button.setText(self.t('unmute') if checked else self.t('mute'))
        self.settings.setValue('mute', 'true' if checked else 'false')

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

    def _on_player_event(self, code: str, value):
        if code == 'opening':
            self.status_changed.emit(self.t('status_opening'))
            self.buffering_visible.emit(True)
            self.buffering_progress.emit(0)
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
            self.update_vlc_status_label()
        elif code == 'paused':
            self.status_changed.emit(self.t('status_paused'))
        elif code == 'stopped':
            self.status_changed.emit(self.t('status_stopped'))
            self.buffering_visible.emit(False)
        elif code == 'ended':
            self.status_changed.emit(self.t('status_ended'))
            self.buffering_visible.emit(False)
        elif code == 'libvlc_init_failed':
            self.status_changed.emit(self.t('libvlc_init_failed'))
            self.buffering_visible.emit(False)
            self.update_vlc_status_label()
        elif code == 'error':
            # Fallback generic error
            self.status_changed.emit(self.t('status_error'))
            self.buffering_visible.emit(False)

    # ------------------- Playback -------------------
    def play_stream(self):
        try:
            if not self.player.is_ready():
                # Try reinitialize with saved path, if any
                saved_path = self.settings.value('libvlc_path', None)
                if not self.player.reinitialize(saved_path):
                    self.status_changed.emit(self.t('libvlc_not_ready'))
                    self.update_vlc_status_label()
                    return
            self.status_changed.emit(self.t('status_opening'))
            self.player.play_url(self.get_selected_stream_url())
            self.player.set_volume(self.volume_slider.value())
            self.player.set_mute(self.mute_button.isChecked())
            self.update_vlc_status_label()
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    def stop_stream(self):
        try:
            self.player.stop()
            self.status_changed.emit(self.t('status_stopped'))
        except Exception as e:
            self.status_changed.emit(f"{self.t('status_error')} {e}")

    # ------------------- WebSocket callbacks -------------------
    def _on_now_playing(self, title: str, artist: str):
        self._current_title = title or self.t('unknown')
        self._current_artist = artist or ''
        self.update_now_playing_label()

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