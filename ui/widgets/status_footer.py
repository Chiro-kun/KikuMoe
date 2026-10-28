"""
StatusFooter widget for KikuMoe 2.0.0
Rich HUD Telemetry Bar with crisp modern typography and LED Pill Badges
for Audio Engine, Stream Codec, and Session Timer.
"""

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from ui.themes.cyber_moe import PALETTE


class StatusFooter(QFrame):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("statusFooter")
        self.setFixedHeight(30)
        self._has_backend_status = False
        self._backend_ready = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 1. Backend Engine Pill Badge
        self.engine_pill = QFrame()
        eng_layout = QHBoxLayout(self.engine_pill)
        eng_layout.setContentsMargins(10, 3, 10, 3)
        eng_layout.setSpacing(6)

        self.backend_dot = QLabel("●")
        self.backend_label = QLabel("AUDIO")
        eng_layout.addWidget(self.backend_dot)
        eng_layout.addWidget(self.backend_label)

        # 2. Codec Pill Badge
        self.codec_pill = QFrame()
        cod_layout = QHBoxLayout(self.codec_pill)
        cod_layout.setContentsMargins(10, 3, 10, 3)
        cod_layout.setSpacing(6)

        self.codec_dot = QLabel("◆")
        self.format_label = QLabel("VORBIS")
        cod_layout.addWidget(self.codec_dot)
        cod_layout.addWidget(self.format_label)

        # 3. Session Timer Pill Badge
        self.session_pill = QFrame()
        ses_layout = QHBoxLayout(self.session_pill)
        ses_layout.setContentsMargins(11, 3, 11, 3)
        ses_layout.setSpacing(6)

        self.session_label = QLabel("00:00:00")
        self.session_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        ses_layout.addWidget(self.session_label)

        layout.addWidget(self.engine_pill)
        layout.addWidget(self.codec_pill)
        layout.addStretch(1)
        layout.addWidget(self.session_pill)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        pill_style = (
            "QFrame {"
            f" background-color: {PALETTE['bg_footer_pill']};"
            " border: 1px solid rgba(255, 255, 255, 0.13);"
            " border-radius: 10px;"
            "}"
            " QLabel { border: none; background: transparent; }"
        )
        label_font_style = (
            'font-family: "Segoe UI", "Inter", -apple-system, sans-serif;'
            f" font-size: 12px; font-weight: 700; letter-spacing: 0.5px;"
            f" color: {PALETTE['text_primary']};"
        )
        for pill in (self.engine_pill, self.codec_pill, self.session_pill):
            pill.setStyleSheet(pill_style)
        for lbl in (self.backend_label, self.format_label, self.session_label):
            lbl.setStyleSheet(label_font_style)
        self.codec_dot.setStyleSheet(f"color: {PALETTE['accent_hover']}; font-size: 10px;")
        if self._has_backend_status:
            dot_color = PALETTE["status_online"] if self._backend_ready else PALETTE["status_error"]
        else:
            dot_color = PALETTE["text_muted"]
        self.backend_dot.setStyleSheet(f"color: {dot_color}; font-size: 10px;")

    def set_backend_status(self, backend_name: str, is_ready: bool = True) -> None:
        self._has_backend_status = True
        self._backend_ready = is_ready
        self.backend_label.setText(backend_name.upper())
        dot_color = PALETTE["status_online"] if is_ready else PALETTE["status_error"]
        self.backend_dot.setStyleSheet(f"color: {dot_color}; font-size: 10px;")

    def set_format(self, fmt: str) -> None:
        self.format_label.setText(fmt.upper())

    def set_session_time(self, text: str) -> None:
        self.session_label.setText(text)

    def set_session_visible(self, visible: bool) -> None:
        self.session_label.setVisible(visible)
        self.session_pill.setVisible(visible)
