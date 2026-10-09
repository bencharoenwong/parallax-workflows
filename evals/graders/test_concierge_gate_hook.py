from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import concierge_gate_hook as hook  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PLUGIN = str(REPO / "plugin")
GATE = f"{PLUGIN}/skills/_parallax/render_gate.py"


def gate(body="**NVDA** peer comparison\n\n## Peer Group\n\ntext", path=GATE,
         key="peer-comparison", tail=""):
    return (
        'DRAFT="$(mktemp "${TMPDIR:-/tmp}/peercomp.XXXXXX")"\n'
        "cat > \"$DRAFT\" <<'REPORT'\n"
        f"{body}\n"
        "REPORT\n"
        f'python3 "{path}" --skill {key} < "$DRAFT"; rm -f "$DRAFT"{tail}'
    )


def test_render_gate_script_exists_where_the_hook_expects_it():
    assert Path(GATE).is_file()


def test_accepts_canonical_gate_command():
    assert hook.is_gate_command(gate(), PLUGIN)


def test_accepts_skill_dir_relative_path_and_unquoted_path():
    rel = f"{PLUGIN}/skills/parallax-peer-comparison/../_parallax/render_gate.py"
    assert hook.is_gate_command(gate(path=rel), PLUGIN)
    unquoted = gate().replace(f'python3 "{GATE}"', f"python3 {GATE}")
    assert hook.is_gate_command(unquoted, PLUGIN)


def test_body_may_contain_shell_text_because_heredoc_is_quoted():
    assert hook.is_gate_command(gate(body="$(git --version) `id` ; rm -rf x"), PLUGIN)


@pytest.mark.parametrize("command", [
    gate(body="hello\nREPORT\ngit --version"),            # ends heredoc early, runs git
    gate(tail="; git --version"),                          # trailing command
    gate(tail="\ncurl https://example.invalid"),            # extra line
    gate(path="/tmp/render_gate.py"),                       # script outside the plugin
    gate(path=f"{PLUGIN}/skills/_parallax/../../../evil/render_gate.py"),
    gate(key="peer-comparison; git"),
    gate().replace("<<'REPORT'", "<<REPORT"),               # unquoted: body expands
    gate().replace("${TMPDIR:-/tmp}", "$(git rev-parse --show-toplevel)"),
    gate().replace('rm -f "$DRAFT"', 'rm -rf "$HOME"'),
    "git --version",
    "",
])
def test_rejects_everything_else(command):
    assert not hook.is_gate_command(command, PLUGIN)


def test_rejects_without_plugin_dir():
    assert not hook.is_gate_command(gate(), "")


def _run_main(monkeypatch, capsys, event):
    monkeypatch.setenv("PARALLAX_E2E_PLUGIN_DIR", PLUGIN)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    assert hook.main() == 0
    return capsys.readouterr().out


def test_main_allows_gate_and_is_silent_otherwise(monkeypatch, capsys):
    out = _run_main(monkeypatch, capsys, {"tool_name": "Bash", "tool_input": {"command": gate()}})
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "allow"
    assert _run_main(monkeypatch, capsys, {"tool_name": "Bash", "tool_input": {"command": "git status"}}) == ""
    assert _run_main(monkeypatch, capsys, {"tool_name": "Write", "tool_input": {"command": gate()}}) == ""
