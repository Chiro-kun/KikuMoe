import json
import threading
from typing import Callable, Optional
from websocket import WebSocketApp
from datetime import datetime, timezone

WS_URL = "wss://listen.moe/gateway_v2"

class NowPlayingWS:
    def __init__(self,
                 on_now_playing: Callable[[str, str, Optional[int], Optional[float]], None],
                 on_error_text: Callable[[str], None],
                 on_closed_text: Callable[[str], None],
                 channel_filter: Optional[Callable[[dict], bool]] = None,
                 ws_url: Optional[str] = None):
        self.ws_app: Optional[WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.ws_heartbeat_interval_ms: Optional[int] = None
        self.ws_heartbeat_timer: Optional[threading.Timer] = None
        self.ws_should_reconnect: bool = True
        self.on_now_playing = on_now_playing
        self.on_error_text = on_error_text
        self.on_closed_text = on_closed_text
        self.channel_filter = channel_filter
        self.ws_url = ws_url or WS_URL

    def start(self):
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
                    self._schedule_heartbeat()
            elif op == 1:
                d = data.get("d", {})
                t = data.get("t")
                if t in ("TRACK_UPDATE", "TRACK_UPDATE_REQUEST"):
                    # Filtra per canale se richiesto
                    try:
                        if self.channel_filter is not None and not self.channel_filter(d):
                            return
                    except Exception:
                        # In caso di errore nel filtro, non bloccare l'aggiornamento
                        pass
                    song = d.get("song") or {}
                    title = song.get("title") or "Unknown"
                    artists = song.get("artists") or []
                    artist_name = artists[0].get("name") if artists else ""
                    # Durata (secondi) se presente nel payload
                    duration = song.get("duration")
                    try:
                        duration = int(duration) if duration is not None else None
                    except Exception:
                        duration = None
                    # startTime ISO8601 (UTC) -> epoch seconds
                    start_ts = None
                    try:
                        start_time_iso = d.get("startTime")
                        if isinstance(start_time_iso, str):
                            iso = start_time_iso.replace("Z", "+00:00")
                            dt = datetime.fromisoformat(iso)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            start_ts = dt.timestamp()
                    except Exception:
                        start_ts = None
                    self.on_now_playing(title, artist_name, duration, start_ts)

        def on_error(ws, error):
            self.on_error_text(str(error))

        def on_close(ws, code, msg):
            self.on_closed_text("")
            if self.ws_should_reconnect:
                threading.Timer(5.0, self.start).start()

        self.ws_app = WebSocketApp(
            self.ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        self.ws_thread = threading.Thread(target=self.ws_app.run_forever, kwargs={"ping_interval": None}, daemon=True)
        self.ws_thread.start()

    def _schedule_heartbeat(self):
        if self.ws_heartbeat_interval_ms is None or self.ws_app is None:
            return
        def send_hb():
            try:
                self.ws_app.send(json.dumps({"op": 9}))
            except Exception:
                pass
            self._schedule_heartbeat()
        delay = self.ws_heartbeat_interval_ms / 1000.0
        self.ws_heartbeat_timer = threading.Timer(delay, send_hb)
        self.ws_heartbeat_timer.daemon = True
        self.ws_heartbeat_timer.start()

    def shutdown(self):
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