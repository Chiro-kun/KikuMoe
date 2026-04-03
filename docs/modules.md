# Module reference

## core/

### `constants.py`

Global app constants and `QSettings` keys. Single source of truth for setting names.

```python
APP_NAME     = "KikuMoe"
APP_VERSION  = _read_version_from_files()   # from version.yml or version_info.txt
APP_TITLE    = f"{APP_NAME} {APP_VERSION}"
ORG_NAME     = "KikuMoe"
APP_SETTINGS = "ListenMoePlayer"

KEY_LANG                  = "lang"
KEY_VOLUME                = "volume"
KEY_MUTE                  = "mute"
KEY_CHANNEL               = "channel"
KEY_FORMAT                = "format"
KEY_AUTOPLAY              = "autoplay"
KEY_TRAY_ENABLED          = "tray_enabled"
KEY_TRAY_NOTIFICATIONS    = "tray_notifications"
KEY_TRAY_HIDE_ON_MINIMIZE = "tray_hide_on_minimize"
KEY_LIBVLC_PATH           = "libvlc_path"
KEY_NETWORK_CACHING       = "network_caching"
KEY_SLEEP_MINUTES         = "sleep_minutes"
KEY_SLEEP_STOP_ON_END     = "sleep_stop_on_end"
KEY_DEV_CONSOLE_ENABLED   = "dev_console_enabled"
KEY_DEV_CONSOLE_SHOW_DEV  = "dev_console_show_dev"
KEY_SESSION_TIMER_ENABLED = "session_timer_enabled"
KEY_AUDIO_DEVICE_INDEX    = "audio_device_index"
KEY_WINDOW_GEOMETRY       = "window_geometry"
KEY_DONT_ASK_ON_CLOSE     = "dont_ask_on_close"
KEY_CLOSE_TO_TRAY         = "close_to_tray"
KEY_AUDIO_BACKEND         = "audio_backend"   # 'auto' | 'ffmpeg' | 'mpv' | 'vlc'
```

Version is resolved in order from:
1. `version.yml` (key `version:`) at the repo root or inside `_MEIPASS` (onefile)
2. `packaging/windows/version_info.txt` (`FileVersion` field or `filevers` tuple)
3. Hardcoded fallback `"1.10.0"`

---

### `config.py`

Stream URL dictionary. Single source of truth for LISTEN.moe endpoints.

```python
STREAMS = {
    "J-POP": {
        "Vorbis": "https://listen.moe/stream",
        "Opus":   "https://listen.moe/opus",
        "MP3":    "https://listen.moe/fallback",
    },
    "K-POP": {
        "Vorbis": "https://listen.moe/kpop/stream",
        "Opus":   "https://listen.moe/kpop/opus",
        "MP3":    "https://listen.moe/kpop/fallback",
    },
}
```

Adding a channel only requires extending this dict; the UI reads it dynamically.

---

### `i18n.py`

`I18n` class for IT/EN translation management.

```python
from core.i18n import I18n

i18n = I18n(lang="it")             # or "en"
label = i18n.t("status_playing")   # returns string in the current language
i18n.set_lang("en")                # switch language at runtime
```

- Missing key in selected language → falls back to Italian.
- Missing key in all languages → returns the key itself.

A runtime language switch calls `retranslateUi()` on the main window without restarting.

---

### `logger.py`

```python
from core.logger import get_logger, silence_stderr, set_debug

log = get_logger(__name__)
log.debug("verbose trace")   # suppressed by default
log.info("backend selected") # always visible
```

- `get_logger(name)` — returns a `logging.Logger` writing to `stdout`. Default level is `INFO`; `DEBUG` traces are hidden unless the app is started with `--debug`.
- `set_debug(enabled)` — switches all created loggers between `DEBUG` and `INFO`. Called once at startup by `KikuMoe.py` when `--debug` is detected.
- `silence_stderr()` — context manager that redirects C-level fd 2 to `/dev/null` for the duration of the block. Used around `PyAudio()` and `vlc.Instance()` to suppress ALSA/JACK/libVLC probe noise. **No-op when debug mode is active** so `--debug` exposes those messages too.

On Windows, `stdout` is wrapped in `_SafeTextStream` to prevent `UnicodeEncodeError` with codepage cp1252.

---

### `now_playing.py`

Time formatting utilities:

- `compute_remaining(duration_seconds, start_epoch)` → remaining seconds (`int | None`); returns `None` if either argument is `None`
- `compute_display_mmss(duration_seconds, start_epoch)` → `tuple[str, bool]` where the string is `"mm:ss"` and the bool is `True` when the value is remaining time, `False` when it falls back to total duration (or `"--:--"` if neither is available)

---

## audio/

All backends expose the same callback interface, letting the main window treat them interchangeably.

### Common interface

```python
player.is_ready()             -> bool   # False if the required library is missing
player.play_url(url: str)     -> bool   # True on success
player.pause_toggle()         -> None   # toggles pause/resume
player.stop()                 -> None
player.force_cleanup()        -> None   # emergency teardown
player.set_volume(vol: int)   -> None   # 0–100
player.set_mute(mute: bool)   -> None
player.get_volume()           -> int
player.get_mute()             -> bool
```

Callback set by `main_window.py`:

```python
player.on_event = fn   # fn(event: str, data=None)
```

Emitted events: `"opening"`, `"buffering"`, `"playing"`, `"paused"`, `"stopped"`, `"ended"`, `"error"`.

---

### `player_ffmpeg.py`

Primary backend. Launches FFmpeg as a subprocess and writes PCM output to a PyAudio device.

- `subprocess.Popen(stdout=PIPE)`; a reader thread consumes PCM chunks.
- `_playback_lock` (RLock) protects shared state across threads.
- `User-Agent` header: `KikuMoe/<version>`.
- URL is sanitized before being passed to FFmpeg.
- Device selection via `pa.open(output_device_index=...)`.

---

### `player_mpv.py`

Second fallback backend via `python-mpv` bindings (wraps libmpv).

- No video output (`--vid=no`), audio-only mode.
- `User-Agent` set via MPV option at initialization.
- Events via `@player.event_callback`: `start-file` → `opening`, `file-loaded` → `playing`, `end-file` → `ended`/`error`.
- Cache buffering progress via `@player.property_observer('cache-buffering-state')`.
- If libmpv is not found at startup, `is_ready()` returns `False` and the main window falls through to VLC.

---

### `player_vlc.py`

Last fallback backend via `python-vlc` bindings.

- VLC instance options: `--network-caching`, `--http-reconnect`, `--quiet`.
- Custom VLC library path via `KEY_LIBVLC_PATH`: on Windows, adds the directory via `os.add_dll_directory`; on Linux, sets `VLC_PLUGIN_PATH` to the `plugins/` subdirectory.
- If libVLC is not found at startup, the error is caught by the main window and the backend is marked unavailable.

---

## network/

### `ws_client.py` — `NowPlayingWS`

Manages the WebSocket connection to the LISTEN.moe gateway (`wss://listen.moe/gateway_v2`).

**Gateway v2 protocol:**

| Sent message | Purpose |
|---|---|
| `{"op": 2}` | Initial acknowledgement (sent on open and on welcome) |
| `{"op": 9}` | Periodic heartbeat (sent at the interval received in the welcome message) |

| Received event (`op`) | Meaning |
|---|---|
| `0` | Welcome — contains `d.heartbeat` interval in ms |
| `1` | Dispatch — `TRACK_UPDATE` / `TRACK_UPDATE_REQUEST`: current track metadata |

`TRACK_UPDATE` payload: `song.title`, `song.artists[].name`, `song.duration` (s), `song.albums[].image` (relative filename, CDN base: `https://cdn.listen.moe/covers/`), `startTime` (ISO 8601).

Channel filtering is applied client-side via the `channel_filter` callback passed to the constructor. Auto-reconnects with a 5 s delay on socket close.

```python
ws = NowPlayingWS(
    on_now_playing=fn,       # fn(title, artist, duration_s, start_epoch, cover_filename)
    on_error_text=fn,        # fn(msg: str)
    on_closed_text=fn,       # fn(msg: str)
    channel_filter=fn,       # optional fn(d: dict) -> bool
)
ws.start()
ws.shutdown()
```

---

## ui/

### `main_window.py` — `ListenMoePlayer`

Main class (`QWidget`) that coordinates all other components.

**Qt signals:**

```python
status_changed        = pyqtSignal(str)
now_playing_changed   = pyqtSignal(str, str)   # title, artist
buffering_progress    = pyqtSignal(int)
cover_data_ready      = pyqtSignal(bytes)
ws_error              = pyqtSignal(str)
ws_closed             = pyqtSignal(str)
```

Signals are the only safe channel for updating the UI from non-main threads.

**Custom widget:** `SmoothProgressBar(QProgressBar)` — rounded corners, custom colors.

**Backend initialization:** `_create_player()` tries backends in order — `PlayerFFmpeg` → `PlayerMPV` → `PlayerVLC` — stopping at the first one whose `is_ready()` returns `True`. Manual selection via `KEY_AUDIO_BACKEND` bypasses the chain. Active backend stored in `self.player`.

---

### `settings_dialog.py`

Non-modal window. Reads and writes directly to `QSettings`. On close, emits `settings_changed`, triggering re-initialization of dependent components (language, audio device, backend).

---

### `tray_manager.py`

Manages `QSystemTrayIcon` and its `QMenu`. The menu is built dynamically on each open to reflect current state. Includes:
- **Custom Styling**: Dark mode applied via inline QSS (Qt Style Sheets) with magenta accents.
- **Screen Awareness**: Logic to "nudge" the menu and submenus to the left if they would overflow the right edge of the screen (typically when the tray is on the right).

---

### `dev_console.py`

Optional window that captures logs from the root logger and displays them in a thread-safe `QTextEdit` via Qt signal.

```python
from ui.dev_console import DevConsole
console = DevConsole(parent=main_window)
console.attach()   # installs the QHandler into the root logger
console.show()
```

---

### `windows_titlebar.py`

```python
from ui.windows_titlebar import apply_windows_titlebar_dark_mode
apply_windows_titlebar_dark_mode(hwnd)
```

Calls `DwmSetWindowAttribute(DWMWA_USE_IMMERSIVE_DARK_MODE)` via `ctypes`. No-op on non-Windows platforms.
