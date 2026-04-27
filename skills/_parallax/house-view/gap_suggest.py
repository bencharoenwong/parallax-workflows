#!/usr/bin/env python3
"""Parallax data-driven gap-fill sourcing for house-view consumer skills.

JIT-loaded alongside `gap_detect.py` by downstream consumer skills (e.g.
/parallax-portfolio-builder --augment-silent) to fill silent dimensions
with current Parallax data, scoped per-portfolio. Pairs with `gap_detect`.
Given a list of detected Gaps, this module:

  1. Plans the MCP calls that need to be made (`plan_calls`). One call per
     unique (tool, args) tuple — covered regions get one `macro_analyst`
     call each in parallel; sectors share a single US `macro_analyst` call;
     macro_regime + factors share a single `get_telemetry` call.

  2. Folds MCP responses into typed `Suggestion` records (`fold_responses`).
     Pure functions over the response dicts — the skill (Claude) makes the
     actual MCP calls and feeds responses back in.

The folding mappings are intentionally simple and conservative:

  - macro_regime: parses get_telemetry regime_tag for keyword tokens.
  - factors: derives factor tilts from the same regime_tag using loader.md
    §3 (forward application — regime implies factor deltas).
  - regions: parses macro_analyst's macro_indicators / tactical components
    for an aggregate constructive/cautious read, mapped to -2..+2.
  - sectors: parses macro_analyst.sector_positioning matrix.

Phase 0 boundary: pillars / themes / styles / excludes are NEVER suggested.
A hard-coded test asserts this in tests/test_gap_suggest.py.

Graceful degradation: when a response is missing the expected fields or
the mapping yields no conviction (|value| < 1), the helper returns None
for that leaf — no Suggestion is emitted, the field stays silent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from gap_detect import Gap, is_eligible_dimension

# ---------------------------------------------------------------------------
# Region / market mapping — schema-key → Parallax market-name translation.
# This is the STABLE half of the coverage logic; the LIVE half (which
# markets are currently online) is supplied at plan time via the
# `available_markets` parameter on plan_calls(). When available_markets is
# None, ALL entries below are eligible (current behavior, back-compat).
#
# Adding a market here requires: (a) confirming the schema region key
# (e.g. "south_korea") matches the Parallax market name format
# ("South Korea"), and (b) verifying the market shows up in
# list_macro_countries() before relying on it in production.
#
# OBS-16 follow-up (2026-04-26): the SKILL.md Step 2.5 instructions now
# call list_macro_countries() at plan time and pass available_markets in,
# so coverage drift (e.g., Thailand coming online 2026-04 between code
# revisions) is discovered automatically. The static REGION_MARKET_MAP
# below covers schema-key translation; the live list filters it.
# ---------------------------------------------------------------------------
REGION_MARKET_MAP: dict[str, str] = {
    "us": "United States",
    "canada": "Canada",
    "uk": "United Kingdom",
    "germany": "Germany",
    "france": "France",
    "japan": "Japan",
    "china": "China",
    "india": "India",
    "south_korea": "South Korea",
    "singapore": "Singapore",
    "malaysia": "Malaysia",
    "thailand": "Thailand",  # added 2026-04-26 (newly covered per list_macro_countries)
}

# ---------------------------------------------------------------------------
# Macro regime keyword extraction from telemetry regime_tag + commentary.
# Conservative — only fires when keywords are unambiguous. Returns None
# (no suggestion) when the signal is ambiguous.
# ---------------------------------------------------------------------------
_GROWTH_TOKENS = {
    "expansion": ["expansion", "expansionary", "robust growth"],
    "reflationary": ["reflation", "reflationary", "re-acceleration"],
    "neutral": ["neutral growth", "trend growth"],
    "slowing": ["slowing", "slowdown", "deceleration", "soft landing"],
    "recessionary": ["recession", "recessionary", "contraction"],
}
_INFLATION_TOKENS = {
    "disinflation": ["disinflation", "disinflationary", "falling inflation"],
    "benign": ["benign inflation", "well-behaved", "anchored"],
    "sticky": ["sticky inflation", "supercore sticky", "persistent core"],
    "accelerating": ["accelerating inflation", "rising inflation", "re-acceleration"],
}
_RATES_TOKENS = {
    "cutting": ["rate cut", "cutting cycle", "easing cycle", "rate cuts"],
    "holding": ["on hold", "holding rates", "pause"],
    "hiking": ["rate hike", "hiking cycle", "tightening cycle"],
}
_RISK_APPETITE_TOKENS = {
    "risk_on": ["risk-on", "risk on", "roro on"],
    "risk_off": ["risk-off", "risk off", "flight to quality", "haven bid"],
    "neutral": ["mixed risk appetite"],
}

# Regime → factor delta. Mirrors loader.md §3 macro-regime mapping table
# in the forward direction. Values are absolute factor tilts to suggest
# (not deltas to add — gap-fill targets silent fields, so the delta IS the
# tilt). Magnitudes capped at ±2 per schema scale.
_REGIME_TO_FACTOR: dict[tuple[str | None, str | None], dict[str, int]] = {
    # (growth, inflation) → factor tilts
    ("recessionary", None): {"low_volatility": 2, "momentum": -1},
    ("slowing", "sticky"): {"low_volatility": 1, "profitability": 1, "momentum": -1},
    ("reflationary", None): {"value": 1, "momentum": 1},
    ("expansion", "benign"): {"momentum": 1},
}


@dataclass(frozen=True)
class CallSpec:
    """An MCP call the skill should make to source gap-fill suggestions."""

    purpose: str  # "telemetry" | "regions" | "sectors"
    tool: str  # "get_telemetry" | "macro_analyst"
    args: dict[str, Any]
    covers_dimensions: tuple[str, ...]
    covers_leaves: tuple[str, ...]


@dataclass(frozen=True)
class Suggestion:
    """A Parallax-derived gap-fill candidate to present to the uploader."""

    field_path: str
    suggested_value: Any
    source_tool: str
    source_call_args: dict[str, Any]
    source_snippet: str
    data_as_of: str | None
    reason: str  # copied from Gap: "silent" or "low_confidence"
    notes: str = ""


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


def plan_calls(
    gaps: list[Gap],
    available_markets: list[str] | None = None,
) -> list[CallSpec]:
    """Group gaps into deduplicated MCP call specs.

    Returns specs in the order: telemetry first (covers macro_regime +
    factors), then one macro_analyst per covered region market, then a
    single US macro_analyst for sectors (if any sector gaps exist).
    The skill should fire all returned calls in parallel.

    Args:
        gaps: Output from gap_detect.detect_gaps().
        available_markets: Live coverage list from list_macro_countries(),
            e.g. ["United States", "Canada", "Thailand", ...]. When provided,
            REGION_MARKET_MAP entries are filtered to only those markets
            currently online — this catches coverage drift (new markets
            coming online, old markets going dark) without code changes.
            When None, ALL REGION_MARKET_MAP entries are eligible (current
            behavior; safe default for tests and back-compat).
    """
    # Phase 0 boundary check — should never fire if gap_detect respects
    # ELIGIBLE_DIMENSIONS, but defense in depth.
    for g in gaps:
        if not is_eligible_dimension(g.dimension):
            raise ValueError(
                f"Phase 0 violation: gap on ineligible dimension '{g.dimension}' "
                f"reached gap_suggest. field_path={g.field_path}"
            )

    # Filter the schema-key→market table by live coverage, when supplied.
    if available_markets is not None:
        live = set(available_markets)
        effective_market_map = {
            schema_key: market
            for schema_key, market in REGION_MARKET_MAP.items()
            if market in live
        }
    else:
        effective_market_map = REGION_MARKET_MAP

    by_dim: dict[str, list[Gap]] = {}
    for g in gaps:
        by_dim.setdefault(g.dimension, []).append(g)

    specs: list[CallSpec] = []

    needs_telemetry = bool(by_dim.get("macro_regime") or by_dim.get("factors"))
    if needs_telemetry:
        covers_dims: list[str] = []
        covers_leaves: list[str] = []
        if "macro_regime" in by_dim:
            covers_dims.append("macro_regime")
            covers_leaves.extend(g.leaf_key for g in by_dim["macro_regime"])
        if "factors" in by_dim:
            covers_dims.append("factors")
            covers_leaves.extend(g.leaf_key for g in by_dim["factors"])
        specs.append(
            CallSpec(
                purpose="telemetry",
                tool="get_telemetry",
                args={
                    "fields": ["regime_tag", "signals", "commentary"],
                },
                covers_dimensions=tuple(covers_dims),
                covers_leaves=tuple(covers_leaves),
            )
        )

    for g in by_dim.get("regions", []):
        market = effective_market_map.get(g.leaf_key)
        if market is None:
            # No Parallax coverage (or market offline today) — skip.
            continue
        specs.append(
            CallSpec(
                purpose="regions",
                tool="macro_analyst",
                args={"market": market},
                covers_dimensions=("regions",),
                covers_leaves=(g.leaf_key,),
            )
        )

    # Sector positioning anchored on the US response (consistent reference
    # market). Only fire if "United States" is in live coverage.
    if by_dim.get("sectors"):
        if available_markets is None or "United States" in available_markets:
            specs.append(
                CallSpec(
                    purpose="sectors",
                    tool="macro_analyst",
                    args={"market": "United States"},
                    covers_dimensions=("sectors",),
                    covers_leaves=tuple(g.leaf_key for g in by_dim["sectors"]),
                )
            )

    return specs


def report_skipped_leaves(
    gaps: list[Gap],
    available_markets: list[str] | None = None,
) -> dict[str, list[str]]:
    """Return per-dimension skipped leaves with the reason they were skipped.

    Used by Step 2.5 zero-state and partial-coverage banners so the IO sees
    HONEST coverage disclosure, not the misleading "checked N → 0 candidates"
    when we silently dropped uncovered regions.

    Returns:
        {"regions_no_coverage": [leaf_keys silently skipped because Parallax
         lacks macro_analyst coverage for that market today]}
    """
    if available_markets is not None:
        live = set(available_markets)
        live_market_map = {k: v for k, v in REGION_MARKET_MAP.items() if v in live}
    else:
        live_market_map = REGION_MARKET_MAP

    no_coverage = [
        g.leaf_key
        for g in gaps
        if g.dimension == "regions" and g.leaf_key not in live_market_map
    ]
    return {"regions_no_coverage": sorted(no_coverage)}


# ---------------------------------------------------------------------------
# Response folding helpers (pure functions; tests use mocked responses)
# ---------------------------------------------------------------------------


def _scan_tokens(haystack: str, table: dict[str, list[str]]) -> str | None:
    """Return the first table key whose synonyms appear in haystack."""
    h = (haystack or "").lower()
    for key, synonyms in table.items():
        for s in synonyms:
            if s in h:
                return key
    return None


def telemetry_to_macro_regime(
    response: dict[str, Any], leaves: list[str]
) -> dict[str, tuple[str, str]]:
    """Parse get_telemetry response into per-leaf (token, snippet) pairs.

    Args:
        response: get_telemetry response dict.
        leaves: subset of {growth, inflation, rates, risk_appetite} to map.

    Returns:
        dict leaf -> (suggested_token, source_snippet). Missing leaves
        are absent from the dict (no suggestion).
    """
    regime_tag = (response.get("regime_tag") or "")
    headline = ""
    commentary = response.get("commentary") or {}
    if isinstance(commentary, dict):
        headline = commentary.get("headline") or ""
    haystack = f"{regime_tag} {headline}"

    tables = {
        "growth": _GROWTH_TOKENS,
        "inflation": _INFLATION_TOKENS,
        "rates": _RATES_TOKENS,
        "risk_appetite": _RISK_APPETITE_TOKENS,
    }

    out: dict[str, tuple[str, str]] = {}
    for leaf in leaves:
        table = tables.get(leaf)
        if table is None:
            continue
        token = _scan_tokens(haystack, table)
        if token is None:
            continue
        snippet = haystack.strip()[:500]
        out[leaf] = (token, snippet)
    return out


def telemetry_to_factor_tilts(
    response: dict[str, Any], leaves: list[str]
) -> dict[str, tuple[int, str]]:
    """Derive factor tilts from telemetry regime_tag via loader.md §3.

    Conservative: only emits factor tilts when the regime_tag matches a
    known mapping row. No mapping → empty dict for that leaf.
    """
    regime = telemetry_to_macro_regime(response, ["growth", "inflation"])
    growth_token = regime.get("growth", (None, ""))[0]
    inflation_token = regime.get("inflation", (None, ""))[0]

    deltas: dict[str, int] = {}
    snippet = ""
    for (g_key, i_key), tilts in _REGIME_TO_FACTOR.items():
        g_match = (g_key is None) or (g_key == growth_token)
        i_match = (i_key is None) or (i_key == inflation_token)
        if g_match and i_match:
            for f, v in tilts.items():
                deltas[f] = v
            snippet = (
                f"Regime: growth={growth_token or 'unknown'}, "
                f"inflation={inflation_token or 'unknown'} → "
                f"loader.md §3 mapping"
            )

    return {f: (v, snippet) for f, v in deltas.items() if f in leaves}


_REGION_POSITIVE_TOKENS = [
    "constructive", "overweight", "favourable", "favorable",
    "improving", "supportive", "tailwind", "attractive", "bullish",
]
_REGION_NEGATIVE_TOKENS = [
    "cautious", "underweight", "headwind", "deteriorating",
    "vulnerable", "challenged", "bearish", "downgraded", "weak",
]


def _extract_component_text(response: dict[str, Any], component_name: str) -> str:
    """Pull prose content for one macro_analyst component across response shapes.

    Priority order (richest live shape first; legacy fallback last):
      1. Single-component live shape — `response["content"]` when
         `response["component"] == component_name`. Discriminator is exact;
         can't co-exist with the components-nested shape (singular vs plural).
      2. Live API overview shape — `response["components"][name]["content"]`.
         Canonical for current overview-mode responses.
      3. Top-level fallback — `response[name]` as string or dict
         (`{"content": ...}` / `{"summary": ...}`). Covers test fixtures and
         legacy callers. Last resort because if the live API ever returns
         BOTH a stale top-level summary AND nested current content, we want
         the nested current content to win.
    """
    # 1. Single-component live shape
    if response.get("component") == component_name and isinstance(response.get("content"), str):
        return response["content"]

    # 2. Nested under "components" (live API overview shape) — preferred over top-level
    components = response.get("components") or {}
    if isinstance(components, dict):
        nested = components.get(component_name)
        if isinstance(nested, str):
            return nested
        if isinstance(nested, dict):
            content = nested.get("content") or nested.get("summary")
            if content:
                return content

    # 3. Top-level fallback (test fixture / legacy)
    top = response.get(component_name)
    if isinstance(top, str):
        return top
    if isinstance(top, dict):
        return top.get("content") or top.get("summary") or ""

    return ""


def macro_analyst_to_region_tilt(
    response: dict[str, Any], leaf_key: str
) -> tuple[int, str] | None:
    """Parse macro_analyst response into a -2..+2 region tilt.

    Reads `macro_indicators` and `tactical` components across response
    shapes (live API nests under `components`, fixtures use top-level).
    Returns None when the signal is ambiguous.
    """
    text_blobs: list[str] = []
    mi_text = _extract_component_text(response, "macro_indicators")
    if mi_text:
        text_blobs.append(mi_text)
    tac_text = _extract_component_text(response, "tactical")
    if tac_text:
        text_blobs.append(tac_text)

    haystack = " ".join(text_blobs).lower()
    if not haystack.strip():
        return None

    pos = sum(1 for t in _REGION_POSITIVE_TOKENS if t in haystack)
    neg = sum(1 for t in _REGION_NEGATIVE_TOKENS if t in haystack)
    score = pos - neg
    # Heuristic token-count thresholds — NOT calibrated against the
    # `sec-macro-regime-deltas` methodology note in loader.md §3, which
    # protects Parallax's actual delta magnitudes. These cutoffs only
    # govern this skill's interpretation of macro_analyst prose for
    # gap-fill suggestion, and adjust freely if MCP response verbosity
    # changes.
    if score >= 3:
        value = 2
    elif score >= 1:
        value = 1
    elif score <= -3:
        value = -2
    elif score <= -1:
        value = -1
    else:
        return None

    snippet_source = " ".join(t for t in text_blobs if t)
    snippet = re.sub(r"\s+", " ", snippet_source).strip()[:500]
    return value, snippet


# Sector aliases for prose extraction (live API returns sector_positioning as
# narrative prose, not a structured key-value map). Keys are canonical schema
# keys; values are surface forms a macro analyst note may use.
_SECTOR_PROSE_ALIASES: dict[str, list[str]] = {
    "information_technology": ["information technology", "tech sector", "technology sector", "software", "semis"],
    "communication_services": ["communication services", "comm services", "telecom", "telecoms"],
    "consumer_discretionary": ["consumer discretionary", "discretionary"],
    "consumer_staples": ["consumer staples", "staples"],
    "health_care": ["health care", "healthcare"],
    "real_estate": ["real estate", "reits"],
    # NOTE: do NOT alias "banks" — fires on monetary policy prose ("Bank of
    # Canada", "central banks") that has nothing to do with sector positioning.
    # Macro analyst sector prose names "financials" or "banking sector" directly.
    "financials": ["financials", "banking sector"],
    "industrials": ["industrials"],
    "materials": ["materials"],
    "utilities": ["utilities"],
    "energy": ["energy"],
}

_SECTOR_POSITIVE_TOKENS = [
    "outperform", "outperforming", "leadership", "favored",
    "overweight", "advancement", "preferred", "constructive on",
    "command outperforming", "improvement", "strength",
    "rank 1", "rank 2", "rank 3",
]
_SECTOR_NEGATIVE_TOKENS = [
    "underperform", "underperforming", "underweight",
    "deterioration", "weakness", "compression", "lagging",
    "face underperformance", "facing", "decline",
    "rank 9", "rank 10", "rank 11",
]


def _extract_sector_from_prose(prose: str, leaf_key: str) -> int | None:
    """Score a sector's prose mentions for positive vs negative context.

    Splits prose into sentences, finds sentences mentioning the sector
    (any alias), counts pos/neg tokens within those sentences. Returns
    -1 / +1 on directional signal, None on ambiguous or absent.
    """
    aliases = _SECTOR_PROSE_ALIASES.get(leaf_key) or [leaf_key.replace("_", " ")]
    aliases_lower = [a.lower() for a in aliases]
    prose_lower = prose.lower()

    sentences = re.split(r"[.!?]\s+", prose_lower)
    pos = neg = 0
    for sentence in sentences:
        if not any(a in sentence for a in aliases_lower):
            continue
        for tok in _SECTOR_POSITIVE_TOKENS:
            if tok in sentence:
                pos += 1
        for tok in _SECTOR_NEGATIVE_TOKENS:
            if tok in sentence:
                neg += 1

    score = pos - neg
    if score >= 1:
        return 1
    if score <= -1:
        return -1
    return None


def macro_analyst_to_sector_tilts(
    response: dict[str, Any], leaves: list[str]
) -> dict[str, tuple[int, str]]:
    """Parse macro_analyst.sector_positioning into per-sector tilts.

    Three response shapes supported:
      - Structured dict: `response["sector_positioning"] = {sector: score}`
      - Structured list: `response["sector_positioning"] = [{sector, tilt}, ...]`
      - Prose: live API returns narrative content under
        `response["components"]["sector_positioning"]["content"]` (overview)
        or `response["content"]` when called with `component="sector_positioning"`.

    Returns empty dict on unknown shape.
    """
    sp = response.get("sector_positioning") or response.get("sectors")

    extracted: dict[str, int] = {}
    snippet = ""

    if isinstance(sp, dict):
        snippet = str(sp)[:500]
        for key, val in sp.items():
            if not isinstance(key, str):
                continue
            normalized = key.strip().lower().replace(" ", "_")
            if normalized not in leaves:
                continue
            v = _coerce_to_tilt(val)
            if v is not None and abs(v) >= 1:
                extracted[normalized] = v

    elif isinstance(sp, list):
        snippet = str(sp)[:500]
        for row in sp:
            if not isinstance(row, dict):
                continue
            key = row.get("sector") or row.get("name")
            val = row.get("tilt") or row.get("score") or row.get("positioning")
            if not isinstance(key, str):
                continue
            normalized = key.strip().lower().replace(" ", "_")
            if normalized not in leaves:
                continue
            v = _coerce_to_tilt(val)
            if v is not None and abs(v) >= 1:
                extracted[normalized] = v

    # If structured paths produced nothing, try prose extraction (live API shape).
    if not extracted:
        prose = _extract_component_text(response, "sector_positioning")
        if not prose:
            prose = _extract_component_text(response, "sectors")
        if prose:
            snippet = re.sub(r"\s+", " ", prose).strip()[:500]
            for leaf in leaves:
                tilt = _extract_sector_from_prose(prose, leaf)
                if tilt is not None and abs(tilt) >= 1:
                    extracted[leaf] = tilt

    return {k: (v, snippet) for k, v in extracted.items()}


def _coerce_to_tilt(val: Any) -> int | None:
    """Coerce a sector positioning value into -2..+2."""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        if val >= 1.5:
            return 2
        if val >= 0.5:
            return 1
        if val <= -1.5:
            return -2
        if val <= -0.5:
            return -1
        return 0
    if isinstance(val, str):
        s = val.strip().lower()
        mapping = {
            "overweight": 1, "ow": 1, "+1": 1,
            "strong overweight": 2, "big ow": 2, "+2": 2,
            "underweight": -1, "uw": -1, "-1": -1,
            "strong underweight": -2, "big uw": -2, "-2": -2,
            "neutral": 0, "0": 0,
        }
        return mapping.get(s)
    return None


# ---------------------------------------------------------------------------
# Folding orchestrator
# ---------------------------------------------------------------------------


def fold_responses(
    gaps: list[Gap],
    call_results: list[tuple[CallSpec, dict[str, Any]]],
) -> list[Suggestion]:
    """Convert call results into Suggestions.

    Args:
        gaps: original list from detect_gaps (preserves reason field).
        call_results: list of (CallSpec, response_dict) pairs in the order
            returned by plan_calls. Skipped specs (no response) should be
            omitted from the list.

    Returns:
        Suggestions in the same per-dimension order as gaps. Gaps without
        a derivable suggestion are absent from the result — no entry.
    """
    gaps_by_path = {g.field_path: g for g in gaps}
    suggestions: list[Suggestion] = []

    for spec, response in call_results:
        # Live API uses `report_date`; legacy fixtures use `as_of` / `data_as_of`.
        data_as_of = (
            response.get("as_of")
            or response.get("data_as_of")
            or response.get("report_date")
        )

        if spec.purpose == "telemetry":
            if "macro_regime" in spec.covers_dimensions:
                regime_leaves = [
                    g.leaf_key for g in gaps if g.dimension == "macro_regime"
                ]
                regime_map = telemetry_to_macro_regime(response, regime_leaves)
                for leaf, (token, snippet) in regime_map.items():
                    fp = f"tilts.macro_regime.{leaf}"
                    g = gaps_by_path.get(fp)
                    if g is None:
                        continue
                    suggestions.append(
                        Suggestion(
                            field_path=fp,
                            suggested_value=token,
                            source_tool=spec.tool,
                            source_call_args=spec.args,
                            source_snippet=snippet,
                            data_as_of=data_as_of,
                            reason=g.reason,
                        )
                    )
            if "factors" in spec.covers_dimensions:
                factor_leaves = [
                    g.leaf_key for g in gaps if g.dimension == "factors"
                ]
                factor_map = telemetry_to_factor_tilts(response, factor_leaves)
                for leaf, (value, snippet) in factor_map.items():
                    fp = f"tilts.factors.{leaf}"
                    g = gaps_by_path.get(fp)
                    if g is None:
                        continue
                    suggestions.append(
                        Suggestion(
                            field_path=fp,
                            suggested_value=value,
                            source_tool=spec.tool,
                            source_call_args=spec.args,
                            source_snippet=snippet,
                            data_as_of=data_as_of,
                            reason=g.reason,
                            notes="derived from regime_tag via loader.md §3",
                        )
                    )

        elif spec.purpose == "regions":
            for leaf_key in spec.covers_leaves:
                fp = f"tilts.regions.{leaf_key}"
                g = gaps_by_path.get(fp)
                if g is None:
                    continue
                tilt = macro_analyst_to_region_tilt(response, leaf_key)
                if tilt is None:
                    continue
                value, snippet = tilt
                suggestions.append(
                    Suggestion(
                        field_path=fp,
                        suggested_value=value,
                        source_tool=spec.tool,
                        source_call_args=spec.args,
                        source_snippet=snippet,
                        data_as_of=data_as_of,
                        reason=g.reason,
                    )
                )

        elif spec.purpose == "sectors":
            sector_leaves = list(spec.covers_leaves)
            sector_map = macro_analyst_to_sector_tilts(response, sector_leaves)
            for leaf, (value, snippet) in sector_map.items():
                fp = f"tilts.sectors.{leaf}"
                g = gaps_by_path.get(fp)
                if g is None:
                    continue
                suggestions.append(
                    Suggestion(
                        field_path=fp,
                        suggested_value=value,
                        source_tool=spec.tool,
                        source_call_args=spec.args,
                        source_snippet=snippet,
                        data_as_of=data_as_of,
                        reason=g.reason,
                    )
                )

    return suggestions


__all__ = [
    "CallSpec",
    "Suggestion",
    "plan_calls",
    "report_skipped_leaves",
    "fold_responses",
    "telemetry_to_macro_regime",
    "telemetry_to_factor_tilts",
    "macro_analyst_to_region_tilt",
    "macro_analyst_to_sector_tilts",
    "REGION_MARKET_MAP",
]
