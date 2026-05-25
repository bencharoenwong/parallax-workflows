"""
White-label branding loader for Parallax skills.

Reads ~/.parallax/client-branding/config.yaml, validates it against the
canonical schema, resolves logo paths, and returns a normalised dict.
Called on every skill invocation — optimised to be silent on success.

Public interface
----------------
    load_client_branding() -> dict[str, Any]
        Full 13-key shape (visual + voice + token tree). Voice consumers only.
    load_visual_branding() -> dict[str, Any]
        Visual-only 6-key subset (client_name, colors, logos, fonts, source,
        error). Structurally excludes voice/typography/multi_source — accessing
        e.g. result["voice"] raises KeyError. Use from any visual-rendering
        consumer skill.
    build_config_from_draft(draft, validation_summary=None) -> dict[str, Any]

Return shape (always 13 top-level keys, identical on success and error paths)
-----------------------------------------------------------------------------
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
        # v2-aware bonus keys — empty dicts on v1 configs and on every error
        # path, so consumers can read result["typography"] etc. unconditionally.
        "typography":        dict | {},
        "rounded":           dict | {},
        "spacing":           dict | {},
        "components":        dict | {},
    }
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

try:
    import jsonschema as _jsonschema
    _HAS_JSONSCHEMA = True
except ImportError:
    _jsonschema = None
    _HAS_JSONSCHEMA = False

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

_CONFIG_PATH: Path = Path.home() / ".parallax" / "client-branding" / "config.yaml"
_SCHEMA_PATH: Path = Path(__file__).parent / "schema.yaml"

# Stable logger namespace regardless of how consumers import this module
# (sys.path.insert style imports make __name__ == "loader", which is too
# generic and collides with any other loader.py on sys.path).
logger = logging.getLogger("parallax.white_label.loader")

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
            # anyOf (not oneOf) so a hand-edited or partially-migrated config
            # carrying BOTH v1 markers (fonts + colors.accent) and v2 markers
            # (typography + colors.tertiary) still validates — _detect_schema_version
            # disambiguates downstream by preferring v2 when both are present.
            # Pre-check via _detect_hybrid_branding() surfaces a clearer error
            # message in the load path when the operator should clean up the file.
            "anyOf": [
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


# _SCHEMA is _SCHEMA_UNPROBED on import; _get_schema() probes schema.yaml on
# each call when still unprobed, avoiding the upgrade-time race where
# schema.yaml is absent at import time. Tests that monkeypatch _SCHEMA to a
# concrete dict OR to None continue to work — the sentinel _SCHEMA_UNPROBED
# is what triggers the re-probe, NOT a bare None (which means "explicitly
# unavailable, skip validation").
_SCHEMA_UNPROBED: object = object()
_SCHEMA: dict[str, Any] | None | object = _SCHEMA_UNPROBED


def _get_schema() -> dict[str, Any] | None:
    """
    Return the active schema dict, or None if schema.yaml is unavailable.

    If _SCHEMA is still the _SCHEMA_UNPROBED sentinel, probe disk via
    _load_schema_or_none() and cache the result. If _SCHEMA has been set to a
    concrete value (dict OR None) by a prior probe or by a test monkeypatch,
    return it directly.
    """
    global _SCHEMA
    if _SCHEMA is _SCHEMA_UNPROBED:
        _SCHEMA = _load_schema_or_none()
    return _SCHEMA  # type: ignore[return-value]

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolve_config_path() -> Path:
    """Return the module-level config path.  Tests monkeypatch _CONFIG_PATH."""
    return _CONFIG_PATH


def _empty_result(error: str) -> dict[str, Any]:
    """Canonical 13-key empty result dict with a populated error field.

    Matches the success-path shape from _build_result so v2-aware consumers
    reading result["typography"] / ["rounded"] / ["spacing"] / ["components"]
    don't KeyError on any error path.
    """
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
        "typography":        {},
        "rounded":           {},
        "spacing":           {},
        "components":        {},
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
    if not _HAS_JSONSCHEMA:
        return None
    try:
        _jsonschema.validate(instance=data, schema=schema)
        return None
    except _jsonschema.ValidationError as exc:
        return f"schema_invalid: {exc.message}"
    except _jsonschema.SchemaError as exc:
        return f"schema_invalid: bad schema — {exc.message}"


_LOGO_ALLOWED_EXTS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp", ".gif"}
)


def _resolve_logo_paths(
    logos: dict[str, str],
) -> tuple[dict[str, str], list[str]]:
    """
    Validate and resolve each logo path.

    Rejects paths whose extension is not in `_LOGO_ALLOWED_EXTS` (blocks
    `/etc/passwd`, `id_rsa`, `.env` and similar credential-disclosure cases)
    and paths that do not resolve to a file on disk. Empty-string values are
    treated as "no logo supplied" and silently resolve to "" with no warning.
    Rejection messages name only the key and reason category — the raw path
    is intentionally omitted from both the error string and the WARNING log,
    so operator paths do not leak into centralized logs or Provenance.

    Returns (resolved_logos_dict, list_of_warning_strings).
    """
    resolved: dict[str, str] = {}
    warnings: list[str] = []

    def _reject(key: str, reason: str) -> None:
        resolved[key] = ""
        warnings.append(f"logo_missing: {key} {reason}")
        logger.warning("White-label logo rejected — key=%s reason=%s", key, reason)

    for key, raw_path in logos.items():
        if not isinstance(raw_path, str):
            _reject(key, "invalid path value")
            continue
        if not raw_path:
            # Deliberate "no logo" — not an error.
            resolved[key] = ""
            continue

        try:
            expanded = Path(raw_path).expanduser().resolve()
        except (TypeError, ValueError, OSError):
            _reject(key, "invalid path value")
            continue

        if expanded.suffix.lower() not in _LOGO_ALLOWED_EXTS:
            _reject(key, "extension not in image allowlist")
            continue

        if expanded.is_file():
            resolved[key] = str(expanded)
        else:
            _reject(key, "path not found")

    return resolved, warnings


def _detect_hybrid_branding(data: dict[str, Any]) -> str | None:
    """Return a human-readable description when branding has BOTH v1 and v2
    shape markers, else None. The anyOf schema would still accept this, but
    the result of the v1↔v2 bridge in `_normalize_branding_v2_to_return_shape`
    is ambiguous — clean up the file rather than guessing which shape wins.
    """
    branding = data.get("branding", {}) or {}
    colors = branding.get("colors", {}) or {}
    has_v1_color_markers = bool({"accent", "background", "text"} & set(colors.keys()))
    has_v2_color_markers = bool({"tertiary", "neutral"} & set(colors.keys()))
    has_v1_fonts = bool(branding.get("fonts"))
    has_v2_typo = bool(branding.get("typography"))

    conflicts = []
    if has_v1_color_markers and has_v2_color_markers:
        v1_keys = sorted({"accent", "background", "text"} & set(colors.keys()))
        v2_keys = sorted({"tertiary", "neutral"} & set(colors.keys()))
        conflicts.append(f"colors has both v1 ({', '.join(v1_keys)}) and v2 ({', '.join(v2_keys)}) keys")
    if has_v1_fonts and has_v2_typo:
        conflicts.append("branding has both `fonts.*` (v1) and `typography.*` (v2)")
    if not conflicts:
        return None
    return "; ".join(conflicts) + ". Run /parallax-white-label-onboard to re-extract, or remove the v1 keys (accent/background/text/fonts) when migrating to v2."


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
    branding = data.get("branding", {}) or {}
    colors_v2 = branding.get("colors", {}) or {}
    typo_v2 = branding.get("typography", {}) or {}
    components_v2 = branding.get("components", {}) or {}

    # Resolve components.body-text.textColor for the legacy `text` slot.
    # The DESIGN.md spec encourages token-refs like "{colors.primary}" inside
    # components, but downstream consumers expect colors.text to be a literal
    # hex. Resolve the token-ref against colors_v2 when possible; fall back to
    # empty (rather than leaking the raw "{colors.X}" string) when the ref
    # points nowhere we can resolve. Symmetric with the defensive handling in
    # _config_to_draft.
    raw_text_color = (components_v2.get("body-text", {}) or {}).get("textColor", "")
    if isinstance(raw_text_color, str) and raw_text_color.startswith("{"):
        # Token-refs of any shape must not leak. Try to resolve {colors.X};
        # any other ref ({typography.X}, malformed) collapses to empty so a
        # downstream hex-validation gate doesn't see "{...}" as a hex value.
        ref_body = raw_text_color.strip("{}")
        if ref_body.startswith("colors."):
            resolved_text = colors_v2.get(ref_body.split(".", 1)[-1], "")
            if isinstance(resolved_text, str) and resolved_text.startswith("{"):
                resolved_text = ""
        else:
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
    Assemble the canonical 13-key result dict from validated, logo-resolved data.

    The four v2 token-tree keys (typography, rounded, spacing, components) are
    populated unconditionally — as empty dicts on v1 configs — so consumers
    can read them with ``[]`` without ``KeyError``. *logo_warnings* are
    joined into the error field when present; error is None on a fully clean
    load.
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
        # v1 has no token tree, but populate empty dicts for the v2 bonus keys
        # so consumers can read them with `[]` access without KeyError. The
        # docstring promises this shape.
        extra = {
            "typography": {},
            "rounded": {},
            "spacing": {},
            "components": {},
        }

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
        
        # Derive typography from draft. Priority:
        #   1. explicit draft.typography (extractor populated it)
        #   2. draft.fonts.* fallback (extractor only set font names; wizard
        #      mode or v1 PDF source)
        #   3. generic CSS family-name placeholder ("sans-serif") so the v2
        #      schema's `typography: minProperties: 1` constraint is satisfied
        #      and the config remains loadable on next read. Using a CSS
        #      generic family rather than a specific name (Arial / Helvetica)
        #      makes the placeholder obvious — the operator sees "sans-serif"
        #      and knows no real typography was extracted.
        typography = draft.get("typography", {}) or {}
        if not typography:
            fonts_in = draft.get("fonts", {}) or {}
            font_map = (("header", "h1"), ("body", "body-md"), ("monospace", "code"))
            for legacy_role, design_level in font_map:
                slot = fonts_in.get(legacy_role) or {}
                name = slot.get("name") if isinstance(slot, dict) else None
                if name:
                    typography[design_level] = {"fontFamily": name}
        if not typography:
            typography = {"body-md": {"fontFamily": "sans-serif"}}
        config["branding"]["typography"] = typography

        if "rounded" in draft and draft["rounded"]:
            config["branding"]["rounded"] = draft["rounded"]
        if "spacing" in draft and draft["spacing"]:
            config["branding"]["spacing"] = draft["spacing"]

        components = draft.get("components", {})
        if not components and "text" in draft.get("colors", {}):
            # Defensive .get() — draft.colors.text may be present as an empty
            # or partial dict (e.g., wizard mode where the operator skipped
            # text color), which would KeyError on bare indexing.
            text_hex = draft["colors"]["text"].get("hex", "") if isinstance(draft["colors"]["text"], dict) else ""
            if text_hex:
                components = {
                    "body-text": {
                        "backgroundColor": "{colors.neutral}",
                        "textColor": text_hex,
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

    Returns a dict with a fixed 13-key shape on every path (success, error,
    schema-unavailable, v1, v2): client_name, colors, logos, fonts, source,
    confidence_scores, voice, multi_source, error, typography, rounded,
    spacing, components. error is None on a fully clean load, a
    human-readable string on any degradation.

    On v1 configs and on every error path, the four token-tree keys
    (typography, rounded, spacing, components) are populated as empty dicts
    so consumers can read them with ``[]`` access without ``KeyError``.
    On v2 configs the keys carry the derived token tree. Downstream
    consumers reading only the legacy 9 keys are unaffected by the v1↔v2
    distinction.

    Visual-rendering skills should prefer :func:`load_visual_branding`,
    which exposes only the visual subset and refuses to leak voice/voice
    data. Use this full-shape loader only when voice consumption is part
    of the skill contract.

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
    active_schema = _get_schema()
    if active_schema is None:
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
    # Hybrid-shape pre-check: a hand-edited config that carries BOTH the v1
    # font/colors keys AND the v2 typography/colors keys passes anyOf
    # validation but signals operator confusion. Surface a clearer error
    # than the generic jsonschema message.
    _hybrid_branding_check = _detect_hybrid_branding(data)
    if _hybrid_branding_check is not None:
        logger.warning("White-label config has hybrid v1+v2 shape: %s", _hybrid_branding_check)
        return _empty_result(f"schema_invalid: hybrid_v1_v2: {_hybrid_branding_check}")
    schema_error = _validate_schema(data, active_schema)
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


_VISUAL_BRANDING_KEYS: tuple[str, ...] = (
    "client_name",
    "colors",
    "logos",
    "fonts",
    "source",
    "error",
)


def load_visual_branding() -> dict[str, Any]:
    """
    Visual-branding-only subset of :func:`load_client_branding`.

    Returns the six keys a visual-rendering skill is permitted to read:
    ``client_name``, ``colors``, ``logos``, ``fonts``, ``source``, ``error``.

    Voice prose and v2-only token-tree keys (``typography``, ``rounded``,
    ``spacing``, ``components``, ``multi_source``, ``confidence_scores``) are
    excluded. This is a structural guardrail: a skill that mistakenly tries
    to read ``branding["voice"]["tone"]`` raises ``KeyError`` instead of
    silently inheriting voice data.

    Voice-consuming skills (CIO letter, newsletter pipeline, future writing
    skills) must continue to call :func:`load_client_branding` directly and
    document their voice-handling contract in their own SKILL.md.

    Error-state contract is identical to :func:`load_client_branding`:
    ``error`` is ``None`` on clean load, ``"config_not_found"`` when no
    client is onboarded, or a degradation string otherwise.

    Raises:
        KeyError: if :func:`load_client_branding` violates its return-shape
            contract by omitting one of the visual keys. This is intentional
            — silent fallback would mask the upstream bug.
    """
    full = load_client_branding()
    return {key: full[key] for key in _VISUAL_BRANDING_KEYS}


# Error prefixes whose data is usable for white-label rendering. The match is
# substring-anywhere (not prefix-only) so combined paths like
# "schema_unavailable; logo_missing: …" still resolve to active.
_ACTIVE_ERROR_TOKENS: tuple[str, ...] = ("logo_missing", "schema_unavailable")


def is_white_label_active(branding: dict[str, Any]) -> bool:
    """Return True when the loader produced palette/font data the consumer
    should apply, False when the consumer should render default Parallax.

    Active: error is None, or contains "logo_missing", or contains
    "schema_unavailable" (best-effort branch). Everything else (config_not_found,
    schema_invalid, yaml_parse_error) falls back to default Parallax.

    Single source of truth for the rendering flag; consumer SKILL.md files
    call this rather than re-implementing the predicate.
    """
    err = branding.get("error")
    if err is None:
        return True
    return any(token in err for token in _ACTIVE_ERROR_TOKENS)


def safe_source_reference(branding: dict[str, Any]) -> str:
    """Display-safe representation of branding["source"]["reference"] for
    embedding in end-client deliverables.

    URLs collapse to scheme+hostname; filesystem paths collapse to basename;
    other strings pass through. Prevents leaking pre-signed URLs, internal
    paths, or full-source URLs into the Provenance footer.
    """
    ref = (branding.get("source") or {}).get("reference", "")
    if not isinstance(ref, str) or not ref:
        return ""
    if ref.startswith(("http://", "https://")):
        from urllib.parse import urlparse
        parsed = urlparse(ref)
        return f"{parsed.scheme}://{parsed.hostname}" if parsed.hostname else ""
    if ref.startswith(("/", "~")):
        return Path(ref).name
    return ref
