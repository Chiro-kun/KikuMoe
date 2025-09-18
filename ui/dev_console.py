from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QCheckBox, QComboBox, QFileDialog
from PyQt5.QtGui import QTextCursor, QTextOption
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, Qt
import builtins
import logging


class _QtStream(QObject):
    text_emitted = pyqtSignal(str)

    def __init__(self, append_fn):
        super().__init__()
        try:
            self.text_emitted.connect(append_fn, Qt.QueuedConnection)
        except Exception:
            pass

    def write(self, s):
        try:
            if s:
                self.text_emitted.emit(str(s))
        except Exception:
            pass

    def flush(self):
        pass

    def isatty(self):
        return False


class _DevConsoleHandler(logging.Handler):
    def __init__(self, write_fn):
        super().__init__()
        self._write = write_fn

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self._write(msg + "\n")
        except Exception:
            pass


class DevConsole(QObject):
    def __init__(self, parent=None, translator=None, logger=None):
        super().__init__(parent)
        self._parent = parent
        self._translator = translator
        self._logger = logger
        self._console_dialog = None
        self._console_text = None
        # monkeypatch print
        self._old_print = None
        # Qt stream per append thread-safe
        self._qt_stream = None
        # pulsanti
        self._btn_clear = None
        self._btn_copy = None
        # nuovi controlli UI
        self._btn_pause = None
        self._btn_save = None
        self._cb_autoscroll = None
        self._cb_wrap = None
        self._level_combo = None
        # stati
        self._autoscroll_enabled = True
        self._paused = False
        self._pause_buffer = []
        # logging handler dedicato
        self._log_handler = None
        # elenco dei logger a cui ho agganciato l'handler (oltre al root)
        self._attached_loggers = []

    def _t(self, key: str, default: str = None):
        try:
            if self._translator is not None and hasattr(self._translator, 't'):
                return self._translator.t(key)
        except Exception:
            pass
        return default or key

    def is_open(self) -> bool:
        return bool(self._console_dialog)

    def raise_window(self):
        try:
            if self._console_dialog:
                self._console_dialog.raise_()
                self._console_dialog.activateWindow()
        except Exception:
            pass

    def set_translator(self, translator):
        try:
            self._translator = translator
            self.refresh_texts()
        except Exception:
            pass

    def refresh_texts(self):
        try:
            if self._console_dialog:
                self._console_dialog.setWindowTitle(self._t('dev_console_title', 'Developer Console'))
                if self._btn_clear:
                    self._btn_clear.setText(self._t('dev_console_clear', 'Clear'))
                if self._btn_copy:
                    self._btn_copy.setText(self._t('dev_console_copy', 'Copy All'))
                if self._btn_pause:
                    self._btn_pause.setText(self._t('dev_console_pause', 'Pause') if not self._paused else self._t('dev_console_resume', 'Resume'))
                if self._btn_save:
                    self._btn_save.setText(self._t('dev_console_save', 'Save...'))
                if self._cb_autoscroll:
                    self._cb_autoscroll.setText(self._t('dev_console_autoscroll', 'Autoscroll'))
                if self._cb_wrap:
                    self._cb_wrap.setText(self._t('dev_console_wrap', 'Wrap'))
                if self._level_combo:
                    # Placeholder text via accessible name (QComboBox non ha label interno)
                    self._level_combo.setToolTip(self._t('dev_console_level', 'Level filter'))
        except Exception:
            pass

    def open(self):
        # If already open, just focus it
        if self._console_dialog:
            self.raise_window()
            return

        # Build console dialog UI
        self._console_dialog = QDialog(self._parent)
        self._console_dialog.setWindowTitle(self._t('dev_console_title', 'Developer Console'))
        self._console_dialog.setModal(False)

        v = QVBoxLayout()
        self._console_text = QTextEdit()
        self._console_text.setReadOnly(True)
        self._console_text.setLineWrapMode(QTextEdit.WidgetWidth)
        try:
            self._console_text.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        except Exception:
            pass
        try:
            self._console_text.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
        except Exception:
            pass
        v.addWidget(self._console_text)

        # Row controlli principali
        hc = QHBoxLayout()
        # livello
        self._level_combo = QComboBox()
        self._level_combo.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR'])
        self._level_combo.setCurrentText('DEBUG')
        self._level_combo.currentTextChanged.connect(self._on_level_changed)
        self._level_combo.setToolTip(self._t('dev_console_level', 'Level filter'))
        # pausa
        self._btn_pause = QPushButton(self._t('dev_console_pause', 'Pause'))
        self._btn_pause.clicked.connect(self._on_toggle_pause)
        # autoscroll
        self._cb_autoscroll = QCheckBox(self._t('dev_console_autoscroll', 'Autoscroll'))
        self._cb_autoscroll.setChecked(True)
        self._cb_autoscroll.toggled.connect(self._on_toggle_autoscroll)
        # wrap
        self._cb_wrap = QCheckBox(self._t('dev_console_wrap', 'Wrap'))
        self._cb_wrap.setChecked(True)
        self._cb_wrap.toggled.connect(self._on_toggle_wrap)
        # salva
        self._btn_save = QPushButton(self._t('dev_console_save', 'Save...'))
        self._btn_save.clicked.connect(self._on_save_clicked)

        hc.addWidget(self._level_combo)
        hc.addStretch(1)
        hc.addWidget(self._btn_pause)
        hc.addWidget(self._cb_autoscroll)
        hc.addWidget(self._cb_wrap)
        hc.addWidget(self._btn_save)
        v.addLayout(hc)

        h = QHBoxLayout()
        self._btn_clear = QPushButton(self._t('dev_console_clear', 'Clear'))
        self._btn_copy = QPushButton(self._t('dev_console_copy', 'Copy All'))
        self._btn_clear.clicked.connect(lambda: self._console_text.clear())
        self._btn_copy.clicked.connect(lambda: (self._console_text.selectAll(), self._console_text.copy()))
        h.addStretch(1)
        h.addWidget(self._btn_clear)
        h.addWidget(self._btn_copy)
        v.addLayout(h)

        self._console_dialog.setLayout(v)

        # Initial message to confirm rendering
        try:
            self._console_text.append(">>> Console pronta. I log appariranno qui.")
        except Exception:
            pass

        # Prepara stream Qt per uso con print e logging handler
        try:
            self._qt_stream = _QtStream(self._append_console)
        except Exception:
            self._qt_stream = None

        # Monkeypatch print per catturare anche librerie che usano print
        try:
            self._old_print = getattr(builtins, 'print', None)

            def _console_print(*args, **kwargs):
                try:
                    sep = kwargs.get('sep', ' ')
                    end = kwargs.get('end', '\n')
                    text = sep.join(str(a) for a in args) + end
                    try:
                        if self._qt_stream:
                            self._qt_stream.write(text)
                    except Exception:
                        pass
                    try:
                        if self._old_print is not None:
                            file_kw = kwargs.copy()
                            self._old_print(*args, **file_kw)
                    except Exception:
                        pass
                except Exception:
                    pass

            try:
                builtins.print = _console_print
            except Exception:
                pass
        except Exception:
            pass

        # Aggiungi un logging.Handler dedicato alla DevConsole
        try:
            if self._qt_stream and self._log_handler is None:
                self._log_handler = _DevConsoleHandler(self._qt_stream.write)
                self._log_handler.setLevel(logging.DEBUG)
                fmt = logging.Formatter('[%(levelname)s] [%(name)s] %(message)s')
                self._log_handler.setFormatter(fmt)
                # Aggancio al root
                root_logger = logging.getLogger()
                if self._log_handler not in getattr(root_logger, 'handlers', []):
                    root_logger.addHandler(self._log_handler)
                # Aggancio a tutti i logger esistenti (propagate=False)
                try:
                    for lname in list(logging.Logger.manager.loggerDict.keys()):
                        try:
                            lg = logging.getLogger(lname)
                            if self._log_handler not in getattr(lg, 'handlers', []):
                                lg.addHandler(self._log_handler)
                                self._attached_loggers.append(lg)
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if self._logger:
                self._logger.info('[DEV] Console sviluppatore attivata.')
        except Exception:
            pass
        QTimer.singleShot(150, lambda: self._logger and self._logger.debug('[DEV] Test timer: console attiva?'))
        QTimer.singleShot(300, lambda: self._append_console('[DEV] Test timer (append diretto)\n'))
        try:
            self._console_dialog.show()
            self.raise_window()
        except Exception:
            pass

    def close(self):
        # Ripristina print monkeypatch
        try:
            if self._old_print is not None:
                builtins.print = self._old_print
        except Exception:
            pass
        self._old_print = None

        # Rimuovi logging handler dedicato
        try:
            if self._log_handler is not None:
                try:
                    logging.getLogger().removeHandler(self._log_handler)
                except Exception:
                    pass
                try:
                    for lg in list(self._attached_loggers):
                        try:
                            lg.removeHandler(self._log_handler)
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass
        self._attached_loggers = []
        self._log_handler = None
        self._qt_stream = None
        # Cleanup dialog references
        try:
            if self._console_dialog:
                try:
                    self._console_dialog.close()
                except Exception:
                    pass
                self._console_dialog.deleteLater()
                self._console_dialog = None
        except Exception:
            pass

    @pyqtSlot(str)
    def _append_console(self, s: str):
        try:
            if not self._console_text:
                return
            if s is None:
                return
            text = str(s)
            if not text:
                return
            if self._paused:
                self._pause_buffer.append(text)
                return
            # Gestione autoscroll: se disabilitato, preservo posizione scrollbar
            sb = self._console_text.verticalScrollBar() if hasattr(self._console_text, 'verticalScrollBar') else None
            prev_val = sb.value() if sb is not None else None
            self._console_text.moveCursor(QTextCursor.End)
            self._console_text.insertPlainText(text)
            if self._autoscroll_enabled:
                self._console_text.moveCursor(QTextCursor.End)
            else:
                if sb is not None and prev_val is not None:
                    sb.setValue(prev_val)
        except Exception:
            pass

    def _on_toggle_pause(self):
        try:
            self._paused = not self._paused
            if self._btn_pause:
                self._btn_pause.setText(self._t('dev_console_pause', 'Pause') if not self._paused else self._t('dev_console_resume', 'Resume'))
            if not self._paused and self._pause_buffer:
                # flush buffer
                flushed = ''.join(self._pause_buffer)
                self._pause_buffer = []
                self._append_console(flushed)
        except Exception:
            pass

    def _on_toggle_autoscroll(self, checked: bool):
        try:
            self._autoscroll_enabled = bool(checked)
        except Exception:
            pass

    def _on_toggle_wrap(self, checked: bool):
        try:
            if not self._console_text:
                return
            if checked:
                self._console_text.setLineWrapMode(QTextEdit.WidgetWidth)
                try:
                    self._console_text.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
                except Exception:
                    pass
            else:
                self._console_text.setLineWrapMode(QTextEdit.NoWrap)
        except Exception:
            pass

    def _on_level_changed(self, level_text: str):
        try:
            level_map = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR,
            }
            lvl = level_map.get(level_text, logging.DEBUG)
            if self._log_handler is not None:
                self._log_handler.setLevel(lvl)
        except Exception:
            pass

    def _on_save_clicked(self):
        try:
            if not self._console_text:
                return
            filename, _ = QFileDialog.getSaveFileName(self._console_dialog, self._t('dev_console_save', 'Save...'), 'console.log', 'Text Files (*.txt);;All Files (*)')
            if filename:
                try:
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(self._console_text.toPlainText())
                except Exception:
                    pass
        except Exception:
            pass