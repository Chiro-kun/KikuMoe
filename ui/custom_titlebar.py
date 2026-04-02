"""Custom client-side title bar (CSD) for KikuMoe.

Draws a minimal title bar entirely within the Qt widget hierarchy so that the
window is always fully decorated regardless of what the compositor or window
manager provides.  Works identically on Wayland, X11, and Windows.

The owning window must have Qt.WindowType.FramelessWindowHint set before this
widget is shown.  Window dragging is delegated to the compositor / WM via
QWindow.startSystemMove(), which is the correct Wayland-native approach and
also works on X11 and Windows.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizeGrip, QWidget

_TITLE_BAR_HEIGHT = 32
_BTN_SIZE = QSize(40, _TITLE_BAR_HEIGHT)

# Plain string (not an f-string) — single braces are literal CSS braces.
_STYLE = """
    #customTitleBar {
        background-color: #2a2a2a;
        border-bottom: 1px solid #3a3a3a;
    }
    #customTitleBar QLabel#titleBarTitle {
        color: #cccccc;
        font-size: 12px;
        padding-left: 4px;
    }
    #customTitleBar QPushButton {
        background-color: transparent;
        color: #aaaaaa;
        border: none;
        border-radius: 0px;
        padding: 0px;
        font-size: 16px;
        font-weight: 600;
    }
    #customTitleBar QPushButton:hover {
        background-color: #3a3a3a;
        color: #ffffff;
    }
    #customTitleBar QPushButton#titleBarBtnClose {
        font-size: 24px;
        font-weight: 700;
    }
    #customTitleBar QPushButton#titleBarBtnClose:hover {
        background-color: #c0392b;
        color: #ffffff;
    }
"""


class CustomTitleBar(QWidget):
    """Minimal CSD title bar: icon · title · [—] [□] [×]."""

    HEIGHT = _TITLE_BAR_HEIGHT

    def __init__(self, window: QWidget, icon: QIcon | None = None) -> None:
        super().__init__(window)
        self._window = window
        self.setObjectName("customTitleBar")
        self.setFixedHeight(self.HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(2)

        # App icon
        self._icon_label = QLabel()
        self._icon_label.setObjectName("titleBarIcon")
        self._icon_label.setFixedSize(QSize(20, self.HEIGHT))
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icon and not icon.isNull():
            self._icon_label.setPixmap(icon.pixmap(QSize(14, 14)))
        layout.addWidget(self._icon_label)

        # Window title text
        self._title_label = QLabel()
        self._title_label.setObjectName("titleBarTitle")
        layout.addWidget(self._title_label, 1)

        # Window control buttons
        self._btn_min = QPushButton("—")
        self._btn_min.setObjectName("titleBarBtn")
        self._btn_min.setToolTip("Minimizza")
        self._btn_min.setFixedSize(_BTN_SIZE)

        self._btn_max = QPushButton("□")
        self._btn_max.setObjectName("titleBarBtn")
        self._btn_max.setToolTip("Ingrandisci")
        self._btn_max.setFixedSize(_BTN_SIZE)

        self._btn_close = QPushButton("×")
        self._btn_close.setObjectName("titleBarBtnClose")
        self._btn_close.setToolTip("Chiudi")
        self._btn_close.setFixedSize(_BTN_SIZE)

        layout.addWidget(self._btn_min)
        layout.addWidget(self._btn_max)
        layout.addWidget(self._btn_close)

        self._btn_min.clicked.connect(window.showMinimized)
        self._btn_max.clicked.connect(self._toggle_maximize)
        self._btn_close.clicked.connect(window.close)

        self.setStyleSheet(_STYLE)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_title(self, title: str) -> None:
        """Update the title text shown in the bar."""
        self._title_label.setText(title)

    def sync_maximize_button(self) -> None:
        """Call this from the window's changeEvent to keep the button in sync."""
        if self._window.isMaximized():
            self._btn_max.setText("❐")
            self._btn_max.setToolTip("Ripristina")
        else:
            self._btn_max.setText("□")
            self._btn_max.setToolTip("Ingrandisci")

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle:
                handle.startSystemMove()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()


# ---------------------------------------------------------------------------
# Resize grip
# ---------------------------------------------------------------------------


class _GripPositioner(QObject):
    """Event filter that keeps a QSizeGrip anchored to its window's bottom-right."""

    def __init__(self, window: QWidget, grip: QSizeGrip) -> None:
        super().__init__(window)
        self._grip = grip
        window.installEventFilter(self)
        self._reposition(window)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize:
            self._reposition(obj)
        return False

    def _reposition(self, window: QObject) -> None:
        g = self._grip
        w = window  # type: ignore[assignment]
        g.move(w.width() - g.width(), w.height() - g.height())


def install_size_grip(window: QWidget) -> None:
    """Attach a QSizeGrip overlay to the bottom-right corner of a frameless window.

    Qt6's QSizeGrip uses QWindow::startSystemResize() on Wayland, so it works
    correctly without any compositor-specific code.  On X11 and Windows it uses
    the platform's native resize mechanism.
    """
    grip = QSizeGrip(window)
    grip.setFixedSize(QSize(16, 16))
    grip.show()
    _GripPositioner(window, grip)
