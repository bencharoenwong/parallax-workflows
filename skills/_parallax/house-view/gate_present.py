"""Shared confirmation gate for House View ingest and synthesis flows.

The confirmation gate is the load-bearing seam where extracted/synthesized
draft YAML meets the uploader (ingest) or the maker operator (synthesis).
Both paths share the same display structure and disposition loop — only the
labels and disposition vocabulary differ.

This module owns:
- The `GateContext` config object that distinguishes ingest vs maker mode
- The `GateResult` return shape carried back to the caller
- `run_gate_loop()` — display rendering + disposition branching

This module deliberately does NOT own:
- AskUserQuestion invocation (it's a Claude tool, not a Python lib).
  Instead, `run_gate_loop` returns a structured `GatePrompt` and accepts a
  `dispose_fn` callback the caller uses to resolve disposition via its own
  AskUserQuestion call. Same pattern used by gap_detect / gap_suggest.
- Audit-row writes (the caller is responsible for `extraction_attempt`
  audit entries per loader.md §6.1; see SKILL.md Step 3b).
- Pre-edit snapshot persistence (the caller writes `pre_edit.yaml` to
  `.archive/...`; this module just returns the pristine draft alongside
  the edited one in `GateResult.pre_edit_snapshot`).

The split keeps audit / provenance semantics in the caller and the gate
purely a display + disposition concern, per v2 plan §6.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


LOW_CONFIDENCE_THRESHOLD = 0.6


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateContext:
    """Configuration for one confirmation-gate invocation.

    Attributes:
        source_label: Free-form source attribution.
            ingest: filename / URL / "wizard".
            maker:  e.g. "Parallax synthesis 2026-05-24T...".
        uploader_present: True for ingest (human uploader edits / confirms),
            False for maker (synthetic source; same gate but different
            framing — "Generated from:" + synthesis verb tense).
        confidence_map: Per-category confidence (NOT per-field). Categories
            are top-level tilts keys: sectors, regions, factors, macro_regime,
            pillars, styles, themes.

            BUG-005: maker extends this with a "pillars" key whose value is
            avg(Ω, Φ, Ξ, Ψ confidences). The ingest path may omit "pillars".
            The gate renders whatever keys are present in the LOW-CONFIDENCE
            block.
        extraction_attempt_action: True for both ingest and maker — both log
            action="extraction_attempt" rows on disposition changes per
            loader.md §6.1. Reserved for caller use; the gate does not act
            on this directly but surfaces it through GateResult so the
            caller can branch on the correct audit action.
        disposition_options: Ordered list of dispositions the gate offers.
            ingest: ["confirm", "edit", "re_extract", "reject"]
            maker:  ["confirm", "edit", "regenerate", "abandon"]
    """

    source_label: str
    uploader_present: bool
    confidence_map: dict[str, float]
    extraction_attempt_action: bool
    disposition_options: list[str]


@dataclass(frozen=True)
class GateResult:
    """What `run_gate_loop` returns to the caller.

    Attributes:
        disposition: The final landing one of:
            ingest: "confirm" | "edited" | "re_extracted" | "rejected"
            maker:  "confirm" | "edited" | "regenerated" | "abandoned"
            (Note: "confirm" stays singular; "edited"/"re_extracted"/etc.
            are past-tense because they describe what happened in the loop.)
        final_draft: Post-edit dict if disposition == "edited"; pristine
            dict if disposition == "confirm"; None for re_extracted /
            rejected / regenerated / abandoned (caller re-runs or aborts).
        pre_edit_snapshot: Populated ONLY when disposition == "edited"
            (per SKILL.md Step 3a). Used by the caller to compute the
            extraction_attempt audit row's draft_yaml_hash over the
            pristine pre-edit YAML.
        edit_notes: Optional one-liner from the uploader about what they
            changed. Populated only when the uploader provided one during
            the edit path.
    """

    disposition: str
    final_draft: dict | None
    pre_edit_snapshot: dict | None = None
    edit_notes: str | None = None


@dataclass(frozen=True)
class GatePrompt:
    """Structured prompt the caller renders via AskUserQuestion.

    The gate module never calls AskUserQuestion directly — it returns this
    object and lets the caller resolve disposition. The caller then passes
    the chosen disposition back through `dispose_fn` (see `run_gate_loop`).

    Attributes:
        display: The pre-rendered bordered draft block (multi-line string).
            Print as-is before invoking AskUserQuestion.
        question: The header question to show with the radio options.
        options: Ordered (label, description) pairs for AskUserQuestion.
            label is the disposition key (matches context.disposition_options).
    """

    display: str
    question: str
    options: list[tuple[str, str]]


# ---------------------------------------------------------------------------
# Display rendering
# ---------------------------------------------------------------------------


def _flag_low_confidence(confidence_map: dict[str, float]) -> list[tuple[str, float]]:
    """Return list of (category, confidence) for categories below threshold."""
    return sorted(
        ((k, v) for k, v in confidence_map.items() if v is not None and v < LOW_CONFIDENCE_THRESHOLD),
        key=lambda kv: kv[1],
    )


def _avg_confidence(confidence_map: dict[str, float]) -> float | None:
    """Mean of all non-None confidence values, or None if map is empty."""
    vals = [v for v in confidence_map.values() if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _lowest_confidence(confidence_map: dict[str, float]) -> tuple[str, float] | None:
    """(category, confidence) of the lowest entry, or None if empty."""
    vals = [(k, v) for k, v in confidence_map.items() if v is not None]
    if not vals:
        return None
    return min(vals, key=lambda kv: kv[1])


def _format_tilts_block(tilts: dict[str, Any]) -> list[str]:
    """Render only non-zero tilts, grouped by top-level category."""
    lines = []
    for category in ("sectors", "regions", "factors", "styles", "themes"):
        sub = tilts.get(category) or {}
        nonzero = {k: v for k, v in sub.items() if v not in (0, None)}
        if nonzero:
            pairs = ", ".join(f"{k}: {v:+d}" if isinstance(v, int) else f"{k}: {v}" for k, v in nonzero.items())
            lines.append(f"{category:18s}{pairs}")
    excludes = tilts.get("excludes") or []
    if excludes:
        lines.append(f"{'excludes':18s}{len(excludes)} entries")
    return lines


def _render_gate_display(draft: dict, context: GateContext) -> str:
    """Render the bordered HOUSE VIEW — DRAFT FOR CONFIRMATION block.

    Both ingest and maker share the structure; only the source-attribution
    line, the framing verb, and the disposition vocabulary differ.
    """
    metadata = draft.get("metadata", {}) or {}
    tilts = draft.get("tilts", {}) or {}
    extraction = draft.get("extraction", {}) or {}
    macro_regime = tilts.get("macro_regime", {}) or {}
    pillars = tilts.get("pillars", {}) or {}

    if context.uploader_present:
        source_line = f"Source: {context.source_label}"
        framing = "we extracted"
        header = "HOUSE VIEW — DRAFT FOR CONFIRMATION"
    else:
        source_line = f"Generated from: {context.source_label}"
        framing = "we synthesized"
        header = "HOUSE VIEW — SYNTHESIZED DRAFT FOR CONFIRMATION"

    avg = _avg_confidence(context.confidence_map)
    lowest = _lowest_confidence(context.confidence_map)
    if avg is not None and lowest is not None:
        conf_line = (
            f"Extraction confidence: avg {avg:.2f}, "
            f"lowest {lowest[0]}: {lowest[1]:.2f}"
        )
    else:
        conf_line = "Extraction confidence: (none reported)"

    lines = [
        "=" * 60,
        header,
        "=" * 60,
        "",
        source_line,
        conf_line,
        "",
        "--- METADATA ---",
        f"view_name:        {metadata.get('view_name', '<unset>')}",
        f"uploader_role:    {metadata.get('uploader_role', '<unset>')}",
        f"effective_date:   {metadata.get('effective_date', '<unset>')}",
        f"valid_through:    {metadata.get('valid_through', '<computed>')}",
        f"basis_statement:  {(metadata.get('basis_statement') or '')[:200]}",
        "",
        "--- PILLARS (quantum-factor decomposition) ---",
        f"Ω econometrics_phase:        {pillars.get('econometrics_phase', 0)}",
        f"Φ valuation_state:           {pillars.get('valuation_state', 0)}",
        f"Ξ market_entropy:            {pillars.get('market_entropy', 0)}",
        f"Ψ psychological_wavelength:  {pillars.get('psychological_wavelength', 0)}",
        "",
        "--- TILTS (only non-zero shown) ---",
    ]
    tilt_lines = _format_tilts_block(tilts)
    lines.extend(tilt_lines if tilt_lines else ["(no non-zero tilts)"])

    dropped = extraction.get("dropped_cross_asset") or []
    lines += [
        "",
        "--- DROPPED (out of scope: cross-asset views) ---",
        ("\n".join(f"- {d}" for d in dropped) if dropped else "none"),
    ]

    lines += [
        "",
        "--- MACRO REGIME ---",
        (
            f"growth: {macro_regime.get('growth')}   "
            f"inflation: {macro_regime.get('inflation')}   "
            f"rates: {macro_regime.get('rates')}   "
            f"risk_appetite: {macro_regime.get('risk_appetite')}"
        ),
    ]
    implied = extraction.get("implied_factor_tilts")
    if implied:
        lines.append(f"Implied factor tilts (override at confirmation if needed): {implied}")

    low_conf = _flag_low_confidence(context.confidence_map)
    lines += ["", "--- LOW-CONFIDENCE FIELDS (< 0.6) ---"]
    if low_conf:
        notes = extraction.get("extraction_notes", "") or ""
        for cat, conf in low_conf:
            note = f" — {notes}" if cat in notes else ""
            lines.append(f"  {cat}: {conf:.2f}{note}")
    else:
        lines.append("  (none)")

    variance = extraction.get("tilt_variance")
    if variance is not None:
        warn = "  [WARN if < 0.5]" if variance < 0.5 else ""
        lines += ["", "--- DEGENERATE-VIEW CHECK ---", f"tilt_variance: {variance:.2f}{warn}"]

    lines += [
        "",
        f"({framing} the above from {context.source_label})",
        "=" * 60,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Disposition vocabulary
# ---------------------------------------------------------------------------


# Maps a context's disposition option keyword to (verb-for-result,
# human-readable description) for the AskUserQuestion prompt.
_INGEST_DESCRIPTIONS = {
    "confirm": "Confirm and save the extraction as-is",
    "edit": "Edit specific fields before saving",
    "re_extract": "Re-extract with a hint to improve quality",
    "reject": "Abandon this ingest, no save",
}
_MAKER_DESCRIPTIONS = {
    "confirm": "Confirm and ship the synthesized view as-is",
    "edit": "Edit specific fields before shipping",
    "regenerate": "Regenerate from source with a hint",
    "abandon": "Abandon this synthesis, no ship",
}

# Map raw disposition keyword to the past-tense form stored in GateResult.
_RESULT_DISPOSITION = {
    "confirm": "confirm",
    "edit": "edited",
    "re_extract": "re_extracted",
    "reject": "rejected",
    "regenerate": "regenerated",
    "abandon": "abandoned",
}


def _option_descriptions(context: GateContext) -> list[tuple[str, str]]:
    table = _INGEST_DESCRIPTIONS if context.uploader_present else _MAKER_DESCRIPTIONS
    return [(opt, table.get(opt, opt)) for opt in context.disposition_options]


# ---------------------------------------------------------------------------
# Loop orchestration
# ---------------------------------------------------------------------------


def build_prompt(draft: dict, context: GateContext) -> GatePrompt:
    """Public helper: build the GatePrompt without running the loop.

    Callers that prefer to drive the loop themselves (e.g., in a Claude
    skill where AskUserQuestion is the natural disposition resolver) can
    use this to render the display + options, then handle disposition
    themselves and pass the result to `apply_disposition`.
    """
    framing = "confirm" if context.uploader_present else "ship"
    return GatePrompt(
        display=_render_gate_display(draft, context),
        question=f"How do you want to {framing} this draft?",
        options=_option_descriptions(context),
    )


def apply_disposition(
    draft: dict,
    context: GateContext,
    disposition: str,
    *,
    edited_draft: dict | None = None,
    edit_notes: str | None = None,
) -> GateResult:
    """Map a chosen disposition keyword to a GateResult.

    The caller is responsible for actually collecting edits (via its own
    AskUserQuestion loop on flagged fields) and passing the edited draft
    back as `edited_draft`. This function just packages the result.

    Args:
        draft: The pristine pre-edit draft.
        context: The GateContext that produced the prompt.
        disposition: One of `context.disposition_options`.
        edited_draft: Required iff disposition == "edit". The post-edit draft.
        edit_notes: Optional uploader-supplied one-liner about edits.
    """
    if disposition not in context.disposition_options:
        raise ValueError(
            f"disposition {disposition!r} not in context.disposition_options "
            f"{context.disposition_options!r}"
        )

    result_disposition = _RESULT_DISPOSITION.get(disposition, disposition)

    if disposition == "confirm":
        return GateResult(
            disposition=result_disposition,
            final_draft=draft,
            pre_edit_snapshot=None,
            edit_notes=None,
        )
    if disposition == "edit":
        if edited_draft is None:
            raise ValueError(
                "apply_disposition(disposition='edit') requires edited_draft"
            )
        return GateResult(
            disposition=result_disposition,
            final_draft=edited_draft,
            pre_edit_snapshot=draft,
            edit_notes=edit_notes,
        )
    # re_extract / reject / regenerate / abandon all return no final draft.
    return GateResult(
        disposition=result_disposition,
        final_draft=None,
        pre_edit_snapshot=None,
        edit_notes=None,
    )


def run_gate_loop(
    draft: dict,
    context: GateContext,
    dispose_fn: Callable[[GatePrompt], str] | None = None,
    *,
    edit_fn: Callable[[dict, GateContext], tuple[dict, str | None]] | None = None,
) -> GateResult:
    """Run one or more passes of the confirmation gate.

    AskUserQuestion is a Claude tool, not a Python callable, so the loop
    delegates disposition resolution and edit collection to caller-supplied
    callbacks. This mirrors the pattern in gap_detect / gap_suggest.

    Behaviour:
      - Render the gate display + options.
      - Call `dispose_fn(prompt)` to obtain a disposition keyword.
      - On "edit": call `edit_fn(draft, context)` to obtain the post-edit
        draft + optional edit_notes, then re-render and re-dispose. If the
        uploader confirms the edited draft, return GateResult with
        disposition="edited" + pre_edit_snapshot=<original pristine draft>.
      - On any other disposition: return immediately.

    If `dispose_fn` is None this function raises — the loop cannot run
    without a way to collect disposition. Callers in a pure-Python test
    context can pass a lambda; callers in a Claude skill context can use
    `build_prompt` + `apply_disposition` directly and skip the loop helper.

    The function never writes audit rows or files — see SKILL.md Step 3b
    and the module docstring.
    """
    if dispose_fn is None:
        raise ValueError(
            "run_gate_loop requires a dispose_fn callback to resolve "
            "disposition; pass a callable that takes a GatePrompt and "
            "returns one of context.disposition_options."
        )

    pristine = draft  # never mutated; carried into pre_edit_snapshot on edit
    current_draft = draft
    pre_edit_snapshot: dict | None = None
    edit_notes: str | None = None

    while True:
        prompt = build_prompt(current_draft, context)
        disposition = dispose_fn(prompt)
        if disposition not in context.disposition_options:
            raise ValueError(
                f"dispose_fn returned {disposition!r}; expected one of "
                f"{context.disposition_options!r}"
            )

        if disposition == "edit":
            if edit_fn is None:
                raise ValueError(
                    "run_gate_loop got disposition='edit' but no edit_fn "
                    "callback was provided. Either supply edit_fn or use "
                    "build_prompt + apply_disposition directly."
                )
            # First entry into edit captures the pristine draft.
            if pre_edit_snapshot is None:
                pre_edit_snapshot = pristine
            current_draft, notes = edit_fn(current_draft, context)
            if notes is not None:
                edit_notes = notes
            # Loop: re-render and ask again.
            continue

        if disposition == "confirm":
            if pre_edit_snapshot is not None:
                # User confirmed after one or more edits — record as the
                # mapped disposition for "edit" (single source of truth in
                # _RESULT_DISPOSITION).
                return GateResult(
                    disposition=_RESULT_DISPOSITION["edit"],
                    final_draft=current_draft,
                    pre_edit_snapshot=pre_edit_snapshot,
                    edit_notes=edit_notes,
                )
            return GateResult(
                disposition=_RESULT_DISPOSITION["confirm"],
                final_draft=current_draft,
                pre_edit_snapshot=None,
                edit_notes=None,
            )

        # re_extract / reject / regenerate / abandon: terminal, no draft.
        return GateResult(
            disposition=_RESULT_DISPOSITION.get(disposition, disposition),
            final_draft=None,
            pre_edit_snapshot=None,
            edit_notes=None,
        )
