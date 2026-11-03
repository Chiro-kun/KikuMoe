"""Over-The-Air (OTA) update checking and release asset download for KikuMoe.

Provides semantic version comparison, GitHub Releases API integration,
release channel filtering (Stable vs. Beta), and asynchronous Qt workers.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from core.constants import (
    APP_VERSION,
    UPDATE_CHANNEL_BETA,
    UPDATE_CHANNEL_STABLE,
    URL_GITHUB_API_RELEASES,
)
from core.ssl_compat import get_ssl_context

logger = logging.getLogger("kikumoe.updater")

_IS_WIN32 = sys.platform == "win32" or platform.system() == "Windows"


@dataclass(order=False)
class SemVer:
    """Semantic Version representation with pre-release tag support."""

    major: int
    minor: int
    patch: int
    prerelease_type: str = ""  # e.g. "beta", "alpha", "rc"
    prerelease_num: int = 0  # e.g. 4 for beta4
    raw: str = ""

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease_type)

    @classmethod
    def parse(cls, version_str: str) -> SemVer:
        """Parse semver string (e.g. 'v2.0.0-beta4', '2.0.0', '1.11.0')."""
        clean = version_str.strip().lstrip("vV")
        # Split pre-release suffix
        parts = clean.split("-", 1)
        core = parts[0]
        core_nums = [int(n) for n in re.findall(r"\d+", core)]
        major = core_nums[0] if len(core_nums) > 0 else 0
        minor = core_nums[1] if len(core_nums) > 1 else 0
        patch = core_nums[2] if len(core_nums) > 2 else 0

        pre_type = ""
        pre_num = 0
        if len(parts) > 1:
            pre_str = parts[1]
            # Match word tag and optional number e.g. "beta4", "beta.4", "rc1"
            m = re.search(r"([a-zA-Z]+)[.\-_]?(\d*)", pre_str)
            if m:
                pre_type = m.group(1).lower()
                pre_num = int(m.group(2)) if m.group(2) else 0
            else:
                pre_type = pre_str.lower()

        return cls(
            major=major,
            minor=minor,
            patch=patch,
            prerelease_type=pre_type,
            prerelease_num=pre_num,
            raw=version_str,
        )

    def _sort_key(self) -> tuple[int, int, int, int, str, int]:
        # Pre-releases are older than stable releases of the same core version!
        # e.g. 2.0.0-beta4 < 2.0.0.
        # We use 0 for pre-release, 1 for final/stable release.
        is_stable = 0 if self.is_prerelease else 1
        return (
            self.major,
            self.minor,
            self.patch,
            is_stable,
            self.prerelease_type,
            self.prerelease_num,
        )

    def __lt__(self, other: SemVer) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._sort_key() < other._sort_key()

    def __le__(self, other: SemVer) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._sort_key() <= other._sort_key()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return False
        return self._sort_key() == other._sort_key()

    def __gt__(self, other: SemVer) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._sort_key() > other._sort_key()

    def __ge__(self, other: SemVer) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._sort_key() >= other._sort_key()


@dataclass
class ReleaseAsset:
    """Individual downloadable asset in a GitHub release."""

    name: str
    download_url: str
    size_bytes: int
    content_type: str = ""

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / (1024 * 1024), 1)


@dataclass
class ReleaseInfo:
    """Parsed release information from GitHub Releases."""

    tag_name: str
    version_str: str
    semver: SemVer
    title: str
    body: str  # Markdown changelog
    published_at: str
    html_url: str
    is_prerelease: bool
    assets: list[ReleaseAsset] = field(default_factory=list)

    def get_platform_asset(self) -> ReleaseAsset | None:
        """Find the most appropriate asset for the current OS."""
        if _IS_WIN32:
            # Prefer Windows installer/exe, then zip
            for ext in (".exe", ".zip"):
                for a in self.assets:
                    if a.name.lower().endswith(ext):
                        return a
        else:
            # Linux: prefer AppImage, then tar.gz / deb
            for ext in (".appimage", ".tar.gz", ".deb"):
                for a in self.assets:
                    if a.name.lower().endswith(ext):
                        return a
        return self.assets[0] if self.assets else None


def fetch_github_releases(
    url: str = URL_GITHUB_API_RELEASES,
    timeout: float = 8.0,
) -> list[dict]:
    """Fetch releases list from GitHub API using pure Python standard library."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"KikuMoe/{APP_VERSION}",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    ctx = get_ssl_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        data = resp.read().decode("utf-8")
        parsed = json.loads(data)
        if isinstance(parsed, list):
            return parsed
        return []


def parse_releases(
    raw_releases: list[dict], channel: str = UPDATE_CHANNEL_BETA
) -> list[ReleaseInfo]:
    """Parse raw GitHub release dictionaries into sorted ReleaseInfo objects."""
    results: list[ReleaseInfo] = []
    for item in raw_releases:
        if not isinstance(item, dict):
            continue
        tag = item.get("tag_name", "").strip()
        if not tag:
            continue
        is_prerelease = bool(item.get("prerelease", False))

        # Channel filtering: if stable channel, skip prereleases
        if channel == UPDATE_CHANNEL_STABLE and is_prerelease:
            continue

        semver = SemVer.parse(tag)
        assets: list[ReleaseAsset] = []
        for raw_asset in item.get("assets", []):
            if not isinstance(raw_asset, dict):
                continue
            name = raw_asset.get("name", "")
            download_url = raw_asset.get("browser_download_url", "")
            size = int(raw_asset.get("size", 0))
            ctype = raw_asset.get("content_type", "")
            if name and download_url:
                assets.append(
                    ReleaseAsset(
                        name=name,
                        download_url=download_url,
                        size_bytes=size,
                        content_type=ctype,
                    )
                )

        results.append(
            ReleaseInfo(
                tag_name=tag,
                version_str=tag.lstrip("vV"),
                semver=semver,
                title=item.get("name", "") or tag,
                body=item.get("body", "") or "",
                published_at=item.get("published_at", "") or "",
                html_url=item.get("html_url", "") or "",
                is_prerelease=is_prerelease,
                assets=assets,
            )
        )

    # Sort newest first
    results.sort(key=lambda r: r.semver, reverse=True)
    return results


def check_for_updates(
    current_version: str = APP_VERSION,
    channel: str = UPDATE_CHANNEL_BETA,
    ignored_version: str = "",
    url: str = URL_GITHUB_API_RELEASES,
    timeout: float = 8.0,
) -> ReleaseInfo | None:
    """Check if a newer release is available on GitHub for the given channel."""
    try:
        raw_releases = fetch_github_releases(url=url, timeout=timeout)
        parsed = parse_releases(raw_releases, channel=channel)
        if not parsed:
            return None

        newest = parsed[0]
        current_semver = SemVer.parse(current_version)

        # Check if remote version is strictly newer
        if newest.semver > current_semver:
            if ignored_version and newest.tag_name == ignored_version:
                logger.info("[UPDATER] Release %s is ignored by user preference.", newest.tag_name)
                return None
            return newest
        return None
    except Exception as e:
        logger.warning("[UPDATER] Update check failed: %s", e)
        raise


class UpdateCheckWorker(QThread):
    """Background worker for non-blocking update checking."""

    update_available = pyqtSignal(object)  # ReleaseInfo
    up_to_date = pyqtSignal(str)  # current_version
    check_failed = pyqtSignal(str)  # error_str

    def __init__(
        self,
        current_version: str = APP_VERSION,
        channel: str = UPDATE_CHANNEL_BETA,
        ignored_version: str = "",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.current_version = current_version
        self.channel = channel
        self.ignored_version = ignored_version

    def run(self) -> None:
        try:
            update = check_for_updates(
                current_version=self.current_version,
                channel=self.channel,
                ignored_version=self.ignored_version,
            )
            if update is not None:
                self.update_available.emit(update)
            else:
                self.up_to_date.emit(self.current_version)
        except Exception as e:
            self.check_failed.emit(str(e))


class AssetDownloadWorker(QThread):
    """Background worker to download a release asset with progress reporting."""

    progress = pyqtSignal(int, int)  # (downloaded_bytes, total_bytes)
    finished = pyqtSignal(str)  # local_file_path
    error = pyqtSignal(str)  # error_message

    def __init__(
        self,
        asset: ReleaseAsset,
        destination_dir: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.asset = asset
        if destination_dir is None:
            # Default to user's Downloads or temp folder
            downloads = Path.home() / "Downloads"
            self.destination_dir = downloads if downloads.is_dir() else Path(os.getcwd())
        else:
            self.destination_dir = destination_dir
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            target_file = self.destination_dir / self.asset.name
            req = urllib.request.Request(
                self.asset.download_url,
                headers={"User-Agent": f"KikuMoe/{APP_VERSION}"},
            )
            ctx = get_ssl_context()

            with urllib.request.urlopen(req, timeout=15.0, context=ctx) as resp:
                total_bytes = int(resp.headers.get("Content-Length", self.asset.size_bytes))
                downloaded = 0
                chunk_size = 65536  # 64 KB

                with open(target_file, "wb") as f:
                    while not self._cancelled:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(downloaded, total_bytes)

            if self._cancelled:
                if target_file.exists():
                    try:
                        target_file.unlink()
                    except Exception:
                        pass
                return

            self.finished.emit(str(target_file))
        except Exception as e:
            logger.error("[UPDATER] Asset download failed: %s", e)
            self.error.emit(str(e))
