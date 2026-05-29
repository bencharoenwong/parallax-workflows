from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from run_judge import check_model, render_prompt, ALLOWED_MODEL_PREFIXES  # noqa: E402
from judge_criteria import CRITERIA  # noqa: E402


def test_allowlist_accepts_anthropic_model():
    check_model("claude-opus-4-8")  # should not raise


def test_allowlist_rejects_external_model():
    with pytest.raises(SystemExit):
        check_model("gemini-3-pro-preview")
    with pytest.raises(SystemExit):
        check_model("gpt-5.5")


def test_criteria_are_well_formed():
    assert len(CRITERIA) >= 4
    for c in CRITERIA:
        assert set(c) >= {"id", "statement", "pass_when"}
        assert c["statement"] and c["pass_when"]
    assert len({c["id"] for c in CRITERIA}) == len(CRITERIA)


def test_render_prompt_inlines_criterion_and_prose():
    prompt = render_prompt(CRITERIA[0], "## Bottom Line\nApple is strong but pricey.")
    assert CRITERIA[0]["statement"] in prompt
    assert CRITERIA[0]["pass_when"] in prompt
    assert "Apple is strong but pricey" in prompt
    assert "JSON" in prompt


def test_allowed_prefixes_are_anthropic_only():
    assert all(p.startswith("claude") for p in ALLOWED_MODEL_PREFIXES)
