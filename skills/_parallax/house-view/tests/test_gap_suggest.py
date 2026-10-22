"""Unit tests for gap_suggest.py."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import gap_detect  # noqa: E402
import gap_suggest  # noqa: E402


def _gap(field_path: str, dimension: str, leaf: str, value=0, reason="silent", conf=0.9):
    return gap_detect.Gap(
        field_path=field_path,
        dimension=dimension,
        leaf_key=leaf,
        current_value=value,
        current_confidence=conf,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Phase 0 boundary — never suggest pillars / themes / styles / excludes.
# ---------------------------------------------------------------------------

def test_planner_rejects_ineligible_dimension():
    bad_gap = gap_detect.Gap(
        field_path="tilts.pillars.econometrics_phase",
        dimension="pillars",
        leaf_key="econometrics_phase",
        current_value=0,
        current_confidence=0.9,
        reason="silent",
    )
    try:
        gap_suggest.plan_calls([bad_gap])
        raise AssertionError("planner should have rejected pillars dimension")
    except ValueError as e:
        assert "Phase 0 violation" in str(e)


def test_no_suggestion_ever_targets_pillars_or_themes_or_styles():
    # End-to-end guard: build a draft with every dimension silent, run
    # detect → plan → fold with mocked responses, assert no suggestion has a
    # field_path starting with tilts.pillars / tilts.themes / tilts.styles.
    draft = {
        "tilts": {
            "pillars": {"econometrics_phase": 0, "valuation_state": 0},
            "themes": {"ai_infrastructure": 0, "energy_transition": 0},
            "styles": {"cap_size": {"large": 0, "mid": 0, "small": 0}},
            "macro_regime": {"growth": None, "inflation": None, "rates": None, "risk_appetite": None},
            "factors": {"momentum": 0},
            "regions": {"us": 0, "japan": 0},
            "sectors": {"information_technology": 0},
        },
        "extraction": {
            "extraction_confidence": {
                "pillars": 0.9, "themes": 0.9, "styles": 0.9,
                "macro_regime": 0.9, "factors": 0.9, "regions": 0.9, "sectors": 0.9,
            }
        },
    }
    gaps = gap_detect.detect_gaps(draft, prose="", extraction_notes="")
    specs = gap_suggest.plan_calls(gaps)

    # Mock responses for every spec.
    mock_telemetry = {
        "regime_tag": "Slowing growth + sticky inflation",
        "commentary": {"headline": "Slowing growth, sticky inflation persists."},
        "as_of": "2026-04-26T00:00:00Z",
    }
    mock_macro_us = {
        "macro_indicators": "Constructive on US large-caps, supportive flows.",
        "tactical": "Overweight US, attractive valuations.",
        "sector_positioning": {"information_technology": 1},
        "as_of": "2026-04-26T00:00:00Z",
    }
    mock_macro_jp = {
        "macro_indicators": "Cautious on Japan, headwind from yen.",
        "tactical": "Underweight Japan equities.",
        "as_of": "2026-04-26T00:00:00Z",
    }

    call_results = []
    for spec in specs:
        if spec.purpose == "telemetry":
            call_results.append((spec, mock_telemetry))
        elif spec.purpose == "regions" and spec.args["market"] == "United States":
            call_results.append((spec, mock_macro_us))
        elif spec.purpose == "regions" and spec.args["market"] == "Japan":
            call_results.append((spec, mock_macro_jp))
        elif spec.purpose == "sectors":
            call_results.append((spec, mock_macro_us))

    suggestions = gap_suggest.fold_responses(gaps, call_results)
    for s in suggestions:
        assert not s.field_path.startswith("tilts.pillars."), s.field_path
        assert not s.field_path.startswith("tilts.themes."), s.field_path
        assert not s.field_path.startswith("tilts.styles."), s.field_path


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

def test_plan_calls_groups_telemetry_for_regime_and_factors():
    gaps = [
        _gap("tilts.macro_regime.growth", "macro_regime", "growth", value=None),
        _gap("tilts.factors.momentum", "factors", "momentum", value=0),
    ]
    specs = gap_suggest.plan_calls(gaps)
    telemetry_specs = [s for s in specs if s.purpose == "telemetry"]
    assert len(telemetry_specs) == 1
    assert "macro_regime" in telemetry_specs[0].covers_dimensions
    assert "factors" in telemetry_specs[0].covers_dimensions


def test_plan_calls_skips_uncovered_regions():
    gaps = [
        _gap("tilts.regions.mexico", "regions", "mexico"),  # not in REGION_MARKET_MAP
        _gap("tilts.regions.us", "regions", "us"),  # covered
    ]
    specs = gap_suggest.plan_calls(gaps)
    region_specs = [s for s in specs if s.purpose == "regions"]
    assert len(region_specs) == 1
    assert region_specs[0].args["market"] == "United States"


def test_plan_calls_one_us_macro_analyst_for_sectors():
    gaps = [
        _gap("tilts.sectors.information_technology", "sectors", "information_technology"),
        _gap("tilts.sectors.energy", "sectors", "energy"),
    ]
    specs = gap_suggest.plan_calls(gaps)
    sector_specs = [s for s in specs if s.purpose == "sectors"]
    assert len(sector_specs) == 1
    assert sector_specs[0].args["market"] == "United States"
    assert set(sector_specs[0].covers_leaves) == {"information_technology", "energy"}


def test_plan_calls_empty_gaps_returns_no_specs():
    assert gap_suggest.plan_calls([]) == []


# ---------------------------------------------------------------------------
# Macro regime mapping from telemetry
# ---------------------------------------------------------------------------

def test_telemetry_to_macro_regime_recognizes_sticky_inflation():
    response = {
        "regime_tag": "Slowing growth + sticky inflation",
        "commentary": {"headline": "Sticky inflation persists; supercore at 4.1%."},
    }
    out = gap_suggest.telemetry_to_macro_regime(response, ["growth", "inflation"])
    assert out["growth"][0] == "slowing"
    assert out["inflation"][0] == "sticky"


def test_telemetry_to_macro_regime_unknown_returns_no_entry():
    response = {"regime_tag": "Steady-as-she-goes", "commentary": {}}
    out = gap_suggest.telemetry_to_macro_regime(response, ["growth", "inflation"])
    assert out == {}


def test_telemetry_to_macro_regime_only_returns_requested_leaves():
    response = {"regime_tag": "Slowing growth + sticky inflation"}
    out = gap_suggest.telemetry_to_macro_regime(response, ["growth"])
    assert "growth" in out
    assert "inflation" not in out


# ---------------------------------------------------------------------------
# Factor tilt derivation from telemetry
# ---------------------------------------------------------------------------

def test_telemetry_to_factor_tilts_slowing_sticky_emits_defensive_tilts():
    response = {"regime_tag": "Slowing growth + sticky inflation"}
    out = gap_suggest.telemetry_to_factor_tilts(
        response, ["low_volatility", "profitability", "momentum"]
    )
    assert out.get("low_volatility", (None,))[0] == 1
    assert out.get("profitability", (None,))[0] == 1
    assert out.get("momentum", (None,))[0] == -1


def test_telemetry_to_factor_tilts_filters_unrequested_leaves():
    response = {"regime_tag": "Slowing growth + sticky inflation"}
    out = gap_suggest.telemetry_to_factor_tilts(response, ["momentum"])
    assert set(out.keys()) == {"momentum"}


def test_telemetry_to_factor_tilts_no_match_returns_empty():
    response = {"regime_tag": "Mixed signals; ambiguous regime"}
    out = gap_suggest.telemetry_to_factor_tilts(response, ["momentum", "value"])
    assert out == {}


# ---------------------------------------------------------------------------
# Region tilt parsing from macro_analyst
# ---------------------------------------------------------------------------

def test_macro_analyst_to_region_tilt_strong_positive():
    response = {
        "macro_indicators": "Constructive on growth and supportive flows.",
        "tactical": "Overweight, attractive valuations and improving breadth.",
    }
    result = gap_suggest.macro_analyst_to_region_tilt(response, "us")
    assert result is not None
    value, snippet = result
    assert value == 2  # ≥3 positive tokens
    assert "constructive" in snippet.lower()


def test_macro_analyst_to_region_tilt_strong_negative():
    response = {
        "macro_indicators": "Cautious; deteriorating earnings and weak flows.",
        "tactical": "Underweight; bearish on near-term path.",
    }
    result = gap_suggest.macro_analyst_to_region_tilt(response, "japan")
    assert result is not None
    value, _ = result
    assert value == -2


def test_macro_analyst_to_region_tilt_ambiguous_returns_none():
    response = {
        "macro_indicators": "Mixed read on growth and inflation.",
        "tactical": "No conviction.",
    }
    result = gap_suggest.macro_analyst_to_region_tilt(response, "us")
    assert result is None


def test_macro_analyst_to_region_tilt_empty_response_returns_none():
    assert gap_suggest.macro_analyst_to_region_tilt({}, "us") is None


# ---------------------------------------------------------------------------
# Sector tilt parsing from macro_analyst
# ---------------------------------------------------------------------------

def test_macro_analyst_to_sector_tilts_dict_shape():
    response = {
        "sector_positioning": {
            "information_technology": 1,
            "energy": -1,
            "utilities": 0,  # filtered (|v| < 1)
        }
    }
    out = gap_suggest.macro_analyst_to_sector_tilts(
        response, ["information_technology", "energy", "utilities"]
    )
    assert out["information_technology"][0] == 1
    assert out["energy"][0] == -1
    assert "utilities" not in out


def test_macro_analyst_to_sector_tilts_string_values():
    response = {
        "sector_positioning": {
            "information_technology": "overweight",
            "financials": "strong underweight",
        }
    }
    out = gap_suggest.macro_analyst_to_sector_tilts(
        response, ["information_technology", "financials"]
    )
    assert out["information_technology"][0] == 1
    assert out["financials"][0] == -2


def test_macro_analyst_to_sector_tilts_list_shape():
    response = {
        "sector_positioning": [
            {"sector": "information_technology", "tilt": 2},
            {"sector": "energy", "tilt": "underweight"},
        ]
    }
    out = gap_suggest.macro_analyst_to_sector_tilts(
        response, ["information_technology", "energy"]
    )
    assert out["information_technology"][0] == 2
    assert out["energy"][0] == -1


def test_macro_analyst_to_sector_tilts_missing_field_returns_empty():
    out = gap_suggest.macro_analyst_to_sector_tilts({}, ["information_technology"])
    assert out == {}


def test_macro_analyst_to_sector_tilts_filters_unrequested_keys():
    response = {"sector_positioning": {"information_technology": 1, "energy": 1}}
    out = gap_suggest.macro_analyst_to_sector_tilts(response, ["information_technology"])
    assert "energy" not in out


# ---------------------------------------------------------------------------
# fold_responses end-to-end
# ---------------------------------------------------------------------------

def test_fold_responses_carries_reason_from_gap():
    gaps = [
        _gap("tilts.factors.momentum", "factors", "momentum", value=1, reason="low_confidence", conf=0.3),
    ]
    spec = gap_suggest.CallSpec(
        purpose="telemetry",
        tool="get_telemetry",
        args={"fields": ["regime_tag"]},
        covers_dimensions=("factors",),
        covers_leaves=("momentum",),
    )
    response = {"regime_tag": "Slowing growth + sticky inflation"}
    suggestions = gap_suggest.fold_responses(gaps, [(spec, response)])
    assert len(suggestions) == 1
    assert suggestions[0].reason == "low_confidence"


def test_fold_responses_omits_gap_with_no_derivable_value():
    gaps = [
        _gap("tilts.regions.us", "regions", "us"),
    ]
    spec = gap_suggest.CallSpec(
        purpose="regions",
        tool="macro_analyst",
        args={"market": "United States"},
        covers_dimensions=("regions",),
        covers_leaves=("us",),
    )
    response = {"macro_indicators": "Mixed and ambiguous.", "tactical": "No view."}
    suggestions = gap_suggest.fold_responses(gaps, [(spec, response)])
    assert suggestions == []


def test_fold_responses_attaches_data_as_of():
    gaps = [_gap("tilts.macro_regime.inflation", "macro_regime", "inflation", value=None)]
    spec = gap_suggest.CallSpec(
        purpose="telemetry",
        tool="get_telemetry",
        args={"fields": ["regime_tag"]},
        covers_dimensions=("macro_regime",),
        covers_leaves=("inflation",),
    )
    response = {"regime_tag": "Sticky inflation persists.", "as_of": "2026-04-26T00:00:00Z"}
    suggestions = gap_suggest.fold_responses(gaps, [(spec, response)])
    assert suggestions[0].data_as_of == "2026-04-26T00:00:00Z"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
