"""Unit tests for the client-policy adaptation helper (invariants 1-5, 7-11).

Invariant 6 (basis conversion) and the validator surface live in
`test_policy_validation.py`. There is deliberately no `conftest.py`:
`skills/_parallax` is one auto-discovered pytest root and its single conftest
slot is already occupied, so both files use the module-level sys.path idiom
instead (same as `house-view/tests/test_view_status.py`).
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).parent
CLIENT_POLICY_DIR = HERE.parent
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(CLIENT_POLICY_DIR))

import adaptation  # noqa: E402

MODULE = CLIENT_POLICY_DIR / "adaptation.py"


# --------------------------------------------------------------------------
# Fixture loading helpers (plain functions — no conftest, no pytest fixtures).
# --------------------------------------------------------------------------

def load_policy(name: str) -> dict:
    with (FIXTURES / name).open() as f:
        return yaml.safe_load(f)


def load_json(name: str) -> dict:
    with (FIXTURES / name).open() as f:
        return json.load(f)


def full_policy() -> dict:
    return load_policy("policy_full.yaml")


def sample_exposures() -> dict:
    return load_json("exposures_sample.json")


def sample_tilts() -> dict:
    return load_json("view_tilts_sample.json")


def india_policy() -> dict:
    """policy_full with `em_ex_china` renamed to `india`, a member of two broad buckets."""
    policy = full_policy()
    region = policy["mandate"]["sub_allocations"]["dimensions"]["region"]
    region["strategic_allocation"]["india"] = region["strategic_allocation"].pop("em_ex_china")
    region["allocation_bands"]["india"] = region["allocation_bands"].pop("em_ex_china")
    return policy


def india_exposures() -> dict:
    exposures = sample_exposures()
    exposures["dimensions"]["region"]["india"] = exposures["dimensions"]["region"].pop("em_ex_china")
    return exposures


def taa_row(key: str, desired, tilt: int = 1, dimension: str = "region"):
    """A synthetic TaaRow for unit-testing apply_budget_cap in isolation."""
    return adaptation.TaaRow(
        dimension=dimension,
        key=key,
        tilt=tilt,
        current_active=0.0,
        room_up=0.10,
        room_down=0.10,
        desired_active=desired,
        budget_scale=1.0,
        semantics="policy",
        alignment="aligned",
    )


def row_by_key(rows, dimension: str, key: str):
    for r in rows:
        if r.dimension == dimension and r.key == key:
            return r
    raise AssertionError(f"no row for {dimension}.{key} in {[(r.dimension, r.key) for r in rows]}")


# ==========================================================================
# Invariant 1 — k scaling
# ==========================================================================

def test_k_preset_resolves_each_of_three_values():
    for preset, expected in (("conservative", 0.25), ("balanced", 0.50), ("aggressive", 0.75)):
        policy = {"adaptation": {"k_preset": preset, "k": None}}
        k, source = adaptation.resolve_k(policy)
        assert k == pytest.approx(expected)
        assert source == f"preset:{preset}"


def test_explicit_k_wins_over_preset():
    policy = {"adaptation": {"k_preset": "conservative", "k": 0.75}}
    k, source = adaptation.resolve_k(policy)
    assert k == pytest.approx(0.75)
    assert source == "explicit"


def test_absent_both_defaults_to_half_with_default_source():
    k, source = adaptation.resolve_k({"adaptation": {}})
    assert k == pytest.approx(adaptation.DEFAULT_K) == pytest.approx(0.50)
    assert source == "default"
    # A policy with no `adaptation` section at all behaves identically.
    assert adaptation.resolve_k({}) == (adaptation.DEFAULT_K, "default")


def test_k_above_one_is_rejected_and_falls_back():
    policy = {"metadata": {"schema_version": 1}, "adaptation": {"k_preset": "balanced", "k": 1.5}}
    paths = [e.path for e in adaptation.validate_policy(policy)]
    assert "adaptation.k" in paths
    # Never clamped to 1.0 — it falls through to the preset.
    assert adaptation.resolve_k(policy) == (0.50, "preset:balanced")


def test_k_zero_or_negative_is_rejected():
    for bad in (0, 0.0, -0.2):
        policy = {"metadata": {"schema_version": 1}, "adaptation": {"k_preset": None, "k": bad}}
        paths = [e.path for e in adaptation.validate_policy(policy)]
        assert "adaptation.k" in paths, f"k={bad!r} should be rejected"
        assert adaptation.resolve_k(policy) == (adaptation.DEFAULT_K, "default")


def test_desired_active_is_linear_in_k():
    half = adaptation.desired_active(1, 0.50, 0.10, 0.10)
    quarter = adaptation.desired_active(1, 0.25, 0.10, 0.10)
    assert half == pytest.approx(2 * quarter)
    assert half == pytest.approx(0.025)


# ==========================================================================
# Invariant 2 — budget capping
# ==========================================================================

def test_cap_scales_all_actives_by_one_factor():
    rows = [taa_row("a", 0.06), taa_row("b", -0.04), taa_row("c", 0.02)]
    capped, scale, applied = adaptation.apply_budget_cap(rows, 0.10)
    assert applied is True
    assert scale == pytest.approx(0.10 / 0.12)
    assert [r.desired_active for r in capped] == pytest.approx([0.06 * scale, -0.04 * scale, 0.02 * scale])
    assert [r.budget_scale for r in capped] == pytest.approx([scale, scale, scale])


def test_post_cap_sum_equals_budget_within_tolerance():
    rows = [taa_row("a", 0.06), taa_row("b", -0.04), taa_row("c", 0.02)]
    capped, _, _ = adaptation.apply_budget_cap(rows, 0.10)
    assert sum(abs(r.desired_active) for r in capped) == pytest.approx(0.10, abs=1e-12)


def test_cap_preserves_pairwise_ratios():
    rows = [taa_row("a", 0.06), taa_row("b", -0.04), taa_row("c", 0.02)]
    capped, _, _ = adaptation.apply_budget_cap(rows, 0.10)
    before = rows[0].desired_active / rows[1].desired_active
    after = capped[0].desired_active / capped[1].desired_active
    assert after == pytest.approx(before)


def test_no_cap_when_under_budget_leaves_scale_one():
    rows = [taa_row("a", 0.02), taa_row("b", -0.01), taa_row("c", None)]
    capped, scale, applied = adaptation.apply_budget_cap(rows, 0.10)
    assert (scale, applied) == (1.0, False)
    assert [r.desired_active for r in capped] == [0.02, -0.01, None]
    # A null desired active is excluded from the sum and untouched by the scale.
    assert capped[2].desired_active is None


def test_cap_applied_flag_tracks_the_cap():
    over = [taa_row("a", 0.20)]
    under = [taa_row("a", 0.05)]
    assert adaptation.apply_budget_cap(over, 0.10)[2] is True
    assert adaptation.apply_budget_cap(under, 0.10)[2] is False
    # No budget declared: the cap can never fire.
    assert adaptation.apply_budget_cap(over, None)[2] is False
    # An all-null row set has total 0.0 and cannot fire the cap either.
    assert adaptation.apply_budget_cap([taa_row("a", None)], 0.10)[2] is False


# ==========================================================================
# Invariant 3 — room math and sign
# ==========================================================================

def test_positive_tilt_uses_room_up():
    # room_up 0.10, room_down 0.04 — a positive tilt must read room_up only.
    assert adaptation.desired_active(1, 0.50, 0.10, 0.04) == pytest.approx(0.025)


def test_negative_tilt_uses_room_down_and_signs_negative():
    got = adaptation.desired_active(-1, 0.50, 0.10, 0.04)
    assert got == pytest.approx(-0.01)
    assert got < 0


def test_tilt_two_gives_full_k_times_room():
    assert adaptation.desired_active(2, 0.50, 0.10, 0.10) == pytest.approx(1.0 * 0.50 * 0.10)
    assert adaptation.desired_active(-2, 0.50, 0.10, 0.10) == pytest.approx(-1.0 * 0.50 * 0.10)


def test_tilt_one_gives_half():
    assert adaptation.desired_active(1, 0.50, 0.10, 0.10) == pytest.approx(
        0.5 * adaptation.desired_active(2, 0.50, 0.10, 0.10)
    )


def test_tilt_zero_gives_zero():
    assert adaptation.desired_active(0, 0.50, 0.10, 0.10) == 0.0
    # Zero tilt returns 0.0 even when neither side has a band.
    assert adaptation.desired_active(0, 0.50, None, None) == 0.0


# ==========================================================================
# Invariant 4 — band-status classification
# ==========================================================================

def test_current_above_max_is_breach_high():
    assert adaptation.band_status(1.1, 0.5, 0.0, 1.0) == "breach_high"
    assert adaptation.band_status(-0.1, 0.5, 0.0, 1.0) == "breach_low"


def test_current_exactly_at_max_is_near_edge_high():
    # Distance 0 is the most sensitive case, not a degenerate one (conventions §11.3).
    assert adaptation.band_status(1.0, 0.5, 0.0, 1.0) == "near_edge_high"


def test_current_exactly_at_min_is_near_edge_low():
    assert adaptation.band_status(0.0, 0.5, 0.0, 1.0) == "near_edge_low"


def test_near_edge_threshold_arithmetic_both_sides():
    # room_up = room_down = 0.5, threshold = 0.20 * 0.5 = 0.10.
    assert adaptation.band_status(0.9, 0.5, 0.0, 1.0) == "near_edge_high"
    assert adaptation.band_status(0.1, 0.5, 0.0, 1.0) == "near_edge_low"


def test_just_inside_threshold_is_inside():
    assert adaptation.band_status(0.85, 0.5, 0.0, 1.0) == "inside"
    assert adaptation.band_status(0.15, 0.5, 0.0, 1.0) == "inside"


def test_no_bands_when_both_edges_absent():
    assert adaptation.band_status(0.5, 0.5, None, None) == "no_bands"
    # One edge present is NOT `no_bands`; the present side still classifies.
    assert adaptation.band_status(0.5, 0.5, None, 1.0) == "inside"


def test_zero_width_band_prefers_breach_over_near_edge():
    # policy == band_max: room_up is 0, so every near-edge test would match.
    # Breach is evaluated first, so a current above the edge reads breach_high.
    assert adaptation.band_status(0.6, 0.5, 0.4, 0.5) == "breach_high"
    assert adaptation.band_status(0.4, 0.5, 0.5, 0.6) == "breach_low"


# ==========================================================================
# Invariant 5 — breach attribution (passive vs active)
# ==========================================================================

def _one_segment(policy=0.55, band_min=0.45, band_max=0.65):
    return [adaptation.Segment("region", "us", policy, band_min, band_max)]


def test_breach_with_zero_tilt_is_passive():
    rows = adaptation.compute_drift(_one_segment(), {"region": {"us": 0.70}}, {})
    assert rows[0].band_status == "breach_high"
    assert rows[0].breach_kind == "passive"


def test_breach_with_same_sign_tilt_is_active():
    rows = adaptation.compute_drift(
        _one_segment(), {"region": {"us": 0.70}}, {"regions": {"us": 1}}
    )
    assert rows[0].band_status == "breach_high"
    assert rows[0].breach_kind == "active"


def test_breach_with_opposite_sign_tilt_is_passive():
    rows = adaptation.compute_drift(
        _one_segment(), {"region": {"us": 0.70}}, {"regions": {"us": -1}}
    )
    assert rows[0].band_status == "breach_high"
    assert rows[0].breach_kind == "passive"
    # A non-breaching row carries no attribution at all.
    inside = adaptation.compute_drift(
        _one_segment(), {"region": {"us": 0.55}}, {"regions": {"us": 1}}
    )
    assert inside[0].band_status == "inside"
    assert inside[0].breach_kind is None


# ==========================================================================
# §4.2.7 — broad-vs-specific tilt precedence
# ==========================================================================

def test_specific_region_tilt_wins_over_broad():
    tilts = {"regions": {"europe": 2, "germany": -1}}
    # `germany` is a member of the `europe` bucket but carries its own tilt.
    assert adaptation.resolve_tilt("region", "germany", tilts) == -1
    # A sibling member with no specific tilt inherits the bucket.
    assert adaptation.resolve_tilt("region", "france", tilts) == 2
    # Never summed: -1 and +2 do not combine into +1.
    assert adaptation.resolve_tilt("region", "germany", tilts) != 1


def test_broad_bucket_tilt_inherited_by_member():
    tilts = {"regions": {"em_ex_china": 1}}
    assert adaptation.resolve_tilt("region", "brazil", tilts) == 1
    assert adaptation.resolve_tilt("region", "mexico", tilts) == 1
    # A non-member inherits nothing.
    assert adaptation.resolve_tilt("region", "us", tilts) == 0
    # The bucket key itself resolves to its own tilt, not by inheritance.
    assert adaptation.resolve_tilt("region", "em_ex_china", tilts) == 1
    # Sector keys have no broad buckets at all.
    assert adaptation.resolve_tilt("sector", "financials", {"sectors": {"energy": 2}}) == 0


def test_overlapping_broad_tilts_agreeing_inherit():
    # `india` is a member of both `apac_ex_japan` and `em_ex_china`.
    tilts = {"regions": {"apac_ex_japan": -1, "em_ex_china": -1}}
    assert adaptation.resolve_tilt("region", "india", tilts) == -1
    result = adaptation.run_pipeline(india_policy(), india_exposures(), tilts)
    assert [r for r in result.data_quality if r.kind == "ambiguous_broad_tilt"] == []
    assert row_by_key(result.taa, "region", "india").tilt == -1


def test_overlapping_broad_tilts_differing_zero_with_disclosure():
    tilts = {"regions": {"apac_ex_japan": 1, "em_ex_china": -2}}
    assert adaptation.resolve_tilt("region", "india", tilts) == 0
    result = adaptation.run_pipeline(india_policy(), india_exposures(), tilts)
    rows = [r for r in result.data_quality if r.kind == "ambiguous_broad_tilt"]
    assert len(rows) == 1
    assert "india" in rows[0].detail
    assert "apac_ex_japan" in rows[0].detail and "em_ex_china" in rows[0].detail
    india = row_by_key(result.taa, "region", "india")
    assert india.tilt == 0
    assert india.alignment == "no_view"
    # A specific tilt on the same key overrides both buckets and clears the disclosure.
    tilts["regions"]["india"] = 2
    resolved = adaptation.run_pipeline(india_policy(), india_exposures(), tilts)
    assert [r for r in resolved.data_quality if r.kind == "ambiguous_broad_tilt"] == []
    assert row_by_key(resolved.taa, "region", "india").tilt == 2


# ==========================================================================
# Invariant 7 — fallback ladder
# ==========================================================================

def test_tier_no_policy_returns_empty_result():
    result = adaptation.run_pipeline(None, sample_exposures(), sample_tilts())
    assert result.fallback_tier == "no_policy"
    assert result.drift == []
    assert result.taa == []
    assert result.errors == []
    assert result.policy_hash == ""


def test_tier_weights_only_marks_every_row_multiplier_fallback():
    result = adaptation.run_pipeline(
        load_policy("policy_weights_only.yaml"), sample_exposures(), sample_tilts()
    )
    assert result.fallback_tier == "weights_only"
    assert result.taa != []
    assert {r.semantics for r in result.taa} == {"multiplier_fallback"}
    assert all(r.desired_active is None for r in result.taa)
    # Drift still renders; the budget line degrades to a sum-of-absolute-drift diagnostic.
    assert len(result.drift) == 7
    assert {r.band_status for r in result.drift} == {"no_bands"}
    assert result.budget["sum_abs_desired"] == pytest.approx(0.32)
    assert result.budget["cap_applied"] is False
    assert result.budget["scale"] == 1.0


def test_tier_full_marks_every_row_policy():
    result = adaptation.run_pipeline(full_policy(), sample_exposures(), sample_tilts())
    assert result.fallback_tier == "full"
    assert {r.semantics for r in result.taa} == {"policy"}
    assert len(result.taa) == 7


def test_tier_partial_dimensions_mixes_semantics_per_segment():
    result = adaptation.run_pipeline(
        load_policy("policy_partial_dims.yaml"), sample_exposures(), sample_tilts()
    )
    assert result.fallback_tier == "partial_dimensions"
    semantics = {(r.dimension, r.key): r.semantics for r in result.taa}
    assert semantics[("region", "us")] == "policy"            # two-sided band
    assert semantics[("region", "europe")] == "policy"        # one-sided band still evaluates
    assert semantics[("region", "japan")] == "multiplier_fallback"
    assert semantics[("region", "em_ex_china")] == "multiplier_fallback"


def test_uncovered_dimension_is_absent_from_drift_and_flagged():
    result = adaptation.run_pipeline(
        load_policy("policy_partial_dims.yaml"), sample_exposures(), sample_tilts()
    )
    assert {r.dimension for r in result.drift} == {"region"}
    assert {r.dimension for r in result.taa} == {"region"}
    flags = [r for r in result.data_quality if r.kind == "uncovered_dimension"]
    assert len(flags) == 1
    assert "sector" in flags[0].detail


# ==========================================================================
# Invariant 8 — capped_by_band
# ==========================================================================

def _no_room_up_policy() -> dict:
    """policy_full with the `us` band max pulled down onto the policy weight."""
    policy = full_policy()
    dims = policy["mandate"]["sub_allocations"]["dimensions"]
    dims["region"]["allocation_bands"]["us"] = {"min": 0.45, "max": 0.55}
    return policy


def test_nonzero_tilt_with_no_room_is_capped_by_band_and_desired_zero():
    exposures = sample_exposures()
    exposures["dimensions"]["region"] = {
        "us": 0.55, "europe": 0.25, "japan": 0.10, "em_ex_china": 0.10,
    }
    result = adaptation.run_pipeline(_no_room_up_policy(), exposures, sample_tilts())
    us = row_by_key(result.taa, "region", "us")
    assert us.tilt == 1
    assert us.room_up == pytest.approx(0.0)
    assert us.desired_active == 0.0
    assert us.alignment == "capped_by_band"
    # The direct helper agrees with the pipeline.
    assert adaptation.classify_alignment(0.0, 0.0, 1, 0.0) == "capped_by_band"


def test_capped_row_contributes_zero_to_the_budget():
    exposures = sample_exposures()
    exposures["dimensions"]["region"] = {
        "us": 0.55, "europe": 0.25, "japan": 0.10, "em_ex_china": 0.10,
    }
    result = adaptation.run_pipeline(_no_room_up_policy(), exposures, sample_tilts())
    us = row_by_key(result.taa, "region", "us")
    assert us.desired_active == 0.0
    others = sum(abs(r.desired_active) for r in result.taa
                 if r.desired_active is not None and (r.dimension, r.key) != ("region", "us"))
    assert result.budget["sum_abs_desired"] == pytest.approx(others)


# ==========================================================================
# Invariant 9 — conflicts (never auto-resolved)
# ==========================================================================

def test_tilt_toward_a_breached_edge_emits_tilt_vs_band():
    result = adaptation.run_pipeline(full_policy(), sample_exposures(), sample_tilts())
    us_drift = row_by_key(result.drift, "region", "us")
    assert us_drift.band_status == "breach_high"
    hits = [c for c in result.conflicts
            if c.kind == "tilt_vs_band" and c.detail["key"] == "us"]
    assert len(hits) == 1
    assert hits[0].detail["tilt"] == 1
    assert "breach" in hits[0].detail["reason"]


def test_desired_active_crossing_the_edge_emits_tilt_vs_band():
    # R-5 replaced the "current + desired would cross the edge" trigger with the
    # room-based one: no room in the tilt direction means any tilt is unsatisfiable.
    exposures = sample_exposures()
    exposures["dimensions"]["region"] = {
        "us": 0.55, "europe": 0.25, "japan": 0.10, "em_ex_china": 0.10,
    }
    result = adaptation.run_pipeline(_no_room_up_policy(), exposures, sample_tilts())
    hits = [c for c in result.conflicts
            if c.kind == "tilt_vs_band" and c.detail["key"] == "us"]
    assert len(hits) == 1
    assert "room" in hits[0].detail["reason"]
    assert hits[0].detail["projected_target"] == pytest.approx(0.55)


def test_holding_on_view_excludes_emits_exclude_vs_holding():
    result = adaptation.run_pipeline(full_policy(), sample_exposures(), sample_tilts())
    hits = [c for c in result.conflicts if c.kind == "exclude_vs_holding"]
    assert [c.detail["symbol"] for c in hits] == ["GAZP.MM"]
    assert hits[0].detail["matched_on"] == "symbol"
    assert hits[0].detail["exclude_entry"] == "GAZP.MM"
    assert hits[0].detail["weight"] == pytest.approx(0.04)


def test_holding_in_prohibited_products_emits_prohibited_vs_holding():
    result = adaptation.run_pipeline(full_policy(), sample_exposures(), sample_tilts())
    hits = [c for c in result.conflicts if c.kind == "prohibited_vs_holding"]
    assert [c.detail["symbol"] for c in hits] == ["XYZ.OQ"]
    assert hits[0].detail["prohibited_entry"] == "XYZ.OQ"


def test_conflicts_are_never_auto_resolved():
    result = adaptation.run_pipeline(full_policy(), sample_exposures(), sample_tilts())
    kinds = {c.kind for c in result.conflicts}
    assert {"tilt_vs_band", "exclude_vs_holding", "prohibited_vs_holding"} <= kinds
    # The excluded and prohibited holdings are surfaced, never dropped or netted out:
    # every policy segment still renders and the tilted rows keep their sizing.
    assert len(result.drift) == 7
    assert len(result.taa) == 7
    us = row_by_key(result.taa, "region", "us")
    assert us.desired_active == pytest.approx(0.025)
    assert us.alignment == "aligned"


# ==========================================================================
# R-3 — tactical overlay disabled
# ==========================================================================

def test_overlay_disabled_skips_s2_but_keeps_drift():
    policy = full_policy()
    policy["mandate"]["tactical_overlay"]["enabled"] = False
    result = adaptation.run_pipeline(policy, sample_exposures(), sample_tilts())
    assert result.taa == []
    assert len(result.drift) == 7
    assert row_by_key(result.drift, "region", "us").band_status == "breach_high"
    assert result.budget["sum_abs_desired"] == 0.0
    assert result.budget["cap_applied"] is False


# ==========================================================================
# Invariant 10 — policy_hash
# ==========================================================================

def _hash_fixture() -> tuple[dict, str]:
    doc = load_policy("policy_hash_fixture.yaml")
    expected = doc.pop("expected_policy_hash")
    return doc, expected


def test_policy_hash_matches_pinned_digest():
    doc, expected = _hash_fixture()
    assert adaptation.compute_policy_hash(doc) == expected


def test_policy_hash_unchanged_by_metadata_edits():
    doc, expected = _hash_fixture()
    edited = copy.deepcopy(doc)
    edited["metadata"]["supplied_at"] = "2027-01-02T03:04:05Z"
    edited["metadata"]["policy_name"] = "Renamed"
    assert adaptation.compute_policy_hash(edited) == expected


def test_policy_hash_unchanged_by_governance_edits():
    doc, expected = _hash_fixture()
    edited = copy.deepcopy(doc)
    edited["governance"]["human_review_recorded"] = [
        {"ts": "2026-08-29T11:00:00Z", "by": "rm@firm.example",
         "segment": "region.us", "override": "band max", "rationale": "documented"}
    ]
    assert adaptation.compute_policy_hash(edited) == expected


def test_policy_hash_strips_zeros_bool_guard_holds():
    doc, _ = _hash_fixture()
    # A numeric-zero band edge hashes identically to a missing one (P-3 footnote).
    without_zero = copy.deepcopy(doc)
    without_zero["mandate"]["allocation_bands"]["equity"].pop("min")
    assert adaptation.compute_policy_hash(without_zero) == adaptation.compute_policy_hash(doc)
    # `False` is NOT stripped: dropping it must move the digest.
    without_bool = copy.deepcopy(doc)
    without_bool["mandate"]["tactical_overlay"].pop("enabled")
    assert adaptation.compute_policy_hash(without_bool) != adaptation.compute_policy_hash(doc)
    # And the guard holds at the primitive level.
    assert adaptation._is_empty(False) is False
    assert adaptation._is_empty(0) is True
    assert adaptation._is_empty(0.0) is True
    assert adaptation._strip_empty({"a": {"b": {}}, "c": False}) == {"c": False}


# ==========================================================================
# Invariant 11 — CLI (subprocess, so argv parsing and exit codes are real)
# ==========================================================================

def run_cli(*args: str):
    return subprocess.run(
        [sys.executable, str(MODULE), *args],
        capture_output=True, text=True,
    )


def test_cli_json_round_trips_through_json_loads():
    proc = run_cli(
        "--policy", str(FIXTURES / "policy_full.yaml"),
        "--exposures", str(FIXTURES / "exposures_sample.json"),
        "--view-tilts", str(FIXTURES / "view_tilts_sample.json"),
        "--json",
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["fallback_tier"] == "full"
    assert len(payload["drift"]) == 7
    assert len(payload["taa"]) == 7
    assert isinstance(payload["budget"], dict)


def test_cli_carries_calibration_resolved_k_k_source_policy_hash():
    proc = run_cli(
        "--policy", str(FIXTURES / "policy_full.yaml"),
        "--exposures", str(FIXTURES / "exposures_sample.json"),
        "--view-tilts", str(FIXTURES / "view_tilts_sample.json"),
        "--today", "2026-08-29",
        "--json",
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["calibration_status"] == adaptation.CALIBRATION_STATUS
    assert payload["resolved_k"] == pytest.approx(0.50)
    assert payload["k_source"] == "preset:balanced"
    assert payload["near_edge_fraction"] == pytest.approx(adaptation.NEAR_EDGE_FRACTION)
    assert len(payload["policy_hash"]) == 64


def test_cli_policy_only_returns_no_policy_rows_and_exit_zero():
    # No exposures payload: there is nothing to compare the policy against, so no
    # drift and no TAA rows are produced. The tier still resolves from the policy
    # structure and the exit code stays 0 (C-2: data-level outcomes never exit nonzero).
    proc = run_cli("--policy", str(FIXTURES / "policy_full.yaml"), "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["drift"] == []
    assert payload["taa"] == []
    assert payload["fallback_tier"] == "full"
    assert payload["errors"] == []


def test_cli_invalid_policy_exits_zero_with_errors_in_json():
    proc = run_cli("--policy", str(FIXTURES / "policy_invalid.yaml"), "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["fallback_tier"] == "no_policy"
    assert payload["drift"] == []
    assert payload["taa"] == []
    assert len(payload["errors"]) >= 5
    assert len(payload["policy_hash"]) == 64


def test_cli_non_mapping_policy_exits_zero_with_blocking_error(tmp_path: Path):
    # Parseable YAML that is not a mapping is a DATA problem, not a read problem:
    # exit 0 with a blocking error, never an unhandled exception.
    for name, body in (("list.yaml", "- a\n- b\n"), ("scalar.yaml", "42\n")):
        path = tmp_path / name
        path.write_text(body)
        proc = run_cli("--policy", str(path), "--json")
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["fallback_tier"] == "no_policy"
        assert payload["drift"] == [] and payload["taa"] == []
        assert payload["errors"] != []
        assert any(e["severity"] == "blocking" for e in payload["errors"])
        # R-2: `policy_hash` is carried only when the policy parsed as a mapping.
        assert payload["policy_hash"] == ""


def test_cli_non_mapping_exposures_exits_two(tmp_path: Path):
    # An exposures payload that is not a JSON object is an operator mistake,
    # graded with the unreadable/unparseable class.
    for name, body in (("arr.json", "[1, 2, 3]\n"), ("scalar.json", "42\n")):
        path = tmp_path / name
        path.write_text(body)
        proc = run_cli("--policy", str(FIXTURES / "policy_full.yaml"),
                       "--exposures", str(path), "--json")
        assert proc.returncode == 2, proc.stdout


def test_cli_exposures_missing_basis_exits_two(tmp_path: Path):
    # I2: Phase 1 accepts sleeve-relative exposures only. An absent `basis` is
    # never assumed to be "sleeve" — it is graded as an operator mistake, exit
    # 2, naming the file and the offending value.
    exposures = sample_exposures()
    del exposures["basis"]
    path = tmp_path / "exposures_no_basis.json"
    path.write_text(json.dumps(exposures))
    proc = run_cli("--policy", str(FIXTURES / "policy_full.yaml"),
                   "--exposures", str(path), "--json")
    assert proc.returncode == 2, proc.stdout
    assert "basis" in proc.stderr
    assert str(path) in proc.stderr


def test_cli_exposures_non_sleeve_basis_exits_two(tmp_path: Path):
    # A "total"-basis exposures payload is a Phase-1-scoped rejection, not a
    # silent mis-score: no conversion is implemented for this payload.
    exposures = sample_exposures()
    exposures["basis"] = "total"
    path = tmp_path / "exposures_total_basis.json"
    path.write_text(json.dumps(exposures))
    proc = run_cli("--policy", str(FIXTURES / "policy_full.yaml"),
                   "--exposures", str(path), "--json")
    assert proc.returncode == 2, proc.stdout
    assert "total" in proc.stderr
    assert str(path) in proc.stderr


def test_cli_non_mapping_view_tilts_exits_two(tmp_path: Path):
    for name, body in (("arr.json", "[1, 2, 3]\n"), ("scalar.json", '"us"\n')):
        path = tmp_path / name
        path.write_text(body)
        proc = run_cli("--policy", str(FIXTURES / "policy_full.yaml"),
                       "--exposures", str(FIXTURES / "exposures_sample.json"),
                       "--view-tilts", str(path), "--json")
        assert proc.returncode == 2, proc.stdout


def test_cli_unreadable_file_exits_two(tmp_path: Path):
    missing = run_cli("--policy", str(tmp_path / "does_not_exist.yaml"), "--json")
    assert missing.returncode == 2
    broken = tmp_path / "broken.yaml"
    broken.write_text("mandate: [unclosed\n")
    assert run_cli("--policy", str(broken), "--json").returncode == 2
    # Bad arguments exit 2 as well (argparse convention).
    assert run_cli("--nope").returncode == 2


# ==========================================================================
# R1 — the exposures payload is validated against its pinned contract
# ==========================================================================

def _write_exposures(tmp_path: Path, exposures: dict, name: str = "exposures.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(exposures))
    return path


def test_cli_exposures_weight_out_of_range_exits_two(tmp_path: Path):
    # The audited probe: region weights {us: 1.2, europe: -0.2} were accepted and
    # rendered `breach_high` / `breach_low` — an impossible input certified as a
    # band verdict. Out-of-range weights are an operator mistake, graded exit 2.
    exposures = sample_exposures()
    exposures["dimensions"]["region"] = {"us": 1.2, "europe": -0.2}
    path = _write_exposures(tmp_path, exposures)
    proc = run_cli("--policy", str(FIXTURES / "policy_full.yaml"),
                   "--exposures", str(path), "--json")
    assert proc.returncode == 2, proc.stdout
    assert str(path) in proc.stderr
    assert "1.2" in proc.stderr or "us" in proc.stderr


def test_cli_exposures_sum_violation_exits_two(tmp_path: Path):
    # Mapped weights must sum to 1.0 within SUM_TOLERANCE; a dimension that does
    # not sum cannot be compared with a policy weight defined over the sleeve.
    exposures = sample_exposures()
    exposures["dimensions"]["sector"] = {"information_technology": 0.40,
                                         "financials": 0.25, "health_care": 0.20}
    path = _write_exposures(tmp_path, exposures)
    proc = run_cli("--policy", str(FIXTURES / "policy_full.yaml"),
                   "--exposures", str(path), "--json")
    assert proc.returncode == 2, proc.stdout
    assert "sector" in proc.stderr


def test_cli_exposures_coverage_inconsistent_exits_two(tmp_path: Path):
    # The audited probe: coverage.region = 0.50 with `unmapped: []` produced no
    # disclosure at all. Coverage must agree with the unmapped weight it implies.
    exposures = sample_exposures()
    exposures["coverage"]["region"] = 0.50
    exposures["unmapped"] = []
    path = _write_exposures(tmp_path, exposures)
    proc = run_cli("--policy", str(FIXTURES / "policy_full.yaml"),
                   "--exposures", str(path), "--json")
    assert proc.returncode == 2, proc.stdout
    assert "coverage" in proc.stderr


def test_pipeline_invalid_exposures_degrades_with_disclosure():
    # Called as a library (not via the CLI) the helper never raises and never
    # certifies the payload: it proceeds WITHOUT exposures and discloses one
    # `invalid_exposures` row per violation.
    exposures = sample_exposures()
    exposures["dimensions"]["region"] = {"us": 1.2, "europe": -0.2}
    result = adaptation.run_pipeline(full_policy(), exposures, sample_tilts())
    assert result.drift == []
    assert result.taa == []
    assert result.conflicts == []
    rows = [r for r in result.data_quality if r.kind == "invalid_exposures"]
    assert len(rows) == len(adaptation.validate_exposures(exposures))
    assert rows != []
    # No unmapped_holding row leaks from a payload that was rejected.
    assert [r for r in result.data_quality if r.kind == "unmapped_holding"] == []
    assert result.coverage == {}


def test_validate_exposures_accepts_the_pinned_sample():
    assert adaptation.validate_exposures(sample_exposures()) == []


# ==========================================================================
# R2 — hard-constraint matching honesty
# ==========================================================================

def test_prohibited_matches_isin_when_provided():
    # The audited probe: a policy prohibiting an ISIN against a holding carrying
    # that ISIN produced `conflicts = []`.
    policy = full_policy()
    policy["mandate"]["prohibited_products"] = ["us0378331005"]
    exposures = sample_exposures()
    exposures["holdings"] = [{"symbol": "AAPL.O", "isin": "US0378331005", "weight": 0.25,
                              "region": "us", "sector": "information_technology"}]
    result = adaptation.run_pipeline(policy, exposures, sample_tilts())
    rows = [c for c in result.conflicts if c.kind == "prohibited_vs_holding"]
    assert len(rows) == 1
    assert rows[0].detail["symbol"] == "AAPL.O"
    assert rows[0].detail["matched_on"] == "isin"


def test_theme_exclude_emits_not_checkable_row():
    # A theme/category exclude is neither a known region key, nor a known sector
    # key, nor a holding symbol. The helper cannot classify it, so an empty
    # Conflicts table must not read as "checked clean".
    result = adaptation.run_pipeline(full_policy(), sample_exposures(), sample_tilts())
    rows = [r for r in result.data_quality if r.kind == "hard_constraint_not_checkable"]
    assert len(rows) == 1
    assert "tobacco" in rows[0].detail


def test_isin_prohibition_without_holding_isin_emits_not_checkable_row():
    policy = full_policy()
    policy["mandate"]["prohibited_products"] = ["US0378331005"]
    exposures = sample_exposures()          # no holding carries an `isin`
    result = adaptation.run_pipeline(policy, exposures, sample_tilts())
    rows = [r for r in result.data_quality if r.kind == "hard_constraint_not_checkable"
            and "isin" in r.detail.lower()]
    assert len(rows) == 1


# ==========================================================================
# R4 — conditional-estimate honesty
# ==========================================================================

def test_off_policy_exposure_disclosed():
    # The audited probe: a 5% Canada exposure absent from the policy appeared in
    # no section at all, hiding where off-policy weight sits.
    exposures = sample_exposures()
    exposures["dimensions"]["region"] = {"us": 0.61, "europe": 0.20, "japan": 0.06,
                                         "em_ex_china": 0.08, "canada": 0.05}
    result = adaptation.run_pipeline(full_policy(), exposures, sample_tilts())
    rows = [r for r in result.data_quality if r.kind == "off_policy_exposure"]
    assert len(rows) == 1
    assert "region" in rows[0].detail
    assert "canada" in rows[0].detail
    assert "0.05" in rows[0].detail


def test_coverage_passthrough_in_result():
    result = adaptation.run_pipeline(full_policy(), sample_exposures(), sample_tilts())
    assert result.coverage == {"region": 0.97, "sector": 1.00}
    # Absent exposures leave it empty rather than absent.
    assert adaptation.run_pipeline(full_policy(), None, sample_tilts()).coverage == {}


# ==========================================================================
# R8 — `_resolve_tier` aligns to the fallback-ladder contract
# ==========================================================================

def test_all_covered_dimensions_forced_resolves_partial_dimensions():
    # Every covered dimension error-forced to `multiplier_fallback` is ladder row
    # 4, not row 2: `weights_only` claims the policy carried no bands at all.
    policy = full_policy()
    for dim in policy["mandate"]["sub_allocations"]["dimensions"].values():
        del dim["basis"]
    result = adaptation.run_pipeline(policy, sample_exposures(), sample_tilts())
    assert result.fallback_tier == "partial_dimensions"
    assert {r.semantics for r in result.taa} == {"multiplier_fallback"}
