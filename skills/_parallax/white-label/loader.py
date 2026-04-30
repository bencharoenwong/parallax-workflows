"""
White-label branding loader for Parallax skills.

Reads ~/.parallax/client-branding/config.yaml, validates it against the
canonical schema, resolves logo paths, and returns a normalised dict.
Called on every skill invocation — optimised to be silent on success.

Public interface
----------------
    load_client_branding() -> dict[str, Any]

Return shape (always 6 top-level keys)
---------------------------------------
    {
        "colors":            dict | {},
        "logos":             dict | {},
        "fonts":             dict | {},
        "source":            dict | {},
        "confidence_scores": dict | {},
        "error":             str | None,   # None = clean load
    }
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

_CONFIG_PATH: Path = Path.home() / ".parallax" / "client-branding" / "config.yaml"
_SCHEMA_PATH: Path = Path(__file__).parent / "schema.yaml"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON Schema — derived from schema.yaml structure; embedded for zero-I/O load
# ---------------------------------------------------------------------------

_JSONSCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["metadata", "branding", "confidence_scores"],
    "properties": {
        "metadata": {
            "type": "object",
            "required": ["schema_version", "client_name", "extracted_at", "source"],
            "properties": {
                "schema_version": {"type": "integer"},
                "client_name":    {"type": "string"},
                "extracted_at":   {"type": "string"},
                "source": {
                    "type": "object",
                    "required": ["type", "reference", "confidence"],
                    "properties": {
                        "type":       {"type": "string", "enum": ["url", "pdf", "wizard"]},
                        "reference":  {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    },
                },
            },
        },
        "branding": {
            "type": "object",
            "required": ["colors", "logos", "fonts"],
            "properties": {
                "colors": {
                    "type": "object",
                    "required": ["primary", "secondary", "accent", "background", "text"],
                    "properties": {
                        "primary":    {"type": "string"},
                        "secondary":  {"type": "string"},
                        "accent":     {"type": "string"},
                        "background": {"type": "string"},
                        "text":       {"type": "string"},
                    },
                },
                "logos": {
                    "type": "object",
                    "required": ["primary", "favicon"],
                    "properties": {
                        "primary": {"type": "string"},
                        "favicon": {"type": "string"},
                    },
                },
                "fonts": {
                    "type": "object",
                    "required": ["header", "body", "monospace"],
                    "properties": {
                        "header":    {"type": "string"},
                        "body":      {"type": "string"},
                        "monospace": {"type": "string"},
                    },
                },
            },
        },
        "confidence_scores": {
            "type": "object",
        },
    },
}


def _load_schema_or_none() -> dict[str, Any] | None:
    """
    Guard: confirm schema.yaml is present on disk.

    Validation uses the embedded _JSONSCHEMA dict; this function determines
    whether schema-based validation runs at all.  Returns the embedded schema
    dict if schema.yaml exists, None otherwise (caller skips validation).
    """
    if _SCHEMA_PATH.exists():
        return _JSONSCHEMA
    return None


# Loaded once at module import.  None => "schema unavailable, skip validation".
_SCHEMA: dict[str, Any] | None = _load_schema_or_none()

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolve_config_path() -> Path:
    """Return the module-level config path.  Tests monkeypatch _CONFIG_PATH."""
    return _CONFIG_PATH


def _empty_result(error: str) -> dict[str, Any]:
    """Canonical 6-key empty result dict with a populated error field."""
    return {
        "colors":            {},
        "logos":             {},
        "fonts":             {},
        "source":            {},
        "confidence_scores": {},
        "error":             error,
    }


def _read_yaml(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """
    Read and parse a YAML file.

    Returns (parsed_dict, None) on success.
    Returns (None, error_string) on read or parse failure.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"yaml_read_error: {exc}"

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return None, f"yaml_parse_error: {exc}"

    if not isinstance(data, dict):
        return None, "yaml_parse_error: top-level value is not a mapping"

    return data, None


def _validate_schema(data: dict[str, Any], schema: dict[str, Any]) -> str | None:
    """
    Validate *data* against *schema* using jsonschema.

    Returns None on success, human-readable error string on failure.
    Returns None (skip) if jsonschema is not installed.
    """
    try:
        import jsonschema

        jsonschema.validate(instance=data, schema=schema)
        return None
    except jsonschema.ValidationError as exc:
        return f"schema_invalid: {exc.message}"
    except jsonschema.SchemaError as exc:
        return f"schema_invalid: bad schema — {exc.message}"
    except ImportError:
        # jsonschema not installed; treat as schema unavailable
        return None


def _resolve_logo_paths(
    logos: dict[str, str],
) -> tuple[dict[str, str], list[str]]:
    """
    Expand tilde and verify each logo path on disk.

    Missing files have their value replaced with "" and a warning string is
    appended.  Present files are stored as fully-resolved absolute paths.

    Returns (resolved_logos_dict, list_of_warning_strings).
    """
    resolved: dict[str, str] = {}
    warnings: list[str] = []

    for key, raw_path in logos.items():
        expanded = Path(raw_path).expanduser()
        if expanded.exists():
            resolved[key] = str(expanded)
        else:
            resolved[key] = ""
            msg = f"logo_missing: {key} path not found: {raw_path}"
            warnings.append(msg)
            logger.warning("White-label logo missing — key=%s path=%s", key, raw_path)

    return resolved, warnings


def _build_result(
    data: dict[str, Any],
    logo_warnings: list[str],
) -> dict[str, Any]:
    """
    Assemble the canonical 6-key result dict from validated, logo-resolved data.

    *logo_warnings* are joined into the error field when present; error is
    None on a fully clean load.
    """
    branding = data.get("branding", {})
    metadata = data.get("metadata", {})

    error: str | None = "; ".join(logo_warnings) if logo_warnings else None

    return {
        "colors":            branding.get("colors", {}),
        "logos":             branding.get("logos", {}),
        "fonts":             branding.get("fonts", {}),
        "source":            metadata.get("source", {}),
        "confidence_scores": data.get("confidence_scores", {}),
        "error":             error,
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def load_client_branding() -> dict[str, Any]:
    """
    Load and validate client branding configuration.

    Returns a dict with exactly 6 keys: colors, logos, fonts, source,
    confidence_scores, error.  error is None on a fully clean load, a
    human-readable string on any degradation.

    Failure points:
        1. Missing config file   -> short-circuit, error="config_not_found"
        2. Corrupted YAML        -> short-circuit, error starts with "yaml_parse_error"
        3. Schema validation     -> short-circuit, error starts with "schema_invalid"
        4. Missing logo files    -> partial degradation, error contains "logo_missing"
           Schema unavailable    -> best-effort data, error="schema_unavailable"

    Never raises — all failure paths return the canonical empty/partial result.
    """
    config_path = _resolve_config_path()

    # --- Failure point 1: missing config file ---
    if not config_path.exists():
        logger.warning(
            "White-label config not found at %s — "
            "returning empty branding (unonboarded install)",
            config_path,
        )
        return _empty_result("config_not_found")

    # --- Failure point 2: corrupted / unreadable YAML ---
    data, parse_error = _read_yaml(config_path)
    if parse_error is not None:
        logger.warning("White-label config parse failure: %s", parse_error)
        return _empty_result(parse_error)

    # --- Schema unavailable branch: best-effort return, skip validation ---
    if _SCHEMA is None:
        logger.warning(
            "White-label schema file not found at %s — skipping validation",
            _SCHEMA_PATH,
        )
        branding = data.get("branding", {})
        logos_raw = branding.get("logos", {})
        resolved_logos, logo_warnings = _resolve_logo_paths(logos_raw)
        patched_data = {**data, "branding": {**branding, "logos": resolved_logos}}
        result = _build_result(patched_data, logo_warnings)
        result["error"] = "schema_unavailable"
        return result

    # --- Failure point 3: schema validation ---
    schema_error = _validate_schema(data, _SCHEMA)
    if schema_error is not None:
        logger.warning("White-label config schema violation: %s", schema_error)
        return _empty_result(schema_error)

    # --- Failure point 4: missing logo files (partial degradation) ---
    branding = data.get("branding", {})
    logos_raw = branding.get("logos", {})
    resolved_logos, logo_warnings = _resolve_logo_paths(logos_raw)

    patched_data = {**data, "branding": {**branding, "logos": resolved_logos}}
    result = _build_result(patched_data, logo_warnings)

    if result["error"] is None:
        logger.debug("White-label branding loaded cleanly from %s", config_path)

    return result
