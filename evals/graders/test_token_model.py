"""Doc<->code consistency for the Parallax token price table.

``token_model.py`` declares ``skills/_parallax/token-costs.md`` as its source of
truth, but nothing tied the two together — a price change in either place could
drift silently. These tests parse the published table and assert the grader
agrees, and reproduce the documented per-workflow estimates through
``estimate()`` so a stale table surfaces as a hard failure.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from token_model import (  # noqa: E402
    FLAT_COST,
    PER_HOLDING_COST,
    USD_PER_TOKEN,
    estimate,
)
from transcript import ToolCall  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKEN_COSTS = REPO_ROOT / "skills" / "_parallax" / "token-costs.md"


def _table_names(doc: str, heading: str) -> set[str]:
    """Backticked tool names in the table under a ``###`` heading."""
    section = doc.split(heading, 1)[1].split("###", 1)[0]
    return {
        name
        for line in section.splitlines()
        if line.startswith("|")
        for name in re.findall(r"`([a-z_]+)`", line.split("|")[1])
    }


def test_flat_cost_matches_published_table():
    doc = TOKEN_COSTS.read_text()
    for heading, cost in [
        ("### 0 tokens (free)", 0),
        ("### 1 token each", 1),
        ("### 5 tokens each", 5),
        ("### 10 tokens each", 10),
    ]:
        names = _table_names(doc, heading)
        assert names, f"no tool names parsed under {heading!r}"
        for name in names:
            assert FLAT_COST.get(name) == cost, (
                f"{name}: doc says {cost}, FLAT_COST says {FLAT_COST.get(name)}"
            )


def test_known_unpriced_is_not_a_stale_table_signal():
    """A deliberately-unpriced endpoint must not read as an unknown one.

    ``unknown_endpoints`` degrades a run because the price table is stale, a
    condition someone can fix. The KNOWN_UNPRICED four can never be fixed by a
    table edit, so folding them in would permanently exclude pair-finder-class
    runs from aggregation for a reason nobody can clear.
    """
    from token_model import KNOWN_UNPRICED  # noqa: PLC0415

    calls = [ToolCall(name=f"mcp__claude_ai_Parallax__{n}", input={})
             for n in sorted(KNOWN_UNPRICED)]
    calls.append(ToolCall(name="mcp__claude_ai_Parallax__brand_new_tool", input={}))
    est = estimate(calls)

    assert est.unpriced_endpoints == tuple(sorted(KNOWN_UNPRICED))
    assert est.unknown_endpoints == ("brand_new_tool",)
    assert est.tokens == 0, "unpriced endpoints must not be costed at a guess"


def test_known_unpriced_endpoints_are_absent_from_the_price_tables():
    """If one of these ever gets measured it belongs in a cost table, and this
    test should fail so the KNOWN_UNPRICED entry gets removed with it."""
    from token_model import KNOWN_UNPRICED  # noqa: PLC0415

    for name in KNOWN_UNPRICED:
        assert name not in FLAT_COST, f"{name} is priced; drop it from KNOWN_UNPRICED"
        assert name not in PER_HOLDING_COST, f"{name} is priced; drop it"


def test_per_holding_cost_matches_published_table():
    """The fan-out table drifts as easily as the flat one, and was unpinned.

    ``test_flat_cost_matches_published_table`` parses only the four flat
    headings, so a mismatch under "1 token per holding (fan-out)" — the table
    backing ``PER_HOLDING_COST`` — used to pass silently.
    """
    names = _table_names(TOKEN_COSTS.read_text(), "### 1 token per holding (fan-out)")
    assert names, "no tool names parsed under the fan-out heading"
    assert names == set(PER_HOLDING_COST), (
        f"doc lists {sorted(names)}, PER_HOLDING_COST has "
        f"{sorted(PER_HOLDING_COST)}"
    )
    for name in names:
        assert PER_HOLDING_COST[name] == 1, (
            f"{name}: doc says 1/holding, code says {PER_HOLDING_COST[name]}"
        )


def test_overage_rate_matches_published_table():
    """``USD_PER_TOKEN`` is the multiplier on every dollar figure quoted to a
    client, and was the one constant with no tie-back to the doc at all."""
    doc = TOKEN_COSTS.read_text()
    assert f"${USD_PER_TOKEN:.2f}" in doc, (
        f"USD_PER_TOKEN={USD_PER_TOKEN} not found as a rate in token-costs.md"
    )


def test_etf_endpoints_priced_and_no_unverified_section():
    doc = TOKEN_COSTS.read_text()
    assert FLAT_COST["etf_profile"] == 1
    assert FLAT_COST["etf_daily_price"] == 1
    assert "measured 2026-07-28" in doc  # provenance, not the harness
    assert "## Unverified costs" not in doc


def test_peer_comparison_documented_sequence_costs_eight():
    # token-costs.md: peer snapshot + peer comparison export
    # + 3 score histories + 3 etf_profile probes = 8.
    calls = [
        ToolCall("mcp__claude_ai_Parallax__get_peer_snapshot", {}),
        ToolCall("mcp__claude_ai_Parallax__export_peer_comparison", {}),
        *[ToolCall("mcp__claude_ai_Parallax__get_score_analysis", {})] * 3,
        *[ToolCall("mcp__claude_ai_Parallax__etf_profile", {})] * 3,
    ]
    est = estimate(calls)
    assert est.unknown_endpoints == ()
    assert est.total == 8


def test_unrecognised_endpoint_is_flagged_not_free():
    est = estimate([ToolCall("mcp__claude_ai_Parallax__brand_new_tool", {})])
    assert est.total == 0
    assert est.unknown_endpoints == ("brand_new_tool",)


def test_foreign_mcp_servers_are_skipped_not_flagged():
    # Non-Parallax MCP tools consume no Parallax tokens and must not be
    # reported as unknown endpoints (which would degrade the run).
    est = estimate(
        [
            ToolCall("mcp__ide__getDiagnostics", {}),
            ToolCall("mcp__plugin_github_github__get_me", {}),
            ToolCall("mcp__claude_ai_Parallax__get_company_info", {}),
        ]
    )
    assert est.total == 1
    assert est.unknown_endpoints == ()
