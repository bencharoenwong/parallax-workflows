"""Tests for recommendation.py — citation validator is the load-bearing one."""
from __future__ import annotations

import recommendation as rec


# ---------------------------------------------------------------------------
# Citation validator — the hallucination control.
# ---------------------------------------------------------------------------


def test_validator_passes_when_rationale_quotes_snippet():
    snippet = "Japan tactical view stays constructive. BoJ holding pattern supports a positive regional tilt."
    recommendation = {
        "recommended_value": 1,
        "confidence": 0.8,
        "rationale": "Maintain OW Japan; BoJ holding pattern supports a positive regional tilt per source.",
        "suggested_basis_statement_addendum": "BoJ steady",
    }
    ok, reason = rec.validate_citation(snippet, recommendation)
    assert ok, f"expected pass; got: {reason}"


def test_validator_fails_when_rationale_is_about_different_topic():
    """Brief example: snippet talks about Japan rates, rationale claims Brazil.

    This is the core hallucination scenario the validator exists to catch.
    The LLM "answered" but cited nothing the user actually showed it.
    """
    snippet = (
        "Japan tactical view stays constructive. BoJ holding pattern supports "
        "a positive regional tilt; corporate-governance reforms continue to "
        "surface value in mid-cap industrials."
    )
    recommendation = {
        "recommended_value": -1,
        "confidence": 0.6,
        "rationale": "Underweight Brazil — central bank is hiking and fiscal stance is loose.",
        "suggested_basis_statement_addendum": "Brazil risk",
    }
    ok, reason = rec.validate_citation(snippet, recommendation)
    assert not ok
    assert "no verbatim substring" in reason.lower()


def test_validator_accepts_evidence_refs_substring():
    snippet = "Quality factor effectiveness 0.50 — leadership rotating toward Health Care defensives."
    recommendation = {
        "recommended_value": 1,
        "confidence": 0.75,
        "rationale": "Hold OW Health Care; rotation continues.",
        "suggested_basis_statement_addendum": "HC defensives",
        "evidence_refs": ["Quality factor effectiveness 0.50 — leadership rotating toward Health Care"],
    }
    ok, reason = rec.validate_citation(snippet, recommendation)
    assert ok
    assert "evidence_refs" in reason


def test_validator_accepts_null_value_with_insufficient_evidence():
    snippet = "Mixed signals across markets — narrative remains in flux."
    recommendation = {
        "recommended_value": None,
        "confidence": 0.0,
        "rationale": "insufficient evidence in source",
        "suggested_basis_statement_addendum": "",
    }
    ok, _ = rec.validate_citation(snippet, recommendation)
    assert ok


def test_validator_rejects_null_value_without_decline_phrase_and_no_citation():
    snippet = "Mixed signals across markets — narrative remains in flux."
    recommendation = {
        "recommended_value": None,
        "confidence": 0.5,
        # Honest-decline phrase missing AND no substring of snippet present.
        "rationale": "The data is unclear and I cannot decide right now.",
        "suggested_basis_statement_addendum": "",
    }
    ok, _ = rec.validate_citation(snippet, recommendation)
    assert not ok


def test_validator_rejects_short_substring():
    """A 10-char overlap shouldn't qualify — too easy for a hallucinator to hit by chance."""
    snippet = "Japan tactical view stays constructive."
    recommendation = {
        "recommended_value": 1,
        "confidence": 0.8,
        "rationale": "Japan view: bullish based on broader macro context.",  # only "Japan view" overlaps
        "suggested_basis_statement_addendum": "",
    }
    ok, _ = rec.validate_citation(snippet, recommendation)
    assert not ok


def test_validator_rejects_empty_snippet():
    ok, reason = rec.validate_citation("", {"rationale": "anything"})
    assert not ok
    assert "empty" in reason.lower()


def test_validator_rejects_non_dict_recommendation():
    ok, reason = rec.validate_citation("any snippet here", "not a dict")  # type: ignore[arg-type]
    assert not ok


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def test_build_prompt_truncates_long_snippet():
    long_snippet = "x" * 500
    prompt = rec.build_recommendation_prompt(
        path="tilts.sectors.health_care",
        cio_value=1,
        parallax_value=-1,
        effective_date="2026-04-24",
        tool="macro_analyst",
        args={"market": "United States", "component": "sectors"},
        parallax_date="2026-05-22",
        source_snippet=long_snippet,
        state="DIVERGENT_FRESH",
        severity="drift_material",
    )
    assert len(prompt["snippet_for_validation"]) == rec.SNIPPET_TRUNCATE_LEN
    # Schema should constrain recommended_value to -2..+2 plus null.
    assert prompt["schema"]["properties"]["recommended_value"]["minimum"] == -2
    assert prompt["schema"]["properties"]["recommended_value"]["maximum"] == 2


def test_build_prompt_includes_state_and_severity():
    prompt = rec.build_recommendation_prompt(
        path="tilts.regions.japan",
        cio_value=1,
        parallax_value=-1,
        effective_date="2026-04-24",
        tool="macro_analyst",
        args=None,
        parallax_date="2026-05-22",
        source_snippet="Japan tactical view has reversed.",
        state="DIVERGENT_FRESH",
        severity="drift_material",
    )
    assert "Japan tactical view has reversed." in prompt["user"]
    assert "DIVERGENT_FRESH" in prompt["user"]
    assert "drift_material" in prompt["user"]


# ---------------------------------------------------------------------------
# apply_recommendation_or_decline
# ---------------------------------------------------------------------------


def test_apply_keeps_valid_recommendation():
    snippet = "Japan tactical view stays constructive."
    rec_in = {
        "recommended_value": 1,
        "confidence": 0.85,
        "rationale": "Maintain OW Japan — Japan tactical view stays constructive.",
        "suggested_basis_statement_addendum": "",
    }
    record, ok = rec.apply_recommendation_or_decline(
        snippet=snippet,
        recommendation=rec_in,
        path="tilts.regions.japan",
        state="DIVERGENT_FRESH",
        severity="drift_material",
    )
    assert ok
    assert record["declined"] is False
    assert record["recommended_value"] == 1
    assert record["path"] == "tilts.regions.japan"
    assert record["stress_state"] == "DIVERGENT_FRESH"


def test_apply_substitutes_decline_on_hallucination():
    # Japan-rates snippet, but the rationale claims Brazil (the load-bearing
    # test from the task brief).
    snippet = (
        "BoJ holding pattern supports a positive regional tilt; "
        "corporate-governance reforms continue to surface value."
    )
    rec_in = {
        "recommended_value": -1,
        "confidence": 0.6,
        "rationale": "Underweight Brazil — central bank is hiking aggressively.",
        "suggested_basis_statement_addendum": "Brazil risk",
    }
    record, ok = rec.apply_recommendation_or_decline(
        snippet=snippet,
        recommendation=rec_in,
        path="tilts.regions.japan",
        state="DIVERGENT_FRESH",
        severity="drift_material",
    )
    assert not ok
    assert record["declined"] is True
    assert record["rationale"] == rec.DECLINE_MARKER
    assert record["recommended_value"] is None
    assert record["confidence"] == 0.0


def test_apply_handles_missing_evidence_refs_field():
    snippet = "China macro picture remains soft."
    rec_in = {
        "recommended_value": -1,
        "confidence": 0.7,
        "rationale": "Keep UW China; China macro picture remains soft per source.",
        "suggested_basis_statement_addendum": "",
        # No evidence_refs field at all — should still pass via rationale.
    }
    record, ok = rec.apply_recommendation_or_decline(
        snippet=snippet,
        recommendation=rec_in,
        path="tilts.regions.china",
        state="DIVERGENT_STALE",
        severity="drift_material",
    )
    assert ok
    assert "evidence_refs" in record  # gets added as []


def test_min_citation_len_constant_is_30():
    # The 30-char threshold is documented in the task brief and SKILL.md.
    # If we ever change it, both the spec docs and tests must move together.
    assert rec.MIN_CITATION_SUBSTRING_LEN == 30
