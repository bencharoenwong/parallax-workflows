"""Shadow-diff rendering for `--shadow-diff` mode.

The maker synthesizes a draft view but DOES NOT save it. Instead, it
diffs the synthesized draft against the currently-active bank view and
renders the differences with explicit ADDITIVE framing — the synthesis
is offered as data the bank could fold in, not as a replacement.

Distinct from `house-view-diff` (which compares portfolio outputs across
two consumer-skill runs). This is a per-cell tilt diff.
"""
from __future__ import annotations

from typing import Any


def _flatten_tilts(view: dict[str, Any]) -> dict[str, Any]:
    """Flatten the tilts subtree to dotted paths → value."""
    tilts = view.get("tilts") or {}
    out: dict[str, Any] = {}

    def _walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                _walk(f"{prefix}.{k}" if prefix else k, v)
        else:
            out[prefix] = node

    _walk("tilts", tilts)
    return out


def diff_views(
    bank_view: dict[str, Any] | None,
    synthesized: dict[str, Any],
) -> dict[str, Any]:
    """Per-cell diff. Returns:

        {
          "added":    {path: synthesized_value},
          "agree":    {path: value},
          "disagree": {path: {bank: ..., synthesized: ...}},
          "bank_only": {path: bank_value},  # synthesized silent
          "total_cells_synth": int,
          "total_cells_bank":  int,
        }

    "Added" means bank silent (0/None) AND synthesized non-zero — this is
    the additive surface, the most useful framing.
    """
    bank_flat = _flatten_tilts(bank_view or {})
    synth_flat = _flatten_tilts(synthesized or {})

    added: dict[str, Any] = {}
    agree: dict[str, Any] = {}
    disagree: dict[str, Any] = {}
    bank_only: dict[str, Any] = {}

    all_paths = set(bank_flat) | set(synth_flat)
    for path in sorted(all_paths):
        b = bank_flat.get(path)
        s = synth_flat.get(path)
        b_silent = b in (0, None)
        s_silent = s in (0, None)

        if b_silent and s_silent:
            continue
        if b_silent and not s_silent:
            added[path] = s
        elif s_silent and not b_silent:
            bank_only[path] = b
        elif b == s:
            agree[path] = b
        else:
            disagree[path] = {"bank": b, "synthesized": s}

    return {
        "added": added,
        "agree": agree,
        "disagree": disagree,
        "bank_only": bank_only,
        "total_cells_synth": sum(
            1 for v in synth_flat.values() if v not in (0, None)
        ),
        "total_cells_bank": sum(
            1 for v in bank_flat.values() if v not in (0, None)
        ),
    }


def render_shadow_diff(
    bank_view: dict[str, Any] | None,
    synthesized: dict[str, Any],
    *,
    pillars: dict[str, Any] | None = None,
) -> str:
    """Render an additive-framed text report of the shadow diff.

    The framing is critical: synthesis adds data points the bank could
    consider, not corrections. Bank's view is sovereign.
    """
    diff = diff_views(bank_view, synthesized)

    bank_name = (
        (bank_view or {}).get("metadata", {}).get("view_name", "active bank view")
    )

    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("SHADOW DIFF — Parallax synthesis vs active bank view")
    lines.append("=" * 60)
    lines.append("")
    lines.append(
        f"This is an ADDITIVE comparison. The bank's view ('{bank_name}') is "
        "sovereign — the synthesis below is data Parallax would offer in "
        "absence of a CIO take, NOT a recommendation to overwrite the bank's "
        "convictions. Use it to spot gaps, not to second-guess views the "
        "bank has explicitly held."
    )
    lines.append("")
    lines.append(
        f"Bank cells set: {diff['total_cells_bank']}   "
        f"Synthesis cells set: {diff['total_cells_synth']}"
    )
    lines.append("")

    lines.append("--- ADDITIVE (synthesis fills cells the bank is silent on) ---")
    if diff["added"]:
        for path, val in diff["added"].items():
            lines.append(f"  + {path}: {val:+d}" if isinstance(val, int) else f"  + {path}: {val}")
    else:
        lines.append("  (none — bank covers everything synthesis surfaces)")
    lines.append("")

    lines.append("--- AGREE (bank and synthesis say the same thing) ---")
    if diff["agree"]:
        for path, val in diff["agree"].items():
            lines.append(f"  = {path}: {val:+d}" if isinstance(val, int) else f"  = {path}: {val}")
    else:
        lines.append("  (no overlap)")
    lines.append("")

    lines.append("--- DISAGREE (bank held a view; synthesis differs) ---")
    if diff["disagree"]:
        for path, both in diff["disagree"].items():
            b, s = both["bank"], both["synthesized"]
            lines.append(
                f"  ≠ {path}: bank={b}, synthesis={s}  "
                "(informational only — bank's view stands)"
            )
    else:
        lines.append("  (no disagreements)")
    lines.append("")

    if pillars:
        lines.append("--- PILLAR CONFIDENCE ---")
        for letter in ("omega", "phi", "xi", "psi"):
            p = pillars.get(letter)
            if p is None:
                continue
            missing = ", ".join(p.missing_inputs) if p.missing_inputs else "—"
            lines.append(
                f"  {letter.upper()}: value={p.value:+d}  "
                f"confidence={p.confidence:.2f}  missing={missing}"
            )
        lines.append("")

    lines.append("=" * 60)
    lines.append(
        "No save performed. Re-run without `--shadow-diff` to route this "
        "synthesis through the confirmation gate."
    )
    lines.append("=" * 60)

    return "\n".join(lines)


__all__ = ["diff_views", "render_shadow_diff"]
