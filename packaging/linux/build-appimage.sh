#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build-appimage.sh — Assemble a KikuMoe AppImage from the PyInstaller onedir bundle
#
# Usage:
#   ./packaging/linux/build-appimage.sh [bundle_directory]
#
# Defaults to dist/KikuMoe if bundle_directory is omitted.
# Requires: wget (or curl), file, sha256sum, and appimagetool.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Read version from version.yml
VERSION="$(sed -nE 's/^version:[[:space:]]*"?([^"[:space:]]+)"?.*/\1/p' "$REPO_ROOT/version.yml" | head -1)"
if [[ -z "$VERSION" ]]; then
    echo "ERROR: Could not read version from version.yml" >&2
    exit 1
fi
echo "Building AppImage for KikuMoe v${VERSION}"

# Locate and validate PyInstaller onedir bundle
BUNDLE="${1:-$REPO_ROOT/dist/KikuMoe}"
if [[ ! -d "$BUNDLE" || ! -x "$BUNDLE/KikuMoe" ]]; then
    echo "ERROR: Bundle directory '$BUNDLE' does not contain executable 'KikuMoe'." >&2
    echo "Run build.sh first or pass the bundle path." >&2
    exit 1
fi
BUNDLE="$(readlink -f "$BUNDLE")"
echo "Using onedir bundle: $BUNDLE"

# Paths
APPDIR="$REPO_ROOT/dist/KikuMoe.AppDir"
LINUX_PKG="$REPO_ROOT/packaging/linux"
APPIMAGETOOL="$REPO_ROOT/dist/appimagetool"
APPIMAGETOOL_VERSION="1.9.1"
APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_VERSION}/appimagetool-x86_64.AppImage"
OUTPUT="$REPO_ROOT/dist/KikuMoe-${VERSION}-x86_64.AppImage"
ARCH="${APPIMAGE_ARCH:-x86_64}"

# Clean previous AppDir
rm -rf "$APPDIR"

# Create AppDir structure
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/metainfo"

# Copy the entire onedir bundle into usr/bin
echo "Populating AppDir from $BUNDLE..."
cp -a "$BUNDLE/." "$APPDIR/usr/bin/"
chmod +x "$APPDIR/usr/bin/KikuMoe"

# Bundle static ffmpeg into AppDir usr/bin (co-located with KikuMoe executable)
if [[ -f "$LINUX_PKG/ffmpeg" ]]; then
    echo "Bundling static ffmpeg into AppDir usr/bin..."
    cp "$LINUX_PKG/ffmpeg" "$APPDIR/usr/bin/ffmpeg"
    chmod +x "$APPDIR/usr/bin/ffmpeg"
elif [[ -f "$BUNDLE/ffmpeg" ]]; then
    echo "Bundling ffmpeg from bundle into AppDir usr/bin..."
    cp "$BUNDLE/ffmpeg" "$APPDIR/usr/bin/ffmpeg"
    chmod +x "$APPDIR/usr/bin/ffmpeg"
elif command -v ffmpeg &>/dev/null; then
    echo "Copying host ffmpeg into AppDir usr/bin..."
    cp "$(command -v ffmpeg)" "$APPDIR/usr/bin/ffmpeg"
    chmod +x "$APPDIR/usr/bin/ffmpeg"
else
    echo "ERROR: ffmpeg not found in $LINUX_PKG/ffmpeg, bundle or system PATH." >&2
    exit 1
fi

# Ensure ffmpeg is accessible both from usr/bin and internal package dir
if [[ -d "$APPDIR/usr/bin/_internal" && ! -f "$APPDIR/usr/bin/_internal/ffmpeg" ]]; then
    ln -s ../ffmpeg "$APPDIR/usr/bin/_internal/ffmpeg" 2>/dev/null || cp "$APPDIR/usr/bin/ffmpeg" "$APPDIR/usr/bin/_internal/ffmpeg"
fi

# Desktop file and icon at AppDir root (required by appimagetool)
cp "$LINUX_PKG/me.chiro.kikumoe.desktop" "$APPDIR/me.chiro.kikumoe.desktop"
cp "$LINUX_PKG/kikumoe.png" "$APPDIR/kikumoe.png"

# Desktop file and icon in FreeDesktop locations (for proper integration)
cp "$LINUX_PKG/me.chiro.kikumoe.desktop" "$APPDIR/usr/share/applications/"
cp "$LINUX_PKG/kikumoe.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/"

# AppStream metadata: single standard copy in usr/share/metainfo/
if [[ -f "$LINUX_PKG/me.chiro.kikumoe.metainfo.xml" ]]; then
    cp "$LINUX_PKG/me.chiro.kikumoe.metainfo.xml" "$APPDIR/usr/share/metainfo/me.chiro.kikumoe.metainfo.xml"
fi

# Create AppRun entrypoint
cat > "$APPDIR/AppRun" << 'APPRUN_EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"

# Ensure host CA certificates are discovered across Linux distros
if [ -z "$SSL_CERT_FILE" ]; then
    for cert in \
        /etc/ssl/certs/ca-certificates.crt \
        /etc/pki/tls/certs/ca-bundle.crt \
        /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem \
        /etc/ssl/ca-bundle.pem \
        /etc/ssl/cert.pem; do
        if [ -f "$cert" ]; then
            export SSL_CERT_FILE="$cert"
            break
        fi
    done
fi
if [ -z "$SSL_CERT_DIR" ]; then
    for cdir in /etc/ssl/certs /etc/pki/tls/certs; do
        if [ -d "$cdir" ]; then
            export SSL_CERT_DIR="$cdir"
            break
        fi
    done
fi
export PATH="$HERE/usr/bin:$PATH"
exec "$HERE/usr/bin/KikuMoe" "$@"
APPRUN_EOF
chmod +x "$APPDIR/AppRun"

# Download and verify appimagetool with pinned SHA256 if not present
if [[ ! -x "$APPIMAGETOOL" ]]; then
    echo "Downloading appimagetool v${APPIMAGETOOL_VERSION}..."
    TMP_TOOL="$(mktemp)"
    if command -v curl &>/dev/null; then
        curl -fsSL -o "$TMP_TOOL" "$APPIMAGETOOL_URL"
    elif command -v wget &>/dev/null; then
        wget -q -O "$TMP_TOOL" "$APPIMAGETOOL_URL"
    else
        echo "ERROR: curl or wget is required to download appimagetool" >&2
        exit 1
    fi

    echo "Verifying appimagetool SHA256 checksum..."
    echo "${APPIMAGETOOL_SHA256}  ${TMP_TOOL}" | sha256sum -c -
    mkdir -p "$(dirname "$APPIMAGETOOL")"
    mv "$TMP_TOOL" "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
fi

# Print footprint analysis before packaging into AppImage
echo ""
echo "=== AppDir Footprint Analysis ==="
if command -v du &>/dev/null; then
    echo "Total uncompressed AppDir size: $(du -sh "$APPDIR" | cut -f1)"
    echo ""
    echo "--- Top 30 Largest Files in AppDir ---"
    find "$APPDIR" -type f -exec du -h {} + 2>/dev/null | sort -rh 2>/dev/null | head -n 30 || true
    echo ""
    echo "--- Directory Breakdown (depth 2) ---"
    du -h -d 2 "$APPDIR" | sort -rh | head -10
fi
echo "=================================="
echo ""

# Build AppImage with Zstandard level 19 compression
echo "Running appimagetool with zstd level 19 compression..."
export ARCH
"$APPIMAGETOOL" --appimage-extract-and-run --comp zstd --mksquashfs-opt -Xcompression-level --mksquashfs-opt 19 "$APPDIR" "$OUTPUT"

echo ""
echo "AppImage created: $OUTPUT"
if command -v du &>/dev/null; then
    echo "Size: $(du -h "$OUTPUT" | cut -f1)"
fi
