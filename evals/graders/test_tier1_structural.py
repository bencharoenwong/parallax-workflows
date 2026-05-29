from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from transcript import load_transcript  # noqa: E402
from tier1_structural import grade_tier1, CHECK_NAMES  # noqa: E402

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
