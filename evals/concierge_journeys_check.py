"""evals/concierge_journeys_check.py — checker for the live concierge journeys
(see evals/concierge_journeys.sh and evals/tasks/concierge/journeys.jsonl).

Pure functions; the only I/O is reading skills/_parallax/render_gate.py, whose
pure ``gate()`` the render-gate requirement replays, and resolving the plugin
directory's real path:

- ``validate_journey(journey)`` rejects a journey line with unknown keys or
  with ``expect``/``forbid``/``expect_any`` that is not a list of strings.
- ``check_journey(output, journey)`` applies the expect/forbid/expect_any
  substring checks to the final assistant text.
- ``check_run(stream_text, journey, exit_code, timed_out)`` parses a
  ``claude -p --output-format stream-json --verbose`` stream and fails the
  journey closed. Helper and gate runs are credited only from the run's
  ground truth: the run trace the plugin helpers write
  (skills/_parallax/run_trace.py), the Python starts the runner's shims log,
  and a listing of the scratch tree taken before it is deleted. The full list
  of fail conditions is in evals/README.md "Live concierge journeys"; this
  function is the implementation.

The shell runner calls this file's CLI; evals/graders/test_concierge_journeys_check.py
pytests the pure functions on canned text (no model, no network — CI-safe).
"""
from __future__ import annotations

import argparse
import contextlib
import functools
import importlib.util
import io
import hashlib
import json
import os
import posixpath
import re
import sys
from pathlib import Path

ALLOWED_KEYS = frozenset({"id", "prompt", "expect", "forbid", "expect_any", "needs", "skill",
                          "require_helpers"})
LIST_KEYS = ("expect", "forbid", "expect_any", "require_helpers")
# Helpers a journey may require via "require_helpers" (conventions §10.3/§14.4).
# render_gate.py needs the journey's "skill", whose key the gate run must name.
REQUIRABLE_HELPERS = frozenset({"adaptation.py", "audit_append.py", "coverage_check.py",
                                "reconcile.py", "render_gate.py"})
# The argument that names each required helper's payload draft: the group name
# in its documented command (_HELPER_PATTERNS) and the role its run trace
# records. A run counts for "require_helpers" only when this input is a
# Write-tool draft of the kind in _PRIMARY_DRAFT.
_PRIMARY_ARG = {"adaptation.py": "policy", "audit_append.py": "input",
                "coverage_check.py": "portfolio_sectors", "reconcile.py": "input",
                "render_gate.py": "input"}
_PRIMARY_DRAFT = {"adaptation.py": "policy", "audit_append.py": "audit",
                  "coverage_check.py": "policy", "reconcile.py": "policy",
                  "render_gate.py": "report"}
# Helpers that read .parallax-policy drafts (conventions §14.4).
_POLICY_HELPERS = frozenset({"adaptation.py", "coverage_check.py", "reconcile.py"})
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
# Files a skill may leave in its working directory, relative to it: payload
# drafts and their .gitignore (conventions §14.4), report drafts (§10.3) and
# house-view audit row drafts (loader §6). Each must be a Write-tool draft.
_REL_POLICY = re.compile(r"\.parallax-policy/[a-z0-9-]+-[0-9a-f]{8}\.(?:json|yaml)")
_REL_POLICY_IGNORE = ".parallax-policy/.gitignore"
_REL_AUDIT = re.compile(r"\.parallax-render/audit-[0-9a-f]{8}\.json")
_REL_REPORT = re.compile(r"\.parallax-render/(?P<key>[a-z0-9-]+)-[0-9a-f]{8}\.md")
# Top-level scratch entries the runner owns: home/, tmp/ (TMPDIR and
# CLAUDE_CODE_TMPDIR), house-view/ (PARALLAX_HOUSE_VIEW_DIR) and e2e-trace/
# (the trace files and the Python start shims).
_RUNNER_DIRS = frozenset({"home", "tmp", "house-view", "e2e-trace"})
# A command or file tool that names the ground-truth files touches the harness,
# not the task.
_TRACE_NAMES = re.compile(r"e2e-trace|journey-trace|python-starts|PARALLAX_E2E_TRACE")
# A draft directory anywhere in a path; only <cwd>/.parallax-policy/ and
# <cwd>/.parallax-render/ hold drafts.
_DRAFT_DIR = re.compile(r"(?:^|/)\.parallax-(?:policy|render)/", re.IGNORECASE)  # APFS folds case
# Code files: a model-written script. A failure in the working directory; a
# warning in the runner's tmp/ and home/, where tools write code of their own
# (npx installs .js files under home/.npm/_npx).
_SCRIPT_SUFFIX = re.compile(r"\.(?:py|sh|bash|zsh|js|mjs|cjs|ts|rb|pl|php|lua)$")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _draft_kind(rel: str | None) -> tuple[str | None, str | None]:
    """(kind, key) for a working-directory-relative path: ``policy``,
    ``ignore``, ``audit`` or ``report`` (with its skill key), else (None, None)."""
    if rel is None:
        return None, None
    if _REL_POLICY.fullmatch(rel):
        return "policy", None
    if rel == _REL_POLICY_IGNORE:
        return "ignore", None
    if _REL_AUDIT.fullmatch(rel):
        return "audit", None
    m = _REL_REPORT.fullmatch(rel)
    if m:
        return "report", m["key"]
    return None, None


def _python_run(argv: list) -> tuple[str, str, int]:
    """How one Python start runs code, from its arguments: ("inline", code) for
    ``-c``, ("module", name) for ``-m``, ("script", path), ("stdin", "") for
    ``-`` or no program, or ("info", "") for ``--version``/``--help``; with the
    index of the script argument (-1 when there is none)."""
    args = [str(a) for a in argv]
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-V", "--version", "-h", "--help", "-?"):
            return "info", "", -1
        if a in ("-c", "-m"):
            return ("inline" if a == "-c" else "module"), (args[i + 1] if i + 1 < len(args) else ""), -1
        if a == "-":
            return "stdin", "", -1
        if a in ("-W", "-X", "--check-hash-based-pycs"):
            i += 2
            continue
        if a.startswith("-") and len(a) > 1:
            flags = a[1:]
            for j, ch in enumerate(flags):
                if ch in "cm":  # -Ic CODE, -cCODE
                    rest = flags[j + 1:] or (args[i + 1] if i + 1 < len(args) else "")
                    return ("inline" if ch == "c" else "module"), rest, -1
                if ch in "WX":
                    if not flags[j + 1:]:
                        i += 1  # -uW ignore: the next argument is the option's value
                    break
            i += 1
            continue
        return "script", a, i
    return "stdin", "", -1


# The gate whose output a required render-gate run must reproduce. The plugin
# copy is a byte-identical build of this file (build_bundle.py).
_RENDER_GATE = Path(__file__).resolve().parent.parent / "skills" / "_parallax" / "render_gate.py"


@functools.lru_cache(maxsize=1)
def _gate_fn():
    spec = importlib.util.spec_from_file_location("_journey_render_gate", _RENDER_GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.gate


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


def _ground_truth_reasons(
    parsed: dict, journey: dict, final_text: str, commands: list[str], denied_ids: set,
    cwd: str | None, plugin_dir: str | None, trace: list | None,
    python_starts: list | None, snapshot: dict | None,
) -> list[str]:
    """The fail reasons that come from the run's ground truth (evals/README.md
    "Live concierge journeys"). Credit for a helper run comes only from a run
    trace line written by this run's plugin copy of the helper, matched to the
    drafts the model wrote by content hash. Shell text decides only whether
    the model used the documented command form (_HELPER_PATTERNS)."""
    reasons: list[str] = []
    plugin_real = os.path.realpath(plugin_dir).rstrip("/") + "/" if plugin_dir else None

    # The model's tool-side drafts: the last successful write to each path.
    # Only a Write carries the full content, so only a Write has a hash.
    last_write: dict[str, dict] = {}
    for w in parsed["file_writes"]:
        if w["ok"]:
            last_write[_norm_path(w["path"], cwd)] = w
    root = _norm_path(cwd).rstrip("/") + "/" if cwd else None
    drafts: dict[str, dict] = {}
    for path, w in last_write.items():
        rel = path[len(root):] if root and path.startswith(root) else None
        kind, key = _draft_kind(rel)
        # Code is never a skill's output (conventions §14.4), and the draft
        # directories hold drafts only. Other data files (a skill's cache or
        # output) are allowed.
        if (w["content"] or "").startswith("#!") or (kind is None and _SCRIPT_SUFFIX.search(path)):
            reasons.append(f"file tool wrote code (conventions §14.4): {w['path']}")
            continue
        if kind is None:
            if _DRAFT_DIR.search(path):
                reasons.append(f"file tool wrote a non-draft file into a draft directory: {w['path']}")
            continue
        content = w["content"] if w["tool"] == "Write" else None
        drafts[rel] = {"kind": kind, "key": key, "path": w["path"], "tool": w["tool"],
                       "content": content, "sha": _sha(content) if content is not None else None}
    by_sha = {d["sha"]: d for d in drafts.values() if d["sha"]}

    # A command or file tool that names the ground-truth files.
    if any(_TRACE_NAMES.search(t) for t in commands + [w["path"] for w in parsed["file_writes"]]):
        reasons.append("a command or file tool named the run's ground-truth files "
                       "(e2e-trace / PARALLAX_E2E_TRACE)")

    # Trace lines from this run's plugin. A helper of the same name elsewhere
    # (a copy the model made and ran) is a failure, never a credit.
    counted: list[dict] = []
    for e in trace or []:
        if not isinstance(e, dict) or e.get("helper") not in _HELPER_SCRIPT_SUFFIX:
            continue
        script = str(e.get("script") or "")
        if not script.endswith(_HELPER_SCRIPT_SUFFIX[e["helper"]]) or (
                plugin_real and not script.startswith(plugin_real)):
            reasons.append(f"helper {e['helper']} ran from outside the plugin: {script}")
            continue
        counted.append(e)

    def _ins(e: dict) -> list[dict]:
        return [i for i in e.get("inputs") or [] if isinstance(i, dict)]

    for e in counted:
        if any(i.get("source") == "inline" for i in _ins(e)):
            reasons.append(f"{e['helper']} was given a payload inline; conventions §14.4 "
                           "require a .parallax-policy draft")

    # Every draft the model wrote must be used: a payload draft read by a
    # plugin helper (any exit: documented nonzero exits still consume it), a
    # report draft read by a successful render-gate run with its key, an audit
    # row draft read by audit_append.py.
    for rel, d in sorted(drafts.items()):
        if d["kind"] == "ignore":
            continue
        if d["sha"] is None:
            reasons.append(f"draft {d['path']} was last changed by {d['tool']}, so its content "
                           "is unknown; a draft is written once, with Write")
            continue
        read_by = [e for e in counted if any(i.get("sha256") == d["sha"] for i in _ins(e))]
        if d["kind"] == "policy" and not any(e["helper"] in _POLICY_HELPERS for e in read_by):
            reasons.append(f"policy draft never consumed: no plugin helper read {d['path']}")
        elif d["kind"] == "report" and not any(
                e["helper"] == "render_gate.py" and e.get("exit") == 0 and e.get("skill") == d["key"]
                for e in read_by):
            reasons.append(f"report draft never gated: no successful plugin render-gate run "
                           f"with --skill {d['key']} read {d['path']}")
        elif d["kind"] == "audit" and not any(e["helper"] == "audit_append.py" for e in read_by):
            reasons.append(f"audit row draft never appended: audit_append.py never read {d['path']}")

    # Required helpers: a successful plugin run whose every file input is a
    # Write-tool draft and whose primary input is the right kind of draft, plus
    # a successful documented command for the same draft (owner decision A,
    # 2026-10-15: the literal form is what real users' Claude Code allows).
    documented = []
    for c in parsed["bash_calls"]:
        if c["ok"] and c["id"] not in denied_ids:
            m = _match_documented_helper(c["command"])
            if m and _in_plugin(m["script"], cwd, plugin_dir):
                documented.append(m)
    gate_key = (journey.get("skill") or "")[len(PLUGIN_PREFIX):].removeprefix("parallax-")
    shown = " ".join(final_text.split())
    replay_differs = False
    for helper in journey.get("require_helpers") or []:
        role = _PRIMARY_ARG[helper]
        met = False
        for e in counted:
            if e["helper"] != helper or e.get("exit") != 0:
                continue
            ins = _ins(e)
            if any(i.get("source") == "inline" for i in ins) or any(
                    i.get("sha256") not in by_sha for i in ins if i.get("source") == "file"):
                continue
            primary = next((i for i in ins if i.get("role") == role and i.get("source") == "file"), None)
            draft = by_sha.get(primary.get("sha256")) if primary else None
            calls = [m for m in documented if m["helper"] == helper]
            if helper == "render_gate.py":
                if e.get("skill") != gate_key:
                    continue
                text = None
                if draft is not None and draft["kind"] == "report":
                    if any(m.get("body") is None
                           and posixpath.basename(m.get("input") or "") == primary.get("name")
                           for m in calls):
                        text = draft["content"]
                else:
                    stdin = next((i for i in ins if i.get("source") == "stdin"), None)
                    if stdin is not None:
                        # A heredoc sends its body plus one newline: the bytes the gate read.
                        text = next((m["body"] + "\n" for m in calls if m.get("body") is not None
                                     and _sha(m["body"] + "\n") == stdin.get("sha256")), None)
                if text is None:
                    continue
                rendered = _render(text, gate_key)
                if (e.get("output") or {}).get("sha256") != _sha(rendered):
                    replay_differs = True
                    continue
                met = bool(shown) and shown == " ".join(rendered.split())
            else:
                met = draft is not None and draft["kind"] == _PRIMARY_DRAFT[helper] and any(
                    posixpath.basename(m.get(role) or "") == primary.get("name") for m in calls)
            if met:
                break
        if not met:
            if helper == "render_gate.py" and replay_differs:
                reasons.append("plugin render_gate.py output differs from the "
                               "skills/_parallax/render_gate.py replay; rebuild the plugin "
                               "(build_bundle.py plugin) and re-run")
            where = ("a Write-tool .parallax-render draft or the stdin form, as the documented "
                     "command, whose gate output is the final answer"
                     if helper == "render_gate.py" else
                     f"a Write-tool {_PRIMARY_DRAFT[helper]} draft, as the documented command")
            reasons.append(f"required helper {helper} never ran successfully from the plugin on {where}")

    # Python starts: code the model wrote and ran. A plugin script is a
    # documented helper; -c (the white-label loader snippet, integration-pattern
    # §2) and -m are warnings (ground_truth_warnings).
    for start in python_starts or []:
        if not isinstance(start, dict):
            continue
        kind, detail, index = _python_run(start.get("argv") or [])
        if kind == "stdin":
            reasons.append("ran Python code from stdin (code the model wrote): "
                           f"{' '.join(map(str, start.get('argv') or []))[:120] or 'python'}")
        elif kind == "script" and plugin_real:
            files = start.get("files") or []
            script = files[index] if 0 <= index < len(files) else None
            if script is None:
                continue  # no such file: nothing ran (ground_truth_warnings)
            if not _norm_path(str(script)).startswith(_norm_path(plugin_real).rstrip("/") + "/"):
                reasons.append(f"ran a Python script outside the plugin: {script}")

    # The working directory after the run: the draft directories hold only
    # Write-tool drafts, byte for byte as written; no code anywhere.
    for ent in (snapshot or {}).get("entries") or []:
        rel = str(ent.get("path", ""))
        if rel.split("/", 1)[0] in _RUNNER_DIRS or ent.get("type") == "dir":
            continue
        if ent.get("type") != "file":
            reasons.append(f"{ent.get('type')} left in the working directory: {rel}")
            continue
        kind, _ = _draft_kind(rel)
        if kind is not None:
            d = drafts.get(rel)
            if d is None or d["sha"] != ent.get("sha256"):
                reasons.append(f"draft left in the working directory differs from what the Write "
                               f"tool wrote (or the Write tool never wrote it): {rel}")
        elif _DRAFT_DIR.search(rel):
            reasons.append(f"non-draft file left in a draft directory: {rel}")
        elif _SCRIPT_SUFFIX.search(rel) or (ent.get("mode", 0) & 0o111):
            reasons.append(f"script left in the working directory: {rel}")
    return reasons


def ground_truth_warnings(python_starts: list | None, snapshot: dict | None) -> list[str]:
    """Warnings from the ground truth: inline (-c) and module (-m) Python
    starts, a Python start whose script did not exist (nothing ran), and
    script-like files in the runner's tmp/ and home/, where tools write code of
    their own."""
    warnings = []
    for start in python_starts or []:
        if isinstance(start, dict):
            kind, detail, index = _python_run(start.get("argv") or [])
            files = start.get("files") or []
            if kind == "inline":
                warnings.append(f"inline Python (-c): {detail.strip().splitlines()[0][:100] if detail.strip() else ''}")
            elif kind == "module":
                warnings.append(f"python -m {detail}")
            elif kind == "script" and not (0 <= index < len(files) and files[index]):
                warnings.append(f"Python script not found, nothing ran: {detail}")
    for ent in (snapshot or {}).get("entries") or []:
        rel = str(ent.get("path", ""))
        top = rel.split("/", 1)[0]
        if top in ("tmp", "home") and ent.get("type") == "file" and (
                _SCRIPT_SUFFIX.search(rel) or (ent.get("mode", 0) & 0o111)):
            warnings.append(f"script-like file in {top}/: {rel}")
    return warnings


def check_run(
    stream_text: str, journey: dict, exit_code: int, timed_out: bool,
    plugin_dir: str | None = None, trace: list | None = None,
    python_starts: list | None = None, snapshot: dict | None = None,
) -> tuple[bool, list[str], str, str]:
    """Fail-closed check of one live journey run.

    ``plugin_dir``, when given, must be the path of a plugin listed in the
    init message, so the run used this branch's built plugin.

    ``trace`` (run_trace.py lines), ``python_starts`` (shim lines) and
    ``snapshot`` (scratch_snapshot.py output) are the run's ground truth. A
    None skips the checks that need it, except that no helper is ever credited
    without a trace; the CLI fails a run whose ground truth is missing.

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
        reasons.extend(_ground_truth_reasons(
            parsed, journey, final_text, commands, denied_ids, cwd, plugin_dir,
            trace, python_starts, snapshot))
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


def _read_jsonl(path: str | None, label: str, missing: list[str]) -> list | None:
    """The JSON lines in ``path`` (non-JSON lines skipped), or None with a
    note in ``missing`` when the file was not given or cannot be read."""
    if path is None:
        missing.append(f"no {label}")
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        missing.append(f"unreadable {label}: {exc}")
        return None
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI.

    ``concierge_journeys_check.py --validate '<journey-json-line>'``
        exit 0 if the line is a valid journey, 2 with the problems otherwise.
    ``concierge_journeys_check.py '<journey-json-line>' --stream FILE
        --exit-code N [--timed-out] [--plugin-dir DIR] [--text-out FILE]
        --trace FILE --python-starts FILE --fs-snapshot FILE``
        run the fail-closed check, print the Parallax servers seen at init,
        the denials, warnings and tool calls, then PASS or one FAIL line per
        reason; write all assistant text to --text-out; exit 0 on pass, 1 on
        fail. A missing ground-truth file is a FAIL.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("journey")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--stream")
    ap.add_argument("--exit-code", type=int, default=0)
    ap.add_argument("--timed-out", action="store_true")
    ap.add_argument("--plugin-dir")
    ap.add_argument("--text-out")
    ap.add_argument("--trace")
    ap.add_argument("--python-starts")
    ap.add_argument("--fs-snapshot")
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
    missing: list[str] = []
    trace = _read_jsonl(args.trace, "run trace", missing)
    python_starts = _read_jsonl(args.python_starts, "Python start log", missing)
    snapshot = None
    if args.fs_snapshot is None:
        missing.append("no scratch-tree listing (--fs-snapshot)")
    else:
        try:
            with open(args.fs_snapshot, encoding="utf-8") as fh:
                snapshot = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            missing.append(f"unreadable scratch-tree listing: {exc}")
    passed, reasons, _, all_text = check_run(
        stream_text, journey, args.exit_code, args.timed_out, plugin_dir=args.plugin_dir,
        trace=trace, python_starts=python_starts, snapshot=snapshot,
    )
    if missing:
        passed = False
        reasons = [f"{m} (the run predates ground-truth checks, or the run removed the file)"
                   for m in missing] + reasons
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
    for warning in ground_truth_warnings(python_starts, snapshot):
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
