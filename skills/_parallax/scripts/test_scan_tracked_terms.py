"""Tests for the tracked-file term scan.

Fixtures are built from the loaded term lists at RUNTIME and never written as
literals -- this file is tracked in a public repo, so a hand-written "realistic
leak" fixture would be the leak it tests for.
"""
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_bundle as bb
import scan_tracked_terms as st


def _git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)


def _track(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=root, check=True)


def _track_bytes(root: Path, rel: str, content: bytes) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    subprocess.run(["git", "add", rel], cwd=root, check=True)


# --------------------------------------------------------------------------
# Term scope: branding + local-only in, pillar vocabulary out
# --------------------------------------------------------------------------

def test_scope_includes_branding_terms():
    scoped = set(st.scoped_terms())
    for term in bb._BRANDING_CANARIES:
        assert term in scoped


def test_scope_excludes_pillar_vocabulary():
    """The pillar vocabulary is how the house-view source is written and is
    documented as the public data contract. Including it would flag 33 legitimate
    files and train everyone to ignore the scanner."""
    scoped = set(st.scoped_terms())
    pillar = set(bb.CANARY_TERMS) - set(bb._BRANDING_CANARIES)
    assert pillar, "no pillar terms found — scope test is vacuous"
    assert not (pillar & scoped)


def test_scope_includes_local_only_terms():
    if not bb.EXTRA_CANARY_FILE.exists():
        pytest.skip("extra term file not present on this machine")
    extra = set(bb.load_canary_terms()) - set(bb.CANARY_TERMS)
    assert extra & set(st.scoped_terms())


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

@pytest.mark.parametrize("which", ["branding", "restricted"])
def test_scanner_catches_planted_term(tmp_path, monkeypatch, which):
    if which == "branding":
        term = bb._BRANDING_CANARIES[0]
    else:
        extra = sorted(set(bb.load_canary_terms()) - set(bb.CANARY_TERMS))
        if not extra:
            pytest.skip("no local-only terms on this machine")
        term = extra[0]
    _git_repo(tmp_path)
    _track(tmp_path, "doc.md", f"planted {term} here\n")
    monkeypatch.setattr(st, "REPO_ROOT", tmp_path)
    hits, _ = st.scan()
    assert [h for h in hits if h[0] == "doc.md"]


def test_scanner_passes_on_clean_repo(tmp_path, monkeypatch):
    _git_repo(tmp_path)
    _track(tmp_path, "doc.md", "nothing restricted here\n")
    monkeypatch.setattr(st, "REPO_ROOT", tmp_path)
    hits, _ = st.scan()
    assert hits == []


def test_scanner_catches_term_in_newline_filename(tmp_path, monkeypatch):
    term = bb._BRANDING_CANARIES[0]
    rel = "nested/name\ncontinued.md"
    _git_repo(tmp_path)
    _track(tmp_path, rel, f"{term}\n")
    monkeypatch.setattr(st, "REPO_ROOT", tmp_path)
    hits, unscanned = st.scan()
    assert (rel, "branding") in hits
    assert unscanned == []


def test_pillar_vocabulary_does_not_trip_the_scanner(tmp_path, monkeypatch):
    pillar = sorted(set(bb.CANARY_TERMS) - set(bb._BRANDING_CANARIES))
    _git_repo(tmp_path)
    _track(tmp_path, "loader.md", " ".join(pillar) + "\n")
    monkeypatch.setattr(st, "REPO_ROOT", tmp_path)
    hits, _ = st.scan()
    assert hits == []


# --------------------------------------------------------------------------
# Binary / archive handling
# --------------------------------------------------------------------------

def test_archive_parts_are_scanned(tmp_path, monkeypatch):
    """A term inside a .docx part must be found; the bundle gate's raw-byte
    approach cannot see into the container."""
    _git_repo(tmp_path)
    term = bb._BRANDING_CANARIES[0]
    docx = tmp_path / "fixture.docx"
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr("word/document.xml", f"<w:t>{term}</w:t>")
    subprocess.run(["git", "add", "fixture.docx"], cwd=tmp_path, check=True)
    monkeypatch.setattr(st, "REPO_ROOT", tmp_path)
    hits, unscanned = st.scan()
    assert [h for h in hits if h[0] == "fixture.docx"]
    assert "fixture.docx" not in unscanned


def test_undecodable_binary_is_reported_not_guessed(tmp_path, monkeypatch):
    """Raw-byte decoding invents characters -- a real .docx fixture decoded to
    branding glyphs that were not in the document. Such files must land in
    `unscanned`, never in `hits`."""
    _git_repo(tmp_path)
    _track_bytes(tmp_path, "asset.bin", bytes(range(256)) * 4)
    monkeypatch.setattr(st, "REPO_ROOT", tmp_path)
    hits, unscanned = st.scan()
    assert "asset.bin" in unscanned
    assert not [h for h in hits if h[0] == "asset.bin"]


def test_main_fails_for_unscanned_file(tmp_path, monkeypatch, capsys):
    _git_repo(tmp_path)
    _track_bytes(tmp_path, "asset.bin", bytes(range(256)) * 4)
    monkeypatch.setattr(st, "REPO_ROOT", tmp_path)
    assert st.main() == 1
    assert "asset.bin" in capsys.readouterr().err


def test_oversized_archive_fails_closed(tmp_path, monkeypatch, capsys):
    _git_repo(tmp_path)
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("document.xml", "ab")
    subprocess.run(["git", "add", "fixture.zip"], cwd=tmp_path, check=True)
    monkeypatch.setattr(st, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(st, "MAX_ARCHIVE_UNCOMPRESSED_BYTES", 1)
    hits, unscanned = st.scan()
    assert hits == []
    assert unscanned == ["fixture.zip"]
    assert st.main() == 1
    assert "fixture.zip" in capsys.readouterr().err


def test_text_file_with_unfamiliar_suffix_is_scanned(tmp_path, monkeypatch):
    """An unfamiliar suffix is not binary. Strict decode settles it, so plain
    ASCII fixtures are covered rather than silently skipped."""
    _git_repo(tmp_path)
    term = bb._BRANDING_CANARIES[0]
    _track(tmp_path, "key.priv", f"{term}\n")
    monkeypatch.setattr(st, "REPO_ROOT", tmp_path)
    hits, unscanned = st.scan()
    assert [h for h in hits if h[0] == "key.priv"]
    assert "key.priv" not in unscanned


# --------------------------------------------------------------------------
# The live assertion
# --------------------------------------------------------------------------

def test_this_repo_has_no_restricted_terms():
    """The point of the whole file: this public repo stays clean. Three
    exposures were found by hand before this ran automatically."""
    hits, unscanned = st.scan()
    assert hits == [], f"{len(set(hits))} tracked file(s) carry restricted terms"
    assert unscanned == [], f"{len(unscanned)} tracked file(s) were not scanned"
