"""
Cyber-Moe Glass Theme for KikuMoe 2.0.0
Defines color palette, visual constants, and dynamic Qt stylesheets (QSS)
inspired by modern dark glassmorphism and the official LISTEN.moe branding.
"""

from typing import Dict

# ---------------------------------------------------------------------------
# Color Palette
# ---------------------------------------------------------------------------
PALETTE: Dict[str, str] = {
    # Backgrounds
    "bg_main": "#0c0d14",  # Deep obsidian background
    "bg_surface": "#131520",  # Dark glass card surface
    "bg_surface_elevated": "#1a1d2e",  # Elevated surface for popups/dropdowns
    "bg_subtle": "#1f2235",  # Subtle fill for input fields / chips
    "bg_glass": "rgba(20, 22, 34, 0.75)",  # Translucent glass for cards
    # Accent & Brand (LISTEN.moe Magenta)
    "accent": "#ec186c",  # Primary neon magenta
    "accent_hover": "#ff2a85",  # Brighter magenta on hover
    "accent_pressed": "#c21056",  # Darker magenta on click
    "accent_glow": "rgba(236, 24, 108, 0.35)",  # Soft glow rgba
    "accent_subtle": "rgba(236, 24, 108, 0.15)",  # Light tint
    # Borders & Dividers
    "border_subtle": "rgba(255, 255, 255, 0.08)",
    "border_card": "rgba(255, 255, 255, 0.12)",
    "border_highlight": "rgba(236, 24, 108, 0.50)",
    # Typography
    "text_primary": "#ffffff",  # Headers and song title
    "text_secondary": "#a0a5b8",  # Artist, subtitle, labels
    "text_muted": "#64687d",  # Placeholders, minor hints
    "text_accent": "#ff2e7e",  # Accent highlights
    # Scrollbars
    "scrollbar_track": "rgba(255, 255, 255, 0.04)",
    "scrollbar_handle": "rgba(236, 24, 108, 0.48)",
    "scrollbar_handle_hover": "#ec186c",
    "scrollbar_handle_pressed": "#ff2a85",
    "lyrics_background": "transparent",
    "lyrics_border": "transparent",
    "lyrics_skeleton_base": "#1affffff",
    "lyrics_skeleton_shine": "#4dffffff",
    # Radio selector glass
    "station_glass_overlay": "#c00c0e18",
    "station_glass_fallback": "#f0141622",
    "station_glass_rim": "#30ffffff",
    "station_selected_bg": "rgba(236, 24, 108, 0.20)",
    "station_selected_hover": "rgba(236, 24, 108, 0.28)",
    # Status Colors
    "status_online": "#00e676",  # Connected / audio playing
    "status_warning": "#ffab00",  # Buffering / reconnecting
    "status_error": "#ff5252",  # Disconnected / backend error
}


def get_cyber_moe_stylesheet(accent: str = PALETTE["accent"]) -> str:
    """
    Returns the application-wide QSS stylesheet formatted with the specified accent color.
    """
    hover_accent = PALETTE["accent_hover"]
    pressed_accent = PALETTE["accent_pressed"]
    border_subtle = PALETTE["border_subtle"]
    border_card = PALETTE["border_card"]
    bg_main = PALETTE["bg_main"]
    bg_subtle = PALETTE["bg_subtle"]
    text_primary = PALETTE["text_primary"]
    text_secondary = PALETTE["text_secondary"]
    text_muted = PALETTE["text_muted"]

    return f"""
    /* --- Global Application Reset & Typography --- */
    QWidget {{
        background-color: transparent;
        color: {text_primary};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 13px;
        outline: none;
    }}

    /* Main Window Root */
    QWidget#mainWindowRoot {{
        background-color: {bg_main};
    }}

    QWidget#lyricsPanel {{
        background-color: {PALETTE["lyrics_background"]};
        border: 1px solid {PALETTE["lyrics_border"]};
        border-radius: 14px;
    }}
    QScrollArea#lyricsScroll {{ border: 0; background: transparent; }}

    /* Glass Cards */
    QFrame#glassCard, QWidget#glassCard {{
        background-color: rgba(18, 20, 32, 0.82);
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: 14px;
    }}

    /* Sculpted Lower Console Deck */
    QFrame#consoleDeck {{
        background-color: qlineargradient(
            x1: 0, y1: 0, x2: 0, y2: 1,
            stop: 0 rgba(25, 28, 44, 0.84),
            stop: 1 rgba(13, 15, 24, 0.92)
        );
        border-top: 1px solid rgba(255, 255, 255, 0.18);
        border-left: 1px solid rgba(255, 255, 255, 0.10);
        border-right: 1px solid rgba(255, 255, 255, 0.10);
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
    }}

    /* --- Labels --- */
    QLabel {{
        background-color: transparent;
        color: {text_primary};
    }}
    QLabel#songTitleLabel {{
        font-size: 16px;
        font-weight: 700;
        color: {text_primary};
        padding: 2px 0px;
    }}
    QLabel#songArtistLabel {{
        font-size: 13px;
        font-weight: 500;
        color: {text_secondary};
        padding: 0px;
    }}
    QLabel#timeDisplayLabel {{
        font-size: 11px;
        font-weight: 600;
        color: {text_muted};
        font-family: "Consolas", "Courier New", monospace;
    }}
    QLabel#sectionTitleLabel {{
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: {text_muted};
    }}

    /* --- Push Buttons --- */
    QPushButton {{
        background-color: {bg_subtle};
        color: {text_primary};
        border: 1px solid {border_subtle};
        border-radius: 8px;
        padding: 6px 14px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.20);
    }}
    QPushButton:pressed {{
        background-color: rgba(255, 255, 255, 0.04);
    }}
    QPushButton:disabled {{
        background-color: rgba(255, 255, 255, 0.02);
        color: {text_muted};
        border-color: rgba(255, 255, 255, 0.04);
    }}

    /* Primary Accent Button */
    QPushButton#primaryButton {{
        background-color: {accent};
        color: #ffffff;
        border: none;
        border-radius: 13px;
        font-weight: 600;
    }}
    QPushButton#primaryButton:hover {{
        background-color: {hover_accent};
    }}
    QPushButton#primaryButton:pressed {{
        background-color: {pressed_accent};
    }}

    /* Circular Hero Play Button */
    QPushButton#heroPlayButton {{
        background-color: {accent};
        border: none;
        border-radius: 25px;
    }}
    QPushButton#heroPlayButton:hover {{
        background-color: {hover_accent};
    }}
    QPushButton#heroPlayButton:pressed {{
        background-color: {pressed_accent};
    }}

    /* Pill Action Buttons (Secondary) */
    QPushButton#pillButton {{
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 12px;
        padding: 3px 8px;
        font-size: 11px;
        color: {text_secondary};
    }}
    QPushButton#pillButton:hover {{
        background-color: rgba(255, 255, 255, 0.12);
        color: {text_primary};
        border-color: rgba(255, 255, 255, 0.25);
    }}
    QPushButton#pillButton:checked {{
        background-color: rgba(236, 24, 108, 0.20);
        border: 1px solid {accent};
        color: #ffffff;
    }}

    /* Danger / Force Stop Button */
    QPushButton#dangerButton {{
        background-color: rgba(255, 82, 82, 0.12);
        color: #ff6e6e;
        border: 1px solid rgba(255, 82, 82, 0.25);
        border-radius: 8px;
        padding: 5px 10px;
        font-size: 11px;
        font-weight: 600;
    }}
    QPushButton#dangerButton:hover {{
        background-color: rgba(255, 82, 82, 0.25);
        border-color: rgba(255, 82, 82, 0.50);
        color: #ffffff;
    }}

    /* Top Bar Settings Icon Button */
    QPushButton#iconMenuButton {{
        background-color: rgba(255, 255, 255, 0.04);
        border: 1px solid {border_subtle};
        border-radius: 8px;
        padding: 5px;
    }}
    QPushButton#iconMenuButton:hover {{
        background-color: rgba(255, 255, 255, 0.10);
        border-color: rgba(255, 255, 255, 0.22);
    }}

    /* --- Sliders --- */
    QSlider::groove:horizontal {{
        height: 4px;
        background: rgba(255, 255, 255, 0.12);
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {accent};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: #ffffff;
        width: 14px;
        height: 14px;
        margin: -5px 0px;
        border-radius: 7px;
        border: 2px solid {accent};
    }}
    QSlider::handle:horizontal:hover {{
        background: #ffeef5;
        border: 2px solid {hover_accent};
        width: 14px;
        height: 14px;
        margin: -5px 0px;
        border-radius: 7px;
    }}

    /* --- Progress Bar --- */
    QProgressBar {{
        background-color: rgba(255, 255, 255, 0.08);
        border: none;
        border-radius: 2px;
        height: 4px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background-color: {accent};
        border-radius: 2px;
    }}

    /* --- Checkboxes --- */
    QCheckBox {{
        spacing: 8px;
        color: {text_secondary};
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 5px;
        border: 1px solid {border_card};
        background-color: rgba(255, 255, 255, 0.04);
    }}
    QCheckBox::indicator:hover {{
        border-color: rgba(255, 255, 255, 0.30);
    }}
    QCheckBox::indicator:checked {{
        background-color: {accent};
        border-color: {accent};
    }}

    /* --- Inputs & Spin Boxes --- */
    QLineEdit, QComboBox {{
        background-color: rgba(255, 255, 255, 0.06);
        color: {text_primary};
        border: 1px solid {border_subtle};
        border-radius: 8px;
        padding: 5px 10px;
        font-size: 12px;
        font-weight: 500;
    }}
    QSpinBox {{
        background-color: rgba(255, 255, 255, 0.06);
        color: {text_primary};
        border: 1px solid {border_subtle};
        border-radius: 8px;
        padding: 2px 6px;
        font-size: 12px;
        font-weight: 600;
    }}
    QLineEdit:focus, QSpinBox:focus {{
        border: 1px solid {accent};
        background-color: rgba(255, 255, 255, 0.08);
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    /* ComboBox popup container transparent background (prevents white box behind corners) */
    QComboBox QFrame {{
        background-color: transparent;
        border: none;
    }}
    QComboBox QAbstractItemView {{
        background-color: #151826;
        border: 1px solid rgba(236, 24, 108, 0.55);
        color: {text_primary};
        font-size: 12px;
        font-weight: 500;
        selection-background-color: {accent};
        selection-color: #ffffff;
        border-radius: 8px;
        padding: 4px;
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 25px;
        padding: 3px 10px;
        border-radius: 5px;
    }}
    QComboBox QAbstractItemView::item:hover,
    QComboBox QAbstractItemView::item:selected {{
        background-color: {accent};
        color: #ffffff;
    }}

    /* --- Context Menus & Tooltips --- */
    QMenu {{
        background-color: #161826;
        border: 1px solid {border_card};
        border-radius: 10px;
        padding: 6px 4px;
    }}
    QMenu::item {{
        padding: 6px 24px 6px 10px;
        border-radius: 6px;
        color: {text_primary};
    }}
    QMenu::item:selected {{
        background-color: rgba(236, 24, 108, 0.25);
        color: #ffffff;
    }}
    QMenu::separator {{
        height: 1px;
        background: {border_subtle};
        margin: 4px 8px;
    }}
    QToolTip {{
        background-color: #1a1d2e;
        color: {text_primary};
        border: 1px solid {border_card};
        padding: 4px 8px;
        font-size: 11px;
    }}

    /* --- Dialogs & Scrollbars --- */
    QDialog {{
        background-color: {bg_main};
        color: {text_primary};
    }}
    QScrollBar:vertical {{
        background: {PALETTE["scrollbar_track"]};
        width: 7px;
        border-radius: 3px;
        margin: 2px 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {PALETTE["scrollbar_handle"]};
        border-radius: 3px;
        min-height: 24px;
    }}
    QScrollBar:horizontal {{
        background: {PALETTE["scrollbar_track"]};
        height: 7px;
        border-radius: 3px;
        margin: 0px 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {PALETTE["scrollbar_handle"]};
        border-radius: 3px;
        min-width: 24px;
    }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: {PALETTE["scrollbar_handle_hover"]};
    }}
    QScrollBar::handle:vertical:pressed, QScrollBar::handle:horizontal:pressed {{
        background: {PALETTE["scrollbar_handle_pressed"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: transparent;
    }}
    """
