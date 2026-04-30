#!/usr/bin/env python3
"""White-label branding validators for Parallax client configurations.

Provides:
  - ColorValidator: hex validation, RGB conversion, WCAG contrast analysis
  - LogoValidator: file existence, dimensions, format, size limits
  - FontValidator: system font detection, fallback suggestions

All validators follow WCAG 2.0 accessibility standards for text contrast.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any


class ColorValidator:
    """Validator for color values in hex format with WCAG contrast analysis."""

    @staticmethod
    def is_valid_hex(hex_color: str) -> bool:
        """Validate hex color format (6-digit or 3-digit with leading #).

        Args:
            hex_color: Color string, e.g., "#FFFFFF" or "#FFF"

        Returns:
            bool: True if valid hex color, False otherwise
        """
        if not hex_color or not isinstance(hex_color, str):
            return False
        # Match #RRGGBB or #RGB format
        pattern = r"^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$"
        return bool(re.match(pattern, hex_color))

    @staticmethod
    def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        """Convert hex color to RGB tuple.

        Args:
            hex_color: Color string in hex format, e.g., "#FFFFFF" or "#FFF"

        Returns:
            tuple: (R, G, B) with values 0-255

        Raises:
            ValueError: If hex_color is not a valid hex format
        """
        if not ColorValidator.is_valid_hex(hex_color):
            raise ValueError(f"Invalid hex color: {hex_color}")

        hex_color = hex_color.lstrip("#").upper()

        # Expand 3-digit to 6-digit
        if len(hex_color) == 3:
            hex_color = "".join([c * 2 for c in hex_color])

        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        return (r, g, b)

    @staticmethod
    def _relative_luminance(rgb: tuple[int, int, int]) -> float:
        """Calculate relative luminance per WCAG 2.0 formula.

        Args:
            rgb: (R, G, B) tuple with values 0-255

        Returns:
            float: Relative luminance (0.0-1.0)
        """
        r, g, b = [x / 255.0 for x in rgb]
        r = r / 12.92 if r <= 0.04045 else ((r + 0.055) / 1.055) ** 2.4
        g = g / 12.92 if g <= 0.04045 else ((g + 0.055) / 1.055) ** 2.4
        b = b / 12.92 if b <= 0.04045 else ((b + 0.055) / 1.055) ** 2.4
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    @staticmethod
    def wcag_contrast_ratio(fg_hex: str, bg_hex: str) -> float:
        """Calculate WCAG 2.0 contrast ratio between two colors.

        Formula: (L1 + 0.05) / (L2 + 0.05) where L1 >= L2
        Ratio range: 1.0 (no contrast) to 21.0 (maximum contrast)

        Args:
            fg_hex: Foreground color in hex format
            bg_hex: Background color in hex format

        Returns:
            float: Contrast ratio (1.0-21.0)
        """
        fg_rgb = ColorValidator.hex_to_rgb(fg_hex)
        bg_rgb = ColorValidator.hex_to_rgb(bg_hex)

        fg_lum = ColorValidator._relative_luminance(fg_rgb)
        bg_lum = ColorValidator._relative_luminance(bg_rgb)

        # Ensure lighter color is L1
        l1 = max(fg_lum, bg_lum)
        l2 = min(fg_lum, bg_lum)

        return (l1 + 0.05) / (l2 + 0.05)

    @staticmethod
    def validate_text_contrast(
        text_color: str, bg_color: str
    ) -> dict[str, Any]:
        """Validate WCAG text contrast between text and background colors.

        Pass: ratio >= 4.5:1 (WCAG AA for normal text)
        Warn: 3.0 <= ratio < 4.5 (WCAG AAA for large text)
        Fail: ratio < 3.0 (insufficient contrast)

        Args:
            text_color: Text color in hex format
            bg_color: Background color in hex format

        Returns:
            dict: {
                'status': 'pass' | 'warn' | 'fail',
                'ratio': float (contrast ratio),
                'recommendation': str (improvement advice if not pass)
            }
        """
        ratio = ColorValidator.wcag_contrast_ratio(text_color, bg_color)

        if ratio >= 4.5:
            return {
                "status": "pass",
                "ratio": round(ratio, 2),
                "recommendation": None,
            }
        elif ratio >= 3.0:
            return {
                "status": "warn",
                "ratio": ratio,
                "recommendation": f"Contrast ratio {ratio:.2f}:1 is acceptable for large text only. Consider increasing contrast for small text.",
            }
        else:
            return {
                "status": "fail",
                "ratio": ratio,
                "recommendation": f"Contrast ratio {ratio:.2f}:1 is insufficient. Increase contrast by using darker text or lighter background.",
            }


class LogoValidator:
    """Validator for logo files: existence, format, dimensions, size."""

    SUPPORTED_FORMATS = {"png", "jpg", "jpeg", "svg", "gif"}
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    MIN_DIMENSIONS = (200, 200)

    @staticmethod
    def validate_logo(file_path: str) -> dict[str, Any]:
        """Validate logo file.

        Checks:
          - File exists
          - Format is supported (png, jpg, jpeg, svg, gif)
          - File size <= 5MB
          - Dimensions >= 200x200px (warn if smaller)

        Args:
            file_path: Path to logo file

        Returns:
            dict: {
                'status': 'pass' | 'warn' | 'fail',
                'path': str,
                'format': str (uppercase),
                'dimensions': tuple (width, height) if applicable,
                'file_size': int (bytes),
                'error': str (if fail),
                'warning': str (if warn)
            }
        """
        path = Path(file_path)

        # Check file exists
        if not path.exists():
            return {
                "status": "fail",
                "path": str(path),
                "error": f"Logo file not found: {path}",
            }

        # Check format
        fmt = path.suffix.lstrip(".").lower()
        if fmt not in LogoValidator.SUPPORTED_FORMATS:
            return {
                "status": "fail",
                "path": str(path),
                "format": fmt.upper(),
                "error": f"Unsupported format: {fmt}. Supported formats: {', '.join(LogoValidator.SUPPORTED_FORMATS)}",
            }

        # Check file size
        file_size = path.stat().st_size
        if file_size > LogoValidator.MAX_FILE_SIZE:
            return {
                "status": "fail",
                "path": str(path),
                "format": fmt.upper(),
                "file_size": file_size,
                "error": f"File size {file_size / 1024 / 1024:.2f}MB exceeds 5MB limit",
            }

        # SVG: PIL cannot open it; skip dimension check, return pass with note
        if fmt == "svg":
            return {
                "status": "pass",
                "path": str(path),
                "format": "SVG",
                "dimensions": None,
                "file_size": file_size,
                "note": "SVG format: dimension check skipped (PIL does not support SVG)",
            }

        # Check dimensions (requires PIL)
        try:
            from PIL import Image

            with Image.open(path) as img:
                dimensions = img.size
            result: dict[str, Any] = {
                "status": "pass",
                "path": str(path),
                "format": fmt.upper(),
                "dimensions": dimensions,
                "file_size": file_size,
            }

            # Warn if dimensions are too small
            if dimensions[0] < LogoValidator.MIN_DIMENSIONS[0] or dimensions[1] < LogoValidator.MIN_DIMENSIONS[1]:
                result["status"] = "warn"
                result["warning"] = f"Dimensions {dimensions[0]}x{dimensions[1]} are below recommended minimum {LogoValidator.MIN_DIMENSIONS[0]}x{LogoValidator.MIN_DIMENSIONS[1]}. May cause pixelation at larger sizes."

            return result
        except ImportError:
            # PIL not available; return pass with unknown dimensions
            return {
                "status": "pass",
                "path": str(path),
                "format": fmt.upper(),
                "file_size": file_size,
                "note": "PIL not available; dimensions not checked",
            }
        except Exception as e:
            return {
                "status": "fail",
                "path": str(path),
                "format": fmt.upper(),
                "file_size": file_size,
                "error": f"Failed to read image: {str(e)}",
            }


class FontValidator:
    """Validator for font availability and fallback suggestions."""

    _SYSTEM_FONTS_CACHE: set[str] | None = None
    _FALLBACK_FONTS: set[str] = {
        "Arial",
        "Helvetica",
        "Times New Roman",
        "Courier New",
        "Georgia",
        "Verdana",
    }

    @staticmethod
    def get_system_fonts() -> set[str]:
        """Get set of installed system fonts.

        Caches result after first call. Uses matplotlib for cross-platform
        font detection.

        Returns:
            set: Font names available on the system
        """
        if FontValidator._SYSTEM_FONTS_CACHE is not None:
            return FontValidator._SYSTEM_FONTS_CACHE

        try:
            import matplotlib.font_manager as fm

            fonts = {Path(font).stem for font in fm.findSystemFonts()}
            FontValidator._SYSTEM_FONTS_CACHE = fonts
            return fonts
        except (ImportError, Exception):
            # Fallback: common fonts that exist on most systems
            FontValidator._SYSTEM_FONTS_CACHE = FontValidator._FALLBACK_FONTS
            return FontValidator._SYSTEM_FONTS_CACHE

    @staticmethod
    def _suggest_fallback(font_name: str) -> str:
        """Suggest a fallback font based on font type heuristics.

        Args:
            font_name: Original font name

        Returns:
            str: Recommended fallback font name
        """
        font_lower = font_name.lower()

        # Monospace heuristics
        if any(x in font_lower for x in ["mono", "courier", "console", "code"]):
            return "Courier New"

        # Serif heuristics
        if any(x in font_lower for x in ["serif", "times", "georgia", "garamond"]):
            return "Georgia"

        # Default: sans-serif
        return "Helvetica"

    @staticmethod
    def validate_font(font_name: str) -> dict[str, Any]:
        """Validate font availability on the system.

        Args:
            font_name: Font name to validate

        Returns:
            dict: {
                'status': 'pass' | 'warn' | 'fail',
                'font_name': str,
                'installed': bool,
                'fallback': str (if not installed)
            }
        """
        system_fonts = FontValidator.get_system_fonts()

        # Exact match
        if font_name in system_fonts:
            return {
                "status": "pass",
                "font_name": font_name,
                "installed": True,
            }

        # Case-insensitive match
        font_lower = font_name.lower()
        for sys_font in system_fonts:
            if sys_font.lower() == font_lower:
                return {
                    "status": "pass",
                    "font_name": font_name,
                    "installed": True,
                    "matched_as": sys_font,
                }

        # Not found; suggest fallback
        fallback = FontValidator._suggest_fallback(font_name)
        result: dict = {
            "status": "warn",
            "font_name": font_name,
            "installed": False,
            "fallback": fallback,
        }
        # Signal degraded detection mode (matplotlib unavailable)
        if system_fonts is FontValidator._FALLBACK_FONTS:
            result["detection"] = "degraded"
            result["note"] = "Font detection unavailable (matplotlib not installed); result may be inaccurate"
        return result
