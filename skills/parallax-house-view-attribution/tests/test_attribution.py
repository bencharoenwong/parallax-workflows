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
    sectors = next(r for r in merged["per_tilt"] if r["group"] == "sectors")
    assert sectors["realized_contribution_bps"] == pytest.approx(180.0)
    with pytest.raises(attribution.InsufficientProvenance):
        attribution.merge_segments([])
