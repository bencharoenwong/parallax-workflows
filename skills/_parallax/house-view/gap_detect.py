#!/usr/bin/env python3
"""Gap detection for house-view ingest (SKILL.md Step 2.5).

Identifies dimensions in the extracted draft view that are candidates for
fill-in from the Parallax data-driven macro view. A "fillable gap" requires
all three:

  1. Eligible dimension. macro_regime / factors / regions / sectors only.
     Pillars (Phase 0 encoding-only), themes (CIO judgment, free-form),
     styles (no clean Parallax mapping), and excludes (policy/ethical) are
     never gap-fillable.

  2. Currently silent OR low-confidence non-zero.
       - Silent: value is 0/None AND the field name (or any prose alias)
         does not appear in prose.md or extraction.extraction_notes. This
         distinguishes "extractor saw nothing about this" from "extractor
         explicitly concluded neutral after seeing it."
       - Low-confidence: value is non-zero but the dimension's
         extraction_confidence < 0.4. The Parallax suggestion is offered
         as a replacement candidate.

  3. Source mode is not "manual" (wizard inputs are explicit by
     construction — no extractor uncertainty to fill).

This module does not call MCP tools. It returns a typed list of Gap
records that gap_suggest.py uses to drive sourcing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Gap-fill activation gate: a non-zero field with extraction_confidence
# below this threshold is offered as a replacement candidate (the Parallax
# suggestion may overwrite). Distinct from loader.md §2 step 7's 0.6
# *consumer-warning* gate (which surfaces low-confidence fields in the
# load preamble but never overrides them). 0.4 is set conservatively
# below 0.6 so a field that merely warrants a "verify before acting"
# warning at load is NOT auto-flagged for replacement at ingest — only
# fields the extractor itself was substantially uncertain about (<0.4)
# trigger the override path.
LOW_CONFIDENCE_THRESHOLD = 0.4

ELIGIBLE_DIMENSIONS = ("macro_regime", "factors", "regions", "sectors")

# Long-tail region keys that no major bank's primary house view covers at
# named-country granularity. Silent-by-default — skipped from gap flagging
# UNLESS the source prose explicitly mentions them (in which case the
# normal silent-AND-not-mentioned check still fires for an explicit override).
# Discovered via cross-doc gap-detect comparison of LO 2024 vs UBS Mar 2026:
# 6 of 26 unique silent leaves were silent in BOTH banks. Adding leaves to
# this set should be evidence-based — only after observing N>=2 banks both
# silent on a given leaf. See notes/2026-04-26-step-2-5-validation.md OBS-13a.
LOW_COVERAGE_REGIONS = frozenset({
    "apac_ex_japan",
    "chile",
    "mena",
    "philippines",
    "vietnam",
    # NOTE: thailand removed 2026-04-26 — now covered per list_macro_countries.
    # Long-tail demotion is about banks-don't-opine, NOT about Parallax-can't-cover.
    # The Parallax-coverage-gap surface is handled by gap_suggest.report_skipped_leaves()
    # at plan time, not by this deny-list.
})

# Informational only — exclusion is enforced by the ELIGIBLE_DIMENSIONS
# allowlist (see _iter_dimension_leaves). Adding a dimension here without
# also handling it in ELIGIBLE_DIMENSIONS has NO effect; this tuple exists
# to document Phase 0 boundary intent for future contributors.
EXCLUDED_DIMENSIONS = ("pillars", "themes", "styles", "tilt_conviction")

# Aliases for prose-mention detection. Keys are canonical schema keys; values
# are alternate surface forms an extractor may have used in prose. Match is
# case-insensitive substring; underscores in canonical keys are also matched
# as spaces.
PROSE_ALIASES: dict[str, list[str]] = {
    # Sectors
    "information_technology": ["tech", "technology", "info_tech", "it sector", "semis", "software"],
    "communication_services": ["comms", "communications", "telecom", "media"],
    "consumer_discretionary": ["discretionary", "cons disc", "consumer disc"],
    "consumer_staples": ["staples", "cons staples"],
    "health_care": ["healthcare", "health", "biotech", "pharma"],
    "real_estate": ["reit", "reits", "real estate"],
    "financials": ["financial", "banks", "bank"],
    "industrials": ["industrial"],
    "materials": ["mining", "chemicals"],
    "utilities": ["utility"],
    "energy": ["oil", "gas"],
    # Factors
    "low_volatility": ["low vol", "low-vol", "defensive", "min vol", "minimum volatility"],
    "profitability": ["quality", "qmj", "roe"],
    "momentum": ["mom", "trend"],
    "value": ["cheap", "deep value"],
    "trading_signals": ["technicals", "short-term signals"],
    # Regions — most country names match by stripping underscores; only add
    # genuinely non-obvious aliases.
    "us": ["united states", "america", "u.s.", "u.s"],
    "uk": ["united kingdom", "britain"],
    "south_korea": ["korea", "kospi"],
    "hong_kong": ["hk", "hkex"],
    "em_ex_china": ["em ex china", "emerging ex-china"],
    "apac_ex_japan": ["apac ex japan", "asia ex-japan"],
    # Macro regime sub-fields
    "growth": ["expansion", "recession", "slowdown", "soft landing"],
    "inflation": ["disinflation", "cpi", "core pce"],
    "rates": ["fed", "rate cut", "rate hike", "monetary policy"],
    "risk_appetite": ["risk-on", "risk-off", "roro"],
}


@dataclass(frozen=True)
class Gap:
    """A dimension of the draft view that is a candidate for Parallax gap-fill."""

    field_path: str  # e.g., "tilts.regions.mexico" or "tilts.macro_regime.inflation"
    dimension: str  # one of ELIGIBLE_DIMENSIONS
    leaf_key: str  # e.g., "mexico", "inflation"
    current_value: Any  # int, str, or None
    current_confidence: float  # 0.0-1.0; from extraction_confidence[dimension]
    reason: str  # "silent" or "low_confidence"
    aliases_checked: tuple[str, ...] = field(default_factory=tuple)


def _normalize_haystack(text: str) -> str:
    """Lowercase + collapse underscores/dashes to spaces for substring matching."""
    return re.sub(r"[_\-]+", " ", (text or "").lower())


def _aliases_for(leaf_key: str) -> list[str]:
    """All surface forms to search for when deciding if prose mentions this leaf."""
    spaced = leaf_key.replace("_", " ")
    base = [leaf_key.lower(), spaced.lower()]
    extras = PROSE_ALIASES.get(leaf_key, [])
    return base + [a.lower() for a in extras]


def _is_mentioned(leaf_key: str, haystack_normalized: str) -> bool:
    """True iff any alias for leaf_key appears as a whole-word match in haystack.

    Uses word-boundary regex to avoid false positives from short keys (e.g.,
    "us" matching inside "cautious") and short aliases ("it" inside "it's").
    Aliases that are themselves multi-word (e.g., "united states") match
    when their boundary terms appear consecutively, which the underlying
    \\b regex handles correctly.
    """
    for alias in _aliases_for(leaf_key):
        if not alias:
            continue
        pattern = r"\b" + re.escape(alias) + r"\b"
        if re.search(pattern, haystack_normalized):
            return True
    return False


def _is_silent_value(value: Any, dimension: str) -> bool:
    """True iff this value should be treated as 'no view'.

    For numeric tilts (sectors, regions, factors): 0 / None / missing.
    For macro_regime sub-fields: None / missing / "neutral" sentinel
    (per schema.yaml the sub-fields are nullable string tokens; loader
    treats null as 'no view' explicitly).
    """
    if value is None:
        return True
    if dimension == "macro_regime":
        # macro_regime sub-fields are string tokens; loader.md §3 treats
        # null/absent as "no auto-tilt", but a literal "neutral" string is
        # an active assertion (uploader took a view). Only null/empty is
        # silent.
        return value == "" or value == "null"
    # Numeric tilts.
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)) and value == 0:
        return True
    return False


def _confidence_for(dimension: str, extraction_confidence: dict[str, float]) -> float:
    """Read the dimension-level confidence; default 0.0 when missing."""
    try:
        return float(extraction_confidence.get(dimension, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _iter_dimension_leaves(
    tilts: dict[str, Any], dimension: str
) -> list[tuple[str, Any]]:
    """Return [(leaf_key, value)] for the eligible dimension's direct children.

    sectors / regions / factors / macro_regime are flat maps in schema.yaml;
    pillars (excluded) and styles (excluded) have nested structure but we
    don't visit them here.
    """
    block = tilts.get(dimension) or {}
    if not isinstance(block, dict):
        return []
    return [(k, v) for k, v in block.items()]


def detect_gaps(
    draft_view: dict[str, Any],
    prose: str = "",
    extraction_notes: str = "",
    source_type: str = "pdf",
) -> list[Gap]:
    """Identify fillable gaps in a draft house view.

    Args:
        draft_view: The post-Step-2 draft, must include `tilts` and
            `extraction.extraction_confidence`.
        prose: Verbatim CIO narrative (for prose-mention detection).
        extraction_notes: extraction.extraction_notes free-text.
        source_type: extraction.source_type. "manual" (wizard) skips entirely.

    Returns:
        Ordered list of Gap records (dimension order: macro_regime, factors,
        regions, sectors; alphabetical within dimension).
    """
    if source_type == "manual":
        return []

    tilts = draft_view.get("tilts") or {}
    extraction = draft_view.get("extraction") or {}
    confidence_map = extraction.get("extraction_confidence") or {}

    haystack = _normalize_haystack(prose + "\n" + extraction_notes)
    gaps: list[Gap] = []

    for dimension in ELIGIBLE_DIMENSIONS:
        dim_confidence = _confidence_for(dimension, confidence_map)
        leaves = _iter_dimension_leaves(tilts, dimension)
        for leaf_key, value in sorted(leaves):
            silent = _is_silent_value(value, dimension)
            mentioned = _is_mentioned(leaf_key, haystack)

            # OBS-13a long-tail demotion: regions in LOW_COVERAGE_REGIONS are
            # silent-by-default. Skip flagging unless the source explicitly
            # mentioned them (in which case the absent-explicit branch below
            # would not have fired anyway — but the low-confidence override
            # branch still applies if the leaf was non-zero).
            if (
                dimension == "regions"
                and leaf_key in LOW_COVERAGE_REGIONS
                and silent
                and not mentioned
            ):
                continue

            if silent and not mentioned:
                gaps.append(
                    Gap(
                        field_path=f"tilts.{dimension}.{leaf_key}",
                        dimension=dimension,
                        leaf_key=leaf_key,
                        current_value=value,
                        current_confidence=dim_confidence,
                        reason="silent",
                        aliases_checked=tuple(_aliases_for(leaf_key)),
                    )
                )
            elif (not silent) and dim_confidence < LOW_CONFIDENCE_THRESHOLD:
                gaps.append(
                    Gap(
                        field_path=f"tilts.{dimension}.{leaf_key}",
                        dimension=dimension,
                        leaf_key=leaf_key,
                        current_value=value,
                        current_confidence=dim_confidence,
                        reason="low_confidence",
                        aliases_checked=tuple(_aliases_for(leaf_key)),
                    )
                )

    return gaps


def is_eligible_dimension(dimension: str) -> bool:
    """Public guard used by gap_suggest and tests to enforce Phase 0 boundary."""
    return dimension in ELIGIBLE_DIMENSIONS


__all__ = [
    "Gap",
    "detect_gaps",
    "is_eligible_dimension",
    "ELIGIBLE_DIMENSIONS",
    "EXCLUDED_DIMENSIONS",
    "LOW_CONFIDENCE_THRESHOLD",
    "LOW_COVERAGE_REGIONS",
    "PROSE_ALIASES",
]
