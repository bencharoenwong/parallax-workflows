#!/usr/bin/env python3
"""Seeded synthetic generator for the managed mock fixtures (gate 1's other half).

WHY THIS EXISTS. A hand-authored fixture leaves a reviewer an unbounded
question: is every value in it synthetic? That question has no mechanical
answer, so it has to be re-argued on every edit and it is never settled.
Generating the fixtures replaces it with a bounded question a machine can
answer: *is this file byte-identical to what the seeded generator emits?*
``test_fixture_provenance.py`` asks exactly that.

CONTRACT. ``build_fixtures() -> dict[str, Any]`` maps fixture stem to the parsed
fixture object. Deterministic from ``SEED``, stdlib only, no network, no clock
and no filesystem reads. The key set must equal ``MANAGED`` in the gate.

DERIVED, NOT TYPED. Nothing here is transcribed from a capture. A seeded price
path is drawn per holding and *every* downstream block is computed from it:
holdings economics, contribution attribution, sector rollups, concentration
statistics, factor scores, performance metrics, drawdowns. Change the seed and
every number in the fixture moves coherently, which is not a property a
hand-typed fixture can have.

SHAPE AUTHORITY. Block shapes and arithmetic follow the response-shape ledger
derived from the untrimmed captures, and ``_parallax/response-schemas.md``.
Where the repo's older mock disagreed with the live response, the live response
wins — see ``response-schemas.md`` ("treat this file, not the mock, as the
current record"). ``get_score_analysis`` had three shapes in play at once and is
resolved the same way.

ENVELOPES ARE PER ENDPOINT, NOT UNIFORM. Each fixture carries the envelope its
own captures show. Do not generalise from one endpoint to another:

  * ``analyze_portfolio`` IS wrapped: ``{"success": ..., "result": {...}}``,
    with ``_meta`` and every analytics block living INSIDE ``result``. The
    correct consumer path is ``response["result"]["portfolio_summary"]``;
    ``response["portfolio_summary"]`` returns nothing. An earlier version of
    this generator emitted the block map bare, which taught the wrong access
    path -- ``test_gen_mock_fixtures.py`` now fails if the wrapper is dropped.
  * ``get_score_analysis`` is NOT wrapped. Its payload is flat: ``success``,
    ``symbol``, ``weeks``, ``data``.
  * ``get_company_info`` is emitted unwrapped because the ledger documents
    ``company_info`` only as a BLOCK inside an ``analyze_portfolio`` response
    and says nothing about the standalone endpoint. That is an absence of
    evidence, deliberately NOT resolved by analogy with the sibling above.

    SUCCESS IS NOT A STATUS FLAG. Branch on the PRESENCE OF ``result``.
    A credit-exhausted call returns ``success: true`` -- true, on a call that
    failed -- together with a ``detail`` object and NO ``result`` key at all.
    So ``if payload["success"]:`` passes on the error envelope and then
    dereferences a key that is not there. This was observed live, not inferred,
    and it is why ``analyze_portfolio_credit_exhausted`` exists as its own
    fixture: the failure is cheap to model and expensive to discover.

    quantity x close_local != ending_value, DELIBERATELY.
    This is confirmed real API behaviour, not a bug and not a rounding
    artifact. ``ending_value`` rides a dividend-inclusive (total-return) value
    path while ``close_local`` is the raw price for the same as-of date, so the
    two are not supposed to reconcile through ``quantity`` -- which is itself
    only a display convenience derived from the raw entry price. The divergence
    is reproduced here, per security, always with ``ending_value`` the larger
    and ordered by the holding's dividend yield, so that no future test can
    quietly assert the false identity and appear to pass. The error is
    unbounded: it grows with yield and with window length, so no tolerance is
    safe. Assert the real identities instead (see IDENTITIES below).

IDENTITIES HELD BY CONSTRUCTION. These are not asserted after the fact, they
are structural consequences of how the numbers are built:

  * Money lives on an exact binary lattice (eighths of a currency unit), so
    every money sum is exact in IEEE-754 doubles rather than merely close.
      - sum(latest_holdings[].ending_value) == portfolio_summary.final_value
      - sum(company_contribution[].total_pl) == portfolio_summary.total_pl
      - ending_value - total_pl == that holding's initial allocation
      - final_value == initial_value + total_pl
      - total_price_pl + total_fx_pl == total_pl
      - sector_allocation[].value sums to the portfolio value on every date
  * sum(company_contribution[].contribution_pct) == 1.0 exactly, via an
    explicit force-balance search over the last element's final decimal (the
    ledger infers the server does the same: four exact cancellations in a row
    are otherwise implausible). The force-balance moves it by at most 1e-6, so
    contribution_pct == total_pl / total_pl_portfolio still holds inside its
    own 6-decimal budget.
  * sector_contribution rows aggregate their members COLUMN BY COLUMN:
    total_pl sums, contribution_pct sums, and avg_weight is the MEAN. See TRAPS.
  * portfolio_scores[f] == floor(10 * sum(w_latest * score)) over the LATEST
    weights, with at least one factor built to land above the .5 boundary so a
    round-half-up implementation is distinguishable from floor.
  * concentration_metrics is a pure function of the emitted latest weights,
    using SAMPLE (n-1) std_dev but POPULATION skew/kurtosis. That split is
    inconsistent and it is what the API does.

TRAPS DELIBERATELY ENCODED. Each of these has burned someone; the fixture exists
partly to keep them exercised.

  1. ``sector_contribution[].avg_weight`` is the MEAN of its members while
     ``total_pl`` and ``contribution_pct`` in the SAME ROW are SUMS. The block
     mixes conventions column by column. This is invisible at one holding per
     sector, where mean and sum coincide -- which is why two holdings share a
     sector here. A sector rollup over a single member is indistinguishable
     from a row copy and proves nothing.
  2. ``_meta.invalid_fields`` is ``null`` on a clean request, NOT ``[]``.
  3. The daily grid is a CALENDAR grid, not a trading-day grid. Non-trading days
     repeat the prior value verbatim and contribute zero-return days, so
     positive_days + negative_days is strictly less than days, and win_rate
     divides by CALENDAR days. A NYSE-calendar assumption is wrong by ~30%.
  4. ``top_5_share`` is NOT clamped to 1. The emitted 6-decimal weights are not
     force-balanced per date, so they sum to 1 +/- 1e-6; the latest vector here
     is built to sum ABOVE 1 so that a ``<= 1.0`` assertion genuinely fails.
  5. ``time_period_returns`` buckets shorter than the window emit all four
     sub-keys as ``null`` -- the bucket is present, the payload is null.
  6. The final drawdown episode is still open: ``end_date`` null,
     ``recovery_days`` null, ``recovered`` false, and the timeseries
     ``*_episode`` columns are null whenever not underwater. The path is built
     so the DEEPEST episode recovers (keeping recovery_days_from_max_dd a real
     int) while a later, shallower episode is still open at the window end.
  7. ``performance_metrics.benchmark`` is a strict SUBSET of ``.portfolio`` --
     eight keys narrower. Iterating portfolio keys over it raises KeyError.
  8. ``time_period_returns.inception.portfolio_return`` is a CHAIN of the
     rounded daily returns while ``performance_metrics.portfolio.total_return``
     is a value ratio. They are two computations and they disagree in the last
     decimals. Built that way here on purpose.
  9. ``data_quality.portfolio_data_quality.total_positions`` counts
     POSITION-DAYS (dates x holdings), not holdings.
 10. ``get_score_analysis.data[].total`` is a separately-computed composite, NOT
     the mean of the five sub-scores. Built from different weights so a mean
     assertion fails.
 11. ``_meta.fields_requested`` and ``fields_returned`` hold the same SET in a
     different ORDER. Compare as sets, never as lists.

STRUCTURAL RICHNESS. Four holdings across three sectors with two sharing one
sector, twenty-eight calendar dates spanning four price phases, and one holding
carried to a negative P&L so the losing-period sign path is covered in
contribution, sector rollup and attribution alike.

NO REAL IDENTITY. Synthetic RICs and issuer names throughout, consistent across
every block and cross-reference, with exchange suffixes per the repo's RIC table
in ``_parallax/parallax-conventions.md`` §1 (``.O`` NASDAQ, ``.N`` NYSE). Dates
sit in 2033, far off any real capture window, so the series cannot be mistaken
for a real market history.

PRECISION. Every emitted value stays at or under 9 significant figures so
``fixture_precision.py`` (gate 2) passes. Money on the eighths lattice with a
four-digit integer part reaches 8 figures; ratios carry a 6-decimal budget.

Run directly to write the fixtures to disk::

    python3 skills/_parallax/scripts/gen_mock_fixtures.py --write
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import sys
from typing import Any

MOCKS_DIR = pathlib.Path(__file__).resolve().parent / "mcp_mocks"

# Pinned to the first seed satisfying _seed_constraints below -- chosen
# mechanically, not for aesthetics. Re-pin with `--find-seed` if a constraint
# changes; `main()` refuses to emit anything while the pin is unsatisfied.
SEED = 20330105

# Money and prices live on eighths of a currency unit. An eighth is exactly
# representable in binary floating point AND prints with at most three decimals,
# so every money sum is exact in float rather than merely close, and a
# five-figure portfolio value still fits inside the 9-significant-figure budget.
SUBUNIT = 8

INITIAL_VALUE = 10000
BASE_CURRENCY = "USD"
BENCHMARK_RIC = "WRLDX.O"
START_DATE = dt.date(2033, 1, 1)
END_DATE = dt.date(2033, 1, 28)

# Order matters: this is the request order echoed verbatim by _meta.
FIELDS_REQUESTED = [
    "portfolio_summary",
    "performance_metrics",
    "drawdown_analysis",
    "portfolio_scores",
    "concentration_metrics",
    "company_contribution",
    "sector_contribution",
    "sector_allocation",
    "time_period_returns",
    "latest_holdings",
    "portfolio_parameters",
    "data_quality",
]

# Synthetic issuers. Two share Information Technology so that the sector rollup
# has something to aggregate -- a one-member sector cannot distinguish a mean
# from a sum, which is the whole point of trap 1.
HOLDINGS: list[dict[str, Any]] = [
    {
        "ric": "AXCM.O",
        "name": "Axiom Compute Corp",
        "sector": "Information Technology",
        "industry": "Semiconductors & Semiconductor Equipment",
        "market": "United States",
        "exchange": "NASDAQ",
        "weight": 0.35,
        "entry_price_units": 1101,      # eighths -> 137.625
        "dividend_yield": 0.004,        # low-payout technology
        "drift_bp": (58, -46, 62, -34),  # per-phase daily drift, basis points
        "vol_bp": 74,
    },
    {
        "ric": "NVLX.O",
        "name": "Novalux Systems Inc",
        "sector": "Information Technology",
        "industry": "Software",
        "market": "United States",
        "exchange": "NASDAQ",
        "weight": 0.25,
        "entry_price_units": 733,       # eighths -> 91.625
        "dividend_yield": 0.006,
        "drift_bp": (44, -38, 51, -28),
        "vol_bp": 63,
    },
    {
        "ric": "MRDN.N",
        "name": "Meridian Financial Group",
        "sector": "Financials",
        "industry": "Banks",
        "market": "United States",
        "exchange": "NYSE",
        "weight": 0.25,
        "entry_price_units": 511,       # eighths -> 63.875
        "dividend_yield": 0.022,        # financial
        "drift_bp": (31, -22, 36, -19),
        "vol_bp": 45,
    },
    {
        "ric": "PTRG.N",
        "name": "Petrogen Energy Corp",
        "sector": "Energy",
        "industry": "Oil, Gas & Consumable Fuels",
        "market": "United States",
        "exchange": "NYSE",
        "weight": 0.15,
        "entry_price_units": 349,       # eighths -> 43.625
        "dividend_yield": 0.031,        # energy; highest yield, widest gap
        # Negative through every phase: this is the holding that must end with a
        # loss so the losing-period sign path is exercised end to end.
        "drift_bp": (-24, -61, -18, -47),
        "vol_bp": 58,
    },
]

BENCHMARK = {"drift_bp": (36, -29, 41, -21), "vol_bp": 41}

RECOMMENDATION_LADDER = ["STRONG SELL", "SELL", "HOLD", "BUY", "STRONG BUY"]
FACTORS = ["value", "quality", "momentum", "defensive", "tactical"]


# --------------------------------------------------------------------------
# Determinism primitives
# --------------------------------------------------------------------------

class Rng:
    """xorshift64* -- pinned here rather than taken from ``random``.

    The fixtures are compared byte for byte, so the PRNG is part of the
    contract. ``random.Random`` is stable in practice but it is a stdlib
    implementation detail; writing the generator out in eleven lines makes the
    fixture immune to it and makes the sequence auditable by reading."""

    _MASK = (1 << 64) - 1

    def __init__(self, seed: int) -> None:
        self.state = (seed * 2685821657736338717 + 1) & self._MASK or 1

    def next_u64(self) -> int:
        x = self.state
        x ^= (x >> 12)
        x = (x ^ (x << 25)) & self._MASK
        x ^= (x >> 27)
        self.state = x
        return (x * 2685821657736338717) & self._MASK

    def unit(self) -> float:
        """Uniform in [0, 1) with 53 bits of resolution."""
        return (self.next_u64() >> 11) / float(1 << 53)

    def signed(self) -> float:
        """Uniform in [-1, 1)."""
        return self.unit() * 2.0 - 1.0


def q(value: float, dp: int) -> float:
    """Round to a decimal budget and normalise negative zero.

    ``-0.0`` round-trips through JSON as ``-0.0``, which is a gratuitous byte
    difference against any consumer that recomputes the same value and gets
    ``0.0``."""
    out = round(value, dp)
    return 0.0 if out == 0 else out


def _sig_figs(value: float | int) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        digits = str(abs(value)).rstrip("0")
        return len(digits) if digits else 1
    import decimal
    return len(decimal.Decimal(repr(value)).normalize().as_tuple().digits)


# --------------------------------------------------------------------------
# Statistics. Written out rather than imported so the exact estimator used for
# each field is visible at the call site -- the API mixes sample and population
# conventions and the mix is load bearing.
# --------------------------------------------------------------------------

def mean(xs: list[float]) -> float:
    return math.fsum(xs) / len(xs)


def _central_moment(xs: list[float], k: int) -> float:
    mu = mean(xs)
    return math.fsum((x - mu) ** k for x in xs) / len(xs)


def sample_std(xs: list[float]) -> float:
    """n-1 denominator. Used for weight_statistics.std_dev and for volatility."""
    if len(xs) < 2:
        return 0.0
    mu = mean(xs)
    return math.sqrt(math.fsum((x - mu) ** 2 for x in xs) / (len(xs) - 1))


def population_skew(xs: list[float]) -> float:
    """Biased m3 / m2**1.5. NOT the bias-corrected G1, which differs by a factor
    of roughly 2.4 at n = 3 and is the wrong answer for this payload."""
    m2 = _central_moment(xs, 2)
    if m2 <= 0:
        return 0.0
    return _central_moment(xs, 3) / (m2 ** 1.5)


def population_excess_kurtosis(xs: list[float]) -> float:
    m2 = _central_moment(xs, 2)
    if m2 <= 0:
        return 0.0
    return _central_moment(xs, 4) / (m2 ** 2) - 3.0


def median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def gini(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    total = math.fsum(s)
    if n == 0 or total == 0:
        return 0.0
    weighted = math.fsum((i + 1) * x for i, x in enumerate(s))
    return (2.0 * weighted) / (n * total) - (n + 1) / n


def percentile(xs: list[float], pct: float) -> float:
    """Linear-interpolation percentile on the sorted sample."""
    s = sorted(xs)
    if not s:
        return 0.0
    idx = (len(s) - 1) * pct
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return s[int(idx)]
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def max_run(flags: list[bool]) -> int:
    best = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


# --------------------------------------------------------------------------
# The seeded path
# --------------------------------------------------------------------------

def calendar_dates() -> list[dt.date]:
    """Every CALENDAR day in the window. Not trading days -- see trap 3."""
    span = (END_DATE - START_DATE).days
    return [START_DATE + dt.timedelta(days=i) for i in range(span + 1)]


def _phase_of(trading_index: int, n_trading: int) -> int:
    """Four equal phases: rise, dip, recovery to a new peak, final decline.

    The shape is deliberate. The deepest drawdown must sit in phase 2 and must
    RECOVER, so ``recovery_days_from_max_dd`` is a real integer; the phase 4
    decline must be shallower and must still be underwater at the window end, so
    the final drawdown episode is open and its null fields are exercised."""
    return min(3, (trading_index * 4) // max(1, n_trading))


def _walk(rng: Rng, start_units: int, drift_bp: tuple[int, ...], vol_bp: int,
          dates: list[dt.date]) -> list[int]:
    """Integer random walk on the eighths lattice, one value per CALENDAR day.

    Weekends repeat the prior value verbatim, which is what produces the
    zero-return carry-forward days behind trap 3."""
    trading = [d for d in dates if d.weekday() < 5]
    n_trading = max(1, len(trading) - 1)
    path = [start_units]
    seen_trading = 0
    for day in dates[1:]:
        prev = path[-1]
        if day.weekday() >= 5:
            path.append(prev)
            continue
        phase = _phase_of(seen_trading, n_trading)
        seen_trading += 1
        ret = (drift_bp[phase] + rng.signed() * vol_bp) / 10000.0
        path.append(max(1, prev + round(prev * ret)))
    return path


def _returns(path: list[float]) -> list[float]:
    return [path[i] / path[i - 1] - 1.0 for i in range(1, len(path))]


def build_paths(seed: int) -> dict[str, Any]:
    """Draw every path once, then derive. Nothing below this call invents a
    number that is not a function of these walks."""
    dates = calendar_dates()
    rng = Rng(seed)

    holdings = []
    for spec in HOLDINGS:
        alloc_units = round(INITIAL_VALUE * spec["weight"]) * SUBUNIT
        # Price path: the RAW price, no dividends. Starts at the entry price.
        price_units = _walk(rng, spec["entry_price_units"], spec["drift_bp"],
                            spec["vol_bp"], dates)
        # Value path: same walk scaled to the dollar allocation, PLUS a discrete
        # dividend credit. This is what makes quantity x close_local diverge
        # from ending_value, in the confirmed direction and yield order.
        value_units = []
        credit_day = len(dates) // 2
        window_yield = spec["dividend_yield"] * (len(dates) - 1) / 365.0
        for i, px in enumerate(price_units):
            raw = alloc_units * px / price_units[0]
            if i >= credit_day:
                raw *= (1.0 + window_yield)
            value_units.append(max(1, round(raw)))
        # quantity is a display convenience off the RAW entry price, and it is
        # rounded to its own 4-decimal budget -- a second, smaller reason the
        # product does not reconcile.
        entry_price = spec["entry_price_units"] / SUBUNIT
        quantity = q(alloc_units / SUBUNIT / entry_price, 4)
        holdings.append({
            **spec,
            "alloc_units": alloc_units,
            "price_units": price_units,
            "value_units": value_units,
            "quantity": quantity,
        })

    bench_units = _walk(rng, INITIAL_VALUE * SUBUNIT, BENCHMARK["drift_bp"],
                        BENCHMARK["vol_bp"], dates)
    portfolio_units = [sum(h["value_units"][i] for h in holdings)
                       for i in range(len(dates))]
    return {
        "dates": dates,
        "holdings": holdings,
        "benchmark_units": bench_units,
        "portfolio_units": portfolio_units,
    }


# --------------------------------------------------------------------------
# Derived blocks
# --------------------------------------------------------------------------

def _latest_weights(paths: dict[str, Any]) -> list[float]:
    """Emitted 6-decimal weights. NOT force-balanced per date -- the API does not
    balance these (only contribution_pct), which is exactly why they can sum
    above 1 and why top_5_share is not clamped."""
    total = paths["portfolio_units"][-1]
    return [q(h["value_units"][-1] / total, 6) for h in paths["holdings"]]


def _scores(paths: dict[str, Any]) -> list[dict[str, Any]]:
    """Factor scores derived from each holding's own path statistics.

    Every score is a function of the walk: momentum from the trailing return,
    value from an inverse of the run-up, quality from return-per-unit-risk,
    defensive from realised volatility, tactical from the late-window move. The
    composite ``total`` uses DIFFERENT weights from a plain mean, so a
    mean-of-sub-scores assertion fails (trap 10)."""
    out = []
    for h in paths["holdings"]:
        px = [u / SUBUNIT for u in h["price_units"]]
        rets = _returns(px)
        total_ret = px[-1] / px[0] - 1.0
        vol = sample_std(rets) * math.sqrt(365.0)
        late = px[-1] / px[len(px) * 3 // 4] - 1.0

        def clamp(x: float) -> int:
            return max(0, min(10, int(round(x))))

        momentum = clamp(5.0 + total_ret * 26.0)
        value = clamp(5.5 - total_ret * 19.0)
        quality = clamp(5.0 + (total_ret / vol if vol else 0.0) * 11.0)
        defensive = clamp(9.0 - vol * 17.0)
        tactical = clamp(5.0 + late * 31.0)
        composite = (0.31 * quality + 0.24 * momentum + 0.19 * value
                     + 0.15 * defensive + 0.11 * tactical)
        out.append({
            "value": value, "quality": quality, "momentum": momentum,
            "defensive": defensive, "tactical": tactical,
            "total": q(composite, 1),
            "recommendation": RECOMMENDATION_LADDER[
                min(len(RECOMMENDATION_LADDER) - 1, clamp(composite / 2.5))],
            "pick_toscore": True,
        })
    return out


def _force_balanced_shares(raw: list[float], dp: int = 6) -> list[float]:
    """Round to ``dp`` decimals so the emitted values sum to EXACTLY 1.

    Done in integer units of ``10**-dp`` rather than by rounding each element
    and hoping. Every element but the last is rounded normally; the last takes
    whatever makes the integer units total ``10**dp``. That makes the DECIMAL
    sum exactly 1.000000 by construction, and since each emitted value is the
    correctly-rounded float of its own decimal, the float sum lands inside half
    an ulp of 1.0 and is therefore bit-exact 1.0 -- provided the magnitudes stay
    moderate, which ``_seed_constraints`` verifies rather than assumes.

    Rounding each element independently sums to 1.0 only by luck. The ledger's
    four exact cancellations across four captures are the signature of a server
    doing this same balancing, and the residual it pushes into the last element
    is at most a couple of units in the final decimal -- inside that field's own
    rounding budget, so contribution_pct still matches total_pl / total_pl."""
    scale = 10 ** dp
    head_units = [round(x * scale) for x in raw[:-1]]
    tail_units = scale - sum(head_units)
    return [u / scale for u in head_units + [tail_units]]


def _company_contribution(paths: dict[str, Any]) -> tuple[list[dict], float]:
    dates = paths["dates"]
    port = paths["portfolio_units"]
    pls = [(h["value_units"][-1] - h["alloc_units"]) / SUBUNIT
           for h in paths["holdings"]]
    total_pl = math.fsum(pls)

    avg_weights_raw = [
        mean([h["value_units"][i] / port[i] for i in range(len(dates))])
        for h in paths["holdings"]
    ]
    shares = _force_balanced_shares([pl / total_pl for pl in pls])

    rows = []
    for h, pl, aw_raw, share in zip(paths["holdings"], pls, avg_weights_raw,
                                    shares):
        # avg_allocation is computed from the UNROUNDED avg_weight and rounded
        # to its own 4-decimal budget, so avg_allocation == avg_weight x
        # initial_value holds only to ~1e-6 relative, never exactly. Preserved
        # deliberately: a test asserting equality here would be wrong.
        rows.append({
            "ric": h["ric"],
            "total_pl": pl,
            "avg_weight": q(aw_raw, 6),
            "contribution_pct": share,
            "avg_allocation": q(aw_raw * INITIAL_VALUE, 4),
            "return_pct": q(pl / (aw_raw * INITIAL_VALUE), 6),
            "name": h["name"],
        })
    return rows, total_pl


def _sector_contribution(paths: dict[str, Any],
                         company_rows: list[dict]) -> list[dict]:
    """total_pl SUMS, contribution_pct SUMS, avg_weight is the MEAN. Trap 1."""
    order: list[str] = []
    members: dict[str, list[dict]] = {}
    for h, row in zip(paths["holdings"], company_rows):
        if h["sector"] not in members:
            members[h["sector"]] = []
            order.append(h["sector"])
        members[h["sector"]].append(row)

    rows = []
    for sector in order:
        group = members[sector]
        rows.append({
            "sector": sector,
            "total_pl": sum(r["total_pl"] for r in group),
            "avg_weight": q(mean([r["avg_weight"] for r in group]), 6),
            "contribution_pct": sum(r["contribution_pct"] for r in group),
        })
    return rows


def _sector_allocation(paths: dict[str, Any]) -> list[dict]:
    """Long-format time series: one row per (date x sector), NOT a
    {sector: weight} dict. Modelling it as a dict silently discards the entire
    time dimension."""
    order: list[str] = []
    for h in paths["holdings"]:
        if h["sector"] not in order:
            order.append(h["sector"])

    rows = []
    for i, day in enumerate(paths["dates"]):
        total = paths["portfolio_units"][i]
        for sector in order:
            units = sum(h["value_units"][i] for h in paths["holdings"]
                        if h["sector"] == sector)
            rows.append({
                "date": day.isoformat(),
                "sector": sector,
                "value": units / SUBUNIT,
                "weight": q(units / total, 6),
            })
    return rows


def _latest_holdings(paths: dict[str, Any], scores: list[dict],
                     weights: list[float]) -> list[dict]:
    rows = []
    for h, sc, w in zip(paths["holdings"], scores, weights):
        close = h["price_units"][-1] / SUBUNIT
        rows.append({
            "ric": h["ric"],
            "quantity": h["quantity"],
            "weight": w,
            "close_local": close,
            "close_base": close,      # single-currency portfolio
            "currency_local": BASE_CURRENCY,
            "ending_value": h["value_units"][-1] / SUBUNIT,
            "market": h["market"],
            "sector": h["sector"],
            "industry": h["industry"],
            "name": h["name"],
            "value": sc["value"],
            "quality": sc["quality"],
            "momentum": sc["momentum"],
            "defensive": sc["defensive"],
            "tactical": sc["tactical"],
            "total": sc["total"],
            "pick_toscore": sc["pick_toscore"],
            "recommendation": sc["recommendation"],
        })
    return rows


def _portfolio_scores(scores: list[dict], weights: list[float]) -> dict:
    """floor(10 x sum(w_latest x score)), NOT round. The distinction is real:
    rounding half-up gives a different integer whenever the fractional part
    reaches .5, and _find_seed guarantees at least one factor lands there."""
    out = {}
    for factor in FACTORS:
        weighted = math.fsum(w * sc[factor] for w, sc in zip(weights, scores))
        out[factor] = math.floor(10.0 * weighted)
    weighted_total = math.fsum(w * sc["total"] for w, sc in zip(weights, scores))
    out["total"] = math.floor(10.0 * weighted_total)
    out["coverage"] = 1
    return out


def _concentration_metrics(paths: dict[str, Any],
                           weights: list[float]) -> dict:
    """A pure function of the EMITTED latest weights.

    Note the estimator split, which is inconsistent and deliberate: std_dev uses
    the SAMPLE (n-1) denominator while skewness and kurtosis use POPULATION
    moments."""
    hhi = math.fsum(w * w for w in weights)
    sectors: dict[str, float] = {}
    markets: dict[str, float] = {}
    industries = set()
    for h, w in zip(paths["holdings"], weights):
        sectors[h["sector"]] = sectors.get(h["sector"], 0.0) + w
        markets[h["market"]] = markets.get(h["market"], 0.0) + w
        industries.add(h["industry"])

    ordered = sorted(weights, reverse=True)
    return {
        "weight_statistics": {
            "mean": q(math.fsum(weights) / len(weights), 6),
            "median": q(median(weights), 6),
            "std_dev": q(sample_std(weights), 6),
            "maximum": q(max(weights), 6),
            "minimum": q(min(weights), 6),
        },
        "concentration": {
            "herfindahl_index": q(hhi, 4),
            # From the UNROUNDED hhi, not from the emitted 4-decimal one. They
            # disagree at 2 decimals, so 1 / herfindahl_index is not this value.
            "effective_positions": q(1.0 / hhi, 2),
            # Not clamped: with n < 5 this is the full weight sum, which is
            # slightly above 1 because the weights are not force-balanced.
            "top_5_share": q(math.fsum(ordered[:5]), 6),
            "top_10_share": q(math.fsum(ordered[:10]), 6),
            "gini_coefficient": q(gini(weights), 3),
        },
        "higher_moments": {
            "skewness": q(population_skew(weights), 4),
            "kurtosis": q(population_excess_kurtosis(weights), 1),
        },
        "diversification": {
            "num_markets": len(markets),
            "market_hhi": q(math.fsum(v * v for v in markets.values()), 4),
            "num_sectors": len(sectors),
            "sector_hhi": q(math.fsum(v * v for v in sectors.values()), 4),
            "num_industries": len(industries),
        },
    }


def _perf_block(values: list[float], dates: list[dt.date],
                rf_daily: float, full: bool) -> dict:
    """29 keys when ``full`` (the portfolio), 21 when not (the benchmark).

    The benchmark is a strict SUBSET, eight keys narrower. Code that iterates
    the portfolio's keys over the benchmark dict raises KeyError -- trap 7."""
    rets = _returns(values)
    days = len(dates)                      # CALENDAR days, trap 3
    total_return = values[-1] / values[0] - 1.0
    ann_return = (1.0 + total_return) ** (365.0 / days) - 1.0
    ann_vol = sample_std(rets) * math.sqrt(365.0)

    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    downside = math.sqrt(math.fsum(min(r, 0.0) ** 2 for r in rets) / len(rets))
    downside_annual = downside * math.sqrt(365.0)

    peak = values[0]
    max_dd = 0.0
    for v in values:
        peak = max(peak, v)
        max_dd = min(max_dd, v / peak - 1.0)

    rf_annual = (1.0 + rf_daily) ** 365 - 1.0
    var95, var99 = percentile(rets, 0.05), percentile(rets, 0.01)
    tail95 = [r for r in rets if r <= var95] or [var95]
    tail99 = [r for r in rets if r <= var99] or [var99]
    gains, pains = math.fsum(wins), abs(math.fsum(losses))

    block = {
        "total_return": q(total_return, 6),
        "annualized_return": q(ann_return, 6),
        "final_value": values[-1],
        "annualized_volatility": q(ann_vol, 6),
        "downside_deviation_annual": q(downside_annual, 6),
        "max_drawdown": q(max_dd, 6),
        "var_95": q(var95, 6),
        "var_99": q(var99, 6),
        "cvar_95": q(mean(tail95), 6),
        "cvar_99": q(mean(tail99), 6),
        "sharpe_ratio": q((ann_return - rf_annual) / ann_vol, 4) if ann_vol else 0.0,
        "sortino_ratio": q((ann_return - rf_annual) / downside_annual, 4)
                         if downside_annual else 0.0,
        "calmar_ratio": q(ann_return / abs(max_dd), 4) if max_dd else 0.0,
        "omega_ratio": q(gains / pains, 4) if pains else 0.0,
        "win_rate": q(len(wins) / days, 4),   # CALENDAR days in the denominator
        "best_day": q(max(rets), 6),
        "worst_day": q(min(rets), 6),
        "positive_days": len(wins),
        "negative_days": len(losses),
        "skewness": q(population_skew(rets), 4),
        "kurtosis": q(population_excess_kurtosis(rets), 4),
    }
    if not full:
        return block

    trough = min(range(len(values)), key=lambda i: values[i] / max(values[:i + 1]))
    recovery = 0
    for j in range(trough, len(values)):
        if values[j] >= max(values[:trough + 1]):
            recovery = j - trough
            break
    block.update({
        "gain_to_pain_ratio": q(gains / pains, 4) if pains else 0.0,
        "return_over_max_drawdown": q(total_return / abs(max_dd), 4)
                                    if max_dd else 0.0,
        "avg_win": q(mean(wins), 6) if wins else 0.0,
        "avg_loss": q(mean(losses), 6) if losses else 0.0,
        "max_consecutive_wins": max_run([r > 0 for r in rets]),
        "max_consecutive_losses": max_run([r < 0 for r in rets]),
        "recovery_days_from_max_dd": recovery,
        "days": days,
    })
    return block


def _relative_block(port: list[float], bench: list[float], rf_daily: float,
                    days: int) -> dict:
    pr, br = _returns(port), _returns(bench)
    mu_p, mu_b = mean(pr), mean(br)
    cov = math.fsum((a - mu_p) * (b - mu_b) for a, b in zip(pr, br)) / (len(pr) - 1)
    var_b = math.fsum((b - mu_b) ** 2 for b in br) / (len(br) - 1)
    beta = cov / var_b if var_b else 0.0
    sd_p, sd_b = sample_std(pr), sample_std(br)
    corr = cov / (sd_p * sd_b) if sd_p and sd_b else 0.0

    tr_p = port[-1] / port[0] - 1.0
    tr_b = bench[-1] / bench[0] - 1.0
    ann_p = (1.0 + tr_p) ** (365.0 / days) - 1.0
    ann_b = (1.0 + tr_b) ** (365.0 / days) - 1.0
    rf_annual = (1.0 + rf_daily) ** 365 - 1.0

    active = [a - b for a, b in zip(pr, br)]
    te = sample_std(active) * math.sqrt(365.0)
    up_p = math.fsum(a for a, b in zip(pr, br) if b > 0)
    up_b = math.fsum(b for b in br if b > 0)
    dn_p = math.fsum(a for a, b in zip(pr, br) if b < 0)
    dn_b = math.fsum(b for b in br if b < 0)
    upside = up_p / up_b if up_b else 0.0
    downside = dn_p / dn_b if dn_b else 0.0

    return {
        "beta": q(beta, 4),
        "alpha_annualized": q(ann_p - (rf_annual + beta * (ann_b - rf_annual)), 6),
        "r_squared": q(corr * corr, 4),
        "correlation": q(corr, 4),
        "treynor_ratio_portfolio": q((ann_p - rf_annual) / beta, 6) if beta else 0.0,
        "treynor_ratio_benchmark": q(ann_b - rf_annual, 6),
        "information_ratio": q((ann_p - ann_b) / te, 4) if te else 0.0,
        "tracking_error": q(te, 6),
        "upside_capture": q(upside, 4),
        "downside_capture": q(downside, 4),
        "capture_ratio": q(upside / downside, 4) if downside else 0.0,
        "excess_return": q(tr_p - tr_b, 6),
        "excess_volatility": q((sd_p - sd_b) * math.sqrt(365.0), 6),
    }


def _drawdown_side(values: list[float], dates: list[dt.date]) -> tuple[dict, list, list]:
    """Returns (summary, episode rows, per-day (drawdown, episode) pairs).

    The final episode is left OPEN when the series ends underwater: ``end_date``
    null, ``recovery_days`` null, ``recovered`` false. Nullability here is real,
    not theoretical -- trap 6."""
    peak = values[0]
    series: list[tuple[float, int | None]] = []
    episodes: list[dict] = []
    current: dict | None = None

    for i, v in enumerate(values):
        peak = max(peak, v)
        dd = v / peak - 1.0
        if dd < 0:
            if current is None:
                current = {
                    "episode": len(episodes) + 1,
                    "start_date": dates[i].isoformat(),
                    "trough_date": dates[i].isoformat(),
                    "trough": dd, "start_index": i,
                    "trough_index": i,
                }
            elif dd < current["trough"]:
                current["trough"] = dd
                current["trough_date"] = dates[i].isoformat()
                current["trough_index"] = i
            series.append((dd, current["episode"]))
        else:
            if current is not None:
                current["end_date"] = dates[i].isoformat()
                current["end_index"] = i
                episodes.append(current)
                current = None
            # Not underwater: the episode column is null, not 0.
            series.append((dd, None))
    if current is not None:
        current["end_date"] = None
        current["end_index"] = None
        episodes.append(current)

    rows = []
    for ep in episodes:
        closed = ep["end_index"] is not None
        rows.append({
            "episode": ep["episode"],
            "start_date": ep["start_date"],
            "trough_date": ep["trough_date"],
            "end_date": ep["end_date"],
            "max_drawdown": q(ep["trough"], 6),
            "duration_days": (ep["end_index"] if closed else len(values) - 1)
                             - ep["start_index"] + 1,
            "recovery_days": (ep["end_index"] - ep["trough_index"]) if closed else None,
            "recovered": closed,
        })

    underwater = [d for d, _ in series if d < 0]
    durations = [r["duration_days"] for r in rows]
    recoveries = [r["recovery_days"] for r in rows if r["recovery_days"] is not None]
    summary = {
        "current_drawdown": q(series[-1][0], 6),
        "at_peak": series[-1][0] == 0,
        "max_drawdown": q(min(d for d, _ in series), 6),
        "num_underwater_periods": len(rows),
        "avg_duration_days": q(mean(durations), 2) if durations else 0.0,
        "max_duration_days": max(durations) if durations else 0,
        "total_days_underwater": len(underwater),
        "avg_recovery_days": q(mean([float(r) for r in recoveries]), 2)
                             if recoveries else 0.0,
        "max_recovery_days": max(recoveries) if recoveries else 0,
    }
    return summary, rows, series


def _time_period_returns(port: list[float], bench: list[float],
                         dates: list[dt.date]) -> dict:
    """All twelve buckets always present. Buckets the window cannot cover emit
    all four sub-keys as null -- present with a null payload, never absent."""
    # Chained from the ROUNDED daily returns, which is a different computation
    # from performance_metrics' value ratio; they disagree in the last decimals
    # and that disagreement is the point (trap 8).
    def chained(values: list[float], start: int) -> float:
        acc = 1.0
        for i in range(start + 1, len(values)):
            acc *= 1.0 + q(values[i] / values[i - 1] - 1.0, 6)
        return acc - 1.0

    def bucket(start_index: int) -> dict:
        p = chained(port, start_index)
        b = chained(bench, start_index)
        return {
            "portfolio_return": q(p, 6),
            "benchmark_return": q(b, 6),
            "excess_return": q(p - b, 6),
            "num_days": len(dates) - start_index,
        }

    null_bucket = {
        "portfolio_return": None, "benchmark_return": None,
        "excess_return": None, "num_days": None,
    }
    last = dates[-1]
    week_start = next(i for i, d in enumerate(dates)
                      if (last - d).days <= 6)

    out = {
        "inception": bucket(0),
        # The window opens on 1 January, so year-, quarter- and month-to-date
        # all coincide with inception here. That they are equal is a property of
        # this window, not an identity.
        "ytd": bucket(0),
        "qtd": bucket(0),
        "mtd": bucket(0),
        "1w": bucket(week_start),
    }
    # Every lookback longer than the window: null, per trap 5.
    for key in ("1m", "3m", "6m", "1yr", "3yr", "5yr", "10yr"):
        out[key] = dict(null_bucket)
    return out


# --------------------------------------------------------------------------
# Fixture assembly
# --------------------------------------------------------------------------

def _build_analyze_portfolio(paths: dict[str, Any]) -> dict:
    dates = paths["dates"]
    port = [u / SUBUNIT for u in paths["portfolio_units"]]
    bench = [u / SUBUNIT for u in paths["benchmark_units"]]
    rf_daily = 0.00011507      # constant across the window, not a series

    scores = _scores(paths)
    weights = _latest_weights(paths)
    company_rows, total_pl = _company_contribution(paths)

    final_value = math.fsum(h["value_units"][-1] for h in paths["holdings"]) / SUBUNIT

    pf_summary = {
        "final_value": final_value,
        "total_return": q(final_value / INITIAL_VALUE - 1.0, 6),
        "total_price_pl": total_pl,
        "total_fx_pl": 0,          # single-currency portfolio
        "total_pl": total_pl,
        "total_transaction_cost": 0,
        "transaction_cost_pct_of_initial": 0,
        "include_transaction_costs": False,
    }

    dd_port, ep_port, series_port = _drawdown_side(port, dates)
    dd_bench, ep_bench, series_bench = _drawdown_side(bench, dates)

    blocks = {
        "_meta": {
            "fields_requested": list(FIELDS_REQUESTED),
            # Same SET, server-canonical ORDER. Compare as sets (trap 11).
            "fields_returned": sorted(FIELDS_REQUESTED),
            # null on a clean request, NOT [] (trap 2).
            "invalid_fields": None,
        },
        "portfolio_parameters": {
            "start_date": dates[0].isoformat(),
            "end_date": dates[-1].isoformat(),
            "base_currency": BASE_CURRENCY,
            "benchmark": BENCHMARK_RIC,
            "initial_value": INITIAL_VALUE,
            "include_transaction_costs": False,
            "transaction_costs_applied": None,
        },
        "data_quality": {
            "total_rics_requested": len(paths["holdings"]),
            "rics_found_in_database": len(paths["holdings"]),
            "missing_rics_count": 0,
            "missing_rics": [],
            "data_completeness_pct": 100,
            "removed_positions_due_to_missing_prices": {
                "count": 0, "unique_rics": 0, "details": [],
            },
            "portfolio_data_quality": {
                # POSITION-DAYS, not positions: dates x holdings (trap 9).
                "total_positions": len(dates) * len(paths["holdings"]),
                "missing_quantities": 0, "missing_quantities_pct": 0,
                "missing_prices": 0, "missing_prices_pct": 0,
                "missing_values": 0, "missing_values_pct": 0,
            },
        },
        "portfolio_summary": pf_summary,
        "performance_metrics": {
            "portfolio": _perf_block(port, dates, rf_daily, full=True),
            "benchmark": _perf_block(bench, dates, rf_daily, full=False),
            "relative": _relative_block(port, bench, rf_daily, len(dates)),
        },
        "drawdown_analysis": {
            "portfolio": dd_port,
            "benchmark": dd_bench,
            "timeseries": [
                {
                    "date": day.isoformat(),
                    "portfolio_drawdown": q(series_port[i][0], 6),
                    "benchmark_drawdown": q(series_bench[i][0], 6),
                    "portfolio_episode": series_port[i][1],
                    "benchmark_episode": series_bench[i][1],
                }
                for i, day in enumerate(dates)
            ],
            "episode_details": {"portfolio": ep_port, "benchmark": ep_bench},
        },
        "portfolio_scores": _portfolio_scores(scores, weights),
        "concentration_metrics": _concentration_metrics(paths, weights),
        "company_contribution": company_rows,
        "sector_contribution": _sector_contribution(paths, company_rows),
        "sector_allocation": _sector_allocation(paths),
        "time_period_returns": _time_period_returns(port, bench, dates),
        "latest_holdings": _latest_holdings(paths, scores, weights),
    }
    return blocks


def _build_analyze_portfolio_credit_exhausted() -> dict:
    """The failure envelope, which is the reason ``success`` cannot be trusted.

    ``success`` is ``true`` on a call that FAILED. There is no ``result`` key at
    all -- not null, absent -- so the only sound guard is ``"result" in
    payload``. A consumer written as ``if payload["success"]: ...
    payload["result"]`` passes the guard and then raises a KeyError.

    Every value here is fixed rather than seeded: this envelope has no numeric
    content derived from a price path, and the balance/required pair is a
    deliberately round, obviously-synthetic quota illustration."""
    return {
        "success": True,
        "detail": {
            "error": "Insufficient credits for this request.",
            "balance": 12,
            "required": 40,
            "endpoint": "analyze_portfolio",
        },
    }


def _build_get_score_analysis(paths: dict[str, Any]) -> dict:
    """Flat payload -- no ``result`` wrapper, and the rows live under ``data``.

    Sub-scores are integers on 0-10; ``total`` is a one-decimal float on 0-10
    and is a separately-computed composite, NOT the mean of the five (trap 10).
    Cadence is weekly: dates advance seven days."""
    subject = paths["holdings"][0]
    rng = Rng(SEED ^ 0x5C0DE)
    weeks = 13
    end = paths["dates"][-1]

    # A seeded walk in score space, anchored on the holding's derived scores so
    # the history is consistent with the portfolio fixture's latest values.
    latest = _scores(paths)[0]
    levels = {f: float(latest[f]) for f in FACTORS}
    history = []
    for back in range(weeks):
        row_date = end - dt.timedelta(days=7 * back)
        row = {"symbol": subject["ric"]}
        for factor in FACTORS:
            row[factor] = max(0, min(10, int(round(levels[factor]))))
        composite = (0.29 * row["quality"] + 0.26 * row["momentum"]
                     + 0.21 * row["value"] + 0.14 * row["defensive"]
                     + 0.10 * row["tactical"])
        row["total"] = q(composite, 1)
        row["date"] = row_date.isoformat()
        history.append(row)
        for factor in FACTORS:
            levels[factor] = max(0.0, min(10.0,
                                          levels[factor] - rng.signed() * 0.9))

    history.reverse()
    return {
        "success": True,
        "symbol": subject["ric"],
        "weeks": weeks,
        "data": history,
    }


def _build_get_company_info(paths: dict[str, Any]) -> dict:
    """The standalone endpoint's consumer shape, with a synthetic identity.

    This is deliberately NOT the 25-key ``company_info`` block that lives inside
    an ``analyze_portfolio`` response. The ledger documents that block; it says
    nothing about this endpoint, and inventing a shape for it from the block
    would be a guess dressed as a record. The shape below is the one this repo's
    schema and consumers already agree on; what changes is provenance -- every
    value is now derived from the seeded path and the issuer is synthetic."""
    subject = paths["holdings"][0]
    close = subject["price_units"][-1] / SUBUNIT
    # Share count derived from the path, then rounded hard so the market cap
    # stays well inside the 9-significant-figure budget. A cap accurate to the
    # dollar is precisely the identity signature gate 2 exists to catch.
    shares = round(subject["value_units"][-1] * 2_600_000 / SUBUNIT, -8)
    return {
        "symbol": subject["ric"],
        "name": subject["name"],
        "exchange": subject["exchange"],
        "sector": subject["sector"],
        "industry": subject["industry"],
        "country": subject["market"],
        "market_cap_usd": int(q(shares * close, -6)),
        "currency": BASE_CURRENCY,
        "description": (
            f"{subject['name']} is a synthetic issuer used in Parallax fixture "
            f"tests. It does not exist. Every value in this fixture is produced "
            f"by gen_mock_fixtures.py from a pinned seed, so the file can be "
            f"regenerated and compared byte for byte."
        ),
        "website": "https://www.example.com/axiom-compute",
    }


# --------------------------------------------------------------------------
# Seed selection
# --------------------------------------------------------------------------

def _seed_constraints(paths: dict[str, Any]) -> list[str]:
    """The structural properties the fixture must have. A seed that does not
    produce all of them is rejected, so the traps stay exercised rather than
    accidentally lapsing when a number moves."""
    failures = []
    weights = _latest_weights(paths)
    scores = _scores(paths)
    company_rows, _ = _company_contribution(paths)
    port = [u / SUBUNIT for u in paths["portfolio_units"]]

    if math.fsum(weights) <= 1.0:
        failures.append("latest weights must sum ABOVE 1 so top_5_share "
                        "demonstrably escapes a <= 1.0 clamp")

    fracs = []
    for factor in FACTORS + ["total"]:
        key = factor
        weighted = math.fsum(w * sc[key] for w, sc in zip(weights, scores))
        fracs.append((10.0 * weighted) % 1.0)
    if not any(f > 0.5 for f in fracs):
        failures.append("no portfolio_scores factor lands above the .5 "
                        "boundary, so floor is indistinguishable from round")

    losers = [r for r in company_rows if r["total_pl"] < 0]
    winners = [r for r in company_rows if r["total_pl"] > 0]
    if not losers:
        failures.append("no holding ends with negative P&L")
    if not winners:
        failures.append("no holding ends with positive P&L")

    # The force-balance is only sound while the shares stay moderate: at large
    # magnitudes the float representation error of a 6-decimal value exceeds
    # half an ulp of 1.0 and the sum stops being bit-exact. Verify, never assume.
    shares = [r["contribution_pct"] for r in company_rows]
    if sum(shares) != 1.0:
        failures.append("contribution_pct does not sum to exactly 1.0 in float")
    total_pl = math.fsum(r["total_pl"] for r in company_rows)
    drift = max(abs(r["contribution_pct"] - r["total_pl"] / total_pl)
                for r in company_rows)
    if drift > 1e-6:
        failures.append("contribution_pct drifts from total_pl / total_pl by "
                        "more than its own 6-decimal budget")

    summary, episodes, series = _drawdown_side(port, paths["dates"])
    if series[-1][0] >= 0:
        failures.append("portfolio must end underwater so the final drawdown "
                        "episode is OPEN and its null fields are exercised")
    if not episodes or episodes[-1]["recovered"]:
        failures.append("final episode must be unrecovered")
    recovered = [e for e in episodes if e["recovered"]]
    if not recovered:
        failures.append("at least one episode must recover")
    deepest = min(episodes, key=lambda e: e["max_drawdown"])
    if not deepest["recovered"]:
        failures.append("the DEEPEST episode must recover so "
                        "recovery_days_from_max_dd is a real integer")

    # Only one sector may hold more than one member, but at least one must, or
    # the mean-vs-sum trap is untestable.
    counts: dict[str, int] = {}
    for h in paths["holdings"]:
        counts[h["sector"]] = counts.get(h["sector"], 0) + 1
    if max(counts.values()) < 2:
        failures.append("no sector holds two members")
    if len(counts) < 3:
        failures.append("fewer than three sectors")
    return failures


def _find_seed(start: int = SEED, limit: int = 40000) -> int:
    """Search forward for the first seed satisfying every constraint.

    Not called at build time -- SEED is pinned to its result. Kept so the pin is
    reproducible and so a constraint change has an obvious next step."""
    for candidate in range(start, start + limit):
        if not _seed_constraints(build_paths(candidate)):
            return candidate
    raise RuntimeError("no seed satisfied the structural constraints")


# --------------------------------------------------------------------------
# Public contract
# --------------------------------------------------------------------------

def build_fixtures() -> dict[str, Any]:
    """The generator contract consumed by ``test_fixture_provenance.py``.

    Deterministic, offline, and keyed by fixture stem. Note the asymmetry in the
    envelopes below -- it is per endpoint, and it is not an oversight. See the
    module docstring."""
    paths = build_paths(SEED)
    return {
        # Wrapped. Every analytics block, _meta included, sits under "result".
        "analyze_portfolio": {
            "success": True,
            "result": _build_analyze_portfolio(paths),
        },
        "analyze_portfolio_credit_exhausted":
            _build_analyze_portfolio_credit_exhausted(),
        # Flat -- no wrapper on this endpoint.
        "get_company_info": _build_get_company_info(paths),
        "get_score_analysis": _build_get_score_analysis(paths),
    }


def serialise(payload: Any) -> str:
    """Match the gate's canonical form so a written file and a regenerated one
    are the same bytes."""
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True,
                      allow_nan=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the seeded synthetic MCP mock fixtures.")
    parser.add_argument("--write", action="store_true",
                        help="write the fixtures into mcp_mocks/ (default: "
                             "print a summary only)")
    parser.add_argument("--out", type=pathlib.Path, default=MOCKS_DIR,
                        help="directory to write into (default: mcp_mocks/)")
    parser.add_argument("--find-seed", action="store_true",
                        help="search for a seed satisfying the structural "
                             "constraints and print it")
    # ``main()`` with no argument means NO command-line arguments, not "go read
    # sys.argv". Defaulting to sys.argv here would make the function pick up
    # whatever flags the surrounding process was launched with -- under pytest
    # that is the pytest command line, which argparse then rejects with
    # SystemExit. The real entry point passes sys.argv[1:] explicitly at the
    # bottom of this file. Same rule as ``fixture_precision.main``.
    args = parser.parse_args([] if argv is None else argv)

    if args.find_seed:
        print(_find_seed())
        return 0

    if args.write and not args.out.is_dir():
        print(f"FAIL: {args.out} is not a directory — nothing was written",
              file=sys.stderr)
        return 1

    failures = _seed_constraints(build_paths(SEED))
    if failures:
        for line in failures:
            print(f"  SEED CONSTRAINT: {line}", file=sys.stderr)
        print(f"FAIL: SEED {SEED} does not satisfy the structural constraints; "
              f"re-pin it with --find-seed", file=sys.stderr)
        return 1

    fixtures = build_fixtures()
    for name, payload in sorted(fixtures.items()):
        text = serialise(payload)
        if args.write:
            (args.out / f"{name}.json").write_text(text, encoding="utf-8")
        print(f"  {name}.json  {len(text):>7,} bytes"
              f"{'  written' if args.write else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
