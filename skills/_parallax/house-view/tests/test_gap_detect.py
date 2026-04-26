"""Unit tests for gap_detect.py."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import gap_detect  # noqa: E402


def _draft(tilts: dict, confidence: dict | None = None) -> dict:
    return {
        "tilts": tilts,
        "extraction": {
            "extraction_confidence": confidence or {
                "sectors": 0.9,
                "regions": 0.9,
                "factors": 0.9,
                "macro_regime": 0.9,
            },
        },
    }


def test_silent_eligible_field_is_a_gap():
    draft = _draft({"regions": {"mexico": 0, "us": 1}})
    gaps = gap_detect.detect_gaps(draft, prose="", extraction_notes="")
    paths = [g.field_path for g in gaps]
    assert "tilts.regions.mexico" in paths
    assert "tilts.regions.us" not in paths  # non-zero, not silent


def test_silent_field_mentioned_in_prose_is_not_a_gap():
    draft = _draft({"regions": {"mexico": 0}})
    prose = "We took a hard look at Mexico and concluded that current valuations price in tariff risk."
    gaps = gap_detect.detect_gaps(draft, prose=prose)
    assert all(g.leaf_key != "mexico" for g in gaps)


def test_silent_field_mentioned_via_alias_is_not_a_gap():
    draft = _draft({"sectors": {"information_technology": 0}})
    prose = "Cautious on tech, prefer healthcare."
    gaps = gap_detect.detect_gaps(draft, prose=prose)
    assert all(g.leaf_key != "information_technology" for g in gaps)


def test_silent_field_mentioned_in_extraction_notes_is_not_a_gap():
    draft = _draft({"factors": {"profitability": 0}})
    notes = "Hedged language on quality factor — extractor set to 0 to be safe."
    gaps = gap_detect.detect_gaps(draft, prose="", extraction_notes=notes)
    # "quality" is an alias for profitability per PROSE_ALIASES
    assert all(g.leaf_key != "profitability" for g in gaps)


def test_pillars_are_never_eligible():
    draft = _draft(
        {
            "pillars": {
                "econometrics_phase": 0,
                "valuation_state": 0,
                "market_entropy": 0,
                "psychological_wavelength": 0,
            }
        }
    )
    gaps = gap_detect.detect_gaps(draft, prose="", extraction_notes="")
    assert all(g.dimension != "pillars" for g in gaps)
    assert len(gaps) == 0


def test_themes_are_never_eligible():
    draft = _draft({"themes": {"ai_infrastructure": 0, "energy_transition": 0}})
    gaps = gap_detect.detect_gaps(draft, prose="", extraction_notes="")
    assert all(g.dimension != "themes" for g in gaps)


def test_styles_are_never_eligible():
    draft = _draft(
        {
            "styles": {
                "cap_size": {"large": 0, "mid": 0, "small": 0},
                "growth_value": {"growth": 0, "value": 0},
            }
        }
    )
    gaps = gap_detect.detect_gaps(draft, prose="", extraction_notes="")
    assert all(g.dimension != "styles" for g in gaps)


def test_low_confidence_nonzero_field_is_a_gap():
    draft = _draft(
        {"factors": {"momentum": 1}},
        confidence={"factors": 0.3, "regions": 0.9, "sectors": 0.9, "macro_regime": 0.9},
    )
    gaps = gap_detect.detect_gaps(draft, prose="", extraction_notes="")
    momentum_gaps = [g for g in gaps if g.leaf_key == "momentum"]
    assert len(momentum_gaps) == 1
    assert momentum_gaps[0].reason == "low_confidence"
    assert momentum_gaps[0].current_value == 1


def test_low_confidence_zero_field_uses_silent_reason():
    draft = _draft(
        {"factors": {"momentum": 0}},
        confidence={"factors": 0.3, "regions": 0.9, "sectors": 0.9, "macro_regime": 0.9},
    )
    gaps = gap_detect.detect_gaps(draft, prose="", extraction_notes="")
    momentum_gaps = [g for g in gaps if g.leaf_key == "momentum"]
    assert len(momentum_gaps) == 1
    # Silent takes precedence over low_confidence when value is 0
    assert momentum_gaps[0].reason == "silent"


def test_wizard_mode_returns_no_gaps():
    draft = _draft({"regions": {"mexico": 0, "japan": 0}})
    gaps = gap_detect.detect_gaps(draft, prose="", source_type="manual")
    assert gaps == []


def test_macro_regime_null_token_is_silent():
    draft = _draft({"macro_regime": {"growth": None, "inflation": None, "rates": None, "risk_appetite": None}})
    gaps = gap_detect.detect_gaps(draft, prose="", extraction_notes="")
    paths = {g.field_path for g in gaps}
    assert "tilts.macro_regime.growth" in paths
    assert "tilts.macro_regime.inflation" in paths


def test_macro_regime_explicit_token_is_not_silent():
    draft = _draft({"macro_regime": {"growth": "expansion", "inflation": None, "rates": None, "risk_appetite": None}})
    gaps = gap_detect.detect_gaps(draft, prose="", extraction_notes="")
    paths = {g.field_path for g in gaps}
    assert "tilts.macro_regime.growth" not in paths
    assert "tilts.macro_regime.inflation" in paths


def test_missing_extraction_block_uses_zero_confidence():
    # Without extraction block, every dimension's confidence defaults to 0.0.
    # That's < 0.4, but only non-zero fields count as low_confidence gaps.
    # All zeros remain silent gaps as usual.
    draft = {"tilts": {"regions": {"mexico": 0}}}
    gaps = gap_detect.detect_gaps(draft, prose="")
    assert any(g.leaf_key == "mexico" and g.reason == "silent" for g in gaps)


def test_aliases_in_prose_are_case_insensitive():
    draft = _draft({"sectors": {"real_estate": 0}})
    prose = "REIT exposure is a meaningful component of the IC view."
    gaps = gap_detect.detect_gaps(draft, prose=prose)
    assert all(g.leaf_key != "real_estate" for g in gaps)


def test_us_alias_matches_united_states_in_prose():
    draft = _draft({"regions": {"us": 0}})
    prose = "United States large-caps remain the focal point of the view."
    gaps = gap_detect.detect_gaps(draft, prose=prose)
    assert all(g.leaf_key != "us" for g in gaps)


def test_underscore_keys_match_spaced_aliases_in_prose():
    draft = _draft({"sectors": {"consumer_discretionary": 0}})
    prose = "Consumer discretionary names look stretched here."
    gaps = gap_detect.detect_gaps(draft, prose=prose)
    assert all(g.leaf_key != "consumer_discretionary" for g in gaps)


def test_is_eligible_dimension_guard():
    assert gap_detect.is_eligible_dimension("regions")
    assert gap_detect.is_eligible_dimension("macro_regime")
    assert not gap_detect.is_eligible_dimension("pillars")
    assert not gap_detect.is_eligible_dimension("themes")
    assert not gap_detect.is_eligible_dimension("styles")
    assert not gap_detect.is_eligible_dimension("excludes")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
