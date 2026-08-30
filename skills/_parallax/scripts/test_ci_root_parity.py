"""Hold GitHub CI to the same test set the local pre-push gate runs.

run-gate-tests.sh AUTO-DISCOVERS its roots; .github/workflows/evals.yml
hand-lists a named step per root so a broken root is identifiable from the step
list alone. Nothing made the two agree, and the drift is silent in the direction
that matters: the local gate stays green because it discovered the new tests,
and CI stays green because it never collected them. That has happened twice --
six roots on 2026-08-18, three more after.

The check is file-level, not root-level. CI narrows four roots to a `tests`
subdirectory, so asserting root-set equality would either false-fail on that
legitimate narrowing or miss a test file added beside `tests/` rather than in
it. Asserting that every discovered test FILE is collected by some CI step
covers both.

evals.yml is parsed into a step model and its pytest arguments resolved as
paths; the discovered set comes from invoking the real script rather than a
second copy of its find pipeline, which would drift from it the same way.
"""
from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
GATE_SCRIPT = REPO_ROOT / "skills" / "_parallax" / "scripts" / "run-gate-tests.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "evals.yml"

TEST_GLOBS = ("test_*.py", "*_test.py")


def _discovered_roots() -> list[Path]:
    proc = subprocess.run(
        ["bash", str(GATE_SCRIPT), "--list-roots"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"run-gate-tests.sh --list-roots failed ({proc.returncode}):\n"
        f"{proc.stderr}")
    roots = [REPO_ROOT / line for line in proc.stdout.split("\n") if line.strip()]
    assert roots, "run-gate-tests.sh discovered no roots"
    return roots


def _ci_pytest_paths() -> list[Path]:
    """Every path argument CI hands to pytest, as a resolved path."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    paths = []
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            run = step.get("run") or ""
            if "pytest" not in run:
                continue
            for token in shlex.split(run):
                if token.startswith(("skills/", "evals/")):
                    paths.append(REPO_ROOT / token.rstrip("/"))
    return paths


def _covers(collected: Path, test_file: Path) -> bool:
    return test_file == collected or collected in test_file.parents


def _test_files(root: Path) -> list[Path]:
    return sorted(
        f for glob in TEST_GLOBS for f in root.rglob(glob) if f.is_file())


@pytest.fixture(scope="module")
def ci_paths() -> list[Path]:
    if not WORKFLOW.is_file():
        pytest.skip("this checkout does not carry the CI workflow")
    return _ci_pytest_paths()


def test_ci_collects_every_test_file_the_local_gate_runs(ci_paths):
    uncovered = [
        f for root in _discovered_roots()
        for f in _test_files(root)
        if not any(_covers(p, f) for p in ci_paths)
    ]
    assert uncovered == [], (
        f"{len(uncovered)} test file(s) run by run-gate-tests.sh are never "
        "collected by .github/workflows/evals.yml -- add a step there:\n"
        + "\n".join(str(f.relative_to(REPO_ROOT)) for f in uncovered[:10]))


def test_ci_pytest_paths_all_exist(ci_paths):
    """A renamed or deleted skill leaves a step pointing at nothing. pytest
    exits 4 on a missing path, so this fails the job rather than under-running
    -- but it fails as an opaque usage error, long after the rename."""
    missing = [p for p in ci_paths if not p.exists()]
    assert missing == [], (
        "evals.yml runs pytest against path(s) that do not exist:\n"
        + "\n".join(str(p.relative_to(REPO_ROOT)) for p in missing))


def test_uncovered_root_is_detected(tmp_path):
    """The gate above passes today, so prove it can fail. A discovered root
    whose tests no CI step collects must be reported, and narrowing a root to
    its `tests` subdirectory -- what four real steps do -- must not be."""
    root = tmp_path / "skills" / "parallax-new-skill"
    (root / "tests").mkdir(parents=True)
    inside = root / "tests" / "test_thing.py"
    inside.touch()
    beside = root / "test_beside.py"
    beside.touch()

    assert _test_files(root) == [beside, inside]

    assert not any(_covers(p, inside) for p in [tmp_path / "skills" / "other"])
    assert _covers(root / "tests", inside)
    # The narrowing four steps use: a file beside `tests/` escapes that step.
    assert not _covers(root / "tests", beside)
    assert _covers(root, beside)


def test_list_roots_rejects_an_unknown_argument():
    """--list-roots must not become a way to silently skip the run: any other
    argument is an error, not an ignored token that falls through to pytest."""
    proc = subprocess.run(
        ["bash", str(GATE_SCRIPT), "--nope"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert proc.returncode == 2, proc.stdout
    assert "unexpected argument" in proc.stderr


def test_list_roots_agrees_with_the_repo_layout():
    """The flag is only trustworthy as a parity source if it reports the roots
    that actually hold tests, so check its output against the tree it read."""
    roots = _discovered_roots()
    for root in roots:
        assert root.is_dir(), root
        assert _test_files(root), f"{root} was listed but holds no test files"
    top_level = sorted(
        d for parent in ("skills", "evals") if (REPO_ROOT / parent).is_dir()
        for d in (REPO_ROOT / parent).iterdir() if d.is_dir())
    unlisted = [d for d in top_level if _test_files(d) and d not in roots]
    assert unlisted == [], (
        "dirs hold test files but --list-roots omitted them:\n"
        + "\n".join(str(d.relative_to(REPO_ROOT)) for d in unlisted))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
