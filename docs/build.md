# Build

Produces a single-file executable (`onefile`) via PyInstaller. Both Windows and Linux are supported.

---

## Windows

### Build script

```powershell
# From the repository root
.\build.ps1
```

The script runs in order:

1. Upgrades `pyinstaller` and `pyinstaller-hooks-contrib`
2. Installs dependencies from `requirements.txt`
3. Validates the environment (`import PyQt5, websocket`)
4. Runs `pyinstaller --noconfirm --clean kikumoe.spec`
5. Produces `dist\KikuMoe-<version>.exe`

### VLC bundling

To bundle VLC into the executable, set the environment variable before building:

```powershell
$env:VLC_DIR = "C:\Program Files\VideoLAN\VLC"
.\build.ps1
```

`kikumoe.spec` automatically includes `libvlc.dll`, `libvlccore.dll`, and the `plugins/` folder.  
`pyi_rthook_vlc.py` sets `VLC_PLUGIN_PATH` to `_MEIPASS/plugins` at executable startup.

If `VLC_DIR` is not set and VLC is not at the default path, VLC binaries are simply omitted from the executable.

### Manual build

```powershell
python -m PyInstaller --noconfirm --clean kikumoe.spec
```

### Output

```
dist\KikuMoe-<version>.exe
```

---

## Linux

### Build script

```bash
# From the repository root
./build.sh
```

The script runs in order:

1. Upgrades `pyinstaller` and `pyinstaller-hooks-contrib`
2. Installs dependencies from `requirements.txt`
3. Validates the environment (`import PyQt5, websocket`)
4. Runs `pyinstaller --noconfirm --clean kikumoe.spec`
5. Produces `dist/KikuMoe-<version>`

VLC is not bundled on Linux; it must be installed system-wide (`python-vlc` will find it automatically). The FFmpeg backend is used by default and requires `ffmpeg` to be in `PATH`.

### Manual build

```bash
python3 -m PyInstaller --noconfirm --clean kikumoe.spec
```

### Output

```
dist/KikuMoe-<version>
```

---

## Adding an audio backend

1. Create `audio/player_new.py` implementing the common interface:

```python
class PlayerNew:
    on_event = None   # callable(event: str, data=None)

    def play(self, url: str): ...
    def pause(self): ...
    def resume(self): ...
    def stop(self): ...
    def force_stop(self): ...
    def set_volume(self, v: int): ...
    def set_mute(self, muted: bool): ...
    def set_device(self, index: int): ...
```

2. In [ui/main_window.py](../ui/main_window.py), add an initialization attempt after FFmpeg:

```python
try:
    from audio.player_new import PlayerNew
    self._player = PlayerNew(...)
except Exception:
    ...   # fall through to the next backend
```

3. If the backend needs dedicated settings, add the keys to `core/constants.py` and the corresponding controls to `ui/settings_dialog.py`.
