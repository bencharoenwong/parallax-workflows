#!/usr/bin/env python3
"""Normalize SKILL.md frontmatter to the agentskills.io spec.

Skills ported from a Claude Code skill library may carry client-convention
frontmatter fields that the spec (and spec-validate.py) rejects. This script
rewrites SKILL.md in place to the spec-clean form:

  - ``negative-triggers`` (list)  -> items moved into a ``## When not to use``
    body section. Created after the H1 if absent; items not already present
    are appended if the section exists. Content is never silently dropped.
  - ``user-invocable``, ``argument-hint`` -> removed (client-specific; the
    spec equivalent of routing hints belongs in ``description``).

Spec fields (name, description, license, compatibility, metadata,
allowed-tools) pass through byte-identical. Idempotent: a spec-clean file is
left untouched and not reported.

Usage: spec-normalize.py <skill_dir> [...]
Exit:  0 (lists rewritten files), 2 on malformed frontmatter.
"""
import re
import sys
from pathlib import Path

DROP_FIELDS = {"user-invocable", "argument-hint"}
FOLD_FIELD = "negative-triggers"
SECTION_RE = re.compile(r"^##\s+when not to use\s*$", re.IGNORECASE)
KEY_RE = re.compile(r"^([A-Za-z][\w\-]*):(.*)$")
ITEM_RE = re.compile(r"^\s*-\s+(.*\S)\s*$")


def split_frontmatter(text):
    """Return (fm_lines, body_lines) or None if no valid frontmatter block."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], lines[i + 1:]
    return None


def group_fields(fm_lines):
    """Group frontmatter lines into ordered (key, [lines]) blocks."""
    blocks, cur = [], None
    for ln in fm_lines:
        m = KEY_RE.match(ln)
        if m:
            cur = [m.group(1), [ln]]
            blocks.append(cur)
        elif cur is not None:
            cur[1].append(ln)
        else:  # leading comment/blank before first key — keep verbatim
            blocks.append([None, [ln]])
    return blocks


def fold_into_section(body_lines, items):
    """Insert/extend a '## When not to use' section with bullet items."""
    bullets = ["- %s\n" % it for it in items]
    for i, ln in enumerate(body_lines):
        if SECTION_RE.match(ln.strip()):
            # find end of this section (next heading or EOF)
            j = i + 1
            while j < len(body_lines) and not body_lines[j].lstrip().startswith("#"):
                j += 1
            existing = "".join(body_lines[i:j])
            new = [b for b in bullets if b.strip() not in
                   {l.strip() for l in existing.splitlines()}]
            # append before trailing blank lines of the section
            k = j
            while k > i + 1 and not body_lines[k - 1].strip():
                k -= 1
            return body_lines[:k] + new + body_lines[k:]
    # no section: insert after the first H1 line (and its trailing blank), else at top
    section = ["\n", "## When not to use\n", "\n"] + bullets
    for i, ln in enumerate(body_lines):
        if ln.startswith("# "):
            return body_lines[:i + 1] + section + body_lines[i + 1:]
    return section + ["\n"] + body_lines


def normalize_text(text):
    """Return spec-clean text, or None if frontmatter is malformed."""
    parts = split_frontmatter(text)
    if parts is None:
        return None
    fm_lines, body_lines = parts
    blocks = group_fields(fm_lines)
    items, out_fm, changed = [], [], False
    for key, lns in blocks:
        if key in DROP_FIELDS:
            changed = True
        elif key == FOLD_FIELD:
            changed = True
            for ln in lns[1:]:
                m = ITEM_RE.match(ln)
                if m:
                    items.append(m.group(1))
        else:
            out_fm.extend(lns)
    if not changed:
        return text
    if items:
        body_lines = fold_into_section(body_lines, items)
    return "---\n" + "".join(out_fm) + "---\n" + "".join(body_lines)


def main(argv):
    dirs = [Path(a) for a in argv if Path(a).is_dir()]
    if not dirs:
        print("usage: spec-normalize.py <skill_dir> [...]", file=sys.stderr)
        return 2
    for d in dirs:
        md = d / "SKILL.md"
        if not md.is_file():
            continue
        text = md.read_text(encoding="utf-8")
        new = normalize_text(text)
        if new is None:
            print("  FAIL %s: malformed frontmatter (run spec-validate.py)" % md,
                  file=sys.stderr)
            return 2
        if new != text:
            md.write_text(new, encoding="utf-8")
            print("  normalized %s" % md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
