#!/usr/bin/env python3
"""Generate the README role list and distribution table from the skill manifest."""
from __future__ import annotations

import argparse
import re
import sys

import build_bundle as bb


def sections() -> dict[str, str]:
    sm = bb.skill_manifest
    catalog = ["| Workflow | Distribution |", "|---|---|"]
    for name, row in sorted(sm.skills().items()):
        surfaces = []
        if row.get("plugin"):
            surfaces.append("Plugin")
        if row.get("web") or row.get("standalone") == "release":
            surfaces.append("Skill upload")
        if not surfaces:
            tier = row.get("standalone")
            surfaces.append("Held: native review pending" if tier == "held" else
                            "Private beta" if tier == "beta" else "Full clone only")
        catalog.append(f"| [{name}](skills/{name}/SKILL.md) | {', '.join(surfaces)} |")
    return {"who-for": bb.render_who_for().rstrip("\n"), "distributions": "\n".join(catalog)}


def render(text: str) -> str:
    for name, body in sections().items():
        start, end = f"<!-- {name}:begin -->", f"<!-- {name}:end -->"
        if text.count(start) != 1 or text.count(end) != 1:
            raise bb.BuildError(f"README requires one {name} marker pair")
        pattern = re.escape(start) + r".*?" + re.escape(end)
        text, n = re.subn(pattern, lambda m: f"{start}\n{body}\n{end}", text, flags=re.S)
        if n != 1:
            raise bb.BuildError(f"README {name} markers are out of order")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = bb.REPO_ROOT / "README.md"
    text = path.read_text()
    updated = render(text)
    if args.check:
        if updated != text:
            print("README distribution tables are stale; run distribution_docs.py", file=sys.stderr)
            return 1
    else:
        path.write_text(updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
