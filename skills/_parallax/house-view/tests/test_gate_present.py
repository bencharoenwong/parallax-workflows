"""Unit tests for gate_present.py."""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import gate_present  # noqa: E402
from gate_present import (  # noqa: E402
    GateContext,
    GatePrompt,
    GateResult,
    apply_disposition,
    build_prompt,
    run_gate_loop,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _ingest_context(**overrides):
    base = dict(
        source_label="Q2-letter.pdf",
        uploader_present=True,
        confidence_map={
            "sectors": 0.9,
            "regions": 0.8,
            "factors": 0.75,
            "macro_regime": 0.9,
        },
        extraction_attempt_action=True,
        disposition_options=["confirm", "edit", "re_extract", "reject"],
    )
    base.update(overrides)
    return GateContext(**base)


def _maker_context(**overrides):
    base = dict(
        source_label="Parallax synthesis 2026-05-24T00:00:00Z",
        uploader_present=False,
        confidence_map={
            "sectors": 0.7,
            "regions": 0.6,
            "factors": 0.55,
            "macro_regime": 0.65,
            "pillars": 0.5,  # BUG-005: maker extends with pillars key
        },
        extraction_attempt_action=True,
        disposition_options=["confirm", "edit", "regenerate", "abandon"],
    )
    base.update(overrides)
    return GateContext(**base)


def _draft():
    return {
        "metadata": {
            "view_name": "Reflationary baseline 2026Q2",
            "uploader_role": "CIO",
            "effective_date": "2026-05-24",
            "valid_through": "2026-08-22",
            "basis_statement": "IC meeting 2026-05-22.",
        },
        "tilts": {
            "pillars": {
                "econometrics_phase": 1,
                "valuation_state": -1,
                "market_entropy": 0,
                "psychological_wavelength": 1,
            },
            "sectors": {"information_technology": 1, "energy": -1},
            "regions": {"japan": 1},
            "factors": {"momentum": 1, "value": -1},
            "macro_regime": {
                "growth": "steady",
                "inflation": "sticky",
                "rates": "holding",
                "risk_appetite": "neutral",
            },
        },
        "extraction": {
            "extraction_confidence": {
                "sectors": 0.9,
                "regions": 0.8,
                "factors": 0.75,
                "macro_regime": 0.9,
            },
            "extraction_notes": "Hedged on semis.",
            "tilt_variance": 0.85,
        },
    }


# ---------------------------------------------------------------------------
# Dataclass immutability (frozen) tests
# ---------------------------------------------------------------------------


def test_gate_context_dataclass_frozen():
    ctx = _ingest_context()
    assert dataclasses.is_dataclass(ctx)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.source_label = "mutated.pdf"


def test_gate_result_dataclass_frozen():
    result = GateResult(
        disposition="confirm",
        final_draft={"x": 1},
        pre_edit_snapshot=None,
        edit_notes=None,
    )
    assert dataclasses.is_dataclass(result)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.disposition = "mutated"


def test_gate_prompt_dataclass_frozen():
    prompt = GatePrompt(display="x", question="q", options=[("a", "A")])
    assert dataclasses.is_dataclass(prompt)
    with pytest.raises(dataclasses.FrozenInstanceError):
        prompt.display = "mutated"


# ---------------------------------------------------------------------------
# Display rendering
# ---------------------------------------------------------------------------


def test_ingest_display_uses_uploader_framing():
    ctx = _ingest_context()
    prompt = build_prompt(_draft(), ctx)
    assert "Source: Q2-letter.pdf" in prompt.display
    assert "Generated from:" not in prompt.display
    assert "DRAFT FOR CONFIRMATION" in prompt.display


def test_maker_display_uses_synthesis_framing():
    ctx = _maker_context()
    prompt = build_prompt(_draft(), ctx)
    assert "Generated from: Parallax synthesis" in prompt.display
    assert "SYNTHESIZED DRAFT FOR CONFIRMATION" in prompt.display


def test_display_shows_only_nonzero_tilts():
    draft = _draft()
    draft["tilts"]["sectors"]["health_care"] = 0  # should be suppressed
    prompt = build_prompt(draft, _ingest_context())
    assert "information_technology" in prompt.display
    assert "health_care" not in prompt.display


def test_low_confidence_block_includes_pillars_for_maker():
    """BUG-005: maker confidence_map carries pillars key — gate should render it."""
    ctx = _maker_context(
        confidence_map={
            "sectors": 0.9,
            "pillars": 0.35,  # low
        },
    )
    prompt = build_prompt(_draft(), ctx)
    assert "pillars: 0.35" in prompt.display


def test_low_confidence_block_omits_pillars_for_ingest():
    """Ingest path doesn't carry pillars confidence — should render without it."""
    ctx = _ingest_context()
    prompt = build_prompt(_draft(), ctx)
    # No "pillars:" entry should appear in the low-confidence block
    # (note: "PILLARS" heading is fine; we're checking the lowercase key)
    assert "  pillars:" not in prompt.display


def test_options_match_disposition_options_for_ingest():
    ctx = _ingest_context()
    prompt = build_prompt(_draft(), ctx)
    keys = [k for k, _ in prompt.options]
    assert keys == ["confirm", "edit", "re_extract", "reject"]


def test_options_match_disposition_options_for_maker():
    ctx = _maker_context()
    prompt = build_prompt(_draft(), ctx)
    keys = [k for k, _ in prompt.options]
    assert keys == ["confirm", "edit", "regenerate", "abandon"]


# ---------------------------------------------------------------------------
# run_gate_loop dispositions
# ---------------------------------------------------------------------------


def test_run_gate_loop_confirm_path():
    draft = _draft()
    ctx = _ingest_context()
    result = run_gate_loop(draft, ctx, dispose_fn=lambda _prompt: "confirm")
    assert result.disposition == "confirm"
    assert result.final_draft is draft
    assert result.pre_edit_snapshot is None
    assert result.edit_notes is None


def test_run_gate_loop_reject_path():
    draft = _draft()
    ctx = _ingest_context()
    result = run_gate_loop(draft, ctx, dispose_fn=lambda _: "reject")
    assert result.disposition == "rejected"
    assert result.final_draft is None
    assert result.pre_edit_snapshot is None


def test_run_gate_loop_re_extract_path():
    draft = _draft()
    ctx = _ingest_context()
    result = run_gate_loop(draft, ctx, dispose_fn=lambda _: "re_extract")
    assert result.disposition == "re_extracted"
    assert result.final_draft is None


def test_run_gate_loop_abandon_path_maker():
    draft = _draft()
    ctx = _maker_context()
    result = run_gate_loop(draft, ctx, dispose_fn=lambda _: "abandon")
    assert result.disposition == "abandoned"
    assert result.final_draft is None


def test_run_gate_loop_regenerate_path_maker():
    draft = _draft()
    ctx = _maker_context()
    result = run_gate_loop(draft, ctx, dispose_fn=lambda _: "regenerate")
    assert result.disposition == "regenerated"
    assert result.final_draft is None


def test_run_gate_loop_edit_then_confirm_returns_pre_edit_snapshot():
    pristine = _draft()
    ctx = _ingest_context()

    # State machine: edit on first call, confirm on second.
    calls = {"n": 0}

    def dispose(prompt):
        calls["n"] += 1
        return "edit" if calls["n"] == 1 else "confirm"

    def edit(current, _ctx):
        edited = {**current, "tilts": {**current["tilts"], "sectors": {"energy": 2}}}
        return edited, "Bumped energy from -1 to +2 per IC pushback."

    result = run_gate_loop(pristine, ctx, dispose_fn=dispose, edit_fn=edit)

    assert result.disposition == "edited"
    assert result.pre_edit_snapshot is pristine
    assert result.final_draft is not pristine
    assert result.final_draft["tilts"]["sectors"]["energy"] == 2
    assert result.edit_notes == "Bumped energy from -1 to +2 per IC pushback."


def test_run_gate_loop_multiple_edits_preserve_original_pristine():
    """Two edit passes followed by confirm — pre_edit_snapshot must be the
    ORIGINAL pristine draft, not the result of the first edit pass."""
    pristine = _draft()
    ctx = _ingest_context()

    calls = {"n": 0}

    def dispose(_prompt):
        calls["n"] += 1
        return "edit" if calls["n"] < 3 else "confirm"

    edit_count = {"n": 0}

    def edit(current, _ctx):
        edit_count["n"] += 1
        edited = {**current, "tilts": {**current["tilts"], "factors": {"momentum": edit_count["n"]}}}
        return edited, None

    result = run_gate_loop(pristine, ctx, dispose_fn=dispose, edit_fn=edit)
    assert result.disposition == "edited"
    assert result.pre_edit_snapshot is pristine
    assert result.final_draft["tilts"]["factors"]["momentum"] == 2  # last edit value


def test_run_gate_loop_rejects_invalid_disposition():
    draft = _draft()
    ctx = _ingest_context()
    with pytest.raises(ValueError, match="dispose_fn returned"):
        run_gate_loop(draft, ctx, dispose_fn=lambda _: "bogus")


def test_run_gate_loop_requires_dispose_fn():
    with pytest.raises(ValueError, match="dispose_fn"):
        run_gate_loop(_draft(), _ingest_context(), dispose_fn=None)


def test_run_gate_loop_edit_without_edit_fn_raises():
    with pytest.raises(ValueError, match="edit_fn"):
        run_gate_loop(
            _draft(),
            _ingest_context(),
            dispose_fn=lambda _: "edit",
            edit_fn=None,
        )


# ---------------------------------------------------------------------------
# apply_disposition (direct API for callers that drive their own loop)
# ---------------------------------------------------------------------------


def test_apply_disposition_confirm():
    draft = _draft()
    ctx = _ingest_context()
    result = apply_disposition(draft, ctx, "confirm")
    assert result.disposition == "confirm"
    assert result.final_draft is draft
    assert result.pre_edit_snapshot is None


def test_apply_disposition_edit_requires_edited_draft():
    with pytest.raises(ValueError, match="edited_draft"):
        apply_disposition(_draft(), _ingest_context(), "edit")


def test_apply_disposition_edit_with_edited_draft():
    pristine = _draft()
    edited = {**pristine, "tilts": {"factors": {"momentum": 2}}}
    ctx = _ingest_context()
    result = apply_disposition(
        pristine, ctx, "edit",
        edited_draft=edited,
        edit_notes="testing",
    )
    assert result.disposition == "edited"
    assert result.final_draft is edited
    assert result.pre_edit_snapshot is pristine
    assert result.edit_notes == "testing"


def test_apply_disposition_rejects_unknown_disposition():
    ctx = _ingest_context()
    with pytest.raises(ValueError, match="not in context.disposition_options"):
        apply_disposition(_draft(), ctx, "regenerate")  # maker-only verb
