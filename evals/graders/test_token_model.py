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


# --- reverse direction (code -> doc) and the tables the forward tests skip ----

_AI_HEADING = "### AI investor profile workflows"
_UNPRICED_HEADING = "### Unpriced (live endpoints nobody has measured)"
_FLAT_HEADINGS = {
    0: "### 0 tokens (free)",
    1: "### 1 token each",
    5: "### 5 tokens each",
    10: "### 10 tokens each",
}


def _section(doc: str, heading: str) -> str:
    assert heading in doc, f"heading {heading!r} missing from token-costs.md"
    return doc.split(heading, 1)[1].split("\n###", 1)[0]


def _workflow_rows(doc: str, heading: str) -> dict[str, str]:
    """{row label incl. mode: bold cost} for a per-workflow table.

    ``_table_names``'s ``[a-z_]+`` class cannot match hyphenated skill names,
    so this parser keeps the whole first cell (name plus optional mode) as the
    label and reads the bold cost cell verbatim.
    """
    rows: dict[str, str] = {}
    for line in _section(doc, heading).splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        m = re.match(r"^`([a-z0-9_-]+)`(?:\s+\(([^)]+)\))?$", cells[0])
        assert m, f"unparseable workflow row: {cells[0]!r}"
        label = m.group(1) + (f" ({m.group(2)})" if m.group(2) else "")
        cost = re.match(r"^\*\*(.+?)\*\*$", cells[1])
        assert cost, f"cost cell is not bold in {label}: {cells[1]!r}"
        rows[label] = cost.group(1)
    return rows


def test_every_flat_cost_key_is_published():
    """Reverse of ``test_flat_cost_matches_published_table``: a name priced in
    code but absent from the doc (``check_api_health`` was one) is drift too."""
    doc = TOKEN_COSTS.read_text()
    published = {
        name: cost
        for cost, heading in _FLAT_HEADINGS.items()
        for name in _table_names(doc, heading)
    }
    for name, cost in FLAT_COST.items():
        assert name in published, f"{name} is in FLAT_COST but not in token-costs.md"
        assert published[name] == cost, f"{name}: code {cost}, doc {published[name]}"


def test_known_unpriced_matches_published_table():
    from token_model import KNOWN_UNPRICED  # noqa: PLC0415

    names = _table_names(TOKEN_COSTS.read_text(), _UNPRICED_HEADING)
    assert names == set(KNOWN_UNPRICED), (
        f"doc lists {sorted(names)}, KNOWN_UNPRICED has {sorted(KNOWN_UNPRICED)}"
    )


_AI_ROWS = {
    "parallax-ai-buffett": "~4",
    "parallax-ai-greenblatt (ticker-check)": "~10-15",
    "parallax-ai-greenblatt (universe mode)": "~10-30",
    "parallax-ai-klarman": "~5-7",
    "parallax-ai-soros (single-ticker)": "~25-30",
    "parallax-ai-soros (basket mode)": "~30-40",
    "parallax-ai-ptj (single-ticker)": "~14-16",
    "parallax-ai-consensus (single ticker)": "~60-70",
    "parallax-ai-consensus (basket of 5)": "~180-240",
}


def test_ai_profile_table_rows_and_values_are_exact():
    """Every mode-specific row, with its value — presence of a directory name
    alone would let a deleted mode row or a typo'd figure pass."""
    rows = _workflow_rows(TOKEN_COSTS.read_text(), _AI_HEADING)
    assert rows == _AI_ROWS


def test_every_ai_profile_skill_has_a_cost_row():
    labels = {label.split(" ")[0] for label in _AI_ROWS}
    for skill_dir in sorted((REPO_ROOT / "skills").glob("parallax-ai-*")):
        assert skill_dir.name in labels, f"{skill_dir.name} has no row under {_AI_HEADING}"


def test_ai_profiles_readme_does_not_carry_a_second_table():
    readme = (REPO_ROOT / "skills" / "_parallax" / "AI-profiles" / "README.md").read_text()
    assert not re.search(r"^\|\s*`parallax-ai-[a-z]+`.*~\d", readme, re.M), (
        "AI-profiles/README.md carries its own cost table; token-costs.md is the single source"
    )
