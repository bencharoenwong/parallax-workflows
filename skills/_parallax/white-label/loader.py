"""
White-label branding loader for Parallax skills.

Reads ~/.parallax/client-branding/config.yaml, validates it against the
canonical schema, resolves logo paths, and returns a normalised dict.
Called on every skill invocation — optimised to be silent on success.

Public interface
----------------
    load_client_branding() -> dict[str, Any]
    build_config_from_draft(draft, validation_summary=None) -> dict[str, Any]

Return shape (always 9 top-level keys)
---------------------------------------
    {
        "client_name":       str,              # "" when no config
        "colors":            dict | {},
        "logos":             dict | {},
        "fonts":             dict | {},
        "source":            dict | {},
        "confidence_scores": dict | {},
        "voice":             dict | {},        # {"enabled": False} if not extracted
        "multi_source":      dict | {},        # populated only when 2+ sources used
        "error":             str | None,       # None = clean load
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
                        "type":       {"type": "string", "enum": ["url", "pdf", "pptx", "docx", "wizard", "multi", "folder-voice-only"]},
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
        "voice": {
            "type": "object",
            "properties": {
                "enabled":     {"type": "boolean"},
                "positioning": {"type": "string"},
                "tone": {
                    "type": "object",
                    "properties": {
                        "register":           {"type": "string"},
                        "primary_attributes": {"type": "array"},
                        "avoid_attributes":   {"type": "array"},
                    },
                },
                "core_rules":          {"type": "array"},
                "anti_filler":         {"type": "array"},
                "audience_adaptation": {"type": "array"},
                "channel_notes":       {"type": "array"},
                "drafted_vs_sent":     {"type": "array"},
                "company_context":     {"type": "string"},
                "disclaimers":         {"type": "array"},
                "source_corpus": {
                    "type": "object",
                    "properties": {
                        "documents":  {"type": "array"},
                        "word_count": {"type": "integer", "minimum": 0},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "notes":      {"type": "string"},
                    },
                },
            },
        },
        "multi_source": {
            "type": "object",
            "properties": {
                "sources":    {"type": "array"},
                "mismatches": {"type": "array"},
                "agreements": {"type": "array"},
            },
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
    """Canonical 9-key empty result dict with a populated error field."""
    return {
        "client_name":       "",
        "colors":            {},
        "logos":             {},
        "fonts":             {},
        "source":            {},
        "confidence_scores": {},
        "voice":             {"enabled": False},
        "multi_source":      {},
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
        try:
            expanded = Path(str(raw_path)).expanduser()
        except (TypeError, ValueError) as exc:
            resolved[key] = ""
            msg = f"logo_missing: {key} invalid path value: {raw_path!r}"
            warnings.append(msg)
            logger.warning("White-label logo invalid path — key=%s error=%s", key, exc)
            continue

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
    Assemble the canonical 9-key result dict from validated, logo-resolved data.

    *logo_warnings* are joined into the error field when present; error is
    None on a fully clean load.
    """
    branding = data.get("branding", {})
    metadata = data.get("metadata", {})
    voice    = data.get("voice", {"enabled": False})
    multi    = data.get("multi_source", {})

    error: str | None = "; ".join(logo_warnings) if logo_warnings else None

    return {
        "client_name":       metadata.get("client_name", ""),
        "colors":            branding.get("colors", {}),
        "logos":             branding.get("logos", {}),
        "fonts":             branding.get("fonts", {}),
        "source":            metadata.get("source", {}),
        "confidence_scores": data.get("confidence_scores", {}),
        "voice":             voice,
        "multi_source":      multi,
        "error":             error,
    }


# ---------------------------------------------------------------------------
# Save-side helper — used by SKILL.md Step 4c at write time, and by tests
# to verify save → reload roundtrip integrity.
# ---------------------------------------------------------------------------


def _avg_confidence(confidence_scores: dict[str, float]) -> float:
    """Compute average confidence across all extracted fields. Returns 0.0 for empty."""
    if not confidence_scores:
        return 0.0
    return sum(confidence_scores.values()) / len(confidence_scores)


def build_config_from_draft(
    draft: dict[str, Any],
    validation_summary: dict[str, Any] | None = None,
    client_name: str = "",
    extracted_by: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Construct a canonical config.yaml dict from an extraction draft.

    This is the inverse of load_client_branding's parsing — it takes the
    in-memory draft produced by extract_from_pptx / extract_from_docx /
    extract_from_url / merge_drafts and assembles the dict that
    yaml.safe_dump should write.

    Used at SKILL.md Step 4c (save time) AND by tests (save → reload roundtrip).
    """
    src = draft.get("source", {}) or {}
    src_type = src.get("type", "wizard")
    src_ref = src.get("reference") or ""

    config: dict[str, Any] = {
        "metadata": {
            "schema_version": 1,
            "client_name":    client_name or draft.get("client_name", ""),
            "extracted_at":   draft.get("extracted_at", ""),
            "source": {
                "type":       src_type,
                "reference":  str(src_ref),
                "confidence": _avg_confidence(draft.get("confidence_scores", {})),
            },
            "extracted_by": extracted_by,
            "notes":        notes,
        },
        "branding": {
            "colors": {
                "primary":    draft.get("colors", {}).get("primary",    {}).get("hex", ""),
                "secondary":  draft.get("colors", {}).get("secondary",  {}).get("hex", ""),
                "accent":     draft.get("colors", {}).get("accent",     {}).get("hex", ""),
                "background": draft.get("colors", {}).get("background", {}).get("hex", "#FFFFFF"),
                "text":       draft.get("colors", {}).get("text",       {}).get("hex", "#333333"),
            },
            "logos": {
                "primary": (
                    draft.get("logos", {}).get("primary", {}).get("local_path")
                    or draft.get("logos", {}).get("primary", {}).get("path")
                    or draft.get("logos", {}).get("primary", {}).get("url", "")
                ),
                "favicon": (
                    draft.get("logos", {}).get("favicon", {}).get("local_path")
                    or draft.get("logos", {}).get("favicon", {}).get("path")
                    or draft.get("logos", {}).get("favicon", {}).get("url", "")
                ),
            },
            "fonts": {
                "header":    draft.get("fonts", {}).get("header",    {}).get("name", "Arial"),
                "body":      draft.get("fonts", {}).get("body",      {}).get("name", "Helvetica"),
                "monospace": draft.get("fonts", {}).get("monospace", {}).get("name", "Courier New"),
            },
        },
        "confidence_scores": draft.get("confidence_scores", {}),
    }

    if validation_summary is not None:
        config["validation_summary"] = validation_summary

    voice = draft.get("voice")
    if voice and voice.get("enabled"):
        config["voice"] = {
            "enabled":             True,
            "positioning":         voice.get("positioning", ""),
            "tone":                voice.get("tone", {"register": "", "primary_attributes": [], "avoid_attributes": []}),
            "core_rules":          voice.get("core_rules", []),
            "anti_filler":         voice.get("anti_filler", []),
            "audience_adaptation": voice.get("audience_adaptation", []),
            "channel_notes":       voice.get("channel_notes", []),
            "drafted_vs_sent":     voice.get("drafted_vs_sent", []),
            "company_context":     voice.get("company_context", ""),
            "disclaimers":         voice.get("disclaimers", []),
            "source_corpus":       voice.get("source_corpus", {
                "documents": [], "word_count": 0, "confidence": 0.0, "notes": "",
            }),
        }
    else:
        config["voice"] = {"enabled": False}

    if "multi_source" in draft:
        config["multi_source"] = draft["multi_source"]

    return config


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def load_client_branding() -> dict[str, Any]:
    """
    Load and validate client branding configuration.

    Returns a dict with exactly 9 keys: client_name, colors, logos, fonts,
    source, confidence_scores, voice, multi_source, error.  error is None on a
    fully clean load, a human-readable string on any degradation.

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
        # Preserve logo warnings alongside schema_unavailable
        if logo_warnings:
            result["error"] = "schema_unavailable; " + result["error"]
        else:
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
