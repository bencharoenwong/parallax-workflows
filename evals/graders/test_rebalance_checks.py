"""Unit tests for the rebalance eval spec's NEW checks (clean_start,
trade_recs_quantified) and its VERBATIM-COPIED macro_conditional. Red/green before
any live spend. Mirrors the other per-skill test files.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eval_spec import load_spec  # noqa: E402
from tier1_structural import grade_tier1  # noqa: E402
from transcript import ToolCall, Transcript  # noqa: E402

SPEC = load_spec("rebalance")
_MACRO = [ToolCall("mcp__claude_ai_Parallax__macro_analyst", {})]


def _results(prose: str, calls=None) -> dict:
    t = Transcript(final_prose=prose, tool_calls=calls if calls is not None else _MACRO)
    return {c.name: c.passed for c in grade_tier1(t, SPEC)}


GOLDEN = """# Portfolio Rebalance

## Current Portfolio Assessment
Tech-concentrated; quality mixed.

## Health Status
🔴 **Attention** — 3 flags.

## Health Flags
| Holding | Flag | Priority |
|---|---|---|
| AAPL.O | Concentration | High |

## Macro Context
US tactical regime is risk-off; favors defensive sectors for the rebalance.

## Score Momentum
| Holding | Trend |
|---|---|
| NVDA.O | declining |

## Trade Recommendations
| Priority | Action | Symbol | Current | Target | Rationale |
|---|---|---|---|---|---|
| High | Trim | AAPL.O | 40% | 25% | Concentration flag (>15%) |
| Low | Hold | JNJ.N | 10% | 10% | Stable scores, no flags |

## Replacement Candidates
PG.N — quality 7.5, defensive.

## Before/After Comparison
Quality 6.2 → 7.0 after trims.

## Implementation Notes
Execute the AAPL trim first for liquidity.

## About This Report
Default Parallax branding.

*AI-assisted output. Verify any specific statement before acting.*

> *This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals.*
"""


def test_golden_passes_every_check():
    res = _results(GOLDEN)
    assert all(res.values()), [n for n, p in res.items() if not p]


def test_sections_present_tolerates_before_after_label_drift():
    # The skill renders "## Before / After" (spaces, no "Comparison") in some runs —
    # the 2-token "Before/After" required label must still match it.
    drifted = GOLDEN.replace("## Before/After Comparison", "## Before / After")
    assert _results(drifted)["sections_present"] is True


# --- clean_start --------------------------------------------


def test_clean_start_red_on_preflight_drift_leak():
    leaked = (
        "Pre-flight: house-view drift check — no active view, skipping.\n\n" + GOLDEN
    )
    assert _results(leaked)["clean_start"] is False


def test_clean_start_red_on_view_probe_leak():
    leaked = (
        "No active house view, white-label inactive. Building trade list.\n\n" + GOLDEN
    )
    assert _results(leaked)["clean_start"] is False


def test_clean_start_green_on_title_and_leading_rule():
    assert _results("---\n\n" + GOLDEN)["clean_start"] is True


def test_clean_start_green_on_current_assessment_open():
    body = GOLDEN.split("\n", 2)[2]  # drop the title
    assert _results(body)["clean_start"] is True


# --- trade_recs_quantified (NEW) -------------------------------------------


def test_trade_recs_red_when_vague_no_weights():
    vague = GOLDEN.replace(
        "| Priority | Action | Symbol | Current | Target | Rationale |\n"
        "|---|---|---|---|---|---|\n"
        "| High | Trim | AAPL.O | 40% | 25% | Concentration flag (>15%) |\n"
        "| Low | Hold | JNJ.N | 10% | 10% | Stable scores, no flags |",
        "Consider rebalancing toward a more diversified mix over time.",
    )
    assert _results(vague)["trade_recs_quantified"] is False


def test_trade_recs_red_when_section_absent():
    no_sec = GOLDEN.replace("## Trade Recommendations", "## Closing Thoughts")
    assert _results(no_sec)["trade_recs_quantified"] is False


# --- macro_conditional (COPIED verbatim — rebalance keeps "Macro Context") --


def test_macro_conditional_red_when_called_but_no_section():
    no_macro = GOLDEN.replace(
        "## Macro Context\nUS tactical regime is risk-off; favors defensive sectors for the rebalance.\n\n",
        "",
    )
    assert _results(no_macro)["macro_conditional"] is False


def test_macro_conditional_pass_when_not_called_and_absent():
    no_macro = GOLDEN.replace(
        "## Macro Context\nUS tactical regime is risk-off; favors defensive sectors for the rebalance.\n\n",
        "",
    )
    # macro_analyst NOT called AND no Macro Context section -> conditional holds (both False).
    assert _results(no_macro, calls=[])["macro_conditional"] is True
