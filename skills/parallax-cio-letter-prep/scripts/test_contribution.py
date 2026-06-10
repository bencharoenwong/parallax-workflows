"""
Tests for daily_contribution() in contribution.py.

Convention notes (must match the implementation):
- Dates are ISO 'YYYY-MM-DD'. We use 2026-01-01..2026-01-31 (31 calendar dates,
  30 return days). Day 0 = 2026-01-01 (period_start), Day 30 = 2026-01-31.
- Returns are computed for return-days 1..30: r_i[d] = price[d]/price[d-1] - 1.
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

    AAPL: 100 -> 130 (linear). Daily price[d] = 100 + d. Daily return r[d] = 1/(99+d).
    MSFT: 100 -> 100 (flat). Daily return = 0.
    JPM:  100 -> 70  (linear). Daily price[d] = 100 - d. Daily return r[d] = -1/(101-d).

    All weights = 1/3 throughout.

    Hand-computed sum of arithmetic daily returns:
      AAPL: sum_{d=1..30} 1/(99+d) = sum_{k=100..129} 1/k
      JPM:  sum_{d=1..30} -1/(101-d) = -sum_{k=71..100} 1/k
      MSFT: 0

    Contribution per holding = (1/3) * sum_of_daily_returns_for_holding.
    Portfolio total return = sum of contributions (by construction).
    """
    days = 30
    aapl = _flat_then_jump_series(100.0, 130.0, days)  # price[d] = 100 + d
    msft = _flat_then_jump_series(100.0, 100.0, days)  # flat
    jpm = _flat_then_jump_series(100.0, 70.0, days)    # price[d] = 100 - d

    daily_prices = {"AAPL.O": aapl, "MSFT.O": msft, "JPM.N": jpm}

    prior = {"AAPL.O": 1 / 3, "MSFT.O": 1 / 3, "JPM.N": 1 / 3}
    current = {"AAPL.O": 1 / 3, "MSFT.O": 1 / 3, "JPM.N": 1 / 3}

    # Hand-computed expected sums (using fractions to keep precision):
    aapl_ret_sum = sum(1.0 / k for k in range(100, 130))  # k = 100..129
    msft_ret_sum = 0.0
    jpm_ret_sum = sum(-1.0 / k for k in range(71, 101))   # k = 71..100

    expected_aapl_contrib = (1 / 3) * aapl_ret_sum
    expected_msft_contrib = (1 / 3) * msft_ret_sum
    expected_jpm_contrib = (1 / 3) * jpm_ret_sum
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
    assert abs(result["reconciliation_diff"]) < DEFAULT_RECONCILIATION_TOLERANCE


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

    # Hand-computed expected contributions:
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

    Pre-exit weights (return days 1..10): AAPL=0.25, MSFT=0.25, GOOG=0.25, JPM=0.25
    Post-exit weights (return days 11..30): AAPL=0.25 + 0.25/3 = 1/3,
                                            MSFT=1/3, GOOG=1/3, JPM=0

    Hand-computed contributions:
      AAPL: only day 10 contributes (r[10] = 110/100 - 1 = 0.10).
            Pre-exit weight on day 10 = 0.25 -> contrib_aapl = 0.25 * 0.10 = 0.025
            (days 11..30 have r=0 for AAPL)
      MSFT: 0
      GOOG: 0
      JPM:  only day 5 contributes (r[5] = 90/100 - 1 = -0.10).
            Pre-exit weight on day 5 = 0.25 -> contrib_jpm = 0.25 * -0.10 = -0.025
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
# Test 4: Dividend / total-return-prices assumption
# --------------------------------------------------------------------------

def test_total_return_prices_assumption_correct():
    """With TR-prices (dividends reinvested), a 5% dividend appears as a
    smooth/flat segment with no ex-date drop (because the price is adjusted
    to bake in the reinvestment). Math is correct.

    Setup: single holding, weight=1.0 throughout, 10 days.
    TR price: 100 -> 105 linearly over 10 days. r_total ~= sum of daily returns.
    Single-holding contribution must equal portfolio total return.
    """
    days = 10
    tr_prices = {_date(d): 100.0 + 0.5 * d for d in range(days + 1)}  # 100 -> 105
    daily_prices = {"AAPL.O": tr_prices}

    prior = {"AAPL.O": 1.0}
    current = {"AAPL.O": 1.0}

    result = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=[],
        daily_prices=daily_prices,
        period_start=_date(0),
        period_end=_date(days),
    )

    # Hand-computed: r[d] = 0.5 / (99.5 + 0.5*d), arithmetic sum over d=1..10
    expected_total = sum(0.5 / (99.5 + 0.5 * d) for d in range(1, days + 1))
    assert math.isclose(
        result["contributions"]["AAPL.O"], expected_total, abs_tol=1e-12
    )
    assert math.isclose(result["portfolio_total_return"], expected_total, abs_tol=1e-12)


def test_non_total_return_prices_break_math_negative_control():
    """Negative control: if the user supplies non-TR prices with an ex-dividend
    drop, the computed return is wrong (it understates total return by the
    dividend amount). This test asserts the WRONG answer, documenting that
    the function REQUIRES TR prices.

    Setup: single holding, weight=1.0, 10 days. Non-TR price drops from 100
    to 95 on ex-date day 5 (5% dividend), then climbs back to 100. Cash dividend
    of 5 was paid but is NOT in the price.

    True total return for the period = 0% (price ends where it started + 5 dividend
    on a $100 base = +5%). But because we ignore the dividend, the function
    computes the price-only return path which sums to a negative number.
    """
    days = 10
    # Non-TR price: 100, 100, ..., 100, 95 (day 5), 96, 97, 98, 99, 100
    non_tr = {_date(0): 100.0}
    for d in range(1, 5):
        non_tr[_date(d)] = 100.0
    non_tr[_date(5)] = 95.0
    for d in range(6, days + 1):
        non_tr[_date(d)] = 95.0 + (d - 5)  # 96, 97, 98, 99, 100

    daily_prices = {"AAPL.O": non_tr}
    prior = {"AAPL.O": 1.0}
    current = {"AAPL.O": 1.0}

    result = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=[],
        daily_prices=daily_prices,
        period_start=_date(0),
        period_end=_date(days),
    )

    # Hand-computed wrong answer: sum of daily price-only returns
    # Day 1..4: r=0
    # Day 5: r = 95/100 - 1 = -0.05
    # Day 6: r = 96/95 - 1
    # Day 7: r = 97/96 - 1
    # Day 8: r = 98/97 - 1
    # Day 9: r = 99/98 - 1
    # Day 10: r = 100/99 - 1
    expected_wrong = (
        -0.05
        + (96 / 95 - 1)
        + (97 / 96 - 1)
        + (98 / 97 - 1)
        + (99 / 98 - 1)
        + (100 / 99 - 1)
    )
    assert math.isclose(
        result["contributions"]["AAPL.O"], expected_wrong, abs_tol=1e-12
    )
    # Sanity: this is materially different from the TRUE ~5% total return
    # (the ex-date drop is not recovered in price-only terms by the climb back
    # to par; the numeric residual is dominated by the lost dividend amount).
    # True TR-period-return ~= +0.05 (5% dividend on flat-priced position).
    # Computed price-only result is far below that — proving the math breaks
    # without total-return prices.
    true_tr_return_approx = 0.05
    assert (
        abs(expected_wrong - true_tr_return_approx) > 0.04
    ), "non-TR result should be materially off from true TR return"


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
        validate_contributions(contributions=contributions, portfolio_total_return=total)
    err = excinfo.value
    # sum(contribs) - total = 0.08 - 0.081 = -0.001
    assert math.isclose(err.diff, -0.001, abs_tol=1e-12)
    assert err.tolerance == DEFAULT_RECONCILIATION_TOLERANCE


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
        {"symbol": "AAPL.O", "action": "trim", "date": _date(20), "weight_delta": -0.05},
        {"symbol": "MSFT.O", "action": "add", "date": _date(20), "weight_delta": +0.05},
        {"symbol": "AAPL.O", "action": "trim", "date": _date(10), "weight_delta": -0.05},
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
        {"symbol": "AAPL.O", "action": "trim", "date": _date(14), "weight_delta": -0.10},
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
        {"symbol": "AAPL.O", "action": "trim", "date": _date(14), "weight_delta": -0.10},
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
    dates = [(gap_start + datetime.timedelta(days=i)).isoformat() for i in range(n_days)]
    prices = [{"date": d, "close": base_price * (1 + 0.001 * i)} for i, d in enumerate(dates)]

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