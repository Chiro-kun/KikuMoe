from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit
from PyQt5.QtGui import QTextCursor, QTextOption
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, Qt
import sys
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


class DevConsole(QObject):
    def __init__(self, parent=None, translator=None, logger=None):
        super().__init__(parent)
        self._parent = parent
        self._translator = translator
        self._logger = logger
        self._console_dialog = None
        self._console_text = None
        self._old_stdout = None
        self._old_stderr = None
        self._old_print = None
        self._qt_stream_stdout = None
        self._qt_stream_stderr = None
        # Store buttons for runtime i18n updates
        self._btn_clear = None
        self._btn_copy = None
        # Track original streams of logging handlers to restore on close
        self._orig_handler_streams = {}

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
            self._console_text.append(">>> Console pronta. I log appariranno qui se la redirezione è attiva.")
        except Exception:
            pass

        # Debug on real stdout before redirect
        try:
            real_out = getattr(sys, '__stdout__', None) or getattr(self, '_old_stdout', None) or sys.stdout
            if real_out:
                real_out.write('[DEV] open_dev_console: pre-redirect reached\n')
                try:
                    real_out.flush()
                except Exception:
                    pass
        except Exception:
            pass

        # Redirect stdout/stderr to the QTextEdit using a Qt-friendly stream
        try:
            self._old_stdout = sys.stdout
            self._old_stderr = sys.stderr
            self._qt_stream_stdout = _QtStream(self._append_console)
            self._qt_stream_stderr = _QtStream(self._append_console)
            sys.stdout = self._qt_stream_stdout
            sys.stderr = self._qt_stream_stderr
            # Monkeypatch print to ensure capture even if libraries bypass sys.stdout
            self._old_print = getattr(builtins, 'print', None)

            def _console_print(*args, **kwargs):
                try:
                    sep = kwargs.get('sep', ' ')
                    end = kwargs.get('end', '\n')
                    text = sep.join(str(a) for a in args) + end
                    try:
                        if self._qt_stream_stdout:
                            self._qt_stream_stdout.write(text)
                    except Exception:
                        pass
                    try:
                        if self._old_print is not None:
                            file_kw = kwargs.copy()
                            # mirror to the original stdout, not the redirected one
                            file_kw['file'] = self._old_stdout
                            self._old_print(*args, **file_kw)
                    except Exception:
                        pass
                except Exception:
                    pass

            try:
                builtins.print = _console_print
            except Exception:
                pass

            # Redirect existing logging handlers to the console stream
            try:
                # Scan root and all known loggers
                all_loggers = [logging.getLogger()]  # root
                try:
                    for lname in list(logging.Logger.manager.loggerDict.keys()):
                        try:
                            lg = logging.getLogger(lname)
                            all_loggers.append(lg)
                        except Exception:
                            pass
                except Exception:
                    pass
                for lg in all_loggers:
                    for h in getattr(lg, 'handlers', []) or []:
                        if isinstance(h, logging.StreamHandler):
                            try:
                                # Save original stream to restore later
                                if h not in self._orig_handler_streams:
                                    try:
                                        self._orig_handler_streams[h] = getattr(h, 'stream', None)
                                    except Exception:
                                        self._orig_handler_streams[h] = None
                                # Point to our Qt stream
                                try:
                                    h.setStream(self._qt_stream_stdout)
                                except Exception:
                                    try:
                                        h.stream = self._qt_stream_stdout
                                    except Exception:
                                        pass
                            except Exception:
                                pass
            except Exception:
                pass

            try:
                if self._logger:
                    self._logger.info('[DEV] Console sviluppatore attivata. Output reindirizzato.')
            except Exception:
                pass
            QTimer.singleShot(150, lambda: self._logger and self._logger.debug('[DEV] Test timer: console attiva e redirect funzionante?'))
            QTimer.singleShot(300, lambda: self._append_console('[DEV] Test timer (append diretto)\n'))
        except Exception:
            pass

        try:
            self._console_dialog.show()
            self.raise_window()
        except Exception:
            pass

    def close(self):
        # Restore print monkeypatch
        try:
            if self._old_print is not None:
                builtins.print = self._old_print
        except Exception:
            pass
        # Restore logging handlers' original streams
        try:
            if self._orig_handler_streams:
                for h, orig in list(self._orig_handler_streams.items()):
                    try:
                        if isinstance(h, logging.StreamHandler):
                            try:
                                h.setStream(orig)
                            except Exception:
                                try:
                                    h.stream = orig
                                except Exception:
                                    pass
                    except Exception:
                        pass
                self._orig_handler_streams.clear()
        except Exception:
            pass
        # Restore sys.stdout/sys.stderr if previously redirected
        try:
            if self._old_stdout:
                sys.stdout = self._old_stdout
        except Exception:
            pass
        try:
            if self._old_stderr:
                sys.stderr = self._old_stderr
        except Exception:
            pass
        self._old_stdout = None
        self._old_stderr = None
        self._qt_stream_stdout = None
        self._qt_stream_stderr = None
        self._old_print = None

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