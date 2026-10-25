# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

_IS_WIN32 = sys.platform == "win32"

# Spec lives at the repo root — all paths resolve from here
repo_root = Path(globals().get("SPECPATH", os.path.abspath("."))).resolve()
packaging_win = repo_root / "packaging" / "windows"

# Windows builds must include the native MPV runtime and Windows metadata.
# Fail before PyInstaller starts instead of producing an executable with a
# silently unavailable MPV backend or missing executable resources.
if _IS_WIN32:
    required_windows_files = [
        packaging_win / "KikuMoe.ico",
        packaging_win / "KikuMoe.manifest",
        packaging_win / "version_info.txt",
        packaging_win / "libmpv-2.dll",
    ]
    missing_windows_files = [path for path in required_windows_files if not path.is_file()]
    if missing_windows_files:
        missing_list = "\n".join(f"  - {path}" for path in missing_windows_files)
        raise SystemExit(
            "Windows build prerequisites are missing:\n"
            f"{missing_list}\n"
            "Add the required assets to packaging/windows and retry."
        )

    # Catch missing transitive DLLs and architecture mismatches on the build
    # machine rather than shipping an MPV DLL that cannot be loaded at runtime.
    dll_dir_cookie = os.add_dll_directory(str(packaging_win))
    try:
        import ctypes

        mpv_probe = ctypes.WinDLL(str(packaging_win / "libmpv-2.dll"))
        del mpv_probe
    except OSError as exc:
        raise SystemExit(
            "Windows build cannot load packaging/windows/libmpv-2.dll. "
            "Check its architecture and include its dependent DLLs in the same "
            f"folder. Loader error: {exc}"
        ) from exc
    finally:
        dll_dir_cookie.close()

# Collect icons folder
datas = []
icon_dir = repo_root / "icons"
if icon_dir.is_dir():
    for root, _, files in os.walk(icon_dir):
        for f in files:
            full = Path(root) / f
            dest = str(Path(root).relative_to(repo_root))
            datas.append((str(full), dest))

# Include version.yml if present so the app can read it at runtime in onefile
version_yml = repo_root / "version.yml"
app_version = "2.0.0-beta2"
if version_yml.exists():
    datas.append((str(version_yml), "."))
    try:
        import re

        m = re.search(r"version:\s*([^\s]+)", version_yml.read_text(encoding="utf-8"))
        if m:
            app_version = m.group(1).strip()
    except Exception:
        pass

# On Linux, include the desktop integration icon for runtime use (e.g. fallback
# for setWindowIcon when the icons/ directory lookup fails in frozen builds).
if not _IS_WIN32:
    _linux_icon = repo_root / "packaging" / "linux" / "kikumoe.png"
    if _linux_icon.exists():
        datas.append((str(_linux_icon), "icons"))

# VLC bundling (Windows: bundle DLLs; Linux: system-installed VLC is used directly)
vlc_binaries = []
if _IS_WIN32:
    vlc_dir = Path(os.environ.get("VLC_DIR") or r"C:\Program Files\VideoLAN\VLC")
    libvlc = vlc_dir / "libvlc.dll"
    libvlccore = vlc_dir / "libvlccore.dll"
    plugins_dir = vlc_dir / "plugins"
    if libvlc.exists():
        vlc_binaries.append((str(libvlc), "."))
        if libvlccore.exists():
            vlc_binaries.append((str(libvlccore), "."))
        if plugins_dir.is_dir():
            datas.append((str(plugins_dir), "plugins"))
            
    # Include the MPV DLL and its sibling runtime dependencies.
    vlc_binaries.extend((str(dll), ".") for dll in sorted(packaging_win.glob("*.dll")))

block_cipher = None

a = Analysis(
    [str(repo_root / "KikuMoe.py")],
    pathex=[str(repo_root)],
    binaries=vlc_binaries,
    datas=datas,
    hiddenimports=["certifi", "mpv"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(repo_root / "pyi_rthook_vlc.py")],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "sqlite3",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuickWidgets",
        "PyQt6.QtPdf",
        "PyQt6.QtPdfWidgets",
        "PyQt6.QtSql",
        "PyQt6.QtXml",
        "PyQt6.QtBluetooth",
        "PyQt6.QtTest",
        "PyQt6.QtSensors",
        "PyQt6.QtPositioning",
        "PyQt6.QtWebChannel",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtNfc",
        "PyQt6.QtRemoteObjects",
        "PyQt6.QtSpatialAudio",
        "PyQt6.QtPrintSupport",
        "PyQt6.QtDesigner",
        "PyQt6.QtHelp",
        "PyQt6.QtCharts",
        "PyQt6.QtOpenGLWidgets",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

# Filter out unused Qt translation files (*.qm) from a.datas to optimize bundle size
a.datas = [
    d
    for d in a.datas
    if not (
        d[0].endswith(".qm")
        or "translations" in d[1].replace("\\", "/").split("/")
        or "translations" in d[0].replace("\\", "/").split("/")
    )
]
# On Linux, exclude low-level host audio system libraries (ALSA, PulseAudio, JACK, VLC)
# and standard C++ runtimes (libstdc++, libgcc_s) per AppImage standards.
# When bundled into PyInstaller/AppImage, these libraries conflict with the host's
# ALSA plugins, PipeWire, and PulseAudio daemons, causing audio initialization to fail.
# Excluding them forces the application to load them directly from the host system.
if not _IS_WIN32:
    _linux_audio_excludes = (
        "libvlc",
        "libvlccore",
        "libasound",
        "libpulse",
        "libpulse-simple",
        "libpulsecommon",
        "libjack",
        "libpipewire",
        "libspa",
        "libasound_module",
        "libstdc++",
        "libgcc_s",
    )
    a.binaries = [
        b for b in a.binaries
        if not any(b[0].startswith(prefix) for prefix in _linux_audio_excludes)
    ]

# Note: Static ffmpeg on Linux is bundled into AppDir usr/bin/ffmpeg (or next to the
# executable) rather than packed inside a.binaries, saving ~90MB of duplication.
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Windows-only EXE metadata (icon, version resource, manifest)
exe_kwargs = {}
if _IS_WIN32:
    ico = packaging_win / "KikuMoe.ico"
    ver = packaging_win / "version_info.txt"
    mfst = packaging_win / "KikuMoe.manifest"
    print(f"\n[BUILD DIAGNOSTICS]")
    print(f" - Icon path: {ico} (Exists: {ico.exists()})")
    print(f" - Version path: {ver} (Exists: {ver.exists()})")
    print(f" - Manifest path: {mfst} (Exists: {mfst.exists()})\n")
    if ico.exists():
        exe_kwargs["icon"] = str(ico)
    if ver.exists():
        exe_kwargs["version"] = str(ver)
    if mfst.exists():
        exe_kwargs["manifest"] = str(mfst)

    # Windows build: single executable (onefile)
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        name=f"KikuMoe-{app_version}",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        argv_emulation=False,
        **exe_kwargs,
    )
else:
    # Linux build: directory mode (onedir) to avoid redundant extraction and compression
    # inside AppImage SquashFS. Output: dist/KikuMoe/KikuMoe and dist/KikuMoe/_internal/
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="KikuMoe",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        argv_emulation=False,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        name="KikuMoe",
    )
