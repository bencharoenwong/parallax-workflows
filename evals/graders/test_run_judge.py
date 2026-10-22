from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from run_judge import check_model, render_prompt, _parse_verdict, ALLOWED_MODEL_PREFIXES  # noqa: E402
from judge_criteria import CRITERIA  # noqa: E402

import json as _json


def _envelope(result_value):
    """Build a `claude -p --output-format json` envelope with the given `result`."""
    return _json.dumps({"result": result_value})


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


# --- _parse_verdict graceful-degradation (code-quality review, Task 5) ---

def test_parse_verdict_explicit_true():
    v = _parse_verdict("c", 0, _envelope('{"pass": true, "reason": "balanced"}'), "")
    assert v["pass"] is True and v["reason"] == "balanced"


def test_parse_verdict_explicit_false():
    v = _parse_verdict("c", 0, _envelope('{"pass": false, "reason": "no con"}'), "")
    assert v["pass"] is False


def test_parse_verdict_null_result_does_not_crash():
    # `claude -p` can return result: null on internal error -> must yield pass=None, not raise.
    v = _parse_verdict("c", 0, _envelope(None), "")
    assert v["pass"] is None


def test_parse_verdict_empty_dict_is_none_not_false():
    # An empty verdict must NOT be silently counted as a fail.
    v = _parse_verdict("c", 0, _envelope("{}"), "")
    assert v["pass"] is None


def test_parse_verdict_garbage_result_is_none():
    v = _parse_verdict("c", 0, _envelope("not json"), "")
    assert v["pass"] is None


def test_parse_verdict_nonzero_returncode_is_none():
    v = _parse_verdict("c", 1, "", "boom")
    assert v["pass"] is None and "boom" in v["reason"]
