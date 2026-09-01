"""S3 Reconciliation: holdings-level constrained optimization for rebalance.

Solves the design-spec S3 problem as a linear program: maximize the supplied
per-holding objective coefficients (tilt-weighted composite scores, built by
the calling skill — this module never computes tilts or scores itself) minus a
turnover penalty, subject to full investment, hard excludes, per-symbol bounds,
a position cap, and aggregate region/sector band constraints. |w - w0| is
linearized with one auxiliary variable per holding, so the whole objective is
linear and scipy's HiGHS backend solves it exactly.

FAIL-CLOSED CONTRACT. The trade list is gate-shaped (conventions §4.0): it
tells an RM what to buy and sell. Three consequences, none negotiable:

  * scipy absent  -> status="solver_unavailable", no weights, no trades. The
    caller renders an UNVERIFIED-class error, never a partial or empty trade
    list. Mirrors the white-label jsonschema precedent (PR #108).
  * a non-excluded holding without a finite objective coefficient ->
    status="invalid_input" naming the symbols. A silent 0.0 coefficient would
    change the optimization without anyone knowing.
  * infeasible constraints -> status="infeasible" with the SMALLEST violations
    (an exact second LP: uniform L1 slacks on every relaxable constraint,
    excludes and the sum(w)=1 budget kept hard), and NOTHING else — no target
    weights, no trade list, not even labeled "suggested". Returning the relaxed
    allocation is exactly the silent relax the spec bans.

Bound conflicts (an exclude against a user minimum, a user minimum above the
cap) are surfaced as named conflicts for human decision before the solver ever
runs — precedence collisions are never auto-resolved (design guardrail 5).

Weights are in the basis the payload declares (`basis`, explicit, never
assumed); the caller converts sleeve results to total-portfolio terms visibly.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

CALIBRATION_STATUS = "heuristic_phase0"

# Phase-0 heuristic, disclosed in every output (design guardrail 4). One unit
# of score per unit of two-sided turnover; Phase 3's attribution work is the
# calibration on-ramp. Overridable per payload, never silently.
DEFAULT_TURNOVER_PENALTY = 1.0

BASES = ("sleeve", "total")

SUM_TOLERANCE = 1e-4        # current weights come from live data, not a schema
BINDING_TOLERANCE = 1e-6    # a band/bound within this of its edge is "binding"
VIOLATION_TOLERANCE = 1e-9  # elastic slack below this is solver noise
TRADE_TOLERANCE = 1e-6      # |delta| at or below this renders as "hold"

STATUS_OPTIMAL = "optimal"
STATUS_INFEASIBLE = "infeasible"
STATUS_CONFLICT = "conflict"
STATUS_INVALID_INPUT = "invalid_input"
STATUS_SOLVER_UNAVAILABLE = "solver_unavailable"
STATUS_SOLVER_ERROR = "solver_error"

SOLVER_BACKEND = "scipy.optimize.linprog:highs"


# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class InputError:
    """One validation failure, addressed by dotted path into the payload."""
    path: str
    reason: str


@dataclass(frozen=True)
class Conflict:
    """A precedence collision surfaced for human decision; never auto-resolved."""
    kind: str          # exclude_vs_user_min|bound_min_above_max|all_holdings_excluded
    detail: dict


@dataclass(frozen=True)
class Trade:
    """One candidate action. Weights are in the result's declared basis."""
    symbol: str
    current: float
    target: float
    delta: float               # target - current
    action: str                # buy|sell|hold


@dataclass(frozen=True)
class BindingConstraint:
    """A constraint sitting on its edge in the optimal solution."""
    constraint: str            # e.g. "band:region:asia:max", "bound:AAA.X:max"
    value: float               # the aggregate or weight sitting at the edge


@dataclass(frozen=True)
class Violation:
    """One smallest-violation entry from the elastic diagnosis LP."""
    constraint: str            # same id scheme as BindingConstraint
    amount: float              # weight points of relaxation required


@dataclass(frozen=True)
class ReconcileResult:
    """Complete S3 result. Every field renders; nothing is computed downstream."""
    status: str                    # optimal|infeasible|conflict|invalid_input|
                                   # solver_unavailable|solver_error
    basis: str | None              # sleeve|total, verbatim from the payload
    turnover_penalty: float | None
    penalty_source: str | None     # "default"|"explicit"
    calibration_status: str
    errors: list[InputError]
    conflicts: list[Conflict]
    target_weights: dict | None    # {symbol: weight}; None unless optimal
    trades: list[Trade] | None     # None unless optimal
    objective: dict | None         # {score_term, turnover_term, total}; None unless optimal
    binding: list[BindingConstraint]
    violations: list[Violation]    # non-empty only when infeasible
    solver: dict                   # {backend, available, message}

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Small shared predicates
# --------------------------------------------------------------------------

def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _result(status: str, *, basis: str | None = None,
            turnover_penalty: float | None = None, penalty_source: str | None = None,
            errors: list[InputError] | None = None,
            conflicts: list[Conflict] | None = None,
            target_weights: dict | None = None, trades: list[Trade] | None = None,
            objective: dict | None = None,
            binding: list[BindingConstraint] | None = None,
            violations: list[Violation] | None = None,
            solver_available: bool = True, solver_message: str = "") -> ReconcileResult:
    return ReconcileResult(
        status=status, basis=basis,
        turnover_penalty=turnover_penalty, penalty_source=penalty_source,
        calibration_status=CALIBRATION_STATUS,
        errors=errors or [], conflicts=conflicts or [],
        target_weights=target_weights, trades=trades, objective=objective,
        binding=binding or [], violations=violations or [],
        solver={"backend": SOLVER_BACKEND, "available": solver_available,
                "message": solver_message},
    )


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate_payload(payload: Any) -> list[InputError]:
    """Every check runs; the caller gets the full list, not the first failure."""
    if not isinstance(payload, dict):
        return [InputError("$", "payload must be an object")]
    errors: list[InputError] = []

    basis = payload.get("basis")
    if basis not in BASES:
        errors.append(InputError("basis",
                                 f"must be one of {list(BASES)}; the basis is "
                                 "declared explicitly, never assumed"))

    holdings = payload.get("holdings")
    symbols: list[str] = []
    if not isinstance(holdings, list) or not holdings:
        errors.append(InputError("holdings", "must be a non-empty array"))
        holdings = []
    excludes = payload.get("excludes", [])
    if not isinstance(excludes, list) or any(not isinstance(s, str) for s in excludes):
        errors.append(InputError("excludes", "must be an array of symbols"))
        excludes = []
    excluded = set(excludes)

    weight_sum = 0.0
    for i, h in enumerate(holdings):
        path = f"holdings[{i}]"
        if not isinstance(h, dict):
            errors.append(InputError(path, "must be an object"))
            continue
        sym = h.get("symbol")
        if not isinstance(sym, str) or not sym:
            errors.append(InputError(f"{path}.symbol", "must be a non-empty string"))
            continue
        if sym in symbols:
            errors.append(InputError(f"{path}.symbol", f"duplicate symbol {sym}"))
            continue
        symbols.append(sym)
        w = h.get("weight")
        if not _is_number(w) or w < 0:
            errors.append(InputError(f"{path}.weight", "must be a finite number >= 0"))
        else:
            weight_sum += w
        # A silent 0.0 for a missing coefficient would change the optimization
        # without anyone knowing; excluded holdings are pinned at 0 and may
        # omit it.
        if sym not in excluded and not _is_number(h.get("coefficient")):
            errors.append(InputError(f"{path}.coefficient",
                                     f"non-excluded holding {sym} has no finite "
                                     "objective coefficient"))
        for side in ("min", "max"):
            if side in h and (not _is_number(h[side]) or not 0 <= h[side] <= 1):
                errors.append(InputError(f"{path}.{side}",
                                         "must be a finite number in [0, 1]"))

    if holdings and not any(e.path == "holdings" or e.path.endswith(".weight")
                            for e in errors):
        if abs(weight_sum - 1.0) > SUM_TOLERANCE:
            errors.append(InputError(
                "holdings",
                f"weights sum to {weight_sum:.6f}, not 1 (tolerance "
                f"{SUM_TOLERANCE}); normalize upstream — this module never "
                "rescales silently"))

    cap = payload.get("position_cap")
    if cap is not None and (not _is_number(cap) or not 0 < cap <= 1):
        errors.append(InputError("position_cap", "must be a finite number in (0, 1]"))

    penalty = payload.get("turnover_penalty")
    if penalty is not None and (not _is_number(penalty) or penalty < 0):
        errors.append(InputError("turnover_penalty",
                                 "must be a finite number >= 0"))

    known = set(symbols)
    if holdings:
        # A typo or unresolved sector/region/theme name here would silently
        # constrain nothing — mirrors the band-symbol check below.
        unknown_excludes = [s for s in excludes if s not in known]
        if unknown_excludes:
            errors.append(InputError("excludes",
                                     f"not in holdings: {unknown_excludes}"))

    bands = payload.get("bands", [])
    if not isinstance(bands, list):
        errors.append(InputError("bands", "must be an array"))
        bands = []
    for i, b in enumerate(bands):
        path = f"bands[{i}]"
        if not isinstance(b, dict):
            errors.append(InputError(path, "must be an object"))
            continue
        for fld in ("dimension", "key"):
            if not isinstance(b.get(fld), str) or not b.get(fld):
                errors.append(InputError(f"{path}.{fld}", "must be a non-empty string"))
        members = b.get("symbols")
        if not isinstance(members, list) or not members:
            errors.append(InputError(f"{path}.symbols", "must be a non-empty array"))
        else:
            # A typo here would silently constrain nothing.
            unknown = [s for s in members if s not in known]
            if unknown:
                errors.append(InputError(f"{path}.symbols",
                                         f"not in holdings: {unknown}"))
        lo, hi = b.get("min"), b.get("max")
        if lo is None and hi is None:
            errors.append(InputError(path, "needs min, max, or both"))
        for side, v in (("min", lo), ("max", hi)):
            if v is not None and (not _is_number(v) or not 0 <= v <= 1):
                errors.append(InputError(f"{path}.{side}",
                                         "must be a finite number in [0, 1]"))
        if _is_number(lo) and _is_number(hi) and lo > hi:
            errors.append(InputError(path, f"min {lo} exceeds max {hi}"))

    return errors


def resolve_bounds(payload: dict) -> tuple[list[dict], list[Conflict]]:
    """Per-symbol [lb, ub] from excludes, user min/max, and the position cap.

    Collisions come back as named conflicts, not a generic LP infeasibility:
    an exclude against a user minimum is a precedence question for a human
    (design guardrail 5), and it must read that way in the report.
    """
    excluded = set(payload.get("excludes", []))
    cap = payload.get("position_cap")
    conflicts: list[Conflict] = []
    rows: list[dict] = []
    for h in payload["holdings"]:
        sym = h["symbol"]
        if sym in excluded:
            if _is_number(h.get("min")) and h["min"] > 0:
                conflicts.append(Conflict("exclude_vs_user_min",
                                          {"symbol": sym, "user_min": h["min"]}))
            rows.append({"symbol": sym, "lb": 0.0, "ub": 0.0, "excluded": True})
            continue
        lb = float(h.get("min", 0.0) or 0.0)
        ub = 1.0
        if _is_number(h.get("max")):
            ub = min(ub, float(h["max"]))
        if _is_number(cap):
            ub = min(ub, float(cap))
        if lb > ub:
            conflicts.append(Conflict("bound_min_above_max",
                                      {"symbol": sym, "min": lb, "max": ub}))
        rows.append({"symbol": sym, "lb": lb, "ub": ub, "excluded": False})
    if rows and all(r["excluded"] for r in rows):
        conflicts.append(Conflict("all_holdings_excluded",
                                  {"detail": "sum(w)=1 cannot be met"}))
    return rows, conflicts


# --------------------------------------------------------------------------
# LP assembly
# --------------------------------------------------------------------------

def _band_rows(payload: dict, index: dict[str, int]) -> list[dict]:
    """One row per band edge: {id, indices, sense, edge}."""
    rows = []
    for b in payload.get("bands", []):
        idxs = [index[s] for s in b["symbols"]]
        stem = f"band:{b['dimension']}:{b['key']}"
        if b.get("max") is not None:
            rows.append({"id": f"{stem}:max", "indices": idxs,
                         "sense": "le", "edge": float(b["max"])})
        if b.get("min") is not None:
            rows.append({"id": f"{stem}:min", "indices": idxs,
                         "sense": "ge", "edge": float(b["min"])})
    return rows


def _solve(payload: dict, bounds: list[dict], penalty: float):
    """The primary LP. Returns (scipy result, band rows, symbol order)."""
    from scipy.optimize import linprog

    syms = [h["symbol"] for h in payload["holdings"]]
    index = {s: i for i, s in enumerate(syms)}
    n = len(syms)
    w0 = [float(h["weight"]) for h in payload["holdings"]]
    coef = [float(h.get("coefficient", 0.0)) for h in payload["holdings"]]

    # Variables: w_0..w_{n-1}, then t_0..t_{n-1} with t_i >= |w_i - w0_i|.
    c = [-cf for cf in coef] + [penalty] * n

    a_ub: list[list[float]] = []
    b_ub: list[float] = []

    def _row(entries: dict[int, float], rhs: float) -> None:
        row = [0.0] * (2 * n)
        for j, v in entries.items():
            row[j] = v
        a_ub.append(row)
        b_ub.append(rhs)

    for i in range(n):
        _row({i: 1.0, n + i: -1.0}, w0[i])      # w_i - t_i <= w0_i
        _row({i: -1.0, n + i: -1.0}, -w0[i])    # -w_i - t_i <= -w0_i

    bands = _band_rows(payload, index)
    for row in bands:
        if row["sense"] == "le":
            _row({j: 1.0 for j in row["indices"]}, row["edge"])
        else:
            _row({j: -1.0 for j in row["indices"]}, -row["edge"])

    a_eq = [[1.0] * n + [0.0] * n]
    b_eq = [1.0]
    var_bounds = [(r["lb"], r["ub"]) for r in bounds] + [(0.0, None)] * n

    res = linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq,
                  bounds=var_bounds, method="highs")
    return res, bands, syms


def _diagnose(payload: dict, bounds: list[dict]) -> list[Violation]:
    """Elastic LP: smallest violations, solved exactly (never approximated).

    Hard: sum(w)=1, excludes (lb=ub=0), and the structural 0<=w<=1 box.
    Relaxable, one slack per edge: every band edge, every non-exclude user
    bound, and the position cap (folded into ub upstream). Uniform L1 weights,
    so "smallest" means smallest total weight-points of relaxation.
    """
    from scipy.optimize import linprog

    syms = [h["symbol"] for h in payload["holdings"]]
    index = {s: i for i, s in enumerate(syms)}
    n = len(syms)

    slack_ids: list[str] = []
    a_ub: list[dict[int, float]] = []   # sparse rows over w-vars; slack added below
    b_ub: list[float] = []

    def _elastic(entries: dict[int, float], rhs: float, cid: str) -> None:
        slack_ids.append(cid)
        a_ub.append(entries)
        b_ub.append(rhs)

    for i, r in enumerate(bounds):
        if r["excluded"]:
            continue
        if r["ub"] < 1.0:
            _elastic({i: 1.0}, r["ub"], f"bound:{syms[i]}:max")
        if r["lb"] > 0.0:
            _elastic({i: -1.0}, -r["lb"], f"bound:{syms[i]}:min")
    for row in _band_rows(payload, index):
        if row["sense"] == "le":
            _elastic({j: 1.0 for j in row["indices"]}, row["edge"], row["id"])
        else:
            _elastic({j: -1.0 for j in row["indices"]}, -row["edge"], row["id"])

    m = len(slack_ids)
    c = [0.0] * n + [1.0] * m
    dense = []
    for k, entries in enumerate(a_ub):
        row = [0.0] * (n + m)
        for j, v in entries.items():
            row[j] = v
        row[n + k] = -1.0                       # ... <= rhs + slack_k
        dense.append(row)
    a_eq = [[1.0] * n + [0.0] * m]
    var_bounds = [(0.0, 0.0) if r["excluded"] else (0.0, 1.0) for r in bounds]
    var_bounds += [(0.0, None)] * m

    res = linprog(c, A_ub=dense, b_ub=b_ub, A_eq=a_eq, b_eq=[1.0],
                  bounds=var_bounds, method="highs")
    if res.status != 0:
        # Only reachable when sum(w)=1 itself cannot hold; that case is caught
        # upstream as all_holdings_excluded.
        return []
    out = [Violation(cid, round(float(res.x[n + k]), 9))
           for k, cid in enumerate(slack_ids)
           if res.x[n + k] > VIOLATION_TOLERANCE]
    return sorted(out, key=lambda v: (-v.amount, v.constraint))


def _binding(payload: dict, bounds: list[dict], weights: dict) -> list[BindingConstraint]:
    out = []
    for r in bounds:
        if r["excluded"]:
            continue
        w = weights[r["symbol"]]
        if r["ub"] < 1.0 and abs(w - r["ub"]) <= BINDING_TOLERANCE:
            out.append(BindingConstraint(f"bound:{r['symbol']}:max", round(w, 9)))
        elif r["lb"] > 0.0 and abs(w - r["lb"]) <= BINDING_TOLERANCE:
            out.append(BindingConstraint(f"bound:{r['symbol']}:min", round(w, 9)))
    index = {h["symbol"]: h["symbol"] for h in payload["holdings"]}
    for b in payload.get("bands", []):
        total = sum(weights[s] for s in b["symbols"] if s in index)
        stem = f"band:{b['dimension']}:{b['key']}"
        if b.get("max") is not None and abs(total - float(b["max"])) <= BINDING_TOLERANCE:
            out.append(BindingConstraint(f"{stem}:max", round(total, 9)))
        if b.get("min") is not None and abs(total - float(b["min"])) <= BINDING_TOLERANCE:
            out.append(BindingConstraint(f"{stem}:min", round(total, 9)))
    return out


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def reconcile(payload: Any) -> ReconcileResult:
    """Validate, resolve bounds, solve; fail closed on every unhappy path."""
    errors = validate_payload(payload)
    if errors:
        return _result(STATUS_INVALID_INPUT,
                       basis=payload.get("basis") if isinstance(payload, dict) else None,
                       errors=errors)

    basis = payload["basis"]
    if payload.get("turnover_penalty") is not None:
        penalty, penalty_source = float(payload["turnover_penalty"]), "explicit"
    else:
        penalty, penalty_source = DEFAULT_TURNOVER_PENALTY, "default"

    bounds, conflicts = resolve_bounds(payload)
    if conflicts:
        return _result(STATUS_CONFLICT, basis=basis, turnover_penalty=penalty,
                       penalty_source=penalty_source, conflicts=conflicts)

    try:
        from scipy.optimize import linprog  # noqa: F401
    except Exception as exc:                # pragma: no cover - message only
        return _result(
            STATUS_SOLVER_UNAVAILABLE, basis=basis, turnover_penalty=penalty,
            penalty_source=penalty_source, solver_available=False,
            solver_message=f"scipy unavailable ({type(exc).__name__}); install "
                           "skills/_parallax/client-policy/requirements.txt. "
                           "Trade list is UNVERIFIED — never render a partial "
                           "or empty one in its place.")

    res, _bands, syms = _solve(payload, bounds, penalty)

    if res.status == 2:                     # linprog: infeasible
        return _result(STATUS_INFEASIBLE, basis=basis, turnover_penalty=penalty,
                       penalty_source=penalty_source,
                       violations=_diagnose(payload, bounds),
                       solver_message="constraints are jointly infeasible; "
                                      "violations list the smallest relaxations")
    if res.status != 0:
        return _result(STATUS_SOLVER_ERROR, basis=basis, turnover_penalty=penalty,
                       penalty_source=penalty_source,
                       solver_message=f"linprog status {res.status}: {res.message}")

    weights = {s: round(float(res.x[i]), 9) for i, s in enumerate(syms)}
    w0 = {h["symbol"]: float(h["weight"]) for h in payload["holdings"]}
    coef = {h["symbol"]: float(h.get("coefficient", 0.0))
            for h in payload["holdings"]}
    trades = []
    for s in syms:
        delta = weights[s] - w0[s]
        action = "hold" if abs(delta) <= TRADE_TOLERANCE else (
            "buy" if delta > 0 else "sell")
        trades.append(Trade(s, round(w0[s], 9), weights[s], round(delta, 9), action))
    score_term = sum(coef[s] * weights[s] for s in syms)
    turnover = sum(abs(t.delta) for t in trades)
    return _result(
        STATUS_OPTIMAL, basis=basis, turnover_penalty=penalty,
        penalty_source=penalty_source, target_weights=weights, trades=trades,
        objective={"score_term": round(score_term, 9),
                   "turnover_term": round(penalty * turnover, 9),
                   "total": round(score_term - penalty * turnover, 9)},
        binding=_binding(payload, bounds, weights))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

_EXIT = {STATUS_OPTIMAL: 0, STATUS_INFEASIBLE: 4, STATUS_CONFLICT: 3,
         STATUS_INVALID_INPUT: 3, STATUS_SOLVER_UNAVAILABLE: 5,
         STATUS_SOLVER_ERROR: 5}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S3 reconciliation: policy-constrained rebalance targets")
    parser.add_argument("--input", required=True,
                        help="JSON payload file (see module docstring)")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": STATUS_INVALID_INPUT,
                          "errors": [{"path": "$", "reason": str(exc)}]}))
        return 3
    result = reconcile(payload)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return _EXIT[result.status]


if __name__ == "__main__":
    sys.exit(main())
