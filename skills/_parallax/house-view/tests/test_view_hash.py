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


def _is_empty(v):
    """Empty iff None / numeric zero / "" / [] / {}, AND not a bool.

    Bool guard is load-bearing: `False == 0` and `False in (..., 0, ...)` are
    both True in Python, so without the isinstance check booleans would be
    stripped despite schema.yaml explicitly excluding them.
    """
    if isinstance(v, bool):
        return False
    if v is None:
        return True
    if isinstance(v, (int, float)) and v == 0:
        return True
    return v == "" or v == [] or v == {}


def _strip_empty(obj):
    """Recursively strip empties bottom-up. Always recurse first, then decide."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            v = _strip_empty(v)
            if _is_empty(v):
                continue
            out[k] = v
        return out
    if isinstance(obj, list):
        result = []
        for x in obj:
            y = _strip_empty(x)
            if _is_empty(y):
                continue
            result.append(y)
        return result
    return obj


def compute_view_hash(view: dict) -> tuple[str, str]:
    """Return (canonical_yaml_body, sha256_hex) per schema.yaml §view_hash."""
    body = {
        "tilts": _strip_empty(view.get("tilts", {})),
        "excludes": _strip_empty(view.get("excludes", []) or []),
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
    """sha256 of prose.md body, frontmatter stripped, line endings normalized.

    Normalization rule (per schema.yaml §prose_body_hash step 2): CRLF → LF,
    then stray CR → LF. Mirrors what the writer side produces, so a reader on
    a CRLF-normalizing filesystem computes the same digest.
    """
    data = prose_text.encode("utf-8").replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    marker = b"---\n"
    if data.startswith(marker):
        end = data.find(marker, len(marker))
        if end != -1:
            data = data[end + len(marker):]
    return hashlib.sha256(data).hexdigest()


def _edge_cases() -> list[tuple[str, bool]]:
    """Return [(description, passed), ...] for strip + hash edge cases."""
    out = []

    # 1. False must NOT be stripped (bool guard).
    stripped = _strip_empty({"flag": False, "zero": 0})
    out.append(("bool False is preserved, int 0 is stripped", stripped == {"flag": False}))

    # 2. Nested dict that becomes empty via child strip is stripped from parent.
    stripped = _strip_empty({"a": {"b": 0}, "c": 1})
    out.append(("dict empty after child strip is dropped", stripped == {"c": 1}))

    # 3. Recursive list: a dict-element that becomes empty after strip is removed.
    stripped = _strip_empty([{"a": 0}, {"b": 1}])
    out.append(("list element empty after strip is dropped", stripped == [{"b": 1}]))

    # 4. excludes with a None entry is stripped.
    view = {"tilts": {"sectors": {"x": 1}}, "excludes": [None, "tobacco", ""]}
    body = {"tilts": _strip_empty(view["tilts"]), "excludes": _strip_empty(view["excludes"])}
    out.append(("excludes strips None and empty-string entries", body["excludes"] == ["tobacco"]))

    # 5. Float zero strips, but float nonzero doesn't.
    stripped = _strip_empty({"a": 0.0, "b": 0.5})
    out.append(("float 0.0 stripped; float 0.5 preserved", stripped == {"b": 0.5}))

    # 6. CRLF-normalized prose produces the same hash as LF prose.
    lf = "---\nk: v\n---\nhello body\n"
    crlf = "---\r\nk: v\r\n---\r\nhello body\r\n"
    out.append(("CRLF normalizes to LF for prose_body_hash",
                compute_prose_body_hash(lf) == compute_prose_body_hash(crlf)))

    # 7. Pure-body prose (no frontmatter) hashes the whole file.
    no_fm = "hello body\n"
    expected = hashlib.sha256(b"hello body\n").hexdigest()
    out.append(("prose without frontmatter hashes entire body",
                compute_prose_body_hash(no_fm) == expected))

    return out


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

    print("--- edge cases ---")
    failures = 0
    for desc, ok in _edge_cases():
        marker = "PASS" if ok else "FAIL"
        print(f"  {marker}  {desc}")
        if not ok:
            failures += 1
    if failures:
        print(f"FAIL: {failures} edge case(s) failed.")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
