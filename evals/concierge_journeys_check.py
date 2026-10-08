"""evals/concierge_journeys_check.py — checker for the live concierge journeys
(see evals/concierge_journeys.sh and evals/tasks/concierge/journeys.jsonl).

Pure functions, no I/O:

- ``validate_journey(journey)`` rejects a journey line with unknown keys or
  with ``expect``/``forbid``/``expect_any`` that is not a list of strings.
- ``check_journey(output, journey)`` applies the expect/forbid/expect_any
  substring checks to the final assistant text.
- ``check_run(stream_text, journey, exit_code, timed_out)`` parses a
  ``claude -p --output-format stream-json --verbose`` stream and fails closed:
  any permission denial, a missing or errored result, a non-zero exit, a
  timeout, no successful run of the plugin's concierge skill, or the wrong
  Parallax connector state fails the journey, whatever the text says.
  ``expect``/``expect_any`` run on the final answer; ``forbid`` runs on all
  assistant text in the run, so a forbidden phrase in an earlier turn fails.

The shell runner calls this file's CLI; evals/graders/test_concierge_journeys_check.py
pytests the pure functions on canned text (no model, no network — CI-safe).
"""
from __future__ import annotations

import argparse
import json
import sys

ALLOWED_KEYS = frozenset({"id", "prompt", "expect", "forbid", "expect_any", "needs"})
LIST_KEYS = ("expect", "forbid", "expect_any")
# no-connector: no Parallax server may load. connector-optional: skip only the
# server-presence check (for a journey that makes no Parallax call, where a
# claude.ai connector may not be listed in the init message yet).
NEEDS_VALUES = frozenset({"no-connector", "connector-optional"})
CONCIERGE_SKILL = "parallax:parallax-concierge"
# The only init-message status that proves a Parallax server is up. "pending"
# does not: a pending claude.ai connector can still turn out signed out.
CONNECTED_STATUS = "connected"


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
    with the requested skill name. ``assistant_texts`` lists every assistant
    text block in order."""
    init = None
    result = None
    calls: dict[str, dict] = {}
    skills: dict[str, dict] = {}
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
                elif btype == "tool_result":
                    for table in (calls, skills):
                        if block.get("tool_use_id") in table:
                            table[block["tool_use_id"]]["ok"] = not block.get("is_error", False)
    servers = (init or {}).get("mcp_servers") or []
    return {"init": init, "result": result, "mcp_servers": servers,
            "parallax_calls": calls, "skill_calls": skills, "assistant_texts": texts}


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
        if denials:
            names = [d.get("tool_name", "?") if isinstance(d, dict) else str(d) for d in denials]
            reasons.append(f"permission denials: {names}")
        if result.get("is_error"):
            reasons.append("result is_error")
        if result.get("subtype") != "success":
            reasons.append(f"result subtype {result.get('subtype')!r}")

    skill_runs = [c for c in parsed["skill_calls"].values() if c["name"] == CONCIERGE_SKILL]
    if not any(c["ok"] for c in skill_runs):
        seen = sorted({c["name"] for c in parsed["skill_calls"].values()})
        reasons.append(f"skill {CONCIERGE_SKILL} did not run (Skill calls: {seen or 'none'})")

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
