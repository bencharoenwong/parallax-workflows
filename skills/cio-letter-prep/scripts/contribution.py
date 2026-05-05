"""
Daily contribution math for the CIO letter prep skill.

Pure-Python (stdlib only) helper that computes per-holding contribution to
portfolio total return over a period by reconstructing daily portfolio
weights from a prior snapshot plus a trade log, then summing daily
contributions across the period.

Math approach
-------------

For each return-day d in (period_start, period_end]:
    r_i[d] = price_i[d] / price_i[d-1] - 1                  (per-holding daily return)
    c_i[d] = w_i[d] * r_i[d]                                (per-holding daily contribution)
    r_p[d] = sum_i c_i[d]                                   (portfolio daily return)

Period totals (ARITHMETIC sums, NOT geometric compounding):
    contribution[i] = sum_d c_i[d]
    portfolio_total_return = sum_d r_p[d]

By construction, sum_i contribution[i] == portfolio_total_return exactly
(modulo floating-point error). The reconciliation gate enforces this within
a tolerance and raises ReconciliationError on violation.

We use ARITHMETIC summing rather than geometric linking on purpose: it makes
the per-holding decomposition clean (sum-of-daily-contributions == portfolio
total) and avoids the linking-error correction that geometric attribution
schemes (Carino, Menchero, etc.) require. The reported portfolio_total_return
is therefore the arithmetic sum of daily portfolio returns, NOT the
geometrically compounded period return; for short letter periods (one month)
the gap is small but it is non-zero and callers should be aware.

Total-return prices assumption
------------------------------

`daily_prices` MUST be total-return prices (dividends reinvested). With
TR-prices the daily-return formula price[t]/price[t-1] - 1 already captures
both price moves and dividend yield. Supplying non-TR (raw close) prices
will under-state holding returns by the dividend amount and break the
reconciliation against true portfolio total return. See
test_non_total_return_prices_break_math_negative_control for a concrete demo.

Trade convention
----------------

Each entry of `trade_log` is a dict with keys:
    symbol       : str (RIC)
    action       : str in {'add', 'trim', 'enter', 'exit'}
    date         : ISO 'YYYY-MM-DD' string
    weight_delta : signed float

A trade with date D applies AFTER day D's close: the new weights take effect
for the return computed from D to the next available date (return-day D+1).
Therefore:
  * "Added on date D" => new holding earns returns from the day AFTER D.
  * "Exited on date D" => exited holding earns its last return on day D, then
    drops to weight 0 from D+1 onward.

Trade weight_deltas in the same period must sum to zero across all symbols
(weight redistribution preserves total = 1.0).
"""

from __future__ import annotations

from datetime import date as _date_cls
from typing import Iterable

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

DEFAULT_RECONCILIATION_TOLERANCE: float = 1e-4   # 1 basis point
DEFAULT_WEIGHT_SUM_TOLERANCE: float = 1e-3       # 10 basis points on weight sums

VALID_TRADE_ACTIONS: frozenset[str] = frozenset({"add", "trim", "enter", "exit"})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ReconciliationError(Exception):
    """Raised when sum-of-contributions diverges from portfolio total return.

    Attributes
    ----------
    diff : float
        sum(contributions) - portfolio_total_return
    tolerance : float
        tolerance threshold that was violated
    """

    def __init__(self, diff: float, tolerance: float) -> None:
        self.diff = diff
        self.tolerance = tolerance
        super().__init__(
            f"Contribution reconciliation failed: |diff|={abs(diff):.3e} > "
            f"tolerance={tolerance:.3e}"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def daily_contribution(
    prior_portfolio: dict[str, float],
    current_portfolio: dict[str, float],
    trade_log: list[dict],
    daily_prices: dict[str, dict[str, float]],
    period_start: str,
    period_end: str,
    reconciliation_tolerance: float = DEFAULT_RECONCILIATION_TOLERANCE,
) -> dict:
    """Compute per-holding contribution to portfolio total return.

    See module docstring for math approach, total-return-prices assumption,
    and trade convention.

    Parameters
    ----------
    prior_portfolio : dict[str, float]
        {symbol: weight} at period start. Weights must sum to ~1.0
        (within DEFAULT_WEIGHT_SUM_TOLERANCE).
    current_portfolio : dict[str, float]
        {symbol: weight} at period end. Sum tolerance same as prior.
    trade_log : list[dict]
        Ordered (chronologically) list of trades. Each entry has
        keys 'symbol', 'action', 'date', 'weight_delta'. Weight deltas
        on the same date should sum to zero across symbols (the function
        does NOT enforce this strictly; weights are recomputed daily and
        the reconciliation gate catches material drift).
    daily_prices : dict[str, dict[str, float]]
        {symbol: {ISO_date: total_return_price}}. Every symbol that
        appears in prior_portfolio, in current_portfolio, or as the
        'symbol' of any trade in trade_log MUST have an entry covering
        all required dates.
    period_start : str
        ISO 'YYYY-MM-DD'. First date of the period (no return computed
        for this date — only used as the prior price for return-day 1).
    period_end : str
        ISO 'YYYY-MM-DD'. Last date of the period.
    reconciliation_tolerance : float
        Tolerance for the sum(contributions) == portfolio_total_return
        check. Defaults to DEFAULT_RECONCILIATION_TOLERANCE (1bp).

    Returns
    -------
    dict
        {
            'contributions': {symbol: contribution_decimal, ...},
            'portfolio_total_return': float,  # arithmetic sum of daily portfolio returns
            'reconciliation_diff': float,      # sum(contributions) - portfolio_total_return
        }

    Raises
    ------
    ValueError
        On input shape / consistency violations:
        - period_end before period_start
        - prior or current weights don't sum to ~1.0
        - missing prices for a held / traded holding
        - trade_log not chronologically ordered
        - invalid action vocabulary
        - trade dates outside [period_start, period_end]
    ReconciliationError
        If abs(sum(contributions) - portfolio_total_return) > tolerance.
    """
    # ---- 1. Validate dates ------------------------------------------------
    start_d = _parse_iso(period_start, field="period_start")
    end_d = _parse_iso(period_end, field="period_end")
    if end_d < start_d:
        raise ValueError(
            f"period_end ({period_end}) is before period_start ({period_start})"
        )

    # ---- 2. Validate weights sum to ~1.0 ----------------------------------
    _validate_weights_sum(prior_portfolio, "prior_portfolio")
    _validate_weights_sum(current_portfolio, "current_portfolio")

    # ---- 3. Validate trade_log structure & ordering -----------------------
    _validate_trade_log(trade_log, start_d, end_d)

    # ---- 4. Build the universe of symbols and required dates --------------
    symbols: set[str] = set()
    symbols.update(prior_portfolio.keys())
    symbols.update(current_portfolio.keys())
    for trade in trade_log:
        symbols.add(trade["symbol"])

    # Build the trading-day timeline: the union of date keys present in any
    # holding's price series, restricted to [period_start, period_end].
    all_dates: set[str] = set()
    for sym, series in daily_prices.items():
        for d_str in series.keys():
            d = _parse_iso(d_str, field=f"daily_prices['{sym}']")
            if start_d <= d <= end_d:
                all_dates.add(d_str)
    timeline = sorted(all_dates, key=_parse_iso_unchecked)

    if len(timeline) < 2:
        raise ValueError(
            "Need at least 2 dated prices in [period_start, period_end] to compute "
            "any returns; got "
            f"{len(timeline)}"
        )
    if timeline[0] != period_start:
        raise ValueError(
            f"period_start ({period_start}) is not present in any daily_prices series"
        )

    # ---- 5. Validate every involved symbol has prices for all timeline dates
    for sym in symbols:
        series = daily_prices.get(sym)
        if series is None:
            raise ValueError(
                f"missing daily_prices entry for symbol '{sym}' (held or traded)"
            )
        for d_str in timeline:
            if d_str not in series:
                raise ValueError(
                    f"missing price for symbol '{sym}' on date {d_str}"
                )

    # ---- 6. Group trades by date for fast lookup --------------------------
    trades_by_date: dict[str, list[dict]] = {}
    for trade in trade_log:
        trades_by_date.setdefault(trade["date"], []).append(trade)

    # ---- 7. Walk the timeline, accumulating contributions -----------------
    # weights[symbol] is the weight effective for the next return day's move.
    weights: dict[str, float] = {s: 0.0 for s in symbols}
    for sym, w in prior_portfolio.items():
        weights[sym] = w

    # Trades dated period_start apply AFTER period_start's close, which is
    # BEFORE return-day 1, so we apply them up-front before walking.
    for trade in trades_by_date.get(period_start, []):
        sym = trade["symbol"]
        weights[sym] = weights.get(sym, 0.0) + trade["weight_delta"]

    contributions: dict[str, float] = {s: 0.0 for s in symbols}
    portfolio_total_return: float = 0.0

    for i in range(1, len(timeline)):
        prev_date = timeline[i - 1]
        cur_date = timeline[i]

        # Returns on day cur_date use weights effective DURING the move from
        # prev_date to cur_date — i.e., the post-trade weights from the
        # previous iteration (or the initial weights for i==1).
        for sym in symbols:
            p_prev = daily_prices[sym][prev_date]
            p_cur = daily_prices[sym][cur_date]
            if p_prev == 0:
                raise ValueError(
                    f"price for '{sym}' on {prev_date} is zero; cannot compute return"
                )
            r = p_cur / p_prev - 1.0
            c = weights[sym] * r
            contributions[sym] += c
            portfolio_total_return += c

        # After the day's return, apply trades dated cur_date so they take
        # effect for the NEXT iteration's return computation.
        for trade in trades_by_date.get(cur_date, []):
            sym = trade["symbol"]
            weights[sym] = weights.get(sym, 0.0) + trade["weight_delta"]

    # ---- 8. Reconciliation gate ------------------------------------------
    diff = sum(contributions.values()) - portfolio_total_return
    if abs(diff) > reconciliation_tolerance:
        raise ReconciliationError(diff=diff, tolerance=reconciliation_tolerance)

    return {
        "contributions": contributions,
        "portfolio_total_return": portfolio_total_return,
        "reconciliation_diff": diff,
    }


def validate_contributions(
    contributions: dict[str, float],
    portfolio_total_return: float,
    tolerance: float = DEFAULT_RECONCILIATION_TOLERANCE,
) -> float:
    """Standalone reconciliation gate.

    Useful when an upstream caller wants to re-check a (possibly mutated)
    contributions dict against a previously-computed portfolio total.

    Returns
    -------
    float
        The signed diff = sum(contributions) - portfolio_total_return.
        Always returned when within tolerance.

    Raises
    ------
    ReconciliationError
        If abs(diff) > tolerance.
    """
    diff = sum(contributions.values()) - portfolio_total_return
    if abs(diff) > tolerance:
        raise ReconciliationError(diff=diff, tolerance=tolerance)
    return diff


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_iso(s: str, *, field: str) -> _date_cls:
    """Parse ISO YYYY-MM-DD; raise ValueError with a helpful field name."""
    try:
        return _date_cls.fromisoformat(s)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}: invalid ISO date '{s}': {exc}") from exc


def _parse_iso_unchecked(s: str) -> _date_cls:
    return _date_cls.fromisoformat(s)


def _validate_weights_sum(weights: dict[str, float], label: str) -> None:
    if not weights:
        raise ValueError(f"{label} is empty")
    total = sum(weights.values())
    if abs(total - 1.0) > DEFAULT_WEIGHT_SUM_TOLERANCE:
        raise ValueError(
            f"{label} weights sum to {total:.6f}, expected ~1.0 "
            f"(tolerance {DEFAULT_WEIGHT_SUM_TOLERANCE})"
        )


def _validate_trade_log(
    trade_log: Iterable[dict],
    start_d: _date_cls,
    end_d: _date_cls,
) -> None:
    prev_d: _date_cls | None = None
    for i, trade in enumerate(trade_log):
        for key in ("symbol", "action", "date", "weight_delta"):
            if key not in trade:
                raise ValueError(f"trade_log[{i}] missing key '{key}'")
        action = trade["action"]
        if action not in VALID_TRADE_ACTIONS:
            raise ValueError(
                f"trade_log[{i}] action '{action}' not in {sorted(VALID_TRADE_ACTIONS)}"
            )
        d = _parse_iso(trade["date"], field=f"trade_log[{i}].date")
        if d < start_d or d > end_d:
            raise ValueError(
                f"trade_log[{i}] date {trade['date']} outside period "
                f"[{start_d.isoformat()}, {end_d.isoformat()}]"
            )
        if prev_d is not None and d < prev_d:
            raise ValueError(
                f"trade_log not in chronological order at index {i}: "
                f"{trade['date']} < previous {prev_d.isoformat()}"
            )
        prev_d = d


