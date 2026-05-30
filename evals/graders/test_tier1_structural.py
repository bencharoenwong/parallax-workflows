from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from transcript import load_transcript  # noqa: E402
from tier1_structural import grade_tier1, CHECK_NAMES, _section_present  # noqa: E402

FIX = Path(__file__).parent.parent / "fixtures" / "should-i-buy"


def _result_map(checks):
    return {c.name: c.passed for c in checks}


def test_golden_passes_every_check():
    t = load_transcript(FIX / "golden_aapl_en.stream.json")
    results = _result_map(grade_tier1(t, skill_path=None))
    assert all(results.values()), [n for n, p in results.items() if not p]


def test_broken_fails_only_disclaimer():
    t = load_transcript(FIX / "broken_aapl_en.stream.json")
    results = _result_map(grade_tier1(t, skill_path=None))
    failed = [n for n, p in results.items() if not p]
    assert failed == ["disclaimer_present_correct"], failed


def test_registry_is_enumerable():
    t = load_transcript(FIX / "golden_aapl_en.stream.json")
    names = [c.name for c in grade_tier1(t, skill_path=None)]
    assert set(names) == set(CHECK_NAMES)


def test_macro_conditional_flags_missing_section_when_macro_called():
    from transcript import Transcript, ToolCall
    t = Transcript(
        final_prose="## The Company\nx\n## Bottom Line\npros and cons\n",
        tool_calls=[ToolCall("mcp__claude_ai_Parallax__macro_analyst", {})],
    )
    results = _result_map(grade_tier1(t, skill_path=None))
    assert results["macro_conditional"] is False


# --- live-output robustness regressions (code-quality review, Task 4) ---

def test_rec_in_analyst_view_does_not_fail_bottom_line():
    # "Strong Buy" consensus in Analyst View must NOT trip bottom_line_no_rec.
    from transcript import Transcript
    t = Transcript(
        final_prose=(
            "## Analyst View\nConsensus: 14 Strong Buy, 8 Buy, 3 Hold.\n\n"
            "## Bottom Line\nSolid quality but rich valuation; growth is slowing.\n"
        ),
        tool_calls=[],
    )
    assert _result_map(grade_tier1(t, skill_path=None))["bottom_line_no_rec"] is True


def test_recommendation_inside_bottom_line_fails():
    from transcript import Transcript
    t = Transcript(final_prose="## Bottom Line\nWe recommend buying this stock now.\n", tool_calls=[])
    assert _result_map(grade_tier1(t, skill_path=None))["bottom_line_no_rec"] is False


def test_ai_disclosure_matches_canonical_92_banner():
    from transcript import Transcript
    t = Transcript(
        final_prose="AI-assisted output. Quantitative data is deterministic; qualitative is LLM-generated.",
        tool_calls=[],
    )
    assert _result_map(grade_tier1(t, skill_path=None))["ai_disclosure_present"] is True


def test_scores_trend_scoped_to_scores_section():
    # A numeric range only in Financial Health must NOT satisfy the Scores trend check.
    from transcript import Transcript
    t = Transcript(
        final_prose=(
            "## The Scores\nQuality is high.\n\n"
            "## Financial Health\nRevenue grew from 100 to 120 billion.\n"
        ),
        tool_calls=[],
    )
    assert _result_map(grade_tier1(t, skill_path=None))["scores_trend_direction"] is False


def test_scores_trend_accepts_arrow_notation():
    from transcript import Transcript
    t = Transcript(final_prose="## The Scores\nQuality 5.8 → 7.2 over 52 weeks.\n", tool_calls=[])
    assert _result_map(grade_tier1(t, skill_path=None))["scores_trend_direction"] is True


# --- real-output format calibration (locked against live should-i-buy, 2026-05-29) ---

def test_section_present_matches_italic_provenance_label():
    # Live skill renders Provenance as "*Provenance: ...*", not a "## Provenance" heading.
    assert _section_present("*Provenance: Branding — default Parallax. Data from pipelines.*", "Provenance") is True


def test_section_present_tolerates_vs_period_heading():
    # Live heading is "### Risk vs. Peers" (period after vs).
    assert _section_present("### Risk vs. Peers\nLower volatility than peers.", "Risk vs Peers") is True


def test_section_present_matches_plain_heading():
    assert _section_present("## The Scores\nbody", "The Scores") is True


def test_section_present_absent_returns_false():
    assert _section_present("## Recent News\nbody", "Provenance") is False
