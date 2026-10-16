"""End-to-end check of evals/concierge_journeys.sh's ground-truth plumbing with a
stub ``claude`` on PATH: no model, no network, no credits.

The stub plays J9: it writes the policy and report drafts where the Write tool
would, runs the real plugin adaptation.py and render_gate.py through the shell
(so the runner's Python start shims and the helpers' run trace both fire), and
prints a stream-json transcript. The test asserts that the runner copies the
trace, the Python start log and the scratch listing out before deleting the
scratch tree, and that the checker's verdict follows them.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")  # adaptation.py needs PyYAML

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "evals" / "concierge_journeys.sh"

STUB = r'''
import json, os, subprocess, sys
args = sys.argv[1:]
plugin = args[args.index("--plugin-dir") + 1]
prompt = args[args.index("-p") + 1]
modes = set(os.environ.get("STUB_MODE", "good").split(","))
cwd = os.getcwd()
out, n = [], [0]

def emit(msg):
    out.append(json.dumps(msg))

def tool(name, tool_input, ok=True):
    n[0] += 1
    tid = f"t{n[0]}"
    emit({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tid, "name": name, "input": tool_input}]}})
    emit({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "is_error": not ok, "content": "ok"}]}})

def write(rel, content):
    path = os.path.join(cwd, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    tool("Write", {"file_path": path, "content": content})

def bash(cmd):
    proc = subprocess.run(["/bin/sh", "-c", cmd], cwd=cwd, capture_output=True, text=True)
    tool("Bash", {"command": cmd}, ok=proc.returncode == 0)
    return proc.stdout

emit({"type": "system", "subtype": "init", "cwd": cwd,
      "plugins": [{"name": "parallax", "path": plugin}],
      "mcp_servers": [{"name": "claude.ai Parallax", "status": "connected"}]})
tool("Skill", {"skill": "parallax:parallax-client-review"})
write(".parallax-policy/.gitignore", "*\n")
write(".parallax-policy/policy-0a1b2c3d.json", prompt.split("policy=", 1)[1])
bash(f"python3 {plugin}/skills/_parallax/client-policy/adaptation.py "
     "--policy .parallax-policy/policy-0a1b2c3d.json --json")
if "own_script" in modes:
    write("tools/check.py", "print('checked')\n")
    bash("python3 tools/check.py")
if "bash_file" in modes:
    bash("printf x > .parallax-policy/notes-11111111.json")
if "stdin_code" in modes:
    bash("python3 - <<'EOF'\nprint(1)\nEOF")
report = "## SAA Drift\nwithin band\n\n## Policy Data Quality\nok\n"
write(".parallax-render/client-review-0a1b2c3d.md", report)
final = bash(f'python3 "{plugin}/skills/_parallax/render_gate.py" --skill client-review '
             f'--input "{cwd}/.parallax-render/client-review-0a1b2c3d.md"')
emit({"type": "result", "subtype": "success", "is_error": False, "result": final,
      "permission_denials": []})
print("\n".join(out))
'''


@pytest.fixture
def run(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "claude"
    stub.write_text(f"#!{sys.executable}\n{STUB}")
    stub.chmod(0o755)
    results = tmp_path / "results"
    temp = tmp_path / "tmp"
    temp.mkdir()

    def _run(mode):
        # An inherited PARALLAX_E2E_* export (timeout, connector, journeys file,
        # dry run) would change what the runner does, so none reaches it. The
        # runner's own timeout is shorter than this test's, so a hung stub is
        # killed by the runner, which then still writes its results.
        inherited = {k: v for k, v in os.environ.items() if not k.startswith("PARALLAX_E2E_")}
        env = {**inherited, "PATH": f"{bin_dir}:{os.environ['PATH']}", "PARALLAX_E2E_LIVE": "1",
               "PARALLAX_E2E_ONLY": "J9", "PARALLAX_E2E_RESULTS_DIR": str(results),
               "PARALLAX_E2E_TIMEOUT": "120", "TMPDIR": str(temp), "STUB_MODE": mode}
        try:
            proc = subprocess.run(["bash", str(RUNNER)], env=env, capture_output=True,
                                  text=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            pytest.fail(f"runner timed out after 180 s\n{_diagnostics(exc, results, temp)}")
        return proc, results, temp

    return _run


def _diagnostics(proc, results: Path, temp: Path) -> str:
    """Everything needed to read a failure from a gate log alone. Assertion
    messages pass it as one str: pytest truncates a non-str message to about
    240 characters under -q."""
    def text(value):
        return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
    def names(path):
        return sorted(p.name for p in path.iterdir()) if path.is_dir() else "absent"
    return (f"returncode: {getattr(proc, 'returncode', None)}\n"
            f"stdout:\n{text(proc.stdout)}\nstderr:\n{text(proc.stderr)}\n"
            f"results: {names(results)}\ntmp: {names(temp)}")


def _one(results: Path, suffix: str, diag: str) -> Path:
    found = sorted(results.glob(f"concierge_J9_*{suffix}"))
    assert len(found) == 1, f"expected one *{suffix}\n{diag}"
    return found[0]


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_a_documented_run_passes_and_the_ground_truth_is_kept(run):
    proc, results, temp = run("good")
    diag = _diagnostics(proc, results, temp)
    assert "PASS: J9_client_review_policy" in proc.stdout, diag
    assert proc.returncode == 0 and "Total: 1, Failed: 0" in proc.stdout, diag
    trace = [json.loads(x) for x in _one(results, ".trace.jsonl", diag).read_text().splitlines()]
    assert [e["helper"] for e in trace] == ["adaptation.py", "render_gate.py"], f"{trace!r}\n{diag}"
    assert all(e["script"].startswith(str((REPO / "plugin").resolve())) for e in trace), (
        f"{trace!r}\n{diag}")
    starts = [json.loads(x)
              for x in _one(results, ".python-starts.jsonl", diag).read_text().splitlines()]
    assert [Path(s["files"][0]).name for s in starts] == ["adaptation.py", "render_gate.py"], (
        f"{starts!r}\n{diag}")
    listing = json.loads(_one(results, ".fs.json", diag).read_text())["entries"]
    paths = {e["path"] for e in listing}
    assert ".parallax-policy/policy-0a1b2c3d.json" in paths, f"{sorted(paths)!r}\n{diag}"
    # the gate deleted the report draft
    assert ".parallax-render/client-review-0a1b2c3d.md" not in paths, f"{sorted(paths)!r}\n{diag}"
    assert not list(temp.glob("concierge_e2e.*")), f"scratch tree left behind\n{diag}"


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_model_written_code_and_bash_files_fail(run):
    proc, results, temp = run("own_script,bash_file,stdin_code")
    diag = _diagnostics(proc, results, temp)
    assert "FAIL: J9_client_review_policy" in proc.stdout, diag
    assert proc.returncode != 0, diag
    for reason in ("file tool wrote code", "ran a Python script outside the plugin",
                   "draft left in the working directory differs from what the Write tool wrote",
                   "ran Python code from stdin"):
        assert reason in proc.stdout, f"missing reason: {reason}\n{diag}"
