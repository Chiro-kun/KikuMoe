"""Dynamic volume (automatic audio ducking) based on running/active applications."""

from __future__ import annotations

import fnmatch
import os
import re
import sys
from collections.abc import Callable, Sequence

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.constants import DEFAULT_DYNAMIC_VOLUME_LEVEL, DEFAULT_DYNAMIC_VOLUME_MODE

DYNAMIC_MODE_ANY_OPEN = "any_open"
DYNAMIC_MODE_FOREGROUND = "foreground"

_VALID_MODES = (DYNAMIC_MODE_ANY_OPEN, DYNAMIC_MODE_FOREGROUND)

# Background OS / helper executables hidden from the quick-pick menu.
_NOISY_PROCESSES = frozenset(
    {
        "system",
        "system idle process",
        "registry",
        "smss",
        "csrss",
        "wininit",
        "services",
        "lsass",
        "svchost",
        "fontdrvhost",
        "dwm",
        "winlogon",
        "conhost",
        "sihost",
        "taskhostw",
        "ctfmon",
        "runtimebroker",
        "searchhost",
        "searchapp",
        "startmenuexperiencehost",
        "shellexperiencehost",
        "shellhost",
        "lockapp",
        "textinputhost",
        "applicationframehost",
        "dllhost",
        "audiodg",
        "spoolsv",
        "explorer",
        "wmiprvse",
        "aggregatorhost",
        "securityhealthservice",
        "searchindexer",
        "smartscreen",
        "msedgewebview2",
        "crashpad_handler",
        "kikumoe",
    }
)


def normalize_process_name(name: str) -> str:
    """Normalize a process name or executable path for case-insensitive matching."""
    text = str(name or "").strip()
    if not text:
        return ""
    if "/" in text or "\\" in text:
        text = text.replace("\\", "/").rsplit("/", 1)[-1]
    text = text.strip().lower()
    if text.endswith(".exe"):
        text = text[:-4]
    return text


def parse_app_list(raw: str) -> list[str]:
    """Parse a comma/semicolon/newline-separated list of app names, deduplicated."""
    if not raw:
        return []
    tokens = re.split(r"[,;\n\r]+", str(raw))
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        cleaned = token.strip()
        norm = normalize_process_name(cleaned)
        if not cleaned or not norm or norm in seen:
            continue
        seen.add(norm)
        result.append(cleaned)
    return result


def _list_windows_process_names() -> list[str]:
    """Return raw process image names on Windows using Toolhelp32 via ctypes."""
    import ctypes
    from ctypes import wintypes

    th32cs_snapprocess = 0x00000002
    invalid_handle = wintypes.HANDLE(-1).value
    max_path = 260

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * max_path),
        ]

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    snap = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
    if snap == invalid_handle or snap == 0:
        return []

    names: list[str] = []
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(ProcessEntry32W)
        if not kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            return []
        while True:
            exe = str(entry.szExeFile or "").strip()
            if exe:
                names.append(exe)
            if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snap)
    return names


def _query_windows_process_basename(kernel32: object, pid: int) -> str:
    """Return executable basename for a Windows PID using QueryFullProcessImageNameW."""
    import ctypes
    from ctypes import wintypes

    if not pid:
        return ""
    process_query_limited = 0x1000
    handle = kernel32.OpenProcess(process_query_limited, False, pid)  # type: ignore[attr-defined]
    if not handle:
        return ""
    try:
        buf_len = wintypes.DWORD(512)
        buf = ctypes.create_unicode_buffer(buf_len.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(buf_len)):  # type: ignore[attr-defined]
            return os.path.basename(buf.value)
    finally:
        kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
    return ""


def _get_windows_foreground_process() -> str:
    """Return executable basename of the current Windows foreground window."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return _query_windows_process_basename(kernel32, int(pid.value))


def _list_windows_windowed_process_names() -> list[str]:
    """Return executable basenames for visible, non-cloaked top-level Windows app windows."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    dwmapi = getattr(ctypes.windll, "dwmapi", None)  # type: ignore[attr-defined]

    gwl_exstyle = -20
    ws_ex_toolwindow = 0x00000080
    dwmwa_cloaked = 14

    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    win_functype = getattr(ctypes, "WINFUNCTYPE", None)
    if win_functype is None:
        return []
    wnd_enum_proc = win_functype(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    names: list[str] = []

    def _on_window(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindowLongW(hwnd, gwl_exstyle) & ws_ex_toolwindow:
            return True
        if user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        if dwmapi is not None:
            cloaked = wintypes.DWORD(0)
            res = dwmapi.DwmGetWindowAttribute(
                hwnd, dwmwa_cloaked, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
            )
            if res == 0 and cloaked.value != 0:
                return True

        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = _query_windows_process_basename(kernel32, int(pid.value))
        if not exe:
            return True
        if exe.lower() == "applicationframehost.exe":
            child_exes: list[str] = []

            def _on_child(ch_hwnd: int, _ch_lp: int) -> bool:
                ch_pid = wintypes.DWORD(0)
                user32.GetWindowThreadProcessId(ch_hwnd, ctypes.byref(ch_pid))
                ch_exe = _query_windows_process_basename(kernel32, int(ch_pid.value))
                if ch_exe and ch_exe.lower() != "applicationframehost.exe":
                    child_exes.append(ch_exe)
                    return False
                return True

            user32.EnumChildWindows(hwnd, wnd_enum_proc(_on_child), 0)
            names.extend(child_exes)
        else:
            names.append(exe)
        return True

    user32.EnumWindows(wnd_enum_proc(_on_window), 0)
    return names


def _read_linux_proc_name(pid_dir: str) -> str:
    """Return process name for a live /proc/<pid> entry, or '' for zombies/exited tasks."""
    stat_path = os.path.join(pid_dir, "stat")
    try:
        with open(stat_path, encoding="utf-8", errors="ignore") as f:
            stat_line = f.read().strip()
        lparen = stat_line.find("(")
        rparen = stat_line.rfind(")")
        if lparen != -1 and rparen > lparen:
            state = stat_line[rparen + 1 :].lstrip()[:1]
            if state in ("Z", "X"):
                return ""
            return stat_line[lparen + 1 : rparen].strip()
    except OSError:
        pass

    try:
        with open(os.path.join(pid_dir, "comm"), encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except OSError:
        return ""


def _list_linux_process_names() -> list[str]:
    """Return live process names on Linux by inspecting /proc/<pid>/stat (or comm)."""
    names: list[str] = []
    try:
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit() or not entry.is_dir():
                continue
            comm = _read_linux_proc_name(entry.path)
            if comm:
                names.append(comm)
    except OSError:
        return []
    return names


def list_running_process_names() -> set[str]:
    """Return normalized names of currently running processes."""
    try:
        if sys.platform == "win32":
            raw_names = _list_windows_process_names()
        elif sys.platform.startswith("linux"):
            raw_names = _list_linux_process_names()
        else:
            raw_names = []
    except Exception:
        return set()

    result: set[str] = set()
    for raw in raw_names:
        norm = normalize_process_name(raw)
        if norm:
            result.add(norm)
    return result


def get_foreground_process_name() -> str:
    """Return normalized process name of the active foreground window (best-effort)."""
    try:
        if sys.platform == "win32":
            return normalize_process_name(_get_windows_foreground_process())
    except Exception:
        return ""
    return ""


def list_suggested_running_apps(exclude_names: Sequence[str] | None = None) -> list[str]:
    """Return sorted human-friendly open app names suitable for the Settings quick-pick popup."""
    excluded = {
        normalize_process_name(n) for n in (exclude_names or ()) if normalize_process_name(n)
    }
    try:
        if sys.platform == "win32":
            raw_names = _list_windows_windowed_process_names()
        elif sys.platform.startswith("linux"):
            raw_names = _list_linux_process_names()
        else:
            raw_names = []
    except Exception:
        return []

    by_norm: dict[str, str] = {}
    for raw in raw_names:
        norm = normalize_process_name(raw)
        if not norm or norm in _NOISY_PROCESSES or norm in excluded:
            continue
        display = raw[:-4] if raw.lower().endswith(".exe") else raw
        if norm not in by_norm:
            by_norm[norm] = display
    return sorted(by_norm.values(), key=lambda s: s.lower())


def match_dynamic_app(
    configured_apps: Sequence[str],
    mode: str,
    running_apps: set[str],
    foreground_app: str = "",
) -> str | None:
    """Return the first matching configured app label, or None if audio should not duck."""
    if not configured_apps:
        return None
    effective_mode = mode if mode in _VALID_MODES else DYNAMIC_MODE_ANY_OPEN
    norm_fg = normalize_process_name(foreground_app)

    candidates: tuple[str, ...]
    if effective_mode == DYNAMIC_MODE_FOREGROUND:
        candidates = (norm_fg,) if norm_fg else ()
    else:
        candidates = tuple(running_apps)

    if not candidates:
        return None

    for app_label in configured_apps:
        pattern = normalize_process_name(app_label)
        if not pattern:
            continue
        has_wildcard = "*" in pattern or "?" in pattern
        for proc in candidates:
            if not proc:
                continue
            if has_wildcard:
                if fnmatch.fnmatchcase(proc, pattern):
                    return app_label
            elif proc == pattern:
                return app_label
    return None


class DynamicVolumeController(QObject):
    """Monitors running/foreground processes and smoothly ducks volume multiplier."""

    factor_changed = pyqtSignal(float, str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        poll_interval_ms: int = 250,
        ramp_interval_ms: int = 25,
        ramp_steps: int = 8,
        unduck_ramp_steps: int = 40,
        list_processes_fn: Callable[[], set[str]] | None = None,
        foreground_process_fn: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._enabled = False
        self._apps_raw = ""
        self._apps: list[str] = []
        self._duck_level = DEFAULT_DYNAMIC_VOLUME_LEVEL
        self._mode = DEFAULT_DYNAMIC_VOLUME_MODE

        self._current_factor: float = 1.0
        self._target_factor: float = 1.0
        self._active_app: str = ""

        self._poll_interval_ms = max(100, int(poll_interval_ms))
        self._ramp_interval_ms = max(10, int(ramp_interval_ms))
        self._ramp_steps = max(1, int(ramp_steps))
        self._unduck_ramp_steps = max(1, int(unduck_ramp_steps))
        self._ramp_start_factor: float = 1.0
        self._ramp_step_index: int = 0
        self._ramp_total_steps: int = self._ramp_steps
        self._ramp_is_unduck: bool = False

        self._list_processes = list_processes_fn or list_running_process_names
        self._foreground_process = foreground_process_fn or get_foreground_process_name

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._poll_interval_ms)
        self._poll_timer.timeout.connect(self.evaluate_now)

        self._ramp_timer = QTimer(self)
        self._ramp_timer.setInterval(self._ramp_interval_ms)
        self._ramp_timer.timeout.connect(self._on_ramp_tick)

    def _sync_poll_timer(self) -> None:
        """Keep the shared duck/unduck poll timer running only when active."""
        if self._enabled and self._apps:
            if not self._poll_timer.isActive():
                self._poll_timer.start()
        elif self._poll_timer.isActive():
            self._poll_timer.stop()

    def configure(
        self,
        enabled: bool,
        apps_raw: str,
        level_percent: int,
        mode: str = DYNAMIC_MODE_ANY_OPEN,
    ) -> None:
        """Update ducking configuration and re-evaluate immediately."""
        self._enabled = bool(enabled)
        self._apps_raw = str(apps_raw or "")
        self._apps = parse_app_list(self._apps_raw)
        try:
            lvl = int(level_percent)
        except (TypeError, ValueError):
            lvl = DEFAULT_DYNAMIC_VOLUME_LEVEL
        self._duck_level = max(5, min(90, lvl))
        self._mode = mode if mode in _VALID_MODES else DYNAMIC_MODE_ANY_OPEN

        self._sync_poll_timer()
        self.evaluate_now()

    def start(self) -> None:
        """Start monitoring if enabled."""
        self._sync_poll_timer()
        self.evaluate_now()

    def stop(self) -> None:
        """Stop all internal timers (used on application shutdown)."""
        if self._poll_timer.isActive():
            self._poll_timer.stop()
        if self._ramp_timer.isActive():
            self._ramp_timer.stop()

    def current_factor(self) -> float:
        return self._current_factor

    def target_factor(self) -> float:
        return self._target_factor

    def active_app(self) -> str:
        return self._active_app

    def is_ducked(self) -> bool:
        return bool(self._active_app) and self._target_factor < 0.999

    def evaluate_now(self) -> None:
        """Inspect running/active apps once and update target volume multiplier."""
        matched_app: str | None = None
        if self._enabled and self._apps:
            try:
                if self._mode == DYNAMIC_MODE_FOREGROUND:
                    fg = self._foreground_process()
                    matched_app = match_dynamic_app(self._apps, self._mode, set(), fg)
                else:
                    running = self._list_processes()
                    matched_app = match_dynamic_app(self._apps, self._mode, running, "")
            except Exception:
                matched_app = None

        new_target = (self._duck_level / 100.0) if matched_app else 1.0
        new_app = matched_app or ""

        target_changed = abs(new_target - self._target_factor) > 1e-4
        app_changed = new_app != self._active_app
        self._target_factor = new_target
        self._active_app = new_app

        if target_changed:
            self._ramp_start_factor = self._current_factor
            self._ramp_step_index = 0
            self._ramp_is_unduck = self._target_factor > self._current_factor
            self._ramp_total_steps = (
                self._unduck_ramp_steps if self._ramp_is_unduck else self._ramp_steps
            )
            if not self._ramp_timer.isActive():
                self._ramp_timer.start()
            # Perform first step right away so fast callers/tests feel responsive.
            self._on_ramp_tick()
        elif app_changed:
            self.factor_changed.emit(self._current_factor, self._active_app)

    def _on_ramp_tick(self) -> None:
        self._ramp_step_index += 1
        total = max(1, self._ramp_total_steps)
        if (
            self._ramp_step_index >= total
            or abs(self._target_factor - self._current_factor) <= 1e-4
        ):
            self._current_factor = self._target_factor
            if self._ramp_timer.isActive():
                self._ramp_timer.stop()
        else:
            t = self._ramp_step_index / float(total)
            # Smoothstep ease when restoring volume so unducking swells gently without blasting.
            eased = t * t * (3.0 - 2.0 * t) if self._ramp_is_unduck else t
            span = self._target_factor - self._ramp_start_factor
            next_factor = self._ramp_start_factor + span * eased
            if self._ramp_is_unduck:
                self._current_factor = min(self._target_factor, next_factor)
            else:
                self._current_factor = max(self._target_factor, next_factor)

        self.factor_changed.emit(self._current_factor, self._active_app)
