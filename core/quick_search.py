"""Cross-platform quick search and external lookup handlers for KikuMoe."""

from __future__ import annotations

import os
import shutil
import sys
import urllib.parse

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication


def _build_search_query(title: str, artist: str = "") -> str:
    """Build a clean search query combining artist and title."""
    clean_artist = artist.strip()
    clean_title = title.strip()
    if clean_artist and clean_title:
        return f"{clean_artist} {clean_title}"
    return clean_title or clean_artist


def is_spotify_installed() -> bool:
    """Detect if Spotify desktop application is installed on the system."""
    if sys.platform == "win32":
        try:
            import winreg

            candidates = [
                (winreg.HKEY_CURRENT_USER, r"Software\Classes\spotify\shell\open\command"),
                (winreg.HKEY_CLASSES_ROOT, r"spotify\shell\open\command"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Classes\spotify\shell\open\command"),
            ]
            for root, subkey in candidates:
                try:
                    with winreg.OpenKey(root, subkey) as key:
                        val, _ = winreg.QueryValueEx(key, "")
                        if val:
                            return True
                except OSError:
                    pass
        except Exception:
            pass

        # Check standard Spotify install directories
        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")
        exe_paths = [
            os.path.join(appdata, "Spotify", "Spotify.exe"),
            os.path.join(localappdata, "Microsoft", "WindowsApps", "Spotify.exe"),
        ]
        return any(os.path.isfile(p) for p in exe_paths)

    elif sys.platform.startswith("linux"):
        if shutil.which("spotify"):
            return True
        # Check flatpak or snap
        if shutil.which("flatpak") and (
            os.path.exists("/var/lib/flatpak/app/com.spotify.Client")
            or os.path.exists(os.path.expanduser("~/.local/share/flatpak/app/com.spotify.Client"))
        ):
            return True
        if os.path.exists("/snap/bin/spotify"):
            return True
        return False

    elif sys.platform == "darwin":
        return os.path.exists("/Applications/Spotify.app")

    return False


def search_spotify(title: str, artist: str = "") -> bool:
    """Search for the track on Spotify (desktop app if installed, browser fallback)."""
    query = _build_search_query(title, artist)
    if not query:
        return False

    encoded = urllib.parse.quote(query)

    if is_spotify_installed():
        # Native Spotify desktop URI protocol
        url = QUrl(f"spotify:search:{encoded}")
        success = QDesktopServices.openUrl(url)
        if success:
            return True

    # Web browser fallback
    web_url = QUrl(f"https://open.spotify.com/search/{encoded}")
    return QDesktopServices.openUrl(web_url)


def search_youtube(title: str, artist: str = "") -> bool:
    """Search for the track on YouTube in default web browser."""
    query = _build_search_query(title, artist)
    if not query:
        return False

    encoded = urllib.parse.quote(query)
    return QDesktopServices.openUrl(QUrl(f"https://www.youtube.com/results?search_query={encoded}"))


def search_youtube_music(title: str, artist: str = "") -> bool:
    """Search for the track on YouTube Music in default web browser."""
    query = _build_search_query(title, artist)
    if not query:
        return False

    encoded = urllib.parse.quote(query)
    return QDesktopServices.openUrl(QUrl(f"https://music.youtube.com/search?q={encoded}"))


def search_apple_music(title: str, artist: str = "") -> bool:
    """Search for the track on Apple Music in default web browser."""
    query = _build_search_query(title, artist)
    if not query:
        return False

    encoded = urllib.parse.quote(query)
    return QDesktopServices.openUrl(QUrl(f"https://music.apple.com/search?term={encoded}"))


def copy_to_clipboard(text: str) -> bool:
    """Copy given text string to OS system clipboard."""
    clip = QApplication.clipboard()
    if clip is not None:
        clip.setText(text)
        return True
    return False
