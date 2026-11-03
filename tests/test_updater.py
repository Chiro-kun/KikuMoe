from __future__ import annotations

import unittest
from unittest.mock import patch

from core.updater import (
    SemVer,
    check_for_updates,
    parse_releases,
)


class TestSemVer(unittest.TestCase):
    def test_semver_parsing(self):
        v1 = SemVer.parse("2.0.0-beta4")
        self.assertEqual(v1.major, 2)
        self.assertEqual(v1.minor, 0)
        self.assertEqual(v1.patch, 0)
        self.assertEqual(v1.prerelease_type, "beta")
        self.assertEqual(v1.prerelease_num, 4)
        self.assertTrue(v1.is_prerelease)

        v2 = SemVer.parse("v2.0.0")
        self.assertEqual(v2.major, 2)
        self.assertEqual(v2.minor, 0)
        self.assertEqual(v2.patch, 0)
        self.assertFalse(v2.is_prerelease)

        v3 = SemVer.parse("1.11.0")
        self.assertEqual(v3.major, 1)
        self.assertEqual(v3.minor, 11)
        self.assertEqual(v3.patch, 0)
        self.assertFalse(v3.is_prerelease)

    def test_semver_ordering(self):
        v_beta3 = SemVer.parse("2.0.0-beta3")
        v_beta4 = SemVer.parse("2.0.0-beta4")
        v_beta5 = SemVer.parse("2.0.0-beta5")
        v_stable = SemVer.parse("2.0.0")
        v_old = SemVer.parse("1.11.0")
        v_next = SemVer.parse("2.0.1-beta1")

        self.assertTrue(v_old < v_beta3)
        self.assertTrue(v_beta3 < v_beta4)
        self.assertTrue(v_beta4 < v_beta5)
        # Beta is older than final stable of the same version!
        self.assertTrue(v_beta5 < v_stable)
        self.assertTrue(v_stable < v_next)
        self.assertEqual(SemVer.parse("v2.0.0"), SemVer.parse("2.0.0"))


class TestReleaseParsing(unittest.TestCase):
    def setUp(self):
        self.mock_releases = [
            {
                "tag_name": "v2.0.0-beta5",
                "name": "KikuMoe 2.0.0-beta5",
                "body": "Changelog for beta 5",
                "prerelease": True,
                "published_at": "2026-11-05T10:00:00Z",
                "html_url": "https://github.com/Chiro-kun/KikuMoe/releases/tag/v2.0.0-beta5",
                "assets": [
                    {
                        "name": "KikuMoe-2.0.0-beta5-Windows-x64.exe",
                        "browser_download_url": "https://example.com/app.exe",
                        "size": 50000000,
                        "content_type": "application/octet-stream",
                    },
                    {
                        "name": "KikuMoe-2.0.0-beta5-x86_64.AppImage",
                        "browser_download_url": "https://example.com/app.AppImage",
                        "size": 45000000,
                        "content_type": "application/x-executable",
                    },
                ],
            },
            {
                "tag_name": "v2.0.0-beta4",
                "name": "KikuMoe 2.0.0-beta4",
                "body": "Changelog for beta 4",
                "prerelease": True,
                "published_at": "2026-11-03T10:00:00Z",
                "html_url": "https://github.com/Chiro-kun/KikuMoe/releases/tag/v2.0.0-beta4",
                "assets": [],
            },
            {
                "tag_name": "v1.11.0",
                "name": "KikuMoe 1.11.0",
                "body": "Old stable release",
                "prerelease": False,
                "published_at": "2026-08-01T10:00:00Z",
                "html_url": "https://github.com/Chiro-kun/KikuMoe/releases/tag/v1.11.0",
                "assets": [],
            },
        ]

    def test_parse_beta_channel(self):
        parsed = parse_releases(self.mock_releases, channel="beta")
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0].tag_name, "v2.0.0-beta5")
        self.assertEqual(parsed[1].tag_name, "v2.0.0-beta4")
        self.assertEqual(parsed[2].tag_name, "v1.11.0")

    def test_parse_stable_channel(self):
        parsed = parse_releases(self.mock_releases, channel="stable")
        # Should exclude prerelease v2.0.0-beta5 and v2.0.0-beta4
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].tag_name, "v1.11.0")

    def test_platform_asset_resolution(self):
        parsed = parse_releases(self.mock_releases, channel="beta")
        rel = parsed[0]
        with patch("core.updater._IS_WIN32", True):
            asset_win = rel.get_platform_asset()
            self.assertIsNotNone(asset_win)
            self.assertTrue(asset_win.name.endswith(".exe"))

        with patch("core.updater._IS_WIN32", False):
            asset_linux = rel.get_platform_asset()
            self.assertIsNotNone(asset_linux)
            self.assertTrue(asset_linux.name.endswith(".AppImage"))

    @patch("core.updater.fetch_github_releases")
    def test_check_for_updates_found(self, mock_fetch):
        mock_fetch.return_value = self.mock_releases
        # If current version is 2.0.0-beta4, beta5 should be found in beta channel
        up = check_for_updates(current_version="2.0.0-beta4", channel="beta")
        self.assertIsNotNone(up)
        self.assertEqual(up.tag_name, "v2.0.0-beta5")

    @patch("core.updater.fetch_github_releases")
    def test_check_for_updates_already_up_to_date(self, mock_fetch):
        mock_fetch.return_value = self.mock_releases
        # If current version is 2.0.0-beta5, no newer update
        up = check_for_updates(current_version="2.0.0-beta5", channel="beta")
        self.assertIsNone(up)

    @patch("core.updater.fetch_github_releases")
    def test_check_for_updates_ignored(self, mock_fetch):
        mock_fetch.return_value = self.mock_releases
        up = check_for_updates(
            current_version="2.0.0-beta4", channel="beta", ignored_version="v2.0.0-beta5"
        )
        self.assertIsNone(up)

    def test_update_dialog_creation(self):
        from PyQt6.QtWidgets import QApplication

        from ui.update_dialog import UpdateDialog

        _ = QApplication.instance() or QApplication([])
        parsed = parse_releases(self.mock_releases, channel="beta")
        dialog = UpdateDialog(release=parsed[0])
        self.assertEqual(dialog.release.tag_name, "v2.0.0-beta5")
        self.assertTrue(dialog.release.is_prerelease)
        dialog.close()
        dialog.deleteLater()
