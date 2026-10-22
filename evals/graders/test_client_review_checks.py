"""Unit tests for the client-review eval spec's NEW/ADAPTED extra checks.

Verifies the matchers fire correctly (red on the failure mode, green on a
conforming output) BEFORE any live rollout spends Parallax tokens. Mirrors the
inline-Transcript fixture style of test_tier1_structural.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eval_spec import load_spec  # noqa: E402
from tier1_structural import grade_tier1  # noqa: E402
from transcript import ToolCall, Transcript  # noqa: E402

SPEC = load_spec("client-review")
_MACRO = [ToolCall("mcp__claude_ai_Parallax__macro_analyst", {})]


def _results(prose: str, calls=None) -> dict:
    t = Transcript(final_prose=prose, tool_calls=calls or _MACRO)
    return {c.name: c.passed for c in grade_tier1(t, SPEC)}


# A conforming, pinned-state (no view, no white-label) output that should pass
# every check in SPEC.check_ids.
GOLDEN = """# Client Portfolio Review

## Portfolio Summary
AUM mix and top holdings.

## Health Status
🟡 **Monitor** — 2 flags raised.

## Factor Analysis
Quality 7.1, Value 4.2. Against the current US tactical macro regime
(equity-underweight), the value tilt is a mild headwind.

## Concentration & Redundancy
Top-1 weight 45% (Concentration flag). AAPL/MSFT redundant pair.

## Per-Holding Analysis
NVDA: score trend 6.8 -> 5.9, risk elevated.

## Suitability Assessment
For a conservative income-focused retiree, this aggressive tech book is misaligned.

## Recommended Actions
- **High — Trim NVDA**: 15% weight + Low Score 4.2.
- **Low — Hold JPM**: stable scores, no flags.

## Appendix: Methodology
Parallax factor scores.

## About This Report
Default Parallax branding.

*AI-assisted output. Verify any specific statement before acting.*

> *This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals.*
"""


def test_golden_passes_every_check():
    res = _results(GOLDEN)
    assert all(res.values()), [n for n, p in res.items() if not p]


# --- clean_start ---------------------------


def test_clean_start_red_on_scaffold_preamble():
    leaked = (
        "**Step A.5 → Batch C complete.** Verified-holdings aggregates.\n\n" + GOLDEN
    )
    assert _results(leaked)["clean_start"] is False


def test_clean_start_red_on_white_label_probe_leak():
    leaked = "**White-label:** `config_not_found` → not active.\n\n" + GOLDEN
    assert _results(leaked)["clean_start"] is False


def test_clean_start_green_on_portfolio_summary_open():
    # No title line; opens directly on the first rendered section.
    body = GOLDEN.split("\n", 2)[2]  # drop the "# Client Portfolio Review" title
    assert _results(body)["clean_start"] is True


# --- recommendations_actionable (NEW directive check) ----------------------


def test_recommendations_actionable_red_when_no_priority_or_action():
    vague = GOLDEN.replace(
        "- **High — Trim NVDA**: 15% weight + Low Score 4.2.\n"
        "- **Low — Hold JPM**: stable scores, no flags.",
        "You may want to think about your overall allocation over time.",
    )
    assert _results(vague)["recommendations_actionable"] is False


def test_recommendations_actionable_red_when_section_absent():
    no_sec = GOLDEN.replace("## Recommended Actions", "## Closing Notes")
    assert _results(no_sec)["recommendations_actionable"] is False


# --- macro_in_factor_analysis (ADAPTED from macro_conditional) -------------


def test_macro_red_when_called_but_absent_from_factor_analysis():
    silent = GOLDEN.replace(
        "Quality 7.1, Value 4.2. Against the current US tactical macro regime\n"
        "(equity-underweight), the value tilt is a mild headwind.",
        "Quality 7.1, Value 4.2 — a quality-led factor profile.",
    )
    assert _results(silent)["macro_in_factor_analysis"] is False


def test_macro_vacuous_pass_when_not_called():
    # macro_analyst not called -> coverage-gated vacuous pass.
    assert _results(GOLDEN, calls=[])["macro_in_factor_analysis"] is True
