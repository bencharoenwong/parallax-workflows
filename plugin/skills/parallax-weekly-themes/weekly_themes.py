"""Deterministic arithmetic for /parallax-weekly-themes.

Reads the ``markets`` object returned by ``get_telemetry`` and computes the
per-market weekly rows and the cross-market "themes of the week" ranking. Pure
functions only: no I/O except the CLI wrapper at the bottom.

Field contract (observed on the public tool; see SKILL.md Gotchas):
    markets[<code>] = {
        "as_of": "YYYY-MM-DD", "market_name": str, "n_baskets": int,
        "top_wtd": {"name": str, "value": float},
        "bottom_wtd": {"name": str, "value": float},
        "distribution_wtd": [min, q1, median, q3, max],
        "n_positive_wtd": int, "aggregate_wtd": float, ...
    }
Returns are decimals (0.0213 means +2.13%).
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import date
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

MIN_THEMES_FOR_RANKING = 3
DEFAULT_TOP = 5


@dataclass(frozen=True)
class MarketRow:
    """One market's week-to-date summary."""

    code: str
    market_name: str
    as_of: str
    n_themes: int
    leader: Optional[str]
    leader_wtd: Optional[float]
    leader_vs_median: Optional[float]
    laggard: Optional[str]
    laggard_wtd: Optional[float]
    laggard_vs_median: Optional[float]
    median_wtd: Optional[float]
    breadth: Optional[float]
    note: str = ""


@dataclass
class WeeklyThemes:
    """Full computed payload consumed by the Compose step."""

    report_date: str
    markets: list[MarketRow] = field(default_factory=list)
    themes_of_week: list[MarketRow] = field(default_factory=list)
    not_covered: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    unknown_freshness: list[str] = field(default_factory=list)


def _num(value: Any) -> Optional[float]:
    """Return value as float, or None when absent or non-numeric."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        raise ValueError("return/distribution value must be finite")
    return float(value)


def _median(dist: Any) -> Optional[float]:
    """Middle point of the 5-point distribution, or None if malformed."""
    if not isinstance(dist, list) or len(dist) != 5:
        return None
    return _num(dist[2])


def _diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return round(a - b, 6)


def _date(value: Any, field_name: str) -> str:
    """Return a validated calendar date, or empty for explicitly missing data."""
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{field_name} must be YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a calendar date") from exc
    return value


def market_row(code: str, m: dict[str, Any], report_date: str) -> MarketRow:
    """Build one market's row from its ``markets`` entry."""
    report_date = _date(report_date, "report_date")
    as_of = _date(m.get("as_of"), f"{code}.as_of")
    n = m.get("n_baskets")
    if n is not None and (isinstance(n, bool) or not isinstance(n, int) or n < 0):
        raise ValueError(f"{code}.n_baskets must be a nonnegative integer")
    n_themes = n if isinstance(n, int) and not isinstance(n, bool) else 0
    top = m.get("top_wtd")
    bottom = m.get("bottom_wtd")
    top = {} if top is None else top
    bottom = {} if bottom is None else bottom
    if not isinstance(top, dict) or not isinstance(bottom, dict):
        raise ValueError(f"{code} leader/laggard must be objects")
    median = _median(m.get("distribution_wtd"))
    leader_wtd = _num(top.get("value"))
    laggard_wtd = _num(bottom.get("value"))
    pos = m.get("n_positive_wtd")
    if pos is not None and (isinstance(pos, bool) or not isinstance(pos, int) or not 0 <= pos <= n_themes):
        raise ValueError(f"{code}.n_positive_wtd must lie between 0 and n_baskets")
    breadth = (
        round(pos / n_themes, 4)
        if n_themes > 0 and isinstance(pos, int) and not isinstance(pos, bool)
        else None
    )
    notes = []
    if n_themes == 1:
        notes.append("single theme; no leader/laggard spread")
    if report_date and m.get("as_of") and m.get("as_of") != report_date:
        notes.append(f"data as of {m.get('as_of')}")
    if not report_date or not as_of:
        notes.append("freshness unknown; excluded from ranking")
    single = n_themes == 1
    return MarketRow(
        code=code,
        market_name=str(m.get("market_name") or code),
        as_of=as_of,
        n_themes=n_themes,
        leader=top.get("name"),
        leader_wtd=leader_wtd,
        leader_vs_median=None if single else _diff(leader_wtd, median),
        laggard=None if single else bottom.get("name"),
        laggard_wtd=None if single else laggard_wtd,
        laggard_vs_median=None if single else _diff(laggard_wtd, median),
        median_wtd=median,
        breadth=breadth,
        note="; ".join(notes),
    )


def compute(
    payload: dict[str, Any],
    markets: Optional[list[str]] = None,
    top: int = DEFAULT_TOP,
) -> WeeklyThemes:
    """Compute market rows and the cross-market ranking.

    Args:
        payload: the ``get_telemetry`` response (needs ``markets``; ``report_date`` optional).
        markets: market codes to include; None means every market returned.
        top: how many themes to rank across markets.

    Ranking: each market contributes its leader once; markets with fewer than
    ``MIN_THEMES_FOR_RANKING`` themes and stale markets (``as_of`` differs from
    ``report_date``) are excluded; order is leader_vs_median
    descending, ties broken by market code. A market's leader is never ranked
    without a median to compare against.
    """
    if isinstance(top, bool) or not isinstance(top, int) or top < 1:
        raise ValueError("top must be >= 1")
    data = payload.get("markets")
    if not isinstance(data, dict):
        raise ValueError("payload has no 'markets' object")
    report_date = _date(payload.get("report_date"), "report_date")
    wanted = list(dict.fromkeys(c.upper() for c in markets)) if markets else sorted(data)
    out = WeeklyThemes(report_date=report_date)
    for code in wanted:
        entry = data.get(code)
        if not isinstance(entry, dict):
            out.not_covered.append(code)
            continue
        row = market_row(code, entry, report_date)
        out.markets.append(row)
        if not report_date or not row.as_of:
            out.unknown_freshness.append(code)
        if report_date and row.as_of and row.as_of != report_date:
            out.stale.append(code)
    rankable = [
        r for r in out.markets
        if r.n_themes >= MIN_THEMES_FOR_RANKING
        and r.leader_vs_median is not None
        and r.code not in out.stale
        and r.code not in out.unknown_freshness
    ]
    rankable.sort(key=lambda r: (-r.leader_vs_median, r.code))
    out.themes_of_week = rankable[:top]
    return out


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: read a get_telemetry JSON response, print the computed JSON."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", required=True, help="path to the get_telemetry JSON response")
    ap.add_argument("--markets", default="", help="comma-separated market codes; empty = all")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP)
    args = ap.parse_args(argv)
    codes = [c.strip() for c in args.markets.split(",") if c.strip()] or None
    try:
        with open(args.input, encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict):
            raise ValueError("payload is not a JSON object")
        result = compute(payload, codes, args.top)
    except (OSError, ValueError) as exc:
        print(f"weekly_themes: {exc}", file=sys.stderr)
        return 2
    json.dump(asdict(result), sys.stdout, indent=2, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
