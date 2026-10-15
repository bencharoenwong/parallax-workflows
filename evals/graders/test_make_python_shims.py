"""Tests for the live-journey Python start shims (evals/make_python_shims.py)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from make_python_shims import write_shims  # noqa: E402


def _setup(tmp_path):
    real_dir = tmp_path / "venv-bin"
    real_dir.mkdir()
    (real_dir / "python3").symlink_to(sys.executable)
    log = tmp_path / "starts.jsonl"
    log.touch()
    bin_dir = tmp_path / "shims"
    assert write_shims(str(bin_dir), str(log), path=str(real_dir)) == ["python3"]
    return bin_dir, real_dir, log


def test_the_shim_execs_the_interpreter_by_the_path_path_gave(tmp_path):
    """A virtual environment's python3 is a symlink; resolving it would drop the venv."""
    bin_dir, real_dir, _ = _setup(tmp_path)
    text = (bin_dir / "python3").read_text()
    assert f"exec {real_dir / 'python3'} " in text


def test_the_shim_logs_each_argument_file_and_passes_stdin_through(tmp_path):
    bin_dir, _, log = _setup(tmp_path)
    script = tmp_path / "s.py"
    script.write_text("import sys; print(sys.stdin.read().upper())")
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    proc = subprocess.run(["python3", "-W", "ignore", str(script), "missing.py"], input="hi",
                          capture_output=True, text=True, env=env, cwd=tmp_path, timeout=60)
    assert proc.stdout.strip() == "HI"
    (line,) = [json.loads(x) for x in log.read_text().splitlines()]
    assert line["argv"] == ["-W", "ignore", str(script), "missing.py"]
    assert line["files"] == [None, None, os.path.realpath(script), None]
