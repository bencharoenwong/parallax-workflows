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


def test_tilde_hooks_path_is_expanded_not_taken_literally(clone: Path) -> None:
    """`git config --get` does not expand `~`; the first version created a
    literal `~` directory inside the work tree and left the real hook alone."""
    _run(["git", "config", "core.hooksPath", "~/nonexistent-parallax-hooks"], clone)
    _install(clone, env={"PARALLAX_HOOKS_FORCE": "1"})
    assert not (clone / "~").exists(), "created a literal ~ directory"


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
    (clone / "skills/_parallax/scripts/scan_commit_messages.py").write_text(
        "import sys\nsys.exit(0)\n")
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
