import json
import threading
import requests
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QComboBox, QProgressBar, QShortcut
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QKeySequence
from websocket import WebSocketApp
import vlc

API_BASE_URL = "https://listen.moe/api"
LOGIN_URL = f"{API_BASE_URL}/login"
WS_URL = "wss://listen.moe/gateway_v2"

class ListenMoeAPI:
    def __init__(self):
        self.jwt = None

    def login(self, username, password):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/vnd.listen.v4+json"
        }
        data = {"username": username, "password": password}
        response = requests.post(LOGIN_URL, json=data, headers=headers)
        if response.status_code == 200:
            self.jwt = response.json().get("token")
            return True
        return False

    def get_headers(self):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/vnd.listen.v4+json"
        }
        if self.jwt:
            headers["Authorization"] = f"Bearer {self.jwt}"
        return headers

class ListenMoePlayer(QWidget):
    status_changed = pyqtSignal(str)
    now_playing_changed = pyqtSignal(str)
    buffering_progress = pyqtSignal(int)
    buffering_visible = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LISTEN.moe Player (VLC)")
        self.layout = QVBoxLayout()

        # Header + Now playing
        self.label = QLabel("LISTEN.moe - Streaming Vorbis (VLC)")
        self.status_label = QLabel("")
        self.now_playing_label = QLabel("Now Playing: –")
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.status_label)
        self.layout.addWidget(self.now_playing_label)

        # Stream selectors (Channel + Format)
        sel_row = QHBoxLayout()
        self.channel_label = QLabel("Canale:")
        self.channel_combo = QComboBox()
        self.channel_combo.addItems(["J-POP", "K-POP"])
        self.format_label = QLabel("Formato:")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Vorbis", "MP3"])  # Vorbis consigliato; MP3 per compatibilità
        sel_row.addWidget(self.channel_label)
        sel_row.addWidget(self.channel_combo)
        sel_row.addWidget(self.format_label)
        sel_row.addWidget(self.format_combo)
        self.layout.addLayout(sel_row)

        # Buffering progress bar
        self.buffer_bar = QProgressBar()
        self.buffer_bar.setRange(0, 100)
        self.buffer_bar.setVisible(False)
        self.layout.addWidget(self.buffer_bar)

        # Controls
        self.play_button = QPushButton("Play")
        self.pause_button = QPushButton("Pause")  # toggle
        self.stop_button = QPushButton("Stop")

        vol_row = QHBoxLayout()
        self.volume_label = QLabel("Volume")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.mute_button = QPushButton("Mute")
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

        # WebSocket state
        self.ws_app = None
        self.ws_thread = None
        self.ws_heartbeat_interval_ms = None
        self.ws_heartbeat_timer = None
        self.ws_should_reconnect = True

        self.start_ws()
        self.update_header_label()

    # ------------------- Helpers -------------------
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
        self.label.setText(f"LISTEN.moe - {channel} - {fmt} (VLC)")

    def on_stream_selection_changed(self):
        # Update header and, if currently playing, switch stream seamlessly
        self.update_header_label()
        try:
            state = self.player.get_state()
            is_playing = state in (vlc.State.Playing, vlc.State.Buffering, vlc.State.Opening)
        except Exception:
            is_playing = False
        if is_playing:
            # Rebuild media and play
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
            self.mute_button.setText("Unmute" if checked else "Mute")
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
            self.status_changed.emit("Opening…")
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
                self.status_changed.emit(f"Buffering… {int(pct)}%")
            else:
                self.buffering_visible.emit(True)
                self.status_changed.emit("Buffering…")
        elif et == vlc.EventType.MediaPlayerPlaying:
            self.status_changed.emit("Playing!")
            self.buffering_visible.emit(False)
        elif et == vlc.EventType.MediaPlayerPaused:
            self.status_changed.emit("Paused.")
        elif et == vlc.EventType.MediaPlayerStopped:
            self.status_changed.emit("Stopped.")
            self.buffering_visible.emit(False)
        elif et == vlc.EventType.MediaPlayerEndReached:
            self.status_changed.emit("Stream ended.")
            self.buffering_visible.emit(False)
        elif et == vlc.EventType.MediaPlayerEncounteredError:
            self.status_changed.emit("Playback error.")
            self.buffering_visible.emit(False)

    # ------------------- WebSocket -------------------
    def start_ws(self):
        def on_open(ws):
            pass

        def on_message(ws, message):
            try:
                data = json.loads(message)
            except Exception:
                return
            op = data.get("op")
            if op == 0:
                d = data.get("d", {})
                hb = d.get("heartbeat")
                if isinstance(hb, int):
                    self.ws_heartbeat_interval_ms = hb
                    self.schedule_heartbeat()
            elif op == 1:
                d = data.get("d", {})
                t = data.get("t")
                if t in ("TRACK_UPDATE", "TRACK_UPDATE_REQUEST"):
                    song = d.get("song") or {}
                    title = song.get("title") or "Unknown"
                    artists = song.get("artists") or []
                    artist_name = artists[0].get("name") if artists else ""
                    text = f"Now Playing: {title}" + (f" — {artist_name}" if artist_name else "")
                    self.now_playing_changed.emit(text)

        def on_error(ws, error):
            self.now_playing_changed.emit(f"Now Playing: errore WS: {error}")

        def on_close(ws, code, msg):
            self.now_playing_changed.emit("Now Playing: WS chiuso, riconnessione...")
            if self.ws_should_reconnect:
                threading.Timer(5.0, self.start_ws).start()

        self.ws_app = WebSocketApp(
            WS_URL,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        self.ws_thread = threading.Thread(target=self.ws_app.run_forever, kwargs={"ping_interval": None}, daemon=True)
        self.ws_thread.start()

    def schedule_heartbeat(self):
        if self.ws_heartbeat_interval_ms is None or self.ws_app is None:
            return
        def send_hb():
            try:
                self.ws_app.send(json.dumps({"op": 9}))
            except Exception:
                pass
            self.schedule_heartbeat()
        delay = self.ws_heartbeat_interval_ms / 1000.0
        self.ws_heartbeat_timer = threading.Timer(delay, send_hb)
        self.ws_heartbeat_timer.daemon = True
        self.ws_heartbeat_timer.start()

    def shutdown_ws(self):
        self.ws_should_reconnect = False
        try:
            if self.ws_heartbeat_timer:
                self.ws_heartbeat_timer.cancel()
        except Exception:
            pass
        try:
            if self.ws_app:
                self.ws_app.close()
        except Exception:
            pass
        try:
            if self.ws_thread and self.ws_thread.is_alive():
                self.ws_thread.join(timeout=1.0)
        except Exception:
            pass

    # ------------------- Playback (VLC) -------------------
    def play_stream(self):
        try:
            self.status_changed.emit("Opening…")
            self.media = self.vlc_instance.media_new(self.get_selected_stream_url())
            self.player.set_media(self.media)
            self.player.audio_set_volume(self.volume_slider.value())
            self.player.audio_set_mute(self.mute_button.isChecked())
            self.player.play()
        except Exception as e:
            self.status_changed.emit(f"Errore avvio: {e}")

    def stop_stream(self):
        try:
            self.player.stop()
            self.status_changed.emit("Stopped.")
        except Exception as e:
            self.status_changed.emit(f"Errore stop: {e}")

    def closeEvent(self, event):
        try:
            self.stop_stream()
        except Exception:
            pass
        try:
            self.shutdown_ws()
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