"""Unit tests for the explain-portfolio eval spec's NEW/ADAPTED extra checks
(clean_start, return_quantified, divergence_verdict, regime_context_grounded).
Red/green before any live spend. Mirrors the other per-skill test files.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eval_spec import load_spec  # noqa: E402
from tier1_structural import grade_tier1  # noqa: E402
from transcript import ToolCall, Transcript  # noqa: E402

SPEC = load_spec("explain-portfolio")
_REGIME = [
    ToolCall("mcp__claude_ai_Parallax__get_telemetry", {}),
    ToolCall("mcp__claude_ai_Parallax__macro_analyst", {}),
]


def _results(prose: str, calls=None) -> dict:
    t = Transcript(
        final_prose=prose, tool_calls=calls if calls is not None else _REGIME
    )
    return {c.name: c.passed for c in grade_tier1(t, SPEC)}


GOLDEN = """# Explain Portfolio — Drawdown Attribution

## What Happened
Your book is down 4.1% over the past month, close to your stated ~4%.

## Performance Attribution
| Holding | Return | Contribution | Driver |
|---|---|---|---|
| NVDA.O | -9% | -2.3% | Factor |
| AAPL.O | -3% | -0.9% | Market |

## Market & Regime Context
The tape is risk-off; a momentum-to-value rotation is underway per the regime tag.

## Factor Exposure
Heavy momentum tilt hurt as momentum de-rated across the book.

## Top Detractors
NVDA: down on factor rotation, not company news; scores steady.

## The Key Question: Noise or Signal?
Portfolio-level read: Transient. Prices fell but factor scores held — quality 7.1, defensive 5.0 unchanged.
| Holding | Price | Scores | Class |
|---|---|---|---|
| NVDA.O | Down | Stable | Transient |

## What To Do
Fundamentals are intact — stay the course unless your risk tolerance changed.

## Provenance
Default Parallax branding.

*AI-assisted output. Verify any specific statement before acting.*

> *This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals.*
"""


def test_golden_passes_every_check():
    res = _results(GOLDEN)
    assert all(res.values()), [n for n, p in res.items() if not p]


# --- clean_start --------------------------------------------


def test_clean_start_red_on_asset_class_preclassification_leak():
    leaked = (
        "Asset-class pre-classification: all 4 holdings are equities, routing to export_price_series.\n\n"
        + GOLDEN
    )
    assert _results(leaked)["clean_start"] is False


def test_clean_start_red_on_view_probe_leak():
    leaked = (
        "No active house view, white-label inactive. Computing attribution.\n\n"
        + GOLDEN
    )
    assert _results(leaked)["clean_start"] is False


def test_clean_start_green_on_title_and_leading_rule():
    assert _results("---\n\n" + GOLDEN)["clean_start"] is True


def test_clean_start_green_on_what_happened_open():
    body = GOLDEN.split("\n", 2)[2]  # drop the title
    assert _results(body)["clean_start"] is True


def test_clean_start_green_on_drawdown_attribution_title():
    # The skill's description names "drawdown attribution" as a synonym — a clean title.
    titled = GOLDEN.replace(
        "# Explain Portfolio — Drawdown Attribution",
        '# Drawdown Attribution — "Why am I down this quarter?"',
        1,
    )
    assert _results(titled)["clean_start"] is True


# --- return_quantified (NEW) -----------------------------------------------


def test_return_quantified_red_without_a_percentage():
    vague = GOLDEN.replace(
        "Your book is down 4.1% over the past month, close to your stated ~4%.",
        "Your book is down over the past month, broadly in line with what you mentioned.",
    )
    assert _results(vague)["return_quantified"] is False


# --- divergence_verdict (NEW; header self-match guard) ---------------------


def test_divergence_verdict_red_when_body_has_no_classification():
    # Header 'Noise or Signal?' must NOT self-satisfy — only the body counts.
    silent = GOLDEN.replace(
        "Portfolio-level read: Transient. Prices fell but factor scores held — quality 7.1, defensive 5.0 unchanged.\n"
        "| Holding | Price | Scores | Class |\n|---|---|---|---|\n| NVDA.O | Down | Stable | Transient |",
        "We looked at price and score moves across the book.",
    )
    assert _results(silent)["divergence_verdict"] is False


def test_divergence_verdict_green_on_body_classification():
    assert _results(GOLDEN)["divergence_verdict"] is True


# --- regime_context_grounded (ADAPTED from macro_conditional) --------------


def test_regime_red_when_tool_called_but_section_empty():
    silent = GOLDEN.replace(
        "The tape is risk-off; a momentum-to-value rotation is underway per the regime tag.",
        "Conditions were what they were.",
    )
    assert _results(silent)["regime_context_grounded"] is False


def test_regime_vacuous_pass_when_no_regime_tool():
    assert _results(GOLDEN, calls=[])["regime_context_grounded"] is True
