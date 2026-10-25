# Changelog

All notable changes to KikuMoe will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0-beta2] - 2026-10-23

### Added
- **Linux Audio Startup Diagnostics**: Automated probing of active sound daemons (PipeWire socket, PulseAudio server, ALSA) and audio backend readiness (FFmpeg binary, PortAudio host APIs, MPV, VLC) logged on startup and inspectable in the Developer Console.
- **Standalone Static FFmpeg Bundling**: Bundled static `ffmpeg` directly into PyInstaller's frozen binary (`sys._MEIPASS`) and automated static FFmpeg download in `build.sh` for self-contained Linux builds.
- **Persistent File Logging & History Buffer**: Added rotating log file handler (`kikumoe.log`) in platform data directories and an in-memory ring buffer (1000 lines) replayed upon opening the Developer Console.
- **Powered By Section**: New cards in Settings (Info tab) and About dialog featuring brand direct links to supported radio stream services (LISTEN.moe, etc.) with vector logos.
- **Telegram Channel Link**: Added official Telegram link button with custom vector plane icon in the About section.
- **Micro-Interactions**: Smooth 60 FPS click-bounce animations (`0.90 -> 1.04 -> 1.0`) on all action, link, and copy buttons across the UI.
- **Dynamic DevConsole Logger Level Sync**: Changing the log level in the Developer Console now immediately synchronizes all active application loggers (`KikuMoe`, `PlayerMPV`, `PlayerVLC`, `PlayerFFmpeg`) in real-time, with automatic restoration of default levels upon closing the console.
- **Lazy Logger Hooks**: DevConsole automatically attaches its log handler to newly instantiated player backends and loggers.
- **Live Track Ambient Mode & Counter**: Added active ambient shimmer wave animation on the progress bar and continuous elapsed second counting (`0:01, 0:02... / LIVE`) for untimed songs or live broadcasts (`duration == 0`) from LISTEN.moe, preventing the UI from appearing frozen.
- **Detailed MPV Diagnostics**: Enhanced audio startup diagnostics to report the exact dynamic linker exception and root cause (`__cause__`) when `libmpv` fails to import on Linux host systems.
- **Audio Scaling Tests**: Automated unit tests validating volume scaling and perceptual curve curves across all playback backends.

### Changed
- **Perceptual Volume Curve**: Implemented unified power 1.5 volume scaling across MPV, VLC, and FFmpeg backends ($100 \cdot \sqrt{\text{vol}/100}$ for cubic backends, $(\text{vol}/100)^{1.5}$ for FFmpeg amplitude). Low volume settings (< 20%) are now clear, audible, and natural without abrupt drop-offs.
- **Log Spam Reduction (#71)**: Downgraded `volume_changed` event messages from `INFO` to `DEBUG` to eliminate console and terminal flooding during volume slider drag.
- **Tagline & Localization**: Updated application tagline and descriptions across Italian and English translations to cover web radio, music, and local playback capabilities.
- **CI / Build Triggers**: Added the `redesign` branch directly to GitHub Actions and Forgejo CI workflow triggers to enable automated builds on both tags and branch pushes.

### Fixed
- **Progress Bar Freeze on Untimed Tracks**: Fixed an issue where receiving a song with `dur == 0` caused `_on_song_tick` to return immediately, leaving the progress bar static at 0% and freezing the elapsed time text.
- **Linux AppImage Audio Playback**:
  - Excluded conflicting low-level system audio libraries (`libasound`, `libpulse*`, `libjack`, `libpipewire*`, `libspa*`, `libasound_module*`) and standard C++ runtime (`libstdc++`, `libgcc_s`) in `kikumoe.spec`, forcing dynamic binding to host ALSA/PipeWire/PulseAudio plugins and resolving `GLIBCXX` symbol mismatches with host `libmpv` and `librubberband`.
  - Bundled standalone static `ffmpeg` in AppImage (`usr/bin/ffmpeg`) and added search paths in `PlayerFFmpeg`.
  - Added multi-output driver fallback (`--aout=pulse,alsa`) for VLC on Linux.
- **Silent Audio Failures & Error Visibility**:
  - Promoted FFmpeg process termination, exit codes, and `stderr` error output from `DEBUG` to `ERROR` in `PlayerFFmpeg`.
  - Promoted VLC and MPV initialization and playback failure exceptions to `ERROR`, ensuring all streaming issues are visible in `kikumoe.log` and the Developer Console.
- **Typing & Event Override Signatures (Pylance)**:
  - Corrected Qt event override parameter signatures (`enterEvent(self, event)`, `mousePressEvent(self, a0)`, `mouseMoveEvent(self, a0)`, `setChecked(self, a0)`, `eventFilter(self, a0, a1)`, `showEvent(self, a0)`) across `custom_titlebar.py`, `settings_dialog.py`, `dev_console.py`, and `about_dialog.py`.
  - Added null safety checks on optional Qt mouse and key events.
- **Settings Animation Stutter (#72)**: Pre-warmed settings panel widgets during application startup idle and cached SVG/PNG brand assets in memory, reducing first-click opening time from ~330 ms to < 10 ms.
- **Settings Dialog Closing Delay**: Streamlined dialog destruction and animation callbacks for instantaneous, lag-free close interactions.
- **Layout & Sizing Stability**:
  - Locked volume percentage label width to prevent layout shifts and controls repositioning when volume reaches 100%.
  - Vertically aligned playback controls and adjusted radio button row spacing and minimum window height to prevent overlap on compact displays.
  - Wrapped all Info tab sections into unified Cyber-Moe glass cards matching Audio and General tabs styling.
- **Dropdown & Combobox Popups (#58)**: Fixed transparent background and text overlap on GlassComboBox dropdown items.
- **System Tray Integration (#65, #67)**:
  - Fixed tray menu quit action to properly respect the "Confirm on exit" preference.
  - Synchronized tray menu state in real-time with the actual player playback state.
- **Settings Slide Transition (#62)**: Fixed layout corruption and rendering glitches during tab transitions.
- **Console Log Locale (#59)**: Fixed developer console log formatting to avoid locale-dependent corruption.
- **UI Contrast & Title Bar Alignment (#60, #61)**: Improved app icon contrast in dark theme and aligned the version badge label with the app title.
- **SSL Certificate Verification**: Fixed OpenSSL certificate bundle verification failures on Linux.

---

## [2.0.0-beta1] - 2026-10-21

### Added
- **Cyber-Moe Glass UI Redesign**: Complete aesthetic overhaul with dark glassmorphism, accent glow effects, custom frameless window title bar, and Cascadia/Segoe UI typography.
- **Ambient Album Art Glow**: Dynamic ambient lighting reacting to currently playing track album covers with smooth cross-fade animation.
- **Integrated Settings Panel**: Slide-in settings interface with tabbed organization (General, Audio, Info) and live hardware output device enumeration.
- **Cyber-Moe Developer Console**: Live floating debug console with filter levels, log autoscroll, text wrap, copy-to-clipboard, and export options.
- **Sleep & Session Timers**: Configurable sleep timers with smooth fade-out and stop-on-end-of-track support.
- **Backend Architecture**: Support for MPV (`libmpv-2`), VLC (`libvlc`), and FFmpeg audio engines with seamless runtime fallback.
