#!/usr/bin/env python3
"""Deterministic redundancy-coverage cross-check for rebalance and client-review.

`check_portfolio_redundancy`'s sector concentration block can silently drop
coverage for holdings the server-side redundancy engine does not recognize --
the response still reports `success: true`, so nothing in the tool's own
output tells the caller its sector total no longer adds up. This
helper compares `check_portfolio_redundancy`'s sector weights against
`analyze_portfolio.sector_allocation`'s and renders a verdict a skill can
render directly, instead of the skill re-deriving the arithmetic in prose on
every run. Pure stdlib, no network -- a real Bash tool call the skill shells
out to, the same operator-agnostic-helper pattern as `render_gate.py` and
`client-policy/reconcile.py` (see `_parallax/house-view/loader.md` §2 for the
rationale: deterministic math lives in a helper, never reproduced in prose).

Verdict:
  consistent        -- the redundancy sector breakdown covers the portfolio
                       and tracks analyze_portfolio's weights closely.
  coverage_limited  -- the redundancy sector total falls short of
                       COVERAGE_TOTAL_MIN, any single sector diverges from
                       analyze_portfolio by more than MAX_DIVERGENCE_PP
                       percentage points, a sector name in one payload has no
                       counterpart in the other, or (when `--holdings` was
                       given) a held symbol is absent from the redundancy
                       payload entirely.

Usage:
    python3 coverage_check.py --portfolio-sectors <json-file-or-inline> \\
        --redundancy-sectors <json-file-or-inline> [--holdings <json-file-or-inline>]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Constants -- chosen, not calibrated. These label a data-quality state
# (the redundancy tool's sector breakdown looks partial) and drive no
# pass/fail trading verdict; a threshold value for a verdict that DOES gate
# a decision would be calibration and is out of scope here.
# --------------------------------------------------------------------------
COVERAGE_TOTAL_MIN = 0.98
MAX_DIVERGENCE_PP = 5.0

VERDICT_CONSISTENT = "consistent"
VERDICT_COVERAGE_LIMITED = "coverage_limited"


class CoverageInputError(ValueError):
    """A CLI input was neither valid inline JSON nor a readable JSON file."""


@dataclass(frozen=True)
class CoverageResult:
    verdict: str
    redundancy_total: float
    max_divergence_pp: float
    diverging_sectors: list[dict[str, Any]]
    absent_holdings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_sector(name: Any) -> str:
    """Case/whitespace-fold a sector name so the two payloads compare cleanly."""
    if not isinstance(name, str):
        return ""
    return " ".join(name.strip().split()).casefold()


def _as_weight_map(sectors: Any) -> dict[str, float]:
    """Coerce a sector-weights payload into ``{normalized_name: weight}``.

    Accepts either ``{"<sector>": <weight>, ...}`` or
    ``[{"sector": ..., "weight": ...}, ...]`` -- the live schema for either
    source tool is discovered at runtime, not pinned here, so both common
    shapes are read. A non-finite or non-numeric weight is dropped, never
    guessed. Two entries that normalize to the same name are summed.
    """
    out: dict[str, float] = {}
    if isinstance(sectors, dict):
        items = list(sectors.items())
    elif isinstance(sectors, list):
        items = [
            (entry.get("sector"), entry.get("weight"))
            for entry in sectors
            if isinstance(entry, dict)
        ]
    else:
        return out
    for name, weight in items:
        key = _normalize_sector(name)
        if not key:
            continue
        try:
            value = float(weight)
        except (TypeError, ValueError):
            continue
        if value != value or value in (float("inf"), float("-inf")):  # NaN/inf guard
            continue
        out[key] = out.get(key, 0.0) + value
    return out


def _holding_symbols(holdings: Any) -> list[str]:
    """Extract holding symbols from ``[<symbol>, ...]`` or ``[{"symbol": ...}, ...]``."""
    if not isinstance(holdings, list):
        return []
    symbols: list[str] = []
    for entry in holdings:
        if isinstance(entry, str):
            symbols.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("symbol"), str):
            symbols.append(entry["symbol"])
    return symbols


def _flatten_strings(value: Any) -> set[str]:
    """Collect every string leaf in a nested JSON structure.

    The redundancy tool's per-sector membership shape is not pinned by any
    schema doc (response-schemas.md documents `analyze_portfolio` only), so
    absence is checked by scanning every string leaf for the symbol rather
    than assuming a `symbols`/`holdings`/`members` key that may not exist in
    the live response.
    """
    found: set[str] = set()
    if isinstance(value, str):
        found.add(value)
    elif isinstance(value, dict):
        for v in value.values():
            found |= _flatten_strings(v)
    elif isinstance(value, list):
        for v in value:
            found |= _flatten_strings(v)
    return found


def _absent_holdings(holdings: Any, redundancy_sectors: Any) -> list[str]:
    """Name every held symbol absent from the redundancy payload.

    Only computable when ``holdings`` was supplied; returns ``[]`` otherwise
    rather than guessing coverage from the sector totals alone.
    """
    if holdings is None:
        return []
    symbols = _holding_symbols(holdings)
    if not symbols:
        return []
    present = _flatten_strings(redundancy_sectors)
    return sorted(s for s in symbols if s not in present)


def check_coverage(
    portfolio_sectors: Any,
    redundancy_sectors: Any,
    holdings: Any = None,
) -> CoverageResult:
    """Cross-check `check_portfolio_redundancy` sector coverage against
    `analyze_portfolio.sector_allocation`.

    portfolio_sectors / redundancy_sectors: the two tools' sector-weight
    payloads (see `_as_weight_map` for accepted shapes). holdings: optional
    list of held symbols; when given, enables `absent_holdings` detection.
    """
    portfolio_map = _as_weight_map(portfolio_sectors)
    redundancy_map = _as_weight_map(redundancy_sectors)

    redundancy_total = round(sum(redundancy_map.values()), 6)

    diverging: list[dict[str, Any]] = []
    max_divergence = 0.0
    for sector in sorted(set(portfolio_map) | set(redundancy_map)):
        p = portfolio_map.get(sector)
        r = redundancy_map.get(sector)
        p_pp = (p or 0.0) * 100.0
        r_pp = (r or 0.0) * 100.0
        divergence_pp = round(abs(p_pp - r_pp), 6)
        max_divergence = max(max_divergence, divergence_pp)
        unmatched = p is None or r is None
        if unmatched or divergence_pp > MAX_DIVERGENCE_PP:
            diverging.append({
                "sector": sector,
                "portfolio_weight": p,
                "redundancy_weight": r,
                "divergence_pp": divergence_pp,
                "unmatched": unmatched,
            })

    absent_holdings = _absent_holdings(holdings, redundancy_sectors)

    verdict = VERDICT_CONSISTENT
    if redundancy_total < COVERAGE_TOTAL_MIN or diverging or absent_holdings:
        verdict = VERDICT_COVERAGE_LIMITED

    return CoverageResult(
        verdict=verdict,
        redundancy_total=redundancy_total,
        max_divergence_pp=round(max_divergence, 6),
        diverging_sectors=diverging,
        absent_holdings=absent_holdings,
    )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _load_json_arg(value: str, flag: str) -> Any:
    """Parse a CLI value as inline JSON, or read and parse it as a file path.

    Tries inline JSON first -- the common case for a compact sector-weights
    payload passed straight from the calling skill's Bash step. Falls back to
    treating the value as a file path. Never guesses a shape from a value
    that is neither.
    """
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass
    path = Path(value)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CoverageInputError(
            f"{flag}: {value!r} is neither valid inline JSON nor a readable "
            f"file ({exc})"
        ) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CoverageInputError(
            f"{flag}: file {value!r} does not contain valid JSON ({exc})"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-check check_portfolio_redundancy sector coverage "
                    "against analyze_portfolio.sector_allocation.")
    parser.add_argument("--portfolio-sectors", required=True,
                        help="analyze_portfolio sector_allocation payload, "
                             "inline JSON or a file path.")
    parser.add_argument("--redundancy-sectors", required=True,
                        help="check_portfolio_redundancy sector weights "
                             "payload, inline JSON or a file path.")
    parser.add_argument("--holdings", default=None,
                        help="Optional held-symbol list, inline JSON or a "
                             "file path; enables absent_holdings detection.")
    args = parser.parse_args(argv)

    try:
        portfolio_sectors = _load_json_arg(args.portfolio_sectors, "--portfolio-sectors")
        redundancy_sectors = _load_json_arg(args.redundancy_sectors, "--redundancy-sectors")
        holdings = (
            _load_json_arg(args.holdings, "--holdings")
            if args.holdings is not None else None
        )
    except CoverageInputError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2

    if not portfolio_sectors or not redundancy_sectors:
        print(json.dumps({
            "error": "--portfolio-sectors and --redundancy-sectors must both "
                     "be non-empty; a missing input is not guessable and "
                     "must never be treated as zero coverage.",
        }))
        return 2

    result = check_coverage(portfolio_sectors, redundancy_sectors, holdings)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
