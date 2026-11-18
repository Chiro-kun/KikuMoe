import json
import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from core.ssl_compat import get_websocket_sslopt

logger = logging.getLogger("kikumoe.ws")

try:
    from websocket import WebSocketApp
except Exception:
    WebSocketApp = None  # type: ignore[assignment, misc]

WS_URL = "wss://listen.moe/gateway_v2"


class NowPlayingWS:
    def __init__(
        self,
        on_now_playing: Callable[[str, str, Optional[int], Optional[float], Optional[str]], None],
        on_error_text: Callable[[str], None],
        on_closed_text: Callable[[str], None],
        channel_filter: Optional[Callable[[dict], bool]] = None,
        ws_url: Optional[str] = None,
    ):
        self.ws_app: Optional[WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.ws_heartbeat_interval_ms: Optional[int] = None
        self.ws_heartbeat_timer: Optional[threading.Timer] = None
        self._reconnect_timer: Optional[threading.Timer] = None
        self.ws_should_reconnect: bool = True
        self.on_now_playing = on_now_playing
        self.on_error_text = on_error_text
        self.on_closed_text = on_closed_text
        self.channel_filter = channel_filter
        self.ws_url = ws_url or WS_URL
        self._lock = threading.RLock()

    def start(self):
        with self._lock:
            if not self.ws_should_reconnect:
                return
            if self._reconnect_timer:
                try:
                    self._reconnect_timer.cancel()
                except Exception:
                    pass
                self._reconnect_timer = None

            if WebSocketApp is None:
                try:
                    self.on_error_text("websocket-client not installed: unable to start WebSocket.")
                except Exception:
                    pass
                return

            def on_open(ws):
                try:
                    if not self.ws_should_reconnect:
                        return
                    ws.send(json.dumps({"op": 2}))
                except Exception:
                    pass

            def on_message(ws, message):
                if not self.ws_should_reconnect:
                    return
                try:
                    data = json.loads(message)
                except Exception:
                    return
                if not isinstance(data, dict):
                    return
                op = data.get("op")
                if op == 0:
                    raw_d = data.get("d")
                    d = raw_d if isinstance(raw_d, dict) else {}
                    hb = d.get("heartbeat")
                    if isinstance(hb, int):
                        self.ws_heartbeat_interval_ms = hb
                        self._schedule_heartbeat()
                    try:
                        if self.ws_should_reconnect:
                            ws.send(json.dumps({"op": 2}))
                    except Exception:
                        pass
                elif op == 1:
                    raw_d = data.get("d")
                    if not isinstance(raw_d, dict):
                        return
                    d = raw_d
                    t = data.get("t")
                    if t in ("TRACK_UPDATE", "TRACK_UPDATE_REQUEST"):
                        try:
                            if self.channel_filter is not None and not self.channel_filter(d):
                                return
                        except Exception:
                            pass
                        raw_song = d.get("song")
                        song = raw_song if isinstance(raw_song, dict) else {}
                        title = song.get("title") or "Unknown"
                        artists = song.get("artists")
                        artist_name = ""
                        if isinstance(artists, list) and artists:
                            first_artist = artists[0]
                            if isinstance(first_artist, dict):
                                artist_name = str(first_artist.get("name") or "")
                        duration = song.get("duration")
                        try:
                            duration = int(duration) if duration is not None else None
                        except Exception:
                            duration = None
                        album_cover = None
                        try:
                            albums = song.get("albums") or []
                            if isinstance(albums, list) and len(albums) > 0:
                                first_album = albums[0] or {}
                                if isinstance(first_album, dict):
                                    album_cover = first_album.get("image")
                        except Exception:
                            album_cover = None
                        start_ts = None
                        try:
                            start_time_iso = d.get("startTime")
                            if isinstance(start_time_iso, str):
                                iso = start_time_iso.replace("Z", "+00:00")
                                try:
                                    dt = datetime.fromisoformat(iso)
                                    if dt.tzinfo is None:
                                        dt = dt.replace(tzinfo=timezone.utc)
                                    start_ts = dt.timestamp()
                                except ValueError:
                                    try:
                                        if "." in iso:
                                            iso_no_ms = iso.split(".")[0] + "+00:00"
                                            dt = datetime.fromisoformat(iso_no_ms)
                                            start_ts = dt.replace(tzinfo=timezone.utc).timestamp()
                                    except Exception:
                                        start_ts = None
                        except Exception:
                            start_ts = None
                        if self.ws_should_reconnect:
                            self.on_now_playing(title, artist_name, duration, start_ts, album_cover)

            def on_error(ws, error):
                if not self.ws_should_reconnect:
                    return
                err_str = str(error)
                if "CERTIFICATE_VERIFY_FAILED" in err_str:
                    logger.error(
                        "[WebSocket] SSL Certificate verification failed: %s. "
                        "Check system CA certificates or local system clock.",
                        err_str,
                    )
                self.on_error_text(err_str)

            def on_close(ws, code, msg):
                with self._lock:
                    if not self.ws_should_reconnect:
                        return
                    self.on_closed_text("")
                    if self._reconnect_timer:
                        try:
                            self._reconnect_timer.cancel()
                        except Exception:
                            pass
                    self._reconnect_timer = threading.Timer(5.0, self.start)
                    self._reconnect_timer.daemon = True
                    self._reconnect_timer.start()

            self.ws_app = WebSocketApp(
                self.ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            self.ws_thread = threading.Thread(
                target=self.ws_app.run_forever,
                kwargs={
                    "ping_interval": None,
                    "sslopt": get_websocket_sslopt() if self.ws_url.startswith("wss://") else None,
                },
                daemon=True,
            )
            self.ws_thread.start()

    def _schedule_heartbeat(self):
        with self._lock:
            if (
                not self.ws_should_reconnect
                or self.ws_heartbeat_interval_ms is None
                or self.ws_app is None
            ):
                return

            def send_hb():
                try:
                    with self._lock:
                        if not self.ws_should_reconnect:
                            return
                        ws = self.ws_app
                    if ws is not None:
                        ws.send(json.dumps({"op": 9}))
                except Exception:
                    pass
                self._schedule_heartbeat()

            delay = self.ws_heartbeat_interval_ms / 1000.0
            if self.ws_heartbeat_timer:
                try:
                    self.ws_heartbeat_timer.cancel()
                except Exception:
                    pass
            self.ws_heartbeat_timer = threading.Timer(delay, send_hb)
            self.ws_heartbeat_timer.daemon = True
            self.ws_heartbeat_timer.start()

    def shutdown(self):
        with self._lock:
            self.ws_should_reconnect = False
            try:
                if self._reconnect_timer:
                    self._reconnect_timer.cancel()
                    self._reconnect_timer = None
            except Exception:
                pass
            try:
                if self.ws_heartbeat_timer:
                    self.ws_heartbeat_timer.cancel()
                    self.ws_heartbeat_timer = None
            except Exception:
                pass
            ws_app = self.ws_app
            self.ws_app = None
            ws_thread = self.ws_thread
            self.ws_thread = None
        try:
            if ws_app:
                ws_app.close()
        except Exception:
            pass
        try:
            if ws_thread and ws_thread.is_alive() and ws_thread is not threading.current_thread():
                ws_thread.join(timeout=0.15)
        except Exception:
            pass

    def stop(self):
        self.shutdown()
