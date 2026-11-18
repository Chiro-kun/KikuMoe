"""UI, interaction, offscreen painting, theming, and persistence tests for the Equalizer."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from PyQt6.QtCore import QPoint, QPointF, QSettings, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication

from audio.equalizer import (
    EQ_PRESET_CUSTOM,
    EQ_PRESET_ORDER,
    EQ_PRESETS,
    parse_eq_bands,
)
from core.constants import (
    KEY_EQ_BANDS,
    KEY_EQ_CUSTOM_BANDS,
    KEY_EQ_CUSTOM_PREAMP,
    KEY_EQ_ENABLED,
    KEY_EQ_PREAMP,
    KEY_EQ_PRESET,
)
from core.i18n import I18n
from ui.equalizer_popover import EqualizerPopover
from ui.themes.cyber_moe import apply_theme_palette
from ui.widgets.history_button import EqualizerIconButton
from ui.widgets.playback_controls import PlaybackControls

_QAPP: QApplication | None = None


def _get_qapp() -> QApplication:
    global _QAPP
    app = QApplication.instance()
    if isinstance(app, QApplication):
        _QAPP = app
        return app
    _QAPP = QApplication([])
    return _QAPP


def test_equalizer_icon_button_states_and_offscreen_paint() -> None:
    _get_qapp()
    btn = EqualizerIconButton()
    try:
        assert btn.is_eq_enabled() is False
        assert btn.is_active() is False

        # Offscreen render in idle, eq-enabled, and popover-active states
        assert not btn.grab().isNull()

        btn.set_eq_enabled(True)
        assert btn.is_eq_enabled() is True
        assert not btn.grab().isNull()

        btn.set_active(True)
        assert btn.is_active() is True
        assert not btn.grab().isNull()

        btn.refresh_theme()
        assert not btn.grab().isNull()
    finally:
        btn.deleteLater()


def test_equalizer_popover_presets_custom_and_offscreen_themes() -> None:
    _get_qapp()
    pop = EqualizerPopover(i18n=I18n("it"))
    try:
        # Must never cause the app to quit when closed (issue #99 safeguard)
        assert not pop.testAttribute(Qt.WidgetAttribute.WA_QuitOnClose)
        assert pop.cmb_preset.count() == len(EQ_PRESET_ORDER)

        emitted: list[tuple[bool, str, float, list[float]]] = []
        pop.eq_changed.connect(lambda en, pid, pre, b: emitted.append((en, pid, pre, b)))

        # Render offscreen while disabled
        assert not pop.grab().isNull()

        # Enable EQ
        pop.set_eq_enabled(True)
        assert emitted[-1][0] is True
        assert emitted[-1][1] == "flat"

        # Cycle every built-in preset and verify exact curve & preamp
        for pid, (expected_pre, expected_bands) in EQ_PRESETS.items():
            pop.select_preset(pid)
            en, got_pid, got_pre, got_bands = emitted[-1]
            assert en is True
            assert got_pid == pid
            assert got_pre == expected_pre
            assert got_bands == list(expected_bands)

        # Render across multiple themes offscreen without errors
        for theme_id in ("cyber_moe", "midnight_amoled", "sakura_bloom", "ocean_cyan"):
            apply_theme_palette(theme_id)
            pop.refresh_theme()
            assert not pop.grab().isNull()
        apply_theme_palette("cyber_moe")

        # Manual adjustment switches automatically to Custom and remembers values
        pop.set_band_gain(2, 7.5)
        pop.set_preamp(-4.0)
        assert emitted[-1][1] == EQ_PRESET_CUSTOM
        assert emitted[-1][2] == -4.0
        assert emitted[-1][3][2] == 7.5

        # Switch away and back to Custom -> restores remembered custom curve
        pop.select_preset("vocal")
        assert emitted[-1][1] == "vocal"
        pop.select_preset(EQ_PRESET_CUSTOM)
        assert emitted[-1][1] == EQ_PRESET_CUSTOM
        assert emitted[-1][2] == -4.0
        assert emitted[-1][3][2] == 7.5

        # Reset button returns to Flat (0.0 dB across preamp & bands)
        pop.btn_reset.click()
        assert emitted[-1][1] == "flat"
        assert emitted[-1][2] == 0.0
        assert emitted[-1][3] == [0.0] * 10
    finally:
        pop.deleteLater()


def test_fader_deck_mouse_drag_wheel_double_click_and_escape() -> None:
    _get_qapp()
    pop = EqualizerPopover(i18n=I18n("en"))
    try:
        pop.resize(454, 304)
        pop.fader_deck.resize(430, 220)
        pop.set_eq_enabled(True)

        emitted: list[tuple[bool, str, float, list[float]]] = []
        pop.eq_changed.connect(lambda en, pid, pre, b: emitted.append((en, pid, pre, b)))
        closed_events: list[bool] = []
        pop.closed.connect(lambda: closed_events.append(True))

        top, bot, preamp_x, band_xs, _div = pop.fader_deck._geometry_metrics()

        # Left-click drag near top of band 0 -> sets +12.0 dB and switches to Custom
        press_ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(band_xs[0], top),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        pop.fader_deck.mousePressEvent(press_ev)
        assert emitted[-1][1] == EQ_PRESET_CUSTOM
        assert emitted[-1][3][0] == 12.0

        # Release mouse
        rel_ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(band_xs[0], top),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        pop.fader_deck.mouseReleaseEvent(rel_ev)

        # Mouse wheel down on band 0 -> steps down by 0.5 dB to +11.5 dB
        wheel_ev = QWheelEvent(
            QPointF(band_xs[0], (top + bot) / 2.0),
            QPointF(band_xs[0], (top + bot) / 2.0),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        pop.fader_deck.wheelEvent(wheel_ev)
        assert emitted[-1][3][0] == 11.5

        # Double-click on band 0 -> snaps back to 0.0 dB
        dbl_ev = QMouseEvent(
            QMouseEvent.Type.MouseButtonDblClick,
            QPointF(band_xs[0], top),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        pop.fader_deck.mouseDoubleClickEvent(dbl_ev)
        assert emitted[-1][3][0] == 0.0

        # Left-click near bottom of Preamp column -> sets -12.0 dB, then right-click resets to 0.0
        pre_press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(preamp_x, bot),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        pop.fader_deck.mousePressEvent(pre_press)
        assert emitted[-1][2] == -12.0

        pre_rclick = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(preamp_x, bot),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        pop.fader_deck.mousePressEvent(pre_rclick)
        assert emitted[-1][2] == 0.0

        # Escape key triggers clean exit and emits closed
        esc_ev = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        )
        pop.keyPressEvent(esc_ev)
        assert closed_events == [True]
    finally:
        pop.deleteLater()


def test_playback_controls_eq_button_and_main_window_persistence(tmp_path) -> None:
    _get_qapp()
    from ui.main_window import ListenMoePlayer

    pb = PlaybackControls(i18n=I18n("en"))
    settings = QSettings(str(tmp_path / "eq_ui_test.ini"), QSettings.Format.IniFormat)
    calls: list[tuple[bool, float, list[float]]] = []
    eq_clicks: list[bool] = []
    pb.eq_clicked.connect(lambda: eq_clicks.append(True))

    fake_win: Any = SimpleNamespace(
        settings=settings,
        eq_button=pb.eq_button,
        player=SimpleNamespace(set_equalizer=lambda en, pre, b: calls.append((en, pre, list(b)))),
        log=logging.getLogger("test_win_eq_ui"),
    )
    fake_win._get_bool = lambda k, d: ListenMoePlayer._get_bool(fake_win, k, d)
    fake_win._load_equalizer_state = lambda: ListenMoePlayer._load_equalizer_state(fake_win)

    try:
        # Clicking eq_button emits PlaybackControls.eq_clicked
        pb.eq_button.click()
        assert eq_clicks == [True]

        # Persist custom curve via _on_eq_changed
        bands = [4.0, 2.0, 0.0, -1.0, 0.0, 1.5, 3.0, 4.5, 5.0, 3.5]
        ListenMoePlayer._on_eq_changed(fake_win, True, EQ_PRESET_CUSTOM, -2.5, bands)
        assert calls[-1] == (True, -2.5, bands)
        assert pb.eq_button.is_eq_enabled() is True
        assert settings.value(KEY_EQ_ENABLED) == "true"
        assert settings.value(KEY_EQ_PRESET) == EQ_PRESET_CUSTOM
        assert float(settings.value(KEY_EQ_PREAMP)) == -2.5
        assert parse_eq_bands(settings.value(KEY_EQ_BANDS)) == bands
        assert float(settings.value(KEY_EQ_CUSTOM_PREAMP)) == -2.5
        assert parse_eq_bands(settings.value(KEY_EQ_CUSTOM_BANDS)) == bands

        # Reload via _apply_equalizer_to_player (app restart / backend switch)
        calls.clear()
        pb.eq_button.set_eq_enabled(False)
        ListenMoePlayer._apply_equalizer_to_player(fake_win)
        assert calls[-1] == (True, -2.5, bands)
        assert pb.eq_button.is_eq_enabled() is True

        # Closing popover clears active highlight on eq_button
        pb.eq_button.set_active(True)
        ListenMoePlayer._on_eq_popover_closed(fake_win)
        assert pb.eq_button.is_active() is False
    finally:
        pb.deleteLater()
