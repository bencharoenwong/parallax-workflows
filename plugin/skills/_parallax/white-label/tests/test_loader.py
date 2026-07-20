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


def _valid_config(
    *,
    primary_logo: str = "",
    favicon: str = "",
    render: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = {
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
    if render is not None:
        cfg["render"] = render
    return cfg


# ---------------------------------------------------------------------------
# Test 1: Happy path
# ---------------------------------------------------------------------------


def test_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Valid config with real logo files -> all 14 keys present, error=None."""
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

    # Loader return contract: 9 legacy keys (preserved for downstream PDF
    # consumers) plus 4 bonus keys (typography/rounded/spacing/components)
    # that v2-aware consumers can opt into. On v1 input the bonus keys are
    # populated as empty dicts so `[]` access works without KeyError.
    assert set(result.keys()) == {
        "client_name", "colors", "logos", "fonts", "source", "confidence_scores",
        "voice", "multi_source", "render", "error",
        "typography", "rounded", "spacing", "components",
    }
    assert result["error"] is None
    assert result["colors"]["primary"] == "#1A2B3C"
    # Voice + multi_source default to empty/disabled when not present in config
    assert result["voice"] == {"enabled": False}
    assert result["multi_source"] == {}
    assert result["render"] == {}
    # client_name surfaced from metadata for downstream consumers
    assert isinstance(result["client_name"], str)
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
    assert result["render"] == {}
    # v2-aware bonus keys must be present (empty) on error paths too —
    # consumers reading result["typography"] should never KeyError.
    assert result["typography"] == {}
    assert result["rounded"] == {}
    assert result["spacing"] == {}
    assert result["components"] == {}


def test_error_and_success_paths_share_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """_empty_result and _build_result must return the same set of top-level keys
    so v2-aware consumers can read bonus keys unconditionally."""
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", tmp_path / "missing.yaml")
    error_keys = set(loader_module.load_client_branding().keys())

    success_keys = set(loader_module._build_result({"branding": {}, "metadata": {}}, []).keys())
    assert error_keys == success_keys, (
        f"shape drift: error={error_keys ^ success_keys}"
    )


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


# ---------------------------------------------------------------------------
# Test 10: load_visual_branding() — structural voice-leak guard
# ---------------------------------------------------------------------------


def test_visual_branding_excludes_voice_and_v2_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Visual subset returns exactly 7 keys; voice/typography/etc. are absent.

    This is the structural guardrail referenced in integration-pattern.md §3:
    voice-consuming skills call load_client_branding directly; visual skills
    use this wrapper so a KeyError fires if anyone reaches for branding["voice"].
    """
    logo = tmp_path / "primary.png"
    logo.write_bytes(b"\x89PNG")
    config_path = _write_config(
        tmp_path, _valid_config(primary_logo=str(logo)),
    )
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    result = loader_module.load_visual_branding()

    assert set(result.keys()) == {
        "client_name", "colors", "logos", "fonts", "source", "error", "render",
    }
    assert result["error"] is None
    assert result["fonts"]["header"] == "Inter"
    assert result["colors"]["primary"] == "#1A2B3C"


def test_visual_branding_missing_config_preserves_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """No client onboarded -> 7-key shape preserved, error='config_not_found'.

    Mirrors the load_client_branding contract so consumers can branch on
    `result["error"] == "config_not_found"` without separate shape handling.
    """
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", tmp_path / "does_not_exist.yaml")

    result = loader_module.load_visual_branding()

    assert set(result.keys()) == {
        "client_name", "colors", "logos", "fonts", "source", "error", "render",
    }
    assert result["error"] == "config_not_found"
    assert result["colors"] == {}
    assert result["logos"] == {}
    assert result["render"] == {}


def test_render_block_exposed_by_full_and_visual_loaders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Valid render block -> both loaders expose deployment render defaults."""
    cfg = _valid_config(render={"audience_default": "client_safe"})
    config_path = _write_config(tmp_path, cfg)
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    full = loader_module.load_client_branding()
    visual = loader_module.load_visual_branding()

    assert full["error"] is None
    assert full["render"] == {"audience_default": "client_safe"}
    assert visual["render"] == {"audience_default": "client_safe"}


def test_missing_render_block_defaults_to_empty_dict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Config without render block preserves the render key as an empty dict."""
    config_path = _write_config(tmp_path, _valid_config())
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    assert loader_module.load_client_branding()["render"] == {}
    assert loader_module.load_visual_branding()["render"] == {}


def test_invalid_render_audience_default_fails_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Unknown audience defaults fail schema validation."""
    config_path = _write_config(
        tmp_path,
        _valid_config(render={"audience_default": "everyone"}),
    )
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    result = loader_module.load_client_branding()

    assert result["error"].startswith("schema_invalid")


def test_visual_branding_voice_in_source_config_is_filtered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Config carries a voice block -> wrapper still excludes it.

    Future client configs may carry tone/persona under `branding.voice`. The
    visual-branding wrapper must drop it regardless of whether the source
    config populated it. KeyError-on-access is the safety property.
    """
    cfg = _valid_config()
    cfg["branding"]["voice"] = {  # type: ignore[index]
        "enabled": True,
        "tone": "authoritative",
        "persona": "institutional CIO",
    }
    config_path = _write_config(tmp_path, cfg)
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    result = loader_module.load_visual_branding()

    assert "voice" not in result
    with pytest.raises(KeyError):
        _ = result["voice"]


def test_visual_branding_keys_are_subset_of_load_client_branding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Drift gate: the visual subset must always be a strict subset of the full
    loader output, so the wrapper never invents keys."""
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", tmp_path / "missing.yaml")

    visual_keys = set(loader_module.load_visual_branding().keys())
    full_keys   = set(loader_module.load_client_branding().keys())

    assert visual_keys <= full_keys, (
        f"visual keys not a subset: extra={visual_keys - full_keys}"
    )
    assert visual_keys == set(loader_module._VISUAL_BRANDING_KEYS)


@pytest.mark.parametrize(
    "error,expected",
    [
        (None, True),
        ("logo_missing: primary path not found: /tmp/x.png", True),
        ("schema_unavailable", True),
        ("schema_unavailable; logo_missing: primary path not found", True),
        ("config_not_found", False),
        ("schema_invalid: bad type", False),
        ("yaml_parse_error: unexpected token", False),
    ],
)
def test_is_white_label_active_contract(
    error: str | None,
    expected: bool,
    loader_module: ModuleType,
) -> None:
    """Active classes (clean, logo_missing, schema_unavailable) → True;
    fallback classes (config_not_found, schema_invalid, yaml_parse_error) → False.
    Resolves the §2/§4/§7/§8 contract disagreement in integration-pattern.md."""
    assert loader_module.is_white_label_active({"error": error}) is expected


def test_schema_unavailable_with_missing_logo_is_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """The combined schema_unavailable + logo_missing path keeps white-label
    rendering active — the loader still returns usable palette/font data."""
    cfg = _valid_config(primary_logo="/nonexistent/logo.png", favicon="")
    config_path = _write_config(tmp_path, cfg)
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", None)

    result = loader_module.load_visual_branding()

    assert "schema_unavailable" in result["error"]
    assert "logo_missing" in result["error"]
    assert loader_module.is_white_label_active(result) is True
    assert result["colors"]["primary"] == "#1A2B3C"


@pytest.mark.parametrize(
    "filename,bytes_",
    [
        ("id_rsa", b"-----BEGIN PRIVATE KEY-----\n"),
        ("credentials", b"aws_access_key_id=AKIA...\n"),
        (".env", b"DATABASE_URL=postgres://...\n"),
        ("passwd", b"root:x:0:0:root:/root:/bin/bash\n"),
    ],
)
def test_logo_with_disallowed_extension_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
    filename: str,
    bytes_: bytes,
) -> None:
    """Credential-disclosure guard: paths without a whitelisted image extension
    are rejected even when the file exists. The rejection reason — not the raw
    filename — appears in the error string."""
    target = tmp_path / filename
    target.write_bytes(bytes_)

    cfg = _valid_config(primary_logo=str(target), favicon="")
    config_path = _write_config(tmp_path, cfg)
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    result = loader_module.load_client_branding()

    assert result["logos"]["primary"] == ""
    assert "extension not in image allowlist" in result["error"]
    # Filename must not leak into the error string
    assert filename not in result["error"]


def test_logo_symlink_to_extensionless_file_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """A .png symlink that resolves to an extensionless file (e.g., /etc/hosts)
    is rejected — `.resolve()` canonicalizes before the extension check."""
    target = tmp_path / "secrets"  # no extension
    target.write_bytes(b"sensitive\n")
    symlink = tmp_path / "logo.png"
    symlink.symlink_to(target)

    cfg = _valid_config(primary_logo=str(symlink), favicon="")
    config_path = _write_config(tmp_path, cfg)
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    result = loader_module.load_client_branding()

    assert result["logos"]["primary"] == ""
    assert "extension not in image allowlist" in result["error"]


def test_empty_logo_path_is_silent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Empty-string logo value (operator deliberately omitting a logo) is not
    a missing-file error — resolves to "" without populating the error field."""
    logo = tmp_path / "primary.png"
    logo.write_bytes(b"\x89PNG")
    cfg = _valid_config(primary_logo=str(logo), favicon="")
    config_path = _write_config(tmp_path, cfg)
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    result = loader_module.load_client_branding()

    assert result["error"] is None
    assert result["logos"]["primary"] == str(logo)
    assert result["logos"]["favicon"] == ""


@pytest.mark.parametrize(
    "raw_ref,expected",
    [
        ("", ""),
        ("Acme Brand Deck v3", "Acme Brand Deck v3"),
        ("https://internal.acme-capital.example/clients/acme/brand.pdf?sig=secret", "https://internal.acme-capital.example"),
        ("http://10.0.0.5:8080/private/deck.pptx", "http://10.0.0.5"),
        ("https://s3.amazonaws.com/bucket/key?X-Amz-Signature=xyz", "https://s3.amazonaws.com"),
        ("/Users/operator/Dropbox/Clients/Acme/brand.pdf", "brand.pdf"),
        ("~/Downloads/acme-brand.pptx", "acme-brand.pptx"),
    ],
)
def test_safe_source_reference_redacts_urls_and_paths(
    raw_ref: str,
    expected: str,
    loader_module: ModuleType,
) -> None:
    """URL refs collapse to scheme+host; filesystem refs to basename; opaque
    strings pass through. Pre-signed URLs and internal paths must not leak."""
    branding = {"source": {"reference": raw_ref}}
    assert loader_module.safe_source_reference(branding) == expected


def test_safe_source_reference_tolerates_missing_source(
    loader_module: ModuleType,
) -> None:
    """Defensive: empty/missing source dict returns "" without raising."""
    assert loader_module.safe_source_reference({}) == ""
    assert loader_module.safe_source_reference({"source": None}) == ""
    assert loader_module.safe_source_reference({"source": {}}) == ""
    assert loader_module.safe_source_reference({"source": {"reference": None}}) == ""


def test_visual_branding_propagates_logo_missing_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    """Partial-degradation paths preserve the error string through the wrapper.

    `logo_missing:*` is the one error class where colors/fonts are still
    populated; the wrapper must surface the error string unchanged so
    consumers can branch on `error.startswith("logo_missing")`.
    """
    cfg = _valid_config(primary_logo="/nonexistent/logo.png", favicon="")
    config_path = _write_config(tmp_path, cfg)
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(loader_module, "_SCHEMA", loader_module._JSONSCHEMA)

    result = loader_module.load_visual_branding()

    assert result["error"] is not None
    assert "logo_missing" in result["error"]
    # Palette still usable on the partial-degradation path
    assert result["colors"]["primary"] == "#1A2B3C"
    assert result["fonts"]["header"] == "Inter"


# ---------------------------------------------------------------------------
# build_config_from_draft typography placeholder
# ---------------------------------------------------------------------------


def test_build_config_from_draft_emits_typography_placeholder(
    loader_module: ModuleType,
) -> None:
    """When a draft has no typography and no fonts.* fallback, the v2 write
    path must emit the `{body-md: {fontFamily: 'sans-serif'}}` placeholder.

    This satisfies the v2 schema's `typography: minProperties: 1` constraint
    so the resulting config remains loadable on the next read. Using the CSS
    generic family name makes the placeholder obvious to operators reviewing
    the saved config.
    """
    draft: dict[str, Any] = {
        "colors": {
            "primary":    {"hex": "#001122", "confidence": 1.0},
            "secondary":  {"hex": "#334455", "confidence": 1.0},
            "accent":     {"hex": "#FF6600", "confidence": 1.0},
            "background": {"hex": "#FFFFFF", "confidence": 1.0},
        },
        # No `typography` and no `fonts` -> placeholder branch fires.
        "logos": {"primary": {"local_path": "/tmp/logo.png", "confidence": 1.0}},
        "source": {"type": "test", "reference": "unit"},
        "extracted_at": "2026-05-18T00:00:00Z",
        "confidence_scores": {"primary": 1.0},
    }

    cfg = loader_module.build_config_from_draft(draft, schema_version=2)

    assert cfg["branding"]["typography"] == {"body-md": {"fontFamily": "sans-serif"}}
