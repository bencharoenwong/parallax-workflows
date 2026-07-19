#!/usr/bin/env python3
"""Scan every TRACKED file for terms that must not appear in a public repo.

Complements the distribution gate in build_bundle.py, which only ever sees
assembled bundle output. Anything tracked but not shipped -- repo-root docs, the
scripts/ directory, test fixtures, operator-tier skills -- was invisible to that
gate. Three separate exposures were found by hand before this existed: a test
fixture that hardcoded terms, this scripts/ directory, and the decision log.

TERM SCOPE DIFFERS FROM THE BUNDLE GATE, deliberately:

  branding + local-only terms  -- must appear in NO tracked file. Checked here.
  pillar vocabulary            -- legitimately present throughout the source
                                  (it is how the house-view skills are written)
                                  and documented in build_bundle.py as the
                                  public data contract. NOT checked here.

The bundle gate still checks all three, because the distribution transforms cut
the pillar sections before packaging; source and artifact have different rules.

BINARY HANDLING. Decoding arbitrary bytes with errors='replace' invents
characters: a compressed .docx byte run decodes to branding glyphs that are not
in the document at all (observed on a real fixture). So archives are opened and
their parts scanned, and other binaries are reported as unscanned rather than
guessed at -- a false positive here fails a build for a term nobody wrote.

Exit 0 clean, 1 on any hit. Run: python3 skills/_parallax/scripts/scan_tracked_terms.py
"""
from __future__ import annotations

import codecs
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_bundle as bb  # noqa: E402

REPO_ROOT = bb.REPO_ROOT

# Text-ish suffixes are decoded directly; everything else is treated as binary.
TEXT_SUFFIXES = {
    ".md", ".py", ".yaml", ".yml", ".json", ".txt", ".sh", ".toml", ".cfg",
    ".ini", ".html", ".css", ".js", ".ts", ".jsonl", ".csv", ".xml", ".sql",
}
# Zip-container formats whose parts carry the real text.
ARCHIVE_SUFFIXES = {".docx", ".xlsx", ".pptx", ".zip"}
MAX_ARCHIVE_MEMBERS = 10_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
APPROVED_UNSCANNED_FILES: frozenset[str] = frozenset()

def scoped_terms() -> list[str]:
    """Branding + local-only terms. Pillar vocabulary is excluded on purpose --
    see the module docstring."""
    pillar = set(bb.CANARY_TERMS) - set(bb._BRANDING_CANARIES)
    return [t for t in bb.load_canary_terms() if t not in pillar]


def _mask_allowlisted(text: str) -> str:
    hay = text.lower()
    for allowed in bb.CANARY_ALLOWLIST:
        hay = re.sub(r"(?<!\w)" + re.escape(allowed.lower()) + r"(?!\w)",
                     "\x00", hay)
    return hay


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        capture_output=True,
        check=True,
    ).stdout
    return sorted(os.fsdecode(path) for path in out.split(b"\0") if path)


def _hit_label(text: str, terms: list[str]) -> str | None:
    hay = _mask_allowlisted(text)
    for term in terms:
        if term.lower() in hay:
            return "branding" if term in bb._BRANDING_CANARIES else "restricted"
    return None


def _raw_hit_label(data: bytes, terms: list[str]) -> str | None:
    for term in terms:
        if term.isascii():
            found = re.search(re.escape(term.encode("ascii")), data, re.IGNORECASE)
        else:
            found = any(form.encode("utf-8") in data
                        for form in {term, term.lower(), term.upper()})
        if found:
            return "branding" if term in bb._BRANDING_CANARIES else "restricted"
    return None


def _archive_hit_label(member: zipfile.ZipExtFile, terms: list[str]) -> str | None:
    span = max([len(term) for term in terms] +
               [len(term) for term in bb.CANARY_ALLOWLIST] + [1])
    byte_span = max(len(form.encode("utf-8"))
                    for term in terms
                    for form in {term, term.lower(), term.upper()})
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    text_retained = ""
    byte_retained = b""
    text_label: str | None = None
    byte_label: str | None = None
    binary = False

    while chunk := member.read(64 * 1024):
        byte_body = byte_retained + chunk
        byte_label = byte_label or _raw_hit_label(byte_body, terms)
        byte_retained = byte_body[-byte_span:]
        if binary:
            continue
        try:
            text_chunk = decoder.decode(chunk)
        except UnicodeDecodeError:
            binary = True
            continue
        if text_label:
            continue
        text_body = text_retained + text_chunk
        if len(text_body) <= 2 * span:
            text_retained = text_body
            continue
        safe_end = len(text_body) - 2 * span
        text_label = _hit_label(text_body[:safe_end + span], terms)
        text_retained = text_body[safe_end:]

    if binary:
        return byte_label
    try:
        text_chunk = decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return byte_label
    if text_label:
        return text_label
    return _hit_label(text_retained + text_chunk, terms)


def _mark_unscanned(unscanned: list[str], rel: str) -> None:
    if rel not in APPROVED_UNSCANNED_FILES:
        unscanned.append(rel)


def scan() -> tuple[list[tuple[str, str]], list[str]]:
    """Returns (hits, unscanned). Each hit is (path, masked_term_label)."""
    terms = scoped_terms()
    hits: list[tuple[str, str]] = []
    unscanned: list[str] = []

    for rel in tracked_files():
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in ARCHIVE_SUFFIXES:
            try:
                with zipfile.ZipFile(path) as zf:
                    members = zf.infolist()
                    total_size = sum(member.file_size for member in members)
                    if (len(members) > MAX_ARCHIVE_MEMBERS or
                            total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES):
                        _mark_unscanned(unscanned, rel)
                        continue
                    for member in members:
                        try:
                            with zf.open(member) as part:
                                label = _archive_hit_label(part, terms)
                        except (zipfile.BadZipFile, OSError, RuntimeError, EOFError):
                            _mark_unscanned(unscanned, rel)
                            break
                        if label:
                            hits.append((rel, label))
                            break
            except (zipfile.BadZipFile, OSError, RuntimeError, EOFError):
                _mark_unscanned(unscanned, rel)
                continue
        elif suffix in TEXT_SUFFIXES or not suffix:
            try:
                label = _hit_label(path.read_bytes().decode("utf-8"), terms)
            except (OSError, UnicodeDecodeError):
                _mark_unscanned(unscanned, rel)
                continue
            if label:
                hits.append((rel, label))
        else:
            # Unfamiliar suffix is not the same as binary. Try a STRICT decode:
            # if it succeeds the file is genuinely text and is scanned normally
            # (a .priv fixture is plain ASCII). Only a file that will not decode
            # is left unscanned -- guessing at its bytes invents characters.
            try:
                label = _hit_label(path.read_bytes().decode("utf-8"), terms)
            except UnicodeDecodeError:
                _mark_unscanned(unscanned, rel)
                continue
            except OSError:
                _mark_unscanned(unscanned, rel)
                continue
            if label:
                hits.append((rel, label))

    return hits, unscanned


def main() -> int:
    try:
        hits, unscanned = scan()
    except bb.BuildError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if unscanned:
        for rel in sorted(set(unscanned)):
            print(f"  UNSCANNED FILE: {rel}", file=sys.stderr)
        print(f"FAIL: {len(set(unscanned))} tracked file(s) could not be reliably "
              "scanned; add only reviewed benign paths to "
              "APPROVED_UNSCANNED_FILES", file=sys.stderr)
    if hits:
        for rel, label in sorted(set(hits)):
            print(f"  TERM HIT [{label}]: {rel}", file=sys.stderr)
        print(f"FAIL: {len(set(hits))} tracked file(s) contain restricted terms",
              file=sys.stderr)
    if unscanned or hits:
        return 1
    print(f"  ✓ {len(tracked_files())} tracked files scanned — no restricted terms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
