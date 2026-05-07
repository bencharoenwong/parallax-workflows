"""Color extraction (regex over text/CSS) and role assignment by frequency.

Public API:
  - ColorExtractor.extract_hex_colors(text) → list of {hex, confidence}
  - _normalize_hex / _is_pure_white / _is_dark_text_candidate / _is_neutral_grey
  - _assign_color_roles_by_frequency(colors_list) → role-keyed dict

Role assignment notes:
  Order-of-appearance assignment misroutes pure-white backgrounds to 'primary'.
  This module assigns by frequency, with white routed to background and the
  darkest dark color routed to text.
"""

import re
from collections import Counter
from typing import Any, Dict, List


class ColorExtractor:
    """Extract colors from text via pattern matching."""

    @staticmethod
    def extract_hex_colors(text: str) -> List[Dict[str, Any]]:
        """Find hex color patterns (#RGB, #RRGGBB, rgb(...)) in text.

        Returns: [{"hex": "#FF5733", "confidence": 0.95}, ...]
        """
        colors = []

        for match in re.finditer(r'#[0-9A-Fa-f]{6}\b', text):
            colors.append({
                "hex": match.group(0).upper(),
                "confidence": 0.95,
            })

        for match in re.finditer(r'#[0-9A-Fa-f]{3}(?![0-9A-Fa-f])\b', text):
            colors.append({
                "hex": match.group(0).upper(),
                "confidence": 0.95,
            })

        for match in re.finditer(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', text):
            r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
            hex_color = f"#{r:02X}{g:02X}{b:02X}"
            colors.append({
                "hex": hex_color,
                "confidence": 0.85,
            })

        return colors


def _normalize_hex(hex_val: str) -> str:
    """Expand 3-digit hex to 6-digit, uppercase. '#fff' → '#FFFFFF'."""
    h = hex_val.upper().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h


def _is_pure_white(h: str) -> bool:
    return _normalize_hex(h) == "#FFFFFF"


def _is_dark_text_candidate(h: str) -> bool:
    """True if the color is dark enough to be a body-text color (max channel < 80)."""
    h = _normalize_hex(h)
    if len(h) != 7:
        return False
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return max(r, g, b) < 80


def _is_neutral_grey(h: str) -> bool:
    """True if the color is a near-greyscale neutral (channels within 10) in the
    light-grey to dark-grey range. Excludes saturated brand colors.

    Upper bound 250 (not 230) so common off-white backgrounds like #F5F5F5,
    #FAFAFA, #F0F0F0, #EAEAEA are caught as neutrals instead of falling into
    the brand pool and getting routed to primary.
    """
    h = _normalize_hex(h)
    if len(h) != 7:
        return False
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    if max(r, g, b) - min(r, g, b) > 10:
        return False
    return 80 <= max(r, g, b) <= 250


def _assign_color_roles_by_frequency(colors_list: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Assign extracted hex colors to white-label brand roles by frequency.

    Routes pure-white → background, darkest-dark → text, then top-3 most-frequent
    saturated brand candidates (excluding neutral greys) → primary, secondary, accent.
    Confidence scales with occurrence count: 0.85 for ≥5, 0.75 for ≥2, 0.6 singleton.
    """
    hex_counts: Counter = Counter()
    for c in colors_list:
        hex_counts[_normalize_hex(c["hex"])] += 1

    role_colors: Dict[str, Dict[str, Any]] = {}

    for hex_val, _ in hex_counts.most_common():
        if _is_pure_white(hex_val):
            role_colors["background"] = {"hex": hex_val, "confidence": 0.85}
            break

    dark_candidates = [
        (h, count) for h, count in hex_counts.items() if _is_dark_text_candidate(h)
    ]
    if dark_candidates:
        def _max_channel(h: str) -> int:
            return max(int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))
        dark_candidates.sort(key=lambda hc: (_max_channel(hc[0]), -hc[1]))
        role_colors["text"] = {"hex": dark_candidates[0][0], "confidence": 0.7}

    brand_pool = [
        (h, count) for h, count in hex_counts.most_common()
        if not _is_pure_white(h)
        and not _is_dark_text_candidate(h)
        and not _is_neutral_grey(h)
    ]

    role_order = ["primary", "secondary", "accent"]
    for i, (hex_val, count) in enumerate(brand_pool[:3]):
        if count >= 5:
            confidence = 0.85
        elif count >= 2:
            confidence = 0.75
        else:
            confidence = 0.6
        role_colors[role_order[i]] = {"hex": hex_val, "confidence": confidence}

    return role_colors
