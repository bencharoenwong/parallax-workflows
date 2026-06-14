"""Unit tests for the portfolio-builder eval spec's NEW checks (clean_start,
holdings_allocated) and the dropped macro_conditional. Red/green before live spend.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eval_spec import load_spec  # noqa: E402
from tier1_structural import grade_tier1  # noqa: E402
from transcript import Transcript  # noqa: E402

SPEC = load_spec("portfolio-builder")


def _results(prose: str) -> dict:
    t = Transcript(final_prose=prose, tool_calls=[])  # no macro in default path
    return {c.name: c.passed for c in grade_tier1(t, SPEC)}


GOLDEN = """# Portfolio Builder

## Investment Thesis
US tech with strong quality and momentum — refined to mega/large-cap software & semis.

## Universe Built
42 candidates across software, semis, internet; re-ranked by factor scores.

## Selected Holdings
| Ticker | Name | Sector | Total Score | Weight | Strengths |
|---|---|---|---|---|---|
| MSFT.O | Microsoft | Software | 7.8 | 22% | Quality 8.1, Momentum 7.4 |
| NVDA.O | NVIDIA | Semis | 7.5 | 20% | Momentum 8.0 |
| AAPL.O | Apple | Hardware | 7.1 | 18% | Quality 7.6 |

## Portfolio Factor Profile
QUALITY 7.6, MOMENTUM 7.3, VALUE 4.1, DEFENSIVE 5.0 — quality/momentum tilted, as intended.

## Redundancy Notes
Mild software overlap MSFT/CRM; trimmed CRM.

## Implementation Notes
Equal-ish weighting; rebalance quarterly; mind semis liquidity.

## Provenance
Default Parallax branding.

*AI-assisted output. Verify any specific statement before acting.*

> *This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals.*
"""


def test_golden_passes_every_check():
    res = _results(GOLDEN)
    assert all(res.values()), [n for n, p in res.items() if not p]


def test_macro_conditional_not_in_spec():
    assert "macro_conditional" not in SPEC.check_ids


# --- clean_start --------------------------------------------


def test_clean_start_red_on_phase_step_leak():
    leaked = (
        "Phase A complete — universe built (42 candidates), scoring done. Selecting.\n\n"
        + GOLDEN
    )
    assert _results(leaked)["clean_start"] is False


def test_clean_start_red_on_view_probe_leak():
    leaked = (
        "No active house view, white-label inactive → default Parallax.\n\n" + GOLDEN
    )
    assert _results(leaked)["clean_start"] is False


def test_clean_start_green_on_title_and_leading_rule():
    assert _results("---\n\n" + GOLDEN)["clean_start"] is True


def test_clean_start_green_on_investment_thesis_open():
    body = GOLDEN.split("\n", 2)[2]  # drop the title
    assert _results(body)["clean_start"] is True


# --- holdings_allocated (NEW) ----------------------------------------------


def test_holdings_allocated_red_without_weights():
    no_w = GOLDEN.replace(
        "| MSFT.O | Microsoft | Software | 7.8 | 22% | Quality 8.1, Momentum 7.4 |\n"
        "| NVDA.O | NVIDIA | Semis | 7.5 | 20% | Momentum 8.0 |\n"
        "| AAPL.O | Apple | Hardware | 7.1 | 18% | Quality 7.6 |",
        "We would pick a mix of large-cap software and semiconductor names.",
    )
    assert _results(no_w)["holdings_allocated"] is False


def test_holdings_allocated_red_when_section_absent_empty_universe():
    # Empty-universe degradation: no Selected Holdings table.
    no_sec = GOLDEN.replace("## Selected Holdings", "## (universe unavailable)")
    assert _results(no_sec)["holdings_allocated"] is False
