"""Thin orchestrator over pillar_formulas.compute_*.

Returns a dict {pillar_letter: PillarResult} so the maker can package
the four pillars uniformly + compute an aggregate pillar confidence
for the GateContext.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from pillar_formulas import (  # noqa: E402
    PillarResult,
    compute_omega,
    compute_phi,
    compute_psi,
    compute_xi,
)


def compute_pillars(
    aggregated: dict[str, Any],
    telemetry: dict[str, Any] | None,
    inventory: dict[str, Any] | None = None,
    *,
    psychological_judge_fn: (
        Callable[[list[str], str | None], tuple[int, str, float]] | None
    ) = None,
) -> dict[str, PillarResult]:
    """Run all four compute_* in a documented order.

    Returns:
        {"omega": PillarResult, "phi": PillarResult,
         "xi": PillarResult, "psi": PillarResult}

    The letter keys match the schema-side pillar names:
        omega → tilts.pillars.econometrics_phase
        phi   → tilts.pillars.valuation_state
        xi    → tilts.pillars.market_entropy
        psi   → tilts.pillars.psychological_wavelength
    """
    return {
        "omega": compute_omega(aggregated, telemetry, inventory),
        "phi": compute_phi(aggregated, telemetry, inventory),
        "xi": compute_xi(aggregated, telemetry, inventory),
        "psi": compute_psi(
            aggregated,
            telemetry,
            inventory,
            psychological_judge_fn=psychological_judge_fn,
        ),
    }


def pillar_values_for_view(pillars: dict[str, PillarResult]) -> dict[str, int]:
    """Map compose output → schema field names for tilts.pillars."""
    return {
        "econometrics_phase": pillars["omega"].value,
        "valuation_state": pillars["phi"].value,
        "market_entropy": pillars["xi"].value,
        "psychological_wavelength": pillars["psi"].value,
    }


def pillar_confidence_average(pillars: dict[str, PillarResult]) -> float:
    """Mean confidence across all four pillars — for GateContext.confidence_map."""
    vals = [p.confidence for p in pillars.values()]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


__all__ = [
    "compute_pillars",
    "pillar_values_for_view",
    "pillar_confidence_average",
]
