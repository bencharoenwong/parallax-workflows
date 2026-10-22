"""Drift severity classification for /parallax-judge-house-view.

Classifies a list of per-cell resolution states from
``stress.resolve_cell_state`` into a single drift severity bucket, with
sufficient details for the renderer / audit row to explain the verdict.

The thresholds are defined in notes/2026-05-24-house-view-v2-plan.md §3.1
Phase 3. They are intentionally coarse — the LLM-as-judge step
(``recommendation.py``) is where per-cell judgment happens. This module
only chooses one of three buckets for the report banner + audit summary.

Severity tiers
--------------
- ``drift_minor``    : < 20% of non-zero cells in DIVERGENT_{FRESH,STALE}
- ``drift_moderate`` : 20-50%
- ``drift_material`` : > 50%, OR any DIVERGENT_* on a pillar,
                       OR sign-flip on a macro_regime cell
- ``drift_breaking`` : reserved for future use; currently not emitted but
                       the schema lets a renderer surface it should we ever
                       wire a stricter tier.

Magnitude escalation (per v2 plan §3.1 Phase 3): any cell whose
``|cio_value - parallax_value| >= 3`` bumps severity one tier
(minor → moderate → material).

Backward compatibility note: ``drift_breaking`` is intentionally absent
from the active output set. ``loader.md §6.2`` reserves the slot
(``drift_breaking_count`` is part of the ``drift_summary`` object) so that
future tightening of thresholds does not require an audit-schema bump.
"""
from __future__ import annotations

from typing import Any

# Severity ladder (lowest → highest). Used by `_bump_tier`.
_SEVERITY_LADDER: list[str] = [
    "drift_minor",
    "drift_moderate",
    "drift_material",
    "drift_breaking",
]

# Magnitude threshold for one-tier escalation per v2 plan §3.1 Phase 3.
_MAGNITUDE_ESCALATION_THRESHOLD = 3

# Path-prefix predicates. Pillar and macro_regime cells get special-cased
# escalation rules per v2 plan §3.1 Phase 3.
_PILLAR_PREFIX = "tilts.pillars."
_MACRO_REGIME_PREFIX = "tilts.macro_regime."

# States that count as drift for severity purposes.
_DIVERGENT_STATES = {"DIVERGENT_FRESH", "DIVERGENT_STALE"}


def _is_sign_flip(cio_value: Any, parallax_value: Any) -> bool:
    """True iff both values are numeric and have opposite (strict) signs."""
    if not (isinstance(cio_value, (int, float)) and not isinstance(cio_value, bool)):
        return False
    if not (isinstance(parallax_value, (int, float)) and not isinstance(parallax_value, bool)):
        return False
    if cio_value == 0 or parallax_value == 0:
        return False
    return (cio_value > 0) != (parallax_value > 0)


def _bump_tier(current: str) -> str:
    """Move severity one rung up the ladder; clamp at the top."""
    try:
        idx = _SEVERITY_LADDER.index(current)
    except ValueError:
        return current
    return _SEVERITY_LADDER[min(idx + 1, len(_SEVERITY_LADDER) - 1)]


def _max_magnitude(resolutions: list[dict[str, Any]]) -> int:
    """Max absolute (cio - parallax) over all DIVERGENT_* numeric cells."""
    best = 0
    for r in resolutions:
        if r.get("state") not in _DIVERGENT_STATES:
            continue
        cio = r.get("cio_tilt")
        plx = r.get("parallax_view")
        if not isinstance(cio, (int, float)) or isinstance(cio, bool):
            continue
        if not isinstance(plx, (int, float)) or isinstance(plx, bool):
            continue
        diff = abs(int(cio) - int(plx)) if isinstance(cio, int) and isinstance(plx, int) else abs(cio - plx)
        if diff > best:
            best = int(diff)
    return best


def classify_severity(
    resolutions: list[dict[str, Any]],
    view_age_days: int,
    denominator: int,
) -> tuple[str, dict[str, Any]]:
    """Return ``(severity, details)``.

    Args:
        resolutions: Per-cell state dicts produced by the orchestrator from
            ``stress.resolve_cell_state`` calls. Each dict carries at minimum
            ``{state, dim, cio_tilt, parallax_view}``; optional ``market``.
        view_age_days: Staleness of the active view at judge time
            (currently informational — surfaced in the returned details).
        denominator: Count of non-zero tilts in the active view, per
            ``stress.enumerate_dimensions``.

    Returns:
        ``(severity, details)`` where ``severity`` is one of
        ``drift_minor | drift_moderate | drift_material`` and ``details``
        is a structured dict the renderer / audit row can use.
    """
    divergent_count = 0
    pillar_divergence = False
    macro_sign_flip = False
    sign_flip_cells: list[str] = []
    pillar_cells: list[str] = []

    for r in resolutions:
        state = r.get("state")
        if state not in _DIVERGENT_STATES:
            continue
        divergent_count += 1
        path = r.get("dim", "") or ""
        if path.startswith(_PILLAR_PREFIX):
            pillar_divergence = True
            pillar_cells.append(path)
        if path.startswith(_MACRO_REGIME_PREFIX) and _is_sign_flip(
            r.get("cio_tilt"), r.get("parallax_view")
        ):
            macro_sign_flip = True
            sign_flip_cells.append(path)

    pct = (divergent_count / denominator) if denominator > 0 else 0.0

    # Base tier from the percentage rule.
    if pct > 0.50:
        severity = "drift_material"
    elif pct >= 0.20:
        severity = "drift_moderate"
    else:
        severity = "drift_minor"

    # Categorical escalations: any pillar divergence OR macro-regime sign-flip
    # forces drift_material per v2 plan §3.1 Phase 3.
    if pillar_divergence or macro_sign_flip:
        severity = "drift_material"

    # Magnitude escalation: bumps one tier (minor→moderate→material).
    max_mag = _max_magnitude(resolutions)
    magnitude_escalated = False
    if max_mag >= _MAGNITUDE_ESCALATION_THRESHOLD and severity != "drift_material":
        severity = _bump_tier(severity)
        magnitude_escalated = True

    details = {
        "divergent_count": divergent_count,
        "denominator": denominator,
        "divergent_pct": round(pct, 4),
        "pillar_divergence": pillar_divergence,
        "pillar_cells": pillar_cells,
        "macro_sign_flip": macro_sign_flip,
        "macro_sign_flip_cells": sign_flip_cells,
        "max_magnitude": max_mag,
        "magnitude_escalated": magnitude_escalated,
        "view_age_days": view_age_days,
    }
    return severity, details


def summarize_states(resolutions: list[dict[str, Any]]) -> dict[str, int]:
    """Group per-cell states into the canonical ``drift_summary`` counts.

    Maps stress.resolve_cell_state output states into the loader.md §6.2
    ``drift_summary`` object shape:

    ``{aligned_count, drift_minor_count, drift_material_count,
       drift_breaking_count, parallax_silent_count, uncovered_count}``

    Note: ``drift_minor_count`` here is a per-cell tally (DIVERGENT_*
    cells), not a tier label. The overall severity tier is computed
    separately by ``classify_severity``. The loader spec uses the same
    field name in both contexts — this preserves audit compatibility.
    """
    counts = {
        "aligned_count": 0,
        "drift_minor_count": 0,
        "drift_material_count": 0,
        "drift_breaking_count": 0,
        "parallax_silent_count": 0,
        "uncovered_count": 0,
        "cio_silent_count": 0,
    }
    for r in resolutions:
        state = r.get("state")
        if state == "ALIGNED":
            counts["aligned_count"] += 1
        elif state in _DIVERGENT_STATES:
            # The per-cell tally is DIVERGENT_* — severity tier is global.
            counts["drift_minor_count"] += 1
        elif state == "PARALLAX_SILENT":
            counts["parallax_silent_count"] += 1
        elif state == "UNCOVERED":
            counts["uncovered_count"] += 1
        elif state == "CIO_SILENT":
            counts["cio_silent_count"] += 1
    return counts
