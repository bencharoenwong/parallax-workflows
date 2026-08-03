"""The infra-failure predicate must give ONE answer per stream.

`grade_corpus` excludes infra failures from its report and `runrecord` excludes
them from `AGGREGATABLE`. When the two disagree, the same run is dropped from
one report and averaged into the other — the specific corruption these tests
exist to prevent. Every case below is asserted through BOTH entry points.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import runrecord  # noqa: E402
from grade_corpus import detect_infra_failure  # noqa: E402
from infra_failure import detect_infra_failure as detect_raw  # noqa: E402

_INIT_OK = '{"type":"system","subtype":"init","mcp_servers":[{"name":"claude_ai_Parallax"}]}'
_RESULT = '{"type":"result","subtype":"success","result":"# report","is_error":false}'


def _both(raw: str) -> tuple[str | None, str | None]:
    """(grade_corpus verdict, runrecord verdict) for the same stream."""
    rec = runrecord.from_stream_json(raw, run_id="t")
    return detect_infra_failure(raw), rec.infra_reason


def _agree(raw: str) -> None:
    corpus_reason, record_reason = _both(raw)
    assert (corpus_reason is None) == (record_reason is None), (
        f"graders disagree: grade_corpus={corpus_reason!r} runrecord={record_reason!r}"
    )


def test_healthy_run_is_gradeable_by_both():
    raw = _INIT_OK + "\n" + _RESULT
    assert _both(raw) == (None, None)
    assert runrecord.from_stream_json(raw, run_id="t").aggregatable()


def test_spaced_401_in_a_successful_result_fails_both():
    """The regression: a pretty-printed `"error_status": 401` alongside a
    `subtype: success` result. A literal-substring test misses the space, so
    the run reads OK to one grader and infra_failure to the other."""
    raw = _INIT_OK + '\n{"type":"result","subtype":"success","error_status": 401}'
    corpus_reason, record_reason = _both(raw)
    assert corpus_reason is not None and record_reason is not None
    assert "401" in corpus_reason and "401" in record_reason
    _agree(raw)


def test_compact_401_fails_both():
    raw = _INIT_OK + '\n{"type":"system","status":401}\n' + _RESULT
    assert all(r is not None for r in _both(raw))
    _agree(raw)


def test_401_unauthorized_prose_fails_both():
    raw = _INIT_OK + '\n{"type":"assistant","text":"401 Unauthorized"}\n' + _RESULT
    _agree(raw)


def test_empty_stream_fails_both():
    _agree("   ")
    assert all(r is not None for r in _both("   "))


def test_missing_result_event_fails_both():
    _agree(_INIT_OK)
    assert all(r is not None for r in _both(_INIT_OK))


def test_missing_connector_fails_both():
    raw = '{"type":"system","subtype":"init","mcp_servers":[]}\n' + _RESULT
    corpus_reason, record_reason = _both(raw)
    assert "connector" in (corpus_reason or "").lower()
    assert "connector" in (record_reason or "").lower()


def test_empty_server_list_with_parallax_present_is_not_a_connector_failure():
    """Another server reporting an empty list must not be read as Parallax
    being absent."""
    raw = (
        '{"type":"system","subtype":"init","mcp_servers":[{"name":"claude_ai_Parallax"}],'
        '"other_servers":{"mcp_servers":[]}}\n' + _RESULT
    )
    _agree(raw)


def test_parsed_result_checks_only_fire_with_a_parsed_result():
    """`api_error_status` / `subtype` live on the result dict, which the
    raw-only caller cannot see. Omitting the argument must not make the
    stream-level rules behave differently."""
    raw = _INIT_OK + '\n{"type":"result","subtype":"error_during_execution"}'
    assert detect_raw(raw) is None
    assert detect_raw(raw, {"subtype": "error_during_execution"}) is not None
    assert detect_raw(raw, {"subtype": "success", "api_error_status": 500}) is not None


def test_infra_failure_run_is_never_aggregated():
    raw = _INIT_OK + '\n{"type":"result","subtype":"success","error_status": 401}'
    rec = runrecord.from_stream_json(raw, run_id="t")
    assert rec.status == runrecord.STATUS_INFRA_FAILURE
    assert not rec.aggregatable()
