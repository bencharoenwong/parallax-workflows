#!/usr/bin/env python3
"""host-primitive-lint.py — flag host-locked identifiers in skills/*/SKILL.md.

`parallax-conventions.md` §14 says a SKILL.md names host PRIMITIVES
(discover-tools, call-tool, ask-operator, run-shell, invoke-skill,
load-reference, write-artifact, read-config, fetch-url), never host tools.
This lint enforces the mechanical half of that rule: outside a
`<!-- host-note -->` … `<!-- /host-note -->` block, a SKILL.md must not
contain any of the identifiers in `HOST_IDENTIFIERS`.

Forward-only (per `skill-structure-conventions.md` → "Host portability"):
`LEGACY_ALLOWLIST` names the skill directories that were host-locked when the
rule landed (2026-09-05). It is EMPTY as of 2026-09-07 — the sweep finished and
every skill now names host primitives. Two rules make the list shrink and never
grow, and they keep working on an empty list:

  * a file NOT on the allowlist with a hit                → HOST-LOCKED, exit 1
  * a file ON the allowlist with zero hits                → STALE ALLOWLIST, exit 1
    (remove it from the list in the same PR that cleaned it)

`test_host_primitive_lint.py` pins the allowlist with an EQUALITY check against
its own literal, so shrinking the script without shrinking the test — or
re-adding a name — is a visible two-file edit, never a silent one.

Deliberately NOT linted: `/parallax-<name>` slash chaining. Routing lines such
as "use /parallax-deep-dive" are legitimate in every description and body, and
§14 treats the slash form as a host-lock only when it is the sole invocation
form — a semantic judgement this lint cannot make.

An opening `<!-- host-note -->` with no closing marker is itself a failure
(UNCLOSED HOST-NOTE): a silent match-to-EOF would hide every identifier after
it. Ordinary `<!-- … -->` comments are stripped before matching so that a
migration-audit comment naming a removed host tool cannot block allowlist
shrinkage.

Usage: python3 host-primitive-lint.py [skills_dir]
Exit:  0 clean, 1 any finding. Importable: `main(root) -> int`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HOST_IDENTIFIERS: dict[str, re.Pattern[str]] = {
    "ToolSearch": re.compile(r"\bToolSearch\b"),
    "AskUserQuestion": re.compile(r"\bAskUserQuestion\b"),
    "WebFetch": re.compile(r"\bWebFetch\b"),
    "mcp__ namespace literal": re.compile(r"\bmcp__"),
    "Write tool": re.compile(r"`Write`|\bWrite tool\b"),
    "Skill tool": re.compile(r"`Skill`|\bSkill tool\b"),
}

HOST_NOTE_OPEN = re.compile(r"<!--\s*host-note\s*-->")
# A span must not swallow a LATER opening tag: with a plain `.*?` an UNCLOSED block
# merges with the next properly-paired block, hiding every identifier between them
# and defeating the unclosed check that exists to catch exactly that.
HOST_NOTE_SPAN = re.compile(
    r"<!--\s*host-note\s*-->(?:(?!<!--\s*host-note\s*-->).)*?<!--\s*/host-note\s*-->",
    re.S,
)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)

# Skill directories that were host-locked on 2026-09-05. Shrinks only; now empty —
# every skill names host primitives and confines host identifiers to host-note blocks.
# Re-adding a name is a deliberate two-file edit (see test_host_primitive_lint.py).
LEGACY_ALLOWLIST: frozenset[str] = frozenset()


def _blank_span(match: re.Match[str]) -> str:
    """Replace a span with newlines only, so line numbers survive."""
    return "\n" * match.group(0).count("\n")


def scan_text(text: str) -> tuple[list[tuple[int, str]], bool]:
    """Return ([(line, identifier), ...], unclosed_host_note)."""
    stripped = HOST_NOTE_SPAN.sub(_blank_span, text)
    unclosed = bool(HOST_NOTE_OPEN.search(stripped))
    stripped = HTML_COMMENT.sub(_blank_span, stripped)
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(stripped.splitlines(), 1):
        for label, pattern in HOST_IDENTIFIERS.items():
            if pattern.search(line):
                hits.append((lineno, label))
    return hits, unclosed


def main(root: Path | None = None, out=sys.stderr) -> int:
    skills_dir = Path(root).resolve() if root else Path(__file__).resolve().parent.parent.parent
    fail = 0
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        name = skill_md.parent.name
        rel = skill_md.relative_to(skills_dir)
        hits, unclosed = scan_text(skill_md.read_text(encoding="utf-8"))
        if unclosed:
            print(f"  ✗ UNCLOSED HOST-NOTE: {rel}", file=out)
            fail = 1
        allowlisted = name in LEGACY_ALLOWLIST
        if hits and not allowlisted:
            for lineno, label in hits:
                print(f"  ✗ HOST-LOCKED: {rel}:{lineno}: {label}", file=out)
            fail = 1
        if allowlisted and not hits:
            print(f"  ✗ STALE ALLOWLIST: {name} has no host identifiers — remove it from LEGACY_ALLOWLIST", file=out)
            fail = 1
    if fail == 0:
        print("  ✓ no host-locked identifiers outside host-note blocks in non-legacy skills", file=out)
    return fail


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
