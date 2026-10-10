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
            tool_call=None, skill="parallax:parallax-concierge", skill_error=False,
            texts=None, plugin_path="/repo/plugin"):
    """tool_call: (tool_name, result_is_error) for one tool_use/tool_result pair.
    skill: the Skill tool's requested skill (None: no Skill call).
    texts: assistant text blocks before the result (default: the result text)."""
    lines = []
    if with_init:
        lines.append(json.dumps({"type": "system", "subtype": "init",
                                 "plugins": [{"name": "parallax", "path": plugin_path}],
                                 "mcp_servers": servers if servers is not None else
                                 [{"name": "claude.ai Parallax", "status": "connected"}]}))
    if skill is not None:
        lines.append(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "sk1", "name": "Skill", "input": {"skill": skill}}]}}))
        lines.append(json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "sk1", "is_error": skill_error,
             "content": "Launching skill"}]}}))
    if tool_call:
        name, err = tool_call
        lines.append(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "tu1", "name": name, "input": {}}]}}))
        lines.append(json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "tu1", "is_error": err, "content": "x"}]}}))
    for text in (texts if texts is not None else [result]):
        lines.append(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": text}]}}))
    if with_result:
        lines.append(json.dumps({"type": "result", "subtype": subtype, "is_error": is_error,
                                 "result": result, "permission_denials": denials or []}))
    return "\n".join(lines) + "\n"


J = {"id": "J5", "prompt": "Hi Parallax", "expect": ["where are we looking today"], "forbid": []}


def test_run_passes_clean_stream_and_returns_final_text():
    passed, reasons, text, _ = check_run(_stream(), J, 0, False)
    assert passed is True, reasons
    assert text == "Hi — where are we looking today?"


def test_run_fails_on_permission_denials_even_when_text_matches():
    denials = [{"tool_name": "mcp__claude_ai_Parallax__check_api_health", "tool_use_id": "t", "tool_input": {}}]
    passed, reasons, _, _ = check_run(_stream(denials=denials), J, 0, False)
    assert passed is False
    assert any("permission denials" in r and "check_api_health" in r for r in reasons)


def test_run_fails_on_nonzero_exit_and_timeout():
    passed, reasons, _, _ = check_run(_stream(), J, 1, True)
    assert passed is False
    assert "timed out" in reasons
    assert any("exited 1" in r for r in reasons)


def test_run_fails_without_result_message():
    passed, reasons, text, _ = check_run(_stream(with_result=False), J, 0, False)
    assert passed is False
    assert text == ""
    assert any("no result message" in r for r in reasons)


def test_run_fails_on_error_result():
    passed, reasons, _, _ = check_run(_stream(is_error=True, subtype="error_during_execution"), J, 0, False)
    assert passed is False
    assert "result is_error" in reasons


def test_run_fails_without_init_message():
    passed, reasons, _, _ = check_run(_stream(with_init=False), J, 0, False)
    assert passed is False
    assert any("no init message" in r for r in reasons)


@pytest.mark.parametrize("servers", [
    [],
    [{"name": "claude.ai Gmail", "status": "connected"}],
    [{"name": "plugin:parallax:parallax", "status": "needs-auth"}],
    [{"name": "claude.ai Parallax", "status": "failed"}],
    [{"name": "claude.ai Parallax", "status": "pending"}],
])
def test_run_fails_when_connector_journey_has_no_connected_parallax_server(servers):
    passed, reasons, _, _ = check_run(_stream(servers=servers), J, 0, False)
    assert passed is False
    assert any("no connected Parallax server" in r for r in reasons)


def test_run_accepts_plugin_server_connected():
    servers = [{"name": "plugin:parallax:parallax", "status": "connected"}]
    passed, reasons, _, _ = check_run(_stream(servers=servers), J, 0, False)
    assert passed is True, reasons


def test_no_connector_run_fails_when_parallax_server_present():
    j = {**J, "needs": "no-connector"}
    passed, reasons, _, _ = check_run(_stream(), j, 0, False)
    assert passed is False
    assert any("no-connector run" in r for r in reasons)
    passed2, reasons2, _, _ = check_run(_stream(servers=[]), j, 0, False)
    assert passed2 is True, reasons2


def test_run_still_applies_substring_checks():
    passed, reasons, _, _ = check_run(_stream(result="Which role are you?"), {**J, "forbid": ["Which role"]}, 0, False)
    assert passed is False
    assert any("found forbidden" in r for r in reasons)


def test_cli_run_writes_text_and_exit_code(tmp_path, capsys):
    stream = tmp_path / "raw.jsonl"
    stream.write_text(_stream(denials=[{"tool_name": "x"}],
                              texts=["Checking your connection.", "Hi — where are we looking today?"]))
    out = tmp_path / "out.txt"
    rc = main([json.dumps(J), "--stream", str(stream), "--exit-code", "0", "--text-out", str(out)])
    assert rc == 1
    written = out.read_text()
    assert "Checking your connection." in written and "where are we looking today" in written
    printed = capsys.readouterr().out
    assert "permission_denials: 1" in printed and "FAIL: permission denials" in printed


def test_successful_parallax_call_proves_connector_absent_from_init():
    # claude.ai connectors can load after the init message is written.
    servers = [{"name": "plugin:parallax:parallax", "status": "needs-auth"}]
    passed, reasons, _, _ = check_run(
        _stream(servers=servers, tool_call=("mcp__claude_ai_Parallax__check_api_health", False)),
        J, 0, False)
    assert passed is True, reasons


def test_errored_parallax_call_does_not_prove_connector():
    passed, reasons, _, _ = check_run(
        _stream(servers=[], tool_call=("mcp__claude_ai_Parallax__check_api_health", True)),
        J, 0, False)
    assert passed is False
    assert any("no connected Parallax server" in r for r in reasons)


def test_non_parallax_tool_call_does_not_prove_connector():
    passed, _, _, _ = check_run(
        _stream(servers=[], tool_call=("mcp__claude_ai_Gmail__list_labels", False)), J, 0, False)
    assert passed is False


def test_no_connector_run_fails_on_any_parallax_tool_call():
    j = {**J, "needs": "no-connector"}
    passed, reasons, _, _ = check_run(
        _stream(servers=[], tool_call=("mcp__claude_ai_Parallax__check_api_health", True)), j, 0, False)
    assert passed is False
    assert any("Parallax tool called in a no-connector run" in r for r in reasons)


# --- round 2: concierge skill, forbid on all text, connector-optional --------

def test_run_fails_when_concierge_skill_not_called():
    passed, reasons, _, _ = check_run(_stream(skill=None), J, 0, False)
    assert passed is False
    assert any("parallax:parallax-concierge did not run" in r for r in reasons)


def test_run_fails_when_a_different_skill_ran():
    passed, reasons, _, _ = check_run(_stream(skill="parallax-concierge"), J, 0, False)
    assert passed is False
    assert any("did not run" in r and "parallax-concierge" in r for r in reasons)


def test_run_fails_when_concierge_skill_errored():
    passed, reasons, _, _ = check_run(_stream(skill_error=True), J, 0, False)
    assert passed is False
    assert any("did not run" in r for r in reasons)


def test_run_checks_plugin_path_when_given():
    ok, reasons, _, _ = check_run(_stream(), J, 0, False, plugin_dir="/repo/plugin")
    assert ok is True, reasons
    bad, reasons2, _, _ = check_run(_stream(plugin_path="/elsewhere"), J, 0, False, plugin_dir="/repo/plugin")
    assert bad is False
    assert any("not loaded" in r for r in reasons2)


def test_forbid_applies_to_earlier_assistant_text():
    stream = _stream(texts=["Run `/mcp` and authenticate Parallax.", "Hi — where are we looking today?"])
    passed, reasons, final, all_text = check_run(stream, {**J, "forbid": ["/mcp"]}, 0, False)
    assert passed is False
    assert any("found forbidden: '/mcp'" in r for r in reasons)
    assert final == "Hi — where are we looking today?"
    assert "/mcp" in all_text and final in all_text


def test_expect_reads_only_the_final_answer():
    stream = _stream(texts=["where are we looking today", "Something else."], result="Something else.")
    passed, reasons, _, _ = check_run(stream, J, 0, False)
    assert passed is False
    assert any("missing expect" in r for r in reasons)


def test_connector_optional_skips_only_server_presence():
    j = {**J, "needs": "connector-optional"}
    passed, reasons, _, _ = check_run(_stream(servers=[]), j, 0, False)
    assert passed is True, reasons
    denials = [{"tool_name": "Bash"}]
    passed2, reasons2, _, _ = check_run(_stream(servers=[], denials=denials, skill=None), j, 3, False)
    assert passed2 is False
    assert any("permission denials" in r for r in reasons2)
    assert any("exited 3" in r for r in reasons2)
    assert any("did not run" in r for r in reasons2)


def test_validate_accepts_connector_optional():
    assert validate_journey({**VALID, "needs": "connector-optional"}) == []


CONNECTOR_JOURNEYS = ("J1_research_connected", "J3_integrator", "J4_rm_support_schedule",
                      "J6_uncovered_ticker", "J7_direct_task_bypass", "J8_role_asked_not_guessed")


# Phrases of the concierge's not-connected state. "/mcp" itself is not one:
# a correct connected run can mention it when a second, signed-out Parallax
# connector is loaded.
NOT_CONNECTED_MARKERS = ("To connect", "No connection needed")


def test_every_connector_journey_forbids_the_not_connected_state():
    journeys = {j["id"]: j for j in map(json.loads, filter(str.strip, JOURNEYS.read_text().splitlines()))}
    assert set(CONNECTOR_JOURNEYS) == {jid for jid, j in journeys.items() if "needs" not in j}
    for jid in CONNECTOR_JOURNEYS:
        assert set(NOT_CONNECTED_MARKERS) <= set(journeys[jid]["forbid"]), jid


def test_pending_server_passes_only_with_a_successful_parallax_call():
    pending = [{"name": "claude.ai Parallax", "status": "pending"}]
    ok, reasons, _, _ = check_run(
        _stream(servers=pending, tool_call=("mcp__claude_ai_Parallax__check_api_health", False)), J, 0, False)
    assert ok is True, reasons
    bad, _, _, _ = check_run(
        _stream(servers=pending, tool_call=("mcp__claude_ai_Parallax__check_api_health", True)), J, 0, False)
    assert bad is False


# --- round 3: required skill per journey --------------------------------------

def test_validate_skill_field():
    assert validate_journey({**VALID, "skill": "parallax:parallax-should-i-buy"}) == []
    for bad in ("parallax-should-i-buy", "parallax:", 3, ["parallax:x"]):
        assert any("'skill'" in p for p in validate_journey({**VALID, "skill": bad})), bad


def test_required_skill_from_journey_field():
    j = {**J, "skill": "parallax:parallax-should-i-buy"}
    ok, reasons, _, _ = check_run(_stream(skill="parallax:parallax-should-i-buy"), j, 0, False)
    assert ok is True, reasons
    bad, reasons2, _, _ = check_run(_stream(), j, 0, False)  # concierge ran instead
    assert bad is False
    assert any("parallax:parallax-should-i-buy did not run" in r for r in reasons2)


def test_unprefixed_parallax_skill_fails_even_with_required_skill():
    lines = _stream().splitlines()
    extra = [
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "sk2", "name": "Skill", "input": {"skill": "parallax-should-i-buy"}}]}}),
        json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "sk2", "content": "ok"}]}}),
    ]
    stream = "\n".join(lines[:-1] + extra + lines[-1:]) + "\n"
    ok, reasons, _, _ = check_run(stream, J, 0, False)
    assert ok is False
    assert any("unprefixed Parallax skill" in r and "parallax-should-i-buy" in r for r in reasons)


def test_no_plugin_namespace_skill_fails():
    ok, reasons, _, _ = check_run(_stream(skill="other:thing"), {**J, "skill": "parallax:x"}, 0, False)
    assert ok is False
    assert any("plugin namespace" in r for r in reasons)


def test_direct_task_journey_requires_should_i_buy():
    journeys = {j["id"]: j for j in map(json.loads, filter(str.strip, JOURNEYS.read_text().splitlines()))}
    assert journeys["J7_direct_task_bypass"]["skill"] == "parallax:parallax-should-i-buy"
    assert all("skill" not in j for jid, j in journeys.items() if jid != "J7_direct_task_bypass")
