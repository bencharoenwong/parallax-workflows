"""Tests for install_git_hooks.sh.

WHY THIS EXISTS. The first version of the installer shipped with zero tests and
five distinct hook shapes that made it print "installed" while a real `git push`
went through unscanned. Every one of them passed `bash -n`. Syntax checking is
not reachability checking, and "the guard is present in the file" is not "the
guard runs".

Each test below is one of those shapes. The property asserted is always the
same: after a reported-successful install, the layer must actually execute and
block. `_hook_blocks()` runs the installed hook rather than reading it.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
INSTALLER = REPO / "skills/_parallax/scripts/install_git_hooks.sh"
MARKER = "# --- parallax:commit-message-scan (BLOCKING)"


def _run(cmd, cwd, env=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


@pytest.fixture()
def clone(tmp_path: Path) -> Path:
    """A throwaway repo carrying a stub scanner that always fails.

    The stub is what makes the block observable: a real scanner would pass on a
    clean history, and a passing scanner cannot distinguish "the guard ran and
    allowed it" from "the guard never ran".
    """
    work = tmp_path / "work"
    (work / "skills/_parallax/scripts").mkdir(parents=True)
    _run(["git", "init", "-q"], work)
    _run(["git", "config", "user.email", "t@example.invalid"], work)
    _run(["git", "config", "user.name", "t"], work)
    # Pin hooksPath locally so a global core.hooksPath on the developer's
    # machine cannot leak in and trip the outside-the-repo refusal.
    _run(["git", "config", "core.hooksPath", ".git/hooks"], work)

    stub = work / "skills/_parallax/scripts/scan_commit_messages.py"
    stub.write_text("import sys\nprint('STUB SCANNER: fail')\nsys.exit(1)\n")
    shutil.copy(INSTALLER, work / "skills/_parallax/scripts/install_git_hooks.sh")
    (work / "f.txt").write_text("x")
    _run(["git", "add", "-A"], work)
    _run(["git", "commit", "-qm", "init"], work)
    return work


def _install(work: Path, env=None):
    return _run(["bash", "skills/_parallax/scripts/install_git_hooks.sh"], work, env)


def _write_hook(work: Path, body: str) -> Path:
    hooks = work / ".git/hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    h = hooks / "pre-push"
    h.write_text(body)
    h.chmod(h.stat().st_mode | stat.S_IEXEC)
    return h


def _hook_blocks(work: Path) -> bool:
    """Run the installed hook the way git does. True = it blocked."""
    hook = work / ".git/hooks/pre-push"
    if not hook.exists():
        return False
    r = subprocess.run(["bash", str(hook), "origin", "http://example.invalid"],
                       cwd=work, capture_output=True, text=True, input="")
    return r.returncode != 0


# --- the five shapes that defeated the first version ------------------------


def test_hook_with_exit_inside_a_conditional(clone: Path) -> None:
    """`exit` indented in an if-body matched the "last exit" search, so the
    layer was inserted into a branch that does not always run."""
    _write_hook(clone, '#!/usr/bin/env bash\nif [ "$FAIL" = 1 ]; then\n    exit 7\nfi\n')
    assert _install(clone).returncode == 0
    assert _hook_blocks(clone), "installed but never blocks"


def test_hook_ending_in_a_bare_exit(clone: Path) -> None:
    """The search required a trailing space, so `exit` alone did not match and
    the layer was appended after it."""
    _write_hook(clone, "#!/usr/bin/env bash\necho hi\nexit\n")
    assert _install(clone).returncode == 0
    assert _hook_blocks(clone), "installed but never blocks"


def test_hook_ending_in_exec(clone: Path) -> None:
    """`exec` replaces the process; nothing after it runs, and there is no
    `exit ` line to anchor on."""
    _write_hook(clone, "#!/usr/bin/env bash\nexec /usr/bin/true\n")
    assert _install(clone).returncode == 0
    assert _hook_blocks(clone), "installed but never blocks"


def test_hook_ending_in_exit_zero(clone: Path) -> None:
    """The shape that shipped broken in this repo."""
    _write_hook(clone, "#!/usr/bin/env bash\necho layered\nexit 0\n")
    assert _install(clone).returncode == 0
    assert _hook_blocks(clone), "installed but never blocks"


def test_existing_hook_exit_status_is_preserved(clone: Path) -> None:
    """Appending discarded the original hook's exit code, silently disabling a
    gate the user already had. Prepending keeps it: with the scanner passing,
    the original's failure must still block."""
    (clone / "skills/_parallax/scripts/scan_commit_messages.py").write_text(
        "import sys\nsys.exit(0)\n")
    _write_hook(clone, "#!/usr/bin/env bash\nexit 9\n")
    assert _install(clone).returncode == 0
    assert _hook_blocks(clone), "original hook's failure was masked"


# --- refusals: better to decline than to report a false success -------------


def test_symlinked_hook_is_refused(clone: Path) -> None:
    real = clone / "shared-pre-push"
    real.write_text("#!/usr/bin/env bash\nexit 0\n")
    hooks = clone / ".git/hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "pre-push").symlink_to(real)
    r = _install(clone)
    assert r.returncode != 0
    assert "symlink" in (r.stdout + r.stderr).lower()
    assert MARKER not in real.read_text(), "mutated the shared target"


def test_non_shell_hook_is_refused_not_corrupted(clone: Path) -> None:
    body = "#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n"
    h = _write_hook(clone, body)
    r = _install(clone)
    assert r.returncode != 0
    assert h.read_text() == body, "corrupted a non-shell hook"


def test_non_shell_hook_whose_body_stays_bash_parseable_is_still_refused(
        clone: Path) -> None:
    """The `test_non_shell_hook_is_refused_not_corrupted` case above passes even
    with the shebang check deleted: prepending the layer into a Python hook
    produces invalid bash, `bash -n` catches THAT, and the installer's own
    syntax-error recovery restores the backup — so the same pass/fail result
    comes from a different guard. This body stays syntactically valid bash
    after the layer is prepended (`print "...";` parses as an ordinary command
    invocation), so only the explicit shebang check can refuse it."""
    body = '#!/usr/bin/env perl\nprint "hello world\\n";\n'
    h = _write_hook(clone, body)
    r = _install(clone)
    assert r.returncode != 0
    assert h.read_text() == body, "corrupted a non-shell hook"


def test_hooks_dir_outside_the_repo_requires_explicit_force(clone: Path,
                                                            tmp_path: Path) -> None:
    """A shared hooksPath makes this a global edit wearing a per-repo costume."""
    shared = tmp_path / "shared-hooks"
    shared.mkdir()
    _run(["git", "config", "core.hooksPath", str(shared)], clone)
    assert _install(clone).returncode != 0
    assert not (shared / "pre-push").exists()
    assert _install(clone, env={"PARALLAX_HOOKS_FORCE": "1"}).returncode == 0
    assert MARKER in (shared / "pre-push").read_text()


def test_tilde_hooks_path_is_expanded_not_taken_literally(clone: Path,
                                                          tmp_path: Path) -> None:
    """`git config --get` does not expand `~`; the first version created a
    literal `~` directory inside the work tree and left the real hook alone.

    HOME is redirected at a temp dir. An earlier version of this test let git
    expand `~` against the DEVELOPER'S REAL HOME and created a directory there
    — a test with a side effect outside its own tmp_path. It also asserted only
    that no literal `~` appeared, never that the hook landed at the expanded
    path, so it would have passed even if nothing was written anywhere."""
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    _run(["git", "config", "core.hooksPath", "~/parallax-hooks-under-test"], clone)
    r = _install(clone, env={"HOME": str(fake_home), "PARALLAX_HOOKS_FORCE": "1"})
    assert r.returncode == 0, r.stderr
    assert not (clone / "~").exists(), "created a literal ~ directory"
    landed = fake_home / "parallax-hooks-under-test/pre-push"
    assert landed.exists(), "hook did not land at the expanded path"
    assert MARKER in landed.read_text()


# --- idempotency and self-repair -------------------------------------------


def test_install_is_idempotent(clone: Path) -> None:
    _write_hook(clone, "#!/usr/bin/env bash\nexit 0\n")
    assert _install(clone).returncode == 0
    second = _install(clone)
    assert second.returncode == 0
    assert "already installed" in second.stdout
    body = (clone / ".git/hooks/pre-push").read_text()
    assert body.count(MARKER) == 1


def test_a_mention_in_a_comment_does_not_count_as_installed(clone: Path) -> None:
    """A bare grep for the marker let a TODO note report "already installed",
    which also blocked the installer from ever repairing a broken install."""
    _write_hook(clone, "#!/usr/bin/env bash\n# TODO: parallax:commit-message-scan here\nexit 0\n")
    r = _install(clone)
    assert r.returncode == 0
    assert "already installed" not in r.stdout
    assert _hook_blocks(clone)


def test_creates_a_working_hook_when_none_exists(clone: Path) -> None:
    assert not (clone / ".git/hooks/pre-push").exists()
    assert _install(clone).returncode == 0
    assert _hook_blocks(clone)


def test_a_clean_scanner_does_not_block(clone: Path) -> None:
    """The negative case. A guard that blocks everything is as useless as one
    that blocks nothing — and only this direction proves the layer is not
    simply failing closed on every push."""
    (clone / "skills/_parallax/scripts/scan_commit_messages.py").write_text(
        "import sys\nsys.exit(0)\n")
    _write_hook(clone, "#!/usr/bin/env bash\nexit 0\n")
    assert _install(clone).returncode == 0
    assert not _hook_blocks(clone), "blocked a clean scan"


def test_the_layer_scans_the_pushed_ref_not_the_checked_out_branch(clone: Path) -> None:
    """The layer originally ran the scanner with no arguments, so it scanned
    `origin/main..HEAD`. Pushing a branch you are not on therefore scanned the
    wrong range: `git push origin feature` from `main` scanned nothing, reported
    clean, and published unscanned commits. The hook now passes the range git
    reports on stdin.

    Driven with a stub scanner that fails only when given an explicit range, so
    a hook that ignores stdin passes and a hook that honours it blocks.
    """
    (clone / "skills/_parallax/scripts/scan_commit_messages.py").write_text(
        "import sys\n"
        "sys.exit(1 if len(sys.argv) > 1 else 0)\n"
    )
    _write_hook(clone, "#!/usr/bin/env bash\nexit 0\n")
    assert _install(clone).returncode == 0

    hook = clone / ".git/hooks/pre-push"
    ref_line = "refs/heads/feature aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa " \
               "refs/heads/feature bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
    r = subprocess.run(["bash", str(hook), "origin", "http://example.invalid"],
                       cwd=clone, capture_output=True, text=True, input=ref_line)
    assert r.returncode != 0, "hook ignored the pushed ref and scanned the default range"


def test_a_deletion_push_does_not_scan_a_bogus_range(clone: Path) -> None:
    """An all-zero local sha is a branch deletion. There are no commits to
    scan, and treating the zero sha as a rev would error."""
    # The stub FAILS if handed any range mentioning the zero sha. A stub that
    # always exits 0 cannot tell "skipped the deletion" from "scanned a bogus
    # range" — the earlier version of this test could not fail, and deleting the
    # zero-sha guard left the whole suite green.
    (clone / "skills/_parallax/scripts/scan_commit_messages.py").write_text(
        "import sys\n"
        "bad = any('0000000000' in a for a in sys.argv[1:])\n"
        "sys.exit(1 if bad else 0)\n")
    _write_hook(clone, "#!/usr/bin/env bash\nexit 0\n")
    assert _install(clone).returncode == 0
    hook = clone / ".git/hooks/pre-push"
    ref_line = ("(delete) 0000000000000000000000000000000000000000 "
                "refs/heads/gone bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n")
    r = subprocess.run(["bash", str(hook), "origin", "http://example.invalid"],
                       cwd=clone, capture_output=True, text=True, input=ref_line)
    assert r.returncode == 0, r.stderr


def test_stdin_is_passed_through_to_the_rest_of_the_hook(clone: Path) -> None:
    """The layer is PREPENDED and reads git's ref list from stdin. A bare
    `while read` drains it, so every gate after the layer — security gate,
    perimeter gate, git-lfs — would receive an EMPTY ref list and silently do
    nothing. Verified as a real regression before the fix: downstream saw 0 of
    2 ref lines.

    This is what a toy hook cannot show. The assertion is on what the REST of
    the hook receives, not on what the layer does.
    """
    (clone / "skills/_parallax/scripts/scan_commit_messages.py").write_text(
        "import sys\nsys.exit(0)\n")
    out = clone / "downstream.txt"
    _write_hook(clone, (
        "#!/usr/bin/env bash\n"
        'T=$(mktemp); cat > "$T"\n'
        f'wc -l < "$T" | tr -d " " > {out}\n'
        "exit 0\n"
    ))
    assert _install(clone).returncode == 0

    hook = clone / ".git/hooks/pre-push"
    refs = ("refs/heads/f aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa "
            "refs/heads/f bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
            "refs/heads/g cccccccccccccccccccccccccccccccccccccccc "
            "refs/heads/g dddddddddddddddddddddddddddddddddddddddd\n")
    r = subprocess.run(["bash", str(hook), "origin", "http://example.invalid"],
                       cwd=clone, capture_output=True, text=True, input=refs)
    assert r.returncode == 0, r.stderr
    assert out.read_text().strip() == "2", (
        f"downstream saw {out.read_text().strip()} ref lines, expected 2 — "
        "the layer drained stdin")


def test_a_symlinked_hooks_directory_does_not_bypass_the_outside_repo_guard(
        clone: Path, tmp_path: Path) -> None:
    """The guard was a string-prefix test on an UNRESOLVED path, so
    `.git/hooks` symlinked elsewhere still matched "$ROOT/*" and the write
    landed through the link. Resolving both sides first closes it.

    Needs the symlink planted beforehand, so this is defence in depth rather
    than a live hole — but a prefix test on an unresolved path is not the check
    it appears to be."""
    outside = tmp_path / "elsewhere-hooks"
    outside.mkdir()
    real_hooks = clone / ".git/hooks"
    if real_hooks.exists():
        shutil.rmtree(real_hooks)
    real_hooks.symlink_to(outside)

    r = _install(clone)
    assert r.returncode != 0, "wrote through a symlinked hooks directory"
    assert not (outside / "pre-push").exists()

    assert _install(clone, env={"PARALLAX_HOOKS_FORCE": "1"}).returncode == 0
    assert (outside / "pre-push").exists()


def test_a_deletion_only_push_scans_nothing_not_the_current_branch(clone: Path) -> None:
    """Every ref was a deletion, so no commits are being published and there is
    nothing to scan. Falling through to the scanner's default range scanned the
    CHECKED-OUT branch instead — unrelated to the ref being deleted, and the
    same wrong-range family this layer exists to fix. Harmless only while that
    branch happens to be clean; from a branch with a hit it blocked an unrelated
    deletion."""
    (clone / "skills/_parallax/scripts/scan_commit_messages.py").write_text(
        "import sys\n"
        "# fails only if invoked with NO explicit range, i.e. the default path\n"
        "sys.exit(1 if len(sys.argv) == 1 else 0)\n")
    _write_hook(clone, "#!/usr/bin/env bash\nexit 0\n")
    assert _install(clone).returncode == 0
    hook = clone / ".git/hooks/pre-push"
    ref_line = ("(delete) 0000000000000000000000000000000000000000 "
                "refs/heads/gone bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n")
    r = subprocess.run(["bash", str(hook), "origin", "http://example.invalid"],
                       cwd=clone, capture_output=True, text=True, input=ref_line)
    assert r.returncode == 0, "fell back to the default range on a deletion-only push"


def test_a_new_branch_scans_only_what_it_adds_over_the_default_branch(clone: Path) -> None:
    """A bare sha is NOT a range: `git log <sha>` walks every ancestor, so the
    first push of a new branch scanned the whole published history. On the real
    repo that produced 60 hits against already-published commits and blocked the
    push with nothing fixable locally."""
    scanned = clone / "range.txt"
    (clone / "skills/_parallax/scripts/scan_commit_messages.py").write_text(
        "import sys, pathlib\n"
        f"pathlib.Path({str(scanned)!r}).write_text(sys.argv[1] if len(sys.argv) > 1 else 'DEFAULT')\n"
        "sys.exit(0)\n")
    _run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], clone)
    _run(["git", "checkout", "-q", "-b", "feature"], clone)
    (clone / "new.txt").write_text("x")
    _run(["git", "add", "-A"], clone)
    _run(["git", "commit", "-qm", "feat: add a thing"], clone)
    head = _run(["git", "rev-parse", "HEAD"], clone).stdout.strip()

    _write_hook(clone, "#!/usr/bin/env bash\nexit 0\n")
    assert _install(clone).returncode == 0
    hook = clone / ".git/hooks/pre-push"
    ref_line = (f"refs/heads/feature {head} refs/heads/feature "
                "0000000000000000000000000000000000000000\n")
    subprocess.run(["bash", str(hook), "origin", "http://example.invalid"],
                   cwd=clone, capture_output=True, text=True, input=ref_line)
    rng = scanned.read_text()
    assert ".." in rng, f"scanned a bare rev, not a range: {rng}"
    assert rng.endswith(head), rng


# --- fail closed when the scan cannot RUN, not only when it finds a hit ------
#
# The tests above prove the layer blocks on a HIT. That is not the same property
# as blocking when the scan could not be performed at all. Two guards cover the
# second case, and both were mutation-tested green by the whole suite above:
#
#   - the mktemp check: without a temp file the ref list is lost, and the layer
#     silently degrades to the scanner's DEFAULT range — the wrong-range bug it
#     exists to fix. Deleting `exit 2` there still prints "BLOCKED" and returns
#     0, so never assert on that string alone; the exit code is the evidence.
#   - the `-ne 0` check: the scanner returns 2 on ScanError (an unresolvable
#     rev-range, a git failure). Narrowing it to `= 1` lets a scan that never
#     ran report a clean push.
#
# Anything added here must keep asserting on the RETURN CODE, and must keep a
# non-zero-but-not-1 scanner exit in the matrix.


_REF_LINE = ("refs/heads/feature aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa "
             "refs/heads/feature bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n")


def _run_hook(work: Path, refs: str, env=None):
    """Run the installed hook the way git does, with a ref list on stdin.

    Asserts the layer is actually in the hook first. A missing hook and a
    working hook can both return non-zero for unrelated reasons, so "the
    installer exited 0" is not enough to make a push-behaviour assertion mean
    anything.
    """
    hook = work / ".git/hooks/pre-push"
    assert hook.exists(), "no pre-push hook was installed"
    assert MARKER in hook.read_text(), "the layer is not in the installed hook"
    return subprocess.run(["bash", str(hook), "origin", "http://example.invalid"],
                          cwd=work, capture_output=True, text=True, input=refs,
                          env={**os.environ, **(env or {})})


def test_the_hook_blocks_when_the_ref_list_temp_file_cannot_be_created(
        clone: Path, tmp_path: Path) -> None:
    """`mktemp` failing loses git's ref list. Unguarded, the layer falls through
    to the scanner's default range and reports a clean push of commits it never
    read — so the failure has to block.

    Driven with a stub that PASSES on the default range and FAILS on an explicit
    one. That asymmetry is what makes the difference observable: a hook that
    keeps the ref list blocks, a hook that loses it passes.

    Deleting the guard still PRINTS "BLOCKED" and then exits 0, so the return
    code is the only admissible evidence here.
    """
    (clone / "skills/_parallax/scripts/scan_commit_messages.py").write_text(
        "import sys\nsys.exit(1 if len(sys.argv) > 1 else 0)\n")
    _write_hook(clone, "#!/usr/bin/env bash\nexit 0\n")
    assert _install(clone).returncode == 0

    missing = tmp_path / "no-such-tmpdir"
    assert not missing.exists()
    r = _run_hook(clone, _REF_LINE, env={"TMPDIR": str(missing)})
    assert r.returncode != 0, (
        "lost the ref list and let the push through on the default range")
    assert "cannot create a temp file" in r.stderr, (
        f"blocked for some other reason: {r.stderr}")


def test_a_usable_temp_dir_does_not_block_a_clean_scan(clone: Path,
                                                       tmp_path: Path) -> None:
    """The negative direction for the guard above. A layer that blocked on every
    push would satisfy the fail-closed test while being useless."""
    (clone / "skills/_parallax/scripts/scan_commit_messages.py").write_text(
        "import sys\nsys.exit(0)\n")
    _write_hook(clone, "#!/usr/bin/env bash\nexit 0\n")
    assert _install(clone).returncode == 0

    usable = tmp_path / "usable-tmpdir"
    usable.mkdir()
    r = _run_hook(clone, _REF_LINE, env={"TMPDIR": str(usable)})
    assert r.returncode == 0, r.stderr
    assert "cannot create a temp file" not in r.stderr
    assert not list(usable.iterdir()), "left the ref-list temp file behind"


@pytest.mark.parametrize("scanner_rc, should_block", [
    (0, False),   # clean scan: must NOT block
    (1, True),    # a hit
    (2, True),    # the scan could not RUN — scan_commit_messages.py returns 2
                  # on ScanError (unresolvable rev-range, git failure)
])
def test_the_hook_blocks_on_every_nonzero_scanner_exit_not_just_a_hit(
        clone: Path, scanner_rc: int, should_block: bool) -> None:
    """Exit 2 means "I could not determine the outgoing range", not "clean".
    Treating only exit 1 as a failure turns a scan that never ran into a
    permitted push, which is the failure mode the whole layer exists to prevent.

    The hook also propagates the scanner's own code, so a blocked push reports
    WHICH failure it was.
    """
    (clone / "skills/_parallax/scripts/scan_commit_messages.py").write_text(
        f"import sys\nsys.exit({scanner_rc})\n")
    _write_hook(clone, "#!/usr/bin/env bash\nexit 0\n")
    assert _install(clone).returncode == 0

    r = _run_hook(clone, _REF_LINE)
    if should_block:
        assert r.returncode == scanner_rc, (
            f"scanner exited {scanner_rc}; the hook returned {r.returncode} "
            "— a scan that failed was reported as a permitted push")
        assert "BLOCKED" in r.stderr
    else:
        assert r.returncode == 0, f"blocked a clean scan: {r.stderr}"
