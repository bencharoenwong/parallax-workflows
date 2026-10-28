"""Static and behavioral checks for .github/workflows/client-guard.yml.

The old workflow ran on `pull_request` (not `pull_request_target`), so GitHub
ran the workflow FILE from the commit under test: a same-repo PR could edit a
step to print CLIENT_GUARD_KEY. This checks the redesigned trust model --
workflow always from main, PR code read as git objects and never checked out
or executed, secret gated behind a main-only environment -- by loading the
YAML (never by eyeballing it). Each trust-model check was confirmed to fail
against the pre-redesign workflow when it was written.

A second defect (confirmed independently 3x) survived that redesign: any
GitHub user could open a fork PR, and the keyed scan -- run on every fork PR
to preserve the trust model above -- printed the path of each matching file
to the public Actions log, turning the scan into a per-file membership oracle
against the private client registry; the issues/issue_comment triggers leaked
the same one bit per post. An earlier fix let a maintainer re-open the scan
for one revision with a label. That still let ANY outsider-authored bytes
reach the keyed scan (just with paths suppressed), and a pass/fail result is
itself at least one bit of oracle signal, so it was replaced outright: the
keyed scan ran ONLY when the run's author already had push access
(`head.repo.full_name == github.repository`, or an OWNER/MEMBER/COLLABORATOR
posting an issue/comment). There was no label, re-run, or other override that
admitted outsider-authored content to the scan.

A third defect (verified 2 of 3 independent reviewers, citing GitHub Docs)
survived that fix: Dependabot opens its PRs from a branch INSIDE this
repository, so `head.repo.full_name == github.repository` was already true
for them, and the `pull_request_target` run it triggers DOES receive
secrets -- GitHub withholds them only when Dependabot created the BASE ref,
never when Dependabot merely opened the PR. Dependabot's own PR bodies carry
upstream release notes written by third parties, and the scan reads the PR
title and body under the key, so the same-repo check alone let bot-authored,
third-party-controlled text reach the keyed scan. The trust step now
requires two more conditions beyond the same-repo check:
`github.event.pull_request.user.type != 'Bot'` and
`github.event.pull_request.author_association` in OWNER/MEMBER/COLLABORATOR.
Per GitHub Docs ("Creating a pull request"), opening a same-repo PR on a
personal-account repository already needs write access, which is why the
same-repo check alone used to double as an author check -- it does not for a
bot account that holds its own push-equivalent access without a reviewed
human behind that specific PR.

An untrusted run gets one fixed, content-independent `::error::` and a red
required check by design; a maintainer reviews and scans locally (see
CONTRIBUTING.md) and merges with an admin bypass. This file checks that
invariant directly: the trust step's decision depends only on which
repository the head branch lives in, whether the PR's author is a bot, and
whether that author already has write access -- never on PR content, author
reputation beyond that fixed set of signals, or a label.

Synthetic throughout -- no real client, partner or fund name, no local
machine path or username.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "client-guard.yml"

_TRUSTED_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")

_FIXED_UNTRUSTED_ERROR = (
    "::error::Pull request from an outside contributor or a bot: the "
    "client-name scan does not run in CI. A maintainer scans it locally "
    "and merges; see CONTRIBUTING.md."
)


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML 1.1 resolves the unquoted scalar key `on` to the boolean True.
    if "on" not in data and True in data:
        data["on"] = data.pop(True)
    return data


def _run_steps(data: dict) -> list[dict]:
    return data["jobs"]["client-guard"]["steps"]


def _run_texts(data: dict) -> list[str]:
    return [s["run"] for s in _run_steps(data) if "run" in s]


def _checkout_step(data: dict) -> dict:
    for step in _run_steps(data):
        if step.get("uses", "").startswith("actions/checkout@"):
            return step
    raise AssertionError("no actions/checkout step found")


def _step_by_id(data: dict, step_id: str) -> dict:
    for step in _run_steps(data):
        if step.get("id") == step_id:
            return step
    raise AssertionError(f"no step with id {step_id!r} found")


def _step_by_name(data: dict, name: str) -> dict:
    for step in _run_steps(data):
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step named {name!r} found")


def _run_trust_step(data: dict, tmp_path: Path, env: dict[str, str]) -> tuple[int, dict[str, str], str]:
    """Extract the "Decide trust for this run" step's `run:` script and
    execute it directly under bash, the way the trust-step tests below do.
    Returns (returncode, parsed-GITHUB_OUTPUT, stdout+stderr)."""
    step = _step_by_id(data, "trust")
    script = tmp_path / "trust.sh"
    script.write_text(step["run"], encoding="utf-8")
    output_file = tmp_path / "github_output"
    output_file.write_text("", encoding="utf-8")
    full_env = dict(os.environ)
    full_env["GITHUB_OUTPUT"] = str(output_file)
    # Defaults describe a trusted-shaped baseline (same repo, human, already
    # a collaborator) so each test below only has to override the one axis
    # it is checking. HEAD_REPO/BASE_REPO default to empty (a missing GitHub
    # expression context field renders as an empty string, never unset); a
    # caller always passes both explicitly, so an empty default never masks
    # a missing value.
    defaults = {
        "HEAD_REPO": "",
        "BASE_REPO": "",
        "PR_USER_TYPE": "User",
        "PR_AUTHOR_ASSOCIATION": "OWNER",
    }
    for key, default in defaults.items():
        full_env[key] = env.get(key, default)
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=full_env)
    parsed: dict[str, str] = {}
    for line in output_file.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            parsed[k] = v
    # The `::error::`/`::notice::` workflow commands are plain `echo`s, i.e.
    # stdout, not stderr; return both so a caller can match either.
    return result.returncode, parsed, result.stdout + result.stderr


@pytest.fixture(scope="module")
def wf() -> dict:
    return _load(WORKFLOW_PATH)


# --- trigger set -------------------------------------------------------------

def test_removed_triggers_absent(wf):
    on_block = wf["on"]
    for removed in ("pull_request", "pull_request_review", "pull_request_review_comment", "release"):
        assert removed not in on_block, f"{removed} must be removed (it let PR/review/release content run the workflow file)"


def test_pull_request_target_only_for_main(wf):
    # The environment's branch policy admits only main; a PR into any other
    # branch would otherwise show as a failed deployment.
    assert wf["on"]["pull_request_target"]["branches"] == ["main"]


def test_pull_request_target_types_no_labeled(wf):
    # `labeled` belonged to the removed maintainer-label override. There is
    # no in-CI override of the author-based trust gate any more, so there is
    # nothing for a `labeled` event to do here.
    types = wf["on"]["pull_request_target"]["types"]
    assert set(types) == {"opened", "edited", "synchronize", "reopened"}
    assert len(types) == 4
    assert "labeled" not in types


def test_push_restricted_to_main_no_tags(wf):
    push = wf["on"]["push"]
    assert push["branches"] == ["main"]
    assert "tags" not in push


def test_issues_and_issue_comment_present(wf):
    assert wf["on"]["issues"]["types"] == ["opened", "edited"]
    assert wf["on"]["issue_comment"]["types"] == ["created", "edited"]


# --- environment / permissions ------------------------------------------------

def test_job_uses_client_guard_environment(wf):
    assert wf["jobs"]["client-guard"]["environment"] == "client-guard"


def test_permissions_contents_read_only(wf):
    assert wf["permissions"] == {"contents": "read"}
    job_perms = wf["jobs"]["client-guard"].get("permissions")
    if job_perms is not None:
        assert job_perms == {"contents": "read"}


# --- checkout never fetches PR code ------------------------------------------

def test_checkout_default_no_pr_ref(wf):
    step = _checkout_step(wf)
    with_block = step.get("with", {})
    assert with_block.get("persist-credentials") is False
    assert "ref" not in with_block
    assert "repository" not in with_block


def test_concurrency_cancels_pr_runs_only(wf):
    assert wf["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request_target' }}"


# --- shell syntax --------------------------------------------------------------

def test_run_scripts_are_valid_bash(wf, tmp_path):
    for i, text in enumerate(_run_texts(wf)):
        script = tmp_path / f"step_{i}.sh"
        script.write_text(text, encoding="utf-8")
        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert result.returncode == 0, f"step {i} run: block fails bash -n: {result.stderr}"


# --- label-flow removal --------------------------------------------------------
# The owner-approved redesign replaces the maintainer-label override outright:
# no `labeled` trigger type (checked above) and no CLIENT_GUARD_LOCATIONS
# variable that used to suppress per-file paths on a labeled run.

def test_scan_step_env_has_no_locations_variable(wf):
    scan = _step_by_name(wf, "Scan for registered client names")
    env = scan.get("env", {})
    assert "CLIENT_GUARD_LOCATIONS" not in env
    assert set(env) == {"CLIENT_GUARD_KEY"}


# --- outside-PR trust gate: author-of-the-run only, never content -------------

def test_trust_step_exists_and_only_runs_for_pull_request_target(wf):
    step = _step_by_id(wf, "trust")
    assert step["if"] == "github.event_name == 'pull_request_target'"


def test_trust_step_env_has_three_trust_fields(wf):
    # The three trust conditions are: same repo (HEAD_REPO vs BASE_REPO),
    # author is not a bot (PR_USER_TYPE), and author already has write
    # access (PR_AUTHOR_ASSOCIATION). The behavior tests below vary each one
    # under bash and check the decision changes.
    step = _step_by_id(wf, "trust")
    env = step.get("env", {})
    assert set(env) == {"HEAD_REPO", "BASE_REPO", "PR_USER_TYPE", "PR_AUTHOR_ASSOCIATION"}


def test_fetch_and_scan_steps_gated_on_trust_output(wf):
    fetch = _step_by_name(wf, "Fetch PR head as a git object")
    assert fetch["if"] == ("github.event_name == 'pull_request_target' && "
                           "steps.trust.outputs.run_scan == 'true'")
    gated = ("github.event_name != 'pull_request_target' || "
             "steps.trust.outputs.run_scan == 'true'")
    assert _step_by_name(wf, "Load the trusted guard copy")["if"] == gated
    assert _step_by_name(wf, "Scan for registered client names")["if"] == gated


def test_issues_and_issue_comment_job_gate_references_both_fields(wf):
    job_if = wf["jobs"]["client-guard"]["if"]
    assert "github.event.issue.author_association" in job_if
    assert "github.event.comment.author_association" in job_if
    # Bots relay third-party text; the issue gate must exclude them as the
    # PR trust step does.
    assert "github.event.issue.user.type != 'Bot'" in job_if
    assert "github.event.comment.user.type != 'Bot'" in job_if
    for assoc in _TRUSTED_ASSOCIATIONS:
        assert assoc in job_if
    assert "issues" in job_if
    assert "issue_comment" in job_if


# --- trust-step behavior, run under bash for each documented case -------------

def test_trust_same_repo_owner_user_is_trusted(wf, tmp_path):
    rc, out, _ = _run_trust_step(wf, tmp_path, {
        "HEAD_REPO": "acme/repo", "BASE_REPO": "acme/repo",
        "PR_USER_TYPE": "User", "PR_AUTHOR_ASSOCIATION": "OWNER",
    })
    assert rc == 0
    assert out["run_scan"] == "true"


def test_trust_same_repo_collaborator_is_trusted(wf, tmp_path):
    rc, out, _ = _run_trust_step(wf, tmp_path, {
        "HEAD_REPO": "acme/repo", "BASE_REPO": "acme/repo",
        "PR_USER_TYPE": "User", "PR_AUTHOR_ASSOCIATION": "COLLABORATOR",
    })
    assert rc == 0
    assert out["run_scan"] == "true"


def test_trust_same_repo_bot_user_is_untrusted(wf, tmp_path):
    # Dependabot (and any other bot-opened PR) opens its PR from a branch
    # inside THIS repository, so the same-repo check alone would pass, and
    # Dependabot-triggered pull_request_target runs DO receive secrets
    # (GitHub withholds them only when Dependabot created the BASE ref, not
    # when it opened the PR). The bot's own PR text (e.g. upstream release
    # notes in the PR body) is still third-party-authored, so
    # `user.type == "Bot"` must fail trust on its own, even with an
    # OWNER-level author_association on the bot account.
    rc, out, err = _run_trust_step(wf, tmp_path, {
        "HEAD_REPO": "acme/repo", "BASE_REPO": "acme/repo",
        "PR_USER_TYPE": "Bot", "PR_AUTHOR_ASSOCIATION": "OWNER",
    })
    assert rc == 1
    assert out.get("run_scan") == "false"
    assert _FIXED_UNTRUSTED_ERROR in err


def test_trust_same_repo_non_collaborator_author_is_untrusted(wf, tmp_path):
    # A same-repo, human (non-bot) PR is still untrusted when its
    # author_association shows no write access -- NONE (no association at
    # all) and CONTRIBUTOR (has contributed before, but still no write
    # access) are both below the OWNER/MEMBER/COLLABORATOR bar.
    for assoc in ("NONE", "CONTRIBUTOR"):
        rc, out, err = _run_trust_step(wf, tmp_path, {
            "HEAD_REPO": "acme/repo", "BASE_REPO": "acme/repo",
            "PR_USER_TYPE": "User", "PR_AUTHOR_ASSOCIATION": assoc,
        })
        assert rc == 1, f"author_association={assoc!r} must be untrusted"
        assert out.get("run_scan") == "false"
        assert _FIXED_UNTRUSTED_ERROR in err


def test_trust_owner_fork_pr_is_untrusted(wf, tmp_path):
    # A PR whose head branch lives in someone else's fork is untrusted even
    # when the author is a human OWNER -- the same-repo check is not
    # satisfiable by author reputation, because the bytes under test did
    # not require write access to THIS repo to produce.
    rc, out, err = _run_trust_step(wf, tmp_path, {
        "HEAD_REPO": "maintainer-personal-fork/repo", "BASE_REPO": "acme/repo",
        "PR_USER_TYPE": "User", "PR_AUTHOR_ASSOCIATION": "OWNER",
    })
    assert rc == 1
    assert out.get("run_scan") == "false"
    assert _FIXED_UNTRUSTED_ERROR in err


def test_trust_outside_fork_pr_is_untrusted(wf, tmp_path):
    rc, out, err = _run_trust_step(wf, tmp_path, {
        "HEAD_REPO": "stranger/repo", "BASE_REPO": "acme/repo",
    })
    assert rc == 1
    assert out.get("run_scan") == "false"
    assert _FIXED_UNTRUSTED_ERROR in err


def test_trust_deleted_head_repo_is_untrusted(wf, tmp_path):
    # A deleted fork reports head.repo.full_name as an empty string. Empty
    # must not accidentally equal BASE_REPO or otherwise fall through to
    # trusted.
    rc, out, err = _run_trust_step(wf, tmp_path, {
        "HEAD_REPO": "", "BASE_REPO": "acme/repo",
    })
    assert rc == 1
    assert out.get("run_scan") == "false"
    assert _FIXED_UNTRUSTED_ERROR in err


def test_untrusted_error_text_identical_across_all_untrusted_cases(wf, tmp_path):
    # The message must not vary with PR content, author, or reason for
    # distrust -- a varying message would itself leak a bit of signal about
    # which untrusted case applied. Covers all three failing axes: wrong
    # repo, bot author, and insufficient author_association.
    cases = [
        {"HEAD_REPO": "maintainer-personal-fork/repo", "BASE_REPO": "acme/repo",
         "PR_USER_TYPE": "User", "PR_AUTHOR_ASSOCIATION": "OWNER"},
        {"HEAD_REPO": "stranger/repo", "BASE_REPO": "acme/repo"},
        {"HEAD_REPO": "", "BASE_REPO": "acme/repo"},
        {"HEAD_REPO": "acme/repo", "BASE_REPO": "acme/repo",
         "PR_USER_TYPE": "Bot", "PR_AUTHOR_ASSOCIATION": "OWNER"},
        {"HEAD_REPO": "acme/repo", "BASE_REPO": "acme/repo",
         "PR_USER_TYPE": "User", "PR_AUTHOR_ASSOCIATION": "NONE"},
        {"HEAD_REPO": "acme/repo", "BASE_REPO": "acme/repo",
         "PR_USER_TYPE": "User", "PR_AUTHOR_ASSOCIATION": "CONTRIBUTOR"},
    ]
    messages = []
    for env in cases:
        rc, out, err = _run_trust_step(wf, tmp_path, env)
        assert rc == 1
        assert out.get("run_scan") == "false"
        error_lines = [line for line in err.splitlines() if line.startswith("::error::")]
        assert len(error_lines) == 1
        messages.append(error_lines[0])
    assert len(set(messages)) == 1, f"untrusted ::error:: text varied across cases: {set(messages)!r}"
    assert messages[0] == _FIXED_UNTRUSTED_ERROR
    # Fixed means fixed: no case-specific detail (repo names, user type,
    # author association) may leak into it.
    for env in cases:
        for value in (env.get("HEAD_REPO"), env.get("BASE_REPO"),
                      env.get("PR_USER_TYPE"), env.get("PR_AUTHOR_ASSOCIATION")):
            if value:
                assert value not in messages[0]


# --- the trusted-guard load step ---------------------------------------------

_GUARD_REL = "skills/_parallax/scripts/client_guard.py"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def _repo_with_commit(tmp_path: Path, with_guard: bool, marker: str) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("x\n")
    if with_guard:
        (repo / _GUARD_REL).parent.mkdir(parents=True)
        (repo / _GUARD_REL).write_text(f"# {marker}\n")
        (repo / ".client-guard").mkdir()
        (repo / ".client-guard/registry.json").write_text("{}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def _run_load_step(data: dict, repo: Path, tmp_path: Path, env: dict[str, str]):
    """Run the "Load the trusted guard copy" step's script in `repo`.
    Returns (returncode, output, copied guard text or None, GITHUB_ENV text)."""
    step = _step_by_name(data, "Load the trusted guard copy")
    script = tmp_path / "load.sh"
    script.write_text(step["run"], encoding="utf-8")
    runner_temp = tmp_path / "runner_temp"
    runner_temp.mkdir()
    github_env = tmp_path / "github_env"
    github_env.write_text("")
    full_env = dict(os.environ)
    full_env.update({"RUNNER_TEMP": str(runner_temp), "GITHUB_ENV": str(github_env),
                     "EVENT_NAME": "", "PR_BASE": "", "PUSH_BEFORE": ""})
    full_env.update(env)
    r = subprocess.run(["bash", str(script)], cwd=repo, capture_output=True, text=True,
                       env=full_env)
    copied = runner_temp / "client_guard.py"
    return (r.returncode, r.stdout + r.stderr,
            copied.read_text() if copied.exists() else None, github_env.read_text())


def test_load_step_pr_never_falls_back_to_the_copy_under_test(wf, tmp_path):
    """A PR whose base has no guard must fail, not run a guard from the
    workspace: that copy is not the trusted revision, and running it would
    also skip CLIENT_GUARD_TRUSTED_REV and the registry-shrink check."""
    repo, base = _repo_with_commit(tmp_path, with_guard=False, marker="")
    (repo / _GUARD_REL).parent.mkdir(parents=True)
    (repo / _GUARD_REL).write_text("# workspace copy\n")
    rc, out, copied, env_text = _run_load_step(
        wf, repo, tmp_path, {"EVENT_NAME": "pull_request_target", "PR_BASE": base})
    assert rc == 2, out
    assert copied is None
    assert "CLIENT_GUARD_TRUSTED_REV" not in env_text


def test_load_step_issue_event_never_falls_back(wf, tmp_path):
    repo, _ = _repo_with_commit(tmp_path, with_guard=False, marker="")
    (repo / _GUARD_REL).parent.mkdir(parents=True)
    (repo / _GUARD_REL).write_text("# workspace copy\n")
    rc, out, copied, _ = _run_load_step(wf, repo, tmp_path, {"EVENT_NAME": "issues"})
    assert rc == 2, out
    assert copied is None


def test_load_step_pr_uses_the_trusted_revision_copy(wf, tmp_path):
    repo, base = _repo_with_commit(tmp_path, with_guard=True, marker="trusted copy")
    (repo / _GUARD_REL).write_text("# workspace copy\n")
    rc, out, copied, env_text = _run_load_step(
        wf, repo, tmp_path, {"EVENT_NAME": "pull_request_target", "PR_BASE": base})
    assert rc == 0, out
    assert copied == "# trusted copy\n"
    assert f"CLIENT_GUARD_TRUSTED_REV={base}" in env_text


def test_load_step_first_install_push_uses_the_checkout(wf, tmp_path):
    repo, base = _repo_with_commit(tmp_path, with_guard=False, marker="")
    (repo / _GUARD_REL).parent.mkdir(parents=True)
    (repo / _GUARD_REL).write_text("# first install\n")
    rc, out, copied, env_text = _run_load_step(
        wf, repo, tmp_path, {"EVENT_NAME": "push", "PUSH_BEFORE": base})
    assert rc == 0, out
    assert copied == "# first install\n"
    assert "CLIENT_GUARD_TRUSTED_REV" not in env_text


# --- the PR-head fetch step ----------------------------------------------------

def _workspace_with_pr_ref(tmp_path: Path, pr_number: str) -> tuple[Path, str]:
    origin, base = _repo_with_commit(tmp_path, with_guard=False, marker="")
    _git(origin, "checkout", "-q", "-b", "pr")
    (origin / "pr-only.txt").write_text("pr content\n")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "pr")
    head = _git(origin, "rev-parse", "HEAD")
    _git(origin, "update-ref", f"refs/pull/{pr_number}/head", head)
    _git(origin, "checkout", "-q", base)
    _git(origin, "branch", "-q", "-D", "pr")
    workspace = tmp_path / "workspace"
    subprocess.run(["git", "clone", "-q", str(origin), str(workspace)], check=True,
                   capture_output=True)
    return workspace, head


def _run_fetch_step(data: dict, workspace: Path, tmp_path: Path, env: dict[str, str]):
    step = _step_by_name(data, "Fetch PR head as a git object")
    script = tmp_path / "fetch.sh"
    script.write_text(step["run"], encoding="utf-8")
    github_env = tmp_path / "github_env"
    github_env.write_text("")
    full_env = {**os.environ, "GITHUB_ENV": str(github_env), **env}
    r = subprocess.run(["bash", str(script)], cwd=workspace, capture_output=True, text=True,
                       env=full_env)
    return r.returncode, r.stdout + r.stderr, github_env.read_text()


def test_fetch_step_exports_pr_head_without_checking_it_out(wf, tmp_path):
    workspace, head = _workspace_with_pr_ref(tmp_path, "7")
    before = _git(workspace, "rev-parse", "HEAD")
    rc, out, env_text = _run_fetch_step(wf, workspace, tmp_path,
                                        {"PR_NUMBER": "7", "PR_HEAD": head})
    assert rc == 0, out
    assert env_text.splitlines() == [f"CLIENT_GUARD_CHANGE_REV={head}"]
    assert _git(workspace, "cat-file", "-t", head) == "commit"
    assert _git(workspace, "rev-parse", "HEAD") == before
    assert not (workspace / "pr-only.txt").exists()


def test_fetch_step_fails_when_announced_head_is_missing(wf, tmp_path):
    workspace, _ = _workspace_with_pr_ref(tmp_path, "7")
    rc, out, env_text = _run_fetch_step(wf, workspace, tmp_path,
                                        {"PR_NUMBER": "7", "PR_HEAD": "1" * 40})
    assert rc == 2, out
    assert env_text == ""


# --- the scan step -------------------------------------------------------------

def test_scan_step_runs_only_the_loaded_guard_copy_isolated(wf, tmp_path):
    record = tmp_path / "record.json"
    workspace_marker = tmp_path / "workspace-guard-ran"
    workspace = tmp_path / "workspace"
    (workspace / _GUARD_REL).parent.mkdir(parents=True)
    (workspace / _GUARD_REL).write_text(
        f"open({str(workspace_marker)!r}, 'w').write('ran')\n")
    runner_temp = tmp_path / "runner_temp"
    runner_temp.mkdir()
    (runner_temp / "client_guard.py").write_text(
        "import json, os, sys\n"
        "json.dump(dict(argv=sys.argv[1:], isolated=sys.flags.isolated,\n"
        "               root=os.environ.get('CLIENT_GUARD_REPO_ROOT'),\n"
        "               key=os.environ.get('CLIENT_GUARD_KEY')),\n"
        f"          open({str(record)!r}, 'w'))\n")
    step = _step_by_name(wf, "Scan for registered client names")
    script = tmp_path / "scan.sh"
    script.write_text(step["run"], encoding="utf-8")
    env = {**os.environ, "RUNNER_TEMP": str(runner_temp), "GITHUB_WORKSPACE": str(workspace),
           "CLIENT_GUARD_KEY": "synthetic-key"}
    r = subprocess.run(["bash", str(script)], cwd=workspace, capture_output=True, text=True,
                       env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(record.read_text()) == {
        "argv": ["ci"], "isolated": 1, "root": str(workspace), "key": "synthetic-key"}
    assert not workspace_marker.exists()
