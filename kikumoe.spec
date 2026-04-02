# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

_IS_WIN32 = sys.platform == "win32"

# Spec lives at the repo root — all paths resolve from here
repo_root = Path(globals().get("SPECPATH", os.path.abspath("."))).resolve()

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
if version_yml.exists():
    datas.append((str(version_yml), "."))

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
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Windows-only EXE metadata (icon, version resource, manifest)
exe_kwargs = {}
if _IS_WIN32:
    packaging_win = repo_root / "packaging" / "windows"
    ico = packaging_win / "KikuMoe.ico"
    ver = packaging_win / "version_info.txt"
    mfst = packaging_win / "KikuMoe.manifest"
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
    name="KikuMoe-1.9.0",
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
