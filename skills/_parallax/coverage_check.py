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
                       given) a held symbol is confirmed absent from the
                       redundancy payload.

absent_holdings / absent_holdings_basis:
  The live `check_portfolio_redundancy` response is aggregate-only --
  sector-level weights, no per-holding inclusion list anywhere in the
  payload. `absent_holdings` is therefore computed two different ways
  depending on what the redundancy payload actually carries, and
  `absent_holdings_basis` names which one ran:
    "per_holding"      -- the redundancy payload carries per-holding data
                          (something beyond aggregate sector/weight pairs);
                          each held symbol was checked against it directly.
    "sector_inference"  -- the redundancy payload is aggregate-only. A held
                          symbol is reportable only when its OWN sector
                          (each holding entry must carry a "sector" tag)
                          shows the redundancy weight materially below the
                          portfolio weight for that sector. A holding whose
                          sector shows no divergence, or that carries no
                          sector tag, is never reported.
    "not_computable"    -- neither is possible (no holdings supplied, or an
                          aggregate-only payload with no sector-tagged
                          holdings to key off). `absent_holdings` is `[]`
                          and this basis alone never forces coverage_limited.

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
# MAX_DIVERGENCE_PP is reused, not re-derived, for the sector_inference
# basis of absent_holdings below -- a single divergence threshold, one
# meaning, everywhere it appears in this module.
# --------------------------------------------------------------------------
COVERAGE_TOTAL_MIN = 0.98
MAX_DIVERGENCE_PP = 5.0

VERDICT_CONSISTENT = "consistent"
VERDICT_COVERAGE_LIMITED = "coverage_limited"

ABSENT_HOLDINGS_BASIS_PER_HOLDING = "per_holding"
ABSENT_HOLDINGS_BASIS_SECTOR_INFERENCE = "sector_inference"
ABSENT_HOLDINGS_BASIS_NOT_COMPUTABLE = "not_computable"


class CoverageInputError(ValueError):
    """A CLI input was neither valid inline JSON nor a readable JSON file."""


@dataclass(frozen=True)
class CoverageResult:
    verdict: str
    redundancy_total: float
    max_divergence_pp: float
    diverging_sectors: list[dict[str, Any]]
    absent_holdings: list[str]
    absent_holdings_basis: str

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


def _holding_records(holdings: Any) -> list[dict[str, Any]]:
    """Normalize holdings into ``[{"symbol": str, "sector": str | None}, ...]``.

    Accepts ``[<symbol>, ...]`` (no sector available -- ``sector`` is
    ``None``) or ``[{"symbol": ..., "sector": ...}, ...]`` (sector optional
    per entry). The sector tag, when present, is normalized the same way as
    a sector-weights payload key so it compares cleanly against
    `diverging_sectors` entries.
    """
    if not isinstance(holdings, list):
        return []
    records: list[dict[str, Any]] = []
    for entry in holdings:
        if isinstance(entry, str):
            records.append({"symbol": entry, "sector": None})
        elif isinstance(entry, dict) and isinstance(entry.get("symbol"), str):
            sector = entry.get("sector")
            records.append({
                "symbol": entry["symbol"],
                "sector": _normalize_sector(sector) if isinstance(sector, str) else None,
            })
    return records


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


def _has_per_holding_data(redundancy_sectors: Any) -> bool:
    """Whether the redundancy payload carries anything beyond aggregate
    sector/weight pairs -- i.e. a per-holding membership list a symbol can
    actually be checked against.

    The live `check_portfolio_redundancy` response is aggregate-only:
    ``{"<sector>": <weight>, ...}`` or ``[{"sector": ..., "weight": ...}, ...]``,
    with no holding-level membership anywhere in the structure. Checking a
    symbol against `_flatten_strings` of that payload only ever matches
    sector *names*, never holdings, so every held symbol reported absent
    regardless of actual coverage -- that was the defect. This detects the
    aggregate-only case so absence falls back to sector-level inference
    instead (see `_absent_holdings`). A dict value or sector-entry key that
    is itself a list/dict (a "members"/"symbols"/"pairs"/"covered"-style
    key, whatever the live shape turns out to be) is treated as per-holding
    data present.
    """
    if isinstance(redundancy_sectors, dict):
        return any(isinstance(v, (dict, list)) for v in redundancy_sectors.values())
    if isinstance(redundancy_sectors, list):
        for entry in redundancy_sectors:
            if not isinstance(entry, dict):
                continue
            for key, v in entry.items():
                if key in ("sector", "weight"):
                    if isinstance(v, (dict, list)):
                        return True
                    continue
                return True
        return False
    return False


def _absent_holdings(
    holdings: Any,
    redundancy_sectors: Any,
    diverging_sectors: list[dict[str, Any]],
) -> tuple[list[str], str]:
    """Name every held symbol absent from the redundancy payload, and the
    basis for that determination -- see the module docstring's
    "absent_holdings / absent_holdings_basis" section for the three values.

    Only computable when ``holdings`` was supplied. Never infers per-holding
    absence from an aggregate-only redundancy payload by string-matching
    symbols against sector names -- that always fails to match and reports
    every holding absent, which is exactly the failure this replaces.
    """
    if holdings is None:
        return [], ABSENT_HOLDINGS_BASIS_NOT_COMPUTABLE
    records = _holding_records(holdings)
    if not records:
        return [], ABSENT_HOLDINGS_BASIS_NOT_COMPUTABLE

    if _has_per_holding_data(redundancy_sectors):
        present = _flatten_strings(redundancy_sectors)
        absent = sorted({r["symbol"] for r in records if r["symbol"] not in present})
        return absent, ABSENT_HOLDINGS_BASIS_PER_HOLDING

    # Aggregate-only redundancy payload: no per-holding list exists to check
    # a symbol against. Fall back to sector-level inference -- a holding is
    # reportable only when its OWN sector's redundancy weight is materially
    # below its portfolio weight (or the sector is missing from the
    # redundancy payload entirely), and only when the holding carries a
    # sector tag at all.
    underrepresented_sectors: set[str] = set()
    for d in diverging_sectors:
        p = d.get("portfolio_weight")
        r = d.get("redundancy_weight")
        if r is None and p is not None:
            underrepresented_sectors.add(d["sector"])
        elif p is not None and r is not None and r < p:
            underrepresented_sectors.add(d["sector"])

    tagged = [r for r in records if r["sector"] is not None]
    if not tagged:
        return [], ABSENT_HOLDINGS_BASIS_NOT_COMPUTABLE

    candidates = sorted({
        r["symbol"] for r in tagged if r["sector"] in underrepresented_sectors
    })
    return candidates, ABSENT_HOLDINGS_BASIS_SECTOR_INFERENCE


def check_coverage(
    portfolio_sectors: Any,
    redundancy_sectors: Any,
    holdings: Any = None,
) -> CoverageResult:
    """Cross-check `check_portfolio_redundancy` sector coverage against
    `analyze_portfolio.sector_allocation`.

    portfolio_sectors / redundancy_sectors: the two tools' sector-weight
    payloads (see `_as_weight_map` for accepted shapes). holdings: optional
    list of held symbols (plain strings, or `{"symbol": ..., "sector": ...}`
    objects -- the sector tag is what enables `sector_inference` basis
    against an aggregate-only redundancy payload); when given, enables
    `absent_holdings` detection. See the module docstring for the three
    `absent_holdings_basis` values.
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

    absent_holdings, absent_holdings_basis = _absent_holdings(
        holdings, redundancy_sectors, diverging)

    # A "not_computable" basis is a data-availability statement, not a
    # divergence finding -- it never forces coverage_limited on its own.
    # This falls out naturally: `_absent_holdings` always returns `[]`
    # alongside "not_computable", so the `absent_holdings` truthiness check
    # below already excludes it without a separate basis check.
    verdict = VERDICT_CONSISTENT
    if redundancy_total < COVERAGE_TOTAL_MIN or diverging or absent_holdings:
        verdict = VERDICT_COVERAGE_LIMITED

    return CoverageResult(
        verdict=verdict,
        redundancy_total=redundancy_total,
        max_divergence_pp=round(max_divergence, 6),
        diverging_sectors=diverging,
        absent_holdings=absent_holdings,
        absent_holdings_basis=absent_holdings_basis,
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
                             "file path; entries may be plain symbols or "
                             "{\"symbol\": ..., \"sector\": ...} objects. "
                             "Enables absent_holdings detection.")
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
