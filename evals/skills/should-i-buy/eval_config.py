"""Eval spec for /parallax-should-i-buy — the reference baseline.

Values lifted verbatim from the pre-refactor tier1_structural.py so the checks
are unchanged after generalization.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "graders"))
from eval_spec import EvalSpec  # noqa: E402
from judge_criteria import CRITERIA  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]

SPEC = EvalSpec(
    name="should-i-buy",
    command="/parallax-should-i-buy",
    skill_md_path=_REPO_ROOT / "skills" / "should-i-buy" / "SKILL.md",
    # "The Company" deliberately NOT required: the live skill folds company
    # identity into the title rather than a standalone section.
    required_sections=[
        "The Scores", "Financial Health", "Dividends", "Risk vs Peers",
        "Recent News", "Analyst View", "Bottom Line", "Provenance",
    ],
    section_labels=[
        "The Company", "Fundamentals", "The Scores", "House View Note",
        "Financial Health", "Technicals", "Macro Context", "Dividends",
        "Risk vs Peers", "Recent News", "Analyst View", "Bottom Line", "Provenance",
    ],
    check_ids=[
        "sections_present", "scores_trend_direction", "macro_conditional",
        "dividends_explicit", "provenance_present", "ai_disclosure_present",
        "disclaimer_present_correct", "bottom_line_no_rec", "orchestrator_length",
    ],
    tier2_criteria=CRITERIA,
    tasks_path="evals/tasks/should-i-buy/core.jsonl",
    orchestrator_max_lines=250,
)
