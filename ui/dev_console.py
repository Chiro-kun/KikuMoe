from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit
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
            self._console_text.moveCursor(QTextCursor.End)
            self._console_text.insertPlainText(text)
            self._console_text.moveCursor(QTextCursor.End)
        except Exception:
            pass