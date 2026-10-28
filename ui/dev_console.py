"""
Cyber-Moe Developer Console for KikuMoe 2.0.0
Features:
- Frameless window with CustomTitleBar, Windows 11 native DWM rounded corners, and resize grip
- Top toolbar card with live status badge, GlassComboBox level filter, and 60 FPS pill toggles
- Deep obsidian terminal view (#0a0c14) with monospace typography and sleek scrollbars
- Bottom action deck with custom vector icons and 60 FPS click-bounce buttons
"""

import builtins
import logging
from typing import List, Optional

from PyQt6.QtCore import QObject, QRectF, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QTextCursor,
    QTextOption,
)
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.custom_titlebar import CustomTitleBar, install_size_grip
from ui.settings_dialog import GlassComboBox
from ui.themes.cyber_moe import PALETTE, accent_qcolor, get_cyber_moe_stylesheet
from ui.windows_titlebar import apply_windows_titlebar_dark_mode


class _QtStream(QObject):
    text_emitted = pyqtSignal(str)

    def __init__(self, append_fn):
        super().__init__()
        try:
            self.text_emitted.connect(append_fn, type=Qt.ConnectionType.QueuedConnection)  # type: ignore[call-arg]
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


class _ConsolePillToggle(QCheckBox):
    """Compact 60 FPS sliding pill toggle for Developer Console toolbar options."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self._hover = False
        self._progress = 1.0 if self.isChecked() else 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(28)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)
        self.toggled.connect(self._on_toggled)

    def setChecked(self, a0: bool) -> None:
        super().setChecked(a0)
        self._progress = 1.0 if a0 else 0.0
        self.update()

    def _on_toggled(self, _checked: bool) -> None:
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def _tick_anim(self) -> None:
        target = 1.0 if self.isChecked() else 0.0
        diff = target - self._progress
        if abs(diff) < 0.06:
            self._progress = target
            self._anim_timer.stop()
        else:
            self._progress += diff * 0.34
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, a0) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(a0)

    def sizeHint(self):
        fm = self.fontMetrics()
        tw = fm.horizontalAdvance(self.text())
        sh = super().sizeHint()
        sh.setWidth(max(92, tw + 56))
        sh.setHeight(28)
        return sh

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        p = self._progress

        # Outer subtle capsule
        bg_alpha = 20 if self._hover else 10
        painter.setBrush(QColor(255, 255, 255, bg_alpha))
        painter.setPen(
            QPen(
                accent_qcolor(int(90 * p)) if p > 0.1 else QColor(255, 255, 255, 28),
                1.0,
            )
        )
        painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), 8.0, 8.0)

        # Toggle switch on the left
        sw_w = 32.0
        sw_h = 17.0
        sw_x = 7.0
        sw_y = (h - sw_h) / 2.0
        sw_rect = QRectF(sw_x, sw_y, sw_w, sw_h)

        act_col = QColor(PALETTE["accent"])
        r = int(34 + (act_col.red() - 34) * p)
        g = int(38 + (act_col.green() - 38) * p)
        b = int(56 + (act_col.blue() - 56) * p)
        painter.setBrush(QColor(r, g, b))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(sw_rect, sw_h / 2.0, sw_h / 2.0)

        knob_d = 13.0
        knob_x = sw_x + 2.0 + p * (sw_w - knob_d - 4.0)
        knob_y = sw_y + (sw_h - knob_d) / 2.0
        kr = int(155 + (255 - 155) * p)
        kg = int(162 + (255 - 162) * p)
        kb = int(184 + (255 - 184) * p)
        painter.setBrush(QColor(kr, kg, kb))
        painter.drawEllipse(QRectF(knob_x, knob_y, knob_d, knob_d))

        # Text on the right
        font = QFont("Segoe UI")
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.DemiBold if self.isChecked() else QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(QColor("#f4f6fd" if self.isChecked() else "#a8b0c8"))
        painter.drawText(
            QRectF(sw_x + sw_w + 7.0, 0.0, w - (sw_x + sw_w + 12.0), h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )
        painter.end()


class _ConsoleActionButton(QPushButton):
    """60 FPS click-bounce action button for Developer Console footer."""

    def __init__(
        self,
        text: str = "",
        role: str = "secondary",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        self._role = role  # "secondary", "primary", "danger", "active_pause"
        self._hover = False
        self._scale = 1.0
        self._step = 0
        self.setFixedHeight(30)
        self.setMinimumWidth(96)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def set_role(self, role: str) -> None:
        self._role = role
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, a0) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(a0)

    def mousePressEvent(self, e) -> None:
        if e is not None and e.button() == Qt.MouseButton.LeftButton:
            self._step = 1
            self._scale = 0.90
            if not self._timer.isActive():
                self._timer.start()
            self.update()
        super().mousePressEvent(e)

    def _tick(self) -> None:
        scales = [0.90, 0.95, 1.04, 1.01, 1.0]
        if 0 < self._step <= len(scales):
            self._scale = scales[self._step - 1]
            self._step += 1
        else:
            self._scale = 1.0
            self._step = 0
            self._timer.stop()
        self.update()

    def paintEvent(self, a0) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        painter.translate(w / 2.0, h / 2.0)
        painter.scale(self._scale, self._scale)
        painter.translate(-w / 2.0, -h / 2.0)

        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        if self._role in ("primary", "active_pause"):
            bg = QColor(PALETTE["accent_hover"] if self._hover else PALETTE["accent"])
            border = QColor(255, 255, 255, 55)
            fg = QColor(PALETTE["on_accent"])
        elif self._role == "danger":
            bg = QColor(255, 75, 95, 52 if self._hover else 22)
            border = QColor(255, 95, 115, 130 if self._hover else 65)
            fg = QColor("#ffffff" if self._hover else "#ff8595")
        else:
            bg = accent_qcolor(38) if self._hover else QColor(255, 255, 255, 16)
            border = QColor(PALETTE["accent"]) if self._hover else QColor(255, 255, 255, 36)
            fg = QColor("#ffffff" if self._hover else "#dfe4f4")

        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.1))
        painter.drawRoundedRect(rect, 9.0, 9.0)

        font = QFont("Segoe UI")
        font.setPixelSize(12)
        font.setWeight(
            QFont.Weight.Bold
            if self._role in ("primary", "active_pause")
            else QFont.Weight.DemiBold
        )
        painter.setFont(font)
        painter.setPen(fg)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        painter.end()


class DevConsole(QObject):
    def __init__(self, parent=None, translator=None, logger=None):
        super().__init__(parent)
        self._parent = parent
        self._translator = translator
        self._logger = logger
        self._console_dialog: Optional[QDialog] = None
        self._console_text: Optional[QTextEdit] = None
        self._title_bar: Optional[CustomTitleBar] = None
        self._hdr_lbl: Optional[QLabel] = None
        self._lvl_lbl: Optional[QLabel] = None
        self._status_badge: Optional[QLabel] = None
        self._old_print = None
        self._qt_stream = None
        self._btn_clear: Optional[_ConsoleActionButton] = None
        self._btn_copy: Optional[_ConsoleActionButton] = None
        self._btn_pause: Optional[_ConsoleActionButton] = None
        self._btn_save: Optional[_ConsoleActionButton] = None
        self._cb_autoscroll: Optional[_ConsolePillToggle] = None
        self._cb_wrap: Optional[_ConsolePillToggle] = None
        self._level_combo: Optional[GlassComboBox] = None
        self._autoscroll_enabled = True
        self._paused = False
        self._pause_buffer: List[str] = []
        self._log_handler: Optional[_DevConsoleHandler] = None
        self._attached_loggers: List[logging.Logger] = []
        self._logging_active = False
        self._preopen_buffer: List[str] = []
        self._show_dev = False
        self._selected_level_text = "DEBUG"

    def _t(self, key: str, default: Optional[str] = None):
        try:
            if self._translator is not None and hasattr(self._translator, "t"):
                return self._translator.t(key)
        except Exception:
            pass
        return default or key

    def is_open(self) -> bool:
        try:
            dlg = getattr(self, "_console_dialog", None)
            return bool(dlg and dlg.isVisible())
        except Exception:
            return False

    def set_show_dev(self, show: bool) -> None:
        try:
            self._show_dev = bool(show)
        except Exception:
            pass

    def activate_logging(self) -> None:
        try:
            if getattr(self, "_logging_active", False):
                return
            self._qt_stream = _QtStream(self._append_console)
            try:
                self._old_print = builtins.print

                def _custom_print(*args, **kwargs):
                    try:
                        if self._old_print:
                            self._old_print(*args, **kwargs)
                    except Exception:
                        pass
                    try:
                        sep = kwargs.get("sep", " ")
                        end = kwargs.get("end", "\n")
                        msg = sep.join(str(a) for a in args) + end
                        if self._qt_stream:
                            self._qt_stream.write(msg)
                    except Exception:
                        pass

                builtins.print = _custom_print
            except Exception:
                pass

            try:
                self._log_handler = _DevConsoleHandler(
                    lambda s: self._qt_stream.write(s) if self._qt_stream else None
                )
                self._log_handler.setLevel(logging.DEBUG)
                fmt = logging.Formatter("[%(levelname)s] %(message)s")
                self._log_handler.setFormatter(fmt)

                root_lg = logging.getLogger()
                if self._log_handler not in root_lg.handlers:
                    root_lg.addHandler(self._log_handler)

                self._attached_loggers = []
                if self._logger is not None and isinstance(self._logger, logging.Logger):
                    if self._log_handler not in self._logger.handlers:
                        self._logger.addHandler(self._log_handler)
                        self._attached_loggers.append(self._logger)

                from core.logger import _created_loggers, register_logger_hook

                for lg in _created_loggers:
                    if isinstance(lg, logging.Logger) and self._log_handler not in lg.handlers:
                        lg.addHandler(self._log_handler)
                        self._attached_loggers.append(lg)

                register_logger_hook(self._on_logger_created)

                for name, lg in list(logging.Logger.manager.loggerDict.items()):
                    if isinstance(lg, logging.Logger):
                        low_name = str(name).lower()
                        if (
                            low_name.startswith("listenmoe")
                            or low_name.startswith("kikumoe")
                            or low_name.startswith("player")
                        ):
                            if self._log_handler not in lg.handlers:
                                lg.addHandler(self._log_handler)
                                self._attached_loggers.append(lg)
            except Exception:
                pass
        except Exception:
            pass
        self._logging_active = True

    def _on_logger_created(self, logger: logging.Logger) -> None:
        try:
            if self._log_handler is not None and logger not in self._attached_loggers:
                if self._log_handler not in logger.handlers:
                    logger.addHandler(self._log_handler)
                self._attached_loggers.append(logger)
        except Exception:
            pass

    def deactivate_logging(self) -> None:
        try:
            from core.logger import restore_default_level, unregister_logger_hook

            unregister_logger_hook(self._on_logger_created)
            restore_default_level()
        except Exception:
            pass
        try:
            if (
                not getattr(self, "_logging_active", False)
                and self._log_handler is None
                and self._old_print is None
            ):
                return
        except Exception:
            pass
        try:
            if self._old_print is not None:
                builtins.print = self._old_print
        except Exception:
            pass
        self._old_print = None
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
        self._logging_active = False

    def raise_window(self):
        try:
            if self._console_dialog:
                try:
                    if not self._console_dialog.isVisible():
                        self._console_dialog.show()
                except Exception:
                    pass
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

    def _update_status_badge(self) -> None:
        if not self._status_badge:
            return
        if self._paused:
            self._status_badge.setText(
                f"● {self._t('dev_console_status_paused', 'PAUSED').upper()}"
            )
            self._status_badge.setStyleSheet(
                f"background-color: {PALETTE['accent_soft']};"
                f" border: 1px solid {PALETTE['accent']};"
                " border-radius: 9px; padding: 2px 9px;"
                " color: #ffffff; font-size: 10px; font-weight: 800; letter-spacing: 0.8px;"
            )
        else:
            self._status_badge.setText(f"● {self._t('dev_console_status_live', 'LIVE').upper()}")
            self._status_badge.setStyleSheet(
                "background-color: rgba(0, 230, 118, 0.14);"
                " border: 1px solid rgba(0, 230, 118, 0.45);"
                " border-radius: 9px; padding: 2px 9px;"
                " color: #5ef2a6; font-size: 10px; font-weight: 800; letter-spacing: 0.8px;"
            )

    def apply_theme(self, dark: bool = True):
        try:
            if not self._console_dialog:
                return
            base_qss = get_cyber_moe_stylesheet(PALETTE["accent"])
            console_qss = f"""
            QDialog#devConsoleRoot {{
                background-color: {PALETTE["bg_dialog"]};
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 12px;
            }}
            QFrame#devConsoleToolbar {{
                background-color: {PALETTE["bg_surface"]};
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-top: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 12px;
            }}
            QFrame#devConsoleFooter {{
                background-color: {PALETTE["bg_footer"]};
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 12px;
            }}
            QTextEdit#devConsoleTerminal {{
                background-color: {PALETTE["bg_terminal"]};
                color: {PALETTE["text_primary"]};
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
                padding: 10px 12px;
                font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
                font-size: 12px;
                selection-background-color: {PALETTE["accent"]};
                selection-color: {PALETTE["on_accent"]};
            }}
            """
            self._console_dialog.setStyleSheet(base_qss + console_qss)
            if self._lvl_lbl is not None:
                self._lvl_lbl.setStyleSheet(
                    f"font-size: 10px; font-weight: 800; letter-spacing: 0.9px;"
                    f" color: {PALETTE['accent_hover']}; background: transparent; border: none;"
                )
            if self._title_bar is not None:
                self._title_bar.refresh_theme()
            if self._level_combo is not None and hasattr(self._level_combo, "refresh_theme"):
                self._level_combo.refresh_theme()
            for w in (
                self._cb_autoscroll,
                self._cb_wrap,
                self._btn_pause,
                self._btn_save,
                self._btn_clear,
                self._btn_copy,
            ):
                if w is not None:
                    w.update()
            self._update_status_badge()
            try:
                self._apply_windows_titlebar_dark_mode(True)
            except Exception:
                pass
        except Exception:
            pass

    def refresh_texts(self):
        try:
            if self._console_dialog:
                self._console_dialog.setWindowTitle(
                    self._t("dev_console_title", "Developer Console")
                )
                if self._hdr_lbl:
                    self._hdr_lbl.setText(self._t("dev_console_title", "Developer Console").upper())
                if self._lvl_lbl:
                    self._lvl_lbl.setText(self._t("dev_console_level_short", "LEVEL").upper())
                self._update_status_badge()
                if self._btn_clear:
                    self._btn_clear.setText(self._t("dev_console_clear", "Clear"))
                if self._btn_copy:
                    self._btn_copy.setText(self._t("dev_console_copy", "Copy All"))
                if self._btn_pause:
                    self._btn_pause.setText(
                        self._t("dev_console_pause", "Pause")
                        if not self._paused
                        else self._t("dev_console_resume", "Resume")
                    )
                if self._btn_save:
                    self._btn_save.setText(self._t("dev_console_save", "Save..."))
                if self._cb_autoscroll:
                    self._cb_autoscroll.setText(self._t("dev_console_autoscroll", "Autoscroll"))
                if self._cb_wrap:
                    self._cb_wrap.setText(self._t("dev_console_wrap", "Wrap"))
                if self._level_combo:
                    self._level_combo.setToolTip(self._t("dev_console_level", "Level filter"))
                if self._console_text:
                    self._console_text.setPlaceholderText(
                        self._t("dev_console_placeholder", "Logs will appear here...")
                    )
                    # Also localize the initial ready banner line if present
                    cur_txt = self._console_text.toPlainText()
                    ready_txt = self._t(
                        "dev_console_ready", "Console ready. Logs will appear here."
                    )
                    new_banner = f">>> {ready_txt}"
                    for old_b in (
                        ">>> Console pronta. I log appariranno qui.",
                        ">>> Console ready. Logs will appear here.",
                    ):
                        if cur_txt.startswith(old_b) and old_b != new_banner:
                            self._console_text.setPlainText(new_banner + cur_txt[len(old_b) :])
                            if self._autoscroll_enabled:
                                self._console_text.moveCursor(QTextCursor.MoveOperation.End)
                            break
        except Exception:
            pass

    def open(self, parent=None):
        try:
            self.activate_logging()
        except Exception:
            pass
        if self._console_dialog:
            self.raise_window()
            return

        dlg_parent = parent or self._parent
        self._console_dialog = QDialog(dlg_parent)
        self._console_dialog.setObjectName("devConsoleRoot")
        self._console_dialog.setWindowTitle(self._t("dev_console_title", "Developer Console"))
        self._console_dialog.setModal(False)
        self._console_dialog.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        )

        try:
            self._console_dialog.finished.connect(self._on_dialog_closed)
            self._console_dialog.destroyed.connect(self._on_dialog_destroyed)
        except Exception:
            pass
        try:
            self._console_dialog.setMinimumSize(720, 460)
            self._console_dialog.resize(760, 500)
        except Exception:
            pass

        outer = QVBoxLayout(self._console_dialog)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Custom Cyber-Moe Titlebar
        icon_app = getattr(dlg_parent, "_icon_app", None) if dlg_parent is not None else None
        self._title_bar = CustomTitleBar(self._console_dialog, icon=icon_app)
        outer.addWidget(self._title_bar)

        body = QVBoxLayout()
        body.setContentsMargins(14, 10, 14, 14)
        body.setSpacing(10)

        # 1. Top Toolbar Card (Header + Status Badge + Level Filter + Pill Toggles)
        toolbar_card = QFrame()
        toolbar_card.setObjectName("devConsoleToolbar")
        tb_lay = QHBoxLayout(toolbar_card)
        tb_lay.setContentsMargins(12, 8, 12, 8)
        tb_lay.setSpacing(10)

        self._hdr_lbl = QLabel(self._t("dev_console_title", "Developer Console").upper())
        self._hdr_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 800; letter-spacing: 1.2px; color: #f4f6fd;"
            " background: transparent; border: none;"
        )
        tb_lay.addWidget(self._hdr_lbl)

        self._status_badge = QLabel(f"● {self._t('dev_console_status_live', 'LIVE').upper()}")
        tb_lay.addWidget(self._status_badge)

        tb_lay.addStretch(1)

        self._lvl_lbl = QLabel(self._t("dev_console_level_short", "LEVEL").upper())
        self._lvl_lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 800; letter-spacing: 0.9px;"
            f" color: {PALETTE['accent_hover']}; background: transparent; border: none;"
        )
        tb_lay.addWidget(self._lvl_lbl)

        self._level_combo = GlassComboBox()
        self._level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        target_lvl = getattr(self, "_selected_level_text", "DEBUG")
        self._level_combo.setCurrentText(target_lvl)
        self._level_combo.currentTextChanged.connect(self._on_level_changed)
        self._on_level_changed(target_lvl)
        self._level_combo.setToolTip(self._t("dev_console_level", "Level filter"))
        self._level_combo.setFixedWidth(115)
        tb_lay.addWidget(self._level_combo)

        self._cb_autoscroll = _ConsolePillToggle(self._t("dev_console_autoscroll", "Autoscroll"))
        self._cb_autoscroll.setChecked(True)
        self._cb_autoscroll.toggled.connect(self._on_toggle_autoscroll)
        tb_lay.addWidget(self._cb_autoscroll)

        self._cb_wrap = _ConsolePillToggle(self._t("dev_console_wrap", "Wrap"))
        self._cb_wrap.setChecked(True)
        self._cb_wrap.toggled.connect(self._on_toggle_wrap)
        tb_lay.addWidget(self._cb_wrap)

        body.addWidget(toolbar_card)

        # 2. Obsidian Terminal Log Viewer
        self._console_text = QTextEdit()
        self._console_text.setObjectName("devConsoleTerminal")
        self._console_text.setReadOnly(True)
        self._console_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        try:
            self._console_text.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        except Exception:
            pass
        sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._console_text.setSizePolicy(sp)
        body.addWidget(self._console_text, 1)

        # 3. Bottom Action Deck
        footer_card = QFrame()
        footer_card.setObjectName("devConsoleFooter")
        f_lay = QHBoxLayout(footer_card)
        f_lay.setContentsMargins(10, 7, 10, 7)
        f_lay.setSpacing(8)

        self._btn_pause = _ConsoleActionButton(
            self._t("dev_console_pause", "Pause"),
            role="active_pause" if self._paused else "secondary",
        )
        self._btn_pause.clicked.connect(self._on_toggle_pause)

        self._btn_save = _ConsoleActionButton(
            self._t("dev_console_save", "Save..."),
            role="secondary",
        )
        self._btn_save.clicked.connect(self._on_save_clicked)

        self._btn_clear = _ConsoleActionButton(
            self._t("dev_console_clear", "Clear"),
            role="danger",
        )
        self._btn_clear.clicked.connect(
            lambda: self._console_text.clear() if self._console_text else None
        )

        self._btn_copy = _ConsoleActionButton(
            self._t("dev_console_copy", "Copy All"),
            role="primary",
        )
        self._btn_copy.clicked.connect(self._on_copy_clicked)

        f_lay.addWidget(self._btn_pause)
        f_lay.addWidget(self._btn_save)
        f_lay.addStretch(1)
        f_lay.addWidget(self._btn_clear)
        f_lay.addWidget(self._btn_copy)

        body.addWidget(footer_card)
        outer.addLayout(body, 1)

        install_size_grip(self._console_dialog)
        self.apply_theme(True)

        try:
            self._console_text.setPlaceholderText(
                self._t("dev_console_placeholder", "Logs will appear here...")
            )
            self._console_text.append(
                f">>> {self._t('dev_console_ready', 'Console ready. Logs will appear here.')}"
            )
        except Exception:
            pass

        try:
            from core.logger import get_recent_logs

            past_logs = get_recent_logs()
            if past_logs:
                for past_line in past_logs:
                    self._append_console(past_line + "\n")
            if getattr(self, "_preopen_buffer", None):
                buffered = "".join(self._preopen_buffer)
                self._preopen_buffer.clear()
                if buffered:
                    self._append_console(buffered)
        except Exception:
            pass

        try:
            self._console_dialog.show()
            self._apply_windows_titlebar_dark_mode(True)
            self.raise_window()
        except Exception:
            pass

    def _on_copy_clicked(self) -> None:
        if not self._console_text:
            return
        self._console_text.selectAll()
        self._console_text.copy()
        cursor = self._console_text.textCursor()
        cursor.clearSelection()
        self._console_text.setTextCursor(cursor)

    def close(self):
        try:
            from core.logger import restore_default_level

            restore_default_level()
        except Exception:
            pass
        try:
            if self._console_dialog:
                try:
                    self._console_dialog.close()
                except Exception:
                    pass
                self._console_dialog.deleteLater()
                self._console_dialog = None
                self._console_text = None
        except Exception:
            pass

    def _on_dialog_closed(self, *args, **kwargs):
        try:
            from core.logger import restore_default_level

            restore_default_level()
        except Exception:
            pass
        try:
            self._console_dialog = None
            self._console_text = None
        except Exception:
            pass

    def _on_dialog_destroyed(self, *args, **kwargs):
        try:
            from core.logger import restore_default_level

            restore_default_level()
        except Exception:
            pass
        try:
            self._console_dialog = None
            self._console_text = None
        except Exception:
            pass

    @pyqtSlot(str)
    def _append_console(self, s: str):
        try:
            if s is None:
                return
            text = str(s)
            if not text:
                return
            if not self._console_text:
                if getattr(self, "_logging_active", False) and not self._paused:
                    self._preopen_buffer.append(text)
                return
            if self._paused:
                self._pause_buffer.append(text)
                return
            try:
                lines = text.splitlines(True)
            except Exception:
                lines = [text]
            try:
                if not getattr(self, "_show_dev", False):
                    lines = [ln for ln in lines if "[DEV]" not in ln]
            except Exception:
                pass
            filtered = "".join(lines)
            if not filtered:
                return
            try:
                current = self._console_text.toPlainText()
                if current and not current.endswith("\n") and not filtered.startswith("\n"):
                    filtered = "\n" + filtered
            except Exception:
                pass
            sb = (
                self._console_text.verticalScrollBar()
                if hasattr(self._console_text, "verticalScrollBar")
                else None
            )
            prev_val = sb.value() if sb is not None else None
            self._console_text.moveCursor(QTextCursor.MoveOperation.End)
            self._console_text.insertPlainText(filtered)
            if self._autoscroll_enabled:
                self._console_text.moveCursor(QTextCursor.MoveOperation.End)
            else:
                if sb is not None and prev_val is not None:
                    sb.setValue(prev_val)
        except Exception:
            pass

    def _on_toggle_pause(self):
        try:
            self._paused = not self._paused
            if self._btn_pause:
                self._btn_pause.setText(
                    self._t("dev_console_pause", "Pause")
                    if not self._paused
                    else self._t("dev_console_resume", "Resume")
                )
                self._btn_pause.set_role("active_pause" if self._paused else "secondary")
            self._update_status_badge()
            if not self._paused and self._pause_buffer:
                flushed = "".join(self._pause_buffer)
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
                self._console_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
                try:
                    self._console_text.setWordWrapMode(
                        QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
                    )
                except Exception:
                    pass
            else:
                self._console_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        except Exception:
            pass

    def _on_level_changed(self, level_text: str):
        try:
            self._selected_level_text = level_text
            level_map = {
                "DEBUG": logging.DEBUG,
                "INFO": logging.INFO,
                "WARNING": logging.WARNING,
                "ERROR": logging.ERROR,
            }
            lvl = level_map.get(level_text, logging.DEBUG)
            if self._log_handler is not None:
                self._log_handler.setLevel(lvl)

            from core.logger import set_logger_level

            set_logger_level(lvl)

            if self._logger is not None and isinstance(self._logger, logging.Logger):
                try:
                    self._logger.setLevel(lvl)
                except Exception:
                    pass

            for lg in list(self._attached_loggers):
                try:
                    lg.setLevel(lvl)
                except Exception:
                    pass

            try:
                logging.getLogger().setLevel(lvl)
            except Exception:
                pass
        except Exception:
            pass

    @pyqtSlot()
    def _on_save_clicked(self):
        try:
            if not self._console_text:
                return
            import time

            ts = time.strftime("%Y%m%d-%H%M%S")
            suggested = f"console-{ts}.log"
            filename, _selected_filter = QFileDialog.getSaveFileName(
                self._console_dialog,
                self._t("dev_console_save", "Save..."),
                suggested,
                "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
            )
            if filename:
                text = self._console_text.toPlainText()
                try:
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(text)
                except Exception:
                    try:
                        with open(filename, "w", encoding="utf-8-sig") as f:
                            f.write(text)
                    except Exception:
                        pass
        except Exception:
            pass

    def _apply_windows_titlebar_dark_mode(self, enable: bool) -> None:
        try:
            dlg = getattr(self, "_console_dialog", None)
            apply_windows_titlebar_dark_mode(dlg, enable)
        except Exception:
            pass
