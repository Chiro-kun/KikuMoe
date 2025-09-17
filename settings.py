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
    KEY_LIBVLC_PATH,
    KEY_NETWORK_CACHING,
    KEY_DARK_MODE,
    KEY_SLEEP_STOP_ON_END,
)

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.settings = QSettings(ORG_NAME, APP_SETTINGS)
        self.i18n = I18n(self.settings.value(KEY_LANG, 'it'))
        self.setWindowTitle(self.i18n.t('settings_title'))

        layout = QVBoxLayout()

        # Autoplay
        self.chk_autoplay = QCheckBox(self.i18n.t('settings_autoplay'))
        self.chk_autoplay.setChecked(self.settings.value(KEY_AUTOPLAY, 'false') == 'true')
        layout.addWidget(self.chk_autoplay)

        # Dark Mode
        self.chk_dark_mode = QCheckBox(self.i18n.t('settings_dark_mode'))
        self.chk_dark_mode.setChecked(self.settings.value(KEY_DARK_MODE, 'false') == 'true')
        layout.addWidget(self.chk_dark_mode)

        # Sleep Timer option: stop on end
        self.chk_sleep_stop = QCheckBox(self.i18n.t('settings_sleep_stop_on_end'))
        self.chk_sleep_stop.setChecked(self.settings.value(KEY_SLEEP_STOP_ON_END, 'true') == 'true')
        layout.addWidget(self.chk_sleep_stop)

        # Language
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(self.i18n.t('settings_language')))
        self.cmb_lang = QComboBox()
        self.cmb_lang.addItems(['Italiano', 'English'])
        self.cmb_lang.setCurrentIndex(0 if self.settings.value(KEY_LANG, 'it') == 'it' else 1)
        lang_row.addWidget(self.cmb_lang)
        layout.addLayout(lang_row)

        # Channel & Format
        ch_row = QHBoxLayout()
        ch_row.addWidget(QLabel(self.i18n.t('settings_channel')))
        self.cmb_channel = QComboBox()
        self.cmb_channel.addItems(['J-POP', 'K-POP'])
        self.cmb_channel.setCurrentText(self.settings.value(KEY_CHANNEL, 'J-POP'))
        ch_row.addWidget(self.cmb_channel)
        layout.addLayout(ch_row)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel(self.i18n.t('settings_format')))
        self.cmb_format = QComboBox()
        self.cmb_format.addItems(['Vorbis', 'MP3'])
        self.cmb_format.setCurrentText(self.settings.value(KEY_FORMAT, 'Vorbis'))
        fmt_row.addWidget(self.cmb_format)
        layout.addLayout(fmt_row)

        # VLC Path
        vlc_row = QHBoxLayout()
        vlc_row.addWidget(QLabel(self.i18n.t('settings_vlc_path')))
        self.txt_vlc_path = QLineEdit(self.settings.value(KEY_LIBVLC_PATH, '') or '')
        vlc_row.addWidget(self.txt_vlc_path)
        self.btn_browse_vlc = QPushButton(self.i18n.t('settings_browse'))
        self.btn_browse_vlc.clicked.connect(self._browse_vlc_path)
        vlc_row.addWidget(self.btn_browse_vlc)
        layout.addLayout(vlc_row)

        # Network caching (ms)
        nc_row = QHBoxLayout()
        nc_row.addWidget(QLabel(self.i18n.t('settings_network_caching')))
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

        self.chk_tray_notifications = QCheckBox(self.i18n.t('settings_tray_notifications'))
        self.chk_tray_notifications.setChecked(self.settings.value(KEY_TRAY_NOTIFICATIONS, 'true') == 'true')
        layout.addWidget(self.chk_tray_notifications)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_ok = QPushButton(self.i18n.t('settings_ok'))
        self.btn_cancel = QPushButton(self.i18n.t('settings_cancel'))
        self.btn_apply = QPushButton(self.i18n.t('settings_apply'))
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

    def _save_settings(self):
        """Logica comune per salvare le impostazioni."""
        self.settings.setValue(KEY_AUTOPLAY, 'true' if self.chk_autoplay.isChecked() else 'false')
        self.settings.setValue(KEY_DARK_MODE, 'true' if self.chk_dark_mode.isChecked() else 'false')
        self.settings.setValue(KEY_SLEEP_STOP_ON_END, 'true' if self.chk_sleep_stop.isChecked() else 'false')
        self.settings.setValue(KEY_LANG, 'it' if self.cmb_lang.currentIndex() == 0 else 'en')
        self.settings.setValue(KEY_CHANNEL, self.cmb_channel.currentText())
        self.settings.setValue(KEY_FORMAT, self.cmb_format.currentText())
        path = self.txt_vlc_path.text().strip()
        self.settings.setValue(KEY_LIBVLC_PATH, path if path else '')
        self.settings.setValue(KEY_NETWORK_CACHING, int(self.spin_network_caching.value()))
        self.settings.setValue(KEY_TRAY_ENABLED, 'true' if self.chk_tray_enabled.isChecked() else 'false')
        self.settings.setValue(KEY_TRAY_NOTIFICATIONS, 'true' if self.chk_tray_notifications.isChecked() else 'false')