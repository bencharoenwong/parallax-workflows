# evals/graders/test_transcript.py
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from transcript import parse_stream_json, Transcript  # noqa: E402

SAMPLE = "\n".join([
    '{"type":"system","subtype":"init","tools":[]}',
    '{"type":"assistant","message":{"content":[{"type":"text","text":"Looking up AAPL."},'
    '{"type":"tool_use","id":"t1","name":"mcp__claude_ai_Parallax__get_company_info","input":{"symbol":"AAPL.O"}}]}}',
    '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":[{"type":"text","text":"{}"}]}]}}',
    '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t2",'
    '"name":"mcp__claude_ai_Parallax__macro_analyst","input":{"component":"tactical"}}]}}',
    '',
    '{"type":"result","subtype":"success","result":"## The Company\\nApple makes phones."}',
])


def test_parses_final_prose_from_result_event():
    t = parse_stream_json(SAMPLE)
    assert isinstance(t, Transcript)
    assert t.final_prose == "## The Company\nApple makes phones."


def test_collects_tool_calls_in_order():
    t = parse_stream_json(SAMPLE)
    names = [c.name for c in t.tool_calls]
    assert names == [
        "mcp__claude_ai_Parallax__get_company_info",
        "mcp__claude_ai_Parallax__macro_analyst",
    ]
    assert t.tool_calls[0].input == {"symbol": "AAPL.O"}


def test_tolerates_blank_lines_and_unknown_types():
    t = parse_stream_json('\n\n{"type":"system"}\n{"type":"result","result":"hi"}\n')
    assert t.final_prose == "hi"
    assert t.tool_calls == []


def test_called_tool_helper():
    t = parse_stream_json(SAMPLE)
    assert t.called("macro_analyst") is True
    assert t.called("get_news_synthesis") is False


def test_returns_empty_prose_when_no_result_event():
    # Interrupted/aborted run with no result event -> empty prose, no error.
    t = parse_stream_json(
        '{"type":"assistant","message":{"content":[{"type":"text","text":"thinking"}]}}'
    )
    assert t.final_prose == ""
    assert t.tool_calls == []


def test_report_survives_trailing_signoff():
    # Regression: skill delivers the report in an earlier assistant turn, then
    # ends with a short sign-off. The result event captures only the sign-off;
    # final_prose must still surface the report (longest candidate wins).
    report = "## Bottom line\n" + ("Apple analysis. " * 200)
    stream = "\n".join([
        '{"type":"assistant","message":{"content":[{"type":"text","text":' + json.dumps(report) + "}]}}",
        '{"type":"result","subtype":"success","result":"Report delivered above; audit logged."}',
    ])
    t = parse_stream_json(stream)
    assert t.final_prose == report


def test_result_wins_when_it_is_the_report():
    # When the report IS the final turn, the result event is the longest
    # candidate and is returned unchanged (no regression vs. earlier preamble).
    stream = "\n".join([
        '{"type":"assistant","message":{"content":[{"type":"text","text":"Looking up AAPL."}]}}',
        '{"type":"result","result":' + json.dumps("## The Company\n" + "x" * 500) + "}",
    ])
    t = parse_stream_json(stream)
    assert t.final_prose.startswith("## The Company")
    assert len(t.final_prose) > 100
