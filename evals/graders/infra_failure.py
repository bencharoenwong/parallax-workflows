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

import re
from typing import Any

# Auth rejection. Whitespace-tolerant on purpose: the same stream is emitted
# both compactly (`"error_status":401`) and pretty-printed (`"status": 401`),
# and a literal-substring test silently passes on the spaced form.
_AUTH_RE = re.compile(
    r'"(?:error_)?status":\s*401'
    r'|authentication_failed'
    r'|Invalid authentication'
    r'|401\s+Unauthorized',
    re.I,
)
_RESULT_RE = re.compile(r'"type":\s*"result"')

# Connector missing. The init event's empty server list is the machine-readable
# form; the prose forms below are what a failed launch prints instead. Both are
# proximity-bound so an unrelated "failed to connect" elsewhere in a long
# transcript cannot pair with an unrelated "mcp server".
_EMPTY_MCP_RE = re.compile(r'"mcp_servers":\s*\[\s*\]')
_MCP_PROSE_RE = re.compile(
    r'no mcp servers configured'
    r'|mcp server[^\n]{0,120}?failed to connect'
    r'|failed to connect[^\n]{0,120}?mcp server',
    re.I,
)

_UNPARSED = object()


def detect_infra_failure(raw: str, result: Any = _UNPARSED) -> str | None:
    """Return an infrastructure-failure reason for a stream, or None if gradeable.

    ``result`` is the stream's parsed ``result`` event when the caller already
    has it — ``None`` meaning 'the stream has no result event'. Omit it and the
    presence of that event is detected from ``raw`` instead.
    """
    if not raw.strip():
        return "empty stream (no output captured)"
    if _AUTH_RE.search(raw):
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

    # The `parallax` guard keeps a run that merely reports an empty list for
    # some *other* server from being called a missing Parallax connector.
    if (_EMPTY_MCP_RE.search(raw) or _MCP_PROSE_RE.search(raw)) \
            and "parallax" not in raw.lower():
        return "no Parallax MCP server loaded (connector missing)"
    return None
