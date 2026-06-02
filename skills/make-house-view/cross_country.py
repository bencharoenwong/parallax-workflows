"""Cross-country aggregator.

Folds per-market `macro_analyst` responses (5 components per market) +
telemetry into a single `aggregated` dict consumed by `pillar_compose`
and the prose synthesizer.

Coverage rule (60% — v2 plan §4.3 / BUG-009 resolution):
- For each output field, compute responded_weight / total_weight across
  the markets that returned usable data for that field.
- >= 0.60: emit aggregated value with weights renormalized over the
  responded subset; weighted MEDIAN, not mean (median is robust to
  one-market outliers in a 14-market mix).
- < 0.60: emit NULL with coverage_warning + force pillar confidence to 0.
- Per-region tilts (single-market): bypass the threshold.

PARTIAL handling (MCP_FIELD_INVENTORY.md §5.4):
- macro_analyst that returns success=True but with prose like "Sector
  ranking data remains unavailable for this reporting period" → treat
  as silent for that component. Detected via _is_silent_content.

Pure-compute module — no MCP calls.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Reuse the pillar_formulas prose-scan primitives without depending on its
# constants (keeps cross_country independent of pillar formula confidence
# math).
_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from pillar_formulas import (  # noqa: E402
    _ENTROPY_PATTERN,
    _VALUATION_PATTERN,
    _scan_prose_for_signed_number,
)

# Reuse the sector and region prose-extraction logic from gap_suggest so
# the maker speaks the same language as gap_detect / gap_suggest. JIT path
# to the shared dir.
_SHARED_DIR = (_HERE / ".." / "_parallax" / "house-view").resolve()
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from gap_suggest import (  # noqa: E402
    REGION_MARKET_MAP,
    macro_analyst_to_region_tilt,
    macro_analyst_to_sector_tilts,
)


COVERAGE_THRESHOLD = 0.60

# Default aggregator weights file (v0 / heuristic_phase0).
DEFAULT_WEIGHTS_PATH = _SHARED_DIR / "aggregator_weights.yaml"

# Sector keys we attempt to extract per-market.
_SECTOR_KEYS = (
    "energy", "materials", "industrials", "consumer_discretionary",
    "consumer_staples", "health_care", "financials",
    "information_technology", "communication_services", "utilities",
    "real_estate",
)

# Prose markers signalling that the component returned data-empty
# (component succeeded but had no data layer to report). MCP_FIELD_INVENTORY.md §5.4.
_DATA_EMPTY_PATTERNS = (
    "data remains unavailable",
    "data is unavailable",
    "ranking data remains unavailable",
    "no data available",
    "data not yet available",
    "no signals available",
)


# Schema-key (e.g. "us") → live macro_analyst market name (e.g. "United States").
# Inverse of REGION_MARKET_MAP — used to translate between weight-file
# region keys and the per-market response dict.
MARKET_NAME_TO_SCHEMA_KEY = {v: k for k, v in REGION_MARKET_MAP.items()}


@dataclass
class MarketResponse:
    """One market's bundle of component responses.

    Each component value is the raw `macro_analyst(market=M, component=C)`
    response dict, or None when the call failed / timed out / was skipped.
    """

    market_name: str  # e.g. "United States" (Parallax-side)
    schema_key: str  # e.g. "us" (view schema-side)
    components: dict[str, dict[str, Any] | None]  # component_name -> response dict
    reachable: bool = True  # False if every component is None
    partial_components: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Weight loading
# ---------------------------------------------------------------------------


def load_weights(weights_path: Path | str | None = None) -> dict[str, Any]:
    """Load aggregator_weights.yaml. Returns the full parsed dict.

    Caller treats `global_macro_weights` as the primary; sector falls back
    to it when `global_sector_weights` is null.
    """
    import yaml

    path = Path(weights_path) if weights_path else DEFAULT_WEIGHTS_PATH
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def get_market_weight(weights: dict[str, Any], schema_key: str) -> float:
    """Return the v0 weight for a schema_key (e.g. 'us'). Missing → 0.0."""
    macro = weights.get("global_macro_weights") or {}
    return float(macro.get(schema_key, 0.0))


# ---------------------------------------------------------------------------
# Per-market parsing
# ---------------------------------------------------------------------------


def _is_silent_content(content: str) -> bool:
    """Detect PARTIAL responses per MCP_FIELD_INVENTORY.md §5.4."""
    if not content:
        return True
    lowered = content.lower()
    for pat in _DATA_EMPTY_PATTERNS:
        if pat in lowered:
            return True
    return False


def _get_content(component_response: dict[str, Any] | None) -> str:
    if not component_response:
        return ""
    if not isinstance(component_response, dict):
        return ""
    return component_response.get("content") or ""


def market_response_phi(
    market: MarketResponse,
) -> tuple[float | None, str | None]:
    """Extract valuation float for one market from its macro_indicators prose.

    Returns (value, snippet) or (None, None) if silent.
    """
    content = _get_content(market.components.get("macro_indicators"))
    if _is_silent_content(content):
        return None, None
    match = _scan_prose_for_signed_number(_VALUATION_PATTERN, content)
    if match is None:
        return None, None
    val, snippet = match
    return val, f"[{market.market_name}] {snippet}"


def market_response_xi(market: MarketResponse) -> tuple[float | None, str | None]:
    """Extract entropy float for one market from its macro_indicators prose."""
    content = _get_content(market.components.get("macro_indicators"))
    if _is_silent_content(content):
        return None, None
    match = _scan_prose_for_signed_number(_ENTROPY_PATTERN, content)
    if match is None:
        return None, None
    val, snippet = match
    return val, f"[{market.market_name}] {snippet}"


def market_response_region_tilt(market: MarketResponse) -> int | None:
    """Single-market region tilt — bypasses coverage threshold."""
    # Build a synthetic response so gap_suggest's parser sees both
    # macro_indicators and tactical components if present.
    mi = market.components.get("macro_indicators")
    tac = market.components.get("tactical")
    if not mi and not tac:
        return None
    synth: dict[str, Any] = {}
    if mi:
        synth["components"] = {"macro_indicators": {"content": _get_content(mi)}}
        if tac:
            synth["components"]["tactical"] = {"content": _get_content(tac)}
    elif tac:
        synth["components"] = {"tactical": {"content": _get_content(tac)}}
    result = macro_analyst_to_region_tilt(synth, market.schema_key)
    if result is None:
        return None
    value, _snippet = result
    return value


def market_response_sectors(
    market: MarketResponse,
) -> dict[str, int]:
    """Per-sector tilts extracted from this market's sectors component."""
    sectors_resp = market.components.get("sectors")
    if not sectors_resp:
        return {}
    content = _get_content(sectors_resp)
    if _is_silent_content(content):
        return {}
    # Reuse gap_suggest's sector extractor via the standard live shape.
    synth = {
        "component": "sector_positioning",
        "content": content,
    }
    extracted = macro_analyst_to_sector_tilts(synth, list(_SECTOR_KEYS))
    return {k: v for k, (v, _snippet) in extracted.items()}


def market_response_news_blob(market: MarketResponse) -> str:
    """Concatenated news/sentiment prose for judgment."""
    news = market.components.get("news")
    return _get_content(news)


# ---------------------------------------------------------------------------
# Coverage-gated aggregation primitives
# ---------------------------------------------------------------------------


def _weighted_median(values_weights: list[tuple[float, float]]) -> float:
    """Weighted median; values sorted, cumulative weight crosses 0.5.

    On exact tie between two values, returns their arithmetic mean.
    """
    if not values_weights:
        return 0.0
    sorted_vw = sorted(values_weights, key=lambda x: x[0])
    total = sum(w for _, w in sorted_vw)
    if total <= 0:
        return 0.0
    cumulative = 0.0
    half = total / 2.0
    prev_val: float | None = None
    for val, w in sorted_vw:
        cumulative += w
        if cumulative >= half:
            # Tie-detection for exact midpoint.
            if abs(cumulative - half) < 1e-12 and prev_val is not None:
                return (prev_val + val) / 2.0
            return val
        prev_val = val
    return sorted_vw[-1][0]


def aggregate_field_with_coverage(
    per_market_values: dict[str, float],
    weights: dict[str, float],
) -> tuple[float | None, bool, list[str]]:
    """Aggregate a per-market dict via weighted median, gated by coverage.

    Args:
        per_market_values: {schema_key: value} for markets that produced
            a numeric value. Markets that were silent are NOT keys here.
        weights: {schema_key: weight} from aggregator_weights.yaml
            (the FULL weight table, not just responded markets).

    Returns:
        (aggregated_value_or_None, coverage_ok, markets_with_data)
    """
    total_weight = sum(weights.values()) or 0.0
    if total_weight <= 0:
        return None, False, []
    responded_weight = sum(weights.get(k, 0.0) for k in per_market_values)
    if total_weight <= 0:
        coverage = 0.0
    else:
        coverage = responded_weight / total_weight

    markets = sorted(per_market_values.keys())

    if coverage < COVERAGE_THRESHOLD:
        return None, False, markets

    # Renormalize over responded subset.
    norm = sum(weights.get(k, 0.0) for k in per_market_values) or 1.0
    vw = [(v, weights.get(k, 0.0) / norm) for k, v in per_market_values.items()]
    return _weighted_median(vw), True, markets


# ---------------------------------------------------------------------------
# Top-level aggregator
# ---------------------------------------------------------------------------


def aggregate(
    per_market_responses: list[MarketResponse],
    telemetry: dict[str, Any] | None,
    weights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fold per-market responses + telemetry into a single `aggregated` dict.

    Output schema (consumed by pillar_compose + prose_synth):

        {
          "phi": {value, coverage_ok, markets_with_data, snippets},
          "xi":  {value, coverage_ok, markets_with_data, snippets},
          "psi_news_blobs": [str, ...],
          "macro_regime": {"growth": <token>, "inflation": ..., ...},
          "regions": {schema_key: int},   # per-region tilts (bypass coverage)
          "sectors": {sector_key: int},   # aggregated; coverage-gated
          "fan_out_summary": {
              "markets_total": int,
              "markets_succeeded": int,
              "markets_unreachable": int,
              "markets_partial": int,
          },
          "field_coverage": {field: {responded, total, coverage_ok}},
        }

    All non-None numeric fields are floats; the caller rounds to -2..+2
    when packaging tilts. Pillar compose treats coverage_ok=False as a
    missing_input signal.
    """
    if weights is None:
        weights = load_weights()
    weight_map = weights.get("global_macro_weights") or {}

    succeeded: list[MarketResponse] = []
    unreachable: list[MarketResponse] = []
    partial: list[MarketResponse] = []
    for m in per_market_responses:
        if not m.reachable:
            unreachable.append(m)
        elif m.partial_components:
            partial.append(m)
            succeeded.append(m)
        else:
            succeeded.append(m)

    # --- prose extraction per market ---
    phi_per_market: dict[str, float] = {}
    phi_snippets: list[str] = []
    for m in succeeded:
        val, snippet = market_response_phi(m)
        if val is not None:
            phi_per_market[m.schema_key] = val
            if snippet:
                phi_snippets.append(snippet)

    phi_val, phi_cov_ok, phi_markets = aggregate_field_with_coverage(
        phi_per_market, weight_map
    )
    if not phi_per_market:
        phi_cov_ok = False
        phi_val = None

    # --- prose extraction per market ---
    xi_per_market: dict[str, float] = {}
    xi_snippets: list[str] = []
    for m in succeeded:
        val, snippet = market_response_xi(m)
        if val is not None:
            xi_per_market[m.schema_key] = val
            if snippet:
                xi_snippets.append(snippet)

    xi_val, _xi_cov_ok, xi_markets = aggregate_field_with_coverage(
        xi_per_market, weight_map
    )

    # --- news blobs ---
    psi_blobs: list[str] = []
    for m in succeeded:
        blob = market_response_news_blob(m)
        if blob:
            psi_blobs.append(f"[{m.market_name}] {blob[:1200]}")

    # --- Per-region tilts (single-market, bypass coverage) ---
    regions: dict[str, int] = {}
    for m in succeeded:
        tilt = market_response_region_tilt(m)
        if tilt is not None:
            regions[m.schema_key] = tilt

    # --- Sectors aggregated via coverage rule ---
    # Per-sector accumulator: {sector_key: {schema_key: int}}
    sector_per_market: dict[str, dict[str, float]] = {}
    for m in succeeded:
        sector_tilts = market_response_sectors(m)
        for sector_key, tilt in sector_tilts.items():
            sector_per_market.setdefault(sector_key, {})[m.schema_key] = float(tilt)

    sectors_aggregated: dict[str, float] = {}
    sectors_coverage: dict[str, dict[str, Any]] = {}
    for sector_key, per_mkt in sector_per_market.items():
        val, cov_ok, markets = aggregate_field_with_coverage(per_mkt, weight_map)
        sectors_coverage[sector_key] = {
            "responded_markets": markets,
            "coverage_ok": cov_ok,
        }
        if cov_ok and val is not None:
            sectors_aggregated[sector_key] = val

    # --- Macro regime from telemetry ---
    telemetry = telemetry or {}
    regime_tag = telemetry.get("regime_tag") or ""
    macro_regime: dict[str, str | None] = {
        "growth": _infer_growth_token(regime_tag),
        "inflation": None,
        "rates": None,
        "risk_appetite": _infer_risk_token(regime_tag),
    }

    return {
        "phi": {
            "value": phi_val,
            "coverage_ok": phi_cov_ok,
            "markets_with_data": phi_markets,
            "snippets": phi_snippets,
        },
        "xi": {
            "value": xi_val,
            "coverage_ok": _xi_cov_ok,
            "markets_with_data": xi_markets,
            "snippets": xi_snippets,
        },
        "psi_news_blobs": psi_blobs,
        "macro_regime": macro_regime,
        "regions": regions,
        "sectors": sectors_aggregated,
        "sectors_coverage": sectors_coverage,
        "fan_out_summary": {
            "markets_total": len(per_market_responses),
            "markets_succeeded": len(succeeded),
            "markets_unreachable": len(unreachable),
            "markets_partial": len(partial),
            "unreachable_markets": [m.market_name for m in unreachable],
        },
    }


def _infer_growth_token(regime_tag: str) -> str | None:
    """Map regime_tag to a growth token (matches gap_suggest vocabulary)."""
    if not regime_tag:
        return None
    t = regime_tag.lower()
    if "expansion" in t:
        return "expansion"
    if "reflation" in t:
        return "reflationary"
    if "slowing" in t or "soft landing" in t or "slowdown" in t:
        return "slowing"
    if "recession" in t or "contraction" in t:
        return "recessionary"
    if "rotation" in t or "selective" in t:
        return "neutral"
    return None


def _infer_risk_token(regime_tag: str) -> str | None:
    if not regime_tag:
        return None
    t = regime_tag.lower()
    if "risk-on" in t or "risk on" in t:
        return "risk_on"
    if "risk-off" in t or "risk off" in t:
        return "risk_off"
    return None


__all__ = [
    "COVERAGE_THRESHOLD",
    "MarketResponse",
    "aggregate",
    "aggregate_field_with_coverage",
    "load_weights",
    "get_market_weight",
    "MARKET_NAME_TO_SCHEMA_KEY",
]
