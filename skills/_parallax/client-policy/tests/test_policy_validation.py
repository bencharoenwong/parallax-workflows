"""Validator surface and basis conversion (invariant 6) for the adaptation helper.

Split from `test_adaptation.py` only to keep the two concerns legible; there is
no `conftest.py` here either — see that module's docstring for why.
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).parent
CLIENT_POLICY_DIR = HERE.parent
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(CLIENT_POLICY_DIR))

import adaptation  # noqa: E402


def load_policy(name: str) -> dict:
    with (FIXTURES / name).open() as f:
        return yaml.safe_load(f)


def load_json(name: str) -> dict:
    with (FIXTURES / name).open() as f:
        return json.load(f)


def region_weights(policy: dict) -> dict:
    return policy["mandate"]["sub_allocations"]["dimensions"]["region"]["strategic_allocation"]


# ==========================================================================
# Invariant 6 — basis conversion
# ==========================================================================

def test_total_basis_divides_by_equity_weight():
    policy = load_policy("policy_total_basis.yaml")
    weights, rows, errors = adaptation.normalize_to_sleeve(region_weights(policy), "total", 0.60)
    assert errors == []
    assert weights == pytest.approx(
        {"us": 0.55, "europe": 0.25, "japan": 0.10, "em_ex_china": 0.10}
    )
    assert rows != []


def test_sleeve_total_round_trip():
    policy = load_policy("policy_total_basis.yaml")
    total = region_weights(policy)
    sleeve, _, _ = adaptation.normalize_to_sleeve(total, "total", 0.60)
    # Multiplying back by the equity weight reproduces the declared total weights.
    assert {k: v * 0.60 for k, v in sleeve.items()} == pytest.approx(total)
    # And the sleeve result equals the sleeve-basis sibling fixture exactly.
    assert sleeve == pytest.approx(region_weights(load_policy("policy_full.yaml")))
    # `sleeve` basis is a pass-through: converting it again is a no-op.
    passthrough, rows, errors = adaptation.normalize_to_sleeve(sleeve, "sleeve", 0.60)
    assert (passthrough, rows, errors) == (sleeve, [], [])


def test_total_basis_without_equity_weight_errors_and_falls_back_not_crashes():
    policy = load_policy("policy_total_basis_no_equity.yaml")
    weights, rows, errors = adaptation.normalize_to_sleeve(region_weights(policy), "total", None)
    assert errors != []
    assert {e.severity for e in errors} == {"dimension"}
    assert weights == pytest.approx(region_weights(policy))   # left untouched
    assert rows == []

    # The full pipeline must not raise, and the region dimension drops to
    # multiplier semantics while everything else keeps running.
    result = adaptation.run_pipeline(
        policy, load_json("exposures_sample.json"), load_json("view_tilts_sample.json")
    )
    assert result.fallback_tier != "no_policy"
    assert {r.semantics for r in result.taa} == {"multiplier_fallback"}
    assert all(r.desired_active is None for r in result.taa)
    dimension_errors = [e for e in result.errors if e.severity == "dimension"]
    assert any(e.dimension == "region" for e in dimension_errors)


def test_basis_conversion_emits_a_disclosure_row():
    result = adaptation.run_pipeline(
        load_policy("policy_total_basis.yaml"),
        load_json("exposures_sample.json"),
        load_json("view_tilts_sample.json"),
    )
    rows = [r for r in result.data_quality if r.kind == "basis_converted"]
    assert len(rows) == 1
    assert "total" in rows[0].detail and "sleeve" in rows[0].detail
    # Conversion happened, so drift is measured against sleeve-basis policy weights.
    us = next(r for r in result.drift if r.key == "us")
    assert us.policy == pytest.approx(0.55)
    assert us.band_max == pytest.approx(0.65)


def test_missing_basis_is_an_error_not_an_assumption():
    errors = adaptation.validate_policy(load_policy("policy_invalid.yaml"))
    basis_errors = [
        e for e in errors
        if e.path == "mandate.sub_allocations.dimensions.region.basis"
    ]
    assert len(basis_errors) == 1
    assert basis_errors[0].severity == "dimension"
    assert basis_errors[0].dimension == "region"
    # Nothing silently assumed `sleeve`: the weights are left exactly as declared.
    weights, rows, errs = adaptation.normalize_to_sleeve({"us": 0.55}, "", 0.60)
    assert weights == {"us": 0.55}
    assert rows == []
    assert errs != []


def test_forced_fallback_dimension_reports_no_bands_not_breach():
    # I1 repro: deleting `region.basis` from `policy_full` forces the region
    # dimension to `multiplier_fallback` (a dimension-scoped error). The raw
    # band edges on file were declared against the basis that could not be
    # resolved and must never be read as a comparison against the weight
    # below — that would render a false band verdict (e.g. breach_high) on an
    # unresolved basis. `us` exposure (0.66) sits above the on-file band max
    # (0.65), so this would previously breach; it must now read `no_bands`.
    policy = load_policy("policy_full.yaml")
    del policy["mandate"]["sub_allocations"]["dimensions"]["region"]["basis"]
    result = adaptation.run_pipeline(
        policy, load_json("exposures_sample.json"), load_json("view_tilts_sample.json")
    )
    dimension_errors = [e for e in result.errors if e.severity == "dimension"]
    assert any(e.dimension == "region" for e in dimension_errors)
    us = next(r for r in result.drift if r.dimension == "region" and r.key == "us")
    assert us.band_status == "no_bands"
    assert us.band_min is None and us.band_max is None
    assert us.breach_kind is None
    # The forced-fallback dimension loses its bands; an unaffected dimension
    # (sector, whose `basis` is still declared) keeps its bands unchanged.
    it = next(r for r in result.drift
              if r.dimension == "sector" and r.key == "information_technology")
    assert it.band_min is not None and it.band_max is not None
    # F1 repro: the policy weight for a forced-fallback dimension stays on its
    # unconverted (possibly non-sleeve) basis while `current` is always sleeve
    # basis, so `drift`/`current_active` for `us` compare incompatible bases.
    # TAA alignment must not render a sign-based aligned/opposed verdict on
    # that unreliable sign, and Policy Data Quality must disclose the gap.
    us_taa = next(r for r in result.taa if r.dimension == "region" and r.key == "us")
    assert us_taa.alignment in ("not_evaluable", "no_view")
    assert any(row.kind == "basis_unconfirmed_drift" and "region" in row.detail
              for row in result.data_quality)


# ==========================================================================
# Validator surface
# ==========================================================================

def test_validator_collects_every_error_not_just_the_first():
    errors = adaptation.validate_policy(load_policy("policy_invalid.yaml"))
    paths = {e.path for e in errors}
    base = "mandate.sub_allocations.dimensions.region"
    expected = {
        f"{base}.allocation_bands.us",          # band min > max
        f"{base}.strategic_allocation.japan",   # policy weight outside its own band
        f"{base}.basis",                        # basis absent
        f"{base}.strategic_allocation",         # weights sum to 0.90
        "adaptation.k",                         # explicit k out of range
    }
    assert expected <= paths, f"missing {expected - paths}"
    # Blocking failures put the whole policy on the `no_policy` rung; nothing partially applies.
    result = adaptation.run_pipeline(
        load_policy("policy_invalid.yaml"),
        load_json("exposures_sample.json"),
        load_json("view_tilts_sample.json"),
    )
    assert result.fallback_tier == "no_policy"
    assert result.drift == [] and result.taa == []
    assert any(e.severity == "blocking" for e in result.errors)


def test_unknown_code_list_is_a_blocking_error():
    # An unrecognized code list disables the segment-key check, so it must fail
    # loud rather than fail open: the whole policy drops to the `no_policy` rung.
    policy = load_policy("policy_full.yaml")
    region = policy["mandate"]["sub_allocations"]["dimensions"]["region"]
    region["code_list"] = "parallax_region_v2"
    region["strategic_allocation"]["us"] = 0.45
    region["strategic_allocation"]["atlantis"] = 0.10        # sum stays 1.0
    hits = [e for e in adaptation.validate_policy(policy)
            if e.path == "mandate.sub_allocations.dimensions.region.code_list"]
    assert len(hits) == 1
    assert hits[0].severity == "blocking"

    result = adaptation.run_pipeline(
        policy, load_json("exposures_sample.json"), load_json("view_tilts_sample.json")
    )
    assert result.fallback_tier == "no_policy"
    assert result.drift == [] and result.taa == []
    # An ABSENT code list is unrecognized too — the key set is never guessed.
    del region["code_list"]
    assert any(e.path.endswith(".region.code_list") and e.severity == "blocking"
               for e in adaptation.validate_policy(policy))
    # Both code lists declared by the shipped fixtures stay clean.
    assert adaptation.validate_policy(load_policy("policy_full.yaml")) == []


def test_unknown_segment_key_is_a_data_quality_row_not_an_error():
    policy = load_policy("policy_full.yaml")
    weights = region_weights(policy)
    weights["us"] = 0.45
    weights["atlantis"] = 0.10          # not in parallax_region_v1; sum stays 1.0
    assert not any(
        "atlantis" in e.path for e in adaptation.validate_policy(policy)
    )
    result = adaptation.run_pipeline(
        policy, load_json("exposures_sample.json"), load_json("view_tilts_sample.json")
    )
    rows = [r for r in result.data_quality if r.kind == "unknown_segment_key"]
    assert len(rows) == 1
    assert "atlantis" in rows[0].detail
    assert "atlantis" not in {r.key for r in result.drift}
    assert "atlantis" not in {r.key for r in result.taa}


def test_stale_policy_is_a_row_not_a_block():
    policy = load_policy("policy_full.yaml")          # review_due 2026-12-31
    exposures = load_json("exposures_sample.json")
    tilts = load_json("view_tilts_sample.json")

    fresh = adaptation.run_pipeline(policy, exposures, tilts, today=date(2026, 8, 29))
    assert [r for r in fresh.data_quality if r.kind == "stale_policy"] == []

    stale = adaptation.run_pipeline(policy, exposures, tilts, today=date(2027, 1, 15))
    rows = [r for r in stale.data_quality if r.kind == "stale_policy"]
    assert len(rows) == 1
    assert "2026-12-31" in rows[0].detail
    # Never a block: the tier and the rows are unchanged.
    assert stale.fallback_tier == fresh.fallback_tier == "full"
    assert len(stale.drift) == len(fresh.drift) == 7


def test_te_budget_present_emits_not_evaluated_row():
    policy = load_policy("policy_full.yaml")
    policy["mandate"]["tactical_overlay"]["max_tracking_error"] = 0.03
    result = adaptation.run_pipeline(
        policy, load_json("exposures_sample.json"), load_json("view_tilts_sample.json")
    )
    rows = [r for r in result.data_quality if r.kind == "te_budget_not_evaluated"]
    assert len(rows) == 1
    assert "0.03" in rows[0].detail
    # Validated and carried, never evaluated: no proxy math anywhere in the result.
    assert adaptation.validate_policy(policy) == []
    assert result.fallback_tier == "full"

    absent = adaptation.run_pipeline(
        load_policy("policy_full.yaml"),
        load_json("exposures_sample.json"),
        load_json("view_tilts_sample.json"),
    )
    assert [r for r in absent.data_quality if r.kind == "te_budget_not_evaluated"] == []


def test_one_sided_band_emits_missing_bands_row():
    result = adaptation.run_pipeline(
        load_policy("policy_partial_dims.yaml"),
        load_json("exposures_sample.json"),
        load_json("view_tilts_sample.json"),
    )
    rows = [r for r in result.data_quality if r.kind == "missing_bands"]
    assert len(rows) == 1
    assert "europe" in rows[0].detail
    europe = next(r for r in result.taa if r.key == "europe")
    assert europe.room_down == pytest.approx(0.07)
    assert europe.room_up is None
    # P-1: the missing side is never inferred; an upward tilt cannot be evaluated.
    upward = copy.deepcopy(load_json("view_tilts_sample.json"))
    upward["regions"]["europe"] = 1
    tilted = adaptation.run_pipeline(
        load_policy("policy_partial_dims.yaml"), load_json("exposures_sample.json"), upward
    )
    europe_tilted = next(r for r in tilted.taa if r.key == "europe")
    assert europe_tilted.desired_active is None
    assert europe_tilted.alignment == "not_evaluable"
