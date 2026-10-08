"""Reader for `_parallax/manifest.json` — the single source for per-skill metadata.

The manifest replaces five hand-maintained literals that had to be edited in
lockstep: `PLUGIN_SKILLS`, `WEB_SKILLS`, `WEB_DESCRIPTIONS`, and
`RESOLUTION_EXEMPT_DOCS` (all build_bundle.py) plus `_NINE_TWO_EXEMPT_SKILLS`
(the white-label test). Every consumer calls a function here instead of
carrying its own copy.

`render_gate.py`'s `SKILL_ANCHORS` is the deliberate exception: it keeps its
own literal rather than being replaced, and is reconciled against this reader
by a test. The gate is the last step of every skill on every host and has no
other file dependency; a missing manifest there would fail every operator's
final output, whereas a missing manifest at build time fails only a
developer's terminal. Mechanical trust is the same either way, because the
equality test fails on any drift. See DECISIONS.md 2026-09-07.

Pure stdlib. Values are cached after the first read; call `reload()` in a test
that rewrites the file.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"

# Standalone .skill tiers built by skills/build-skills.sh: `release` builds by
# default, `beta` and `held` only when named (with a warning). `held` means
# awaiting native-speaker review; such a package must not be distributed.
STANDALONE_TIERS = ("release", "beta", "held")

# claude.ai truncates skill descriptions past this length.
WEB_DESCRIPTION_MAX = 200

# Fixed roster for the concierge welcome flow. Order is the display order.
ROLE_IDS = ("fund-manager", "rm", "rm-support", "research-analyst",
            "wealth-advisor", "individual-investor", "integrator")
INPUT_KINDS = ("ticker", "holdings")


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
        if row.get("standalone", "release") not in STANDALONE_TIERS:
            raise ValueError(
                f"{MANIFEST_PATH}: {name} standalone must be one of {STANDALONE_TIERS}"
            )
        if ("anchors" in row) != ("anchors_key" in row):
            raise ValueError(
                f"{MANIFEST_PATH}: {name} must carry anchors and anchors_key together"
            )
    roles = data.get("roles", [])
    if not isinstance(roles, list) or not all(isinstance(r, dict) for r in roles):
        raise ValueError(f"{MANIFEST_PATH}: roles must be a list of objects")
    ids = [r.get("id") for r in roles]
    if tuple(ids) != ROLE_IDS:
        raise ValueError(f"{MANIFEST_PATH}: roles must be exactly {ROLE_IDS}")
    for r in roles:
        for field in ("label", "description"):
            if not isinstance(r.get(field), str) or not r[field].strip():
                raise ValueError(f"{MANIFEST_PATH}: role {r['id']} needs a non-empty {field}")
    seen: dict[tuple[str, int], str] = {}
    for name, row in data["skills"].items():
        starts = row.get("starts", {})
        if not isinstance(starts, dict):
            raise ValueError(f"{MANIFEST_PATH}: {name} starts must be an object")
        for role, entry in starts.items():
            if role not in ROLE_IDS:
                raise ValueError(f"{MANIFEST_PATH}: {name} starts unknown role {role}")
            if not isinstance(entry, dict):
                raise ValueError(f"{MANIFEST_PATH}: {name} {role} start must be an object")
            rank, kind = entry.get("rank"), entry.get("input")
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                raise ValueError(f"{MANIFEST_PATH}: {name} {role} rank must be a positive integer")
            if kind not in INPUT_KINDS:
                raise ValueError(f"{MANIFEST_PATH}: {name} {role} input must be one of {INPUT_KINDS}")
            if (role, rank) in seen:
                raise ValueError(f"{MANIFEST_PATH}: {role} rank {rank} used by {seen[(role, rank)]} and {name}")
            seen[(role, rank)] = name


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


def roles() -> list[dict]:
    """The fixed role roster for the concierge welcome flow, in display order."""
    return [dict(r) for r in _data()["roles"]]


def starts_for(role: str, available: set[str]) -> list[tuple[str, str]]:
    """Up to 3 (skill, input kind) for a role, in rank order, among the
    skills a distribution ships. The first is the first run."""
    ranked = sorted(
        (row["starts"][role]["rank"], name, row["starts"][role]["input"])
        for name, row in _data()["skills"].items()
        if role in row.get("starts", {}) and name in available)
    return [(name, kind) for _, name, kind in ranked][:3]


def exempt_docs() -> set[str]:
    """Bundled docs exempt from build_bundle's reference-resolution check."""
    return set(_data()["exempt_docs"])


def standalone_skills(tier: str) -> list[str]:
    """Skill dirs packaged as standalone .skill files at the given tier. Sorted."""
    if tier not in STANDALONE_TIERS:
        raise ValueError(f"unknown standalone tier: {tier}")
    return sorted(n for n, r in _data()["skills"].items() if r.get("standalone") == tier)


if __name__ == "__main__":
    # `python3 skill_manifest.py standalone <tier>` prints space-separated names
    # for build-skills.sh (bash 3.2 has no JSON parser).
    import sys

    if len(sys.argv) != 3 or sys.argv[1] != "standalone":
        sys.exit("usage: skill_manifest.py standalone {release|beta|held}")
    print(" ".join(standalone_skills(sys.argv[2])))
