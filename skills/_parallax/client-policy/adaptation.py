"""Client-policy adaptation — operator-agnostic, deterministic helper.

Computes stages S0-S2 for an optional client policy supplied at invocation:

    S0  Basis normalization. A dimension declaring `basis: total` has its
        weights (and band edges) divided by `mandate.strategic_allocation.equity`
        so everything downstream is on the equity-SLEEVE basis. `basis: sleeve`
        passes through. A missing basis is never assumed.
    S1  Drift. `drift = current - policy` per segment, the band status
        (inside / near_edge_* / breach_* / no_bands), and passive-vs-active
        attribution for a breach.
    S2  Tactical sizing. `desired_active = (tilt / 2) * k * room` in the tilt
        direction, one common budget scale when the total exceeds
        `max_total_tilt`, and a closed five-value alignment verdict.

Why this exists separately from `policy-loader.md`:
the allocation arithmetic and the threshold comparisons must be identical
across operator LLMs (Claude / GPT / Gemini). Markdown instructions can drift
or get skipped under context pressure; a one-line shell call to this module
returns the same numbers every time. This is the same argument that keeps the
house-view date arithmetic in `house-view/view_status.py`.

The helper NEVER auto-resolves a conflict. Precedence is: view excludes and
mandate `prohibited_products` outrank bands and user constraints, which outrank
tilts. When any of those collide, a `Conflict` row is emitted for a human to
decide. Nothing is dropped, netted out, or silently reweighted.

CLI:
    python adaptation.py --policy <file.yaml>
    python adaptation.py --policy <file.yaml> --exposures <file.json> \\
        --view-tilts <file.json> --today 2026-08-29 --json

Exit 0 on any data-level outcome, validation errors included — a policy that
parses but is not a mapping is one of those, and returns the `no_policy` tier
with a blocking error and an empty `policy_hash`. Exit 2 only on an unreadable
file, unparseable YAML/JSON, bad arguments, or an `--exposures` / `--view-tilts`
payload that parses but is not a JSON object (an operator mistake, not data).

--------------------------------------------------------------------------
`--exposures` payload schema (pinned; stated identically in `policy-loader.md`
§3 and in `SKILL.md` Batch C)
--------------------------------------------------------------------------

    {
      "basis": "sleeve",
      "dimensions": {
        "region": {"us": 0.62, "europe": 0.20, "japan": 0.08, "em_ex_china": 0.10},
        "sector": {"information_technology": 0.34, "financials": 0.18,
                   "health_care": 0.30, "energy": 0.18}
      },
      "coverage": {"region": 0.97, "sector": 1.00},
      "unmapped": [{"symbol": "ABC.L", "weight": 0.03, "dimension": "region"}],
      "holdings": [{"symbol": "AAPL.O", "isin": "US0378331005", "weight": 0.25,
                    "region": "us", "sector": "information_technology"}]
    }

  - `basis` must be `"sleeve"` — Phase 1 accepts sleeve-relative exposures only;
    the producer converts before calling. A missing or non-`"sleeve"` `basis`
    is rejected at the CLI (exit 2, naming the file and the offending value),
    the same operator-mistake class as a non-object payload; no conversion is
    implemented in Phase 1.
  - The whole payload is checked by `validate_exposures` against this contract
    (known dimensions, finite weights in [0, 1], per-dimension sums, coverage
    consistent with the `unmapped` weight it implies). At the CLI a violation is
    an operator mistake: exit 2, naming the file and every violation. Called as
    a library the helper proceeds WITHOUT exposures and discloses one
    `invalid_exposures` Data Quality row per violation; it never certifies an
    impossible payload with a band verdict.
  - Per dimension, weights are renormalized over MAPPED holdings and sum to 1.0
    within 1e-6. Every dimension in the example above sums to 1.0.
  - `coverage[dim]` is the mapped weight fraction BEFORE renormalization. A
    coverage below 1.0 emits `unmapped_holding` rows and is disclosed in the
    rendered table. `coverage` passes through onto the result unchanged so the
    consumer can caveat a conditional diagnostic.
  - `unmapped` lists every holding excluded from a dimension's denominator.
  - `holdings` is required only for the exclude and prohibited-product conflict
    checks. Absent `holdings` suppresses those two conflict kinds and emits
    nothing; the check is a disclosure, not a gate.
  - `isin` on a holding is OPTIONAL. When present it is matched against
    `mandate.prohibited_products` alongside `symbol` (case-insensitive). An
    ISIN-shaped prohibition with any holding lacking an `isin` emits a
    `hard_constraint_not_checkable` row: the check ran on partial identifiers.

--------------------------------------------------------------------------
`--view-tilts` payload schema (pinned)
--------------------------------------------------------------------------

    {"regions": {"us": 1, "japan": -1}, "sectors": {"information_technology": -2},
     "excludes": ["tobacco", "GAZP.MM", "russia"]}

Produced from the loaded house view after the `loader.md` §3 alias collapse.
Factors, styles, and themes are deliberately absent: they are tactical-only and
never enter band math.

Row order is deterministic: dimensions in `DIMENSIONS` order, then segments in
policy declaration order within each dimension.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import yaml

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

K_PRESETS = {"conservative": 0.25, "balanced": 0.50, "aggressive": 0.75}
DEFAULT_K = 0.50
NEAR_EDGE_FRACTION = 0.20          # fraction of the room on that side; see band_status
CALIBRATION_STATUS = "heuristic_phase0"
DIMENSIONS = ("region", "sector")  # Phase 1 dimensions, in render order
EQUITY_KEY = "equity"

SUM_TOLERANCE = 1e-6

# Shape of a security identifier of the 12-character checksummed kind: two letter
# country prefix, nine alphanumerics, one check digit. Used only to recognize
# which `prohibited_products` entries need an `isin` on the holding to match.
ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

# Segment key sets, verbatim from `house-view/schema.yaml`. `code_list` on a
# dimension names which of these the segment keys must come from.
REGION_KEYS = frozenset({
    "us", "canada", "uk", "europe", "germany", "france", "italy", "spain",
    "switzerland", "japan", "australia",
    "china", "hong_kong", "taiwan", "south_korea", "india", "apac_ex_japan",
    "singapore", "indonesia", "philippines", "thailand", "vietnam", "malaysia",
    "em_ex_china", "mexico", "brazil", "chile",
    "emea", "mena",
})
SECTOR_KEYS = frozenset({
    "energy", "materials", "industrials", "consumer_discretionary",
    "consumer_staples", "health_care", "financials", "information_technology",
    "communication_services", "utilities", "real_estate",
})
CODE_LISTS = {
    "parallax_region_v1": REGION_KEYS,
    "gics_sector_v1": SECTOR_KEYS,
}

# Broad bucket -> the SPECIFIC country keys it contains, derived from the four
# keys marked "# broad" in `house-view/schema.yaml` and that file's own section
# comments (Developed Markets / Emerging Asia / ASEAN / Latam / EMEA-MENA).
# Only specific keys appear as members; a broad key is never a member of another.
# `loader.md` §3 precedence: a specific country key wins over its bucket, and a
# specific and a broad tilt are NEVER summed.
BROAD_REGION_MEMBERS: dict[str, tuple[str, ...]] = {
    "europe": ("uk", "germany", "france", "italy", "spain", "switzerland"),
    "apac_ex_japan": (
        "china", "hong_kong", "taiwan", "south_korea", "india", "australia",
        "singapore", "indonesia", "philippines", "thailand", "vietnam", "malaysia",
    ),
    "em_ex_china": (
        "taiwan", "south_korea", "india", "indonesia", "philippines", "thailand",
        "vietnam", "malaysia", "mexico", "brazil", "chile",
    ),
    "emea": ("mena",),
}

# Which key in the view-tilts payload carries each policy dimension's tilts.
_TILT_SECTION = {"region": "regions", "sector": "sectors"}


# --------------------------------------------------------------------------
# Dataclasses
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PolicyError:
    """One validation failure, addressed by dotted path into the policy document."""
    path: str
    reason: str
    severity: str = "blocking"      # blocking | dimension
    dimension: str | None = None


@dataclass(frozen=True)
class Segment:
    """One policy segment: a dimension key with its policy weight and optional band edges."""
    dimension: str
    key: str
    policy: float
    band_min: float | None
    band_max: float | None


@dataclass(frozen=True)
class DriftRow:
    """S1 output for one segment: current vs policy, band status, and breach attribution."""
    dimension: str
    key: str
    current: float
    policy: float
    drift: float               # current - policy
    band_min: float | None
    band_max: float | None
    band_status: str           # inside|near_edge_high|near_edge_low|breach_high|breach_low|no_bands
    breach_kind: str | None    # passive|active; None when band_status is not a breach
    distance_to_edge: float | None   # |current - nearest present edge|; feeds conventions §11


@dataclass(frozen=True)
class TaaRow:
    """S2 output for one segment: tilt, available room, desired active, and alignment verdict."""
    dimension: str
    key: str
    tilt: int
    current_active: float          # current - policy
    room_up: float | None          # band_max - policy; None when band_max absent
    room_down: float | None        # policy - band_min; None when band_min absent
    desired_active: float | None   # None under multiplier_fallback or a missing band side
    budget_scale: float            # 1.0 when no cap fired
    semantics: str                 # policy|multiplier_fallback
    alignment: str                 # aligned|opposed|capped_by_band|no_view|not_evaluable


@dataclass(frozen=True)
class Conflict:
    """A precedence collision surfaced for human decision; never auto-resolved."""
    kind: str          # tilt_vs_band|exclude_vs_holding|prohibited_vs_holding
    detail: dict


@dataclass(frozen=True)
class DataQualityRow:
    """One disclosure about coverage, conversion, staleness, an unevaluated budget, an
    unresolvable tilt inheritance, a rejected exposures payload, an unclassifiable hard
    constraint, or exposure weight sitting outside the policy."""
    kind: str          # uncovered_dimension|unmapped_holding|basis_converted|
                       # basis_unconfirmed_drift|stale_policy|
                       # te_budget_not_evaluated|missing_bands|unknown_segment_key|
                       # ambiguous_broad_tilt|invalid_exposures|
                       # hard_constraint_not_checkable|off_policy_exposure
    detail: str


@dataclass(frozen=True)
class AdaptationResult:
    """Complete S0-S2 result. Every field renders; nothing is computed downstream."""
    fallback_tier: str             # no_policy|weights_only|full|partial_dimensions
    resolved_k: float
    k_source: str                  # "preset:<name>"|"explicit"|"default"
    calibration_status: str
    near_edge_fraction: float      # disclosed in the SAA Drift table
    errors: list[PolicyError]
    drift: list[DriftRow]
    taa: list[TaaRow]
    conflicts: list[Conflict]
    data_quality: list[DataQualityRow]
    coverage: dict                 # exposures `coverage` passthrough; {} when absent or rejected
    budget: dict                   # {sum_abs_desired, max_total_tilt, cap_applied, scale}
    policy_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Small shared predicates
# --------------------------------------------------------------------------

def _is_number(v: Any) -> bool:
    """True for a real int/float. Bools are excluded: `True` is an int in Python."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _parse_date(s: Any) -> date | None:
    if not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _budget(sum_abs_desired: float, max_total_tilt: Any, cap_applied: bool, scale: float) -> dict:
    return {
        "sum_abs_desired": sum_abs_desired,
        "max_total_tilt": float(max_total_tilt) if _is_number(max_total_tilt) else None,
        "cap_applied": cap_applied,
        "scale": scale,
    }


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def _finite_weight(value: Any) -> bool:
    """True for a real, finite number in [0, 1]. NaN and infinities are excluded."""
    return _is_number(value) and math.isfinite(float(value)) and 0.0 <= float(value) <= 1.0


def validate_exposures(exposures: Any) -> list[str]:
    """Check the `--exposures` payload against its pinned contract; return violations.

    The producer of this payload is a non-deterministic operator LLM, so the
    helper never trusts its arithmetic: without these checks an impossible input
    (a 120% weight, a coverage fraction contradicting the disclosed unmapped
    weight) is certified downstream as a band verdict. Basis is checked
    separately at the CLI and is not repeated here.

    Every violation is one human-readable string; the list is empty when the
    payload conforms. This function never raises on a data problem.
    """
    violations: list[str] = []
    if not isinstance(exposures, dict):
        return ["exposures payload is not a mapping"]

    dimensions = exposures.get("dimensions")
    if not isinstance(dimensions, dict):
        violations.append("`dimensions` is missing or not a mapping")
        dimensions = {}
    for dim_name, weights in dimensions.items():
        if dim_name not in DIMENSIONS:
            violations.append(
                f"dimensions.{dim_name}: unknown dimension; expected one of {list(DIMENSIONS)}")
            continue
        if not isinstance(weights, dict):
            violations.append(f"dimensions.{dim_name}: not a mapping of segment key to weight")
            continue
        usable = True
        for key, weight in weights.items():
            if not isinstance(key, str):
                violations.append(f"dimensions.{dim_name}: segment key {key!r} is not a string")
                usable = False
                continue
            if not _finite_weight(weight):
                violations.append(
                    f"dimensions.{dim_name}.{key}: weight {weight!r} is not a finite number "
                    "in [0, 1]")
                usable = False
        if usable and weights:
            total = sum(float(v) for v in weights.values())
            if abs(total - 1.0) > SUM_TOLERANCE:
                violations.append(
                    f"dimensions.{dim_name}: mapped weights must sum to 1.0 within "
                    f"{SUM_TOLERANCE} (got {total:.6f})")

    unmapped = exposures.get("unmapped")
    unmapped_by_dim: dict[str, float] = {}
    if unmapped is not None:
        if not isinstance(unmapped, list):
            violations.append("`unmapped` is present but is not a sequence")
            unmapped = []
        for index, entry in enumerate(unmapped):
            if not isinstance(entry, dict):
                violations.append(f"unmapped[{index}]: entry is not a mapping")
                continue
            dim_name = entry.get("dimension")
            if dim_name not in DIMENSIONS:
                violations.append(
                    f"unmapped[{index}].dimension: {dim_name!r} is not a known dimension; "
                    f"expected one of {list(DIMENSIONS)}")
            weight = entry.get("weight")
            if not _finite_weight(weight):
                violations.append(
                    f"unmapped[{index}].weight: {weight!r} is not a finite number in [0, 1]")
                continue
            if isinstance(dim_name, str):
                unmapped_by_dim[dim_name] = unmapped_by_dim.get(dim_name, 0.0) + float(weight)

    coverage = exposures.get("coverage")
    if coverage is not None:
        if not isinstance(coverage, dict):
            violations.append("`coverage` is present but is not a mapping")
        else:
            for dim_name, value in coverage.items():
                if not _finite_weight(value):
                    violations.append(
                        f"coverage.{dim_name}: {value!r} is not a finite number in [0, 1]")
                    continue
                implied = 1.0 - unmapped_by_dim.get(dim_name, 0.0)
                if abs(float(value) - implied) > SUM_TOLERANCE:
                    if dim_name not in unmapped_by_dim:
                        violations.append(
                            f"coverage.{dim_name}: {float(value)} is below 1.0 but no `unmapped` "
                            "entry is disclosed for that dimension")
                    else:
                        violations.append(
                            f"coverage.{dim_name}: {float(value)} disagrees with the disclosed "
                            f"unmapped weight for that dimension (implies {implied:.6f})")

    holdings = exposures.get("holdings")
    if holdings is not None:
        if not isinstance(holdings, list):
            violations.append("`holdings` is present but is not a sequence")
            holdings = []
        for index, entry in enumerate(holdings):
            if not isinstance(entry, dict):
                violations.append(f"holdings[{index}]: entry is not a mapping")
                continue
            if not _finite_weight(entry.get("weight")):
                violations.append(
                    f"holdings[{index}].weight: {entry.get('weight')!r} is not a finite number "
                    "in [0, 1]")
    return violations


def validate_policy(policy: dict) -> list[PolicyError]:
    """Collect every validation failure; never raise on a data problem, never partial-apply.

    Severity is two-class. `blocking` puts the whole policy on the `no_policy`
    rung: structural failures, a wrong `schema_version`, non-numeric or
    out-of-range weights, a band with `min > max`, a policy weight outside its
    own band, a dimension weight-sum violation. `dimension` scopes the failure
    to one dimension, which falls to `multiplier_fallback` while the rest of the
    policy proceeds: a missing `basis`, and `basis: total` without a usable
    `strategic_allocation.equity`.

    `adaptation.k` / `k_preset` failures are also non-blocking: `resolve_k` falls
    through to the preset and then to `DEFAULT_K` rather than clamping, so the
    rest of the policy stays usable. They carry no `dimension`, so the
    per-dimension partition drops nothing.

    Weight-sum target depends on the declared basis: 1.0 on `sleeve`, the equity
    weight on `total`. When `basis` is absent nothing may be assumed, so the sum
    is accepted if it matches EITHER legal target and flagged only when it
    matches neither.

    An unknown segment key is NOT an error; it becomes an `unknown_segment_key`
    Data Quality row and that segment drops out of band math.
    """
    errors: list[PolicyError] = []
    if not isinstance(policy, dict):
        return [PolicyError("<root>", "policy document is not a mapping")]

    meta = policy.get("metadata")
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        errors.append(PolicyError("metadata", "metadata is not a mapping"))
        meta = {}
    schema_version = meta.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version != 1:
        errors.append(PolicyError("metadata.schema_version",
                                  "schema_version must be the integer 1"))
    for field in ("as_of_date", "review_due"):
        value = meta.get(field)
        if value is not None and _parse_date(value) is None:
            errors.append(PolicyError(f"metadata.{field}", "not an ISO-8601 date"))

    mandate = policy.get("mandate")
    if mandate is None:
        mandate = {}
    if not isinstance(mandate, dict):
        errors.append(PolicyError("mandate", "mandate is not a mapping"))
        mandate = {}

    strategic = mandate.get("strategic_allocation") or {}
    if not isinstance(strategic, dict):
        errors.append(PolicyError("mandate.strategic_allocation", "not a mapping"))
        strategic = {}
    for key, value in strategic.items():
        if not _is_number(value) or not (0.0 <= float(value) <= 1.0):
            errors.append(PolicyError(f"mandate.strategic_allocation.{key}",
                                      "weight must be a number in [0, 1]"))
    equity = strategic.get(EQUITY_KEY)

    errors.extend(_validate_bands(mandate.get("allocation_bands") or {},
                                  "mandate.allocation_bands", strategic,
                                  "mandate.strategic_allocation"))

    overlay = mandate.get("tactical_overlay") or {}
    if not isinstance(overlay, dict):
        errors.append(PolicyError("mandate.tactical_overlay", "not a mapping"))
        overlay = {}
    for field in ("max_total_tilt", "max_tracking_error"):
        value = overlay.get(field)
        if value is None:
            continue
        if not _is_number(value) or float(value) <= 0.0:
            errors.append(PolicyError(f"mandate.tactical_overlay.{field}",
                                      "must be a positive number when set"))

    prohibited = mandate.get("prohibited_products")
    if prohibited is not None and not isinstance(prohibited, list):
        errors.append(PolicyError("mandate.prohibited_products", "must be a sequence"))

    sub_allocations = mandate.get("sub_allocations") or {}
    if not isinstance(sub_allocations, dict):
        errors.append(PolicyError("mandate.sub_allocations", "not a mapping"))
        sub_allocations = {}
    dimensions = sub_allocations.get("dimensions") or {}
    if not isinstance(dimensions, dict):
        errors.append(PolicyError("mandate.sub_allocations.dimensions", "not a mapping"))
        dimensions = {}

    for dim_name, dim in dimensions.items():
        base = f"mandate.sub_allocations.dimensions.{dim_name}"
        if not isinstance(dim, dict):
            errors.append(PolicyError(base, "dimension is not a mapping"))
            continue
        basis = dim.get("basis")
        if basis not in ("sleeve", "total"):
            errors.append(PolicyError(
                f"{base}.basis",
                "basis is required and must be 'sleeve' or 'total'; it is never assumed",
                severity="dimension", dimension=dim_name))
        elif basis == "total" and (not _is_number(equity) or float(equity) == 0.0):
            errors.append(PolicyError(
                f"{base}.basis",
                "basis 'total' requires a non-zero mandate.strategic_allocation.equity",
                severity="dimension", dimension=dim_name))

        # Fail loud on an unrecognized (or absent) code list. An unknown name
        # would silently disable the segment-key check in `run_pipeline`, so a
        # typo'd key set would pass validation AND emit no disclosure.
        if dim.get("code_list") not in CODE_LISTS:
            errors.append(PolicyError(
                f"{base}.code_list",
                f"unrecognized code list {dim.get('code_list')!r}; expected one of "
                f"{sorted(CODE_LISTS)}. The segment key set is never guessed."))

        allocation = dim.get("strategic_allocation") or {}
        if not isinstance(allocation, dict):
            errors.append(PolicyError(f"{base}.strategic_allocation", "not a mapping"))
            continue
        for key, value in allocation.items():
            if not _is_number(value) or not (0.0 <= float(value) <= 1.0):
                errors.append(PolicyError(f"{base}.strategic_allocation.{key}",
                                          "weight must be a number in [0, 1]"))

        errors.extend(_validate_bands(dim.get("allocation_bands") or {},
                                      f"{base}.allocation_bands", allocation,
                                      f"{base}.strategic_allocation"))

        if allocation:
            total_weight = sum(float(v) for v in allocation.values() if _is_number(v))
            if basis == "sleeve":
                if abs(total_weight - 1.0) > SUM_TOLERANCE:
                    errors.append(PolicyError(
                        f"{base}.strategic_allocation",
                        f"weights must sum to 1.0 on 'sleeve' basis (got {total_weight:.6f})"))
            elif basis == "total":
                if _is_number(equity) and float(equity) != 0.0 \
                        and abs(total_weight - float(equity)) > SUM_TOLERANCE:
                    errors.append(PolicyError(
                        f"{base}.strategic_allocation",
                        f"weights must sum to the equity weight {float(equity):.6f} on "
                        f"'total' basis (got {total_weight:.6f})"))
            else:
                targets = [1.0] + ([float(equity)] if _is_number(equity) else [])
                if all(abs(total_weight - t) > SUM_TOLERANCE for t in targets):
                    errors.append(PolicyError(
                        f"{base}.strategic_allocation",
                        f"weights sum to {total_weight:.6f}, which matches neither legal "
                        "target (1.0 on 'sleeve', the equity weight on 'total')"))

    adaptation_cfg = policy.get("adaptation") or {}
    if not isinstance(adaptation_cfg, dict):
        errors.append(PolicyError("adaptation", "not a mapping", severity="dimension"))
        adaptation_cfg = {}
    k = adaptation_cfg.get("k")
    if k is not None and (not _is_number(k) or not (0.0 < float(k) <= 1.0)):
        errors.append(PolicyError("adaptation.k",
                                  "explicit k must satisfy 0 < k <= 1.0; it is never clamped",
                                  severity="dimension"))
    k_preset = adaptation_cfg.get("k_preset")
    if k_preset is not None and k_preset not in K_PRESETS:
        errors.append(PolicyError("adaptation.k_preset",
                                  f"unknown preset; expected one of {sorted(K_PRESETS)}",
                                  severity="dimension"))
    return errors


def _validate_bands(bands: Any, base_path: str, weights: dict, weights_path: str
                    ) -> list[PolicyError]:
    """Range, ordering, and policy-within-band checks for one `allocation_bands` map."""
    errors: list[PolicyError] = []
    if not isinstance(bands, dict):
        return [PolicyError(base_path, "not a mapping")]
    for key, band in bands.items():
        path = f"{base_path}.{key}"
        if not isinstance(band, dict):
            errors.append(PolicyError(path, "band is not a mapping"))
            continue
        band_min, band_max = band.get("min"), band.get("max")
        malformed = False
        for edge_name, edge in (("min", band_min), ("max", band_max)):
            if edge is None:
                continue
            if not _is_number(edge) or not (0.0 <= float(edge) <= 1.0):
                errors.append(PolicyError(f"{path}.{edge_name}",
                                          "band edge must be a number in [0, 1]"))
                malformed = True
        if malformed:
            continue
        if band_min is not None and band_max is not None and float(band_min) > float(band_max):
            errors.append(PolicyError(path, "band min is greater than band max"))
            continue  # A reversed band cannot also be checked for containment.
        weight = weights.get(key)
        if not _is_number(weight):
            continue
        low = band_min is not None and float(weight) < float(band_min)
        high = band_max is not None and float(weight) > float(band_max)
        if low or high:
            errors.append(PolicyError(f"{weights_path}.{key}",
                                      "policy weight lies outside its own band"))
    return errors


# --------------------------------------------------------------------------
# policy_hash (canonicalization pinned in schema.yaml §policy_hash)
# --------------------------------------------------------------------------

def _is_empty(v):
    """Empty iff None / numeric zero / "" / [] / {}, AND not a bool.

    The bool guard is load-bearing: `False == 0` is True in Python, so without
    the isinstance check a `False` would be stripped even though schema.yaml
    Rule 2 explicitly excludes booleans from the empty set.
    """
    if isinstance(v, bool):
        return False
    if v is None:
        return True
    if isinstance(v, (int, float)) and v == 0:
        return True
    return v == "" or v == [] or v == {}


def _strip_empty(obj):
    """Recursively strip empties bottom-up. Always recurse first, then decide."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            v = _strip_empty(v)
            if _is_empty(v):
                continue
            out[k] = v
        return out
    if isinstance(obj, list):
        result = []
        for x in obj:
            y = _strip_empty(x)
            if _is_empty(y):
                continue
            result.append(y)
        return result
    return obj


def compute_policy_hash(policy: dict) -> str:
    """sha256 over the canonicalized `mandate` + `adaptation` subtrees per schema.yaml.

    `metadata` and `governance` are out of scope on purpose: re-supplying the
    same mandate with a new `supplied_at` must preserve the digest, so the audit
    row correlates policy CONTENT, not delivery events.

    A non-mapping argument is canonicalized as an empty body rather than raising
    (invariant 6: never raise on a data problem). `run_pipeline` does not rely on
    that: it reports `policy_hash = ""` for a policy that is not a mapping,
    because R-2 carries a digest only when the policy parsed AS a mapping.
    """
    if not isinstance(policy, dict):
        policy = {}
    body = {
        "mandate": _strip_empty(policy.get("mandate", {}) or {}),
        "adaptation": _strip_empty(policy.get("adaptation", {}) or {}),
    }
    canonical = yaml.safe_dump(
        body, sort_keys=True, default_flow_style=False,
        allow_unicode=True, width=1_000_000, indent=2,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# S0 — k resolution and basis normalization
# --------------------------------------------------------------------------

def resolve_k(policy: dict) -> tuple[float, str]:
    """Explicit k wins over preset; preset over DEFAULT_K. Returns (k, source).

    An out-of-range explicit k is reported by `validate_policy` and falls through
    to the preset, then to DEFAULT_K. It is never clamped silently.
    """
    adaptation_cfg = (policy or {}).get("adaptation") or {}
    if not isinstance(adaptation_cfg, dict):
        return DEFAULT_K, "default"
    k = adaptation_cfg.get("k")
    if _is_number(k) and 0.0 < float(k) <= 1.0:
        return float(k), "explicit"
    preset = adaptation_cfg.get("k_preset")
    if preset in K_PRESETS:
        return K_PRESETS[preset], f"preset:{preset}"
    return DEFAULT_K, "default"


def normalize_to_sleeve(segments: dict, basis: str, equity_weight: float | None
                        ) -> tuple[dict, list[DataQualityRow], list[PolicyError]]:
    """S0. `total` basis divides every weight by equity_weight; `sleeve` passes through.

    `basis == "total"` with `equity_weight` missing or zero returns a PolicyError
    and leaves the weights untouched; the caller drops that dimension to
    multiplier semantics. It never raises and never assumes a basis.
    """
    if basis == "sleeve":
        return dict(segments), [], []
    if basis != "total":
        return dict(segments), [], [PolicyError(
            "basis", "basis is required and must be 'sleeve' or 'total'; it is never assumed",
            severity="dimension")]
    if not _is_number(equity_weight) or float(equity_weight) == 0.0:
        return dict(segments), [], [PolicyError(
            f"mandate.strategic_allocation.{EQUITY_KEY}",
            "basis 'total' requires a non-zero equity weight; weights left unconverted",
            severity="dimension")]
    equity = float(equity_weight)
    converted = {k: (float(v) / equity if _is_number(v) else v) for k, v in segments.items()}
    row = DataQualityRow(
        kind="basis_converted",
        detail=(f"weights converted from 'total' to 'sleeve' basis by dividing by "
                f"equity={equity}"),
    )
    return converted, [row], []


def _convert_bands(bands: dict, equity: float) -> dict:
    """Divide every present band edge by the equity weight (the `total` basis divisor)."""
    out = {}
    for key, band in (bands or {}).items():
        if not isinstance(band, dict):
            continue
        converted = {}
        for edge in ("min", "max"):
            value = band.get(edge)
            if _is_number(value):
                converted[edge] = float(value) / equity
        out[key] = converted
    return out


# --------------------------------------------------------------------------
# S1 — band status and drift
# --------------------------------------------------------------------------

def band_status(current: float, policy: float,
                band_min: float | None, band_max: float | None,
                near_edge_fraction: float = NEAR_EDGE_FRACTION) -> str:
    """Classify a segment against its band. Evaluation order: breach, near-edge, inside.

    Geometry shares the S2 room quantities so S1 and S2 cannot disagree:
    `room_up = band_max - policy`, `room_down = policy - band_min`. The near-edge
    threshold is `near_edge_fraction` of the room on that side. `current` exactly
    at an edge gives distance 0 and therefore classifies near-edge, matching
    `parallax-conventions.md` §11.3 item 3: distance 0 is the most sensitive
    case, not a degenerate one.

    The order is binding. Breach runs first so a zero-width band
    (`policy == band_max`) cannot classify as near-edge while it is breaching.
    """
    if band_min is None and band_max is None:
        return "no_bands"
    if band_max is not None and current > band_max:
        return "breach_high"
    if band_min is not None and current < band_min:
        return "breach_low"
    if band_max is not None:
        room_up = band_max - policy
        if (band_max - current) <= near_edge_fraction * room_up:
            return "near_edge_high"
    if band_min is not None:
        room_down = policy - band_min
        if (current - band_min) <= near_edge_fraction * room_down:
            return "near_edge_low"
    return "inside"


def _distance_to_edge(current: float, band_min: float | None, band_max: float | None
                      ) -> float | None:
    edges = [e for e in (band_min, band_max) if e is not None]
    if not edges:
        return None
    return min(abs(current - e) for e in edges)


def _tilt_section(dimension: str, view_tilts: dict | None) -> dict:
    if not isinstance(view_tilts, dict):
        return {}
    section = view_tilts.get(_TILT_SECTION.get(dimension, dimension)) or {}
    return section if isinstance(section, dict) else {}


def _broad_bucket_tilts(dimension: str, key: str, section: dict) -> list[tuple[str, int]]:
    """(bucket, tilt) for every tilted broad bucket containing `key`, in map order.

    Only the `region` dimension has broad buckets; sectors and every other
    dimension inherit nothing.
    """
    if dimension != "region":
        return []
    return [(bucket, int(section[bucket]))
            for bucket, members in BROAD_REGION_MEMBERS.items()
            if key in members and _is_number(section.get(bucket))]


def ambiguous_broad_tilt(dimension: str, key: str, view_tilts: dict | None
                         ) -> list[tuple[str, int]] | None:
    """The conflicting (bucket, tilt) pairs when a key inherits DISAGREEING buckets.

    None when there is no ambiguity: the key carries its own tilt, no bucket
    contains it, or every containing bucket agrees.
    """
    section = _tilt_section(dimension, view_tilts)
    if _is_number(section.get(key)):
        return None
    candidates = _broad_bucket_tilts(dimension, key, section)
    if len({tilt for _, tilt in candidates}) > 1:
        return candidates
    return None


def resolve_tilt(dimension: str, key: str, view_tilts: dict | None) -> int:
    """Tilt for one policy segment, applying `loader.md` §3 broad-vs-specific precedence.

    A specific country key wins over a broad bucket for its members. A specific
    tilt and a broad tilt are never summed.

    A key can belong to more than one broad bucket (`india` is in both
    `apac_ex_japan` and `em_ex_china`). With no specific tilt: agreeing buckets
    inherit their shared tilt; disagreeing buckets resolve to 0 and `run_pipeline`
    discloses the collision as an `ambiguous_broad_tilt` row rather than picking
    a winner by map order.
    """
    section = _tilt_section(dimension, view_tilts)
    value = section.get(key)
    if _is_number(value):
        return int(value)
    candidates = _broad_bucket_tilts(dimension, key, section)
    if not candidates:
        return 0
    tilts = {tilt for _, tilt in candidates}
    return candidates[0][1] if len(tilts) == 1 else 0


def compute_drift(segments: list[Segment], current_exposures: dict,
                  view_tilts: dict) -> list[DriftRow]:
    """S1. drift = current - policy, band status, and passive/active breach attribution.

    A segment present in the policy but absent from the exposures reads
    `current = 0.0` and is rendered, not dropped. `breach_kind` is `active` when
    the status is a breach and the tilt is nonzero with the same sign as the
    drift; `passive` when the status is a breach and the tilt is zero or of the
    opposite sign; None otherwise.
    """
    rows: list[DriftRow] = []
    for segment in segments:
        dim_exposures = (current_exposures or {}).get(segment.dimension) or {}
        raw = dim_exposures.get(segment.key)
        current = float(raw) if _is_number(raw) else 0.0
        drift = current - segment.policy
        status = band_status(current, segment.policy, segment.band_min, segment.band_max)
        tilt = resolve_tilt(segment.dimension, segment.key, view_tilts)
        if status in ("breach_high", "breach_low"):
            same_sign = tilt != 0 and ((tilt > 0) == (drift > 0)) and drift != 0
            breach_kind = "active" if same_sign else "passive"
        else:
            breach_kind = None
        rows.append(DriftRow(
            dimension=segment.dimension,
            key=segment.key,
            current=current,
            policy=segment.policy,
            drift=drift,
            band_min=segment.band_min,
            band_max=segment.band_max,
            band_status=status,
            breach_kind=breach_kind,
            distance_to_edge=_distance_to_edge(current, segment.band_min, segment.band_max),
        ))
    return rows


# --------------------------------------------------------------------------
# S2 — sizing, budget, alignment
# --------------------------------------------------------------------------

def desired_active(tilt: int, k: float,
                   room_up: float | None, room_down: float | None) -> float | None:
    """(t/2) * k * room in the tilt direction. 0.0 at t == 0; None when that side has no band.

    Sign falls out of `t/2` because both rooms are non-negative. `room <= 0` is
    the capped case and returns 0.0.
    """
    if tilt == 0:
        return 0.0
    room = room_up if tilt > 0 else room_down
    if room is None:
        return None
    if room <= 0:
        return 0.0
    return (tilt / 2.0) * k * room


def apply_budget_cap(rows: list[TaaRow], max_total_tilt: float | None
                     ) -> tuple[list[TaaRow], float, bool]:
    """Scale every desired active by one common factor when the budget is exceeded.

    Ratios are preserved because the same scale is applied to every row. A None
    desired active is excluded from the sum and left unchanged.
    """
    total = sum(abs(r.desired_active) for r in rows if r.desired_active is not None)
    if max_total_tilt is None or total <= 0 or total <= max_total_tilt:
        return list(rows), 1.0, False
    scale = max_total_tilt / total
    scaled = [
        r if r.desired_active is None
        else replace(r, desired_active=r.desired_active * scale, budget_scale=scale)
        for r in rows
    ]
    return scaled, scale, True


def classify_alignment(current_active: float, desired_active: float | None,
                       tilt: int, room_in_dir: float | None) -> str:
    """Verdict for one TAA row. Enum is closed at five values."""
    if tilt == 0:
        return "no_view"
    if room_in_dir is None or desired_active is None:
        return "not_evaluable"
    if room_in_dir <= 0:
        return "capped_by_band"
    if current_active * desired_active > 0:
        return "aligned"
    return "opposed"


def _classify_alignment_fallback(current_active: float, tilt: int) -> str:
    """Ladder row 2 / dimension-fallback verdict: no room exists, so sign is all there is.

    Same order as `classify_alignment` with the room branches skipped:
    `desired_active` stays None and alignment comes from sign(current_active)
    against sign(tilt).
    """
    if tilt == 0:
        return "no_view"
    if current_active * tilt > 0:
        return "aligned"
    return "opposed"


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def _empty_result(tier: str, resolved_k: float, k_source: str, calibration: str,
                  errors: list[PolicyError], data_quality: list[DataQualityRow],
                  budget: dict, policy_hash: str,
                  coverage: dict | None = None) -> AdaptationResult:
    return AdaptationResult(
        fallback_tier=tier,
        resolved_k=resolved_k,
        k_source=k_source,
        calibration_status=calibration,
        near_edge_fraction=NEAR_EDGE_FRACTION,
        errors=errors,
        drift=[],
        taa=[],
        conflicts=[],
        data_quality=data_quality,
        coverage=dict(coverage or {}),
        budget=budget,
        policy_hash=policy_hash,
    )


def run_pipeline(policy: dict | None, exposures: dict | None,
                 view_tilts: dict | None, today: date | None = None) -> AdaptationResult:
    """S0-S2 orchestration plus fallback-ladder tier resolution.

    Tier resolution (pinned decision table):
      - no policy, a policy that is not a mapping, or any blocking validation
        error                                        -> `no_policy`, no rows
      - >= 1 covered dimension error-forced to fallback  -> `partial_dimensions`
      - >= 1 covered dimension, no covered segment banded -> `weights_only`
      - both dimensions covered, every segment two-sided  -> `full`
      - anything else                                  -> `partial_dimensions`

    A non-empty error-forced set forecloses both `weights_only` and `full`:
    `weights_only` asserts the policy carried no bands at all, which is a
    different statement from "the bands on file could not be read against a
    confirmed basis". Both fall to `partial_dimensions`, matching
    `policy-loader.md` §4 ladder row 4.

    "Covered" means the dimension exists under `sub_allocations.dimensions` with
    a non-empty `strategic_allocation`. An uncovered dimension is absent from
    `drift` and `taa` and appears as an `uncovered_dimension` disclosure.

    With no `exposures` payload there is nothing to compare the policy against,
    so `drift` and `taa` are empty; the tier still resolves from the policy
    structure and the outcome stays data-level (exit 0 at the CLI). An exposures
    payload that violates `validate_exposures` is treated the same way — the
    payload is dropped and every violation renders as an `invalid_exposures`
    disclosure, so an impossible input is never certified as a band verdict.
    """
    today = today or date.today()
    # Non-mapping payloads are data problems, never exceptions. A non-mapping
    # exposures payload reads as "no portfolio supplied"; the CLI grades it
    # more strictly (exit 2) because there it is an operator mistake.
    view_tilts = view_tilts if isinstance(view_tilts, dict) else {}
    if exposures is not None and not isinstance(exposures, dict):
        exposures = None

    exposure_violations: list[str] = []
    if exposures is not None:
        exposure_violations = validate_exposures(exposures)
        if exposure_violations:
            exposures = None
    coverage = {}
    if exposures is not None and isinstance(exposures.get("coverage"), dict):
        coverage = dict(exposures["coverage"])
    invalid_exposure_rows = [
        DataQualityRow(
            kind="invalid_exposures",
            detail=(f"{violation}. The exposures payload was rejected in full; drift, TAA, "
                    "and conflicts are not computed."),
        )
        for violation in exposure_violations
    ]

    if policy is None:
        return _empty_result("no_policy", DEFAULT_K, "default", CALIBRATION_STATUS,
                             [], invalid_exposure_rows,
                             _budget(0.0, None, False, 1.0), "", coverage)

    if not isinstance(policy, dict):
        # Parseable but not a mapping. `validate_policy` reports the blocking
        # failure; `policy_hash` stays empty because R-2 carries a digest only
        # when the policy parsed AS a mapping.
        return _empty_result("no_policy", DEFAULT_K, "default", CALIBRATION_STATUS,
                             validate_policy(policy), invalid_exposure_rows,
                             _budget(0.0, None, False, 1.0), "", coverage)

    errors = validate_policy(policy)
    policy_hash = compute_policy_hash(policy)
    resolved_k, k_source = resolve_k(policy)
    metadata = policy.get("metadata") or {}
    calibration = metadata.get("calibration_status") or CALIBRATION_STATUS

    if any(e.severity == "blocking" for e in errors):
        return _empty_result("no_policy", resolved_k, k_source, calibration,
                             errors, invalid_exposure_rows,
                             _budget(0.0, None, False, 1.0), policy_hash, coverage)

    data_quality: list[DataQualityRow] = list(invalid_exposure_rows)

    review_due = _parse_date(metadata.get("review_due"))
    if review_due is not None and today > review_due:
        data_quality.append(DataQualityRow(
            kind="stale_policy",
            detail=(f"policy review_due {review_due.isoformat()} has passed as of "
                    f"{today.isoformat()}; refresh with the RM. Never a block."),
        ))

    mandate = policy.get("mandate") or {}
    overlay = mandate.get("tactical_overlay") or {}
    max_tracking_error = overlay.get("max_tracking_error")
    if max_tracking_error is not None:
        data_quality.append(DataQualityRow(
            kind="te_budget_not_evaluated",
            detail=(f"max_tracking_error {max_tracking_error} is carried and validated but "
                    "NOT evaluated in Phase 1: there is no covariance input and no proxy."),
        ))

    forced_fallback = {e.dimension for e in errors
                       if e.severity == "dimension" and e.dimension}
    strategic = mandate.get("strategic_allocation") or {}
    equity = strategic.get(EQUITY_KEY)
    dimensions = ((mandate.get("sub_allocations") or {}).get("dimensions") or {})

    segments: list[Segment] = []
    covered: list[str] = []
    policy_keys: dict[str, set] = {}
    for dim_name in DIMENSIONS:
        dim = dimensions.get(dim_name)
        allocation = (dim or {}).get("strategic_allocation") or {} if isinstance(dim, dict) else {}
        if not isinstance(dim, dict) or not allocation:
            data_quality.append(DataQualityRow(
                kind="uncovered_dimension",
                detail=(f"{dim_name}: no strategic_allocation declared in the policy; "
                        "absent from drift and TAA."),
            ))
            continue
        covered.append(dim_name)
        if dim_name in forced_fallback:
            # The policy weight below is never converted to sleeve basis when
            # the basis itself could not be resolved, while `current` in the
            # drift row always comes from sleeve-basis exposures. `drift` and
            # `current_active` for this dimension's segments therefore compare
            # two potentially incompatible bases; disclose that rather than
            # let a numeric drift render as trustworthy as a confirmed-basis
            # segment's.
            data_quality.append(DataQualityRow(
                kind="basis_unconfirmed_drift",
                detail=(f"{dim_name}: basis could not be resolved, so policy weights were "
                        "never converted to sleeve basis; drift and TAA alignment for this "
                        "dimension's segments are not basis-comparable and TAA alignment "
                        "reports `not_evaluable`."),
            ))

        basis = dim.get("basis") if dim.get("basis") in ("sleeve", "total") else ""
        weights, conversion_rows, _ = normalize_to_sleeve(allocation, basis, equity)
        policy_keys[dim_name] = set(weights)
        data_quality.extend(conversion_rows)
        bands = dim.get("allocation_bands") or {}
        if basis == "total" and dim_name not in forced_fallback and _is_number(equity):
            bands = _convert_bands(bands, float(equity))

        code_list = dim.get("code_list")
        allowed = CODE_LISTS.get(code_list)
        for key, weight in weights.items():
            if allowed is not None and key not in allowed:
                data_quality.append(DataQualityRow(
                    kind="unknown_segment_key",
                    detail=(f"{dim_name}.{key}: not a member of code list '{code_list}'; "
                            "dropped from band math. Not a validation error."),
                ))
                continue
            band = bands.get(key) or {}
            band_min = float(band["min"]) if _is_number(band.get("min")) else None
            band_max = float(band["max"]) if _is_number(band.get("max")) else None
            if dim_name in forced_fallback:
                # The dimension's basis could not be resolved (missing `basis`,
                # or `basis: total` without a usable equity weight). Whatever
                # band edges are on file were declared against that unresolved
                # basis and must never be read against the (possibly
                # unconverted) weight below — that would render a band verdict
                # against a basis nobody confirmed. Segment assembly drops the
                # edges here so `band_status` reports `no_bands`, matching
                # ladder row 2 intent: `multiplier_fallback` rows carry drift
                # flags only, never a band comparison.
                band_min = None
                band_max = None
            if (band_min is None) != (band_max is None):
                missing = "max" if band_max is None else "min"
                data_quality.append(DataQualityRow(
                    kind="missing_bands",
                    detail=(f"{dim_name}.{key}: one-sided band, `{missing}` absent; that "
                            "direction has no room and is never inferred."),
                ))
            conflicting = ambiguous_broad_tilt(dim_name, key, view_tilts)
            if conflicting:
                pairs = ", ".join(f"{bucket} {tilt:+d}" for bucket, tilt in conflicting)
                data_quality.append(DataQualityRow(
                    kind="ambiguous_broad_tilt",
                    detail=(f"{dim_name}.{key}: inherits disagreeing broad-bucket tilts "
                            f"({pairs}) and carries no specific tilt; resolved to 0. Add a "
                            f"specific `{key}` tilt to the view to settle it."),
                ))
            segments.append(Segment(dim_name, key, float(weight), band_min, band_max))

    tier = _resolve_tier(covered, segments, forced_fallback)

    if exposures is None:
        return _empty_result(tier, resolved_k, k_source, calibration, errors,
                             data_quality,
                             _budget(0.0, overlay.get("max_total_tilt"), False, 1.0),
                             policy_hash, coverage)

    current_exposures = exposures.get("dimensions") or {}
    for entry in exposures.get("unmapped") or []:
        if not isinstance(entry, dict):
            continue
        dim_name = entry.get("dimension")
        data_quality.append(DataQualityRow(
            kind="unmapped_holding",
            detail=(f"{entry.get('symbol')} (weight {entry.get('weight')}) is excluded from "
                    f"the {dim_name} denominator; coverage[{dim_name}]="
                    f"{coverage.get(dim_name)}."),
        ))

    data_quality.extend(_off_policy_rows(covered, policy_keys, current_exposures))

    drift = compute_drift(segments, current_exposures, view_tilts)
    status_by_key = {(r.dimension, r.key): r.band_status for r in drift}

    overlay_enabled = overlay.get("enabled")
    overlay_enabled = True if overlay_enabled is None else bool(overlay_enabled)
    max_total_tilt = overlay.get("max_total_tilt")

    taa: list[TaaRow] = []
    if not overlay_enabled:
        budget = _budget(0.0, max_total_tilt, False, 1.0)
    else:
        for segment, drift_row in zip(segments, drift):
            tilt = resolve_tilt(segment.dimension, segment.key, view_tilts)
            current_active = drift_row.drift
            room_up = (segment.band_max - segment.policy) if segment.band_max is not None else None
            room_down = (segment.policy - segment.band_min) if segment.band_min is not None else None
            semantics = _segment_semantics(segment, tier, forced_fallback)
            if semantics == "multiplier_fallback":
                desired = None
                if segment.dimension in forced_fallback:
                    # Basis unresolved: current_active's sign is not trustworthy
                    # either (see basis_unconfirmed_drift above), so this must
                    # not fall through to a sign-based aligned/opposed verdict.
                    alignment = "no_view" if tilt == 0 else "not_evaluable"
                else:
                    alignment = _classify_alignment_fallback(current_active, tilt)
            else:
                desired = desired_active(tilt, resolved_k, room_up, room_down)
                room_in_dir = None if tilt == 0 else (room_up if tilt > 0 else room_down)
                alignment = classify_alignment(current_active, desired, tilt, room_in_dir)
            taa.append(TaaRow(
                dimension=segment.dimension,
                key=segment.key,
                tilt=tilt,
                current_active=current_active,
                room_up=room_up,
                room_down=room_down,
                desired_active=desired,
                budget_scale=1.0,
                semantics=semantics,
                alignment=alignment,
            ))

        if all(r.desired_active is None for r in taa):
            # Ladder row 2: nothing to scale, so the budget line degrades to a
            # sum-of-absolute-drift diagnostic against max_total_tilt.
            budget = _budget(sum(abs(r.current_active) for r in taa),
                             max_total_tilt, False, 1.0)
        else:
            taa, scale, cap_applied = apply_budget_cap(taa, max_total_tilt)
            budget = _budget(
                sum(abs(r.desired_active) for r in taa if r.desired_active is not None),
                max_total_tilt, cap_applied, scale)

    conflicts = _collect_conflicts(policy, exposures, view_tilts, segments, taa, status_by_key)
    data_quality.extend(_not_checkable_rows(policy, exposures, view_tilts))

    return AdaptationResult(
        fallback_tier=tier,
        resolved_k=resolved_k,
        k_source=k_source,
        calibration_status=calibration,
        near_edge_fraction=NEAR_EDGE_FRACTION,
        errors=errors,
        drift=drift,
        taa=taa,
        conflicts=conflicts,
        data_quality=data_quality,
        coverage=coverage,
        budget=budget,
        policy_hash=policy_hash,
    )


def _off_policy_rows(covered: list[str], policy_keys: dict[str, set],
                     current_exposures: dict) -> list[DataQualityRow]:
    """Disclose exposure weight sitting in segments the policy does not declare.

    Segment assembly iterates POLICY keys, so an exposure key absent from the
    policy contributes to no drift row and to no conflict — it simply vanishes.
    The rendered drift table then reads as a complete account of the sleeve when
    it is not. One row per dimension carrying off-policy weight.
    """
    rows: list[DataQualityRow] = []
    for dim_name in covered:
        weights = current_exposures.get(dim_name)
        if not isinstance(weights, dict):
            continue
        declared = policy_keys.get(dim_name, set())
        off = {k: float(v) for k, v in weights.items()
               if k not in declared and _is_number(v)}
        total = sum(off.values())
        if total <= SUM_TOLERANCE:
            continue
        named = ", ".join(f"{k} {off[k]}" for k in sorted(off))
        rows.append(DataQualityRow(
            kind="off_policy_exposure",
            detail=(f"{dim_name}: {total:.4f} of mapped exposure sits in segments the policy "
                    f"does not declare ({named}); absent from drift and TAA."),
        ))
    return rows


def _not_checkable_rows(policy: dict, exposures: dict,
                        view_tilts: dict) -> list[DataQualityRow]:
    """Disclose hard constraints the helper cannot classify or cannot fully match.

    An empty Conflicts table means "checked clean" only when no row from here is
    present. Two classes are disclosed:

      a. a view exclude entry that is neither a known region key, nor a known
         sector key, nor a holding symbol — a theme or category the helper has
         no field to match against;
      b. an ISIN-shaped `prohibited_products` entry while one or more holdings
         carry no `isin`, so the match ran on partial identifiers.

    Both are silent-miss classes, never precedence collisions, so they render in
    Policy Data Quality rather than as `conflicts[]` rows.
    """
    holdings = [h for h in ((exposures or {}).get("holdings") or []) if isinstance(h, dict)]
    if not holdings:
        # The exclude and prohibited checks never ran; §3's pinned contract says
        # absent `holdings` emits nothing at all for those two kinds.
        return []

    rows: list[DataQualityRow] = []
    symbols = {h["symbol"].lower() for h in holdings if isinstance(h.get("symbol"), str)}
    known_keys = REGION_KEYS | SECTOR_KEYS
    excludes = [e for e in ((view_tilts or {}).get("excludes") or []) if isinstance(e, str)]
    unclassifiable = [e for e in excludes
                      if e.lower() not in known_keys and e.lower() not in symbols]
    if unclassifiable:
        rows.append(DataQualityRow(
            kind="hard_constraint_not_checkable",
            detail=(f"view exclude entries {sorted(unclassifiable)} name neither a known "
                    "region key, a known sector key, nor a held symbol; this helper has no "
                    "field to match them against. They are enforced by the house-view flow "
                    "at skill level, not here. An empty Conflicts table does not clear them."),
        ))

    prohibited = [p for p in ((policy.get("mandate") or {}).get("prohibited_products") or [])
                  if isinstance(p, str)]
    isin_shaped = [p for p in prohibited if ISIN_PATTERN.match(p.strip().upper())]
    without_isin = [h.get("symbol") for h in holdings
                    if not isinstance(h.get("isin"), str) or not h["isin"].strip()]
    if isin_shaped and without_isin:
        rows.append(DataQualityRow(
            kind="hard_constraint_not_checkable",
            detail=(f"{len(isin_shaped)} prohibited entr"
                    f"{'y is' if len(isin_shaped) == 1 else 'ies are'} ISIN-shaped while "
                    f"{len(without_isin)} holding(s) carry no `isin` field; the prohibition "
                    "check ran on incomplete ISIN coverage and cannot clear those holdings."),
        ))
    return rows


def _resolve_tier(covered: list[str], segments: list[Segment],
                  forced_fallback: set) -> str:
    if not covered:
        return "partial_dimensions"
    if forced_fallback & set(covered):
        # A covered dimension forced to `multiplier_fallback` by a
        # dimension-scoped error is ladder row 4. `weights_only` would assert
        # the policy declared no bands at all, and `full` would assert every
        # covered segment is two-sided against a confirmed basis. Neither is
        # true here, so both rungs are foreclosed.
        return "partial_dimensions"
    usable = [s for s in segments if s.dimension not in forced_fallback]
    if not any(s.band_min is not None or s.band_max is not None for s in usable):
        return "weights_only"
    if (set(covered) == set(DIMENSIONS) and not forced_fallback
            and all(s.band_min is not None and s.band_max is not None for s in segments)):
        return "full"
    return "partial_dimensions"


def _segment_semantics(segment: Segment, tier: str, forced_fallback: set) -> str:
    if segment.dimension in forced_fallback:
        return "multiplier_fallback"
    if tier == "weights_only":
        return "multiplier_fallback"
    if segment.band_min is None and segment.band_max is None:
        return "multiplier_fallback"
    return "policy"


def _collect_conflicts(policy: dict, exposures: dict, view_tilts: dict,
                       segments: list[Segment], taa: list[TaaRow],
                       status_by_key: dict) -> list[Conflict]:
    """Guardrail 5. Emit rows for a human; never resolve, drop, or net out."""
    conflicts: list[Conflict] = []
    segment_by_key = {(s.dimension, s.key): s for s in segments}

    # tilt_vs_band. R-5 pinned exactly two triggers: no room in the tilt
    # direction, and a band already breached in the tilt direction.
    for row in taa:
        if row.tilt == 0 or row.semantics != "policy":
            continue
        segment = segment_by_key[(row.dimension, row.key)]
        room_in_dir = row.room_up if row.tilt > 0 else row.room_down
        reasons = []
        if room_in_dir is not None and room_in_dir <= 0:
            reasons.append("no room in the tilt direction")
        status = status_by_key.get((row.dimension, row.key))
        if (row.tilt > 0 and status == "breach_high") or (row.tilt < 0 and status == "breach_low"):
            reasons.append("band already breached in the tilt direction")
        if not reasons:
            continue
        conflicts.append(Conflict(kind="tilt_vs_band", detail={
            "dimension": row.dimension,
            "key": row.key,
            "tilt": row.tilt,
            "current": segment.policy + row.current_active,
            "policy": segment.policy,
            "band_min": segment.band_min,
            "band_max": segment.band_max,
            "desired_active": row.desired_active,
            # Display only: the policy-relative target expressed as an exposure.
            "projected_target": (segment.policy + row.desired_active
                                 if row.desired_active is not None else None),
            "reason": "; ".join(reasons),
        }))

    holdings = (exposures or {}).get("holdings")
    if not holdings:
        return conflicts

    excludes = [e for e in ((view_tilts or {}).get("excludes") or []) if isinstance(e, str)]
    exclude_set = {e.lower() for e in excludes}
    prohibited = [p for p in ((policy.get("mandate") or {}).get("prohibited_products") or [])
                  if isinstance(p, str)]
    prohibited_set = {p.strip().upper(): p for p in prohibited}

    for holding in holdings:
        if not isinstance(holding, dict):
            continue
        symbol = holding.get("symbol")
        for field in ("symbol", "region", "sector"):
            value = holding.get(field)
            if isinstance(value, str) and value.lower() in exclude_set:
                conflicts.append(Conflict(kind="exclude_vs_holding", detail={
                    "symbol": symbol,
                    "weight": holding.get("weight"),
                    "matched_on": field,
                    "exclude_entry": value,
                }))
        # A prohibition may name either identifier. Both sides normalize to
        # upper case; an absent `isin` simply does not match (and is disclosed
        # as `hard_constraint_not_checkable` when a prohibition is ISIN-shaped).
        for field in ("symbol", "isin"):
            value = holding.get(field)
            if not isinstance(value, str):
                continue
            entry = prohibited_set.get(value.strip().upper())
            if entry is None:
                continue
            conflicts.append(Conflict(kind="prohibited_vs_holding", detail={
                "symbol": symbol,
                "weight": holding.get("weight"),
                "matched_on": field,
                "prohibited_entry": entry,
            }))
    return conflicts


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _load_yaml(path: str) -> dict:
    with Path(path).open() as f:
        return yaml.safe_load(f) or {}


def _load_json(path: str) -> dict:
    with Path(path).open() as f:
        return json.load(f)


def _render_text(result: AdaptationResult) -> str:
    lines = [
        f"fallback_tier: {result.fallback_tier}",
        f"resolved_k: {result.resolved_k} ({result.k_source})",
        f"calibration_status: {result.calibration_status}",
        f"near_edge_fraction: {result.near_edge_fraction}",
        f"policy_hash: {result.policy_hash or '(none)'}",
        f"errors: {len(result.errors)}  drift rows: {len(result.drift)}  "
        f"taa rows: {len(result.taa)}  conflicts: {len(result.conflicts)}  "
        f"data quality: {len(result.data_quality)}",
    ]
    for row in result.drift:
        lines.append(f"  drift {row.dimension}.{row.key}: current={row.current:.4f} "
                     f"policy={row.policy:.4f} drift={row.drift:+.4f} [{row.band_status}]")
    for row in result.taa:
        desired = "n/a" if row.desired_active is None else f"{row.desired_active:+.4f}"
        lines.append(f"  taa   {row.dimension}.{row.key}: tilt={row.tilt:+d} "
                     f"desired_active={desired} {row.alignment} ({row.semantics})")
    for conflict in result.conflicts:
        lines.append(f"  conflict {conflict.kind}: {conflict.detail}")
    for row in result.data_quality:
        lines.append(f"  data quality {row.kind}: {row.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI: --policy <file> [--exposures <json>] [--view-tilts <json>] [--today ISO] [--json]"""
    parser = argparse.ArgumentParser(
        description="Client-policy S0-S2 adaptation helper (operator-agnostic).",
    )
    parser.add_argument("--policy", required=True, help="Client policy YAML file.")
    parser.add_argument("--exposures", default=None, help="Exposures JSON file.")
    parser.add_argument("--view-tilts", dest="view_tilts", default=None,
                        help="Collapsed view-tilts JSON file.")
    parser.add_argument("--today", default=None,
                        help="ISO date override; makes staleness deterministic.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    try:
        policy = _load_yaml(args.policy)
    except (OSError, yaml.YAMLError) as e:
        print(f"error: cannot read policy {args.policy}: {type(e).__name__}", file=sys.stderr)
        return 2

    # A payload that parses but is not a JSON object is an operator mistake (the
    # wrong file, or a bare array), so it is graded with the unparseable class.
    # The policy is different: there a parseable non-mapping is a DATA problem
    # and stays exit 0 with a blocking validation error.
    exposures = None
    if args.exposures:
        try:
            exposures = _load_json(args.exposures)
        except (OSError, ValueError) as e:
            print(f"error: cannot read exposures {args.exposures}: {type(e).__name__}",
                  file=sys.stderr)
            return 2
        if not isinstance(exposures, dict):
            print(f"error: exposures {args.exposures} must be a JSON object, got "
                  f"{type(exposures).__name__}", file=sys.stderr)
            return 2
        # Phase 1 accepts sleeve-relative exposures only (see the `--exposures`
        # payload schema above). An absent or non-"sleeve" `basis` is graded
        # with the operator-mistake class, same as a non-object payload: this
        # is never silently converted or assumed.
        exposures_basis = exposures.get("basis")
        if exposures_basis != "sleeve":
            print(f"error: exposures {args.exposures} must declare basis 'sleeve'; got "
                  f"{exposures_basis!r}. Phase 1 accepts sleeve-relative exposures only; "
                  "the producer converts before calling.", file=sys.stderr)
            return 2
        # The rest of the pinned contract. A payload the producer got wrong is
        # an operator mistake at the CLI, graded with the same class: the helper
        # must never certify an impossible exposure as a band verdict.
        violations = validate_exposures(exposures)
        if violations:
            print(f"error: exposures {args.exposures} violate the pinned payload contract:",
                  file=sys.stderr)
            for violation in violations:
                print(f"  - {violation}", file=sys.stderr)
            return 2

    view_tilts = None
    if args.view_tilts:
        try:
            view_tilts = _load_json(args.view_tilts)
        except (OSError, ValueError) as e:
            print(f"error: cannot read view tilts {args.view_tilts}: {type(e).__name__}",
                  file=sys.stderr)
            return 2
        if not isinstance(view_tilts, dict):
            print(f"error: view tilts {args.view_tilts} must be a JSON object, got "
                  f"{type(view_tilts).__name__}", file=sys.stderr)
            return 2

    today = None
    if args.today:
        today = _parse_date(args.today)
        if today is None:
            print("error: --today must be an ISO-8601 date", file=sys.stderr)
            return 2

    result = run_pipeline(policy, exposures, view_tilts, today=today)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(_render_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
