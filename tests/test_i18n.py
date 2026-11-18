import ast
import string
from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication, QWidget

from core.config import get_station_display_name
from core.i18n import I18N, I18n, install_qt_translator
from core.local_playlist import LocalPlaylistManager
from core.updater import ReleaseInfo, SemVer
from ui.about_dialog import AboutDialog
from ui.custom_titlebar import CustomTitleBar
from ui.equalizer_popover import EqualizerPopover
from ui.local_queue_dialog import LocalQueueDialog
from ui.update_dialog import UpdateDialog
from ui.widgets.local_prompt_dialog import LocalMusicPromptDialog
from ui.widgets.playback_controls import PlaybackControls
from ui.widgets.sleep_timer_widget import SleepTimerWidget
from ui.widgets.station_pill import StationPillButton

ROOT_DIR = Path(__file__).resolve().parent.parent
UI_DIR = ROOT_DIR / "ui"

# Non-translatable literals permitted in Qt UI calls (brand names, codecs, tokens, symbols)
ALLOWED_UI_LITERALS = frozenset(
    {
        "",
        "...",
        "−",
        "+",
        "✕",
        "×",
        "▼",
        "▲",
        "▶",
        "🔊",
        "● LIVE",
        "LIVE",
        "IDLE",
        "AUDIO",
        "VORBIS",
        "OPUS",
        "MP3",
        "FLAC",
        "AAC",
        "Vorbis",
        "Opus",
        "Auto",
        "HEX",
        "KIKUMOE",
        "KikuMoe",
        "LISTEN.moe",
        "LISTEN.MOE",
        "Gensokyo Radio",
        "ANISON.FM",
        "Neuro 21",
        "TruckersFM",
        "J-POP",
        "K-POP",
        "Italiano",
        "English",
        "GitHub",
        "Discord",
        "Discord RPC",
        "Ctrl+,",
        "00:00",
        "00:00:00",
        "100%",
        "44.1 kHz",
        "44.1 / 48 kHz",
        "10m",
        "15m",
        "30m",
        "45m",
        "60m",
        "90m",
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "--:-- / --:--",
        "0",
        "1",
    }
)

# Qt setter methods and constructors whose first string argument is user-visible text.
TEXT_SETTER_METHODS = frozenset(
    {
        "setText",
        "setToolTip",
        "setPlaceholderText",
        "setWindowTitle",
        "set_badge_text",
        "setStatusTip",
        "setTitle",
    }
)
TEXT_WIDGET_CTORS = frozenset(
    {
        "QLabel",
        "QPushButton",
        "QAction",
        "QCheckBox",
        "QRadioButton",
        "QGroupBox",
        "AnimatedToggleSwitch",
        "BackToPlayerButton",
        "_AnimatedSleepBtn",
        "_make_card",
        "_make_field_row",
    }
)


def _iter_ui_py_files() -> Iterable[Path]:
    return sorted(p for p in UI_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def _extract_placeholders(template: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(template)
        if field_name is not None
    }


def test_i18n_key_parity_and_placeholders() -> None:
    it_keys = set(I18N["it"].keys())
    en_keys = set(I18N["en"].keys())
    assert it_keys == en_keys, (
        f"Missing in en: {sorted(it_keys - en_keys)}; Missing in it: {sorted(en_keys - it_keys)}"
    )

    for key in sorted(it_keys):
        it_val = I18N["it"][key]
        en_val = I18N["en"][key]
        assert isinstance(it_val, str) and it_val.strip(), f"Empty IT value for key: {key}"
        assert isinstance(en_val, str) and en_val.strip(), f"Empty EN value for key: {key}"
        assert _extract_placeholders(it_val) == _extract_placeholders(en_val), (
            f"Placeholder mismatch for key '{key}': IT={it_val!r} vs EN={en_val!r}"
        )


def test_ui_translation_keys_exist() -> None:
    missing: list[str] = []
    for path in _iter_ui_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in {"t", "_t"} and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                    key = arg0.value
                    # Skip non-i18n helpers if the method doesn't match a real translation key only
                    # when clearly on unrelated objects; check i18n/self attributes strictly.
                    owner = func.value
                    is_i18n_call = (
                        (isinstance(owner, ast.Name) and owner.id in {"i18n", "_i18n"})
                        or (isinstance(owner, ast.Attribute) and owner.attr in {"i18n", "_i18n"})
                        or (
                            isinstance(owner, ast.Name)
                            and owner.id == "self"
                            and func.attr in {"t", "_t"}
                        )
                    )
                    if is_i18n_call and (key not in I18N["it"] or key not in I18N["en"]):
                        missing.append(f"{path.relative_to(ROOT_DIR)}:{node.lineno} -> {key!r}")
    assert not missing, "Missing i18n keys referenced in UI:\n" + "\n".join(missing)


def test_no_hardcoded_ui_strings_ast() -> None:
    violations: list[str] = []

    def _check_literal(path: Path, lineno: int, label: str, literal: str) -> None:
        stripped = literal.strip()
        if stripped in ALLOWED_UI_LITERALS:
            return
        if not any(ch.isalpha() for ch in stripped):
            return
        # Allow numeric strings with unit suffix like '30m', '15 min', '100 ms', '10 px'
        tokens = stripped.replace("/", " ").split()
        if all(
            t in {"ms", "px", "MB", "kHz", "kbps", "Hz", "s", "m", "min"} or not t.isalpha()
            for t in tokens
        ):
            return
        # Allow HTML/rich-text CSS or purely numeric/symbol markup without words
        violations.append(f"{path.relative_to(ROOT_DIR)}:{lineno} ({label}): {stripped!r}")

    for path in _iter_ui_py_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            # Disallow inline `is_it = self.i18n.lang == "it"` UI branching hacks
            if isinstance(node, ast.Name) and node.id == "is_it":
                violations.append(
                    f"{path.relative_to(ROOT_DIR)}:{node.lineno} (inline branch): is_it"
                )
            if not isinstance(node, ast.Call):
                continue

            call_name: str | None = None
            arg_idx = 0
            if isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                if attr in TEXT_SETTER_METHODS:
                    call_name = attr
                    arg_idx = 0
                elif attr == "addItem":
                    call_name = attr
                    arg_idx = 0
            elif isinstance(node.func, ast.Name) and node.func.id in TEXT_WIDGET_CTORS:
                call_name = node.func.id
                arg_idx = 0

            if call_name is None or len(node.args) <= arg_idx:
                continue

            arg = node.args[arg_idx]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                _check_literal(path, node.lineno, call_name, arg.value)

    assert not violations, "Hardcoded UI strings detected:\n" + "\n".join(violations)


_APP: QApplication | None = None


def _ensure_qapp() -> QApplication:
    global _APP
    app = QApplication.instance()
    if isinstance(app, QApplication):
        _APP = app
        return app
    _APP = QApplication([])
    return _APP


def test_qt_translator_installs_for_it_and_en() -> None:
    app = _ensure_qapp()
    assert install_qt_translator(app, "it") is True
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "Annulla"

    assert install_qt_translator(app, "en") is True
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "Cancel"


def test_local_station_display_name_localized() -> None:
    assert get_station_display_name("local", I18n("it")) == "Musica Locale"
    assert get_station_display_name("local", I18n("en")) == "Local Music"
    assert get_station_display_name("listenmoe", I18n("en")) == "LISTEN.moe"


def test_widgets_render_en_and_retranslate() -> None:
    _ensure_qapp()
    mgr = LocalPlaylistManager()

    # LocalQueueDialog explicit EN and dynamic retranslate -> IT
    q_dlg = LocalQueueDialog(mgr, i18n=I18n("en"))
    assert q_dlg.titlebar._btn_close.toolTip() == I18N["en"]["window_close"]
    assert q_dlg.btn_add_files.text() == I18N["en"]["local_add_files"]
    assert q_dlg.btn_clear.text() == I18N["en"]["local_clear_queue"]
    assert q_dlg.search_box.placeholderText() == I18N["en"]["local_search_placeholder"]
    assert q_dlg.stats_lbl.text() == I18N["en"]["local_tracks_summary"].format(
        count=0, duration="00:00"
    )
    assert q_dlg.empty_title.text() == I18N["en"]["local_prompt_title"]

    q_dlg.retranslate(I18n("it"))
    assert q_dlg.titlebar._btn_close.toolTip() == I18N["it"]["window_close"]
    assert q_dlg.btn_add_files.text() == I18N["it"]["local_add_files"]
    assert q_dlg.btn_clear.text() == I18N["it"]["local_clear_queue"]
    assert q_dlg.search_box.placeholderText() == I18N["it"]["local_search_placeholder"]
    assert q_dlg.stats_lbl.text() == I18N["it"]["local_tracks_summary"].format(
        count=0, duration="00:00"
    )
    assert q_dlg.empty_title.text() == I18N["it"]["local_prompt_title"]
    q_dlg.close()

    # LocalQueueDialog inherits parent.i18n when i18n arg is omitted
    host = QWidget()
    host.i18n = I18n("en")  # type: ignore[attr-defined]
    inherited_dlg = LocalQueueDialog(mgr, parent=host)
    assert inherited_dlg.btn_add_files.text() == I18N["en"]["local_add_files"]
    assert inherited_dlg.empty_title.text() == I18N["en"]["local_prompt_title"]
    inherited_dlg.close()
    host.close()

    # LocalMusicPromptDialog in EN
    prompt_dlg = LocalMusicPromptDialog(mgr, i18n=I18n("en"))
    assert prompt_dlg._title_bar._ver_badge.text() == I18N["en"]["station_local"].upper()
    assert I18N["en"]["local_select_folder"] in prompt_dlg.btn_folder.text()
    assert I18N["en"]["local_select_files"] in prompt_dlg.btn_files.text()
    prompt_dlg.close()

    # PlaybackControls in EN -> retranslate IT
    pb = PlaybackControls(i18n=I18n("en"))
    assert pb.hero_play.toolTip() == I18N["en"]["tt_play_pause"]
    assert pb.btn_queue.toolTip() == I18N["en"]["tt_queue"]
    assert pb.eq_button.toolTip() == I18N["en"]["eq_button"]
    assert pb.chk_autoplay.text() == I18N["en"]["settings_autoplay"]
    pb.apply_translations(I18n("it"))
    assert pb.hero_play.toolTip() == I18N["it"]["tt_play_pause"]
    assert pb.btn_queue.toolTip() == I18N["it"]["tt_queue"]
    assert pb.eq_button.toolTip() == I18N["it"]["eq_button"]
    assert pb.chk_autoplay.text() == I18N["it"]["settings_autoplay"]
    pb.close()

    # EqualizerPopover in EN -> retranslate IT
    eq_pop = EqualizerPopover(i18n=I18n("en"))
    assert eq_pop.lbl_title.text() == I18N["en"]["eq_title"]
    assert eq_pop.btn_reset.text() == I18N["en"]["eq_reset"]
    eq_pop.retranslate(I18n("it"))
    assert eq_pop.lbl_title.text() == I18N["it"]["eq_title"]
    assert eq_pop.btn_reset.text() == I18N["it"]["eq_reset"]
    eq_pop.close()

    # SleepTimerWidget in EN -> retranslate IT
    sleep_w = SleepTimerWidget(i18n=I18n("en"))
    assert sleep_w.title_label.text() == I18N["en"]["sleep_timer"].upper()
    assert sleep_w.btn_start.text() == I18N["en"]["sleep_start"]
    assert sleep_w.btn_cancel.text() == I18N["en"]["sleep_cancel"]
    assert sleep_w.spin_minutes.toolTip() == I18N["en"]["sleep_custom_minutes_tip"]
    sleep_w.apply_translations(
        title=I18N["it"]["sleep_timer"],
        start_btn=I18N["it"]["sleep_start"],
        cancel_btn=I18N["it"]["sleep_cancel"],
        custom_minutes_tip=I18N["it"]["sleep_custom_minutes_tip"],
        toggle_tip=I18N["it"]["tt_sleep_toggle_drawer"],
    )
    assert sleep_w.title_label.text() == I18N["it"]["sleep_timer"].upper()
    assert sleep_w.btn_start.text() == I18N["it"]["sleep_start"]
    assert sleep_w.spin_minutes.toolTip() == I18N["it"]["sleep_custom_minutes_tip"]
    assert sleep_w.btn_close.toolTip() == I18N["it"]["tt_sleep_toggle_drawer"]
    sleep_w.close()

    # StationPillButton in EN -> retranslate IT
    pill = StationPillButton(initial_station="local", i18n=I18n("en"))
    assert pill.get_display_title() == "Local Music"
    assert pill.toolTip() == I18N["en"]["station_switch_tooltip"]
    pill.retranslate(I18n("it"))
    assert pill.get_display_title() == "Musica Locale"
    assert pill.toolTip() == I18N["it"]["station_switch_tooltip"]
    pill.close()

    # CustomTitleBar in EN -> retranslate IT
    tb_host = QWidget()
    tb = CustomTitleBar(tb_host, i18n=I18n("en"))
    assert tb._btn_min.toolTip() == I18N["en"]["window_minimize"]
    assert tb._btn_close.toolTip() == I18N["en"]["window_close"]
    tb.retranslate(I18n("it"))
    assert tb._btn_min.toolTip() == I18N["it"]["window_minimize"]
    assert tb._btn_close.toolTip() == I18N["it"]["window_close"]
    tb_host.close()

    # AboutDialog in EN -> retranslate IT
    about_dlg = AboutDialog(i18n=I18n("en"))
    assert about_dlg._title_bar._ver_badge.text() == I18N["en"]["about_badge"]
    about_dlg.retranslate(I18n("it"))
    assert about_dlg._title_bar._ver_badge.text() == I18N["it"]["about_badge"]
    about_dlg.close()

    # UpdateDialog in EN
    rel = ReleaseInfo(
        tag_name="v2.6.0",
        version_str="2.6.0",
        semver=SemVer.parse("2.6.0"),
        title="v2.6.0",
        body="",
        published_at="2026-01-01T00:00:00Z",
        html_url="https://example.com",
        is_prerelease=False,
        assets=[],
    )
    upd_dlg = UpdateDialog(rel, i18n=I18n("en"))
    assert upd_dlg.asset_info_lbl.text() == I18N["en"]["updates_available_github"]
    upd_dlg.close()
