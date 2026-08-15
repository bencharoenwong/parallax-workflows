"""Tests for the outgoing commit-message scan (gate 3).

Two conventions, for two different reasons:

* Redaction-vocabulary cases spell their messages out as LITERALS. They must be
  written independently of ``REDACTION_RULES``; a test that looped that table
  would pass for any table, including an empty one, and could never fail for the
  reason it claims. The stems are ordinary English, so writing them here costs
  nothing.
* Restricted-term cases are built from the loaded term list at RUNTIME and never
  written as literals -- same rule as ``test_scan_tracked_terms.py``. This file
  is tracked in a public repo, so a hand-written "realistic leak" fixture would
  be the leak it tests for.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_bundle as bb
import scan_commit_messages as scm
import scan_tracked_terms as st
from canary_fixture import hermetic_extra_terms  # noqa: F401 -- autouse fixture


# --------------------------------------------------------------------------
# tmp-repo helpers
# --------------------------------------------------------------------------

def _run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=True)


def _repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _run(root, "init", "-q")
    # Not `init -b main`: the runner's git may predate it, and the default
    # branch name is configurable per machine.
    _run(root, "symbolic-ref", "HEAD", "refs/heads/main")
    _run(root, "config", "user.email", "t@example.com")
    _run(root, "config", "user.name", "t")
    _run(root, "config", "commit.gpgsign", "false")
    return root


def _commit(root: Path, message: str) -> str:
    marker = root / "f.txt"
    marker.write_text((marker.read_text() if marker.exists() else "") + "x\n",
                      encoding="utf-8")
    _run(root, "add", "f.txt")
    _run(root, "commit", "-q", "-m", message)
    return _run(root, "rev-parse", "HEAD").stdout.strip()


def _branch_off_main(root: Path) -> None:
    """Leave main behind so `main..HEAD` is a non-empty outgoing range."""
    _run(root, "checkout", "-q", "-b", "feature")


# --------------------------------------------------------------------------
# Range resolution
# --------------------------------------------------------------------------

def test_prefers_origin_main_over_main(tmp_path):
    root = _repo(tmp_path / "r")
    _commit(root, "chore: base")
    _run(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert scm.resolve_range(root) == "origin/main..HEAD"


def test_falls_back_to_main(tmp_path):
    root = _repo(tmp_path / "r")
    _commit(root, "chore: base")
    assert scm.resolve_range(root) == "main..HEAD"


def test_fails_closed_when_no_base_ref_resolves(tmp_path):
    """A scan that cannot see the outgoing range must not report clean. The
    tried refs are named in the error; no commit content is."""
    root = _repo(tmp_path / "r")
    _commit(root, "chore: base")
    with pytest.raises(scm.ScanError, match="no base ref resolved"):
        scm.resolve_range(root, base_refs=("nope/absent",))


def test_range_excludes_commits_already_on_the_base(tmp_path):
    root = _repo(tmp_path / "r")
    _commit(root, "chore: this message mentions a leak but is already pushed")
    _run(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _branch_off_main(root)
    _commit(root, "chore: an ordinary outgoing change")
    assert scm.scan(root) == []


# --------------------------------------------------------------------------
# Redaction vocabulary — literal messages, written independently of the table
# --------------------------------------------------------------------------

@pytest.mark.parametrize("message,expected", [
    ("chore: redact the fixture", "redaction/redact"),
    ("chore: redacted an identifier", "redaction/redact"),
    ("chore: scrub the mocks", "redaction/scrub"),
    ("chore: sanitize the captures", "redaction/sanitize"),
    ("chore: sanitised the captures", "redaction/sanitize"),
    ("chore: de-identify the issuer", "redaction/de-identify"),
    ("chore: deidentified the issuer", "redaction/de-identify"),
    ("chore: anonymize the holdings", "redaction/anonymize"),
    ("chore: anonymise the holdings", "redaction/anonymize"),
    ("chore: obfuscate the figures", "redaction/obfuscate"),
    ("chore: fix a leak in the mocks", "redaction/leak"),
    ("chore: leaked values removed", "redaction/leak"),
    ("chore: rename the real issuer", "redaction/real-subject"),
    ("chore: swap out real tickers", "redaction/real-subject"),
    ("chore: drop the real company", "redaction/real-subject"),
    ("chore: replace real values", "redaction/real-subject"),
    ("chore: rebuild from a live capture", "redaction/live-source"),
    ("chore: refresh from live data", "redaction/live-source"),
    ("chore: pin the live response", "redaction/live-source"),
    ("chore: pin live values", "redaction/live-source"),
])
def test_redaction_vocabulary_is_matched(message, expected):
    assert expected in scm.rule_hits(message, terms=[])


@pytest.mark.parametrize("message", [
    "fix(credit-lens): express quality-trend bands on the 0-10 score scale",
    "feat(_parallax): extract MCP contract-test infrastructure",
    "chore(mocks): add a silent-fail fixture for the redundancy endpoint",
    "docs: describe the alive-and-well heuristic",   # 'live' inside a word
    "test: widen the breakage window",               # 'leak' is not 'break'
    "refactor: unreal expectations in the stub",     # 'real' inside a word
    "chore: reallocate weights across sectors",      # 'real' prefix, no subject
])
def test_ordinary_messages_are_clean(message):
    assert scm.rule_hits(message, terms=[]) == []


def test_vocabulary_matches_anywhere_in_a_multiline_body(tmp_path):
    root = _repo(tmp_path / "r")
    _commit(root, "chore: base")
    _run(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _branch_off_main(root)
    sha = _commit(
        root,
        "fix(mocks): correct the fixture shape\n\n"
        "The endpoint changed. While here, scrub the stale field.\n")
    assert scm.scan(root, terms=[]) == [(sha, "redaction/scrub")]


def test_only_the_offending_commit_is_reported(tmp_path):
    root = _repo(tmp_path / "r")
    _commit(root, "chore: base")
    _run(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _branch_off_main(root)
    _commit(root, "feat: add a new endpoint schema")
    guilty = _commit(root, "chore: redact the fixture")
    _commit(root, "docs: update the mocks README")
    assert scm.scan(root, terms=[]) == [(guilty, "redaction/redact")]


def test_one_message_can_match_several_rules(tmp_path):
    hits = scm.rule_hits("chore: scrub the leak from live data", terms=[])
    assert set(hits) == {"redaction/scrub", "redaction/leak",
                         "redaction/live-source"}


# --------------------------------------------------------------------------
# Restricted terms — built at runtime, never written as literals
# --------------------------------------------------------------------------

@pytest.mark.parametrize("which", ["branding", "restricted"])
def test_restricted_term_in_a_message_is_caught(tmp_path, which):
    scoped = st.scoped_terms()
    if which == "branding":
        term = next(t for t in scoped if t in bb._BRANDING_CANARIES)
    else:
        term = next(t for t in scoped if t not in bb._BRANDING_CANARIES)
    root = _repo(tmp_path / "r")
    _commit(root, "chore: base")
    _run(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _branch_off_main(root)
    sha = _commit(root, f"chore: touch {term} handling")
    assert scm.scan(root) == [(sha, f"canary/{which}")]


def test_public_contract_fields_are_not_flagged(tmp_path):
    """The allowlisted MCP response fields contain a scan term as a substring and
    are part of the published contract. Mentioning one in a commit message is
    ordinary."""
    allowed = bb.CANARY_ALLOWLIST[0]
    assert scm.rule_hits(f"fix: read {allowed} from the response") == []


# --------------------------------------------------------------------------
# Output discipline: SHAs and rule ids ONLY
# --------------------------------------------------------------------------

def test_output_never_echoes_a_restricted_term(tmp_path, monkeypatch, capsys):
    """The gate's whole point is that naming a term to prove its presence
    publishes it. That binds the gate's own output."""
    term = next(t for t in st.scoped_terms() if t not in bb._BRANDING_CANARIES)
    root = _repo(tmp_path / "r")
    _commit(root, "chore: base")
    _run(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _branch_off_main(root)
    _commit(root, f"chore: touch {term} handling")
    monkeypatch.setattr(scm, "REPO_ROOT", root)
    assert scm.main() == 1
    captured = capsys.readouterr()
    assert term.lower() not in (captured.out + captured.err).lower()


def test_output_never_echoes_the_matched_message(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path / "r")
    _commit(root, "chore: base")
    _run(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _branch_off_main(root)
    _commit(root, "chore: redact zz-distinctive-sentinel from the fixture")
    monkeypatch.setattr(scm, "REPO_ROOT", root)
    assert scm.main() == 1
    combined = capsys.readouterr()
    text = combined.out + combined.err
    assert "zz-distinctive-sentinel" not in text
    assert "redact zz" not in text
    # The stem appears only as the rule id, which is defined in this repo's own
    # source and is not the commit's text.
    assert "MESSAGE HIT [redaction/redact]" in text


def test_reported_sha_is_the_offending_commit(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path / "r")
    _commit(root, "chore: base")
    _run(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _branch_off_main(root)
    _commit(root, "feat: an ordinary change")
    guilty = _commit(root, "chore: scrub the fixture")
    monkeypatch.setattr(scm, "REPO_ROOT", root)
    scm.main()
    err = capsys.readouterr().err
    assert guilty[:12] in err


# --------------------------------------------------------------------------
# Exit codes
# --------------------------------------------------------------------------

def test_main_exits_zero_on_a_clean_range(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path / "r")
    _commit(root, "chore: base")
    _run(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _branch_off_main(root)
    _commit(root, "feat: add a country deep-dive step")
    monkeypatch.setattr(scm, "REPO_ROOT", root)
    assert scm.main() == 0
    assert "scanned — clean" in capsys.readouterr().out


def test_main_exits_zero_on_an_empty_range(tmp_path, monkeypatch, capsys):
    """Nothing outgoing is genuinely clean — distinct from no base ref at all."""
    root = _repo(tmp_path / "r")
    _commit(root, "chore: base")
    _run(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    monkeypatch.setattr(scm, "REPO_ROOT", root)
    assert scm.main() == 0


def test_main_exits_two_when_the_range_is_undeterminable(tmp_path, monkeypatch,
                                                         capsys):
    """Exit 2, not 0: a scan that cannot see the range has not cleared it."""
    root = _repo(tmp_path / "r")
    _commit(root, "chore: base")
    _run(root, "branch", "-m", "main", "trunk")
    monkeypatch.setattr(scm, "REPO_ROOT", root)
    assert scm.main() == 2
    assert "no base ref resolved" in capsys.readouterr().err


def test_main_exits_one_on_a_hit(tmp_path, monkeypatch):
    root = _repo(tmp_path / "r")
    _commit(root, "chore: base")
    _run(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _branch_off_main(root)
    _commit(root, "chore: rebuild the mocks from a live capture")
    monkeypatch.setattr(scm, "REPO_ROOT", root)
    assert scm.main() == 1
