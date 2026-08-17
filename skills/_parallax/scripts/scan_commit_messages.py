#!/usr/bin/env python3
"""Scan outgoing commit MESSAGES for redaction vocabulary and restricted terms.

Commit messages are published with the push and are never rewritten afterwards.
They are also where the intent behind a cleanup gets written down: a message
saying a fixture was scrubbed of real values is an index into which commit to
diff, and a message containing a restricted term publishes that term forever
even if the file it described was fixed in the same push.

``scan_tracked_terms.py`` covers tracked FILES at HEAD. Nothing covered messages.

TWO RULE FAMILIES.

  redaction/*   Vocabulary that says "something was removed here" -- an
                admission, in public, that there was something to remove. A
                cleanup commit should say what it changed, not that it was a
                redaction. Rule ids name the stem, which is fine: the stems are
                ordinary English and live in this source file.
  canary/*      The tracked restricted-term list, shared with the file scan.
                Labelled branding/restricted exactly as the file scan labels
                them, and NEVER named.

OUTPUT IS SHAs AND RULE IDS ONLY. Not the matched text, not the line, not the
surrounding message, not an excerpt -- and not inside an exception message
either. This repo's own rule is that naming a term to prove its presence
publishes it, and that constraint binds a scanner's output as hard as it binds a
skill's. The SHA is enough: whoever needs the detail can read the message
locally, where reading it is not publishing it.

RANGE. ``origin/main..HEAD``, falling back to ``main..HEAD``. If neither base
ref resolves the scan FAILS CLOSED (exit 2) rather than reporting a clean scan
of nothing -- a silent pass is how a weakened gate ships.

Exit 0 clean, 1 on any hit, 2 when the range cannot be determined.
Run: python3 skills/_parallax/scripts/scan_commit_messages.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_bundle as bb  # noqa: E402
import scan_tracked_terms as st  # noqa: E402

REPO_ROOT = bb.REPO_ROOT

BASE_REFS = ("origin/main", "main")

# (rule id, pattern). Stems, not whole words: "redact" must catch "redacted" and
# "redaction". A leading (?<!\w) stops a stem matching mid-identifier.
REDACTION_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("redaction/redact", re.compile(r"(?<!\w)redact", re.I)),
    ("redaction/scrub", re.compile(r"(?<!\w)scrub", re.I)),
    # [sz], not a bare z: "sanitised" is the spelling half the world uses, and a
    # z-only stem passed it. Caught by the UK-spelling case in the test table.
    ("redaction/sanitize", re.compile(r"(?<!\w)saniti[sz]", re.I)),
    ("redaction/de-identify", re.compile(r"(?<!\w)de-?identif", re.I)),
    ("redaction/anonymize", re.compile(r"(?<!\w)anonymi[sz]", re.I)),
    ("redaction/obfuscate", re.compile(r"(?<!\w)obfuscat", re.I)),
    ("redaction/leak", re.compile(r"(?<!\w)leak", re.I)),
    ("redaction/real-subject",
     re.compile(r"(?<!\w)real\s+(issuer|ticker|company|companies|values)", re.I)),
    ("redaction/live-source",
     re.compile(r"(?<!\w)live\s+(capture|data|response|values)", re.I)),
]


class ScanError(RuntimeError):
    """Never carries matched text — only why the scan could not run."""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)


def resolve_range(repo: Path | None = None,
                  base_refs: tuple[str, ...] = BASE_REFS) -> str:
    """First base ref that resolves, as ``<base>..HEAD``."""
    root = REPO_ROOT if repo is None else repo
    for ref in base_refs:
        if _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode == 0:
            return f"{ref}..HEAD"
    raise ScanError(
        f"no base ref resolved (tried: {', '.join(base_refs)}) — cannot "
        f"determine which commits are outgoing; refusing to report a clean scan")


def read_commits(repo: Path | None = None,
                 rev_range: str | None = None) -> list[tuple[str, str]]:
    """Returns [(sha, message)]. NUL-separated records, because a commit message
    can contain anything a newline-separated format would be confused by."""
    root = REPO_ROOT if repo is None else repo
    span = resolve_range(root) if rev_range is None else rev_range
    result = _git(root, "log", "-z", "--format=%H%n%B", span)
    if result.returncode != 0:
        raise ScanError(f"git log failed for range {span!r}")
    commits = []
    for record in result.stdout.split("\0"):
        if not record.strip():
            continue
        sha, _, message = record.partition("\n")
        commits.append((sha.strip(), message))
    return commits


def rule_hits(message: str, terms: list[str] | None = None) -> list[str]:
    """Rule ids matched by one message, deduplicated and ordered.

    The return type is deliberately ``list[str]`` and not anything that could
    carry a span, an offset or a matched group — there is no code path from a
    match object to output."""
    hits = [rule for rule, pattern in REDACTION_RULES if pattern.search(message)]
    scoped = st.scoped_terms() if terms is None else terms
    label = st._hit_label(message, scoped)
    if label:
        hits.append(f"canary/{label}")
    return hits


def scan(repo: Path | None = None,
         rev_range: str | None = None,
         terms: list[str] | None = None) -> list[tuple[str, str]]:
    """Returns sorted [(sha, rule_id)]."""
    scoped = st.scoped_terms() if terms is None else terms
    findings = []
    for sha, message in read_commits(repo, rev_range):
        for rule in rule_hits(message, scoped):
            findings.append((sha, rule))
    return sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    """Scan the outgoing range. An explicit range may be passed as argv[0].

    The pre-push hook passes the range git actually reports on stdin. Without
    that the default `origin/main..HEAD` silently scans the WRONG commits when
    the pushed branch is not the checked-out one: `git push origin feature`
    from `main` scanned an empty range and reported clean while the push
    published unscanned commits. An explicit range closes that.
    """
    # Never read sys.argv here: called as a library (tests, other tooling)
    # that would pick up the HOST process's arguments — under pytest it made
    # main() try to use `-q` as a rev-range. The __main__ block passes argv.
    args = list(argv or [])
    try:
        rev_range = args[0] if args else resolve_range()
        findings = scan(rev_range=rev_range)
    except ScanError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    except bb.BuildError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if findings:
        for sha, rule in findings:
            print(f"  MESSAGE HIT [{rule}]: {sha[:12]}", file=sys.stderr)
        shas = {sha for sha, _ in findings}
        print(f"FAIL: {len(shas)} outgoing commit message(s) in {rev_range} match "
              "restricted vocabulary. Read the message locally (git show -s <sha>) "
              "— it is not reproduced here. Rewrite the message before pushing; "
              "a pushed message cannot be unpublished.", file=sys.stderr)
        return 1

    count = len(read_commits(rev_range=rev_range))
    print(f"  ✓ {count} outgoing commit message(s) in {rev_range} scanned — clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
