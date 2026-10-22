"""Eval spec for /parallax-portfolio-builder.

portfolio-builder is the only constructive skill in the cluster — it builds a portfolio
from a natural-language thesis (build_stock_universe -> score -> select -> optimize).
It has no macro in the default path (macro_conditional is dropped). Its core deliverable
is the Selected Holdings allocation table (weights, scores).

Checks: sections_present, ai_disclosure_present, disclaimer_present_correct,
provenance_present, holdings_allocated, clean_start, orchestrator_length.
Tier-2: no_hallucinated_data, factor_profile_consistent, thesis_alignment,
allocation_weights_valid.

NOTE: if build_stock_universe returns nothing the skill renders "Universe Built: unavailable"
and skips Selected Holdings by design. A capture hitting that path causes holdings_allocated
and sections_present to fail; triage as the empty-universe path, not an output defect.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "graders"))
from eval_spec import EvalSpec  # noqa: E402
from judge_criteria import CRITERIA  # noqa: E402
from tier1_structural import Check, _section_text  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Unconditional sections in the PINNED state (no view, no white-label). Redundancy Notes is
# conditional (only if overlap flagged) -> section_labels only. View-Effect Summary +
# House View Preamble are view-only.
_REQUIRED_SECTIONS = [
    "Investment Thesis",
    "Universe Built",
    "Selected Holdings",
    "Portfolio Factor Profile",
    "Implementation Notes",
    "About This Report",
]
_SECTION_LABELS = [
    "House View Preamble",
    "Branding Header",
    "Investment Thesis",
    "Universe Built",
    "Selected Holdings",
    "View-Effect Summary",
    "Portfolio Factor Profile",
    "Redundancy Notes",
    "Implementation Notes",
    "About This Report",
]

_PCT = re.compile(r"\d+(?:\.\d+)?\s*%")
_SCORE_NUM = re.compile(r"\d+\.\d+")


def _c_holdings_allocated(t, spec) -> Check:
    """Checks that Selected Holdings is present and contains at least one weight (%) and
    a score number. A thesis restatement with no allocation table fails. Also flags the
    empty-universe degradation path (triage, not a fix)."""
    sec = _section_text(t.final_prose, "Selected Holdings", spec.section_labels)
    if not sec:
        return Check(
            "holdings_allocated",
            False,
            "Selected Holdings absent (empty-universe? triage)",
        )
    has_w, has_s = bool(_PCT.search(sec)), bool(_SCORE_NUM.search(sec))
    return Check(
        "holdings_allocated", has_w and has_s, f"weight_pct={has_w} score_num={has_s}"
    )


# Scaffold tokens that must NOT open the response; titles/headers that legitimately may.
_LEAK_START = re.compile(
    r"(?i)^\s*(?:\*\*)?(step\b|phase [ab]\b|all data\b|pre-?flight|drift check|"
    r"white-?label\b|branding state|config_not_found|composing\b|no active (house )?view|"
    r"audit log|universe (build|built)|building (the )?universe|divergence assert|"
    r"gap[_ ]detect|build_stock_universe|get_(peer|company|score)|"
    r"tool (search|loading)|scoring (top|picks)|candidates? (built|scored))"
)
_OK_START = re.compile(
    r"(?i)^\s*(?:#{1,4}\s*.*\b|\*\*\s*)"
    r"(portfolio builder|portfolio construction|investment thesis)\b"
)
_HR_OR_BLANK = re.compile(r"^[-*_ ]{0,}$|^[-*_ ]{3,}$")


def _c_clean_start(t, spec) -> Check:
    """Checks that the output begins with the rendered report title or the Investment Thesis
    section, not with internal scaffold (step narration, universe-build/scoring chatter,
    config-probes, audit-log). Leading blank/horizontal-rule lines are skipped."""
    first = ""
    for line in t.final_prose.splitlines():
        s = line.strip()
        if _HR_OR_BLANK.fullmatch(s):
            continue
        first = s
        break
    if _LEAK_START.search(first):
        ok = False
    elif _OK_START.search(first):
        ok = True
    else:
        ok = False
    return Check("clean_start", ok, f"first_line={first[:70]!r}")


_NO_HALLUC = next(c for c in CRITERIA if c["id"] == "no_hallucinated_data")  # COPIED

SPEC = EvalSpec(
    name="portfolio-builder",
    command="/parallax-portfolio-builder",
    rollout_prefix="portfolio-builder",
    skill_md_path=_REPO_ROOT / "skills" / "parallax-portfolio-builder" / "SKILL.md",
    required_sections=_REQUIRED_SECTIONS,
    section_labels=_SECTION_LABELS,
    check_ids=[
        "sections_present",  # COPIED
        "ai_disclosure_present",  # COPIED (§9.2)
        "disclaimer_present_correct",  # COPIED (§9.1)
        "provenance_present",  # COPIED
        "holdings_allocated",  # NEW
        "clean_start",  # NEW
        "orchestrator_length",  # COPIED
        # macro_conditional DROPPED: this skill has no macro tool or macro section in the default path.
    ],
    extra_checks={
        "holdings_allocated": _c_holdings_allocated,
        "clean_start": _c_clean_start,
    },
    tier2_criteria=[
        _NO_HALLUC,  # COPIED (generic)
        {
            "id": "factor_profile_consistent",  # ADAPTED
            "statement": "The Portfolio Factor Profile (VALUE/QUALITY/MOMENTUM/DEFENSIVE) is consistent with the selected holdings' individual scores and weights.",
            "pass_when": "The weighted aggregate direction matches the holdings shown; e.g. a quality+momentum thesis book shows high QUALITY/MOMENTUM in the profile.",
        },
        {
            "id": "thesis_alignment",
            "statement": "The Selected Holdings actually match the stated investment thesis (sector/region/style/constraints).",
            "pass_when": "Holdings fit the thesis (e.g. 'US tech quality+momentum' -> US technology names with strong quality/momentum scores); off-thesis picks are absent or explicitly justified.",
        },
        {
            "id": "allocation_weights_valid",
            "statement": "The allocation weights are valid — they sum to approximately 1.0 (100%) and no single position dominates unless the thesis justifies concentration.",
            "pass_when": "Weights total ~100% (±a few %); position sizes are reasonable for the stated thesis.",
        },
    ],
    tasks_path="evals/tasks/portfolio-builder/core.jsonl",
    orchestrator_max_lines=250,
)
