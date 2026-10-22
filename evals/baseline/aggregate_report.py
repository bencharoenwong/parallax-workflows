"""Pure aggregation of per-run grader scores into a noise-floor report."""
from __future__ import annotations

import statistics
from collections import defaultdict


def _mean(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 6) if xs else 0.0


def _var(xs: list[float]) -> float:
    return round(statistics.pvariance(xs), 6) if len(xs) > 1 else 0.0


def summarize(runs: list[dict]) -> dict:
    """runs: list of {task, tier1, tier2} where tier1/tier2 are per-run pass-fractions;
    tier2 may be None (excluded from aggregation) for specs with no Tier-2 criteria."""
    by_task: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"tier1": [], "tier2": []})
    for r in runs:
        by_task[r["task"]]["tier1"].append(float(r["tier1"]))
        if r["tier2"] is not None:
            by_task[r["task"]]["tier2"].append(float(r["tier2"]))

    per_task = {}
    for task, d in by_task.items():
        per_task[task] = {
            "n": len(d["tier1"]),
            "tier1_mean": _mean(d["tier1"]), "tier1_var": _var(d["tier1"]),
            "tier2_mean": _mean(d["tier2"]) if d["tier2"] else None,
            "tier2_var": _var(d["tier2"]) if d["tier2"] else None,
        }

    all_t1 = [float(r["tier1"]) for r in runs]
    all_t2 = [float(r["tier2"]) for r in runs if r["tier2"] is not None]
    overall = {
        "n_runs": len(runs),
        "tier1_mean": _mean(all_t1), "tier1_var": _var(all_t1),
        "tier2_mean": _mean(all_t2) if all_t2 else None,
        "tier2_var": _var(all_t2) if all_t2 else None,
    }
    return {
        "overall": overall,
        "per_task": per_task,
        "below_ceiling": overall["tier1_mean"] < 1.0
        or (overall["tier2_mean"] is not None and overall["tier2_mean"] < 1.0),
    }
