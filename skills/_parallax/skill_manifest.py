"""Reader for `_parallax/manifest.json` — the single source for per-skill metadata.

The manifest replaces five hand-maintained literals that had to be edited in
lockstep: `PLUGIN_SKILLS`, `WEB_SKILLS`, `WEB_DESCRIPTIONS` (build_bundle.py),
`SKILL_ANCHORS` (render_gate.py) and `_NINE_TWO_EXEMPT_SKILLS` (the white-label
test). Every consumer calls a function here instead of carrying its own copy.

`render_gate.py` is the deliberate exception: it keeps its literal and is
reconciled against this reader by a test. The gate is the last step of every
skill on every host and has no other file dependency; a missing manifest there
would fail every operator's final output, whereas a missing manifest at build
time fails only a developer's terminal. Mechanical trust is the same either way,
because the equality test fails on any drift. See DECISIONS.md 2026-09-07.

Pure stdlib. Values are cached after the first read; call `reload()` in a test
that rewrites the file.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"

# claude.ai truncates skill descriptions past this length.
WEB_DESCRIPTION_MAX = 200


@lru_cache(maxsize=1)
def _data() -> dict:
    try:
        raw = MANIFEST_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - operator-facing path
        raise FileNotFoundError(
            f"{MANIFEST_PATH} is missing. It is generated: run "
            f"`python3 skills/_parallax/scripts/bootstrap_manifest.py`."
        ) from exc
    data = json.loads(raw)
    _validate(data)
    return data


def _validate(data: dict) -> None:
    """Reject a manifest that cannot be trusted, rather than half-using it."""
    if not isinstance(data.get("skills"), dict) or not data["skills"]:
        raise ValueError(f"{MANIFEST_PATH}: 'skills' must be a non-empty object")
    for name, row in data["skills"].items():
        if not isinstance(row, dict):
            raise ValueError(f"{MANIFEST_PATH}: {name} row must be an object")
        if row.get("web"):
            desc = row.get("web_description")
            if not desc:
                raise ValueError(
                    f"{MANIFEST_PATH}: {name} has web=true but no web_description"
                )
            if len(desc) > WEB_DESCRIPTION_MAX:
                raise ValueError(
                    f"{MANIFEST_PATH}: {name} web_description is {len(desc)} chars, "
                    f"over the {WEB_DESCRIPTION_MAX}-char claude.ai cap"
                )
        if ("anchors" in row) != ("anchors_key" in row):
            raise ValueError(
                f"{MANIFEST_PATH}: {name} must carry anchors and anchors_key together"
            )


def reload() -> None:
    """Drop the cache. For tests that rewrite the manifest on disk."""
    _data.cache_clear()


def skills() -> dict[str, dict]:
    """The whole per-skill mapping, keyed by skill directory name."""
    return dict(_data()["skills"])


def plugin_skills() -> list[str]:
    """Skill dirs shipped in the Claude Code plugin bundle. Sorted; a list."""
    return sorted(n for n, r in _data()["skills"].items() if r.get("plugin"))


def web_skills() -> list[str]:
    """Skill dirs shipped in the claude.ai web build. Sorted; a list."""
    return sorted(n for n, r in _data()["skills"].items() if r.get("web"))


def web_descriptions() -> dict[str, str]:
    """Web-build descriptions, capped at WEB_DESCRIPTION_MAX by `_validate`."""
    return {
        n: r["web_description"]
        for n, r in _data()["skills"].items()
        if r.get("web")
    }


def skill_anchors() -> dict[str, list[str]]:
    """Render-gate anchors, keyed WITHOUT the `parallax-` prefix (the gate's keys)."""
    return {
        r["anchors_key"]: list(r["anchors"])
        for r in _data()["skills"].values()
        if "anchors" in r
    }


def nine_two_exempt() -> frozenset[str]:
    """Skill dirs exempt from the §9.2 disclosure reference check."""
    return frozenset(
        n for n, r in _data()["skills"].items() if r.get("nine_two_exempt")
    )


def exempt_docs() -> set[str]:
    """Bundled docs exempt from build_bundle's reference-resolution check."""
    return set(_data()["exempt_docs"])
