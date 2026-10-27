import json
import struct
import time
import uuid

from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtWidgets import QApplication

from core.discord_presence import DiscordPresence, activity_payload


def wait_for(qapp, predicate):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    assert predicate()


def frame(opcode, payload):
    data = json.dumps(payload).encode()
    return struct.pack("<II", opcode, len(data)) + data


def receive(qapp, socket):
    wait_for(qapp, lambda: socket.bytesAvailable() >= 8)
    header = bytes(socket.read(8))
    opcode, size = struct.unpack("<II", header)
    wait_for(qapp, lambda: socket.bytesAvailable() >= size)
    return opcode, json.loads(bytes(socket.read(size)))


def test_activity_timestamps_and_pause():
    playing = activity_payload("Song", "Artist", "Radio", "https://example.com/cover.png",
                               200, 60, False)
    assert playing["timestamps"] == {"start": 140, "end": 200}
    assert playing["assets"]["large_image"] == "https://example.com/cover.png"
    paused = activity_payload("Song", "Artist", "Radio", "local.png", 200, 60, True)
    assert "timestamps" not in paused
    assert "assets" not in paused
    assert activity_payload("–", "Artist", "Radio", None, None, 0, False) is None


def test_ipc_handshake_update_clear_and_reconnect():
    qapp = QApplication.instance() or QApplication([])
    server = QLocalServer()
    name = "kikumoe-test-" + uuid.uuid4().hex
    assert server.listen(name)
    rpc = DiscordPresence()
    rpc.configure(True, "123456789")
    rpc.paths = [name, name]
    rpc.set_activity({"details": "Song"})
    wait_for(qapp, server.hasPendingConnections)
    peer = server.nextPendingConnection()
    assert receive(qapp, peer) == (0, {"v": 1, "client_id": "123456789"})
    ready = frame(1, {"evt": "READY"})
    peer.write(ready[:5])
    peer.flush()
    qapp.processEvents()
    assert not rpc.ready
    peer.write(ready[5:])
    peer.flush()
    _, command = receive(qapp, peer)
    assert command["cmd"] == "SET_ACTIVITY"
    assert command["args"]["activity"] == {"details": "Song"}
    rpc.set_activity(None)
    _, clear = receive(qapp, peer)
    assert clear["args"]["activity"] is None
    peer.disconnectFromServer()
    wait_for(qapp, server.hasPendingConnections)
    peer = server.nextPendingConnection()
    assert receive(qapp, peer)[0] == 0
    rpc.stop()
    server.close()


def test_playback_sync_supports_backend_without_pause_method(monkeypatch):
    from types import SimpleNamespace

    from ui.main_window import ListenMoePlayer

    class Presence:
        enabled = False
        activity = None

        def configure(self, enabled, client_id):
            self.client_id = client_id
            self.enabled = enabled and bool(client_id)

        def set_activity(self, activity):
            self.activity = activity

    monkeypatch.setenv("KIKUMOE_DISCORD_CLIENT_ID", "123456789")
    presence = Presence()
    window = SimpleNamespace(
        discord_presence=presence,
        settings=SimpleNamespace(value=lambda key, default: default),
        _get_bool=lambda key, default: True,
        player=SimpleNamespace(is_playing=lambda: True),
        _ui_paused=False,
        _current_title="Song",
        _current_artist="Artist",
        _current_radio_provider="listenmoe",
        _current_start_epoch=200,
        _current_duration_seconds=60,
        _clock_sync_offset=0,
        _current_cover_ref=None,
        _normalize_album_cover_url=lambda cover: None,
        i18n=SimpleNamespace(t=lambda key: key),
    )
    ListenMoePlayer._sync_discord_presence(window)
    assert presence.activity["details"] == "Song"
    assert presence.client_id == "123456789"
    monkeypatch.delenv("KIKUMOE_DISCORD_CLIENT_ID")
    ListenMoePlayer._sync_discord_presence(window)
    assert presence.client_id == "484517809179852800"
    window.settings.value = lambda key, default: "987654321"
    monkeypatch.setenv("KIKUMOE_DISCORD_CLIENT_ID", "123456789")
    ListenMoePlayer._sync_discord_presence(window)
    assert presence.client_id == "987654321"
    window._ui_paused = True
    ListenMoePlayer._sync_discord_presence(window)
    assert "timestamps" not in presence.activity
    assert "pause" in presence.activity["state"]
    window._ui_paused = False
    window.player.is_playing = lambda: False
    ListenMoePlayer._sync_discord_presence(window)
    assert presence.activity is None


def test_custom_id_row_follows_toggle(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings

    import ui.settings_dialog as settings_module

    qapp = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(settings_module, "QSettings", lambda *args: settings)
    dialog = settings_module.SettingsDialog(embedded=True)
    assert dialog.discord_id_row.isHidden()
    dialog.chk_discord_rpc.setChecked(True)
    assert not dialog.discord_id_row.isHidden()
    dialog.txt_discord_client_id.setText("987654321")
    dialog.chk_discord_rpc.setChecked(False)
    assert dialog.discord_id_row.isHidden()
    assert dialog.txt_discord_client_id.text() == "987654321"
    dialog.close()
    qapp.processEvents()
