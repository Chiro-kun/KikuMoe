"""
Midnight AMOLED theme preset for KikuMoe 2.0.0.
Pure #000000 black surfaces engineered for OLED/AMOLED displays with neon pink accents.
"""

from typing import Dict

MIDNIGHT_AMOLED_PRESET: Dict[str, str] = {
    "i18n_key": "theme_midnight_amoled",
    "default_accent": "#ff1e7a",
    "bg_main": "#000000",
    "bg_canvas": "#000000",
    "bg_dialog": "#000000",
    "bg_embedded_panel": "rgba(0, 0, 0, 0.97)",
    "bg_popover": "#050508",
    "bg_surface": "#08080c",
    "bg_surface_elevated": "#101016",
    "bg_footer": "#050508",
    "bg_terminal": "#000000",
    "bg_subtle": "#121218",
    "bg_glass": "rgba(8, 8, 12, 0.85)",
    "bg_card_glass": "rgba(7, 7, 10, 0.90)",
    "bg_console_top": "rgba(14, 14, 20, 0.90)",
    "bg_console_bottom": "rgba(0, 0, 0, 0.97)",
    "bg_footer_pill": "rgba(10, 10, 14, 0.92)",
    "bg_pill_idle": "#060609",
    "bg_pill_active": "#111118",
    "bg_titlebar": "rgba(0, 0, 0, 0.72)",
    "nebula_secondary": "#7c1fff",
    "border_subtle": "rgba(255, 255, 255, 0.10)",
    "border_card": "rgba(255, 255, 255, 0.15)",
    "text_primary": "#ffffff",
    "text_secondary": "#9ca0b0",
    "text_muted": "#606473",
    "scrollbar_track": "rgba(255, 255, 255, 0.05)",
    "lyrics_background": "transparent",
    "lyrics_border": "transparent",
    "lyrics_skeleton_base": "#1affffff",
    "lyrics_skeleton_shine": "#4dffffff",
    "station_glass_overlay": "#d8000000",
    "station_glass_fallback": "#f5060609",
    "station_glass_rim": "#2effffff",
    "status_online": "#00e676",
    "status_warning": "#ffab00",
    "status_error": "#ff5252",
}
