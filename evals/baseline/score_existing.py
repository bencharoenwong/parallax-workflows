"""Score already-captured rollout stream.json files (Tier-1 only, offline).

Re-derives a trustworthy structural noise-floor from existing captures without
any live model calls. Tier-2 (judge) is intentionally excluded here — it costs
Anthropic calls; run baseline/run_baseline.sh for the full Tier-1+Tier-2 report.

Usage:
  python3 baseline/score_existing.py results/should-i-buy_baseline_*.stream.json
Task label is parsed from the filename segment after 'baseline_' up to '_r<N>'.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "graders"))
from transcript import load_transcript  # noqa: E402
from tier1_structural import grade_tier1, CHECK_NAMES  # noqa: E402
from eval_spec import load_spec  # noqa: E402
from aggregate_report import summarize  # noqa: E402

_TASK_RE = re.compile(r"baseline_(.+?)_r\d+_")


def _task_of(path: str) -> str:
    m = _TASK_RE.search(Path(path).name)
    return m.group(1) if m else Path(path).stem


def main(paths: list[str], skill: str = "should-i-buy") -> int:
    spec = load_spec(skill)
    runs = []
    per_check_fail: dict[str, int] = {n: 0 for n in CHECK_NAMES}
    for p in paths:
        t = load_transcript(p)
        checks = grade_tier1(t, spec)
        frac = sum(c.passed for c in checks) / len(checks) if checks else 0.0
        for c in checks:
            if not c.passed:
                per_check_fail[c.name] = per_check_fail.get(c.name, 0) + 1
        runs.append({"task": _task_of(p), "tier1": frac, "tier2": 0.0})
        fails = [c.name for c in checks if not c.passed]
        print(f"{Path(p).name}: tier1={frac:.3f}  fails={fails or '-'}")

    report = summarize(runs)
    print("\n=== per-task Tier-1 ===")
    for task, d in sorted(report["per_task"].items()):
        print(f"  {task}: n={d['n']} mean={d['tier1_mean']:.3f} var={d['tier1_var']:.4f}")
    print("\n=== overall Tier-1 ===")
    o = report["overall"]
    print(f"  n_runs={o['n_runs']} mean={o['tier1_mean']:.3f} var={o['tier1_var']:.4f}")
    flagged = {n: c for n, c in per_check_fail.items() if c}
    print(f"  checks ever failing: {flagged or 'none — all 9 pass every run'}")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    skill = "should-i-buy"
    if "--skill" in argv:
        i = argv.index("--skill")
        skill = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(argv, skill))
