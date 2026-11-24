"""Tests for cross-platform native file/directory picker helpers."""

from __future__ import annotations

import asyncio
import os
import sys
import types
from pathlib import Path

import pytest

_QAPP = None


def _ensure_qapp():
    global _QAPP
    from PyQt6.QtWidgets import QApplication

    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


def test_parse_qt_filters_normalizes_all_files():
    from ui.native_file_dialog import _format_portal_filters, _parse_qt_filters

    qt_filter = "Audio Files (*.mp3 *.flac *.ogg *.opus *.m4a *.aac *.wav);;All Files (*.*)"
    parsed = _parse_qt_filters(qt_filter)
    assert parsed == [
        ("Audio Files", ["*.mp3", "*.flac", "*.ogg", "*.opus", "*.m4a", "*.aac", "*.wav"]),
        ("All Files", ["*"]),
    ]

    portal = _format_portal_filters(parsed)
    assert portal[0] == (
        "Audio Files",
        [
            (0, "*.mp3"),
            (0, "*.flac"),
            (0, "*.ogg"),
            (0, "*.opus"),
            (0, "*.m4a"),
            (0, "*.aac"),
            (0, "*.wav"),
        ],
    )
    assert portal[1] == ("All Files", [(0, "*")])
    assert _parse_qt_filters("") == []


def test_uri_to_local_path():
    from ui.native_file_dialog import _uri_to_local_path

    assert (
        _uri_to_local_path("file:///home/alsog/Music/01.%20Kid%20Yugi%20-%20%231.flac")
        == "/home/alsog/Music/01. Kid Yugi - #1.flac"
    )
    assert _uri_to_local_path("https://example.com/song.mp3") == ""
    assert _uri_to_local_path("") == ""


def test_resolve_folder_and_name(tmp_path: Path):
    from ui.native_file_dialog import _resolve_folder_and_name

    music = tmp_path / "Music"
    music.mkdir()

    assert _resolve_folder_and_name(str(music), is_save=False) == (str(music.resolve()), "")
    assert _resolve_folder_and_name(str(tmp_path / "missing"), is_save=False) == (
        str(tmp_path.resolve()),
        "",
    )
    assert _resolve_folder_and_name(
        str(tmp_path / "no_such_parent" / "missing"), is_save=False
    ) == ("", "")
    assert _resolve_folder_and_name("console-20261114.log", is_save=True) == (
        "",
        "console-20261114.log",
    )
    assert _resolve_folder_and_name(str(music / "console.log"), is_save=True) == (
        str(music.resolve()),
        "console.log",
    )


def _install_socketless_event_loop(monkeypatch):
    """Avoid Windows sandbox socketpair() blocks inside asyncio.new_event_loop()."""
    if sys.platform != "win32":
        return

    import selectors
    import time

    class _NoSocketSelector(selectors.BaseSelector):
        def register(self, fileobj, events, data=None):
            raise NotImplementedError

        def unregister(self, fileobj):
            raise NotImplementedError

        def select(self, timeout=None):
            if timeout is not None and timeout > 0:
                time.sleep(min(timeout, 0.005))
            return []

        def get_map(self):
            return {}

    class _SocketlessSelectorLoop(asyncio.SelectorEventLoop):
        def __init__(self) -> None:
            super().__init__(selector=_NoSocketSelector())

        def _make_self_pipe(self) -> None:
            self._ssock = None
            self._csock = None

        def _close_self_pipe(self) -> None:
            pass

        def _write_to_self(self) -> None:
            pass

    monkeypatch.setattr(asyncio, "new_event_loop", _SocketlessSelectorLoop)


def _install_fake_dbus_next(monkeypatch, *, portal_version=4, response_code=0, response_uris=None):
    _install_socketless_event_loop(monkeypatch)
    calls: list[dict[str, object]] = []

    class FakeBusType:
        SESSION = 1

    class FakeMessageType:
        METHOD_CALL = 1
        ERROR = 3
        SIGNAL = 4

    class FakeVariant:
        def __init__(self, signature: str, value):
            self.signature = signature
            self.value = value

    class FakeMessage:
        def __init__(
            self,
            *,
            destination="",
            path="",
            interface="",
            member="",
            signature="",
            body=None,
            message_type=FakeMessageType.METHOD_CALL,
        ):
            self.destination = destination
            self.path = path
            self.interface = interface
            self.member = member
            self.signature = signature
            self.body = body or []
            self.message_type = message_type

    class FakeBus:
        def __init__(self):
            self.unique_name = ":1.99"
            self.handlers = []
            self.disconnected = False
            self._disconnect_future: asyncio.Future[None] | None = None

        async def connect(self):
            return self

        def add_message_handler(self, cb):
            self.handlers.append(cb)

        async def wait_for_disconnect(self):
            loop = asyncio.get_running_loop()
            self._disconnect_future = loop.create_future()
            await self._disconnect_future

        def disconnect(self):
            self.disconnected = True
            if self._disconnect_future and not self._disconnect_future.done():
                self._disconnect_future.cancel()

        async def call(self, msg: FakeMessage):
            calls.append(
                {
                    "interface": msg.interface,
                    "member": msg.member,
                    "body": msg.body,
                }
            )
            if msg.member == "Get":
                return FakeMessage(body=[FakeVariant("u", portal_version)])
            if msg.member == "AddMatch":
                return FakeMessage(body=[])
            if msg.member in ("OpenFile", "SaveFile"):
                options = msg.body[2]
                token = options["handle_token"].value
                req_path = f"/org/freedesktop/portal/desktop/request/1_99/{token}"

                def _emit_response():
                    results = {}
                    if response_uris is not None:
                        results["uris"] = FakeVariant("as", list(response_uris))
                    sig = FakeMessage(
                        path=req_path,
                        interface="org.freedesktop.portal.Request",
                        member="Response",
                        message_type=FakeMessageType.SIGNAL,
                        body=[response_code, results],
                    )
                    for cb in list(self.handlers):
                        cb(sig)

                asyncio.get_running_loop().call_soon(_emit_response)
                return FakeMessage(body=[req_path])
            return FakeMessage(message_type=FakeMessageType.ERROR, body=["Unsupported"])

    fake_dbus_next = types.ModuleType("dbus_next")
    fake_dbus_next.BusType = FakeBusType  # type: ignore[attr-defined]
    fake_dbus_next.Message = FakeMessage  # type: ignore[attr-defined]
    fake_dbus_next.MessageType = FakeMessageType  # type: ignore[attr-defined]
    fake_dbus_next.Variant = FakeVariant  # type: ignore[attr-defined]

    fake_aio = types.ModuleType("dbus_next.aio")
    fake_aio.MessageBus = lambda bus_type=None: FakeBus()  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "dbus_next", fake_dbus_next)
    monkeypatch.setitem(sys.modules, "dbus_next.aio", fake_aio)
    return calls


@pytest.mark.parametrize(
    ("mode", "expected_member"),
    [
        ("open_files", "OpenFile"),
        ("open_dir", "OpenFile"),
        ("save_file", "SaveFile"),
    ],
)
def test_portal_file_chooser_modes(tmp_path: Path, monkeypatch, mode: str, expected_member: str):
    from ui.native_file_dialog import _run_portal_sync

    music_dir = tmp_path / "Music"
    music_dir.mkdir()
    uri = "file:///home/alsog/Music/01%20Track.flac"
    calls = _install_fake_dbus_next(
        monkeypatch, portal_version=4, response_code=0, response_uris=[uri]
    )

    directory = str(music_dir / "console.log") if mode == "save_file" else str(music_dir)
    res = _run_portal_sync(
        mode=mode,
        caption="Select",
        directory=directory,
        file_filter="Audio Files (*.mp3 *.flac);;All Files (*.*)",
        parent_window="",
    )

    assert res.handled is True
    assert res.cancelled is False
    assert res.paths == ["/home/alsog/Music/01 Track.flac"]

    chooser_call = next(c for c in calls if c["member"] == expected_member)
    options = chooser_call["body"][2]  # type: ignore[index]
    assert options["modal"].value is True
    expected_folder = os.fsencode(str(music_dir.resolve())) + b"\x00"
    assert options["current_folder"].value == expected_folder
    if mode == "open_files":
        assert options["multiple"].value is True
        assert "filters" in options
    elif mode == "open_dir":
        assert options["directory"].value is True
    elif mode == "save_file":
        assert options["current_name"].value == "console.log"


def test_portal_cancel_and_old_version_fallback(tmp_path: Path, monkeypatch):
    from ui.native_file_dialog import _run_portal_sync

    _install_fake_dbus_next(monkeypatch, portal_version=4, response_code=1, response_uris=[])
    cancelled = _run_portal_sync(
        mode="open_files",
        caption="Add Files",
        directory=str(tmp_path),
        file_filter="",
        parent_window="",
    )
    assert cancelled.handled is True
    assert cancelled.cancelled is True
    assert cancelled.paths == []

    # FileChooser < v3 does not support directory selection; should signal fallback
    _install_fake_dbus_next(monkeypatch, portal_version=2, response_code=0, response_uris=[])
    old_portal = _run_portal_sync(
        mode="open_dir",
        caption="Add Folder",
        directory=str(tmp_path),
        file_filter="",
        parent_window="",
    )
    assert old_portal.handled is False


def test_cli_fallback_commands_and_results(tmp_path: Path, monkeypatch):
    import ui.native_file_dialog as nfd

    cmd = nfd._build_cli_command(
        "zenity",
        mode="open_files",
        caption="Add Files",
        directory=str(tmp_path),
        file_filter="Audio Files (*.mp3 *.flac);;All Files (*.*)",
    )
    assert cmd[0] == "zenity"
    assert "--multiple" in cmd
    assert f"--filename={str(tmp_path).rstrip(os.sep)}{os.sep}" in cmd
    assert "--file-filter=Audio Files | *.mp3 *.flac" in cmd
    assert "--file-filter=All Files | *" in cmd

    kcmd = nfd._build_cli_command(
        "kdialog",
        mode="open_dir",
        caption="Add Folder",
        directory=str(tmp_path),
        file_filter="",
    )
    assert kcmd[:4] == ["kdialog", "--title", "Add Folder", "--getexistingdirectory"]

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.delenv("KDE_FULL_SESSION", raising=False)
    monkeypatch.setattr(
        nfd.shutil, "which", lambda name: f"/usr/bin/{name}" if name == "zenity" else None
    )

    class FakeProc:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    monkeypatch.setattr(
        nfd.subprocess, "run", lambda *a, **kw: FakeProc(0, "/tmp/a.mp3\n/tmp/b.flac\n")
    )
    accepted = nfd._run_cli_picker(
        mode="open_files", caption="Files", directory=str(tmp_path), file_filter=""
    )
    assert accepted.handled is True
    assert accepted.cancelled is False
    assert accepted.paths == ["/tmp/a.mp3", "/tmp/b.flac"]

    monkeypatch.setattr(nfd.subprocess, "run", lambda *a, **kw: FakeProc(1, ""))
    cancelled = nfd._run_cli_picker(
        mode="open_files", caption="Files", directory=str(tmp_path), file_filter=""
    )
    assert cancelled.handled is True
    assert cancelled.cancelled is True


def test_public_wrappers_use_native_and_cancel_without_qfiledialog(monkeypatch):
    from PyQt6.QtWidgets import QFileDialog, QWidget

    import ui.native_file_dialog as nfd

    _ensure_qapp()
    parent = QWidget()
    qt_calls: list[str] = []

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *a, **kw: qt_calls.append("files") or ([], ""),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *a, **kw: qt_calls.append("dir") or "",
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *a, **kw: qt_calls.append("save") or ("", ""),
    )

    monkeypatch.setattr(nfd, "_should_use_linux_native", lambda: True)

    # 1. Native accepted -> QFileDialog is not invoked
    monkeypatch.setattr(
        nfd,
        "_run_linux_native_worker",
        lambda **kw: nfd._DialogResult(handled=True, paths=["/music/song.flac"]),
    )
    assert nfd.get_open_file_names(parent, "Add Files") == (["/music/song.flac"], "")
    assert nfd.get_existing_directory(parent, "Add Folder") == "/music/song.flac"
    assert nfd.get_save_file_name(parent, "Save") == ("/music/song.flac", "")
    assert qt_calls == []

    # 2. Native cancelled -> QFileDialog must NOT reopen
    monkeypatch.setattr(
        nfd,
        "_run_linux_native_worker",
        lambda **kw: nfd._DialogResult(handled=True, cancelled=True),
    )
    assert nfd.get_open_file_names(parent, "Add Files") == ([], "")
    assert nfd.get_existing_directory(parent, "Add Folder") == ""
    assert nfd.get_save_file_name(parent, "Save") == ("", "")
    assert qt_calls == []

    # 3. Native unavailable -> falls back cleanly to QFileDialog
    monkeypatch.setattr(
        nfd,
        "_run_linux_native_worker",
        lambda **kw: nfd._DialogResult(handled=False),
    )
    nfd.get_open_file_names(parent, "Add Files")
    nfd.get_existing_directory(parent, "Add Folder")
    nfd.get_save_file_name(parent, "Save")
    assert qt_calls == ["files", "dir", "save"]
    parent.close()
