"""Tests for TrayManager and icon rendering in KikuMoe 1.11.1."""

import os

import pytest
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QApplication, QWidget

from core.i18n import I18n
from ui.main_window import ListenMoePlayer
from ui.tray_manager import TrayManager


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest"])
    return app


def test_tint_icon_optical_normalization(qapp):
    player = ListenMoePlayer.__new__(ListenMoePlayer)

    # Test with app_stop.png (which previously had 37% empty padding and shrank to 5px)
    icon_path = os.path.join("icons", "app_stop.png")
    raw_icon = QIcon(icon_path)
    tinted = player._tint_icon(raw_icon, QColor("#ec186c"))

    assert not tinted.isNull()
    # Check 16x16 pixmap
    pm16 = tinted.pixmap(16, 16)
    assert not pm16.isNull()
    img16 = pm16.toImage()

    # Measure non-transparent bounds in 16x16
    min_x, max_x = 16, 0
    min_y, max_y = 16, 0
    for y in range(16):
        for x in range(16):
            if img16.pixelColor(x, y).alpha() > 10:
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)

    content_w = max_x - min_x + 1
    content_h = max_y - min_y + 1

    # Content must occupy at least 11px (not 5px as in the bug)
    assert content_w >= 11
    assert content_h >= 11

    # Check horizontal & vertical centering (margins within 1px)
    left_m = min_x
    right_m = 16 - 1 - max_x
    top_m = min_y
    bottom_m = 16 - 1 - max_y
    assert abs(left_m - right_m) <= 1
    assert abs(top_m - bottom_m) <= 1


def test_tray_manager_icons_and_submenus(qapp):
    win = QWidget()
    i18n = I18n("it")
    tray = TrayManager(win, i18n)
    tray.ensure_tray_enabled(True, tooltip="Line0\nLine1\nLine2")

    dummy_icon = QIcon(os.path.join("icons", "app_stop.png"))
    icons = {
        "play": dummy_icon,
        "pause": dummy_icon,
        "stop": dummy_icon,
        "mute": dummy_icon,
        "unmute": dummy_icon,
        "force_stop": dummy_icon,
        "channel": dummy_icon,
        "codec": dummy_icon,
        "quit": dummy_icon,
    }
    tray.update_controls_icons(icons)

    assert not tray._act_play_pause.icon().isNull()
    assert not tray._act_stop.icon().isNull()
    assert not tray._act_mute.icon().isNull()
    assert not tray._act_quit.icon().isNull()
    assert not tray._act_ch.icon().isNull()
    assert not tray._act_fmt.icon().isNull()

    # Submenus are properly parented to context menu
    menu = tray._tray.contextMenu()
    assert tray._act_ch.menu().parent() is menu
    assert tray._act_fmt.menu().parent() is menu
