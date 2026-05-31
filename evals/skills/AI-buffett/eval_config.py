"""Eval spec for /parallax-ai-buffett.

Reuse tally vs should-i-buy (the templatability measurement):
  Tier-1: sections_present, orchestrator_length = GENERIC (copied mechanism;
          required_sections is per-skill config). verdict_present, citation_present,
          no_impersonation, disclaimer_verbatim = NEW (the output contract differs:
          plain-line labels not headings; "not financial advice" not "not investment
          advice"; "AI-inferred" not "AI-assisted"; arrow trends not "X to Y").
  Tier-2: no_hallucinated_data = COPIED from should-i-buy; verdict_consistent_with_table,
          citation_grounded, no_impersonation_judge = NEW.
Finding: even the nearest-neighbour skill reuses only 2/6 tier-1 checks and 1/4
tier-2 criteria directly — the engine generalizes, the criteria mostly do not.
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


_NO_HALLUC = next(c for c in CRITERIA if c["id"] == "no_hallucinated_data")  # COPIED

SPEC = EvalSpec(
    name="AI-buffett",
    command="/parallax-ai-buffett",
    rollout_prefix="ai-buffett",
    skill_md_path=_REPO_ROOT / "skills" / "AI-buffett" / "SKILL.md",
    required_sections=_REQUIRED_SECTIONS,
    section_labels=_SECTION_LABELS,
    check_ids=[
        "sections_present",          # GENERIC (mechanism reused)
        "verdict_present",           # NEW
        "citation_present",          # NEW
        "no_impersonation",          # NEW
        "disclaimer_verbatim",       # NEW
        "orchestrator_length",       # GENERIC
    ],
    extra_checks={
        "verdict_present": _c_verdict_present,
        "citation_present": _c_citation_present,
        "no_impersonation": _c_no_impersonation,
        "disclaimer_verbatim": _c_disclaimer_verbatim,
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
