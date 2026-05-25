"""End-to-end pillar composition with fixture MCP responses."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import cross_country
import pillar_compose
from cross_country import MarketResponse


FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    with open(FIXTURES / name, "r", encoding="utf-8") as f:
        return json.load(f)


def _market(name: str, schema_key: str, components: dict) -> MarketResponse:
    return MarketResponse(
        market_name=name,
        schema_key=schema_key,
        components=components,
        reachable=True,
    )


def test_compose_end_to_end_with_fixtures():
    """Run cross_country + pillar_compose against US + Japan + China fixtures.

    Verifies the contract: each pillar comes back with value (-2..+2),
    confidence (0.0-1.0), missing_inputs (list).
    """
    us_mi = _load_fixture("us_macro_indicators.json")
    japan_tac = _load_fixture("japan_tactical.json")
    china_mi = _load_fixture("china_macro_indicators.json")
    telemetry = _load_fixture("telemetry_full.json")

    markets = [
        _market("United States", "us", {"macro_indicators": us_mi}),
        _market("Japan", "japan", {"tactical": japan_tac, "macro_indicators": None}),
        _market("China", "china", {"macro_indicators": china_mi}),
    ]
    agg = cross_country.aggregate(markets, telemetry)
    pillars = pillar_compose.compute_pillars(agg, telemetry)

    for name in ("omega", "phi", "xi", "psi"):
        p = pillars[name]
        assert -2 <= p.value <= 2, f"{name} value out of range: {p.value}"
        assert 0.0 <= p.confidence <= 1.0, f"{name} confidence out of range"

    # Ω should have meaningful value — regime_tag + growth nudge available.
    assert pillars["omega"].value != 0 or "regime_tag" in str(pillars["omega"].missing_inputs)


def test_compose_handles_all_missing_inputs_gracefully():
    """Empty aggregated + empty telemetry should still return four PillarResults
    with missing_inputs flagged."""
    pillars = pillar_compose.compute_pillars({}, {})
    assert set(pillars.keys()) == {"omega", "phi", "xi", "psi"}
    for name, p in pillars.items():
        assert p.missing_inputs, f"{name} should have missing inputs when no data"
        assert p.confidence < 0.4  # gap_detect threshold


def test_pillar_values_for_view_maps_to_schema_keys():
    pillars = pillar_compose.compute_pillars({}, {"regime_tag": "selective rotation"})
    schema = pillar_compose.pillar_values_for_view(pillars)
    assert set(schema.keys()) == {
        "econometrics_phase",
        "valuation_state",
        "market_entropy",
        "psychological_wavelength",
    }


def test_pillar_confidence_average_is_mean():
    pillars = pillar_compose.compute_pillars({}, {})
    avg = pillar_compose.pillar_confidence_average(pillars)
    manual = sum(p.confidence for p in pillars.values()) / 4
    assert avg == pytest.approx(manual)
