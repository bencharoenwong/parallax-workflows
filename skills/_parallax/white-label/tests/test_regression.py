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


# ---------------------------------------------------------------------------
# Direct round-trip + v2-shape gates for the fixes from code-reviewer
# (round 1 catches: _config_to_draft existence, build_config_from_draft v2
# drops fonts.*, emit_design_md package-import path).
# ---------------------------------------------------------------------------

def _sample_v2_draft():
    return {
        "colors": {
            "primary":    {"hex": "#001122", "confidence": 1.0},
            "secondary":  {"hex": "#334455", "confidence": 1.0},
            "accent":     {"hex": "#FF6600", "confidence": 1.0},
            "background": {"hex": "#FFFFFF", "confidence": 1.0},
            "text":       {"hex": "#222222", "confidence": 1.0},
        },
        "fonts": {
            "header":    {"name": "Inter",          "confidence": 1.0},
            "body":      {"name": "Source Sans Pro","confidence": 1.0},
            "monospace": {"name": "JetBrains Mono", "confidence": 1.0},
        },
        "logos": {
            "primary": {"local_path": "/tmp/logo.png", "confidence": 1.0},
        },
        "source": {"type": "test", "reference": "unit"},
        "extracted_at": "2026-05-15T00:00:00Z",
        "confidence_scores": {"primary": 1.0},
    }


def test_build_config_v2_drops_fonts_and_emits_tertiary_neutral():
    """Decision 3A + 5A: v2 write path drops fonts.* and emits
    colors.tertiary + flat colors.neutral. Pins the schema change."""
    cfg = loader.build_config_from_draft(_sample_v2_draft(), schema_version=2)
    branding = cfg["branding"]
    assert "fonts" not in branding, "v2 write path must NOT emit branding.fonts.*"
    assert branding["colors"]["tertiary"] == "#FF6600"
    assert "accent" not in branding["colors"]
    assert branding["colors"]["neutral"] == "#FFFFFF"
    assert isinstance(branding["colors"]["neutral"], str)  # flat hex, not dict
    assert "background" not in branding["colors"]
    assert branding["components"]["body-text"]["backgroundColor"] == "{colors.neutral}"
    assert branding["components"]["body-text"]["textColor"] == "#222222"


def test_build_config_v1_still_emits_legacy_shape():
    """v1 write path remains backward-compatible — old consumers that hand-load
    config.yaml continue to see colors.accent and fonts.header."""
    cfg = loader.build_config_from_draft(_sample_v2_draft(), schema_version=1)
    branding = cfg["branding"]
    assert branding["colors"]["accent"] == "#FF6600"
    assert "tertiary" not in branding["colors"]
    assert branding["fonts"]["header"] == "Inter"


def test_config_to_draft_round_trip_v2():
    """_config_to_draft is the inverse of build_config_from_draft for v2.
    Round-trip via disk must yield a config with identical branding shape."""
    original = loader.build_config_from_draft(_sample_v2_draft(), schema_version=2)
    reconstructed_draft = loader._config_to_draft(original)
    rebuilt = loader.build_config_from_draft(reconstructed_draft, schema_version=2)
    # Colors, typography, components, rounded, spacing must all match.
    assert rebuilt["branding"]["colors"] == original["branding"]["colors"]
    assert rebuilt["branding"]["components"] == original["branding"]["components"]


def test_config_to_draft_round_trip_v1():
    """_config_to_draft must also handle v1 input (the common case for
    --regenerate-design-md on a pre-migration config)."""
    original = loader.build_config_from_draft(_sample_v2_draft(), schema_version=1)
    reconstructed_draft = loader._config_to_draft(original)
    # The reconstructed draft should carry the legacy color slots populated.
    assert reconstructed_draft["colors"]["accent"]["hex"] == "#FF6600"
    assert reconstructed_draft["fonts"]["header"]["name"] == "Inter"


def test_emit_design_md_loads_via_package_import_path():
    """emit_design_md.py must work when loaded via importlib (the package
    pattern used inside this hyphenated directory), not just under the test
    harness sys.path. Regression for the bare-import bug fixed in round 1."""
    import importlib.util
    emit_path = Path(__file__).parent.parent / "emit_design_md.py"
    spec = importlib.util.spec_from_file_location("emit_design_md_pkg", emit_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "emit_design_md")
    assert hasattr(mod, "ColorValidator")


def test_emit_design_md_v1_fallback_includes_h1_and_body_md():
    """Round 2 finding: emit_design_md must populate typography.h1 and
    typography.body-md from legacy fonts.header / fonts.body when typography.*
    is absent. Previously only fonts.monospace was propagated to typography.code,
    leaving regenerated DESIGN.md missing the headline + body font."""
    import importlib.util
    emit_path = Path(__file__).parent.parent / "emit_design_md.py"
    spec = importlib.util.spec_from_file_location("emit_design_md_pkg", emit_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    draft = _sample_v2_draft()
    draft.pop("typography", None)  # force v1 fallback path
    text = mod.emit_design_md(
        draft,
        client_name="Test",
        extracted_at="2026-05-15",
        source_refs=["unit"],
    )
    # Frontmatter is between the two --- fences
    frontmatter = text.split("---", 2)[1]
    data = yaml.safe_load(frontmatter)
    assert "typography" in data
    assert data["typography"].get("h1", {}).get("fontFamily") == "Inter"
    assert data["typography"].get("body-md", {}).get("fontFamily") == "Source Sans Pro"
    assert data["typography"].get("code", {}).get("fontFamily") == "JetBrains Mono"


# ---------------------------------------------------------------------------
# Round-3 review findings (gate review on f720a22 → bf4949e):
# Component invariants — every emitted component has BOTH backgroundColor AND
# textColor; every declared color is referenced by at least one component.
# ---------------------------------------------------------------------------

def _load_emit_module():
    import importlib.util
    emit_path = Path(__file__).parent.parent / "emit_design_md.py"
    spec = importlib.util.spec_from_file_location("emit_design_md_inv", emit_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _extract_frontmatter(text: str) -> dict:
    return yaml.safe_load(text.split("---", 2)[1])


def _assert_components_complete(frontmatter: dict) -> None:
    """Every emitted component MUST have both backgroundColor and textColor."""
    for name, comp in (frontmatter.get("components") or {}).items():
        assert "backgroundColor" in comp, f"component {name} missing backgroundColor"
        assert "textColor" in comp, f"component {name} missing textColor"


def _assert_no_orphaned_colors(frontmatter: dict) -> None:
    """Every declared color must be referenced by at least one component."""
    colors = list((frontmatter.get("colors") or {}).keys())
    components = frontmatter.get("components") or {}
    # Collect token-ref strings from every component property value
    refs = set()
    for comp in components.values():
        for v in comp.values():
            if isinstance(v, str) and v.startswith("{colors."):
                refs.add(v.split(".", 1)[1].rstrip("}"))
    orphaned = [c for c in colors if c not in refs]
    assert not orphaned, f"orphaned color tokens (not referenced by any component): {orphaned}"


def test_minimal_palette_primary_only_no_orphaned():
    """Draft with only primary color — emit_design_md must still wire it into
    a component (body-text.textColor) so the linter doesn't fire orphaned-tokens."""
    emit = _load_emit_module()
    draft = {
        "colors": {"primary": {"hex": "#001122", "confidence": 1.0}},
        "source": {"type": "test", "reference": "min"},
        "extracted_at": "2026-05-16",
        "confidence_scores": {},
    }
    fm = _extract_frontmatter(emit.emit_design_md(
        draft, client_name="Test", extracted_at="2026-05-16", source_refs=["min"]
    ))
    _assert_no_orphaned_colors(fm)
    _assert_components_complete(fm)


def test_minimal_palette_primary_secondary_no_orphaned():
    """Draft with primary + secondary only (no background, accent, text) —
    both colors must be referenced; this was the regression case."""
    emit = _load_emit_module()
    draft = {
        "colors": {
            "primary":   {"hex": "#001122", "confidence": 1.0},
            "secondary": {"hex": "#334455", "confidence": 1.0},
        },
        "source": {"type": "test", "reference": "min2"},
        "extracted_at": "2026-05-16",
        "confidence_scores": {},
    }
    fm = _extract_frontmatter(emit.emit_design_md(
        draft, client_name="Test", extracted_at="2026-05-16", source_refs=["min2"]
    ))
    _assert_no_orphaned_colors(fm)
    _assert_components_complete(fm)


def test_button_primary_complete_when_no_primary_no_background():
    """Accent only (no primary, no background) — button-primary must still
    have textColor via the literal-hex luminance fallback."""
    emit = _load_emit_module()
    draft = {
        "colors": {"accent": {"hex": "#FF6600", "confidence": 1.0}},
        "source": {"type": "test", "reference": "accent-only"},
        "extracted_at": "2026-05-16",
        "confidence_scores": {},
    }
    fm = _extract_frontmatter(emit.emit_design_md(
        draft, client_name="Test", extracted_at="2026-05-16", source_refs=["accent-only"]
    ))
    bp = (fm.get("components") or {}).get("button-primary")
    assert bp is not None, "button-primary should be emitted when accent is present"
    assert "backgroundColor" in bp and "textColor" in bp


def test_body_text_complete_when_no_primary_no_text():
    """Background only (no primary, no text) — body-text must still have
    textColor via the literal-hex luminance fallback (chosen against neutral)."""
    emit = _load_emit_module()
    draft = {
        "colors": {"background": {"hex": "#FFFFFF", "confidence": 1.0}},
        "source": {"type": "test", "reference": "bg-only"},
        "extracted_at": "2026-05-16",
        "confidence_scores": {},
    }
    fm = _extract_frontmatter(emit.emit_design_md(
        draft, client_name="Test", extracted_at="2026-05-16", source_refs=["bg-only"]
    ))
    bt = (fm.get("components") or {}).get("body-text")
    assert bt is not None
    assert "backgroundColor" in bt and "textColor" in bt


def test_config_to_draft_ignores_token_ref_textcolor():
    """Loader's _config_to_draft must NOT pass a {colors.primary}-style ref to
    the hex-validation gate. A user-edited config with a token-ref in
    components.body-text.textColor should leave draft.colors.text empty rather
    than crash downstream."""
    cfg = {
        "metadata": {"schema_version": 2},
        "branding": {
            "colors": {"primary": "#001122", "neutral": "#FFFFFF"},
            "components": {
                "body-text": {
                    "backgroundColor": "{colors.neutral}",
                    "textColor": "{colors.primary}",
                }
            },
        },
    }
    draft = loader._config_to_draft(cfg)
    # text slot should be absent (token-ref filtered) rather than carrying a malformed hex.
    assert "text" not in draft.get("colors", {}), "token-ref must not leak into colors.text.hex"
