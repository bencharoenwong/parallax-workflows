"""Input-only Parallax credit planning estimates, never observed account charges.

Legacy ``tokens`` names mean Parallax credits, not model context tokens. Prices
follow ``skills/_parallax/token-costs.md``. All-success estimates cannot establish
HTTP/job success or response-dependent request branches. Existing saved records
are not repriced; explicitly parsing a trace creates a new current-price estimate.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite

# Truly fixed per-call prices. Conditional and multiplicative prices stay separate.
FLAT_COST: dict[str, float] = {
    "check_job_status": 0, "check_api_health": 0, "explain_methodology": 0,
    "list_macro_countries": 0, "check_macro_health": 0, "get_docs": 0,
    "list_docs": 0, "submit_feedback": 0, "etf_search": 0,
    "search_stocks": 0, "search_etfs": 0,
    "get_peer_snapshot": 0.1, "export_peer_comparison": 0.1,
    "get_score_analysis": 0.1, "get_score_summary": 0.1,
    "get_telemetry": 0.05, "etf_profile": 0.1, "etf_holdings": 0.1,
    "build_stock_universe": 5, "analyze_portfolio": 5,
    "get_news_synthesis": 5, "get_technical_analysis": 5,
    "get_financial_analysis": 5, "get_stock_report": 10,
    "get_assessment": 10, "get_etf_report": 10,
    # Always attempts calendar and risk/return reads, .1 each on success.
    "get_performance_history": 0.2,
}
PER_SYMBOL_COST: dict[str, float] = {
    "get_company_info": 0.05, "export_price_series": 0.05,
    "etf_daily_price": 0.05,
}
PER_HOLDING_COST: dict[str, float] = {
    "quick_portfolio_scores": 0.1, "check_portfolio_redundancy": 0.1,
}
CONDITIONAL_COST: dict[str, tuple[float, float]] = {
    "get_financials": (0.05, 0.1), "get_stock_outlook": (0.05, 0.1),
    "macro_analyst": (5, 50), "explore_telemetry": (0.05, 0.2),
}
# Compatibility export: all 36 endpoints now have published prices. Invalid
# multiplicative inputs still enter an estimate's unpriced_endpoints.
KNOWN_UNPRICED: frozenset[str] = frozenset()
KNOWN_ENDPOINTS = frozenset(FLAT_COST) | frozenset(PER_SYMBOL_COST) | frozenset(PER_HOLDING_COST) | frozenset(CONDITIONAL_COST)

# Legacy illustrative assumption only; not verified against any current plan.
USD_PER_TOKEN = 0.20
PRICE_BASIS = "2026-10-19 published credit contract"
ASSUMPTIONS = (
    "Planning estimate assumes successful requests; inputs do not establish billed outcomes.",
    "Conditional upper bound covers known branches, not retries or omitted calls; null means incomplete pricing.",
    "USD uses an illustrative rate, not a verified subscription or overage price.",
)


@dataclass(frozen=True)
class TokenEstimate:
    # Legacy public key; unit is credits. Outward floats remain JSON compatible.
    tokens: float
    unknown_endpoints: tuple[str, ...]
    unpriced_endpoints: tuple[str, ...] = ()
    ambiguous_endpoints: tuple[str, ...] = ()
    upper_bound_tokens: float | None = None
    assumptions: tuple[str, ...] = ASSUMPTIONS
    unpriced_inputs: tuple[str, ...] = ()

    @property
    def total(self) -> float:
        return self.tokens

    def usd(self, rate: float = USD_PER_TOKEN) -> float:
        if isinstance(rate, bool) or not isinstance(rate, (float, int)):
            raise ValueError("rate must be a finite nonnegative number")
        decimal_rate = Decimal(str(rate))
        if not decimal_rate.is_finite() or decimal_rate < 0:
            raise ValueError("rate must be a finite nonnegative number")
        result = float(Decimal(str(self.total)) * decimal_rate)
        if not isfinite(result):
            raise ValueError("USD estimate exceeds finite JSON number range")
        return result


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

# The mirror of the above: namespaces known NOT to be Parallax. Without this,
# ambiguity has only one resolution, so a genuine foreign collision (HubSpot
# also exposes ``submit_feedback``) could never be cleared -- declaring HubSpot
# a Parallax alias to silence it would be a lie that starts billing its calls.
# That would rebuild the permanent-unfixable-degrade trap ``KNOWN_UNPRICED``
# exists to avoid. Both answers must be expressible.
FOREIGN_NAMESPACES: frozenset[str] = frozenset(
    part.strip().lower()
    for part in os.environ.get("PARALLAX_MCP_FOREIGN_NAMESPACES", "").split(",")
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
    ``PARALLAX_MCP_ALIASES``, is Parallax. One listed in
    ``PARALLAX_MCP_FOREIGN_NAMESPACES`` is not. A name with no MCP namespace is
    harness-local. Anything else whose bare name this table happens to know is
    reported ``ambiguous`` and billed to nobody, because the honest answer is
    that we cannot tell.

    Ambiguity is always resolvable, in whichever direction is true: declare the
    namespace an alias if it is Parallax, or foreign if it is not. Offering only
    the first would leave a real foreign collision degrading runs forever with
    no honest remedy.
    """
    if not name.startswith("mcp__"):
        return CALL_FOREIGN  # harness-local; never MCP-namespaced
    namespace = name[len("mcp__"):].rsplit("__", 1)[0].lower()
    if "parallax" in namespace or namespace in PARALLAX_ALIASES:
        return CALL_PARALLAX
    if namespace in FOREIGN_NAMESPACES:
        return CALL_FOREIGN  # operator has stated this server is not Parallax
    if bare(name) in KNOWN_ENDPOINTS:
        return CALL_AMBIGUOUS
    return CALL_FOREIGN


def is_parallax_mcp(name: str) -> bool:
    """True only when the call is definitively Parallax's.

    Ambiguous calls are excluded: this answers "may I bill this?", and the
    answer under ambiguity is no.
    """
    return classify_call(name) == CALL_PARALLAX


def _symbol_count(call_input: dict) -> int:
    symbols = call_input.get("symbol")
    if not isinstance(symbols, str) or not symbols.strip():
        raise ValueError("nonempty symbol string required")
    parts = symbols.split(",")
    if any(not part.strip() for part in parts):
        raise ValueError("empty symbol in list")
    return len(parts)


def _holdings_in(name: str, call_input: dict) -> int:
    holdings = call_input.get("holdings")
    if not isinstance(holdings, list) or not holdings:
        raise ValueError("nonempty holdings array required")
    for row in holdings:
        if not isinstance(row, dict) or not isinstance(row.get("symbol"), str) or not row["symbol"].strip():
            raise ValueError("holding symbol required")
        weight = row.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 <= weight <= 1 or not isfinite(weight):
            raise ValueError("holding weight must be finite and between zero and one")
    if all(row["weight"] == 0 for row in holdings):
        raise ValueError("all holdings have zero weight; tool stops before any lookup")
    cap = 100
    if name == "quick_portfolio_scores":
        cap = call_input.get("max_holdings", 50)
        if isinstance(cap, bool) or not isinstance(cap, (int, float)) or not 1 <= cap <= 100 or not isfinite(cap) or cap % 1 != 0:
            raise ValueError("max_holdings must be an integer from 1 to 100")
    # Selection is by weight; for an all-success request-count estimate only
    # the trimmed count matters. Surviving zero-weight rows still make requests.
    return min(len(holdings), int(cap))


def _price(name: str, args: dict) -> tuple[Decimal, Decimal]:
    """Normal all-success request cost and conditional all-success ceiling."""
    def pair(normal, upper=None):
        return Decimal(str(normal)), Decimal(str(normal if upper is None else upper))

    if name in FLAT_COST:
        if name == "get_performance_history":
            _symbol_count(args)
        return pair(FLAT_COST[name])
    if name in PER_SYMBOL_COST:
        return pair(Decimal(str(PER_SYMBOL_COST[name])) * _symbol_count(args))
    if name in PER_HOLDING_COST:
        return pair(Decimal(str(PER_HOLDING_COST[name])) * _holdings_in(name, args))
    if name == "get_financials":
        n = _symbol_count(args)
        statement = args.get("statement", "summary")
        if not isinstance(statement, str) or statement not in {"income", "balance_sheet", "cash_flow", "ratios", "summary"}:
            raise ValueError("unsupported financial statement")
        latest = args.get("latest", False)
        if not isinstance(latest, bool):
            raise ValueError("latest must be boolean")
        rate = Decimal("0.1") if latest and statement in {"income", "balance_sheet", "cash_flow"} else Decimal("0.05")
        return pair(rate * n)
    if name == "get_stock_outlook":
        aspect = args.get("aspect", "analyst_targets")
        if not isinstance(aspect, str) or aspect not in {"analyst_targets", "recommendations", "risk_return", "dividends"}:
            raise ValueError("unsupported outlook aspect")
        n = _symbol_count(args)
        return pair(Decimal("0.05") * n if aspect == "dividends" else ("0.1" if aspect == "risk_return" else "0.05"))
    if name == "macro_analyst":
        market = args.get("market")
        if not isinstance(market, str) or not market.strip() or len(market) > 64:
            raise ValueError("nonempty market string of at most 64 characters required")
        component = args.get("component")
        if component is None and "component" not in args:
            return pair(5, 50)
        if not isinstance(component, str) or component not in {"macro_indicators", "tactical", "fixed_income", "currency", "sectors", "sector_positioning", "liquidity", "news", "factors"}:
            raise ValueError("unsupported macro component")
        return pair(5)
    if name == "explore_telemetry":
        if args.get("stock") is not None:
            return pair("0.1")
        if args.get("basket") is not None:
            return pair("0.05", "0.2")
        return pair("0.05")
    raise ValueError("no published price")


def estimate(tool_calls) -> TokenEstimate:
    """Estimate current published credits without asserting observed billing.

    Invalid pricing inputs are omitted with explicit unpriced markers, never
    silently treated as free. Unknown endpoints and unattributed namespaces are
    reported separately. This validates pricing dimensions, not entire schemas.
    """
    normal = Decimal("0")
    upper = Decimal("0")
    unknown: set[str] = set()
    unpriced: set[str] = set()
    ambiguous: set[str] = set()
    invalid: list[str] = []
    for call in tool_calls:
        kind = classify_call(call.name)
        if kind == CALL_FOREIGN:
            continue
        if kind == CALL_AMBIGUOUS:
            ambiguous.add(call.name)
            continue
        name = bare(call.name)
        if name not in KNOWN_ENDPOINTS:
            unknown.add(name)
            continue
        try:
            args = call.input
            if not isinstance(args, dict):
                raise ValueError("input must be an object")
            cost, ceiling = _price(name, args)
        except ValueError as error:
            unpriced.add(name)
            invalid.append(f"{name}: {error}")
            continue
        normal += cost
        upper += ceiling
    return TokenEstimate(
        tokens=float(normal), unknown_endpoints=tuple(sorted(unknown)),
        unpriced_endpoints=tuple(sorted(unpriced)), ambiguous_endpoints=tuple(sorted(ambiguous)),
        upper_bound_tokens=None if unknown or unpriced or ambiguous else float(upper),
        unpriced_inputs=tuple(invalid),
    )
