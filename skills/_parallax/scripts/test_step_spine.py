"""Gate: every data-producing SKILL.md carries the canonical step spine.

`skill-structure-conventions.md` ("Canonical step spine") fixes the seven
Workflow headings and their order. A SKILL.md with a `## Workflow` section is
data-producing and must carry them; a router (concierge) or an interface spec
(house-view-diff) has no Workflow section and is out of scope by definition.

SPINE_PENDING is the forward-only list of Workflow-bearing skills not yet
migrated. It shrinks only: a pending skill that now carries Step 0 fails as
STALE, and a non-pending skill that lacks a heading fails as MISSING.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[2]

# Equality-pinned; edit deliberately when a skill is migrated.
SPINE_PENDING = frozenset({"parallax-rebalance"})

SPINE = (
    "### Step 0 — Pre-flight",
    "### Step 1 — Resolve inputs",
    "### Step 2 — Fetch (parallel batches)",
    "### Step 3 — Verify",
    "### Step 4 — Compute",
    "### Step 5 — ",
    "### Step 6 — ",
)
STEP5_LABELS = ("Compose", "Confirm")
STEP6_LABELS = ("Render", "Persist")


def workflow_skills() -> list[Path]:
    return sorted(
        p for p in SKILLS_DIR.glob("parallax-*/SKILL.md")
        if "\n## Workflow" in p.read_text(encoding="utf-8")
    )


def spine_errors(text: str) -> list[str]:
    errors: list[str] = []
    positions: list[int] = []
    for heading in SPINE:
        m = re.search("^" + re.escape(heading), text, re.M)
        if m is None:
            errors.append(f"MISSING: {heading.strip()}")
            continue
        positions.append(m.start())
    if positions != sorted(positions):
        errors.append("ORDER: spine headings out of order")
    m5 = re.search(r"^### Step 5 — (\w+)", text, re.M)
    if m5 and m5.group(1) not in STEP5_LABELS:
        errors.append(f"STEP5: label {m5.group(1)!r} not in {STEP5_LABELS}")
    m6 = re.search(r"^### Step 6 — (\w+)", text, re.M)
    if m6 and m6.group(1) not in STEP6_LABELS:
        errors.append(f"STEP6: label {m6.group(1)!r} not in {STEP6_LABELS}")
    return errors


@pytest.mark.parametrize("path", workflow_skills(), ids=lambda p: p.parent.name)
def test_workflow_skill_carries_the_spine(path: Path):
    name = path.parent.name
    text = path.read_text(encoding="utf-8")
    errors = spine_errors(text)
    if name in SPINE_PENDING:
        assert errors, f"STALE SPINE_PENDING: {name} is on the spine — remove it from SPINE_PENDING"
        return
    assert errors == [], f"{name}: {errors}"


def test_every_pending_name_is_a_real_workflow_skill():
    names = {p.parent.name for p in workflow_skills()}
    assert SPINE_PENDING <= names, SPINE_PENDING - names


def test_seeded_violations_are_named():
    planted = ("## Workflow\n\n### Step 1 — Resolve inputs\n### Step 0 — Pre-flight\n"
               "### Step 2 — Fetch (parallel batches)\n### Step 3 — Verify\n"
               "### Step 4 — Compute\n### Step 5 — Synthesis\n### Step 6 — Emit\n")
    errors = spine_errors(planted)
    assert "ORDER: spine headings out of order" in errors
    assert any(e.startswith("STEP5:") for e in errors)
    assert any(e.startswith("STEP6:") for e in errors)
    assert not any(e.startswith("MISSING") for e in errors)
