import json
import threading
import requests
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QLabel
from PyQt5.QtCore import pyqtSignal
from websocket import WebSocketApp
import vlc

STREAM_URL = "https://listen.moe/stream"
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

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LISTEN.moe Player (VLC)")
        self.layout = QVBoxLayout()
        self.label = QLabel("LISTEN.moe - Streaming Vorbis (VLC)")
        self.status_label = QLabel("")
        self.now_playing_label = QLabel("Now Playing: –")
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.status_label)
        self.layout.addWidget(self.now_playing_label)
        self.play_button = QPushButton("Play")
        self.stop_button = QPushButton("Stop")
        self.layout.addWidget(self.play_button)
        self.layout.addWidget(self.stop_button)
        self.setLayout(self.layout)

        self.play_button.clicked.connect(self.play_stream)
        self.stop_button.clicked.connect(self.stop_stream)
        self.status_changed.connect(self.status_label.setText)
        self.now_playing_changed.connect(self.now_playing_label.setText)

        # VLC setup
        self.vlc_instance = vlc.Instance()
        self.player = self.vlc_instance.media_player_new()
        self.media = None

        # WebSocket state
        self.ws_app = None
        self.ws_thread = None
        self.ws_heartbeat_interval_ms = None
        self.ws_heartbeat_timer = None
        self.ws_should_reconnect = True

        self.start_ws()

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
            self.status_changed.emit("Starting playback…")
            self.media = self.vlc_instance.media_new(STREAM_URL)
            self.player.set_media(self.media)
            self.player.play()
            self.status_changed.emit("Playing!")
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