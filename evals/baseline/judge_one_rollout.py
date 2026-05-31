"""Tier-2 judge for a single rollout stream.json -> verdict JSON.

One rollout per process so the 12-rollout judge pass can be fanned out as
parallel background tasks (a single 48-call serial loop gets reaped by the
harness). Writes {task, tier2, verdicts} to the output path.

Usage:
  python3 baseline/judge_one_rollout.py <stream.json> <out.json> [model]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "graders"))
from transcript import load_transcript  # noqa: E402
from run_judge import grade_tier2  # noqa: E402

_TASK_RE = re.compile(r"baseline_(.+?)_r\d+_")


def main(stream: str, out: str, model: str = "claude-opus-4-8") -> int:
    t = load_transcript(stream)
    verdicts = grade_tier2(t, model)
    scored = [v for v in verdicts if v["pass"] is not None]
    frac = (sum(1 for v in scored if v["pass"]) / len(scored)) if scored else 0.0
    m = _TASK_RE.search(Path(stream).name)
    task = m.group(1) if m else Path(stream).stem
    result = {"task": task, "stream": Path(stream).name, "tier2": frac,
              "n_scored": len(scored), "verdicts": verdicts}
    Path(out).write_text(json.dumps(result, indent=2))
    print(f"{task}: tier2={frac:.3f} scored={len(scored)}/{len(verdicts)} "
          f"fails={[v['id'] for v in verdicts if v['pass'] is False]}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:4]))
