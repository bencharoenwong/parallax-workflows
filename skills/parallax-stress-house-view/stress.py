"""
Core logic for the House View Stress Test skill.
"""
import datetime
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import sys

import yaml

_HOUSE_VIEW_DIR = Path(__file__).resolve().parent.parent / "_parallax" / "house-view"
if str(_HOUSE_VIEW_DIR) not in sys.path:
    sys.path.insert(0, str(_HOUSE_VIEW_DIR))
import audit_chain  # noqa: E402

# Data Classes
@dataclass
class View:
    data: Dict[str, Any]
    view_hash: str
    view_path: Path
    audit_path: Path

@dataclass
class Rule:
    id: str
    description: str
    class_: Literal["hard_stop", "taste"]
    last_reviewed: datetime.date
    confidence: float
    pattern: Dict[str, Any]

@dataclass
class RuleResult:
    rule_id: str
    triggered: bool
    # rule_class carried explicitly so the renderer can pick HARD STOP vs TASTE
    # without string-matching rule IDs (which never contained "hard_stop").
    rule_class: Literal["hard_stop", "taste"] = "taste"
    evidence: List[str] = field(default_factory=list)
    downgraded_from_stale_config: bool = False

@dataclass
class FanOutCapExceeded(Exception):
    tilted_markets: List[str]
    message: str = "Tilted markets exceed the fan-out cap."

# Constants
STALE_THRESHOLD_DAYS = 30
FANOUT_CAP = 12
HOUSE_VIEW_DIR = Path(
    os.environ.get("PARALLAX_HOUSE_VIEW_DIR")
    or os.path.expanduser("~/.parallax/active-house-view")
)


# --- Canonical view_hash (per schema.yaml §"view_hash computation") ---
# Reference implementation lives in skills/_parallax/house-view/tests/test_view_hash.py;
# inlined here because no public module currently exposes it and we MUST not drift
# from the reference. Any change must coincide with a schema bump.
def _is_empty(v):
    # Guard required by schema.yaml §"view_hash computation" Rule 2:
    # `False == 0` and `isinstance(False, int)` are both True in Python; without
    # this guard a boolean tilt of False would be silently stripped from the
    # canonical hash body — diverging from any conforming implementation.
    if isinstance(v, bool):
        return False
    if v is None:
        return True
    if isinstance(v, (int, float)) and v == 0:
        return True
    return v == "" or v == [] or v == {}


def _strip_empty(obj):
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


def compute_view_hash(view_data: dict) -> str:
    """sha256 of canonical YAML of (tilts + excludes), empties stripped recursively."""
    body = {
        "tilts": _strip_empty(view_data.get("tilts", {})),
        "excludes": _strip_empty(view_data.get("excludes", []) or []),
    }
    canonical = yaml.safe_dump(
        body,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
        width=1_000_000,
        indent=2,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now_iso_z() -> str:
    """ISO 8601 UTC with `Z` suffix, per loader.md §6.1."""
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

# Helper functions for rule evaluation
def _get_nested(data: dict, path: str):
    keys = path.split('.')
    for key in keys:
        if isinstance(data, dict) and key in data:
            data = data[key]
        else:
            return None
    return data

def _evaluate_condition(value, condition):
    # Numeric comparison operators. Order matters: ">=" / "<=" must come before
    # ">" / "<" to avoid `>=` being parsed as `>` with the `=` left in the threshold.
    # float() parses both "1" and "0.6" (some rules use fractional thresholds).
    if isinstance(condition, str):
        if condition.startswith(">="):
            return value is not None and value >= float(condition[2:])
        if condition.startswith("<="):
            return value is not None and value <= float(condition[2:])
        if condition.startswith(">"):
            return value is not None and value > float(condition[1:])
        if condition.startswith("<"):
            return value is not None and value < float(condition[1:])
        if condition.startswith("contains:"):
            return value is not None and condition.split(":", 1)[1] in value
    return value == condition


State = Literal["ok", "PARALLAX_SILENT", "UNCOVERED", "UNREACHABLE"]


def classify_mcp_meta_state(
    response: dict | None,
    market: str,
    covered_markets: set,
) -> tuple[State, str]:
    """Classify the meta-state of one Parallax MCP response.

    Pure classifier — does NOT extract parallax_view content. Returns
    (state, summary). When state == "ok", caller (LLM orchestrator) does
    the prose→sign interpretation as today.
    """
    if market not in covered_markets:
        return "UNCOVERED", f"{market} not in Parallax macro coverage"
    if response is None:
        return "UNREACHABLE", "no response from MCP"
    if not isinstance(response, dict):
        return "UNREACHABLE", f"unexpected response type: {type(response).__name__}"
    if "success" not in response and "error" not in response:
        # Malformed shape: neither healthy nor error-flagged. Fail closed.
        return "UNREACHABLE", "malformed response shape (no `success`/`error`)"
    if response.get("success") is False:
        return "PARALLAX_SILENT", f"success=false: {response.get('error', 'unspecified')}"
    err = response.get("error")
    # Any non-None `error` flags a degraded response, regardless of `success`.
    # Production MCPs use diverse error vocabularies (permission_denied,
    # tool_not_found, internal_error, ...) — we cannot enumerate them.
    if err is not None:
        return "PARALLAX_SILENT", f"{err} on {market}"
    if response.get("success") is True:
        return "ok", f"healthy response for {market}"
    # Defensive fallthrough — response shape we don't recognize.
    return "UNREACHABLE", "unrecognized response shape"

# Core Functions
def load_active_view(view_dir: Path = HOUSE_VIEW_DIR) -> View:
    """Loads the active house view, computes its hash, and verifies the audit chain."""
    view_path = view_dir / "view.yaml"
    audit_path = view_dir / "audit.jsonl"

    if not view_path.exists():
        raise FileNotFoundError("No active house view found. Use /parallax-load-house-view to create one.")

    try:
        audit_chain.verify_chain(audit_path)
    except audit_chain.AuditChainError as e:
        raise ConnectionAbortedError(f"Audit chain is broken: {e}. Cannot proceed.")

    with open(view_path, "r", encoding="utf-8") as f:
        view_data = yaml.safe_load(f)

    view_hash = compute_view_hash(view_data)

    return View(data=view_data, view_hash=view_hash, view_path=view_path, audit_path=audit_path)

def enumerate_dimensions(view: View) -> Tuple[List[str], Dict[str, List[str]]]:
    """Enumerates non-zero dimensions and tilted markets from the view."""
    tilts = view.data.get("tilts", {})
    dimensions = []
    tilted_markets = []
    
    # Dotted paths carry the canonical `tilts.` prefix to match the load-house-view
    # `--why <tilt-path>` convention (see schema.yaml + loader.md).
    # Null guard: schema.yaml documents macro_regime sub-fields as nullable (e.g.
    # `rates: null`) and the loader treats null as "no view." `value != 0` is True
    # for None in Python, so we must screen None before the zero check.
    for category, values in tilts.items():
        if not isinstance(values, dict):
            continue
        for dim, value in values.items():
            if isinstance(value, dict):  # For styles
                for sub_dim, sub_value in value.items():
                    if sub_value is not None and sub_value != 0:
                        dimensions.append(f"tilts.{category}.{dim}.{sub_dim}")
            elif value is not None and value != 0:
                dimensions.append(f"tilts.{category}.{dim}")
                if category == "regions":
                    tilted_markets.append(dim)

    # Primary market fallback (TODO: infer from basis_statement per design doc
    # §"Premises" — defaulting to US until the heuristic lands).
    return dimensions, {"tilted": tilted_markets, "primary": "us"}

def evaluate_internal_rules(view: View, rules_path: Path) -> List[RuleResult]:
    """Evaluates internal consistency rules against the view."""
    with open(rules_path, "r") as f:
        rules_data = yaml.safe_load(f)
    
    rules = [Rule(
        id=r['id'],
        description=r['description'],
        class_=r['class'],
        last_reviewed=datetime.date.fromisoformat(r['last_reviewed']),
        confidence=r['confidence'],
        pattern=r['pattern']
    ) for r in rules_data]

    results = []
    for rule in rules:
        triggered = False
        evidence = []
        
        when_clause = rule.pattern.get('when', {})
        all_when_match = True
        for path, condition in when_clause.items():
            value = _get_nested(view.data, path)
            if value is None or not _evaluate_condition(value, condition):
                all_when_match = False
                break
            evidence.append(f"'{path}' is '{value}'")

        if not all_when_match:
            results.append(RuleResult(rule_id=rule.id, triggered=False))
            continue

        any_of_clause = rule.pattern.get('any_of')
        if any_of_clause:
            any_of_match = False
            for condition_group in any_of_clause:
                for path, condition in condition_group.items():
                    value = _get_nested(view.data, path)
                    if value is not None and _evaluate_condition(value, condition):
                        any_of_match = True
                        evidence.append(f"'{path}' is '{value}'")
                        break
                if any_of_match:
                    break
            if not any_of_match:
                results.append(RuleResult(rule_id=rule.id, triggered=False))
                continue
        
        triggered = True
        downgraded = (datetime.date.today() - rule.last_reviewed).days > 180 and rule.class_ == 'hard_stop'
        # Effective class after stale-config downgrade.
        effective_class = "taste" if downgraded else rule.class_
        results.append(RuleResult(
            rule_id=rule.id,
            triggered=True,
            rule_class=effective_class,
            evidence=evidence,
            downgraded_from_stale_config=downgraded
        ))
        
    return results

def compute_age_delta(cio_age_days: int, parallax_age_days: Optional[int]) -> str:
    """Computes the age delta classification."""
    if parallax_age_days is None:
        return "unverifiable"
    if cio_age_days <= STALE_THRESHOLD_DAYS and parallax_age_days <= STALE_THRESHOLD_DAYS:
        return "both_fresh"
    if cio_age_days > parallax_age_days + STALE_THRESHOLD_DAYS:
        return "stale"
    return "fresh"

def resolve_cell_state(
    cio_tilt: Any,
    parallax_view: Any,
    age_delta: str,
    *,
    market: Optional[str] = None,
    covered_markets: Optional[set] = None,
) -> str:
    """Resolves the state of a single (market, dimension) cell.

    UNCOVERED takes precedence when the market is outside Parallax's coverage
    (per list_macro_countries) — independent of whether the CIO has a view.
    Per design's 6-state table.
    """
    cio_has_view = cio_tilt is not None and cio_tilt != 0
    parallax_has_view = parallax_view is not None
    market_uncovered = (
        covered_markets is not None
        and market is not None
        and market not in covered_markets
    )

    if market_uncovered:
        return "UNCOVERED"

    if not cio_has_view:
        return "CIO_SILENT" if parallax_has_view else "UNCOVERED"

    if not parallax_has_view:
        return "PARALLAX_SILENT"

    # Accept int OR float on either side. yaml.safe_load gives ints for `1` but
    # MCP responses may carry numeric floats (e.g., `momentum: 1.0`). Treating
    # float-vs-int as DIVERGENT was a silent misclassification.
    aligned = (
        isinstance(cio_tilt, (int, float))
        and isinstance(parallax_view, (int, float))
        and (cio_tilt > 0) == (parallax_view > 0)
    )

    if aligned:
        return "ALIGNED"
    return "DIVERGENT_STALE" if age_delta == "stale" else "DIVERGENT_FRESH"

def enforce_fanout_cap(tilted_markets: List[str], cap: int = FANOUT_CAP) -> List[str]:
    """Enforces the fan-out cap on the number of markets to query."""
    if len(tilted_markets) > cap:
        raise FanOutCapExceeded(tilted_markets=tilted_markets)
    return tilted_markets

def build_recommended_deltas(
    resolutions: List[Dict[str, Any]],
    cio_age_days: int,
    parallax_age_days: int,
    include_fresh: bool = False,
) -> List[Dict[str, Any]]:
    """Turn DIVERGENT cell resolutions into a list of recommended deltas.

    v1 (default `include_fresh=False`) emits `kind="informational"` entries
    only for DIVERGENT_STALE cells — humans apply manually via
    /parallax-load-house-view. The structured shape is forward-compatible
    with a future `--apply-stress <audit-hash>` operational mode that would
    auto-populate a draft (Option B in the design doc).

    When `include_fresh=True` (used by the judge skill — see
    notes/2026-05-24-house-view-v2-plan.md §3.1 Phase 4), DIVERGENT_FRESH
    cells are ALSO emitted with `kind="informational_fresh"`. Structural
    fields are identical to stale deltas; only `kind` and the carried
    `stress_state` differ. Backward-compatible: existing callers that do
    not pass `include_fresh` see byte-identical output to today.

    `path` follows the load-house-view `--why <tilt-path>` convention
    (dotted, with `tilts.` prefix).
    """
    out = []
    for r in resolutions:
        state = r.get("state")
        if state == "DIVERGENT_STALE":
            kind = "informational"
        elif include_fresh and state == "DIVERGENT_FRESH":
            kind = "informational_fresh"
        else:
            continue
        dim = r.get("dim", "")
        if not dim:
            # Malformed resolution dict; skip rather than crash.
            continue
        out.append({
            "kind": kind,
            "path": dim if dim.startswith("tilts.") else f"tilts.{dim}",
            "market": r.get("market"),
            "cio_value": r.get("cio_tilt"),
            "parallax_signal": r.get("parallax_view"),
            "parallax_summary": r.get("parallax_summary", ""),
            "stress_state": state,
            "cio_age_days": cio_age_days,
            "parallax_age_days": parallax_age_days,
        })
    return out


def _load_schema_categories(schema_path: Path) -> dict:
    """Return {category: set(allowed_dims)} from schema.yaml's `tilts.*`.

    Re-parses on every call (sub-10ms; no module-level cache, per design).
    Raises yaml.YAMLError or OSError on read failure — caller handles.
    """
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = yaml.safe_load(f)
    tilts = schema.get("tilts", {}) or {}
    cats: dict = {}
    for cat_name, cat_body in tilts.items():
        if isinstance(cat_body, dict):
            cats[cat_name] = set(cat_body.keys())
        else:
            cats[cat_name] = set()
    return cats


# Factor aliases per schema.yaml documentation.
_FACTOR_ALIASES = {"quality": "profitability", "defensive": "low_volatility"}


def validate_recommended_deltas(
    deltas: list,
    schema_path: Path,
) -> tuple[bool, list]:
    """Validate recommended_deltas against schema.yaml.

    Returns (ok, errors). All-or-nothing: any failure → ok=False.
    On schema.yaml read failure, returns a sentinel error with
    index=None, field=None, reason=f"schema_unreadable: ..." so the
    caller maps to disposition="schema_unreadable".
    """
    try:
        categories = _load_schema_categories(schema_path)
    except (yaml.YAMLError, OSError) as exc:
        return False, [{
            "index": None,
            "field": None,
            "reason": f"schema_unreadable: {exc.__class__.__name__}: {exc}",
        }]
    errors: list = []
    for i, d in enumerate(deltas):
        path = d.get("path", "")
        if not isinstance(path, str) or not path.startswith("tilts."):
            errors.append({"index": i, "field": "path",
                           "reason": f"path must start with 'tilts.'; got {path!r}"})
            continue
        segments = path.split(".")
        if len(segments) < 3:
            errors.append({"index": i, "field": "path",
                           "reason": f"path needs at least 3 segments; got {path!r}"})
            continue
        _, category, dim = segments[0], segments[1], segments[2]
        if category not in categories:
            errors.append({"index": i, "field": "path",
                           "reason": f"unknown category {category!r}; known: {sorted(categories)}"})
            continue
        # Factor aliases (Plan #5): accept documented synonyms.
        canonical_dim = dim
        if category == "factors" and dim in _FACTOR_ALIASES:
            canonical_dim = _FACTOR_ALIASES[dim]
        # Styles special case (Plan #4): paths may have 4 segments
        # (tilts.styles.<sub>.<leaf>); validate the sub-category exists, then
        # skip the leaf-level dim check (deeper walk is v1-deferred). Do NOT
        # `continue` — kind/parallax_signal/market checks below must still run
        # for styles deltas.
        is_styles_4seg = category == "styles" and len(segments) == 4
        if is_styles_4seg:
            sub_cat = dim  # third segment is the styles sub-category
            if sub_cat not in categories["styles"]:
                errors.append({"index": i, "field": "path",
                               "reason": f"unknown styles sub-category {sub_cat!r}"})
        elif canonical_dim not in categories[category]:
            errors.append({"index": i, "field": "path",
                           "reason": f"unknown dim {dim!r} under {category}; "
                                     f"known: {sorted(categories[category])}"})
        # kind check
        kind = d.get("kind")
        if kind not in {"informational", "global", "informational_fresh"}:
            errors.append({"index": i, "field": "kind",
                           "reason": f"kind must be 'informational', 'global', or 'informational_fresh'; got {kind!r}"})
        # parallax_signal type strictness for informational deltas (decision 4d).
        # NOTE: deliberately NOT applied to "informational_fresh". A FRESH
        # divergence is an observation surfaced by the judge (not a strict
        # delta the stress skill emits), so it may carry richer non-numeric
        # signal payloads (e.g., regime tokens, summary strings). The judge's
        # citation validator is the relevant integrity gate for that path.
        if kind == "informational":
            sig = d.get("parallax_signal")
            if not (sig is None or isinstance(sig, (int, float))) or isinstance(sig, bool):
                errors.append({"index": i, "field": "parallax_signal",
                               "reason": f"informational parallax_signal must be int|float|None; "
                                         f"got {type(sig).__name__}: {sig!r}"})
        # market ↔ regions path correlation
        if category == "regions":
            market = d.get("market")
            if market is not None and market != dim:
                errors.append({"index": i, "field": "market",
                               "reason": f"market {market!r} must match regions path segment {dim!r}"})
    return (len(errors) == 0), errors


def append_stress_audit(
    view: View,
    summary: Dict[str, Any],
    applied: bool = False,
    disposition: Optional[str] = None,
    recommended_deltas: Optional[List[Dict[str, Any]]] = None,
    validation_errors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Appends a stress test entry to the audit log.

    Race-condition guard re-reads view.yaml and recomputes the canonical hash
    (covers tilts AND excludes, per schema.yaml). disposition is optional and
    captures hard-stop / completed / etc. on the audit row when set.

    recommended_deltas (optional, structured): forward-compatible payload for
    Option B (`load-house-view --apply-stress <audit-hash>`). When present,
    consumer skills can read this entry by hash and pre-populate a draft view.

    validation_errors (optional, structured): per loader.md §6.2, required
    when disposition is "validation_failed" or "schema_unreadable". Each
    entry is {index, field, reason}. Caller responsibility to pass when
    these dispositions apply — function does not infer.

    Returns the finalized audit entry (including prev_entry_hash and the
    schema_version default applied by audit_chain). Callers can pass the
    return value to `audit_chain.compute_entry_hash()` to get the
    `audit_hash_short` for the Phase 4-B citation in render_artifact.
    """
    with open(view.view_path, "r", encoding="utf-8") as f:
        current_data = yaml.safe_load(f)
    current_hash = compute_view_hash(current_data)

    if view.view_hash != current_hash:
        raise RuntimeError("View changed mid-run, please retry.")

    entry_data = {
        "ts": _now_iso_z(),
        "view_id": view.data["metadata"]["view_id"],
        "version_id": view.data["metadata"]["version_id"],
        "view_hash": view.view_hash,
        "skill": "parallax-stress-house-view",
        "action": "stress_test",
        "applied": applied,
        "stress_summary": summary,
    }
    if disposition is not None:
        entry_data["disposition"] = disposition
    if recommended_deltas is not None:
        entry_data["recommended_deltas"] = recommended_deltas
    if validation_errors is not None:
        entry_data["validation_errors"] = validation_errors
    return audit_chain.append_entry(view.audit_path, entry_data)
