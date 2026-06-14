"""Eval spec for /parallax-morning-brief.

morning-brief is fund-manager-facing. Macro is unconditional (Market Regime & Signals +
Macro Snapshot, macro_analyst always called in Batch A), so it uses macro_snapshot_grounded
instead of the generic macro_conditional. It carries an explicit 800-word cap yielding a
skill-specific word_limit check.

Checks: sections_present, macro_snapshot_grounded, ai_disclosure_present,
disclaimer_present_correct, provenance_present, word_limit, clean_start, orchestrator_length.
Tier-2: no_hallucinated_data, regime_macro_specific, factor_tilt_interpretation_consistent,
action_items_grounded.
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

# Unconditional sections in the PINNED state (no view, no white-label). "Market
# Regime" is the token-prefix of "Market Regime & Signals" (tolerates the "& Signals"
# label drift). Holding News + Redundancy & Alignment Alerts are NOT required: news is
# async ("don't block output") and alerts are flagged-only — requiring either invites a
# false-fail (see client-review's get_assessment async-timeout lesson).
_REQUIRED_SECTIONS = [
    "Market Regime", "Macro Snapshot", "Portfolio Factor Tilt",
    "Action Items", "Provenance",
]
_SECTION_LABELS = [
    "House View Preamble", "Branding Header", "Market Regime & Signals",
    "Macro Snapshot", "Ground-truth Integrity", "Portfolio Factor Tilt",
    "Redundancy & Alignment Alerts", "Holding News", "Action Items", "Provenance",
]

_MACRO_TERMS = re.compile(
    r"\b(macro|regime|tactical|stagflation|inflation|rate cut|rate hike|"
    r"cpi|ppi|fomc|outlook|tilt|overweight|underweight|growth|recession)\b", re.I,
)


def _c_macro_snapshot_grounded(t, spec) -> Check:
    """Checks that the Macro Snapshot section is present and contains macro terms when
    macro_analyst was called. Passes vacuously if macro_analyst was not called."""
    if not t.called("macro_analyst"):
        return Check("macro_snapshot_grounded", True, "macro_analyst not called (vacuous)")
    snap = _section_text(t.final_prose, "Macro Snapshot", spec.section_labels)
    # Exclude the header line — "Macro Snapshot" itself contains "macro", which would
    # satisfy the term search on an empty section and defeat the grounded-ness check.
    body = "\n".join(snap.splitlines()[1:]) if snap else ""
    ok = bool(body.strip()) and _MACRO_TERMS.search(body) is not None
    return Check("macro_snapshot_grounded", ok, f"snapshot_present={bool(snap)} body_terms={bool(_MACRO_TERMS.search(body))}")


def _c_word_limit(t, spec) -> Check:
    """Checks that the brief body (excluding §9.1/§9.2 boilerplate) is at most 880 words
    (800-word cap plus ~10% tolerance for headers/table cells)."""
    prose = t.final_prose
    marks = [m.start() for m in re.finditer(
        r"(?i)AI-assisted output|AI-interaction disclosure|not investment advice", prose)]
    body = prose[:min(marks)] if marks else prose
    n = len(body.split())
    return Check("word_limit", n <= 880, f"brief_words={n} (cap 800, gate <=880)")


# Scaffold tokens that must NOT open the response; headers that legitimately may.
# Pinned state = no view, no white-label, so the brief opens with the title or the
# first rendered section (Market Regime).
_LEAK_START = re.compile(
    r"(?i)^\s*(?:\*\*)?(step\b|batch\b|all data\b|quick comp|cross-valid|"
    r"verified-holdings|white-?label\b|branding state|config_not_found|composing\b|"
    r"no active (house )?view|audit log|get_(news|assessment|telemetry)|"
    r"tool (search|loading)|holdings? (loaded|parsed|scored))"
)
# The skill titles the brief "Morning Brief" OR "Fund Manager Morning Brief" (it
# expands per the description) — both are clean. A leading horizontal rule (---/***)
# is a harmless separator, not a leak.
# Require a heading marker (#) OR bold (**) before the keyword (blocks bare-prose
# scaffold that opens with a section keyword, e.g. "market regime data loading...").
_OK_START = re.compile(
    r"(?i)^\s*(?:#{1,4}\s*.*\b|\*\*\s*)"
    r"((fund manager )?morning brief|market regime|house view)\b"
)
_HR_OR_BLANK = re.compile(r"^[-*_ ]{0,}$|^[-*_ ]{3,}$")


def _c_clean_start(t, spec) -> Check:
    """Checks that the brief begins with the rendered report title or the Market Regime
    section, not with internal scaffold (step/batch announcements, config-probe results,
    audit-log narration). Leading blank/horizontal-rule lines are skipped."""
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
    name="morning-brief",
    command="/parallax-morning-brief",
    rollout_prefix="morning-brief",
    skill_md_path=_REPO_ROOT / "skills" / "parallax-morning-brief" / "SKILL.md",
    required_sections=_REQUIRED_SECTIONS,
    section_labels=_SECTION_LABELS,
    check_ids=[
        "sections_present",             # COPIED
        "macro_snapshot_grounded",      # ADAPTED
        "ai_disclosure_present",        # COPIED (§9.2)
        "disclaimer_present_correct",   # COPIED (§9.1)
        "provenance_present",           # COPIED
        "word_limit",                   # NEW
        "clean_start",                  # NEW
        "orchestrator_length",          # COPIED
    ],
    extra_checks={
        "macro_snapshot_grounded": _c_macro_snapshot_grounded,
        "word_limit": _c_word_limit,
        "clean_start": _c_clean_start,
    },
    tier2_criteria=[
        _NO_HALLUC,  # COPIED (generic)
        {
            "id": "regime_macro_specific",  # ADAPTED
            "statement": "The Market Regime & Macro Snapshot sections are specific to the actual market(s) in the portfolio, not generic boilerplate.",
            "pass_when": "They reference the real regime tag / macro figures for the relevant market (e.g. US tactical stance, named CPI/rate signals), not 'markets are uncertain' filler.",
        },
        {
            "id": "factor_tilt_interpretation_consistent",  # ADAPTED
            "statement": "Any plain-English reading of the Portfolio Factor Tilt is consistent with the VALUE/QUALITY/MOMENTUM/DEFENSIVE values in the tilt table.",
            "pass_when": "The narrative direction (high/low tilt) matches the table numbers; e.g. a tech-heavy book described as momentum-tilted shows a high MOMENTUM score.",
        },
        {
            "id": "action_items_grounded",
            "statement": "Action Items name SPECIFIC holdings, flags, or regime/macro signals — not generic advice.",
            "pass_when": "Each item points to a concrete trigger ('NVDA 15% weight + concentration', 'energy overweight into negative tactical outlook'); a generic 'monitor your portfolio' item FAILS.",
        },
    ],
    tasks_path="evals/tasks/morning-brief/core.jsonl",
    orchestrator_max_lines=250,
)
