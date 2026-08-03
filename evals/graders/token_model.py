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

import os
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
    "check_api_health": 0,
    # 1 token
    "get_company_info": 1,
    "list_macro_countries": 1,
    "get_telemetry": 1,
    "get_peer_snapshot": 1,
    "export_peer_comparison": 1,
    "get_financials": 1,
    "get_stock_outlook": 1,
    "get_score_analysis": 1,
    "etf_profile": 1,
    "etf_daily_price": 1,
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

# Live Parallax endpoints deliberately left unpriced: nobody has measured them,
# and this repo does not publish inferred numbers. They are NOT a stale-table
# signal -- that signal is reserved for a name we do not recognise at all, which
# clears once someone prices it. These four never clear, so folding them into
# ``unknown_endpoints`` would permanently degrade any run that touches them
# (``parallax-pair-finder`` calls etf_search/etf_holdings) for a reason no table
# edit can fix. They are reported separately so a total can state what it omits.
KNOWN_UNPRICED: frozenset[str] = frozenset({
    "etf_search",
    "etf_holdings",
    "check_job_status",
    "submit_feedback",
})

# Every endpoint name this module can say anything about, priced or explicitly
# not. Used to recognise a Parallax call mounted under a non-standard MCP alias.
KNOWN_ENDPOINTS: frozenset[str] = (
    frozenset(FLAT_COST) | frozenset(PER_HOLDING_COST) | KNOWN_UNPRICED
)

# Harness-local tools (Read, Bash, ToolSearch, ...) used to be skipped by a
# hand-maintained blocklist. That inverted the burden: every tool the harness
# gained in future had to be remembered here, and a forgotten one would land in
# ``unknown_endpoints`` and permanently degrade runs -- the same unfixable-signal
# failure ``KNOWN_UNPRICED`` exists to prevent, relocated into blocklist drift.
#
# A Parallax endpoint always arrives MCP-namespaced (``mcp__<alias>__<tool>``),
# so a name carrying no MCP namespace cannot be a Parallax endpoint by
# construction. ``estimate`` therefore allowlists on ``is_parallax_mcp`` and
# ignores everything else structurally -- no list to keep current.

# Default overage rate. Override per plan; never hardcode into a client-facing
# figure without stating the plan it came from.
USD_PER_TOKEN = 0.20


@dataclass(frozen=True)
class TokenEstimate:
    tokens: int
    unknown_endpoints: tuple[str, ...]
    unpriced_endpoints: tuple[str, ...] = ()
    ambiguous_endpoints: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return self.tokens

    def usd(self, rate: float = USD_PER_TOKEN) -> float:
        return self.total * rate


def bare(name: str) -> str:
    """Strip any MCP namespace prefix, leaving the endpoint name."""
    return name.rsplit("__", 1)[-1]


# Extra MCP namespaces that are known to be Parallax, for deployments that mount
# the connector under a name with no "parallax" in it (white-label, in
# particular). Comma-separated, matched case-insensitively against the full
# namespace segment. This is the supported way to resolve an ambiguous alias --
# see ``classify_call``.
PARALLAX_ALIASES: frozenset[str] = frozenset(
    part.strip().lower()
    for part in os.environ.get("PARALLAX_MCP_ALIASES", "").split(",")
    if part.strip()
)

CALL_PARALLAX = "parallax"
CALL_FOREIGN = "foreign"
CALL_AMBIGUOUS = "ambiguous"


def classify_call(name: str) -> str:
    """Whose endpoint is this: Parallax, another server's, or undecidable?

    A tool name cannot prove which server served it, and both ways of guessing
    fail silently in opposite directions. Guessing by namespace undercounts a
    connector mounted off-brand: every call bills zero with an empty
    ``unknown_endpoints``, indistinguishable from a genuinely free run. Guessing
    by bare name misattributes a foreign server's colliding tool onto the
    client's invoice -- not hypothetical, since ``submit_feedback`` is exposed by
    both the Parallax and HubSpot connectors.

    So this does not guess. A namespace containing ``parallax``, or listed in
    ``PARALLAX_MCP_ALIASES``, is Parallax. A name with no MCP namespace is
    harness-local. Anything else whose bare name this table happens to know is
    reported ``ambiguous`` and billed to nobody, because the honest answer is
    that we cannot tell -- and an operator can settle it permanently by naming
    the alias in ``PARALLAX_MCP_ALIASES``.
    """
    if not name.startswith("mcp__"):
        return CALL_FOREIGN  # harness-local; never MCP-namespaced
    namespace = name[len("mcp__"):].rsplit("__", 1)[0].lower()
    if "parallax" in namespace or namespace in PARALLAX_ALIASES:
        return CALL_PARALLAX
    if bare(name) in KNOWN_ENDPOINTS:
        return CALL_AMBIGUOUS
    return CALL_FOREIGN


def is_parallax_mcp(name: str) -> bool:
    """True only when the call is definitively Parallax's.

    Ambiguous calls are excluded: this answers "may I bill this?", and the
    answer under ambiguity is no.
    """
    return classify_call(name) == CALL_PARALLAX


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

    A ``KNOWN_UNPRICED`` endpoint lands in ``unpriced_endpoints`` instead. Both
    are excluded from ``tokens``, but only the former means the table is stale.
    """
    tokens = 0
    unknown: list[str] = []
    unpriced: list[str] = []
    ambiguous: list[str] = []

    for call in tool_calls:
        kind = classify_call(call.name)
        if kind == CALL_FOREIGN:
            # Harness-local tool or another MCP server. Cannot be a Parallax
            # endpoint, so it is not a stale-table signal either.
            continue
        if kind == CALL_AMBIGUOUS:
            # A known endpoint name under an unrecognised namespace. Billing it
            # risks charging the client for another server's call; skipping it
            # silently undercounts a legitimately off-brand connector. Neither
            # is defensible in silence, so it is surfaced instead.
            ambiguous.append(call.name)
            continue
        name = bare(call.name)
        if name in FLAT_COST:
            tokens += FLAT_COST[name]
        elif name in PER_HOLDING_COST:
            tokens += PER_HOLDING_COST[name] * _holdings_in(call.input or {})
        elif name in KNOWN_UNPRICED:
            unpriced.append(name)
        else:
            unknown.append(name)

    return TokenEstimate(
        tokens,
        tuple(sorted(set(unknown))),
        tuple(sorted(set(unpriced))),
        tuple(sorted(set(ambiguous))),
    )
