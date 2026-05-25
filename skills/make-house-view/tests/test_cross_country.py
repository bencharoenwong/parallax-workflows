"""Unit tests for cross_country.aggregate + coverage rule."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import cross_country
from cross_country import (
    COVERAGE_THRESHOLD,
    MarketResponse,
    aggregate,
    aggregate_field_with_coverage,
    load_weights,
)


# ---------------------------------------------------------------------------
# Coverage threshold math
# ---------------------------------------------------------------------------


def test_coverage_below_threshold_returns_none():
    """When responded_weight/total_weight < 60%, return None + coverage_ok False."""
    weights = {"us": 0.55, "japan": 0.10, "china": 0.10, "uk": 0.25}
    # Only japan + china responded → 0.20 / 1.00 = 20% < 60%
    per_market = {"japan": 1.0, "china": -1.0}
    val, cov_ok, markets = aggregate_field_with_coverage(per_market, weights)
    assert val is None
    assert cov_ok is False
    assert set(markets) == {"japan", "china"}


def test_coverage_above_threshold_renormalizes_and_emits():
    """≥60% coverage → emit weighted median over responded subset."""
    weights = {"us": 0.55, "japan": 0.10, "china": 0.10, "uk": 0.05, "germany": 0.20}
    # us + japan + china respond → 0.75 / 1.00 = 75% ≥ 60%
    per_market = {"us": -1.0, "japan": 1.0, "china": 0.0}
    val, cov_ok, _ = aggregate_field_with_coverage(per_market, weights)
    assert cov_ok is True
    assert val is not None
    # Renormalized weights: us=0.733, japan=0.133, china=0.133.
    # Weighted median: us dominates → -1.0
    assert val == pytest.approx(-1.0)


def test_coverage_at_exact_threshold_passes():
    """Exactly 60% should pass (>=, not >)."""
    weights = {"us": 0.6, "japan": 0.4}
    per_market = {"us": 1.0}
    val, cov_ok, _ = aggregate_field_with_coverage(per_market, weights)
    assert cov_ok is True


def test_empty_per_market_returns_none():
    weights = {"us": 1.0}
    val, cov_ok, markets = aggregate_field_with_coverage({}, weights)
    assert val is None
    assert cov_ok is False
    assert markets == []


def test_weighted_median_picks_high_weight_value():
    """Weighted median should follow the heavy weight, not a simple mean."""
    weights = {"us": 0.7, "japan": 0.15, "china": 0.15}
    per_market = {"us": -2.0, "japan": 2.0, "china": 2.0}
    val, cov_ok, _ = aggregate_field_with_coverage(per_market, weights)
    assert cov_ok is True
    # US dominates → median lands at -2
    assert val == pytest.approx(-2.0)


# ---------------------------------------------------------------------------
# load_weights round-trips
# ---------------------------------------------------------------------------


def test_load_weights_default_path():
    weights = load_weights()
    assert "global_macro_weights" in weights
    macro = weights["global_macro_weights"]
    # 14 markets per MCP_FIELD_INVENTORY.md §1.
    assert "us" in macro
    assert "japan" in macro
    assert "malaysia" in macro  # added in v0 alignment
    # Brazil / Mexico / Hong Kong dropped per MCP_FIELD_INVENTORY.md §1.
    assert "brazil" not in macro
    assert "mexico" not in macro
    assert "hong_kong" not in macro


# ---------------------------------------------------------------------------
# Per-region tilt bypasses coverage threshold
# ---------------------------------------------------------------------------


def _build_market(name: str, schema_key: str, content_by_comp: dict) -> MarketResponse:
    components = {}
    for comp, content in content_by_comp.items():
        components[comp] = {
            "report_date": "2026-05-19",
            "market": name,
            "component": comp,
            "success": True,
            "content": content,
        }
    return MarketResponse(
        market_name=name,
        schema_key=schema_key,
        components=components,
        reachable=True,
        partial_components=tuple(),
    )


def test_aggregate_region_tilt_emits_single_market_bypass():
    """One market with strong constructive prose → region tilt emitted even
    with no coverage at all from other markets (per-region single-source)."""
    markets = [
        _build_market(
            "United States",
            "us",
            {
                "macro_indicators": (
                    "US conditions are constructive — favourable backdrop, "
                    "improving trends, supportive policy, bullish, attractive."
                ),
                "tactical": "Overweight US equities, constructive backdrop.",
            },
        ),
    ]
    telemetry = {"regime_tag": "Selective rotation"}
    agg = aggregate(markets, telemetry)
    # us region tilt should be populated (bypass coverage rule).
    assert "us" in agg["regions"], f"got regions={agg['regions']!r}"
    assert agg["regions"]["us"] != 0


# ---------------------------------------------------------------------------
# Φ aggregation across markets uses 60% rule
# ---------------------------------------------------------------------------


def test_phi_silent_in_majority_caps_coverage_false():
    """Only US has Φ prose — well below 60% coverage → coverage_ok False."""
    markets = [
        _build_market(
            "United States",
            "us",
            {"macro_indicators": "Valuation metrics at -1.00 across the index."},
        ),
        _build_market(
            "Japan",
            "japan",
            {"macro_indicators": "Tactical positioning constructive; no explicit valuation read."},
        ),
        _build_market(
            "China",
            "china",
            {"macro_indicators": "Slowing growth; reflationary impulse."},
        ),
    ]
    agg = aggregate(markets, {})
    # Only US carries valuation prose. US weight is 0.55 — below 60%.
    assert agg["phi"]["coverage_ok"] is False or agg["phi"]["value"] is None


def test_phi_aggregates_when_coverage_ok():
    """Manufacture coverage with enough markets to clear 60% threshold."""
    # Use minimal weights where US alone gives coverage_ok.
    custom_weights = {"global_macro_weights": {"us": 1.0}}
    markets = [
        _build_market(
            "United States",
            "us",
            {"macro_indicators": "Valuation metrics at -1.00 across the S&P."},
        ),
    ]
    agg = aggregate(markets, {}, weights=custom_weights)
    assert agg["phi"]["coverage_ok"] is True
    assert agg["phi"]["value"] == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# Fan-out summary captures unreachable markets
# ---------------------------------------------------------------------------


def test_unreachable_markets_counted_in_fan_out_summary():
    markets = [
        _build_market("United States", "us", {"macro_indicators": "x"}),
        MarketResponse(
            market_name="Japan",
            schema_key="japan",
            components={"macro_indicators": None},
            reachable=False,
        ),
    ]
    agg = aggregate(markets, {})
    assert agg["fan_out_summary"]["markets_total"] == 2
    assert agg["fan_out_summary"]["markets_unreachable"] == 1
    assert "Japan" in agg["fan_out_summary"]["unreachable_markets"]


# ---------------------------------------------------------------------------
# PARTIAL handling (silent content)
# ---------------------------------------------------------------------------


def test_partial_silent_content_treated_as_silent_not_unreachable():
    """A successful response with 'data remains unavailable' content
    shouldn't contribute Φ but the market remains reachable."""
    markets = [
        _build_market(
            "United States",
            "us",
            {"macro_indicators": "Sector ranking data remains unavailable for this reporting period."},
        ),
    ]
    agg = aggregate(markets, {})
    # Market is reachable, but Φ has no contribution from US.
    assert agg["fan_out_summary"]["markets_unreachable"] == 0
    assert "us" not in agg["phi"]["markets_with_data"]
