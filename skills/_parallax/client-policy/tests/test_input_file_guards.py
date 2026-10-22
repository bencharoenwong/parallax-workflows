"""Input-file guards shared by the three policy helpers.

adaptation.py, coverage_check.py and reconcile.py each read the draft files
the policy docs tell the model to write under `.parallax-policy/`. A symlink,
FIFO or hard link already in that directory must not be read through, and a
FIFO must not hang the helper. Each helper carries its own copy of
`_read_input_file` (they ship as standalone scripts), so every case runs
against all three.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
CLIENT_POLICY_DIR = HERE.parent
PARALLAX_DIR = CLIENT_POLICY_DIR.parent
FIXTURES = HERE / "fixtures"

POLICY_TEXT = (FIXTURES / "policy_full.yaml").read_text(encoding="utf-8")
EXPOSURES_TEXT = (FIXTURES / "exposures_sample.json").read_text(encoding="utf-8")
SECTORS_TEXT = json.dumps({"Technology": 1.0})
RECONCILE_TEXT = json.dumps({
    "basis": "sleeve",
    "holdings": [{"symbol": "AAA.X", "weight": 1.0, "coefficient": 1.0}],
    "position_cap": 1.0, "bands": [], "turnover_penalty": 0.0,
})

# helper -> (script, argv builder for one input path, text of a valid input)
HELPERS = {
    "adaptation": (CLIENT_POLICY_DIR / "adaptation.py",
                   lambda p: ["--policy", p, "--json"], POLICY_TEXT),
    "coverage_check": (PARALLAX_DIR / "coverage_check.py",
                       lambda p: ["--portfolio-sectors", p, "--redundancy-sectors", SECTORS_TEXT],
                       SECTORS_TEXT),
    "reconcile": (CLIENT_POLICY_DIR / "reconcile.py",
                  lambda p: ["--input", p], RECONCILE_TEXT),
}
# Exit code each helper uses for an unreadable input.
READ_FAILURE_EXIT = {"adaptation": 2, "coverage_check": 2, "reconcile": 3}


def _run(helper: str, path: Path, cwd: Path) -> subprocess.CompletedProcess:
    script, argv, _ = HELPERS[helper]
    return subprocess.run(
        [sys.executable, str(script), *argv(str(path))],
        capture_output=True, text=True, timeout=180, cwd=cwd,
    )


def _draft_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".parallax-policy"
    d.mkdir()
    return d


@pytest.mark.parametrize("helper", sorted(HELPERS))
def test_a_regular_draft_is_read(helper, tmp_path):
    draft = _draft_dir(tmp_path) / "input-0a1b2c3d.txt"
    draft.write_text(HELPERS[helper][2], encoding="utf-8")
    proc = _run(helper, draft, tmp_path)
    assert proc.returncode != READ_FAILURE_EXIT[helper] or "error" not in proc.stdout + proc.stderr, (
        proc.stdout + proc.stderr)


@pytest.mark.parametrize("helper", sorted(HELPERS))
def test_a_symlinked_draft_is_refused(helper, tmp_path):
    target = tmp_path / "elsewhere.txt"
    target.write_text(HELPERS[helper][2], encoding="utf-8")
    link = _draft_dir(tmp_path) / "input-0a1b2c3d.txt"
    link.symlink_to(target)
    assert _run(helper, link, tmp_path).returncode == READ_FAILURE_EXIT[helper]


@pytest.mark.parametrize("helper", sorted(HELPERS))
def test_a_symlinked_draft_directory_is_refused(helper, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "input-0a1b2c3d.txt").write_text(HELPERS[helper][2], encoding="utf-8")
    (tmp_path / ".parallax-policy").symlink_to(real)
    draft = tmp_path / ".parallax-policy" / "input-0a1b2c3d.txt"
    assert _run(helper, draft, tmp_path).returncode == READ_FAILURE_EXIT[helper]


@pytest.mark.parametrize("helper", sorted(HELPERS))
def test_a_hard_linked_draft_is_refused(helper, tmp_path):
    target = tmp_path / "elsewhere.txt"
    target.write_text(HELPERS[helper][2], encoding="utf-8")
    link = _draft_dir(tmp_path) / "input-0a1b2c3d.txt"
    os.link(target, link)
    assert _run(helper, link, tmp_path).returncode == READ_FAILURE_EXIT[helper]


@pytest.mark.parametrize("helper", sorted(HELPERS))
def test_a_fifo_draft_fails_without_hanging(helper, tmp_path):
    fifo = _draft_dir(tmp_path) / "input-0a1b2c3d.txt"
    os.mkfifo(fifo)
    assert _run(helper, fifo, tmp_path).returncode == READ_FAILURE_EXIT[helper]


def test_an_operator_symlink_outside_the_draft_dir_is_still_read(tmp_path):
    """policy= may name the RM's own file, which can legitimately be a link."""
    target = tmp_path / "policy-store.yaml"
    target.write_text(POLICY_TEXT, encoding="utf-8")
    link = tmp_path / "client.yaml"
    link.symlink_to(target)
    proc = _run("adaptation", link, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "fallback_tier" in json.loads(proc.stdout)


@pytest.mark.parametrize("flag", ["--exposures", "--view-tilts"])
def test_an_empty_optional_path_is_an_error_not_an_absent_flag(flag, tmp_path):
    """An unexpanded shell variable yields an empty path; it must not be
    silently treated as "no exposures" with exit 0."""
    policy = _draft_dir(tmp_path) / "policy-0a1b2c3d.yaml"
    policy.write_text(POLICY_TEXT, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(CLIENT_POLICY_DIR / "adaptation.py"),
         "--policy", str(policy), flag, "", "--json"],
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 2
    assert "empty path" in proc.stderr
