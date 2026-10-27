"""
Tests for KikuMoe 2.0.0 Cyber-Moe UI widgets and theming system.
"""

import os
import time

import pytest
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication

from ui.themes.cyber_moe import get_cyber_moe_stylesheet
from ui.widgets.ambient_cover import AmbientCoverCard
from ui.widgets.playback_controls import PlaybackControls
from ui.widgets.segmented_switch import SegmentedSwitch
from ui.widgets.sleep_timer_widget import SleepTimerWidget
from ui.widgets.status_footer import StatusFooter


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest"])
    return app


def test_cyber_moe_stylesheet():
    css = get_cyber_moe_stylesheet("#ec186c")
    assert "#ec186c" in css
    assert "mainWindowRoot" in css
    assert "glassCard" in css
    assert "heroPlayButton" in css


def test_segmented_switch(qapp):
    switch = SegmentedSwitch(items=["J-POP", "K-POP"], default_index=0)
    assert switch.current_selection() == "J-POP"

    emitted = []
    switch.selection_changed.connect(emitted.append)
    switch.set_selected("K-POP")
    assert switch.current_selection() == "K-POP"


def test_playback_controls(qapp):
    ctrl = PlaybackControls()
    assert ctrl._volume == 60

    vol_events = []
    ctrl.volume_changed.connect(vol_events.append)
    ctrl.set_volume(85)
    assert ctrl.volume_label.text() == "85%"

    ctrl.set_playing_state(is_playing=True, is_paused=False)
    assert ctrl.hero_play._is_playing is True
    assert ctrl.hero_play._is_paused is False


def test_sleep_timer_widget(qapp):
    timer = SleepTimerWidget()
    timer.set_minutes(45)
    assert timer.get_minutes() == 45

    timer.set_active_countdown(1500)
    assert timer._is_active is True
    assert "25:00" in timer.badge_countdown.text()
    assert timer.btn_cancel.isEnabled() is True
    assert timer.btn_start.isEnabled() is False

    timer.set_inactive()
    assert timer._is_active is False
    assert timer.badge_countdown.isVisible() is False


def test_status_footer(qapp):
    footer = StatusFooter()
    footer.set_backend_status("MPV", is_ready=True)
    assert footer.backend_label.text() == "MPV"

    footer.set_format("OPUS")
    assert footer.format_label.text() == "OPUS"

    footer.set_session_time("01:23:45")
    assert footer.session_label.text() == "01:23:45"


def test_backend_footer_updates_without_legacy_widgets(qapp):
    from types import SimpleNamespace

    from ui.main_window import ListenMoePlayer

    class PlayerFFmpeg:
        def is_ready(self):
            return True

        def get_version(self):
            return "ffmpeg"

    footer = StatusFooter()
    host = SimpleNamespace(
        player=PlayerFFmpeg(),
        status_footer=footer,
        settings=SimpleNamespace(value=lambda key, default: default),
    )
    ListenMoePlayer.update_vlc_status_label(host)
    assert footer.backend_label.text() == "FFMPEG"
    assert "#00e676" in footer.backend_dot.styleSheet()


def test_ambient_cover(qapp):
    from ui.widgets.ambient_cover import AnimatedTrackLabel, FullBleedCanvas

    cover = AmbientCoverCard(cover_size=160)
    cover.show()
    assert cover._cover_size == 160

    # Test with blank / None cover
    cover.set_cover(None)
    assert cover._cover_pixmap is None

    # Test with a dummy 100x100 pixmap -> triggers 60 FPS crossfade
    pm = QPixmap(100, 100)
    pm.fill(QColor("#ec186c"))
    cover.set_cover(pm)
    assert cover._cover_pixmap is not None
    assert cover._fade_progress == 0.0
    assert cover._prev_rounded_cover is not None

    canvas = FullBleedCanvas()
    canvas.show()
    canvas.set_backdrop(pm)
    assert canvas._fade_progress == 0.0

    lbl = AnimatedTrackLabel("Old Song", font_px=16, font_weight=800)
    lbl.show()
    lbl.setText("New Song")
    assert lbl._prev_text == "Old Song"
    assert lbl._anim_progress == 0.0


def test_settings_dialog_and_toggles(qapp):
    from ui.settings_dialog import AnimatedToggleSwitch, SettingsDialog

    toggle = AnimatedToggleSwitch("Autoplay")
    toggle.setChecked(True)
    assert toggle.isChecked() is True
    assert toggle._progress == 1.0

    dlg = SettingsDialog()
    assert dlg.pages.count() == 4
    dlg.category_bar.set_selected(1)
    dlg.pages.setCurrentIndex(1)
    assert dlg.pages.currentIndex() == 1
    assert hasattr(dlg, "chk_autoplay")
    assert hasattr(dlg, "cmb_audio_backend")
    assert hasattr(dlg, "btn_ok")


def test_settings_apply_shows_and_restarts_toast(qapp, monkeypatch):
    from ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog(embedded=True)
    dlg.resize(400, 600)
    dlg.show()
    qapp.processEvents()
    saved = []
    monkeypatch.setattr(dlg, "_save_settings", lambda: saved.append(True))
    emitted = []
    dlg.settings_changed.connect(lambda: emitted.append(True))
    dlg.cmb_lang.setCurrentIndex(0)
    dlg._applied_values = dlg._settings_values()
    dlg.btn_apply.click()
    assert not saved and not emitted
    assert dlg._apply_toast.text() == "Nessuna modifica da applicare"
    initial_autoplay = dlg.chk_autoplay.isChecked()
    dlg.chk_autoplay.setChecked(not initial_autoplay)
    dlg.chk_autoplay.setChecked(initial_autoplay)
    dlg.btn_apply.click()
    assert not saved and not emitted
    assert dlg._apply_toast.text() == "Nessuna modifica da applicare"
    dlg.chk_autoplay.setChecked(not dlg.chk_autoplay.isChecked())
    dlg.btn_apply.click()
    assert saved == [True] and emitted == [True]
    assert dlg._apply_toast.isVisible()
    assert dlg._apply_toast.text() == "Impostazioni salvate"
    assert abs(dlg._apply_toast.geometry().center().x() - dlg.rect().center().x()) <= 1
    dlg._hide_apply_toast()
    dlg.cmb_lang.setCurrentIndex(1)
    dlg.btn_apply.click()
    assert dlg._apply_toast.isVisible()
    assert dlg._apply_toast.text() == "Settings saved"
    dlg.btn_apply.click()
    assert dlg._apply_toast.text() == "No changes to apply"
    assert len(saved) == len(emitted) == 2
    assert dlg._toast_timer.isActive()
    dlg._hide_apply_toast()
    dlg._toast_animation.setCurrentTime(dlg._toast_animation.duration())
    assert dlg._apply_toast.isHidden()
    dlg.close()


def test_apply_before_device_enumeration_preserves_audio_device(qapp, monkeypatch, tmp_path):
    from PyQt6.QtCore import QSettings

    import ui.settings_dialog as settings_module
    from core.constants import KEY_AUDIO_DEVICE_INDEX

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue(KEY_AUDIO_DEVICE_INDEX, 7)
    monkeypatch.setattr(settings_module, "QSettings", lambda *args: settings)
    dlg = settings_module.SettingsDialog(embedded=True)
    assert not dlg._devices_populated
    dlg.chk_autoplay.setChecked(not dlg.chk_autoplay.isChecked())
    dlg._on_apply()
    assert int(settings.value(KEY_AUDIO_DEVICE_INDEX)) == 7
    dlg.close()


def test_embedded_settings_slide_and_console_button(qapp):
    from PyQt6.QtWidgets import QWidget

    from ui.settings_dialog import SettingsDialog, SlidingStackedWidget

    class DummyHost(QWidget):
        def __init__(self):
            super().__init__()
            self.console_opened = False

        def open_dev_console(self):
            self.console_opened = True

    host = DummyHost()
    host.resize(400, 600)
    stack = SlidingStackedWidget(host)
    stack.resize(400, 600)
    page0 = QWidget()
    stack.addWidget(page0)

    dlg = SettingsDialog(host, embedded=True)
    stack.addWidget(dlg)

    # Even though stack.addWidget reparents dlg to stack, _host_window stays host
    assert dlg._host_window is host

    # Slide from page 0 to page 1 (settings)
    host.show()
    stack.slide_to_index(1, direction=1)
    stack.finish_active_slide()
    assert stack.currentIndex() == 1

    # Clicking Console button invokes host.open_dev_console()
    dlg.chk_dev_console.setChecked(True)
    dlg._on_open_console()
    assert host.console_opened is True

    # Switching tabs resets any sticky hover/popup state on GlassComboBox
    dlg.cmb_lang._hover = True
    dlg.cmb_lang._popup_open = True
    dlg._on_tab_changed(1)
    assert dlg.cmb_lang._hover is False
    assert dlg.cmb_lang._popup_open is False


def test_smooth_progress_bar_and_dev_console(qapp):
    from ui.dev_console import DevConsole
    from ui.main_window import SmoothProgressBar

    bar = SmoothProgressBar()
    assert bar.height() == 16
    bar.trigger_play_launch()
    assert bar._launch_progress == 0.0
    bar.set_buffering_active(True)
    bar.set_buffering_indeterminate(True)
    assert bar._buffering_active is True
    bar.set_buffering_active(False)
    assert bar._buffering_active is False

    import logging

    from core.logger import get_logger, is_debug

    log = get_logger("KikuMoeTest")
    console = DevConsole(logger=log)
    console.open()
    assert console.is_open() is True
    assert is_debug() is True
    assert log.isEnabledFor(logging.DEBUG) is True

    log.debug("[UI] volume_changed -> 42")
    qapp.processEvents()
    assert "[DEBUG] [UI] volume_changed -> 42" in (
        console._console_text.toPlainText() if console._console_text else ""
    )

    if console._level_combo is not None:
        console._level_combo.setCurrentText("INFO")
    qapp.processEvents()
    assert is_debug() is False
    assert log.isEnabledFor(logging.DEBUG) is False
    console._on_toggle_pause()
    assert console._paused is True
    console._on_toggle_pause()
    assert console._paused is False
    console.close()
    assert console.is_open() is False
    assert is_debug() is False


def test_glass_combo_box_rendering_and_layout(qapp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QVBoxLayout, QWidget

    from ui.settings_dialog import GlassComboBox, GlassComboDelegate

    win = QWidget()
    lay = QVBoxLayout(win)
    combo = GlassComboBox(win)
    combo.addItems(["Vorbis", "Opus", "MP3"])
    lay.addWidget(combo)
    win.show()

    # 1. Verify GlassComboBox internal configuration
    view = combo.view()
    assert view.uniformItemSizes() is True
    assert isinstance(view.itemDelegate(), GlassComboDelegate)

    popup = view.window()
    assert popup.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is True
    flags = popup.windowFlags()
    assert Qt.WindowType.FramelessWindowHint in flags
    assert Qt.WindowType.NoDropShadowWindowHint in flags

    # 2. Test short dropdown layout across styles (Fusion on Linux, Windows)
    for style_name in ["Fusion", "Windows"]:
        qapp.setStyle(style_name)
        qapp.setStyleSheet(get_cyber_moe_stylesheet("#ec186c"))
        combo.showPopup()
        m = combo.model()
        rects = [view.visualRect(m.index(i, 0)) for i in range(m.rowCount())]

        # Each item must satisfy minimum height
        for r in rects:
            assert r.height() >= 25

        # Strict non-overlapping test: row i + height must not intrude into row i+1
        for i in range(len(rects) - 1):
            assert rects[i].y() + rects[i].height() <= rects[i + 1].y()

        # Visual corner transparency test (no white background box)
        pix = popup.grab()
        img = pix.toImage()
        assert img.pixelColor(0, 0).alpha() == 0
        # Card interior must remain solid/opaque (never transparent)
        assert img.pixelColor(img.width() // 2, img.height() // 2).alpha() == 255
        combo.hidePopup()

    # 3. Test long dropdown layout
    combo.clear()
    combo.addItems([f"Device {i}" for i in range(15)])
    combo.showPopup()
    m = combo.model()
    rects_long = [
        view.visualRect(m.index(i, 0))
        for i in range(m.rowCount())
        if view.visualRect(m.index(i, 0)).y() > 0
    ]
    for i in range(len(rects_long) - 1):
        assert rects_long[i].y() + rects_long[i].height() <= rects_long[i + 1].y()
    combo.hidePopup()
    win.close()


def test_about_widget(qapp):
    from core.constants import (
        AUTHORS,
        LICENSE_NAME,
        URL_ANISON,
        URL_FORGEJO,
        URL_GENSOKYO,
        URL_GITHUB,
        URL_LISTENMOE,
        URL_NEURO21,
        URL_TELEGRAM,
        URL_TRUCKERSFM,
    )
    from core.i18n import I18n
    from ui.about_dialog import AboutWidget

    i18n = I18n("it")
    widget = AboutWidget(i18n=i18n, backend_name="MPV")
    widget.show()

    # 1. Authors & License
    assert AUTHORS in widget._lbl_authors_val.text()
    assert LICENSE_NAME in widget._lbl_license_val.text()

    # 2. URLs
    assert widget.btn_forgejo.toolTip() == URL_FORGEJO
    assert widget.btn_github.toolTip() == URL_GITHUB
    assert widget.btn_telegram.toolTip().endswith(URL_TELEGRAM)
    assert widget.btn_listenmoe.toolTip() == URL_LISTENMOE
    assert widget.btn_gensokyo.toolTip() == URL_GENSOKYO
    assert widget.btn_anison.toolTip() == URL_ANISON
    assert widget.btn_neuro21.toolTip() == URL_NEURO21
    assert widget.btn_truckersfm.toolTip() == URL_TRUCKERSFM

    # 3. Audio Backend
    assert widget._lbl_backend_val.text() == "MPV"
    widget.set_backend_name("VLC")
    assert widget._lbl_backend_val.text() == "VLC"

    # 4. Copy System Info to clipboard
    widget._copy_system_info()
    clipboard_text = QApplication.clipboard().text()
    assert "KikuMoe" in clipboard_text
    assert AUTHORS in clipboard_text
    assert "VLC" in clipboard_text
    assert URL_FORGEJO in clipboard_text

    # 5. Language switch
    i18n_en = I18n("en")
    widget.set_i18n(i18n_en)
    assert widget.btn_copy.text() == i18n_en.t("about_copy_sys_info")
    widget.close()


def test_about_dialog(qapp):
    from ui.about_dialog import AboutDialog

    dlg = AboutDialog(backend_name="FFmpeg")
    dlg.show()
    assert dlg.about_widget._backend_name == "FFmpeg"
    assert dlg.windowTitle() != ""
    dlg.close()


def test_settings_dialog_four_tabs(qapp):
    from ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog(embedded=True)
    # Check 4 labels present in category bar
    assert len(dlg.category_bar._labels) == 4
    assert dlg.category_bar._labels[0] == dlg.i18n.t("settings_tab_general")
    assert dlg.category_bar._labels[1] == dlg.i18n.t("settings_tab_audio")
    assert dlg.category_bar._labels[2] == dlg.i18n.t("settings_tab_advanced")
    assert dlg.category_bar._labels[3] == dlg.i18n.t("settings_tab_info")

    # Switch to 4th tab (Info)
    dlg.set_tab(3)
    assert dlg.category_bar._selected == 3
    assert dlg.pages.currentIndex() == 3
    dlg.close()


def test_embedded_back_snapshots_visible_settings(qapp, monkeypatch):
    from PyQt6.QtWidgets import QWidget

    from ui.settings_dialog import SettingsDialog, SlidingStackedWidget

    host = QWidget()
    host.resize(405, 600)
    stack = SlidingStackedWidget(host)
    stack.resize(405, 600)
    stack.addWidget(QWidget())
    dialog = SettingsDialog(host, embedded=True)
    stack.addWidget(dialog)
    host.show()
    stack.setCurrentIndex(1)
    qapp.processEvents()
    visibility = []
    render = stack._render_snapshot

    def record_snapshot(widget):
        visibility.append(widget.isVisible())
        return render(widget)

    monkeypatch.setattr(stack, "_render_snapshot", record_snapshot)
    dialog.rejected.connect(lambda: stack.slide_to_index(0, direction=-1))
    dialog.btn_back.click()
    assert visibility[0] is True
    assert stack._pm_from is not None and stack._pm_to is not None
    stack.finish_active_slide()
    assert stack.currentIndex() == 0
    host.close()


def test_settings_pages_scroll_in_compact_window(qapp):
    from PyQt6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

    from ui.settings_dialog import SettingsDialog

    host = QWidget()
    layout = QVBoxLayout(host)
    dlg = SettingsDialog(host, embedded=True)
    layout.addWidget(dlg)
    host.resize(405, 550)
    host.show()
    dlg.set_tab(3)
    qapp.processEvents()
    scroll = dlg.pages.currentWidget()
    assert isinstance(scroll, QScrollArea)
    assert scroll.verticalScrollBar().maximum() > 0
    cards = [
        dlg.about_widget.layout().itemAt(i).widget()
        for i in range(dlg.about_widget.layout().count())
        if dlg.about_widget.layout().itemAt(i).widget() is not None
    ]
    assert all(a.geometry().bottom() < b.geometry().top() for a, b in zip(cards, cards[1:]))
    scroll.ensureWidgetVisible(dlg.about_widget.btn_copy)
    qapp.processEvents()
    copy_pos = dlg.about_widget.btn_copy.mapTo(
        scroll.viewport(), dlg.about_widget.btn_copy.rect().center()
    )
    assert scroll.viewport().rect().contains(copy_pos)
    assert dlg.btn_apply.isVisible()
    host.close()


def test_compact_settings_controls_remain_reachable_horizontally(qapp):
    from PyQt6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

    from ui.settings_dialog import SettingsDialog

    host = QWidget()
    layout = QVBoxLayout(host)
    dlg = SettingsDialog(host, embedded=True)
    layout.addWidget(dlg)
    host.resize(380, 700)
    host.show()
    for tab, controls in (
        (1, (dlg.cmb_format, dlg.cmb_audio_backend, dlg.btn_audio_refresh, dlg.btn_browse)),
        (3, (dlg.about_widget.btn_telegram, dlg.about_widget.btn_truckersfm)),
    ):
        dlg.set_tab(tab)
        qapp.processEvents()
        scroll = dlg.pages.currentWidget()
        assert isinstance(scroll, QScrollArea)
        for control in controls:
            scroll.ensureWidgetVisible(control, 0, 0)
            qapp.processEvents()
            left = control.mapTo(scroll.viewport(), control.rect().topLeft())
            right = control.mapTo(scroll.viewport(), control.rect().bottomRight())
            assert 0 <= left.x() <= right.x() < scroll.viewport().width()
        assert dlg.btn_apply.isVisible()
    host.close()


def test_settings_prewarm_and_logo_cache(qapp):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QWidget

    from core.constants import APP_SETTINGS, ORG_NAME
    from core.i18n import I18n
    from ui.about_dialog import _APP_LOGO_CACHE, AboutWidget
    from ui.settings_dialog import SettingsDialog, SlidingStackedWidget

    w = AboutWidget()
    assert _APP_LOGO_CACHE is not None
    assert not _APP_LOGO_CACHE.isNull()
    w.close()

    class DummyPlayer(QWidget):
        def __init__(self):
            super().__init__()
            self.i18n = I18n("it")
            self.player = None
            self.settings = QSettings(ORG_NAME, APP_SETTINGS)
            self._view_stack = SlidingStackedWidget(self)
            self._settings_dlg = None

        def _prewarm_settings(self):
            if self._settings_dlg is not None:
                return
            dlg = SettingsDialog(self, embedded=True)
            self._settings_dlg = dlg
            self._view_stack.addWidget(dlg)
            self._view_stack._render_snapshot(dlg)

    p = DummyPlayer()
    p._prewarm_settings()
    assert p._settings_dlg is not None
    assert p._view_stack.count() == 1
    p._prewarm_settings()
    p.close()


def test_close_confirm_dialog(qapp):
    """Verify CloseConfirmDialog triggers correct actions, remember flags, and styling."""
    from ui.close_dialog import CloseConfirmDialog

    # 1. Tray selection
    dlg = CloseConfirmDialog()
    dlg.cb_remember.setChecked(True)
    dlg._on_tray()
    assert dlg.action == "tray"
    assert dlg.remember is True
    dlg.close()

    # 2. Quit selection
    dlg2 = CloseConfirmDialog()
    dlg2.cb_remember.setChecked(False)
    dlg2._on_quit()
    assert dlg2.action == "quit"
    assert dlg2.remember is False
    dlg2.close()

    # 3. Cancel selection
    dlg3 = CloseConfirmDialog()
    dlg3._on_cancel()
    assert dlg3.action == "cancel"
    dlg3.close()

    # 4. Entrance animation
    dlg_anim = CloseConfirmDialog()
    dlg_anim.show()
    assert dlg_anim._entrance_animated is True
    assert dlg_anim._anim_group is not None
    dlg_anim.close()


def test_close_dialog_remember_checkbox_alignment_and_animation(qapp):
    from PyQt6.QtCore import QPoint, Qt

    from ui.close_dialog import CloseConfirmDialog

    dlg = CloseConfirmDialog()
    dlg.show()
    qapp.processEvents()
    assert dlg.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    checkbox_x = dlg.cb_remember.mapTo(dlg, QPoint(0, 0)).x()
    prompt_x = dlg.prompt_label.mapTo(dlg, QPoint(0, 0)).x()
    assert checkbox_x == prompt_x
    dlg.cb_remember.click()
    assert dlg.cb_remember.isChecked()
    assert dlg.cb_remember._animation.endValue() == 1.0
    dlg.cb_remember._animation.setCurrentTime(dlg.cb_remember._animation.duration())
    assert dlg.cb_remember._progress == 1.0
    image = dlg.cb_remember.grab().toImage()
    check_color = image.pixelColor(8, image.height() // 2)
    assert check_color.red() > check_color.green()
    dlg.cb_remember.click()
    assert not dlg.cb_remember.isChecked()
    dlg.cb_remember._animation.setCurrentTime(dlg.cb_remember._animation.duration())
    assert dlg.cb_remember._progress == 0.0
    dlg._on_cancel()


def test_sleep_timer_no_extra_window_spawn(qapp, monkeypatch):
    """Verify starting sleep timer does not spawn detached top-level labels or windows."""
    from ui.main_window import ListenMoePlayer

    monkeypatch.setattr(ListenMoePlayer, "_sync_clock_with_server", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_audio_backend", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_websocket", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_tray", lambda self: None)
    monkeypatch.setattr(
        ListenMoePlayer, "_init_system_media", lambda self: setattr(self, "system_media", None)
    )
    monkeypatch.setattr(ListenMoePlayer, "_init_extra_logic", lambda self: None)

    player = ListenMoePlayer()
    try:
        top_levels_before = [w for w in QApplication.topLevelWidgets() if w.isVisible()]

        # Start sleep timer
        player._on_sleep_start_requested(15)
        assert player._sleep_remaining_sec == 15 * 60

        top_levels_after = [w for w in QApplication.topLevelWidgets() if w.isVisible()]
        # Verify no new detached top-level windows were opened
        assert len(top_levels_after) == len(top_levels_before)
        assert player.sleep_label.isVisible() is False
        assert player.sleep_label.isWindow() is False
    finally:
        player.deleteLater()


def test_main_window_minimum_size_keeps_track_below_cover(qapp, monkeypatch):
    from PyQt6.QtCore import QPoint

    from ui.main_window import ListenMoePlayer

    monkeypatch.setattr(ListenMoePlayer, "_sync_clock_with_server", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_audio_backend", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_websocket", lambda self: None)
    monkeypatch.setattr(ListenMoePlayer, "_init_tray", lambda self: None)
    monkeypatch.setattr(
        ListenMoePlayer, "_init_system_media", lambda self: setattr(self, "system_media", None)
    )
    monkeypatch.setattr(ListenMoePlayer, "_init_extra_logic", lambda self: None)
    player = ListenMoePlayer()
    player.resize(200, 200)
    player.show()
    qapp.processEvents()
    assert player.width() >= 380
    assert player.height() >= 700
    cover_bottom = player.ambient_cover.mapTo(player, QPoint(0, player.ambient_cover.height())).y()
    title_top = player.now_playing_title.mapTo(player, QPoint(0, 0)).y()
    assert title_top >= cover_bottom
    player.deleteLater()


def test_lyrics_opens_next_to_cover_and_updates_on_track_change(qapp, monkeypatch):
    from PyQt6.QtTest import QTest

    from ui.main_window import ListenMoePlayer

    for name in (
        "_sync_clock_with_server",
        "_init_audio_backend",
        "_init_websocket",
        "_init_tray",
        "_init_extra_logic",
    ):
        monkeypatch.setattr(ListenMoePlayer, name, lambda self: None)
    monkeypatch.setattr(
        ListenMoePlayer, "_init_system_media", lambda self: setattr(self, "system_media", None)
    )
    window = ListenMoePlayer()
    calls = []
    monkeypatch.setattr(window.lyrics_provider, "search", lambda *args: calls.append(args))
    window._current_title, window._current_artist = "Song", "Artist"
    window._current_duration_seconds = 120
    window._current_start_epoch = 1000
    window.resize(380, 720)
    window.show()
    qapp.processEvents()
    assert window.lyrics_button.parentWidget() is window.history_button.parentWidget()
    assert window.lyrics_button.size() == window.history_button.size()
    assert window.lyrics_button.geometry().right() < window.history_button.geometry().left()
    assert window.station_pill.mapTo(window, window.station_pill.rect().topRight()).x() < (
        window.lyrics_button.mapTo(window, window.lyrics_button.rect().topLeft()).x()
    )
    window.lyrics_button.click()
    qapp.processEvents()
    assert window._lyrics_transition.state() == window._lyrics_transition.State.Running
    assert window.lyrics_panel.stack.currentWidget() is window.lyrics_panel.skeleton
    QTest.qWait(350)
    assert window.width() >= 650
    assert window.lyrics_panel.isVisible()
    assert window.lyrics_button.isCheckable()
    assert window.lyrics_button.toolTip() == window.i18n.t("lyrics_button")
    assert not window.lyrics_button.text()
    assert window.ambient_cover.width() == window._album_cover_size + 26
    assert window.lyrics_panel.x() > window.ambient_cover.x()
    assert calls == [("Song", "Artist", 120)]
    assert window.lyrics_panel.skeleton.timer.isActive()
    window.lyrics_provider.finished.emit({"syncedLyrics": "[00:01.00]Hello"}, "ok")
    assert not window.lyrics_panel.skeleton.timer.isActive()
    assert window.lyrics_panel.labels[0].text() == "Hello"
    window._current_title = "Next"
    window._refresh_lyrics()
    assert calls[-1] == ("Next", "Artist", 120)
    window.lyrics_button.click()
    QTest.qWait(350)
    assert window.lyrics_panel.isHidden()
    assert not window.lyrics_panel.skeleton.timer.isActive()
    assert window.width() == 380
    window.lyrics_button.click()
    QTest.qWait(80)
    window.lyrics_button.click()
    QTest.qWait(350)
    assert window.lyrics_panel.isHidden()
    assert window.width() == 380
    lyrics = "\n".join(f"[00:{n:02}.00]Line {n}" for n in range(1, 51))
    monkeypatch.setattr(
        window.lyrics_provider,
        "search",
        lambda *args: window.lyrics_provider.finished.emit({"syncedLyrics": lyrics}, "ok"),
    )
    window._current_start_epoch = time.time() + 90
    window.lyrics_button.click()
    QTest.qWait(800)
    panel = window.lyrics_panel
    assert panel.active == 29
    line = panel.labels[panel.active]
    assert (
        abs(
            line.mapTo(panel.scroll.viewport(), line.rect().center()).y()
            - panel.scroll.viewport().height() // 2
        )
        < 5
    )
    window.hide()
    window.deleteLater()


@pytest.mark.parametrize("linux", [False, True])
def test_mini_hud_switches_geometry_and_shares_controls(qapp, monkeypatch, tmp_path, linux):
    from types import SimpleNamespace

    from PyQt6.QtCore import QSettings, Qt
    from PyQt6.QtWidgets import QWidget

    from core.constants import KEY_MINI_ALWAYS_ON_TOP, KEY_MINI_GEOMETRY, KEY_WINDOW_GEOMETRY
    from ui import main_window

    cls = main_window.ListenMoePlayer
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    old_mini = QWidget()
    old_mini.resize(360, 88)
    settings.setValue(KEY_MINI_GEOMETRY, old_mini.saveGeometry())
    monkeypatch.setattr(main_window, "QSettings", lambda *args: settings)
    monkeypatch.setattr(main_window, "_IS_LINUX", linux)
    monkeypatch.setattr(cls, "_sync_clock_with_server", lambda self: None)
    monkeypatch.setattr(cls, "_init_audio_backend", lambda self: None)
    monkeypatch.setattr(cls, "_init_websocket", lambda self: None)
    monkeypatch.setattr(cls, "_init_tray", lambda self: None)
    monkeypatch.setattr(cls, "_init_system_media", lambda self: setattr(self, "system_media", None))
    monkeypatch.setattr(cls, "_init_extra_logic", lambda self: None)
    calls = []
    monkeypatch.setattr(cls, "_tray_toggle_play_pause", lambda self: calls.append("play"))
    window = cls()
    window.player = SimpleNamespace(is_playing=lambda: True)
    window._current_title = "A long song title"
    window._current_artist = "Artist"
    window.show()
    qapp.processEvents()
    window.resize(405, 720)
    window.toggle_mini_hud()
    qapp.processEvents()
    assert window._mini_mode and window.mini_hud.isVisible()
    assert 400 <= window.width() and 104 <= window.height() <= 140
    assert window.mini_button.toolTip() == window.i18n.t("mini_mode")
    assert "Ctrl+," in window.settings_button.toolTip()
    assert window._settings_shortcut.key().toString() == "Ctrl+,"
    if linux:
        window.resize(2000, 500)
        assert window.width() == 420 and window.height() == 112
        window.showMaximized()
        qapp.processEvents()
        qapp.processEvents()
        assert not window.isMaximized()
    assert window.mini_hud.cover.width() == 68
    assert window.mini_hud.track_progress.width() > 40
    assert window.mini_hud.title._text == "A long song title"
    assert window.mini_hud.artist._text == "Artist"
    assert window.mini_hud.play_button.kind == "pause"
    monkeypatch.setattr(main_window.time, "time", lambda: 900.0)
    window._clock_sync_offset = 0
    window._current_start_epoch = 1000
    window._current_duration_seconds = 200
    window._sync_mini_hud()
    assert window.mini_hud.elapsed_label.text() == "1:40"
    assert window.mini_hud.duration_label.text() == "3:20"
    assert window.mini_hud.track_progress.value() == 500
    window._current_duration_seconds = 0
    window._current_start_epoch = 840
    window._sync_mini_hud()
    assert window.mini_hud.elapsed_label.text() == "1:00"
    assert window.mini_hud.duration_label.text() == "LIVE"
    assert window.mini_hud.track_progress.value() == 0
    window._current_duration_seconds = 180
    window._current_start_epoch = None
    window._sync_mini_hud()
    assert window.mini_hud.elapsed_label.text() == "--:--"
    assert window.mini_hud.duration_label.text() == "3:00"
    window.mini_hud.volume.setValue(37)
    assert window.volume_slider.value() == 37
    assert window.mini_hud.volume_popup.isVisible()
    assert window.mini_hud.volume_popup.text() == "37%"
    first_x = window.mini_hud.volume_popup.x()
    window.volume_slider.setValue(55)
    assert window.mini_hud.volume.value() == 55
    assert window.mini_hud.volume_popup.text() == "55%"
    assert window.mini_hud.volume_popup.x() > first_x
    assert window.mini_hud._volume_timer.isActive()
    window.mini_hud.play_button.click()
    assert calls == ["play"]
    window.mini_hud.pin_button.setChecked(True)
    assert bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    assert settings.value(KEY_MINI_ALWAYS_ON_TOP) == "true"
    window.move(80, 90)
    window.toggle_mini_hud()
    qapp.processEvents()
    assert not window._mini_mode and window.height() >= 700
    assert window.mini_hud.volume_popup.isHidden()
    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert settings.value(KEY_WINDOW_GEOMETRY) is not None
    assert settings.value(KEY_MINI_GEOMETRY) is not None
    window.toggle_mini_hud()
    qapp.processEvents()
    assert window.x() == 80 and window.y() == 90
    assert window.mini_hud.pin_button.isChecked()
    from PyQt6.QtGui import QCloseEvent

    normal_geometry = settings.value(KEY_WINDOW_GEOMETRY)
    monkeypatch.setattr(window, "_get_bool", lambda key, default: False)
    monkeypatch.setattr(window, "_cleanup_before_close", lambda: None)
    close_event = QCloseEvent()
    window.closeEvent(close_event)
    assert close_event.isAccepted()
    assert settings.value(KEY_WINDOW_GEOMETRY) == normal_geometry
    opened_settings = []
    monkeypatch.setattr(window, "open_settings", lambda: opened_settings.append(True))
    window._settings_shortcut.activated.emit()
    assert not window._mini_mode and opened_settings == [True]
    window.hide()
    window.deleteLater()


def test_mini_hud_marquee_and_paused_playback(qapp):
    from types import SimpleNamespace

    from ui.main_window import ListenMoePlayer
    from ui.widgets.mini_hud import MarqueeLabel

    label = MarqueeLabel("#ffffff")
    label.resize(70, 18)
    label.set_text("A long title that must scroll in the mini player")
    label.show()
    qapp.processEvents()
    label._pause = 0
    label._tick()
    assert label._offset > 0
    label.set_text("Short")
    label._tick()
    assert label._offset == 0
    assert not label._timer.isActive()
    label.close()

    actions = []
    window = SimpleNamespace(
        player=SimpleNamespace(is_playing=lambda: False),
        _ui_paused=True,
        pause_resume=lambda: actions.append("resume"),
        play_stream=lambda: actions.append("play"),
    )
    ListenMoePlayer._tray_toggle_play_pause(window)
    assert actions == ["resume"]


def test_mini_hud_cover_is_rounded_and_clears(qapp):
    from PyQt6.QtGui import QColor, QPixmap

    from ui.widgets.mini_hud import MiniHud

    hud = MiniHud()
    cover = QPixmap(90, 60)
    cover.fill(QColor("red"))
    hud.set_cover(cover)
    pixmap = hud.cover.pixmap()
    assert pixmap is not None
    image = pixmap.toImage()
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(image.width() // 2, image.height() // 2).red() == 255
    assert image.pixelColor(image.width() // 2, image.height() // 2).alpha() == 255
    hud.set_cover(None)
    assert hud.cover.pixmap() is None or hud.cover.pixmap().isNull()
    hud.close()
