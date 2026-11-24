"""Tests for Wayland compositor detection, IPC pin helpers, and detached Mini-HUD window."""

from __future__ import annotations

import json
import os
import subprocess
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication

from core import wayland_window


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest"])
    return app


def test_is_wayland_session_detection():
    assert wayland_window.is_wayland_session("wayland") is True
    assert wayland_window.is_wayland_session("wayland-egl") is True
    assert wayland_window.is_wayland_session("WAYLAND") is True
    assert wayland_window.is_wayland_session("xcb") is False
    assert wayland_window.is_wayland_session("windows") is False
    assert wayland_window.is_wayland_session("offscreen") is False
    assert wayland_window.is_wayland_session("") is False


def test_detect_wayland_compositor_and_support(monkeypatch):
    for var in ("NIRI_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE", "SWAYSOCK"):
        monkeypatch.delenv(var, raising=False)
    assert wayland_window.detect_wayland_compositor() == "other"
    assert wayland_window.supports_wayland_pin() is False

    monkeypatch.setenv("NIRI_SOCKET", "/run/user/1000/niri.sock")
    assert wayland_window.detect_wayland_compositor() == "niri"
    monkeypatch.setattr(
        wayland_window.shutil, "which", lambda name: "/usr/bin/niri" if name == "niri" else None
    )
    assert wayland_window.supports_wayland_pin() is True
    monkeypatch.setattr(wayland_window.shutil, "which", lambda name: None)
    assert wayland_window.supports_wayland_pin() is False

    monkeypatch.delenv("NIRI_SOCKET")
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "abc123")
    assert wayland_window.detect_wayland_compositor() == "hyprland"
    monkeypatch.setattr(
        wayland_window.shutil,
        "which",
        lambda name: "/usr/bin/hyprctl" if name == "hyprctl" else None,
    )
    assert wayland_window.supports_wayland_pin() is True

    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE")
    monkeypatch.setenv("SWAYSOCK", "/run/user/1000/sway.sock")
    assert wayland_window.detect_wayland_compositor() == "sway"
    monkeypatch.setattr(
        wayland_window.shutil,
        "which",
        lambda name: "/usr/bin/swaymsg" if name == "swaymsg" else None,
    )
    assert wayland_window.supports_wayland_pin() is True


def test_apply_wayland_pin_niri_idempotent_fallback_and_focus_guard(monkeypatch):
    calls: list[list[str]] = []

    def make_cp(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")

    # 1. Already floating when enabled=True -> idempotent no-op
    def run_already_floating(args, **kwargs):
        calls.append(list(args))
        if args[:3] == ["niri", "msg", "-j"]:
            return make_cp(
                0,
                json.dumps({"title": "KikuMoe Mini-HUD", "app_id": "kikumoe", "is_floating": True}),
            )
        return make_cp(0)

    monkeypatch.setattr(wayland_window.subprocess, "run", run_already_floating)
    assert wayland_window.apply_wayland_pin(True, compositor="niri") is True
    assert calls == [["niri", "msg", "-j", "focused-window"]]

    # 2. Currently floating when enabled=False -> moves to tiling
    calls.clear()
    assert wayland_window.apply_wayland_pin(False, compositor="niri") is True
    assert calls == [
        ["niri", "msg", "-j", "focused-window"],
        ["niri", "msg", "action", "move-window-to-tiling"],
    ]

    # 3. Older niri without move-window-to-floating -> falls back to toggle-window-floating
    calls.clear()

    def run_old_niri(args, **kwargs):
        calls.append(list(args))
        if args[:3] == ["niri", "msg", "-j"]:
            return make_cp(
                0,
                json.dumps(
                    {"title": "KikuMoe Mini-HUD", "app_id": "kikumoe", "is_floating": False}
                ),
            )
        if args[-1] == "move-window-to-floating":
            return make_cp(1)
        return make_cp(0)

    monkeypatch.setattr(wayland_window.subprocess, "run", run_old_niri)
    assert wayland_window.apply_wayland_pin(True, compositor="niri") is True
    assert calls == [
        ["niri", "msg", "-j", "focused-window"],
        ["niri", "msg", "action", "move-window-to-floating"],
        ["niri", "msg", "action", "toggle-window-floating"],
    ]

    # 4. Focus belongs to another app -> refuses to move unrelated window
    calls.clear()

    def run_other_focused(args, **kwargs):
        calls.append(list(args))
        return make_cp(
            0, json.dumps({"title": "Firefox", "app_id": "firefox", "is_floating": False})
        )

    monkeypatch.setattr(wayland_window.subprocess, "run", run_other_focused)
    assert wayland_window.apply_wayland_pin(True, compositor="niri") is False
    assert calls == [["niri", "msg", "-j", "focused-window"]]


def test_apply_wayland_pin_hyprland_and_sway(monkeypatch):
    calls: list[list[str]] = []

    def make_cp(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")

    # Hyprland: not floating & not pinned -> setfloating + pin
    def run_hypr(args, **kwargs):
        calls.append(list(args))
        if args[:2] == ["hyprctl", "activewindow"]:
            return make_cp(0, json.dumps({"floating": False, "pinned": False}))
        return make_cp(0)

    monkeypatch.setattr(wayland_window.subprocess, "run", run_hypr)
    assert wayland_window.apply_wayland_pin(True, compositor="hyprland") is True
    assert calls == [
        ["hyprctl", "activewindow", "-j"],
        ["hyprctl", "dispatch", "setfloating", "active"],
        ["hyprctl", "dispatch", "pin", "active"],
    ]

    # Hyprland: already unpinned when enabled=False -> no dispatch needed
    calls.clear()
    assert wayland_window.apply_wayland_pin(False, compositor="hyprland") is True
    assert calls == [["hyprctl", "activewindow", "-j"]]

    # Sway: enable & disable
    calls.clear()
    monkeypatch.setattr(
        wayland_window.subprocess,
        "run",
        lambda args, **kwargs: (calls.append(list(args)), make_cp(0))[1],
    )
    assert wayland_window.apply_wayland_pin(True, compositor="sway") is True
    assert wayland_window.apply_wayland_pin(False, compositor="sway") is True
    assert calls == [
        ["swaymsg", "floating enable; sticky enable"],
        ["swaymsg", "sticky disable"],
    ]

    # Unsupported compositor
    assert wayland_window.apply_wayland_pin(True, compositor="other") is False


def _make_wayland_player(qapp, monkeypatch, tmp_path, *, compositor: str, has_binary: bool):
    from ui import main_window

    cls = main_window.ListenMoePlayer
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(main_window, "QSettings", lambda *args: settings)
    monkeypatch.setattr(main_window, "_IS_LINUX", True)
    monkeypatch.setattr(main_window, "is_wayland_session", lambda: True)
    monkeypatch.setattr(main_window, "detect_wayland_compositor", lambda: compositor)
    monkeypatch.setattr(main_window, "supports_wayland_pin", lambda comp=None: has_binary)
    monkeypatch.setattr(cls, "_sync_clock_with_server", lambda self: None)
    monkeypatch.setattr(cls, "_init_audio_backend", lambda self: None)
    monkeypatch.setattr(cls, "_init_websocket", lambda self: None)
    monkeypatch.setattr(cls, "_init_tray", lambda self: None)
    monkeypatch.setattr(cls, "_init_system_media", lambda self: setattr(self, "system_media", None))
    monkeypatch.setattr(cls, "_init_extra_logic", lambda self: None)

    window = cls()
    window.player = SimpleNamespace(is_playing=lambda: True)
    window._current_title = "Wayland Song"
    window._current_artist = "Niri Artist"
    window.show()
    qapp.processEvents()
    return window, settings


def test_wayland_niri_detached_mini_hud_lifecycle_and_pin_ipc(qapp, monkeypatch, tmp_path):
    from ui.widgets.mini_hud import MiniHudWindow

    window, _settings = _make_wayland_player(
        qapp, monkeypatch, tmp_path, compositor="niri", has_binary=True
    )
    pin_calls: list[bool] = []
    monkeypatch.setattr(
        window, "_apply_wayland_pin_async", lambda enabled: pin_calls.append(enabled)
    )

    # On niri with unset preference, pin starts enabled and uses niri tooltip
    assert window.mini_hud.pin_button.isEnabled() is True
    assert window.mini_hud.pin_button.isChecked() is True
    assert window.mini_hud.pin_button.toolTip() == window.i18n.t("mini_pin_niri")

    # Entering Mini-HUD hides main window and opens dedicated fixed-size MiniHudWindow
    window.toggle_mini_hud()
    qapp.processEvents()
    assert window._mini_mode is True
    assert window.isVisible() is False
    assert isinstance(window._mini_window, MiniHudWindow)
    assert window._mini_window.isVisible() is True
    assert window._mini_window.windowTitle() == "KikuMoe Mini-HUD"
    assert window._mini_window.width() == MiniHudWindow.MINI_WIDTH
    assert window._mini_window.height() == MiniHudWindow.MINI_HEIGHT
    assert window._mini_window.minimumSize() == window._mini_window.maximumSize()
    assert window.mini_hud.parent() is window._mini_window
    assert window._is_any_ui_visible() is True

    # Toggling Pin invokes compositor IPC instead of WindowStaysOnTopHint
    window.mini_hud.pin_button.setChecked(False)
    assert pin_calls[-1] is False
    assert not (window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    window.mini_hud.pin_button.setChecked(True)
    assert pin_calls[-1] is True

    # Close event on detached MiniHudWindow forwards to main window's close()
    close_forwarded = []
    monkeypatch.setattr(window, "close", lambda: close_forwarded.append(True))
    window._mini_window.close()
    assert close_forwarded == [True]

    # Toggling Mini-HUD off restores main window and reparents MiniHud cleanly
    window.toggle_mini_hud()
    qapp.processEvents()
    assert window._mini_mode is False
    assert window._mini_window.isVisible() is False
    assert window.mini_hud.parent() is window
    assert window.isVisible() is True

    window._mini_window.force_close()
    window.hide()
    window.deleteLater()


def test_wayland_unsupported_compositor_disables_pin_button(qapp, monkeypatch, tmp_path):
    window, _settings = _make_wayland_player(
        qapp, monkeypatch, tmp_path, compositor="other", has_binary=False
    )
    assert window.mini_hud.pin_button.isEnabled() is False
    assert window.mini_hud.pin_button.toolTip() == window.i18n.t("mini_pin_wayland_unsupported")

    window.toggle_mini_hud()
    qapp.processEvents()
    assert window._mini_window is not None
    assert window._mini_window.isVisible() is True
    assert window.mini_hud.pin_button.isEnabled() is False

    window.toggle_mini_hud()
    qapp.processEvents()
    window._mini_window.force_close()
    window.hide()
    window.deleteLater()
