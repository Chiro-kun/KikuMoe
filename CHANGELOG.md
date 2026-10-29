# Changelog

All notable changes to KikuMoe will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0-beta3] - Unreleased

### Added
- **Cyber-Glass System Tray Header Card (`TrayNowPlayingCard` in `ui/tray_manager.py`)**:
  - Replaced the two plain disabled text lines with a rich, interactive cyber-glass card embedded at the top of the tray menu via `QWidgetAction`.
  - Displays high-resolution rounded album cover art (or fallback KikuMoe brand logo) with anti-aliased corner clipping.
  - Features real-time track metadata (auto-elided title, artist, station branding pill, and live session timer).
  - Integrates 4 quick inline glass action buttons directly in the card: `[Play/Pause]`, `[Stop]`, `[Mute]`, and `[Cronologia brani...]`.
  - Clicking anywhere on the card body immediately raises and brings KikuMoe to the foreground.
- **Complete Vector Icon Suite Expansion (`ui/vector_icons.py`)**:
  - Implemented anti-aliased SVG vector icons for all system tray and window actions:
    - Play triangle (`get_play_icon`) and Pause dual bars (`get_pause_icon`).
    - Stop rounded square (`get_stop_icon`).
    - Speaker with audio waves and muted slash (`get_volume_icon`).
    - Window layout emblem (`get_window_icon`).
    - High-visibility bright gear (`get_settings_icon`), replacing the dark/invisible PNG.
    - Information circle badge (`get_info_icon`).
    - Radio broadcast tower with electromagnetic waves (`get_station_icon`).
    - Dual musical notes (`get_channel_icon`).
    - Audio waveform (`get_codec_icon`).
    - Standby power emblem in glowing crimson/rose (`get_power_quit_icon`).
- **Bespoke Cyber-Moe Color Picker Dialog (`ui/color_picker_dialog.py`)**:
  - Designed a high-DPI frameless modal color picker replacing Qt's legacy `QColorDialog`, complete with `CustomTitleBar`, KikuMoe branding, and 60 FPS drop-in/fade animations.
  - Interactive 2D Saturation/Value gradient canvas with high-contrast dual-ring cursor and full-spectrum vertical Hue rainbow slider.
  - Split Before/After color comparison swatch with one-click restore.
  - Monospace HEX input with automatic normalization and one-click copy feedback.
  - Un-truncated, spacious RGB (0..255) and HSV (H°, S%, V%) numeric spinboxes with mouse-wheel support.
  - Built-in desktop Screen Eyedropper (`Pipetta`) with a live 9×9 magnified pixel grid loupe and real-time color sampling.
  - 16 curated Cyber-Moe and vibrant neon quick-palette swatches with selection checkmarks.
  - 8 user-customizable saved color slots persisted in `QSettings` (`custom_accent_palette`).
  - Real-time accent preview on the dialog's primary OK button with contrast-aware foreground styling.
- **Theme & Custom Accent Engine**:
  - Added 5 curated Cyber-Moe visual presets in Settings (*Generali → Aspetto e Tema*), organized in dedicated modular theme files under `ui/themes/` (`cyber_moe.py`, `midnight_amoled.py`, `sakura_bloom.py`, `neon_matrix.py`, `ocean_cyan.py`, and shared `engine.py`): **Cyber Moe** (default dark violet & neon pink), **Midnight AMOLED** (pure `#000000` black surfaces), **Sakura Bloom** (soft rose & cherry glow), **Neon Matrix** (deep slate & acid green), and **Ocean Cyan** (navy deep & cyan glow).
  - Added an interactive **Custom Accent Color** toggle, glowing color swatch picker, and one-click preset reset (`AccentColorSwatchButton`) that dynamically derives hover, pressed, shimmer, contrast-aware foreground (`on_accent`), glass border, scrollbar, and glow RGBA tokens across the entire UI.
  - Real-time live preview across the main player, title bar, waveform/equalizer badge, station selector, progress scrubber, lyrics panel, mini-player HUD, dialogs, popovers, and system tray menu, with automatic rollback to persisted `QSettings` on Cancel.
- **Lyrics**: Show LRCLIB lyrics beside the album cover, with animated scrolling for synchronized tracks and a plain-text fallback.
- **System Media Controls**: Integrate with Windows SMTC and Linux MPRIS for playback controls and track metadata, with a media-key fallback on Windows.
- **Discord Rich Presence Button**: Add a localized button linking to the KikuMoe project page.
- **Settings Shortcut**: Open settings with Ctrl+, including from the mini player.
- **Mini Player Track Progress**: Show elapsed time, duration and a compact progress indicator, with a live label for streams without a known duration.
- **Mini Player Volume Feedback**: Show an animated percentage bubble when the mini player volume changes.
- **Mini Player HUD**: Toggle a compact player with F9 or the title bar button, with cover art, scrolling track information, playback, volume, always-on-top, and separately saved window geometry.
- **Settings Feedback**: Show a short, animated confirmation when settings are applied.
- **Discord Rich Presence**: Optional local IPC integration for Discord desktop and compatible arRPC clients, with configurable Application ID, track metadata, artwork, playback state, and automatic reconnection.
- **Multi-Station Radio Engine**:
  - Integrated community and partner web radio stations: LISTEN.moe (J-POP & K-POP), Gensokyo Radio (Touhou Project 24/7), ANISON.FM (Japanese anime music), Neuro 21 Radio (Neuro & Evil karaoke covers), and TruckersFM (Euro Truck & gaming hits).
  - Modernized top HUD station selector: `StationPillButton` featuring an animated vector chevron, active station branding, and the `StationGlassPopover` frosted glass channel switcher.
  - Pluggable provider architecture (`StationProvider`) handling diverse metadata streams (LISTEN.moe WebSockets, AzuraCast REST APIs, Icecast/Liquidsoap status endpoints).
- **Session Song History & Popover**:
  - In-memory thread-safe `SongHistoryManager` ring buffer (up to 100 tracks) with consecutive duplicate filtering to avoid spamming the history during reconnects or polling cycles.
  - Cyber-Glass `SongHistoryPopover` modal card featuring smooth drop-in/fade animations (190ms `OutCubic`), session track count badge, "Svuota" (clear) action, and empty state guidance.
  - Dedicated vector history button (`HistoryIconButton`) in the header HUD with 60 FPS click-bounce animation (`0.84 -> 1.04 -> 1.0`).
- **Intelligent Quick Search Engine (`core/quick_search.py`)**:
  - **Spotify Desktop Detection & Fallback**: Automatically probes for Spotify desktop installations across platforms (Windows Registry `HKCU/HKCR/HKLM\Software\Classes\spotify\shell\open\command` + exe paths, Linux `which spotify`, Flatpak, Snap, macOS). Launches native URI `spotify:search:<query>` if installed, with seamless fallback to `https://open.spotify.com/search/<query>` in the default browser.
  - Direct search integrations for **YouTube**, **YouTube Music**, and **Apple Music**.
  - One-click clipboard actions: Copy formatted `"Artist - Title"`, song title, or artist name with visual feedback.
- **Track Title Dropdown Chevron & Interactive Capsule (`TrackMenuChevronButton`)**:
  - Interactive vector chevron (`▾`) positioned dynamically right at the optical midline and baseline of the song title in `AnimatedTrackLabel`.
  - Added subtle glowing Cyber-Glass hover capsule surrounding the active song title and chevron on mouse hover with pointing hand cursor.
  - Left-clicking either the title text or the chevron directly opens the Quick Search & Actions menu anchored underneath.
  - Automatically hidden when playback is idle and elides cleanly on long titles without pushing title text off-center.
- **Official Vector Icon Suite (`ui/vector_icons.py`)**:
  - Replaced all Unicode emojis across menus and buttons with authentic, pixel-perfect vector SVGs rendered via `QSvgRenderer`:
    - Official Spotify brand green disc `#1ED760` with accurate convex sound waves.
    - Official YouTube red badge `#FF0000` with centered white play triangle.
    - Official Apple Music gradient badge (`#FA2D48` → `#FA5570`) with white paired musical notes.
    - Copy documents icon with rounded corners in slate `#CBD5E1`.
    - Neon clock history icon with hour and minute hands.
  - Rendered across the Now Playing context menu, history popover action buttons, and system tray.

### Changed
- **Seamless System Tray Header & Enlarged Artwork (`TrayNowPlayingCard` in `ui/tray_manager.py`)**:
  - Removed detached card container borders and background box, seamlessly integrating the Now Playing widget as the native top header of the system tray context menu.
  - Eliminated the top dark padding gap above the header card by configuring top padding to `0px` and matching top corner curvature with asymmetric rounded clipping, making the ambient glow sit completely flush with the top border.
  - Implemented dynamic Cyber ambient glow in the tray header background (`TrayNowPlayingCard.paintEvent`): renders an anti-aliased radial aura behind the album cover art and a soft top-down ambient light wash that dynamically morphs with the active theme preset and custom accent color, with smooth Destination-In vertical falloff masking that guarantees 0% alpha before the card bottom to prevent any cutoff seam.
  - Increased album cover art thumbnail size from 46×46 px to 58×58 px with smooth anti-aliased 8px rounded corners.
  - Removed cramped hint text and centered quick media buttons (`[Play/Pause]`, `[Stop]`, `[Mute]`, `[Cronologia brani...]`) with comfortable 36×28 px touch targets.
  - Added real-time playback control state synchronization whenever the tray menu is opened (`menu.aboutToShow.connect(self._sync_controls_from_parent)`), ensuring the Play/Pause icon immediately reflects current playback state.
  - Polished section header typography and spacing (`FINESTRA`, `PREFERENZE`).
- **Mini Player Layout**: Increased its compact window size and cover art to give track information, progress, and volume more room.
- **Scrollbars**: Apply Cyber-Moe track and accent colors to vertical and horizontal scrollbars, with hover and pressed states defined in the theme palette.
- **Track Metadata Hover**: Connected title and artist highlights follow each text width, fade smoothly, and open the track actions from either row.
- **Apple Music Icon**: Refined the gradient badge and music note for clearer rendering at menu sizes.
- **Close Confirmation Dialog UI**:
  - Modernized `CloseConfirmDialog` with custom Cyber-Glass title bar (`CustomTitleBar`), dialog title "Chiudere l'app?", and clean non-redundant description body.
  - Replaced asymmetric dialog icon with a perfectly balanced standby power emblem badge (`DialogIconBadge`).
  - Added smooth drop-in and fade entrance/exit animations with `WindowStaysOnTopHint`.
- **System Tray Context Menu Overhaul (`ui/tray_manager.py`)**:
  - Replaced all legacy low-res PNGs and bitmap icons with crisp, resolution-independent vector icons that automatically re-tint with the active theme and custom accent color.
  - Streamlined the context menu by removing redundant duplicate playback items (*Riproduci*, *Stop*, *Muto*, *Cronologia brani*), which are now integrated directly inside the interactive Cyber-Glass Now Playing header card.
  - Modernized section headers (`FINESTRA`, `PREFERENZE`) with bold, uppercase, tracked typography and polished item spacing.
  - Deep glassmorphism background (`#141624`), subtle borders (`PALETTE["border_card"]`), and smooth accent hover highlights (`PALETTE["accent_menu_hover"]`).
  - Full-box edge-to-edge menu item hover state (`margin: 0px`, `padding: 0px` on menu): removed inset horizontal margins and bottom padding so hover states fill the entire width and reach the bottom of the tray menu seamlessly.
  - Dynamic theme accent styling and increased font size (`11px` bold) for tray section headers (*FINESTRA*, *PREFERENZE*), harmonizing section titles with the active theme and custom accent.
  - Inward subcontrol positioning for submenu chevrons (`QMenu::right-arrow { right: 12px; }`), preventing `>` arrows from colliding with the right border.
  - Added localized tooltips and labels (`tray_open_app`, `tray_no_track`).
- **Audio-Reactive Conformal Fluid Wave Visualizer (`core/audio_analyzer.py`, `ui/widgets/ambient_cover.py`)**:
  - Implemented an audio-reactive **Conformal Fluid Neon Wave** visualizer that envelops the rounded album cover art and vinyl disc placeholder, bringing organic Cyber-Moe fluid wave dynamics to playback.
  - Conformal contour geometry: dynamically follows the rounded-rectangle boundary of the cover pedestal on all four sides and corners, eliminating edge occlusions and clipping.
  - Dual-wave neon rendering: primary high-intensity neon fluid spline with white core and vibrant theme bloom, backed by a resonant echo wave and soft translucent neon aura.
  - Frequency perimeter distribution: deep sub-bass and kick punch ripple downward and outward at the bottom, mids contour the sides, and treble sparkles at the top.
  - Zero binary dependencies: high-performance pure-Python Radix-2 Cooley-Tukey iterative FFT (<0.2 ms execution budget per frame) with Hanning windowing and logarithmic frequency grouping into 64 symmetric perceptual nodes.
  - Silky physical smoothing with instant attack (0.65) and exponential gravity decay (0.86), preventing harsh flickering and ensuring smooth natural movement at 60 FPS.
  - Audio-reactive ambient nebula glow: kick-drum / sub-bass energy dynamically pulses the radial background glow behind the artwork in real time.
  - Thread-safe zero-overhead PCM tap on `PlayerFFmpeg` with procedural harmonic generator fallback when streaming via VLC/MPV or when muted.
  - Fully integrated with dynamic themes and custom accents: visualizer wave and glow inherit `PALETTE["accent"]` or artwork dominant colors automatically.
  - Configurable toggle switch (*Visualizzatore audio radiale*) in *Impostazioni → Aspetto* with instant live preview.

### Fixed
- **System Tray Section Header Alignment**: Corrected the horizontal alignment of disabled section headers (*FINESTRA*, *PREFERENZE*) in `ui/tray_manager.py` by applying `margin-left: -13px; padding-left: 0px;` on `QMenu::item:disabled`, bringing section titles into perfect optical alignment with the icon column.
- **System Tray Icon Left Padding**: Added explicit `padding-left: 10px;` and `padding-right: 6px;` to `QMenu::icon` in `ui/tray_manager.py`, preventing action icons from touching the left menu border when full-width hover is active.
- **Color Picker UI & SpinBox Truncation**: Replaced Qt's unlocalized, fixed-width non-native `QColorDialog` with the bespoke `AccentColorPickerDialog`, resolving cut-off spinbox digits (`3:`, `2!`), native window titlebar clash, and archaic Windows 95 layout.
- **History Popover Cover Art Cache**: Added a shared, thread-safe in-memory LRU cover art cache (`network/image_cache.py`) so `SongHistoryPopover` renders album art thumbnails across LISTEN.moe and partner web radio stations.
- **PortAudio Thread Safety & Device Enumeration**: Serialized concurrent `Pa_Initialize`/`Pa_Terminate` and `silence_stderr()` calls via `PORTAUDIO_LOCK` across audio backends and Settings to prevent Linux PortAudio segfaults, and cancelled pending device-refresh timers when closing Settings.
- **PyQt6 Type Annotations & Method Overrides**: Aligned widget override signatures and optional type narrowing across `ui/`, `core/`, and `network/` with PyQt6 type stubs and Pylance/mypy checks.
- **Settings Panel & Backdrop Rendering Performance**:
  - Cached steady-state HiDPI composited backdrop frames in `FullBleedCanvas` to eliminate per-frame CPU pixmap scaling and multi-gradient recomputation during Settings scrolling, widget hovers, and 60 FPS tab/panel slides.
  - Moved PyAudio output device enumeration (`Pa_Initialize`) off the Qt main thread into a background worker, deduplicated global QSS rules on embedded `SettingsDialog`, cached tinted icons and theme application state in `ListenMoePlayer.apply_theme`, and eliminated redundant theme re-polishing on Cancel/Apply/OK.
- **Close Confirmation Dialog**: Use a translucent, themed frame and a compact animated remember-choice checkbox with a vector checkmark.
- **Station Selector and Settings Transitions**: Deliver station selections immediately, avoid popup motion on Linux, and preserve the settings panel during return animations.
- **Audio Status Badge**: Show the active audio backend instead of the misleading initial AUTO label, and update its readiness indicator even when legacy widgets are absent.
- **Tooltip Corners**: Match the tooltip border to its rectangular native background.
- **Mini Player on Linux**: Keep the compact window at its intended size and reject maximize/full-screen requests.
- **FFmpeg Rapid Pause**: Avoid stopping the audio output while another thread is writing, preventing host errors during rapid pause and resume.
- **Mini Player Artwork**: Clip album covers to rounded corners, including on high-DPI displays.
- **Discord Settings Labels**: Match the wording and localization of the other settings.
- **Settings Horizontal Clipping**: Allow horizontal scrolling when a narrow window cannot fit a settings page, and keep the audio device selector flexible.
- **Minimum Window Size**: Prevent the main window from being resized below the height needed by the player layout.
- **Compact Settings Layout**: Settings pages scroll vertically when the window is too small for their contents, preventing overlapping cards while keeping the action buttons visible.
- **Title Capsule Hit-Testing**: Hit-testing is now strictly bounded to the title text and chevron geometry (`get_capsule_rect()`). Mouse movements and clicks in empty margin areas to the left or right of centered text are properly ignored.
- **Active Menu State Retention**: The unified title hover capsule remains fully illuminated while the dropdown search context menu is open (`set_menu_active(True)`), preventing the capsule from prematurely collapsing on `leaveEvent`.
- **Chevron Button Clean Rendering**: Removed standalone square box background from `TrackMenuChevronButton` when clicked/active; the chevron icon seamlessly tints to the accent color `#EC186C` inside the unified title capsule without an isolated bounding box.
- **CloseConfirmDialog Geometry Conflict**: Resolved Windows platform window geometry error (`QWindowsWindow::setGeometry: Unable to set geometry 430x180 ... Resulting geometry: 430x181`) by dynamically clamping the height to `max(186, self.sizeHint().height())`.
- **History Popover Widget Overlap**: Fixed visual ghosting and overlapping text rows in `SongHistoryPopover` by explicitly invoking `w.setParent(None)` prior to `w.deleteLater()` when clearing and rebuilding the scrollable track list.
- **Station Selection Persistence**: Fixed issue where switching to Neuro 21 or TruckersFM reverted back to LISTEN.moe due to station ID normalization.
- **Audio Scrubber Duration for Web Stations**: Ensured non-websocket radio stations correctly report duration and track countdowns without progress bar resets.

---

## [2.0.0-beta2] - 2026-10-26

### Added
- **Linux Audio Startup Diagnostics**: Automated probing of active sound daemons (PipeWire socket, PulseAudio server, ALSA) and audio backend readiness (FFmpeg binary, PortAudio host APIs, MPV, VLC) logged on startup and inspectable in the Developer Console.
- **Standalone Static FFmpeg Bundling**: Bundled static `ffmpeg` directly into PyInstaller's frozen binary (`sys._MEIPASS`) and automated static FFmpeg download in `build.sh` for self-contained Linux builds.
- **Minimal Audio-Only FFmpeg Linux Build**: Dedicated compilation recipe (`packaging/linux/build-minimal-ffmpeg.sh`) building a specialized static FFmpeg binary (~15 MB vs ~140 MB full build) tailored specifically for web radio audio streams (PCM, MP3, AAC, FLAC, Opus, Ogg/Vorbis) and protocols (`pipe`, `crypto`, `https`, `tls`).
- **Headless CLI Flags (`--check-audio`, `--help`)**: Non-GUI command-line interface arguments in `KikuMoe.py` allowing headless verification of system audio daemons, sound backends, and environment diagnostics with standardized process exit codes.
- **CI Smoke Tests & Footprint Profiling**: Headless automated CI validation on both GitHub Actions and Forgejo CI executing `--check-audio` and `--help` directly against built Linux AppImage artifacts, coupled with automated AppDir footprint and largest file breakdowns.
- **PyAudio & PortAudio Linux Bundling**: Explicit inclusion of `pyaudio` C-extensions (`_portaudio`), `libportaudio.so.2`, and fallback `libjack.so.0` inside the Linux AppDir, guaranteeing PortAudio availability out-of-the-box even on systems without JACK or pipewire-jack packages.
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
- **PyInstaller Onedir Mode on Linux**: Converted Linux packaging from `onefile` to `onedir` in `kikumoe.spec`, eliminating the runtime overhead of unpacking files to `/tmp` on every launch, speeding up startup time and reducing disk churn.
- **AppImage Zstandard Compression**: Modernized `packaging/linux/build-appimage.sh` with pinned `appimagetool` v1.9.1 and `zstd` level 19 compression, achieving an ultra-compact distribution footprint.
- **Binary & Asset Stripping**: Excluded unused Qt translations (>15 MB saved), stripped host media codecs (Mesa/GPU, x264, x265, VP8/VP9, AV1), and removed duplicate system ICU libraries from the bundled AppDir.
- **Perceptual Volume Curve**: Implemented unified power 1.5 volume scaling across MPV, VLC, and FFmpeg backends ($100 \cdot \sqrt{\text{vol}/100}$ for cubic backends, $(\text{vol}/100)^{1.5}$ for FFmpeg amplitude). Low volume settings (< 20%) are now clear, audible, and natural without abrupt drop-offs.
- **CI / Build Triggers & Concurrency**: Added `concurrency: cancel-in-progress` groups to GitHub and Forgejo CI workflows, and included the `redesign` branch directly in build triggers to enable automated builds on both tags and branch pushes.
- **Isolated Build Dependency Group**: Introduced `tool.poetry.group.build.dependencies` in `pyproject.toml` isolating PyInstaller and build tooling from runtime dependencies.
- **Log Spam Reduction (#71)**: Downgraded `volume_changed` event messages from `INFO` to `DEBUG` to eliminate console and terminal flooding during volume slider drag.
- **Tagline & Localization**: Updated application tagline and descriptions across Italian and English translations to cover web radio, music, and local playback capabilities.
- **Binary Size Optimization**: Excluded unused heavy Qt6 modules (`QtQml`, `QtQuick`, `QtPdf`, `QtSql`, `QtXml`, `QtBluetooth`, etc.) and stdlib modules (`tkinter`, `unittest`, `pydoc`, `sqlite3`) in `kikumoe.spec`, and eliminated duplicate ffmpeg bundling inside the onefile payload in favor of AppDir placement, drastically reducing Linux executable and AppImage size.

### Fixed
- **Host MPV Dynamic Library Conflicts (Arch / Fedora)**:
  - Excluded `libssl.so*` and `libcrypto.so*` from the PyInstaller bundle on Linux, resolving `OPENSSL_3.5.0 not found` caused when host `libmpv` dynamically loads host `libcurl.so.4`.
  - Excluded `libfontconfig.so*` from the PyInstaller bundle on Linux, resolving `undefined symbol: FcConfigSetDefaultSubstitute` when host `libmpv` loads host `libass.so.9` against modern host Fontconfig 2.14+.
- **Host VLC Dynamic Library Loading & Discovery**:
  - Implemented `_find_libvlc_path()` to systematically probe system library directories (`/usr/lib`, `/usr/lib64`, `/usr/local/lib`, etc.) and export `PYTHON_VLC_LIB_PATH` prior to `import vlc`.
  - Updated audio diagnostics to verify `libvlc_new()` instantiation, reporting VLC as `Ready` only when confirmed operational and reporting exact initialization exceptions under `Unavailable` instead of misleading `Available`.
- **PyAudio Sample Rate Auto-Negotiation**:
  - Added multi-rate candidate probing (`48000 Hz`, `44100 Hz`, and device default rate) in `PlayerFFmpeg._open_pyaudio_stream`, eliminating audio crackling, pitch distortion, and invalid sample rate errors when connecting to non-48kHz sinks or fallback devices.
- **Packaging Script Path Resolution**: Fixed relative path ambiguities in `build-minimal-ffmpeg.sh` and `fetch-ffmpeg.sh` by ensuring destination paths are resolved to absolute coordinates.
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
