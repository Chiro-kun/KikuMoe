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

1. Checks that `packaging/windows/` contains `KikuMoe.ico`, `KikuMoe.manifest`, `version_info.txt`, and `libmpv-2.dll`.
2. Runs `poetry install --with dev` (installs runtime + dev dependencies)
3. Runs `pyinstaller --noconfirm --clean kikumoe.spec` via `poetry run`
4. Produces `dist\KikuMoe-<version>.exe`

The build stops with a list of missing files if the prerequisites are absent.
The spec also checks that `libmpv-2.dll` can load on the build machine and
bundles the DLLs found beside it, including its runtime dependencies. Get the
matching Windows `mpv-dev` package and place `libmpv-2.dll` plus its dependent
DLLs in `packaging/windows/` before building.

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
poetry run python -m PyInstaller --noconfirm --clean kikumoe.spec
```

### Output

```
dist\KikuMoe-<version>.exe
```

---

## Linux

### Build script (bare binary)

```bash
# From the repository root
./build.sh
```

The script runs in order:

1. Runs `poetry install --with dev` (installs runtime + dev dependencies)
2. Runs `pyinstaller --noconfirm --clean kikumoe.spec` via `poetry run`
3. Produces `dist/KikuMoe-<version>`

VLC is not bundled on Linux; it must be installed system-wide (`python-vlc` will find it automatically). The FFmpeg backend is used by default and requires `ffmpeg` to be in `PATH`.

> **Note:** PyInstaller's ctypes analysis auto-detects `libvlc.so.5` / `libvlccore.so.9` and would bundle them, but without the full VLC plugin tree (audio outputs, codecs…) and transitive runtime dependencies those copies cannot initialize audio output. `kikumoe.spec` explicitly removes them from `a.binaries` on Linux so the system-installed VLC is used end-to-end.

### AppImage (recommended for distribution)

After building the bare binary, wrap it in an AppImage:

```bash
./build.sh
bash packaging/linux/build-appimage.sh
```

The script:

1. Creates an `AppDir` with the binary, `.desktop` file, icon, and AppStream metadata
2. Downloads `appimagetool` automatically if not cached in `dist/`
3. Produces `dist/KikuMoe-<version>-x86_64.AppImage`

The AppImage is the recommended distribution format — it bundles the binary with desktop integration and avoids glibc linking issues on end-user systems.

### Manual build

```bash
poetry run python -m PyInstaller --noconfirm --clean kikumoe.spec
bash packaging/linux/build-appimage.sh          # optional: wrap in AppImage
```

### Output

```
dist/KikuMoe-<version>                          # bare binary
dist/KikuMoe-<version>-x86_64.AppImage          # AppImage (if built)
```

### CI/CD

Builds are automated via Forgejo Actions (`.forgejo/workflows/build.yml`). Pushing a `v*` tag triggers a build that produces the AppImage and creates a release with the artifact attached.

---

## Adding an audio backend

1. Create `audio/player_new.py` implementing the common interface:

```python
class PlayerNew:
    on_event = None  # callable(event: str, data=None)

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
    ...  # fall through to the next backend
```

3. If the backend needs dedicated settings, add the keys to `core/constants.py` and the corresponding controls to `ui/settings_dialog.py`.
