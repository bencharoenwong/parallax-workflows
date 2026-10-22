#!/usr/bin/env python3
"""authority-header-lint.py — every shared `.md` under skills/_parallax/ declares its kind.

`skill-structure-conventions.md` → "Authority header": directly under the H1,
within the first six non-blank lines, three HTML comments in this order:

    <!-- authority: contract | registry | observation -->
    <!-- verified: YYYY-MM-DD -->
    <!-- overrides: ... -->

`contract` binds. `registry` is a list tests reconcile against code.
`observation` is dated field notes — live wins. The date is required for every
kind so an agent never has to guess how old a table is.

Scope: tracked `*.md` under skills/_parallax/, excluding any path segment named
`tests` or `profiles` (frontmatter-led data records; their contract is
`profile-schema.md`) and dot-directories. Discovery uses `git ls-files` when a
repository is present so local scratch markdown cannot fail the lint, and
falls back to a directory walk otherwise.

Usage: python3 authority-header-lint.py [skills_dir]
Exit:  0 clean, 1 any finding. Importable: `main(root) -> int`.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KINDS = ("contract", "registry", "observation")
EXCLUDED_SEGMENTS = {"tests", "profiles"}
HEADER_WINDOW = 6  # non-blank lines after the H1 in which the header must sit

AUTHORITY_RE = re.compile(r"^<!--\s*authority:\s*(\w+)\s*-->$")
VERIFIED_RE = re.compile(r"^<!--\s*verified:\s*(\d{4}-\d{2}-\d{2})\s*-->$")
OVERRIDES_RE = re.compile(r"^<!--\s*overrides:\s*(.+?)\s*-->$")


def _excluded(rel: Path) -> bool:
    return any(part in EXCLUDED_SEGMENTS or part.startswith(".") for part in rel.parts)


def scoped_files(skills_dir: Path) -> list[Path]:
    shared = skills_dir / "_parallax"
    try:
        out = subprocess.run(
            ["git", "-C", str(skills_dir), "ls-files", "--", "_parallax"],
            capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        candidates = [skills_dir / p for p in out if p.endswith(".md")]
    except (subprocess.CalledProcessError, FileNotFoundError):
        candidates = list(shared.rglob("*.md"))
    return sorted(p for p in candidates if not _excluded(p.relative_to(shared)))


def check_text(text: str) -> list[str]:
    """Return a list of problems for one file's text (empty when clean)."""
    lines = text.splitlines()
    h1 = next((i for i, line in enumerate(lines) if line.startswith("# ")), None)
    if h1 is None:
        return ["no H1 heading"]
    window = [line.strip() for line in lines[h1 + 1:] if line.strip()][:HEADER_WINDOW]
    problems: list[str] = []
    idx = {}
    for name, rx in (("authority", AUTHORITY_RE), ("verified", VERIFIED_RE), ("overrides", OVERRIDES_RE)):
        for i, line in enumerate(window):
            m = rx.match(line)
            if m:
                idx[name] = (i, m.group(1))
                break
        else:
            problems.append(f"missing or malformed `{name}` header line within {HEADER_WINDOW} lines of the H1")
    if problems:
        return problems
    if not (idx["authority"][0] < idx["verified"][0] < idx["overrides"][0]):
        problems.append("header lines out of order (authority, verified, overrides)")
    if idx["authority"][1] not in KINDS:
        problems.append(f"authority `{idx['authority'][1]}` is not one of {KINDS}")
    try:
        d = date.fromisoformat(idx["verified"][1])
        if d > latest_local_date():
            problems.append("verified date is in the future")
    except ValueError:
        problems.append("verified date is not a real calendar date")
    return problems


def latest_local_date(now: datetime | None = None) -> date:
    """The most advanced calendar date anywhere on earth (UTC+14). A header stamped
    with today's local date must never read as future, whatever zone stamped it."""
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(hours=14)).date()


def main(root: Path | None = None, out=sys.stderr) -> int:
    skills_dir = Path(root).resolve() if root else Path(__file__).resolve().parent.parent.parent
    fail = 0
    for path in scoped_files(skills_dir):
        for problem in check_text(path.read_text(encoding="utf-8")):
            print(f"  ✗ AUTHORITY HEADER: {path.relative_to(skills_dir)}: {problem}", file=out)
            fail = 1
    if fail == 0:
        print("  ✓ every shared _parallax/*.md carries an authority header", file=out)
    return fail


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
