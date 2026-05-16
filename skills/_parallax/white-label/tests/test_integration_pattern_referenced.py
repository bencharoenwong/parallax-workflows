"""
Drift gate for white-label integration pattern.

Scans every `skills/*/SKILL.md` for the sentinel comment:
    <!-- white-label: integration-pattern.md -->

For each SKILL.md that carries the sentinel, asserts the body also carries
a load directive — defined here as a `Load ... integration-pattern.md`
phrase (case-insensitive). The regex requires the sentinel and load
directive within the same document, not just any mention of the filename
in an unrelated context.

Tier 1 skills (client-review, due-diligence, deep-dive) inline the loader
snippet but still carry the sentinel and a body reference for uniformity.
The regex matches both inline and JIT-ref consumer patterns.

A consumer SKILL.md that wires white-label branding without one of these
two elements is the drift this test prevents:
  - Sentinel present, body reference missing  -> test FAIL
  - Body reference present, sentinel missing  -> NOT FAIL (the sentinel
    is the canonical marker; missing sentinel means the consumer opted
    out of the drift gate. This is acceptable for unwired skills.)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Locate the repo's skills directory.
# This file lives at skills/_parallax/white-label/tests/, so the skills
# root is three levels up.
# ---------------------------------------------------------------------------

_SKILLS_ROOT: Path = Path(__file__).resolve().parents[3]
SENTINEL_RE = re.compile(
    r"<!--\s*white-label:\s*integration-pattern\.md\s*-->", re.IGNORECASE
)
LOAD_DIRECTIVE_RE = re.compile(
    r"(?:load|jit-load|consume|apply)\b[^.\n]{0,200}?integration-pattern\.md",
    re.IGNORECASE,
)


def _collect_wired_skills() -> list[Path]:
    """Return every SKILL.md under skills/* that contains the sentinel."""
    wired: list[Path] = []
    for skill_md in sorted(_SKILLS_ROOT.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        if SENTINEL_RE.search(text):
            wired.append(skill_md)
    return wired


def test_skills_root_is_resolvable() -> None:
    """Smoke check: the skills root must exist and contain at least one SKILL.md."""
    assert _SKILLS_ROOT.is_dir(), f"skills root not found: {_SKILLS_ROOT}"
    skill_mds = list(_SKILLS_ROOT.glob("*/SKILL.md"))
    assert skill_mds, f"no SKILL.md files found under {_SKILLS_ROOT}"


def test_at_least_one_skill_is_wired() -> None:
    """Smoke check: at least one consumer carries the sentinel."""
    wired = _collect_wired_skills()
    assert wired, (
        "No SKILL.md carries the white-label sentinel comment. Either every "
        "wired skill lost its sentinel (drift) or this test is mis-rooted."
    )


@pytest.mark.parametrize("skill_md", _collect_wired_skills(), ids=lambda p: p.parent.name)
def test_wired_skill_references_integration_pattern(skill_md: Path) -> None:
    """Every sentinel-tagged SKILL.md must also carry a real load directive.

    Detects the drift case where a SKILL.md retains the sentinel but the
    body reference was deleted or never added — the runtime would silently
    fail to apply branding without this gate catching it at PR review.
    """
    text = skill_md.read_text(encoding="utf-8")
    match = LOAD_DIRECTIVE_RE.search(text)
    assert match is not None, (
        f"{skill_md.relative_to(_SKILLS_ROOT.parent)} carries the white-label "
        f"sentinel but the body has no `Load ... integration-pattern.md` "
        f"directive. The wiring will silently skip integration-pattern.md at "
        f"runtime. Either add the load directive or remove the sentinel."
    )
