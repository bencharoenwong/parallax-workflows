"""
Tests for skills/_parallax/white-label/loader.py

Run from the repo root:
    pytest skills/_parallax/white-label/tests/ -v

Requirements: pytest, pyyaml, jsonschema
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, data: dict[str, Any]) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


def _valid_config(*, primary_logo: str = "", favicon: str = "") -> dict[str, Any]:
    return {
        "metadata": {
            "schema_version": 1,
            "client_name": "Acme Capital",
            "extracted_at": "2026-04-30T00:00:00Z",
            "source": {
                "type": "url",
                "reference": "https://acme.example.com",
                "confidence": 0.95,
            },
        },
        "branding": {
            "colors": {
                "primary":    "#1A2B3C",
                "secondary":  "#FFFFFF",
                "accent":     "#FF6600",
                "background": "#F5F5F5",
                "text":       "#333333",
            },
            "logos": {
                "primary": primary_logo,
                "favicon": favicon,
            },
            "fonts": {
                "header":    "Inter",
                "body":      "Roboto",
                "monospace": "JetBrains Mono",
            },
        },
        "confidence_scores": {
            "primary_color": 0.99,
            "primary_logo":  0.85,
            "favicon":       0.85,
        },
    }


# ---------------------------------------------------------------------------
# Test 1: Happy path
# ---------------------------------------------------------------------------


def test_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Valid config with real logo files -> all 6 keys present, error=None."""
    logo = tmp_path / "primary-logo.png"
    favicon = tmp_path / "favicon.ico"
    logo.write_bytes(b"\x89PNG")
    favicon.write_bytes(b"\x00\x00")

    config_path = _write_config(
        tmp_path,
        _valid_config(primary_logo=str(logo), favicon=str(favicon)),
    )
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    result = loader_module.load_client_branding()

    assert set(result.keys()) == {
        "colors", "logos", "fonts", "source", "confidence_scores", "error"
    }
    assert result["error"] is None
    assert result["colors"]["primary"] == "#1A2B3C"
    assert result["logos"]["primary"] == str(logo)
    assert result["logos"]["favicon"] == str(favicon)
    assert result["fonts"]["header"] == "Inter"
    assert result["source"]["type"] == "url"
    assert "primary_color" in result["confidence_scores"]


# ---------------------------------------------------------------------------
# Test 2: Missing config file
# ---------------------------------------------------------------------------


def test_missing_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """No config file -> error='config_not_found', all data keys are empty dicts."""
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", tmp_path / "does_not_exist.yaml")

    result = loader_module.load_client_branding()

    assert result["error"] == "config_not_found"
    assert result["colors"] == {}
    assert result["logos"] == {}
    assert result["fonts"] == {}
    assert result["source"] == {}
    assert result["confidence_scores"] == {}


# ---------------------------------------------------------------------------
# Test 3: Corrupt YAML
# ---------------------------------------------------------------------------


def test_corrupt_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Unparseable YAML -> error starts with 'yaml_parse_error'."""
    p = tmp_path / "config.yaml"
    p.write_text("key: [\nbad yaml {{{\n", encoding="utf-8")
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", p)

    result = loader_module.load_client_branding()

    assert result["error"].startswith("yaml_parse_error"), result["error"]
    assert result["colors"] == {}


# ---------------------------------------------------------------------------
# Test 4: Schema validation failure
# ---------------------------------------------------------------------------


def test_schema_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """schema_version as string (should be int) -> error starts with 'schema_invalid'."""
    bad = _valid_config()
    bad["metadata"]["schema_version"] = "not-an-integer"  # type: ignore[assignment]

    config_path = _write_config(tmp_path, bad)
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    result = loader_module.load_client_branding()

    assert result["error"].startswith("schema_invalid"), result["error"]
    assert result["colors"] == {}


# ---------------------------------------------------------------------------
# Test 5: One logo missing
# ---------------------------------------------------------------------------


def test_one_logo_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Primary logo exists, favicon absent -> favicon='', error contains 'logo_missing', colors populated."""
    logo = tmp_path / "primary-logo.png"
    logo.write_bytes(b"\x89PNG")
    missing_favicon = str(tmp_path / "favicon.ico")  # intentionally absent

    config_path = _write_config(
        tmp_path,
        _valid_config(primary_logo=str(logo), favicon=missing_favicon),
    )
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    result = loader_module.load_client_branding()

    assert "logo_missing" in result["error"]
    assert result["logos"]["primary"] == str(logo)
    assert result["logos"]["favicon"] == ""
    assert result["colors"]["primary"] == "#1A2B3C"


# ---------------------------------------------------------------------------
# Test 6: Both logos missing
# ---------------------------------------------------------------------------


def test_both_logos_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Neither logo file exists -> both paths '', error has two 'logo_missing' entries, colors populated."""
    config_path = _write_config(
        tmp_path,
        _valid_config(
            primary_logo=str(tmp_path / "primary-logo.png"),
            favicon=str(tmp_path / "favicon.ico"),
        ),
    )
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    result = loader_module.load_client_branding()

    assert result["logos"]["primary"] == ""
    assert result["logos"]["favicon"] == ""
    assert result["error"].count("logo_missing") == 2
    assert result["colors"]["primary"] == "#1A2B3C"


# ---------------------------------------------------------------------------
# Test 7: Schema file missing (schema_unavailable)
# ---------------------------------------------------------------------------


def test_schema_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """_SCHEMA=None (schema.yaml absent) -> best-effort data returned, error='schema_unavailable'."""
    logo = tmp_path / "primary-logo.png"
    favicon = tmp_path / "favicon.ico"
    logo.write_bytes(b"\x89PNG")
    favicon.write_bytes(b"\x00\x00")

    config_path = _write_config(
        tmp_path,
        _valid_config(primary_logo=str(logo), favicon=str(favicon)),
    )
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", None)

    result = loader_module.load_client_branding()

    assert result["error"] == "schema_unavailable"
    # Data still populated best-effort
    assert result["colors"]["primary"] == "#1A2B3C"
    assert result["fonts"]["header"] == "Inter"
    assert result["logos"]["primary"] == str(logo)


# ---------------------------------------------------------------------------
# Test 8: Logger output — four branches
# ---------------------------------------------------------------------------


def test_logger_warning_missing_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Missing config -> WARNING emitted, no lower-severity records."""
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", tmp_path / "nope.yaml")

    with caplog.at_level(logging.DEBUG, logger=loader_module.logger.name):
        loader_module.load_client_branding()

    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warns) >= 1
    assert any("config not found" in r.message.lower() for r in warns)


def test_logger_warning_corrupt_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Corrupt YAML -> WARNING emitted."""
    p = tmp_path / "config.yaml"
    p.write_text(": broken: {{{\n", encoding="utf-8")
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", p)

    with caplog.at_level(logging.DEBUG, logger=loader_module.logger.name):
        loader_module.load_client_branding()

    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warns) >= 1
    assert any("parse" in r.message.lower() for r in warns)


def test_logger_warning_schema_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Schema violation -> WARNING emitted."""
    bad = _valid_config()
    bad["metadata"]["schema_version"] = "wrong"  # type: ignore[assignment]
    config_path = _write_config(tmp_path, bad)
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    with caplog.at_level(logging.DEBUG, logger=loader_module.logger.name):
        loader_module.load_client_branding()

    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warns) >= 1
    assert any("schema" in r.message.lower() for r in warns)


def test_logger_debug_clean_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Clean load -> exactly one DEBUG record, zero WARNINGs."""
    logo = tmp_path / "primary-logo.png"
    favicon = tmp_path / "favicon.ico"
    logo.write_bytes(b"\x89PNG")
    favicon.write_bytes(b"\x00\x00")

    config_path = _write_config(
        tmp_path,
        _valid_config(primary_logo=str(logo), favicon=str(favicon)),
    )
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    with caplog.at_level(logging.DEBUG, logger=loader_module.logger.name):
        loader_module.load_client_branding()

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    warn_records  = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(debug_records) >= 1
    assert any("loaded cleanly" in r.message.lower() for r in debug_records)
    assert len(warn_records) == 0


# ---------------------------------------------------------------------------
# Test 9: Invalid logo path value (non-string, schema-unavailable path)
# ---------------------------------------------------------------------------


def test_invalid_logo_value_schema_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Non-string logo value (int) in schema-unavailable path -> treated as missing path, no exception."""
    bad = _valid_config(primary_logo="42", favicon="/path/to/favicon.ico")
    bad["branding"]["logos"]["primary"] = 42  # type: ignore[assignment]
    config_path = _write_config(tmp_path, bad)
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", None)

    result = loader_module.load_client_branding()

    assert "schema_unavailable" in result["error"]
    assert "logo_missing" in result["error"]
    assert result["logos"]["primary"] == ""
    assert result["logos"]["favicon"] == ""
    assert result["colors"]["primary"] == "#1A2B3C"
