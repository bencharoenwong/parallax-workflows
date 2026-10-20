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
import select
import signal
import shutil
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")  # adaptation.py needs PyYAML

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "evals" / "concierge_journeys.sh"
CHECK = REPO / "evals" / "concierge_journeys_check.py"


def _communicate(proc: subprocess.Popen, timeout: float) -> tuple[str, str]:
    """Collect output; on timeout kill the isolated group, then reap the runner."""
    try:
        return proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # Killing only bash leaves its stub and helper children alive, holding
        # the output pipes open. The caller must use start_new_session=True.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        exc.stdout, exc.stderr = proc.communicate(timeout=10)
        raise


def _wait_for_ready(proc: subprocess.Popen, timeout: float) -> None:
    """Bound startup before the deliberate communicate-timeout check."""
    if not select.select([proc.stdout], [], [], timeout)[0]:
        raise TimeoutError("child did not signal readiness")
    assert os.read(proc.stdout.fileno(), 6) == b"ready\n"


@pytest.mark.skipif(os.name != "posix", reason="runner uses POSIX process groups")
@pytest.mark.parametrize("signals_ready", [True, False])
def test_timeout_kills_descendants_and_keeps_diagnostics(signals_ready):
    parent = (
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print('timeout diagnostic', file=sys.stderr, flush=True)\n"
        f"if {signals_ready!r}: print('ready', flush=True)\n"
        "time.sleep(60)\n"
    )
    with subprocess.Popen([sys.executable, "-c", parent], start_new_session=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
        try:
            if signals_ready:
                _wait_for_ready(proc, timeout=30)
                with pytest.raises(subprocess.TimeoutExpired) as caught:
                    _communicate(proc, timeout=0.1)
                assert proc.returncode == -signal.SIGKILL
                assert "timeout diagnostic" in caught.value.stderr
            else:
                with pytest.raises(TimeoutError, match="did not signal readiness"):
                    _wait_for_ready(proc, timeout=0.1)
        finally:
            if proc.returncode is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            # On either timeout, group cleanup must also close the output
            # pipes inherited by the descendant so collection can finish.
            proc.communicate(timeout=10)
            assert proc.returncode == -signal.SIGKILL


def test_preflight_preserves_prompt_and_selects_full_or_short_ids(tmp_path):
    prompt = "  Unicode 日本語 🙂\n\tquotes ' \" $HOME `pwd` \\ tail  "
    journeys = tmp_path / "journeys.jsonl"
    rows = [{"id": "J1_first", "prompt": prompt},
            {"id": "J2_second", "prompt": "second", "needs": "no-connector"},
            {"id": "J3_third", "prompt": "third"}]
    # Comments, blank lines and a final line without a newline are supported.
    lines = [json.dumps(row) for row in rows]
    journeys.write_text("# comment\n\n" + "\n".join(lines), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(CHECK), "--prepare", str(journeys),
                           "--only", "J1,J2_second,missing"], capture_output=True, timeout=10)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.decode("utf-8").split("\0") == [
        lines[0], "J1_first", prompt, "", lines[1], "J2_second", "second", "no-connector", ""]
    assert b"entry matched no journey: missing" in proc.stderr


@pytest.mark.parametrize("bad_line", [
    "not json", json.dumps({"id": "J2_bad", "prompt": "bad", "unknown": True}),
    json.dumps({"id": "J2_bad", "prompt": "nul\0prompt"}),
    json.dumps({"id": "J2_bad", "prompt": "bad\ud800prompt"}),
    json.dumps({"id": "J2_\udfff", "prompt": "bad"}),
    json.dumps({"id": "J2_bad", "prompt": "bad", "needs": []}),
    json.dumps({"id": "J2_bad", "prompt": "bad", "require_helpers": [{}]}),
])
@pytest.mark.parametrize("only", ["J1", ""])
def test_preflight_rejects_unselected_invalid_line_without_partial_output(tmp_path, bad_line, only):
    journeys = tmp_path / "journeys.jsonl"
    journeys.write_text(json.dumps({"id": "J1_good", "prompt": "good"}) + "\n" + bad_line)
    proc = subprocess.run([sys.executable, str(CHECK), "--prepare", str(journeys),
                           "--only", only], capture_output=True, text=True, timeout=10)
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "invalid journey line 2" in proc.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_dry_run_preflights_all_journeys_with_one_python_start(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    starts = tmp_path / "starts"
    wrapper = bin_dir / "python3"
    wrapper.write_text("#!/bin/sh\n"
                       f"printf 'start\\n' >> {shlex.quote(str(starts))}\n"
                       f"exec {shlex.quote(sys.executable)} \"$@\"\n")
    wrapper.chmod(0o755)
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("PARALLAX_E2E_")}
    env = {**inherited, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "PARALLAX_E2E_DRY_RUN": "1", "PARALLAX_E2E_ONLY": "J2,J9_client_review_policy",
           "PARALLAX_E2E_RESULTS_DIR": str(tmp_path / "results"), "TMPDIR": str(tmp_path)}
    proc = subprocess.run(["bash", str(RUNNER)], env=env, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert starts.read_text().splitlines() == ["start"]
    assert proc.stdout.count("DRY RUN") == 2
    assert "[J2_not_connected]" in proc.stdout
    assert "[J9_client_review_policy]" in proc.stdout
    assert not list(tmp_path.glob("concierge_preflight.*"))

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
      "mcp_deadlines": {key: os.environ.get(key) for key in
                        ("MCP_TOOL_TIMEOUT", "CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT")},
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

    def _run(mode, mcp_timeout=None):
        # An inherited PARALLAX_E2E_* export (timeout, connector, journeys file,
        # dry run) would change what the runner does, so none reaches it. The
        # runner's own timeout is shorter than this test's, so a hung stub is
        # killed by the runner, which then still writes its results.
        inherited = {k: v for k, v in os.environ.items() if not k.startswith("PARALLAX_E2E_")}
        inherited.pop("MCP_TOOL_TIMEOUT", None)
        inherited.pop("CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT", None)
        if mcp_timeout is not None:
            inherited["MCP_TOOL_TIMEOUT"] = mcp_timeout
        env = {**inherited, "PATH": f"{bin_dir}:{os.environ['PATH']}", "PARALLAX_E2E_LIVE": "1",
               "PARALLAX_E2E_ONLY": "J9", "PARALLAX_E2E_RESULTS_DIR": str(results),
               "PARALLAX_E2E_TIMEOUT": "120", "TMPDIR": str(temp), "STUB_MODE": mode}
        with subprocess.Popen(["bash", str(RUNNER)], env=env, start_new_session=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as child:
            try:
                stdout, stderr = _communicate(child, timeout=180)
            except subprocess.TimeoutExpired as exc:
                pytest.fail(f"runner timed out after 180 s\n{_diagnostics(exc, results, temp)}")
            proc = subprocess.CompletedProcess(child.args, child.returncode, stdout, stderr)
        return proc, results, temp

    return _run


@pytest.mark.parametrize("configured", [None, "420000"])
def test_async_deadline_reaches_fresh_claude_session(run, configured):
    proc, results, temp = run("good", mcp_timeout=configured)
    diag = _diagnostics(proc, results, temp)
    assert proc.returncode == 0, diag
    transcripts = [path for path in results.glob("concierge_J9_*.jsonl")
                   if not path.name.endswith((".trace.jsonl", ".python-starts.jsonl"))]
    assert len(transcripts) == 1, diag
    events = [json.loads(line) for line in transcripts[0].read_text().splitlines()]
    init = next(event for event in events if event.get("subtype") == "init")
    assert init["mcp_deadlines"] == {
        "MCP_TOOL_TIMEOUT": configured or "300000",
        "CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT": "0",
    }


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
