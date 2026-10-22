"""
Tests for daily_contribution() in contribution.py.

Convention notes (must match the implementation):
- Dates are ISO 'YYYY-MM-DD'. We use 2026-01-01..2026-01-31 (31 calendar dates,
  30 return days). Day 0 = 2026-01-01 (period_start), Day 30 = 2026-01-31.
- Returns are computed for return-days 1..30: r_i[d] = price[d]/price[d-1] - 1.
- Per-holding value COMPOUNDS daily (value[d] = value[d-1] * (1 + r[d])); a
  holding's weight therefore drifts with its own relative performance unless
  a rebalance resets it. A rebalance applies AFTER its date's close: that
  day's return still accrues to the PRE-rebalance value, and only then does
  the book reweight to the new target.
- Trade convention: a trade with date D applies AFTER day D's close. The new
  weights take effect for the next return day (D+1). So:
    * "Added a holding on return-day 15" => trade.date = day 14 (2026-01-15
      is the 15th calendar date but day 14 zero-indexed; we use the literal
      date strings in the fixtures and document explicitly).
    * "Exited a holding on return-day 10" => trade.date = day 10 (2026-01-11),
      so exited weight contributes returns 1..10, then drops to 0.

To avoid off-by-one ambiguity in prose we always express trade dates as
explicit ISO strings tied to which return-days the new weights are in effect.

All expected values are HAND-COMPUTED in the test comments, not reverse-derived.
Where a fixture has no rebalance before the days that move, a single holding's
own compounded return telescopes to a simple end/start price ratio
(`P_end / P_start - 1`), independent of the path between them — several tests
below rely on that identity rather than summing per-day terms.
"""

from __future__ import annotations

import datetime
import math

import pytest

from contribution import (
    DEFAULT_RECONCILIATION_TOLERANCE,
    DEFAULT_WEIGHT_SUM_TOLERANCE,
    ReconciliationError,
    daily_contribution,
    validate_contributions,
)


# --------------------------------------------------------------------------
# Helpers for building synthetic price series
# --------------------------------------------------------------------------


def _date(day: int) -> str:
    """day 0 -> 2026-01-01, day 30 -> 2026-01-31."""
    return f"2026-01-{day + 1:02d}"


def _flat_then_jump_series(start: float, end: float, days: int) -> dict[str, float]:
    """Linear price path day 0..days inclusive. days=30 => 31 prices."""
    series: dict[str, float] = {}
    for d in range(days + 1):
        # linear interpolation (not realistic but easy to hand-compute)
        price = start + (end - start) * d / days
        series[_date(d)] = price
    return series


# --------------------------------------------------------------------------
# Test 1: Held entire period, 3 holdings, 30 return-days, no trades
# --------------------------------------------------------------------------


def test_held_entire_period_no_trades():
    """3 holdings, equal weights, no trades over 30 return-days.

    No rebalance ever occurs, so each holding's own value compounds
    independently of the others and telescopes exactly to its end/start
    price ratio — the per-day path shape (linear here) is irrelevant to the
    total, only the endpoints matter:

      AAPL: 100 -> 130. contribution = (1/3) * (130/100 - 1) = (1/3)*0.30 = +0.10
      JPM:  100 -> 70.  contribution = (1/3) * (70/100 - 1)  = (1/3)*-0.30 = -0.10
      MSFT: 100 -> 100. contribution = 0

    Portfolio total return = sum of contributions = 0.0.
    """
    days = 30
    aapl = _flat_then_jump_series(100.0, 130.0, days)
    msft = _flat_then_jump_series(100.0, 100.0, days)
    jpm = _flat_then_jump_series(100.0, 70.0, days)

    daily_prices = {"AAPL.O": aapl, "MSFT.O": msft, "JPM.N": jpm}

    prior = {"AAPL.O": 1 / 3, "MSFT.O": 1 / 3, "JPM.N": 1 / 3}
    current = {"AAPL.O": 1 / 3, "MSFT.O": 1 / 3, "JPM.N": 1 / 3}

    expected_aapl_contrib = (1 / 3) * (130.0 / 100.0 - 1.0)
    expected_jpm_contrib = (1 / 3) * (70.0 / 100.0 - 1.0)
    expected_msft_contrib = 0.0
    expected_total = expected_aapl_contrib + expected_msft_contrib + expected_jpm_contrib

    result = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=[],
        daily_prices=daily_prices,
        period_start=_date(0),
        period_end=_date(days),
    )

    assert math.isclose(
        result["contributions"]["AAPL.O"], expected_aapl_contrib, abs_tol=1e-12
    )
    assert math.isclose(
        result["contributions"]["MSFT.O"], expected_msft_contrib, abs_tol=1e-12
    )
    assert math.isclose(
        result["contributions"]["JPM.N"], expected_jpm_contrib, abs_tol=1e-12
    )
    assert math.isclose(result["portfolio_total_return"], expected_total, abs_tol=1e-12)
    assert abs(result["reconciliation_diff"]) < 1e-12


# --------------------------------------------------------------------------
# Test 2: Add a 4th holding mid-period
# --------------------------------------------------------------------------


def test_added_mid_period():
    """3 holdings at start. New holding NVDA enters such that it earns
    returns on days 15..30. Funded by trimming AAPL.

    Trade.date convention: trade applies AFTER day D's close, taking effect
    for return-day D+1. To make NVDA earn returns 15..30 we set trade.date
    = day 14 (date string for day 14).

    Setup (per holding, simple flat-then-jump prices for clean math):
      AAPL: 100 throughout (no return). Skip return contribution math.
      MSFT: 100 throughout.
      JPM:  100 throughout.
      NVDA: 100 on days 0..14, then 110 on day 15..30 (one-shot 10% return on day 15;
            flat afterwards). NVDA daily returns: r[15] = 0.10, r[d!=15] = 0.

    Initial weights: AAPL=0.5, MSFT=0.25, JPM=0.25 (sum=1.0).
    Trade on day 14: trim AAPL by -0.10, add NVDA at +0.10.
    Post-trade weights (effective return-days 15..30):
      AAPL=0.4, MSFT=0.25, JPM=0.25, NVDA=0.10  (sum=1.0)

    Every price here is flat except NVDA's single jump, and that jump
    happens strictly after the only rebalance in this fixture, so there is
    nothing for compounding drift to act on before the trade — this result
    is identical under compounding and under a naive per-day sum.

    Expected contributions:
      AAPL contrib = 0 (price flat, every day)
      MSFT contrib = 0
      JPM  contrib = 0
      NVDA contrib = w[15] * r[15] = 0.10 * 0.10 = 0.01
                     (only day 15 contributes; days 16..30 have r=0)
    Portfolio total return = 0.01.
    """
    days = 30
    flat_100 = {_date(d): 100.0 for d in range(days + 1)}

    nvda = {}
    for d in range(days + 1):
        nvda[_date(d)] = 100.0 if d < 15 else 110.0

    daily_prices = {
        "AAPL.O": flat_100,
        "MSFT.O": dict(flat_100),
        "JPM.N": dict(flat_100),
        "NVDA.O": nvda,
    }

    prior = {"AAPL.O": 0.5, "MSFT.O": 0.25, "JPM.N": 0.25}
    current = {"AAPL.O": 0.4, "MSFT.O": 0.25, "JPM.N": 0.25, "NVDA.O": 0.10}

    trade_log = [
        {
            "symbol": "AAPL.O",
            "action": "trim",
            "date": _date(14),
            "weight_delta": -0.10,
        },
        {
            "symbol": "NVDA.O",
            "action": "enter",
            "date": _date(14),
            "weight_delta": +0.10,
        },
    ]

    result = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=trade_log,
        daily_prices=daily_prices,
        period_start=_date(0),
        period_end=_date(days),
    )

    assert math.isclose(result["contributions"]["AAPL.O"], 0.0, abs_tol=1e-12)
    assert math.isclose(result["contributions"]["MSFT.O"], 0.0, abs_tol=1e-12)
    assert math.isclose(result["contributions"]["JPM.N"], 0.0, abs_tol=1e-12)
    assert math.isclose(result["contributions"]["NVDA.O"], 0.01, abs_tol=1e-12)
    assert math.isclose(result["portfolio_total_return"], 0.01, abs_tol=1e-12)
    assert abs(result["reconciliation_diff"]) < DEFAULT_RECONCILIATION_TOLERANCE


# --------------------------------------------------------------------------
# Test 3: Exit a holding mid-period; freed weight redistributed
# --------------------------------------------------------------------------


def test_exited_mid_period():
    """4 holdings at start, equal 0.25 each. JPM is exited on day 10
    (trade.date = day 10 means: weight effective for return-days 11..30
    excludes JPM). Freed weight (0.25) is redistributed equally to the
    three survivors (each gets +0.25/3).

    Prices (chosen so contributions are easy):
      AAPL: 100 on day 0..9, 110 on day 10..30 (one-shot +10% return on day 10)
      MSFT: flat 100
      GOOG: flat 100
      JPM:  100 on day 0..4, 90 on day 5..30 (one-shot -10% return on day 5)

    AAPL and JPM each have exactly one non-flat day, and both occur before
    (or simultaneously with, for AAPL) the single rebalance on day 10 while
    every weight involved has been constant since day 0 — so there is no
    compounding drift to diverge from a naive per-day sum here either, and
    the total P&L at the moment of rebalance is exactly 0, so the
    rebalance itself does not even change total portfolio value.

    Pre-exit weights (return days 1..10): AAPL=0.25, MSFT=0.25, GOOG=0.25, JPM=0.25
    Post-exit weights (return days 11..30): AAPL=0.25 + 0.25/3 = 1/3,
                                            MSFT=1/3, GOOG=1/3, JPM=0

    Hand-computed contributions:
      AAPL: only day 10 contributes (r[10] = 110/100 - 1 = 0.10), using the
            PRE-rebalance weight 0.25 (the trade applies after day 10's
            close) -> contrib_aapl = 0.25 * 0.10 = 0.025
      MSFT: 0
      GOOG: 0
      JPM:  only day 5 contributes (r[5] = 90/100 - 1 = -0.10).
            weight on day 5 = 0.25 -> contrib_jpm = 0.25 * -0.10 = -0.025
    Portfolio total return = 0.025 + 0 + 0 - 0.025 = 0.0
    """
    days = 30

    aapl = {_date(d): (100.0 if d < 10 else 110.0) for d in range(days + 1)}
    msft = {_date(d): 100.0 for d in range(days + 1)}
    goog = {_date(d): 100.0 for d in range(days + 1)}
    jpm = {_date(d): (100.0 if d < 5 else 90.0) for d in range(days + 1)}

    daily_prices = {"AAPL.O": aapl, "MSFT.O": msft, "GOOG.O": goog, "JPM.N": jpm}

    prior = {"AAPL.O": 0.25, "MSFT.O": 0.25, "GOOG.O": 0.25, "JPM.N": 0.25}
    current = {"AAPL.O": 1 / 3, "MSFT.O": 1 / 3, "GOOG.O": 1 / 3}

    trade_log = [
        {
            "symbol": "JPM.N",
            "action": "exit",
            "date": _date(10),
            "weight_delta": -0.25,
        },
        {
            "symbol": "AAPL.O",
            "action": "add",
            "date": _date(10),
            "weight_delta": +0.25 / 3,
        },
        {
            "symbol": "MSFT.O",
            "action": "add",
            "date": _date(10),
            "weight_delta": +0.25 / 3,
        },
        {
            "symbol": "GOOG.O",
            "action": "add",
            "date": _date(10),
            "weight_delta": +0.25 / 3,
        },
    ]

    result = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=trade_log,
        daily_prices=daily_prices,
        period_start=_date(0),
        period_end=_date(days),
    )

    assert math.isclose(result["contributions"]["AAPL.O"], 0.025, abs_tol=1e-12)
    assert math.isclose(result["contributions"]["MSFT.O"], 0.0, abs_tol=1e-12)
    assert math.isclose(result["contributions"]["GOOG.O"], 0.0, abs_tol=1e-12)
    assert math.isclose(result["contributions"]["JPM.N"], -0.025, abs_tol=1e-12)
    assert math.isclose(result["portfolio_total_return"], 0.0, abs_tol=1e-12)
    assert abs(result["reconciliation_diff"]) < DEFAULT_RECONCILIATION_TOLERANCE


# --------------------------------------------------------------------------
# Test 3b: One rebalance AND one dividend in the same short period
# --------------------------------------------------------------------------


def test_one_rebalance_and_one_dividend():
    """2 holdings, 0.5/0.5. A rallies, B pays a dividend the next day, and a
    rebalance sits between the two events — exercising compounding,
    rebalance-after-close, and the dividend add-back together.

    Day 1: A 100 -> 110 (r=0.10), B flat (r=0). Trade dated day 1: A +0.10
    (0.5 -> 0.6), B -0.10 (0.5 -> 0.4).
    Day 2: A flat (r=0), B flat price but a 5.0 cash dividend on this
    ex-date (r = (100+5)/100 - 1 = 0.05). No further trade.

    Hand-computed walk (initial value A=0.5, B=0.5):
      Day 1: price_pl_A = 0.5*0.10 = 0.05 -> value_A = 0.55 (pre-rebalance)
             price_pl_B = 0.5*0 = 0 -> value_B = 0.5 (pre-rebalance)
             rebalance: total = 0.55+0.5 = 1.05;
               value_A = 0.6*1.05 = 0.63, value_B = 0.4*1.05 = 0.42
      Day 2: price_pl_A = 0.63*0 = 0 -> value_A stays 0.63
             price_pl_B = 0.42*0.05 = 0.021 -> value_B = 0.441

    contributions: A = 0.05 + 0 = 0.05; B = 0 + 0.021 = 0.021
    Final total value = 0.63 + 0.441 = 1.071 -> portfolio_total_return = 0.071
    sum(contributions) = 0.071, matching exactly.
    """
    prices = {
        "A": {_date(0): 100.0, _date(1): 110.0, _date(2): 110.0},
        "B": {_date(0): 100.0, _date(1): 100.0, _date(2): 100.0},
    }
    prior = {"A": 0.5, "B": 0.5}
    current = {"A": 0.6, "B": 0.4}
    trade_log = [
        {"symbol": "A", "action": "add", "date": _date(1), "weight_delta": +0.10},
        {"symbol": "B", "action": "trim", "date": _date(1), "weight_delta": -0.10},
    ]
    dividend_schedule = {"B": {_date(2): 5.0}}

    result = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=trade_log,
        daily_prices=prices,
        period_start=_date(0),
        period_end=_date(2),
        dividend_schedule=dividend_schedule,
    )

    assert math.isclose(result["contributions"]["A"], 0.05, abs_tol=1e-12)
    assert math.isclose(result["contributions"]["B"], 0.021, abs_tol=1e-12)
    assert math.isclose(result["portfolio_total_return"], 0.071, abs_tol=1e-12)
    assert abs(result["reconciliation_diff"]) < 1e-12


# --------------------------------------------------------------------------
# Test 4: Price-return-prices contract (the real contract — export_price_series
# returns raw closes, no dividend adjustment)
# --------------------------------------------------------------------------


def test_price_return_prices_with_ex_dividend_drop_compute_correctly():
    """The real contract: `daily_prices` is price-return (raw close, no
    dividend adjustment) — exactly what `export_price_series` returns. An
    ex-dividend drop shows up as a price drop on the ex-date, and WITHOUT a
    `dividend_schedule` the function correctly computes the price-only
    return over that drop: it does not try to recover the dividend.

    Single holding, weight=1.0, 10 days. Price-return price is flat at 100
    through day 4, drops to 95 on ex-date day 5 (a 5.0 cash dividend was
    paid that day, but — correctly, per the contract — is NOT reflected in
    the price), then stays flat at 95 through day 10 (no recovery, so the
    numbers stay hand-computable).

    With no rebalance, this telescopes to the simple end/start ratio:
      price-only: 95 / 100 - 1 = -0.05
    Supplying the 5.0 dividend via `dividend_schedule` on the ex-date
    exactly cancels the drop: (95 + 5) / 100 - 1 = 0.0 on that day, and
    every other day is flat, so the total with the schedule is exactly 0.0.
    See test_total_return_style_prices_plus_dividend_schedule_double_counts_negative_control
    for what happens if dividend-adjusted prices are supplied directly
    instead of using `dividend_schedule`.
    """
    days = 10
    price_return = {_date(d): 100.0 for d in range(5)}
    for d in range(5, days + 1):
        price_return[_date(d)] = 95.0

    daily_prices = {"AAPL.O": price_return}
    prior = {"AAPL.O": 1.0}
    current = {"AAPL.O": 1.0}

    price_only = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=[],
        daily_prices=daily_prices,
        period_start=_date(0),
        period_end=_date(days),
    )
    assert math.isclose(
        price_only["contributions"]["AAPL.O"], -0.05, abs_tol=1e-12
    )
    assert math.isclose(price_only["portfolio_total_return"], -0.05, abs_tol=1e-12)

    with_div = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=[],
        daily_prices=daily_prices,
        period_start=_date(0),
        period_end=_date(days),
        dividend_schedule={"AAPL.O": {_date(5): 5.0}},
    )
    assert math.isclose(with_div["contributions"]["AAPL.O"], 0.0, abs_tol=1e-12)
    assert math.isclose(with_div["portfolio_total_return"], 0.0, abs_tol=1e-12)


def test_total_return_style_prices_plus_dividend_schedule_double_counts_negative_control():
    """Negative control: `dividend_schedule` exists precisely so callers do
    NOT need to smooth dividends into `daily_prices`. If a caller supplies
    dividend-adjusted / total-return-style prices directly as `daily_prices`
    AND ALSO passes `dividend_schedule` for the same symbol/dividend, the
    dividend is counted twice — once baked into the smoothed price ramp,
    once again via the schedule's cash add-back. This test pins that
    double-counted (wrong) answer, documenting why `daily_prices` must stay
    raw price-return and `dividend_schedule` is the only sanctioned path for
    adding dividends back in.

    Setup: same economic event as
    test_price_return_prices_with_ex_dividend_drop_compute_correctly (a ~5%
    cash dividend around day 5). Here the price path is WRONGLY smoothed as
    a total-return series would show it (no ex-date drop, just a steady
    100 -> 105 climb baking the dividend into the price), and a
    dividend_schedule for the same ~5-unit dividend on day 5 is passed on
    top of it. Expected values are computed by the same compounding the
    module performs (a running product of daily factors), not by a
    hand-derived closed form — this test's job is to show the double-count
    overstates the correct (price-return + schedule) total, not to pin an
    exact number from first principles.
    """
    days = 10
    tr_style_prices = {_date(d): 100.0 + 0.5 * d for d in range(days + 1)}  # 100 -> 105
    daily_prices = {"AAPL.O": tr_style_prices}

    prior = {"AAPL.O": 1.0}
    current = {"AAPL.O": 1.0}
    dividend_schedule = {"AAPL.O": {_date(5): 5.0}}

    result = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=[],
        daily_prices=daily_prices,
        period_start=_date(0),
        period_end=_date(days),
        dividend_schedule=dividend_schedule,
    )

    # Compounded double-counted total: the same running product the module
    # itself performs, computed independently here from the raw prices.
    dates = sorted(tr_style_prices)
    double_count_factor = 1.0
    for prev_d, cur_d in zip(dates, dates[1:]):
        p_prev = tr_style_prices[prev_d]
        p_cur = tr_style_prices[cur_d]
        div = 5.0 if cur_d == _date(5) else 0.0
        double_count_factor *= (p_cur + div) / p_prev
    expected_double_count_total = double_count_factor - 1.0

    assert math.isclose(
        result["contributions"]["AAPL.O"], expected_double_count_total, abs_tol=1e-12
    )
    assert math.isclose(
        result["portfolio_total_return"], expected_double_count_total, abs_tol=1e-12
    )

    # The correct way to get this same ~5-unit dividend into the total
    # return is price-return prices (the ex-date drop, no smoothing) PLUS
    # dividend_schedule — not smoothed prices plus dividend_schedule.
    price_return_prices = {_date(d): 100.0 for d in range(5)}
    for d in range(5, days + 1):
        price_return_prices[_date(d)] = 95.0 + (d - 5)  # 95, 96, ..., 100
    correct_result = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=[],
        daily_prices={"AAPL.O": price_return_prices},
        period_start=_date(0),
        period_end=_date(days),
        dividend_schedule=dividend_schedule,
    )
    correct_total = correct_result["portfolio_total_return"]

    # The double-counted (wrong) total overstates the correct total-return
    # figure by roughly the dividend amount (~5%) — large enough that this
    # is not merely a rounding difference.
    assert expected_double_count_total - correct_total > 0.04, (
        "smoothed total-return-style prices plus dividend_schedule should "
        "overstate the correct price-return-plus-schedule total by roughly "
        "the dividend amount (double counting)"
    )


# --------------------------------------------------------------------------
# Test 4b: Live-verified VZ.N single-holding book (2026-10-06 settled facts)
#
# Raw closes and server-reported total_price_pl are from a live
# analyze_portfolio / export_price_series / get_stock_outlook run against a
# single-holding VZ.N book, period 2026-07-06..2026-07-14, ex-dividend
# 2026-07-10, divrate 0.7075. The server reported total_price_pl = 264.6483
# on a 10000 initial_value (+2.6465%), establishing that total_price_pl is a
# TOTAL-RETURN field (dividends included via a compounded path), not
# price-only — and this module now compounds too, so the comparison is
# tight (1e-5), not a 25-bp arithmetic-vs-geometric allowance.
# --------------------------------------------------------------------------


_VZ_CLOSES = {
    "2026-07-06": 42.070008,
    "2026-07-07": 42.589997,
    "2026-07-08": 42.449997,
    "2026-07-09": 42.240006,
    "2026-07-10": 42.119996,
    "2026-07-13": 42.679993,
    "2026-07-14": 42.470002,
}
_VZ_EX_DATE = "2026-07-10"
_VZ_DIVRATE = 0.7075
_VZ_PERIOD_START = "2026-07-06"
_VZ_PERIOD_END = "2026-07-14"
_VZ_SERVER_TOTAL_RETURN = 264.6483 / 10000.0  # 0.02646483


def test_vz_single_holding_with_dividend_schedule_matches_server_total_return():
    """Reproduce the live-verified VZ.N numbers: raw closes + the one
    ex-dividend cash amount, via `dividend_schedule`, must match the
    server's total_price_pl-implied return to within 1e-5 — this module
    now replicates the server's own compounding method, so there is no
    arithmetic-vs-geometric gap left to absorb.
    """
    dates = sorted(_VZ_CLOSES)
    assert dates[0] == _VZ_PERIOD_START
    assert dates[-1] == _VZ_PERIOD_END

    # Hand-computed daily returns, dividend added back only on the ex-date —
    # used here only to pin the two single-day assertions below, not to
    # derive the module's answer independently (the module's own compounding
    # is what is under test).
    r = {}
    for prev_d, cur_d in zip(dates, dates[1:]):
        p_prev = _VZ_CLOSES[prev_d]
        p_cur = _VZ_CLOSES[cur_d]
        div = _VZ_DIVRATE if cur_d == _VZ_EX_DATE else 0.0
        r[cur_d] = (p_cur + div) / p_prev - 1.0

    assert math.isclose(
        r["2026-07-07"], 42.589997 / 42.070008 - 1.0, abs_tol=1e-15
    )
    assert math.isclose(
        r["2026-07-10"],
        (42.119996 + _VZ_DIVRATE) / 42.240006 - 1.0,
        abs_tol=1e-15,
    )

    daily_prices = {"VZ.N": dict(_VZ_CLOSES)}
    dividend_schedule = {"VZ.N": {_VZ_EX_DATE: _VZ_DIVRATE}}
    result = daily_contribution(
        prior_portfolio={"VZ.N": 1.0},
        current_portfolio={"VZ.N": 1.0},
        trade_log=[],
        daily_prices=daily_prices,
        period_start=_VZ_PERIOD_START,
        period_end=_VZ_PERIOD_END,
        dividend_schedule=dividend_schedule,
    )
    compounded_total = result["portfolio_total_return"]

    # Single holding, no trades: contribution IS the portfolio total, and it
    # must equal the geometric compound of the same six hand-computed
    # returns pinned above.
    geometric_total = 1.0
    for cur_d in dates[1:]:
        geometric_total *= 1.0 + r[cur_d]
    geometric_total -= 1.0
    assert math.isclose(compounded_total, geometric_total, abs_tol=1e-12)
    assert math.isclose(result["contributions"]["VZ.N"], compounded_total, abs_tol=1e-12)

    assert math.isclose(
        compounded_total, _VZ_SERVER_TOTAL_RETURN, abs_tol=1e-5
    ), (
        f"compounded local total {compounded_total} should match the "
        f"server's reported total_price_pl return {_VZ_SERVER_TOTAL_RETURN} "
        "to within 1e-5 now that local replicates the server's method"
    )


def test_vz_single_holding_without_dividend_schedule_gives_price_only_result():
    """Same VZ.N raw closes, but WITHOUT `dividend_schedule` (the default).
    With no trades, the price-only result telescopes to the simple
    end/start close ratio — hand-verifiable without summing six terms.
    """
    daily_prices = {"VZ.N": dict(_VZ_CLOSES)}

    with_div = daily_contribution(
        prior_portfolio={"VZ.N": 1.0},
        current_portfolio={"VZ.N": 1.0},
        trade_log=[],
        daily_prices=daily_prices,
        period_start=_VZ_PERIOD_START,
        period_end=_VZ_PERIOD_END,
        dividend_schedule={"VZ.N": {_VZ_EX_DATE: _VZ_DIVRATE}},
    )
    without_div = daily_contribution(
        prior_portfolio={"VZ.N": 1.0},
        current_portfolio={"VZ.N": 1.0},
        trade_log=[],
        daily_prices=daily_prices,
        period_start=_VZ_PERIOD_START,
        period_end=_VZ_PERIOD_END,
        # dividend_schedule omitted entirely — default None -> price-only.
    )

    expected_price_only = (
        _VZ_CLOSES[_VZ_PERIOD_END] / _VZ_CLOSES[_VZ_PERIOD_START] - 1.0
    )
    assert math.isclose(
        without_div["portfolio_total_return"], expected_price_only, abs_tol=1e-12
    )

    # Sanity: the price-only result is materially smaller than the
    # total-return result — roughly the dividend's ~1.7% contribution on a
    # ~42 close — confirming omitting dividend_schedule is not a no-op.
    assert with_div["portfolio_total_return"] - without_div["portfolio_total_return"] > 0.01


# --------------------------------------------------------------------------
# Test 5: Reconciliation gate fires on broken contributions
# --------------------------------------------------------------------------


def test_reconciliation_gate_catches_broken_contributions():
    """Run a clean computation, then simulate a downstream bug by mutating
    one contribution. validate_contributions() must raise ReconciliationError.
    """
    days = 30
    aapl = _flat_then_jump_series(100.0, 130.0, days)
    msft = _flat_then_jump_series(100.0, 100.0, days)
    daily_prices = {"AAPL.O": aapl, "MSFT.O": msft}
    prior = {"AAPL.O": 0.5, "MSFT.O": 0.5}
    current = dict(prior)

    result = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=[],
        daily_prices=daily_prices,
        period_start=_date(0),
        period_end=_date(days),
    )

    # Sanity: clean validate passes
    validate_contributions(
        contributions=result["contributions"],
        portfolio_total_return=result["portfolio_total_return"],
    )

    # Break one contribution by 0.5%
    broken = dict(result["contributions"])
    broken["AAPL.O"] -= 0.005  # 50bp drop, well above 1bp tolerance

    with pytest.raises(ReconciliationError):
        validate_contributions(
            contributions=broken,
            portfolio_total_return=result["portfolio_total_return"],
        )


def test_reconciliation_gate_carries_diff_and_tolerance():
    """ReconciliationError exposes the diff and tolerance for caller logging.

    diff is defined as sum(contributions) - portfolio_total_return.
    """
    contributions = {"AAPL.O": 0.05, "MSFT.O": 0.03}  # sum = 0.08
    total = 0.08 + 0.001  # 10bp above the contributions sum

    with pytest.raises(ReconciliationError) as excinfo:
        validate_contributions(
            contributions=contributions, portfolio_total_return=total
        )
    err = excinfo.value
    # sum(contribs) - total = 0.08 - 0.081 = -0.001
    assert math.isclose(err.diff, -0.001, abs_tol=1e-12)
    assert err.tolerance == DEFAULT_RECONCILIATION_TOLERANCE


def test_reconciliation_gate_rejects_nan_diff_rather_than_passing_it():
    """BUG-005: a NaN diff must never silently clear the gate. In plain
    Python, `abs(float('nan')) > tolerance` is False, so an unguarded gate
    would treat a NaN total return as reconciled. The gate must check
    isfinite first and fail closed.
    """
    contributions = {"AAPL.O": float("nan")}
    with pytest.raises(ReconciliationError):
        validate_contributions(contributions=contributions, portfolio_total_return=0.0)


# --------------------------------------------------------------------------
# Test 6: Input validation
# --------------------------------------------------------------------------


def test_missing_prices_for_held_holding():
    """A holding present in prior_portfolio with no daily_prices entry => ValueError."""
    days = 5
    daily_prices = {"AAPL.O": _flat_then_jump_series(100.0, 105.0, days)}
    # MSFT.O is held but has no prices
    prior = {"AAPL.O": 0.5, "MSFT.O": 0.5}
    current = dict(prior)

    with pytest.raises(ValueError, match="(?i)price"):
        daily_contribution(
            prior_portfolio=prior,
            current_portfolio=current,
            trade_log=[],
            daily_prices=daily_prices,
            period_start=_date(0),
            period_end=_date(days),
        )


def test_weights_not_summing_raises():
    """prior weights must sum to ~1.0 within tolerance."""
    days = 5
    daily_prices = {
        "AAPL.O": _flat_then_jump_series(100.0, 105.0, days),
        "MSFT.O": _flat_then_jump_series(100.0, 105.0, days),
    }
    prior = {"AAPL.O": 0.4, "MSFT.O": 0.4}  # sums to 0.8
    current = {"AAPL.O": 0.5, "MSFT.O": 0.5}

    with pytest.raises(ValueError, match="(?i)sum"):
        daily_contribution(
            prior_portfolio=prior,
            current_portfolio=current,
            trade_log=[],
            daily_prices=daily_prices,
            period_start=_date(0),
            period_end=_date(days),
        )


def test_weights_sum_rejects_nan_rather_than_passing():
    """BUG-005-adjacent: a NaN weight sum must raise, not silently pass the
    sum-close-to-1.0 check (`abs(nan - 1.0) > tolerance` is False in Python)."""
    days = 5
    daily_prices = {
        "AAPL.O": _flat_then_jump_series(100.0, 105.0, days),
        "MSFT.O": _flat_then_jump_series(100.0, 105.0, days),
    }
    prior = {"AAPL.O": float("nan"), "MSFT.O": 0.5}
    current = {"AAPL.O": 0.5, "MSFT.O": 0.5}

    with pytest.raises(ValueError, match="(?i)sum"):
        daily_contribution(
            prior_portfolio=prior,
            current_portfolio=current,
            trade_log=[],
            daily_prices=daily_prices,
            period_start=_date(0),
            period_end=_date(days),
        )


def test_period_end_before_start_raises():
    """period_end < period_start => ValueError."""
    days = 5
    daily_prices = {"AAPL.O": _flat_then_jump_series(100.0, 105.0, days)}
    prior = {"AAPL.O": 1.0}
    current = {"AAPL.O": 1.0}

    with pytest.raises(ValueError, match="(?i)period"):
        daily_contribution(
            prior_portfolio=prior,
            current_portfolio=current,
            trade_log=[],
            daily_prices=daily_prices,
            period_start=_date(days),
            period_end=_date(0),
        )


def test_trade_log_out_of_order_raises():
    """Trades must be in chronological order."""
    days = 30
    daily_prices = {
        "AAPL.O": _flat_then_jump_series(100.0, 100.0, days),
        "MSFT.O": _flat_then_jump_series(100.0, 100.0, days),
    }
    prior = {"AAPL.O": 0.6, "MSFT.O": 0.4}
    current = {"AAPL.O": 0.5, "MSFT.O": 0.5}

    trade_log = [
        # day 20 first, day 10 second -> out of order
        {
            "symbol": "AAPL.O",
            "action": "trim",
            "date": _date(20),
            "weight_delta": -0.05,
        },
        {"symbol": "MSFT.O", "action": "add", "date": _date(20), "weight_delta": +0.05},
        {
            "symbol": "AAPL.O",
            "action": "trim",
            "date": _date(10),
            "weight_delta": -0.05,
        },
        {"symbol": "MSFT.O", "action": "add", "date": _date(10), "weight_delta": +0.05},
    ]

    with pytest.raises(ValueError, match="(?i)order"):
        daily_contribution(
            prior_portfolio=prior,
            current_portfolio=current,
            trade_log=trade_log,
            daily_prices=daily_prices,
            period_start=_date(0),
            period_end=_date(days),
        )


def test_weight_sum_tolerance_constant_is_named():
    """Tolerance is module-level, not a magic number."""
    assert DEFAULT_WEIGHT_SUM_TOLERANCE > 0
    assert DEFAULT_RECONCILIATION_TOLERANCE > 0


# --------------------------------------------------------------------------
# Test 7: Cross-check current_portfolio against reconstructed ending weights
# --------------------------------------------------------------------------


def test_inconsistent_current_portfolio_raises():
    """current_portfolio that disagrees with trade reconstruction by > 1e-3
    must raise ValueError, with a message identifying the offending symbol,
    reconstructed weight, claimed weight, and diff.
    """
    days = 30
    flat_100 = {_date(d): 100.0 for d in range(days + 1)}
    daily_prices = {
        "AAPL.O": flat_100,
        "MSFT.O": dict(flat_100),
        "JPM.N": dict(flat_100),
    }

    # Prior weights sum to 1.0. Single trim of AAPL -0.10 -> MSFT +0.10.
    # Reconstructed ending: AAPL=0.4, MSFT=0.35, JPM=0.25
    prior = {"AAPL.O": 0.5, "MSFT.O": 0.25, "JPM.N": 0.25}
    trade_log = [
        {
            "symbol": "AAPL.O",
            "action": "trim",
            "date": _date(14),
            "weight_delta": -0.10,
        },
        {"symbol": "MSFT.O", "action": "add", "date": _date(14), "weight_delta": +0.10},
    ]

    # Caller claims AAPL ended at 0.30 (off by 0.10 from reconstructed 0.40).
    # Sums to 1.0 so weight-sum gate passes, but cross-check should fire.
    bad_current = {"AAPL.O": 0.30, "MSFT.O": 0.45, "JPM.N": 0.25}

    with pytest.raises(ValueError) as excinfo:
        daily_contribution(
            prior_portfolio=prior,
            current_portfolio=bad_current,
            trade_log=trade_log,
            daily_prices=daily_prices,
            period_start=_date(0),
            period_end=_date(days),
        )

    msg = str(excinfo.value)
    # Message must identify offending symbol and surface the numbers.
    # Both AAPL.O and MSFT.O violate the gate (each off by 0.10 in this fixture);
    # set iteration order determines which surfaces first. Either is correct.
    assert ("AAPL.O" in msg) or ("MSFT.O" in msg)
    # Reconstructed = 0.4, claimed = 0.30, diff = -0.10 (or 0.10 depending on sign).
    assert "0.4" in msg or "0.40" in msg
    assert "0.3" in msg or "0.30" in msg


def test_consistent_current_portfolio_within_tolerance_passes():
    """current_portfolio within DEFAULT_WEIGHT_SUM_TOLERANCE (1e-3) of the
    reconstructed ending weights must pass without error.
    """
    days = 30
    flat_100 = {_date(d): 100.0 for d in range(days + 1)}
    daily_prices = {
        "AAPL.O": flat_100,
        "MSFT.O": dict(flat_100),
        "JPM.N": dict(flat_100),
    }

    prior = {"AAPL.O": 0.5, "MSFT.O": 0.25, "JPM.N": 0.25}
    trade_log = [
        {
            "symbol": "AAPL.O",
            "action": "trim",
            "date": _date(14),
            "weight_delta": -0.10,
        },
        {"symbol": "MSFT.O", "action": "add", "date": _date(14), "weight_delta": +0.10},
    ]

    # Reconstructed ending: AAPL=0.40, MSFT=0.35, JPM=0.25.
    # Caller passes 5e-4 drift on each — sub-tolerance.
    near_current = {"AAPL.O": 0.40 + 5e-4, "MSFT.O": 0.35 - 5e-4, "JPM.N": 0.25}

    # Should not raise.
    result = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=near_current,
        trade_log=trade_log,
        daily_prices=daily_prices,
        period_start=_date(0),
        period_end=_date(days),
    )
    assert "contributions" in result


def test_inconsistent_current_portfolio_extra_symbol_raises():
    """current_portfolio names a symbol with non-zero weight that the trade
    reconstruction never establishes (or has at zero) -> ValueError.
    """
    days = 30
    flat_100 = {_date(d): 100.0 for d in range(days + 1)}
    daily_prices = {
        "AAPL.O": flat_100,
        "MSFT.O": dict(flat_100),
        "TSLA.O": dict(flat_100),
    }

    prior = {"AAPL.O": 0.5, "MSFT.O": 0.5}
    # No trades. Reconstructed end: AAPL=0.5, MSFT=0.5, TSLA=0 (not present).
    trade_log: list[dict] = []

    # Caller claims TSLA at 0.10 with offsetting trim — sums to 1.0 but
    # contradicts the empty trade log.
    bad_current = {"AAPL.O": 0.4, "MSFT.O": 0.5, "TSLA.O": 0.10}

    with pytest.raises(ValueError) as excinfo:
        daily_contribution(
            prior_portfolio=prior,
            current_portfolio=bad_current,
            trade_log=trade_log,
            daily_prices=daily_prices,
            period_start=_date(0),
            period_end=_date(days),
        )

    msg = str(excinfo.value)
    # Either AAPL.O (off by 0.1) or TSLA.O (off by 0.1) should be named — both fail.
    assert "AAPL.O" in msg or "TSLA.O" in msg


def test_prices_start_after_period_start_raises():
    """T1a: daily_prices starting after period_start → ValueError with clear message.

    Scenario: period is 2026-01-01 to 2026-01-15 but export_price_series only
    returned prices from 2026-01-06 onward (5-day gap at the start). The
    contribution engine must raise ValueError rather than silently using whatever
    prices it has.
    """
    period_start = "2026-01-01"
    period_end = "2026-01-15"
    # daily_prices starts 5 days AFTER period_start
    gap_start = datetime.date(2026, 1, 6)
    period_end_date = datetime.date(2026, 1, 15)
    n_days = (period_end_date - gap_start).days + 2  # include period_end + 1 extra

    base_price = 100.0
    dates = [
        (gap_start + datetime.timedelta(days=i)).isoformat() for i in range(n_days)
    ]
    prices = [
        {"date": d, "close": base_price * (1 + 0.001 * i)} for i, d in enumerate(dates)
    ]

    prior_portfolio = {"AAPL.O": 1.0}
    current_portfolio = {"AAPL.O": 1.0}
    trade_log = []
    daily_prices_for_symbol = {d_price["date"]: d_price["close"] for d_price in prices}
    daily_prices = {"AAPL.O": daily_prices_for_symbol}

    with pytest.raises(ValueError, match="period_start"):
        daily_contribution(
            prior_portfolio=prior_portfolio,
            current_portfolio=current_portfolio,
            trade_log=trade_log,
            daily_prices=daily_prices,
            period_start=period_start,
            period_end=period_end,
        )
