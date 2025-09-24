# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

# Project layout (use current working directory as project root)
project_root = Path(os.path.abspath('.'))
src_dir = project_root / "KikuMoe"
icon_dir = src_dir / "icons"

# Collect icons folder preserving structure under the app root (icons/...)
datas = []
if icon_dir.is_dir():
    for root, _, files in os.walk(icon_dir):
        for f in files:
            full = Path(root) / f
            dest = str(Path(root).relative_to(src_dir))  # e.g. "icons" or "icons/subdir"
            datas.append((str(full), dest))

# Force ONEFILE build
onefile = True

# Zero-config VLC bundling (optional if VLC not found)
vlc_binaries = []
vlc_dir = os.environ.get('VLC_DIR') or r'C:\\Program Files\\VideoLAN\\VLC'
libvlc = Path(vlc_dir) / 'libvlc.dll'
libvlccore = Path(vlc_dir) / 'libvlccore.dll'
plugins_dir = Path(vlc_dir) / 'plugins'
if libvlc.exists():
    vlc_binaries.append((str(libvlc), '.'))
    if libvlccore.exists():
        vlc_binaries.append((str(libvlccore), '.'))
    if plugins_dir.is_dir():
        # In onefile, include plugins via datas so they extract under _MEIPASS/plugins
        datas.append((str(plugins_dir), 'plugins'))

block_cipher = None


a = Analysis(
    [str(src_dir / "KikuMoe.py")],
    pathex=[str(src_dir)],
    binaries=vlc_binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(src_dir / "pyi_rthook_vlc.py")],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Build ONEFILE: embed binaries/zipfiles/datas directly into EXE, no COLLECT
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='KikuMoe-1.8.2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='KikuMoe.ico',
    version=str(project_root / 'version_info.txt'),
    argv_emulation=False,
    manifest='KikuMoe.manifest',
)