"""Eval spec for /parallax-deep-dive.

This is a structural baseline for the single-position research workflow. The
skill-specific regression check enforces the Technical Stance fallback so the
lens does not disappear when `get_technical_analysis` is unavailable.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "graders"))
from eval_spec import EvalSpec  # noqa: E402
from tier1_structural import Check, _section_text  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _c_technical_fallback_explicit(t, spec):
    tech = _section_text(t.final_prose, "Technical Stance", spec.section_labels)
    if not tech:
        return Check("technical_fallback_explicit", False, "Technical Stance section missing")
    if re.search(r"technical analysis unavailable", tech, re.I):
        ok = re.search(r"momentum factor proxy", tech, re.I) is not None
        return Check(
            "technical_fallback_explicit",
            ok,
            "fallback note must name the Momentum factor proxy",
        )
    return Check("technical_fallback_explicit", True, "technical analysis available")


def _c_disclaimer_present_deep_dive(t, spec):
    prose = t.final_prose.lower()
    ok = (
        "not investment advice" in prose
        or "this analysis reflects active house view" in prose
    )
    return Check("disclaimer_present_deep_dive", ok, "standard or view-aware disclaimer present")


SPEC = EvalSpec(
    name="deep-dive",
    command="/parallax-deep-dive",
    skill_md_path=_REPO_ROOT / "skills" / "parallax-deep-dive" / "SKILL.md",
    required_sections=[
        "Company Overview",
        "Macro Environment",
        "Factor Profile",
        "Financial Highlights",
        "Dividend Profile",
        "Risk/Return Profile",
        "Technical Stance",
        "News Catalyst Watch",
        "Assessment",
        "Risk Factors",
        "Provenance",
    ],
    section_labels=[
        "Company Overview",
        "Macro Environment",
        "Factor Profile",
        "House View Note",
        "Financial Highlights",
        "Dividend Profile",
        "Risk/Return Profile",
        "Technical Stance",
        "News Catalyst Watch",
        "Assessment",
        "Risk Factors",
        "Provenance",
    ],
    check_ids=[
        "sections_present",
        "technical_fallback_explicit",
        "provenance_present",
        "ai_disclosure_present",
        "disclaimer_present_deep_dive",
        "orchestrator_length",
    ],
    tier2_criteria=[],
    tasks_path="evals/tasks/deep-dive/core.jsonl",
    orchestrator_max_lines=220,
    extra_checks={
        "technical_fallback_explicit": _c_technical_fallback_explicit,
        "disclaimer_present_deep_dive": _c_disclaimer_present_deep_dive,
    },
)
