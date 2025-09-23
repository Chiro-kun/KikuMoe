from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QPushButton, QLineEdit, QFileDialog, QSpinBox
)
from PyQt5.QtCore import Qt, QSettings
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
)

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
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
        self.btn_open_console.setEnabled(self.chk_dev_console.isChecked())
        self.btn_open_console.clicked.connect(self._on_open_console)
        dev_row.addStretch(1)
        dev_row.addWidget(self.btn_open_console)
        layout.addLayout(dev_row)
        # Enable/disable button based on checkbox state
        self.chk_dev_console.stateChanged.connect(lambda s: self.btn_open_console.setEnabled(self.chk_dev_console.isChecked()))

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

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(8)
        lab_fmt = QLabel(self.i18n.t('settings_format'))
        lab_fmt.setMinimumWidth(140)
        fmt_row.addWidget(lab_fmt)
        self.cmb_format = QComboBox()
        self.cmb_format.addItems(['Vorbis', 'MP3'])
        self.cmb_format.setCurrentText(self.settings.value(KEY_FORMAT, 'Vorbis'))
        fmt_row.addWidget(self.cmb_format, 1)
        layout.addLayout(fmt_row)

        # VLC Path
        vlc_row = QHBoxLayout()
        vlc_row.setSpacing(8)
        lab_vlc = QLabel(self.i18n.t('settings_vlc_path'))
        lab_vlc.setMinimumWidth(140)
        vlc_row.addWidget(lab_vlc)
        self.txt_vlc_path = QLineEdit(self.settings.value(KEY_LIBVLC_PATH, '') or '')
        self.txt_vlc_path.setPlaceholderText('C:/Program Files/VideoLAN/VLC' if Qt.Key_Enter else '')
        try:
            self.txt_vlc_path.setMinimumWidth(260)
        except Exception:
            pass
        vlc_row.addWidget(self.txt_vlc_path, 1)
        self.btn_browse_vlc = QPushButton(self.i18n.t('settings_browse'))
        try:
            self.btn_browse_vlc.setIcon(self.style().standardIcon(self.style().SP_DialogOpenButton))
        except Exception:
            pass
        self.btn_browse_vlc.clicked.connect(self._browse_vlc_path)
        vlc_row.addWidget(self.btn_browse_vlc)
        layout.addLayout(vlc_row)

        # Network caching (ms)
        nc_row = QHBoxLayout()
        nc_row.setSpacing(8)
        lab_nc = QLabel(self.i18n.t('settings_network_caching'))
        lab_nc.setMinimumWidth(140)
        nc_row.addWidget(lab_nc)
        self.spin_network_caching = QSpinBox()
        self.spin_network_caching.setRange(0, 20000)
        self.spin_network_caching.setSingleStep(250)
        try:
            default_nc = int(self.settings.value(KEY_NETWORK_CACHING, 1000))
        except Exception:
            default_nc = 1000
        self.spin_network_caching.setValue(default_nc)
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

    def _on_ok(self):
        """Salva i valori e chiude la finestra."""
        self._save_settings()
        self.accept()

    def _on_open_console(self):
        # Only open if enabled
        if not self.chk_dev_console.isChecked():
            return
        try:
            # Salva subito lo stato della checkbox per permettere al gating del parent di leggere 'true'
            self._save_settings()
            parent = self.parent()
            if parent and hasattr(parent, 'open_dev_console'):
                parent.open_dev_console(self)
        except Exception:
            pass

    def _save_settings(self):
        """Logica comune per salvare le impostazioni."""
        self.settings.setValue(KEY_AUTOPLAY, 'true' if self.chk_autoplay.isChecked() else 'false')
        self.settings.setValue(KEY_DARK_MODE, 'true' if self.chk_dark_mode.isChecked() else 'false')
        self.settings.setValue(KEY_SLEEP_STOP_ON_END, 'true' if self.chk_sleep_stop.isChecked() else 'false')
        self.settings.setValue(KEY_SESSION_TIMER_ENABLED, 'true' if self.chk_session_timer.isChecked() else 'false')
        self.settings.setValue(KEY_DEV_CONSOLE_ENABLED, 'true' if self.chk_dev_console.isChecked() else 'false')
        self.settings.setValue(KEY_LANG, 'it' if self.cmb_lang.currentIndex() == 0 else 'en')
        self.settings.setValue(KEY_CHANNEL, self.cmb_channel.currentText())
        self.settings.setValue(KEY_FORMAT, self.cmb_format.currentText())
        path = self.txt_vlc_path.text().strip()
        self.settings.setValue(KEY_LIBVLC_PATH, path if path else '')
        self.settings.setValue(KEY_NETWORK_CACHING, int(self.spin_network_caching.value()))
        self.settings.setValue(KEY_TRAY_ENABLED, 'true' if self.chk_tray_enabled.isChecked() else 'false')
        self.settings.setValue(KEY_TRAY_HIDE_ON_MINIMIZE, 'true' if self.chk_tray_hide_on_minimize.isChecked() else 'false')
        self.settings.setValue(KEY_TRAY_NOTIFICATIONS, 'true' if self.chk_tray_notifications.isChecked() else 'false')

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