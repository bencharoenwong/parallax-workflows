"""Tests for client_guard.py. Synthetic names and key only; no real client names."""
from __future__ import annotations

import base64
import gzip
import io
import json
import os
import struct
import subprocess
import sys
import time
import tracemalloc
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import client_guard as cg  # noqa: E402

KEY = b"test-key-not-a-secret"
NAMES = ["Acme Widgets", "O'Neil Capital"]


@pytest.fixture
def registry(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "registry.json"
    # add_names scans REPO_ROOT before saving and refuses outside a git
    # repository, so register the fixture names inside an empty one -- never
    # the real checkout the tests run from.
    empty = tmp_path / "registry-repo"
    empty.mkdir()
    subprocess.run(["git", "init", "-q", str(empty)], check=True, capture_output=True)
    monkeypatch.setattr(cg, "REPO_ROOT", empty)
    cg.add_names(KEY, NAMES, path)
    monkeypatch.setattr(cg, "REGISTRY_PATH", path)
    monkeypatch.setattr(cg, "ALLOW_PATH", tmp_path / "allow-binary.txt")
    monkeypatch.setenv(cg.KEY_ENV, KEY.decode())
    return path


@pytest.fixture
def scanner(registry) -> cg.Scanner:
    return cg.Scanner(KEY, cg.Registry.load(registry))


# --- matching ---------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "AcmeWidgets", "Acme Widgets", "ACME-WIDGETS", "acme_widgets", "acme+widgets",
    "see https://www.acme.widgets.com/ for the guide", "theAcmeWidgetsPack",
    "A c m e Widgets", "\uff21\uff43\uff4d\uff45 \uff37\uff49\uff44\uff47\uff45\uff54\uff53",
    "Acme & Widgets", "Acme&Widgets", "Acme/Widgets", "Acme: Widgets", "Acme|Widgets",
    "Acme\u00b7Widgets", "Acme\u2013Widgets", "Acme \u2014 Widgets", "Acme%20Widgets",
    "Acme\u00a0Widgets", "Acme    Widgets", "Acme*Widgets",
    "brand: Acme\n  Widgets", "> Acme\n> Widgets", "# Acme\n# Widgets",
    "// Acme\n// Widgets", " * Acme\n * Widgets", "Acme\rWidgets", "Acme\n\nWidgets",
    "Ac\u200bme Widgets", "Acme\u00adWidgets", "Acme\u2060Widgets",
    "\u0410cme Widgets", "Acm\u0435 Widg\u0435ts",
    "&#65;cme Widgets", "Acme &amp; Widgets", "\\u0041cme Widgets",
    "<w:t>Acme</w:t></w:r><w:r><w:t xml:space=\"preserve\"> Widgets</w:t>",
    "<w:t>Ac</w:t></w:r><w:r><w:t>meWidgets</w:t>",
    "O'Neil Capital", "O\u2019Neil Capital", "ONeil Capital",
    '"Acme" Widgets', "Acme`Widgets", "Acme~Widgets", "Acme\u2022Widgets", "Acme\u2212Widgets",
])
def test_variants_match(scanner, text):
    assert scanner.text_hits(text)


@pytest.mark.parametrize("text", [
    "", "Acme", "Widgets", "acme, widgets", "Acme;Widgets", "Acme\n\n\nWidgets",
    "match that first, plus the fallback", "Acme (Widgets)",
])
def test_non_matches(scanner, text):
    assert not scanner.text_hits(text)


def test_long_runs_stay_fast(scanner):
    blob = base64.b64encode(bytes(range(256)) * 2000).decode()  # ~680 KB, one run
    t = time.monotonic()
    assert not scanner.text_hits(blob)
    assert time.monotonic() - t < 10


# --- registry ---------------------------------------------------------------------

def test_registry_holds_no_plaintext(registry):
    raw = registry.read_text().lower()
    for word in ("acme", "widget", "neil", "capital"):
        assert word not in raw
    data = json.loads(raw)
    assert data["version"] == 2
    assert len(data["digests"]) == 2 and len(data["prefixes"]) == 2


def test_add_is_idempotent(registry):
    assert cg.add_names(KEY, ["ACME widgets", "acme-widgets", "Acme & Widgets"], registry) == 0


def test_add_warns_on_punctuation_that_ends_a_run(registry, capsys):
    cg.add_names(KEY, ["Smith, Jones Group"], registry)
    assert "comma" in capsys.readouterr().err


def test_add_rejects_short_names(registry):
    with pytest.raises(cg.GuardError):
        cg.add_names(KEY, ["a-b"], registry)


def test_wrong_key_does_not_match(registry):
    assert not cg.Scanner(b"another-key", cg.Registry.load(registry)).text_hits("Acme Widgets")


def test_v1_or_empty_registry_fails_closed(tmp_path):
    for payload in ({"version": 1, "algorithm": "hmac-sha256", "lengths": [3], "digests": ["x"]},
                    {"version": 2, "algorithm": "hmac-sha256", "lengths": [], "digests": [],
                     "prefixes": []}):
        p = tmp_path / "r.json"
        p.write_text(json.dumps(payload))
        with pytest.raises(cg.GuardError):
            cg.Registry.load(p)


def test_missing_key_fails_closed(registry, monkeypatch, tmp_path):
    monkeypatch.delenv(cg.KEY_ENV, raising=False)
    monkeypatch.setattr(cg, "KEY_FILE", tmp_path / "absent.key")
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))
    assert cg.main(["scan-text"]) == 2


# --- output never names the client ------------------------------------------------

def _assert_no_name(*streams: str) -> None:
    for s in streams:
        low = s.lower()
        assert "acme" not in low and "widget" not in low


def test_output_never_contains_the_name(registry, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("Built for Acme Widgets first."))
    assert cg.main(["scan-text", "--label", "PR #1 body"]) == 1
    out = capsys.readouterr()
    _assert_no_name(out.out, out.err)
    assert "PR #1 body" in out.err


def test_a_location_that_contains_the_name_is_withheld_in_ci(scanner):
    scanner.withhold = True
    scanner.scan_path("fixtures/acme-widgets-holdings.json",
                      "commit abc:fixtures/acme-widgets-holdings.json", "commit abc")
    assert scanner.hits
    for _rule, where in scanner.hits:
        _assert_no_name(where)
        assert where.startswith("commit abc")


# --- file formats -----------------------------------------------------------------

def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_archive_members_are_scanned(scanner):
    scanner.scan_bytes(_zip({"word/document.xml": b"<w:t>Acme Widgets pack</w:t>"}),
                       "fixtures/pack.docx", "pack.docx")
    assert ("client/name", "pack.docx!word/document.xml") in scanner.hits


def test_archive_member_names_are_scanned(scanner):
    scanner.scan_bytes(_zip({"media/acme-widgets-logo.xml": b"clean"}), "f.zip", "f.zip")
    assert any(rule == "client/name-in-path" for rule, _ in scanner.hits)


def test_split_word_runs_in_a_docx(scanner):
    xml = (b"<w:p><w:r><w:t>Ac</w:t></w:r><w:r><w:t>me Widg</w:t></w:r>"
           b"<w:r><w:t>ets</w:t></w:r></w:p>")
    scanner.scan_bytes(_zip({"word/document.xml": xml}), "x.docx", "x.docx")
    assert any(rule == "client/name" for rule, _ in scanner.hits)


@pytest.mark.parametrize("data", [
    "\ufeffAcme Widgets".encode("utf-16-le"),
    "Acme Widgets pricing table".encode("utf-16-le"),
    "Acme Widgets".encode("utf-32"),
    "\ufeffAcme Widgets".encode("utf-8"),
])
def test_unicode_encodings_are_decoded(scanner, data):
    scanner.scan_bytes(data, "notes.csv", "notes.csv")
    assert ("client/name", "notes.csv") in scanner.hits


@pytest.mark.parametrize("path, data, rule", [
    ("brand.pdf", b"%PDF-1.4 anything", "unscanned/opaque-file"),
    ("letter.doc", b"\xd0\xcf\x11\xe0 old office", "unscanned/opaque-file"),
    ("logo.png", b"\x89PNG\r\n\x1a\n", "unscanned/opaque-file"),
    ("data.gz", gzip.compress(b"Acme Widgets"), "unscanned/opaque-file"),
    ("blob.bin", b"\x00\x01\x02\x03" * 100, "unscanned/binary"),
    ("big.ds", b"version https://git-lfs.github.com/spec/v1\noid sha256:ab\n",
     "unscanned/lfs-pointer"),
    ("x.docx", b"PK\x03\x04garbage", "unscanned/bad-archive"),
])
def test_unreadable_files_are_blocked(scanner, path, data, rule):
    scanner.scan_bytes(data, path, path)
    assert scanner.hits == [(rule, path)]


def test_nested_archives_are_blocked(scanner):
    inner = _zip({"a.txt": b"hello"})
    scanner.scan_bytes(_zip({"inner.zip": inner}), "outer.zip", "outer.zip")
    assert ("unscanned/nested-archive", "outer.zip!inner.zip") in scanner.hits


def test_oversize_blob_is_a_hit(scanner, monkeypatch):
    monkeypatch.setattr(cg, "MAX_BLOB_BYTES", 10)
    scanner.scan_bytes(b"x" * 11, "big.txt", "big.txt")
    assert scanner.hits == [("unscanned/too-large", "big.txt")]


def test_allowlist_needs_the_key(registry, tmp_path):
    png = tmp_path / "logo.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nreviewed")
    assert cg.allow_files(KEY, [str(png)]) == 1
    raw = cg.ALLOW_PATH.read_text()
    assert "logo" not in raw  # no paths: a path could itself carry a name
    allowed = cg.parse_allowlist(KEY, raw, "allow")
    s = cg.Scanner(KEY, cg.Registry.load(registry), allowed)
    s.scan_bytes(png.read_bytes(), "logo.png", "logo.png")
    assert s.hits == []
    forged = f"{cg.git_blob_sha(b'other')} {'0' * 32}\n"
    for bad_key, text in ((KEY, forged), (b"wrong-key", raw),
                          (KEY, raw + "# note for Acme Widgets\n")):
        with pytest.raises(cg.GuardError):
            cg.parse_allowlist(bad_key, text, "allow")


# --- paths ------------------------------------------------------------------------

@pytest.mark.parametrize("path, rule", [
    ("skills/acme-widgets/SKILL.md", "client/name-in-path"),
    ("DECISIONS.md", "path/internal-doc"),
    ("skills/x/LEARNINGS.md", "path/internal-doc"),
    ("notes/HANDOFF-2026.md", "path/internal-doc"),
    ("docs/plans/spec.md", "path/internal-doc"),
    ("clients/foo/brand.yaml", "path/client-work"),
    ("skills/x/client-work/a.md", "path/client-work"),
])
def test_path_rules(scanner, path, rule):
    scanner.scan_path(path, path, "tree")
    assert any(r == rule for r, _ in scanner.hits)


@pytest.mark.parametrize("path", [
    "skills/parallax-client-review/SKILL.md", "docs/security/audit-latest.md",
    "skills/_parallax/client-policy/policy-loader.md", "README.md",
])
def test_paths_that_must_pass(scanner, path):
    scanner.scan_path(path)
    assert scanner.hits == []


# --- git integration --------------------------------------------------------------

def _git(repo: Path, *args: str, env: dict | None = None) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env={**os.environ, **(env or {})}).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch, registry) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "T")
    (r / "README.md").write_text("hello\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    monkeypatch.setattr(cg, "REPO_ROOT", r)
    return r


def _commit(repo: Path, rel: str, text: str, msg: str, env: dict | None = None) -> str:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg, env=env)
    return _git(repo, "rev-parse", "HEAD")


# --- add refuses to register a name already public in REPO_ROOT ------------------

def test_add_refuses_when_new_name_already_in_head_tree(repo, registry):
    _commit(repo, "fixture.yaml", "brand: Globex Corp\n", "add fixture")
    before = registry.read_text()
    with pytest.raises(cg.RegistrationBlocked):
        cg.add_names(KEY, ["Globex Corp"], registry)
    assert registry.read_text() == before


def test_add_refuses_when_new_name_in_uncommitted_working_file(repo, registry):
    # Untracked, never committed -- only the working-tree pass can see it.
    (repo / "draft.md").write_text("notes: Globex Corp\n")
    before = registry.read_text()
    with pytest.raises(cg.RegistrationBlocked):
        cg.add_names(KEY, ["Globex Corp"], registry)
    assert registry.read_text() == before


def test_add_succeeds_on_a_clean_repo(repo, registry):
    assert cg.add_names(KEY, ["Totally Clean Co"], registry) == 1


def test_add_ignores_preexisting_hits_from_already_registered_names(repo, registry):
    # "Acme Widgets" is already registered (see NAMES) and already leaked
    # into this unrelated file; registering an unrelated new name must not
    # be blocked by a pre-existing hit that new name did not cause.
    _commit(repo, "legacy.yaml", "brand: Acme Widgets\n", "legacy leak")
    assert cg.add_names(KEY, ["Globex Corp"], registry) == 1


def test_add_works_on_a_repo_with_no_head(tmp_path, registry, monkeypatch):
    empty_repo = tmp_path / "empty-repo"
    empty_repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(empty_repo)], check=True,
                   capture_output=True)
    monkeypatch.setattr(cg, "REPO_ROOT", empty_repo)
    assert cg.add_names(KEY, ["Brand New Co"], registry) == 1


def test_add_refusal_prints_locations_but_never_commits_the_name(repo, registry, capsys):
    _commit(repo, "fixture.yaml", "brand: Globex Corp\n", "add fixture")
    with pytest.raises(cg.RegistrationBlocked):
        cg.add_names(KEY, ["Globex Corp"], registry)
    err = capsys.readouterr().err
    assert "fixture.yaml" in err
    assert "globex" not in err.lower()  # a content hit prints its path, never the text


def test_add_cli_exits_1_not_2_when_name_already_public(repo, registry, monkeypatch, capsys):
    # The GuardError/RegistrationBlocked except-clause ordering in main() is
    # what actually decides the exit code; drive the CLI, not add_names
    # directly, so that routing is under test too.
    _commit(repo, "fixture.yaml", "brand: Globex Corp\n", "add fixture")
    monkeypatch.setattr(sys, "stdin", io.StringIO("Globex Corp\n"))
    assert cg.main(["add"]) == 1
    assert "BLOCKED" in capsys.readouterr().err


def test_add_refuses_when_new_name_only_in_a_path(repo, registry):
    # The name never appears in file content here -- only in the filename --
    # so this exercises the client/name-in-path rule specifically, not
    # client/name.
    _commit(repo, "globex-corp-notes.md", "clean\n", "add notes")
    with pytest.raises(cg.RegistrationBlocked):
        cg.add_names(KEY, ["Globex Corp"], registry)
    # add is local and key-holder only, so a path that itself contains the
    # name is printed as is; CI withholds such locations instead.


def test_add_ignores_gitignored_working_tree_files(repo, registry):
    # _scan_worktree_paths uses --exclude-standard like a real `git add`
    # would respect, not scan_dir's blanket walk -- an ignored file must not
    # block registration just because the name happens to sit in it on disk.
    (repo / ".gitignore").write_text("secret.md\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add gitignore")
    (repo / "secret.md").write_text("notes: Globex Corp\n")
    assert cg.add_names(KEY, ["Globex Corp"], registry) == 1


def test_range_catches_intermediate_commit(repo, scanner):
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "fixture.yaml", "brand: Acme Widgets\n", "add fixture")
    _commit(repo, "fixture.yaml", "brand: Example\n", "rename fixture")
    assert cg.scan_range(scanner, ["HEAD", f"^{base}"]) == 2
    assert any(w.endswith(":fixture.yaml") for _, w in scanner.hits)


def test_range_catches_message_and_branch(repo, scanner):
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "a.md", "clean\n", "validated against the acme-widgets site")
    cg.scan_range(scanner, ["HEAD", f"^{base}"], ref="refs/heads/feat/acme/widgets")
    rules = {r for r, _ in scanner.hits}
    assert "client/name" in rules and "client/name-in-path" in rules


def test_range_catches_author_identity(repo, scanner):
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "a.md", "clean\n", "feat: a",
            env={"GIT_AUTHOR_EMAIL": "dev@acmewidgets.com", "GIT_AUTHOR_NAME": "Dev"})
    cg.scan_range(scanner, ["HEAD", f"^{base}"])
    assert any(rule == "client/name" for rule, _ in scanner.hits)


def test_range_catches_content_added_in_a_merge(repo, scanner):
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, "side.md", "side\n", "side")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "main.md", "main\n", "main")
    _git(repo, "merge", "-q", "--no-commit", "--no-ff", "side")
    (repo / "evil.txt").write_text("Acme Widgets pricing\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "merge side")
    _git(repo, "rm", "-q", "evil.txt")
    _git(repo, "commit", "-q", "-m", "cleanup")
    cg.scan_range(scanner, ["HEAD", f"^{base}"])
    assert any(w.endswith(":evil.txt") for _, w in scanner.hits)


def test_annotated_tag_message_is_scanned(repo, scanner):
    _git(repo, "tag", "-a", "v9", "-m", "Release for Acme Widgets")
    tag = _git(repo, "rev-parse", "v9")
    cg.scan_range(scanner, [tag], ref="refs/tags/v9")
    assert any(where.startswith("tag object") for _, where in scanner.hits)


def test_a_gitlink_does_not_hide_later_blobs(repo, scanner):
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{base},aaa/sub")
    (repo / "zzz-leak.txt").write_text("Acme Widgets\n")
    _git(repo, "add", "zzz-leak.txt")
    _git(repo, "commit", "-q", "-m", "vendor")
    cg.scan_range(scanner, ["HEAD", f"^{base}"])
    assert any(w.endswith(":zzz-leak.txt") for _, w in scanner.hits)


def test_unreadable_object_fails_closed(repo):
    with pytest.raises(cg.GuardError):
        cg._cat_blobs(["0123456789abcdef0123456789abcdef01234567"])


def test_range_rejects_option_like_revs(repo, scanner):
    with pytest.raises(cg.GuardError):
        cg.scan_range(scanner, ["--all"])


def _commit_registry(repo: Path, registry: Path, monkeypatch) -> str:
    (repo / ".client-guard").mkdir(exist_ok=True)
    (repo / cg.REGISTRY_REL).write_text(registry.read_text())
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "registry")
    monkeypatch.setattr(cg, "REGISTRY_PATH", repo / cg.REGISTRY_REL)
    return _git(repo, "rev-parse", "HEAD")


def _event(tmp_path, monkeypatch, name: str, payload: dict) -> None:
    ev = tmp_path / "event.json"
    ev.write_text(json.dumps(payload))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(ev))
    monkeypatch.setenv("GITHUB_EVENT_NAME", name)


def test_ci_pull_request_scans_body(repo, registry, tmp_path, monkeypatch, capsys):
    base = _commit_registry(repo, registry, monkeypatch)
    head = _commit(repo, "a.md", "clean\n", "feat: a")
    _event(tmp_path, monkeypatch, "pull_request", {"pull_request": {
        "number": 7, "title": "feat: a", "body": "Built first for ACME Widgets.",
        "head": {"sha": head, "ref": "feat/a"}, "base": {"sha": base}}})
    monkeypatch.setenv("CLIENT_GUARD_TRUSTED_REV", base)
    assert cg.main(["ci"]) == 1
    assert "PR #7 body" in capsys.readouterr().err


def test_ci_uses_trusted_registry_so_a_pr_cannot_drop_digests(repo, registry, tmp_path,
                                                             monkeypatch):
    base = _commit_registry(repo, registry, monkeypatch)
    weakened = json.loads(registry.read_text())
    weakened["digests"], weakened["prefixes"] = ["0" * 64], ["0" * 64]
    (repo / cg.REGISTRY_REL).write_text(json.dumps(weakened))
    head = _commit(repo, "brand.yaml", "name: Acme Widgets\n", "feat: brand")
    _event(tmp_path, monkeypatch, "pull_request", {"pull_request": {
        "number": 9, "title": "t", "body": "",
        "head": {"sha": head, "ref": "feat/b"}, "base": {"sha": base}}})
    monkeypatch.setenv("CLIENT_GUARD_TRUSTED_REV", base)
    assert cg.main(["ci"]) == 1


def test_ci_fails_closed_without_a_trusted_registry(repo, registry, tmp_path, monkeypatch):
    base = _git(repo, "rev-parse", "HEAD")  # no registry committed here
    head = _commit(repo, "a.md", "clean\n", "feat: a")
    _event(tmp_path, monkeypatch, "pull_request", {"pull_request": {
        "number": 3, "title": "t", "body": "",
        "head": {"sha": head, "ref": "feat/a"}, "base": {"sha": base}}})
    monkeypatch.setenv("CLIENT_GUARD_TRUSTED_REV", base)
    assert cg.main(["ci"]) == 2


def test_ci_push_clean_and_deletion(repo, registry, tmp_path, monkeypatch):
    before = _git(repo, "rev-parse", "HEAD")
    after = _commit(repo, "a.md", "clean\n", "feat: a")
    _event(tmp_path, monkeypatch, "push", {"before": before, "after": after,
                                           "ref": "refs/heads/feat/a"})
    assert cg.main(["ci"]) == 0
    _event(tmp_path, monkeypatch, "push", {"before": after, "after": cg.ZERO_SHA,
                                           "ref": "refs/heads/feat/a"})
    assert cg.main(["ci"]) == 0


def test_scan_path_directory(tmp_path, scanner):
    d = tmp_path / "promote"
    (d / "sub").mkdir(parents=True)
    (d / "__pycache__").mkdir()
    (d / "__pycache__" / "x.pyc").write_bytes(b"\x00\x01binary")
    (d / "sub" / "ok.md").write_text("generic\n")
    (d / "sub" / "bad.md").write_text("for Acme Widgets\n")
    cg.scan_dir(scanner, d)
    assert scanner.hits == [("client/name", "sub/bad.md")]


def test_tracked_registry_is_valid():
    reg = cg.Registry.load(Path(__file__).resolve().parents[3] / cg.REGISTRY_REL)
    assert reg.digests and reg.prefixes and min(reg.lengths) >= cg.PREFIX_LEN


def test_the_guard_files_are_scanned_and_strict(scanner, registry):
    data = json.loads(registry.read_text())
    data["note"] = "for Acme Widgets"
    with pytest.raises(cg.GuardError):
        cg.Registry.parse(json.dumps(data), "registry")
    scanner.scan_bytes(b'{"note": "Acme Widgets"}', cg.REGISTRY_REL, cg.REGISTRY_REL)
    assert scanner.hits


def test_a_wrong_key_fails_closed(registry, monkeypatch):
    monkeypatch.setenv(cg.KEY_ENV, "stale-key")
    monkeypatch.setattr(sys, "stdin", io.StringIO("Acme Widgets"))
    assert cg.main(["scan-text"]) == 2
    with pytest.raises(cg.GuardError):
        cg.add_names(b"stale-key", ["Globex Corp"], registry)


@pytest.mark.parametrize("text, hit", [
    ("Apex", True), ("the apex fund", True), ("ApexFund", True), ("APEX-2", True),
    ("apex2026", True), ("capex", False), ("apexes", False), ("Tapex holdings", False),
])
def test_short_names_need_word_boundaries(registry, text, hit):
    cg.add_names(KEY, ["Apex"], registry)
    s = cg.Scanner(KEY, cg.Registry.load(registry))
    assert s.text_hits(text) is hit


def test_null_free_binary_is_blocked(scanner):
    scanner.scan_bytes(bytes(range(0x80, 0xFF)) * 3, "payload.key", "payload.key")
    assert scanner.hits == [("unscanned/binary", "payload.key")]


def test_a_few_legacy_bytes_still_read_as_text(scanner):
    data = ("plain notes " * 200 + "caf\u00e9 ").encode("latin-1") + b" Acme Widgets"
    scanner.scan_bytes(data, "notes.txt", "notes.txt")
    assert ("client/name", "notes.txt") in scanner.hits


def test_nested_tag_objects_are_scanned(repo, scanner):
    _git(repo, "tag", "-a", "inner", "-m", "Release for Acme Widgets")
    _git(repo, "tag", "-a", "outer", "-m", "wrapper", "inner")
    cg.scan_range(scanner, [_git(repo, "rev-parse", "outer")])
    assert sum(w.startswith("tag object") for _, w in scanner.hits) == 1


def _blob(repo: Path, text: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"], check=True,
                          capture_output=True, text=True, input=text).stdout.strip()


@pytest.mark.parametrize("annotated", [True, False])
def test_a_tag_pointing_at_a_blob_has_its_content_scanned(repo, scanner, annotated):
    """rev-list lists no commits for a blob, so its content was never read."""
    blob = _blob(repo, "deck for Acme Widgets\n")
    _git(repo, "tag", *(["-a", "-m", "clean"] if annotated else []), "b1", blob)
    cg.scan_range(scanner, [_git(repo, "rev-parse", "b1")], ref="refs/tags/b1")
    assert ("client/name", f"tagged blob {blob[:12]}") in scanner.hits


def test_a_tag_pointing_at_a_tree_has_its_content_scanned(repo, scanner):
    blob = _blob(repo, "deck for Acme Widgets\n")
    tree = subprocess.run(["git", "-C", str(repo), "mktree"], check=True, capture_output=True,
                          text=True, input=f"100644 blob {blob}\tdeck.txt\n").stdout.strip()
    _git(repo, "tag", "-a", "-m", "clean", "t1", tree)
    cg.scan_range(scanner, [_git(repo, "rev-parse", "t1")], ref="refs/tags/t1")
    assert ("client/name", f"{tree}:deck.txt") in scanner.hits


def test_a_clean_blob_tag_passes(repo, scanner):
    blob = _blob(repo, "nothing to see\n")
    _git(repo, "tag", "-a", "-m", "clean", "b2", blob)
    cg.scan_range(scanner, [_git(repo, "rev-parse", "b2")], ref="refs/tags/b2")
    assert scanner.hits == []


def test_ci_tag_push_reads_the_tag_through_the_ref(repo, registry, tmp_path, monkeypatch):
    _git(repo, "tag", "-a", "v1", "-m", "Release for Acme Widgets")
    commit = _git(repo, "rev-parse", "HEAD")
    _event(tmp_path, monkeypatch, "push", {"before": cg.ZERO_SHA, "after": commit,
                                           "ref": "refs/tags/v1"})
    assert cg.main(["ci"]) == 1


@pytest.mark.parametrize("text,rc", [("nothing to see\n", 0), ("deck for Acme Widgets\n", 1)])
def test_ci_push_of_a_tag_on_a_blob_scans_it_without_failing(repo, registry, tmp_path,
                                                             monkeypatch, text, rc):
    """A blob has no tree; CI went red on every such tag, clean or not."""
    blob = _blob(repo, text)
    _git(repo, "tag", "-a", "-m", "clean", "b1", blob)
    tag = _git(repo, "rev-parse", "b1")
    _event(tmp_path, monkeypatch, "push", {"before": cg.ZERO_SHA, "after": tag,
                                           "ref": "refs/tags/b1"})
    assert cg.main(["ci"]) == rc


def test_ci_push_whose_object_is_missing_fails_closed(repo, registry, tmp_path, monkeypatch):
    _event(tmp_path, monkeypatch, "push", {"before": cg.ZERO_SHA, "after": "2" * 40,
                                           "ref": "refs/heads/feat/x"})
    assert cg.main(["ci"]) == 2


def test_ci_force_push_with_missing_old_tip_still_scans(repo, registry, tmp_path, monkeypatch):
    after = _commit(repo, "a.md", "Acme Widgets\n", "feat: a")
    _event(tmp_path, monkeypatch, "push", {"before": "1" * 40, "after": after,
                                           "ref": "refs/heads/feat/a"})
    assert cg.main(["ci"]) == 1


def test_ci_new_ref_at_trusted_tip_scans_nothing_old(repo, registry, tmp_path, monkeypatch):
    _commit(repo, "a.md", "Acme Widgets\n", "old public commit")
    _commit_registry(repo, registry, monkeypatch)
    (repo / "a.md").write_text("clean\n")
    tip = _commit(repo, "a.md", "clean\n", "clean tip")
    _event(tmp_path, monkeypatch, "push", {"before": cg.ZERO_SHA, "after": tip,
                                           "ref": "refs/heads/feat/new"})
    monkeypatch.setenv("CLIENT_GUARD_TRUSTED_REV", tip)
    assert cg.main(["ci"]) == 0


@pytest.mark.parametrize("name, payload", [
    ("issue_comment", {"comment": {"body": "see the Acme Widgets deck"}, "issue": {"title": "t"}}),
    ("issues", {"issue": {"title": "Acme Widgets onboarding", "body": ""}}),
    ("release", {"release": {"name": "v1", "body": "for Acme Widgets", "tag_name": "v1"}}),
])
def test_ci_scans_issue_comment_and_release_text(registry, tmp_path, monkeypatch, name, payload):
    _event(tmp_path, monkeypatch, name, payload)
    assert cg.main(["ci"]) == 1


# --- issue_comment scans only the comment's own fields, never the issue's --------

def test_issue_comment_with_name_only_in_the_issue_is_clean(registry, tmp_path, monkeypatch):
    # The issue (someone else's text) carries the name; the comment itself
    # does not. An issue_comment run must not scan the issue's own fields.
    _event(tmp_path, monkeypatch, "issue_comment", {
        "comment": {"body": "looks fine to me"},
        "issue": {"title": "Acme Widgets onboarding", "body": "for Acme Widgets"},
    })
    assert cg.main(["ci"]) == 0


def test_issue_comment_with_name_in_the_comment_hits_only_the_comment_location(
        registry, tmp_path, monkeypatch, capsys):
    _event(tmp_path, monkeypatch, "issue_comment", {
        "comment": {"body": "see the Acme Widgets deck"},
        "issue": {"title": "clean title", "body": "clean body"},
    })
    assert cg.main(["ci"]) == 1
    err = capsys.readouterr().err
    assert "issue_comment comment body" in err
    assert "issue_comment issue" not in err


def test_an_unexpected_crash_blocks(registry, monkeypatch):
    def boom(*a, **k):
        raise KeyError("x")
    monkeypatch.setattr(cg.Scanner, "scan_text", boom)
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))
    assert cg.main(["scan-text"]) == 2


@pytest.mark.parametrize("text, hit", [
    ("APEXClient", True), ("loadAPEXHoldings", True), ("XMLApex", True), ("APIApex", True),
])
def test_short_acronym_names_glued_to_words(registry, text, hit):
    cg.add_names(KEY, ["Apex"], registry)
    assert cg.Scanner(KEY, cg.Registry.load(registry)).text_hits(text) is hit


def test_duplicate_content_reports_every_path(repo, scanner):
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("Acme Widgets\n")
    (repo / "b.txt").write_text("Acme Widgets\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "dup")
    cg.scan_range(scanner, ["HEAD", f"^{base}"])
    paths = {w.rsplit(":", 1)[1] for _, w in scanner.hits}
    assert {"a.txt", "b.txt"} <= paths


def test_unreadable_tag_object_fails_closed(repo, scanner):
    with pytest.raises(cg.GuardError):
        cg._scan_tags(scanner, "deadbeef" * 5)


def test_withheld_location_never_falls_back_to_itself(scanner):
    scanner.withhold = True
    scanner.report("client/name", "x/acme-widgets.txt", context="acme-widgets.zip")
    scanner.report("client/name", "y/acme-widgets.txt")
    for _, where in scanner.hits:
        _assert_no_name(where)


def test_ref_names_skip_path_rules(scanner):
    scanner.scan_path("notes/release-plan", "ref refs/heads/notes/release-plan",
                      "pushed ref", path_rules=False)
    assert scanner.hits == []


def test_a_group_readable_key_file_is_refused(tmp_path, monkeypatch):
    kf = tmp_path / "k.key"
    kf.write_text("abc")
    kf.chmod(0o644)
    monkeypatch.delenv(cg.KEY_ENV, raising=False)
    monkeypatch.setattr(cg, "KEY_FILE", kf)
    with pytest.raises(cg.GuardError):
        cg.load_key()
    kf.chmod(0o600)
    assert cg.load_key() == b"abc"


# --- CLIENT_GUARD_CHANGE_REV (pull_request_target reads the PR's own files as
# git objects, since the working copy stays pinned to the trusted base) ------------

def test_change_rev_registry_is_matched(repo, registry, tmp_path, monkeypatch):
    (repo / ".client-guard").mkdir(exist_ok=True)
    (repo / cg.REGISTRY_REL).write_text(registry.read_text())
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "registry")
    change_rev = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(cg, "REGISTRY_PATH", tmp_path / "nowhere.json")  # no working-copy registry
    monkeypatch.setenv(cg.CHANGE_ENV, change_rev)
    scanner = cg.build_scanner(KEY)
    assert scanner.text_hits("Acme Widgets")


def test_change_rev_allowlist_is_honored(repo, registry, tmp_path, monkeypatch):
    png = tmp_path / "logo.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nreviewed")
    cg.allow_files(KEY, [str(png)])
    (repo / ".client-guard").mkdir(exist_ok=True)
    (repo / cg.REGISTRY_REL).write_text(registry.read_text())
    (repo / cg.ALLOW_REL).write_text(cg.ALLOW_PATH.read_text())
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "allow")
    change_rev = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(cg, "REGISTRY_PATH", tmp_path / "nowhere.json")
    monkeypatch.setattr(cg, "ALLOW_PATH", tmp_path / "nowhere-allow.txt")
    monkeypatch.setenv(cg.CHANGE_ENV, change_rev)
    scanner = cg.build_scanner(KEY)
    assert cg.git_blob_sha(png.read_bytes()) in scanner.allowed
    scanner.scan_bytes(png.read_bytes(), "logo.png", "logo.png")
    assert scanner.hits == []


def test_change_rev_allowlist_unsigned_line_fails_closed(repo, registry, tmp_path, monkeypatch):
    bad = f"{cg.git_blob_sha(b'x')} {'0' * 32}\n"  # not signed by this key
    (repo / ".client-guard").mkdir(exist_ok=True)
    (repo / cg.REGISTRY_REL).write_text(registry.read_text())
    (repo / cg.ALLOW_REL).write_text(bad)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "bad-allow")
    change_rev = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(cg, "REGISTRY_PATH", tmp_path / "nowhere.json")
    monkeypatch.setattr(cg, "ALLOW_PATH", tmp_path / "nowhere-allow.txt")
    monkeypatch.setenv(cg.CHANGE_ENV, change_rev)
    with pytest.raises(cg.GuardError):
        cg.build_scanner(KEY)


def test_change_rev_with_files_absent_there_is_fine(repo, registry, monkeypatch):
    base = _git(repo, "rev-parse", "HEAD")  # neither file is committed at this rev
    monkeypatch.setenv(cg.CHANGE_ENV, base)
    scanner = cg.build_scanner(KEY)  # the working-copy registry still supplies a source
    assert isinstance(scanner, cg.Scanner)


# --- invisible characters (every Cf code point plus invisible marks) --------------

_NEW_INVISIBLE_RANGES = [
    (0x0600, 0x0605), (0x06DD, 0x06DD), (0x070F, 0x070F), (0x0890, 0x0891),
    (0x08E2, 0x08E2), (0x180B, 0x180D), (0x180F, 0x180F), (0xFE00, 0xFE0F),
    (0xFFF9, 0xFFFB), (0x110BD, 0x110BD), (0x110CD, 0x110CD),
    (0x13430, 0x1343F), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A),
    (0xE0001, 0xE0001), (0xE0020, 0xE007F), (0xE0100, 0xE01EF),
    (0x3164, 0x3164), (0xFFA0, 0xFFA0),
]
_NEW_INVISIBLE_CODEPOINTS = [cp for lo, hi in _NEW_INVISIBLE_RANGES for cp in range(lo, hi + 1)]


@pytest.mark.parametrize("cp", _NEW_INVISIBLE_CODEPOINTS, ids=lambda cp: f"U+{cp:04X}")
def test_every_newly_added_invisible_codepoint_is_stripped(scanner, cp):
    assert scanner.text_hits(f"Ac{chr(cp)}me Widgets")


@pytest.mark.parametrize("sep", [" ", " "])
def test_line_and_paragraph_separator_join_a_run(scanner, sep):
    assert scanner.text_hits(f"Acme{sep}Widgets")


# --- word boundaries in no-space scripts -------------------------------------------

def test_apex_matches_inside_unspaced_chinese_prose(registry):
    cg.add_names(KEY, ["Apex"], registry)
    s = cg.Scanner(KEY, cg.Registry.load(registry))
    assert s.text_hits("我们和Apex公司合作")  # "we and Apex company cooperate"


def test_thai_short_name_matches_inside_unspaced_sentence(registry):
    # Synthetic nonsense consonant string, not a real company name.
    thai_name = "กขคง"
    cg.add_names(KEY, [thai_name], registry)
    s = cg.Scanner(KEY, cg.Registry.load(registry))
    # "we work with <name> company" with no spaces, as Thai prose is written.
    sentence = ("เราทํางานกับ"
                + thai_name + "บริษัท")
    assert s.text_hits(sentence)


@pytest.mark.parametrize("text, hit", [
    ("Apex", True), ("the apex fund", True), ("ApexFund", True), ("APEX-2", True),
    ("apex2026", True), ("capex", False), ("apexes", False), ("Tapex holdings", False),
])
def test_latin_short_name_boundaries_are_unchanged(registry, text, hit):
    cg.add_names(KEY, ["Apex"], registry)
    s = cg.Scanner(KEY, cg.Registry.load(registry))
    assert s.text_hits(text) is hit


# --- SVG and embedded images -------------------------------------------------------

def test_svg_file_is_opaque(scanner):
    scanner.scan_bytes(b"<svg><text>hello</text></svg>", "logo.svg", "logo.svg")
    assert scanner.hits == [("unscanned/opaque-file", "logo.svg")]


def test_markdown_with_embedded_image_payload_is_a_hit(scanner):
    png = base64.b64encode(b"\x89PNG\r\n\x1a\nreviewed-image-bytes").decode()
    text = f"![pic](data:image/png;base64,{png})"
    scanner.scan_bytes(text.encode(), "notes.md", "notes.md")
    assert ("unscanned/opaque-file", "notes.md (embedded image)") in scanner.hits


def test_embedded_image_allowlisted_by_blob_sha_is_clean(registry):
    payload_bytes = b"\x89PNG\r\n\x1a\nreviewed-image-bytes"
    allowed = frozenset({cg.git_blob_sha(payload_bytes)})
    s = cg.Scanner(KEY, cg.Registry.load(registry), allowed)
    png = base64.b64encode(payload_bytes).decode()
    s.scan_bytes(f"![pic](data:image/png;base64,{png})".encode(), "notes.md", "notes.md")
    assert s.hits == []


def test_embedded_image_empty_payload_is_clean(scanner):
    scanner.scan_bytes(b"data:image/png;base64,", "notes.md", "notes.md")
    assert scanner.hits == []


def test_known_empty_payload_fixture_text_stays_clean(scanner):
    # Mirrors the only data-URI occurrence in the repo today (a render-smoke
    # assertion string with an empty payload); it must never become a hit.
    scanner.scan_bytes(
        b"assert 'data:image/svg+xml;base64,' in r.render_html(RESPONSE, branding)",
        "test_render_smoke.py", "test_render_smoke.py")
    assert scanner.hits == []


def test_embedded_image_malformed_base64_reports_bad_embedded_image(scanner):
    # Split so this source file does not itself carry a malformed embedded image.
    scanner.scan_bytes(b"data:image/png;" + b"base64,QQ", "notes.md", "notes.md")
    assert ("unscanned/bad-embedded-image", "notes.md (embedded image)") in scanner.hits


def test_embedded_image_inside_an_archive_member_is_refused(scanner):
    png = base64.b64encode(b"\x89PNG\r\n\x1a\nreviewed-image-bytes").decode()
    md = f"![pic](data:image/png;base64,{png})".encode()
    scanner.scan_bytes(_zip({"notes.md": md}), "bundle.zip", "bundle.zip")
    assert ("unscanned/nested-archive", "bundle.zip!notes.md (embedded image)") in scanner.hits


def test_ipynb_png_output_is_a_hit(scanner):
    nb = {"cells": [{"cell_type": "code", "outputs": [{"output_type": "display_data",
          "data": {"image/png": base64.b64encode(
              b"\x89PNG\r\n\x1a\nreviewed-image-bytes").decode()}}]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("unscanned/opaque-file", "notebook.ipynb (embedded image)") in scanner.hits


def test_ipynb_svg_output_is_routed_as_svg(scanner):
    nb = {"cells": [{"outputs": [{"data": {"image/svg+xml": "<svg></svg>"}}]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("unscanned/opaque-file", "notebook.ipynb (embedded image)") in scanner.hits


def test_ipynb_malformed_base64_image_reports_bad_embedded_image(scanner):
    nb = {"cells": [{"outputs": [{"data": {"image/png": "QQ"}}]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("unscanned/bad-embedded-image", "notebook.ipynb (embedded image)") in scanner.hits


def test_malformed_ipynb_falls_back_to_plain_text_scan(scanner):
    scanner.scan_bytes(b"{not valid json, built for Acme Widgets", "broken.ipynb", "broken.ipynb")
    assert ("client/name", "broken.ipynb") in scanner.hits
    assert ("unscanned/bad-notebook", "broken.ipynb") in scanner.hits


def test_ipynb_that_parses_to_a_non_dict_reports_bad_notebook(scanner):
    scanner.scan_bytes(b"[1, 2, 3]", "notalist.ipynb", "notalist.ipynb")
    assert ("unscanned/bad-notebook", "notalist.ipynb") in scanner.hits


def test_ipynb_huge_integer_literal_is_parsed_without_raising(scanner):
    # Python's int-string conversion limit (4300 digits by default, 3.11+)
    # would otherwise turn a huge numeric literal into a ValueError
    # indistinguishable from genuinely malformed JSON. The source is split
    # across list entries (comma-separated in the raw bytes, so the
    # top-level whole-file plain-text scan does NOT join it -- see
    # test_ipynb_source_split_across_list_entries_is_joined) so this only
    # becomes a hit if the structured notebook parse actually succeeds.
    nb = {"cells": [{"cell_type": "markdown", "source": ["Ac", "me Widgets"]}],
          "n": None}
    nb_text = json.dumps(nb).replace("null", "9" * 5000)
    scanner.scan_bytes(nb_text.encode(), "huge.ipynb", "huge.ipynb")
    assert ("client/name", "huge.ipynb") in scanner.hits
    assert not any(rule == "unscanned/bad-notebook" for rule, _ in scanner.hits)


def test_deeply_nested_ipynb_reports_bad_notebook_not_crash(scanner):
    nested = "[" * 60000 + "]" * 60000
    scanner.scan_bytes(nested.encode(), "deep.ipynb", "deep.ipynb")
    assert ("unscanned/bad-notebook", "deep.ipynb") in scanner.hits


# --- notebook output mimes: javascript, +json/+xml, and the opaque fallback ------
# Each mime value below is a list split across two entries (comma-separated in
# the raw bytes) rather than one contiguous string, so the top-level whole-file
# plain-text scan does not already catch it on its own -- a hit here can only
# come from this mime actually being routed to the joined-text scan.

def test_ipynb_javascript_output_is_scanned_as_text(scanner):
    nb = {"cells": [{"outputs": [{"data": {"application/javascript":
          ["console.log('Ac", "me Widgets')"]}}]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("client/name", "notebook.ipynb") in scanner.hits


def test_ipynb_plus_json_suffix_mime_is_scanned_as_text(scanner):
    nb = {"cells": [{"outputs": [{"data": {"application/vnd.plotly.v1+json":
          ['{"brand": "Ac', 'me Widgets"}']}}]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("client/name", "notebook.ipynb") in scanner.hits


def test_ipynb_plus_xml_suffix_mime_is_scanned_as_text(scanner):
    nb = {"cells": [{"outputs": [{"data": {"application/rss+xml":
          ["<rss>Ac", "me Widgets</rss>"]}}]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("client/name", "notebook.ipynb") in scanner.hits


def test_ipynb_application_xml_mime_is_scanned_as_text(scanner):
    nb = {"cells": [{"outputs": [{"data": {"application/xml":
          ["<doc>Ac", "me Widgets</doc>"]}}]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("client/name", "notebook.ipynb") in scanner.hits


def test_ipynb_unrecognized_mime_is_opaque_not_silently_skipped(scanner):
    nb = {"cells": [{"outputs": [{"data": {"application/x-custom-widget":
          "clean, no name here"}}]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("unscanned/opaque-file", "notebook.ipynb") in scanner.hits


# --- lows: mergetag content, symlinks, quoted-printable ---------------------------

def test_commit_text_for_scan_drops_hex_headers_keeps_mergetag_body():
    raw = (
        "tree 1111111111111111111111111111111111111111\n"
        "parent 2222222222222222222222222222222222222222\n"
        "author T <t@example.com> 1700000000 +0000\n"
        "committer T <t@example.com> 1700000000 +0000\n"
        "mergetag object 3333333333333333333333333333333333333333\n"
        " type tag\n"
        " tag relTag\n"
        " tagger T <t@example.com> 1700000000 +0000\n"
        " \n"
        " Release for Acme Widgets\n"
        "\n"
        "merge tag\n"
    )
    cleaned = cg._commit_text_for_scan(raw)
    assert "1111111111111111111111111111111111111111" not in cleaned
    assert "2222222222222222222222222222222222222222" not in cleaned
    assert "3333333333333333333333333333333333333333" not in cleaned
    assert "Release for Acme Widgets" in cleaned
    assert "merge tag" in cleaned


def test_mergetag_carried_name_is_scanned_via_scan_range(repo, scanner):
    base = _git(repo, "rev-parse", "HEAD")
    tree = _git(repo, "rev-parse", "HEAD^{tree}")
    raw = (
        f"tree {tree}\n"
        f"parent {base}\n"
        "author T <t@example.com> 1700000000 +0000\n"
        "committer T <t@example.com> 1700000000 +0000\n"
        "mergetag object " + "a" * 40 + "\n"
        " type tag\n"
        " tag relTag\n"
        " tagger T <t@example.com> 1700000000 +0000\n"
        " \n"
        " Release for Acme Widgets\n"
        "\n"
        "merge tag\n"
    )
    commit_sha = subprocess.run(
        ["git", "-C", str(repo), "hash-object", "-t", "commit", "-w", "--stdin"],
        check=True, capture_output=True, text=True, input=raw,
    ).stdout.strip()
    cg.scan_range(scanner, [commit_sha, f"^{base}"])
    assert any(rule == "client/name" and where.endswith("message or identity")
              for rule, where in scanner.hits)


def test_scan_dir_scans_symlink_target_without_following(tmp_path, scanner):
    d = tmp_path / "promote2"
    d.mkdir()
    link = d / "notes.md"
    os.symlink("../private/Acme Widgets/secret.pdf", link)  # target need not exist
    cg.scan_dir(scanner, d)
    assert ("client/name", "notes.md") in scanner.hits
    assert all(rule != "unscanned/opaque-file" for rule, _ in scanner.hits)


@pytest.mark.parametrize("text", ["Acme Widg=\nets", "Acme Widg=\r\nets"])
def test_quoted_printable_soft_break_is_joined(scanner, text):
    assert scanner.text_hits(text)


# --- commit encoding header (ISO-8859-1 etc.) -------------------------------------

def test_commit_encoding_header_is_honored_for_the_message(repo, registry, monkeypatch):
    cg.add_names(KEY, ["Müller Kapital"], registry)
    base = _git(repo, "rev-parse", "HEAD")
    tree = _git(repo, "rev-parse", "HEAD^{tree}")
    msg = "Release for Müller Kapital\n".encode("latin-1")
    raw = (
        f"tree {tree}\n"
        f"parent {base}\n"
        "author T <t@example.com> 1700000000 +0000\n"
        "committer T <t@example.com> 1700000000 +0000\n"
        "encoding ISO-8859-1\n"
        "\n"
    ).encode("ascii") + msg
    commit_sha = subprocess.run(
        ["git", "-C", str(repo), "hash-object", "-t", "commit", "-w", "--stdin"],
        check=True, capture_output=True, input=raw,
    ).stdout.decode().strip()
    scanner = cg.Scanner(KEY, cg.Registry.load(registry))
    cg.scan_range(scanner, [commit_sha, f"^{base}"])
    assert any(rule == "client/name" for rule, _ in scanner.hits)


# --- data URIs: generic mime, params before base64, decoded-bytes routing --------

def _data_uri(mime: str, payload: bytes) -> bytes:
    # Each literal kept short and joined with `+` so this source file's own
    # text never contains a contiguous `data:...;base64,...` run (mirrors the
    # "Split so this source file" pattern used above for embedded images).
    return b"data:" + mime.encode() + b";" + b"base64," + base64.b64encode(payload)


def test_data_uri_svg_is_decoded_before_hashing_for_the_allowlist(registry):
    svg_bytes = b"<svg><text>reviewed</text></svg>"
    allowed = frozenset({cg.git_blob_sha(svg_bytes)})
    s = cg.Scanner(KEY, cg.Registry.load(registry), allowed)
    text = b"![x](" + _data_uri("image/svg+xml", svg_bytes) + b")"
    s.scan_bytes(text, "notes.md", "notes.md")
    assert s.hits == []


def test_data_uri_svg_without_the_allowlist_is_still_opaque(scanner):
    svg_bytes = b"<svg><text>not reviewed</text></svg>"
    text = b"![x](" + _data_uri("image/svg+xml", svg_bytes) + b")"
    scanner.scan_bytes(text, "notes.md", "notes.md")
    assert ("unscanned/opaque-file", "notes.md (embedded image)") in scanner.hits


def test_data_uri_pdf_is_routed_as_opaque(scanner):
    text = _data_uri("application/pdf", b"%PDF-1.4 fake")
    scanner.scan_bytes(text, "notes.md", "notes.md")
    assert ("unscanned/opaque-file", "notes.md (embedded data)") in scanner.hits


def test_data_uri_text_plain_is_scanned_as_decoded_text(scanner):
    text = _data_uri("text/plain", b"brand: Acme Widgets")
    scanner.scan_bytes(text, "notes.md", "notes.md")
    assert ("client/name", "notes.md (embedded data)") in scanner.hits


def test_data_uri_application_json_is_scanned_as_decoded_text(scanner):
    text = _data_uri("application/json", b'{"brand": "Acme Widgets"}')
    scanner.scan_bytes(text, "notes.md", "notes.md")
    assert ("client/name", "notes.md (embedded data)") in scanner.hits


def test_data_uri_unknown_mime_is_routed_as_binary(scanner):
    payload = bytes(range(0x80, 0xFF)) * 3  # not valid text in any read encoding
    text = _data_uri("application/octet-stream", payload)
    scanner.scan_bytes(text, "notes.md", "notes.md")
    assert ("unscanned/binary", "notes.md (embedded data)") in scanner.hits


def test_data_uri_params_before_base64_marker_and_case_insensitive(scanner):
    payload = base64.b64encode(b"brand: Acme Widgets").decode()
    text = ("DATA:" + "TEXT/PLAIN;charset=utf-8;" + "BASE64," + payload).encode()
    scanner.scan_bytes(text, "notes.md", "notes.md")
    assert ("client/name", "notes.md (embedded data)") in scanner.hits


# --- RFC 2397: empty media type, JSON-escaped slash -------------------------------
# Each piece below is kept as its own short literal and joined with `+` so this
# source file's own text never contains a contiguous `data:...;base64,...` run
# (same reasoning as the `_data_uri` helper above).

def test_data_uri_empty_media_type_defaults_to_text_plain(scanner):
    payload = base64.b64encode(b"brand: Acme Widgets").decode()
    text = "data:" + ";" + "base64," + payload
    scanner.scan_bytes(text.encode(), "notes.md", "notes.md")
    assert ("client/name", "notes.md (embedded data)") in scanner.hits


def test_data_uri_empty_media_type_and_empty_payload_is_clean(scanner):
    text = "data:" + ";" + "base64,"
    scanner.scan_bytes(text.encode(), "notes.md", "notes.md")
    assert scanner.hits == []


def test_data_uri_json_escaped_slash_in_media_type_is_normalized(scanner):
    payload = base64.b64encode(b"\x89PNG\r\n\x1a\nreviewed-image-bytes").decode()
    text = "data:" + "image" + "\\/" + "png" + ";" + "base64," + payload
    scanner.scan_bytes(text.encode(), "notes.md", "notes.md")
    assert ("unscanned/opaque-file", "notes.md (embedded image)") in scanner.hits


# --- quadratic backtracking on an adversarial header shape ------------------------

def test_data_uri_header_attacker_shape_is_bounded_in_time(scanner):
    # "data:a/b;x=" * n, ~1 MB: no "base64," marker ever arrives, which used
    # to make the old unbounded `(?:;...=[^;,]*)*` group backtrack
    # quadratically while hunting for one (0.9s at 22 KB, 15s at 88 KB).
    pattern = "data:a/b;x="
    text = (pattern * (1_000_000 // len(pattern) + 1))[:1_000_000]
    t = time.monotonic()
    scanner._scan_embedded_images(text, "n.md", "n.md", 0)
    assert time.monotonic() - t < 2


# --- data URI memory/size caps ----------------------------------------------------

def test_oversized_data_uri_payload_reports_too_large_without_materializing(scanner,
                                                                            monkeypatch):
    monkeypatch.setattr(cg, "MAX_BLOB_BYTES", 16)
    payload = "A" * 1000
    text = "data:" + "image/png;" + "base64," + payload
    scanner._scan_embedded_images(text, "n.md", "n.md", 0)
    assert scanner.hits == [("unscanned/too-large", "n.md (embedded data)")]


def test_large_data_uri_payload_is_bounded_in_time_and_memory(scanner):
    payload = "A" * (20 * 1024 * 1024)  # 20 MB of valid base64 characters, under the cap
    text = "data:" + "image/png;" + "base64," + payload
    tracemalloc.start()
    try:
        t = time.monotonic()
        scanner._scan_embedded_images(text, "big.md", "big.md", 0)
        elapsed = time.monotonic() - t
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert elapsed < 10
    assert peak < 6 * len(text)


def test_cat_blobs_returns_none_for_an_oversized_body(repo, monkeypatch):
    sha = _blob(repo, "x" * 2000)
    monkeypatch.setattr(cg, "MAX_BLOB_BYTES", 500)
    out = cg._cat_blobs([sha])
    assert out[sha] is None


# --- an oversized blob that is already allowlisted stays clean -------------------
# _cat_blobs discards its body without reading it into memory, so it never runs
# through scan_bytes's own in-memory allowlist check; the sha must be checked
# directly instead, as it was before MAX_BLOB_BYTES existed.

def test_report_oversized_skips_an_allowlisted_sha(scanner):
    scanner.allowed = frozenset({"deadbeef" * 5})
    cg._report_oversized(scanner, "deadbeef" * 5, "big.bin", "ctx")
    assert scanner.hits == []
    cg._report_oversized(scanner, "0" * 40, "other.bin", "ctx")
    assert scanner.hits == [("unscanned/too-large", "other.bin")]


def test_oversized_blob_allowlisted_by_sha_is_clean_in_scan_tree(repo, scanner, monkeypatch):
    monkeypatch.setattr(cg, "MAX_BLOB_BYTES", 10)
    (repo / "big.bin").write_text("x" * 50)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "big")
    sha = _git(repo, "rev-parse", "HEAD:big.bin")
    scanner.allowed = frozenset({sha})
    cg.scan_tree(scanner, "HEAD")
    assert scanner.hits == []


def test_oversized_blob_allowlisted_by_sha_is_clean_in_scan_range(repo, scanner, monkeypatch):
    base = _git(repo, "rev-parse", "HEAD")
    # The cap sits between the blob's size and the (much smaller) commit
    # object's own size, so only the blob trips the oversized path -- the
    # commit's own too-large check (a separate, unrelated code path) stays
    # out of this assertion.
    monkeypatch.setattr(cg, "MAX_BLOB_BYTES", 200)
    (repo / "big.bin").write_text("y" * 300)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "big")
    sha = _git(repo, "rev-parse", "HEAD:big.bin")
    scanner.allowed = frozenset({sha})
    cg.scan_range(scanner, ["HEAD", f"^{base}"])
    assert scanner.hits == []


def test_oversized_blob_not_allowlisted_is_still_a_hit_in_scan_tree(repo, scanner,
                                                                    monkeypatch):
    monkeypatch.setattr(cg, "MAX_BLOB_BYTES", 10)
    (repo / "big.bin").write_text("z" * 50)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "big")
    cg.scan_tree(scanner, "HEAD")
    assert any(rule == "unscanned/too-large" and where.endswith("big.bin")
              for rule, where in scanner.hits)


def test_oversized_commit_object_reports_too_large(repo, scanner, monkeypatch):
    base = _git(repo, "rev-parse", "HEAD")
    big = _commit(repo, "a.md", "x\n", "a very long commit message " * 50)
    monkeypatch.setattr(cg, "MAX_BLOB_BYTES", 500)
    cg.scan_range(scanner, [big, f"^{base}"])
    assert any(rule == "unscanned/too-large" and where.endswith("message or identity")
              for rule, where in scanner.hits)


def test_oversized_tag_object_reports_too_large(repo, scanner, monkeypatch):
    _git(repo, "tag", "-a", "bigtag", "-m", "x" * 2000)
    tag = _git(repo, "rev-parse", "bigtag")
    monkeypatch.setattr(cg, "MAX_BLOB_BYTES", 500)
    cg.scan_range(scanner, [tag], ref="refs/tags/bigtag")
    assert any(rule == "unscanned/too-large" and where.startswith("tag object")
              for rule, where in scanner.hits)


# --- notebooks: attachments, split source, nbformat 3 -----------------------------

def test_ipynb_attachment_image_is_blocked_not_silently_clean(scanner):
    nb = {"cells": [{"cell_type": "markdown", "source": "see image",
          "attachments": {"pic.png": {"image/png": base64.b64encode(
              b"\x89PNG\r\n\x1a\nreviewed-image-bytes").decode()}}}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("unscanned/opaque-file", "notebook.ipynb (embedded image)") in scanner.hits


def test_ipynb_source_split_across_list_entries_is_joined(scanner):
    nb = {"cells": [{"cell_type": "markdown", "source": ["Ac", "me Widgets"]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("client/name", "notebook.ipynb") in scanner.hits


def test_ipynb_nbformat3_worksheets_source_split_is_joined(scanner):
    nb = {"nbformat": 3, "worksheets": [{"cells": [{"cell_type": "code",
          "input": ["bra = 'Ac", "me Widgets'"]}]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("client/name", "notebook.ipynb") in scanner.hits


def test_ipynb_nbformat3_output_short_key_png_is_blocked(scanner):
    nb = {"cells": [{"outputs": [{"output_type": "pyout",
          "png": base64.b64encode(b"\x89PNG\r\n\x1a\nreviewed-image-bytes").decode()}]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("unscanned/opaque-file", "notebook.ipynb (embedded image)") in scanner.hits


# --- notebooks: malformed structure (wrong type where nbformat expects list/dict) -

def test_ipynb_dict_shaped_outputs_reports_bad_notebook(scanner):
    # A renderer that writes outputs as a dict (keyed, not a list) instead of
    # the list nbformat expects: the structured scan must not silently skip
    # the png riding inside it -- it must report the structure as bad.
    nb = {"cells": [{"outputs": {"o1": {"output_type": "display_data",
          "data": {"image/png": base64.b64encode(
              b"\x89PNG\r\n\x1a\nreviewed-image-bytes").decode()}}}}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("unscanned/bad-notebook", "notebook.ipynb") in scanner.hits


def test_ipynb_dict_shaped_cells_reports_bad_notebook(scanner):
    nb = {"cells": {"c1": {"cell_type": "markdown", "source": "hello"}}}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("unscanned/bad-notebook", "notebook.ipynb") in scanner.hits


def test_ipynb_dict_shaped_worksheets_reports_bad_notebook(scanner):
    nb = {"nbformat": 3, "worksheets": {"w1": {"cells": []}}}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("unscanned/bad-notebook", "notebook.ipynb") in scanner.hits


def test_ipynb_string_shaped_attachments_reports_bad_notebook(scanner):
    nb = {"cells": [{"cell_type": "markdown", "source": "see image",
          "attachments": "not-a-dict"}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert ("unscanned/bad-notebook", "notebook.ipynb") in scanner.hits


def test_ipynb_well_formed_notebook_reports_no_bad_notebook(scanner):
    # Sanity check alongside the malformed-structure cases above: a normal,
    # well-formed notebook must never trip the new type checks.
    nb = {"cells": [{"cell_type": "markdown", "source": "hello",
          "outputs": [], "attachments": {}}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "notebook.ipynb", "notebook.ipynb")
    assert not any(rule == "unscanned/bad-notebook" for rule, _ in scanner.hits)


# --- registry shrink via CLIENT_GUARD_CHANGE_REV ----------------------------------

def test_change_rev_registry_shrink_is_rejected_both_directions(repo, registry, tmp_path,
                                                                 monkeypatch):
    (repo / ".client-guard").mkdir(exist_ok=True)
    (repo / cg.REGISTRY_REL).write_text(registry.read_text())
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "registry")
    trusted_rev = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv(cg.TRUSTED_ENV, trusted_rev)
    monkeypatch.setattr(cg, "REGISTRY_PATH", tmp_path / "nowhere.json")

    # Direction 1: the change copy is a strict superset (adds a name) -- fine.
    cg.add_names(KEY, ["Globex Corp"], registry)
    (repo / cg.REGISTRY_REL).write_text(registry.read_text())
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "grow")
    change_rev = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv(cg.CHANGE_ENV, change_rev)
    scanner = cg.build_scanner(KEY)
    assert isinstance(scanner, cg.Scanner)

    # Direction 2: the change copy drops an entry the trusted copy has -- rejected.
    shrunk = json.loads(registry.read_text())
    shrunk["digests"] = shrunk["digests"][:1]
    shrunk["prefixes"] = shrunk["prefixes"][:1]
    (repo / cg.REGISTRY_REL).write_text(json.dumps(shrunk))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "shrink")
    shrink_rev = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv(cg.CHANGE_ENV, shrink_rev)
    with pytest.raises(cg.GuardError):
        cg.build_scanner(KEY)


def test_change_rev_missing_registry_file_is_rejected_when_trusted_exists(
        repo, registry, tmp_path, monkeypatch):
    # A trusted registry exists, but the change rev deletes the registry
    # file outright -- indistinguishable from a shrink to zero without a key
    # holder's say. Treating "absent" as "nothing to merge" here (the
    # ordinary optional-file behaviour) would let a PR dodge the shrink
    # check above just by deleting the file instead of editing it.
    (repo / ".client-guard").mkdir(exist_ok=True)
    (repo / cg.REGISTRY_REL).write_text(registry.read_text())
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "registry")
    trusted_rev = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv(cg.TRUSTED_ENV, trusted_rev)
    monkeypatch.setattr(cg, "REGISTRY_PATH", tmp_path / "nowhere.json")

    (repo / cg.REGISTRY_REL).unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "delete registry")
    change_rev = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv(cg.CHANGE_ENV, change_rev)
    with pytest.raises(cg.GuardError):
        cg.build_scanner(KEY)


# --- boundary offsets on the folded text, not the raw character index ------------

def test_folded_boundary_offsets_survive_casefold_expansion(registry):
    cg.add_names(KEY, ["acme"], registry)
    s = cg.Scanner(KEY, cg.Registry.load(registry))
    assert s.text_hits("ß漢acme漢")  # ß漢acme漢


# --- new line-break and filler separators -----------------------------------------

@pytest.mark.parametrize("sep", ["\x85", "\x0b", "\x0c"])  # NEL, VT, FF
def test_nel_vt_ff_join_a_run(scanner, sep):
    assert scanner.text_hits(f"Acme{sep}Widgets")


@pytest.mark.parametrize("cp", [0x115F, 0x1160, 0x3164, 0xFFA0])
def test_hangul_filler_is_a_separator_restoring_the_boundary(registry, cp):
    cg.add_names(KEY, ["apex"], registry)
    s = cg.Scanner(KEY, cg.Registry.load(registry))
    assert s.text_hits(f"T{chr(cp)}apex")


# --- corrupt deflate inside an otherwise well-formed zip --------------------------

def test_scan_archive_reports_bad_archive_on_corrupt_deflate(scanner):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.txt", b"hello world" * 50)
    data = bytearray(buf.getvalue())
    fn = struct.unpack("<H", data[26:28])[0]
    ex = struct.unpack("<H", data[28:30])[0]
    compressed_size = struct.unpack("<I", data[18:22])[0]
    start = 30 + fn + ex
    data[start:start + compressed_size] = b"\x00" * compressed_size
    scanner.scan_bytes(bytes(data), "x.zip", "x.zip")
    assert scanner.hits == [("unscanned/bad-archive", "x.zip")]


def test_add_refuses_outside_a_git_repository(tmp_path, registry, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "notes.md").write_text("Globex Corp\n")
    monkeypatch.setattr(cg, "REPO_ROOT", plain)
    before = registry.read_text()
    with pytest.raises(cg.GuardError):
        cg.add_names(KEY, ["Globex Corp"], registry)
    assert registry.read_text() == before


def test_add_refuses_a_name_only_in_unpushed_history(repo, registry):
    # Committed, then deleted from HEAD: the PR range scan would still print
    # the old commit's path, so registration must see it first.
    _commit(repo, "old.md", "Globex Corp\n", "add")
    _git(repo, "rm", "-q", "old.md")
    _git(repo, "commit", "-q", "-m", "remove")
    with pytest.raises(cg.RegistrationBlocked):
        cg.add_names(KEY, ["Globex Corp"], registry)


def test_add_ignores_history_already_on_origin_main(repo, registry):
    _commit(repo, "old.md", "Globex Corp\n", "add")
    _git(repo, "rm", "-q", "old.md")
    _git(repo, "commit", "-q", "-m", "remove")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert cg.add_names(KEY, ["Globex Corp"], registry) == 1


def test_add_refuses_a_name_only_in_the_index(repo, registry):
    (repo / "staged.md").write_text("Globex Corp\n")
    _git(repo, "add", "staged.md")
    (repo / "staged.md").write_text("clean\n")
    with pytest.raises(cg.RegistrationBlocked):
        cg.add_names(KEY, ["Globex Corp"], registry)


def test_add_refuses_a_named_index_path_missing_from_disk(repo, registry):
    staged = repo / "globex-corp.md"
    staged.write_text("clean\n")
    _git(repo, "add", staged.name)
    staged.unlink()
    before = registry.read_bytes()

    with pytest.raises(cg.RegistrationBlocked):
        cg.add_names(KEY, ["Globex Corp"], registry)

    assert registry.read_bytes() == before


def test_add_refuses_when_a_working_file_cannot_be_read(repo, registry):
    f = repo / "locked.md"
    f.write_text("Globex Corp\n")
    f.chmod(0)
    try:
        if os.access(f, os.R_OK):
            pytest.skip("running with privileges that ignore file modes")
        with pytest.raises(cg.GuardError):
            cg.add_names(KEY, ["Globex Corp"], registry)
    finally:
        f.chmod(0o644)


def test_add_refuses_a_name_in_an_untracked_symlink(repo, registry):
    (repo / "globex-corp-link").symlink_to("README.md")
    with pytest.raises(cg.RegistrationBlocked):
        cg.add_names(KEY, ["Globex Corp"], registry)


def test_add_with_no_names_is_an_error(repo, registry):
    with pytest.raises(cg.GuardError):
        cg.add_names(KEY, [], registry)


def test_allow_refuses_a_key_that_does_not_match_the_registry(repo, registry, tmp_path):
    f = tmp_path / "blob.bin"
    f.write_bytes(b"\x00\x01")
    with pytest.raises(cg.GuardError):
        cg.allow_files(b"some-other-key", [str(f)])


def test_symmetric_range_is_rejected_clearly(repo, scanner):
    with pytest.raises(cg.GuardError, match="symmetric range"):
        cg.scan_range(scanner, ["HEAD~0...HEAD"])


def test_change_rev_that_is_not_available_names_the_cause(repo, registry, monkeypatch):
    monkeypatch.setenv(cg.CHANGE_ENV, "f" * 40)
    with pytest.raises(cg.GuardError, match="not available"):
        cg.build_scanner(KEY)


# --- combining marks, wrapped data URIs, malformed notebooks, size caps --------

@pytest.mark.parametrize("name, sentence", [
    # Synthetic strings, not real company names.
    ("กรุงเทพ", "เราทำงานกับกรุงเทพบริษัท"),          # Thai with vowel marks
    ("नमस्ते भारत", "हम नमस्ते भारत के साथ"),          # Devanagari with matras
    ("Zentrq\u0301 Holdings", "notes on Zentrq\u0301 Holdings"),  # q + acute: no precomposed form
])
def test_names_with_combining_marks_match_when_written_verbatim(registry, name, sentence):
    cg.add_names(KEY, [name], registry)
    s = cg.Scanner(KEY, cg.Registry.load(registry))
    assert s.text_hits(sentence)


def test_add_does_not_warn_about_combining_marks(registry, capsys):
    cg.add_names(KEY, ["กรุงเทพ"], registry)
    assert "comma" not in capsys.readouterr().err


def _wrapped(payload: bytes, width: int = 76) -> list[str]:
    text = _data_uri("text/plain", payload).decode()
    return [text[i:i + width] + "\n" for i in range(0, len(text), width)]


def test_a_text_data_uri_wrapped_across_notebook_source_lines_is_read(scanner):
    lines = _wrapped(b"x" * 200 + b" Acme Widgets " + b"y" * 200)
    nb = {"cells": [{"cell_type": "markdown", "source": lines}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "n.ipynb", "n.ipynb")
    assert any(r == "client/name" for r, _ in scanner.hits)


def test_a_text_data_uri_wrapped_across_an_html_output_is_read(scanner):
    lines = _wrapped(b"x" * 200 + b" Acme Widgets " + b"y" * 200)
    nb = {"cells": [{"outputs": [{"data": {"text/html": lines}}]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "n.ipynb", "n.ipynb")
    assert any(r == "client/name" for r, _ in scanner.hits)


@pytest.mark.parametrize("value", [["iVBO", None], {"a": "b"}, True])
def test_a_malformed_binary_notebook_value_is_reported_not_crashed(scanner, value):
    nb = {"cells": [{"outputs": [{"data": {"image/png": value}}]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "n.ipynb", "n.ipynb")
    assert ("unscanned/bad-notebook", "n.ipynb") in scanner.hits


def test_a_non_dict_output_data_field_is_reported(scanner):
    nb = {"cells": [{"outputs": [{"data": ["not", "a", "dict"]}]}]}
    scanner.scan_bytes(json.dumps(nb).encode(), "n.ipynb", "n.ipynb")
    assert ("unscanned/bad-notebook", "n.ipynb") in scanner.hits


def test_an_unparsed_data_uri_header_is_reported(scanner):
    params = "".join(f";p{i}=v" for i in range(9))
    text = ("see data:text/plain" + params + ";" + "base64," + "QUJD" * 8).encode()
    scanner.scan_bytes(text, "notes.md", "notes.md")
    assert any(r == "unscanned/bad-embedded-image" for r, _ in scanner.hits)


@pytest.mark.parametrize("parameter_length", [1100, 100_000])
@pytest.mark.parametrize("payload", [b"Acme Widgets", b"x"])
@pytest.mark.parametrize("padding", [b"", b"\n", b"\\n"])
def test_a_long_unparsed_data_uri_header_is_reported(
        scanner, parameter_length, payload, padding):
    data = _data_uri("text/plain;p=" + "x" * parameter_length, payload)
    header, encoded = data.split(b",", 1)
    scanner.scan_bytes(header + b"," + padding + encoded, "notes.md", "notes.md")
    assert ("unscanned/bad-embedded-image", "notes.md (embedded data)") in scanner.hits


def test_a_data_uri_template_in_code_is_not_reported(scanner):
    code = ('return f"data:image/{mime};' + 'base64,{payload}"\n').encode()
    scanner.scan_bytes(code, "render.py", "render.py")
    assert scanner.hits == []


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_an_archive_over_the_member_cap_is_not_unpacked(scanner, monkeypatch):
    monkeypatch.setattr(cg, "MAX_ARCHIVE_MEMBERS", 3)
    data = _zip_bytes({f"m{i}.txt": b"Acme Widgets" for i in range(4)})
    scanner.scan_bytes(data, "a.zip", "a.zip")
    assert scanner.hits == [("unscanned/archive-too-large", "a.zip")]


def test_an_archive_over_the_size_cap_is_not_unpacked(scanner, monkeypatch):
    monkeypatch.setattr(cg, "MAX_ARCHIVE_BYTES", 100)
    data = _zip_bytes({"big.txt": b"x" * 101})
    scanner.scan_bytes(data, "a.zip", "a.zip")
    assert scanner.hits == [("unscanned/archive-too-large", "a.zip")]


def test_scan_dir_reports_an_oversized_file_without_reading_it(scanner, tmp_path, monkeypatch):
    monkeypatch.setattr(cg, "MAX_BLOB_BYTES", 10)
    d = tmp_path / "promote"
    d.mkdir()
    (d / "big.txt").write_bytes(b"Acme Widgets padding")
    read = []
    original = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes",
                        lambda self: read.append(self.name) or original(self))
    cg.scan_dir(scanner, d)
    assert ("unscanned/too-large", "big.txt") in scanner.hits
    assert "big.txt" not in read


def test_scan_dir_keeps_an_allowlisted_oversized_file_clean(registry, tmp_path, monkeypatch):
    monkeypatch.setattr(cg, "MAX_BLOB_BYTES", 10)
    d = tmp_path / "promote"
    d.mkdir()
    big = d / "big.bin"
    big.write_bytes(b"\x00" * 64)
    s = cg.Scanner(KEY, cg.Registry.load(registry), allowed=frozenset({cg._file_blob_sha(big)}))
    cg.scan_dir(s, d)
    assert s.hits == []
    assert cg._file_blob_sha(big) == cg.git_blob_sha(big.read_bytes())
