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

The parse must UNDER-approximate rather than over-approximate. A path this
module credits to CI that CI does not actually collect is a hole in the gate
itself, so a step contributes only the positional arguments of a sub-command
that really invokes pytest: comments, option values and non-pytest commands
(`pip install -r <path>`) are not coverage. A step that reaches pytest through
a wrapper this parser cannot read therefore reports its files as uncovered,
which fails loudly instead of passing on an assumption.
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

# Options whose VALUE is a separate token. `-m "not npx"` is the one this
# workflow uses; the rest are pytest options whose value can itself look like a
# repo path, which is exactly what must not be mistaken for a collected root.
VALUE_OPTIONS = frozenset({
    "-m", "-k", "-p", "-o", "-c", "-W", "-n", "-r",
    "--rootdir", "--ignore", "--ignore-glob", "--deselect", "--confcutdir",
})
COMMAND_SEPARATORS = frozenset({"&&", "||", ";", "|"})

# Options that subtract from, or reinterpret, the set of files a positional
# argument collects. `-m` and `-k` are absent on purpose: they select within a
# file, so the file is still collected and file-level coverage still holds.
# These, by contrast, would let a positional keep crediting a file that pytest
# never runs -- the over-approximation this module's contract forbids. The
# parser does not model them, so it refuses the invocation instead of guessing.
UNMODELED_OPTIONS = frozenset({
    "--ignore", "--ignore-glob", "--deselect", "--collect-only", "--co",
    "--pyargs",
})


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


def _sub_commands(tokens: list[str]) -> list[list[str]]:
    commands: list[list[str]] = [[]]
    for token in tokens:
        if token in COMMAND_SEPARATORS:
            commands.append([])
        else:
            commands[-1].append(token)
    return [c for c in commands if c]


def _pytest_argv(command: list[str]) -> list[str] | None:
    """The arguments after the pytest command word, or None if not pytest."""
    head = Path(command[0]).name
    if head == "pytest":
        return command[1:]
    if head.startswith("python") and command[1:3] == ["-m", "pytest"]:
        return command[3:]
    return None


def _unmodeled_options(argv: list[str]) -> list[str]:
    return [token for token in argv
            if token.split("=", 1)[0] in UNMODELED_OPTIONS]


def _positional_args(argv: list[str]) -> list[str]:
    positionals = []
    skip_next = False
    for token in argv:
        if skip_next:
            skip_next = False
            continue
        if token in VALUE_OPTIONS:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        positionals.append(token)
    return positionals


def _ci_pytest_paths(workflow_text: str | None = None) -> list[Path]:
    """Every path argument CI actually hands to pytest, as a resolved path."""
    if workflow_text is None:
        workflow_text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    paths = []
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            run = step.get("run") or ""
            for line in run.replace("\\\n", " ").splitlines():
                if not line.strip():
                    continue
                try:
                    tokens = shlex.split(line, comments=True)
                except ValueError as exc:
                    pytest.fail(
                        f"step {step.get('name')!r} has a line this gate cannot "
                        f"parse, so its pytest arguments cannot be checked: "
                        f"{exc}\n  {line.strip()}")
                for command in _sub_commands(tokens):
                    argv = _pytest_argv(command)
                    if argv is None:
                        continue
                    unmodeled = _unmodeled_options(argv)
                    if unmodeled:
                        pytest.fail(
                            f"step {step.get('name')!r} narrows pytest "
                            f"collection with {' '.join(unmodeled)}, which this "
                            "gate does not model. Its positional paths would "
                            "credit files pytest never collects. Teach "
                            "_ci_pytest_paths to subtract them before using "
                            "this option here.")
                    for arg in _positional_args(argv):
                        if arg.startswith(("skills/", "evals/")):
                            paths.append(REPO_ROOT / arg.rstrip("/"))
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


def _workflow(*runs: str) -> str:
    steps = "\n".join(
        f"      - name: step-{i}\n        run: |\n"
        + "\n".join(f"          {line}" for line in run.splitlines())
        for i, run in enumerate(runs))
    return "jobs:\n  structural:\n    steps:\n" + steps


def test_a_comment_naming_a_test_path_is_not_coverage():
    """The install step names paths in prose and hands paths to `pip -r`. If
    either counted as coverage, a skill could be mentioned in a dependency
    comment, have no pytest step, and still pass this gate -- the exact drift
    it exists to catch."""
    text = _workflow(
        "# somedep: needed by skills/parallax-foo/tests/test_foo.py\n"
        "python -m pip install pytest\n"
        "python -m pip install -r skills/_parallax/house-view/requirements.txt")

    assert _ci_pytest_paths(text) == []


def test_option_values_are_not_collected_paths():
    text = _workflow(
        'python -m pytest skills/parallax-foo/tests -q -m "not npx" '
        "-p no:cacheprovider -k skills/parallax-baz "
        "--rootdir skills/parallax-bar")

    assert _ci_pytest_paths(text) == [REPO_ROOT / "skills/parallax-foo/tests"]


@pytest.mark.parametrize("option", [
    "--ignore=skills/parallax-foo/tests/test_skipped.py",
    "--ignore skills/parallax-foo/tests/test_skipped.py",
    "--ignore-glob=*_slow.py",
    "--deselect skills/parallax-foo/tests/test_skipped.py",
    "--collect-only",
    "--co",
    "--pyargs",
])
def test_collection_narrowing_options_are_refused(option):
    """A positional credits every test file beneath it. An option that removes
    files from that set, or reinterprets the positional as a module name, makes
    the credit wrong -- the gate would report a file as covered that CI never
    runs. Refuse the invocation rather than over-credit it."""
    text = _workflow(f"python -m pytest skills/parallax-foo/tests -q {option}")

    with pytest.raises(pytest.fail.Exception, match="does not model"):
        _ci_pytest_paths(text)


def test_within_file_selection_is_still_accepted():
    """-m and -k deselect tests inside a file without removing the file from
    collection, so file-level coverage still holds and the real workflow's
    `-m \"not npx\"` step must keep working."""
    text = _workflow('python -m pytest skills/parallax-foo/tests -q -m "not npx"')

    assert _ci_pytest_paths(text) == [REPO_ROOT / "skills/parallax-foo/tests"]


def test_an_apostrophe_in_a_comment_does_not_break_the_parse():
    """Unbalanced quotes in prose used to abort the whole gate with an opaque
    shlex error rather than reporting anything."""
    text = _workflow(
        "# this root doesn't ship a conftest\n"
        "python -m pytest skills/parallax-foo/tests -q")

    assert _ci_pytest_paths(text) == [REPO_ROOT / "skills/parallax-foo/tests"]


def test_only_real_pytest_invocations_contribute():
    text = _workflow(
        "python skills/_parallax/scripts/scan_tracked_terms.py",
        "bash skills/_parallax/scripts/coverage-lint.sh || true",
        "pytest skills/parallax-foo/tests -q",
        "cd skills && python -m pytest evals/graders/ -q")

    assert _ci_pytest_paths(text) == [
        REPO_ROOT / "skills/parallax-foo/tests",
        REPO_ROOT / "evals/graders",
    ]


def test_unparseable_pytest_line_fails_loudly():
    """An unbalanced quote on a real command must not silently yield zero
    paths, which would read as `this step collects nothing`."""
    text = _workflow('python -m pytest skills/parallax-foo/tests -q -m "not npx')

    with pytest.raises(pytest.fail.Exception, match="cannot parse"):
        _ci_pytest_paths(text)


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
