"""Eval spec for /parallax-watchlist-monitor.

watchlist-monitor is a pure score-surveillance scan over a ticker list (not weighted
holdings). It has no macro integration (macro_conditional is dropped) and no health-flag
badge structure. The core surveillance deliverable is the Watchlist Summary/Scan table
with numeric score data.

Checks: sections_present, ai_disclosure_present, disclaimer_present_correct,
provenance_present, score_changes_quantified, clean_start, orchestrator_length.
Tier-2: no_hallucinated_data, score_change_consistent, alerts_ranked_by_magnitude,
actions_target_movers.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "graders"))
from eval_spec import EvalSpec  # noqa: E402
from tier1_structural import Check, _section_text  # noqa: E402
from judge_criteria import CRITERIA  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Unconditional sections in the PINNED state (no white-label; no view by design). Stable
# Names is conditional (only if some names are unchanged) -> section_labels only. Alerts is
# required: the surveillance deliverable renders the section header even when empty.
# The summary table is NOT in required_sections because the skill heads it "Watchlist
# Summary" OR "Watchlist Scan" (a synonym it uses in its own body/branding) — drifts ~2/6.
# Its presence + numeric content is enforced more strongly by score_changes_quantified,
# which accepts either header.
_REQUIRED_SECTIONS = [
    "Alerts", "Recommended Actions", "Provenance",
]
_SECTION_LABELS = [
    "Branding Header", "Watchlist Summary", "Watchlist Scan", "Alerts",
    "Stable Names", "Recommended Actions", "Provenance",
]

# A decimal score (7.2) or a signed change (+1.3 / -0.8) — a quantified summary/alert.
_SCORE_NUM = re.compile(r"[-+]?\d+\.\d+|[+\-]\s?\d+")


def _c_score_changes_quantified(t, spec) -> Check:
    """Checks that the Watchlist Summary or Watchlist Scan table is present and contains
    numeric score data (decimal scores or signed score changes). A purely qualitative
    summary with no numbers fails. Accepts either header variant."""
    sec = (_section_text(t.final_prose, "Watchlist Summary", spec.section_labels)
           or _section_text(t.final_prose, "Watchlist Scan", spec.section_labels))
    ok = bool(sec) and _SCORE_NUM.search(sec) is not None
    return Check("score_changes_quantified", ok, f"summary_present={bool(sec)} numeric={bool(_SCORE_NUM.search(sec))}")


# Scaffold tokens that must NOT open the response; titles/headers that legitimately may.
_LEAK_START = re.compile(
    r"(?i)^\s*(?:\*\*)?(step\b|score scan|flag movers|news check|technical check|"
    r"analyst check|all data\b|scanning\b|white-?label\b|branding state|config_not_found|"
    r"composing\b|get_(score|news|technical|stock)|tool (search|loading)|"
    r"symbols? (loaded|parsed|scanned))"
)
_OK_START = re.compile(
    r"(?i)^\s*(?:#{1,4}\s*.*\b|\*\*\s*)"
    r"(watchlist (monitor|summary|scan))\b"
)
_HR_OR_BLANK = re.compile(r"^[-*_ ]{0,}$|^[-*_ ]{3,}$")


def _c_clean_start(t, spec) -> Check:
    """Checks that the output begins with the rendered report title or the Watchlist Summary
    section, not with internal scaffold (step narration, white-label config-probes, tool
    status). Leading blank/horizontal-rule lines are skipped."""
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
    name="watchlist-monitor",
    command="/parallax-watchlist-monitor",
    rollout_prefix="watchlist-monitor",
    skill_md_path=_REPO_ROOT / "skills" / "parallax-watchlist-monitor" / "SKILL.md",
    required_sections=_REQUIRED_SECTIONS,
    section_labels=_SECTION_LABELS,
    check_ids=[
        "sections_present",             # COPIED
        "ai_disclosure_present",        # COPIED (§9.2)
        "disclaimer_present_correct",   # COPIED (§9.1)
        "provenance_present",           # COPIED
        "score_changes_quantified",     # NEW
        "clean_start",                  # NEW
        "orchestrator_length",          # COPIED
        # macro_conditional DROPPED: this skill has no macro tool or macro section.
    ],
    extra_checks={
        "score_changes_quantified": _c_score_changes_quantified,
        "clean_start": _c_clean_start,
    },
    tier2_criteria=[
        _NO_HALLUC,  # COPIED (generic)
        {
            "id": "score_change_consistent",  # ADAPTED
            "statement": "The score-change descriptions in Alerts are consistent with the Watchlist Summary table values.",
            "pass_when": "A name flagged as a big mover in Alerts shows a correspondingly large score change in the summary table; directions (up/down) agree.",
        },
        {
            "id": "alerts_ranked_by_magnitude",
            "statement": "Alerts are ordered by magnitude of change, largest first (the skill's stated ranking contract).",
            "pass_when": "The first alert has the largest absolute score change among alerted names; ordering is monotonic non-increasing in |change|.",
        },
        {
            "id": "actions_target_movers",
            "statement": "Recommended Actions point to the names actually flagged as movers, not arbitrary or unchanged names.",
            "pass_when": "Each name suggested for a deeper look appears among the alerted movers; stable names are not recommended for action.",
        },
    ],
    tasks_path="evals/tasks/watchlist-monitor/core.jsonl",
    orchestrator_max_lines=250,
)
