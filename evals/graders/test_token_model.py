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


def test_unlisted_harness_tool_is_ignored_not_degraded():
    """A harness tool nobody registered anywhere must not degrade a run.

    Endpoint recognition allowlists on the Parallax MCP namespace rather than
    blocklisting known harness tool names. Under the old blocklist this call
    would have landed in ``unknown_endpoints`` and marked the run degraded
    forever -- a tool the harness gained after the list was written.
    """
    est = estimate([
        ToolCall(name="SomeToolInventedNextYear", input={}),
        ToolCall(name="Read", input={}),
        ToolCall(name="mcp__plugin_github_github__get_me", input={}),
    ])
    assert est.unknown_endpoints == ()
    assert est.tokens == 0


def test_alternate_parallax_connector_alias_is_billed():
    """Both live connector aliases must count.

    Real transcripts carry `mcp__claude_ai_Parallax__*` and
    `mcp__claude_ai_Parallax_2__*`. An exact-match allowlist on one alias would
    silently drop the other's calls from the client's derived bill.
    """
    est = estimate([
        ToolCall(name="mcp__claude_ai_Parallax__get_company_info", input={}),
        ToolCall(name="mcp__claude_ai_Parallax_2__get_company_info", input={}),
    ])
    assert est.tokens == 2, "an aliased connector's calls must still be billed"
    assert est.unknown_endpoints == ()


def test_non_standard_alias_is_surfaced_not_guessed():
    """Neither silent undercount nor silent misattribution.

    A known endpoint name under an unrecognised namespace is genuinely
    undecidable: it may be a connector mounted off-brand, or another server's
    colliding tool. Billing it risks charging a client for someone else's call;
    dropping it reports ``tokens=0`` on a real run. It is reported instead.
    """
    est = estimate([
        ToolCall(name="mcp__research_desk__get_company_info", input={}),
        ToolCall(name="mcp__research_desk__get_stock_report", input={}),
    ])
    assert est.tokens == 0, "must not bill a call we cannot attribute"
    assert est.ambiguous_endpoints == (
        "mcp__research_desk__get_company_info",
        "mcp__research_desk__get_stock_report",
    )
    assert est.unknown_endpoints == (), "not a stale table -- an unknown server"


def test_declared_alias_resolves_ambiguity_and_bills():
    """PARALLAX_MCP_ALIASES is the supported way to settle an off-brand mount."""
    import importlib  # noqa: PLC0415
    import os  # noqa: PLC0415

    import token_model  # noqa: PLC0415

    prior = os.environ.get("PARALLAX_MCP_ALIASES")
    os.environ["PARALLAX_MCP_ALIASES"] = "research_desk"
    try:
        reloaded = importlib.reload(token_model)
        est = reloaded.estimate([
            ToolCall(name="mcp__research_desk__get_company_info", input={}),
            ToolCall(name="mcp__research_desk__get_stock_report", input={}),
        ])
        assert est.tokens == 11
        assert est.ambiguous_endpoints == ()
    finally:
        if prior is None:
            os.environ.pop("PARALLAX_MCP_ALIASES", None)
        else:
            os.environ["PARALLAX_MCP_ALIASES"] = prior
        importlib.reload(token_model)


def test_declared_foreign_namespace_resolves_ambiguity_truthfully():
    """Ambiguity must be resolvable in BOTH directions.

    With only PARALLAX_MCP_ALIASES, the sole way to stop a genuine foreign
    collision degrading every run was to declare that server Parallax -- which
    would then bill its calls to the client. Offering one direction rebuilt the
    permanent-unfixable-degrade trap KNOWN_UNPRICED exists to prevent.
    """
    import importlib  # noqa: PLC0415
    import os  # noqa: PLC0415

    import token_model  # noqa: PLC0415

    prior = os.environ.get("PARALLAX_MCP_FOREIGN_NAMESPACES")
    os.environ["PARALLAX_MCP_FOREIGN_NAMESPACES"] = "claude_ai_hubspot"
    try:
        reloaded = importlib.reload(token_model)
        est = reloaded.estimate([
            ToolCall(name="mcp__claude_ai_HubSpot__submit_feedback", input={})
        ])
        assert est.ambiguous_endpoints == (), "declared foreign must stop degrading"
        assert est.tokens == 0, "and must still never be billed"
        assert est.unpriced_endpoints == ()
    finally:
        if prior is None:
            os.environ.pop("PARALLAX_MCP_FOREIGN_NAMESPACES", None)
        else:
            os.environ["PARALLAX_MCP_FOREIGN_NAMESPACES"] = prior
        importlib.reload(token_model)


def test_foreign_server_colliding_name_is_never_billed():
    """`submit_feedback` is exposed by both the Parallax and HubSpot connectors.

    Attributing HubSpot's copy to the client's Parallax invoice is the concrete
    failure that rules out recognising a call by its bare name alone.
    """
    est = estimate([ToolCall(name="mcp__claude_ai_HubSpot__submit_feedback", input={})])
    assert est.tokens == 0
    assert est.unpriced_endpoints == (), "not Parallax's endpoint to report"
    assert est.ambiguous_endpoints == ("mcp__claude_ai_HubSpot__submit_feedback",)


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
