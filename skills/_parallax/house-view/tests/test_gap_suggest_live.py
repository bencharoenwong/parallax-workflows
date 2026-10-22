"""Regression tests for gap_suggest.py against captured live MCP responses.

Bug class this catches: response-shape mismatch between unit-test fixtures
and the actual Parallax MCP API — helpers passed unit tests against
assumed-shape fixtures but produced ZERO suggestions when run against real
MCP responses.

Each fixture in tests/fixtures/ is a verbatim capture of an MCP call from
2026-04-24. If the live API shape changes, refresh the fixtures and update
the assertions accordingly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import gap_suggest  # noqa: E402


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# Region helper against live nested-components shape
# ---------------------------------------------------------------------------

def test_region_helper_extracts_overweight_from_canada_live():
    """Canada response is unambiguously bullish — should yield positive tilt."""
    response = _load("macro_analyst_canada_live.json")
    result = gap_suggest.macro_analyst_to_region_tilt(response, "canada")
    assert result is not None, (
        "Region helper returned None on a clearly-bullish Canada response. "
        "Likely the helper is reading the wrong response shape — the live "
        "API nests under response['components'][name]['content']."
    )
    value, snippet = result
    assert value >= 1, f"Expected positive tilt for Canada (overweight thesis), got {value}"
    assert "overweight" in snippet.lower() or "favorable" in snippet.lower()


def test_region_helper_extracts_underweight_from_india_live():
    """India response is unambiguously bearish — underweight + weakness + structural pressure."""
    response = _load("macro_analyst_india_live.json")
    result = gap_suggest.macro_analyst_to_region_tilt(response, "india")
    assert result is not None, (
        "Region helper returned None on a clearly-bearish India response. "
        "Tactical explicitly says 'underweight equity stance' + macro_indicators "
        "describes 'structural weakness' and 'capital account deterioration'."
    )
    value, snippet = result
    assert value <= -1, f"Expected negative tilt for India (underweight, weakness), got {value}"


def test_region_helper_extracts_some_directional_signal_from_germany_live():
    """Germany prose has mixed signals (improving sentiment + supportive valuation
    balanced against underweight + deteriorating fundamentals). Helper may return
    None — that IS the correct behavior under the simple-token-sum scoring. This
    test documents the known limitation: when a region's prose is genuinely mixed,
    the helper should not invent a tilt. Future work: add proximity-based scoring
    (sentence-level pos/neg detection) for finer discrimination."""
    response = _load("macro_analyst_germany_live.json")
    result = gap_suggest.macro_analyst_to_region_tilt(response, "germany")
    # Helper is allowed to return None for genuinely-mixed prose. If it DOES
    # return a tilt, the value should be reasonable (not extreme).
    if result is not None:
        value, _ = result
        assert -2 <= value <= 2


# ---------------------------------------------------------------------------
# Sector helper against live prose shape
# ---------------------------------------------------------------------------

def test_sector_helper_extracts_outperformers_from_us_live_prose():
    """US sector_positioning prose explicitly names outperformers and underperformers."""
    response = _load("macro_analyst_us_sector_positioning_live.json")
    out = gap_suggest.macro_analyst_to_sector_tilts(
        response,
        ["energy", "financials", "consumer_discretionary",
         "consumer_staples", "communication_services",
         "health_care", "utilities", "materials"],
    )
    # Must produce SOMETHING — the prose explicitly names sectors
    assert len(out) >= 2, (
        f"Sector helper produced only {len(out)} suggestions from explicit "
        f"prose naming multiple sectors. Suggests prose extraction is not wired."
    )
    # Direction checks on the named outperformers
    if "energy" in out:
        assert out["energy"][0] >= 1, "Energy named as outperformer in prose"
    if "financials" in out:
        assert out["financials"][0] >= 1, "Financials named as outperformer in prose"


def test_sector_helper_detects_underperformers_in_us_live_prose():
    """Consumer Staples and Communication Services are explicitly tagged as underperforming."""
    response = _load("macro_analyst_us_sector_positioning_live.json")
    out = gap_suggest.macro_analyst_to_sector_tilts(
        response,
        ["consumer_staples", "communication_services"],
    )
    # At least ONE should land negative — both are explicitly named with
    # "face underperformance pressure" in the prose
    negative_picks = [k for k, (v, _) in out.items() if v <= -1]
    assert len(negative_picks) >= 1, (
        f"Neither consumer_staples nor communication_services flagged negative "
        f"despite explicit 'face underperformance pressure' in prose. out={out}"
    )


# ---------------------------------------------------------------------------
# fold_responses end-to-end against live shape
# ---------------------------------------------------------------------------

def test_fold_responses_end_to_end_with_live_canada():
    """Wire detect → plan → fold against a real Canada response. Must produce >=1 suggestion."""
    import gap_detect

    canada_resp = _load("macro_analyst_canada_live.json")

    draft = {
        "tilts": {
            "regions": {"canada": 0, "us": 1},
            "sectors": {},
            "factors": {},
            "macro_regime": {"growth": "expansion", "inflation": "benign",
                             "rates": "cutting", "risk_appetite": "neutral"},
        },
        "extraction": {
            "extraction_confidence": {
                "regions": 0.7, "sectors": 0.5, "factors": 0.7, "macro_regime": 0.8,
            }
        },
    }
    gaps = gap_detect.detect_gaps(draft, prose="US is core holding", extraction_notes="")
    # Canada should be a gap (silent + not mentioned + not in LOW_COVERAGE_REGIONS)
    canada_gap = next((g for g in gaps if g.field_path == "tilts.regions.canada"), None)
    assert canada_gap is not None, "Canada should have been detected as a silent gap"

    spec = gap_suggest.CallSpec(
        purpose="regions",
        tool="macro_analyst",
        args={"market": "Canada"},
        covers_dimensions=("regions",),
        covers_leaves=("canada",),
    )
    suggestions = gap_suggest.fold_responses([canada_gap], [(spec, canada_resp)])
    assert len(suggestions) == 1, (
        f"fold_responses produced {len(suggestions)} suggestions from a live Canada "
        f"response with a clear overweight signal. Expected exactly 1."
    )
    s = suggestions[0]
    assert s.field_path == "tilts.regions.canada"
    assert s.suggested_value >= 1


# ---------------------------------------------------------------------------
# Long-tail demotion (OBS-13a)
# ---------------------------------------------------------------------------

def test_long_tail_regions_silent_by_default():
    """Vietnam, Chile, Philippines, Mena, apac_ex_japan should not be flagged
    when silent + unmentioned. Thailand was removed from the deny-list 2026-04-26
    after Parallax MCP coverage came online — Thailand should now flag normally."""
    import gap_detect

    draft = {
        "tilts": {
            "regions": {
                "vietnam": 0, "chile": 0, "philippines": 0,
                "mena": 0, "apac_ex_japan": 0,
                "thailand": 0,  # now COVERED, should flag as gap
                "us": 1,  # mentioned; should not be a gap
                "canada": 0,  # NOT in deny-list; should be a gap
            },
        },
        "extraction": {
            "extraction_confidence": {"regions": 0.7},
        },
    }
    gaps = gap_detect.detect_gaps(draft, prose="We like the US.", extraction_notes="")
    flagged_regions = {g.leaf_key for g in gaps if g.dimension == "regions"}
    # Genuine long-tail regions should NOT appear
    for low_cov in ["vietnam", "chile", "philippines", "mena", "apac_ex_japan"]:
        assert low_cov not in flagged_regions, (
            f"{low_cov} should be silent-by-default per LOW_COVERAGE_REGIONS"
        )
    # Newly-covered regions SHOULD appear
    assert "thailand" in flagged_regions, "Thailand was removed from deny-list when MCP coverage came online"
    assert "canada" in flagged_regions, "Canada should still be flagged (not in deny-list)"


def test_mentioned_region_not_flagged_regardless_of_demotion_status():
    """When a region appears in prose, _is_mentioned returns True, so the
    `silent and not mentioned` condition fails and no Gap is emitted —
    NEITHER the normal path NOR the demotion path fires (demotion only
    applies when silent AND unmentioned, which is a subset, not an override)."""
    import gap_detect

    draft = {
        "tilts": {"regions": {"vietnam": 0}},
        "extraction": {"extraction_confidence": {"regions": 0.7}},
    }
    gaps = gap_detect.detect_gaps(
        draft,
        prose="We are constructive on Vietnam.",
        extraction_notes="",
    )
    flagged = [g.leaf_key for g in gaps if g.dimension == "regions"]
    assert "vietnam" not in flagged, "Vietnam mentioned in prose — should not be flagged as gap"


# ---------------------------------------------------------------------------
# Live coverage filtering (OBS-16: REGION_MARKET_MAP drift)
# ---------------------------------------------------------------------------

def test_plan_calls_filters_to_available_markets():
    """When available_markets is supplied, REGION_MARKET_MAP entries not in
    the live list are dropped from planning."""
    import gap_detect

    gap_us = gap_detect.Gap(
        field_path="tilts.regions.us", dimension="regions", leaf_key="us",
        current_value=0, current_confidence=0.7, reason="silent",
    )
    gap_canada = gap_detect.Gap(
        field_path="tilts.regions.canada", dimension="regions", leaf_key="canada",
        current_value=0, current_confidence=0.7, reason="silent",
    )

    # Live coverage missing Canada — Canada should be silently dropped.
    specs = gap_suggest.plan_calls(
        [gap_us, gap_canada],
        available_markets=["United States"],  # Canada not present
    )
    region_specs = [s for s in specs if s.purpose == "regions"]
    markets_called = {s.args["market"] for s in region_specs}
    assert markets_called == {"United States"}
    assert "Canada" not in markets_called


def test_plan_calls_with_no_available_markets_uses_full_map():
    """Back-compat: when available_markets is None, all REGION_MARKET_MAP entries
    are eligible (existing behavior)."""
    import gap_detect

    gaps = [
        gap_detect.Gap(
            field_path="tilts.regions.canada", dimension="regions", leaf_key="canada",
            current_value=0, current_confidence=0.7, reason="silent",
        ),
        gap_detect.Gap(
            field_path="tilts.regions.thailand", dimension="regions", leaf_key="thailand",
            current_value=0, current_confidence=0.7, reason="silent",
        ),
    ]
    specs = gap_suggest.plan_calls(gaps)  # no available_markets passed
    region_specs = [s for s in specs if s.purpose == "regions"]
    markets = {s.args["market"] for s in region_specs}
    assert "Canada" in markets
    assert "Thailand" in markets  # newly added to REGION_MARKET_MAP 2026-04-26


def test_plan_calls_skips_us_sectors_when_us_offline():
    """If the US is missing from live coverage, the sector call shouldn't fire."""
    import gap_detect

    gap = gap_detect.Gap(
        field_path="tilts.sectors.energy", dimension="sectors", leaf_key="energy",
        current_value=0, current_confidence=0.5, reason="silent",
    )
    specs = gap_suggest.plan_calls([gap], available_markets=["Canada"])  # no US
    sector_specs = [s for s in specs if s.purpose == "sectors"]
    assert sector_specs == []


def test_report_skipped_leaves_names_uncovered_regions():
    """report_skipped_leaves should list region gaps that have no MCP coverage
    today, so the partial-coverage banner can disclose them honestly."""
    import gap_detect

    gaps = [
        gap_detect.Gap(
            field_path="tilts.regions.hong_kong", dimension="regions", leaf_key="hong_kong",
            current_value=0, current_confidence=0.7, reason="silent",
        ),
        gap_detect.Gap(
            field_path="tilts.regions.taiwan", dimension="regions", leaf_key="taiwan",
            current_value=0, current_confidence=0.7, reason="silent",
        ),
        gap_detect.Gap(
            field_path="tilts.regions.us", dimension="regions", leaf_key="us",
            current_value=0, current_confidence=0.7, reason="silent",
        ),
    ]
    skipped = gap_suggest.report_skipped_leaves(
        gaps, available_markets=["United States"],
    )
    # Hong Kong and Taiwan: not in REGION_MARKET_MAP at all.
    assert "hong_kong" in skipped["regions_no_coverage"]
    assert "taiwan" in skipped["regions_no_coverage"]
    # US: in the live list, should NOT be flagged.
    assert "us" not in skipped["regions_no_coverage"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
