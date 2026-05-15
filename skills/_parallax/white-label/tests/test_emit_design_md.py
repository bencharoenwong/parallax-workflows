import pytest
import yaml
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from emit_design_md import emit_design_md

def test_minimal_valid_frontmatter():
    draft = {
        "colors": {
            "primary": {"hex": "#FF0000"}
        }
    }
    out = emit_design_md(draft, client_name="Test", extracted_at="2026-01-01", source_refs=[])
    assert "---" in out
    parts = out.split("---")
    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter["colors"]["primary"] == "#FF0000"

def test_all_8_sections_in_order():
    draft = {}
    out = emit_design_md(draft, client_name="Test", extracted_at="2026-01-01", source_refs=["ref1"])
    sections = [
        "## Overview",
        "## Colors",
        "## Typography",
        "## Layout",
        "## Elevation & Depth",
        "## Shapes",
        "## Components",
        "## Do's and Don'ts"
    ]
    last_idx = -1
    for s in sections:
        idx = out.find(s)
        assert idx > last_idx
        last_idx = idx

def test_accent_tertiary_rename():
    draft = {
        "colors": {
            "accent": {"hex": "#ABCDEF"}
        }
    }
    out = emit_design_md(draft, client_name="Test", extracted_at="2026-01-01", source_refs=[])
    frontmatter = yaml.safe_load(out.split("---")[1])
    assert frontmatter["colors"]["tertiary"] == "#ABCDEF"
    assert "accent" not in frontmatter["colors"]

def test_components_body_text_wiring():
    draft = {
        "colors": {
            "background": {"hex": "#FFFFFF"},
            "text": {"hex": "#000000"}
        }
    }
    out = emit_design_md(draft, client_name="Test", extracted_at="2026-01-01", source_refs=[])
    frontmatter = yaml.safe_load(out.split("---")[1])
    assert frontmatter["colors"]["neutral"] == "#FFFFFF"
    assert frontmatter["components"]["body-text"]["backgroundColor"] == "{colors.neutral}"
    assert frontmatter["components"]["body-text"]["textColor"] == "#000000"

def test_omitting_missing_tokens():
    draft = {
        "colors": {
            "primary": {"hex": "#111111"}
        }
    }
    out = emit_design_md(draft, client_name="Test", extracted_at="2026-01-01", source_refs=[])
    frontmatter = yaml.safe_load(out.split("---")[1])
    assert "spacing" not in frontmatter
    assert "rounded" not in frontmatter
    assert "typography" not in frontmatter
    assert "components" not in frontmatter

def test_determinism_across_two_calls():
    draft = {
        "colors": {
            "primary": {"hex": "#111111"},
            "background": {"hex": "#FFFFFF"}
        },
        "spacing": {"xs": "4px", "sm": "8px"}
    }
    out1 = emit_design_md(draft, client_name="Test", extracted_at="2026-01-01", source_refs=["ref1"])
    out2 = emit_design_md(draft, client_name="Test", extracted_at="2026-01-01", source_refs=["ref1"])
    assert out1 == out2

def test_invalid_hex_raises_value_error():
    draft = {
        "colors": {
            "primary": {"hex": "invalid"}
        }
    }
    with pytest.raises(ValueError, match="invalid hex at colors.primary: invalid"):
        emit_design_md(draft, client_name="Test", extracted_at="2026-01-01", source_refs=[])
