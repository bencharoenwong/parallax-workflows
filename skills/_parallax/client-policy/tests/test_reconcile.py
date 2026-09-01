"""Unit tests for the S3 reconciliation solver.

Fixtures are synthetic (AAA.X-style symbols, round numbers) and every optimal
case is built to have a UNIQUE optimal vertex, so assertions compare exact
weights under a tolerance rather than accepting alternate optima. Same
module-level sys.path idiom as `test_adaptation.py` (no conftest slot free in
the `skills/_parallax` pytest root).
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).parent
CLIENT_POLICY_DIR = HERE.parent
sys.path.insert(0, str(CLIENT_POLICY_DIR))

import reconcile  # noqa: E402

MODULE = CLIENT_POLICY_DIR / "reconcile.py"

TOL = 1e-6


def _payload(**overrides) -> dict:
    """Base case with a unique optimum: coefficients strictly ordered, the cap
    and one band both binding. With lambda=0: max 3a+2b+c, sum=1, a<=0.6,
    a+b<=0.7  ->  a=0.6, b=0.1, c=0.3 (unique vertex)."""
    base = {
        "basis": "sleeve",
        "holdings": [
            {"symbol": "AAA.X", "weight": 0.5, "coefficient": 3.0},
            {"symbol": "BBB.X", "weight": 0.3, "coefficient": 2.0},
            {"symbol": "CCC.X", "weight": 0.2, "coefficient": 1.0},
        ],
        "position_cap": 0.6,
        "bands": [
            {"dimension": "region", "key": "north", "symbols": ["AAA.X", "BBB.X"],
             "max": 0.7},
        ],
        "turnover_penalty": 0.0,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Optimal path
# --------------------------------------------------------------------------

def test_optimal_unique_vertex():
    r = reconcile.reconcile(_payload())
    assert r.status == "optimal"
    assert abs(r.target_weights["AAA.X"] - 0.6) < TOL
    assert abs(r.target_weights["BBB.X"] - 0.1) < TOL
    assert abs(r.target_weights["CCC.X"] - 0.3) < TOL
    assert abs(sum(r.target_weights.values()) - 1.0) < TOL


def test_trades_carry_direction_and_delta():
    r = reconcile.reconcile(_payload())
    by_symbol = {t.symbol: t for t in r.trades}
    assert by_symbol["AAA.X"].action == "buy"
    assert by_symbol["BBB.X"].action == "sell"
    assert by_symbol["CCC.X"].action == "buy"
    assert abs(by_symbol["BBB.X"].delta - (-0.2)) < TOL


def test_binding_constraints_are_reported():
    r = reconcile.reconcile(_payload())
    ids = {b.constraint for b in r.binding}
    assert "bound:AAA.X:max" in ids
    assert "band:region:north:max" in ids


def test_large_turnover_penalty_holds_current_weights():
    """Without the band, the current weights are feasible (the base fixture's
    band is deliberately breached by them), so a penalty dominating every
    score spread must return them unchanged."""
    r = reconcile.reconcile(_payload(turnover_penalty=100.0, bands=[]))
    assert r.status == "optimal"
    for h in _payload()["holdings"]:
        assert abs(r.target_weights[h["symbol"]] - h["weight"]) < TOL
    assert all(t.action == "hold" for t in r.trades)


def test_large_turnover_penalty_still_cures_a_band_breach():
    """The base fixture's current weights breach the band (AAA+BBB=0.8 over a
    0.7 max), so even a dominant penalty must trade back inside it — by the
    cheapest route: sell 0.1 of the lower-coefficient member, buy CCC."""
    r = reconcile.reconcile(_payload(turnover_penalty=100.0))
    assert r.status == "optimal"
    assert abs(r.target_weights["AAA.X"] - 0.5) < TOL
    assert abs(r.target_weights["BBB.X"] - 0.2) < TOL
    assert abs(r.target_weights["CCC.X"] - 0.3) < TOL


def test_default_penalty_is_disclosed():
    p = _payload()
    del p["turnover_penalty"]
    r = reconcile.reconcile(p)
    assert r.turnover_penalty == reconcile.DEFAULT_TURNOVER_PENALTY
    assert r.penalty_source == "default"
    assert r.calibration_status == "heuristic_phase0"


def test_exclude_pins_weight_to_zero():
    r = reconcile.reconcile(_payload(excludes=["CCC.X"], bands=[]))
    assert r.status == "optimal"
    assert r.target_weights["CCC.X"] == 0.0


def test_deterministic_across_runs():
    a = reconcile.reconcile(_payload()).to_dict()
    b = reconcile.reconcile(_payload()).to_dict()
    assert a == b


def test_objective_terms_reconcile():
    r = reconcile.reconcile(_payload(turnover_penalty=0.5))
    assert r.status == "optimal"
    score = sum(h["coefficient"] * r.target_weights[h["symbol"]]
                for h in _payload()["holdings"])
    turnover = sum(abs(t.delta) for t in r.trades)
    assert abs(r.objective["score_term"] - score) < TOL
    assert abs(r.objective["turnover_term"] - 0.5 * turnover) < TOL
    assert abs(r.objective["total"] - (score - 0.5 * turnover)) < TOL


# --------------------------------------------------------------------------
# total_turnover: two-sided disclosure, present-as-null off the optimal path
# --------------------------------------------------------------------------

def test_total_turnover_is_reported_on_optimal():
    """Base fixture's unique optimum (AAA .5->.6, BBB .3->.1, CCC .2->.3) has
    a two-sided turnover of exactly 0.4: |.1| + |-.2| + |.1|."""
    r = reconcile.reconcile(_payload())
    assert r.status == "optimal"
    assert abs(r.total_turnover - 0.4) < TOL


def test_total_turnover_equals_sum_of_absolute_trade_deltas():
    r = reconcile.reconcile(_payload(turnover_penalty=0.5))
    assert r.status == "optimal"
    expected = sum(abs(t.delta) for t in r.trades)
    assert abs(r.total_turnover - expected) < TOL


def test_total_turnover_is_reported_when_penalty_is_zero():
    """turnover_penalty=0.0 is the base fixture's own value, and makes
    objective['turnover_term'] identically 0 — total_turnover is not
    derivable from it by dividing out the penalty, so it must still be
    reported and be strictly positive here (the base optimum trades)."""
    r = reconcile.reconcile(_payload())
    assert r.status == "optimal"
    assert r.objective["turnover_term"] == 0.0
    assert r.total_turnover > 0.0


def test_total_turnover_is_zero_when_nothing_trades():
    r = reconcile.reconcile(_payload(turnover_penalty=100.0, bands=[]))
    assert r.status == "optimal"
    assert all(t.action == "hold" for t in r.trades)
    assert abs(r.total_turnover - 0.0) < TOL


def test_total_turnover_absent_on_non_optimal_statuses(monkeypatch):
    """Parametrized (manually — no pytest.mark.parametrize import in this
    module) over the four statuses that never reach the optimal return:
    infeasible, conflict (exclude-vs-user-min shape), invalid_input (dropped
    coefficient), and solver_unavailable (monkeypatch idiom)."""
    infeasible = _payload(excludes=["CCC.X"])
    conflict = _payload(excludes=["AAA.X"])
    conflict["holdings"][0]["min"] = 0.1
    invalid_input = _payload()
    del invalid_input["holdings"][1]["coefficient"]
    for expected_status, payload in (
        ("infeasible", infeasible),
        ("conflict", conflict),
        ("invalid_input", invalid_input),
    ):
        r = reconcile.reconcile(payload)
        assert r.status == expected_status
        assert r.total_turnover is None
        assert r.target_weights is None

    monkeypatch.setitem(sys.modules, "scipy", None)
    monkeypatch.setitem(sys.modules, "scipy.optimize", None)
    r = reconcile.reconcile(_payload())
    assert r.status == "solver_unavailable"
    assert r.total_turnover is None
    assert r.target_weights is None


def test_total_turnover_round_trips_through_the_cli(tmp_path):
    f = tmp_path / "payload.json"
    f.write_text(json.dumps(_payload()), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(MODULE), "--input", str(f)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "optimal"
    assert abs(out["total_turnover"] - 0.4) < TOL


# --------------------------------------------------------------------------
# Infeasibility: report smallest violations, never silently relax
# --------------------------------------------------------------------------

def test_infeasible_reports_smallest_violation_and_nothing_else():
    """Excluding CCC.X while band north caps AAA+BBB at 0.7 leaves only 0.7 of
    budget for a sum-to-1 portfolio: the exact smallest relaxation is 0.3 on
    the band max."""
    r = reconcile.reconcile(_payload(excludes=["CCC.X"]))
    assert r.status == "infeasible"
    assert r.target_weights is None
    assert r.trades is None
    assert r.objective is None
    v = {x.constraint: x.amount for x in r.violations}
    assert abs(v["band:region:north:max"] - 0.3) < TOL


def test_infeasible_bound_violation_is_attributed_to_the_symbol():
    """Caps of 0.2 each over 3 names leave 0.4 of budget unplaceable; the
    uniform-slack diagnosis spreads the smallest total relaxation across the
    cap bounds and must name bounds, not bands."""
    r = reconcile.reconcile(_payload(position_cap=0.2, bands=[]))
    assert r.status == "infeasible"
    assert r.violations, "no violations reported"
    assert all(x.constraint.startswith("bound:") for x in r.violations)
    assert abs(sum(x.amount for x in r.violations) - 0.4) < TOL


# --------------------------------------------------------------------------
# Conflicts surface for human decision, never auto-resolved
# --------------------------------------------------------------------------

def test_exclude_vs_user_min_is_a_named_conflict():
    p = _payload(excludes=["AAA.X"])
    p["holdings"][0]["min"] = 0.1
    r = reconcile.reconcile(p)
    assert r.status == "conflict"
    assert r.conflicts[0].kind == "exclude_vs_user_min"
    assert r.target_weights is None and r.trades is None


def test_user_min_above_cap_is_a_named_conflict():
    p = _payload()
    p["holdings"][2]["min"] = 0.8
    r = reconcile.reconcile(p)
    assert r.status == "conflict"
    assert r.conflicts[0].kind == "bound_min_above_max"


def test_all_holdings_excluded_is_a_named_conflict():
    r = reconcile.reconcile(_payload(excludes=["AAA.X", "BBB.X", "CCC.X"]))
    assert r.status == "conflict"
    assert any(c.kind == "all_holdings_excluded" for c in r.conflicts)


# --------------------------------------------------------------------------
# Input validation fails closed
# --------------------------------------------------------------------------

def test_missing_coefficient_on_non_excluded_holding_is_rejected():
    p = _payload()
    del p["holdings"][1]["coefficient"]
    r = reconcile.reconcile(p)
    assert r.status == "invalid_input"
    assert any("BBB.X" in e.reason for e in r.errors)


def test_excluded_holding_may_omit_coefficient():
    p = _payload(excludes=["CCC.X"], bands=[])
    del p["holdings"][2]["coefficient"]
    assert reconcile.reconcile(p).status == "optimal"


def test_unknown_symbol_in_band_is_rejected():
    p = _payload()
    p["bands"][0]["symbols"].append("ZZZ.X")
    r = reconcile.reconcile(p)
    assert r.status == "invalid_input"
    assert any("ZZZ.X" in e.reason for e in r.errors)


def test_unknown_symbol_in_excludes_is_rejected():
    p = _payload(excludes=["tobacco"])
    r = reconcile.reconcile(p)
    assert r.status == "invalid_input"
    assert any("tobacco" in e.reason for e in r.errors)


def test_weights_not_summing_to_one_are_rejected_not_rescaled():
    p = _payload()
    p["holdings"][0]["weight"] = 0.9
    r = reconcile.reconcile(p)
    assert r.status == "invalid_input"
    assert any(e.path == "holdings" for e in r.errors)


def test_missing_basis_is_rejected():
    p = _payload()
    del p["basis"]
    r = reconcile.reconcile(p)
    assert r.status == "invalid_input"
    assert any(e.path == "basis" for e in r.errors)


def test_validation_collects_every_error():
    p = _payload()
    del p["basis"]
    p["holdings"][0]["weight"] = -1
    p["bands"][0]["min"] = 2
    r = reconcile.reconcile(p)
    assert r.status == "invalid_input"
    assert len(r.errors) >= 3


# --------------------------------------------------------------------------
# Solver availability fails closed (the jsonschema / PR #108 precedent)
# --------------------------------------------------------------------------

def test_missing_scipy_is_solver_unavailable_not_a_clean_result(monkeypatch):
    monkeypatch.setitem(sys.modules, "scipy", None)
    monkeypatch.setitem(sys.modules, "scipy.optimize", None)
    r = reconcile.reconcile(_payload())
    assert r.status == "solver_unavailable"
    assert r.solver["available"] is False
    assert r.target_weights is None and r.trades is None
    assert "UNVERIFIED" in r.solver["message"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def test_cli_round_trip(tmp_path):
    f = tmp_path / "payload.json"
    f.write_text(json.dumps(_payload()), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(MODULE), "--input", str(f)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "optimal"
    assert abs(out["target_weights"]["AAA.X"] - 0.6) < TOL


def test_cli_exit_codes_distinguish_outcomes(tmp_path):
    f = tmp_path / "payload.json"
    p = _payload(excludes=["CCC.X"])       # infeasible case from above
    f.write_text(json.dumps(p), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(MODULE), "--input", str(f)],
                          capture_output=True, text=True)
    assert proc.returncode == 4
    assert json.loads(proc.stdout)["status"] == "infeasible"


def test_cli_rejects_unreadable_payload(tmp_path):
    f = tmp_path / "payload.json"
    f.write_text("{not json", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(MODULE), "--input", str(f)],
                          capture_output=True, text=True)
    assert proc.returncode == 3
    assert json.loads(proc.stdout)["status"] == "invalid_input"


# --------------------------------------------------------------------------
# Immutability of the input
# --------------------------------------------------------------------------

def test_payload_is_not_mutated():
    p = _payload()
    snapshot = copy.deepcopy(p)
    reconcile.reconcile(p)
    assert p == snapshot
