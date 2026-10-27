"""Compact lyric panel with animated scrolling for timed lines."""

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PyQt6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from core.lyrics import parse_lrc
from ui.themes.cyber_moe import PALETTE


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
        self.heading = QLabel("LYRICS · LRCLIB")
        self.heading.setObjectName("lyricsHeading")
        layout.addWidget(self.heading)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("lyricsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 4, 0)
        self.content_layout.setSpacing(9)
        self.content_layout.addStretch()
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, 1)
        self.animation = QPropertyAnimation(self.scroll.verticalScrollBar(), b"value", self)
        self.animation.setDuration(350)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_accent(self, accent):
        self._accent = accent
        self._update_styles()

    def _clear(self):
        self.animation.stop()
        self.lines, self.labels, self.active = [], [], -1
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_line(self, text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.content_layout.addWidget(label)
        self.labels.append(label)

    def show_message(self, text):
        self._clear()
        self._add_line(text)
        self.content_layout.addStretch()
        self._update_styles()
        self.scroll.verticalScrollBar().setValue(0)

    def show_record(self, record, plain_note):
        self._clear()
        self.lines = parse_lrc(record.get("syncedLyrics"))
        if self.lines:
            for _, text in self.lines:
                self._add_line(text or "♪")
        else:
            self._add_line(plain_note)
            self._add_line(record.get("plainLyrics") or "")
        self.content_layout.addStretch()
        self._update_styles()
        self.scroll.verticalScrollBar().setValue(0)

    def _update_styles(self):
        for index, label in enumerate(self.labels):
            if index == self.active:
                label.setStyleSheet(f"color: {self._accent}; font-size: 15px; font-weight: 800;")
            else:
                label.setStyleSheet("color: rgba(255, 255, 255, 0.65); font-size: 13px;")

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
        self.active = current
        self._update_styles()
        if current >= 0:
            bar = self.scroll.verticalScrollBar()
            target = self.labels[current].y() - self.scroll.viewport().height() // 2
            self.animation.stop()
            self.animation.setStartValue(bar.value())
            self.animation.setEndValue(max(0, min(bar.maximum(), target)))
            self.animation.start()
