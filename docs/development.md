# Development

## Environment setup

Dependencies are managed with [Poetry](https://python-poetry.org/).

```bash
# Clone the repository
git clone https://git.alsogamer.com/chiro/KikuMoe.git
cd KikuMoe

# Install all dependencies (runtime + dev: pyinstaller, mypy, ruff)
poetry install --with dev

# Run the application
poetry run python KikuMoe.py

# Run with verbose debug output (Python DEBUG traces + raw C-level stderr)
poetry run python KikuMoe.py --debug
```


---

## Linux platform notes

### Display (Wayland / X11)

`KikuMoe.py` sets `QT_QPA_PLATFORM=wayland;xcb` before creating `QApplication` when running on Linux and the variable is not already set. Qt will try Wayland first and fall back to XCB (X11) automatically. To force X11, run:

```bash
QT_QPA_PLATFORM=xcb poetry run python KikuMoe.py
```

### Audio (PipeWire / PulseAudio / ALSA)

Each backend routes audio on Linux without requiring manual configuration:

**FFmpeg / PyAudio (`PlayerFFmpeg`)** — probes PortAudio host APIs at startup and selects the default output device of the first available backend:

| Priority | PortAudio host API | Typical provider |
|---|---|---|
| 1 | PulseAudio (type 18) | PipeWire-pulse **or** PulseAudio |
| 2 | ALSA (type 8) | Direct ALSA |

The **Audio output** selector in Settings lists each device with its host API tag (`[PipeWire/Pulse]`, `[ALSA]`, etc.) so the user can override the auto-detected device.

**MPV (`PlayerMPV`)** — passes `ao='pipewire,pulse,alsa'` to libmpv when a PipeWire socket is detected at `/run/user/<uid>/pipewire-0`, otherwise `ao='pulse,alsa'`. libmpv tries each driver in order and falls back automatically.

**VLC (`PlayerVLC`)** — passes `--aout=pulse` to the VLC instance on Linux, routing audio through PulseAudio. On systems running PipeWire, `pipewire-pulse` transparently satisfies this.

**System dependencies** (not installed by Poetry):

```bash
# Arch / CachyOS
sudo pacman -S pipewire pipewire-pulse wireplumber ffmpeg

# Debian / Ubuntu
sudo apt install pipewire pipewire-pulse wireplumber ffmpeg libportaudio2
```

---

## Settings system

All settings persist via `QSettings`:

```python
from PyQt6.QtCore import QSettings
from core.constants import ORG_NAME, APP_SETTINGS, KEY_VOLUME

settings = QSettings(ORG_NAME, APP_SETTINGS)

vol = settings.value(KEY_VOLUME, 80, type=int)   # read with default
settings.setValue(KEY_VOLUME, 75)                 # write
```

- **Windows:** `HKEY_CURRENT_USER\Software\KikuMoe\ListenMoePlayer`
- **Linux/macOS:** INI file at a path determined by Qt

Always use the constants from `core/constants.py`. Never use string literals as keys.

---

## Internationalization (i18n)

To add or modify strings:

1. Open [core/i18n.py](../core/i18n.py).
2. Find the translations dictionary.
3. Add/update the key in both the `"it"` and `"en"` sections.

To add a new language (e.g. French):

1. Add a `"fr"` section in `core/i18n.py` with all keys translated (use `"en"` as the base).
2. In [ui/settings_dialog.py](../ui/settings_dialog.py), add `"fr"` to the language selector list.

Strings are accessed everywhere via `self._i18n.t("key")`. A runtime language switch calls `retranslateUi()` without restarting.

---

## Versioning

The version is defined in `version.yml` at the repository root:

```yaml
version: 1.9.0
```

To release a new version:

1. Update `version.yml`.
2. Update `packaging/windows/version_info.txt` (`filevers` and `FileVersion` fields).
3. Update the output name in `kikumoe.spec` (`name='KikuMoe-X.Y.Z'`), `build.ps1`, and `build.sh`.
4. Create the tag: `git tag vX.Y.Z`.

---

## Static analysis and formatting

Run these before committing:

```bash
# Linting and import sorting
poetry run ruff check .

# Auto-fix safe issues (including import order)
poetry run ruff check --fix .

# Code formatting
poetry run ruff format .

# Type checking
poetry run mypy .
```

Configuration for both tools lives in `pyproject.toml` under `[tool.ruff]` and `[tool.mypy]`.

---

## Code conventions

- **Style:** PEP 8, 4-space indentation. Enforced by `ruff format`.
- **Imports:** absolute from the root (`from core.constants import ...`), not relative.
- **Logging:** use `get_logger(__name__)` instead of `print()`. Use `log.debug()` for verbose traces (hidden by default, shown with `--debug`) and `log.info()` for messages that should always be visible. Wrap C-library init calls (PyAudio, libVLC) with `silence_stderr()` from `core.logger`.
- **UI thread safety:** any UI update from a non-main thread must go through a Qt signal. Never call Qt methods directly from secondary threads.
- **UI strings:** always use `self._i18n.t("key")`. Never hardcode user-visible strings.
- **Settings keys:** always use the constants from `core/constants.py`. Never use string literals.
