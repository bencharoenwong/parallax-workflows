"""Pure dated-price arithmetic for pair-finder; no market-data or network calls.

CLI input: {"long_prices": <export_price_series payload>, "short_prices":
<export_price_series payload>, "benchmark_prices": <etf_daily_price list>}.
Accepts observed equity `price` and legacy `close` without conflating them.
Output is arithmetic evidence, never an execution/suitability recommendation.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import math
from pathlib import Path
import re
import sys
import statistics
from typing import Any

MIN_LEG_PRICES = 90
MIN_BENCHMARK_PRICES = 60
# A conservative daily-observation support check, not a volatility calibration.
# Normal weekends/one-day adjoining holidays fit; longer closures stay unverified.
MAX_DAILY_INTERVAL_CALENDAR_DAYS = 4


def prices(payload: Any) -> dict[str, float]:
    """Validate a decoded equity data envelope or bare ETF list, keyed by date."""
    if isinstance(payload, dict):
        if payload.get("success") is False:
            raise ValueError("price endpoint reports failure")
        payload = payload.get("data")
    if not isinstance(payload, list):
        raise ValueError("prices must be a row list or an envelope with data list")
    out = {}
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("price row must be an object")
        stamp = row.get("date")
        if not isinstance(stamp, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
            raise ValueError("price date must be YYYY-MM-DD")
        date.fromisoformat(stamp)
        if stamp in out:
            raise ValueError(f"duplicate price date: {stamp}")
        raw = row.get("price") if "price" in row else row.get("close")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw) or raw <= 0:
            raise ValueError("prices must be finite and positive")
        if "price" in row and "close" in row and row["price"] != row["close"]:
            raise ValueError("conflicting price and close values")
        out[stamp] = float(raw)
    return dict(sorted(out.items()))


def returns(series: dict[str, float]) -> dict[tuple[str, str], float]:
    """Consecutive interval returns; align BOTH endpoints across instruments."""
    rows = list(series.items())
    out = {(a[0], b[0]): b[1] / a[1] - 1 for a, b in zip(rows, rows[1:])}
    if any(not math.isfinite(v) for v in out.values()):
        raise ValueError("return overflow")
    return out


def max_drawdown(wealth: list[float]) -> float:
    """Peak-relative drawdown, including initial wealth in the peak path."""
    if not wealth or any(not math.isfinite(x) or x <= 0 for x in wealth):
        raise ValueError("wealth index must be finite and positive")
    peak = wealth[0]
    worst = 0.0
    for value in wealth:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst


def _beta(leg: list[float], benchmark: list[float]) -> float:
    mean_l, mean_b = statistics.mean(leg), statistics.mean(benchmark)
    var_b = sum((b - mean_b) ** 2 for b in benchmark)
    if not math.isfinite(var_b) or var_b <= 0:
        raise ValueError("benchmark return variance is zero or non-finite")
    value = sum((l - mean_l) * (b - mean_b) for l, b in zip(leg, benchmark)) / var_b
    if not math.isfinite(value):
        raise ValueError("beta is non-finite")
    return value


def history_stats(long: dict[str, float], short: dict[str, float], ratio: float) -> dict[str, Any]:
    """Daily-reset synthetic spread index per $1 long; no fees/dividends/FX."""
    lr, sr = returns(long), returns(short)
    common = sorted(lr.keys() & sr.keys())
    if len(common) < 2:
        return {"available": False, "reason": "fewer than two common return intervals"}
    gaps = [{"after": left[1], "before": right[0]}
            for left, right in zip(common, common[1:]) if left[1] != right[0]]
    if gaps:
        return {"available": False,
                "reason": "gaps between common return intervals; cumulative spread history unavailable",
                "common_return_intervals": len(common), "gaps": gaps}
    sparse = [{"start_date": start, "end_date": end,
               "calendar_days": (date.fromisoformat(end) - date.fromisoformat(start)).days}
              for start, end in common
              if (date.fromisoformat(end) - date.fromisoformat(start)).days > MAX_DAILY_INTERVAL_CALENDAR_DAYS]
    if sparse:
        return {"available": False,
                "reason": "daily-observation support unverified: common intervals exceed four calendar days; no annualized daily statistics",
                "common_return_intervals": len(common), "sparse_intervals": sparse,
                "max_daily_interval_calendar_days": MAX_DAILY_INTERVAL_CALENDAR_DAYS}
    l = [lr[k] for k in common]
    s = [sr[k] for k in common]
    spread = [a - ratio * b for a, b in zip(l, s)]
    wealth = [1.0]
    months: dict[str, float] = {}
    for key, value in zip(common, spread):
        wealth.append(wealth[-1] * (1 + value))
        month = key[1][:7]
        months[month] = months.get(month, 1.0) * (1 + value)
    try:
        dd = max_drawdown(wealth)
    except ValueError:
        return {"available": False, "reason": "synthetic spread wealth became nonpositive or non-finite"}
    corr = statistics.correlation(l, s) if statistics.pstdev(l) > 0 and statistics.pstdev(s) > 0 else None
    return {"available": True, "common_return_intervals": len(common),
            "start_date": common[0][0], "end_date": common[-1][1],
            "correlation": corr, "annualized_spread_volatility": statistics.stdev(spread) * math.sqrt(252),
            "max_drawdown": dd, "positive_month_fraction": sum(v > 1 for v in months.values()) / len(months),
            "months_observed": len(months), "hedge_ratio": ratio,
            "max_daily_interval_calendar_days": MAX_DAILY_INTERVAL_CALENDAR_DAYS,
            "basis": "daily-reset synthetic spread index per dollar long, raw local prices; excludes dividends, borrow, fees and FX conversion; partial months included"}


def compute(payload: dict[str, Any], *, no_beta: bool = False, history: bool = False) -> dict[str, Any]:
    """Compute feasible beta-neutral evidence or a reason for dollar-neutral only.

    A missing/short benchmark fails the default benchmark gate (ValueError).
    Per-pair joint-history/variance/sign gaps preserve dollar-neutral output.
    """
    out: dict[str, Any] = {"dollar_neutral_ratio": 1.0, "beta_neutral_ratio": None,
                           "beta_long": None, "beta_short": None, "basis": "raw local-currency price returns; not total returns"}
    if no_beta and not history:
        out["beta_status"] = "not requested (--no-beta); prices and benchmark not read"
        return out
    long, short = prices(payload.get("long_prices")), prices(payload.get("short_prices"))
    ratio = 1.0
    if no_beta:
        out["beta_status"] = "not requested (--no-beta); benchmark not read"
    else:
        benchmark = prices(payload.get("benchmark_prices"))
        if len(benchmark) < MIN_BENCHMARK_PRICES:
            raise ValueError("benchmark needs at least 60 dated prices")
        lr, sr, br = returns(long), returns(short), returns(benchmark)
        common = sorted(lr.keys() & sr.keys() & br.keys())
        out["common_return_intervals"] = len(common)
        if min(len(long), len(short)) < MIN_LEG_PRICES or len(common) < MIN_LEG_PRICES - 1:
            out["beta_status"] = "insufficient common dated history; dollar-neutral only"
        else:
            out["beta_start_date"], out["beta_end_date"] = common[0][0], common[-1][1]
            try:
                b = [br[k] for k in common]
                bl, bs = _beta([lr[k] for k in common], b), _beta([sr[k] for k in common], b)
                out["beta_long"], out["beta_short"] = bl, bs
                if abs(bs) < 0.1:
                    raise ValueError("short beta near zero; beta-neutral ratio unstable")
                proposed = bl / bs
                if not math.isfinite(proposed) or proposed <= 0:
                    raise ValueError("no positive long/short beta-neutral ratio for these beta signs")
                ratio = proposed
                out["beta_neutral_ratio"] = ratio
                out["beta_status"] = "feasible arithmetic ratio; execution and suitability unverified"
            except ValueError as exc:
                out["beta_status"] = str(exc) + "; dollar-neutral only"
    if history:
        out["history"] = history_stats(
            prices(payload["history_long_prices"]) if "history_long_prices" in payload else long,
            prices(payload["history_short_prices"]) if "history_short_prices" in payload else short, ratio)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--no-beta", action="store_true")
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(Path(args.input).read_text())
        if not isinstance(payload, dict):
            raise ValueError("input must be an object")
        result = compute(payload, no_beta=args.no_beta, history=args.history)
        rendered = json.dumps(result, allow_nan=False, indent=2)
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        print(f"pair_math: {exc}", file=sys.stderr)
        return 2
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
