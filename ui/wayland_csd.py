"""Wayland client-side decoration support (Qt6).

On Wayland compositors that do not implement the xdg-decoration-unstable-v1
protocol (server-side decorations), Qt may render the application window
without a title bar or window management buttons.

This module provides configure_wayland_csd(), which must be called BEFORE
QApplication is instantiated.  It selects a CSD plugin for Qt's Wayland
backend so that the window always shows minimize / maximize / close buttons
even when the compositor provides no server-side decorations.
"""

from __future__ import annotations

import os
import sys

_IS_LINUX = sys.platform.startswith("linux")


def _is_wayland_session() -> bool:
    """Return True when the process is running inside a Wayland session."""
    if not _IS_LINUX:
        return False
    return bool(os.environ.get("WAYLAND_DISPLAY")) or (
        os.environ.get("XDG_SESSION_TYPE") == "wayland"
    )


def configure_wayland_csd() -> None:
    """Configure client-side decorations for Wayland sessions.

    Sets QT_WAYLAND_DECORATION when not already set by the user, instructing
    Qt's Wayland backend to use a CSD plugin as fallback for compositors that
    do not advertise server-side decoration support
    (i.e. zxdg_decoration_manager_v1 is absent).

    The "adwaita" plugin (shipped with qt6-wayland on most distributions)
    produces GNOME/Adwaita-style decorations.  If the plugin is not installed,
    Qt silently falls back to its own built-in generic CSD, so window
    management buttons are always visible.

    Must be called BEFORE QApplication is instantiated.
    """
    if not _is_wayland_session():
        return
    if "QT_WAYLAND_DECORATION" not in os.environ:
        os.environ["QT_WAYLAND_DECORATION"] = "adwaita"
