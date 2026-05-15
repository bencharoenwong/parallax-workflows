import pytest
import yaml
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import loader

def test_v1_file_returns_legacy_colors_accent(tmp_path, monkeypatch):
    fixture_path = Path(__file__).parent / "fixtures" / "legacy_v1_config.yaml"
    test_config = tmp_path / "config.yaml"
    test_config.write_text(fixture_path.read_text())
    
    monkeypatch.setattr(loader, "_CONFIG_PATH", test_config)
    monkeypatch.setattr(loader, "_SCHEMA_PATH", Path(__file__).parent.parent / "schema.yaml")
    
    result = loader.load_client_branding()
    
    assert result["error"] is None or "logo_missing" in result["error"]
    assert result["colors"]["accent"] == "#FF6600"
    assert result["fonts"]["header"] == "Inter"

def test_v2_file_returns_legacy_keys_via_tertiary(tmp_path, monkeypatch):
    test_config = tmp_path / "config.yaml"
    
    # Synthesize v2 dict
    v2_dict = {
        "metadata": {
            "schema_version": 2,
            "client_name": "Test Client",
            "extracted_at": "2026-04-30T00:00:00Z",
            "source": {"type": "url", "reference": "https://example.com", "confidence": 0.9}
        },
        "branding": {
            "colors": {
                "primary": "#001122",
                "secondary": "#334455",
                "tertiary": "#0066CC", # accent value
                "neutral": "#FFFFFF",  # background value
            },
            "typography": {
                "h1": {"fontFamily": "Inter"},
                "body-md": {"fontFamily": "Source Sans Pro"},
                "code": {"fontFamily": "JetBrains Mono"}
            },
            "components": {
                "body-text": {
                    "backgroundColor": "{colors.neutral}",
                    "textColor": "#222222" # text value
                }
            },
            "logos": {
                "primary": "~/.parallax/client-branding/primary-logo.png",
                "favicon": "~/.parallax/client-branding/favicon.ico"
            }
        },
        "confidence_scores": {}
    }
    
    test_config.write_text(yaml.dump(v2_dict))
    
    monkeypatch.setattr(loader, "_CONFIG_PATH", test_config)
    monkeypatch.setattr(loader, "_SCHEMA_PATH", Path(__file__).parent.parent / "schema.yaml")
    
    result = loader.load_client_branding()
    
    assert result["error"] is None or "logo_missing" in result["error"]
    assert result["colors"]["accent"] == "#0066CC"
    assert result["colors"]["background"] == "#FFFFFF"
    assert result["colors"]["text"] == "#222222"
    
    assert result["fonts"]["header"] == "Inter"
    assert result["fonts"]["body"] == "Source Sans Pro"
    assert result["fonts"]["monospace"] == "JetBrains Mono"
    
    assert "typography" in result
    assert result["typography"]["h1"]["fontFamily"] == "Inter"

def test_clear_archives_both_files(tmp_path, monkeypatch):
    # Test `archive_legacy_config` directly since `--clear` orchestration lives in SKILL.md.
    test_config = tmp_path / "config.yaml"
    test_config.write_text("dummy")
    
    design_md = tmp_path / "DESIGN.md"
    design_md.write_text("dummy design")
    
    archive_path = loader.archive_legacy_config(test_config)
    
    assert archive_path.exists()
    assert archive_path.name == "config.yaml"
    assert archive_path.parent.name.endswith("-pre-v2-migration")
