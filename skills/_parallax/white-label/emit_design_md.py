import importlib.util
from pathlib import Path
from typing import Any

import yaml


def _load_color_validator():
    # Resolve ColorValidator by absolute path so this module works whether it is
    # imported as a package (skills._parallax.white_label.emit_design_md) or
    # loaded directly from disk (the existing skill machinery uses importlib for
    # sibling modules in this hyphenated directory, which is not a valid Python
    # package identifier).
    validator_path = Path(__file__).resolve().parent / "validator.py"
    spec = importlib.util.spec_from_file_location(
        "parallax_white_label_validator", validator_path
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ColorValidator


ColorValidator = _load_color_validator()

def _frontmatter_dict(draft: dict[str, Any]) -> dict[str, Any]:
    # Hex validation gate
    for role in ("primary", "secondary", "accent", "background", "text"):
        if role in draft.get("colors", {}):
            val = draft["colors"][role].get("hex")
            if val:
                if not ColorValidator.is_valid_hex(val):
                    raise ValueError(f"invalid hex at colors.{role}: {val}")

    out = {}
    out["colors"] = {}
    if "primary" in draft.get("colors", {}):
        out["colors"]["primary"] = draft["colors"]["primary"]["hex"].upper()
    if "secondary" in draft.get("colors", {}):
        out["colors"]["secondary"] = draft["colors"]["secondary"]["hex"].upper()
    if "accent" in draft.get("colors", {}):
        out["colors"]["tertiary"] = draft["colors"]["accent"]["hex"].upper()
    if "background" in draft.get("colors", {}):
        out["colors"]["neutral"] = draft["colors"]["background"]["hex"].upper()
    
    if not out["colors"]:
        del out["colors"]

    if "typography" in draft:
        out["typography"] = draft["typography"].copy()
    else:
        out["typography"] = {}

    # v1 fallback: when typography.* is absent or partial, fill from legacy
    # fonts.{header,body,monospace} so /parallax-white-label-onboard
    # --regenerate-design-md on an old config still produces a complete
    # DESIGN.md. fonts.header → typography.h1, fonts.body → typography.body-md,
    # fonts.monospace → typography.code. typography.* takes precedence when
    # both are present (typography is the v2 source of truth).
    legacy_font_map = (
        ("header", "h1"),
        ("body", "body-md"),
        ("monospace", "code"),
    )
    fonts = draft.get("fonts", {}) or {}
    for legacy_role, design_level in legacy_font_map:
        if design_level in out["typography"]:
            continue
        slot = fonts.get(legacy_role) or {}
        name = slot.get("name") if isinstance(slot, dict) else None
        if name:
            out["typography"][design_level] = {"fontFamily": name}

    if not out["typography"]:
        del out["typography"]

    if "rounded" in draft and draft["rounded"]:
        out["rounded"] = draft["rounded"].copy()

    if "spacing" in draft and draft["spacing"]:
        out["spacing"] = draft["spacing"].copy()

    # Components wire each declared color token to a semantic surface via
    # {colors.<name>} token-refs so the linter's `orphaned-tokens` rule passes.
    # Canonical mapping (matches the DESIGN.md spec README example):
    #   primary   → body-text ink (typography surface)
    #   secondary → caption / border accents
    #   tertiary  → primary call-to-action surface
    #   neutral   → page background
    out["components"] = {}
    colors_in = draft.get("colors", {})

    if "background" in colors_in:
        body_text = {"backgroundColor": "{colors.neutral}"}
        if "primary" in colors_in:
            body_text["textColor"] = "{colors.primary}"
        elif "text" in colors_in:
            body_text["textColor"] = colors_in["text"]["hex"].upper()
        out["components"]["body-text"] = body_text

    if "secondary" in colors_in and "background" in colors_in:
        out["components"]["caption"] = {
            "backgroundColor": "{colors.neutral}",
            "textColor": "{colors.secondary}",
        }

    if "accent" in colors_in:
        # button-primary textColor: pick the higher-contrast of neutral (light
        # paper) and primary (dark ink) against tertiary. Warm accents like
        # #FF6600 fail WCAG against white but pass easily against dark ink;
        # cool accents are the inverse. Compute via ColorValidator's contrast
        # helper rather than hardcoding the assumption.
        button_primary = {"backgroundColor": "{colors.tertiary}"}
        tertiary_hex = colors_in["accent"].get("hex", "")
        primary_hex = colors_in.get("primary", {}).get("hex", "")
        neutral_hex = colors_in.get("background", {}).get("hex", "")

        candidates = [
            ("{colors.primary}", primary_hex),
            ("{colors.neutral}", neutral_hex),
        ]
        scored = []
        for ref, candidate_hex in candidates:
            if not candidate_hex:
                continue
            try:
                ratio = ColorValidator.wcag_contrast_ratio(candidate_hex, tertiary_hex)
            except (AttributeError, ValueError):
                ratio = 0.0
            scored.append((ratio, ref))

        if scored:
            scored.sort(reverse=True)
            button_primary["textColor"] = scored[0][1]
        elif "background" in colors_in:
            button_primary["textColor"] = "{colors.neutral}"

        out["components"]["button-primary"] = button_primary

    if not out["components"]:
        del out["components"]

    return out

def _body_sections(draft: dict[str, Any], client_name: str, source_refs: list[str]) -> str:
    brand_guide = draft.get("brand_guide_prose", {})
    
    def get_prose(key: str, default: str) -> str:
        if key in brand_guide:
            return brand_guide[key]
        return default

    overview = get_prose("overview", f"Brand guidelines for {client_name}. Sources: {', '.join(source_refs) if source_refs else 'None'}.")
    colors = get_prose("colors", f"The brand color palette defines the visual identity. Primary token: {{colors.primary}}.")
    typography = get_prose("typography", "Typography scale for consistent text rendering. Heading reference: {typography.h1}.")
    layout = get_prose("layout", "Layout and spacing guidelines. Base spacing: {spacing.md}.")
    elevation = get_prose("elevation_depth", "Elevation guidelines are not strictly defined.")
    shapes = get_prose("shapes", "Shape corner radii. Reference: {rounded.md}.")
    components = get_prose("components", "Component tokens. Body text uses: {components.body-text}.")
    dos_and_donts = get_prose("dos_and_donts", "Follow these guidelines strictly.")

    return f"""## Overview
{overview}

## Colors
{colors}

## Typography
{typography}

## Layout
{layout}

## Elevation & Depth
{elevation}

## Shapes
{shapes}

## Components
{components}

## Do's and Don'ts
{dos_and_donts}
"""

def emit_design_md(draft: dict[str, Any], *, client_name: str, extracted_at: str, source_refs: list[str]) -> str:
    frontmatter = _frontmatter_dict(draft)
    
    # Custom float formatting for PyYAML
    class NoZeroFloatDumper(yaml.SafeDumper):
        pass

    def float_representer(dumper, value):
        text = repr(value)
        if text.endswith(".0"):
            text = text[:-2]
        return dumper.represent_scalar('tag:yaml.org,2002:float', text)

    NoZeroFloatDumper.add_representer(float, float_representer)

    frontmatter_yaml = yaml.dump(frontmatter, Dumper=NoZeroFloatDumper, sort_keys=False, default_flow_style=False, allow_unicode=True)
    body = _body_sections(draft, client_name, source_refs)
    
    return f"---\n{frontmatter_yaml}---\n{body}"
