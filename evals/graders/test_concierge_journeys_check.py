from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json  # noqa: E402

import pytest  # noqa: E402

from concierge_journeys_check import (  # noqa: E402
    check_journey,
    check_run,
    classify_denials,
    documented_helper,
    main,
    parse_stream,
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
                      "J6_uncovered_ticker", "J7_direct_task_bypass", "J8_role_asked_not_guessed",
                      "J9_client_review_policy")


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
    # An ungated skill, so this tests only the required-skill rule.
    j = {**J, "skill": "parallax:parallax-ai-buffett"}
    ok, reasons, _, _ = check_run(_stream(skill="parallax:parallax-ai-buffett"), j, 0, False)
    assert ok is True, reasons
    bad, reasons2, _, _ = check_run(_stream(), j, 0, False)  # concierge ran instead
    assert bad is False
    assert any("parallax:parallax-ai-buffett did not run" in r for r in reasons2)


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


# Journeys that bypass the concierge and the skill each one must run.
DIRECT_SKILL_JOURNEYS = {
    "J7_direct_task_bypass": "parallax:parallax-should-i-buy",
    "J9_client_review_policy": "parallax:parallax-client-review",
}


def test_direct_task_journeys_name_their_skill():
    journeys = {j["id"]: j for j in map(json.loads, filter(str.strip, JOURNEYS.read_text().splitlines()))}
    assert {jid: j["skill"] for jid, j in journeys.items() if "skill" in j} == DIRECT_SKILL_JOURNEYS


def test_the_policy_journey_requires_adaptation():
    journeys = {j["id"]: j for j in map(json.loads, filter(str.strip, JOURNEYS.read_text().splitlines()))}
    assert journeys["J9_client_review_policy"]["require_helpers"] == ["adaptation.py", "render_gate.py"]


# --- denial classes: documented-helper vs improvised commands ----------------

_GATE = ('python3 "/p/skills/parallax-should-i-buy/../_parallax/render_gate.py" '
         '--skill should-i-buy --input "/s/.parallax-render/should-i-buy-0a1b2c3d.md"')
_APPEND = ('python3 "/p/skills/parallax-should-i-buy/../_parallax/house-view/audit_append.py" '
           '--input "/s/.parallax-render/audit-0a1b2c3d.json"')


def _bash_stream(calls, denied_ids, **stream_kw):
    """calls: list of (id, command, is_error); denied_ids: ids also listed as
    permission denials in the result. stream_kw goes to _stream."""
    base = _stream(**stream_kw).rstrip("\n").split("\n")
    result = json.loads(base.pop())
    extra = []
    for cid, cmd, err in calls:
        extra.append(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": cid, "name": "Bash", "input": {"command": cmd}}]}}))
        extra.append(json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": cid, "is_error": err, "content": "x"}]}}))
    result["permission_denials"] = [
        {"tool_name": "Bash", "tool_use_id": cid, "tool_input": {"command": cmd}}
        for cid, cmd, _ in calls if cid in denied_ids]
    return "\n".join(base + extra + [json.dumps(result)]) + "\n"


def test_improvised_doc_read_denial_warns_but_passes():
    cmd = "cd /p/skills/_parallax; sed -n 1,80p parallax-conventions.md"
    stream = _bash_stream([("b1", cmd, True), ("b2", _GATE, False)], {"b1"})
    passed, reasons, _, _ = check_run(stream, J, 0, False)
    assert passed is True, reasons
    blocking, warnings = classify_denials(json.loads(stream.splitlines()[-1])["permission_denials"],
                                          parse_stream(stream)["bash_calls"])
    assert blocking == [] and "improvised" in warnings[0]


def test_documented_helper_command_denied_fails():
    stream = _bash_stream([("b1", _GATE, True)], {"b1"})
    passed, reasons, _, _ = check_run(stream, J, 0, False)
    assert passed is False
    assert any("documented helper command denied" in r for r in reasons)


def test_decorated_helper_denial_passes_only_if_helper_later_ran():
    decorated = _APPEND + '; echo "exit=$?"'
    recovered = _bash_stream([("b1", decorated, True), ("b2", _APPEND, False)], {"b1"})
    assert check_run(recovered, J, 0, False)[0] is True
    stranded = _bash_stream([("b1", decorated, True)], {"b1"})
    passed, reasons, _, _ = check_run(stranded, J, 0, False)
    assert passed is False
    assert any("helper never ran" in r and "audit_append.py" in r for r in reasons)


@pytest.mark.parametrize("cmd,denied", [
    ("printf '%s\\n' '{\"a\":1}' >> \"/hv/audit.jsonl\"", False),
    ("printf x >> \"$PARALLAX_HOUSE_VIEW_DIR/audit.jsonl\"", True),
    ("echo x > /hv/audit.jsonl", False),
    ("echo '{}' | tee -a /hv/audit.jsonl", False),
    ("cp fake.json \"/hv/my dir/audit.jsonl\"", False),
    ("python3 -c \"open('/hv/audit.jsonl','a').write('x')\"", False),
    ("wc -l /hv/audit.jsonl", False),
])
def test_any_shell_command_naming_the_audit_log_fails(cmd, denied):
    stream = _bash_stream([("b1", cmd, denied)], {"b1"} if denied else set())
    passed, reasons, _, _ = check_run(stream, J, 0, False)
    assert passed is False
    assert any("names audit.jsonl" in r for r in reasons)


def test_audit_log_lookalike_names_are_not_flagged():
    stream = _bash_stream([("b1", "ls /hv/audit.jsonl.bak /hv/audit_jsonl", False)], set())
    assert check_run(stream, J, 0, False)[0] is True


@pytest.mark.parametrize("later", [
    'cat "/p/skills/_parallax/render_gate.py"',
    'python3 "/p/skills/_parallax/render_gate.py" --help',
])
def test_recovery_needs_the_documented_command_not_a_mention(later):
    decorated = _GATE + '; echo "exit=$?"'
    stream = _bash_stream([("b1", decorated, True), ("b2", later, False)], {"b1"})
    passed, reasons, _, _ = check_run(stream, J, 0, False)
    assert passed is False
    assert any("helper never ran" in r for r in reasons)



@pytest.mark.parametrize("cmd", [
    "cd /p/skills/_parallax; grep -n render_gate.py parallax-conventions.md",
    "sed -n 1,40p /p/skills/_parallax/render_gate.py",
    "cat /p/skills/_parallax/house-view/audit_append.py",
])
def test_denied_command_that_only_mentions_a_helper_warns_but_passes(cmd):
    stream = _bash_stream([("b1", cmd, True)], {"b1"})
    passed, reasons, _, _ = check_run(stream, J, 0, False)
    assert passed is True, reasons
    blocking, warnings = classify_denials(json.loads(stream.splitlines()[-1])["permission_denials"],
                                          parse_stream(stream)["bash_calls"])
    assert blocking == [] and "improvised" in warnings[0]


def test_a_helper_named_inside_another_path_segment_is_not_that_helper():
    decorated = ('python3 "/s/render_gate.py.d/house-view/audit_append.py" '
                 '--input "/s/.parallax-render/audit-0a1b2c3d.json"; echo "exit=$?"')
    blocking, _ = classify_denials(
        [{"tool_name": "Bash", "tool_use_id": "b1", "tool_input": {"command": decorated}}],
        [{"id": "b1", "ok": False, "seq": 1, "command": decorated}])
    assert blocking == ["helper never ran after its command was denied: ['audit_append.py']"]


def test_non_dict_tool_input_in_a_denial_fails_closed_without_crashing():
    stream = _bash_stream([("b1", "ls", False)], set())
    lines = stream.rstrip("\n").split("\n")
    result = json.loads(lines[-1])
    result["permission_denials"] = [{"tool_name": "Bash", "tool_input": "not a dict"}]
    lines[-1] = json.dumps(result)
    passed, reasons, _, _ = check_run("\n".join(lines) + "\n", J, 0, False)
    assert passed is False and any("permission denials" in r for r in reasons)


def test_cli_prints_warn_lines_for_improvised_denials(tmp_path, capsys):
    stream = tmp_path / "s.jsonl"
    stream.write_text(_bash_stream([("b1", "cd /x; ls", True)], {"b1"}))
    assert main([json.dumps(J), "--stream", str(stream)]) == 0
    out = capsys.readouterr().out
    assert "WARN: improvised Bash command denied" in out and "PASS" in out


GATED = {**J, "skill": "parallax:parallax-should-i-buy"}


def _with_skill(stream, skill="parallax:parallax-should-i-buy"):
    lines = stream.rstrip("\n").split("\n")
    lines[1:1] = [
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "sk2", "name": "Skill", "input": {"skill": skill}}]}}),
        json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "sk2", "is_error": False, "content": "ok"}]}}),
    ]
    return "\n".join(lines) + "\n"





@pytest.mark.parametrize("tool", ["Write", "Edit"])
def test_file_tool_writing_the_audit_log_fails(tool):
    lines = _stream().rstrip("\n").split("\n")
    lines.insert(-1, json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "w1", "name": tool,
         "input": {"file_path": "/s/house-view/audit.jsonl", "content": "{}"}}]}}))
    passed, reasons, _, _ = check_run("\n".join(lines) + "\n", J, 0, False)
    assert passed is False and any("file tool wrote audit.jsonl" in r for r in reasons)


_DRAFT = "/s/.parallax-render/should-i-buy-0a1b2c3d.md"


def _with_write(stream, path=_DRAFT, at=1, wid="w1", error=False, tool="Write", content="# report"):
    """Insert a file-tool call (Write by default) and its result at line ``at``
    (after init by default)."""
    lines = stream.rstrip("\n").split("\n")
    lines[at:at] = [
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": wid, "name": tool,
             "input": {"file_path": path, "content": content}}]}}),
        json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": wid, "is_error": error, "content": "ok"}]}}),
    ]
    return "\n".join(lines) + "\n"


def test_report_draft_gated_with_its_key_passes():
    stream = _with_write(_bash_stream([("b1", _GATE, False)], set()))
    assert check_run(stream, J, 0, False)[0] is True


@pytest.mark.parametrize("calls", [
    [],                                           # draft written, gate never run
    [("b1", _GATE, True)],                        # gate run errored
    [("b1", _GATE.replace("should-i-buy --input", "deep-dive --input"), False)],   # wrong key
    [("b1", _GATE.replace("0a1b2c3d", "ffffffff"), False)],                         # other draft
])
def test_report_draft_not_properly_gated_fails(calls):
    stream = _with_write(_bash_stream(calls, set()))
    passed, reasons, _, _ = check_run(stream, J, 0, False)
    assert passed is False and any("report draft never gated" in r for r in reasons)


def test_gate_failing_once_then_succeeding_passes():
    stream = _with_write(_bash_stream([("b1", _GATE, True), ("b2", _GATE, False)], set()))
    assert check_run(stream, J, 0, False)[0] is True


def test_gated_skill_that_stops_before_drafting_needs_no_gate():
    """J6: should-i-buy cannot resolve the ticker and asks for a RIC (no draft)."""
    stream = _with_skill(_bash_stream([], set()))
    assert check_run(stream, GATED, 0, False)[0] is True


@pytest.mark.parametrize("retry_error", [False, True])
def test_audit_retry_counts_when_it_ran_even_with_a_documented_nonzero_exit(retry_error):
    decorated = _APPEND + '; echo "exit=$?"'
    stream = _bash_stream([("b1", decorated, True), ("b2", _APPEND, retry_error)], {"b1"})
    assert check_run(stream, J, 0, False)[0] is True


def test_helper_name_must_be_the_documented_one_not_a_path_mention():
    fake = ('python3 "/s/render_gate.py.d/house-view/audit_append.py" '
            '--input "/s/.parallax-render/audit-0a1b2c3d.json"')
    assert documented_helper(fake) == "audit_append.py"
    assert documented_helper(_GATE) == "render_gate.py"
    assert documented_helper(_GATE + "; echo hi") is None


def test_rewrite_after_the_gate_must_be_gated_again():
    gated = _with_write(_bash_stream([("b1", _GATE, False)], set()))
    rewritten = _with_write(gated, at=len(gated.rstrip("\n").split("\n")) - 1, wid="w2")
    passed, reasons, _, _ = check_run(rewritten, J, 0, False)
    assert passed is False and any("report draft never gated" in r for r in reasons)


def test_path_spellings_of_the_same_draft_match():
    var_gate = _GATE.replace('"/s/.parallax-render', '"/var/folders/x//.parallax-render')
    stream = _with_write(_bash_stream([("b1", var_gate, False)], set()),
                         path="/private/var/folders/x/.parallax-render/should-i-buy-0a1b2c3d.md")
    assert check_run(stream, J, 0, False)[0] is True


def test_a_failed_write_leaves_nothing_to_gate():
    stream = _with_write(_bash_stream([], set()), error=True)
    assert check_run(stream, J, 0, False)[0] is True


def test_a_backup_named_like_a_draft_is_not_a_draft():
    stream = _with_write(_bash_stream([], set()), path=_DRAFT + ".bak")
    assert check_run(stream, J, 0, False)[0] is True


# --- Literal draft paths for the policy and coverage helpers (#154/#159 pattern) --

_ADAPT_FULL = ('python3 "/p/skills/parallax-client-review/../_parallax/client-policy/adaptation.py" '
               '--policy "/s/.parallax-policy/policy-0a1b2c3d.yaml" '
               '--exposures "/s/.parallax-policy/exposures-0a1b2c3d.json" '
               '--view-tilts "/s/.parallax-policy/tilts-0a1b2c3d.json" --json')
_ADAPT_POLICY_ONLY = ('python3 "/p/skills/parallax-client-review/../_parallax/client-policy/adaptation.py" '
                      '--policy "/s/.parallax-policy/policy-0a1b2c3d.yaml" --json')
_COVERAGE = ('python3 "/p/skills/parallax-client-review/../_parallax/coverage_check.py" '
             '--portfolio-sectors "/s/.parallax-policy/portfolio-sectors-0a1b2c3d.json" '
             '--redundancy-sectors "/s/.parallax-policy/redundancy-sectors-0a1b2c3d.json" '
             '--holdings "/s/.parallax-policy/holdings-0a1b2c3d.json"')
_RECONCILE = ('python3 "/p/skills/parallax-rebalance/../_parallax/client-policy/reconcile.py" '
              '--input "/s/.parallax-policy/reconcile-0a1b2c3d.json"')


@pytest.mark.parametrize("cmd,helper", [
    (_ADAPT_FULL, "adaptation.py"),
    (_ADAPT_POLICY_ONLY, "adaptation.py"),
    (_COVERAGE, "coverage_check.py"),
    (_RECONCILE, "reconcile.py"),
    (_GATE, "render_gate.py"),
    (_APPEND, "audit_append.py"),
])
def test_documented_helper_recognizes_every_helper_shape(cmd, helper):
    assert documented_helper(cmd) == helper
    assert documented_helper(cmd + "; echo hi") is None


def test_documented_new_helper_command_denied_fails():
    stream = _bash_stream([("b1", _ADAPT_FULL, True)], {"b1"})
    passed, reasons, _, _ = check_run(stream, J, 0, False)
    assert passed is False
    assert any("documented helper command denied" in r for r in reasons)


def test_decorated_adaptation_denial_passes_only_if_helper_later_ran():
    decorated = _ADAPT_FULL + '; echo "exit=$?"'
    recovered = _bash_stream([("b1", decorated, True), ("b2", _ADAPT_FULL, False)], {"b1"})
    assert check_run(recovered, J, 0, False)[0] is True
    stranded = _bash_stream([("b1", decorated, True)], {"b1"})
    passed, reasons, _, _ = check_run(stranded, J, 0, False)
    assert passed is False
    assert any("helper never ran" in r and "adaptation.py" in r for r in reasons)


def test_policy_draft_consumed_by_a_later_helper_run_passes():
    stream = _with_write(
        _bash_stream([("b1", _ADAPT_FULL, False)], set()),
        path="/s/.parallax-policy/policy-0a1b2c3d.yaml",
    )
    assert check_run(stream, J, 0, False)[0] is True


@pytest.mark.parametrize("calls", [
    [],                                               # draft written, helper never run
    [("b1", _ADAPT_FULL.replace("0a1b2c3d", "ffffffff"), False)],   # different draft suffix
])
def test_policy_draft_never_consumed_fails(calls):
    stream = _with_write(
        _bash_stream(calls, set()),
        path="/s/.parallax-policy/policy-0a1b2c3d.yaml",
    )
    passed, reasons, _, _ = check_run(stream, J, 0, False)
    assert passed is False
    assert any("policy draft never consumed" in r for r in reasons)


def test_coverage_check_draft_consumed_passes():
    stream = _with_write(
        _bash_stream([("b1", _COVERAGE, False)], set()),
        path="/s/.parallax-policy/holdings-0a1b2c3d.json",
    )
    assert check_run(stream, J, 0, False)[0] is True


def test_policy_gitignore_write_is_not_a_draft_and_needs_no_consumer():
    stream = _with_write(_bash_stream([], set()), path="/s/.parallax-policy/.gitignore")
    assert check_run(stream, J, 0, False)[0] is True


def test_policy_draft_consumed_despite_a_documented_nonzero_exit():
    """adaptation.py exit 2 (unparseable inline policy, policy-loader.md §2)
    and reconcile.py exit 3/4/5 (conflict/infeasible/solver_unavailable,
    policy-reconciliation.md step 3) are documented rendered outcomes, not
    permission denials -- a nonzero exit alone must not orphan the draft.
    Mirrors ``test_audit_retry_counts_when_it_ran_even_with_a_documented_nonzero_exit``."""
    stream = _with_write(
        _bash_stream([("b1", _RECONCILE, True)], set()),  # error=True, never denied
        path="/s/.parallax-policy/reconcile-0a1b2c3d.json",
    )
    assert check_run(stream, J, 0, False)[0] is True


@pytest.mark.parametrize("cmd", [
    'python3 "/p/skills/parallax-client-review/../_parallax/client-policy/adaptation.py" '
    '--policy "/s/.parallax-policy/policy-0a1b2c3d.yaml" '
    '--exposures "/s/.parallax-policy/exposures-0a1b2c3d.json" --json',
    'python3 "/p/skills/parallax-client-review/../_parallax/client-policy/adaptation.py" '
    '--policy "/s/.parallax-policy/policy-0a1b2c3d.yaml" '
    '--view-tilts "/s/.parallax-policy/tilts-0a1b2c3d.json" --json',
])
def test_adaptation_accepts_exposures_or_view_tilts_independently(cmd):
    """adaptation.py's CLI defaults each of --exposures/--view-tilts to None
    independently; client-review Step 4 item 2 only assembles tilts when a
    house view is active, so an exposures-only call is a real, documented
    shape and must not fall into the improvised bucket."""
    assert documented_helper(cmd) == "adaptation.py"


# --- require_helpers: a policy journey needs its helper to really run --------

_POLICY_PATH = "/s/.parallax-policy/policy-0a1b2c3d.yaml"
_ADAPT_ON_DRAFT = ('python3 "/p/skills/parallax-client-review/../_parallax/client-policy/adaptation.py" '
                   f'--policy "{_POLICY_PATH}" --json')
JR = {**J, "require_helpers": ["adaptation.py"]}


def test_a_required_helper_that_ran_on_a_written_draft_passes():
    stream = _with_write(_bash_stream([("b1", _ADAPT_ON_DRAFT, False)], set()), path=_POLICY_PATH)
    assert check_run(stream, JR, 0, False)[0] is True


@pytest.mark.parametrize("calls,denied,write_path,why", [
    ([], set(), _POLICY_PATH, "never ran"),
    ([("b1", _ADAPT_ON_DRAFT, True)], set(), _POLICY_PATH, "errored"),
    ([("b1", _ADAPT_ON_DRAFT, False)], {"b1"}, _POLICY_PATH, "denied"),
    ([("b1", _ADAPT_ON_DRAFT, False)], set(), None, "no Write-tool draft (heredoc)"),
    ([("b1", _ADAPT_ON_DRAFT.replace("/s/.parallax-policy/", "/tmp/"), False)], set(),
     "/tmp/policy-0a1b2c3d.yaml", "draft outside .parallax-policy"),
    ([("b1", 'cd /p && python3 adaptation.py --policy "' + _POLICY_PATH + '" --json', False)],
     set(), _POLICY_PATH, "improvised command"),
])
def test_a_required_helper_fails_unless_it_really_ran(calls, denied, write_path, why):
    stream = _bash_stream(calls, denied)
    if write_path:
        stream = _with_write(stream, path=write_path)
    passed, reasons, _, _ = check_run(stream, JR, 0, False)
    assert passed is False, why
    assert any("required helper adaptation.py" in r for r in reasons), (why, reasons)


def test_a_draft_written_after_the_run_does_not_satisfy_the_requirement():
    stream = _bash_stream([("b1", _ADAPT_ON_DRAFT, False)], set())
    stream = _with_write(stream, path=_POLICY_PATH, at=len(stream.rstrip("\n").split("\n")) - 1)
    passed, reasons, _, _ = check_run(stream, JR, 0, False)
    assert passed is False
    assert any("required helper adaptation.py" in r for r in reasons)


@pytest.mark.parametrize("value,ok", [
    (["adaptation.py"], True),
    (["coverage_check.py", "reconcile.py"], True),
    (["render_gate.py"], False),
    (["audit_append.py"], False),
    ("adaptation.py", False),
])
def test_require_helpers_is_validated(value, ok):
    journey = {"id": "J", "prompt": "p", "require_helpers": value}
    assert (validate_journey(journey) == []) is ok


def test_require_render_gate_needs_a_skill_key():
    journey = {"id": "J", "prompt": "p", "skill": "parallax:parallax-client-review",
               "require_helpers": ["render_gate.py"]}
    assert validate_journey(journey) == []


# --- relative and bare helper arguments; no model-written code ------------------

_SCRATCH = "/s"


def _with_cwd(stream, cwd=_SCRATCH):
    lines = stream.rstrip("\n").split("\n")
    init = json.loads(lines[0])
    init["cwd"] = cwd
    lines[0] = json.dumps(init)
    return "\n".join(lines) + "\n"


_ADAPT_RELATIVE = ("python3 /p/skills/parallax-client-review/../_parallax/client-policy/adaptation.py "
                   "--policy .parallax-policy/policy-0a1b2c3d.json --json")


def test_a_bare_relative_helper_command_is_documented_and_consumes_the_draft():
    assert documented_helper(_ADAPT_RELATIVE) == "adaptation.py"
    stream = _with_cwd(_with_write(_bash_stream([("b1", _ADAPT_RELATIVE, False)], set()),
                                   path="/s/.parallax-policy/policy-0a1b2c3d.json"))
    passed, reasons, _, _ = check_run(stream, {**J, "require_helpers": ["adaptation.py"]}, 0, False)
    assert passed is True, reasons


def test_without_the_run_cwd_a_relative_argument_does_not_match_the_draft():
    stream = _with_write(_bash_stream([("b1", _ADAPT_RELATIVE, False)], set()),
                         path="/s/.parallax-policy/policy-0a1b2c3d.json")
    passed, reasons, _, _ = check_run(stream, J, 0, False)
    assert passed is False
    assert any("policy draft never consumed" in r for r in reasons)


@pytest.mark.parametrize("cmd", [
    "python3 /p/x/evil.py --policy .parallax-policy/policy-0a1b2c3d.json --json",
    'python3 "/p/client-policy/adaptation.py" --policy $POLICY --json',
    "python3 /p/client-policy/adaptation.py --policy .parallax-policy/p-0a1b2c3d.json;touch x --json",
    "python3 /p/client-policy/adaptation.py --policy `x` --json",
])
def test_lookalike_or_expanding_commands_are_not_documented(cmd):
    assert documented_helper(cmd) is None


def test_running_a_script_the_model_wrote_fails():
    stream = _with_cwd(_with_write(
        _bash_stream([("b1", "python3 .parallax-policy/gate-0a1b2c3d.json", False)], set()),
        path="/s/.parallax-policy/gate-0a1b2c3d.json"))
    passed, reasons, _, _ = check_run(stream, J, 0, False)
    assert passed is False
    assert any("ran a script the model wrote" in r for r in reasons)


@pytest.mark.parametrize("cmd", [
    "python3 /s/tools/gate.py", "bash /s/tools/gate.py", "./tools/gate.py",
    "python3 -u /s/tools/gate.py", "bash -x /s/tools/gate.py", "(python3 /s/tools/gate.py)",
    "bash -c 'python3 /s/tools/gate.py'", "tools/gate.py", "/s/tools/gate.py",
    "cd /s && tools/gate.py",
])
def test_every_way_of_running_a_written_script_is_caught(cmd):
    stream = _with_cwd(_with_write(_bash_stream([("b1", cmd, False)], set()), path="/s/tools/gate.py"))
    passed, reasons, _, _ = check_run(stream, J, 0, False)
    assert passed is False
    assert any("ran a script the model wrote" in r for r in reasons), reasons


def test_a_denied_run_of_a_written_script_is_not_counted_as_run():
    stream = _with_cwd(_with_write(_bash_stream([("b1", "python3 /s/tools/gate.py", False)], {"b1"}),
                                   path="/s/tools/gate.py"))
    _, reasons, _, _ = check_run(stream, J, 0, False)
    assert not any("ran a script the model wrote" in r for r in reasons)


@pytest.mark.parametrize("path", [
    "/s/.parallax-policy/gate.py", "/s/.parallax-policy/draft-0a1b2c3d.md", "/s/.parallax-policy/notes.txt",
])
def test_a_non_draft_file_in_parallax_policy_fails(path):
    stream = _with_cwd(_with_write(_bash_stream([], set()), path=path))
    passed, reasons, _, _ = check_run(stream, J, 0, False)
    assert passed is False
    assert any("non-draft file written into .parallax-policy" in r for r in reasons)


# --- required render gate; literal, plugin-anchored helper runs ---------------

_CR = "parallax:parallax-client-review"
_PLUG = "/repo/plugin"
_CR_GATE_SCRIPT = f"{_PLUG}/skills/parallax-client-review/../_parallax/render_gate.py"
_CR_DRAFT = "/s/.parallax-render/client-review-0a1b2c3d.md"
_CR_GATE = f'python3 "{_CR_GATE_SCRIPT}" --skill client-review --input "{_CR_DRAFT}"'
_CR_REPORT = "## Portfolio Summary\nok"
_CR_GATE_STDIN = f"python3 \"{_CR_GATE_SCRIPT}\" --skill client-review <<'REPORT'\n{_CR_REPORT}\nREPORT"
JG = {**J, "expect": [], "skill": _CR, "require_helpers": ["render_gate.py"]}


def _gate_run(calls, denied=frozenset(), draft=_CR_DRAFT, tool="Write", shown=_CR_REPORT,
              content="Preamble.\n" + _CR_REPORT):
    """A client-review run whose final answer is ``shown`` and whose report
    draft (when ``draft``) holds ``content``."""
    stream = _bash_stream(calls, set(denied), skill=_CR, result=shown)
    if draft:
        stream = _with_write(stream, path=draft, tool=tool, content=content)
    return _with_cwd(stream)


@pytest.mark.parametrize("calls,draft", [
    ([("b1", _CR_GATE, False)], _CR_DRAFT),
    ([("b1", _CR_GATE_STDIN, False)], None),
])
def test_a_required_gate_passes_by_draft_or_stdin(calls, draft):
    passed, reasons, _, _ = check_run(_gate_run(calls, draft=draft), JG, 0, False, plugin_dir=_PLUG)
    assert passed is True, reasons


@pytest.mark.parametrize("calls,draft,tool,why", [
    ([], None, "Write", "no gate run and no draft"),
    ([("b1", _CR_GATE, True)], _CR_DRAFT, "Write", "gate errored"),
    ([("b1", _CR_GATE.replace("client-review", "deep-dive"), False)],
     _CR_DRAFT.replace("client-review", "deep-dive"), "Write", "another skill's key"),
    ([("b1", _CR_GATE, False)], _CR_DRAFT, "Edit", "draft made by Edit"),
    ([("b1", _CR_GATE.replace(_CR_GATE_SCRIPT, "/s/tools/_parallax/render_gate.py"), False)],
     _CR_DRAFT, "Write", "gate script outside the plugin"),
    ([("b1", _CR_GATE_STDIN + "\ntouch x\nREPORT", False)], None, "Write", "heredoc ends early"),
])
def test_a_required_gate_fails_unless_the_real_gate_ran(calls, draft, tool, why):
    passed, reasons, _, _ = check_run(_gate_run(calls, draft=draft, tool=tool), JG, 0, False, plugin_dir=_PLUG)
    assert passed is False, why
    assert any("required helper render_gate.py" in r for r in reasons), (why, reasons)


def test_a_denied_stdin_gate_recovered_by_a_draft_gate_is_not_blocking():
    stream = _gate_run([("b1", _CR_GATE_STDIN, False), ("b2", _CR_GATE, False)], denied={"b1"})
    passed, reasons, _, _ = check_run(stream, JG, 0, False, plugin_dir=_PLUG)
    assert passed is True, reasons


def test_a_denied_stdin_gate_never_recovered_is_blocking():
    stream = _gate_run([("b1", _CR_GATE_STDIN, False)], denied={"b1"}, draft=None)
    passed, reasons, _, _ = check_run(stream, JG, 0, False, plugin_dir=_PLUG)
    assert passed is False
    assert any("helper never ran after its command was denied" in r for r in reasons), reasons


@pytest.mark.parametrize("cmd", [
    'python3 "$PWD/tools/render_gate.py" --skill client-review --input "/s/.parallax-render/client-review-0a1b2c3d.md"',
    'python3 "/p/_parallax/render_gate.py" --skill client-review --input "$(cd x;pwd)/../d.md"',
    'python3 "/p/client-policy/adaptation.py" --policy "$HOME/../.parallax-policy/policy-0a1b2c3d.json" --json',
    'python3 "/p/client-policy/adaptation.py" --policy "`pwd`/policy-0a1b2c3d.json" --json',
])
def test_quoted_arguments_that_expand_are_not_documented(cmd):
    assert documented_helper(cmd) is None


def test_a_fake_helper_outside_the_plugin_is_not_credited():
    cmd = f'python3 "/s/tools/client-policy/adaptation.py" --policy "{_POLICY_PATH}" --json'
    stream = _with_write(_bash_stream([("b1", cmd, False)], set(), plugin_path=_PLUG), path=_POLICY_PATH)
    passed, reasons, _, _ = check_run(stream, JR, 0, False, plugin_dir=_PLUG)
    assert passed is False
    assert any("required helper adaptation.py" in r for r in reasons), reasons


def test_without_plugin_dir_a_documented_helper_is_credited_anywhere():
    cmd = f'python3 "/s/tools/client-policy/adaptation.py" --policy "{_POLICY_PATH}" --json'
    stream = _with_write(_bash_stream([("b1", cmd, False)], set()), path=_POLICY_PATH)
    assert check_run(stream, JR, 0, False)[0] is True


def test_a_required_helper_needs_its_primary_argument_to_be_the_draft():
    exposures = "/s/.parallax-policy/exposures-11111111.json"
    cmd = ('python3 "/p/skills/parallax-client-review/../_parallax/client-policy/adaptation.py" '
           f'--policy "/s/tampered.json" --exposures "{exposures}" --json')
    stream = _with_write(_bash_stream([("b1", cmd, False)], set()), path=exposures)
    passed, reasons, _, _ = check_run(stream, JR, 0, False)
    assert passed is False
    assert any("required helper adaptation.py" in r for r in reasons), reasons


@pytest.mark.parametrize("tool", ["Edit", "MultiEdit"])
def test_a_policy_draft_made_by_an_edit_tool_does_not_satisfy_the_requirement(tool):
    stream = _with_write(_bash_stream([("b1", _ADAPT_ON_DRAFT, False)], set()), path=_POLICY_PATH, tool=tool)
    passed, reasons, _, _ = check_run(stream, JR, 0, False)
    assert passed is False
    assert any("required helper adaptation.py" in r for r in reasons), reasons


@pytest.mark.parametrize("extra", [
    None,
    "cat ./.parallax-policy/policy-0a1b2c3d.json",
    "grep -c python /s/.parallax-policy/policy-0a1b2c3d.json",
    "du -sh /s/.parallax-policy/policy-0a1b2c3d.json",
])
def test_naming_a_draft_is_not_running_a_script(extra):
    adapt = _ADAPT_RELATIVE.replace("--policy .parallax-policy/", "--policy ./.parallax-policy/")
    calls = [("b1", adapt, False)] + ([("b2", extra, False)] if extra else [])
    stream = _with_cwd(_with_write(_bash_stream(calls, set()), path="/s/.parallax-policy/policy-0a1b2c3d.json"))
    passed, reasons, _, _ = check_run(stream, {**J, "require_helpers": ["adaptation.py"]}, 0, False)
    assert passed is True, reasons


def test_a_stdin_gate_report_line_is_not_a_command():
    stdin = _CR_GATE_STDIN.replace(_CR_REPORT, "/s/notes.md was the source")
    stream = _with_write(_gate_run([("b1", stdin, False)], draft=None, shown="/s/notes.md was the source"),
                         path="/s/notes.md", wid="w2")
    passed, reasons, _, _ = check_run(stream, JG, 0, False, plugin_dir=_PLUG)
    assert passed is True, reasons


@pytest.mark.parametrize("calls,draft,content", [
    # the full stdin report is denied; a stub goes through the gate instead
    ([("b1", _CR_GATE_STDIN.replace(_CR_REPORT, _CR_REPORT + "\n{\"a\": 1}"), False),
      ("b2", _CR_GATE_STDIN.replace(_CR_REPORT, "# x\nok"), False)], None, None),
    # a stub draft is gated and the final answer is something else
    ([("b1", _CR_GATE, False)], _CR_DRAFT, "# x\nok"),
])
def test_a_required_gate_must_have_gated_the_final_answer(calls, draft, content):
    denied = {"b1"} if draft is None else set()
    kw = {} if content is None else {"content": content}
    stream = _gate_run(calls, denied=denied, draft=draft, **kw)
    passed, reasons, _, _ = check_run(stream, JG, 0, False, plugin_dir=_PLUG)
    assert passed is False
    assert any("required helper render_gate.py" in r for r in reasons), reasons


def test_a_denied_stdin_report_that_mentions_a_helper_is_not_a_helper_run():
    body = _CR_GATE_STDIN.replace(_CR_REPORT, _CR_REPORT + "\nran python3 adaptation.py ok")
    stream = _gate_run([("b1", body, False), ("b2", _CR_GATE, False)], denied={"b1"})
    passed, reasons, _, _ = check_run(stream, JG, 0, False, plugin_dir=_PLUG)
    assert passed is True, reasons


def test_a_required_gate_accepts_the_degraded_note_the_gate_moves():
    draft = "Batch 3 done; get_assessment unavailable for AAPL.O.\n" + _CR_REPORT
    shown = _CR_REPORT + "\n\n> _Status note (preserved): Batch 3 done; get_assessment unavailable for AAPL.O._"
    stream = _gate_run([("b1", _CR_GATE, False)], content=draft, shown=shown)
    passed, reasons, _, _ = check_run(stream, JG, 0, False, plugin_dir=_PLUG)
    assert passed is True, reasons


@pytest.mark.parametrize("shown", [
    "Scaffold: batch 1 done.\n" + _CR_REPORT,   # the raw draft instead of the gate output
    "ok",                                         # a piece of the gate output
])
def test_a_required_gate_rejects_text_the_gate_did_not_output(shown):
    stream = _gate_run([("b1", _CR_GATE, False)], content="Scaffold: batch 1 done.\n" + _CR_REPORT, shown=shown)
    passed, reasons, _, _ = check_run(stream, JG, 0, False, plugin_dir=_PLUG)
    assert passed is False
    assert any("required helper render_gate.py" in r for r in reasons), reasons
