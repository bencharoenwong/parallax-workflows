"""Each wired helper writes one run-trace line when PARALLAX_E2E_TRACE is set,
and nothing when it is not (run_trace.py; evals/README.md § Live concierge journeys).

Run: python3 -m pytest skills/_parallax/test_run_trace_helpers.py -q
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PARALLAX = Path(__file__).resolve().parent
RENDER_GATE = PARALLAX / "render_gate.py"
COVERAGE = PARALLAX / "coverage_check.py"
ADAPTATION = PARALLAX / "client-policy" / "adaptation.py"
RECONCILE = PARALLAX / "client-policy" / "reconcile.py"
AUDIT_APPEND = PARALLAX / "house-view" / "audit_append.py"

POLICY = json.dumps({
    "metadata": {"schema_version": 1, "policy_id": "b41d7e60-2c19-4a83-8f77-1d0c9a2b4e55",
                 "policy_name": "Test", "client_ref": "acct", "supplied_by": "rm@firm.example",
                 "supplied_at": "2026-10-13T00:00:00Z", "as_of_date": "2026-09-30",
                 "review_due": "2027-03-31", "calibration_status": "heuristic_phase0"},
    "mandate": {"base_currency": "USD", "strategic_allocation": {"equity": 0.6},
                "allocation_bands": {"equity": {"min": 0.5, "max": 0.7}},
                "tactical_overlay": {"enabled": False}, "prohibited_products": []},
    "adaptation": {"k_preset": "balanced", "k": None},
    "governance": {"human_review_recorded": []},
})


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def work(tmp_path):
    trace = tmp_path / "e2e-trace" / "journey-trace.jsonl"
    trace.parent.mkdir()
    trace.touch()
    trace.chmod(0o600)
    env = {**os.environ, "PARALLAX_E2E_TRACE": str(trace),
           "PARALLAX_HOUSE_VIEW_DIR": str(tmp_path / "house-view")}
    return tmp_path, trace, env


def _run(args, cwd, env, stdin=None):
    return subprocess.run([sys.executable, *map(str, args)], cwd=cwd, env=env, input=stdin,
                          capture_output=True, timeout=60)


def _draft(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _entries(trace: Path) -> list[dict]:
    return [json.loads(line) for line in trace.read_text().splitlines()]


def test_render_gate_file_form_records_input_skill_and_output(work):
    root, trace, env = work
    body = "## Report\n\nbody\n"
    draft = _draft(root, ".parallax-render/client-review-0a1b2c3d.md", body)
    proc = _run([RENDER_GATE, "--skill", "client-review", "--input", draft], root, env)
    assert proc.returncode == 0
    (entry,) = _entries(trace)
    assert entry["helper"] == "render_gate.py" and entry["exit"] == 0
    assert entry["script"] == os.path.realpath(RENDER_GATE)
    assert entry["skill"] == "client-review"
    assert entry["inputs"] == [{"role": "input", "source": "file", "name": "client-review-0a1b2c3d.md",
                                "sha256": _sha(body.encode()), "size": len(body.encode())}]
    assert entry["output"]["sha256"] == _sha(proc.stdout)


def test_render_gate_stdin_form_records_the_bytes_a_heredoc_sends(work):
    root, trace, env = work
    body = "## Report\n\nbody"
    script = f"{sys.executable} {RENDER_GATE} --skill client-review <<'REPORT'\n{body}\nREPORT\n"
    proc = subprocess.run(["bash", "-c", script], cwd=root, env=env, capture_output=True, timeout=60)
    assert proc.returncode == 0
    (entry,) = _entries(trace)
    assert entry["inputs"][0]["role"] == "stdin" and entry["inputs"][0]["source"] == "stdin"
    assert entry["inputs"][0]["sha256"] == _sha((body + "\n").encode())


def test_render_gate_refused_draft_records_exit_2_and_no_input(work):
    root, trace, env = work
    proc = _run([RENDER_GATE, "--skill", "client-review", "--input", root / "report.md"], root, env)
    assert proc.returncode == 2
    (entry,) = _entries(trace)
    assert entry["exit"] == 2 and entry["inputs"] == []


def test_adaptation_records_each_role(work):
    root, trace, env = work
    policy = _draft(root, ".parallax-policy/policy-0a1b2c3d.json", POLICY)
    exposures = _draft(root, ".parallax-policy/exposures-11111111.json", '{"basis": "nope"}')
    proc = _run([ADAPTATION, "--policy", ".parallax-policy/policy-0a1b2c3d.json",
                 "--exposures", exposures, "--json"], root, env)
    (entry,) = _entries(trace)
    assert entry["helper"] == "adaptation.py" and entry["exit"] == proc.returncode == 2
    assert [(i["role"], i["name"], i["sha256"]) for i in entry["inputs"]] == [
        ("policy", "policy-0a1b2c3d.json", _sha(policy.read_bytes())),
        ("exposures", "exposures-11111111.json", _sha(exposures.read_bytes())),
    ]


def test_reconcile_records_its_input(work):
    root, trace, env = work
    payload = _draft(root, ".parallax-policy/reconcile-22222222.json", "{}")
    proc = _run([RECONCILE, "--input", payload], root, env)
    (entry,) = _entries(trace)
    assert entry["helper"] == "reconcile.py" and entry["exit"] == proc.returncode
    assert [(i["role"], i["sha256"]) for i in entry["inputs"]] == [("input", _sha(b"{}"))]


def test_coverage_check_records_inline_and_file_inputs(work):
    root, trace, env = work
    sectors = _draft(root, ".parallax-policy/portfolio-sectors-33333333.json",
                     '[{"sector": "Technology", "weight": 1.0}]')
    inline = '{"Technology": 1.0}'
    proc = _run([COVERAGE, "--portfolio-sectors", sectors, "--redundancy-sectors", inline], root, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    (entry,) = _entries(trace)
    assert [(i["role"], i["source"], i["name"]) for i in entry["inputs"]] == [
        ("portfolio_sectors", "file", "portfolio-sectors-33333333.json"),
        ("redundancy_sectors", "inline", None),
    ]
    assert entry["inputs"][1]["sha256"] == _sha(inline.encode())


def test_audit_append_records_one_entry_for_itself(work):
    root, trace, env = work
    row = json.dumps({"ts": "2026-10-15T00:00:00Z", "view_id": "v", "version_id": "1",
                      "skill": "client-review", "action": "applied", "applied": True})
    draft = _draft(root, ".parallax-render/audit-44444444.json", row)
    proc = _run([AUDIT_APPEND, "--input", draft], root, env)
    (entry,) = _entries(trace)
    assert entry["helper"] == "audit_append.py" and entry["exit"] == proc.returncode
    assert [(i["role"], i["sha256"]) for i in entry["inputs"]] == [("input", _sha(row.encode()))]


def test_argparse_error_is_recorded(work):
    root, trace, env = work
    proc = _run([ADAPTATION], root, env)
    assert proc.returncode == 2
    assert _entries(trace)[0]["exit"] == 2


def _real_args(root: Path, script: Path) -> list[str]:
    """A real invocation of each helper that reads an input file."""
    if script == RENDER_GATE:
        return ["--skill", "client-review", "--input",
                str(_draft(root, ".parallax-render/client-review-0a1b2c3d.md", "## R\n"))]
    if script == COVERAGE:
        sectors = _draft(root, ".parallax-policy/portfolio-sectors-33333333.json",
                         '[{"sector": "Technology", "weight": 1.0}]')
        return ["--portfolio-sectors", str(sectors), "--redundancy-sectors", '{"Technology": 1.0}']
    if script == ADAPTATION:
        return ["--policy", str(_draft(root, ".parallax-policy/policy-0a1b2c3d.json", POLICY)), "--json"]
    if script == RECONCILE:
        return ["--input", str(_draft(root, ".parallax-policy/reconcile-22222222.json", "{}"))]
    return ["--input", str(_draft(root, ".parallax-render/audit-44444444.json", '{"ts": "x"}'))]


@pytest.mark.parametrize("script", [RENDER_GATE, COVERAGE, ADAPTATION, RECONCILE, AUDIT_APPEND])
def test_unset_variable_writes_nothing_and_loads_nothing(work, script):
    root, trace, env = work
    env = {k: v for k, v in env.items() if k != "PARALLAX_E2E_TRACE"}
    argv = [str(script), *_real_args(root, script)]
    probe = (f"import runpy, sys; sys.argv = {argv!r}\n"
             "try:\n    runpy.run_path(sys.argv[0], run_name='__main__')\n"
             "except SystemExit:\n    pass\n"
             "assert '_parallax_run_trace' not in sys.modules, 'trace module loaded'\n")
    proc = subprocess.run([sys.executable, "-c", probe], cwd=root, env=env, capture_output=True,
                          timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert trace.read_bytes() == b""


def test_unset_variable_leaves_output_and_exit_code_unchanged(work):
    root, trace, env = work
    draft = _draft(root, ".parallax-render/client-review-0a1b2c3d.md", "## R\nbody\n")
    traced = _run([RENDER_GATE, "--skill", "client-review", "--input", draft], root, env)
    draft = _draft(root, ".parallax-render/client-review-0a1b2c3d.md", "## R\nbody\n")
    plain_env = {k: v for k, v in env.items() if k != "PARALLAX_E2E_TRACE"}
    plain = _run([RENDER_GATE, "--skill", "client-review", "--input", draft], root, plain_env)
    assert (traced.returncode, traced.stdout, traced.stderr) == (plain.returncode, plain.stdout, plain.stderr)
