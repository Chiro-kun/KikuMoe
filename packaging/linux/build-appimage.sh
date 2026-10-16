#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build-appimage.sh — Assemble a KikuMoe AppImage from the PyInstaller binary
#
# Usage:
#   ./packaging/linux/build-appimage.sh [binary]
#
# If [binary] is omitted the script looks for dist/KikuMoe-* in the repo root.
# Requires: wget (or curl), file, and FUSE (or --appimage-extract-and-run).
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Read version from version.yml
VERSION="$(grep -oP '(?<=version:\s).+' "$REPO_ROOT/version.yml" | tr -d '[:space:]')"
if [[ -z "$VERSION" ]]; then
    echo "ERROR: Could not read version from version.yml" >&2
    exit 1
fi
echo "Building AppImage for KikuMoe v${VERSION}"

# Locate the PyInstaller binary
BINARY="${1:-}"
if [[ -z "$BINARY" ]]; then
    BINARY="$(ls "$REPO_ROOT/dist/KikuMoe-"* 2>/dev/null | head -1 || true)"
fi
if [[ -z "$BINARY" || ! -f "$BINARY" ]]; then
    echo "ERROR: PyInstaller binary not found. Run build.sh first or pass the path." >&2
    exit 1
fi
BINARY="$(readlink -f "$BINARY")"
echo "Using binary: $BINARY"

# Paths
APPDIR="$REPO_ROOT/dist/KikuMoe.AppDir"
LINUX_PKG="$REPO_ROOT/packaging/linux"
APPIMAGETOOL="$REPO_ROOT/dist/appimagetool"
OUTPUT="$REPO_ROOT/dist/KikuMoe-${VERSION}-x86_64.AppImage"
ARCH="${APPIMAGE_ARCH:-x86_64}"

# Clean previous AppDir
rm -rf "$APPDIR"

# Create AppDir structure
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/metainfo"

# Copy the PyInstaller binary
cp "$BINARY" "$APPDIR/usr/bin/KikuMoe"
chmod +x "$APPDIR/usr/bin/KikuMoe"

# Desktop file and icon at AppDir root (required by appimagetool)
cp "$LINUX_PKG/me.chiro.kikumoe.desktop" "$APPDIR/me.chiro.kikumoe.desktop"
cp "$LINUX_PKG/kikumoe.png" "$APPDIR/kikumoe.png"

# Desktop file and icon in FreeDesktop locations (for proper integration)
cp "$LINUX_PKG/me.chiro.kikumoe.desktop" "$APPDIR/usr/share/applications/"
cp "$LINUX_PKG/kikumoe.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/"

# AppStream metadata (appimagetool looks for .appdata.xml; AppStream spec uses .metainfo.xml)
mkdir -p "$APPDIR/usr/share/appdata"
if [[ -f "$LINUX_PKG/me.chiro.kikumoe.metainfo.xml" ]]; then
    cp "$LINUX_PKG/me.chiro.kikumoe.metainfo.xml" "$APPDIR/usr/share/metainfo/me.chiro.kikumoe.metainfo.xml"
    cp "$LINUX_PKG/me.chiro.kikumoe.metainfo.xml" "$APPDIR/usr/share/metainfo/me.chiro.kikumoe.appdata.xml"
    cp "$LINUX_PKG/me.chiro.kikumoe.metainfo.xml" "$APPDIR/usr/share/appdata/me.chiro.kikumoe.appdata.xml"
elif [[ -f "$LINUX_PKG/me.chiro.kikumoe.appdata.xml" ]]; then
    cp "$LINUX_PKG/me.chiro.kikumoe.appdata.xml" "$APPDIR/usr/share/metainfo/me.chiro.kikumoe.appdata.xml"
    cp "$LINUX_PKG/me.chiro.kikumoe.appdata.xml" "$APPDIR/usr/share/metainfo/me.chiro.kikumoe.metainfo.xml"
    cp "$LINUX_PKG/me.chiro.kikumoe.appdata.xml" "$APPDIR/usr/share/appdata/me.chiro.kikumoe.appdata.xml"
fi

# Create AppRun
cat > "$APPDIR/AppRun" << 'APPRUN_EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/KikuMoe" "$@"
APPRUN_EOF
chmod +x "$APPDIR/AppRun"

# Download appimagetool if not present
if [[ ! -x "$APPIMAGETOOL" ]]; then
    echo "Downloading appimagetool..."
    TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    if command -v wget &>/dev/null; then
        wget -q -O "$APPIMAGETOOL" "$TOOL_URL"
    elif command -v curl &>/dev/null; then
        curl -fsSL -o "$APPIMAGETOOL" "$TOOL_URL"
    else
        echo "ERROR: wget or curl is required to download appimagetool" >&2
        exit 1
    fi
    chmod +x "$APPIMAGETOOL"
fi

# Build the AppImage
echo "Running appimagetool..."
export ARCH
# Use --appimage-extract-and-run in case FUSE is not available (e.g. CI containers)
"$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "$OUTPUT"

echo ""
echo "AppImage created: $OUTPUT"
echo "Size: $(du -h "$OUTPUT" | cut -f1)"

