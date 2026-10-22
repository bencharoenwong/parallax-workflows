"""Edge and degenerate-input coverage for contribution.py.

WHY A SECOND FILE. ``test_contribution.py`` covers the happy paths and most
of the validation raises. What it does not cover is the shape of data a real
period can hand this function and the fixture set never does: a flat period, a
period in which every holding loses, a zero price, a one-dated-price window, an
empty book, the trade-log validations, and the cases specific to replicating
the server's compounding/rebalancing method — a transient weight imbalance
that the reconciliation gate must actually catch, a dividend ex-date that is
valid under a loose (union-timeline) check but not under the tighter
per-symbol check this module enforces before resolving it (BUG-009: shifted or
unapplied, not rejected), a trade dated on a non-trading day (BUG-003), and
period_start itself falling on one (BUG-004).

CONVENTIONS. Prices are round numbers chosen so every expected value is exact
in binary floating point, so the assertions below are ``==`` rather than
``isclose`` wherever the arithmetic really is exact. Where it is not, the
tolerance is an absolute literal and never a fraction of a signed quantity: a
tolerance scaled by a return is unsatisfiable the moment the return is negative.
"""

from __future__ import annotations

import pytest

from contribution import (
    DEFAULT_RECONCILIATION_TOLERANCE,
    ReconciliationError,
    daily_contribution,
)


def _date(day: int) -> str:
    """day 0 -> 2026-01-01, matching test_contribution.py."""
    return f"2026-01-{day + 1:02d}"


def _series(values: list[float]) -> dict[str, float]:
    return {_date(d): v for d, v in enumerate(values)}


def _run(prior, current, prices, trade_log=None, days=None, dividend_schedule=None):
    last = days if days is not None else max(
        len(s) for s in prices.values()) - 1
    return daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=[] if trade_log is None else trade_log,
        daily_prices=prices,
        period_start=_date(0),
        period_end=_date(last),
        dividend_schedule=dividend_schedule,
    )


# --------------------------------------------------------------------------
# Degenerate periods the fixture set does not contain
# --------------------------------------------------------------------------

def test_flat_period_returns_exactly_zero_without_dividing_by_it():
    """Every price unchanged. The period total is exactly 0.0, and the function
    must reach that answer rather than a near-zero one or a ZeroDivisionError.

    A flat period is where any per-row identity expressed as a share of the
    period total stops being defined, which is why it gets its own test rather
    than riding along inside a mixed-sign case.
    """
    flat = _series([100.0] * 6)
    prior = {"ZZAA.O": 0.6, "ZZBB.O": 0.4}
    result = _run(prior, dict(prior), {"ZZAA.O": flat, "ZZBB.O": dict(flat)})

    assert result["portfolio_total_return"] == 0.0
    assert set(result["contributions"].values()) == {0.0}
    assert result["reconciliation_diff"] == 0.0


def test_losing_period_carries_a_negative_total_and_negative_contributions():
    """Every holding down. Nothing in the existing suite pins the all-negative
    case, and a sign error is invisible in a book that contains a winner.

    Each holding has exactly one non-zero-return day and no trade ever
    touches it, so the value entering that day is still its original weight
    — this fixture does not exercise compounding drift, only the sign path.
    """
    prior = {"ZZAA.O": 0.5, "ZZBB.O": 0.5}
    prices = {
        "ZZAA.O": _series([100.0, 100.0, 80.0]),   # -20% on return-day 2
        "ZZBB.O": _series([100.0, 50.0, 50.0]),    # -50% on return-day 1
    }
    result = _run(prior, dict(prior), prices)

    assert result["contributions"]["ZZAA.O"] == pytest.approx(-0.10, abs=1e-12)
    assert result["contributions"]["ZZBB.O"] == pytest.approx(-0.25, abs=1e-12)
    assert result["portfolio_total_return"] < 0
    assert all(c < 0 for c in result["contributions"].values())
    # The tolerance is an absolute literal. Expressed as a fraction of the
    # period return it would be negative here and the assertion unsatisfiable.
    assert abs(result["reconciliation_diff"]) < 1e-12


def test_single_holding_book_reconciles_against_itself():
    """N=1 is the degenerate weight case: the one contribution IS the portfolio
    return, so an accidental double count or a dropped weight both surface.

    Two consecutive +10% days COMPOUND: (1.1 * 1.1) - 1 = 0.21, not the 0.20
    an arithmetic sum would give — this is the clearest single-number
    regression against the retired arithmetic-summing model.
    """
    prices = {"ZZAA.O": _series([100.0, 110.0, 121.0])}
    result = _run({"ZZAA.O": 1.0}, {"ZZAA.O": 1.0}, prices)
    assert result["contributions"]["ZZAA.O"] == result["portfolio_total_return"]
    assert result["portfolio_total_return"] == pytest.approx(0.21, abs=1e-12)


def test_a_zero_weight_holding_contributes_nothing_but_is_still_reported():
    """A holding at zero weight must appear in the contributions map with 0.0,
    not be silently dropped: the letter's coverage-gap accounting counts rows,
    and a vanished row reads as a holding that was never held."""
    prior = {"ZZAA.O": 1.0, "ZZBB.O": 0.0}
    prices = {"ZZAA.O": _series([100.0, 110.0]),
              "ZZBB.O": _series([100.0, 200.0])}
    result = _run(prior, dict(prior), prices)
    assert result["contributions"]["ZZBB.O"] == 0.0
    assert result["portfolio_total_return"] == pytest.approx(0.1, abs=1e-12)


# --------------------------------------------------------------------------
# Raises with no existing coverage
# --------------------------------------------------------------------------

def test_zero_prior_price_raises_rather_than_dividing_by_it():
    """A zero close is what a suspended or unlisted line returns. Unguarded it
    is a ZeroDivisionError several frames from the input that caused it."""
    prices = {"ZZAA.O": _series([0.0, 100.0])}
    with pytest.raises(ValueError, match="(?i)zero"):
        _run({"ZZAA.O": 1.0}, {"ZZAA.O": 1.0}, prices)


def test_empty_prior_portfolio_raises():
    prices = {"ZZAA.O": _series([100.0, 110.0])}
    with pytest.raises(ValueError, match="(?i)empty"):
        _run({}, {"ZZAA.O": 1.0}, prices)


def test_empty_current_portfolio_raises():
    prices = {"ZZAA.O": _series([100.0, 110.0])}
    with pytest.raises(ValueError, match="(?i)empty"):
        _run({"ZZAA.O": 1.0}, {}, prices)


def test_a_single_dated_price_raises_rather_than_returning_zero():
    """One price in the window means no return day at all. Returning 0.0 here
    would be indistinguishable from a genuinely flat period -- the case
    immediately above -- so it has to raise."""
    prices = {"ZZAA.O": {_date(0): 100.0}}
    with pytest.raises(ValueError, match="(?i)at least 2"):
        daily_contribution(
            prior_portfolio={"ZZAA.O": 1.0},
            current_portfolio={"ZZAA.O": 1.0},
            trade_log=[],
            daily_prices=prices,
            period_start=_date(0),
            period_end=_date(0),
        )


def test_unrecognised_trade_action_raises():
    """The action vocabulary is validated but nothing exercised the branch. A
    typo'd action silently accepted would apply its weight_delta anyway."""
    prices = {"ZZAA.O": _series([100.0, 110.0]),
              "ZZBB.O": _series([100.0, 110.0])}
    trade_log = [{"symbol": "ZZAA.O", "action": "rebalance",
                  "date": _date(0), "weight_delta": -0.1},
                 {"symbol": "ZZBB.O", "action": "add",
                  "date": _date(0), "weight_delta": +0.1}]
    with pytest.raises(ValueError, match="(?i)action"):
        _run({"ZZAA.O": 0.5, "ZZBB.O": 0.5},
             {"ZZAA.O": 0.4, "ZZBB.O": 0.6}, prices, trade_log)


def test_trade_dated_outside_the_period_raises():
    prices = {"ZZAA.O": _series([100.0, 110.0, 120.0]),
              "ZZBB.O": _series([100.0, 110.0, 120.0])}
    trade_log = [{"symbol": "ZZAA.O", "action": "trim",
                  "date": _date(9), "weight_delta": -0.1}]
    with pytest.raises(ValueError, match="(?i)outside period"):
        _run({"ZZAA.O": 0.5, "ZZBB.O": 0.5},
             {"ZZAA.O": 0.4, "ZZBB.O": 0.6}, prices, trade_log, days=2)


def test_trade_missing_a_required_key_raises():
    prices = {"ZZAA.O": _series([100.0, 110.0])}
    trade_log = [{"symbol": "ZZAA.O", "action": "trim", "date": _date(0)}]
    with pytest.raises(ValueError, match="(?i)missing key"):
        _run({"ZZAA.O": 1.0}, {"ZZAA.O": 1.0}, prices, trade_log)


# --------------------------------------------------------------------------
# Trade timing at the boundaries of the window
# --------------------------------------------------------------------------

def test_a_trade_dated_period_start_is_in_force_for_the_first_return_day():
    """The documented convention: a trade applies AFTER its date's close, and
    period_start's close precedes return-day 1, so a start-dated trade affects
    every return in the window."""
    prices = {"ZZAA.O": _series([100.0, 110.0]),
              "ZZBB.O": _series([100.0, 100.0])}
    trade_log = [{"symbol": "ZZAA.O", "action": "add",
                  "date": _date(0), "weight_delta": +0.5},
                 {"symbol": "ZZBB.O", "action": "trim",
                  "date": _date(0), "weight_delta": -0.5}]
    result = _run({"ZZAA.O": 0.5, "ZZBB.O": 0.5},
                  {"ZZAA.O": 1.0, "ZZBB.O": 0.0}, prices, trade_log)
    # Post-trade weight 1.0, not the prior 0.5.
    assert result["contributions"]["ZZAA.O"] == pytest.approx(0.1, abs=1e-12)


def test_a_trade_dated_period_end_moves_no_return_at_all():
    """Its date's close is the last one in the window, so the new weight never
    earns anything. It still has to reconcile against current_portfolio, which
    is why it is accepted rather than rejected."""
    prices = {"ZZAA.O": _series([100.0, 110.0]),
              "ZZBB.O": _series([100.0, 100.0])}
    trade_log = [{"symbol": "ZZAA.O", "action": "trim",
                  "date": _date(1), "weight_delta": -0.5},
                 {"symbol": "ZZBB.O", "action": "add",
                  "date": _date(1), "weight_delta": +0.5}]
    result = _run({"ZZAA.O": 0.5, "ZZBB.O": 0.5},
                  {"ZZAA.O": 0.0, "ZZBB.O": 1.0}, prices, trade_log)
    # Weight during the only return day was still the prior 0.5.
    assert result["contributions"]["ZZAA.O"] == pytest.approx(0.05, abs=1e-12)


# --------------------------------------------------------------------------
# dividend_schedule validation (new branches, no existing coverage)
# --------------------------------------------------------------------------

def test_dividend_schedule_unknown_symbol_raises():
    """A dividend_schedule entry naming a symbol absent from
    prior/current/trade_log must raise rather than being silently ignored
    -- an unknown symbol here is almost always a typo'd RIC."""
    prices = {"ZZAA.O": _series([100.0, 110.0, 120.0])}
    with pytest.raises(ValueError, match="(?i)not in"):
        _run({"ZZAA.O": 1.0}, {"ZZAA.O": 1.0}, prices,
             dividend_schedule={"ZZBB.O": {_date(1): 1.0}}, days=2)


def test_dividend_schedule_ex_date_not_in_timeline_marks_unapplied_when_no_later_close():
    """BUG-009: an ex_date strictly inside (period_start, period_end] but
    with no price data on that exact date (e.g. a holiday the price feed
    skips) no longer raises. The server includes such a dividend via the
    vendor return on the NEXT trading day it has a close for that symbol;
    this module replicates that by shifting the dividend forward. Here
    ZZAA.O's own series ends at date 2 and the dividend is dated date 3,
    so there is no later close in the period to shift to -- the dividend
    is UNAPPLIED, not dropped silently: it is named in the result so the
    caller can mark the holding dividend-unchecked."""
    prices = {"ZZAA.O": _series([100.0, 110.0, 120.0])}  # dates 0, 1, 2 only
    result = daily_contribution(
        prior_portfolio={"ZZAA.O": 1.0},
        current_portfolio={"ZZAA.O": 1.0},
        trade_log=[],
        daily_prices=prices,
        period_start=_date(0),
        period_end=_date(5),
        dividend_schedule={"ZZAA.O": {_date(3): 1.0}},
    )
    assert result["dividends_unapplied"] == {"ZZAA.O": [_date(3)]}
    assert result["dividends_shifted"] == {}
    # Unapplied means the price-only path ran: 120/100 - 1 = 0.20.
    assert result["contributions"]["ZZAA.O"] == pytest.approx(0.20, abs=1e-12)


def test_dividend_schedule_ex_date_not_an_actual_close_shifts_to_the_next_one():
    """BUG-009: an ex_date that IS in the union timeline (because a
    DIFFERENT symbol has a price that day) but is NOT an actual close for
    the symbol the dividend names is SHIFTED to that symbol's own next
    actual close in the period rather than rejected -- an ex-date is a
    trading day on the symbol's OWN exchange, and a loose union-timeline
    check would otherwise let the add-back land on a day this symbol never
    actually traded.

    ZZAA.O has prices on dates 0, 1, 2, 4 (date 3 is a gap for ZZAA.O
    specifically). ZZBB.O has a price on every date 0-4, which is what
    puts date 3 in the union timeline. The dividend below names ZZAA.O on
    date 3; it must shift to ZZAA.O's own next close, date 4.
    """
    prices = {
        "ZZAA.O": {_date(0): 100.0, _date(1): 110.0, _date(2): 120.0,
                   _date(4): 130.0},
        "ZZBB.O": {_date(0): 100.0, _date(1): 100.0, _date(2): 100.0,
                   _date(3): 100.0, _date(4): 100.0},
    }
    prior = {"ZZAA.O": 0.5, "ZZBB.O": 0.5}
    result = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=dict(prior),
        trade_log=[],
        daily_prices=prices,
        period_start=_date(0),
        period_end=_date(4),
        dividend_schedule={"ZZAA.O": {_date(3): 1.0}},
    )
    assert result["dividends_shifted"] == {"ZZAA.O": [(_date(3), _date(4))]}
    assert result["dividends_unapplied"] == {}
    # No rebalance ever touches ZZAA, so its contribution telescopes exactly
    # to its own compounded end/start factor minus 1, scaled by its constant
    # weight. Date 3 is a zero-return forward-fill for ZZAA (its own series
    # has no date-3 close); the shifted dividend lands on date 4 instead:
    # factor = (110/100) * (120/110) * (120/120) * ((130+1)/120) = 131/100.
    expected_zzaa = 0.5 * (131.0 / 100.0 - 1.0)
    assert result["contributions"]["ZZAA.O"] == pytest.approx(expected_zzaa, abs=1e-12)


def test_dividend_schedule_dated_period_start_raises():
    """period_start has no return day (it is only the prior price for
    return-day 1), so a dividend dated period_start can never be applied.
    Rejecting it is consistent with how trade_log applies at period_start
    (before return-day 1) but a dividend has nothing to attach to there."""
    prices = {"ZZAA.O": _series([100.0, 110.0, 120.0])}
    with pytest.raises(ValueError, match="(?i)outside period"):
        _run({"ZZAA.O": 1.0}, {"ZZAA.O": 1.0}, prices,
             dividend_schedule={"ZZAA.O": {_date(0): 1.0}}, days=2)


def test_dividend_schedule_rejects_negative_cash_amount():
    """BUG-005: a negative dividend must be rejected at validation time
    rather than quietly flowing into the return formula as a cash
    deduction -- no observed divtypecode this schedule is meant to carry
    (recurring cash, or special-cash SPL) is ever negative."""
    prices = {"ZZAA.O": _series([100.0, 110.0, 120.0])}
    with pytest.raises(ValueError, match="(?i)finite and >= 0"):
        _run({"ZZAA.O": 1.0}, {"ZZAA.O": 1.0}, prices,
             dividend_schedule={"ZZAA.O": {_date(1): -1.0}}, days=2)


def test_dividend_schedule_rejects_non_finite_cash_amount():
    """BUG-005: NaN/inf must be rejected at validation time -- letting one
    through would poison every downstream `>` comparison, which treats NaN
    as always-False and would make a broken dividend look reconciled."""
    prices = {"ZZAA.O": _series([100.0, 110.0, 120.0])}
    with pytest.raises(ValueError, match="(?i)finite and >= 0"):
        _run({"ZZAA.O": 1.0}, {"ZZAA.O": 1.0}, prices,
             dividend_schedule={"ZZAA.O": {_date(1): float("nan")}}, days=2)


def test_dividend_schedule_applies_with_the_weight_in_force_on_the_ex_date():
    """The dividend add-back must use the SAME weight the price return
    uses for that day -- i.e. it respects mid-period trades exactly like
    the price-return term does. ZZAA is trimmed from 1.0 to 0.5 effective
    return-day 2 (trade dated day 1); the ex-date (day 2) dividend must
    therefore be weighted at 0.5, not the prior 1.0. Every price here is
    flat except the dividend itself, so there is no compounding drift to
    separately account for."""
    prices = {"ZZAA.O": _series([100.0, 100.0, 100.0]),
              "ZZBB.O": _series([100.0, 100.0, 100.0])}
    trade_log = [{"symbol": "ZZAA.O", "action": "trim",
                  "date": _date(1), "weight_delta": -0.5},
                 {"symbol": "ZZBB.O", "action": "add",
                  "date": _date(1), "weight_delta": +0.5}]
    result = _run({"ZZAA.O": 1.0, "ZZBB.O": 0.0},
                  {"ZZAA.O": 0.5, "ZZBB.O": 0.5},
                  prices, trade_log,
                  dividend_schedule={"ZZAA.O": {_date(2): 4.0}})
    # Day 2 return for ZZAA: (100 + 4.0)/100 - 1 = 0.04, weighted at the
    # post-trade 0.5 -> contribution 0.02. Day 1 return is flat (0.0).
    assert result["contributions"]["ZZAA.O"] == pytest.approx(0.02, abs=1e-12)
    assert result["portfolio_total_return"] == pytest.approx(0.02, abs=1e-12)


def test_dividend_on_a_rebalance_date_with_several_payers_uses_the_pre_rebalance_weight():
    """BUG-013: a dividend landing ON a rebalance date, across several
    dividend-paying holdings at once. Both dividends must be weighted at
    the PRE-rebalance weight (the trade applies after the day's close, and
    the day's return — dividend included — accrues before that).

    3 holdings A=0.4, B=0.3, C=0.3, all flat prices. On day 1 (the only
    rebalance date): A stays flat (r=0); B pays a 4.0 dividend on a flat
    100 close (r=0.04); C pays a 2.0 dividend on a flat 100 close (r=0.02).
    The same day, a trade shifts A +0.10 (0.4 -> 0.5) and B -0.10
    (0.3 -> 0.2); C is untouched (0.3).

    Hand-computed walk (initial value A=0.4, B=0.3, C=0.3):
      price_pl_A = 0.4*0 = 0      -> pre-rebal value_A = 0.4
      price_pl_B = 0.3*0.04 = 0.012 -> pre-rebal value_B = 0.312
      price_pl_C = 0.3*0.02 = 0.006 -> pre-rebal value_C = 0.306
      total = 0.4 + 0.312 + 0.306 = 1.018
      reweight: value_A = 0.5*1.018 = 0.509
                value_B = 0.2*1.018 = 0.2036
                value_C = 0.3*1.018 = 0.3054
    No further days move. contributions: A=0, B=0.012, C=0.006.
    Final total = 1.018 -> portfolio_total_return = 0.018, matching the sum.
    """
    prices = {
        "A": _series([100.0, 100.0]),
        "B": _series([100.0, 100.0]),
        "C": _series([100.0, 100.0]),
    }
    prior = {"A": 0.4, "B": 0.3, "C": 0.3}
    current = {"A": 0.5, "B": 0.2, "C": 0.3}
    trade_log = [
        {"symbol": "A", "action": "add", "date": _date(1), "weight_delta": +0.10},
        {"symbol": "B", "action": "trim", "date": _date(1), "weight_delta": -0.10},
    ]
    dividend_schedule = {"B": {_date(1): 4.0}, "C": {_date(1): 2.0}}

    result = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=trade_log,
        daily_prices=prices,
        period_start=_date(0),
        period_end=_date(1),
        dividend_schedule=dividend_schedule,
    )

    assert result["contributions"]["A"] == pytest.approx(0.0, abs=1e-12)
    assert result["contributions"]["B"] == pytest.approx(0.012, abs=1e-12)
    assert result["contributions"]["C"] == pytest.approx(0.006, abs=1e-12)
    assert result["portfolio_total_return"] == pytest.approx(0.018, abs=1e-12)
    assert abs(result["reconciliation_diff"]) < 1e-12


# --------------------------------------------------------------------------
# Reconciliation gate: exact with no rebalance, genuinely falsifiable with one
# --------------------------------------------------------------------------

BOOKS = [
    # (label, prior weights, price series per symbol)
    ("flat", {"ZZAA.O": 0.5, "ZZBB.O": 0.5},
     {"ZZAA.O": [100.0] * 5, "ZZBB.O": [100.0] * 5}),
    ("all-up", {"ZZAA.O": 0.25, "ZZBB.O": 0.75},
     {"ZZAA.O": [100.0, 101.0, 103.0, 107.0, 115.0],
      "ZZBB.O": [50.0, 50.5, 51.5, 53.5, 57.5]}),
    ("all-down", {"ZZAA.O": 0.6, "ZZBB.O": 0.4},
     {"ZZAA.O": [100.0, 95.0, 90.0, 85.0, 80.0],
      "ZZBB.O": [200.0, 190.0, 180.0, 170.0, 160.0]}),
    ("mixed", {"ZZAA.O": 0.3, "ZZBB.O": 0.7},
     {"ZZAA.O": [100.0, 120.0, 90.0, 130.0, 70.0],
      "ZZBB.O": [80.0, 76.0, 88.0, 72.0, 96.0]}),
]


@pytest.mark.parametrize("label,prior,paths", BOOKS, ids=[b[0] for b in BOOKS])
def test_inner_reconciliation_gate_is_exact_with_no_rebalance(label, prior, paths):
    """No trades in any of these books, so no rebalance ever reweights the
    per-holding values. Each holding's own compounded value therefore
    telescopes exactly to `value_final - value_initial`, and summing those
    per-holding telescoping sums gives exactly `final_total - initial_total`
    with no cross-holding transfer involved at all -- the diff is floating-
    point noise, not an approximation.

    This is NOT a claim that the gate can never fire (see
    test_reconciliation_gate_fires_on_a_transient_weight_imbalance_that_nets_to_zero
    immediately below for a case where it does): it is a claim about these
    specific no-rebalance books.
    """
    prices = {sym: _series(path) for sym, path in paths.items()}
    result = _run(prior, dict(prior), prices)
    diff = abs(result["reconciliation_diff"])
    assert diff < 1e-12


def test_reconciliation_gate_fires_on_a_transient_weight_imbalance_that_nets_to_zero():
    """A genuinely reachable failure, not a hypothetical one.

    Two holdings, 0.5/0.5, every price flat (every daily return is exactly
    0 for both holdings on every day) -- so a correct computation must
    report portfolio_total_return == 0.0 and every contribution == 0.0.

    The trade_log has an UNBALANCED delta on day 1 (A +0.10, nothing
    offsetting it: target weights sum to 1.1 for one day) followed by a
    CORRECTIVE delta on day 2 that undoes it (A -0.10: target weights sum
    back to 1.0). Net effect on current_portfolio: none -- the final
    target weights are exactly the prior weights, so BOTH the weight-sum
    validation and the current_portfolio cross-check pass cleanly.

    But the day-1 rebalance reweighted the book using target weights that
    summed to 1.1, which manufactures 10% of value out of nothing (the
    server's own reweight step, `new_weights * current_value_base`, does
    the same thing if handed unbalanced weights -- this is a faithful
    replication, not an added bug). That extra value is never undone by
    the day-2 correction, which only fixes the WEIGHTS, not the total. The
    per-holding P&L sum (every daily return was 0, so it is exactly 0)
    diverges from the actual final-total-implied return (+0.10) by far
    more than the 1bp inner tolerance, and the gate fires.
    """
    prices = {
        "A": _series([100.0, 100.0, 100.0]),
        "B": _series([100.0, 100.0, 100.0]),
    }
    prior = {"A": 0.5, "B": 0.5}
    current = {"A": 0.5, "B": 0.5}  # unchanged net of the round-trip delta
    trade_log = [
        {"symbol": "A", "action": "add", "date": _date(1), "weight_delta": +0.10},
        {"symbol": "A", "action": "trim", "date": _date(2), "weight_delta": -0.10},
    ]

    with pytest.raises(ReconciliationError) as excinfo:
        daily_contribution(
            prior_portfolio=prior,
            current_portfolio=current,
            trade_log=trade_log,
            daily_prices=prices,
            period_start=_date(0),
            period_end=_date(2),
        )
    err = excinfo.value
    assert abs(err.diff) > DEFAULT_RECONCILIATION_TOLERANCE
    # The manufactured value is ~10% of the book -- nowhere near the 1bp gate.
    assert abs(err.diff) > 0.05


# --------------------------------------------------------------------------
# BUG-003: a trade dated on a non-trading day must not be dropped
# --------------------------------------------------------------------------

def test_trade_dated_on_a_weekend_is_applied_after_the_prior_trading_days_close():
    """2026-01-03/04 (day 2/3) are Saturday/Sunday; neither holding has a
    price on either date, so they never enter `timeline` at all. A trade
    dated Sunday (day 3) must still take effect -- it is bucketed under
    the latest timeline date <= its own date (day 1, Friday) and applied
    after THAT date's close, exactly matching the server's calendar-daily
    rebalance (which would reweight on day 3 using day 3's own
    forward-filled zero return, so the new weights earn nothing until the
    next date that actually has one -- day 4, Monday).

    AAPL jumps +10% on day 4 (Monday); MSFT stays flat throughout. The
    trade shifts AAPL 0.5 -> 1.0 / MSFT 0.5 -> 0.0. If the trade were
    dropped (the bug), AAPL would still be weighted at 0.5 when it jumps,
    halving the answer.
    """
    prices = {
        "AAPL.O": {_date(0): 100.0, _date(1): 100.0, _date(4): 110.0,
                   _date(5): 110.0},
        "MSFT.O": {_date(0): 100.0, _date(1): 100.0, _date(4): 100.0,
                   _date(5): 100.0},
    }
    prior = {"AAPL.O": 0.5, "MSFT.O": 0.5}
    current = {"AAPL.O": 1.0, "MSFT.O": 0.0}
    trade_log = [
        {"symbol": "AAPL.O", "action": "add", "date": _date(3),
         "weight_delta": +0.5},
        {"symbol": "MSFT.O", "action": "trim", "date": _date(3),
         "weight_delta": -0.5},
    ]

    result = daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=trade_log,
        daily_prices=prices,
        period_start=_date(0),
        period_end=_date(5),
    )

    assert result["contributions"]["AAPL.O"] == pytest.approx(0.10, abs=1e-12)
    assert result["contributions"]["MSFT.O"] == pytest.approx(0.0, abs=1e-12)
    assert result["portfolio_total_return"] == pytest.approx(0.10, abs=1e-12)
    assert abs(result["reconciliation_diff"]) < 1e-12


def test_trade_dated_on_saturday_maps_to_the_same_effective_date_as_sunday():
    """Both weekend dates (Saturday day 2, Sunday day 3) are absent from
    `timeline`, so both must snap to the SAME last trading day (day 1,
    Friday) and produce an identical result -- the exact calendar day
    within the gap must not matter, only "which trading day precedes it"."""
    prices = {
        "AAPL.O": {_date(0): 100.0, _date(1): 100.0, _date(4): 110.0},
        "MSFT.O": {_date(0): 100.0, _date(1): 100.0, _date(4): 100.0},
    }
    prior = {"AAPL.O": 0.5, "MSFT.O": 0.5}
    current = {"AAPL.O": 1.0, "MSFT.O": 0.0}

    def _result_for(trade_date):
        trade_log = [
            {"symbol": "AAPL.O", "action": "add", "date": trade_date,
             "weight_delta": +0.5},
            {"symbol": "MSFT.O", "action": "trim", "date": trade_date,
             "weight_delta": -0.5},
        ]
        return daily_contribution(
            prior_portfolio=prior,
            current_portfolio=current,
            trade_log=trade_log,
            daily_prices=prices,
            period_start=_date(0),
            period_end=_date(4),
        )

    saturday_result = _result_for(_date(2))
    sunday_result = _result_for(_date(3))
    assert saturday_result["contributions"] == sunday_result["contributions"]
    assert (
        saturday_result["portfolio_total_return"]
        == sunday_result["portfolio_total_return"]
    )


# --------------------------------------------------------------------------
# BUG-004: period_start on a non-trading day forward-fills, not raises
# --------------------------------------------------------------------------

def test_period_start_on_a_weekend_forward_fills_from_the_last_close_before_it():
    """period_start = day 2 (Saturday). AAPL's series has no price on day 2
    itself, only day 1 (Friday, BEFORE period_start -- used only to seed
    the period_start anchor) and day 4 (Monday) / day 5 onward. This must
    forward-fill the period_start anchor from day 1's close rather than
    raising "no earlier price to forward-fill from"."""
    prices = {
        "AAPL.O": {_date(1): 100.0, _date(4): 110.0, _date(5): 110.0},
    }
    result = daily_contribution(
        prior_portfolio={"AAPL.O": 1.0},
        current_portfolio={"AAPL.O": 1.0},
        trade_log=[],
        daily_prices=prices,
        period_start=_date(2),
        period_end=_date(5),
    )
    assert result["contributions"]["AAPL.O"] == pytest.approx(0.10, abs=1e-12)
    assert result["portfolio_total_return"] == pytest.approx(0.10, abs=1e-12)
    assert abs(result["reconciliation_diff"]) < 1e-12


def test_period_start_on_a_weekend_still_raises_with_no_price_at_all_before_it():
    """Unlike the case above, if a symbol has NO price on or before
    period_start, there is genuinely nothing to forward-fill from, and the
    function must still raise -- forward-fill extends the contract, it
    does not remove the floor."""
    prices = {"AAPL.O": {_date(4): 110.0, _date(5): 115.0}}
    with pytest.raises(ValueError, match="(?i)no earlier price"):
        daily_contribution(
            prior_portfolio={"AAPL.O": 1.0},
            current_portfolio={"AAPL.O": 1.0},
            trade_log=[],
            daily_prices=prices,
            period_start=_date(2),
            period_end=_date(5),
        )


# --------------------------------------------------------------------------
# BUG-008: a zero-weight, zero-value holding with a zero close must not
# raise; a non-numeric or non-finite weight_delta must raise ValueError
# (not an uncaught TypeError several frames downstream).
# --------------------------------------------------------------------------

def test_zero_weight_holding_with_a_zero_close_does_not_raise():
    """ZZBB.O is held at weight 0.0 throughout (never traded in or out) and
    its entire price series is a placeholder zero. Nothing ever multiplies
    that zero close by a nonzero value, so there is nothing to divide by
    and nothing to raise about -- unlike test_zero_prior_price_raises...,
    where the zero-priced holding carries full weight 1.0."""
    prices = {
        "ZZAA.O": _series([100.0, 110.0]),
        "ZZBB.O": _series([0.0, 0.0]),
    }
    prior = {"ZZAA.O": 1.0, "ZZBB.O": 0.0}
    result = _run(prior, dict(prior), prices)
    assert result["contributions"]["ZZBB.O"] == 0.0
    assert result["contributions"]["ZZAA.O"] == pytest.approx(0.10, abs=1e-12)
    assert result["portfolio_total_return"] == pytest.approx(0.10, abs=1e-12)


def test_non_numeric_weight_delta_raises_value_error_not_type_error():
    prices = {"ZZAA.O": _series([100.0, 110.0]),
              "ZZBB.O": _series([100.0, 110.0])}
    trade_log = [{"symbol": "ZZAA.O", "action": "trim",
                  "date": _date(0), "weight_delta": "oops"},
                 {"symbol": "ZZBB.O", "action": "add",
                  "date": _date(0), "weight_delta": 0.0}]
    with pytest.raises(ValueError, match="(?i)weight_delta must be a number"):
        _run({"ZZAA.O": 0.5, "ZZBB.O": 0.5},
             {"ZZAA.O": 0.5, "ZZBB.O": 0.5}, prices, trade_log)


def test_non_finite_weight_delta_raises_value_error():
    prices = {"ZZAA.O": _series([100.0, 110.0]),
              "ZZBB.O": _series([100.0, 110.0])}
    trade_log = [{"symbol": "ZZAA.O", "action": "trim",
                  "date": _date(0), "weight_delta": float("nan")},
                 {"symbol": "ZZBB.O", "action": "add",
                  "date": _date(0), "weight_delta": 0.0}]
    with pytest.raises(ValueError, match="(?i)weight_delta must be finite"):
        _run({"ZZAA.O": 0.5, "ZZBB.O": 0.5},
             {"ZZAA.O": 0.5, "ZZBB.O": 0.5}, prices, trade_log)
