"""evals/concierge_journeys_check.py — checker for the live concierge journeys
(see evals/concierge_journeys.sh and evals/tasks/concierge/journeys.jsonl).

Pure functions; the only I/O is reading skills/_parallax/render_gate.py, whose
pure ``gate()`` the render-gate requirement replays, and comparing it with the
plugin's copy:

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
import contextlib
import functools
import importlib.util
import io
import json
import posixpath
import re
import sys
from pathlib import Path

ALLOWED_KEYS = frozenset({"id", "prompt", "expect", "forbid", "expect_any", "needs", "skill",
                          "require_helpers"})
LIST_KEYS = ("expect", "forbid", "expect_any", "require_helpers")
# Helpers a journey may require via "require_helpers" (conventions §10.3/§14.4).
# render_gate.py needs the journey's "skill", whose key the gate run must name.
REQUIRABLE_HELPERS = frozenset({"adaptation.py", "coverage_check.py", "reconcile.py",
                                "render_gate.py"})
# The argument that names each required helper's payload draft. A run counts
# for "require_helpers" only when this argument is a Write-tool draft.
_PRIMARY_ARG = {"adaptation.py": "policy", "coverage_check.py": "portfolio_sectors",
                "reconcile.py": "input", "render_gate.py": "input"}
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
# A shell segment that runs a shared helper a skill tells the model to run
# (conventions §10.3/§14.4, loader §6). A bare mention (``sed``, ``grep``) is not a run.
_HELPER_RUN = re.compile(
    r"\bpython3?\s[^;&|\n]*?(?<![\w.-])(?P<helper>render_gate\.py|audit_append\.py|"
    r"adaptation\.py|coverage_check\.py|reconcile\.py)(?![\w.-])"
)
# The house-view audit log is written only by audit_append.py, whose command
# names a draft, never the log (loader §6). A shell command that names the log
# is a raw write (which bypasses the hash chain) or a shell read (which §0.0
# forbids); either fails, denied or not.
_AUDIT_LOG = re.compile(r"audit\.jsonl(?![\w.])")
def _arg(name: str) -> str:
    """One path argument: double-quoted, or a bare token with no whitespace,
    quote or shell metacharacter. Neither form may hold ``$``, a backtick or
    ``\\``, so the argument cannot expand (``"$PWD/x"``, ``"$(cmd)"``) and
    names the file the shell reads. A bare cwd-relative path such as
    ``.parallax-policy/policy-<hex>.json`` is as literal as a quoted absolute
    one (conventions §14.4)."""
    return (rf'(?:"(?P<{name}>[^"\n$`\\]+)"'
            rf"|(?P<{name}__bare>[^\s\"'$`;&|<>(){{}}*?!~\\]+))")


# The documented one-line form of each helper command, keyed by bare helper
# name. A denial of exactly one of these shapes is a defect in the skill's own
# instructions; anything else the model wrote is improvised. Each pattern is
# tried with ``fullmatch`` (one line except the render gate's stdin heredoc,
# canonical flag order per conventions §14.1/§14.4 — a doc that reorders flags
# would make the real command fall into the "improvised" bucket below).
_HELPER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("render_gate.py", re.compile(
        r"python3 " + _arg("script_rg") + r" --skill (?P<key>[a-z0-9-]+) "
        r"--input " + _arg("input")
    )),
    # The stdin fallback (conventions §10.3): the report in a quoted heredoc.
    # _match_documented_helper also rejects a body that ends the heredoc early.
    ("render_gate.py", re.compile(
        r"python3 " + _arg("script_rg") + r" --skill (?P<key>[a-z0-9-]+) "
        r"<<'REPORT'\n(?P<body>.*)\nREPORT", re.DOTALL
    )),
    ("audit_append.py", re.compile(
        r"python3 " + _arg("script_aa") + r" --input " + _arg("input")
    )),
    ("adaptation.py", re.compile(
        r"python3 " + _arg("script_ad") + r" --policy " + _arg("policy")
        + r"(?: --exposures " + _arg("exposures") + r")?"
        + r"(?: --view-tilts " + _arg("view_tilts") + r")?"
        + r" --json"
    )),
    ("coverage_check.py", re.compile(
        r"python3 " + _arg("script_cc") + r" --portfolio-sectors " + _arg("portfolio_sectors")
        + r" --redundancy-sectors " + _arg("redundancy_sectors")
        + r"(?: --holdings " + _arg("holdings") + r")?"
    )),
    ("reconcile.py", re.compile(
        r"python3 " + _arg("script_rc") + r" --input " + _arg("input")
    )),
]
# The helper script each pattern's first argument must name.
_HELPER_SCRIPT_SUFFIX = {
    "render_gate.py": "/render_gate.py",
    "audit_append.py": "/house-view/audit_append.py",
    "adaptation.py": "/client-policy/adaptation.py",
    "coverage_check.py": "/coverage_check.py",
    "reconcile.py": "/client-policy/reconcile.py",
}
# An interpreter or shell given a script path (``python3 x.py``, ``bash x.sh``,
# ``sh x``), or a ``./`` path in command position (``./x``).
# Interpreter flags (``-u``, ``-x``) are skipped; ``-c`` is not, so
# ``bash -c 'python3 x'`` matches the inner run. Best-effort: other spellings
# (``python3 - < x``, ``source x``) are not caught (evals/README.md).
_INTERPRETER_RUN = re.compile(
    r"""(?<![\w.-])(?:python3?|bash|sh)(?:\s+-(?!c\b)[A-Za-z]+)*\s+(["']?[^\s"';&|<>()-][^\s"';&|<>()]*["']?)"""
)
# ``[ \t]*`` (not ``\s*``) after a separator keeps the scan linear on long runs
# of newlines.
_COMMAND_WORD = re.compile(r"""(?:^|[;&|(\n])[ \t]*(\./[^\s"';&|<>()]+)""")


def _script_tokens(command: str) -> list[str]:
    """The paths ``command`` may run as a script, quotes stripped. The two
    scans are separate so a command word (``(python3``) cannot hide the
    interpreter run that follows it."""
    return [m.group(1).strip("\"'") for rx in (_INTERPRETER_RUN, _COMMAND_WORD)
            for m in rx.finditer(command)]


# Payload-draft labels the skills write (conventions §14.4). A draft with one
# of these labels is data: a command that names it is not running a script.
_DATA_DRAFT = re.compile(
    r"/\.parallax-policy/(?:policy|exposures|tilts|portfolio-sectors|redundancy-sectors|holdings|"
    r"reconcile)-[0-9a-f]{8}\.(?:json|yaml)$"
)
# A report draft (conventions §10.3); its key is the gated skill's key.
_REPORT_DRAFT = re.compile(r"/\.parallax-render/(?P<key>[a-z0-9-]+)-[0-9a-f]{8}\.md$")
# A policy/coverage payload draft (conventions §14.4); its label names which
# payload it is (``policy``, ``exposures``, ``tilts``, ``portfolio-sectors``,
# ``redundancy-sectors``, ``holdings``, ``reconcile``). Requires the trailing
# ``-<8 hex>.(json|yaml)`` shape, so a sibling ``.gitignore`` never matches.
_POLICY_DRAFT = re.compile(r"/\.parallax-policy/(?P<label>[a-z0-9-]+)-[0-9a-f]{8}\.(?:json|yaml)$")


# The gate whose output a required render-gate run must reproduce. The plugin
# copy is a byte-identical build of this file (build_bundle.py).
_RENDER_GATE = Path(__file__).resolve().parent.parent / "skills" / "_parallax" / "render_gate.py"


@functools.lru_cache(maxsize=1)
def _gate_fn():
    spec = importlib.util.spec_from_file_location("_journey_render_gate", _RENDER_GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.gate


def _stale_plugin_gate(plugin_dir: str | None) -> bool:
    """True when ``plugin_dir`` holds a render_gate.py that differs from the
    one this checker replays (the plugin was not rebuilt after an edit)."""
    if plugin_dir is None:
        return False
    built = Path(plugin_dir) / "skills" / "_parallax" / "render_gate.py"
    return built.is_file() and built.read_bytes() != _RENDER_GATE.read_bytes()


def _render(text: str, key: str) -> str:
    """``render_gate.gate(text, key)``, its fail-open warning discarded."""
    with contextlib.redirect_stderr(io.StringIO()):
        return _gate_fn()(text, key)


def _norm_path(path: str, cwd: str | None = None) -> str:
    """One spelling per file: resolve a relative path against ``cwd`` (the
    run's working directory, from the init message), collapse ``//`` and
    ``..``, and drop macOS's ``/private`` prefix (``/private/var`` and
    ``/var`` are the same dir)."""
    path = path.strip()
    if cwd and not path.startswith("/"):
        path = posixpath.join(cwd, path)
    norm = posixpath.normpath(path)
    for root in ("/private/var/", "/private/tmp/"):
        if norm.startswith(root):
            norm = norm[len("/private"):]
    return norm


def _match_documented_helper(command: str) -> dict[str, str] | None:
    """Try each pattern in ``_HELPER_PATTERNS`` in turn; return
    ``{"helper": <bare name>, "script": <script path>, **matched groups}`` for
    the first exact match (one line, canonical flag order; the render-gate
    stdin form also has ``body``), else None. Missing optional groups are
    present with value None (``re.Match.groupdict()``)."""
    stripped = command.strip()
    for helper, pattern in _HELPER_PATTERNS:
        m = pattern.fullmatch(stripped)
        if not m:
            continue
        # A heredoc ends at its first terminator line; text after it would run.
        if m.groupdict().get("body") is not None and "REPORT" in m["body"].split("\n"):
            continue
        groups: dict[str, str | None] = {}
        for name, value in m.groupdict().items():
            base = name[: -len("__bare")] if name.endswith("__bare") else name
            if value is not None or base not in groups:
                groups[base] = value
        script = next((v for k, v in groups.items() if k.startswith("script_") and v), "")
        if not script.endswith(_HELPER_SCRIPT_SUFFIX[helper]):
            continue
        return {"helper": helper, "script": script,
                **{k: v for k, v in groups.items() if not k.startswith("script_")}}
    return None


def _helper_args(m: dict) -> dict[str, str]:
    """The path arguments of a ``_match_documented_helper`` result."""
    return {k: v for k, v in m.items() if k not in ("helper", "script", "key", "body") and v}


def _in_plugin(script: str, cwd: str | None, plugin_dir: str | None) -> bool:
    """True when ``plugin_dir`` is None or ``script`` resolves under it, so a
    command that names a file the model wrote is never credited as a helper run."""
    if plugin_dir is None:
        return True
    return _norm_path(script, cwd).startswith(_norm_path(plugin_dir).rstrip("/") + "/")


def documented_helper(command: str) -> str | None:
    """The helper name ("render_gate.py" / "audit_append.py" / "adaptation.py"
    / "coverage_check.py" / "reconcile.py") when ``command`` is exactly a
    documented helper command, else None."""
    m = _match_documented_helper(command)
    return m["helper"] if m else None


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
    if isinstance(journey.get("require_helpers"), list):
        bad = sorted(set(journey["require_helpers"]) - REQUIRABLE_HELPERS)
        if bad:
            problems.append(f"'require_helpers' entries must be in {sorted(REQUIRABLE_HELPERS)}: {bad}")
        if "render_gate.py" in journey["require_helpers"] and "skill" not in journey:
            problems.append("'require_helpers' with render_gate.py needs 'skill' (the gate's --skill key)")
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
    Write/Edit/MultiEdit/NotebookEdit call as {"id", "tool", "path", "content",
    "ok", "seq"} (content is None except for Write). ``seq`` is the call's
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
                        "id": block.get("id", ""), "tool": block["name"], "ok": False, "seq": seq,
                        "path": str(tool_input.get("file_path") or tool_input.get("notebook_path") or ""),
                        "content": str(tool_input.get("content", "")) if block["name"] == "Write" else None}
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


def classify_denials(denials: list, bash_calls: list[dict], cwd: str | None = None,
                     plugin_dir: str | None = None) -> tuple[list[str], list[str]]:
    """Split permission denials into (blocking, warnings).

    Blocking: any non-Bash denial (an MCP tool, Write, Skill); a Bash denial
    whose command cannot be read; the documented helper command itself
    (``_HELPER_PATTERNS``), except the render gate's stdin fallback, which
    Claude Code refuses for some report text (conventions §10.3) and is
    treated as below; or an improvised command that used a helper when
    no later Bash call ran that helper's documented command, from
    ``plugin_dir`` when given (the gate must
    succeed; the audit, adaptation, coverage and reconcile helpers must run,
    since their nonzero exits are documented outcomes, loader §6 /
    policy-loader.md §2 / policy-reconciliation.md step 3). Everything else,
    including a command that only mentions a helper without running it, is a
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
        documented = _match_documented_helper(command)
        if documented and documented.get("body") is None:
            blocking.append(f"documented helper command denied: {command[:120]}")
            continue
        # A stdin gate's heredoc body is report text; only its first line runs.
        scanned = command.split("\n", 1)[0] if documented else command
        used = sorted({m["helper"] for m in _HELPER_RUN.finditer(scanned)})
        if documented:
            used = sorted(set(used) | {documented["helper"]})
        if used:
            denied_at = order.index(d.get("tool_use_id")) if d.get("tool_use_id") in order else -1
            later = bash_calls[denied_at + 1:] if denied_at >= 0 else []
            runs = [(c, _match_documented_helper(c["command"])) for c in later]
            missing = [h for h in used if not any(
                m is not None and m["helper"] == h and _in_plugin(m["script"], cwd, plugin_dir)
                and (c["ok"] if h == "render_gate.py" else c["id"] not in denied_ids)
                for c, m in runs)]
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
        denied_ids = {d.get("tool_use_id") for d in denials if isinstance(d, dict)}
        # The run's working directory, so a cwd-relative helper argument such as
        # .parallax-policy/policy-<hex>.json names the same file the Write tool
        # wrote under its absolute path.
        cwd = (parsed["init"] or {}).get("cwd")
        blocking, _ = classify_denials(denials, parsed["bash_calls"], cwd=cwd, plugin_dir=plugin_dir)
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
        # A helper run counts only when its script is this run's plugin copy
        # (plugin_dir), never a same-named file the model wrote.
        gate_runs = []
        policy_runs = []
        for c in parsed["bash_calls"]:
            m = _match_documented_helper(c["command"].strip())
            if not m or not _in_plugin(m["script"], cwd, plugin_dir):
                continue
            args = {k: _norm_path(v, cwd) for k, v in _helper_args(m).items()}
            if m["helper"] == "render_gate.py":
                gate_runs.append({**c, "key": m["key"], "input": args.get("input"),
                                  "stdin": m.get("body") is not None})
            elif m["helper"] in ("adaptation.py", "coverage_check.py", "reconcile.py"):
                policy_runs.append({**c, "inputs": set(args.values()), "helper": m["helper"],
                                    "primary": args.get(_PRIMARY_ARG[m["helper"]])})
        last_write: dict[str, dict] = {}
        for w in parsed["file_writes"]:
            if w["ok"]:  # a failed write left nothing to gate/consume
                last_write[_norm_path(w["path"], cwd)] = w
        # A skill never writes code and runs it (conventions §14.4): a run of a
        # file the model wrote is an improvised helper, whatever it is named,
        # and a gate.py that "checks" a report stands in for the real gate.
        # Payload and report drafts are data, so a command that names one
        # (``grep -c python <draft>``) is not a script run.
        written = set(last_write)
        for c in parsed["bash_calls"]:
            if c["id"] in denied_ids:
                continue
            # A documented stdin gate run's heredoc body is report text, not commands.
            m = _match_documented_helper(c["command"])
            command = c["command"].strip().split("\n", 1)[0] if m and m.get("body") is not None \
                else c["command"]
            for script in dict.fromkeys(_script_tokens(command)):
                target = _norm_path(script, cwd)
                if target in written and not (_DATA_DRAFT.search(target) or _REPORT_DRAFT.search(target)):
                    reasons.append(f"ran a script the model wrote: {script}")
        # .parallax-policy/ holds payload drafts and its .gitignore only.
        for path in written:
            if "/.parallax-policy/" in path and not _POLICY_DRAFT.search(path) \
                    and not path.endswith("/.parallax-policy/.gitignore"):
                reasons.append(f"non-draft file written into .parallax-policy: {path}")
        # Every report draft the model wrote must be gated: a successful
        # documented gate run on that same draft, with the draft's own key,
        # after the last successful write to it. A skill that stops before
        # drafting (an unresolvable ticker) needs no gate.
        for path, w in last_write.items():
            draft = _REPORT_DRAFT.search(path)
            if draft:
                if not any(g["ok"] and g["seq"] > w["seq"] and g["input"] == path
                           and g["key"] == draft["key"] for g in gate_runs):
                    reasons.append(f"report draft never gated: no successful documented render-gate run "
                                   f"with --skill {draft['key']} on {path}")
                continue
            # Every policy/coverage draft the model wrote (conventions §14.4)
            # must be read by a later successful documented run of
            # adaptation.py, coverage_check.py, or reconcile.py that names
            # this same literal path. These helpers do not delete their input
            # after reading it, so this is a consumption check, not a
            # gating check — see policy-loader.md §1 / §5.
            if _POLICY_DRAFT.search(path) and not any(
                r["id"] not in denied_ids and r["seq"] > w["seq"] and path in r["inputs"]
                for r in policy_runs
            ):
                reasons.append(f"policy draft never consumed: no successful documented helper run "
                               f"reading {path}")
        # A journey that names required helpers needs each one to have run as
        # documented, from the plugin, not denied, exiting cleanly, with its
        # primary argument (_PRIMARY_ARG) a draft the Write tool created before
        # the run. The consumption check above is deliberately lenient (a
        # documented nonzero exit still consumes a draft); this one is not: a
        # helper that errored, an improvised replacement, or a draft made by a
        # heredoc, by Edit, or in /tmp does not count. render_gate.py needs the
        # journey skill's key, on a Write-tool report draft or by the stdin
        # form (conventions §10.3), and the final answer must be that run's
        # output: render_gate.gate() replayed on the gated text, compared with
        # whitespace collapsed. The gate also moves degraded-state notes from
        # the stripped preamble to the end, so a substring test is not enough.
        def _write_draft_before(path: str | None, pattern: re.Pattern[str], seq: int) -> bool:
            w = last_write.get(path) if path else None
            return bool(w and w["tool"] == "Write" and pattern.search(path) and w["seq"] < seq)

        def _gated_text(g: dict) -> str | None:
            if g["stdin"]:
                return _match_documented_helper(g["command"])["body"]
            if _write_draft_before(g["input"], _REPORT_DRAFT, g["seq"]):
                return last_write[g["input"]]["content"]
            return None

        def _squash(text: str) -> str:
            return " ".join(text.split())

        gate_key = (journey.get("skill") or "")[len(PLUGIN_PREFIX):].removeprefix("parallax-")
        shown = _squash(final_text)
        for helper in journey.get("require_helpers") or []:
            if helper == "render_gate.py" and _stale_plugin_gate(plugin_dir):
                reasons.append("plugin render_gate.py differs from skills/_parallax/render_gate.py; "
                               "rebuild the plugin (build_bundle.py plugin) and re-run")
                continue
            if helper == "render_gate.py":
                met = bool(shown) and any(
                    g["ok"] and g["id"] not in denied_ids and g["key"] == gate_key
                    and _gated_text(g) is not None
                    and shown == _squash(_render(_gated_text(g), gate_key))
                    for g in gate_runs)
                where = ("a Write-tool .parallax-render draft or the stdin form whose gate output "
                         "is the final answer")
            else:
                met = any(
                    r["helper"] == helper and r["ok"] and r["id"] not in denied_ids
                    and _write_draft_before(r["primary"], _POLICY_DRAFT, r["seq"])
                    for r in policy_runs)
                where = "a Write-tool .parallax-policy draft"
            if not met:
                reasons.append(f"required helper {helper} never ran successfully on {where}")
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
    cwd = (parsed["init"] or {}).get("cwd")
    for warning in classify_denials(denials, parsed["bash_calls"], cwd=cwd, plugin_dir=args.plugin_dir)[1]:
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
