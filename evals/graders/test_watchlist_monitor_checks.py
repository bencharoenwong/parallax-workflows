"""Unit tests for the watchlist-monitor eval spec's NEW checks (clean_start,
score_changes_quantified). Red/green before any live spend.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eval_spec import load_spec  # noqa: E402
from tier1_structural import grade_tier1  # noqa: E402
from transcript import Transcript  # noqa: E402

SPEC = load_spec("watchlist-monitor")


def _results(prose: str) -> dict:
    # This skill calls no macro tool; checks don't depend on tool_calls.
    t = Transcript(final_prose=prose, tool_calls=[])
    return {c.name: c.passed for c in grade_tier1(t, SPEC)}


GOLDEN = """# Watchlist Monitor

## Watchlist Summary
| Symbol | Total Score | Change | Alert |
|---|---|---|---|
| NVDA.O | 5.9 | -1.4 | ⚠ |
| AAPL.O | 7.2 | +0.2 | — |

## Alerts
- **NVDA.O** — total score -1.4 (momentum -2.3); catalyst: sector rotation out of AI.

## Stable Names
- AAPL.O — no material changes.

## Recommended Actions
- NVDA.O warrants a deeper look via /parallax-deep-dive.

## Provenance
Default Parallax branding.

*AI-assisted output. Verify any specific statement before acting.*

> *This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals.*
"""


def test_golden_passes_every_check():
    res = _results(GOLDEN)
    assert all(res.values()), [n for n, p in res.items() if not p]


def test_macro_conditional_not_in_spec():
    # watchlist-monitor drops macro_conditional entirely (no macro tool/section).
    assert "macro_conditional" not in SPEC.check_ids


def test_summary_table_under_watchlist_scan_label():
    # The skill heads the table "Watchlist Scan" in ~2/6 runs instead of "Watchlist
    # Summary" — both sections_present (summary not required) and score_changes_quantified
    # (accepts either header) must still pass.
    scan = GOLDEN.replace("## Watchlist Summary", "## Watchlist Scan — 7 names, 8-week window")
    res = _results(scan)
    assert res["score_changes_quantified"] is True, "Scan-headed table must be accepted"
    assert res["sections_present"] is True


# --- clean_start --------------------------------------------

def test_clean_start_red_on_score_scan_step_leak():
    leaked = "Score Scan: fetching get_score_analysis for 7 symbols in parallel...\n\n" + GOLDEN
    assert _results(leaked)["clean_start"] is False


def test_clean_start_red_on_white_label_probe_leak():
    leaked = "**Branding state:** config_not_found → default Parallax.\n\n" + GOLDEN
    assert _results(leaked)["clean_start"] is False


def test_clean_start_green_on_title_and_leading_rule():
    assert _results("---\n\n" + GOLDEN)["clean_start"] is True


def test_clean_start_green_on_summary_open():
    body = GOLDEN.split("\n", 2)[2]  # drop the title
    assert _results(body)["clean_start"] is True


# --- score_changes_quantified (NEW) ----------------------------------------

def test_score_changes_red_when_summary_has_no_numbers():
    qualitative = GOLDEN.replace(
        "| Symbol | Total Score | Change | Alert |\n"
        "|---|---|---|---|\n"
        "| NVDA.O | 5.9 | -1.4 | ⚠ |\n"
        "| AAPL.O | 7.2 | +0.2 | — |",
        "NVDA looks weaker lately; AAPL is roughly flat.",
    )
    assert _results(qualitative)["score_changes_quantified"] is False


def test_score_changes_red_when_summary_absent():
    no_sec = GOLDEN.replace("## Watchlist Summary", "## Overview")
    assert _results(no_sec)["score_changes_quantified"] is False
