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
