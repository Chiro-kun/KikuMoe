# Changelog

All notable changes to KikuMoe will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0-beta2] - 2026-10-23

### Added
- **Powered By Section**: New cards in Settings (Info tab) and About dialog featuring brand direct links to supported radio stream services (LISTEN.moe, etc.) with vector logos.
- **Telegram Channel Link**: Added official Telegram link button with custom vector plane icon in the About section.
- **Micro-Interactions**: Smooth 60 FPS click-bounce animations (`0.90 -> 1.04 -> 1.0`) on all action, link, and copy buttons across the UI.
- **Dynamic DevConsole Logger Level Sync**: Changing the log level in the Developer Console now immediately synchronizes all active application loggers (`KikuMoe`, `PlayerMPV`, `PlayerVLC`, `PlayerFFmpeg`) in real-time, with automatic restoration of default levels upon closing the console.
- **Lazy Logger Hooks**: DevConsole automatically attaches its log handler to newly instantiated player backends and loggers.
- **Audio Scaling Tests**: Automated unit tests validating volume scaling and perceptual curve curves across all playback backends.

### Changed
- **Perceptual Volume Curve**: Implemented unified power 1.5 volume scaling across MPV, VLC, and FFmpeg backends ($100 \cdot \sqrt{\text{vol}/100}$ for cubic backends, $(\text{vol}/100)^{1.5}$ for FFmpeg amplitude). Low volume settings (< 20%) are now clear, audible, and natural without abrupt drop-offs.
- **Log Spam Reduction (#71)**: Downgraded `volume_changed` event messages from `INFO` to `DEBUG` to eliminate console and terminal flooding during volume slider drag.
- **Tagline & Localization**: Updated application tagline and descriptions across Italian and English translations to cover web radio, music, and local playback capabilities.
- **CI / Build Triggers**: Added the `redesign` branch directly to GitHub Actions and Forgejo CI workflow triggers to enable automated builds on both tags and branch pushes.

### Fixed
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
