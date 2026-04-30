#!/usr/bin/env python3
"""Unit tests for white-label branding validators.

Tests ColorValidator, LogoValidator, and FontValidator classes.
All validators follow TDD pattern with failing tests first.

Run from skills/_parallax/white-label/:
    python3 -m pytest tests/test_validator.py -v
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

# Allow running tests: add parent (white-label/) to path
HERE = Path(__file__).parent
WHITE_LABEL_DIR = HERE.parent
sys.path.insert(0, str(WHITE_LABEL_DIR))

import validator  # noqa: E402


class TestColorValidator:
    """Tests for ColorValidator class."""

    def test_valid_6digit_hex(self) -> None:
        """Test valid 6-digit hex color."""
        assert validator.ColorValidator.is_valid_hex("#FFFFFF")
        assert validator.ColorValidator.is_valid_hex("#000000")
        assert validator.ColorValidator.is_valid_hex("#FF5733")
        assert validator.ColorValidator.is_valid_hex("#aabbcc")

    def test_valid_3digit_hex(self) -> None:
        """Test valid 3-digit hex color."""
        assert validator.ColorValidator.is_valid_hex("#FFF")
        assert validator.ColorValidator.is_valid_hex("#000")
        assert validator.ColorValidator.is_valid_hex("#F5C")

    def test_invalid_hex_bad_characters(self) -> None:
        """Test invalid hex with non-hex characters."""
        assert not validator.ColorValidator.is_valid_hex("#GGGGGG")
        assert not validator.ColorValidator.is_valid_hex("#12345Z")

    def test_invalid_hex_bad_length(self) -> None:
        """Test invalid hex with wrong length."""
        assert not validator.ColorValidator.is_valid_hex("#FFF00")
        assert not validator.ColorValidator.is_valid_hex("#FF")
        assert not validator.ColorValidator.is_valid_hex("")

    def test_invalid_hex_missing_hash(self) -> None:
        """Test invalid hex without leading #."""
        assert not validator.ColorValidator.is_valid_hex("FFFFFF")
        assert not validator.ColorValidator.is_valid_hex("FFF")

    def test_hex_to_rgb_6digit(self) -> None:
        """Test hex to RGB conversion for 6-digit hex."""
        assert validator.ColorValidator.hex_to_rgb("#FFFFFF") == (255, 255, 255)
        assert validator.ColorValidator.hex_to_rgb("#000000") == (0, 0, 0)
        assert validator.ColorValidator.hex_to_rgb("#FF5733") == (255, 87, 51)

    def test_hex_to_rgb_3digit(self) -> None:
        """Test hex to RGB conversion for 3-digit hex (expands to 6-digit)."""
        assert validator.ColorValidator.hex_to_rgb("#FFF") == (255, 255, 255)
        assert validator.ColorValidator.hex_to_rgb("#000") == (0, 0, 0)
        assert validator.ColorValidator.hex_to_rgb("#F5C") == (255, 85, 204)

    def test_hex_to_rgb_lowercase(self) -> None:
        """Test hex to RGB conversion with lowercase."""
        assert validator.ColorValidator.hex_to_rgb("#ffffff") == (255, 255, 255)
        assert validator.ColorValidator.hex_to_rgb("#ff5733") == (255, 87, 51)

    def test_wcag_contrast_ratio_high(self) -> None:
        """Test WCAG contrast ratio for high-contrast pair."""
        # Black text on white background is 21:1
        ratio = validator.ColorValidator.wcag_contrast_ratio("#000000", "#FFFFFF")
        assert ratio == pytest.approx(21.0, rel=0.1)

    def test_wcag_contrast_ratio_low(self) -> None:
        """Test WCAG contrast ratio for low-contrast pair."""
        # White on white is 1:1
        ratio = validator.ColorValidator.wcag_contrast_ratio("#FFFFFF", "#FFFFFF")
        assert ratio == pytest.approx(1.0, rel=0.01)

    def test_wcag_contrast_ratio_medium(self) -> None:
        """Test WCAG contrast ratio for medium-contrast pair."""
        # Dark gray on light gray
        ratio = validator.ColorValidator.wcag_contrast_ratio("#333333", "#CCCCCC")
        assert ratio > 1.0
        assert ratio < 21.0

    def test_validate_text_contrast_pass(self) -> None:
        """Test validate_text_contrast returns PASS for high contrast."""
        result = validator.ColorValidator.validate_text_contrast("#000000", "#FFFFFF")
        assert result["status"] == "pass"
        assert result["ratio"] >= 4.5
        assert isinstance(result["ratio"], float)

    def test_validate_text_contrast_warn(self) -> None:
        """Test validate_text_contrast returns WARN for medium contrast."""
        # #888888 on #FFFFFF should be warn (3.0-4.5 range)
        result = validator.ColorValidator.validate_text_contrast("#888888", "#FFFFFF")
        assert result["status"] == "warn"
        assert 3.0 <= result["ratio"] < 4.5
        assert "recommendation" in result

    def test_validate_text_contrast_fail(self) -> None:
        """Test validate_text_contrast returns FAIL for low contrast."""
        # Light color on light background
        result = validator.ColorValidator.validate_text_contrast("#EEEEEE", "#FFFFFF")
        assert result["status"] == "fail"
        assert result["ratio"] < 3.0
        assert "recommendation" in result


class TestLogoValidator:
    """Tests for LogoValidator class."""

    def test_validate_logo_file_not_found(self) -> None:
        """Test validation fails when logo file doesn't exist."""
        result = validator.LogoValidator.validate_logo("/nonexistent/path/logo.png")
        assert result["status"] == "fail"
        assert "not found" in result["error"].lower() or "does not exist" in result["error"].lower()

    def test_validate_logo_valid_png(self) -> None:
        """Test validation passes for valid PNG with sufficient dimensions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple PNG file (300x300)
            try:
                from PIL import Image
                img = Image.new("RGB", (300, 300), color="red")
                logo_path = Path(tmpdir) / "logo.png"
                img.save(logo_path)

                result = validator.LogoValidator.validate_logo(str(logo_path))
                assert result["status"] == "pass"
                assert result["dimensions"] == (300, 300)
                assert result["format"] == "PNG"
            except ImportError:
                pytest.skip("PIL not installed")

    def test_validate_logo_dimensions_too_small(self) -> None:
        """Test validation warns when logo dimensions are below 200x200."""
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                from PIL import Image
                img = Image.new("RGB", (100, 100), color="blue")
                logo_path = Path(tmpdir) / "logo.png"
                img.save(logo_path)

                result = validator.LogoValidator.validate_logo(str(logo_path))
                assert result["status"] == "warn"
                assert result["dimensions"] == (100, 100)
                assert "pixelation" in result.get("warning", "").lower()
            except ImportError:
                pytest.skip("PIL not installed")

    def test_validate_logo_invalid_format(self) -> None:
        """Test validation fails for unsupported file format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a text file with image extension
            invalid_logo = Path(tmpdir) / "logo.txt"
            invalid_logo.write_text("not an image")

            result = validator.LogoValidator.validate_logo(str(invalid_logo))
            assert result["status"] == "fail"
            assert "format" in result["error"].lower() or "invalid" in result["error"].lower()

    def test_validate_logo_supported_formats(self) -> None:
        """Test that common image formats are supported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                from PIL import Image
                supported_formats = ["png", "jpg", "jpeg", "svg", "gif"]

                for fmt in ["png", "jpg", "gif"]:  # Test supported PIL formats
                    img = Image.new("RGB", (250, 250), color="green")
                    logo_path = Path(tmpdir) / f"logo.{fmt}"
                    img.save(logo_path)

                    result = validator.LogoValidator.validate_logo(str(logo_path))
                    # Should not fail on format
                    assert "unsupported format" not in result.get("error", "").lower()
            except ImportError:
                pytest.skip("PIL not installed")

    def test_validate_logo_file_size_limit(self) -> None:
        """Test that file size > 5MB fails validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake 6MB file
            oversized_logo = Path(tmpdir) / "oversized.png"
            oversized_logo.write_bytes(b"x" * (6 * 1024 * 1024 + 1))

            result = validator.LogoValidator.validate_logo(str(oversized_logo))
            assert result["status"] == "fail"
            assert "size" in result["error"].lower()


class TestFontValidator:
    """Tests for FontValidator class."""

    def test_get_system_fonts_returns_set(self) -> None:
        """Test that get_system_fonts returns a set of font names."""
        fonts = validator.FontValidator.get_system_fonts()
        assert isinstance(fonts, set)
        assert len(fonts) > 0

    def test_validate_font_common_serif(self) -> None:
        """Test validation of common serif font (likely to exist)."""
        result = validator.FontValidator.validate_font("Times New Roman")
        assert "status" in result
        assert isinstance(result, dict)

    def test_validate_font_common_sans_serif(self) -> None:
        """Test validation of common sans-serif font (likely to exist)."""
        result = validator.FontValidator.validate_font("Arial")
        assert "status" in result
        assert isinstance(result, dict)

    def test_validate_font_common_monospace(self) -> None:
        """Test validation of common monospace font (likely to exist)."""
        result = validator.FontValidator.validate_font("Courier New")
        assert "status" in result
        assert isinstance(result, dict)

    def test_validate_font_nonexistent_returns_fallback(self) -> None:
        """Test that nonexistent font returns fallback recommendation."""
        result = validator.FontValidator.validate_font("ImpossiblyWeirdFontName12345")
        assert "fallback" in result
        assert result["fallback"] is not None
        assert isinstance(result["fallback"], str)

    def test_suggest_fallback_serif(self) -> None:
        """Test fallback suggestion for serif fonts."""
        fallback = validator.FontValidator._suggest_fallback("WeirdSerifFont")
        # Should suggest a serif fallback (check if it's Georgia or similar serif)
        assert fallback in ["Georgia", "Times New Roman", "Garamond"]

    def test_suggest_fallback_monospace(self) -> None:
        """Test fallback suggestion for monospace fonts."""
        fallback = validator.FontValidator._suggest_fallback("WeirdMonoFont")
        # Should suggest a monospace fallback
        assert fallback in ["Courier New", "Courier", "Menlo", "Monaco"]

    def test_suggest_fallback_default(self) -> None:
        """Test default fallback for unclassified fonts."""
        fallback = validator.FontValidator._suggest_fallback("CompletelyRandomName")
        # Should suggest a reasonable default
        assert fallback is not None
        assert isinstance(fallback, str)
        assert len(fallback) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
