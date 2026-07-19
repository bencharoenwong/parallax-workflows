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

# build_bundle.py defines the term list, so it necessarily contains the terms.
SELF_EXEMPT = {
    "skills/_parallax/scripts/build_bundle.py",
    "skills/_parallax/scripts/scan_tracked_terms.py",
}


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
    out = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files"],
                         capture_output=True, text=True, check=True).stdout
    return sorted(p for p in out.splitlines() if p.strip())


def scan() -> tuple[list[tuple[str, str]], list[str]]:
    """Returns (hits, unscanned). Each hit is (path, masked_term_label)."""
    terms = scoped_terms()
    hits: list[tuple[str, str]] = []
    unscanned: list[str] = []

    for rel in tracked_files():
        if rel in SELF_EXEMPT:
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        bodies: list[str] = []

        if suffix in ARCHIVE_SUFFIXES:
            try:
                zf = zipfile.ZipFile(path)
                bodies = [zf.read(n).decode("utf-8", errors="replace")
                          for n in zf.namelist()]
            except (zipfile.BadZipFile, OSError):
                unscanned.append(rel)
                continue
        elif suffix in TEXT_SUFFIXES or not suffix:
            try:
                bodies = [path.read_bytes().decode("utf-8", errors="replace")]
            except OSError:
                unscanned.append(rel)
                continue
        else:
            # Unfamiliar suffix is not the same as binary. Try a STRICT decode:
            # if it succeeds the file is genuinely text and is scanned normally
            # (a .priv fixture is plain ASCII). Only a file that will not decode
            # is left unscanned -- guessing at its bytes invents characters.
            try:
                bodies = [path.read_bytes().decode("utf-8")]
            except UnicodeDecodeError:
                unscanned.append(rel)
                continue
            except OSError:
                unscanned.append(rel)
                continue

        for body in bodies:
            hay = _mask_allowlisted(body)
            for term in terms:
                if term.lower() in hay:
                    # Never print the term itself -- this output can land in logs.
                    label = ("branding" if term in bb._BRANDING_CANARIES
                             else "restricted")
                    hits.append((rel, label))
                    break

    return hits, unscanned


def main() -> int:
    try:
        hits, unscanned = scan()
    except bb.BuildError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if unscanned:
        print(f"  note: {len(unscanned)} binary file(s) not scanned "
              f"(no reliable text extraction)")
    if hits:
        for rel, label in sorted(set(hits)):
            print(f"  TERM HIT [{label}]: {rel}", file=sys.stderr)
        print(f"FAIL: {len(set(hits))} tracked file(s) contain restricted terms",
              file=sys.stderr)
        return 1
    print(f"  ✓ {len(tracked_files())} tracked files scanned — no restricted terms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
