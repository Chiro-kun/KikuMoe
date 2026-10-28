"""
Dynamic Theme & Custom Accent Engine for KikuMoe 2.0.0.
Aggregates individual theme preset modules, computes dynamic custom accent shades/glows,
synchronizes PALETTE in-place, and caches generated Qt stylesheets (QSS).
"""

import colorsys
import re
from typing import Dict, Optional, Tuple

from PyQt6.QtGui import QColor

from core.constants import (
    DEFAULT_ACCENT_COLOR,
    DEFAULT_THEME,
    THEME_CYBER_MOE,
    THEME_MIDNIGHT_AMOLED,
    THEME_NEON_MATRIX,
    THEME_OCEAN_CYAN,
    THEME_SAKURA_BLOOM,
)

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

THEME_ORDER: Tuple[str, ...] = (
    THEME_CYBER_MOE,
    THEME_MIDNIGHT_AMOLED,
    THEME_SAKURA_BLOOM,
    THEME_NEON_MATRIX,
    THEME_OCEAN_CYAN,
)

THEME_PRESETS: Dict[str, Dict[str, str]] = {}
PALETTE: Dict[str, str] = {}
_STYLESHEET_CACHE: Dict[Tuple[str, str], str] = {}


def is_valid_hex_color(value: Optional[str]) -> bool:
    """Return True if value is a valid 3-digit or 6-digit RGB hex color string."""
    if not isinstance(value, str):
        return False
    return bool(_HEX_RE.match(value.strip()))


def normalize_hex_color(value: Optional[str], fallback: str = DEFAULT_ACCENT_COLOR) -> str:
    """Normalize a hex color string to lowercase '#rrggbb', falling back safely if invalid."""
    if not isinstance(value, str):
        return fallback.lower()
    m = _HEX_RE.match(value.strip())
    if not m:
        return fallback.lower()
    raw = m.group(1).lower()
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    return f"#{raw}"


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    norm = normalize_hex_color(hex_color)
    return int(norm[1:3], 16), int(norm[3:5], 16), int(norm[5:7], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def _hls_to_hex(h: float, lightness: float, s: float) -> str:
    rf, gf, bf = colorsys.hls_to_rgb(
        h % 1.0,
        max(0.0, min(1.0, lightness)),
        max(0.0, min(1.0, s)),
    )
    return _rgb_to_hex(round(rf * 255), round(gf * 255), round(bf * 255))


def _relative_luminance(r: int, g: int, b: int) -> float:
    def _lin(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def derive_accent_tokens(accent_hex: str) -> Dict[str, str]:
    """
    Derive all hover, pressed, glow, border, shimmer, text, and scrollbar tokens
    dynamically from any primary accent color.
    """
    base = normalize_hex_color(accent_hex)
    r, g, b = _hex_to_rgb(base)
    h, lightness, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)

    hover_l = min(0.84, lightness + max(0.07, (1.0 - lightness) * 0.20))
    hover_s = min(1.0, s * 1.08) if s > 0.04 else s
    hover_hex = _hls_to_hex(h, hover_l, hover_s)

    pressed_l = max(0.14, lightness * 0.78)
    pressed_hex = _hls_to_hex(h, pressed_l, s)

    deep_l = max(0.11, lightness * 0.62)
    deep_hex = _hls_to_hex(h, deep_l, s)

    deeper_l = max(0.08, lightness * 0.46)
    deeper_hex = _hls_to_hex(h, deeper_l, s)

    shimmer_l = min(0.90, lightness + max(0.16, (1.0 - lightness) * 0.42))
    shimmer_s = min(1.0, max(s, 0.65)) if s > 0.04 else s
    shimmer_hex = _hls_to_hex(h, shimmer_l, shimmer_s)

    handle_hover_l = min(0.96, lightness + (1.0 - lightness) * 0.84)
    handle_hover_hex = _hls_to_hex(h, handle_hover_l, min(1.0, s * 0.85))

    text_l = max(0.64, min(0.86, lightness + 0.14))
    text_s = min(1.0, max(s, 0.70)) if s > 0.04 else s
    text_accent_hex = _hls_to_hex(h, text_l, text_s)

    lum = _relative_luminance(r, g, b)
    on_accent = "#080c12" if lum > 0.62 else "#ffffff"

    return {
        "accent": base,
        "accent_hover": hover_hex,
        "accent_pressed": pressed_hex,
        "accent_deep": deep_hex,
        "accent_deeper": deeper_hex,
        "accent_shimmer": shimmer_hex,
        "accent_handle_hover": handle_hover_hex,
        "text_accent": text_accent_hex,
        "on_accent": on_accent,
        "accent_glow": f"rgba({r}, {g}, {b}, 0.35)",
        "accent_subtle": f"rgba({r}, {g}, {b}, 0.15)",
        "accent_soft": f"rgba({r}, {g}, {b}, 0.22)",
        "accent_menu_hover": f"rgba({r}, {g}, {b}, 0.25)",
        "accent_focus_bg": f"rgba({r}, {g}, {b}, 0.12)",
        "border_highlight": f"rgba({r}, {g}, {b}, 0.55)",
        "scrollbar_handle": f"rgba({r}, {g}, {b}, 0.48)",
        "scrollbar_handle_hover": base,
        "scrollbar_handle_pressed": hover_hex,
        "station_selected_bg": f"rgba({r}, {g}, {b}, 0.20)",
        "station_selected_hover": f"rgba({r}, {g}, {b}, 0.28)",
    }


def get_preset_default_accent(theme_id: Optional[str]) -> str:
    """Return the built-in default accent hex color for a given theme preset."""
    preset = THEME_PRESETS.get(str(theme_id or "").strip().lower())
    if preset is None:
        preset = THEME_PRESETS[DEFAULT_THEME]
    return preset["default_accent"]


def resolve_theme_and_accent(
    theme_id: Optional[str] = None,
    custom_accent: Optional[str] = None,
) -> Tuple[str, str]:
    """Resolve normalized (theme_id, effective_accent_hex) without mutating PALETTE."""
    key = str(theme_id or DEFAULT_THEME).strip().lower()
    if key not in THEME_PRESETS:
        key = DEFAULT_THEME
    preset = THEME_PRESETS[key]
    if is_valid_hex_color(custom_accent):
        acc = normalize_hex_color(custom_accent, preset["default_accent"])
    else:
        acc = preset["default_accent"].lower()
    return key, acc


def _build_palette_dict(
    theme_id: str = DEFAULT_THEME,
    custom_accent: Optional[str] = None,
) -> Dict[str, str]:
    key, effective_accent = resolve_theme_and_accent(theme_id, custom_accent)
    preset = THEME_PRESETS[key]
    use_custom = is_valid_hex_color(custom_accent)

    built: Dict[str, str] = dict(preset)
    built["theme_id"] = key
    built["custom_accent_active"] = "true" if use_custom else "false"
    built.update(derive_accent_tokens(effective_accent))
    return built


def apply_theme_palette(
    theme_id: str = DEFAULT_THEME,
    custom_accent: Optional[str] = None,
) -> Dict[str, str]:
    """
    Mutate PALETTE in-place with the chosen preset surfaces and optional custom accent override.
    Returns PALETTE for convenience.
    """
    updated = _build_palette_dict(theme_id=theme_id, custom_accent=custom_accent)
    PALETTE.clear()
    PALETTE.update(updated)
    return PALETTE


def accent_qcolor(alpha: Optional[int] = None, key: str = "accent") -> QColor:
    """Return a QColor from PALETTE[key] (defaults to 'accent') with optional 0..255 alpha."""
    col = QColor(PALETTE.get(key, PALETTE["accent"]))
    if alpha is not None:
        col.setAlpha(max(0, min(255, int(alpha))))
    return col


def surface_qcolor(alpha: Optional[int] = None, key: str = "bg_surface") -> QColor:
    """Return a QColor from PALETTE[key] (defaults to 'bg_surface') with optional 0..255 alpha."""
    col = QColor(PALETTE.get(key, "#151826"))
    if alpha is not None:
        col.setAlpha(max(0, min(255, int(alpha))))
    return col


def get_cyber_moe_stylesheet(accent: Optional[str] = None) -> str:
    """
    Return the application-wide QSS stylesheet formatted with the active theme surfaces
    and either PALETTE's active accent or an explicitly supplied accent override.
    Cached by (theme_id, accent) to avoid redundant large-string formatting.
    """
    theme_key = PALETTE.get("theme_id", DEFAULT_THEME)
    if accent is not None and is_valid_hex_color(accent):
        norm = normalize_hex_color(accent)
        if norm != PALETTE["accent"]:
            tokens = {**PALETTE, **derive_accent_tokens(norm)}
        else:
            tokens = PALETTE
    else:
        norm = PALETTE["accent"]
        tokens = PALETTE

    cache_key = (theme_key, norm)
    cached = _STYLESHEET_CACHE.get(cache_key)
    if cached is not None:
        return cached

    act = tokens["accent"]
    hover_accent = tokens["accent_hover"]
    pressed_accent = tokens["accent_pressed"]
    on_accent = tokens["on_accent"]
    handle_hover = tokens["accent_handle_hover"]
    border_subtle = tokens["border_subtle"]
    border_card = tokens["border_card"]
    border_highlight = tokens["border_highlight"]
    bg_main = tokens["bg_main"]
    bg_surface = tokens["bg_surface"]
    bg_surface_elevated = tokens["bg_surface_elevated"]
    bg_popover = tokens["bg_popover"]
    bg_subtle = tokens["bg_subtle"]
    bg_card_glass = tokens["bg_card_glass"]
    bg_console_top = tokens["bg_console_top"]
    bg_console_bottom = tokens["bg_console_bottom"]
    text_primary = tokens["text_primary"]
    text_secondary = tokens["text_secondary"]
    text_muted = tokens["text_muted"]
    station_sel_bg = tokens["station_selected_bg"]
    menu_hover_bg = tokens["accent_menu_hover"]

    qss = f"""
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
        background-color: {tokens["lyrics_background"]};
        border: 1px solid {tokens["lyrics_border"]};
        border-radius: 14px;
    }}
    QScrollArea#lyricsScroll {{ border: 0; background: transparent; }}

    /* Glass Cards */
    QFrame#glassCard, QWidget#glassCard {{
        background-color: {bg_card_glass};
        border: 1px solid {border_card};
        border-radius: 14px;
    }}

    /* Sculpted Lower Console Deck */
    QFrame#consoleDeck {{
        background-color: qlineargradient(
            x1: 0, y1: 0, x2: 0, y2: 1,
            stop: 0 {bg_console_top},
            stop: 1 {bg_console_bottom}
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
        background-color: {act};
        color: {on_accent};
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
        background-color: {act};
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
        background-color: {station_sel_bg};
        border: 1px solid {act};
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
        background: {act};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: #ffffff;
        width: 14px;
        height: 14px;
        margin: -5px 0px;
        border-radius: 7px;
        border: 2px solid {act};
    }}
    QSlider::handle:horizontal:hover {{
        background: {handle_hover};
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
        background-color: {act};
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
        background-color: {act};
        border-color: {act};
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
        border: 1px solid {act};
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
        background-color: {bg_surface};
        border: 1px solid {border_highlight};
        color: {text_primary};
        font-size: 12px;
        font-weight: 500;
        selection-background-color: {act};
        selection-color: {on_accent};
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
        background-color: {act};
        color: {on_accent};
    }}

    /* --- Context Menus & Tooltips --- */
    QMenu {{
        background-color: {bg_popover};
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
        background-color: {menu_hover_bg};
        color: #ffffff;
    }}
    QMenu::separator {{
        height: 1px;
        background: {border_subtle};
        margin: 4px 8px;
    }}
    QToolTip {{
        background-color: {bg_surface_elevated};
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
        background: {tokens["scrollbar_track"]};
        width: 7px;
        border-radius: 3px;
        margin: 2px 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {tokens["scrollbar_handle"]};
        border-radius: 3px;
        min-height: 24px;
    }}
    QScrollBar:horizontal {{
        background: {tokens["scrollbar_track"]};
        height: 7px;
        border-radius: 3px;
        margin: 0px 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {tokens["scrollbar_handle"]};
        border-radius: 3px;
        min-width: 24px;
    }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: {tokens["scrollbar_handle_hover"]};
    }}
    QScrollBar::handle:vertical:pressed, QScrollBar::handle:horizontal:pressed {{
        background: {tokens["scrollbar_handle_pressed"]};
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

    if len(_STYLESHEET_CACHE) >= 16:
        _STYLESHEET_CACHE.pop(next(iter(_STYLESHEET_CACHE)), None)
    _STYLESHEET_CACHE[cache_key] = qss
    return qss


def _register_builtin_presets() -> None:
    from ui.themes.cyber_moe import CYBER_MOE_PRESET
    from ui.themes.midnight_amoled import MIDNIGHT_AMOLED_PRESET
    from ui.themes.neon_matrix import NEON_MATRIX_PRESET
    from ui.themes.ocean_cyan import OCEAN_CYAN_PRESET
    from ui.themes.sakura_bloom import SAKURA_BLOOM_PRESET

    THEME_PRESETS.update(
        {
            THEME_CYBER_MOE: CYBER_MOE_PRESET,
            THEME_MIDNIGHT_AMOLED: MIDNIGHT_AMOLED_PRESET,
            THEME_SAKURA_BLOOM: SAKURA_BLOOM_PRESET,
            THEME_NEON_MATRIX: NEON_MATRIX_PRESET,
            THEME_OCEAN_CYAN: OCEAN_CYAN_PRESET,
        }
    )
    apply_theme_palette(DEFAULT_THEME)


_register_builtin_presets()
