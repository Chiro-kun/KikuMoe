import os
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication, QWidget

from core.constants import KEY_CHANNEL, KEY_FORMAT
from ui.tray_manager import TrayManager


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest"])
    return app


class DummySettings:
    def __init__(self, initial_values=None):
        self._values = initial_values or {}

    def value(self, key, default=None):
        return self._values.get(key, default)

    def setValue(self, key, val):
        self._values[key] = val


class DummyParent(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = DummySettings(
            {
                KEY_CHANNEL: "J-POP",
                KEY_FORMAT: "Vorbis",
            }
        )


def test_tray_manager_initial_sync(qapp):
    parent = DummyParent()
    i18n = MagicMock()
    i18n.t.side_effect = lambda key: key

    channel_callback = MagicMock()
    format_callback = MagicMock()

    tray_mgr = TrayManager(
        parent=parent,
        i18n=i18n,
        on_change_channel=channel_callback,
        on_change_format=format_callback,
    )
    tray_mgr.ensure_tray_enabled(True)

    # Verifica che le azioni siano state registrate
    assert "listenmoe" in tray_mgr._station_actions
    assert "gensokyo" in tray_mgr._station_actions
    assert "anison" in tray_mgr._station_actions
    assert tray_mgr._station_actions["listenmoe"].isChecked() is True
    assert "J-POP" in tray_mgr._channel_actions
    assert "K-POP" in tray_mgr._channel_actions
    assert "Vorbis" in tray_mgr._format_actions
    assert "Opus" in tray_mgr._format_actions
    assert "MP3" in tray_mgr._format_actions

    # Verifica che le selezioni iniziali corrispondano a QSettings
    assert tray_mgr._channel_actions["J-POP"].isChecked() is True
    assert tray_mgr._channel_actions["K-POP"].isChecked() is False
    assert tray_mgr._format_actions["Vorbis"].isChecked() is True
    assert tray_mgr._format_actions["Opus"].isChecked() is False
    assert tray_mgr._format_actions["MP3"].isChecked() is False


def test_tray_manager_sync_stream_settings_explicit(qapp):
    parent = DummyParent()
    i18n = MagicMock()
    i18n.t.side_effect = lambda key: key

    channel_callback = MagicMock()
    format_callback = MagicMock()

    tray_mgr = TrayManager(
        parent=parent,
        i18n=i18n,
        on_change_channel=channel_callback,
        on_change_format=format_callback,
    )
    tray_mgr.ensure_tray_enabled(True)

    # Sincronizza esplicitamente su K-POP e Opus
    tray_mgr.sync_stream_settings(channel="K-POP", fmt="Opus")

    assert tray_mgr._channel_actions["K-POP"].isChecked() is True
    assert tray_mgr._channel_actions["J-POP"].isChecked() is False
    assert tray_mgr._format_actions["Opus"].isChecked() is True
    assert tray_mgr._format_actions["Vorbis"].isChecked() is False
    assert tray_mgr._format_actions["MP3"].isChecked() is False

    # Assicurati che i callback non siano stati scatenati dalla sincronizzazione programmatica
    assert channel_callback.call_count == 0
    assert format_callback.call_count == 0


def test_tray_manager_sync_stream_settings_from_settings(qapp):
    parent = DummyParent()
    i18n = MagicMock()
    i18n.t.side_effect = lambda key: key

    tray_mgr = TrayManager(parent=parent, i18n=i18n)
    tray_mgr.ensure_tray_enabled(True)

    # Cambia le impostazioni nel genitore simulando il salvataggio da SettingsDialog
    parent.settings.setValue(KEY_CHANNEL, "K-POP")
    parent.settings.setValue(KEY_FORMAT, "MP3")

    tray_mgr.sync_stream_settings()

    assert tray_mgr._channel_actions["K-POP"].isChecked() is True
    assert tray_mgr._channel_actions["J-POP"].isChecked() is False
    assert tray_mgr._format_actions["MP3"].isChecked() is True
    assert tray_mgr._format_actions["Vorbis"].isChecked() is False
    assert tray_mgr._format_actions["Opus"].isChecked() is False


def test_tray_manager_on_quit_triggered(qapp):
    parent = DummyParent()
    i18n = MagicMock()
    i18n.t.side_effect = lambda key: key
    quit_callback = MagicMock()

    tray_mgr = TrayManager(parent=parent, i18n=i18n, on_quit=quit_callback)
    tray_mgr.ensure_tray_enabled(True)

    assert tray_mgr._act_quit is not None
    tray_mgr._act_quit.trigger()
    assert quit_callback.call_count == 1


def test_tray_manager_settings_and_about_actions(qapp):
    parent = DummyParent()
    i18n = MagicMock()
    i18n.t.side_effect = lambda key: key
    settings_cb = MagicMock()
    about_cb = MagicMock()

    tray_mgr = TrayManager(
        parent=parent,
        i18n=i18n,
        on_open_settings=settings_cb,
        on_about=about_cb,
    )
    tray_mgr.ensure_tray_enabled(True)

    assert tray_mgr._act_settings is not None
    assert tray_mgr._act_about is not None

    tray_mgr._act_settings.trigger()
    assert settings_cb.call_count == 1

    tray_mgr._act_about.trigger()
    assert about_cb.call_count == 1


def test_tray_manager_now_playing_card_integration(qapp):
    from PyQt6.QtGui import QColor, QPixmap

    parent = DummyParent()
    i18n = MagicMock()
    i18n.t.side_effect = lambda key: key

    play_cb = MagicMock()
    stop_cb = MagicMock()
    mute_cb = MagicMock()
    history_cb = MagicMock()
    show_cb = MagicMock()

    parent.toggle_history_popover = history_cb

    tray_mgr = TrayManager(
        parent=parent,
        i18n=i18n,
        on_show_window=show_cb,
        on_toggle_play_pause=play_cb,
        on_stop_stream=stop_cb,
        on_toggle_mute=mute_cb,
    )
    tray_mgr.ensure_tray_enabled(True)

    # 1. Card should be initialized and added
    assert tray_mgr._card is not None
    assert tray_mgr._card_action is not None
    assert tray_mgr._card_action.defaultWidget() == tray_mgr._card

    # 2. Update tooltip and check metadata extraction
    tooltip_text = "LISTEN.moe (J-POP • Vorbis)\nPoison — Alice Cooper\nSessione: 05:20"
    tray_mgr.update_tooltip(tooltip_text)

    assert "Poison" in tray_mgr._card._lbl_title.text()
    assert "Alice Cooper" in tray_mgr._card._lbl_artist.text()
    assert "05:20" in tray_mgr._card._lbl_session.text()

    # 3. Update cover pixmap (58x58 px)
    pm = QPixmap(100, 100)
    pm.fill(QColor("magenta"))
    tray_mgr.set_cover_pixmap(pm)
    assert tray_mgr._card._cover_lbl.pixmap() is not None
    assert not tray_mgr._card._cover_lbl.pixmap().isNull()
    assert tray_mgr._card._cover_lbl.width() == 58
    assert tray_mgr._card._cover_lbl.height() == 58

    # Reset cover pixmap to None (fallback)
    tray_mgr.set_cover_pixmap(None)
    assert tray_mgr._card._cover_lbl.pixmap() is not None

    # 4. Update controls state
    tray_mgr.update_controls_state(is_playing=True, is_paused=False, is_muted=True)
    assert tray_mgr._card._is_playing is True
    assert tray_mgr._card._is_muted is True
    assert tray_mgr._act_play_pause.text() == "pause"
    assert tray_mgr._act_mute.text() == "tray_unmute"

    tray_mgr.update_controls_state(is_playing=False, is_paused=False, is_muted=False)
    assert tray_mgr._act_play_pause.text() == "play"
    assert tray_mgr._act_mute.text() == "tray_mute"

    # 5. Sync controls from parent player
    mock_player = MagicMock()
    mock_player.is_playing.return_value = True
    mock_player.is_paused.return_value = False
    mock_player.is_muted.return_value = False
    parent.player = mock_player
    tray_mgr._sync_controls_from_parent()
    assert tray_mgr._card._is_playing is True
    assert tray_mgr._card._is_paused is False


def test_tray_manager_card_inline_buttons(qapp):
    parent = DummyParent()
    i18n = MagicMock()
    i18n.t.side_effect = lambda key: key

    play_cb = MagicMock()
    stop_cb = MagicMock()
    mute_cb = MagicMock()
    history_cb = MagicMock()

    parent.toggle_history_popover = history_cb

    tray_mgr = TrayManager(
        parent=parent,
        i18n=i18n,
        on_toggle_play_pause=play_cb,
        on_stop_stream=stop_cb,
        on_toggle_mute=mute_cb,
    )
    tray_mgr.ensure_tray_enabled(True)

    card = tray_mgr._card
    assert card is not None

    # Trigger inline buttons
    card._btn_play.click()
    assert play_cb.call_count == 1

    card._btn_stop.click()
    assert stop_cb.call_count == 1

    card._btn_mute.click()
    assert mute_cb.call_count == 1

    card._btn_history.click()
    assert history_cb.call_count == 1


def test_tray_manager_vector_icons_and_theme_refresh(qapp):
    parent = DummyParent()
    i18n = MagicMock()
    i18n.t.side_effect = lambda key: key

    tray_mgr = TrayManager(parent=parent, i18n=i18n)
    tray_mgr.ensure_tray_enabled(True)

    # Verify all action vector icons are set and non-null
    assert not tray_mgr._act_play_pause.icon().isNull()
    assert not tray_mgr._act_stop.icon().isNull()
    assert not tray_mgr._act_mute.icon().isNull()
    assert not tray_mgr._act_history.icon().isNull()
    assert not tray_mgr._act_show.icon().isNull()
    assert not tray_mgr._act_settings.icon().isNull()
    assert not tray_mgr._act_about.icon().isNull()
    assert not tray_mgr._act_st.icon().isNull()
    assert not tray_mgr._act_ch.icon().isNull()
    assert not tray_mgr._act_fmt.icon().isNull()
    assert not tray_mgr._act_quit.icon().isNull()

    # Trigger theme refresh
    tray_mgr.refresh_theme()

    # Ensure icons remain valid after theme refresh
    assert not tray_mgr._act_settings.icon().isNull()
    assert not tray_mgr._act_quit.icon().isNull()


def test_tray_menu_clean_layout(qapp):
    parent = DummyParent()
    i18n = MagicMock()
    i18n.t.side_effect = lambda key: key

    tray_mgr = TrayManager(parent=parent, i18n=i18n)
    tray_mgr.ensure_tray_enabled(True)

    assert tray_mgr._tray is not None
    menu = tray_mgr._tray.contextMenu()
    assert menu is not None
    actions = menu.actions()

    # The card must be the first action in the menu
    assert actions[0] == tray_mgr._card_action

    # Redundant actions must NOT be present in the visible menu actions
    assert tray_mgr._act_play_pause not in actions
    assert tray_mgr._act_stop not in actions
    assert tray_mgr._act_mute not in actions
    assert tray_mgr._act_history not in actions
    assert tray_mgr._act_hdr_playback not in actions

    # Window, settings, prefs, and quit actions MUST be in the menu
    assert tray_mgr._act_show in actions
    assert tray_mgr._act_settings in actions
    assert tray_mgr._act_about in actions
    assert tray_mgr._act_quit in actions
