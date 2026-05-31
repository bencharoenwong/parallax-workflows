"""Eval spec for /parallax-portfolio-checkup.

Same FAMILY as should-i-buy (structured English research output, MCP tools, shared
conventions: §9.2 AI-disclosure, "not investment advice" disclaimer, Provenance
line via integration-pattern §7, conditional Macro Context). So it reuses the
GENERIC checks that AI-buffett (a different family) could not:

Reuse tally vs should-i-buy:
  Tier-1: sections_present, macro_conditional, ai_disclosure_present,
          disclaimer_present_correct, provenance_present, orchestrator_length
          = 6 GENERIC (copied). consider_no_directive = NEW (analogue of
          bottom_line_no_rec, scoped to the "Consider" section). Reuse 6/7.
  Tier-2: no_hallucinated_data = COPIED; health_status_consistent,
          consider_as_questions, plain_language = NEW. Reuse 1/4.
Finding: reuse tracks FAMILY — portfolio-checkup (should-i-buy's family) reuses
6/7 tier-1 vs AI-buffett's 2/6. The generator is per-family.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "graders"))
from eval_spec import EvalSpec  # noqa: E402
from tier1_structural import Check, _section_text, _REC_PATTERNS  # noqa: E402
from judge_criteria import CRITERIA  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]

_REQUIRED_SECTIONS = [
    "Portfolio Health Status", "Health Flags", "What This Means",
    "Consider", "Provenance",
]
_SECTION_LABELS = [
    "House View Preamble", "Portfolio Health Status", "Verification Note",
    "Your Portfolio Scorecard", "Health Flags", "Overlap Alert",
    "Macro Context", "What This Means", "Consider", "Provenance",
]


def _c_consider_no_directive(t, spec) -> Check:
    """The Consider section frames suggestions as questions, not buy/sell directives."""
    text = _section_text(t.final_prose, "Consider", spec.section_labels)
    hit = next((p for p in _REC_PATTERNS if re.search(p, text, re.I)), None)
    return Check("consider_no_directive", hit is None, f"directive_token_in_consider={hit}")


_NO_HALLUC = next(c for c in CRITERIA if c["id"] == "no_hallucinated_data")  # COPIED

SPEC = EvalSpec(
    name="portfolio-checkup",
    command="/parallax-portfolio-checkup",
    rollout_prefix="portfolio-checkup",
    skill_md_path=_REPO_ROOT / "skills" / "portfolio-checkup" / "SKILL.md",
    required_sections=_REQUIRED_SECTIONS,
    section_labels=_SECTION_LABELS,
    check_ids=[
        "sections_present",             # GENERIC
        "macro_conditional",            # GENERIC
        "ai_disclosure_present",        # GENERIC
        "disclaimer_present_correct",   # GENERIC ("not investment advice" — same family)
        "provenance_present",           # GENERIC
        "consider_no_directive",        # NEW (analogue of bottom_line_no_rec)
        "orchestrator_length",          # GENERIC
    ],
    extra_checks={"consider_no_directive": _c_consider_no_directive},
    tier2_criteria=[
        _NO_HALLUC,  # COPIED
        {
            "id": "health_status_consistent",
            "statement": "The Portfolio Health Status badge (Healthy/Monitor/Attention) is consistent with the number and severity of Health Flags shown.",
            "pass_when": "More/severe flags → Monitor/Attention; no/minor flags → Healthy. Badge and flags agree.",
        },
        {
            "id": "consider_as_questions",
            "statement": "The 'Consider' suggestions are framed as questions or options for the investor, not as buy/sell directives.",
            "pass_when": "Suggestions read as 'you might consider…/have you thought about…', not 'buy X / sell Y'.",
        },
        {
            "id": "plain_language",
            "statement": "The output is plain-language for an individual investor — finance jargon is explained or avoided.",
            "pass_when": "A retail investor could follow it; any technical term (beta, factor) is given a plain gloss.",
        },
    ],
    tasks_path="evals/tasks/portfolio-checkup/core.jsonl",
    orchestrator_max_lines=250,
)
