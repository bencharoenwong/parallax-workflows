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

# loader.md tilt table: "+2 (Big OW) ... Cap final exposure at 2x neutral to
# prevent runaway". Multipliers compound across sector, region and every
# matched theme, so the product exceeds this without an explicit cap.
#
# This is a HARD bound, not a target approached by iteration: weights_for_groups
# guarantees w[s] <= EXPOSURE_CAP * neutral[s] for every holding on return.
EXPOSURE_CAP = 2.0

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


def _tilt_mult(raw: Any) -> float:
    """Multiplier for a raw tilt value, degrading to neutral on anything that
    is not an exact integer in the table.

    `int(raw)` raised an uncaught ValueError on a non-numeric tilt, aborting an
    entire attribution run over one malformed cell in hand-edited view YAML.
    An unparseable or out-of-range tilt means "no instruction I can act on",
    which is 1.0 — the same neutral the table gives tilt 0.
    """
    # bool is an int in Python, so YAML `tech: yes` arrived as True and became
    # a +1 overweight. neutral_weights() in this same file already excludes bool
    # for the same reason; this now matches it.
    if isinstance(raw, bool):
        return 1.0
    if raw is None or raw == "":
        return 1.0
    # Only an exact integer is a tilt. int(2.9) truncated INTO range and
    # returned 1.50, and 1.5 vs the string "1.5" — the same authored value under
    # different YAML quoting — gave different multipliers.
    if isinstance(raw, int):
        return WEIGHT_MULT.get(raw, 1.0)
    if isinstance(raw, float):
        return WEIGHT_MULT.get(int(raw), 1.0) if raw.is_integer() else 1.0
    if isinstance(raw, str):
        try:
            return WEIGHT_MULT.get(int(raw.strip()), 1.0)
        except ValueError:
            return 1.0
    return 1.0


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
        out["sectors"][symbol] = _tilt_mult(sector_tilts.get(sector, 0)) if sector else 1.0
        out["regions"][symbol] = _tilt_mult(region_tilts.get(region, 0)) if region else 1.0
        theme_mult = 1.0
        for t in themes:
            theme_mult *= _tilt_mult(theme_tilts.get(t, 0))
        out["themes"][symbol] = theme_mult
    return out


def weights_for_groups(
    neutral_w: dict[str, float],
    group_mults: dict[str, dict[str, float]],
    active_groups: frozenset[str] | set[str],
) -> dict[str, float]:
    """Model-implied weights with only ``active_groups``' multipliers applied.

    The per-group multipliers COMPOUND — sector × region × every matched theme —
    so the product runs past what any single tilt authorises. loader.md's tilt
    table caps final exposure at 2× neutral "to prevent runaway", and that cap
    was missing here: a +2 sector with three +1 themes reached 2.93×, and a +2
    sector with a +2 theme reached 2.25×. The excess inflated model_active_bps
    and landed in selection_residual_bps with the opposite sign, distorting the
    verdict this skill exists to produce.

    Capping inside this function rather than at the call sites is deliberate:
    it is the single place the product is formed, so every Shapley coalition
    sees the same rule. The sum invariant is unaffected — Shapley efficiency
    holds for any value function, and this only changes what that function
    returns.

    THE GUARANTEE ON RETURN, for any ``neutral_w`` summing to 1 (the only kind
    this module builds): the weights sum to 1.0, and every holding with a
    positive neutral weight satisfies ``w[s] <= EXPOSURE_CAP * neutral[s]``.
    That is the loader.md contract stated exactly, and it is what the tests
    assert — no "usually", no dependence on a pass count. The bound is exact up
    to the absolute ``1e-12`` slack in the over-cap test below, which in ratio
    terms is ``1e-12 / neutral[s]``; that is ~4e-10 at the smallest neutral
    weight in the pinned fixtures, and only matters if neutral weights many
    orders of magnitude smaller are ever fed in.

    loader.md specifies no downside floor, so none is invented here; -2 tilts
    compound unbounded toward zero exactly as the table describes.
    """
    raw = {}
    for symbol, w in neutral_w.items():
        m = 1.0
        for g in active_groups:
            m *= group_mults.get(g, {}).get(symbol, 1.0)
        raw[symbol] = w * m
    total = sum(raw.values())
    if total <= 0:
        raise AttributionError("degenerate weights: multipliers zeroed the portfolio")
    weights = {s: v / total for s, v in raw.items()}

    # Cap FINAL exposure, not the raw multiplier. Clamping the multiplier before
    # normalisation does not bound what loader.md actually constrains: the ratio
    # that survives normalisation is m / mean(m), which grows without limit as
    # OTHER holdings' multipliers fall. Measured with a pre-normalisation cap of
    # 2.0: one holding still reached 3.37x neutral.
    #
    # Clamp, redistribute the excess across the holdings not yet capped, repeat.
    # The capped set is PERSISTENT: once a name is clamped it stays at exactly
    # EXPOSURE_CAP * neutral and never re-enters redistribution.
    #
    # That persistence is the whole fix. Recomputing the over-cap set from
    # scratch each pass excluded already-capped names — they sit at exactly the
    # cap, which the strict `>` test rejects — so they fell back into the free
    # set and redistribution lifted them over again. The result oscillated and
    # was non-monotone in the pass count: one reachable 5-holding view measured
    # 2.925x at one pass, 2.413x at two, 2.453x at three, and did not reach
    # 2.000x (to six decimals) until pass 28 — and never lands exactly on the
    # cap at all, still reading 2.000000000005 at pass 200. Convergence was geometric, so NO fixed pass count bounds
    # it: over 20,000 random portfolios the worst needed 70 passes under the
    # suite's own seed (20260818) and 124 under seed 4242. The figure is
    # seed-dependent, so treat it as "tens of passes, unbounded", not a
    # constant — that is the whole point.
    #
    # With the capped set persistent the loop is finite, not asymptotic: each
    # pass that does anything adds at least one name to the capped set, so it
    # settles in at most one pass per holding, landing exactly at the cap. The
    # free set can never empty while sum(neutral) == 1 — all names over the cap
    # would need sum(weights) > EXPOSURE_CAP — but the guard below keeps a
    # degenerate neutral from dividing by zero.
    #
    # DO NOT replace `len(weights) + 1` with a small constant. The bound has to
    # scale with the holding count: a 14-holding view built only from documented
    # tilt values needs SEVEN passes, so range(3), range(5) and range(6) all
    # leave a holding above the cap. That view is pinned in
    # test_the_redistribution_bound_scales_with_the_portfolio_not_a_constant.
    capped: set[str] = set()
    for _ in range(len(weights) + 1):
        newly = {s for s, w in weights.items()
                 if s not in capped and neutral_w[s] > 0
                 and w > EXPOSURE_CAP * neutral_w[s] + 1e-12}
        if not newly:
            break
        capped |= newly
        excess = sum(weights[s] - EXPOSURE_CAP * neutral_w[s] for s in newly)
        for s in newly:
            weights[s] = EXPOSURE_CAP * neutral_w[s]
        free = {s: w for s, w in weights.items() if s not in capped}
        free_total = sum(free.values())
        if free_total <= 0:
            break
        for s in free:
            weights[s] += excess * (free[s] / free_total)
    return weights


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
    dropped = [s for s in neutral if s not in returns]
    return {
        "active_return_bps": actual_bps,
        "model_active_bps": model_bps,
        "selection_residual_bps": actual_bps - model_bps,
        "per_tilt": per_tilt,
        "counterfactual_quality": quality,
        "holdings_covered": len(covered),
        "holdings_dropped": len(dropped),
        # Symbol lists for the merge step. They exist because counts cannot be
        # merged: the same holding appearing in three version segments was
        # counted three times.
        #
        # SORTED LISTS, not sets. SKILL.md Phase 5 writes per-segment detail
        # into report.json, and json.dumps raises on a set — the report would
        # have crashed on write. Deterministic order also keeps report bundles
        # diffable between runs.
        #
        # loader.md §6.3 forbids logging holdings arrays, so these must not
        # reach the AUDIT row. merge_segments emits counts only; report.json is
        # a local operator bundle and is not bound by that rule.
        "_covered_symbols": sorted(covered),
        "_dropped_symbols": sorted(dropped),
    }


def merge_segments(segment_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum per-segment evidence into the run-level attribution_summary body.

    ``counterfactual_quality`` degrades to "approximate" if ANY segment was
    approximate. Per-tilt contributions sum across segments (bps are
    additive under the arithmetic convention).

    Holdings do NOT sum. They are a set: a 3-holding portfolio spanning three
    version segments reported 9 covered holdings, which SKILL.md renders as
    "[C] holdings covered" — a wrong number in a client-facing report. Counts
    are taken over the union instead, and a holding covered in any segment is
    covered, not dropped, even if another segment lacked its price.

    Only the counts are returned. loader.md §6.3 forbids logging holdings
    arrays, and this return value is the audit-row payload.
    """
    if not segment_results:
        raise InsufficientProvenance("no segments to merge")
    per_tilt_totals = {g: 0.0 for g in GROUPS}
    total_active = 0.0
    total_model = 0.0
    covered_syms: set[str] = set()
    dropped_syms: set[str] = set()
    quality = "exact"
    for seg in segment_results:
        total_active += seg["active_return_bps"]
        total_model += seg["model_active_bps"]
        # A segment declaring a holdings count but carrying no symbol list
        # cannot be merged: the count is not additive, and defaulting to an
        # empty set silently reported 0 holdings covered for a run that had
        # some. SKILL.md invites hand-built segments and renders this figure
        # client-facing as "[C] holdings covered", so it must fail loudly
        # rather than under-report.
        if "_covered_symbols" not in seg and seg.get("holdings_covered"):
            raise AttributionError(
                "segment declares holdings_covered but carries no "
                "_covered_symbols; holdings are merged as a set, so the count "
                "alone cannot be combined. Build segments with "
                "attribute_segment()."
            )
        covered_syms |= set(seg.get("_covered_symbols") or ())
        dropped_syms |= set(seg.get("_dropped_symbols") or ())
        if seg["counterfactual_quality"] != "exact":
            quality = "approximate"
        for row in seg["per_tilt"]:
            per_tilt_totals[row["group"]] += row["realized_contribution_bps"]
    return {
        "segments": len(segment_results),
        # A holding covered in ANY segment is covered; only holdings never
        # priced in any segment count as dropped.
        "holdings_covered": len(covered_syms),
        "holdings_dropped": len(dropped_syms - covered_syms),
        "active_return_bps": total_active,
        "model_active_bps": total_model,
        "selection_residual_bps": total_active - total_model,
        "per_tilt": [
            {"group": g, "realized_contribution_bps": per_tilt_totals[g]} for g in GROUPS
        ],
        "counterfactual_quality": quality,
    }
