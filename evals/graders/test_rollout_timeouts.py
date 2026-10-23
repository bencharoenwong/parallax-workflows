"""Exercise the actual rollout subprocess boundary without model or MCP calls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


RUNNER = Path(__file__).resolve().parents[1] / "rollout" / "run_rollout.sh"


@pytest.mark.parametrize("configured", [None, "420000"])
def test_rollout_preserves_async_tool_deadline(tmp_path, configured):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "claude"
    stub.write_text(
        f"#!{sys.executable}\n"
        "import json, os\n"
        "print(json.dumps({key: os.environ.get(key) for key in "
        "('MCP_TOOL_TIMEOUT', 'CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT')}))\n"
    )
    stub.chmod(0o755)
    env = {key: value for key, value in os.environ.items()
           if key not in {"MCP_TOOL_TIMEOUT", "CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT"}
           and not key.startswith("ROLLOUT_")}
    if configured is not None:
        env["MCP_TOOL_TIMEOUT"] = configured
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    proc = subprocess.run(
        ["bash", str(RUNNER), "AAPL.O", "en", "deadline-test"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    output = Path(proc.stdout.strip())
    assert json.loads(output.read_text()) == {
        "MCP_TOOL_TIMEOUT": configured or "300000",
        "CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT": "0",
    }
