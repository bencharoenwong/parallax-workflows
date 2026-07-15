from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from transcript import Transcript  # noqa: E402
from tier1_structural import grade_tier1  # noqa: E402
from eval_spec import load_spec  # noqa: E402


SPEC = load_spec("deep-dive")


def _result_map(checks):
    return {c.name: c.passed for c in checks}


def test_deep_dive_spec_has_expected_sections():
    assert SPEC.command == "/parallax-deep-dive"
    assert "Technical Stance" in SPEC.required_sections
    assert "Assessment" in SPEC.required_sections
    assert "House View Note" in SPEC.section_labels


def test_technical_fallback_requires_proxy_label_when_unavailable():
    t = Transcript(
        final_prose=(
            "## Technical Stance\n"
            "Technical analysis unavailable — insufficient data.\n"
        )
    )
    results = _result_map(grade_tier1(t, SPEC))
    assert results["technical_fallback_explicit"] is False


def test_technical_fallback_passes_when_proxy_is_named():
    t = Transcript(
        final_prose=(
            "## Technical Stance\n"
            "Technical analysis unavailable — Momentum factor proxy: momentum is firm.\n"
        )
    )
    results = _result_map(grade_tier1(t, SPEC))
    assert results["technical_fallback_explicit"] is True


def test_view_aware_disclaimer_is_accepted():
    t = Transcript(
        final_prose=(
            "## Provenance\nBranding: default Parallax\n"
            "This analysis reflects active house view 'Q2 Defensive Tilt' uploaded by CIO on 2026-06-28, "
            "effective 2026-06-28 through 2026-09-01. Tilts and excludes per the loaded view; "
            "conflicts with explicit user scope are flagged inline. Outputs should be reviewed against "
            "client suitability before any action.\n"
        )
    )
    results = _result_map(grade_tier1(t, SPEC))
    assert results["disclaimer_present_deep_dive"] is True


def test_deep_dive_minimal_golden_shape_passes_structure_checks():
    t = Transcript(
        final_prose=(
            "## Company Overview\nbody\n"
            "## Macro Environment\nbody\n"
            "## Factor Profile\nbody\n"
            "## Financial Highlights\nbody\n"
            "## Dividend Profile\nbody\n"
            "## Risk/Return Profile\nbody\n"
            "## Technical Stance\ntrend, momentum, support\n"
            "## News Catalyst Watch\nbody\n"
            "## Assessment\nbody\n"
            "## Risk Factors\nbody\n"
            "## Provenance\nBranding: default Parallax\n"
            "AI-assisted output. Quantitative data is deterministic; qualitative is LLM-generated.\n"
            "This is informational analysis based on Parallax factor scores, not investment advice. "
            "All outputs should be reviewed by qualified professionals before any investment decisions.\n"
        )
    )
    results = _result_map(grade_tier1(t, SPEC))
    assert results["sections_present"] is True
    assert results["technical_fallback_explicit"] is True
    assert results["provenance_present"] is True
    assert results["ai_disclosure_present"] is True
    assert results["disclaimer_present_deep_dive"] is True
