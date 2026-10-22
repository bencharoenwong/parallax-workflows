#!/usr/bin/env python3
"""section-ref-lint.py — flag dangling `<file>.md §N[.M]` cross-references.

Scans skills/**/*.md for references of the form `<name>.md §N` or `<name>.md §N.M`
and verifies the named file contains a matching heading. This is the class of
drift that produced the `loader.md §2.6` bug (the section never existed; the
numbering jumped §2 -> §3).

Scope: cross-file refs only — a bare intra-file `§N.M` is NOT checked, because
the repo carries ~870 of them and many legitimately point at other docs without
naming a `.md` file (disambiguating them produces too many false positives). The
cross-file `X.md §N` form is unambiguous and low-noise.

Findings:
  - section-missing      : the named .md exists but has no heading for that section
  - file-not-found       : the named .md is not under skills/ (likely a notes/ or
                           external doc — not JIT-loadable from a skill at runtime)

Exit 1 on any dangling ref, 0 if clean. Run from build-skills.sh (cwd skills/) or
standalone: python3 _parallax/scripts/section-ref-lint.py [skills_dir]
"""
import re
import sys
import pathlib

# Default to the skills/ dir this script lives under, regardless of cwd.
_default = pathlib.Path(__file__).resolve().parent.parent.parent
SKILLS = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else _default

# `<name>.md`, optional backtick, optional space, §, optional space, N or N.M (optional trailing letter, e.g. 3b)
REF_RE = re.compile(r"([A-Za-z][\w.-]*\.md)`?\s*§\s*(\d+(?:\.\d+)?[a-z]?)")
# heading line: optional indent (some headings nest inside list items), #'s, whitespace,
# optional §, the leading section token
HEAD_RE = re.compile(r"^\s*#{1,6}\s+§?\s*(\d+(?:\.\d+)?[a-z]?)\b")


def nearest_skill_md(path: pathlib.Path) -> list[pathlib.Path]:
    """A bare `SKILL.md §N` ref means the SKILL.md of the skill the file lives in."""
    d = path if path.is_dir() else path.parent
    while True:
        cand = d / "SKILL.md"
        if cand.exists():
            return [cand]
        if d == SKILLS or SKILLS not in d.parents:
            return []
        d = d.parent

# index: basename (lowercased) -> [paths]
index: dict[str, list[pathlib.Path]] = {}
for p in SKILLS.rglob("*.md"):
    index.setdefault(p.name.lower(), []).append(p)

_hcache: dict[pathlib.Path, set[str]] = {}


def headings(path: pathlib.Path) -> set[str]:
    if path not in _hcache:
        secs = set()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = HEAD_RE.match(line)
            if m:
                secs.add(m.group(1))
        _hcache[path] = secs
    return _hcache[path]


dangling = []
for p in SKILLS.rglob("*.md"):
    text = p.read_text(encoding="utf-8", errors="ignore")
    # Drop HTML comments before scanning — a `<!-- ... -->` audit-trail pointer is
    # hidden from the model and not a live reference. Preserve line numbers.
    text = re.sub(r"<!--.*?-->", lambda mm: "\n" * mm.group(0).count("\n"), text, flags=re.S)
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in REF_RE.finditer(line):
            fname, sec = m.group(1).lower(), m.group(2)
            targets = nearest_skill_md(p) if fname == "skill.md" else index.get(fname, [])
            if not targets:
                dangling.append((str(p.relative_to(SKILLS)), lineno, m.group(0), "file-not-found"))
            elif not any(sec in headings(t) for t in targets):
                dangling.append((str(p.relative_to(SKILLS)), lineno, m.group(0), "section-missing"))

for rel, ln, ref, why in sorted(set(dangling)):
    print(f"  ✗ SECTION-REF DANGLING: {rel}:{ln} -> {ref} ({why})", file=sys.stderr)

if dangling:
    print(f"\n{len(set(dangling))} dangling section-reference(s).", file=sys.stderr)
    sys.exit(1)
print("  ✓ all `<file>.md §N` cross-references resolve")
