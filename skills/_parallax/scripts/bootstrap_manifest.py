#!/usr/bin/env python3
"""Regenerate `_parallax/manifest.json` from the live Python constants.

The manifest is the single source for per-skill distribution metadata. It is
GENERATED, never hand-edited: the anchor patterns are regexes whose backslashes
double under JSON escaping, and hand-editing them is how a mirror silently rots.

Run this only when a constant below is still the authority for a field — that is,
during the flip itself, or when adding a skill before the reader is wired up.
Afterwards the manifest is the authority and this script is a one-way check:
re-running it must produce a byte-identical file.

Usage: python3 bootstrap_manifest.py [--check]
       --check exits 1 if the regenerated manifest differs from the tracked one.
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
VERIFIED = "2026-09-07"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build() -> dict:
    bb = _load("bb", SHARED / "scripts" / "build_bundle.py")
    rg = _load("rg", SHARED / "render_gate.py")
    ip = _load(
        "ip", SHARED / "white-label" / "tests" / "test_integration_pattern_referenced.py"
    )

    plugin = set(bb.PLUGIN_SKILLS)
    web = set(bb.WEB_SKILLS)
    anchors = rg.SKILL_ANCHORS
    exempt = set(ip._NINE_TWO_EXEMPT_SKILLS)

    dirs = sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))
    skills: dict[str, dict] = {}
    for name in dirs:
        key = name.removeprefix("parallax-")
        row: dict = {"plugin": name in plugin, "web": name in web}
        if name in web:
            row["web_description"] = bb.WEB_DESCRIPTIONS[name]
        if key in anchors:
            row["anchors_key"] = key
            row["anchors"] = list(anchors[key])
        if name in exempt:
            row["nine_two_exempt"] = True
        skills[name] = row

    # Every constant entry must have landed on a real skill directory.
    for label, want in (
        ("PLUGIN_SKILLS", plugin), ("WEB_SKILLS", web), ("_NINE_TWO_EXEMPT_SKILLS", exempt),
    ):
        stray = want - set(dirs)
        if stray:
            raise SystemExit(f"{label} names non-existent skill dirs: {sorted(stray)}")
    stray_anchor = set(anchors) - {n.removeprefix("parallax-") for n in dirs}
    if stray_anchor:
        raise SystemExit(f"SKILL_ANCHORS names non-existent skills: {sorted(stray_anchor)}")

    return {
        "_authority": {
            "kind": "registry",
            "verified": VERIFIED,
            "overrides": (
                "PLUGIN_SKILLS / WEB_SKILLS / WEB_DESCRIPTIONS / SKILL_ANCHORS / "
                "_NINE_TWO_EXEMPT_SKILLS literals"
            ),
            "generated_by": "scripts/bootstrap_manifest.py — do not hand-edit",
        },
        "skills": skills,
        "exempt_docs": sorted(_load("bb2", SHARED / "scripts" / "build_bundle.py").RESOLUTION_EXEMPT_DOCS),
    }


def render(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = render(build())
    if args.check:
        if not MANIFEST.exists():
            print(f"  ✗ {MANIFEST} missing", file=sys.stderr)
            return 1
        if MANIFEST.read_text(encoding="utf-8") != text:
            print("  ✗ manifest.json is stale — rerun bootstrap_manifest.py", file=sys.stderr)
            return 1
        print("  ✓ manifest.json matches the live constants", file=sys.stderr)
        return 0
    MANIFEST.write_text(text, encoding="utf-8")
    print(f"  ✓ {MANIFEST.relative_to(SKILLS.parent)} ({len(build()['skills'])} skills)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
