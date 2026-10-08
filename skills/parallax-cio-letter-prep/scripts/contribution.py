"""
Daily contribution math for the CIO letter prep skill.

Pure-Python (stdlib only) helper that computes per-holding contribution to
portfolio total return over a period by reconstructing daily portfolio
values from a prior snapshot plus a trade log, then summing the per-day
dollar P&L across the period.

Math approach — replicates the server's method
-------------------------------------------------

This module replicates, in weight space, the same method the Parallax
server-side analytics engine uses to turn a portfolio snapshot plus a
trade log into a value path:

  * Between rebalances, each holding is buy-and-hold: its value compounds
    daily by `value[d] = value[d-1] * (1 + r[d])`, so weights DRIFT with
    relative performance rather than staying fixed.
  * On a rebalance date D, D's return is applied to the pre-rebalance
    (drifted) values FIRST; only after that does the book reweight to the
    new target weights — i.e. the trade is applied after D's close, exactly
    like the server.
  * Portfolio value is the sum of holding values. Per-holding contribution
    is that holding's dollar P&L (the sum of its own daily price_pl terms,
    which EXCLUDES any value transferred in or out at a rebalance — a
    rebalance moves value between holdings, it does not create return).
  * `portfolio_total_return = final_total_value / initial_total_value - 1`,
    computed independently of the per-holding P&L sum (see "Reconciliation
    gate" below) — the same identity the server reports.

For each return-day d in (period_start, period_end]:
    r_i[d] = (price_i[d] + dividend_i[d]) / price_i[d-1] - 1
    price_pl_i[d] = value_i[d-1] * r_i[d]
    value_i[d] = value_i[d-1] + price_pl_i[d]           (drift)
    # ... then, only on a date with trades dated d:
    total_value[d] = sum_i value_i[d]                    (post-return, pre-rebalance)
    target_weight_i[d] = target_weight_i[d-1] + weight_delta_i[d]
    value_i[d] = target_weight_i[d] * total_value[d]      (reweight, after d's close)

contribution[i] = sum_d price_pl_i[d]
portfolio_total_return = sum_i value_i[final] / sum_i value_i[initial] - 1

Because a rebalance only ever MOVES value between holdings (it preserves
the post-return total as long as the target weights it reweights to sum to
1.0), `sum_i contribution[i]` telescopes to exactly
`sum_i value_i[final] - sum_i value_i[initial]` — the same total return the
server reports, to floating-point precision, not merely within a tolerance
that papers over an arithmetic-vs-geometric gap. There is no such gap here:
this module compounds, it does not sum arithmetically.

Reconciliation gate
--------------------

`contributions` is accumulated as the running sum of each day's
`price_pl_i[d]` terms. `portfolio_total_return` is derived SEPARATELY, from
the literal end state of the per-holding `value` dict (which also reflects
every rebalance, including a malformed one). The two are therefore
independent accumulations of the same underlying walk, and the gate
(`|sum(contributions) - portfolio_total_return| > 1bp` -> `ReconciliationError`)
is a real identity check: it is unreachable for a clean input (any book with
no trades, or whose trade deltas sum to zero on net), and it fires whenever
a rebalance's target weights do not sum to 1.0 at the time they are applied
even transiently — because that rebalance manufactures or destroys value
that the per-holding P&L sum never counted. See
`test_reconciliation_gate_fires_on_a_transient_weight_imbalance_that_nets_to_zero`
in `test_contribution_edges.py` for a worked, reachable example.

Price-return prices contract
-----------------------------

`daily_prices` MUST be price-return prices: raw daily closes, with no
dividend adjustment. This is what the upstream price tool actually returns,
so callers should pass its output directly. With price-return prices and no
`dividend_schedule` (see below), the daily-return formula
price[t]/price[t-1] - 1 captures price moves only — it does NOT capture
dividend yield, so the reported portfolio_total_return is a price-only
return. Supplying dividend-adjusted / total-return prices directly as
`daily_prices` instead of using `dividend_schedule` is still wrong under this
contract: it bakes the dividend into a smoothed price ramp instead of the
discrete jump it actually is on the ex-date, and if a `dividend_schedule` is
also supplied for the same symbol, the dividend is counted twice. See
test_total_return_style_prices_plus_dividend_schedule_double_counts_negative_control
for a concrete demo.

Calendar handling — forward-fill, zero return
-----------------------------------------------

The timeline is the union of every symbol's price dates in
[period_start, period_end], plus `period_start` itself unconditionally.
Every symbol involved MUST have a price AT OR BEFORE `period_start` —
BUG-004: if `period_start` itself falls on a weekend or a single-market
holiday with no literal close for a symbol, its `period_start` anchor
price is forward-filled from that symbol's own last known close on or
before `period_start` (dates strictly before `period_start` are used ONLY
to seed this anchor; they never become timeline dates and never generate
a return of their own). The function raises only when a symbol has no
close at or before `period_start` at all — there is nothing earlier to
forward-fill from in that case. Callers (SKILL.md) should pass every
price `export_price_series` returns for the trailing window, including
dates before `period_start`, rather than slicing them away — slicing to
exactly `[period_start, period_end]` would remove the very data this
forward-fill needs when `period_start` is not a trading day.

For any LATER timeline date on which a given symbol has no price of its
own — a vendor gap, a market holiday the feed skips, a different exchange
calendar — that symbol's close is carried forward from its last known
price and its return for that day is exactly 0, matching the server's
calendar-daily grid with forward-filled closes.

Split handling for `daily_prices` closes themselves is UNVERIFIED
(BUG-010): whether `export_price_series` returns split-adjusted history is
not established here. If a stock split occurs for a holding during the
period, do not feed its raw post-split closes into this function expecting
a correct answer — the price-return formula would see a spurious jump that
is not a real return. Mark that holding audit-unchecked instead of
guessing a split-adjustment factor.

Dividend schedule (optional) — total return, not price-only
-------------------------------------------------------------

Live verification against the Parallax server (single-holding VZ.N book,
2026-07-06..2026-07-14, ex-dividend 2026-07-10) established that the
server-side fields this skill reconciles against (`total_price_pl`,
`total_pl`, `total_return`, per-row `price_pl`) are TOTAL-RETURN fields:
dividends are included (added to the price on the ex-date, then carried
forward), and only FX is isolated separately (`total_fx_pl` plus a
price x FX cross term).

To compute a like-for-like local total return, pass the optional
`dividend_schedule` parameter: `{symbol: {ex_date: cash_amount}}`, cash
amount in the holding's own listing currency, keyed by the SAME ex-date
convention the server uses (`get_stock_outlook(aspect="dividends")`'s
`effective_date`). On each ex-date present in the schedule, the daily-return
formula becomes `(price[t] + dividend[t]) / price[t-1] - 1` instead of the
plain price-return formula; every other day is unaffected. BUG-009: an
ex_date that is not an actual close for that symbol is SHIFTED to that
symbol's next actual close in the period (the server includes it via the
vendor return on the next trading day it has a close); with no later
close to shift to, the dividend is UNAPPLIED. Both cases are reported in
the return value (`dividends_shifted`, `dividends_unapplied`) rather than
raising — see `_resolve_dividend_schedule`. Omitting `dividend_schedule`
(the default, `None` -> treated as empty) preserves the original
price-only behavior documented above; it is not removed, since not every
caller has dividend data to supply.

`portfolio_total_return` with `dividend_schedule` supplied is a total
return BEFORE FX. It is directly comparable to `total_price_pl /
initial_value` ONLY for a single-currency book (every holding listed in
the portfolio's base currency, equivalently `total_fx_pl == 0`). On a
multi-currency book, the server's `total_price_pl` carries an
FX-weight-drift cross term this module has no way to replicate: the
server's internal base-currency weights drift with FX as well as with
price, so `starting_value_base x changepercent` is not the same quantity
as this module's FX-free `value[sym] x r`. A local-vs-server gap on a
multi-currency book is therefore NOT comparable at the same tolerance as a
single-currency book's exact gate — see SKILL.md Step 3 for the
owner-decided split (exact halt at 25bp single-currency; informational,
never a halt, multi-currency).

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

BUG-003: D need not be a date in `timeline` (a weekend, a holiday the price
feed skips). Such a trade is never dropped: it is bucketed under the latest
`timeline` date <= D and applied after THAT date's close, which is exactly
equivalent to the server's calendar-daily rebalance (reweighting on D's own
calendar date using D's forward-filled, zero return, so the new weights earn
nothing until the next date that actually has a return).

Trade weight_deltas in the same period must sum to zero across all symbols
(weight redistribution preserves total = 1.0). This is NOT enforced
strictly by this function (see docstring of `daily_contribution`); the
reconciliation gate above is what catches material drift from it.
"""

from __future__ import annotations

import math
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
    dividend_schedule: dict[str, dict[str, float]] | None = None,
    reconciliation_tolerance: float = DEFAULT_RECONCILIATION_TOLERANCE,
) -> dict:
    """Compute per-holding contribution to portfolio total return.

    See module docstring for the compounding/rebalancing method this
    replicates from the server, the price-return-prices contract, the
    calendar forward-fill rule, the optional dividend_schedule / total-return
    extension, and the trade convention.

    Parameters
    ----------
    prior_portfolio : dict[str, float]
        {symbol: weight} at period start. Weights must sum to ~1.0
        (within DEFAULT_WEIGHT_SUM_TOLERANCE).
    current_portfolio : dict[str, float]
        {symbol: weight} at period end. This is the DECLARED target weight
        after the last trade (`prior_portfolio` walked forward through
        `trade_log`), not the drifted/compounded ending weight — same
        convention `analyze_portfolio`'s multi-date `portfolio` array uses.
        Sum tolerance same as prior.
    trade_log : list[dict]
        Ordered (chronologically) list of trades. Each entry has
        keys 'symbol', 'action', 'date', 'weight_delta' (a finite,
        non-bool number — BUG-008). Weight deltas on the same date should
        sum to zero across symbols (the function does NOT enforce this
        strictly; the reconciliation gate below catches material drift
        from it). A trade's 'date' need not be a date any symbol has a
        price on (BUG-003): it is applied after the close of the latest
        price-bearing date at or before it — see module docstring.
    daily_prices : dict[str, dict[str, float]]
        {symbol: {ISO_date: price_return_price}}. Raw daily close, no
        dividend adjustment. Every symbol that appears in prior_portfolio,
        in current_portfolio, or as the 'symbol' of any trade in trade_log
        MUST have an entry with a price AT OR BEFORE `period_start`
        (BUG-004) — if `period_start` itself has no literal close for a
        symbol, its anchor price is forward-filled from that symbol's own
        last close on or before `period_start`. Any LATER timeline date a
        symbol lacks is forward-filled from its last known price (zero
        return that day) rather than erroring.
    period_start : str
        ISO 'YYYY-MM-DD'. First date of the period (no return computed
        for this date — only used as the prior price for return-day 1).
    period_end : str
        ISO 'YYYY-MM-DD'. Last date of the period.
    dividend_schedule : dict[str, dict[str, float]] | None
        Optional. {symbol: {ex_date: cash_amount}}, cash amount in the
        holding's own listing currency. ex_date MUST fall strictly after
        period_start and on/before period_end. Cash amounts must be
        finite and non-negative. When ex_date is not an actual close for
        that symbol, the dividend is SHIFTED to that symbol's next actual
        close in the period, or UNAPPLIED if none exists (BUG-009; see
        `dividends_shifted` / `dividends_unapplied` in Returns, and the
        module docstring) — this no longer raises. When applied, that
        day's return becomes (price + cash_amount) / price[prior_date] - 1
        instead of the plain price-return formula, turning the reported
        portfolio_total_return into a total return before FX (see module
        docstring — single-currency books only; see SKILL.md for
        multi-currency). Defaults to None, treated as empty (no dividends
        applied) — the original price-only behavior.
    reconciliation_tolerance : float
        Tolerance for the sum(contributions) == portfolio_total_return
        check. Defaults to DEFAULT_RECONCILIATION_TOLERANCE (1bp).

    Returns
    -------
    dict
        {
            'contributions': {symbol: contribution_decimal, ...},
            'portfolio_total_return': float,  # final_total/initial_total - 1
            'reconciliation_diff': float,      # sum(contributions) - portfolio_total_return
            'dividends_shifted': {symbol: [(ex_date, applied_date), ...]},
            'dividends_unapplied': {symbol: [ex_date, ...]},
        }

    Raises
    ------
    ValueError
        On input shape / consistency violations:
        - period_end before period_start
        - prior or current weights don't sum to ~1.0 (or are NaN)
        - missing prices for a held / traded holding, or no price at or
          before period_start for an involved symbol (BUG-004)
        - trade_log not chronologically ordered
        - invalid action vocabulary
        - non-numeric, bool, or non-finite trade weight_delta (BUG-008)
        - trade dates outside [period_start, period_end]
        - a zero close on a symbol that carries nonzero weight or value
          (a zero-weight, zero-value holding with a zero close does not
          raise — BUG-008)
        - dividend_schedule naming an unknown symbol, a non-finite or
          negative cash amount, or an ex_date outside
          (period_start, period_end]
        - current_portfolio inconsistent with prior_portfolio + trade_log
    ReconciliationError
        If abs(sum(contributions) - portfolio_total_return) > tolerance, or
        if that diff is not finite (a NaN diff is never treated as passing).
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
    # holding's price series, restricted to [period_start, period_end], PLUS
    # period_start itself unconditionally (BUG-004: period_start may fall on
    # a weekend or a market holiday with no literal close in any symbol's
    # series — it is still the zero-return anchor date, seeded below from
    # each symbol's last close AT OR BEFORE period_start, exactly like a
    # later in-period gap is forward-filled).
    all_dates: set[str] = {period_start}
    for sym, series in daily_prices.items():
        for d_str in series.keys():
            d = _parse_iso(d_str, field=f"daily_prices['{sym}']")
            if start_d <= d <= end_d:
                all_dates.add(d_str)
    timeline = sorted(all_dates, key=lambda d: _parse_iso(d, field="daily_prices"))

    if len(timeline) < 2:
        raise ValueError(
            "Need at least 2 dated prices in [period_start, period_end] to compute "
            "any returns; got "
            f"{len(timeline)}"
        )
    # timeline[0] == period_start always holds here because period_start was
    # inserted unconditionally above and every other candidate is filtered to
    # start_d <= d.

    # ---- 5. Every involved symbol must have a price ON OR BEFORE
    # period_start, used to seed its period_start anchor price (BUG-004).
    # period_start itself need not carry a literal close for a symbol — a
    # weekend or a single-market holiday forward-fills from that symbol's
    # own last known close before period_start, same as any later gap (step
    # 7). The function raises only when a symbol has no close at or before
    # period_start at all: there is nothing earlier to forward-fill from.
    # Dates strictly before period_start are used ONLY for this seed — they
    # never enter `timeline` and never generate a return of their own.
    seed_price: dict[str, float] = {}
    for sym in symbols:
        series = daily_prices.get(sym)
        if series is None:
            raise ValueError(
                f"missing daily_prices entry for symbol '{sym}' (held or traded)"
            )
        seed_candidates = [
            d_str for d_str in series
            if _parse_iso(d_str, field=f"daily_prices['{sym}']") <= start_d
        ]
        if not seed_candidates:
            raise ValueError(
                f"missing price for symbol '{sym}' on or before {period_start} "
                "(period_start) — there is no earlier price to forward-fill from"
            )
        latest_seed = max(
            seed_candidates, key=lambda d: _parse_iso(d, field=f"daily_prices['{sym}']")
        )
        seed_price[sym] = series[latest_seed]

    # ---- 5b. Validate + resolve dividend_schedule (optional; BUG-009) -----
    dividend_schedule = dividend_schedule or {}
    resolved_dividends, dividends_shifted, dividends_unapplied = _resolve_dividend_schedule(
        dividend_schedule, symbols, daily_prices, start_d, end_d
    )

    # ---- 6. Group trades by EFFECTIVE timeline date (BUG-003) ------------
    # A trade dated on a non-trading day (weekend, a holiday the feed skips)
    # has no corresponding entry in `timeline`, so grouping by its literal
    # date would make it un-appliable and the trade would be silently
    # dropped. The server's calendar-daily rebalance resolves this by
    # reweighting the book on the trade's own calendar date using that
    # date's return (which forward-fills to 0 on a non-trading day) — the
    # net effect is identical to applying the trade "after the close of the
    # last timeline date on or before the trade's date", which is what this
    # module (having no notion of a non-trading calendar day in `timeline`)
    # replicates directly: every trade is bucketed under the latest
    # timeline date <= its own date. A trade dated exactly on a timeline
    # date (the common case) maps to itself, so this is a no-op then.
    timeline_parsed = [_parse_iso(d, field="daily_prices") for d in timeline]

    def _effective_timeline_date(trade_date: str) -> str:
        d = _parse_iso(trade_date, field="trade_log.date")
        idx = None
        for i, td in enumerate(timeline_parsed):
            if td <= d:
                idx = i
            else:
                break
        if idx is None:
            # Unreachable given _validate_trade_log's bounds check (every
            # trade date is >= start_d == timeline[0]), kept as a defensive
            # guard rather than a silent fallback.
            raise ValueError(
                f"trade_log date {trade_date} is before the earliest timeline "
                f"date {timeline[0]}"
            )
        return timeline[idx]

    trades_by_date: dict[str, list[dict]] = {}
    for trade in trade_log:
        effective_date = _effective_timeline_date(trade["date"])
        trades_by_date.setdefault(effective_date, []).append(trade)

    # ---- 7. Walk the timeline, compounding per-holding values and
    # reweighting on trade dates — see module docstring.
    #
    # `target_weight` is the DECLARED weight (prior_portfolio walked through
    # trade_log deltas); it is what current_portfolio is cross-checked
    # against (step 7b) and what a rebalance reweights `value` to.
    # `value` is the actual compounding per-holding value, normalized so the
    # portfolio's total starts at exactly 1.0 (the ~1e-3 rounding slop
    # `prior_portfolio` is allowed to carry is snapped to 1.0 here so a
    # rebalance's `target_weight * total_value` reweight is dimensionally
    # exact rather than leaking that slop into every subsequent rebalance).
    initial_total = sum(prior_portfolio.values())
    scale = 1.0 / initial_total

    target_weight: dict[str, float] = {s: 0.0 for s in symbols}
    for sym, w in prior_portfolio.items():
        target_weight[sym] = w * scale
    value: dict[str, float] = dict(target_weight)

    last_price: dict[str, float] = dict(seed_price)

    # Trades dated period_start apply AFTER period_start's close, which is
    # BEFORE return-day 1, so we apply them (and the resulting reweight)
    # up-front before walking.
    start_trades = trades_by_date.get(period_start, [])
    if start_trades:
        for trade in start_trades:
            sym = trade["symbol"]
            target_weight[sym] = target_weight.get(sym, 0.0) + trade["weight_delta"]
        total_value_t = sum(value.values())
        for sym in symbols:
            value[sym] = target_weight.get(sym, 0.0) * total_value_t

    contributions: dict[str, float] = {s: 0.0 for s in symbols}

    for i in range(1, len(timeline)):
        cur_date = timeline[i]

        for sym in symbols:
            series = daily_prices[sym]
            p_prev = last_price[sym]
            if cur_date in series:
                p_cur = series[cur_date]
                last_price[sym] = p_cur
            else:
                # Forward-fill: no price for this symbol on this calendar
                # date (vendor gap, holiday the feed skips, different
                # exchange calendar) — carry the last known close forward,
                # which makes this day's return exactly 0 for this symbol.
                p_cur = p_prev
                last_price[sym] = p_cur

            if p_prev == 0:
                if value[sym] == 0.0 and target_weight.get(sym, 0.0) == 0.0:
                    # BUG-008: a zero-weight holding carrying a zero close
                    # (e.g. a placeholder row for a symbol never actually
                    # held in this window) has no value for any return to
                    # apply to — 0 * r is 0 regardless of r, so there is
                    # nothing to divide by and nothing to raise about.
                    continue
                raise ValueError(
                    f"price for '{sym}' is zero (as of its last known close); "
                    f"cannot compute the return into {cur_date}"
                )

            dividend = resolved_dividends.get(sym, {}).get(cur_date, 0.0)
            r = (p_cur + dividend) / p_prev - 1.0
            price_pl = value[sym] * r
            contributions[sym] += price_pl
            value[sym] += price_pl  # value_i[t] = value_i[t-1] * (1 + r)

        # After the day's return, apply any trades dated cur_date: reweight
        # the post-return (pre-rebalance) total to the new target weights.
        # This is the "trade after D's close" convention, and it is also
        # exactly where a target_weight sum that drifts away from 1.0
        # manufactures or destroys value — see the reconciliation-gate
        # section of the module docstring.
        day_trades = trades_by_date.get(cur_date, [])
        if day_trades:
            total_value_t = sum(value.values())
            for trade in day_trades:
                sym = trade["symbol"]
                target_weight[sym] = target_weight.get(sym, 0.0) + trade["weight_delta"]
            for sym in symbols:
                value[sym] = target_weight.get(sym, 0.0) * total_value_t

    # ---- 7b. Cross-check the DECLARED ending weights vs current_portfolio
    # `target_weight` is the ending state implied by prior_portfolio +
    # trade_log, walked forward with no drift (the same convention
    # `current_portfolio` is defined under). If the two disagree by more
    # than DEFAULT_WEIGHT_SUM_TOLERANCE for any symbol present in either
    # dict, the inputs are internally inconsistent — fail loudly rather than
    # silently letting sub-tolerance trade-log drift accumulate.
    cross_check_symbols = set(target_weight.keys()) | set(current_portfolio.keys())
    for sym in cross_check_symbols:
        reconstructed = target_weight.get(sym, 0.0)
        claimed = current_portfolio.get(sym, 0.0)
        diff = reconstructed - claimed
        if abs(diff) > DEFAULT_WEIGHT_SUM_TOLERANCE:
            raise ValueError(
                f"current_portfolio inconsistent with prior_portfolio + trade_log "
                f"for symbol '{sym}': reconstructed weight {reconstructed:.6f} vs "
                f"claimed {claimed:.6f} (diff={diff:+.6f}, "
                f"tolerance={DEFAULT_WEIGHT_SUM_TOLERANCE})"
            )

    # ---- 8. Reconciliation gate ------------------------------------------
    # portfolio_total_return is derived from the literal end state of
    # `value` — independently of the running `contributions` sum above —
    # so this is a real identity check, not a tautology. See the
    # reconciliation-gate section of the module docstring.
    final_total = sum(value.values())
    portfolio_total_return = final_total - 1.0
    diff = sum(contributions.values()) - portfolio_total_return
    if not math.isfinite(diff) or abs(diff) > reconciliation_tolerance:
        raise ReconciliationError(diff=diff, tolerance=reconciliation_tolerance)

    return {
        "contributions": contributions,
        "portfolio_total_return": portfolio_total_return,
        "reconciliation_diff": diff,
        # BUG-009: additive — present even when empty ({}), so callers can
        # unconditionally inspect them without a KeyError.
        "dividends_shifted": dividends_shifted,
        "dividends_unapplied": dividends_unapplied,
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
        If abs(diff) > tolerance, or if diff is not finite (a NaN diff is
        never treated as passing — `abs(nan) > tolerance` is False in
        Python, which would otherwise let a NaN silently clear the gate).
    """
    diff = sum(contributions.values()) - portfolio_total_return
    if not math.isfinite(diff) or abs(diff) > tolerance:
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


def _validate_weights_sum(weights: dict[str, float], label: str) -> None:
    if not weights:
        raise ValueError(f"{label} is empty")
    total = sum(weights.values())
    if not math.isfinite(total) or abs(total - 1.0) > DEFAULT_WEIGHT_SUM_TOLERANCE:
        raise ValueError(
            f"{label} weights sum to {total!r}, expected ~1.0 "
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
        # BUG-008: a non-numeric weight_delta must raise ValueError here,
        # not a bare TypeError several frames away at `target_weight[sym]
        # + trade["weight_delta"]`. bool is excluded even though it is
        # technically an int subclass -- True/False is never a meaningful
        # weight delta.
        wd = trade["weight_delta"]
        if not isinstance(wd, (int, float)) or isinstance(wd, bool):
            raise ValueError(
                f"trade_log[{i}].weight_delta must be a number, got "
                f"{type(wd).__name__}"
            )
        if not math.isfinite(wd):
            raise ValueError(
                f"trade_log[{i}].weight_delta must be finite, got {wd!r}"
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


def _resolve_dividend_schedule(
    dividend_schedule: dict[str, dict[str, float]],
    symbols: set[str],
    daily_prices: dict[str, dict[str, float]],
    start_d: _date_cls,
    end_d: _date_cls,
) -> tuple[
    dict[str, dict[str, float]],
    dict[str, list[tuple[str, str]]],
    dict[str, list[str]],
]:
    """Validate and resolve the optional dividend_schedule parameter.

    Every {symbol, ex_date} pair must: name a symbol already in the
    computed universe (prior/current/trade_log — a typo'd or unheld symbol
    is rejected rather than silently ignored); carry an ex_date strictly
    after period_start and on/before period_end (period_start has no
    return day, so a dividend dated period_start can never be applied and
    is rejected rather than silently dropped); and carry a finite,
    non-negative cash amount (BUG-005: a NaN or negative dividend must be
    rejected here rather than silently corrupting a downstream gate that
    compares it with `>`, which treats NaN as always-False).

    BUG-009: an ex_date that is NOT an actual, non-forward-filled close for
    that symbol (a market holiday the price feed skips, a different
    exchange calendar) is no longer rejected outright. The server includes
    such a dividend via the vendor return on the next trading day it has a
    close for that symbol, so this resolves the same way: the dividend is
    SHIFTED forward to that symbol's own next actual close strictly after
    ex_date, at or before period_end. If no such close exists in the
    period, the dividend is UNAPPLIED — recorded in the return value, not
    silently applied, and not an error; the caller (SKILL.md) must mark
    that holding dividend-unchecked rather than treat the reconciliation
    audit as having covered it.

    Returns
    -------
    tuple
        ``(resolved, shifted, unapplied)``:
        - ``resolved``: ``{symbol: {applied_date: cash_amount}}`` — summed
          when more than one original ex_date resolves to the same
          applied_date.
        - ``shifted``: ``{symbol: [(ex_date, applied_date), ...]}`` for
          every entry whose applied_date differs from its own ex_date.
        - ``unapplied``: ``{symbol: [ex_date, ...]}`` for every entry with
          no later close in the period to shift to.
    """
    resolved: dict[str, dict[str, float]] = {}
    shifted: dict[str, list[tuple[str, str]]] = {}
    unapplied: dict[str, list[str]] = {}

    for sym, by_date in dividend_schedule.items():
        if sym not in symbols:
            raise ValueError(
                f"dividend_schedule names symbol '{sym}' which is not in "
                "prior_portfolio, current_portfolio, or trade_log"
            )
        if not isinstance(by_date, dict):
            raise ValueError(
                f"dividend_schedule['{sym}'] must be a dict of {{ex_date: cash_amount}}"
            )
        series = daily_prices.get(sym, {})
        parsed_series = {
            d_str: _parse_iso(d_str, field=f"daily_prices['{sym}']") for d_str in series
        }
        for ex_date, cash_amount in by_date.items():
            d = _parse_iso(ex_date, field=f"dividend_schedule['{sym}']")
            if d <= start_d or d > end_d:
                raise ValueError(
                    f"dividend_schedule['{sym}']['{ex_date}'] outside period "
                    f"({start_d.isoformat()}, {end_d.isoformat()}] — period_start "
                    "has no return day, so a dividend dated period_start can "
                    "never be applied"
                )
            if not isinstance(cash_amount, (int, float)) or isinstance(cash_amount, bool):
                raise ValueError(
                    f"dividend_schedule['{sym}']['{ex_date}'] cash amount "
                    f"must be a number, got {type(cash_amount).__name__}"
                )
            if not math.isfinite(cash_amount) or cash_amount < 0:
                raise ValueError(
                    f"dividend_schedule['{sym}']['{ex_date}'] cash amount "
                    f"must be finite and >= 0, got {cash_amount!r}"
                )

            if ex_date in series:
                applied_date = ex_date
            else:
                later_closes = sorted(
                    (d_str for d_str, pd in parsed_series.items() if pd > d and pd <= end_d),
                    key=lambda d_str: parsed_series[d_str],
                )
                if not later_closes:
                    unapplied.setdefault(sym, []).append(ex_date)
                    continue
                applied_date = later_closes[0]
                shifted.setdefault(sym, []).append((ex_date, applied_date))

            resolved.setdefault(sym, {})
            resolved[sym][applied_date] = resolved[sym].get(applied_date, 0.0) + cash_amount

    return resolved, shifted, unapplied
