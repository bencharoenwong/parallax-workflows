import pytest
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from extract import (
    ColorExtractor,
    LogoExtractor,
    FontExtractor,
    extract_from_url,
    extract_from_pdf,
    extract_from_wizard,
)


class TestColorExtractor:
    """Test color extraction from text."""

    def test_extract_hex_colors_6digit(self):
        text = "Primary color: #FF5733, secondary: #3498DB"
        result = ColorExtractor.extract_hex_colors(text)
        assert len(result) == 2
        assert result[0]["hex"] == "#FF5733"
        assert result[0]["confidence"] == 0.95
        assert result[1]["hex"] == "#3498DB"

    def test_extract_hex_colors_3digit(self):
        text = "Color: #FFF"
        result = ColorExtractor.extract_hex_colors(text)
        assert len(result) == 1
        assert result[0]["hex"] == "#FFF"
        assert result[0]["confidence"] == 0.95

    def test_extract_hex_colors_rgb(self):
        text = "Background: rgb(255, 87, 51)"
        result = ColorExtractor.extract_hex_colors(text)
        assert len(result) == 1
        assert result[0]["hex"] == "#FF5733"
        assert result[0]["confidence"] == 0.85

    def test_extract_hex_colors_empty(self):
        text = "No colors here"
        result = ColorExtractor.extract_hex_colors(text)
        assert result == []


class TestLogoExtractor:
    """Test logo extraction from text."""

    def test_extract_logo_urls_markdown(self):
        text = "![logo](https://example.com/logo.png)"
        result = LogoExtractor.extract_logo_urls(text)
        assert len(result) == 1
        assert result[0]["url"] == "https://example.com/logo.png"
        assert result[0]["alt_text"] == "logo"
        assert 0.6 <= result[0]["confidence"] <= 0.95

    def test_extract_logo_urls_heuristic_brand(self):
        text = "Logo: https://example.com/brand-logo.png"
        result = LogoExtractor.extract_logo_urls(text)
        assert len(result) == 1
        assert result[0]["confidence"] >= 0.85  # Higher confidence for "brand"

    def test_extract_logo_urls_low_confidence(self):
        text = "Image: https://example.com/image.jpg"
        result = LogoExtractor.extract_logo_urls(text)
        assert len(result) == 1
        assert result[0]["confidence"] == 0.6

    def test_extract_logo_paths_local(self):
        text = "Logo at /assets/logo.png"
        result = LogoExtractor.extract_logo_paths(text)
        assert len(result) == 1
        assert result[0]["path"] == "/assets/logo.png"
        assert result[0]["confidence"] == 0.8

    def test_extract_logo_paths_not_found(self):
        text = "No paths here"
        result = LogoExtractor.extract_logo_paths(text)
        assert result == []

    def test_extract_logo_urls_empty(self):
        text = ""
        result = LogoExtractor.extract_logo_urls(text)
        assert result == []


class TestFontExtractor:
    """Test font extraction from CSS and text."""

    def test_extract_fonts_css_header(self):
        css = "h1, h2, h3 { font-family: Helvetica; }"
        result = FontExtractor.extract_fonts_from_css(css)
        assert len(result) >= 1
        assert any(f["font_name"] == "Helvetica" and f["usage"] == "header" for f in result)
        assert any(f["confidence"] >= 0.8 for f in result)

    def test_extract_fonts_css_body(self):
        css = "body, p { font-family: Georgia; }"
        result = FontExtractor.extract_fonts_from_css(css)
        assert len(result) >= 1
        assert any(f["font_name"] == "Georgia" and f["usage"] == "body" for f in result)

    def test_extract_fonts_pdf_text(self):
        text = "Our headers use Roboto, body uses Open Sans"
        result = FontExtractor.extract_fonts_from_pdf_text(text)
        assert len(result) >= 1
        # Should identify fonts mentioned in text

    def test_extract_fonts_empty(self):
        result = FontExtractor.extract_fonts_from_css("")
        assert result == []


class TestExtractFromUrl:
    """Test URL-based extraction."""

    def test_extract_from_url_returns_dict_shape(self):
        # Passes an invalid/unreachable URL — extract_from_url must degrade gracefully
        result = extract_from_url("https://0.0.0.0")
        assert isinstance(result, dict)
        required_keys = ["colors", "logos", "fonts", "source", "extracted_at", "confidence_scores"]
        assert all(k in result for k in required_keys), f"Missing keys: {set(required_keys) - set(result.keys())}"

    def test_extract_from_url_confidence_scores(self):
        result = extract_from_url("https://0.0.0.0")
        assert isinstance(result["confidence_scores"], dict)

    def test_extract_from_url_sets_source_type(self):
        result = extract_from_url("https://0.0.0.0")
        assert result["source"]["type"] == "url"


class TestExtractFromPdf:
    """Test PDF-based extraction."""

    def test_extract_from_pdf_missing_file(self):
        # Spec requires graceful degradation (no exception) for missing files
        result = extract_from_pdf("/nonexistent/path/that/does/not/exist.pdf")
        assert isinstance(result, dict), "Must return dict, not raise"
        assert "error" in result, "Must include 'error' key on missing file"
        assert result["source"]["type"] == "pdf"

    def test_extract_from_pdf_returns_dict_shape(self):
        # Pass a missing file — graceful degradation still returns correct shape
        result = extract_from_pdf("/nonexistent/path/that/does/not/exist.pdf")
        required_keys = ["colors", "logos", "fonts", "source", "extracted_at", "confidence_scores"]
        assert all(k in result for k in required_keys), f"Missing keys: {set(required_keys) - set(result.keys())}"


class TestExtractFromWizard:
    """Test wizard intake."""

    def test_extract_from_wizard_signature(self):
        # Verify function exists and is callable
        assert callable(extract_from_wizard)

    def test_extract_from_wizard_returns_dict_shape(self):
        result = extract_from_wizard()
        required_keys = ["colors", "logos", "fonts", "source", "extracted_at", "confidence_scores"]
        assert all(k in result for k in required_keys), f"Missing keys: {set(required_keys) - set(result.keys())}"
        assert result["source"]["type"] == "wizard"
        assert "reference" in result["source"], "source must include 'reference' key for schema consistency"
