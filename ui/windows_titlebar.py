from __future__ import annotations
import sys
from typing import Any, Optional

_IS_WIN32 = sys.platform == "win32"


def apply_windows_titlebar_dark_mode(target: Any, enable: bool) -> None:
    """Enable/disable immersive dark mode on a window title bar (Windows only)."""
    try:
        if not _IS_WIN32:
            return

        hwnd: Optional[int] = None
        try:
            if isinstance(target, int):
                hwnd = int(target)
            elif target is not None and hasattr(target, "winId"):
                hwnd = int(target.winId())
        except Exception:
            hwnd = None

        if not hwnd:
            return

        import ctypes
        value = ctypes.c_int(1 if enable else 0)

        for attr in (20, 19):
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
                )
            except Exception:
                pass
    except Exception:
        pass

