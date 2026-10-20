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
app_version = "1.11.0"
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
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(repo_root / "pyi_rthook_vlc.py")],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)
# On Linux, PyInstaller auto-detects libvlc.so.5 / libvlccore.so.9 via ctypes
# analysis and bundles them — but without the full VLC plugin tree and runtime
# dependencies (libdbus, libsystemd, audio plugins…), the bundled copy cannot
# initialise audio output.  Remove them so the system-installed VLC is used
# end-to-end, which is what the comment above already intends.
if not _IS_WIN32:
    a.binaries = [b for b in a.binaries if not b[0].startswith(("libvlc", "libvlccore"))]

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
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    argv_emulation=False,
    **exe_kwargs,
)
