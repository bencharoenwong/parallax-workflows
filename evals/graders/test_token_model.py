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

from token_model import FLAT_COST, estimate  # noqa: E402
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
