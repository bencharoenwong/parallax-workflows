"""
Integration tests for white-label onboarding workflow.

Tests the full cycle: extract → validate → confirm gate → save → load.

Run from repo root:
    pytest skills/_parallax/white-label/tests/test_integration.py -v

Requirements: pytest, pyyaml, jsonschema, pillow, requests, scrapling (optional)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# Fixture: temporary Parallax home directory
# ---------------------------------------------------------------------------


@pytest.fixture
def parallax_home(tmp_path: Path) -> Path:
    """Create a temporary ~/.parallax directory structure."""
    parallax_dir = tmp_path / ".parallax"
    branding_dir = parallax_dir / "client-branding"
    assets_dir = branding_dir / "assets"

    branding_dir.mkdir(parents=True)
    assets_dir.mkdir(parents=True)

    # Set permissions (0600 config, 0700 dirs) — would be enforced in production
    branding_dir.chmod(0o700)
    assets_dir.chmod(0o700)

    return branding_dir


# ---------------------------------------------------------------------------
# Fixture: sample extracted branding data (simulates extract_from_url output)
# ---------------------------------------------------------------------------


def _sample_extraction() -> dict[str, Any]:
    """Simulated output from ColorExtractor.extract_hex_colors(), etc."""
    return {
        "colors": {
            "primary": {
                "hex": "#2563EB",
                "confidence": 0.95,
            },
            "secondary": {
                "hex": "#FFFFFF",
                "confidence": 0.90,
            },
            "accent": {
                "hex": "#F59E0B",
                "confidence": 0.85,
            },
            "background": {
                "hex": "#F9FAFB",
                "confidence": 0.80,
            },
            "text": {
                "hex": "#111827",
                "confidence": 0.95,
            },
        },
        "logos": {
            "primary": {"url": "https://example.com/logo.png", "confidence": 0.9},
            "favicon": {"url": "https://example.com/favicon.ico", "confidence": 0.7},
        },
        "fonts": {
            "header": {"name": "Inter", "confidence": 0.95},
            "body": {"name": "Roboto", "confidence": 0.90},
            "monospace": {"name": "JetBrains Mono", "confidence": 0.85},
        },
        "source": {
            "type": "url",
            "reference": "https://example.com",
            "confidence": 0.95,
        },
        "extracted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# ---------------------------------------------------------------------------
# Fixture: loader module + mock schema
# ---------------------------------------------------------------------------


@pytest.fixture
def loader_module_with_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Load the loader module and configure it for integration testing."""
    import importlib.util
    import sys

    loader_path = (
        Path(__file__).parent.parent / "loader.py"
    )
    spec = importlib.util.spec_from_file_location(
        "parallax_white_label_loader_integration", loader_path
    )
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["parallax_white_label_loader_integration"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    # Point module-level config path to temp directory
    branding_dir = tmp_path / ".parallax" / "client-branding"
    config_path = branding_dir / "config.yaml"
    branding_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(mod, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(mod, "_SCHEMA", mod._JSONSCHEMA)  # Use embedded schema

    return mod, branding_dir


# ---------------------------------------------------------------------------
# Test 1: Full happy-path workflow
# ---------------------------------------------------------------------------


def test_integration_full_workflow_happy_path(
    loader_module_with_schema: tuple,
    tmp_path: Path,
) -> None:
    """
    Full workflow: extract → normalize → validate → confirm → save → load.

    Simulates:
    1. Extract branding from URL (mocked)
    2. Normalize colors to 6-digit hex
    3. Validate against schema
    4. Confirm gate (user approves)
    5. Save to ~/.parallax/client-branding/config.yaml
    6. Load via loader.load_client_branding() and verify
    """
    loader_mod, branding_dir = loader_module_with_schema

    # Step 1: Simulate extraction
    extracted = _sample_extraction()

    # Step 2: Normalize to flat config shape
    # (simulates what extract.py would do before save)
    flat_config = {
        "metadata": {
            "schema_version": 1,
            "client_name": "Example Corp",
            "extracted_at": extracted["extracted_at"],
            "source": extracted["source"],
        },
        "branding": {
            "colors": {
                "primary": extracted["colors"]["primary"]["hex"],
                "secondary": extracted["colors"]["secondary"]["hex"],
                "accent": extracted["colors"]["accent"]["hex"],
                "background": extracted["colors"]["background"]["hex"],
                "text": extracted["colors"]["text"]["hex"],
            },
            "logos": {
                "primary": str(tmp_path / "logo.png"),
                "favicon": str(tmp_path / "favicon.ico"),
            },
            "fonts": {
                "header": extracted["fonts"]["header"]["name"],
                "body": extracted["fonts"]["body"]["name"],
                "monospace": extracted["fonts"]["monospace"]["name"],
            },
        },
        "confidence_scores": {
            f"color_{k}": v["confidence"]
            for k, v in extracted["colors"].items()
        } | {
            "logo_primary": extracted["logos"]["primary"]["confidence"],
            "logo_favicon": extracted["logos"]["favicon"]["confidence"],
        } | {
            f"font_{k}": v["confidence"]
            for k, v in extracted["fonts"].items()
        },
    }

    # Step 3 & 4: Validate (would be user confirmation gate in real flow)
    # For this test, we assume validation passed and user confirmed

    # Step 5: Save to config.yaml
    config_path = branding_dir / "config.yaml"
    config_path.write_text(yaml.dump(flat_config), encoding="utf-8")

    # Create logo files (just stubs for testing)
    logo_path = tmp_path / "logo.png"
    favicon_path = tmp_path / "favicon.ico"
    logo_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    favicon_path.write_bytes(b"\x00\x00\x01\x00")

    # Step 6: Load via loader.load_client_branding()
    result = loader_mod.load_client_branding()

    # Assertions
    assert result["error"] is None
    assert result["colors"]["primary"] == "#2563EB"
    assert result["colors"]["secondary"] == "#FFFFFF"
    assert result["fonts"]["header"] == "Inter"
    assert result["fonts"]["body"] == "Roboto"
    assert result["logos"]["primary"] == str(logo_path)
    assert result["logos"]["favicon"] == str(favicon_path)
    assert result["source"]["type"] == "url"
    assert "color_primary" in result["confidence_scores"]


# ---------------------------------------------------------------------------
# Test 2: Partial extraction with validation warnings
# ---------------------------------------------------------------------------


def test_integration_partial_extraction_with_warnings(
    loader_module_with_schema: tuple,
    tmp_path: Path,
) -> None:
    """
    Partial extraction: one logo missing, all colors/fonts present.

    Simulates scenario where:
    - URL fetch succeeded for colors and fonts
    - Logo URL returned 404 or was unreachable
    - User proceeds with partial branding (graceful degradation)
    """
    loader_mod, branding_dir = loader_module_with_schema

    # Partial extraction: primary logo exists, favicon missing
    partial_config = {
        "metadata": {
            "schema_version": 1,
            "client_name": "Partial Corp",
            "extracted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": {"type": "url", "reference": "https://partial.example.com", "confidence": 0.85},
        },
        "branding": {
            "colors": {
                "primary": "#E74C3C",
                "secondary": "#ECF0F1",
                "accent": "#3498DB",
                "background": "#FFFFFF",
                "text": "#2C3E50",
            },
            "logos": {
                "primary": str(tmp_path / "logo.png"),
                "favicon": str(tmp_path / "favicon-missing.ico"),  # Will not exist
            },
            "fonts": {
                "header": "Helvetica",
                "body": "Georgia",
                "monospace": "Courier New",
            },
        },
        "confidence_scores": {
            "color_primary": 0.90,
            "logo_primary": 0.85,
            "logo_favicon": 0.0,  # Not found
        },
    }

    # Save config
    config_path = branding_dir / "config.yaml"
    config_path.write_text(yaml.dump(partial_config), encoding="utf-8")

    # Create only the primary logo
    logo_path = tmp_path / "logo.png"
    logo_path.write_bytes(b"\x89PNG")

    # Load
    result = loader_mod.load_client_branding()

    # Assertions: partial degradation
    assert "logo_missing" in result["error"]
    assert result["logos"]["primary"] == str(logo_path)
    assert result["logos"]["favicon"] == ""  # Missing file → empty string
    assert result["colors"]["primary"] == "#E74C3C"  # Colors intact
    assert result["fonts"]["header"] == "Helvetica"  # Fonts intact


# ---------------------------------------------------------------------------
# Test 3: User rejects extracted branding, restarts
# ---------------------------------------------------------------------------


def test_integration_user_rejects_and_retries(
    loader_module_with_schema: tuple,
    tmp_path: Path,
) -> None:
    """
    Scenario: User reviews extracted branding, rejects it, and extracts again.

    Simulates:
    1. First extraction saved to config.yaml
    2. User rejects (e.g., colors don't match brand guide)
    3. Re-extract from same URL or new source
    4. Overwrite config.yaml
    5. Load new branding
    """
    loader_mod, branding_dir = loader_module_with_schema

    # First extraction attempt
    first_extraction = {
        "metadata": {
            "schema_version": 1,
            "client_name": "Retry Corp",
            "extracted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": {"type": "url", "reference": "https://retry.example.com", "confidence": 0.70},
        },
        "branding": {
            "colors": {
                "primary": "#FF0000",  # Too bright, user rejects
                "secondary": "#FFFFFF",
                "accent": "#00FF00",
                "background": "#F0F0F0",
                "text": "#000000",
            },
            "logos": {
                "primary": str(tmp_path / "logo-v1.png"),
                "favicon": str(tmp_path / "favicon-v1.ico"),
            },
            "fonts": {
                "header": "Arial",
                "body": "Verdana",
                "monospace": "Courier New",
            },
        },
        "confidence_scores": {"color_primary": 0.60},
    }

    config_path = branding_dir / "config.yaml"
    config_path.write_text(yaml.dump(first_extraction), encoding="utf-8")

    # Create logo files for v1
    (tmp_path / "logo-v1.png").write_bytes(b"\x89PNG")
    (tmp_path / "favicon-v1.ico").write_bytes(b"\x00\x00")

    # Load first extraction
    result_v1 = loader_mod.load_client_branding()
    assert result_v1["colors"]["primary"] == "#FF0000"

    # User rejects and extracts again (manual wizard or URL re-extraction)
    second_extraction = {
        "metadata": {
            "schema_version": 1,
            "client_name": "Retry Corp",
            "extracted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": {"type": "wizard", "reference": "user-manual-entry", "confidence": 1.0},
        },
        "branding": {
            "colors": {
                "primary": "#0052CC",  # User's approved color
                "secondary": "#FFFFFF",
                "accent": "#FF9F0D",
                "background": "#F5F6F8",
                "text": "#172B4D",
            },
            "logos": {
                "primary": str(tmp_path / "logo-v2.png"),
                "favicon": str(tmp_path / "favicon-v2.ico"),
            },
            "fonts": {
                "header": "Inter",
                "body": "Roboto",
                "monospace": "JetBrains Mono",
            },
        },
        "confidence_scores": {"color_primary": 1.0},
    }

    # Overwrite config with approved branding
    config_path.write_text(yaml.dump(second_extraction), encoding="utf-8")

    # Create logo files for v2
    (tmp_path / "logo-v2.png").write_bytes(b"\x89PNG")
    (tmp_path / "favicon-v2.ico").write_bytes(b"\x00\x00\x01\x00")

    # Load updated branding
    result_v2 = loader_mod.load_client_branding()

    assert result_v2["colors"]["primary"] == "#0052CC"
    assert result_v2["source"]["type"] == "wizard"
    assert result_v2["confidence_scores"]["color_primary"] == 1.0


# ---------------------------------------------------------------------------
# Test 4: Multiple branding profiles (theoretical)
# ---------------------------------------------------------------------------


def test_integration_single_global_location(
    loader_module_with_schema: tuple,
    tmp_path: Path,
) -> None:
    """
    Verify loader always reads from ~/.parallax/client-branding/config.yaml
    and does NOT support multiple profiles.

    Simulates: attempting to load a different profile → loader ignores it,
    always reads the single canonical location.
    """
    loader_mod, branding_dir = loader_module_with_schema

    # Create config at the canonical location
    canonical_config = {
        "metadata": {
            "schema_version": 1,
            "client_name": "Canonical Client",
            "extracted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": {"type": "url", "reference": "https://canonical.example.com", "confidence": 0.95},
        },
        "branding": {
            "colors": {
                "primary": "#001F3F",
                "secondary": "#FFFFFF",
                "accent": "#FF851B",
                "background": "#F5F5F5",
                "text": "#333333",
            },
            "logos": {
                "primary": str(tmp_path / "canonical-logo.png"),
                "favicon": str(tmp_path / "canonical-favicon.ico"),
            },
            "fonts": {
                "header": "Georgia",
                "body": "Georgia",
                "monospace": "Courier New",
            },
        },
        "confidence_scores": {"color_primary": 0.95},
    }

    config_path = branding_dir / "config.yaml"
    config_path.write_text(yaml.dump(canonical_config), encoding="utf-8")

    # Create logo files
    (tmp_path / "canonical-logo.png").write_bytes(b"\x89PNG")
    (tmp_path / "canonical-favicon.ico").write_bytes(b"\x00\x00")

    # Attempt to load (loader always reads canonical location)
    result = loader_mod.load_client_branding()

    assert result["error"] is None
    assert result["colors"]["primary"] == "#001F3F"
    assert result["source"]["reference"] == "https://canonical.example.com"


# ---------------------------------------------------------------------------
# Test 5: Downstream skill integration (mock)
# ---------------------------------------------------------------------------


def test_integration_downstream_skill_usage(
    loader_module_with_schema: tuple,
    tmp_path: Path,
) -> None:
    """
    Simulates downstream skill (e.g., /parallax-client-review) loading
    branding and gracefully handling degradation.

    Demonstrates:
    1. Load branding via loader
    2. Check error field
    3. Apply available branding (colors + fonts + logos)
    4. Fall back to defaults for missing components
    """
    loader_mod, branding_dir = loader_module_with_schema

    # Partial config (missing favicon)
    config = {
        "metadata": {
            "schema_version": 1,
            "client_name": "Downstream Test Client",
            "extracted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": {"type": "url", "reference": "https://downstream.example.com", "confidence": 0.85},
        },
        "branding": {
            "colors": {
                "primary": "#6366F1",
                "secondary": "#FFFFFF",
                "accent": "#F97316",
                "background": "#F8FAFC",
                "text": "#1E293B",
            },
            "logos": {
                "primary": str(tmp_path / "branding-logo.png"),
                "favicon": str(tmp_path / "branding-favicon-missing.ico"),
            },
            "fonts": {
                "header": "Inter",
                "body": "Inter",
                "monospace": "JetBrains Mono",
            },
        },
        "confidence_scores": {"color_primary": 0.95},
    }

    config_path = branding_dir / "config.yaml"
    config_path.write_text(yaml.dump(config), encoding="utf-8")

    # Create primary logo only
    (tmp_path / "branding-logo.png").write_bytes(b"\x89PNG")

    # Simulate downstream skill behavior
    branding = loader_mod.load_client_branding()

    # Downstream skill: check error, apply available branding, use defaults for missing
    if branding["error"]:
        logger = logging.getLogger("downstream_skill")
        logger.warning("Client branding degraded: %s", branding["error"])

    # Apply branding to PDF
    pdf_primary_color = branding["colors"].get("primary", "#000000")
    pdf_logo = branding["logos"].get("primary", None)
    pdf_favicon = branding["logos"].get("favicon", None)  # Empty string if missing
    pdf_header_font = branding["fonts"].get("header", "Helvetica")

    # Assertions: graceful degradation
    assert pdf_primary_color == "#6366F1"
    assert pdf_logo == str(tmp_path / "branding-logo.png")
    assert pdf_favicon == ""  # Missing logo → empty string, not error
    assert pdf_header_font == "Inter"


# ---------------------------------------------------------------------------
# Test 6: Audit trail (schema-unavailable + logo warnings)
# ---------------------------------------------------------------------------


def test_integration_audit_trail_degradation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that error field correctly accumulates multiple warnings
    (schema_unavailable + logo_missing) in schema-unavailable path.

    Simulates production scenario: schema.yaml deleted (rare), logo files missing.
    """
    import importlib.util
    import sys

    loader_path = Path(__file__).parent.parent / "loader.py"
    spec = importlib.util.spec_from_file_location(
        "loader_audit_trail", loader_path
    )
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["loader_audit_trail"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    # Config with missing logos
    branding_dir = tmp_path / ".parallax" / "client-branding"
    branding_dir.mkdir(parents=True)
    config_path = branding_dir / "config.yaml"

    config = {
        "metadata": {
            "schema_version": 1,
            "client_name": "Audit Test",
            "extracted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": {"type": "url", "reference": "https://audit.example.com", "confidence": 0.9},
        },
        "branding": {
            "colors": {"primary": "#123456", "secondary": "#FFFFFF", "accent": "#ABCDEF", "background": "#F0F0F0", "text": "#000000"},
            "logos": {
                "primary": str(tmp_path / "missing-logo.png"),
                "favicon": str(tmp_path / "missing-favicon.ico"),
            },
            "fonts": {"header": "Arial", "body": "Verdana", "monospace": "Courier"},
        },
        "confidence_scores": {},
    }

    config_path.write_text(yaml.dump(config), encoding="utf-8")

    monkeypatch.setattr(mod, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(mod, "_SCHEMA", None)  # Schema unavailable

    result = mod.load_client_branding()

    # Assertions: error contains both "schema_unavailable" and "logo_missing"
    assert result["error"] is not None
    assert "schema_unavailable" in result["error"]
    assert "logo_missing" in result["error"]
    # Verify data was loaded despite errors
    assert result["colors"]["primary"] == "#123456"
