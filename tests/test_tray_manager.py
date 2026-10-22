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
        self.settings = DummySettings({
            KEY_CHANNEL: "J-POP",
            KEY_FORMAT: "Vorbis",
        })


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
