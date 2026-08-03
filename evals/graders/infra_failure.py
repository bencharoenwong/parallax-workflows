"""The single infrastructure-failure predicate, shared by every consumer.

An infra failure is 'the harness/connector broke', as distinct from 'the skill
produced a bad report'. The two must never be conflated: an auth 401 yields an
empty report that would otherwise be mis-scored as a skill failure.

This lives in its own module because two callers need the same answer from
different vantage points and MUST NOT disagree — a run excluded from one report
and averaged into another is worse than either verdict alone:

* ``grade_corpus`` has only the raw stream.
* ``runrecord`` has already parsed the ``result`` event and can read fields the
  regexes cannot see (``api_error_status``, ``subtype``).

Both call ``detect_infra_failure``; the parsed-result caller passes ``result=``
to enable the extra checks. The stream-level rules are identical either way.
"""
from __future__ import annotations

import json
import re
from typing import Any

# Auth rejection. Whitespace-tolerant on purpose: the same stream is emitted
# both compactly (`"error_status":401`) and pretty-printed (`"status": 401`),
# and a literal-substring test silently passes on the spaced form.
#
# Matched per event with tool-result payloads excluded, never against the whole
# stream: these alternatives are broad enough that a Parallax response quoting
# an HTTP status table (`get_docs`, `explain_methodology`) would otherwise read
# as a connector auth failure and silently shrink the aggregate. Auth rejection
# is reported by the harness — in the result/system events and the assistant's
# own text — not inside a payload a tool handed back.
_AUTH_RE = re.compile(
    r'"(?:error_)?status":\s*401(?!\d)'
    r'|authentication_failed'
    r'|Invalid authentication'
    r'|401\s+Unauthorized',
    re.I,
)
_RESULT_RE = re.compile(r'"type":\s*"result"')

# Connector state is read from the init event's `mcp_servers` entries, never by
# scanning the transcript for the word "parallax": the rollout prompt is the
# skill command itself (`/parallax-should-i-buy AAPL`, echoed back as a user
# event) and every tool name is `mcp__claude_ai_Parallax__*`, so that word is
# present in EVERY captured stream — including one where the connector failed to
# load. A whole-stream substring test therefore never fires when it matters.
_PARALLAX_RE = re.compile(r"parallax", re.I)
_CONNECTED_STATES = frozenset({"", "connected", "ok", "ready", "running", "active"})

# Fallback signals, used only when a stream carries no parseable init event
# (hand-written fixtures, truncated captures). Proximity-bound so an unrelated
# "failed to connect" cannot pair with an unrelated "mcp server" paragraphs away.
_EMPTY_MCP_RE = re.compile(r'"mcp_servers":\s*\[\s*\]')
_MCP_PROSE_RE = re.compile(
    r'no mcp servers configured'
    r'|mcp server[^\n]{0,120}?failed to connect'
    r'|failed to connect[^\n]{0,120}?mcp server',
    re.I,
)

_UNPARSED = object()


def _init_mcp_servers(raw: str) -> list | None:
    """The `mcp_servers` list from the stream's system/init event, or None."""
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") != "system" or event.get("subtype") != "init":
            continue
        servers = event.get("mcp_servers")
        if isinstance(servers, list):
            return servers
    return None


def _without_tool_results(event: dict) -> dict | None:
    """``event`` with its tool-result blocks dropped, or None if it carries none."""
    message = event.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, list):
        return None
    kept = [
        block
        for block in content
        if not (isinstance(block, dict) and block.get("type") == "tool_result")
    ]
    if len(kept) == len(content):
        return None
    return {**event, "message": {**message, "content": kept}}


def _has_auth_failure(raw: str) -> bool:
    """True when the harness itself reported a 401, ignoring tool payloads.

    Scans line by line so a tool result quoting a status code cannot vouch for
    the connector's state. Lines that do not parse as a JSON object (hand-written
    fixtures, truncated captures) are scanned verbatim, and so is any event that
    carries no tool result — preserving the raw spacing the regex tolerates.
    """
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            event = None
        scrubbed = _without_tool_results(event) if isinstance(event, dict) else None
        if scrubbed is None:
            if _AUTH_RE.search(line):
                return True
        elif _AUTH_RE.search(json.dumps(scrubbed)):
            return True
    return False


def _is_parallax(server: Any) -> bool:
    if isinstance(server, str):
        return bool(_PARALLAX_RE.search(server))
    if isinstance(server, dict):
        return any(
            _PARALLAX_RE.search(str(server.get(key, "")))
            for key in ("name", "serverName", "server")
        )
    return False


def _is_connected(server: Any) -> bool:
    """A server entry with no status field is assumed up; only an explicit
    non-connected state counts as a failure."""
    if not isinstance(server, dict):
        return True
    return str(server.get("status", "")).strip().lower() in _CONNECTED_STATES


def detect_infra_failure(raw: str, result: Any = _UNPARSED) -> str | None:
    """Return an infrastructure-failure reason for a stream, or None if gradeable.

    ``result`` is the stream's parsed ``result`` event when the caller already
    has it — ``None`` meaning 'the stream has no result event'. Omit it and the
    presence of that event is detected from ``raw`` instead.
    """
    if not raw.strip():
        return "empty stream (no output captured)"
    if _has_auth_failure(raw):
        return "authentication error (401) — no valid credentials in the session"

    if result is _UNPARSED:
        if not _RESULT_RE.search(raw):
            return "no result event — run interrupted/aborted"
    elif result is None:
        return "no result event — run interrupted/aborted"
    else:
        if result.get("api_error_status"):
            return f"api error {result['api_error_status']}"
        if result.get("subtype") not in (None, "success"):
            return f"result subtype {result['subtype']}"

    servers = _init_mcp_servers(raw)
    if servers is not None:
        parallax = [s for s in servers if _is_parallax(s)]
        if not parallax:
            return "no Parallax MCP server loaded (connector missing)"
        if not any(_is_connected(s) for s in parallax):
            return "Parallax MCP server did not connect (connector unavailable)"
    elif _EMPTY_MCP_RE.search(raw) or _MCP_PROSE_RE.search(raw):
        return "no Parallax MCP server loaded (connector missing)"
    return None
