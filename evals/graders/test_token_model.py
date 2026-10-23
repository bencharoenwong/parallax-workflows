"""Published decimal prices, request multiplicity and honest planning limits."""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from token_model import (  # noqa: E402
    CONDITIONAL_COST, FLAT_COST, KNOWN_ENDPOINTS, PER_HOLDING_COST,
    PER_SYMBOL_COST, USD_PER_TOKEN, estimate,
)
from transcript import ToolCall  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKEN_COSTS = REPO_ROOT / "skills" / "_parallax" / "token-costs.md"


def call(name, **args):
    return ToolCall("mcp__parallax__" + name, args)


def test_all_36_published_tools_and_decimal_prices_match():
    """Read the single Tool | Credits | Basis table in both directions."""
    rows = {}
    for line in TOKEN_COSTS.read_text().splitlines():
        if not line.startswith("| `"):
            continue
        cells = [part.strip() for part in line.strip("|").split("|")]
        match = re.fullmatch(r"`([a-z_]+)`", cells[0])
        if match:
            assert match[1] not in rows, f"duplicate tool price: {match[1]}"
            rows[match[1]] = cells
    assert len(KNOWN_ENDPOINTS) == 36
    assert sum(value == 0 for value in FLAT_COST.values()) == 11
    assert set(rows) == KNOWN_ENDPOINTS
    for name, price in {**FLAT_COST, **PER_SYMBOL_COST, **PER_HOLDING_COST}.items():
        numbers = [Decimal(n) for n in re.findall(r"(?<![a-z_])\d+(?:\.\d+)?", rows[name][1])]
        assert Decimal(str(price)) in numbers, (name, price, rows[name])
    for name, (normal, upper) in CONDITIONAL_COST.items():
        numbers = [Decimal(n) for n in re.findall(r"(?<![a-z_])\d+(?:\.\d+)?", rows[name][1])]
        assert Decimal(str(upper)) in numbers, (name, rows[name])
        assert Decimal(str(normal)) in numbers, (name, rows[name])
        assert len(rows[name]) >= 3 and rows[name][2]


def test_every_data_workflow_has_a_credit_estimate_row():
    """A new skill or deleted profile row must not silently lose its estimate."""
    rows = {}
    for line in TOKEN_COSTS.read_text().splitlines():
        match = re.match(r"^\| `/?(parallax-[a-z-]+)`", line)
        if match:
            cells = [part.strip() for part in line.strip("|").split("|")]
            assert re.fullmatch(r"\*\*.+\*\*", cells[1]), line
            rows[match[1]] = cells[1]
    # The concierge only routes and makes free health/resolution calls; its
    # downstream workflow is separately priced. Supplied-source translations
    # also have no Parallax data plan.
    expected = {
        path.parent.name
        for path in (REPO_ROOT / "skills").glob("parallax-*/SKILL.md")
    } - {"parallax-concierge"}
    assert set(rows) == expected


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
        ToolCall(name="mcp__claude_ai_Parallax__get_company_info", input={"symbol": "AAPL.O"}),
        ToolCall(name="mcp__claude_ai_Parallax_2__get_company_info", input={"symbol": "AAPL.O"}),
    ])
    assert est.tokens == 0.1, "an aliased connector's calls must still be billed"
    assert est.unknown_endpoints == ()


def test_non_standard_alias_is_surfaced_not_guessed():
    """Neither silent undercount nor silent misattribution.

    A known endpoint name under an unrecognised namespace is genuinely
    undecidable: it may be a connector mounted off-brand, or another server's
    colliding tool. Billing it risks charging a client for someone else's call;
    dropping it reports ``tokens=0`` on a real run. It is reported instead.
    """
    est = estimate([
        ToolCall(name="mcp__research_desk__get_company_info", input={"symbol": "AAPL.O"}),
        ToolCall(name="mcp__research_desk__get_stock_report", input={"symbol": "AAPL.O"}),
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
            ToolCall(name="mcp__research_desk__get_company_info", input={"symbol": "AAPL.O"}),
            ToolCall(name="mcp__research_desk__get_stock_report", input={"symbol": "AAPL.O"}),
        ])
        assert est.tokens == 10.05
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



@pytest.mark.parametrize("tool", sorted(PER_SYMBOL_COST))
def test_symbol_lists_multiply_even_in_one_request(tool):
    est = estimate([call(tool, symbol="AAPL.O, MSFT.O, JPM.N")])
    assert est.total == 0.15
    assert est.upper_bound_tokens == 0.15


def test_decimal_sums_and_usd_are_json_compatible():
    est = estimate([call("get_company_info", symbol="AAPL.O")] * 6)
    assert est.tokens == 0.3
    assert est.usd() == 0.06
    assert json.loads(json.dumps(asdict(est)))["tokens"] == 0.3
    assert "Planning" in est.assumptions[0]


@pytest.mark.parametrize("statement", ["income", "balance_sheet", "cash_flow"])
def test_latest_comparisons_double_only_full_statements(statement):
    est = estimate([call("get_financials", symbol="AAPL.O,MSFT.O", statement=statement, latest=True)])
    assert est.total == 0.2
    assert estimate([call("get_financials", symbol="AAPL.O", statement=statement)]).total == 0.05


@pytest.mark.parametrize("statement", ["ratios", "summary"])
def test_latest_does_not_double_ratios_or_summary(statement):
    assert estimate([call("get_financials", symbol="AAPL.O,MSFT.O", statement=statement, latest=True)]).total == 0.1


@pytest.mark.parametrize("aspect,expected", [("analyst_targets", .05), ("recommendations", .05), ("risk_return", .1), ("dividends", .15)])
def test_outlook_per_call_aspects_and_per_symbol_dividends(aspect, expected):
    assert estimate([call("get_stock_outlook", symbol="AAPL.O,MSFT.O,JPM.N", aspect=aspect)]).total == expected


def holdings(n):
    return [{"symbol": f"S{i}.O", "weight": 1 if i == 0 else 0} for i in range(n)]


@pytest.mark.parametrize("tool,n,kwargs,expected", [
    ("quick_portfolio_scores", 3, {}, .3),
    ("quick_portfolio_scores", 70, {}, 5),
    ("quick_portfolio_scores", 130, {"max_holdings": 100}, 10),
    ("quick_portfolio_scores", 70, {"max_holdings": 7}, .7),
    ("quick_portfolio_scores", 70, {"max_holdings": 7.0}, .7),
    ("check_portfolio_redundancy", 3, {}, .3),
    ("check_portfolio_redundancy", 130, {}, 10),
])
def test_holding_caps_and_surviving_zero_weights(tool, n, kwargs, expected):
    assert estimate([call(tool, holdings=holdings(n), **kwargs)]).total == expected


def test_macro_omitted_overview_has_explicit_conditional_ceiling():
    est = estimate([call("macro_analyst", market="Japan")])
    assert est.total == 5
    assert est.upper_bound_tokens == 50
    assert estimate([call("macro_analyst", market="Japan", component="tactical")]).upper_bound_tokens == 5


@pytest.mark.parametrize("kwargs,expected", [
    ({"stock": "MSFT.O"}, (.1, .1)),
    ({"basket": "semiconductor"}, (.05, .2)),
    ({"market": "Japan"}, (.05, .05)),
    ({}, (.05, .05)),
])
def test_explore_telemetry_is_priced_by_view(kwargs, expected):
    est = estimate([call("explore_telemetry", **kwargs)])
    assert est.unpriced_endpoints == ()
    assert (est.total, est.upper_bound_tokens) == expected


def test_performance_always_attempts_both_reads_in_all_success_plan():
    est = estimate([call("get_performance_history", symbol="AAPL.O")])
    assert (est.total, est.upper_bound_tokens) == (.2, .2)


def test_mixed_fractional_and_conditional_calls_sum_without_truncation():
    est = estimate([call("macro_analyst", market="Japan"), call("get_performance_history", symbol="AAPL.O"), call("get_company_info", symbol="AAPL.O")])
    assert est.total == 5.25
    assert est.upper_bound_tokens == 50.25


@pytest.mark.parametrize("tool,args", [
    ("get_company_info", {}),
    ("export_price_series", {"symbol": "AAPL.O,"}),
    ("etf_daily_price", {"symbol": ["SPY"]}),
    ("get_financials", {"symbol": "AAPL.O", "latest": "true"}),
    ("get_financials", {"symbol": "AAPL.O", "statement": "invalid"}),
    ("get_stock_outlook", {"symbol": "AAPL.O", "aspect": "invalid"}),
    ("get_stock_outlook", {"symbol": "AAPL.O", "aspect": []}),
    ("get_financials", {"symbol": "AAPL.O", "statement": []}),
    ("macro_analyst", {"market": "Japan", "component": []}),
    ("macro_analyst", {}),
    ("macro_analyst", {"market": "Japan", "component": "overview"}),
    ("macro_analyst", {"market": "Japan", "component": None}),
    ("quick_portfolio_scores", {"holdings": holdings(2), "max_holdings": 101}),
    ("quick_portfolio_scores", {"holdings": holdings(2), "max_holdings": 1.5}),
    ("quick_portfolio_scores", {"holdings": holdings(2), "max_holdings": True}),
    ("check_portfolio_redundancy", {"holdings": []}),
    ("check_portfolio_redundancy", {"holdings": [{"symbol": "AAPL.O", "weight": -1}]}),
    ("check_portfolio_redundancy", {"holdings": [{"symbol": "AAPL.O", "weight": float("nan")}]}),
])
def test_invalid_pricing_inputs_are_explicitly_unpriced(tool, args):
    est = estimate([call(tool, **args)])
    assert est.unpriced_endpoints == (tool,)
    assert est.unpriced_inputs and est.total == 0
    assert not est.unknown_endpoints


def test_unknown_call_is_not_silently_free():
    est = estimate([call("brand_new_tool")])
    assert est.unknown_endpoints == ("brand_new_tool",)


def test_all_current_endpoints_including_former_unpriced_have_prices():
    est = estimate([call("etf_holdings", symbol="SPY"), call("check_job_status", job_id="123e4567-e89b-42d3-a456-426614174000"), call("submit_feedback", description="Synthetic test feedback; no submission is sent."), call("get_score_summary", symbol="AAPL.O"), call("get_etf_report", symbol="SPY")])
    assert est.total == 10.2
    assert not est.unpriced_endpoints
    assert not est.unknown_endpoints


@pytest.mark.parametrize("rate", [-1, float("nan"), float("inf"), True])
def test_invalid_usd_rates_are_rejected(rate):
    with pytest.raises(ValueError):
        estimate([]).usd(rate)


def test_omitted_financial_statement_defaults_to_summary_even_with_latest():
    est = estimate([call("get_financials", symbol="AAPL.O", latest=True)])
    assert est.total == .05
    assert est.upper_bound_tokens == .05


def test_omitted_outlook_aspect_defaults_to_targets_per_call():
    assert estimate([call("get_stock_outlook", symbol="AAPL.O,MSFT.O")]).total == .05


@pytest.mark.parametrize("tool", ["quick_portfolio_scores", "check_portfolio_redundancy"])
def test_all_zero_holdings_stop_before_lookups_and_are_marked_invalid(tool):
    est = estimate([call(tool, holdings=[{"symbol": "AAPL.O", "weight": 0}])])
    assert est.unpriced_endpoints == (tool,)
    assert "tool stops before any lookup" in est.unpriced_inputs[0]
    assert est.total == 0
    assert est.upper_bound_tokens is None


@pytest.mark.parametrize("incomplete", [
    call("unpublished_tool"),
    call("get_company_info"),
    ToolCall("mcp__unidentified_server__get_company_info", {"symbol": "AAPL.O"}),
])
def test_incomplete_estimate_retains_subtotal_but_has_no_full_ceiling(incomplete):
    est = estimate([call("get_company_info", symbol="MSFT.O"), incomplete])
    assert est.total == .05
    assert est.upper_bound_tokens is None
    assert est.unknown_endpoints or est.unpriced_endpoints or est.ambiguous_endpoints
    assert json.loads(json.dumps(asdict(est)))["upper_bound_tokens"] is None


@pytest.mark.parametrize("args", [
    {"holdings": [{"symbol": "AAPL.O", "weight": 10**400}]},
    {"holdings": holdings(2), "max_holdings": 10**400},
])
def test_enormous_json_integers_are_unpriced_without_float_overflow(args):
    est = estimate([call("quick_portfolio_scores", **args)])
    assert est.unpriced_endpoints == ("quick_portfolio_scores",)
    assert est.upper_bound_tokens is None


@pytest.mark.parametrize("rate", [1e308, 10**400])
def test_usd_overflow_is_rejected_before_nonfinite_json_output(rate):
    est = estimate([call("get_stock_report", symbol="AAPL.O")])
    with pytest.raises(ValueError, match="finite JSON number"):
        est.usd(rate)
