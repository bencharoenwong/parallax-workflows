"""Eval spec for /parallax-rebalance.

rebalance keeps the canonical "Macro Context" section label, so the generic macro_conditional
and macro_specific criteria apply verbatim. Its core deliverable is the Trade Recommendations
table with quantified weights, priority labels, and action verbs.

Checks: sections_present, macro_conditional, ai_disclosure_present, disclaimer_present_correct,
provenance_present, trade_recs_quantified, clean_start, orchestrator_length.
Tier-2: no_hallucinated_data, macro_specific, health_status_consistent,
trade_recs_cite_findings, before_after_consistent.
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

# Unconditional sections in the PINNED state (no view, no white-label). Macro Context is
# governed by the generic macro_conditional (coverage-gated), NOT hard-required. Health
# Flags (flag-gated), Replacement Candidates (trim-gated), Ground-truth Integrity
# (mismatch-gated) are conditional -> in section_labels only.
# "Before/After" (not "Before/After Comparison"): the skill renders the header as
# "Before/After Comparison" OR "Before / After" — the 2-token prefix matches both
# (token-prefix matching; "Comparison" is an optional trailing word that drifts 2/6).
_REQUIRED_SECTIONS = [
    "Current Portfolio Assessment",
    "Health Status",
    "Score Momentum",
    "Trade Recommendations",
    "Before/After",
    "Implementation Notes",
    "About This Report",
]
_SECTION_LABELS = [
    "House View Preamble",
    "Branding Header",
    "Current Portfolio Assessment",
    "Health Status",
    "Health Flags",
    "Macro Context",
    "Score Momentum",
    "Ground-truth Integrity",
    "Trade Recommendations",
    "Replacement Candidates",
    "Before/After",
    "Implementation Notes",
    "About This Report",
]

_PRIORITY = re.compile(r"\b(high|medium|low)\b", re.I)
_ACTION = re.compile(
    r"\b(trim|exit|hold|reweight|investigate|monitor|buy|sell|reduce|add)\b", re.I
)
_PCT = re.compile(r"\d+(?:\.\d+)?\s*%")


def _c_trade_recs_quantified(t, spec) -> Check:
    """Checks that Trade Recommendations is present and contains a priority label
    (High/Medium/Low), an action verb (Trim/Exit/Hold/Reweight/Buy/Sell/...), and at
    least one quantified weight (%). A vague or label-less suggestion block fails."""
    sec = _section_text(t.final_prose, "Trade Recommendations", spec.section_labels)
    if not sec:
        return Check("trade_recs_quantified", False, "Trade Recommendations absent")
    has_p, has_a, has_w = (
        bool(_PRIORITY.search(sec)),
        bool(_ACTION.search(sec)),
        bool(_PCT.search(sec)),
    )
    return Check(
        "trade_recs_quantified",
        has_p and has_a and has_w,
        f"priority={has_p} action={has_a} weight_pct={has_w}",
    )


# Scaffold tokens that must NOT open the response; headers/titles that legitimately may.
_LEAK_START = re.compile(
    r"(?i)^\s*(?:\*\*)?(step\b|batch\b|all data\b|quick comp|cross-valid|"
    r"verified-holdings|white-?label\b|branding state|config_not_found|composing\b|"
    r"no active (house )?view|audit log|pre-?flight|drift check|build_stock_universe|"
    r"replacement (candidate|pool)|get_(news|assessment|telemetry|peer|score|company)|"
    r"analyze_portfolio|tool (search|loading)|holdings? (loaded|parsed|scored))"
)
_OK_START = re.compile(
    r"(?i)^\s*(?:#{1,4}\s*.*\b|\*\*\s*)"
    r"(portfolio rebalance|rebalance|current portfolio (assessment)?)\b"
)
_HR_OR_BLANK = re.compile(r"^[-*_ ]{0,}$|^[-*_ ]{3,}$")


def _c_clean_start(t, spec) -> Check:
    """Checks that the output begins with the rendered report title or the Current Portfolio
    Assessment section, not with internal scaffold (step/batch announcements, tool/probe
    status, config-probes, audit-log). Leading blank/horizontal-rule lines are skipped.
    """
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
_MACRO_SPECIFIC = next(
    c for c in CRITERIA if c["id"] == "macro_specific"
)  # COPIED (canonical Macro Context)

SPEC = EvalSpec(
    name="rebalance",
    command="/parallax-rebalance",
    rollout_prefix="rebalance",
    skill_md_path=_REPO_ROOT / "skills" / "parallax-rebalance" / "SKILL.md",
    required_sections=_REQUIRED_SECTIONS,
    section_labels=_SECTION_LABELS,
    check_ids=[
        "sections_present",  # COPIED
        "macro_conditional",  # COPIED
        "ai_disclosure_present",  # COPIED (§9.2)
        "disclaimer_present_correct",  # COPIED (§9.1)
        "provenance_present",  # COPIED
        "trade_recs_quantified",  # NEW
        "clean_start",  # NEW
        "orchestrator_length",  # COPIED
    ],
    extra_checks={
        "trade_recs_quantified": _c_trade_recs_quantified,
        "clean_start": _c_clean_start,
    },
    tier2_criteria=[
        _NO_HALLUC,  # COPIED (generic)
        _MACRO_SPECIFIC,  # COPIED (generic)
        {
            "id": "health_status_consistent",  # COPIED
            "statement": "The Health Status badge (Healthy/Monitor/Attention) is consistent with the number and severity of flags in the Health Flags table.",
            "pass_when": "More/severe flags -> Monitor/Attention; no/minor flags -> Healthy. Badge and flags agree.",
        },
        {
            "id": "trade_recs_cite_findings",  # ADAPTED
            "statement": "Every row in Trade Recommendations cites a SPECIFIC trigger — a named health flag, score, concentration figure, or stated constraint — not generic advice.",
            "pass_when": "Each trade names its concrete driver (e.g. 'Trim AAPL 40%->25% — Concentration flag', 'Exit XOM — no-energy constraint'); no boilerplate like 'rebalance for diversification'.",
        },
        {
            "id": "before_after_consistent",
            "statement": "The Before/After Comparison reflects the proposed trades — the 'after' allocation/scores are the logical result of applying the Trade Recommendations to the current book.",
            "pass_when": "Trimmed names have lower 'after' weight, added/replacement names appear, and any claimed factor-score improvement is directionally consistent with the trades shown.",
        },
    ],
    tasks_path="evals/tasks/rebalance/core.jsonl",
    orchestrator_max_lines=250,
)
