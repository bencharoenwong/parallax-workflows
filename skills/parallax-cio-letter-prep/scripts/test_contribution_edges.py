"""Edge and degenerate-input coverage for contribution.py.

WHY A SECOND FILE. ``test_contribution.py`` covers the happy paths and four of
the validation raises. What it does not cover is the shape of data a real
period can hand this function and the fixture set never does: a flat period, a
period in which every holding loses, a zero price, a one-dated-price window, an
empty book, and the three trade-log validations that have no test at all.

Those are the cases where an assertion most easily becomes unfalsifiable --
a divisor that is zero, a sign that is already correct in the sample, a raise
whose branch nothing enters.

CONVENTIONS. Prices are round numbers chosen so every expected value is exact
in binary floating point, so the assertions below are ``==`` rather than
``isclose`` wherever the arithmetic really is exact. Where it is not, the
tolerance is an absolute literal and never a fraction of a signed quantity: a
tolerance scaled by a return is unsatisfiable the moment the return is negative.

One test is an HONESTY PIN: it asserts that the module's inner reconciliation
gate cannot fire for a computational reason, which is a property of how the
function accumulates rather than a bug to be fixed here.
"""

from __future__ import annotations

import pytest

from contribution import (
    DEFAULT_RECONCILIATION_TOLERANCE,
    daily_contribution,
)


def _date(day: int) -> str:
    """day 0 -> 2026-01-01, matching test_contribution.py."""
    return f"2026-01-{day + 1:02d}"


def _series(values: list[float]) -> dict[str, float]:
    return {_date(d): v for d, v in enumerate(values)}


def _run(prior, current, prices, trade_log=None, days=None):
    last = days if days is not None else max(
        len(s) for s in prices.values()) - 1
    return daily_contribution(
        prior_portfolio=prior,
        current_portfolio=current,
        trade_log=[] if trade_log is None else trade_log,
        daily_prices=prices,
        period_start=_date(0),
        period_end=_date(last),
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
    case, and a sign error is invisible in a book that contains a winner."""
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
    return, so an accidental double count or a dropped weight both surface."""
    prices = {"ZZAA.O": _series([100.0, 110.0, 121.0])}
    result = _run({"ZZAA.O": 1.0}, {"ZZAA.O": 1.0}, prices)
    assert result["contributions"]["ZZAA.O"] == result["portfolio_total_return"]
    assert result["portfolio_total_return"] == pytest.approx(0.2, abs=1e-12)


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
# Honesty pin: the inner reconciliation gate is structural
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
def test_inner_reconciliation_gate_cannot_fire_for_a_computational_reason(
        label, prior, paths):
    """HONESTY PIN, not a bug report.

    ``daily_contribution`` accumulates ``portfolio_total_return`` by adding the
    SAME per-holding term it adds into ``contributions[sym]``, in the same loop.
    The two therefore agree to float-associativity noise for any input, and the
    1-basis-point gate at the end of the function is unreachable in practice --
    the margin below is at least eight orders of magnitude.

    That is worth pinning rather than deleting, because the gate is real
    protection against a FUTURE change: the moment the period total is derived
    independently (geometric linking, a value-ratio, a server figure), the two
    sides can diverge and the gate starts doing work. If this test fails, that
    change happened, and the correct response is to write a real gate test.

    What already IS falsifiable is ``validate_contributions``, which takes both
    sides as arguments and is exercised against a mutated map in
    ``test_contribution.py``.
    """
    prices = {sym: _series(path) for sym, path in paths.items()}
    result = _run(prior, dict(prior), prices)
    diff = abs(result["reconciliation_diff"])
    assert diff < 1e-12
    assert diff < DEFAULT_RECONCILIATION_TOLERANCE / 1e8, (
        f"{label}: the inner gate is now within eight orders of magnitude of "
        f"firing — the period total may no longer be the same accumulation")
