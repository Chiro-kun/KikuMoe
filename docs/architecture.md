# Architecture

## Tech stack

| Component | Technology |
|---|---|
| Language | Python 3.8+ |
| GUI | PyQt6 (Qt6) — Wayland-first on Linux, XCB (X11) fallback |
| Window decorations | Custom CSD (`CustomTitleBar`) — frameless window, works on Wayland, X11, Windows |
| Audio | FFmpeg + PyAudio/PortAudio → PipeWire · PulseAudio · ALSA (Linux), WASAPI/MME (Windows); MPV and VLC as fallbacks |
| Metadata | WebSocket (`websocket-client`) → `wss://listen.moe/gateway_v2` |
| Settings persistence | `QSettings` (Windows registry, INI file on Linux) |
| Build / packaging | PyInstaller (onefile) — Windows and Linux |

---

## Project structure

```
KikuMoe/                     # Repository root
├── KikuMoe.py               # Application entry point
├── build.ps1                # Windows build script (PowerShell)
├── build.sh                 # Linux build script (Bash)
├── kikumoe.spec             # PyInstaller configuration (cross-platform)
├── pyi_rthook_vlc.py        # VLC runtime hook for PyInstaller
├── install-ffmpeg.bat       # FFmpeg installer script for Windows
├── version.yml              # Current application version
├── LICENSE
├── README.md                # User documentation
├── DEVELOPER.md             # Developer documentation index
│
├── core/                    # Shared modules — no UI dependencies
│   ├── config.py            # Stream URLs (STREAMS dict)
│   ├── constants.py         # App constants, QSettings keys, version reader
│   ├── i18n.py              # IT/EN strings and I18n class
│   ├── logger.py            # get_logger() and _SafeTextStream
│   └── now_playing.py       # Time formatting utilities (mm:ss, remaining)
│
├── audio/                   # Swappable audio backends
│   ├── player_ffmpeg.py     # FFmpeg backend (subprocess + PyAudio)
│   ├── player_mpv.py        # MPV backend (python-mpv / libmpv bindings)
│   └── player_vlc.py        # VLC backend (python-vlc bindings)
│
├── network/                 # Network client
│   └── ws_client.py         # NowPlayingWS: LISTEN.moe Gateway v2 WebSocket
│
├── ui/                      # PyQt6 GUI
│   ├── main_window.py       # ListenMoePlayer (main window)
│   ├── settings_dialog.py   # Settings window
│   ├── tray_manager.py      # System tray icon and menu
│   ├── dev_console.py       # Developer console (log viewer)
│   ├── windows_titlebar.py  # Dark mode DWM attribute for Windows
│   └── custom_titlebar.py   # CustomTitleBar: cross-platform CSD widget
│
├── icons/                   # Graphic assets (PNG, ICO)
└── docs/                    # Developer documentation
```

> The code is not structured as an installable package. All imports use paths relative to `KikuMoe/` as the working directory.

---

## Layers and dependencies

Dependencies always flow downward. `core/` never imports from `ui/`, `audio/`, or `network/`.

```
┌──────────────────────────────────────────────┐
│               UI Layer (ui/)                 │
│  ListenMoePlayer · TrayManager               │
│  SettingsDialog  · DevConsole                │
└────────────┬─────────────────────────────────┘
             │  Qt signals/slots (thread-safe)
┌────────────▼─────────────────────────────────┐
│           Audio Layer (audio/)               │
│  PlayerFFmpeg (primary)                      │
│  PlayerMPV    (second fallback)              │
│  PlayerVLC    (last fallback)                │
└────────────┬─────────────────────────────────┘
             │  callback on_player_event()
┌────────────▼─────────────────────────────────┐
│          Network Layer (network/)            │
│  NowPlayingWS (WebSocket daemon thread)      │
└────────────┬─────────────────────────────────┘
             │  callback on_now_playing()
┌────────────▼─────────────────────────────────┐
│            Core Layer (core/)                │
│  Constants · Config · I18n · Logger · Utils  │
└──────────────────────────────────────────────┘
```

---

## Thread model

| Thread | Responsibility |
|---|---|
| Main (Qt event loop) | UI rendering, user event handling |
| Player thread | FFmpeg subprocess / MPV event loop / VLC instance |
| WebSocket thread | Daemon connection to `gateway_v2` |
| Cover thread | Background album art download |

Synchronization uses an `RLock` inside the player and Qt signals for marshaling back to the main thread. Never call Qt methods directly from secondary threads.

---

## Data flow

### Starting playback

```
1.  User → clicks Play
2.  ListenMoePlayer._play_stream()
3.  Selects URL from STREAMS[channel][format] (Vorbis, Opus, or MP3)
4.  player.play_url(url)
5.  Backend starts FFmpeg / MPV / VLC
6.  Callback on_event("opening")       → status_changed.emit("Opening…")
7.  Callback on_event("buffering", pct) → buffering_progress.emit(pct)
8.  Callback on_event("playing")       → UI updated
9.  [concurrent] NowPlayingWS receives TRACK_UPDATE
10. on_now_playing(title, artist, duration, cover_url, start_epoch)
11. now_playing_changed.emit(title, artist)
12. Background thread downloads cover  → cover_data_ready.emit(bytes)
13. UI slot updates label + album art
```

### Changing channel / format / language

1. The current stream is stopped.
2. Affected components are re-initialized (i18n, backend, WS channel).
3. If `autoplay` is enabled, playback restarts automatically.
