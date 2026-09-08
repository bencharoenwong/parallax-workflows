#!/usr/bin/env python3
"""Maintain `_parallax/manifest.json` — add missing rows, refresh gate anchors.

The manifest is the AUTHORITY for per-skill distribution metadata. Editorial
fields (`plugin`, `web`, `web_description`, `nine_two_exempt`, `exempt_docs`) are
decisions, not derived data: this script preserves whatever the manifest already
says about them and never overwrites them from a consumer. Overwriting would be
circular, because `build_bundle.py` reads those fields FROM here.

Two things ARE derived, and `--check` asserts exactly those two:

  * every `skills/*/SKILL.md` directory has a row (and no row names a dead dir);
  * `anchors` matches `render_gate.py`'s `SKILL_ANCHORS`, which deliberately
    keeps its literal (see `skill_manifest.py` and DECISIONS.md 2026-09-07).
    Anchors are regexes whose backslashes double under JSON escaping — that is
    why they are copied by this script and never typed by hand.

A new skill gets a row with `plugin`/`web` false; set them here by hand, on
purpose. Editing a description by hand is correct and this script preserves it.

Usage: python3 bootstrap_manifest.py [--check]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parent.parent          # skills/_parallax
SKILLS = SHARED.parent                                    # skills
MANIFEST = SHARED / "manifest.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build() -> dict:
    """Current manifest, with rows and anchors reconciled against the tree."""
    current = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows: dict = current.get("skills", {})
    anchors = _load("rg_boot", SHARED / "render_gate.py").SKILL_ANCHORS

    dirs = sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))
    stray = set(anchors) - {n.removeprefix("parallax-") for n in dirs}
    if stray:
        raise SystemExit(f"SKILL_ANCHORS names non-existent skills: {sorted(stray)}")

    out: dict[str, dict] = {}
    for name in dirs:
        row = dict(rows.get(name, {}))          # preserve editorial fields verbatim
        row.setdefault("plugin", False)
        row.setdefault("web", False)
        key = name.removeprefix("parallax-")
        if key in anchors:                       # derived: refresh from the gate
            row["anchors_key"] = key
            row["anchors"] = list(anchors[key])
        else:
            row.pop("anchors_key", None)
            row.pop("anchors", None)
        # stable field order so the diff of a real change stays readable
        order = ("plugin", "web", "web_description", "anchors_key", "anchors",
                 "nine_two_exempt")
        out[name] = {k: row[k] for k in order if k in row}

    authority = dict(current.get("_authority", {}))
    authority.update(kind="registry", generated_by="scripts/bootstrap_manifest.py")
    return {
        "_authority": authority,
        "skills": out,
        "exempt_docs": sorted(current.get("exempt_docs", [])),
    }


def render(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if rows or anchors are out of sync (not editorial fields)")
    args = ap.parse_args(argv)
    if not MANIFEST.exists():
        print(f"  ✗ {MANIFEST} missing", file=sys.stderr)
        return 1
    text = render(build())
    if args.check:
        if MANIFEST.read_text(encoding="utf-8") != text:
            print("  ✗ manifest rows/anchors are stale — rerun bootstrap_manifest.py",
                  file=sys.stderr)
            return 1
        print("  ✓ manifest rows and gate anchors are in sync", file=sys.stderr)
        return 0
    MANIFEST.write_text(text, encoding="utf-8")
    print(f"  ✓ {MANIFEST.relative_to(SKILLS.parent)} ({len(text.splitlines())} lines)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
