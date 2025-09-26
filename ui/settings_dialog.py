from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QPushButton, QLineEdit, QFileDialog, QSpinBox
)
from PyQt5.QtCore import Qt, QSettings, pyqtSignal
from i18n import I18n
from constants import (
    ORG_NAME,
    APP_SETTINGS,
    KEY_LANG,
    KEY_CHANNEL,
    KEY_FORMAT,
    KEY_AUTOPLAY,
    KEY_TRAY_ENABLED,
    KEY_TRAY_NOTIFICATIONS,
    KEY_TRAY_HIDE_ON_MINIMIZE,
    KEY_LIBVLC_PATH,
    KEY_NETWORK_CACHING,
    KEY_DARK_MODE,
    KEY_SLEEP_STOP_ON_END,
    KEY_DEV_CONSOLE_ENABLED,
    KEY_SESSION_TIMER_ENABLED,
    KEY_AUDIO_DEVICE_INDEX,
    KEY_DEV_CONSOLE_SHOW_DEV,
)

class SettingsDialog(QDialog):
    settings_changed = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        # Rendi il dialogo non modale per permettere interazione con altre finestre (es. DevConsole)
        self.setModal(False)
        self.settings = QSettings(ORG_NAME, APP_SETTINGS)
        self.i18n = I18n(self.settings.value(KEY_LANG, 'it'))
        self.setWindowTitle(self.i18n.t('settings_title'))
        try:
            self.setMinimumSize(560, 360)
        except Exception:
            pass

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Autoplay
        self.chk_autoplay = QCheckBox(self.i18n.t('settings_autoplay'))
        self.chk_autoplay.setChecked(self.settings.value(KEY_AUTOPLAY, 'false') == 'true')
        self.chk_autoplay.setToolTip(self.i18n.t('settings_autoplay_tip') if hasattr(self.i18n, 't') else '')
        layout.addWidget(self.chk_autoplay)

        # Dark Mode
        self.chk_dark_mode = QCheckBox(self.i18n.t('settings_dark_mode'))
        self.chk_dark_mode.setChecked(self.settings.value(KEY_DARK_MODE, 'false') == 'true')
        layout.addWidget(self.chk_dark_mode)

        # Sleep Timer option: stop on end
        self.chk_sleep_stop = QCheckBox(self.i18n.t('settings_sleep_stop_on_end'))
        self.chk_sleep_stop.setChecked(self.settings.value(KEY_SLEEP_STOP_ON_END, 'true') == 'true')
        layout.addWidget(self.chk_sleep_stop)

        # Session timer enable
        self.chk_session_timer = QCheckBox(self.i18n.t('settings_session_timer_enable'))
        self.chk_session_timer.setToolTip(self.i18n.t('settings_session_timer_tip'))
        self.chk_session_timer.setChecked(self.settings.value(KEY_SESSION_TIMER_ENABLED, 'true') == 'true')
        layout.addWidget(self.chk_session_timer)

        # Developer Console (optional)
        self.chk_dev_console = QCheckBox(self.i18n.t('settings_dev_console'))
        self.chk_dev_console.setChecked(self.settings.value(KEY_DEV_CONSOLE_ENABLED, 'false') == 'true')
        # Row with checkbox + open button
        dev_row = QHBoxLayout()
        dev_row.setSpacing(8)
        dev_row.addWidget(self.chk_dev_console)
        self.btn_open_console = QPushButton(self.i18n.t('dev_console_button'))
        try:
            self.btn_open_console.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
        except Exception:
            pass
        # Mantieni il pulsante sempre abilitato, indipendentemente dallo stato della checkbox
        self.btn_open_console.setEnabled(True)
        self.btn_open_console.clicked.connect(self._on_open_console)
        dev_row.addStretch(1)
        dev_row.addWidget(self.btn_open_console)
        layout.addLayout(dev_row)
        # RIMOSSO: non disabilitare più il pulsante quando la console è disattivata
        # self.chk_dev_console.stateChanged.connect(lambda s: self.btn_open_console.setEnabled(self.chk_dev_console.isChecked()))

        # New: show [DEV] tagged messages toggle (only meaningful when console enabled)
        self.chk_dev_show_dev = QCheckBox(self.i18n.t('settings_dev_console_show_dev'))
        self.chk_dev_show_dev.setChecked(self.settings.value(KEY_DEV_CONSOLE_SHOW_DEV, 'false') == 'true')
        self.chk_dev_show_dev.setEnabled(self.chk_dev_console.isChecked())
        # sync enabled state
        self.chk_dev_console.stateChanged.connect(lambda s: self.chk_dev_show_dev.setEnabled(self.chk_dev_console.isChecked()))
        layout.addWidget(self.chk_dev_show_dev)

        # Language
        lang_row = QHBoxLayout()
        lang_row.setSpacing(8)
        lab_lang = QLabel(self.i18n.t('settings_language'))
        lab_lang.setMinimumWidth(140)
        lang_row.addWidget(lab_lang)
        self.cmb_lang = QComboBox()
        self.cmb_lang.addItems(['Italiano', 'English'])
        self.cmb_lang.setCurrentIndex(0 if self.settings.value(KEY_LANG, 'it') == 'it' else 1)
        try:
            self.cmb_lang.setMinimumWidth(160)
        except Exception:
            pass
        lang_row.addWidget(self.cmb_lang, 1)
        layout.addLayout(lang_row)

        # Channel & Format
        ch_row = QHBoxLayout()
        ch_row.setSpacing(8)
        lab_ch = QLabel(self.i18n.t('settings_channel'))
        lab_ch.setMinimumWidth(140)
        ch_row.addWidget(lab_ch)
        self.cmb_channel = QComboBox()
        self.cmb_channel.addItems(['J-POP', 'K-POP'])
        self.cmb_channel.setCurrentText(self.settings.value(KEY_CHANNEL, 'J-POP'))
        ch_row.addWidget(self.cmb_channel, 1)
        layout.addLayout(ch_row)

        # Format
        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(8)
        lab_fmt = QLabel(self.i18n.t('settings_format'))
        lab_fmt.setMinimumWidth(140)
        fmt_row.addWidget(lab_fmt)
        self.cmb_format = QComboBox()
        try:
            self.cmb_format.addItems(['Vorbis', 'MP3'])
        except Exception:
            pass
        try:
            self.cmb_format.setMinimumWidth(160)
        except Exception:
            pass
        self.cmb_format.setCurrentText(self.settings.value(KEY_FORMAT, 'Vorbis'))
        fmt_row.addWidget(self.cmb_format, 1)
        layout.addLayout(fmt_row)

        # Audio Output Device
        audio_row = QHBoxLayout()
        audio_row.setSpacing(8)
        lab_audio = QLabel(self.i18n.t('settings_audio_output'))
        lab_audio.setMinimumWidth(140)
        audio_row.addWidget(lab_audio)
        self.cmb_audio_device = QComboBox()
        try:
            self.cmb_audio_device.setMinimumWidth(260)
        except Exception:
            pass
        # Prima voce: default di sistema
        try:
            self.cmb_audio_device.addItem(self.i18n.t('settings_audio_default'), userData=None)
        except Exception:
            pass
        audio_row.addWidget(self.cmb_audio_device, 1)
        self.btn_audio_refresh = QPushButton(self.i18n.t('settings_audio_refresh'))
        try:
            self.btn_audio_refresh.clicked.connect(self._populate_audio_devices)
        except Exception:
            pass
        audio_row.addWidget(self.btn_audio_refresh)
        layout.addLayout(audio_row)

        # LibVLC Path
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        lab_path = QLabel(self.i18n.t('libvlc_path'))
        lab_path.setMinimumWidth(140)
        path_row.addWidget(lab_path)
        self.txt_vlc_path = QLineEdit(self.settings.value(KEY_LIBVLC_PATH, ''))
        path_row.addWidget(self.txt_vlc_path, 1)
        self.btn_browse = QPushButton(self.i18n.t('browse'))
        self.btn_browse.clicked.connect(self._browse_vlc_path)
        path_row.addWidget(self.btn_browse)
        layout.addLayout(path_row)

        # Network caching
        nc_row = QHBoxLayout()
        nc_row.setSpacing(8)
        lab_nc = QLabel(self.i18n.t('settings_network_caching'))
        lab_nc.setMinimumWidth(140)
        nc_row.addWidget(lab_nc)
        self.spin_network_caching = QSpinBox()
        self.spin_network_caching.setRange(100, 5000)
        try:
            self.spin_network_caching.setSingleStep(100)
        except Exception:
            pass
        try:
            self.spin_network_caching.setSuffix(' ms')
        except Exception:
            pass
        try:
            self.spin_network_caching.setMinimumWidth(120)
        except Exception:
            pass
        try:
            self.spin_network_caching.setValue(int(self.settings.value(KEY_NETWORK_CACHING, 1000)))
        except Exception:
            self.spin_network_caching.setValue(1000)
        nc_row.addWidget(self.spin_network_caching)
        layout.addLayout(nc_row)

        # Tray options
        self.chk_tray_enabled = QCheckBox(self.i18n.t('settings_tray_enable'))
        self.chk_tray_enabled.setChecked(self.settings.value(KEY_TRAY_ENABLED, 'true') == 'true')
        layout.addWidget(self.chk_tray_enabled)

        self.chk_tray_hide_on_minimize = QCheckBox(self.i18n.t('settings_tray_hide_on_minimize'))
        self.chk_tray_hide_on_minimize.setChecked(self.settings.value(KEY_TRAY_HIDE_ON_MINIMIZE, 'true') == 'true')
        self.chk_tray_hide_on_minimize.setEnabled(self.chk_tray_enabled.isChecked())
        self.chk_tray_enabled.stateChanged.connect(lambda s: self.chk_tray_hide_on_minimize.setEnabled(self.chk_tray_enabled.isChecked()))
        layout.addWidget(self.chk_tray_hide_on_minimize)

        self.chk_tray_notifications = QCheckBox(self.i18n.t('settings_tray_notifications'))
        self.chk_tray_notifications.setChecked(self.settings.value(KEY_TRAY_NOTIFICATIONS, 'true') == 'true')
        layout.addWidget(self.chk_tray_notifications)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_ok = QPushButton(self.i18n.t('settings_ok'))
        self.btn_cancel = QPushButton(self.i18n.t('settings_cancel'))
        self.btn_apply = QPushButton(self.i18n.t('settings_apply'))
        try:
            self.btn_ok.setIcon(self.style().standardIcon(self.style().SP_DialogOkButton))
            self.btn_cancel.setIcon(self.style().standardIcon(self.style().SP_DialogCancelButton))
            self.btn_apply.setIcon(self.style().standardIcon(self.style().SP_DialogApplyButton))
        except Exception:
            pass
        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply.clicked.connect(self._on_apply)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_apply)
        btn_row.addWidget(self.btn_ok)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _browse_vlc_path(self):
        start_dir = self.txt_vlc_path.text().strip() or self.settings.value(KEY_LIBVLC_PATH, None) or 'C:/'
        chosen = QFileDialog.getExistingDirectory(self, self.i18n.t('libvlc_choose_title'), start_dir)
        if chosen:
            self.txt_vlc_path.setText(chosen)

    def _on_apply(self):
        """Salva i valori senza chiudere la finestra."""
        self._save_settings()
        try:
            self.settings_changed.emit()
        except Exception:
            pass

    def _on_ok(self):
        """Salva i valori e chiude la finestra."""
        self._save_settings()
        self.accept()

    def _on_open_console(self):
        # Apri la console senza chiudere questo dialogo, che rimane aperto/non modale
        try:
            # Salva subito le impostazioni (incluso KEY_DEV_CONSOLE_SHOW_DEV)
            self._save_settings()
            parent = self.parent()
            if parent and hasattr(parent, 'open_dev_console'):
                # Apri la console con parent = finestra principale
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(0, lambda: parent.open_dev_console(parent))
        except Exception:
            pass

    def _save_settings(self):
        """Logica comune per salvare le impostazioni."""
        self.settings.setValue(KEY_AUTOPLAY, 'true' if self.chk_autoplay.isChecked() else 'false')
        self.settings.setValue(KEY_DARK_MODE, 'true' if self.chk_dark_mode.isChecked() else 'false')
        self.settings.setValue(KEY_SLEEP_STOP_ON_END, 'true' if self.chk_sleep_stop.isChecked() else 'false')
        self.settings.setValue(KEY_SESSION_TIMER_ENABLED, 'true' if self.chk_session_timer.isChecked() else 'false')
        self.settings.setValue(KEY_DEV_CONSOLE_ENABLED, 'true' if self.chk_dev_console.isChecked() else 'false')
        self.settings.setValue(KEY_DEV_CONSOLE_SHOW_DEV, 'true' if self.chk_dev_show_dev.isChecked() else 'false')
        self.settings.setValue(KEY_LANG, 'it' if self.cmb_lang.currentIndex() == 0 else 'en')
        self.settings.setValue(KEY_CHANNEL, self.cmb_channel.currentText())
        self.settings.setValue(KEY_FORMAT, self.cmb_format.currentText())
        path = self.txt_vlc_path.text().strip()
        self.settings.setValue(KEY_LIBVLC_PATH, path if path else '')
        self.settings.setValue(KEY_NETWORK_CACHING, int(self.spin_network_caching.value()))
        self.settings.setValue(KEY_TRAY_ENABLED, 'true' if self.chk_tray_enabled.isChecked() else 'false')
        self.settings.setValue(KEY_TRAY_HIDE_ON_MINIMIZE, 'true' if self.chk_tray_hide_on_minimize.isChecked() else 'false')
        self.settings.setValue(KEY_TRAY_NOTIFICATIONS, 'true' if self.chk_tray_notifications.isChecked() else 'false')
        # Save audio device selection: None => use system default
        try:
            idx_data = self.cmb_audio_device.currentData()
            if idx_data is None:
                self.settings.setValue(KEY_AUDIO_DEVICE_INDEX, '')
            else:
                self.settings.setValue(KEY_AUDIO_DEVICE_INDEX, int(idx_data))
        except Exception:
            pass

    def showEvent(self, event):
        try:
            super().showEvent(event)
        except Exception:
            pass
        # Riapplica la titlebar scura quando la finestra viene mostrata
        try:
            dark = self.settings.value(KEY_DARK_MODE, 'false') == 'true'
            self._apply_windows_titlebar_dark_mode(dark)
        except Exception:
            pass
        # Populate audio devices on show
        try:
            self._populate_audio_devices()
        except Exception:
            pass

    def _apply_windows_titlebar_dark_mode(self, enable: bool) -> None:
        try:
            import sys
            if sys.platform != 'win32':
                return
            hwnd = int(self.winId()) if hasattr(self, 'winId') else None
            if not hwnd:
                return
            import ctypes
            value = ctypes.c_int(1 if enable else 0)
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            except Exception:
                pass
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
            except Exception:
                pass
        except Exception:
            pass

    def _populate_audio_devices(self):
        """Enumerate PortAudio devices via PyAudio and fill combo box.
        Keeps first entry as 'System default'; lists output-capable devices with index.
        """
        try:
            import pyaudio
        except Exception:
            pyaudio = None
        # Keep 'System default' as index 0
        try:
            # Clear all except first
            for i in range(self.cmb_audio_device.count() - 1, 0, -1):
                self.cmb_audio_device.removeItem(i)
        except Exception:
            pass
        if pyaudio is None:
            return
        pa = None
        try:
            pa = pyaudio.PyAudio()
            host_info = pa.get_host_api_info_by_index(0) if hasattr(pa, 'get_host_api_info_by_index') else None
            device_count = host_info.get('deviceCount', 0) if isinstance(host_info, dict) else (
                pa.get_device_count() if hasattr(pa, 'get_device_count') else 0
            )
            for i in range(device_count):
                try:
                    info = pa.get_device_info_by_index(i)
                except Exception:
                    info = None
                if not isinstance(info, dict):
                    continue
                max_output = int(info.get('maxOutputChannels', 0))
                name = str(info.get('name', f'Device {i}'))
                # Include only devices that can output
                if max_output > 0:
                    # Show name and index in label
                    label = f"{name} (#{i})"
                    self.cmb_audio_device.addItem(label, userData=i)
            # Restore persisted selection if available
            persisted = self.settings.value(KEY_AUDIO_DEVICE_INDEX, '')
            if persisted != '' and persisted is not None:
                try:
                    persisted = int(persisted)
                    # Find index in combo where userData == persisted
                    for combo_idx in range(self.cmb_audio_device.count()):
                        if self.cmb_audio_device.itemData(combo_idx) == persisted:
                            self.cmb_audio_device.setCurrentIndex(combo_idx)
                            break
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            try:
                if pa is not None and hasattr(pa, 'terminate'):
                    pa.terminate()
            except Exception:
                pass