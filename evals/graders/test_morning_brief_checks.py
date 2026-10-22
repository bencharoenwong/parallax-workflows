"""Unit tests for the morning-brief eval spec's NEW/ADAPTED extra checks
(clean_start, word_limit, macro_snapshot_grounded). Red/green before any live spend.
Mirrors test_client_review_checks.py / test_tier1_structural.py fixture style.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eval_spec import load_spec  # noqa: E402
from tier1_structural import grade_tier1  # noqa: E402
from transcript import ToolCall, Transcript  # noqa: E402

SPEC = load_spec("morning-brief")
_MACRO = [ToolCall("mcp__claude_ai_Parallax__macro_analyst", {})]


def _results(prose: str, calls=None) -> dict:
    t = Transcript(final_prose=prose, tool_calls=calls or _MACRO)
    return {c.name: c.passed for c in grade_tier1(t, SPEC)}


GOLDEN = """# Morning Brief

## Market Regime & Signals
Risk-off tilt; the regime tag is defensive with rates elevated.

## Macro Snapshot
- US tactical macro: stagflation lean, CPI 3.8%, June FOMC in focus.
- Equity stance: underweight.

## Portfolio Factor Tilt
| Factor | Score |
|---|---|
| VALUE | 4.1 |
| QUALITY | 7.2 |
| MOMENTUM | 6.8 |
| DEFENSIVE | 5.0 |
Momentum-tilted book, quality-led.

## Holding News
NVDA: in-line print, guidance steady.

## Action Items
- NVDA 15% weight + concentration — review sizing.
- Energy overweight into a negative tactical outlook.

## About This Report
Default Parallax branding.

*AI-assisted output. Verify any specific statement before acting.*

> *This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals.*
"""


def test_golden_passes_every_check():
    res = _results(GOLDEN)
    assert all(res.values()), [n for n, p in res.items() if not p]


# --- clean_start --------------------------------------------


def test_clean_start_red_on_view_probe_leak():
    leaked = (
        "No active house view and no white-label config, so standard framing.\n\n"
        + GOLDEN
    )
    assert _results(leaked)["clean_start"] is False


def test_clean_start_red_on_async_tool_status_leak():
    leaked = (
        "get_news_synthesis is async — I'll mark holding news pending.\n\n" + GOLDEN
    )
    assert _results(leaked)["clean_start"] is False


def test_clean_start_green_on_market_regime_open():
    body = GOLDEN.split("\n", 2)[2]  # drop the "# Morning Brief" title
    assert _results(body)["clean_start"] is True


def test_clean_start_green_on_fund_manager_title():
    # The skill expands the H1 to "# Fund Manager Morning Brief" — a clean title.
    titled = GOLDEN.replace(
        "# Morning Brief", "# Fund Manager Morning Brief — 2026-06-13", 1
    )
    assert _results(titled)["clean_start"] is True


def test_clean_start_green_skips_leading_horizontal_rule():
    # A stray leading '---' separator before the title is harmless, not a leak.
    assert _results("---\n\n" + GOLDEN)["clean_start"] is True


# --- word_limit (NEW; ≤800-word cap, gate ≤880) ----------------------------


def test_word_limit_green_on_short_brief():
    assert _results(GOLDEN)["word_limit"] is True


def test_word_limit_red_on_overlong_brief():
    filler = (
        "The portfolio shows broad cross-sector exposure with notable factor "
        "dispersion across holdings. "
    ) * 90  # ~1170 words of body (well over 880)
    over = GOLDEN.replace(
        "Momentum-tilted book, quality-led.",
        "Momentum-tilted book, quality-led. " + filler,
    )
    assert _results(over)["word_limit"] is False


def test_word_limit_disclaimer_exclusion_is_load_bearing():
    # An 802-word BODY (<=880 gate) followed by a ~105-word mandatory banner. The brief
    # must PASS — but only because the banner is excluded: counting full prose (907 words)
    # would exceed the gate. This isolates the exclusion logic (the golden fixture is too
    # short to do so).
    body = (
        "# Morning Brief\n\n" + "alpha " * 800
    )  # title (2 words) + 800 = 802 body words
    banner = "\n\n*AI-assisted output. " + "beta " * 100 + "not investment advice.*"
    prose = body + banner
    assert (
        len(prose.split()) > 880
    ), "fixture must exceed the gate when banner is counted"
    assert _results(prose)["word_limit"] is True  # passes only via banner exclusion


# --- macro_snapshot_grounded (ADAPTED from macro_conditional) --------------


def test_macro_red_when_called_but_snapshot_has_no_terms():
    silent = GOLDEN.replace(
        "- US tactical macro: stagflation lean, CPI 3.8%, June FOMC in focus.\n"
        "- Equity stance: underweight.",
        "- (snapshot pending)",
    )
    assert _results(silent)["macro_snapshot_grounded"] is False


def test_macro_vacuous_pass_when_not_called():
    assert _results(GOLDEN, calls=[])["macro_snapshot_grounded"] is True
