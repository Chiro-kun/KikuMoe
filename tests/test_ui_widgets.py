"""
Tests for KikuMoe 2.0.0 Cyber-Moe UI widgets and theming system.
"""

import os

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

    console = DevConsole()
    console.open()
    assert console.is_open() is True
    console._on_toggle_pause()
    assert console._paused is True
    console._on_toggle_pause()
    assert console._paused is False
    console.close()
    assert console.is_open() is False


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
