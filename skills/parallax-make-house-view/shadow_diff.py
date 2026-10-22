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


# ---------------------------------------------------------------------------
# Compare mode (--compare): symmetric per-cell diff of two SAVED views.
#
# Distinct from shadow-diff: neither view is authoritative (no synthesis, no
# "bank is sovereign" framing). Reuses the symmetric diff_views core unchanged
# and re-reads its buckets with neutral semantics:
#   diff_views(left, right)["added"]     = present in RIGHT, silent in LEFT  -> right_only
#   diff_views(left, right)["bank_only"] = present in LEFT, silent in RIGHT  -> left_only
# Excludes are diffed separately (diff_excludes) because _flatten_tilts treats
# tilts.excludes as a single list-valued leaf, which is not a meaningful cell.
# ---------------------------------------------------------------------------


def _flatten_excludes(view: dict[str, Any] | None) -> set[str]:
    """Return the set of exclude identifiers for a view.

    Reads `tilts.excludes` (canonical per schema.yaml); falls back to a
    top-level `excludes` key (the location `_compute_view_hash` also tolerates).
    """
    view = view or {}
    tilts = view.get("tilts") or {}
    excludes = tilts.get("excludes")
    if excludes is None:
        excludes = view.get("excludes")
    if not isinstance(excludes, list):
        return set()
    return {str(x) for x in excludes}


def diff_excludes(
    left_view: dict[str, Any] | None, right_view: dict[str, Any] | None
) -> dict[str, list[str]]:
    """Symmetric diff of two views' exclude lists.

    Returns sorted lists keyed `common` / `left_only` / `right_only`.
    """
    left_set = _flatten_excludes(left_view)
    right_set = _flatten_excludes(right_view)
    return {
        "common": sorted(left_set & right_set),
        "left_only": sorted(left_set - right_set),
        "right_only": sorted(right_set - left_set),
    }


def _compare_display_name(
    view: dict[str, Any] | None, fallback_name: str | None, default: str
) -> str:
    meta = (view or {}).get("metadata")
    name = meta.get("view_name") if isinstance(meta, dict) else None
    return name or fallback_name or default


def _is_excludes_path(path: str) -> bool:
    """tilts.excludes is a list leaf from _flatten_tilts; diff_excludes owns it."""
    return path == "tilts.excludes" or path == "excludes"


def render_compare(
    left_view: dict[str, Any] | None,
    right_view: dict[str, Any] | None,
    *,
    left_name: str | None = None,
    right_name: str | None = None,
) -> str:
    """Render a NEUTRAL per-cell diff of two saved house views.

    Neither view is treated as authoritative. No synthesis, no pillar block,
    no "sovereign"/"additive" framing — this is a structural file diff. Tilts
    use symmetric left_only/right_only/agree/disagree buckets; excludes are a
    separate section.
    """
    left_display = _compare_display_name(left_view, left_name, "View A")
    right_display = _compare_display_name(right_view, right_name, "View B")

    tilt = diff_views(left_view or {}, right_view or {})

    def _without_excludes(bucket: dict[str, Any]) -> dict[str, Any]:
        return {p: v for p, v in bucket.items() if not _is_excludes_path(p)}

    agree = _without_excludes(tilt["agree"])
    disagree = _without_excludes(tilt["disagree"])
    right_only = _without_excludes(tilt["added"])  # present in RIGHT, silent in LEFT
    left_only = _without_excludes(tilt["bank_only"])  # present in LEFT, silent in RIGHT
    ex = diff_excludes(left_view, right_view)

    def _fmt(val: Any) -> str:
        return f"{val:+d}" if isinstance(val, int) else str(val)

    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"COMPARE — {left_display} (left) vs {right_display} (right)")
    lines.append("=" * 60)
    lines.append("")
    lines.append(
        "Per-cell diff of two saved house views. Neither view is authoritative."
    )
    lines.append("")
    lines.append(
        f"Left cells set: {len(left_only) + len(agree) + len(disagree)}   "
        f"Right cells set: {len(right_only) + len(agree) + len(disagree)}"
    )
    lines.append("")

    lines.append("--- AGREE (both views hold the same value) ---")
    if agree:
        for path, val in agree.items():
            lines.append(f"  = {path}: {_fmt(val)}")
    else:
        lines.append("  (no overlap)")
    lines.append("")

    lines.append(f"--- LEFT ONLY (held by {left_display}; right is silent) ---")
    if left_only:
        for path, val in left_only.items():
            lines.append(f"  L {path}: {_fmt(val)}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append(f"--- RIGHT ONLY (held by {right_display}; left is silent) ---")
    if right_only:
        for path, val in right_only.items():
            lines.append(f"  R {path}: {_fmt(val)}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("--- DISAGREE (both hold a value; they differ) ---")
    if disagree:
        for path, both in disagree.items():
            lines.append(f"  ≠ {path}: left={both['bank']}, right={both['synthesized']}")
    else:
        lines.append("  (no disagreements)")
    lines.append("")

    if ex["common"] or ex["left_only"] or ex["right_only"]:
        lines.append("--- EXCLUDES ---")
        lines.append(f"  both:       {', '.join(ex['common']) or '(none)'}")
        lines.append(f"  left only:  {', '.join(ex['left_only']) or '(none)'}")
        lines.append(f"  right only: {', '.join(ex['right_only']) or '(none)'}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


__all__ = [
    "diff_views",
    "render_shadow_diff",
    "diff_excludes",
    "render_compare",
]
