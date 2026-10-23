"""Tests for client_guard.py. Synthetic names and key only; no real client names."""
from __future__ import annotations

import base64
import gzip
import io
import json
import os
import subprocess
import sys
import time
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
    main_tip = _commit_registry(repo, registry, monkeypatch)
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
