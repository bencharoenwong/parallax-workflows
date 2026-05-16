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
            "required": ["colors", "logos"],
            "oneOf": [
                {
                    # v1 schema
                    "required": ["fonts"],
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
                        "fonts": {
                            "type": "object",
                            "required": ["header", "body", "monospace"],
                            "properties": {
                                "header":    {"type": "string"},
                                "body":      {"type": "string"},
                                "monospace": {"type": "string"},
                            },
                        },
                    }
                },
                {
                    # v2 schema
                    "required": ["typography"],
                    "properties": {
                        "colors": {
                            "type": "object",
                            "required": ["primary", "secondary", "tertiary", "neutral"],
                            "properties": {
                                "primary":   {"type": "string"},
                                "secondary": {"type": "string"},
                                "tertiary":  {"type": "string"},
                                "neutral":   {"type": "string"},
                            },
                        },
                        "typography": {
                            "type": "object",
                            "minProperties": 1
                        },
                        "rounded": {"type": "object"},
                        "spacing": {"type": "object"},
                        "components": {"type": "object"}
                    }
                }
            ],
            "properties": {
                "logos": {
                    "type": "object",
                    "required": ["primary", "favicon"],
                    "properties": {
                        "primary": {"type": "string"},
                        "favicon": {"type": "string"},
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


def _detect_schema_version(data: dict[str, Any]) -> int:
    metadata = data.get("metadata", {})
    if "schema_version" in metadata and isinstance(metadata["schema_version"], int):
        return metadata["schema_version"]
    # Heuristic
    colors = data.get("branding", {}).get("colors", {})
    if "tertiary" in colors and "accent" not in colors:
        return 2
    return 1

def _normalize_branding_v2_to_return_shape(data: dict[str, Any]) -> dict[str, Any]:
    branding = data.get("branding", {})
    colors_v2 = branding.get("colors", {})
    typo_v2 = branding.get("typography", {})
    components_v2 = branding.get("components", {})

    # Resolve components.body-text.textColor for the legacy `text` slot.
    # The DESIGN.md spec encourages token-refs like "{colors.primary}" inside
    # components, but downstream consumers expect colors.text to be a literal
    # hex. Resolve the token-ref against colors_v2 when possible; fall back to
    # empty (rather than leaking the raw "{colors.X}" string) when the ref
    # points nowhere we can resolve. Symmetric with the defensive handling in
    # _config_to_draft.
    raw_text_color = components_v2.get("body-text", {}).get("textColor", "")
    if isinstance(raw_text_color, str) and raw_text_color.startswith("{colors."):
        ref_key = raw_text_color.strip("{}").split(".", 1)[-1]
        resolved_text = colors_v2.get(ref_key, "")
        # Don't resolve to another token-ref (defends against chained refs)
        if isinstance(resolved_text, str) and resolved_text.startswith("{"):
            resolved_text = ""
    else:
        resolved_text = raw_text_color

    colors_legacy = {
        "primary":    colors_v2.get("primary", ""),
        "secondary":  colors_v2.get("secondary", ""),
        "accent":     colors_v2.get("tertiary", ""),
        "background": colors_v2.get("neutral", ""),
        "text":       resolved_text,
    }
    fonts_legacy = {
        "header":    typo_v2.get("h1", {}).get("fontFamily", ""),
        "body":      typo_v2.get("body-md", {}).get("fontFamily", ""),
        "monospace": typo_v2.get("code", {}).get("fontFamily", ""),
    }
    return {
        "colors":     colors_legacy,
        "fonts":      fonts_legacy,
        "typography": typo_v2,
        "rounded":    branding.get("rounded", {}),
        "spacing":    branding.get("spacing", {}),
        "components": components_v2,
    }

def _config_to_draft(cfg: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct a synthetic draft dict from an on-disk config.yaml.

    Inverse of build_config_from_draft, used by /parallax-white-label-onboard
    --regenerate-design-md so emit_design_md can be re-run without re-extracting
    from source. Works for both v1 (accent/background/text + fonts.*) and v2
    (tertiary/neutral/components.body-text + typography.*) shapes.

    Confidence is set to 1.0 on every reconstructed field — these values came
    from a previously-confirmed config, not a fresh extraction.
    """
    branding = cfg.get("branding", {}) or {}
    colors_in = branding.get("colors", {}) or {}
    fonts_in = branding.get("fonts", {}) or {}
    typo_in = branding.get("typography", {}) or {}
    components_in = branding.get("components", {}) or {}

    # Canonical legacy color slots regardless of v1/v2 on disk.
    # Defensive: if a user hand-edited config.yaml to use a {colors.X} token
    # reference (DESIGN.md spec encourages it inside components), we cannot
    # resolve the literal hex here without a token-resolution pass — emit_design_md
    # would then ValueError on the hex-validation gate. Skip token-refs and let
    # the caller fall back to the raw color from the colors map.
    raw_text = (components_in.get("body-text", {}) or {}).get("textColor", "")
    legacy_text = colors_in.get("text") or (
        raw_text if not (isinstance(raw_text, str) and raw_text.startswith("{")) else ""
    )
    legacy_background = colors_in.get("background") or colors_in.get("neutral", "")
    legacy_accent = colors_in.get("accent") or colors_in.get("tertiary", "")

    def _col(value: str) -> dict[str, Any]:
        # Refuse token-refs ('{colors.primary}') — only literal hex is valid here.
        if isinstance(value, str) and value.startswith("{"):
            return {}
        return {"hex": value, "confidence": 1.0} if value else {}

    draft: dict[str, Any] = {
        "colors": {
            k: v
            for k, v in {
                "primary": _col(colors_in.get("primary", "")),
                "secondary": _col(colors_in.get("secondary", "")),
                "accent": _col(legacy_accent),
                "background": _col(legacy_background),
                "text": _col(legacy_text),
            }.items()
            if v
        },
        "logos": {
            role: ({"local_path": ref, "confidence": 1.0} if isinstance(ref, str) and ref else {})
            for role, ref in (branding.get("logos", {}) or {}).items()
        },
        "fonts": {
            role: ({"name": name, "confidence": 1.0} if name else {})
            for role, name in {
                "header": fonts_in.get("header", "") or (typo_in.get("h1", {}) or {}).get("fontFamily", ""),
                "body": fonts_in.get("body", "") or (typo_in.get("body-md", {}) or {}).get("fontFamily", ""),
                "monospace": fonts_in.get("monospace", "") or (typo_in.get("code", {}) or {}).get("fontFamily", ""),
            }.items()
        },
        "source": (cfg.get("metadata", {}) or {}).get(
            "source", {"type": "regenerated-from-config", "reference": ""}
        ),
        "extracted_at": (cfg.get("metadata", {}) or {}).get("extracted_at", ""),
        "confidence_scores": {},
    }

    # v2 token tree (used by emit_design_md when present; absent = emitter
    # falls back to fonts.*)
    if typo_in:
        draft["typography"] = typo_in
    if branding.get("rounded"):
        draft["rounded"] = branding["rounded"]
    if branding.get("spacing"):
        draft["spacing"] = branding["spacing"]

    return draft


def archive_legacy_config(config_path: Path) -> Path:
    from datetime import datetime, timezone
    import shutil
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    archive_dir = config_path.parent / ".archive" / f"{ts}-pre-v2-migration"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / "config.yaml"
    shutil.copy2(config_path, archive_path)
    return archive_path

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

    version = _detect_schema_version(data)
    if version >= 2:
        norm = _normalize_branding_v2_to_return_shape(data)
        colors = norm["colors"]
        fonts = norm["fonts"]
        extra = {
            "typography": norm["typography"],
            "rounded": norm["rounded"],
            "spacing": norm["spacing"],
            "components": norm["components"],
        }
    else:
        colors = branding.get("colors", {})
        fonts = branding.get("fonts", {})
        extra = {}

    error: str | None = "; ".join(logo_warnings) if logo_warnings else None

    return {
        "client_name":       metadata.get("client_name", ""),
        "colors":            colors,
        "logos":             branding.get("logos", {}),
        "fonts":             fonts,
        "source":            metadata.get("source", {}),
        "confidence_scores": data.get("confidence_scores", {}),
        "voice":             voice,
        "multi_source":      multi,
        "error":             error,
        **extra
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
    *, schema_version: int = 2
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
            "schema_version": schema_version,
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
        },
        "confidence_scores": draft.get("confidence_scores", {}),
    }

    if schema_version >= 2:
        config["branding"]["colors"] = {
            "primary":    draft.get("colors", {}).get("primary",    {}).get("hex", ""),
            "secondary":  draft.get("colors", {}).get("secondary",  {}).get("hex", ""),
            "tertiary":   draft.get("colors", {}).get("accent",     {}).get("hex", ""),
            "neutral":    draft.get("colors", {}).get("background", {}).get("hex", "#FFFFFF"),
        }
        
        # Use default typography if missing
        typography = draft.get("typography", {})
        if not typography:
            typography = {
                "h1": {"fontFamily": "Arial"},
                "body-md": {"fontFamily": "Helvetica"},
                "code": {"fontFamily": "Courier New"}
            }
        config["branding"]["typography"] = typography
        
        if "rounded" in draft and draft["rounded"]:
            config["branding"]["rounded"] = draft["rounded"]
        if "spacing" in draft and draft["spacing"]:
            config["branding"]["spacing"] = draft["spacing"]
            
        components = draft.get("components", {})
        if not components and "text" in draft.get("colors", {}):
            components = {
                "body-text": {
                    "backgroundColor": "{colors.neutral}",
                    "textColor": draft["colors"]["text"]["hex"]
                }
            }
        config["branding"]["components"] = components
    else:
        config["branding"]["colors"] = {
            "primary":    draft.get("colors", {}).get("primary",    {}).get("hex", ""),
            "secondary":  draft.get("colors", {}).get("secondary",  {}).get("hex", ""),
            "accent":     draft.get("colors", {}).get("accent",     {}).get("hex", ""),
            "background": draft.get("colors", {}).get("background", {}).get("hex", "#FFFFFF"),
            "text":       draft.get("colors", {}).get("text",       {}).get("hex", "#333333"),
        }
        config["branding"]["fonts"] = {
            "header":    draft.get("fonts", {}).get("header",    {}).get("name", "Arial"),
            "body":      draft.get("fonts", {}).get("body",      {}).get("name", "Helvetica"),
            "monospace": draft.get("fonts", {}).get("monospace", {}).get("name", "Courier New"),
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
