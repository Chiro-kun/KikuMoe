"""
Modular Theme Presets & Dynamic Custom Accent Engine for KikuMoe 2.0.0.
"""

from ui.themes.cyber_moe import CYBER_MOE_PRESET
from ui.themes.engine import (
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
from ui.themes.midnight_amoled import MIDNIGHT_AMOLED_PRESET
from ui.themes.neon_matrix import NEON_MATRIX_PRESET
from ui.themes.ocean_cyan import OCEAN_CYAN_PRESET
from ui.themes.sakura_bloom import SAKURA_BLOOM_PRESET

__all__ = [
    "CYBER_MOE_PRESET",
    "MIDNIGHT_AMOLED_PRESET",
    "NEON_MATRIX_PRESET",
    "OCEAN_CYAN_PRESET",
    "PALETTE",
    "SAKURA_BLOOM_PRESET",
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
