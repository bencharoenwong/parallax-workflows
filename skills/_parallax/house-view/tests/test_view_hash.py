#!/usr/bin/env python3
"""Regression test: view_hash canonicalization must be byte-stable.

Loads the pinned fixture and asserts that the reference implementation from
schema.yaml produces the expected sha256 digest. Run:

    python3 tests/test_view_hash.py

from `skills/_parallax/house-view/`. Exits nonzero on mismatch — wire into
CI or a pre-commit hook.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import yaml


def _strip_empty(obj):
    """Recursively strip None / 0 / "" / [] / {} bottom-up."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            v = _strip_empty(v)
            if v is None or v == 0 or v == "" or v == [] or v == {}:
                continue
            out[k] = v
        return out
    if isinstance(obj, list):
        return [_strip_empty(x) for x in obj if x not in (None, 0, "", [], {})]
    return obj


def compute_view_hash(view: dict) -> tuple[str, str]:
    """Return (canonical_yaml_body, sha256_hex) per schema.yaml §view_hash."""
    body = {
        "tilts": _strip_empty(view.get("tilts", {})),
        "excludes": view.get("excludes", []) or [],
    }
    canonical = yaml.safe_dump(
        body,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
        width=1_000_000,
        indent=2,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return canonical, digest


def compute_prose_body_hash(prose_text: str) -> str:
    """sha256 of prose.md body (frontmatter stripped). Mirrors schema.yaml spec."""
    data = prose_text.encode("utf-8")
    marker = b"---\n"
    if data.startswith(marker):
        end = data.find(marker, len(marker))
        if end != -1:
            data = data[end + len(marker):]
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    fixture_path = Path(__file__).parent / "fixtures" / "view_hash_fixture.yaml"
    fixture = yaml.safe_load(fixture_path.read_text())

    expected = fixture.pop("expected_view_hash")
    # Fixture is itself a view; drop the assertion key before hashing.
    view = {"tilts": fixture.get("tilts", {}), "excludes": fixture.get("excludes", [])}
    canonical, digest = compute_view_hash(view)

    print("--- canonical body ---")
    print(canonical, end="")
    print("--- sha256 ---")
    print(f"expected: {expected}")
    print(f"actual:   {digest}")

    if digest != expected:
        print("FAIL: view_hash canonicalization drifted.")
        print("      If this change is intentional, bump audit.jsonl schema_version")
        print("      and update fixtures/view_hash_fixture.yaml.")
        return 1

    # Secondary: prose_body_hash shape check on a minimal example.
    sample_prose = "---\npaired_yaml_hash: abc\nview_id: x\nversion_id: y\n---\nhello body\n"
    pbh = compute_prose_body_hash(sample_prose)
    expected_pbh = hashlib.sha256(b"hello body\n").hexdigest()
    if pbh != expected_pbh:
        print(f"FAIL: prose_body_hash mismatch (got {pbh}, expected {expected_pbh})")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
