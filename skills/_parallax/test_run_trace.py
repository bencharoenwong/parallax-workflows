"""Unit tests for the live-journey run trace (run_trace.py).

Run: python3 -m pytest skills/_parallax/test_run_trace.py -q
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


@pytest.fixture
def rt():
    """A fresh copy of run_trace, so module state never leaks between tests."""
    spec = importlib.util.spec_from_file_location("_run_trace_under_test", HERE / "run_trace.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def trace(tmp_path, monkeypatch):
    path = tmp_path / "journey-trace.jsonl"
    path.touch()
    path.chmod(0o600)
    monkeypatch.setenv("PARALLAX_E2E_TRACE", str(path))
    return path


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_finish_appends_one_line_with_digests_and_no_text(rt, trace):
    rt.note_input(b"secret policy text", role="policy")
    rt.note_output(b"rendered report")
    rt.note_skill("client-review")
    rt.finish("adaptation.py", __file__, 0)
    (entry,) = _lines(trace)
    assert entry == {
        "v": 1, "helper": "adaptation.py", "script": os.path.realpath(__file__), "exit": 0,
        "inputs": [{"role": "policy", "source": "file", "name": None,
                    "sha256": hashlib.sha256(b"secret policy text").hexdigest(), "size": 18}],
        "output": {"sha256": hashlib.sha256(b"rendered report").hexdigest(), "size": 15},
        "skill": "client-review",
    }
    assert b"secret" not in trace.read_bytes() and b"rendered" not in trace.read_bytes()


def test_roles_resolve_from_paths(rt, trace):
    rt.note_input(b"a", path="/w/.parallax-policy/policy-0a1b2c3d.json")
    rt.note_input(b"b", path="/w/other.json")
    rt.note_roles({"policy": "/w/.parallax-policy/policy-0a1b2c3d.json", "exposures": None})
    rt.finish("adaptation.py", __file__, 2)
    (entry,) = _lines(trace)
    assert [i["role"] for i in entry["inputs"]] == ["policy", None]
    assert [i["name"] for i in entry["inputs"]] == ["policy-0a1b2c3d.json", "other.json"]
    assert entry["exit"] == 2


def test_inline_and_stdin_inputs_carry_their_source_and_no_name(rt, trace):
    rt.note_input(b"{}", role="portfolio_sectors", path="{}", source="inline")
    rt.note_input(b"report", role="stdin", source="stdin")
    rt.finish("coverage_check.py", __file__, 0)
    (entry,) = _lines(trace)
    assert [(i["source"], i["name"]) for i in entry["inputs"]] == [("inline", None), ("stdin", None)]


@pytest.mark.parametrize("key, want", [("client-review", "client-review"), ("../x", None),
                                       ("Client", None), ("a" * 65, None)])
def test_skill_key_is_validated(rt, trace, key, want):
    rt.note_skill(key)
    rt.finish("render_gate.py", __file__, 0)
    assert _lines(trace)[0]["skill"] == want


def test_refuses_any_other_file_name(rt, tmp_path, monkeypatch):
    other = tmp_path / "notes.txt"
    other.touch()
    other.chmod(0o600)
    monkeypatch.setenv("PARALLAX_E2E_TRACE", str(other))
    rt.finish("reconcile.py", __file__, 0)
    assert other.read_bytes() == b""


def test_refuses_a_group_or_world_accessible_file(rt, trace):
    trace.chmod(0o644)
    rt.finish("reconcile.py", __file__, 0)
    assert trace.read_bytes() == b""


def test_appends_never_truncates(rt, trace):
    trace.write_text('{"earlier": true}\n')
    rt.finish("reconcile.py", __file__, 0)
    lines = trace.read_text().splitlines()
    assert lines[0] == '{"earlier": true}' and len(lines) == 2


def test_unset_variable_writes_nothing(rt, tmp_path, monkeypatch):
    monkeypatch.delenv("PARALLAX_E2E_TRACE", raising=False)
    rt.finish("reconcile.py", __file__, 0)
    assert list(tmp_path.iterdir()) == []


def test_never_creates_the_file(rt, tmp_path, monkeypatch):
    target = tmp_path / "journey-trace.jsonl"
    monkeypatch.setenv("PARALLAX_E2E_TRACE", str(target))
    rt.finish("reconcile.py", __file__, 0)
    assert not target.exists()


def test_refuses_a_symlinked_trace(rt, tmp_path, monkeypatch):
    real = tmp_path / "real.jsonl"
    real.touch()
    real.chmod(0o600)
    (tmp_path / "d").mkdir()
    link = tmp_path / "d" / "journey-trace.jsonl"
    link.symlink_to(real)
    monkeypatch.setenv("PARALLAX_E2E_TRACE", str(link))
    rt.finish("reconcile.py", __file__, 0)
    assert real.read_bytes() == b""


def test_refuses_a_hard_linked_trace(rt, tmp_path, monkeypatch):
    real = tmp_path / "journey-trace.jsonl"
    real.touch()
    real.chmod(0o600)
    os.link(real, tmp_path / "second.jsonl")
    monkeypatch.setenv("PARALLAX_E2E_TRACE", str(real))
    rt.finish("reconcile.py", __file__, 0)
    assert real.read_bytes() == b""


def test_refuses_a_fifo_without_blocking(rt, tmp_path, monkeypatch):
    fifo = tmp_path / "journey-trace.jsonl"
    os.mkfifo(fifo, 0o600)
    monkeypatch.setenv("PARALLAX_E2E_TRACE", str(fifo))
    rt.finish("reconcile.py", __file__, 0)  # returns: no reader, O_NONBLOCK open fails


def test_refuses_a_directory(rt, tmp_path, monkeypatch):
    (tmp_path / "journey-trace.jsonl").mkdir(mode=0o700)
    monkeypatch.setenv("PARALLAX_E2E_TRACE", str(tmp_path / "journey-trace.jsonl"))
    rt.finish("reconcile.py", __file__, 0)


def test_run_records_the_return_code(rt, trace):
    assert rt.run("render_gate.py", __file__, lambda: 2) == 2
    assert _lines(trace)[0]["exit"] == 2


def test_run_records_and_reraises_system_exit(rt, trace):
    def main():
        raise SystemExit(2)
    with pytest.raises(SystemExit):
        rt.run("render_gate.py", __file__, main)
    assert _lines(trace)[0]["exit"] == 2


def test_run_records_exit_1_on_an_uncaught_exception(rt, trace):
    def main():
        raise RuntimeError("boom")
    with pytest.raises(RuntimeError):
        rt.run("render_gate.py", __file__, main)
    assert _lines(trace)[0]["exit"] == 1


def test_run_maps_none_to_0(rt, trace):
    assert rt.run("render_gate.py", __file__, lambda: None) == 0
    assert _lines(trace)[0]["exit"] == 0
