"""Eval spec for /parallax-ai-buffett.

AI-buffett's output contract differs from should-i-buy (plain-line labels not
headings; "not financial advice"; "AI-inferred"; arrow trends), so it declares
its own required sections and adds skill-specific checks: verdict_present,
citation_present, no_impersonation, disclaimer_verbatim (Tier-1) and
verdict_consistent_with_table, citation_grounded, no_impersonation_judge (Tier-2).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "graders"))
from eval_spec import EvalSpec  # noqa: E402
from tier1_structural import Check, _section_present  # noqa: E402
from judge_criteria import CRITERIA  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Plain-line label anchors the AI-profile template always emits (output-template.md).
_REQUIRED_SECTIONS = ["Source", "Profile fit", "Tool sequence"]
_SECTION_LABELS = [
    "Buffett style profile applied", "Source", "Profile fit",
    "Workflow derived from", "Tool sequence", "Token cost",
]

_VERDICT_RE = re.compile(
    r"profile fit:\s*(match|partial match|no match)\b.*?\b\d+\s+of\s+\d+", re.I | re.S
)
_IMPERSONATION_RE = [
    r"\bI would (buy|sell|hold)\b", r"\bBuffett would (buy|sell)\b",
    r"\bwe recommend\b", r"\b(buy|sell) recommendation\b", r"\bI (like|love|hate)\b",
    r"\brating:\s*(buy|sell)\b",
]


def _c_verdict_present(t, spec) -> Check:
    ok = _VERDICT_RE.search(t.final_prose) is not None
    return Check("verdict_present", ok, "Profile fit verdict line (match/partial/no — N of M)")


def _c_citation_present(t, spec) -> Check:
    p = t.final_prose
    has_source = _section_present(p, "Source")
    has_cite = bool(re.search(r"frazzini.*?2018|doi\.org|faj", p, re.I))
    return Check("citation_present", has_source and has_cite, "Source + BKP-2018/DOI citation")


def _c_no_impersonation(t, spec) -> Check:
    hit = next((pat for pat in _IMPERSONATION_RE if re.search(pat, t.final_prose, re.I)), None)
    return Check("no_impersonation", hit is None, f"impersonation/rec token={hit}")


def _c_disclaimer_verbatim(t, spec) -> Check:
    low = t.final_prose.lower()
    needed = ["not financial advice", "ai-inferred", "consult a qualified"]
    missing = [s for s in needed if s not in low]
    return Check("disclaimer_verbatim", not missing, f"missing load-bearing phrases={missing}")


def _c_clean_start(t, spec) -> Check:
    """CONFORMANCE (was missing): Step 7 forbids commentary, yet 5/6 baseline
    outputs leaked internal scratch ('Step 5 — Verdict:', 'Cross-validation
    passed…') before the Header. The output must begin with the Header line."""
    ok = t.final_prose.lstrip().startswith("Buffett-style profile applied")
    first = t.final_prose.lstrip().split("\n", 1)[0][:50]
    return Check("clean_start", ok, f"first_line={first!r}")


def _c_synthesis_present(t, spec) -> Check:
    """RAISED BAR: a labeled interpretive synthesis must follow the verdict for
    EVERY result (the edited skill mandates a '**Synthesis:**' block; the old
    skill gave NVDA an inline paragraph and KO nothing). Structural label check —
    not a keyword list (the first cut over-fit to NVDA's 'matches/fails' phrasing
    and false-failed KO's valid 'fits/embodies' synthesis)."""
    ok = _section_present(t.final_prose, "Synthesis")
    return Check("synthesis_present", ok, "labeled Synthesis block after verdict")


_NO_HALLUC = next(c for c in CRITERIA if c["id"] == "no_hallucinated_data")  # COPIED

SPEC = EvalSpec(
    name="AI-buffett",
    command="/parallax-ai-buffett",
    rollout_prefix="ai-buffett",
    skill_md_path=_REPO_ROOT / "skills" / "parallax-ai-buffett" / "SKILL.md",
    required_sections=_REQUIRED_SECTIONS,
    section_labels=_SECTION_LABELS,
    check_ids=[
        "sections_present",          # GENERIC (mechanism reused)
        "verdict_present",           # NEW
        "citation_present",          # NEW
        "no_impersonation",          # NEW
        "disclaimer_verbatim",       # NEW
        "clean_start",               # NEW conformance (rubric was missing it — caught 5/6 leak)
        "synthesis_present",         # NEW raised-bar (synthesis required on every verdict)
        "orchestrator_length",       # GENERIC
    ],
    extra_checks={
        "verdict_present": _c_verdict_present,
        "citation_present": _c_citation_present,
        "no_impersonation": _c_no_impersonation,
        "disclaimer_verbatim": _c_disclaimer_verbatim,
        "clean_start": _c_clean_start,
        "synthesis_present": _c_synthesis_present,
    },
    tier2_criteria=[
        _NO_HALLUC,  # COPIED
        {
            "id": "verdict_consistent_with_table",
            "statement": "The 'Profile fit' verdict (match/partial/no, N of M) is consistent with the YES/NO Match entries in the factor table.",
            "pass_when": "The count and verdict label match the table's per-factor Match column.",
        },
        {
            "id": "citation_grounded",
            "statement": "The characterization sentence reflects the cited BKP 2018 source (factor decomposition of Berkshire), not invented claims.",
            "pass_when": "It describes Quality/Value/Momentum/Defensive factor exposures from the academic source; no fabricated specifics.",
        },
        {
            "id": "no_impersonation_judge",
            "statement": "The output frames as a 'Buffett-style'/academic factor profile and never impersonates Buffett or issues a buy/sell call.",
            "pass_when": "Third-person/profile framing throughout; no first-person Buffett voice, no recommendation.",
        },
    ],
    tasks_path="evals/tasks/AI-buffett/core.jsonl",
    orchestrator_max_lines=250,
)
