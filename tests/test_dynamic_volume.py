import os
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPoint, QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import ui.settings_dialog as settings_module
from core.constants import (
    KEY_DYNAMIC_VOLUME_APPS,
    KEY_DYNAMIC_VOLUME_ENABLED,
    KEY_DYNAMIC_VOLUME_LEVEL,
    KEY_DYNAMIC_VOLUME_MODE,
    KEY_VOLUME,
)
from core.dynamic_volume import (
    DYNAMIC_MODE_ANY_OPEN,
    DYNAMIC_MODE_FOREGROUND,
    DynamicVolumeController,
    match_dynamic_app,
    normalize_process_name,
    parse_app_list,
)
from core.i18n import I18n
from ui.main_window import ListenMoePlayer
from ui.widgets.playback_controls import PlaybackControls


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest"])
    return app


def test_normalize_and_parse_app_list():
    assert normalize_process_name("C:\\Games\\Valorant-Win64-Shipping.exe") == (
        "valorant-win64-shipping"
    )
    assert normalize_process_name("  /usr/bin/Discord ") == "discord"
    assert parse_app_list("cs2.exe, discord, CS2, ; obs64.exe\n") == [
        "cs2.exe",
        "discord",
        "obs64.exe",
    ]


def test_match_dynamic_app_modes_and_wildcards():
    running = {"steam", "cs2", "discord"}
    assert match_dynamic_app(["valorant", "cs2.exe"], DYNAMIC_MODE_ANY_OPEN, running, "") == (
        "cs2.exe"
    )
    assert match_dynamic_app(["cs2.exe"], DYNAMIC_MODE_FOREGROUND, running, "discord.exe") is None
    assert (
        match_dynamic_app(["cs2.exe"], DYNAMIC_MODE_FOREGROUND, running, "C:\\bin\\cs2.exe")
        == "cs2.exe"
    )
    assert (
        match_dynamic_app(["valorant*"], DYNAMIC_MODE_ANY_OPEN, {"valorant-win64-shipping"}, "")
        == "valorant*"
    )


def test_controller_ramps_down_and_restores_on_app_exit(qapp):
    state = {"running": set(), "fg": ""}
    events: list[tuple[float, str]] = []

    ctrl = DynamicVolumeController(
        ramp_steps=4,
        list_processes_fn=lambda: set(state["running"]),
        foreground_process_fn=lambda: state["fg"],
    )
    ctrl.factor_changed.connect(lambda f, app: events.append((f, app)))
    ctrl.configure(True, "game.exe", 20, DYNAMIC_MODE_ANY_OPEN)

    assert ctrl.current_factor() == 1.0
    assert not ctrl.is_ducked()

    # Game opens -> immediate evaluate starts ramping down toward 0.20
    state["running"] = {"game"}
    ctrl.evaluate_now()
    assert ctrl.is_ducked()
    assert ctrl.active_app() == "game.exe"
    assert ctrl.target_factor() == 0.20
    while ctrl._ramp_timer.isActive():
        ctrl._on_ramp_tick()
    assert abs(ctrl.current_factor() - 0.20) < 1e-6

    # Game closes -> smoothly restores back to 1.0
    state["running"] = set()
    ctrl.evaluate_now()
    assert not ctrl.is_ducked()
    assert ctrl.active_app() == ""
    while ctrl._ramp_timer.isActive():
        ctrl._on_ramp_tick()
    assert abs(ctrl.current_factor() - 1.0) < 1e-6
    assert events[-1] == (1.0, "")
    ctrl.stop()


def test_player_effective_volume_scales_without_mutating_user_volume(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "player.ini"), QSettings.Format.IniFormat)
    settings.setValue(KEY_VOLUME, 60)

    backend_calls: list[int] = []
    controls = PlaybackControls()
    controls.set_volume(60)

    fake = SimpleNamespace(
        settings=settings,
        i18n=I18n("en"),
        log=SimpleNamespace(debug=lambda *_a, **_kw: None),
        player=SimpleNamespace(set_volume=lambda v: backend_calls.append(v)),
        playback_controls=controls,
        volume_slider=controls.volume_slider,
        volume_value_label=controls.volume_label,
        _dynamic_volume_factor=1.0,
        _dynamic_volume_app="",
    )
    fake._effective_volume = lambda v: ListenMoePlayer._effective_volume(fake, v)
    fake._apply_effective_volume = lambda v=None: ListenMoePlayer._apply_effective_volume(fake, v)

    ListenMoePlayer._on_dynamic_volume_factor_changed(fake, 0.25, "game.exe")

    assert backend_calls[-1] == 15
    assert controls.volume_slider.value() == 60
    assert int(settings.value(KEY_VOLUME)) == 60
    assert controls.volume_label.text() == "15%"
    assert "game.exe" in controls.volume_label.toolTip()

    # User manually bumps base volume to 80 while ducked -> backend gets 20, KEY_VOLUME gets 80
    controls.volume_slider.setValue(80)
    ListenMoePlayer.change_volume(fake, 80)
    assert backend_calls[-1] == 20
    assert int(settings.value(KEY_VOLUME)) == 80
    assert controls.volume_label.text() == "20%"

    # Unducked -> restores full 80% cleanly
    ListenMoePlayer._on_dynamic_volume_factor_changed(fake, 1.0, "")
    assert backend_calls[-1] == 80
    assert controls.volume_label.text() == "80%"
    controls.close()


def test_settings_dialog_dynamic_volume_persistence_and_toggle(qapp, monkeypatch, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(settings_module, "QSettings", lambda *args: settings)
    monkeypatch.setattr(
        settings_module.SettingsDialog, "_ensure_devices_populated", lambda self: None
    )

    dlg = settings_module.SettingsDialog(embedded=True)
    assert dlg.chk_dynamic_volume.isChecked() is False
    assert dlg.dynvol_options_box.isHidden() is True

    dlg.chk_dynamic_volume.setChecked(True)
    assert dlg.dynvol_options_box.isHidden() is False
    QTest.qWait(260)
    assert dlg.dynvol_options_box.maximumHeight() == 16777215

    # Stepper buttons replace native spinbox arrows and update target level cleanly
    start_val = dlg.spin_dynamic_volume_level.value()
    dlg.btn_dynvol_plus.click()
    assert dlg.spin_dynamic_volume_level.value() == min(90, start_val + 5)
    dlg.btn_dynvol_minus.click()
    assert dlg.spin_dynamic_volume_level.value() == start_val

    # GlassComboBox popup style uses subtle glass hover/selection instead of solid wall
    popup_css = dlg.cmb_dynamic_volume_mode._list_view.styleSheet()
    assert "selection-background-color: transparent" in popup_css
    assert "rgba(255, 255, 255, 0.09)" in popup_css

    dlg.cmb_dynamic_volume_mode.setCurrentIndex(1)
    dlg.spin_dynamic_volume_level.setValue(35)
    dlg.txt_dynamic_volume_apps.setText("cs2.exe, discord")
    dlg._on_apply()

    assert settings.value(KEY_DYNAMIC_VOLUME_ENABLED) == "true"
    assert settings.value(KEY_DYNAMIC_VOLUME_MODE) == DYNAMIC_MODE_FOREGROUND
    assert int(settings.value(KEY_DYNAMIC_VOLUME_LEVEL)) == 35
    assert settings.value(KEY_DYNAMIC_VOLUME_APPS) == "cs2.exe, discord"

    # Re-open / reload confirms round-trip and animated collapse hides cleanly
    dlg2 = settings_module.SettingsDialog(embedded=True)
    assert dlg2.chk_dynamic_volume.isChecked() is True
    assert dlg2.dynvol_options_box.isHidden() is False
    assert dlg2.cmb_dynamic_volume_mode.currentData() == DYNAMIC_MODE_FOREGROUND
    assert dlg2.spin_dynamic_volume_level.value() == 35
    assert dlg2.txt_dynamic_volume_apps.text() == "cs2.exe, discord"
    dlg2.chk_dynamic_volume.setChecked(False)
    QTest.qWait(260)
    assert dlg2.dynvol_options_box.isHidden() is True

    dlg.close()
    dlg2.close()


def test_settings_audio_no_horizontal_overflow_and_sleep_toggle_restores_drawer(
    qapp, tmp_path, monkeypatch
):
    from ui import main_window

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(settings_module, "QSettings", lambda *args: settings)
    monkeypatch.setattr(
        settings_module.SettingsDialog, "_ensure_devices_populated", lambda self: None
    )

    dlg = settings_module.SettingsDialog(embedded=True)
    try:
        dlg.show()
        dlg.pages.setCurrentIndex(1)
        dlg.chk_dynamic_volume.setChecked(True)
        QTest.qWait(300)

        scroll = dlg.pages.currentWidget()
        assert scroll.horizontalScrollBar().isVisible() is False
        assert dlg.txt_vlc_path.height() == 32
        assert dlg.txt_vlc_path.maximumHeight() == 32
        assert dlg.txt_dynamic_volume_apps.height() == 32
        assert dlg.txt_dynamic_volume_apps.maximumHeight() == 32
        apps_rect = dlg.txt_dynamic_volume_apps.geometry()
        assert apps_rect.y() + apps_rect.height() <= dlg.dynvol_options_box.height()
    finally:
        dlg.close()

    monkeypatch.setattr(main_window, "QSettings", lambda *args: settings)
    for name in (
        "_sync_clock_with_server",
        "_init_audio_backend",
        "_init_websocket",
        "_init_tray",
        "_init_extra_logic",
    ):
        monkeypatch.setattr(main_window.ListenMoePlayer, name, lambda self: None)
    monkeypatch.setattr(
        main_window.ListenMoePlayer,
        "_init_system_media",
        lambda self: setattr(self, "system_media", None),
    )

    player = main_window.ListenMoePlayer()
    player.player = None
    try:
        player.show()
        qapp.processEvents()
        assert player.sleep_button.isVisible() is True
        assert player.sleep_button.isChecked() is True
        assert player.sleep_timer_widget.isVisible() is True
        assert player.live_badge.geometry().right() < player.sleep_button.geometry().left()

        # Dismiss via close button -> header toggle reflects hidden state
        player.sleep_timer_widget.btn_close.click()
        qapp.processEvents()
        assert player.sleep_timer_widget.isVisible() is False
        assert player.sleep_button.isChecked() is False
        assert player.minimumHeight() == 592
        assert settings.value("show_sleep_timer") == "false"

        # Resizing windowed height with Sleep Timer hidden keeps StatusFooter pinned near bottom
        player.resize(650, 740)
        qapp.processEvents()
        footer_bottom = player.status_footer.mapTo(
            player, QPoint(0, player.status_footer.height())
        ).y()
        assert player.height() - footer_bottom <= 16

        # Enabling again via embedded SettingsDialog restores height and minHeight properly
        player.open_settings()
        QTest.qWait(300)
        assert player._settings_dlg is not None
        player._settings_dlg.chk_show_sleep_timer.setChecked(True)
        player._settings_dlg.btn_ok.click()
        QTest.qWait(350)
        assert player.sleep_timer_widget.isVisible() is True
        assert player.sleep_button.isChecked() is True
        assert player.minimumHeight() == 700
        assert settings.value("show_sleep_timer") == "true"

        # Clicking the header moon button hides/shows Sleep Timer immediately
        player.sleep_button.click()
        qapp.processEvents()
        assert player.sleep_timer_widget.isVisible() is False
        assert player.sleep_button.isChecked() is False
        player.sleep_button.click()
        qapp.processEvents()
        assert player.sleep_timer_widget.isVisible() is True
        assert player.sleep_button.isChecked() is True
        assert settings.value("show_sleep_timer") == "true"
    finally:
        player.deleteLater()


def test_dynamic_app_picker_uses_windowed_apps_and_scrollable_popup(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QListWidget

    import core.dynamic_volume as dynvol_module

    # On Windows, picker suggestions only query visible windowed apps.
    if os.name == "nt":
        monkeypatch.setattr(
            dynvol_module,
            "_list_windows_windowed_process_names",
            lambda: ["Discord.exe", "KikuMoe.exe", "explorer.exe", "VALORANT-Win64-Shipping.exe"],
        )
        assert dynvol_module.list_suggested_running_apps(exclude_names=["discord"]) == [
            "VALORANT-Win64-Shipping"
        ]

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(settings_module, "QSettings", lambda *args: settings)
    monkeypatch.setattr(
        settings_module.SettingsDialog, "_ensure_devices_populated", lambda self: None
    )
    many_apps = [f"Game{i:02d}" for i in range(30)]
    monkeypatch.setattr(
        settings_module, "list_suggested_running_apps", lambda exclude_names=None: many_apps
    )

    dlg = settings_module.SettingsDialog(embedded=True)
    try:
        dlg.show()
        dlg.pages.setCurrentIndex(1)
        dlg.chk_dynamic_volume.setChecked(True)
        QTest.qWait(50)

        dlg.btn_pick_dynamic_app.click()
        qapp.processEvents()
        popup = dlg._dynamic_app_popup
        assert popup is not None
        assert popup.isVisible() is True
        # Compact scrollable list (not stretching across the whole screen)
        assert popup.height() <= 240
        list_w = popup.findChild(QListWidget, "dynamicAppPickerList")
        assert list_w is not None
        assert list_w.count() == 30

        list_w.itemClicked.emit(list_w.item(12))
        qapp.processEvents()
        assert dlg.txt_dynamic_volume_apps.text() == "Game12"
        assert popup.isVisible() is False
    finally:
        dlg.close()


def test_responsive_stage_hero_transition_animates_footer(qapp, tmp_path, monkeypatch):
    from PyQt6.QtCore import QPoint, QVariantAnimation

    from ui import main_window

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(main_window, "QSettings", lambda *args: settings)
    for name in (
        "_sync_clock_with_server",
        "_init_audio_backend",
        "_init_websocket",
        "_init_tray",
        "_init_extra_logic",
    ):
        monkeypatch.setattr(main_window.ListenMoePlayer, name, lambda self: None)
    monkeypatch.setattr(
        main_window.ListenMoePlayer,
        "_init_system_media",
        lambda self: setattr(self, "system_media", None),
    )

    player = main_window.ListenMoePlayer()
    try:
        player.show()
        # Compact windowed mode: badges never overflow/clip past bottom of stage
        player.resize(420, 700)
        qapp.processEvents()
        assert (
            player.status_footer.y() + player.status_footer.height()
            <= player._player_stage.height()
        )

        # Compact windowed mode: badges never overflow/clip past bottom of stage
        player.resize(420, 700)
        qapp.processEvents()
        assert (
            player.status_footer.y() + player.status_footer.height()
            <= player._player_stage.height()
        )

        # Wide windowed mode below hero height threshold: badges anchor edge-to-edge at footer
        player.resize(1100, 760)
        qapp.processEvents()
        assert player.status_footer.width() == player._player_stage.width()
        assert (
            player.status_footer.y() + player.status_footer.height()
            <= player._player_stage.height()
        )
        assert (
            player.status_footer.y() + player.status_footer.height()
            <= player._player_stage.height()
        )
        assert player._stage_column.width() == 760

        player.resize(940, 860)
        qapp.processEvents()
        assert player.status_footer.width() == player._player_stage.width()
        assert (
            player.status_footer.y() + player.status_footer.height()
            <= player._player_stage.height()
        )
        assert (
            player.status_footer.y() + player.status_footer.height()
            <= player._player_stage.height()
        )

        footer_start_y = player.status_footer.mapTo(player, QPoint(0, 0)).y()
        footer_start_w = player.status_footer.width()
        footer_start_bottom = footer_start_y + player.status_footer.height()
        assert player.height() - footer_start_bottom <= 16

        # Crossing into hero stage (960x820) must smoothly animate badges up & inward
        player.resize(970, 860)
        qapp.processEvents()
        assert player._stage_hero_anim.state() == QVariantAnimation.State.Running

        player._on_stage_hero_anim_changed(0.5)
        qapp.processEvents()
        footer_mid_y = player.status_footer.mapTo(player, QPoint(0, 0)).y()
        footer_mid_w = player.status_footer.width()

        QTest.qWait(300)
        qapp.processEvents()
        assert player._stage_hero_anim.state() == QVariantAnimation.State.Stopped
        assert player._stage_hero_blend == 1.0
        footer_end_y = player.status_footer.mapTo(player, QPoint(0, 0)).y()
        footer_end_w = player.status_footer.width()
        assert footer_end_y < footer_mid_y < footer_start_y
        assert footer_end_w == player._stage_column.width() == 760
        assert footer_end_w < footer_mid_w < player._player_stage.width()
        assert footer_start_w > footer_end_w
        assert player.height() - (footer_end_y + player.status_footer.height()) > 20

        # Shrinking back below hero stage must animate badges back down & full-width
        player.resize(940, 860)
        qapp.processEvents()
        assert player._stage_hero_anim.state() == QVariantAnimation.State.Running

        QTest.qWait(300)
        qapp.processEvents()
        assert player._stage_hero_anim.state() == QVariantAnimation.State.Stopped
        assert player._stage_hero_blend == 0.0
        assert player.status_footer.width() == player._player_stage.width()
        footer_restored_bottom = (
            player.status_footer.mapTo(player, QPoint(0, 0)).y() + player.status_footer.height()
        )
        assert player.height() - footer_restored_bottom <= 16
    finally:
        player.deleteLater()


def test_controller_unducks_promptly_and_gradually_on_process_exit(qapp):
    state = {"running": set(), "fg": ""}
    ctrl = DynamicVolumeController(
        list_processes_fn=lambda: set(state["running"]),
        foreground_process_fn=lambda: state["fg"],
    )
    try:
        assert ctrl._poll_timer.interval() <= 250
        assert ctrl._ramp_timer.interval() * ctrl._ramp_steps <= 250
        assert ctrl._ramp_timer.interval() * ctrl._unduck_ramp_steps >= 800

        # Empty app list -> poll timer stays idle even when enabled
        ctrl.configure(True, "", 25, DYNAMIC_MODE_ANY_OPEN)
        assert ctrl._poll_timer.isActive() is False

        # Configured app -> shared poll timer monitors both start and exit
        ctrl.configure(True, "game.exe", 25, DYNAMIC_MODE_ANY_OPEN)
        assert ctrl._poll_timer.isActive() is True

        state["running"] = {"game"}
        QTest.qWait(550)
        assert ctrl.is_ducked() is True
        assert abs(ctrl.current_factor() - 0.25) < 1e-6

        # Selected process exits -> exit is detected promptly, and volume swells gradually (not blasted to 1.0)
        state["running"] = set()
        QTest.qWait(400)
        assert ctrl.is_ducked() is False
        assert ctrl.active_app() == ""
        assert ctrl.target_factor() == 1.0
        assert 0.25 < ctrl.current_factor() < 0.90

        # Remainder of the gradual fade completes smoothly to 1.0
        QTest.qWait(1050)
        assert abs(ctrl.current_factor() - 1.0) < 1e-6
    finally:
        ctrl.stop()


def test_controller_gradual_unduck_easing_and_reduck_mid_fade(qapp):
    state = {"running": {"game"}, "fg": ""}
    events: list[tuple[float, str]] = []
    ctrl = DynamicVolumeController(
        ramp_steps=4,
        unduck_ramp_steps=20,
        list_processes_fn=lambda: set(state["running"]),
        foreground_process_fn=lambda: state["fg"],
    )
    try:
        ctrl.factor_changed.connect(lambda f, app: events.append((f, app)))
        ctrl.configure(True, "game.exe", 20, DYNAMIC_MODE_ANY_OPEN)
        while ctrl._ramp_timer.isActive():
            ctrl._on_ramp_tick()
        assert abs(ctrl.current_factor() - 0.20) < 1e-6

        events.clear()
        state["running"] = set()
        ctrl.evaluate_now()
        # First tick rises very gently (smoothstep start), never snapping
        assert events[0][0] < 0.22
        assert ctrl._ramp_step_index == 1

        # Advance 5 ticks (quarter of unduck fade) -> stays below linear midpoint (still gentle)
        for _ in range(4):
            ctrl._on_ramp_tick()
        assert 0.20 < events[-1][0] < 0.40

        # Monotonically non-decreasing upward ticks until mid-fade
        up_factors = [f for f, _ in events]
        assert up_factors == sorted(up_factors)

        # If target app re-opens mid-unduck, controller ducks smoothly from current factor
        mid_factor = ctrl.current_factor()
        state["running"] = {"game"}
        ctrl.evaluate_now()
        assert ctrl.is_ducked() is True
        assert ctrl.current_factor() < mid_factor
        while ctrl._ramp_timer.isActive():
            ctrl._on_ramp_tick()
        assert abs(ctrl.current_factor() - 0.20) < 1e-6
    finally:
        ctrl.stop()


def test_read_linux_proc_name_ignores_zombies_and_falls_back_to_comm(tmp_path):
    from core.dynamic_volume import _read_linux_proc_name

    live_dir = tmp_path / "101"
    live_dir.mkdir()
    (live_dir / "stat").write_text("101 (my game (1)) S 1 101 101 0 -1\n", encoding="utf-8")
    assert _read_linux_proc_name(str(live_dir)) == "my game (1)"

    zombie_dir = tmp_path / "102"
    zombie_dir.mkdir()
    (zombie_dir / "stat").write_text("102 (game) Z 1 102 102 0 -1\n", encoding="utf-8")
    (zombie_dir / "comm").write_text("game\n", encoding="utf-8")
    assert _read_linux_proc_name(str(zombie_dir)) == ""

    dead_dir = tmp_path / "103"
    dead_dir.mkdir()
    (dead_dir / "stat").write_text("103 (game) X 1 103 103 0 -1\n", encoding="utf-8")
    assert _read_linux_proc_name(str(dead_dir)) == ""

    comm_only_dir = tmp_path / "104"
    comm_only_dir.mkdir()
    (comm_only_dir / "comm").write_text("discord\n", encoding="utf-8")
    assert _read_linux_proc_name(str(comm_only_dir)) == "discord"
