# Application constants and settings keys
import os
import re
import sys

APP_NAME = "KikuMoe"


def _get_project_root() -> str:
    try:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    except Exception:
        return os.getcwd()


def _read_version_from_files() -> str:
    # 1) Try version.yml (simple to parse without YAML dep)
    try:
        root = _get_project_root()
        search_paths = [
            os.path.join(root, "version.yml"),
            os.path.join(os.path.dirname(__file__), "version.yml"),
        ]
        try:
            if getattr(sys, "frozen", False):
                meipass = getattr(sys, "_MEIPASS", None)
                if meipass:
                    search_paths.insert(0, os.path.join(meipass, "version.yml"))
        except Exception:
            pass
        for path in search_paths:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().lower().startswith("version:"):
                            ver = line.split(":", 1)[1].strip()
                            if ver:
                                return ver
    except Exception:
        pass

    # 2) Try version_info.txt (parse FileVersion or filevers tuple)
    try:
        root = _get_project_root()
        candidate_paths = [
            os.path.join(root, "version_info.txt"),
        ]
        try:
            if getattr(sys, "frozen", False):
                meipass = getattr(sys, "_MEIPASS", None)
                if meipass:
                    candidate_paths.insert(0, os.path.join(meipass, "version_info.txt"))
        except Exception:
            pass
        data = ""
        for path in candidate_paths:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = f.read()
                break
        if data:
            # Prefer StringStruct 'FileVersion', e.g. 1.8.3.0
            m = re.search(r"FileVersion\'\s*,\s*u?\'([^\']+)\'", data)
            if m:
                return m.group(1).strip()
            # Fallback to filevers=(1,8,3,0)
            m2 = re.search(r"filevers=\((\d+),(\d+),(\d+),(\d+)\)", data)
            if m2:
                return ".".join(m2.groups())
    except Exception:
        pass

    # 3) Fallback to default
    return "1.8"


APP_VERSION = _read_version_from_files()
APP_TITLE = f"{APP_NAME} {APP_VERSION}"

# QSettings scope
ORG_NAME = "KikuMoe"
APP_SETTINGS = "ListenMoePlayer"

# Settings keys
KEY_LANG = "lang"
KEY_VOLUME = "volume"
KEY_MUTE = "mute"
KEY_CHANNEL = "channel"
KEY_FORMAT = "format"
KEY_AUTOPLAY = "autoplay"
KEY_TRAY_ENABLED = "tray_enabled"
KEY_TRAY_NOTIFICATIONS = "tray_notifications"
KEY_TRAY_HIDE_ON_MINIMIZE = "tray_hide_on_minimize"
KEY_LIBVLC_PATH = "libvlc_path"
KEY_WINDOW_GEOMETRY = "window_geometry"
KEY_NETWORK_CACHING = "network_caching"
# New settings keys
KEY_DARK_MODE = "dark_mode"
KEY_SLEEP_MINUTES = "sleep_minutes"
KEY_SLEEP_STOP_ON_END = "sleep_stop_on_end"
KEY_DEV_CONSOLE_ENABLED = "dev_console_enabled"
KEY_SESSION_TIMER_ENABLED = "session_timer_enabled"
# Audio output selection
KEY_AUDIO_DEVICE_INDEX = "audio_device_index"
# New: Dev console option to show [DEV] tagged messages
KEY_DEV_CONSOLE_SHOW_DEV = "dev_console_show_dev"