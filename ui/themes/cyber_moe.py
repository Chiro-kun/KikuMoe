"""
Cyber Moe default theme preset for KikuMoe 2.0.0.
Dark violet glassmorphism paired with signature neon pink (#ec186c) accents.
Also re-exports shared theme engine symbols for backward compatibility.
"""

from typing import Dict

CYBER_MOE_PRESET: Dict[str, str] = {
    "i18n_key": "theme_cyber_moe",
    "default_accent": "#ec186c",
    "bg_main": "#0c0d14",
    "bg_canvas": "#0b0c14",
    "bg_dialog": "#0c0e17",
    "bg_embedded_panel": "rgba(12, 14, 22, 0.96)",
    "bg_popover": "#141624",
    "bg_surface": "#151826",
    "bg_surface_elevated": "#1a1d2e",
    "bg_footer": "#121523",
    "bg_terminal": "#080a11",
    "bg_subtle": "#1f2235",
    "bg_glass": "rgba(20, 22, 34, 0.75)",
    "bg_card_glass": "rgba(18, 20, 32, 0.82)",
    "bg_console_top": "rgba(25, 28, 44, 0.84)",
    "bg_console_bottom": "rgba(13, 15, 24, 0.92)",
    "bg_footer_pill": "rgba(20, 23, 36, 0.86)",
    "bg_pill_idle": "#0e101a",
    "bg_pill_active": "#181a28",
    "bg_titlebar": "rgba(8, 9, 15, 0.54)",
    "nebula_secondary": "#6e32dc",
    "border_subtle": "rgba(255, 255, 255, 0.08)",
    "border_card": "rgba(255, 255, 255, 0.12)",
    "text_primary": "#ffffff",
    "text_secondary": "#a0a5b8",
    "text_muted": "#64687d",
    "scrollbar_track": "rgba(255, 255, 255, 0.04)",
    "lyrics_background": "transparent",
    "lyrics_border": "transparent",
    "lyrics_skeleton_base": "#1affffff",
    "lyrics_skeleton_shine": "#4dffffff",
    "station_glass_overlay": "#c00c0e18",
    "station_glass_fallback": "#f0141622",
    "station_glass_rim": "#30ffffff",
    "status_online": "#00e676",
    "status_warning": "#ffab00",
    "status_error": "#ff5252",
}

from ui.themes.engine import (  # noqa: E402
    PALETTE,
    THEME_ORDER,
    THEME_PRESETS,
    accent_qcolor,
    apply_theme_palette,
    derive_accent_tokens,
    get_cyber_moe_stylesheet,
    get_preset_default_accent,
    is_valid_hex_color,
    normalize_hex_color,
    resolve_theme_and_accent,
    surface_qcolor,
)

__all__ = [
    "CYBER_MOE_PRESET",
    "PALETTE",
    "THEME_ORDER",
    "THEME_PRESETS",
    "accent_qcolor",
    "apply_theme_palette",
    "derive_accent_tokens",
    "get_cyber_moe_stylesheet",
    "get_preset_default_accent",
    "is_valid_hex_color",
    "normalize_hex_color",
    "resolve_theme_and_accent",
    "surface_qcolor",
]
