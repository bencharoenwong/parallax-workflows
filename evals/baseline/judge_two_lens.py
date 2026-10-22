"""Tier-2 judge using the TWO_LENS_CRITERIA raised-bar set (design-doc §4.4).

Grades one stream.json against lenses_separate_reads + technicals_grounded.
Used for the red/green check: old rollouts should FAIL, upgraded should PASS.

Usage:
  python3 baseline/judge_two_lens.py <stream.json> <out.json> [model]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "graders"))
from transcript import load_transcript  # noqa: E402
from judge_criteria import TWO_LENS_CRITERIA  # noqa: E402
from run_judge import judge_one, check_model, DEFAULT_JUDGE_MODEL  # noqa: E402


def main(stream: str, out: str, model: str = DEFAULT_JUDGE_MODEL) -> int:
    check_model(model)
    prose = load_transcript(stream).final_prose
    verdicts = [judge_one(c, prose, model) for c in TWO_LENS_CRITERIA]
    scored = [v for v in verdicts if v["pass"] is not None]
    frac = (sum(1 for v in scored if v["pass"]) / len(scored)) if scored else 0.0
    result = {"stream": Path(stream).name, "two_lens_tier2": frac,
              "n_scored": len(scored), "verdicts": verdicts}
    Path(out).write_text(json.dumps(result, indent=2))
    print(f"{Path(stream).name}: two_lens_tier2={frac:.3f} "
          f"verdicts={[(v['id'], v['pass']) for v in verdicts]}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:4]))
