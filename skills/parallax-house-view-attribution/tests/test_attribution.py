"""Tests for the house-view attribution pure layer."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

import attribution  # noqa: E402


def _view(sector_tilts=None, region_tilts=None, theme_tilts=None,
          view_id="v-1", version_id="ver-1"):
    return {
        "metadata": {"view_id": view_id, "version_id": version_id},
        "tilts": {
            "sectors": sector_tilts or {},
            "regions": region_tilts or {},
            "themes": theme_tilts or {},
        },
    }


def _chain(weights, view=None, scores=None, emitted="2026-05-10T00:00:00Z",
           run_id="r1"):
    return {
        "spec_version": 1,
        "skill": "parallax-portfolio-builder",
        "run_id": run_id,
        "emitted_at": emitted,
        "view": view or _view(),
        "base_scores": {"response_inline": scores or {}, "response_hash": "0" * 64},
        "final_portfolio": {"weights": weights},
    }


META = {
    "AAA.X": {"sector": "information_technology", "region": "us", "themes": ["ai_infrastructure"]},
    "BBB.Y": {"sector": "energy", "region": "us", "themes": []},
    "CCC.Z": {"sector": "health_care", "region": "japan", "themes": []},
}


# -- neutral counterfactual ----------------------------------------------------

def test_neutral_exact_score_proportional():
    chain = _chain({"AAA.X": 0.5, "BBB.Y": 0.3, "CCC.Z": 0.2},
                   scores={"AAA.X": 8.0, "BBB.Y": 6.0, "CCC.Z": 6.0})
    w, quality = attribution.neutral_weights(chain)
    assert quality == "exact"
    assert w["AAA.X"] == pytest.approx(0.4)
    assert sum(w.values()) == pytest.approx(1.0)


def test_neutral_approximate_equal_weight_fallback():
    chain = _chain({"AAA.X": 0.5, "BBB.Y": 0.5}, scores={})
    w, quality = attribution.neutral_weights(chain)
    assert quality == "approximate"
    assert w == {"AAA.X": pytest.approx(0.5), "BBB.Y": pytest.approx(0.5)}


# -- zero-tilt view => zero active ----------------------------------------------

def test_all_zero_tilts_zero_model_active():
    chain = _chain({"AAA.X": 1 / 3, "BBB.Y": 1 / 3, "CCC.Z": 1 / 3})
    returns = {"AAA.X": 0.10, "BBB.Y": -0.05, "CCC.Z": 0.02}
    seg = attribution.attribute_segment(chain, returns, META)
    assert seg["model_active_bps"] == pytest.approx(0.0, abs=1e-9)
    for row in seg["per_tilt"]:
        assert row["realized_contribution_bps"] == pytest.approx(0.0, abs=1e-9)


# -- Shapley invariant -----------------------------------------------------------

def test_shapley_sums_to_model_active():
    view = _view(sector_tilts={"information_technology": 2, "energy": -1},
                 region_tilts={"japan": 1},
                 theme_tilts={"ai_infrastructure": 1})
    chain = _chain({"AAA.X": 0.5, "BBB.Y": 0.2, "CCC.Z": 0.3}, view=view)
    returns = {"AAA.X": 0.12, "BBB.Y": -0.08, "CCC.Z": 0.03}
    neutral, _ = attribution.neutral_weights(chain)
    mults = attribution.group_multipliers(view, META)
    per_tilt = attribution.shapley_tilt_attribution(neutral, mults, returns)
    model_w = attribution.weights_for_groups(neutral, mults, frozenset(attribution.GROUPS))
    model_bps = attribution.active_return_bps(model_w, neutral, returns)
    assert sum(r["realized_contribution_bps"] for r in per_tilt) == pytest.approx(model_bps, abs=1e-6)


def test_hand_computed_single_sector_tilt():
    # 2 holdings, equal neutral. OW tech +2 (1.5x): raw = {0.75, 0.5} ->
    # normalized {0.6, 0.4}. dw = {+0.1, -0.1}; r = {10%, 0%} -> active = 1% = 100 bps.
    view = _view(sector_tilts={"information_technology": 2})
    chain = _chain({"AAA.X": 0.6, "BBB.Y": 0.4}, view=view)
    returns = {"AAA.X": 0.10, "BBB.Y": 0.0}
    seg = attribution.attribute_segment(chain, returns,
                                        {k: META[k] for k in ("AAA.X", "BBB.Y")})
    assert seg["model_active_bps"] == pytest.approx(100.0, abs=0.5)
    sectors = next(r for r in seg["per_tilt"] if r["group"] == "sectors")
    assert sectors["realized_contribution_bps"] == pytest.approx(100.0, abs=0.5)
    # Chain weights exactly match model-implied -> residual ~ 0.
    assert seg["selection_residual_bps"] == pytest.approx(0.0, abs=0.5)


def test_selection_residual_captures_off_model_weights():
    view = _view(sector_tilts={"information_technology": 2})
    # Actual chain weights diverge from model-implied (e.g. redundancy trim).
    chain = _chain({"AAA.X": 0.8, "BBB.Y": 0.2}, view=view)
    returns = {"AAA.X": 0.10, "BBB.Y": 0.0}
    seg = attribution.attribute_segment(chain, returns,
                                        {k: META[k] for k in ("AAA.X", "BBB.Y")})
    assert seg["active_return_bps"] > seg["model_active_bps"]
    assert seg["selection_residual_bps"] == pytest.approx(
        seg["active_return_bps"] - seg["model_active_bps"], abs=1e-9)


# -- missing data ---------------------------------------------------------------

def test_missing_price_drops_and_renormalizes():
    chain = _chain({"AAA.X": 0.5, "BBB.Y": 0.3, "CCC.Z": 0.2})
    returns = {"AAA.X": 0.10, "BBB.Y": 0.0}  # CCC.Z missing
    seg = attribution.attribute_segment(chain, returns, META)
    assert seg["holdings_covered"] == 2
    assert seg["holdings_dropped"] == 1


def test_no_returns_at_all_raises():
    chain = _chain({"AAA.X": 1.0})
    with pytest.raises(attribution.AttributionError):
        attribution.attribute_segment(chain, {}, META)


# -- chain loading / segmentation -------------------------------------------------

def test_load_window_chains_filters(tmp_path):
    base = tmp_path / "chains"
    month = base / "2026-05"
    month.mkdir(parents=True)
    inside = _chain({"AAA.X": 1.0}, emitted="2026-05-10T00:00:00Z", run_id="in")
    outside = _chain({"AAA.X": 1.0}, emitted="2026-08-01T00:00:00Z", run_id="out")
    other_view = _chain({"AAA.X": 1.0}, view=_view(view_id="v-OTHER"),
                        emitted="2026-05-11T00:00:00Z", run_id="other")
    empty = _chain({}, emitted="2026-05-12T00:00:00Z", run_id="empty")
    for c in (inside, outside, other_view, empty):
        (month / f"{c['run_id']}.yaml").write_text(yaml.safe_dump(c))
    got = attribution.load_window_chains("v-1", "2026-05-01", "2026-06-30", chain_dir=base)
    assert [c["run_id"] for c in got] == ["in"]
    assert attribution.load_window_chains("v-1", "2026-05-01", "2026-06-30",
                                          chain_dir=tmp_path / "missing") == []


def test_segment_by_version_orders_and_groups():
    c1 = _chain({"AAA.X": 1.0}, view=_view(version_id="ver-1"),
                emitted="2026-05-01T00:00:00Z", run_id="a")
    c2 = _chain({"AAA.X": 1.0}, view=_view(version_id="ver-2"),
                emitted="2026-05-20T00:00:00Z", run_id="b")
    c3 = _chain({"AAA.X": 1.0}, view=_view(version_id="ver-1"),
                emitted="2026-05-05T00:00:00Z", run_id="c")
    segs = attribution.segment_by_version([c2, c1, c3])
    assert [s.version_id for s in segs] == ["ver-1", "ver-2"]
    assert [c["run_id"] for c in segs[0].chains] == ["a", "c"]


# -- merge ------------------------------------------------------------------------

def test_merge_segments_sums_and_degrades_quality():
    seg_exact = {
        "active_return_bps": 100.0, "model_active_bps": 90.0,
        "selection_residual_bps": 10.0, "counterfactual_quality": "exact",
        "holdings_covered": 3, "holdings_dropped": 0,
        # Symbol lists, as attribute_segment() emits. This test previously
        # omitted them and never asserted holdings_covered, so it could not
        # notice that the merged count was being silently zeroed.
        "_covered_symbols": ["A", "B", "C"], "_dropped_symbols": [],
        "per_tilt": [{"group": "sectors", "realized_contribution_bps": 90.0},
                     {"group": "regions", "realized_contribution_bps": 0.0},
                     {"group": "themes", "realized_contribution_bps": 0.0}],
    }
    seg_approx = dict(seg_exact, counterfactual_quality="approximate",
                      active_return_bps=-20.0, model_active_bps=-30.0,
                      selection_residual_bps=10.0)
    merged = attribution.merge_segments([seg_exact, seg_approx])
    assert merged["segments"] == 2
    assert merged["active_return_bps"] == pytest.approx(80.0)
    assert merged["counterfactual_quality"] == "approximate"
    assert merged["holdings_covered"] == 3, "same three holdings, not six"
    sectors = next(r for r in merged["per_tilt"] if r["group"] == "sectors")
    assert sectors["realized_contribution_bps"] == pytest.approx(180.0)
    with pytest.raises(attribution.InsufficientProvenance):
        attribution.merge_segments([])


# ---------------------------------------------------------------------------
# Gaps found by adversarial review: paths the original 11 tests did not pin
# ---------------------------------------------------------------------------


def test_compounded_exposure_is_capped_at_the_documented_2x():
    """loader.md caps FINAL exposure at 2x neutral. The first version clamped
    the raw multiplier before normalisation, which does not bound that: the
    ratio surviving normalisation is m / mean(m) and grows as OTHER holdings'
    multipliers fall. Measured with the old pre-normalisation cap, this exact
    input reached 3.37x neutral while EXPOSURE_CAP was 2.0.

    The assertion is on the ratio to neutral, which is the documented quantity —
    the previous version asserted raw weights of 2/3 vs 1/3, a 1.33x exposure,
    and so never checked the property it was named for.
    """
    neutral = {k: 0.25 for k in "ABCD"}
    mults = {
        "sectors": {"A": 1.50, "B": 0.5, "C": 0.5, "D": 0.5},
        "regions": {"A": 1.25, "B": 0.5, "C": 0.5, "D": 0.5},
        "themes":  {"A": 1.50, "B": 0.5, "C": 0.5, "D": 0.5},
    }
    w = attribution.weights_for_groups(
        neutral, mults, frozenset({"sectors", "regions", "themes"}))
    assert abs(sum(w.values()) - 1.0) < 1e-9, sum(w.values())
    ratio = w["A"] / neutral["A"]
    assert ratio <= attribution.EXPOSURE_CAP + 1e-9, ratio
    assert abs(ratio - attribution.EXPOSURE_CAP) < 1e-9, ratio


def test_no_holding_exceeds_the_cap_across_random_configurations():
    """One hand-built case cannot show the redistribution never pushes a second
    holding over the cap."""
    import itertools
    vals = [0.5, 0.75, 1.0, 1.25, 1.5]
    syms = list("ABCD")
    neutral = {k: 0.25 for k in syms}
    for combo in itertools.product(vals, repeat=4):
        mults = {"sectors": dict(zip(syms, combo)),
                 "regions": {k: 1.0 for k in syms},
                 "themes": {k: 1.0 for k in syms}}
        w = attribution.weights_for_groups(neutral, mults, frozenset({"sectors"}))
        assert abs(sum(w.values()) - 1.0) < 1e-9, combo
        for sym in syms:
            assert w[sym] / neutral[sym] <= attribution.EXPOSURE_CAP + 1e-6, (combo, sym)


def test_the_cap_does_not_break_the_shapley_sum_invariant():
    """Shapley efficiency holds for any value function, so capping inside
    weights_for_groups must not disturb the sum. Asserted directly because the
    cap changes what every coalition is worth."""
    neutral = {"A": 0.4, "B": 0.35, "C": 0.25}
    mults = {
        "sectors": {"A": 1.50, "B": 0.75, "C": 1.0},
        "regions": {"A": 1.25, "B": 1.00, "C": 1.0},
        "themes": {"A": 1.50, "B": 1.00, "C": 1.25},
    }
    returns = {"A": 0.10, "B": -0.04, "C": 0.02}
    parts = attribution.shapley_tilt_attribution(neutral, mults, returns)
    total = sum(p["realized_contribution_bps"] for p in parts)
    full = attribution.weights_for_groups(
        neutral, mults, frozenset({"sectors", "regions", "themes"}))
    model = attribution.active_return_bps(full, neutral, returns)
    assert abs(total - model) < 1e-6, (total, model)


def test_a_negative_tilt_is_not_floored():
    """loader.md specifies a 2x upside cap and NO downside floor, so a -2 tilt
    compounding toward zero is correct. Pinned so a symmetric floor is not
    added later on the assumption that the cap should mirror."""
    neutral = {"A": 0.5, "B": 0.5}
    mults = {
        "sectors": {"A": 0.50, "B": 1.0},
        "regions": {"A": 1.00, "B": 1.0},
        "themes": {"A": 0.50, "B": 1.0},
    }
    w = attribution.weights_for_groups(
        neutral, mults, frozenset({"sectors", "regions", "themes"}))
    assert abs(w["A"] - 0.2) < 1e-9, w   # 0.25 vs 1.0 => 1/5


def test_renormalization_uses_only_the_covered_set():
    """`test_missing_price_drops_and_renormalizes` asserts only the covered and
    dropped COUNTS, so replacing the covered-set sum with a sum over all
    neutral weights survived it. That mutant changes the number: on a 3-holding
    portfolio with one missing return the correct answer is 62.5 bps and the
    mutant returns 150.0."""
    neutral = {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}
    tilted = {"A": 0.5, "B": 0.25, "C": 0.25}
    returns = {"A": 0.05, "B": 0.01}          # C has no price data
    bps = attribution.active_return_bps(tilted, neutral, returns)
    # Renormalized over {A,B}: neutral .5/.5, tilted 2/3,1/3.
    # (2/3-1/2)*.05 + (1/3-1/2)*.01 = .008333-.001667 = .006667 -> 66.67 bps
    assert abs(bps - 66.6667) < 0.01, bps


def test_region_multipliers_actually_reach_the_result():
    """Replacing the region multiplier with a literal 1.0 survives every other
    test in this file: the only test that sets a region tilt
    (`test_shapley_sums_to_model_active`) asserts just the Shapley sum
    invariant, which holds for any value function — including one where
    regions never contribute. Pinned with a direct numeric check, the same
    shape as the theme-multiplier test above."""
    view = {"tilts": {"sectors": {}, "regions": {"japan": 2}, "themes": {}}}
    meta = {"A": {"sector": "Tech", "region": "japan", "themes": []},
            "B": {"sector": "Tech", "region": "us", "themes": []}}
    m = attribution.group_multipliers(view, meta)
    assert m["regions"]["A"] == 1.50, m["regions"]
    assert m["regions"]["B"] == 1.00, m["regions"]


def test_theme_multipliers_actually_reach_the_result():
    """Replacing the theme multiplier with 1.0 survived all 11 original tests:
    the one test that set a theme tilt asserted only the Shapley sum, which
    still holds when themes contribute nothing."""
    view = {"tilts": {"sectors": {}, "regions": {}, "themes": {"ai": 2}}}
    meta = {"A": {"sector": "Tech", "region": "US", "themes": ["ai"]},
            "B": {"sector": "Tech", "region": "US", "themes": []}}
    m = attribution.group_multipliers(view, meta)
    assert m["themes"]["A"] == 1.50, m["themes"]
    assert m["themes"]["B"] == 1.00, m["themes"]


def test_multiple_matched_themes_compound():
    view = {"tilts": {"sectors": {}, "regions": {}, "themes": {"ai": 1, "energy": 1}}}
    meta = {"A": {"sector": "Tech", "region": "US", "themes": ["ai", "energy"]}}
    m = attribution.group_multipliers(view, meta)
    assert abs(m["themes"]["A"] - 1.25 * 1.25) < 1e-12, m["themes"]


def test_a_non_numeric_tilt_does_not_crash_the_run():
    """`int()` on a tilt value raises an uncaught ValueError on malformed view
    YAML, which would abort an attribution run rather than degrade it."""
    view = {"tilts": {"sectors": {"Tech": "big"}, "regions": {}, "themes": {}}}
    meta = {"A": {"sector": "Tech", "region": "US", "themes": []}}
    m = attribution.group_multipliers(view, meta)
    assert m["sectors"]["A"] == 1.0, m["sectors"]


def test_holdings_are_unioned_across_segments_not_summed():
    """A 3-holding portfolio spanning three version segments reported 9 covered
    holdings, which SKILL.md renders as "[C] holdings covered" — a wrong number
    in a client-facing report. Holdings are a set, not an additive quantity."""
    def seg(covered, dropped):
        return {
            "active_return_bps": 0.0, "model_active_bps": 0.0,
            "selection_residual_bps": 0.0,
            "per_tilt": [{"group": g, "realized_contribution_bps": 0.0}
                         for g in attribution.GROUPS],
            "counterfactual_quality": "exact",
            "holdings_covered": len(covered), "holdings_dropped": len(dropped),
            "_covered_symbols": set(covered), "_dropped_symbols": set(dropped),
        }
    same = ["A", "B", "C"]
    merged = attribution.merge_segments([seg(same, []) for _ in range(3)])
    assert merged["segments"] == 3
    assert merged["holdings_covered"] == 3, merged["holdings_covered"]
    assert merged["holdings_dropped"] == 0


def test_a_holding_priced_in_any_segment_is_not_counted_as_dropped():
    """C has no price in segment 1 but does in segment 2. Summing would report
    it both covered and dropped."""
    def seg(covered, dropped):
        return {
            "active_return_bps": 0.0, "model_active_bps": 0.0,
            "selection_residual_bps": 0.0,
            "per_tilt": [{"group": g, "realized_contribution_bps": 0.0}
                         for g in attribution.GROUPS],
            "counterfactual_quality": "exact",
            "holdings_covered": len(covered), "holdings_dropped": len(dropped),
            "_covered_symbols": set(covered), "_dropped_symbols": set(dropped),
        }
    merged = attribution.merge_segments([
        seg(["A", "B"], ["C"]),
        seg(["A", "B", "C"], []),
    ])
    assert merged["holdings_covered"] == 3
    assert merged["holdings_dropped"] == 0


def test_the_audit_payload_carries_no_holdings_array():
    """loader.md §6.3 forbids logging holdings arrays and merge_segments'
    return value IS the audit-row payload. The symbol sets are internal to the
    merge and must not leak into it."""
    seg = {
        "active_return_bps": 1.0, "model_active_bps": 1.0,
        "selection_residual_bps": 0.0,
        "per_tilt": [{"group": g, "realized_contribution_bps": 0.0}
                     for g in attribution.GROUPS],
        "counterfactual_quality": "exact",
        "holdings_covered": 2, "holdings_dropped": 0,
        "_covered_symbols": {"AAPL.O", "MSFT.O"}, "_dropped_symbols": set(),
    }
    merged = attribution.merge_segments([seg])
    flat = repr(merged)
    assert "AAPL.O" not in flat and "MSFT.O" not in flat, flat
    assert not any(k.startswith("_") for k in merged), list(merged)


def test_segment_output_is_json_serialisable():
    """SKILL.md Phase 5 writes per-segment detail into report.json. The symbol
    collections were `set` objects, and json.dumps raises on a set — the report
    would have crashed on write. Sorted lists also keep bundles diffable."""
    import json
    chain = {"final_portfolio": {"weights": {"A": 0.6, "B": 0.4}},
             "view": {"tilts": {"sectors": {}, "regions": {}, "themes": {}}}}
    seg = attribution.attribute_segment(
        chain, {"A": 0.05, "B": 0.01},
        {"A": {"sector": "Tech", "region": "US", "themes": []},
         "B": {"sector": "Tech", "region": "US", "themes": []}})
    json.dumps(seg)                       # must not raise
    assert seg["_covered_symbols"] == ["A", "B"], seg["_covered_symbols"]
    assert isinstance(seg["_dropped_symbols"], list)


def test_tilt_parsing_is_consistent_across_yaml_spellings():
    """Three separate inconsistencies, all reachable from hand-edited view YAML:

    `tech: yes` is boolean True under YAML 1.1, and bool is an int in Python, so
    it silently became a +1 overweight — while neutral_weights() in the same
    file already excluded bool for exactly this reason.

    `int(2.9)` truncated INTO range and returned the +2 multiplier, though the
    docstring promised out-of-range degrades to neutral.

    `1.5` and the string `"1.5"` — the same authored value under different
    quoting — returned different multipliers.
    """
    m = attribution._tilt_mult
    assert m(True) == 1.0 and m(False) == 1.0, "bool must not act as a tilt"
    assert m(2.9) == 1.0, "a non-integer must not truncate into range"
    assert m(1.5) == m("1.5") == 1.0, "quoting must not change the multiplier"
    assert m(3) == 1.0 and m(-3) == 1.0, "out of range degrades to neutral"
    # Real tilts still work, quoted or not.
    assert m(2) == m("2") == 1.50
    assert m(-2) == m("-2") == 0.50
    assert m(2.0) == 1.50, "an integral float is a legitimate YAML integer"


def test_merged_residual_keeps_its_sign():
    """`selection_residual_bps = active - model`. Flipping it to model - active
    survived the suite, so a wrong-sign residual would have shipped into the
    audit row and the client-facing report unnoticed."""
    def seg(active, model):
        return {"active_return_bps": active, "model_active_bps": model,
                "selection_residual_bps": active - model,
                "per_tilt": [{"group": g, "realized_contribution_bps": 0.0}
                             for g in attribution.GROUPS],
                "counterfactual_quality": "exact",
                "holdings_covered": 1, "holdings_dropped": 0,
                "_covered_symbols": ["A"], "_dropped_symbols": []}
    merged = attribution.merge_segments([seg(120.0, 50.0)])
    assert merged["active_return_bps"] == 120.0
    assert merged["model_active_bps"] == 50.0, "model total is unpinned"
    assert merged["selection_residual_bps"] == 70.0, "residual sign flipped"


def test_merge_unions_rather_than_taking_the_last_segment():
    """Both earlier union tests used identical or nested symbol sets, so neither
    could distinguish a union from last-segment-wins."""
    def seg(covered):
        return {"active_return_bps": 0.0, "model_active_bps": 0.0,
                "selection_residual_bps": 0.0,
                "per_tilt": [{"group": g, "realized_contribution_bps": 0.0}
                             for g in attribution.GROUPS],
                "counterfactual_quality": "exact",
                "holdings_covered": len(covered), "holdings_dropped": 0,
                "_covered_symbols": sorted(covered), "_dropped_symbols": []}
    merged = attribution.merge_segments([seg(["A", "B"]), seg(["C"])])
    assert merged["holdings_covered"] == 3, "last-segment-wins would give 1"


def test_a_segment_without_symbol_keys_is_rejected_not_silently_zeroed():
    """`.get(..., ())` reported 0 holdings covered for a hand-built segment that
    declared a real count. SKILL.md invites hand-built segments, and the count
    is rendered client-facing as "[C] holdings covered"."""
    seg = {"active_return_bps": 0.0, "model_active_bps": 0.0,
           "selection_residual_bps": 0.0,
           "per_tilt": [{"group": g, "realized_contribution_bps": 0.0}
                        for g in attribution.GROUPS],
           "counterfactual_quality": "exact",
           "holdings_covered": 3, "holdings_dropped": 1}
    with pytest.raises(attribution.AttributionError, match="_covered_symbols"):
        attribution.merge_segments([seg])


# ---------------------------------------------------------------------------
# The exposure cap: bounded, not "usually settles"
# ---------------------------------------------------------------------------


def test_the_cap_holds_on_the_measured_multi_group_counterexample():
    """A fixed-pass redistribution loop does not bound exposure at all.

    The shipped loop recomputed the over-cap set from scratch each pass. A name
    clamped in pass N sits at exactly EXPOSURE_CAP x neutral, so the strict `>`
    test dropped it from the over-set in pass N+1, it fell back into the free
    set, and redistribution lifted it above the cap again. The iteration
    oscillated instead of settling, and convergence was NON-MONOTONE in the
    pass count: on this exact input the max exposure went 2.925448 (1 pass) ->
    2.412839 (2) -> 2.453204 (3, the shipped setting) -> 2.182907 (4) ->
    2.007906 (10) -> 2.000000 (200).

    Raising the pass count is therefore not a fix. The property the code must
    hold is the loader.md tilt-table contract: final per-holding exposure is
    bounded at EXPOSURE_CAP x neutral. That needs a persistent capped set, which
    terminates at the cap in at most one pass per holding.

    Multipliers here are drawn only from the documented tilt table
    (0.50 / 0.75 / 1.00 / 1.25 / 1.50), so this is a reachable view, not a
    synthetic input.
    """
    neutral = {
        "S0": 0.31130298136963735,
        "S1": 0.22315873398843988,
        "S2": 0.13497491145738316,
        "S3": 0.23614376719175859,
        "S4": 0.09441960599278096,
    }
    mults = {
        "sector": {"S0": 0.5, "S1": 0.5, "S2": 1.25, "S3": 1.25, "S4": 0.5},
        "region": {"S0": 0.75, "S1": 0.5, "S2": 1.5, "S3": 1.5, "S4": 0.75},
        "theme1": {"S0": 0.5, "S1": 1.5, "S2": 1.25, "S3": 1.5, "S4": 1.0},
        "theme2": {"S0": 0.5, "S1": 0.5, "S2": 1.0, "S3": 1.25, "S4": 1.0},
    }
    w = attribution.weights_for_groups(neutral, mults, frozenset(mults))
    assert abs(sum(w.values()) - 1.0) < 1e-9, sum(w.values())
    worst = max(w[s] / neutral[s] for s in neutral)
    assert worst <= attribution.EXPOSURE_CAP + 1e-9, worst


def test_the_cap_holds_across_seeded_random_portfolios():
    """One counterexample cannot show the bound holds everywhere.

    Convergence of the old loop was geometric, not finite: the worst case over
    20,000 random portfolios still needed 70 redistribution passes (this
    module's seed; 124 under seed 4242) to reach the
    cap. Any fixed pass count therefore has a counterexample. This test asserts
    the bound itself over a seeded sweep, so it fails for a loop that merely
    converges slowly as well as for one that oscillates.

    Multipliers are sampled from the documented tilt table only. Four
    compounding groups mirror `group_multipliers`, where the theme group is
    already a product over every matched theme. The seed is fixed so a failure
    is reproducible.
    """
    import random

    rng = random.Random(20260818)
    table = [0.5, 0.75, 1.0, 1.25, 1.5]
    worst = 0.0
    worst_case = None
    for _ in range(3000):
        n = rng.randint(3, 8)
        syms = [f"S{i}" for i in range(n)]
        draws = [rng.random() + 0.05 for _ in syms]
        tot = sum(draws)
        neutral = {s: d / tot for s, d in zip(syms, draws)}
        mults = {
            g: {s: rng.choice(table) for s in syms}
            for g in ("sector", "region", "theme1", "theme2")
        }
        w = attribution.weights_for_groups(neutral, mults, frozenset(mults))
        assert abs(sum(w.values()) - 1.0) < 1e-9, (neutral, mults)
        ratio = max(w[s] / neutral[s] for s in syms)
        if ratio > worst:
            worst, worst_case = ratio, (neutral, mults)
    assert worst <= attribution.EXPOSURE_CAP + 1e-9, (worst, worst_case)


# ---------------------------------------------------------------------------
# Bool is not a score
# ---------------------------------------------------------------------------


def test_a_bool_inline_score_falls_back_to_approximate():
    """`bool` is a subclass of `int`, so a YAML `true` in `base_scores.
    response_inline` passes a bare `isinstance(v, (int, float))` and scores as
    1.0. Deleting `and not isinstance(v, bool)` left the whole suite green.

    The weights are wrong (True/(True+4) = 0.2 instead of the 0.5 equal-weight
    fallback), but the severe part is the quality tag: without the guard the run
    reports `"exact"`, so corrupt input is presented on the high-confidence
    path. Both are asserted.
    """
    chain = _chain({"AAPL.O": 0.5, "MSFT.O": 0.5},
                   scores={"AAPL.O": True, "MSFT.O": 4})
    w, quality = attribution.neutral_weights(chain)
    assert quality == "approximate", quality
    assert w["AAPL.O"] == pytest.approx(0.5), w
    assert w["MSFT.O"] == pytest.approx(0.5), w


def test_the_redistribution_bound_scales_with_the_portfolio_not_a_constant():
    """The pass bound is `len(weights) + 1`, and that is load-bearing.

    With the capped set persistent, each pass that does anything adds at least
    one name to it, so a bound of one pass per holding always suffices. A small
    fixed constant does not. This 14-holding view — multipliers drawn only from
    the documented tilt table, in the exact three-group shape
    `group_multipliers` emits, where `themes` is already a product over every
    matched theme — needs SEVEN passes to settle. Measured max exposure against
    a cap of 2.0 when the bound is replaced by a constant:

        range(3) -> 2.356220    range(6) -> 2.002722
        range(4) -> 2.154241    range(7) -> 2.000000
        range(5) -> 2.083134

    So `range(3)` and `range(5)` — the two most likely "simplifications" — both
    breach here, as does `range(6)`. A constant of 7 or more would survive this
    single case; the guarantee for a constant does not exist at all, because the
    termination argument bounds the passes by the holding count and nothing
    smaller. Directed search over portfolios up to 26 holdings did not exceed 7
    passes, so the linear bound is sufficient but not tight — it is chosen
    because it is PROVABLE, not because 7 was the largest number found.

    The literals are pinned rather than searched: the suite must stay
    deterministic and fast.
    """
    neutral = {
        "S0": 0.054398458226485855, "S1": 0.002851675930842207,
        "S2": 0.024024739647950093, "S3": 0.006785453657828538,
        "S4": 0.005784625822735527, "S5": 0.350549974937791,
        "S6": 0.002614504440067373, "S7": 0.19343221501984695,
        "S8": 0.02397587066931312, "S9": 0.03389871759794953,
        "S10": 0.042575840187557765, "S11": 0.17768347872099916,
        "S12": 0.053473927312974935, "S13": 0.027950517827657943
    }
    mults = {
        "sectors": {
            "S0": 1.5, "S1": 0.75, "S2": 0.75, "S3": 1.5, "S4": 1.25, "S5": 0.75,
            "S6": 0.5, "S7": 1.0, "S8": 0.75, "S9": 0.5, "S10": 0.75, "S11": 0.5,
            "S12": 0.5, "S13": 1.5
        },
        "regions": {
            "S0": 1.0, "S1": 0.75, "S2": 1.5, "S3": 1.0, "S4": 1.25, "S5": 0.5,
            "S6": 0.75, "S7": 1.5, "S8": 1.5, "S9": 0.5, "S10": 0.75, "S11": 0.5,
            "S12": 1.25, "S13": 0.75
        },
        "themes": {
            "S0": 3.375, "S1": 1.6875, "S2": 1.875, "S3": 0.28125, "S4": 0.25,
            "S5": 0.125, "S6": 1.171875, "S7": 0.84375, "S8": 0.5, "S9": 0.1875,
            "S10": 0.84375, "S11": 0.1875, "S12": 1.40625, "S13": 0.5
        },
    }
    assert len(neutral) == 14, len(neutral)
    assert abs(sum(neutral.values()) - 1.0) < 1e-12, sum(neutral.values())
    w = attribution.weights_for_groups(neutral, mults, frozenset(mults))
    assert abs(sum(w.values()) - 1.0) < 1e-9, sum(w.values())
    worst = max(w[s] / neutral[s] for s in neutral)
    assert worst <= attribution.EXPOSURE_CAP + 1e-9, worst


# ---------------------------------------------------------------------------
# The cap survives coverage renormalization -- on the model leg only
# ---------------------------------------------------------------------------


def test_the_cap_holds_after_a_dropped_holding_renormalizes_the_model_leg():
    """`weights_for_groups` honouring the cap is not enough on its own.

    `active_return_bps` drops symbols with no return data and renormalizes both
    legs over the covered set, which rescales every surviving ratio by
    `nw_total / w_total`. When the dropped name was overweighted that factor
    exceeds 1 and carries a survivor above the cap -- so the number the skill
    REPORTS breached 2x while the dict it was built from did not.

    Neutral {A .1, B .1, C .8}, +2 sector and +2 region on A and B: the returned
    weights put A and B at exactly 2.00x. Drop A for missing prices and B's
    effective ratio was 2.25x before this fix.
    """
    neutral = {"A": 0.1, "B": 0.1, "C": 0.8}
    mults = {"sectors": {"A": 1.5, "B": 1.5, "C": 0.5},
             "regions": {"A": 1.5, "B": 1.5, "C": 0.5}}
    w = attribution.weights_for_groups(neutral, mults, frozenset(mults))
    assert max(w[s] / neutral[s] for s in neutral) <= attribution.EXPOSURE_CAP + 1e-9

    covered = ["B", "C"]                      # A dropped: no return data
    nt = sum(neutral[s] for s in covered)
    wt = sum(w[s] for s in covered)
    nw_cov = {s: neutral[s] / nt for s in covered}
    w_cov = {s: w[s] / wt for s in covered}
    assert max(w_cov[s] / nw_cov[s] for s in covered) > attribution.EXPOSURE_CAP + 1e-9, \
        "premise gone: renormalization no longer breaches, so this test proves nothing"

    capped = attribution._apply_exposure_cap(dict(w_cov), nw_cov)
    assert abs(sum(capped.values()) - 1.0) < 1e-9, sum(capped.values())
    worst = max(capped[s] / nw_cov[s] for s in covered)
    assert worst <= attribution.EXPOSURE_CAP + 1e-9, worst


def test_the_realized_leg_is_never_capped():
    """The cap constrains what the MODEL may imply, never what the book held.

    `tilted_actual` is a measured fact reconstructed from the chain. Clamping it
    would overwrite that fact and silently move `selection_residual_bps`, which
    is defined as actual minus model. A book genuinely 3x neutral in one name
    must report 3x.
    """
    neutral = {"A": 0.25, "B": 0.25, "C": 0.5}
    actual = {"A": 0.75, "B": 0.125, "C": 0.125}      # A at 3x neutral
    returns = {"A": 0.10, "B": 0.0, "C": 0.0}

    uncapped = attribution.active_return_bps(actual, neutral, returns)
    capped = attribution.active_return_bps(
        actual, neutral, returns, enforce_cap=True)
    assert uncapped != capped, "enforce_cap made no difference; the test is vacuous"

    # the default (realized) path must report the full 3x exposure
    expected = (actual["A"] - neutral["A"]) * returns["A"] * 10_000.0
    assert uncapped == pytest.approx(expected), uncapped


def test_model_and_shapley_legs_agree_after_capping():
    """Shapley efficiency must survive the changed value function.

    Efficiency holds for any value function, but both legs must use the SAME
    one -- `shapley_tilt_attribution` and the `model_active_bps` call site both
    pass enforce_cap=True. If one drifts, the per-tilt contributions stop
    summing to the total they are reported against.
    """
    neutral = {"A": 0.1, "B": 0.1, "C": 0.8}
    mults = {g: {"A": 1.5, "B": 1.5, "C": 0.5} for g in attribution.GROUPS}
    returns = {"B": 0.05, "C": -0.02}                  # A dropped
    per = attribution.shapley_tilt_attribution(neutral, mults, returns)
    model_w = attribution.weights_for_groups(
        neutral, mults, frozenset(attribution.GROUPS))
    model_bps = attribution.active_return_bps(
        model_w, neutral, returns, enforce_cap=True)
    total = sum(p["realized_contribution_bps"] for p in per)
    assert total == pytest.approx(model_bps, abs=1e-9), (total, model_bps)

    # Independent value, not derived from active_return_bps itself: catches a
    # mutation that caps against the un-renormalized neutral_w (0.1/0.8)
    # instead of the covered-set renormalization nw_cov (1/9, 8/9). model_w is
    # {A: .2, B: .2, C: .6} (weights_for_groups' own cap already lands A and B
    # on exactly 2x). Dropping A and renormalizing over {B, C} gives nw_cov =
    # {B: 1/9, C: 8/9}, w_cov = {B: .25, C: .75} -- B breaches at 2.25x. Capping
    # against nw_cov (correct) clamps B to 2/9 and lifts C to 7/9, giving
    # active = (2/9 - 1/9)*0.05 + (7/9 - 8/9)*(-0.02) = 700/9 bps. Capping
    # against the raw un-renormalized {B: .1, C: .8} instead clamps B to .2 and
    # lifts C to .8, giving 560/9 bps -- a different, wrong number that every
    # self-referential assertion above stays blind to.
    assert model_bps == pytest.approx(700 / 9, abs=1e-6), model_bps


def test_attribute_segment_wires_the_cap_into_model_active_bps():
    """Test the WIRING, not the helper.

    `test_model_and_shapley_legs_agree_after_capping` passes enforce_cap=True
    itself, so it stays green even if the real call site inside
    `attribute_segment` drops the flag. Mutation proved that: removing
    `enforce_cap=True` from the `model_bps` line left all 35 tests passing.
    This test drives the public entry point instead.

    Inline scores 1 / 2 / 7 make neutral unequal (equal-weight neutral cannot
    reach a breach with three holdings). Dropping the overweighted BBB.Y
    renormalizes the covered set to a 2.667x effective ratio before the cap.
    """
    view = _view(sector_tilts={"information_technology": -2, "energy": -1,
                               "health_care": -2},
                 region_tilts={"us": 1, "japan": -2},
                 theme_tilts={"ai_infrastructure": 2})
    chain = _chain({"AAA.X": 1 / 3, "BBB.Y": 1 / 3, "CCC.Z": 1 / 3}, view=view,
                   scores={"AAA.X": 1, "BBB.Y": 2, "CCC.Z": 7})
    returns = {"AAA.X": 0.05, "CCC.Z": -0.02}          # BBB.Y dropped

    seg = attribution.attribute_segment(chain, returns, META)
    assert seg["holdings_dropped"] == 1, seg["holdings_dropped"]

    neutral, quality = attribution.neutral_weights(chain)
    assert quality == "exact", quality
    mults = attribution.group_multipliers(view, META)
    model_w = attribution.weights_for_groups(
        neutral, mults, frozenset(attribution.GROUPS))
    uncapped = attribution.active_return_bps(model_w, neutral, returns)
    capped = attribution.active_return_bps(
        model_w, neutral, returns, enforce_cap=True)
    assert uncapped != capped, "premise gone: renormalization no longer breaches"

    assert seg["model_active_bps"] == pytest.approx(capped, abs=1e-9), (
        "attribute_segment is not passing enforce_cap=True to the model leg")
    assert seg["selection_residual_bps"] == pytest.approx(
        seg["active_return_bps"] - seg["model_active_bps"], abs=1e-9)


def test_attribute_segment_never_caps_the_realized_leg():
    """Test the WIRING of the realized leg, not just `active_return_bps` itself.

    `test_the_realized_leg_is_never_capped` calls `active_return_bps` directly
    and never drives `attribute_segment`, so it cannot catch `enforce_cap=True`
    creeping onto the `actual_bps` call site. This drives the public entry
    point with a chain whose actual holdings are 2.25x neutral -- a real
    breach -- and pins the uncapped value.
    """
    chain = _chain({"AAA.X": 0.75, "BBB.Y": 0.125, "CCC.Z": 0.125})
    returns = {"AAA.X": 0.10, "BBB.Y": 0.0, "CCC.Z": 0.0}

    seg = attribution.attribute_segment(chain, returns, META)

    neutral, quality = attribution.neutral_weights(chain)
    assert quality == "approximate", quality
    assert neutral["AAA.X"] == pytest.approx(1 / 3)
    ratio = 0.75 / neutral["AAA.X"]
    assert ratio > attribution.EXPOSURE_CAP + 1e-9, \
        "premise gone: AAA.X no longer breaches the cap"

    expected = (0.75 - neutral["AAA.X"]) * 0.10 * 10_000.0
    assert seg["active_return_bps"] == pytest.approx(expected, abs=1e-6), (
        "attribute_segment is capping the realized leg -- it must not")
