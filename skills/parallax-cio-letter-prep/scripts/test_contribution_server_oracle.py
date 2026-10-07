"""BUG-006: an independent server-walk oracle for daily_contribution().

Ports the server-replica walk from the scratch simulator used to validate
this module against the live Parallax server (`sim.py`, matched to the
real server at 8.5e-16 over 300 random single-currency books). That
simulator's `server()` iterates every CALENDAR day (not just the days a
price feed happens to have), applies each day's `changepercent` (0 on a
non-trading day) to the pre-rebalance value first, then reweights on any
date present in the trade/portfolio-snapshot map — the same rebalance
timing `contribution.py` targets. Here it is ported with `lpb=None`
(no FX; `L=1` everywhere), since this module has no currency notion, and
extended to accumulate PER-HOLDING price_pl so it can be checked against
`contributions`, not only the portfolio total.

This is a cross-check BETWEEN TWO INDEPENDENT IMPLEMENTATIONS of the same
method, not a hand-derived expected value: the oracle below shares no code
with `contribution.py` beyond the economic method itself (iterate every
calendar day; rebalance after a day's return using that day's own
`changepercent`, 0 when there is no close).
"""

from __future__ import annotations

import datetime as dt

import pytest

from contribution import daily_contribution


def _server_oracle(
    start: str,
    end: str,
    portfolio: list[tuple[str, dict[str, float]]],
    closes: dict[str, dict[str, float]],
    divs: dict[str, dict[str, float]],
    initial: float = 10000.0,
) -> tuple[dict[str, float], float, float]:
    """Ported from sim.py's `server()`, `lpb=None` (L=1 everywhere, no FX),
    extended to accumulate per-holding price_pl.

    Returns (per_holding_price_pl, total_price_pl_over_initial, total_return).
    """
    d0 = dt.date.fromisoformat(start)
    d1 = dt.date.fromisoformat(end)
    dates = [(d0 + dt.timedelta(i)).isoformat() for i in range((d1 - d0).days + 1)]
    rics = sorted({r for _, w in portfolio for r in w})

    cp: dict[str, dict[str, float]] = {r: {} for r in rics}
    for r in rics:
        last = None
        for d in dates:
            if d in closes[r]:
                c = closes[r][d]
                cp[r][d] = 0.0 if last is None else (c + divs.get(r, {}).get(d, 0.0)) / last - 1
                last = c
            else:
                cp[r][d] = 0.0

    W = {d: w for d, w in portfolio}
    price_pl = {r: 0.0 for r in rics}
    vl: dict[str, float] | None = None
    first = True
    for d in dates:
        if first:
            if d not in W:
                continue
            w = W[d]
            vl = {r: w.get(r, 0) * initial for r in rics}
            first = False
            continue
        sb = dict(vl)
        for r in rics:
            price_pl[r] += sb[r] * cp[r][d]
        vl = {r: vl[r] * (1 + cp[r][d]) for r in rics}
        if d in W:
            tot = sum(vl.values())
            vl = {r: W[d].get(r, 0) * tot for r in rics}

    final = sum(vl.values())
    total_price_pl = sum(price_pl.values())
    return price_pl, total_price_pl / initial, final / initial - 1


# --------------------------------------------------------------------------
# The oracle book: 3 holdings, 2 rebalances (one on a trading day, one on a
# Saturday -- BUG-003), a dividend on a real close date, built exactly as
# SKILL.md Step 2 builds the analyze_portfolio `portfolio` array (one entry
# at period_start, one per distinct trade date, cumulative post-trade
# weights), which also exercises BUG-005 (no duplicate period_start entry,
# since no trade is dated period_start here).
# --------------------------------------------------------------------------

_PERIOD_START = "2026-02-02"  # Monday
_PERIOD_END = "2026-02-13"  # Friday
_REBAL_1 = "2026-02-04"  # Wednesday -- ordinary trading-day rebalance
_REBAL_2 = "2026-02-07"  # Saturday -- BUG-003: non-trading-day rebalance
_DIV_DATE = "2026-02-11"  # Wednesday -- an actual close for CCC
_DIV_AMOUNT = 1.3

_TRADING_DAYS = [
    "2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06",
    "2026-02-09", "2026-02-10", "2026-02-11", "2026-02-12", "2026-02-13",
]

_AAA_CLOSES = [100.0, 101.0, 102.0, 103.0, 104.0, 106.0, 107.0, 106.0, 108.0, 109.0]
_BBB_CLOSES = [50.0, 49.0, 51.0, 50.0, 52.0, 53.0, 52.0, 54.0, 55.0, 54.0]
_CCC_CLOSES = [200.0, 202.0, 201.0, 205.0, 207.0, 210.0, 208.0, 209.0, 211.0, 214.0]

_CLOSES = {
    "AAA.O": dict(zip(_TRADING_DAYS, _AAA_CLOSES)),
    "BBB.O": dict(zip(_TRADING_DAYS, _BBB_CLOSES)),
    "CCC.O": dict(zip(_TRADING_DAYS, _CCC_CLOSES)),
}
_DIVS = {"CCC.O": {_DIV_DATE: _DIV_AMOUNT}}

_PRIOR = {"AAA.O": 0.5, "BBB.O": 0.3, "CCC.O": 0.2}
# Rebalance 1 (Wed 02-04): AAA -0.1, BBB +0.1, CCC unchanged.
_AFTER_REBAL_1 = {"AAA.O": 0.4, "BBB.O": 0.4, "CCC.O": 0.2}
# Rebalance 2 (Sat 02-07): BBB -0.15, CCC +0.15, AAA unchanged.
_CURRENT = {"AAA.O": 0.4, "BBB.O": 0.25, "CCC.O": 0.35}

_TRADE_LOG = [
    {"symbol": "AAA.O", "action": "trim", "date": _REBAL_1, "weight_delta": -0.1},
    {"symbol": "BBB.O", "action": "add", "date": _REBAL_1, "weight_delta": +0.1},
    {"symbol": "BBB.O", "action": "trim", "date": _REBAL_2, "weight_delta": -0.15},
    {"symbol": "CCC.O", "action": "add", "date": _REBAL_2, "weight_delta": +0.15},
]

# Exactly how SKILL.md Step 2 Batch A builds the analyze_portfolio
# `portfolio` array: one entry at period_start, one per distinct trade
# date, cumulative post-trade weights.
_PORTFOLIO_SNAPSHOTS: list[tuple[str, dict[str, float]]] = [
    (_PERIOD_START, _PRIOR),
    (_REBAL_1, _AFTER_REBAL_1),
    (_REBAL_2, _CURRENT),
]


def test_server_oracle_matches_contribution_py_within_1e9():
    """Two independent implementations of the same method -- this module's
    `daily_contribution` and the ported server-walk oracle above -- must
    agree to within 1e-9 on a book exercising two rebalances (one on a
    trading day, one on a Saturday -- BUG-003), a dividend on a real close
    (BUG-006's "dividend" requirement), and a weekend gap coinciding with
    the second rebalance (the gap requirement)."""
    oracle_per_holding, oracle_total_price_pl, oracle_total_return = _server_oracle(
        _PERIOD_START, _PERIOD_END, _PORTFOLIO_SNAPSHOTS, _CLOSES, _DIVS,
    )

    # No dividend-driven cross term and no rebalance-manufactured value in
    # this fixture (both rebalances' deltas net to zero across symbols), so
    # the oracle's own price_pl total and final-value-implied total return
    # must already agree with each other -- a sanity check on the oracle
    # itself before trusting it as ground truth.
    assert oracle_total_price_pl == pytest.approx(oracle_total_return, abs=1e-9)

    result = daily_contribution(
        prior_portfolio=_PRIOR,
        current_portfolio=_CURRENT,
        trade_log=_TRADE_LOG,
        daily_prices=_CLOSES,
        period_start=_PERIOD_START,
        period_end=_PERIOD_END,
        dividend_schedule=_DIVS,
    )

    for sym in ("AAA.O", "BBB.O", "CCC.O"):
        assert result["contributions"][sym] == pytest.approx(
            oracle_per_holding[sym] / 10000.0, abs=1e-9
        ), f"{sym} diverges from the server-walk oracle"

    assert result["portfolio_total_return"] == pytest.approx(
        oracle_total_return, abs=1e-9
    )
    assert abs(result["reconciliation_diff"]) < 1e-9
    # No dividend shift/unapplied in this fixture -- the ex-date is a real
    # close for CCC.
    assert result["dividends_shifted"] == {}
    assert result["dividends_unapplied"] == {}


def test_server_oracle_without_the_saturday_rebalance_also_matches():
    """Narrower control: the same book but with the second rebalance moved
    to the preceding Friday (a real trading day) instead of Saturday.
    Confirms the oracle and contribution.py agree on the ordinary path too,
    isolating BUG-003's non-trading-day snap as the only moving part
    between this test and the one above."""
    friday_rebal_2 = "2026-02-06"
    portfolio_snapshots = [
        (_PERIOD_START, _PRIOR),
        (_REBAL_1, _AFTER_REBAL_1),
        (friday_rebal_2, _CURRENT),
    ]
    trade_log = [
        {"symbol": "AAA.O", "action": "trim", "date": _REBAL_1, "weight_delta": -0.1},
        {"symbol": "BBB.O", "action": "add", "date": _REBAL_1, "weight_delta": +0.1},
        {"symbol": "BBB.O", "action": "trim", "date": friday_rebal_2, "weight_delta": -0.15},
        {"symbol": "CCC.O", "action": "add", "date": friday_rebal_2, "weight_delta": +0.15},
    ]

    oracle_per_holding, _, oracle_total_return = _server_oracle(
        _PERIOD_START, _PERIOD_END, portfolio_snapshots, _CLOSES, _DIVS,
    )
    result = daily_contribution(
        prior_portfolio=_PRIOR,
        current_portfolio=_CURRENT,
        trade_log=trade_log,
        daily_prices=_CLOSES,
        period_start=_PERIOD_START,
        period_end=_PERIOD_END,
        dividend_schedule=_DIVS,
    )
    for sym in ("AAA.O", "BBB.O", "CCC.O"):
        assert result["contributions"][sym] == pytest.approx(
            oracle_per_holding[sym] / 10000.0, abs=1e-9
        )
    assert result["portfolio_total_return"] == pytest.approx(oracle_total_return, abs=1e-9)
