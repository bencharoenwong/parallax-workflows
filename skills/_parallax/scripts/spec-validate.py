#!/usr/bin/env python3
"""Validate skill directories against the agentskills.io specification.

Checks per skill dir:
  - SKILL.md exists with `---`-delimited YAML frontmatter that parses
  - frontmatter keys are a subset of the spec's allowed set
  - name: 1-64 chars, lowercase a-z0-9 + hyphens, no leading/trailing/
    consecutive hyphens, equals the parent directory name
  - description: non-empty string, <= 1024 chars
  - compatibility (optional): <= 500 chars
  - metadata (optional): flat string->string map
  - allowed-tools (optional): string
  - WARN (not fail) if SKILL.md exceeds 500 lines (spec recommendation)

Usage: spec-validate.py <skill_dir> [...]
Exit:  0 all pass, 1 any failure.
"""
import re
import sys
from pathlib import Path

import yaml

ALLOWED = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def validate(skill_dir):
    d = Path(skill_dir)
    md = d / "SKILL.md"
    errs, warns = [], []
    if not md.is_file():
        return [f"missing {md}"], warns
    text = md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return ["SKILL.md does not start with '---' frontmatter delimiter"], warns
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return ["unterminated frontmatter block"], warns
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        return [f"frontmatter is not valid YAML: {str(e).splitlines()[0]}"], warns
    if not isinstance(fm, dict):
        return ["frontmatter is not a mapping"], warns

    extra = set(fm) - ALLOWED
    if extra:
        errs.append(f"non-spec frontmatter keys: {sorted(extra)}")

    name = fm.get("name")
    if not isinstance(name, str) or not name:
        errs.append("missing/invalid 'name'")
    else:
        if not 1 <= len(name) <= 64:
            errs.append(f"name length {len(name)} outside 1-64")
        if not NAME_RE.match(name):
            errs.append(f"name {name!r} violates [a-z0-9-] / hyphen rules")
        if name != d.resolve().name:
            errs.append(f"name {name!r} != directory name {d.resolve().name!r}")

    desc = fm.get("description")
    if not isinstance(desc, str) or not desc.strip():
        errs.append("missing/invalid 'description'")
    elif len(desc) > 1024:
        errs.append(f"description {len(desc)} chars (> 1024)")

    comp = fm.get("compatibility")
    if comp is not None and (not isinstance(comp, str) or not 1 <= len(comp) <= 500):
        errs.append("'compatibility' must be a 1-500 char string")

    meta = fm.get("metadata")
    if meta is not None:
        if not isinstance(meta, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in meta.items()
        ):
            errs.append("'metadata' must be a flat string->string map")

    at = fm.get("allowed-tools")
    if at is not None and not isinstance(at, str):
        errs.append("'allowed-tools' must be a space-separated string")

    n_lines = text.count("\n") + 1
    if n_lines > 500:
        warns.append(f"SKILL.md is {n_lines} lines (spec recommends <= 500)")
    return errs, warns


def main(argv):
    dirs = [a for a in argv if Path(a).is_dir()]
    if not dirs:
        print("usage: spec-validate.py <skill_dir> [...]", file=sys.stderr)
        return 1
    failed = 0
    for sd in dirs:
        errs, warns = validate(sd)
        for w in warns:
            print(f"  WARN {sd}: {w}")
        for e in errs:
            print(f"  FAIL {sd}: {e}")
        if errs:
            failed += 1
    total = len(dirs)
    print(f"spec-validate: {total - failed}/{total} skill(s) pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
