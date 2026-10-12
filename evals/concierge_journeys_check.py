"""evals/concierge_journeys_check.py — checker for the live concierge journeys
(see evals/concierge_journeys.sh and evals/tasks/concierge/journeys.jsonl).

Pure functions, no I/O:

- ``validate_journey(journey)`` rejects a journey line with unknown keys or
  with ``expect``/``forbid``/``expect_any`` that is not a list of strings.
- ``check_journey(output, journey)`` applies the expect/forbid/expect_any
  substring checks to the final assistant text.
- ``check_run(stream_text, journey, exit_code, timed_out)`` parses a
  ``claude -p --output-format stream-json --verbose`` stream and fails the
  journey closed. The full list of fail conditions is in evals/README.md
  "Live concierge journeys"; this function is the implementation.

The shell runner calls this file's CLI; evals/graders/test_concierge_journeys_check.py
pytests the pure functions on canned text (no model, no network — CI-safe).
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys

ALLOWED_KEYS = frozenset({"id", "prompt", "expect", "forbid", "expect_any", "needs", "skill"})
LIST_KEYS = ("expect", "forbid", "expect_any")
# no-connector: no Parallax server may load. connector-optional: skip only the
# server-presence check (for a journey that makes no Parallax call, where a
# claude.ai connector may not be listed in the init message yet).
NEEDS_VALUES = frozenset({"no-connector", "connector-optional"})
# The skill a journey must run when its line names none.
CONCIERGE_SKILL = "parallax:parallax-concierge"
PLUGIN_PREFIX = "parallax:"
# Skill names this plugin ships, without the plugin prefix. A Skill call to
# one of these unprefixed means a copy outside the plugin answered.
_UNPREFIXED = re.compile(r"(parallax|translate)-")
# The only init-message status that proves a Parallax server is up. "pending"
# does not: a pending claude.ai connector can still turn out signed out.
CONNECTED_STATUS = "connected"
# Shared helpers a skill tells the model to run (conventions §10.3, loader §6).
HELPERS = ("render_gate.py", "audit_append.py")
# The house-view audit log is written only by audit_append.py, whose command
# names a draft, never the log (loader §6). A shell command that names the log
# is a raw write (which bypasses the hash chain) or a shell read (which §0.0
# forbids); either fails, denied or not.
_AUDIT_LOG = re.compile(r"audit\.jsonl(?![\w.])")
# The documented one-line form of a helper command. A denial of exactly this
# shape is a defect in the skill's own instructions; anything else the model
# wrote is improvised.
_DOCUMENTED_HELPER = re.compile(
    r'python3 "[^"\n]+/(?P<helper>render_gate\.py|house-view/audit_append\.py)"'
    r'(?: --skill (?P<key>[a-z0-9-]+))? --input "(?P<input>[^"\n]+)"'
)
# A report draft (conventions §10.3); its key is the gated skill's key.
_REPORT_DRAFT = re.compile(r"/\.parallax-render/(?P<key>[a-z0-9-]+)-[0-9a-f]{8}\.md$")


def _norm_path(path: str) -> str:
    """One spelling per file: collapse ``//`` and ``..``, and drop macOS's
    ``/private`` prefix (``/private/var`` and ``/var`` are the same dir)."""
    norm = posixpath.normpath(path.strip())
    for root in ("/private/var/", "/private/tmp/"):
        if norm.startswith(root):
            norm = norm[len("/private"):]
    return norm


def documented_helper(command: str) -> str | None:
    """The helper name ("render_gate.py" / "audit_append.py") when
    ``command`` is exactly a documented helper command, else None."""
    m = _DOCUMENTED_HELPER.fullmatch(command.strip())
    return m["helper"].rsplit("/", 1)[-1] if m else None


def validate_journey(journey: object) -> list[str]:
    """Return the problems with one parsed journey line; empty if valid."""
    if not isinstance(journey, dict):
        return [f"journey is not a JSON object: {type(journey).__name__}"]
    problems: list[str] = []
    unknown = sorted(set(journey) - ALLOWED_KEYS)
    if unknown:
        problems.append(f"unknown keys: {unknown}")
    for key in ("id", "prompt"):
        value = journey.get(key)
        if not isinstance(value, str) or not value:
            problems.append(f"{key!r} must be a non-empty string")
    for key in LIST_KEYS:
        if key not in journey:
            continue
        value = journey[key]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            problems.append(f"{key!r} must be a list of strings")
    if "skill" in journey:
        value = journey["skill"]
        if not isinstance(value, str) or not value.startswith(PLUGIN_PREFIX) or value == PLUGIN_PREFIX:
            problems.append(f"'skill' must be a string starting with {PLUGIN_PREFIX!r}")
    if "needs" in journey and journey["needs"] not in NEEDS_VALUES:
        problems.append(f"'needs' must be one of {sorted(NEEDS_VALUES)}")
    return problems


def check_journey(output: str, journey: dict, forbid_text: str | None = None) -> tuple[bool, list[str]]:
    """Check ``output`` against one journey's expect/forbid/expect_any lists.

    - expect: every substring must appear (case-insensitive). Each missing one
      is a failure reason.
    - forbid: no substring may appear (case-insensitive). Each present one is
      a failure reason.
    - expect_any: if non-empty, at least one substring must appear; none
      present is a single failure reason.

    ``forbid_text``, when given, is the text the forbid list is checked
    against instead of ``output`` (the runner passes all assistant text).

    Returns (passed, reasons); reasons lists every failure, not just the first.
    """
    text = (output or "").lower()
    ftext = text if forbid_text is None else forbid_text.lower()
    reasons: list[str] = []

    for phrase in journey.get("expect") or []:
        if phrase.lower() not in text:
            reasons.append(f"missing expect: {phrase!r}")

    for phrase in journey.get("forbid") or []:
        if phrase.lower() in ftext:
            reasons.append(f"found forbidden: {phrase!r}")

    expect_any = journey.get("expect_any") or []
    if expect_any and not any(phrase.lower() in text for phrase in expect_any):
        reasons.append(f"none of expect_any present: {expect_any!r}")

    return (len(reasons) == 0, reasons)


def parse_stream(stream_text: str) -> dict:
    """Pull the init message, the final result message and the Parallax MCP
    tool calls out of a stream-json transcript. Lines that are not JSON
    objects are ignored. ``parallax_calls`` maps each Parallax tool_use id to
    {"name", "ok"}; ok is True when its tool_result came back without is_error.
    ``skill_calls`` does the same for Skill tool calls, keyed by tool_use id,
    with the requested skill name. ``bash_calls`` lists every Bash tool call in
    order as {"id", "command", "ok", "seq"}. ``file_writes`` lists every
    Write/Edit call as {"id", "path", "ok", "seq"}. ``seq`` is the call's
    position in the stream, shared by both lists. ``assistant_texts`` lists every assistant
    text block in order."""
    init = None
    result = None
    calls: dict[str, dict] = {}
    skills: dict[str, dict] = {}
    bash: dict[str, dict] = {}
    writes: dict[str, dict] = {}
    seq = 0
    texts: list[str] = []
    for line in (stream_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        if msg.get("type") == "system" and msg.get("subtype") == "init" and init is None:
            init = msg
        elif msg.get("type") == "result":
            result = msg
        elif msg.get("type") in ("assistant", "user"):
            content = (msg.get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text" and msg["type"] == "assistant" and isinstance(block.get("text"), str):
                    texts.append(block["text"])
                elif btype == "tool_use" and block.get("name") == "Skill":
                    tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                    skills[block.get("id", "")] = {"name": str(tool_input.get("skill", "")), "ok": False}
                elif btype == "tool_use" and is_parallax_tool(block.get("name", "")):
                    calls[block.get("id", "")] = {"name": block["name"], "ok": False}
                elif btype == "tool_use" and block.get("name") in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
                    tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                    seq += 1
                    writes[block.get("id", "")] = {
                        "id": block.get("id", ""), "ok": False, "seq": seq,
                        "path": str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")}
                elif btype == "tool_use" and block.get("name") == "Bash":
                    tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                    seq += 1
                    bash[block.get("id", "")] = {"id": block.get("id", ""), "ok": False, "seq": seq,
                                                 "command": str(tool_input.get("command", ""))}
                elif btype == "tool_result":
                    for table in (calls, skills, bash, writes):
                        if block.get("tool_use_id") in table:
                            table[block["tool_use_id"]]["ok"] = not block.get("is_error", False)
    servers = (init or {}).get("mcp_servers") or []
    return {"init": init, "result": result, "mcp_servers": servers,
            "parallax_calls": calls, "skill_calls": skills,
            "bash_calls": list(bash.values()), "file_writes": list(writes.values()),
            "assistant_texts": texts}


def classify_denials(denials: list, bash_calls: list[dict]) -> tuple[list[str], list[str]]:
    """Split permission denials into (blocking, warnings).

    Blocking: any non-Bash denial (an MCP tool, Write, Skill); a Bash denial
    whose command cannot be read; the documented helper command itself
    (``_DOCUMENTED_HELPER``); or an improvised command that used a helper when
    no later Bash call ran that helper's documented command (the gate must
    succeed; the audit helper must run, since its exits 3 and 4 are documented
    non-fatal outcomes, loader §6). Everything else is a
    command the model improvised (a doc-reading ``cd``/``sed`` chain, an
    ``echo $?`` suffix) and a warning: Claude Code's checker refuses such
    commands inconsistently, and the run recovered without them.
    """
    blocking: list[str] = []
    warnings: list[str] = []
    order = [c["id"] for c in bash_calls]
    denied_ids = {d.get("tool_use_id") for d in denials if isinstance(d, dict)}
    for d in denials:
        if not isinstance(d, dict):
            blocking.append(f"permission denials: {d!r}")
            continue
        name = d.get("tool_name", "?")
        tool_input = d.get("tool_input") if isinstance(d.get("tool_input"), dict) else {}
        command = str(tool_input.get("command", "")).strip()
        if name != "Bash" or not command:
            blocking.append(f"permission denials: [{name!r}]")
            continue
        if _DOCUMENTED_HELPER.fullmatch(command):
            blocking.append(f"documented helper command denied: {command[:120]}")
            continue
        used = [h for h in HELPERS if h in command]
        if used:
            denied_at = order.index(d.get("tool_use_id")) if d.get("tool_use_id") in order else -1
            later = bash_calls[denied_at + 1:] if denied_at >= 0 else []
            missing = [h for h in used if not any(
                documented_helper(c["command"]) == h
                and (c["ok"] if h == "render_gate.py" else c["id"] not in denied_ids)
                for c in later)]
            if missing:
                blocking.append(f"helper never ran after its command was denied: {missing}")
                continue
        warnings.append(f"improvised Bash command denied: {command[:120]}")
    return blocking, warnings


def is_parallax_tool(name: str) -> bool:
    """An MCP tool exposed by a Parallax server, whatever its namespace."""
    return name.startswith("mcp__") and "parallax" in name.lower()


def parallax_servers(mcp_servers: list) -> list[dict]:
    """The init message's MCP server entries whose name mentions Parallax."""
    return [
        s for s in mcp_servers
        if isinstance(s, dict) and "parallax" in str(s.get("name", "")).lower()
    ]


def _describe(servers: list[dict]) -> str:
    return ", ".join(f"{s.get('name')} ({s.get('status')})" for s in servers)


def check_run(
    stream_text: str, journey: dict, exit_code: int, timed_out: bool,
    plugin_dir: str | None = None,
) -> tuple[bool, list[str], str, str]:
    """Fail-closed check of one live journey run.

    ``plugin_dir``, when given, must be the path of a plugin listed in the
    init message, so the run used this branch's built plugin.

    Returns (passed, reasons, final_text, all_text). final_text is the result
    message's text ("" when there is none); expect/expect_any run on it.
    all_text is every assistant text block joined; forbid runs on it.
    """
    parsed = parse_stream(stream_text)
    reasons: list[str] = []

    if timed_out:
        reasons.append("timed out")
    if exit_code != 0:
        reasons.append(f"claude exited {exit_code}")

    if parsed["init"] is None:
        reasons.append("no init message in stream")
    else:
        if plugin_dir is not None:
            paths = [pl.get("path") for pl in parsed["init"].get("plugins") or [] if isinstance(pl, dict)]
            if plugin_dir not in paths:
                reasons.append(f"plugin {plugin_dir} not loaded (init plugins: {paths})")
        found = parallax_servers(parsed["mcp_servers"])
        calls = list(parsed["parallax_calls"].values())
        if journey.get("needs") == "connector-optional":
            pass
        elif journey.get("needs") == "no-connector":
            if found:
                reasons.append(f"Parallax server present in a no-connector run: {_describe(found)}")
            if calls:
                reasons.append(f"Parallax tool called in a no-connector run: {sorted({c['name'] for c in calls})}")
        else:
            # A claude.ai connector can finish loading after the init message
            # is written (absent or "pending" there), so a Parallax tool call
            # that returned without error also proves the connector is up.
            connected = [s for s in found if s.get("status") == CONNECTED_STATUS]
            if not connected and not any(c["ok"] for c in calls):
                reasons.append(
                    f"no connected Parallax server at init ({_describe(found) or 'none'}) "
                    "and no successful Parallax tool call"
                )

    result = parsed["result"]
    final_text = ""
    if result is None:
        reasons.append("no result message in stream")
    else:
        if isinstance(result.get("result"), str):
            final_text = result["result"]
        denials = result.get("permission_denials") or []
        blocking, _ = classify_denials(denials, parsed["bash_calls"])
        reasons.extend(blocking)
        commands = [c["command"] for c in parsed["bash_calls"]]
        for d in denials:
            tool_input = d.get("tool_input") if isinstance(d, dict) else None
            if isinstance(tool_input, dict):
                commands.append(str(tool_input.get("command", "")))
        if any(_AUDIT_LOG.search(cmd) for cmd in commands):
            reasons.append("shell command names audit.jsonl (only audit_append.py may touch it; loader §6)")
        if any(_AUDIT_LOG.search(w["path"]) for w in parsed["file_writes"]):
            reasons.append("file tool wrote audit.jsonl (only audit_append.py may write it; loader §6)")
        # Every report draft the model wrote must be gated: a successful
        # documented gate run on that same draft, with the draft's own key,
        # after the last successful write to it. A skill that stops before
        # drafting (an unresolvable ticker) needs no gate.
        gate_runs = []
        for c in parsed["bash_calls"]:
            m = _DOCUMENTED_HELPER.fullmatch(c["command"].strip())
            if m and m["helper"] == "render_gate.py":
                gate_runs.append({**c, "key": m["key"], "input": _norm_path(m["input"])})
        last_write: dict[str, dict] = {}
        for w in parsed["file_writes"]:
            if w["ok"]:  # a failed write left nothing to gate
                last_write[_norm_path(w["path"])] = w
        for path, w in last_write.items():
            draft = _REPORT_DRAFT.search(path)
            if not draft:
                continue
            if not any(g["ok"] and g["seq"] > w["seq"] and g["input"] == path
                       and g["key"] == draft["key"] for g in gate_runs):
                reasons.append(f"report draft never gated: no successful documented render-gate run "
                               f"with --skill {draft['key']} on {path}")
        if result.get("is_error"):
            reasons.append("result is_error")
        if result.get("subtype") != "success":
            reasons.append(f"result subtype {result.get('subtype')!r}")

    skill_calls = list(parsed["skill_calls"].values())
    seen = sorted({c["name"] for c in skill_calls}) or "none"
    required = journey.get("skill") or CONCIERGE_SKILL
    if not any(c["ok"] and c["name"] == required for c in skill_calls):
        reasons.append(f"skill {required} did not run (Skill calls: {seen})")
    if not any(c["ok"] and c["name"].startswith(PLUGIN_PREFIX) for c in skill_calls):
        reasons.append(f"no skill from the plugin namespace ran (Skill calls: {seen})")
    unprefixed = sorted({c["name"] for c in skill_calls if _UNPREFIXED.match(c["name"])})
    if unprefixed:
        reasons.append(f"unprefixed Parallax skill called (not this plugin's copy): {unprefixed}")

    all_text = "\n\n".join(parsed["assistant_texts"])
    if final_text and final_text not in all_text:
        all_text = f"{all_text}\n\n{final_text}" if all_text else final_text
    _, text_reasons = check_journey(final_text, journey, forbid_text=all_text)
    reasons.extend(text_reasons)
    return (len(reasons) == 0, reasons, final_text, all_text)


def main(argv: list[str] | None = None) -> int:
    """CLI.

    ``concierge_journeys_check.py --validate '<journey-json-line>'``
        exit 0 if the line is a valid journey, 2 with the problems otherwise.
    ``concierge_journeys_check.py '<journey-json-line>' --stream FILE
        --exit-code N [--timed-out] [--plugin-dir DIR] [--text-out FILE]``
        run the fail-closed check, print the Parallax servers seen at init,
        the denials and tool calls, then PASS or one FAIL line per reason;
        write all assistant text to --text-out; exit 0 on pass, 1 on fail.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("journey")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--stream")
    ap.add_argument("--exit-code", type=int, default=0)
    ap.add_argument("--timed-out", action="store_true")
    ap.add_argument("--plugin-dir")
    ap.add_argument("--text-out")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        journey = json.loads(args.journey)
    except json.JSONDecodeError as exc:
        print(f"INVALID: not JSON: {exc}")
        return 2
    problems = validate_journey(journey)
    if problems:
        for p in problems:
            print(f"INVALID: {p}")
        return 2
    if args.validate:
        return 0
    if not args.stream:
        print("usage: --stream FILE is required unless --validate", file=sys.stderr)
        return 2

    with open(args.stream, encoding="utf-8", errors="replace") as fh:
        stream_text = fh.read()
    passed, reasons, _, all_text = check_run(
        stream_text, journey, args.exit_code, args.timed_out, plugin_dir=args.plugin_dir
    )
    if args.text_out:
        with open(args.text_out, "w", encoding="utf-8") as fh:
            fh.write(all_text)
    parsed = parse_stream(stream_text)
    denials = (parsed["result"] or {}).get("permission_denials") or []
    print(f"parallax servers at init: {_describe(parallax_servers(parsed['mcp_servers'])) or 'none'}")
    print(f"permission_denials: {len(denials)}")
    for warning in classify_denials(denials, parsed["bash_calls"])[1]:
        print(f"WARN: {warning}")
    calls = parsed["parallax_calls"].values()
    print("parallax tool calls: " + (", ".join(
        f"{c['name']} ({'ok' if c['ok'] else 'error'})" for c in calls) or "none"))
    if passed:
        print("PASS")
        return 0
    for reason in reasons:
        print(f"FAIL: {reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
