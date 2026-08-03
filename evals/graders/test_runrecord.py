"""Status classification and the two cost meters on a RunRecord.

``runrecord.py`` shipped with no tests, and every rule below was reasoned about
in review rather than executed. That is how a permanent-degrade bug in the
ambiguity path survived three rounds of inspection: nothing could contradict the
argument. These tests exist so the classification contract is asserted rather
than argued.

What matters here is which runs reach ``AGGREGATABLE``. A run wrongly pooled
into an aggregate presents a wrong number as a measured client bill; a run
wrongly excluded silently shrinks the sample.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import runrecord  # noqa: E402
from runrecord import (  # noqa: E402
    STATUS_DEGRADED,
    STATUS_INFRA_FAILURE,
    STATUS_OK,
    STATUS_SKILL_ERROR,
    from_stream_json,
)


def _stream(tool_names=(), *, is_error=False, cost=1.25, include_result=True):
    """A minimal but structurally real stream-json transcript."""
    lines = [json.dumps({
        "type": "system",
        "subtype": "init",
        "mcp_servers": [{"name": "claude_ai_Parallax", "status": "connected"}],
    })]
    for i, name in enumerate(tool_names):
        lines.append(json.dumps({
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "id": f"t{i}", "name": name, "input": {}}
            ]},
        }))
    lines.append(json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "Done."}]},
    }))
    if include_result:
        lines.append(json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": is_error,
            "duration_ms": 4000,
            "duration_api_ms": 3000,
            "num_turns": 2,
            "total_cost_usd": cost,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }))
    return "\n".join(lines)


def _p(tool: str) -> str:
    return f"mcp__claude_ai_Parallax__{tool}"


# --- the happy path -------------------------------------------------------

def test_clean_run_is_ok_and_aggregatable():
    rec = from_stream_json(_stream([_p("get_company_info")]), "r1")
    assert rec.status == STATUS_OK
    assert rec.aggregatable()
    assert rec.parallax_tokens == 1
    assert rec.degraded_paths == []


def test_the_two_meters_are_not_merged():
    """The Anthropic bill is CG's; the Parallax total is the client's."""
    rec = from_stream_json(_stream([_p("get_assessment")], cost=3.10), "r2")
    assert rec.anthropic_cost_usd == 3.10       # metered
    assert rec.parallax_tokens == 10            # derived
    assert rec.parallax_cost_usd == round(10 * 0.20, 4)


def test_tool_calls_parallax_counts_parallax_work_not_harness_tools():
    rec = from_stream_json(
        _stream([_p("get_peer_snapshot"), _p("get_peer_snapshot"), "Read"]), "r3"
    )
    assert rec.tool_calls_parallax == {"get_peer_snapshot": 2}
    assert rec.tool_calls_total == 3


def test_tool_calls_parallax_counts_unpriced_endpoints_too():
    """Work performed is not the same question as work billed.

    A pair-finder run is mostly KNOWN_UNPRICED calls. Counting only the priced
    tables would report it as having made zero Parallax calls, leaving nothing
    on the record that states how much Parallax work it actually did.
    """
    rec = from_stream_json(
        _stream([_p("etf_holdings"), _p("etf_holdings"), _p("etf_search")]), "r3b"
    )
    assert rec.tool_calls_parallax == {"etf_holdings": 2, "etf_search": 1}
    assert rec.parallax_tokens == 0


# --- degrade rules: what must and must not leave AGGREGATABLE -------------

def test_unknown_endpoint_degrades_as_a_stale_table_signal():
    rec = from_stream_json(_stream([_p("brand_new_tool")]), "r4")
    assert rec.status == STATUS_DEGRADED
    assert not rec.aggregatable()
    assert rec.degraded_paths == ["unknown_endpoint:brand_new_tool"]


def test_known_unpriced_endpoint_stays_aggregatable():
    """The carve-out that keeps pair-finder runs usable.

    These four can never be cleared by a table edit, so degrading on them would
    exclude an entire workflow from aggregation permanently.
    """
    rec = from_stream_json(_stream([_p("etf_holdings"), _p("etf_search")]), "r5")
    assert rec.status == STATUS_OK
    assert rec.aggregatable()
    assert rec.unpriced_endpoints == ["etf_holdings", "etf_search"]
    assert rec.degraded_paths == []


def test_ambiguous_endpoint_degrades_and_is_recorded():
    """An unattributable call makes the derived total untrustworthy."""
    rec = from_stream_json(_stream(["mcp__research_desk__get_company_info"]), "r6")
    assert rec.status == STATUS_DEGRADED
    assert not rec.aggregatable()
    assert rec.ambiguous_endpoints == ["mcp__research_desk__get_company_info"]
    assert rec.parallax_tokens == 0, "must not bill a call we cannot attribute"


def test_foreign_server_does_not_degrade_or_bill():
    rec = from_stream_json(
        _stream(["mcp__plugin_github_github__get_me", "Read", "Bash"]), "r7"
    )
    assert rec.status == STATUS_OK
    assert rec.parallax_tokens == 0
    assert rec.unknown_endpoints == []
    assert rec.ambiguous_endpoints == []


def test_declared_foreign_namespace_clears_ambiguity_without_billing(monkeypatch):
    """A real collision must be resolvable in the truthful direction.

    Only ``PARALLAX_MCP_ALIASES`` existed at first, so the sole way to stop a
    genuine foreign collision from degrading every run was to declare that
    server Parallax -- which would then bill its calls to the client. This is
    the honest resolution.
    """
    import importlib

    monkeypatch.setenv("PARALLAX_MCP_FOREIGN_NAMESPACES", "claude_ai_hubspot")
    importlib.reload(runrecord.token_model)
    importlib.reload(runrecord)
    try:
        rec = runrecord.from_stream_json(
            _stream(["mcp__claude_ai_HubSpot__submit_feedback"]), "r8"
        )
        assert rec.status == STATUS_OK, "a declared foreign server must not degrade"
        assert rec.ambiguous_endpoints == []
        assert rec.parallax_tokens == 0, "and must never be billed"
    finally:
        monkeypatch.delenv("PARALLAX_MCP_FOREIGN_NAMESPACES", raising=False)
        importlib.reload(runrecord.token_model)
        importlib.reload(runrecord)


# --- failure classification ----------------------------------------------

def test_infra_failure_is_retained_not_dropped():
    rec = from_stream_json("", "r9")
    assert rec.status == STATUS_INFRA_FAILURE
    assert rec.infra_reason
    assert not rec.aggregatable()


def test_missing_result_event_is_infra_failure_but_keeps_tool_calls():
    raw = _stream([_p("get_company_info")], include_result=False)
    rec = from_stream_json(raw, "r10")
    assert rec.status == STATUS_INFRA_FAILURE
    assert rec.tool_calls_total == 1, "tool calls survive a missing result event"


def test_skill_error_is_distinct_from_infra_failure():
    rec = from_stream_json(_stream([_p("get_company_info")], is_error=True), "r11")
    assert rec.status == STATUS_SKILL_ERROR
    assert not rec.aggregatable()


def test_infra_failure_outranks_a_degrade():
    """Classification must not be overwritten by a later, weaker signal."""
    raw = _stream([_p("brand_new_tool")], include_result=False)
    rec = from_stream_json(raw, "r12")
    assert rec.status == STATUS_INFRA_FAILURE


def test_a_scalar_json_line_does_not_abort_classification():
    """A stray scalar line parses fine as JSON, so the JSONDecodeError guard
    never fires; without an isinstance check the record aborts on AttributeError
    instead of classifying the run."""
    raw = _stream([_p("get_company_info")])
    lines = raw.splitlines()
    lines.insert(1, "42")
    lines.insert(2, json.dumps(["not", "an", "event"]))
    lines.insert(3, json.dumps({"type": "assistant", "message": "unexpected string"}))
    rec = from_stream_json("\n".join(lines), "r14")
    assert rec.status == STATUS_OK
    assert rec.tool_calls_total == 1
    assert rec.tool_errors == 0


def test_to_json_roundtrips_every_field():
    rec = from_stream_json(_stream([_p("get_company_info")]), "r13")
    parsed = json.loads(rec.to_json())
    for key in ("status", "parallax_tokens", "unknown_endpoints",
                "unpriced_endpoints", "ambiguous_endpoints", "anthropic_cost_usd"):
        assert key in parsed
