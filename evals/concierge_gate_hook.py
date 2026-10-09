"""evals/concierge_gate_hook.py — PreToolUse hook for the live concierge
journeys (evals/concierge_journeys.sh).

Claude Code permission rules cannot approve the render-gate command that every
gated skill runs (parallax-conventions.md §10.3): its ``$(mktemp …)`` command
substitution is never auto-approved by a prefix rule, and it ends with
``rm -f "$DRAFT"``, which the journeys must not allow in general. This hook
approves that one command shape and nothing else:

    DRAFT="$(mktemp "${TMPDIR:-/tmp}/<name>.XXXXXX")"
    cat > "$DRAFT" <<'REPORT'
    <report body; no line may be exactly REPORT>
    REPORT
    python3 "<PLUGIN_DIR>/skills/<any>/../_parallax/render_gate.py" --skill <key> < "$DRAFT"; rm -f "$DRAFT"

The quoted heredoc terminator means the shell does not expand the body. The
render_gate.py path must resolve to this branch's plugin copy. For any other
command the hook prints nothing and exits 0, so normal permission rules apply.

The plugin directory comes from the PARALLAX_E2E_PLUGIN_DIR environment
variable. Pure matcher: ``is_gate_command``; pytested at
evals/graders/test_concierge_gate_hook.py.
"""
from __future__ import annotations

import json
import os
import re
import sys

_MKTEMP = re.compile(r'DRAFT="\$\(mktemp "\$\{TMPDIR:-/tmp\}/[A-Za-z0-9_-]+\.XXXXXX"\)"')
_CAT = "cat > \"$DRAFT\" <<'REPORT'"
_GATE = re.compile(
    r'python3 "?(?P<path>[^"\s;<>|&$`]+)"? --skill (?P<key>[a-z0-9-]+) < "\$DRAFT"; rm -f "\$DRAFT"'
)


def is_gate_command(command: str, plugin_dir: str) -> bool:
    """True only for the exact render-gate command shape, with render_gate.py
    inside ``plugin_dir``."""
    if not isinstance(command, str) or not plugin_dir:
        return False
    lines = command.rstrip("\n").split("\n")
    if len(lines) < 4:
        return False
    if not _MKTEMP.fullmatch(lines[0]) or lines[1] != _CAT:
        return False
    # The shell ends the heredoc at the first line that is exactly REPORT;
    # that line must be the second to last, so nothing else gets executed.
    end = next((i for i in range(2, len(lines)) if lines[i] == "REPORT"), None)
    if end != len(lines) - 2:
        return False
    m = _GATE.fullmatch(lines[-1])
    if not m:
        return False
    expected = os.path.join(os.path.realpath(plugin_dir), "skills", "_parallax", "render_gate.py")
    return os.path.realpath(m.group("path")) == expected


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command", "")
    if is_gate_command(command, os.environ.get("PARALLAX_E2E_PLUGIN_DIR", "")):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "Parallax render gate",
        }}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
