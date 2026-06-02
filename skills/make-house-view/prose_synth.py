"""Deterministic YAML → markdown narrative.

The maker produces a Parallax-derived view that has no CIO source prose.
For schema parity with ingested views (paired prose.md), we synthesize a
short narrative from the aggregated tilts so the prose body always exists
and the paired_yaml_hash check stays meaningful.

Deliberately deterministic — no LLM call. The maker may later layer an
LLM narrative on top, but this module guarantees a baseline.
"""
from __future__ import annotations

from typing import Any


def _tilt_to_word(value: int) -> str:
    """Map integer tilt to a human word — used in narrative."""
    return {
        2: "strongly overweight",
        1: "overweight",
        0: "neutral",
        -1: "underweight",
        -2: "strongly underweight",
    }.get(value, "neutral")


def _pillar_to_phrase(name: str, value: int) -> str:
    if value == 0:
        return f"{name} reads as neutral"
    direction = {
        "econometrics_phase": "constructive" if value > 0 else "deteriorating",
        "valuation_state": "undervalued" if value > 0 else "stretched",
        "market_entropy": "orderly" if value > 0 else "disordered",
        "psychological_wavelength": "constructive sentiment" if value > 0 else "cautious sentiment",
    }.get(name, "skewed")
    magnitude = "moderately" if abs(value) == 1 else "strongly"
    return f"{name} reads as {magnitude} {direction}"


def render_prose(
    draft_view: dict[str, Any],
    fan_out_summary: dict[str, Any] | None = None,
    pillar_missing_inputs: dict[str, list[str]] | None = None,
) -> str:
    """Render a short markdown narrative for prose.md body.

    Body must NOT include the frontmatter — caller paginates with
    paired_yaml_hash / prose_body_hash / view_id / version_id at write time.
    """
    metadata = draft_view.get("metadata", {}) or {}
    tilts = draft_view.get("tilts", {}) or {}
    pillars = tilts.get("pillars", {}) or {}
    regions = {k: v for k, v in (tilts.get("regions") or {}).items() if v}
    sectors = {k: v for k, v in (tilts.get("sectors") or {}).items() if v}

    lines: list[str] = []
    lines.append(
        f"# {metadata.get('view_name', 'Parallax-synthesized house view')}"
    )
    lines.append("")
    lines.append(
        "*This view was synthesized deterministically from Parallax "
        "macro_analyst + telemetry MCP outputs by `/parallax-make-house-view`. "
        "It carries no CIO source prose.*"
    )
    lines.append("")

    # --- Pillars ---
    lines.append("## Pillars")
    pillar_lines: list[str] = []
    for name in (
        "econometrics_phase",
        "valuation_state",
        "market_entropy",
        "psychological_wavelength",
    ):
        v = int(pillars.get(name, 0) or 0)
        phrase = _pillar_to_phrase(name, v)
        pillar_lines.append(f"- **{name}** ({v:+d}) — {phrase}.")
        if pillar_missing_inputs and pillar_missing_inputs.get(name):
            missing = ", ".join(pillar_missing_inputs[name])
            pillar_lines.append(
                f"  - *Missing inputs:* {missing}. Pillar confidence reduced."
            )
    lines.extend(pillar_lines)
    lines.append("")

    # --- Regions ---
    if regions:
        lines.append("## Regions")
        for key, val in sorted(regions.items()):
            lines.append(f"- **{key}**: {_tilt_to_word(int(val))} ({val:+d}).")
        lines.append("")

    # --- Sectors ---
    if sectors:
        lines.append("## Sectors")
        for key, val in sorted(sectors.items()):
            lines.append(f"- **{key}**: {_tilt_to_word(int(val))} ({val:+d}).")
        lines.append("")

    # --- Fan-out summary ---
    if fan_out_summary:
        lines.append("## Synthesis provenance")
        lines.append(
            f"- Markets queried: {fan_out_summary.get('markets_total', 0)}"
        )
        lines.append(
            f"- Markets succeeded: {fan_out_summary.get('markets_succeeded', 0)}"
        )
        lines.append(
            f"- Markets unreachable: {fan_out_summary.get('markets_unreachable', 0)}"
        )
        if fan_out_summary.get("unreachable_markets"):
            unr = ", ".join(fan_out_summary["unreachable_markets"])
            lines.append(f"  - Unreachable: {unr}")
        lines.append("")

    lines.append(
        "*See `provenance.yaml` for per-leaf `generator_synthesis` entries "
        "with source_tools, composition_formula, and aggregator_weights_ref.*"
    )

    return "\n".join(lines) + "\n"


__all__ = ["render_prose"]
