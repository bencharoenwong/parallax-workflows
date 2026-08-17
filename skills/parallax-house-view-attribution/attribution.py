"""Ex-post house-view attribution — pure math layer.

Backs `/parallax-house-view-attribution`. Measures whether an active (or
archived) house view added value over its effective window by reconstructing
the tilted-vs-neutral portfolio decision and attributing the return
difference to the view's tilt groups.

Reconstruction source is the REASONING-CHAIN archive, not the audit log:
loader.md §6.3 forbids logging holdings arrays, so `consume` rows carry no
weights — but `chain_emit` persists `final_portfolio.weights` (and the full
view) in `~/.parallax/reasoning-chains/<YYYY-MM>/<run_id>.yaml`. Chains are
the authoritative "what was actually built"; consume rows serve only as a
cross-check index.

Definitions (pinned so the number is falsifiable):
- **Neutral counterfactual** = the same holdings with every loader.md §3
  weight multiplier at 1.00x and no exclude effects — concretely,
  score-proportional weights over the chain's holdings when per-holding base
  scores are recoverable (`counterfactual_quality="exact"`), else
  equal-weight (`"approximate"`). Neutral is NOT a market benchmark.
- **Active return (bps)** = sum_i (w_tilted_i - w_neutral_i) * r_i * 10_000,
  with r_i the holding's period return over the segment window. Arithmetic
  first-order attribution — documented approximation, matching the repo's
  daily-contribution conventions at period granularity.
- **Per-tilt decomposition** = Shapley value over the tilt GROUPS
  (sectors / regions / themes) using the loader.md §3 multiplier table.
  Order-independent; sums exactly to the model-implied active return. The
  gap between the chain's ACTUAL weights and the model-implied tilted
  weights is reported separately as `selection_residual_bps` — universe
  effects, redundancy trims, and excludes live there, never silently folded
  into a tilt's contribution.

Read-only vs the view (like the judge): no writes here; the SKILL.md appends
the single `attribution` audit row and report bundle.

Pure stdlib + PyYAML. No MCP coupling — the consuming skill supplies
`returns` (from export_price_series) and `holding_meta` (sector/region/theme
classification from get_peer_snapshot / get_company_info).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CHAIN_DIR = Path.home() / ".parallax" / "reasoning-chains"

# loader.md §3 "Sector / region / theme tilts" weight multipliers.
WEIGHT_MULT = {-2: 0.50, -1: 0.75, 0: 1.00, 1: 1.25, 2: 1.50}

# Tilt groups the weight-effect decomposition covers. Factor tilts re-rank
# the composite (loader.md §3 factor table) rather than multiplying weights,
# and style tilts are universe filters — both fall into the selection
# residual by construction.
GROUPS = ("sectors", "regions", "themes")


class AttributionError(Exception):
    pass


class InsufficientProvenance(AttributionError):
    """No reasoning chains found for the view in the window."""


@dataclass
class Segment:
    version_id: str
    chains: list[dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------
# Chain loading / segmentation
# --------------------------------------------------------------------------

def load_window_chains(
    view_id: str,
    window_start: str,
    window_end: str,
    chain_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Load reasoning chains for ``view_id`` emitted within the window.

    ``window_start`` / ``window_end`` are ISO dates (inclusive). Chains that
    fail to parse, carry no view, or have empty weights are skipped — this
    walks an append-only archive that may contain non-portfolio chains
    (loader/judge runs emit dummy empty weights).
    """
    base = Path(chain_dir) if chain_dir is not None else DEFAULT_CHAIN_DIR
    if not base.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for month_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        for f in sorted(month_dir.glob("*.yaml")):
            try:
                chain = yaml.safe_load(f.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(chain, dict):
                continue
            view = chain.get("view") or {}
            meta = view.get("metadata") or {}
            if meta.get("view_id") != view_id:
                continue
            emitted = str(chain.get("emitted_at") or "")
            if not emitted:
                continue
            emitted_date = emitted[:10]
            if not (window_start <= emitted_date <= window_end):
                continue
            weights = ((chain.get("final_portfolio") or {}).get("weights")) or {}
            if not weights:
                continue
            out.append(chain)
    return out


def segment_by_version(chains: list[dict[str, Any]]) -> list[Segment]:
    """Group chains by the view ``version_id`` they were built against.

    A view superseded mid-window attributes per-segment; the caller sums
    segment results (`merge_segments`). Order follows first appearance by
    ``emitted_at``.
    """
    ordered = sorted(chains, key=lambda c: str(c.get("emitted_at") or ""))
    segments: dict[str, Segment] = {}
    for chain in ordered:
        vid = ((chain.get("view") or {}).get("metadata") or {}).get("version_id") or "unknown"
        segments.setdefault(vid, Segment(version_id=vid)).chains.append(chain)
    return list(segments.values())


# --------------------------------------------------------------------------
# Weights
# --------------------------------------------------------------------------

def reconstruct_tilted_weights(chain: dict[str, Any]) -> dict[str, float]:
    """The chain's realized weights — what was actually built."""
    weights = ((chain.get("final_portfolio") or {}).get("weights")) or {}
    return {str(k): float(v) for k, v in weights.items()}


def neutral_weights(chain: dict[str, Any]) -> tuple[dict[str, float], str]:
    """Neutral counterfactual weights + quality tag.

    Exact path: ``base_scores.response_inline`` carries a numeric per-holding
    score for every holding — neutral is score-proportional (all multipliers
    1.00x). Otherwise fall back to equal-weight over the same holdings and
    tag ``"approximate"`` (e.g. inline scores absent, or the response cache
    was pruned).
    """
    holdings = list(reconstruct_tilted_weights(chain).keys())
    if not holdings:
        raise AttributionError("chain has no holdings")
    inline = ((chain.get("base_scores") or {}).get("response_inline")) or {}
    scores: dict[str, float] = {}
    if isinstance(inline, dict):
        for h in holdings:
            v = inline.get(h)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                scores[h] = float(v)
    if len(scores) == len(holdings):
        total = sum(scores.values())
        return {h: scores[h] / total for h in holdings}, "exact"
    eq = 1.0 / len(holdings)
    return {h: eq for h in holdings}, "approximate"


def group_multipliers(
    view: dict[str, Any],
    holding_meta: dict[str, dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Per-group, per-holding weight multipliers from the view's tilts.

    ``holding_meta`` maps symbol -> {"sector": <schema key>, "region":
    <schema key>, "themes": [<schema keys>]} (classification supplied by the
    consuming skill from MCP metadata). Missing metadata means multiplier
    1.0 for that group — unclassifiable exposure lands in the residual, not
    in a fabricated tilt.
    """
    tilts = view.get("tilts") or {}
    sector_tilts = tilts.get("sectors") or {}
    region_tilts = tilts.get("regions") or {}
    theme_tilts = tilts.get("themes") or {}
    out: dict[str, dict[str, float]] = {g: {} for g in GROUPS}
    for symbol, meta in holding_meta.items():
        sector = meta.get("sector")
        region = meta.get("region")
        themes = meta.get("themes") or []
        out["sectors"][symbol] = WEIGHT_MULT.get(int(sector_tilts.get(sector, 0) or 0), 1.0) if sector else 1.0
        out["regions"][symbol] = WEIGHT_MULT.get(int(region_tilts.get(region, 0) or 0), 1.0) if region else 1.0
        theme_mult = 1.0
        for t in themes:
            theme_mult *= WEIGHT_MULT.get(int(theme_tilts.get(t, 0) or 0), 1.0)
        out["themes"][symbol] = theme_mult
    return out


def weights_for_groups(
    neutral_w: dict[str, float],
    group_mults: dict[str, dict[str, float]],
    active_groups: frozenset[str] | set[str],
) -> dict[str, float]:
    """Model-implied weights with only ``active_groups``' multipliers applied."""
    raw = {}
    for symbol, w in neutral_w.items():
        m = 1.0
        for g in active_groups:
            m *= group_mults.get(g, {}).get(symbol, 1.0)
        raw[symbol] = w * m
    total = sum(raw.values())
    if total <= 0:
        raise AttributionError("degenerate weights: multipliers zeroed the portfolio")
    return {s: v / total for s, v in raw.items()}


# --------------------------------------------------------------------------
# Returns / decomposition
# --------------------------------------------------------------------------

def active_return_bps(
    weights: dict[str, float],
    neutral_w: dict[str, float],
    returns: dict[str, float],
) -> float:
    """First-order active return of ``weights`` vs neutral, in bps.

    Symbols missing from ``returns`` are dropped from BOTH legs with weights
    renormalized over the covered set (mirrors loader.md §3b partial-result
    semantics); the caller reports the drop count.
    """
    covered = [s for s in neutral_w if s in returns]
    if not covered:
        raise AttributionError("no holdings have return data")
    nw_total = sum(neutral_w[s] for s in covered)
    w_total = sum(weights.get(s, 0.0) for s in covered)
    if nw_total <= 0 or w_total <= 0:
        raise AttributionError("degenerate coverage after dropping missing returns")
    active = 0.0
    for s in covered:
        dw = weights.get(s, 0.0) / w_total - neutral_w[s] / nw_total
        active += dw * returns[s]
    return active * 10_000.0


def shapley_tilt_attribution(
    neutral_w: dict[str, float],
    group_mults: dict[str, dict[str, float]],
    returns: dict[str, float],
) -> list[dict[str, Any]]:
    """Shapley decomposition of the model-implied active return over GROUPS.

    Exact enumeration (2^3 subsets). The Shapley values sum to the
    model-implied active return by construction — `test_attribution.py`
    asserts that invariant.
    """
    groups = [g for g in GROUPS if any(
        abs(m - 1.0) > 1e-12 for m in group_mults.get(g, {}).values()
    )]
    value_cache: dict[frozenset[str], float] = {}

    def value(subset: frozenset[str]) -> float:
        if subset not in value_cache:
            if not subset:
                value_cache[subset] = 0.0
            else:
                w = weights_for_groups(neutral_w, group_mults, subset)
                value_cache[subset] = active_return_bps(w, neutral_w, returns)
        return value_cache[subset]

    import math
    n = len(groups)
    result = []
    for g in GROUPS:
        if g not in groups:
            result.append({"group": g, "realized_contribution_bps": 0.0})
            continue
        others = [x for x in groups if x != g]
        shap = 0.0
        for k in range(len(others) + 1):
            for combo in itertools.combinations(others, k):
                s = frozenset(combo)
                weight = math.factorial(k) * math.factorial(n - k - 1) / math.factorial(n)
                shap += weight * (value(s | {g}) - value(s))
        result.append({"group": g, "realized_contribution_bps": shap})
    return result


def attribute_segment(
    chain: dict[str, Any],
    returns: dict[str, float],
    holding_meta: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Attribute one chain: neutral vs model-implied tilts vs actual weights.

    Returns the evidence block for this segment:
    ``{active_return_bps (actual), model_active_bps, selection_residual_bps,
    per_tilt, counterfactual_quality, holdings_covered, holdings_dropped}``.
    """
    view = chain.get("view") or {}
    tilted_actual = reconstruct_tilted_weights(chain)
    neutral, quality = neutral_weights(chain)
    mults = group_multipliers(view, holding_meta)

    actual_bps = active_return_bps(tilted_actual, neutral, returns)
    model_w = weights_for_groups(neutral, mults, frozenset(GROUPS))
    model_bps = active_return_bps(model_w, neutral, returns)
    per_tilt = shapley_tilt_attribution(neutral, mults, returns)

    covered = [s for s in neutral if s in returns]
    return {
        "active_return_bps": actual_bps,
        "model_active_bps": model_bps,
        "selection_residual_bps": actual_bps - model_bps,
        "per_tilt": per_tilt,
        "counterfactual_quality": quality,
        "holdings_covered": len(covered),
        "holdings_dropped": len(neutral) - len(covered),
    }


def merge_segments(segment_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum per-segment evidence into the run-level attribution_summary body.

    ``counterfactual_quality`` degrades to "approximate" if ANY segment was
    approximate. Per-tilt contributions sum across segments (bps are
    additive under the arithmetic convention).
    """
    if not segment_results:
        raise InsufficientProvenance("no segments to merge")
    per_tilt_totals = {g: 0.0 for g in GROUPS}
    total_active = 0.0
    total_model = 0.0
    covered = 0
    dropped = 0
    quality = "exact"
    for seg in segment_results:
        total_active += seg["active_return_bps"]
        total_model += seg["model_active_bps"]
        covered += seg["holdings_covered"]
        dropped += seg["holdings_dropped"]
        if seg["counterfactual_quality"] != "exact":
            quality = "approximate"
        for row in seg["per_tilt"]:
            per_tilt_totals[row["group"]] += row["realized_contribution_bps"]
    return {
        "segments": len(segment_results),
        "holdings_covered": covered,
        "holdings_dropped": dropped,
        "active_return_bps": total_active,
        "model_active_bps": total_model,
        "selection_residual_bps": total_active - total_model,
        "per_tilt": [
            {"group": g, "realized_contribution_bps": per_tilt_totals[g]} for g in GROUPS
        ],
        "counterfactual_quality": quality,
    }
