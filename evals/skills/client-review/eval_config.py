"""Eval spec for /parallax-client-review.

client-review is adviser-facing and emits directive recommendations
(Trim/Exit/Hold/Investigate/Reweight, prioritized High/Medium/Low). Macro is folded
inside Factor Analysis rather than rendered as a standalone section, so it uses a
skill-specific check (macro_in_factor_analysis) instead of the generic macro_conditional.

Checks: sections_present, macro_in_factor_analysis, ai_disclosure_present,
disclaimer_present_correct, provenance_present, recommendations_actionable,
clean_start, orchestrator_length.
Tier-2: no_hallucinated_data, health_status_consistent, recommendations_cite_findings,
suitability_tailored_to_client.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "graders"))
from eval_spec import EvalSpec  # noqa: E402
from tier1_structural import Check, _section_text, _section_present  # noqa: E402
from judge_criteria import CRITERIA  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Unconditional sections in the PINNED eval state (no active house view, no
# white-label client). Conditional sections (House View Preamble, Branding Header,
# Ground-truth Integrity, House View Alignment) are intentionally NOT required.
_REQUIRED_SECTIONS = [
    "Portfolio Summary", "Health Status", "Factor Analysis",
    "Concentration & Redundancy", "Per-Holding Analysis",
    "Suitability Assessment", "Recommended Actions", "Provenance",
]
_SECTION_LABELS = [
    "House View Preamble", "Branding Header", "Ground-truth Integrity",
    "Portfolio Summary", "Health Status", "Performance vs Benchmark",
    "Factor Analysis", "Concentration & Redundancy", "House View Alignment",
    "Per-Holding Analysis", "Suitability Assessment", "Recommended Actions",
    "Appendix: Methodology", "Provenance",
]

# Directive recommendation vocabulary (references/recommendation-matrix.md).
_PRIORITY = re.compile(r"\b(high|medium|low)\b", re.I)
_ACTION = re.compile(r"\b(trim|exit|hold|investigate|reweight|monitor|reduce)\b", re.I)
# Macro / regime terms that should surface in Factor Analysis when macro ran.
_MACRO_TERMS = re.compile(
    r"\b(macro|regime|tactical|stagflation|inflation|rate cut|rate hike|"
    r"cpi|fomc|outlook|tilt|overweight|underweight)\b", re.I,
)


def _c_macro_in_factor_analysis(t, spec) -> Check:
    """Checks that Factor Analysis contains macro/regime terms when macro_analyst was called.
    Passes vacuously if macro_analyst was not called."""
    called = t.called("macro_analyst")
    if not called:
        return Check("macro_in_factor_analysis", True, "macro_analyst not called (vacuous)")
    fa = _section_text(t.final_prose, "Factor Analysis", spec.section_labels)
    ok = _MACRO_TERMS.search(fa) is not None
    return Check("macro_in_factor_analysis", ok, f"macro_called=True macro_in_FA={ok}")


def _c_recommendations_actionable(t, spec) -> Check:
    """Checks that Recommended Actions contains at least one priority label (High/Medium/Low)
    and at least one action verb (Trim/Exit/Hold/Investigate/Reweight/Monitor)."""
    text = _section_text(t.final_prose, "Recommended Actions", spec.section_labels)
    if not text:
        return Check("recommendations_actionable", False, "Recommended Actions absent")
    ok = bool(_PRIORITY.search(text) and _ACTION.search(text))
    return Check(
        "recommendations_actionable", ok,
        f"priority={bool(_PRIORITY.search(text))} action={bool(_ACTION.search(text))}",
    )


# Scaffold tokens that must NOT open the response; headers that legitimately may.
# Pinned state = no view, no white-label, so the report opens with the title or the
# first rendered section (Portfolio Summary).
_LEAK_START = re.compile(
    r"(?i)^\s*(?:\*\*)?(step\b|batch\b|all data\b|quick comp|cross-valid|"
    r"verified-holdings|white-?label\b|config_not_found|composing\b|drill-?down\b|"
    r"holdings? (loaded|parsed)|tool (search|loading))"
)
# Require a heading marker (#) OR bold (**) before the keyword: a clean report opens
# with a '# Title' or '## Section' (or bold-only) header, never bare prose. This blocks
# the false-pass where scaffold narration begins with a section keyword, e.g.
# "client portfolio review loading holdings..." (no marker).
_OK_START = re.compile(
    r"(?i)^\s*(?:#{1,4}\s*.*\b|\*\*\s*)"
    r"(client portfolio review|portfolio review|portfolio summary)\b"
)
_HR_OR_BLANK = re.compile(r"^[-*_ ]{0,}$|^[-*_ ]{3,}$")


def _c_clean_start(t, spec) -> Check:
    """Checks that the output begins with the rendered report title or the Portfolio Summary
    section, not with internal scaffold (step/batch announcements, config-probe results).
    Leading blank/horizontal-rule lines are skipped."""
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
    return Check("clean_start", ok, f"first_line={first.strip()[:70]!r}")


_NO_HALLUC = next(c for c in CRITERIA if c["id"] == "no_hallucinated_data")  # COPIED

SPEC = EvalSpec(
    name="client-review",
    command="/parallax-client-review",
    rollout_prefix="client-review",
    skill_md_path=_REPO_ROOT / "skills" / "parallax-client-review" / "SKILL.md",
    required_sections=_REQUIRED_SECTIONS,
    section_labels=_SECTION_LABELS,
    check_ids=[
        "sections_present",             # COPIED
        "macro_in_factor_analysis",     # ADAPTED (from macro_conditional)
        "ai_disclosure_present",        # COPIED (§9.2 "AI-assisted output")
        "disclaimer_present_correct",   # COPIED (§9.1 "not investment advice")
        "provenance_present",           # COPIED
        "recommendations_actionable",   # NEW
        "clean_start",                  # NEW
        "orchestrator_length",          # COPIED
    ],
    extra_checks={
        "macro_in_factor_analysis": _c_macro_in_factor_analysis,
        "recommendations_actionable": _c_recommendations_actionable,
        "clean_start": _c_clean_start,
    },
    tier2_criteria=[
        _NO_HALLUC,  # COPIED (generic)
        {
            "id": "health_status_consistent",  # COPIED
            "statement": "The Health Status badge (Healthy/Monitor/Attention) is consistent with the number and severity of health flags surfaced in Concentration & Redundancy and Per-Holding Analysis.",
            "pass_when": "More/severe flags -> Monitor/Attention; no/minor flags -> Healthy. Badge and flags agree.",
        },
        {
            "id": "recommendations_cite_findings",
            "statement": "Every entry in Recommended Actions cites a SPECIFIC finding (a named health flag, factor score, concentration figure, redundant pair, or macro misalignment) — not generic advice.",
            "pass_when": "Each recommendation names the concrete trigger (e.g. 'Trim NVDA — 15% weight + Low Score 4.2'); no entry reads as boilerplate like 'consider diversifying' (the matrix explicitly forbids this).",
        },
        {
            "id": "suitability_tailored_to_client",
            "statement": "The Suitability Assessment is tailored to the stated client context (risk tolerance, income vs growth focus, horizon), not a generic portfolio comment.",
            "pass_when": "It explicitly reconciles the holdings against the client's stated mandate (e.g. flags an aggressive tech book as misaligned with a 'conservative income' retiree); a generic 'well-diversified portfolio' note with no reference to the client profile FAILS.",
        },
    ],
    tasks_path="evals/tasks/client-review/core.jsonl",
    orchestrator_max_lines=250,
)
