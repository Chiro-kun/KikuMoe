# Application constants and settings keys
import os
import re
import sys

APP_NAME = "KikuMoe"


def _get_project_root() -> str:
    try:
        start = os.path.abspath(os.path.dirname(__file__))
        cur = start
        for _ in range(5):
            if os.path.isfile(os.path.join(cur, "version.yml")):
                return cur
            if os.path.isfile(os.path.join(cur, "packaging", "windows", "version_info.txt")):
                return cur
            parent = os.path.abspath(os.path.join(cur, os.pardir))
            if parent == cur:
                break
            cur = parent
        return os.path.abspath(os.path.join(start, os.pardir, os.pardir))
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
                with open(path, encoding="utf-8") as f:
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
            os.path.join(root, "packaging", "windows", "version_info.txt"),
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
                with open(path, encoding="utf-8") as f:
                    data = f.read()
                break
        if data:
            # Prefer StringStruct 'FileVersion', e.g. 1.11.0.0
            m = re.search(r"FileVersion\'\s*,\s*u?\'([^\']+)\'", data)
            if m:
                return m.group(1).strip()
            # Fallback to filevers=(1,9,0,0)
            m2 = re.search(r"filevers=\((\d+),(\d+),(\d+),(\d+)\)", data)
            if m2:
                return ".".join(m2.groups())
    except Exception:
        pass

    # 3) Fallback to default
    return "2.0.0-beta3"


APP_VERSION = _read_version_from_files()
APP_TITLE = f"{APP_NAME} {APP_VERSION}"

# Project metadata & links
AUTHORS = "Chirokun & alsogamer"
URL_FORGEJO = "https://git.alsogamer.com/chiro/KikuMoe"
URL_GITHUB = "https://github.com/Chiro-kun/KikuMoe"
URL_TELEGRAM = "https://t.me/Chiro_kun"
URL_LISTENMOE = "https://listen.moe"
URL_GENSOKYO = "https://gensokyoradio.net/"
URL_ANISON = "https://en.anison.fm/"
URL_NEURO21 = "https://radio.twinskaraoke.com/"
URL_TRUCKERSFM = "https://truckers.fm/"
LICENSE_NAME = "MIT License"

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
KEY_DISCORD_RPC_ENABLED = "discord_rpc_enabled"
KEY_DISCORD_CLIENT_ID = "discord_client_id"
DEFAULT_DISCORD_CLIENT_ID = "484517809179852800"
KEY_TRAY_ENABLED = "tray_enabled"
KEY_TRAY_NOTIFICATIONS = "tray_notifications"
KEY_TRAY_HIDE_ON_MINIMIZE = "tray_hide_on_minimize"
KEY_LIBVLC_PATH = "libvlc_path"
KEY_WINDOW_GEOMETRY = "window_geometry"
KEY_MINI_GEOMETRY = "mini_geometry"
KEY_MINI_ALWAYS_ON_TOP = "mini_always_on_top"
KEY_NETWORK_CACHING = "network_caching"
# New settings keys
KEY_SLEEP_MINUTES = "sleep_minutes"
KEY_SLEEP_STOP_ON_END = "sleep_stop_on_end"
KEY_DEV_CONSOLE_ENABLED = "dev_console_enabled"
KEY_SESSION_TIMER_ENABLED = "session_timer_enabled"
# Audio output selection
KEY_AUDIO_DEVICE_INDEX = "audio_device_index"
# Close behavior keys
KEY_DONT_ASK_ON_CLOSE = "dont_ask_on_close"
KEY_CLOSE_TO_TRAY = "close_to_tray"
# New: Dev console option to show [DEV] tagged messages
KEY_DEV_CONSOLE_SHOW_DEV = "dev_console_show_dev"
# Audio backend selection: 'auto' | 'ffmpeg' | 'mpv' | 'vlc'
KEY_AUDIO_BACKEND = "audio_backend"
# Radio station selection & provider identifiers
KEY_STATION = "station"
STATION_LISTENMOE = "listenmoe"
STATION_GENSOKYO = "gensokyo"
STATION_ANISON = "anison"
STATION_NEURO21 = "neuro21"
STATION_TRUCKERSFM = "truckersfm"
DEFAULT_STATION = STATION_LISTENMOE

# Theme & Custom Accent Engine (Phase 8)
KEY_THEME = "theme"
KEY_CUSTOM_ACCENT_ENABLED = "custom_accent_enabled"
KEY_CUSTOM_ACCENT = "custom_accent"
KEY_CUSTOM_ACCENT_PALETTE = "custom_accent_palette"
THEME_CYBER_MOE = "cyber_moe"
THEME_MIDNIGHT_AMOLED = "midnight_amoled"
THEME_SAKURA_BLOOM = "sakura_bloom"
THEME_NEON_MATRIX = "neon_matrix"
THEME_OCEAN_CYAN = "ocean_cyan"
DEFAULT_THEME = THEME_CYBER_MOE
DEFAULT_ACCENT_COLOR = "#ec186c"

# Audio visualizer (Radial Halo)
KEY_VISUALIZER_ENABLED = "visualizer_enabled"
DEFAULT_VISUALIZER_ENABLED = True
