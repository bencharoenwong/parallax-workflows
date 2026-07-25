"""Parallax token price table, parsed from the published price list.

The client's bill is metered in Parallax tokens, not Anthropic tokens. There is
no billing endpoint in the MCP surface, so a run's Parallax cost must be
DERIVED: counted tool calls x published unit price.

Anything produced here is *derived, not metered*, and must be labelled that way
wherever it is reported. Validate against the operator billing dashboard once
before any figure is published externally.

Source of truth: ``skills/_parallax/token-costs.md``.
"""
from __future__ import annotations

from dataclasses import dataclass

# Flat per-call cost, keyed on the bare endpoint name (namespace-stripped).
FLAT_COST: dict[str, int] = {
    # free
    "explain_methodology": 0,
    "get_docs": 0,
    "list_docs": 0,
    "search_stocks": 0,
    "search_etfs": 0,
    "export_price_series": 0,
    "list_macro_countries": 0,
    "get_telemetry": 0,
    "check_api_health": 0,
    # 1 token
    "get_company_info": 1,
    "get_peer_snapshot": 1,
    "export_peer_comparison": 1,
    "get_financials": 1,
    "get_stock_outlook": 1,
    "get_score_analysis": 1,
    # 5 tokens
    "build_stock_universe": 5,
    "get_news_synthesis": 5,
    "get_technical_analysis": 5,
    "get_financial_analysis": 5,
    "analyze_portfolio": 5,
    "macro_analyst": 5,
    "check_macro_health": 5,
    # 10 tokens
    "get_stock_report": 10,
    "get_assessment": 10,
}

# Cost scales with the number of holdings in the call, not per call.
PER_HOLDING_COST: dict[str, int] = {
    "quick_portfolio_scores": 1,
    "check_portfolio_redundancy": 1,
}

# Published price list explicitly marks these UNVERIFIED. Counted separately so
# any total can state how much of it rests on an unverified price.
UNVERIFIED: set[str] = {"etf_profile", "etf_daily_price"}
UNVERIFIED_ASSUMED_COST = 1

# Harness-local tools. These consume Anthropic tokens but never Parallax ones,
# so they must be skipped rather than reported as unpriced endpoints -- an
# unrecognised name is meant to signal a stale price table, and noise here would
# mask that signal.
HARNESS_TOOLS: set[str] = {
    "ToolSearch", "TodoWrite", "SlashCommand", "Skill", "Task", "Agent",
    "AskUserQuestion", "ExitPlanMode", "EnterPlanMode", "KillShell",
    "BashOutput", "NotebookEdit", "ListMcpResourcesTool", "ReadMcpResourceTool",
}
HARNESS_PREFIXES = (
    "Read", "Write", "Edit", "Bash", "Glob", "Grep", "LS", "WebFetch",
    "WebSearch", "Notebook", "mcp__ide__",
)

# Default overage rate. Override per plan; never hardcode into a client-facing
# figure without stating the plan it came from.
USD_PER_TOKEN = 0.20


@dataclass(frozen=True)
class TokenEstimate:
    tokens: int
    tokens_unverified: int
    unknown_endpoints: tuple[str, ...]

    @property
    def total(self) -> int:
        return self.tokens + self.tokens_unverified

    def usd(self, rate: float = USD_PER_TOKEN) -> float:
        return self.total * rate


def bare(name: str) -> str:
    """Strip any MCP namespace prefix, leaving the endpoint name."""
    return name.rsplit("__", 1)[-1]


def _holdings_in(call_input: dict) -> int:
    for key in ("portfolio", "holdings", "symbols"):
        val = call_input.get(key)
        if isinstance(val, list):
            return len(val)
    return 1


def estimate(tool_calls) -> TokenEstimate:
    """Derive Parallax token cost from an ordered list of ToolCall.

    An endpoint absent from every table is reported in ``unknown_endpoints``
    rather than silently costed at zero -- a new billable tool must surface as a
    hard failure, not as a free call.
    """
    tokens = 0
    unverified = 0
    unknown: list[str] = []

    for call in tool_calls:
        name = bare(call.name)
        if name in FLAT_COST:
            tokens += FLAT_COST[name]
        elif name in PER_HOLDING_COST:
            tokens += PER_HOLDING_COST[name] * _holdings_in(call.input or {})
        elif name in UNVERIFIED:
            unverified += UNVERIFIED_ASSUMED_COST
        elif name in HARNESS_TOOLS or name.startswith(HARNESS_PREFIXES):
            continue  # harness-local tool, not a Parallax endpoint
        else:
            unknown.append(name)

    return TokenEstimate(tokens, unverified, tuple(sorted(set(unknown))))
