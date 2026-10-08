from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json  # noqa: E402

import pytest  # noqa: E402

from concierge_journeys_check import (  # noqa: E402
    check_journey,
    check_run,
    main,
    validate_journey,
)

REPO = Path(__file__).resolve().parents[2]
JOURNEYS = REPO / "evals" / "tasks" / "concierge" / "journeys.jsonl"
MANIFEST = REPO / "skills" / "_parallax" / "manifest.json"


def test_pass_when_expect_present_and_forbid_absent():
    passed, reasons = check_journey(
        "Here is the peer comparison for NVDA.",
        {"expect": ["peer"], "forbid": ["upload"]},
    )
    assert passed is True
    assert reasons == []


def test_fail_on_missing_expect():
    passed, reasons = check_journey(
        "Nothing relevant here.",
        {"expect": ["peer"], "forbid": []},
    )
    assert passed is False
    assert any("missing expect" in r and "peer" in r for r in reasons)


def test_fail_on_present_forbid():
    passed, reasons = check_journey(
        "Please upload your holdings as a CSV.",
        {"expect": [], "forbid": ["upload"]},
    )
    assert passed is False
    assert any("found forbidden" in r and "upload" in r for r in reasons)


def test_expect_any_passes_with_one_match():
    passed, reasons = check_journey(
        "Fund manager, Wealth advisor, or Individual investor?",
        {"expect_any": ["fund manager", "nonexistent phrase"]},
    )
    assert passed is True
    assert reasons == []


def test_expect_any_fails_with_no_match():
    passed, reasons = check_journey(
        "Something else entirely.",
        {"expect_any": ["fund manager", "wealth advisor"]},
    )
    assert passed is False
    assert any("expect_any" in r for r in reasons)


def test_expect_any_empty_list_is_a_no_op():
    passed, reasons = check_journey("Anything at all.", {"expect_any": []})
    assert passed is True
    assert reasons == []


def test_case_insensitive_expect_and_forbid():
    passed, _ = check_journey(
        "CONNECT your account to get started.",
        {"expect": ["connect"], "forbid": ["UPLOAD"]},
    )
    assert passed is True

    passed2, reasons2 = check_journey(
        "please UPLOAD a file",
        {"expect": [], "forbid": ["upload"]},
    )
    assert passed2 is False
    assert reasons2 != []


def test_case_insensitive_expect_any():
    passed, _ = check_journey(
        "RUNNING /PARALLAX-SHOULD-I-BUY NOW.",
        {"expect_any": ["running /"]},
    )
    assert passed is True


def test_reports_every_failure_not_just_first():
    passed, reasons = check_journey(
        "upload your file",
        {"expect": ["peer", "AAPL"], "forbid": ["upload"]},
    )
    assert passed is False
    assert len(reasons) == 3


def test_missing_keys_default_to_no_requirement():
    passed, reasons = check_journey("anything goes", {})
    assert passed is True
    assert reasons == []


# --- validate_journey -------------------------------------------------------

VALID = {"id": "J0", "prompt": "Hi Parallax", "expect": ["a"], "forbid": [], "expect_any": ["b"]}


def test_valid_journey_has_no_problems():
    assert validate_journey(VALID) == []


def test_rejects_unknown_key():
    problems = validate_journey({**VALID, "expects": ["typo"]})
    assert any("unknown keys" in p and "expects" in p for p in problems)


@pytest.mark.parametrize("key", ["expect", "forbid", "expect_any"])
@pytest.mark.parametrize("bad", ["peer", ["ok", 3], {"a": 1}, None])
def test_rejects_list_key_that_is_not_list_of_strings(key, bad):
    problems = validate_journey({**VALID, key: bad})
    assert any(key in p and "list of strings" in p for p in problems)


def test_rejects_missing_prompt_and_bad_needs():
    problems = validate_journey({"id": "J0", "needs": "offline"})
    assert any("'prompt'" in p for p in problems)
    assert any("'needs'" in p for p in problems)


def test_rejects_non_object():
    assert validate_journey(["J0"]) != []


def test_cli_validate_exit_codes(capsys):
    assert main(["--validate", json.dumps(VALID)]) == 0
    assert main(["--validate", json.dumps({**VALID, "forbid": "upload"})]) == 2
    assert "INVALID" in capsys.readouterr().out


def test_every_shipped_journey_is_valid():
    lines = [ln for ln in JOURNEYS.read_text().splitlines() if ln.strip()]
    assert lines
    for ln in lines:
        assert validate_journey(json.loads(ln)) == [], ln


def test_returning_and_direct_task_forbid_every_manifest_role_label():
    labels = {r["label"] for r in json.loads(MANIFEST.read_text())["roles"]}
    assert len(labels) == 7
    journeys = {j["id"]: j for j in map(json.loads, filter(str.strip, JOURNEYS.read_text().splitlines()))}
    for jid in ("J5_returning", "J7_direct_task_bypass"):
        assert labels <= set(journeys[jid]["forbid"]), jid


# --- check_run (stream-json, fail closed) ------------------------------------

def _stream(servers=None, result="Hi — where are we looking today?", denials=None,
            is_error=False, subtype="success", with_init=True, with_result=True,
            tool_call=None):
    """tool_call: (tool_name, result_is_error) for one tool_use/tool_result pair."""
    lines = []
    if with_init:
        lines.append(json.dumps({"type": "system", "subtype": "init",
                                 "mcp_servers": servers if servers is not None else
                                 [{"name": "claude.ai Parallax", "status": "pending"}]}))
    lines.append(json.dumps({"type": "assistant", "message": {"content": []}}))
    if tool_call:
        name, err = tool_call
        lines.append(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "tu1", "name": name, "input": {}}]}}))
        lines.append(json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "tu1", "is_error": err, "content": "x"}]}}))
    if with_result:
        lines.append(json.dumps({"type": "result", "subtype": subtype, "is_error": is_error,
                                 "result": result, "permission_denials": denials or []}))
    return "\n".join(lines) + "\n"


J = {"id": "J5", "prompt": "Hi Parallax", "expect": ["where are we looking today"], "forbid": []}


def test_run_passes_clean_stream_and_returns_final_text():
    passed, reasons, text = check_run(_stream(), J, 0, False)
    assert passed is True, reasons
    assert text == "Hi — where are we looking today?"


def test_run_fails_on_permission_denials_even_when_text_matches():
    denials = [{"tool_name": "mcp__claude_ai_Parallax__check_api_health", "tool_use_id": "t", "tool_input": {}}]
    passed, reasons, _ = check_run(_stream(denials=denials), J, 0, False)
    assert passed is False
    assert any("permission denials" in r and "check_api_health" in r for r in reasons)


def test_run_fails_on_nonzero_exit_and_timeout():
    passed, reasons, _ = check_run(_stream(), J, 1, True)
    assert passed is False
    assert "timed out" in reasons
    assert any("exited 1" in r for r in reasons)


def test_run_fails_without_result_message():
    passed, reasons, text = check_run(_stream(with_result=False), J, 0, False)
    assert passed is False
    assert text == ""
    assert any("no result message" in r for r in reasons)


def test_run_fails_on_error_result():
    passed, reasons, _ = check_run(_stream(is_error=True, subtype="error_during_execution"), J, 0, False)
    assert passed is False
    assert "result is_error" in reasons


def test_run_fails_without_init_message():
    passed, reasons, _ = check_run(_stream(with_init=False), J, 0, False)
    assert passed is False
    assert any("no init message" in r for r in reasons)


@pytest.mark.parametrize("servers", [
    [],
    [{"name": "claude.ai Gmail", "status": "connected"}],
    [{"name": "plugin:parallax:parallax", "status": "needs-auth"}],
    [{"name": "claude.ai Parallax", "status": "failed"}],
])
def test_run_fails_when_connector_journey_has_no_usable_parallax_server(servers):
    passed, reasons, _ = check_run(_stream(servers=servers), J, 0, False)
    assert passed is False
    assert any("no usable Parallax server" in r for r in reasons)


def test_run_accepts_plugin_server_connected():
    servers = [{"name": "plugin:parallax:parallax", "status": "connected"}]
    passed, reasons, _ = check_run(_stream(servers=servers), J, 0, False)
    assert passed is True, reasons


def test_no_connector_run_fails_when_parallax_server_present():
    j = {**J, "needs": "no-connector"}
    passed, reasons, _ = check_run(_stream(), j, 0, False)
    assert passed is False
    assert any("no-connector run" in r for r in reasons)
    passed2, reasons2, _ = check_run(_stream(servers=[]), j, 0, False)
    assert passed2 is True, reasons2


def test_run_still_applies_substring_checks():
    passed, reasons, _ = check_run(_stream(result="Which role are you?"), {**J, "forbid": ["Which role"]}, 0, False)
    assert passed is False
    assert any("found forbidden" in r for r in reasons)


def test_cli_run_writes_text_and_exit_code(tmp_path, capsys):
    stream = tmp_path / "raw.jsonl"
    stream.write_text(_stream(denials=[{"tool_name": "x"}]))
    out = tmp_path / "out.txt"
    rc = main([json.dumps(J), "--stream", str(stream), "--exit-code", "0", "--text-out", str(out)])
    assert rc == 1
    assert out.read_text() == "Hi — where are we looking today?"
    printed = capsys.readouterr().out
    assert "permission_denials: 1" in printed and "FAIL: permission denials" in printed


def test_successful_parallax_call_proves_connector_absent_from_init():
    # claude.ai connectors can load after the init message is written.
    servers = [{"name": "plugin:parallax:parallax", "status": "needs-auth"}]
    passed, reasons, _ = check_run(
        _stream(servers=servers, tool_call=("mcp__claude_ai_Parallax__check_api_health", False)),
        J, 0, False)
    assert passed is True, reasons


def test_errored_parallax_call_does_not_prove_connector():
    passed, reasons, _ = check_run(
        _stream(servers=[], tool_call=("mcp__claude_ai_Parallax__check_api_health", True)),
        J, 0, False)
    assert passed is False
    assert any("no usable Parallax server" in r for r in reasons)


def test_non_parallax_tool_call_does_not_prove_connector():
    passed, _, _ = check_run(
        _stream(servers=[], tool_call=("mcp__claude_ai_Gmail__list_labels", False)), J, 0, False)
    assert passed is False


def test_no_connector_run_fails_on_any_parallax_tool_call():
    j = {**J, "needs": "no-connector"}
    passed, reasons, _ = check_run(
        _stream(servers=[], tool_call=("mcp__claude_ai_Parallax__check_api_health", True)), j, 0, False)
    assert passed is False
    assert any("Parallax tool called in a no-connector run" in r for r in reasons)
