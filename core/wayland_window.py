"""Wayland compositor detection and native IPC helpers for floating/pinning Mini-HUD."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from PyQt6.QtGui import QGuiApplication

_IPC_TIMEOUT_SEC = 1.5
_COMPOSITOR_BINS: dict[str, str] = {
    "niri": "niri",
    "hyprland": "hyprctl",
    "sway": "swaymsg",
}


def is_wayland_session(platform_name: str | None = None) -> bool:
    """Return True when Qt is actively running on the Wayland QPA platform."""
    if platform_name is None:
        app = QGuiApplication.instance()
        platform_name = QGuiApplication.platformName() if isinstance(app, QGuiApplication) else ""
    return str(platform_name or "").strip().lower().startswith("wayland")


def detect_wayland_compositor() -> str:
    """Identify the active Wayland compositor from standard session environment variables."""
    if os.environ.get("NIRI_SOCKET"):
        return "niri"
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"
    if os.environ.get("SWAYSOCK"):
        return "sway"
    return "other"


def supports_wayland_pin(compositor: str | None = None) -> bool:
    """Return True when the active Wayland compositor supports IPC floating/pin control."""
    comp = compositor if compositor is not None else detect_wayland_compositor()
    binary = _COMPOSITOR_BINS.get(comp)
    if not binary:
        return False
    return shutil.which(binary) is not None


def _run_ipc_cmd(args: list[str], capture: bool = False) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args,
            capture_output=capture,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=_IPC_TIMEOUT_SEC,
            check=False,
        )
    except Exception:
        return None


def _apply_niri_pin(enabled: bool, window_title: str) -> bool:
    """Move KikuMoe's focused Mini-HUD window between niri's floating and tiling layers."""
    is_floating: bool | None = None
    query = _run_ipc_cmd(["niri", "msg", "-j", "focused-window"], capture=True)
    if query is not None and query.returncode == 0 and query.stdout:
        try:
            info: Any = json.loads(query.stdout)
            if isinstance(info, dict):
                title = str(info.get("title") or "")
                app_id = str(info.get("app_id") or "").lower()
                # Avoid moving an unrelated window if focus has already left KikuMoe
                if title and title != window_title and "kikumoe" not in app_id:
                    return False
                if isinstance(info.get("is_floating"), bool):
                    is_floating = info["is_floating"]
        except Exception:
            pass

    if is_floating is not None and is_floating == enabled:
        return True

    action = "move-window-to-floating" if enabled else "move-window-to-tiling"
    res = _run_ipc_cmd(["niri", "msg", "action", action])
    if res is not None and res.returncode == 0:
        return True

    # Fallback for older niri versions that only expose toggle-window-floating
    if is_floating is None or is_floating != enabled:
        fb = _run_ipc_cmd(["niri", "msg", "action", "toggle-window-floating"])
        return bool(fb is not None and fb.returncode == 0)
    return False


def _apply_hyprland_pin(enabled: bool) -> bool:
    """Idempotently pin or unpin the active Mini-HUD window in Hyprland."""
    is_floating: bool | None = None
    is_pinned: bool | None = None
    query = _run_ipc_cmd(["hyprctl", "activewindow", "-j"], capture=True)
    if query is not None and query.returncode == 0 and query.stdout:
        try:
            info: Any = json.loads(query.stdout)
            if isinstance(info, dict):
                if isinstance(info.get("floating"), bool):
                    is_floating = info["floating"]
                if isinstance(info.get("pinned"), bool):
                    is_pinned = info["pinned"]
        except Exception:
            pass

    if enabled:
        if is_floating is not True:
            _run_ipc_cmd(["hyprctl", "dispatch", "setfloating", "active"])
        if is_pinned is True:
            return True
        res = _run_ipc_cmd(["hyprctl", "dispatch", "pin", "active"])
        return bool(res is not None and res.returncode == 0)

    if is_pinned is False:
        return True
    res = _run_ipc_cmd(["hyprctl", "dispatch", "pin", "active"])
    return bool(res is not None and res.returncode == 0)


def _apply_sway_pin(enabled: bool) -> bool:
    """Enable or disable sticky floating mode in Sway."""
    cmd = "floating enable; sticky enable" if enabled else "sticky disable"
    res = _run_ipc_cmd(["swaymsg", cmd])
    return bool(res is not None and res.returncode == 0)


def apply_wayland_pin(
    enabled: bool,
    window_title: str = "KikuMoe Mini-HUD",
    compositor: str | None = None,
) -> bool:
    """Apply compositor-native floating/pinning on supported Wayland compositors."""
    comp = compositor if compositor is not None else detect_wayland_compositor()
    if comp == "niri":
        return _apply_niri_pin(bool(enabled), window_title)
    if comp == "hyprland":
        return _apply_hyprland_pin(bool(enabled))
    if comp == "sway":
        return _apply_sway_pin(bool(enabled))
    return False
