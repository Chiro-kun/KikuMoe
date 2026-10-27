"""Optional Discord/arRPC Rich Presence over the local Discord IPC protocol."""

import json
import os
import struct
import sys
import tempfile
import uuid

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtNetwork import QLocalSocket

from core.constants import URL_FORGEJO


def ipc_paths():
    if sys.platform == "win32":
        return [rf"\\.\pipe\discord-ipc-{i}" for i in range(10)]
    roots = [os.environ.get(k) for k in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP")]
    roots += [tempfile.gettempdir(), "/tmp"]
    paths = []
    for root in roots:
        if root:
            for subdir in ("", "app/com.discordapp.Discord", "app/dev.vencord.Vesktop"):
                for i in range(10):
                    path = os.path.join(root, subdir, f"discord-ipc-{i}")
                    if path not in paths:
                        paths.append(path)
    return paths


def activity_payload(
    title, artist, station, cover, end_epoch, duration, paused, button_label="Open KikuMoe"
):
    if not title or title in ("–", "-"):
        return None
    activity = {"details": title[:128], "state": (artist or station or "Radio")[:128]}
    activity["buttons"] = [{"label": button_label, "url": URL_FORGEJO}]
    if cover and cover.startswith(("https://", "http://")) and len(cover) <= 300:
        activity["assets"] = {"large_image": cover, "large_text": (station or "KikuMoe")[:128]}
    if not paused and end_epoch and duration and duration > 0:
        activity["timestamps"] = {
            "start": int(end_epoch - duration),
            "end": int(end_epoch),
        }
    return activity


class DiscordPresence(QObject):
    """Non-blocking IPC client; retries when Discord or arRPC is unavailable."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.socket = QLocalSocket(self)
        self.socket.connected.connect(self._connected)
        self.socket.readyRead.connect(self._read)
        self.socket.disconnected.connect(self._disconnected)
        self.socket.errorOccurred.connect(self._error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._try_connect)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._failed)
        self.client_id = ""
        self.enabled = False
        self.ready = False
        self.paths = []
        self.index = 0
        self.buffer = b""
        self.activity = None
        self.sent = object()

    def configure(self, enabled, client_id):
        client_id = str(client_id or "").strip()
        enabled = bool(enabled and client_id.isascii() and client_id.isdigit())
        if (enabled, client_id) == (self.enabled, self.client_id):
            return
        self.stop()
        self.client_id = client_id
        self.enabled = enabled
        if enabled:
            self.paths = ipc_paths()
            self.index = 0
            self.timer.start(0)

    def set_activity(self, activity):
        self.activity = activity
        if self.ready and self.sent != activity:
            self._send(
                1,
                {
                    "cmd": "SET_ACTIVITY",
                    "args": {"pid": os.getpid(), "activity": activity},
                    "nonce": str(uuid.uuid4()),
                },
            )
            self.sent = activity

    def _send(self, opcode, payload):
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.socket.write(struct.pack("<II", opcode, len(data)) + data)

    def _try_connect(self):
        if not self.enabled:
            return
        if self.index >= len(self.paths):
            self.index = 0
            self.timer.start(10000)
            return
        path = self.paths[self.index]
        self.index += 1
        self.buffer = b""
        self.timeout.start(1500)
        self.socket.connectToServer(path)

    def _connected(self):
        self._send(0, {"v": 1, "client_id": self.client_id})

    def _read(self):
        self.buffer += bytes(self.socket.readAll())
        while len(self.buffer) >= 8:
            opcode, length = struct.unpack("<II", self.buffer[:8])
            if length > 1024 * 1024:
                self._failed()
                return
            if len(self.buffer) < 8 + length:
                return
            body, self.buffer = self.buffer[8 : 8 + length], self.buffer[8 + length :]
            if opcode == 3:
                self.socket.write(struct.pack("<II", 4, len(body)) + body)
            elif opcode == 2:
                self._failed()
                return
            elif opcode == 1:
                try:
                    message = json.loads(body.decode("utf-8"))
                except (ValueError, UnicodeError):
                    self._failed()
                    return
                if message.get("evt") == "READY":
                    self.timeout.stop()
                    self.ready = True
                    self.sent = object()
                    self.set_activity(self.activity)

    def _error(self, _error):
        self._failed()

    def _disconnected(self):
        self._failed()

    def _failed(self):
        self.timeout.stop()
        self.ready = False
        self.socket.abort()
        if self.enabled and not self.timer.isActive():
            self.timer.start(0 if self.index < len(self.paths) else 10000)
            if self.index >= len(self.paths):
                self.index = 0

    def stop(self):
        self.enabled = False
        self.timer.stop()
        self.timeout.stop()
        if self.ready:
            self.set_activity(None)
            self.socket.flush()
        self.ready = False
        self.socket.abort()
