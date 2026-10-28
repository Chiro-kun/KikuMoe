"""
Unit tests for Phase 8: Theme & Custom Accent Engine.
Covers preset switching, in-place PALETTE mutation, custom accent derivation,
dynamic QSS generation, SettingsDialog live preview/rollback/persistence,
and runtime widget theme propagation.
"""

import os
from typing import List, Optional, Tuple

import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

import ui.settings_dialog as settings_module
from core.constants import (
    DEFAULT_ACCENT_COLOR,
    DEFAULT_THEME,
    KEY_CUSTOM_ACCENT,
    KEY_CUSTOM_ACCENT_ENABLED,
    KEY_LANG,
    KEY_THEME,
    THEME_CYBER_MOE,
    THEME_MIDNIGHT_AMOLED,
    THEME_NEON_MATRIX,
    THEME_OCEAN_CYAN,
    THEME_SAKURA_BLOOM,
)
from core.i18n import I18N
from ui.about_dialog import AboutWidget
from ui.close_dialog import CloseConfirmDialog
from ui.custom_titlebar import CustomTitleBar
from ui.main_window import SmoothProgressBar
from ui.themes.cyber_moe import (
    PALETTE,
    THEME_ORDER,
    THEME_PRESETS,
    apply_theme_palette,
    derive_accent_tokens,
    get_cyber_moe_stylesheet,
    get_preset_default_accent,
    is_valid_hex_color,
    normalize_hex_color,
)
from ui.widgets.history_button import LyricsButton
from ui.widgets.lyrics_panel import LyricsPanel
from ui.widgets.mini_hud import MiniHud
from ui.widgets.playback_controls import PlaybackControls
from ui.widgets.sleep_timer_widget import SleepTimerWidget
from ui.widgets.station_pill import StationPillButton
from ui.widgets.status_footer import StatusFooter


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest"])
    return app


@pytest.fixture(autouse=True)
def reset_default_palette(qapp):
    """Ensure PALETTE and global QApplication stylesheet always start and finish on Cyber Moe."""
    apply_theme_palette(THEME_CYBER_MOE)
    qapp.setStyleSheet(get_cyber_moe_stylesheet())
    yield
    apply_theme_palette(THEME_CYBER_MOE)
    qapp.setStyleSheet(get_cyber_moe_stylesheet())


def test_five_curated_presets_and_inplace_palette_mutation():
    assert THEME_ORDER == (
        THEME_CYBER_MOE,
        THEME_MIDNIGHT_AMOLED,
        THEME_SAKURA_BLOOM,
        THEME_NEON_MATRIX,
        THEME_OCEAN_CYAN,
    )
    palette_id = id(PALETTE)

    for theme_id in THEME_ORDER:
        preset = THEME_PRESETS[theme_id]
        i18n_key = preset["i18n_key"]
        assert i18n_key in I18N["it"]
        assert i18n_key in I18N["en"]

        result = apply_theme_palette(theme_id)
        assert id(result) == palette_id
        assert id(PALETTE) == palette_id
        assert PALETTE["theme_id"] == theme_id
        assert PALETTE["accent"] == preset["default_accent"].lower()
        assert PALETTE["bg_main"] == preset["bg_main"]
        # GlassComboBox popup rendering requires opaque #RRGGBB bg_surface
        assert QColor(PALETTE["bg_surface"]).alpha() == 255

    # Midnight AMOLED specifically guarantees pure #000000 surfaces
    apply_theme_palette(THEME_MIDNIGHT_AMOLED)
    assert PALETTE["bg_main"] == "#000000"
    assert PALETTE["bg_canvas"] == "#000000"
    assert PALETTE["bg_dialog"] == "#000000"
    assert PALETTE["bg_terminal"] == "#000000"

    # Unknown preset falls back cleanly to Cyber Moe
    apply_theme_palette("non_existent_theme")
    assert PALETTE["theme_id"] == DEFAULT_THEME
    assert PALETTE["accent"] == DEFAULT_ACCENT_COLOR


def test_hex_validation_and_custom_accent_derivation():
    assert is_valid_hex_color("#ec186c") is True
    assert is_valid_hex_color("0af") is True
    assert is_valid_hex_color("#FF8800") is True
    assert is_valid_hex_color("") is False
    assert is_valid_hex_color("#12345") is False
    assert is_valid_hex_color("not-a-color") is False
    assert is_valid_hex_color(None) is False

    assert normalize_hex_color("#0AF") == "#00aaff"
    assert normalize_hex_color("FF8800") == "#ff8800"
    assert normalize_hex_color("invalid", fallback="#00e676") == "#00e676"

    tokens = derive_accent_tokens("#ff8800")
    assert tokens["accent"] == "#ff8800"
    assert tokens["accent_glow"] == "rgba(255, 136, 0, 0.35)"
    assert tokens["accent_subtle"] == "rgba(255, 136, 0, 0.15)"
    assert tokens["accent_menu_hover"] == "rgba(255, 136, 0, 0.25)"
    assert tokens["border_highlight"] == "rgba(255, 136, 0, 0.55)"
    assert is_valid_hex_color(tokens["accent_hover"])
    assert is_valid_hex_color(tokens["accent_pressed"])
    assert is_valid_hex_color(tokens["accent_shimmer"])
    assert is_valid_hex_color(tokens["text_accent"])

    # Contrast-aware foreground text on accent buttons
    bright_tokens = derive_accent_tokens("#ffff80")
    dark_tokens = derive_accent_tokens("#ec186c")
    assert bright_tokens["on_accent"] == "#080c12"
    assert dark_tokens["on_accent"] == "#ffffff"

    # Custom accent overrides preset accent while preserving preset surfaces
    apply_theme_palette(THEME_MIDNIGHT_AMOLED, custom_accent="#ff8800")
    assert PALETTE["theme_id"] == THEME_MIDNIGHT_AMOLED
    assert PALETTE["bg_main"] == "#000000"
    assert PALETTE["accent"] == "#ff8800"
    assert PALETTE["accent_glow"] == "rgba(255, 136, 0, 0.35)"

    # Invalid custom accent falls back to the selected preset's default accent
    apply_theme_palette(THEME_OCEAN_CYAN, custom_accent="invalid-hex")
    assert PALETTE["accent"] == get_preset_default_accent(THEME_OCEAN_CYAN)


def test_dynamic_stylesheet_reflects_preset_and_custom_accent():
    apply_theme_palette(THEME_NEON_MATRIX)
    css_matrix = get_cyber_moe_stylesheet()
    assert "#00e676" in css_matrix
    assert "#ec186c" not in css_matrix.lower()

    apply_theme_palette(THEME_MIDNIGHT_AMOLED, custom_accent="#ff8800")
    css_custom = get_cyber_moe_stylesheet()
    assert "#000000" in css_custom
    assert "#ff8800" in css_custom
    assert "rgba(255, 136, 0," in css_custom
    assert "#ec186c" not in css_custom.lower()


def test_settings_dialog_theme_preview_rollback_and_persistence(qapp, tmp_path, monkeypatch):
    ini_path = str(tmp_path / "theme_settings.ini")
    settings = QSettings(ini_path, QSettings.Format.IniFormat)
    monkeypatch.setattr(settings_module, "QSettings", lambda *args: settings)

    class DummyHost(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.calls: List[Tuple[Optional[str], Optional[str], Optional[bool]]] = []

        def apply_theme(
            self,
            theme_id: Optional[str] = None,
            custom_accent: Optional[str] = None,
            use_custom_accent: Optional[bool] = None,
        ) -> None:
            self.calls.append((theme_id, custom_accent, use_custom_accent))
            if theme_id is None:
                saved_tid = str(settings.value(KEY_THEME, DEFAULT_THEME))
                saved_on = settings.value(KEY_CUSTOM_ACCENT_ENABLED, "false") == "true"
                saved_hex = str(settings.value(KEY_CUSTOM_ACCENT, "") or "")
                apply_theme_palette(saved_tid, custom_accent=saved_hex if saved_on else None)
            else:
                apply_theme_palette(
                    theme_id,
                    custom_accent=custom_accent if use_custom_accent else None,
                )

    host = DummyHost()
    dlg = settings_module.SettingsDialog(host, embedded=True)
    dlg.resize(400, 650)
    dlg.show()
    qapp.processEvents()

    assert dlg.cmb_theme.count() == 5
    assert dlg.cmb_theme.currentData() == THEME_CYBER_MOE
    assert dlg.custom_accent_row.isHidden()

    # 1. Selecting Ocean Cyan triggers live preview immediately without saving
    ocean_idx = dlg.cmb_theme.findData(THEME_OCEAN_CYAN)
    assert ocean_idx >= 0
    dlg.cmb_theme.setCurrentIndex(ocean_idx)
    assert PALETTE["theme_id"] == THEME_OCEAN_CYAN
    assert PALETTE["accent"] == "#00d2ff"
    assert settings.value(KEY_THEME, DEFAULT_THEME) == DEFAULT_THEME

    # 2. Enabling Custom Accent reveals swatch row and previews chosen color
    dlg.chk_custom_accent.setChecked(True)
    assert not dlg.custom_accent_row.isHidden()
    dlg.btn_accent_swatch.set_color("#ff8800", emit_signal=True)
    assert PALETTE["accent"] == "#ff8800"

    # 3. Reset button restores active preset default accent (#00d2ff for Ocean Cyan)
    dlg.btn_accent_reset.click()
    assert dlg.btn_accent_swatch.color() == "#00d2ff"
    assert PALETTE["accent"] == "#00d2ff"

    # Re-apply a custom color before testing Cancel rollback
    dlg.btn_accent_swatch.set_color("#a855f7", emit_signal=True)
    assert PALETTE["accent"] == "#a855f7"

    # 4. Rejecting (Cancel / '< Player') rolls back live preview to persisted Cyber Moe
    dlg.reject()
    assert PALETTE["theme_id"] == THEME_CYBER_MOE
    assert PALETTE["accent"] == DEFAULT_ACCENT_COLOR

    # 5. Re-open, select Sakura Bloom + custom accent, and click Apply to persist
    dlg.reload_from_settings()
    sakura_idx = dlg.cmb_theme.findData(THEME_SAKURA_BLOOM)
    dlg.cmb_theme.setCurrentIndex(sakura_idx)
    dlg.chk_custom_accent.setChecked(True)
    dlg.btn_accent_swatch.set_color("#ff99cc", emit_signal=True)
    dlg.btn_apply.click()

    assert settings.value(KEY_THEME) == THEME_SAKURA_BLOOM
    assert settings.value(KEY_CUSTOM_ACCENT_ENABLED) == "true"
    assert settings.value(KEY_CUSTOM_ACCENT) == "#ff99cc"
    assert PALETTE["theme_id"] == THEME_SAKURA_BLOOM
    assert PALETTE["accent"] == "#ff99cc"
    assert dlg._apply_toast.text() == "Impostazioni salvate"

    # Clicking Apply again without changes reports unchanged
    dlg.btn_apply.click()
    assert dlg._apply_toast.text() == "Nessuna modifica da applicare"

    # 6. Reloading in English localizes preset names
    settings.setValue(KEY_LANG, "en")
    dlg.reload_from_settings()
    assert dlg.lbl_theme.text() == I18N["en"]["settings_theme"]
    assert dlg.cmb_theme.itemText(0) == I18N["en"]["theme_cyber_moe"]
    dlg.close()


def test_widgets_refresh_theme_across_presets_and_custom_accents(qapp):
    bar = SmoothProgressBar()
    bar.resize(240, 16)
    bar.setMaximum(100)
    bar.setValue(50)

    controls = PlaybackControls()
    controls.resize(360, 110)

    sleep_widget = SleepTimerWidget()
    sleep_widget.resize(360, 95)
    sleep_widget.set_active_countdown(600)

    footer = StatusFooter()
    footer.set_backend_status("MPV", is_ready=True)
    footer.set_format("OPUS")

    mini = MiniHud()
    mini.resize(420, 112)

    host = QWidget()
    title_bar = CustomTitleBar(host)
    title_bar.resize(400, CustomTitleBar.HEIGHT)

    lyrics = LyricsPanel()
    lyrics.show_record({"syncedLyrics": "[00:01.00] Hello world"}, "Plain")
    lyrics.set_position(2.0)

    lyrics_btn = LyricsButton()
    lyrics_btn.setChecked(True)

    station_pill = StationPillButton()
    about = AboutWidget()

    # Switch to Neon Matrix with custom orange accent and refresh all widgets
    apply_theme_palette(THEME_NEON_MATRIX, custom_accent="#ff8800")
    qapp.setStyleSheet(get_cyber_moe_stylesheet())

    bar.refresh_theme()
    controls.refresh_theme()
    sleep_widget.refresh_theme()
    footer.refresh_theme()
    mini.refresh_theme()
    title_bar.refresh_theme()
    lyrics.refresh_theme()
    lyrics_btn.refresh_theme()
    station_pill.refresh_theme()
    about.refresh_theme()

    assert bar._accent_color.name().lower() == "#ff8800"
    assert controls.hero_play._custom_accent is None
    assert "#ff8800" in qapp.styleSheet().lower()
    assert PALETTE["accent_hover"].lower() in footer.codec_dot.styleSheet().lower()
    assert "#ff8800" in mini.styleSheet().lower()
    assert lyrics._accent.lower() == "#ff8800"
    assert lyrics_btn._custom_accent is None
    assert station_pill._accent.name().lower() == "#ff8800"

    # Render custom-painted widgets offscreen to verify paintEvent succeeds cleanly
    for widget in (bar, controls, sleep_widget, footer, mini, title_bar, lyrics_btn, station_pill):
        pm = QPixmap(max(1, widget.width()), max(1, widget.height()))
        pm.fill(Qt.GlobalColor.transparent)
        widget.render(pm)

    close_dlg = CloseConfirmDialog()
    pm_dlg = QPixmap(close_dlg.size())
    pm_dlg.fill(Qt.GlobalColor.transparent)
    close_dlg.render(pm_dlg)
    close_dlg.close()


def test_main_window_apply_theme_preview_and_persisted_lookup(qapp, tmp_path):
    from types import SimpleNamespace

    from ui.main_window import ListenMoePlayer

    ini_path = str(tmp_path / "window_theme.ini")
    settings = QSettings(ini_path, QSettings.Format.IniFormat)
    settings.setValue(KEY_THEME, THEME_NEON_MATRIX)
    settings.setValue(KEY_CUSTOM_ACCENT_ENABLED, "true")
    settings.setValue(KEY_CUSTOM_ACCENT, "#38bdf8")

    host = SimpleNamespace(
        settings=settings,
        COLOR_ACCENT=DEFAULT_ACCENT_COLOR,
        song_progress=SmoothProgressBar(),
        sleep_timer_widget=SleepTimerWidget(),
        status_footer=StatusFooter(),
        lyrics_panel=LyricsPanel(),
        lyrics_button=LyricsButton(),
        playback_controls=PlaybackControls(),
        mini_hud=MiniHud(),
        update=lambda: None,
    )
    host._get_bool = lambda key, default: ListenMoePlayer._get_bool(host, key, default)
    host._refresh_time_row_styles = lambda: ListenMoePlayer._refresh_time_row_styles(host)

    # 1. Calling apply_theme() without args loads persisted Neon Matrix + #38bdf8
    ListenMoePlayer.apply_theme(host)
    assert PALETTE["theme_id"] == THEME_NEON_MATRIX
    assert PALETTE["accent"] == "#38bdf8"
    assert host.COLOR_ACCENT == "#38bdf8"
    assert host.song_progress._accent_color.name().lower() == "#38bdf8"

    # 2. Live preview override applies Midnight AMOLED preset default without mutating QSettings
    ListenMoePlayer.apply_theme(
        host,
        theme_id=THEME_MIDNIGHT_AMOLED,
        custom_accent="#ff0000",
        use_custom_accent=False,
    )
    assert PALETTE["theme_id"] == THEME_MIDNIGHT_AMOLED
    assert PALETTE["bg_main"] == "#000000"
    assert PALETTE["accent"] == get_preset_default_accent(THEME_MIDNIGHT_AMOLED)

    # 3. Calling apply_theme() again restores persisted Neon Matrix + #38bdf8
    ListenMoePlayer.apply_theme(host)
    assert PALETTE["theme_id"] == THEME_NEON_MATRIX
    assert PALETTE["accent"] == "#38bdf8"

    # 4. Calling apply_theme() with identical state is an O(1) idempotent no-op
    update_calls = []
    host.update = lambda: update_calls.append(True)
    ListenMoePlayer.apply_theme(host)
    assert update_calls == []

    # force=True bypasses the idempotency short-circuit when explicitly requested
    ListenMoePlayer.apply_theme(host, force=True)
    assert update_calls == [True]


def test_modular_per_theme_files_and_canvas_cache_and_qss_dedup(qapp, tmp_path, monkeypatch):
    from ui.themes import engine
    from ui.themes.cyber_moe import CYBER_MOE_PRESET
    from ui.themes.midnight_amoled import MIDNIGHT_AMOLED_PRESET
    from ui.themes.neon_matrix import NEON_MATRIX_PRESET
    from ui.themes.ocean_cyan import OCEAN_CYAN_PRESET
    from ui.themes.sakura_bloom import SAKURA_BLOOM_PRESET
    from ui.widgets.ambient_cover import FullBleedCanvas

    # 1. Each theme lives in its own dedicated module and matches THEME_PRESETS
    assert THEME_PRESETS[THEME_CYBER_MOE] is CYBER_MOE_PRESET
    assert THEME_PRESETS[THEME_MIDNIGHT_AMOLED] is MIDNIGHT_AMOLED_PRESET
    assert THEME_PRESETS[THEME_SAKURA_BLOOM] is SAKURA_BLOOM_PRESET
    assert THEME_PRESETS[THEME_NEON_MATRIX] is NEON_MATRIX_PRESET
    assert THEME_PRESETS[THEME_OCEAN_CYAN] is OCEAN_CYAN_PRESET
    assert engine.PALETTE is PALETTE

    # 2. FullBleedCanvas caches steady-state HiDPI backdrop frames and invalidates on theme change
    canvas = FullBleedCanvas()
    canvas.resize(320, 480)
    pm1 = QPixmap(canvas.size())
    canvas.render(pm1)
    cached_first = canvas._cached_frame
    assert cached_first is not None

    pm2 = QPixmap(canvas.size())
    canvas.render(pm2)
    assert canvas._cached_frame is cached_first

    apply_theme_palette(THEME_OCEAN_CYAN)
    canvas.refresh_theme()
    assert canvas._cached_frame is None
    canvas.render(pm2)
    assert canvas._cached_frame is not None
    assert canvas._cached_frame is not cached_first

    # 3. Embedded SettingsDialog deduplicates global QSS and skips rollback when untouched
    ini_path = str(tmp_path / "perf_settings.ini")
    settings = QSettings(ini_path, QSettings.Format.IniFormat)
    monkeypatch.setattr(settings_module, "QSettings", lambda *args: settings)

    class SpyHost(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.apply_calls = 0

        def apply_theme(self, *args, **kwargs) -> None:
            self.apply_calls += 1

    apply_theme_palette(THEME_CYBER_MOE)
    qapp.setStyleSheet(get_cyber_moe_stylesheet())

    spy_host = SpyHost()
    dlg = settings_module.SettingsDialog(spy_host, embedded=True)
    # Global rules like QWidget#mainWindowRoot are not duplicated on embedded SettingsDialog
    assert "QWidget#mainWindowRoot" not in dlg.styleSheet()
    assert "QDialog#settingsEmbeddedPanel" in dlg.styleSheet()

    # Closing/rejecting without touching theme controls performs zero redundant apply_theme calls
    dlg.reject()
    assert spy_host.apply_calls == 0
    dlg.close()


def test_portaudio_device_enumeration_thread_safety_and_close_cancellation(
    qapp, tmp_path, monkeypatch
):
    import sys
    import threading
    import time
    from types import SimpleNamespace

    ini_path = str(tmp_path / "pa_safety.ini")
    settings = QSettings(ini_path, QSettings.Format.IniFormat)
    monkeypatch.setattr(settings_module, "QSettings", lambda *args: settings)
    monkeypatch.setattr(settings_module, "_CACHED_AUDIO_DEVICES", None)

    state_lock = threading.Lock()
    active_count = 0
    max_concurrent = 0
    init_calls = 0

    class FakePyAudioInstance:
        def get_host_api_count(self) -> int:
            return 1

        def get_host_api_info_by_index(self, _idx: int) -> dict:
            return {"type": 13}

        def get_device_count(self) -> int:
            time.sleep(0.015)
            return 1

        def get_device_info_by_index(self, _idx: int) -> dict:
            return {"name": "Test DAC", "maxOutputChannels": 2, "hostApi": 0}

        def terminate(self) -> None:
            nonlocal active_count
            with state_lock:
                active_count -= 1

    def make_fake_pa() -> FakePyAudioInstance:
        nonlocal active_count, max_concurrent, init_calls
        with state_lock:
            init_calls += 1
            active_count += 1
            if active_count > max_concurrent:
                max_concurrent = active_count
        return FakePyAudioInstance()

    monkeypatch.setitem(sys.modules, "pyaudio", SimpleNamespace(PyAudio=make_fake_pa))

    # 1. Showing and immediately closing SettingsDialog cancels _device_enum_timer
    dlg = settings_module.SettingsDialog(embedded=True)
    dlg.show()
    assert dlg._device_enum_timer.isActive()
    dlg.close()
    assert not dlg._device_enum_timer.isActive()
    assert dlg._is_closed is True
    assert init_calls == 0

    # 2. Four concurrent force_refresh threads strictly serialize Pa_Initialize/Pa_Terminate
    barrier = threading.Barrier(4)
    results: List[List[Tuple[str, int]]] = []

    def _runner() -> None:
        barrier.wait()
        res = settings_module.SettingsDialog._collect_pyaudio_devices(force_refresh=True)
        with state_lock:
            results.append(res)

    threads = [threading.Thread(target=_runner) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert max_concurrent == 1
    assert active_count == 0
    assert len(results) == 4
    assert all(len(r) == 1 for r in results)

    # 3. Subsequent non-forced lookup reuses _CACHED_AUDIO_DEVICES with zero extra Pa_Initialize
    prev_inits = init_calls
    cached = settings_module.SettingsDialog._collect_pyaudio_devices(force_refresh=False)
    assert len(cached) == 1
    assert init_calls == prev_inits
