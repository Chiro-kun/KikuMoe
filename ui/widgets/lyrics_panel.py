"""Compact lyric panel with animated scrolling for timed lines."""

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PyQt6.QtGui import QColor, QLinearGradient, QPainter
from PyQt6.QtWidgets import QLabel, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from core.lyrics import parse_lrc
from ui.themes.cyber_moe import PALETTE


class LyricLine(QLabel):
    """A line that fades smoothly between its inactive and active colors."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._color = QColor(255, 255, 255, 165)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(400)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.valueChanged.connect(self._set_color)
        self._set_color(self._color)

    def _set_color(self, color):
        self._color = QColor(color)
        self.setStyleSheet(
            f"color: rgba({self._color.red()}, {self._color.green()}, "
            f"{self._color.blue()}, {self._color.alpha()}); font-size: 14px; font-weight: 700;"
        )

    def set_active(self, active, accent, animate=True):
        target = QColor(accent) if active else QColor(255, 255, 255, 165)
        self._animation.stop()
        if not animate:
            self._set_color(target)
            return
        self._animation.setStartValue(self._color)
        self._animation.setEndValue(target)
        self._animation.start()


class LyricsSkeleton(QWidget):
    """Shimmering placeholders while the lyrics request is in flight."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(32)
        self.timer.timeout.connect(self._tick)

    def _tick(self):
        self._phase = (self._phase + 0.025) % 1.0
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        width = float(self.width())
        center_y = float(self.height()) / 2
        for index, fraction in enumerate((0.55, 0.76, 0.63, 0.82, 0.48)):
            line_width = max(10.0, width * fraction)
            rect = QRectF((width - line_width) / 2, center_y - 61 + index * 27, line_width, 10)
            gradient = QLinearGradient(rect.left(), 0, rect.right(), 0)
            base = QColor(PALETTE["lyrics_skeleton_base"])
            shine = QColor(PALETTE["lyrics_skeleton_shine"])
            pos = self._phase * 1.5 - 0.25
            center = max(0.0, min(1.0, pos))
            for stop in (0.0, max(0.0, center - 0.23), center, min(1.0, center + 0.23), 1.0):
                strength = max(0.0, 1.0 - abs(stop - pos) / 0.23)
                color = QColor(base)
                color.setAlpha(round(base.alpha() + (shine.alpha() - base.alpha()) * strength))
                gradient.setColorAt(stop, color)
            painter.setBrush(gradient)
            painter.drawRoundedRect(rect, 5, 5)
        painter.end()


class LyricsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("lyricsPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(190)
        self.setFixedHeight(222)
        self.lines = []
        self.labels = []
        self.active = -1
        self._accent = PALETTE["accent"]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("lyricsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().installEventFilter(self)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 4, 0)
        self.content_layout.setSpacing(9)
        self.content_layout.addStretch()
        self.scroll.setWidget(self.content)
        self.skeleton = LyricsSkeleton()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.scroll)
        self.stack.addWidget(self.skeleton)
        layout.addWidget(self.stack, 1)
        self.animation = QPropertyAnimation(self.scroll.verticalScrollBar(), b"value", self)
        self.animation.setDuration(350)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._recenter_timer = QTimer(self)
        self._recenter_timer.setSingleShot(True)
        self._recenter_timer.timeout.connect(self._recenter_active)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._schedule_recenter)

    def set_accent(self, accent):
        self._accent = accent
        self._update_styles(animate=False)
        self.skeleton.update()
        self.update()

    def refresh_theme(self):
        self.set_accent(PALETTE["accent"])

    def _clear(self):
        self.animation.stop()
        self._recenter_timer.stop()
        self.lines, self.labels, self.active = [], [], -1
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_line(self, text):
        label = LyricLine(text)
        self.content_layout.addWidget(label)
        self.labels.append(label)

    def show_message(self, text):
        self.stack.setCurrentWidget(self.scroll)
        self._clear()
        self.content_layout.setContentsMargins(0, 0, 4, 0)
        self._add_line(text)
        self.content_layout.addStretch()
        self._update_styles()
        self.scroll.verticalScrollBar().setValue(0)

    def show_record(self, record, plain_note, timing_note=""):
        self.stack.setCurrentWidget(self.scroll)
        self._clear()
        self.lines = parse_lrc(record.get("syncedLyrics"))
        if self.lines and not timing_note:
            self._update_padding()
            for _, text in self.lines:
                self._add_line(text or "♪")
        else:
            self.content_layout.setContentsMargins(0, 0, 4, 0)
            text = record.get("plainLyrics") or "\n".join(text for _, text in self.lines)
            self.lines = []
            self._add_line(timing_note or plain_note)
            self._add_line(text)
            self.content_layout.addStretch()
        self._update_styles()
        self.scroll.verticalScrollBar().setValue(0)

    def show_loading(self, text):
        self._clear()
        self.skeleton.setAccessibleName(text)
        self.stack.setCurrentWidget(self.skeleton)
        if self.skeleton.isVisible():
            self.skeleton.timer.start()

    def _update_styles(self, animate=False):
        for index, label in enumerate(self.labels):
            label.set_active(index == self.active, self._accent, animate)

    def _update_padding(self):
        padding = max(0, self.scroll.viewport().height() // 2)
        self.content_layout.setContentsMargins(0, padding, 4, padding)

    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize and self.lines:
            self._update_padding()
            self._schedule_recenter()
        return super().eventFilter(watched, event)

    def _schedule_recenter(self, *args):
        if self.active >= 0:
            self._recenter_timer.start(0)

    def _recenter_active(self):
        if self.active < 0 or self.active >= len(self.labels):
            return
        self.content_layout.activate()
        label = self.labels[self.active]
        bar = self.scroll.verticalScrollBar()
        target = label.y() + label.height() // 2 - self.scroll.viewport().height() // 2
        self.animation.stop()
        self.animation.setStartValue(bar.value())
        self.animation.setEndValue(max(0, min(bar.maximum(), target)))
        self.animation.start()

    def set_position(self, seconds):
        if not self.lines:
            return
        current = -1
        for index, (timestamp, _) in enumerate(self.lines):
            if timestamp > seconds:
                break
            current = index
        if current == self.active:
            return
        previous = self.active
        self.active = current
        if previous >= 0:
            self.labels[previous].set_active(False, self._accent)
        if current >= 0:
            self.labels[current].set_active(True, self._accent)
            self._schedule_recenter()
