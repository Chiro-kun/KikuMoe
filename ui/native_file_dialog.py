"""Cross-platform native file and directory picker helpers.

On Windows and macOS, Qt's static ``QFileDialog`` helpers already open the OS
native file picker. On Linux, bundled Qt builds (pip wheels / PyInstaller /
AppImage) frequently lack matching desktop platform-theme plugins (e.g. KDE,
qt6ct, or GTK3 in isolated bundles) and silently fall back to Qt's built-in
toolkit file dialog.

To provide a truly native desktop file picker across Linux environments (GNOME,
KDE Plasma, Hyprland, Sway, XFCE, AppImage, etc.), this module prefers the
FreeDesktop XDG Desktop Portal (``org.freedesktop.portal.FileChooser`` over
session D-Bus via ``dbus_next``), falls back to ``kdialog`` / ``zenity`` if
the portal is unavailable, and finally falls back to ``QFileDialog``.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import QEvent, QEventLoop, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QFileDialog, QWidget

from core.logger import get_logger

_log = get_logger("NativeFileDialog")

_PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
_PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
_PORTAL_FILE_CHOOSER_IFACE = "org.freedesktop.portal.FileChooser"
_PORTAL_REQUEST_IFACE = "org.freedesktop.portal.Request"
_DBUS_IFACE = "org.freedesktop.DBus"
_DBUS_PROPS_IFACE = "org.freedesktop.DBus.Properties"

_BLOCKED_INPUT_EVENTS = frozenset(
    {
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.MouseButtonRelease,
        QEvent.Type.KeyPress,
        QEvent.Type.KeyRelease,
    }
)

_active_pickers: set[int] = set()


@dataclass
class _DialogResult:
    """Outcome of a native picker attempt."""

    handled: bool
    cancelled: bool = False
    paths: list[str] = field(default_factory=list)
    selected_filter: str = ""


class _PickerBridge(QObject):
    """Thread-safe signal bridge back to the Qt GUI thread."""

    finished = pyqtSignal(object)


class _ModalInputBlocker(QObject):
    """Consume user input targeting a parent window while a portal dialog is open."""

    def __init__(self, modal_window: QWidget) -> None:
        super().__init__()
        self._modal_window = modal_window

    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        if (
            a1 is not None
            and a1.type() in _BLOCKED_INPUT_EVENTS
            and isinstance(a0, QWidget)
            and a0.window() is self._modal_window
        ):
            return True
        return False


def _should_use_linux_native() -> bool:
    """Return True when running an interactive Linux session (not offscreen/pytest)."""
    if not sys.platform.startswith("linux"):
        return False
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return False
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return True


def _parse_qt_filters(filter_str: str) -> list[tuple[str, list[str]]]:
    """Parse Qt-style ``'Audio Files (*.mp3 *.flac);;All Files (*.*)'`` filters.

    Normalizes ``*.*`` to ``*`` so POSIX/GTK/portal pickers also show files
    without dots/extensions under "All Files".
    """
    if not filter_str or not filter_str.strip():
        return []

    parsed: list[tuple[str, list[str]]] = []
    for raw_entry in filter_str.split(";;"):
        entry = raw_entry.strip()
        if not entry:
            continue
        match = re.match(r"^(.*?)\(([^()]*)\)\s*$", entry)
        if match:
            label = match.group(1).strip() or entry
            raw_globs = match.group(2)
        else:
            label = entry
            raw_globs = entry

        globs: list[str] = []
        for token in re.split(r"[\s,;]+", raw_globs.strip()):
            tok = token.strip()
            if not tok:
                continue
            if tok == "*.*":
                tok = "*"
            if tok not in globs:
                globs.append(tok)

        if globs:
            parsed.append((label, globs))

    return parsed


def _format_portal_filters(
    parsed_filters: list[tuple[str, list[str]]],
) -> list[tuple[str, list[tuple[int, str]]]]:
    """Convert parsed filters into XDG FileChooser ``a(sa(us))`` structure."""
    portal_filters: list[tuple[str, list[tuple[int, str]]]] = []
    for label, globs in parsed_filters:
        patterns = [(0, glob) for glob in globs]
        portal_filters.append((label, patterns))
    return portal_filters


def _uri_to_local_path(uri: str) -> str:
    """Convert a ``file://`` URI returned by XDG Desktop Portal to a local path."""
    if not uri:
        return ""
    parsed = urlparse(uri)
    if parsed.scheme and parsed.scheme != "file":
        return ""
    path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc not in ("", "localhost"):
        return f"//{parsed.netloc}{path}"
    return path


def _build_parent_window_handle(parent: QWidget | None) -> str:
    """Build an XDG portal parent_window identifier when safe (X11), else empty."""
    if parent is None:
        return ""
    app = QGuiApplication.instance()
    if not isinstance(app, QGuiApplication):
        return ""
    if app.platformName() == "xcb":
        win = parent.window()
        if win is not None and win.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
            return f"x11:{int(win.winId()):x}"
    return ""


def _resolve_folder_and_name(directory: str, is_save: bool) -> tuple[str, str]:
    """Split *directory* into an existing initial folder and optional suggested filename."""
    if not directory:
        return "", ""

    expanded = os.path.expanduser(directory)
    if is_save:
        if os.path.isdir(expanded):
            return os.path.abspath(expanded), ""
        parent_dir = os.path.dirname(expanded)
        basename = os.path.basename(expanded)
        resolved_dir = (
            os.path.abspath(parent_dir) if parent_dir and os.path.isdir(parent_dir) else ""
        )
        return resolved_dir, basename

    if os.path.isdir(expanded):
        return os.path.abspath(expanded), ""
    parent_dir = os.path.dirname(expanded)
    if parent_dir and os.path.isdir(parent_dir):
        return os.path.abspath(parent_dir), ""
    return "", ""


async def _query_portal_file_chooser_version(bus: Any) -> int:
    """Return the ``org.freedesktop.portal.FileChooser.version`` property, or 0 on error."""
    from dbus_next import Message, MessageType

    reply = await asyncio.wait_for(
        bus.call(
            Message(
                destination=_PORTAL_BUS_NAME,
                path=_PORTAL_OBJECT_PATH,
                interface=_DBUS_PROPS_IFACE,
                member="Get",
                signature="ss",
                body=[_PORTAL_FILE_CHOOSER_IFACE, "version"],
            )
        ),
        timeout=3.0,
    )
    if reply is None or reply.message_type == MessageType.ERROR or not reply.body:
        return 0
    val = reply.body[0]
    raw = getattr(val, "value", val)
    return int(raw) if isinstance(raw, int) else 0


async def _call_portal_file_chooser(
    *,
    mode: str,
    caption: str,
    directory: str,
    file_filter: str,
    parent_window: str,
) -> _DialogResult:
    """Invoke ``org.freedesktop.portal.FileChooser`` over the session D-Bus."""
    try:
        from dbus_next import BusType, Message, MessageType, Variant
        from dbus_next.aio import MessageBus
    except Exception as exc:
        _log.debug("dbus_next unavailable for native file picker: %s", exc)
        return _DialogResult(handled=False)

    bus = None
    try:
        bus = await asyncio.wait_for(
            MessageBus(bus_type=BusType.SESSION).connect(),
            timeout=3.0,
        )
    except Exception as exc:
        _log.debug("Session D-Bus unavailable for portal file picker: %s", exc)
        return _DialogResult(handled=False)

    try:
        if mode == "open_dir":
            version = await _query_portal_file_chooser_version(bus)
            if version < 3:
                _log.debug("Portal FileChooser v%s does not support directory selection", version)
                return _DialogResult(handled=False)

        unique_name = (bus.unique_name or "").lstrip(":").replace(".", "_")
        if not unique_name:
            return _DialogResult(handled=False)

        token = f"kikumoe_{uuid.uuid4().hex[:12]}"
        expected_path = f"/org/freedesktop/portal/desktop/request/{unique_name}/{token}"
        valid_paths = {expected_path}

        loop = asyncio.get_running_loop()
        response_future: asyncio.Future[tuple[int, dict[str, Any]]] = loop.create_future()

        def _on_message(msg: Message) -> bool | None:
            if (
                msg.message_type == MessageType.SIGNAL
                and msg.interface == _PORTAL_REQUEST_IFACE
                and msg.member == "Response"
                and msg.path in valid_paths
                and not response_future.done()
            ):
                code = int(msg.body[0]) if msg.body else 2
                results = msg.body[1] if len(msg.body) > 1 and isinstance(msg.body[1], dict) else {}
                response_future.set_result((code, results))
            return None

        bus.add_message_handler(_on_message)

        match_rule = f"type='signal',interface='{_PORTAL_REQUEST_IFACE}',member='Response'"
        add_match_reply = await asyncio.wait_for(
            bus.call(
                Message(
                    destination="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus",
                    interface=_DBUS_IFACE,
                    member="AddMatch",
                    signature="s",
                    body=[match_rule],
                )
            ),
            timeout=3.0,
        )
        if add_match_reply is None or add_match_reply.message_type == MessageType.ERROR:
            return _DialogResult(handled=False)

        options: dict[str, Variant] = {
            "handle_token": Variant("s", token),
            "modal": Variant("b", True),
        }

        if mode == "open_files":
            options["multiple"] = Variant("b", True)
        elif mode == "open_dir":
            options["directory"] = Variant("b", True)

        folder_path, current_name = _resolve_folder_and_name(
            directory, is_save=(mode == "save_file")
        )
        if folder_path:
            options["current_folder"] = Variant("ay", os.fsencode(folder_path) + b"\x00")
        if mode == "save_file" and current_name:
            options["current_name"] = Variant("s", current_name)

        parsed_filters = _parse_qt_filters(file_filter) if mode != "open_dir" else []
        if parsed_filters:
            portal_filters = _format_portal_filters(parsed_filters)
            options["filters"] = Variant("a(sa(us))", portal_filters)
            options["current_filter"] = Variant("(sa(us))", portal_filters[0])

        member = "SaveFile" if mode == "save_file" else "OpenFile"
        reply = await asyncio.wait_for(
            bus.call(
                Message(
                    destination=_PORTAL_BUS_NAME,
                    path=_PORTAL_OBJECT_PATH,
                    interface=_PORTAL_FILE_CHOOSER_IFACE,
                    member=member,
                    signature="ssa{sv}",
                    body=[parent_window, caption or "", options],
                )
            ),
            timeout=5.0,
        )
        if reply is None or reply.message_type == MessageType.ERROR:
            _log.debug(
                "Portal %s returned error: %s",
                member,
                reply.body if reply is not None else None,
            )
            return _DialogResult(handled=False)

        if reply.body and isinstance(reply.body[0], str):
            valid_paths.add(reply.body[0])

        disconnect_task = asyncio.create_task(bus.wait_for_disconnect())
        try:
            done, pending = await asyncio.wait(
                {response_future, disconnect_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
        finally:
            if not disconnect_task.done():
                disconnect_task.cancel()

        if not response_future.done():
            return _DialogResult(handled=False)

        code, results = response_future.result()
        if code == 1:
            return _DialogResult(handled=True, cancelled=True)
        if code != 0:
            _log.debug("Portal %s ended with non-success response code %s", member, code)
            return _DialogResult(handled=False)

        uris_var = results.get("uris")
        raw_uris = getattr(uris_var, "value", uris_var) if uris_var is not None else []
        paths = [
            local_path
            for uri in (raw_uris or [])
            if isinstance(uri, str) and (local_path := _uri_to_local_path(uri))
        ]
        selected_filter = ""
        cur_filter_var = results.get("current_filter")
        cur_filter = getattr(cur_filter_var, "value", cur_filter_var)
        if isinstance(cur_filter, (list, tuple)) and cur_filter:
            selected_filter = str(cur_filter[0])

        return _DialogResult(
            handled=True,
            cancelled=not paths,
            paths=paths,
            selected_filter=selected_filter,
        )
    except Exception as exc:
        _log.debug("Portal file picker failed: %s", exc)
        return _DialogResult(handled=False)
    finally:
        if bus is not None:
            try:
                bus.disconnect()
            except Exception:
                pass


def _run_portal_sync(
    *,
    mode: str,
    caption: str,
    directory: str,
    file_filter: str,
    parent_window: str,
) -> _DialogResult:
    """Run the async D-Bus portal picker in an isolated asyncio loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            _call_portal_file_chooser(
                mode=mode,
                caption=caption,
                directory=directory,
                file_filter=file_filter,
                parent_window=parent_window,
            )
        )
    finally:
        loop.close()


def _is_kde_session() -> bool:
    if os.environ.get("KDE_FULL_SESSION"):
        return True
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    return "kde" in desktop or "plasma" in desktop


def _build_cli_command(
    tool: str,
    *,
    mode: str,
    caption: str,
    directory: str,
    file_filter: str,
) -> list[str]:
    """Build a ``kdialog`` or ``zenity`` command line."""
    folder_path, current_name = _resolve_folder_and_name(directory, is_save=(mode == "save_file"))
    parsed_filters = _parse_qt_filters(file_filter)

    if tool == "kdialog":
        cmd = ["kdialog"]
        if caption:
            cmd.extend(["--title", caption])
        qt_filter = ";;".join(f"{name} ({' '.join(globs)})" for name, globs in parsed_filters)
        if mode == "open_files":
            cmd.extend(
                [
                    "--multiple",
                    "--separate-output",
                    "--getopenfilename",
                    folder_path or os.path.expanduser("~"),
                ]
            )
            if qt_filter:
                cmd.append(qt_filter)
        elif mode == "open_dir":
            cmd.extend(["--getexistingdirectory", folder_path or os.path.expanduser("~")])
        else:
            target = (
                os.path.join(folder_path, current_name)
                if folder_path and current_name
                else (current_name or folder_path or os.path.expanduser("~"))
            )
            cmd.extend(["--getsavefilename", target])
            if qt_filter:
                cmd.append(qt_filter)
        return cmd

    cmd = ["zenity", "--file-selection"]
    if caption:
        cmd.append(f"--title={caption}")
    if mode == "open_files":
        cmd.extend(["--multiple", "--separator=\n"])
        if folder_path:
            cmd.append(f"--filename={folder_path.rstrip(os.sep)}{os.sep}")
    elif mode == "open_dir":
        cmd.append("--directory")
        if folder_path:
            cmd.append(f"--filename={folder_path.rstrip(os.sep)}{os.sep}")
    else:
        cmd.extend(["--save", "--confirm-overwrite"])
        if folder_path and current_name:
            cmd.append(f"--filename={os.path.join(folder_path, current_name)}")
        elif current_name:
            cmd.append(f"--filename={current_name}")
        elif folder_path:
            cmd.append(f"--filename={folder_path.rstrip(os.sep)}{os.sep}")

    if mode != "open_dir":
        for name, globs in parsed_filters:
            cmd.append(f"--file-filter={name} | {' '.join(globs)}")
    return cmd


def _run_cli_picker(
    *,
    mode: str,
    caption: str,
    directory: str,
    file_filter: str,
) -> _DialogResult:
    """Fall back to native ``kdialog`` or ``zenity`` binaries when available."""
    preferred_order = ("kdialog", "zenity") if _is_kde_session() else ("zenity", "kdialog")
    for tool in preferred_order:
        binary = shutil.which(tool)
        if not binary:
            continue
        cmd = _build_cli_command(
            tool,
            mode=mode,
            caption=caption,
            directory=directory,
            file_filter=file_filter,
        )
        cmd[0] = binary
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except Exception as exc:
            _log.debug("%s execution failed: %s", tool, exc)
            continue

        if proc.returncode == 0:
            lines = [line.rstrip("\r") for line in proc.stdout.splitlines() if line.strip()]
            return _DialogResult(handled=True, cancelled=not lines, paths=lines)
        if proc.returncode == 1:
            return _DialogResult(handled=True, cancelled=True)
        _log.debug("%s exited with unexpected code %s: %s", tool, proc.returncode, proc.stderr)
    return _DialogResult(handled=False)


def _run_linux_native_worker(
    *,
    mode: str,
    caption: str,
    directory: str,
    file_filter: str,
    parent_window: str,
) -> _DialogResult:
    """Attempt XDG Desktop Portal first, then native CLI tools (kdialog/zenity)."""
    portal_result = _run_portal_sync(
        mode=mode,
        caption=caption,
        directory=directory,
        file_filter=file_filter,
        parent_window=parent_window,
    )
    if portal_result.handled:
        return portal_result
    return _run_cli_picker(
        mode=mode,
        caption=caption,
        directory=directory,
        file_filter=file_filter,
    )


def _run_blocking(parent: QWidget | None, worker_fn: Callable[[], _DialogResult]) -> _DialogResult:
    """Execute *worker_fn* in a worker thread while keeping Qt responsive."""
    picker_key = id(parent) if parent is not None else 0
    if picker_key in _active_pickers:
        return _DialogResult(handled=True, cancelled=True)

    _active_pickers.add(picker_key)
    app = QApplication.instance()
    blocker: _ModalInputBlocker | None = None
    modal_win = parent.window() if parent is not None else None
    if app is not None and modal_win is not None:
        blocker = _ModalInputBlocker(modal_win)
        app.installEventFilter(blocker)

    loop = QEventLoop()
    bridge = _PickerBridge()
    result_box: list[_DialogResult] = []

    def _on_done(res: object) -> None:
        if isinstance(res, _DialogResult):
            result_box.append(res)
        if loop.isRunning():
            loop.quit()

    bridge.finished.connect(_on_done)
    if parent is not None:
        parent.destroyed.connect(loop.quit)

    def _worker() -> None:
        try:
            res = worker_fn()
        except Exception as exc:
            _log.debug("Native picker worker error: %s", exc)
            res = _DialogResult(handled=False)
        bridge.finished.emit(res)

    thread = threading.Thread(target=_worker, name="KikuMoe-FilePicker", daemon=True)
    thread.start()

    try:
        if not result_box:
            loop.exec()
    finally:
        if parent is not None:
            try:
                parent.destroyed.disconnect(loop.quit)
            except Exception:
                pass
        if blocker is not None and app is not None:
            try:
                app.removeEventFilter(blocker)
            except Exception:
                pass
        _active_pickers.discard(picker_key)
        if thread.is_alive():
            thread.join(timeout=0.5)

    return result_box[0] if result_box else _DialogResult(handled=False)


def get_open_file_names(
    parent: QWidget | None,
    caption: str,
    directory: str = "",
    file_filter: str = "",
) -> tuple[list[str], str]:
    """Select multiple existing files using the OS native dialog when available."""
    if _should_use_linux_native():
        parent_handle = _build_parent_window_handle(parent)
        res = _run_blocking(
            parent,
            lambda: _run_linux_native_worker(
                mode="open_files",
                caption=caption,
                directory=directory,
                file_filter=file_filter,
                parent_window=parent_handle,
            ),
        )
        if res.handled:
            if res.cancelled:
                return [], ""
            return res.paths, res.selected_filter

    return QFileDialog.getOpenFileNames(parent, caption, directory, file_filter)


def get_existing_directory(
    parent: QWidget | None,
    caption: str,
    directory: str = "",
) -> str:
    """Select an existing directory using the OS native dialog when available."""
    if _should_use_linux_native():
        parent_handle = _build_parent_window_handle(parent)
        res = _run_blocking(
            parent,
            lambda: _run_linux_native_worker(
                mode="open_dir",
                caption=caption,
                directory=directory,
                file_filter="",
                parent_window=parent_handle,
            ),
        )
        if res.handled:
            if res.cancelled or not res.paths:
                return ""
            return res.paths[0]

    return QFileDialog.getExistingDirectory(parent, caption, directory)


def get_save_file_name(
    parent: QWidget | None,
    caption: str,
    directory: str = "",
    file_filter: str = "",
) -> tuple[str, str]:
    """Select a save file destination using the OS native dialog when available."""
    if _should_use_linux_native():
        parent_handle = _build_parent_window_handle(parent)
        res = _run_blocking(
            parent,
            lambda: _run_linux_native_worker(
                mode="save_file",
                caption=caption,
                directory=directory,
                file_filter=file_filter,
                parent_window=parent_handle,
            ),
        )
        if res.handled:
            if res.cancelled or not res.paths:
                return "", ""
            return res.paths[0], res.selected_filter

    return QFileDialog.getSaveFileName(parent, caption, directory, file_filter)
