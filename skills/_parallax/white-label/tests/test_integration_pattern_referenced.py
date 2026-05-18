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
# Words that, when they immediately precede a load-directive match, invert
# its meaning ("no JIT-load of integration-pattern.md" must not satisfy the
# drift gate). Checked over the 16 chars before the match.
_NEGATION_PREFIXES = ("no ", "not ", "never ", "without ", "skip ", "skipping ")


def _has_positive_load_directive(text: str) -> bool:
    """True if text contains at least one non-negated load directive."""
    for match in LOAD_DIRECTIVE_RE.finditer(text):
        prefix = text[max(0, match.start() - 16):match.start()].lower()
        if not any(neg in prefix for neg in _NEGATION_PREFIXES):
            return True
    return False


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
    assert _has_positive_load_directive(text), (
        f"{skill_md.relative_to(_SKILLS_ROOT.parent)} carries the white-label "
        f"sentinel but the body has no positive `Load ... integration-pattern.md` "
        f"directive (negated mentions like 'no JIT-load of integration-pattern.md' "
        f"do not count). Either add the load directive or remove the sentinel."
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Load `integration-pattern.md` §2", True),
        ("JIT-load _parallax/white-label/integration-pattern.md before render", True),
        ("(no JIT-load of integration-pattern.md from this skill)", False),
        ("we do not load integration-pattern.md here", False),
        ("Skip loading integration-pattern.md when offline", False),
    ],
)
def test_negated_load_directives_do_not_satisfy_gate(text: str, expected: bool) -> None:
    """Unit-level coverage for the negation filter."""
    assert _has_positive_load_directive(text) is expected



# ---------------------------------------------------------------------------
# §9.2 AI-interaction disclosure gate
# ---------------------------------------------------------------------------

_ANALYSIS_DISCLAIMER_RE = re.compile(
    r"informational analysis based on Parallax|scenario-based analysis, not investment advice",
    re.IGNORECASE,
)

_NINE_TWO_REF_RE = re.compile(
    r"parallax-conventions\.md[`\s]*§9\.2",
    re.IGNORECASE,
)

# Skills explicitly exempt from §9.2 because they emit config artifacts AND
# gate any LLM-generated content behind an operator confirmation step before
# downstream consumers render it. Adding a skill here must be paired with
# updating the exemption rationale in `parallax-conventions.md §9.2` in the
# same PR — the test gate and the spec text are co-load-bearing.
_NINE_TWO_EXEMPT_SKILLS: frozenset[str] = frozenset({"white-label-onboard"})


@pytest.mark.parametrize(
    "skill_md", _collect_wired_skills(), ids=lambda p: p.parent.name
)
def test_wired_skill_renders_ai_disclosure(skill_md: Path) -> None:
    """Every wired analysis-producing SKILL.md must reference §9.2.

    Two-stage gate:
    1. If skill is in `_NINE_TWO_EXEMPT_SKILLS`, skip (explicit exemption,
       rationale documented in `parallax-conventions.md §9.2`).
    2. Otherwise, the skill MUST carry a recognised analysis disclaimer
       AND a §9.2 reference. A wired-but-unmatched skill fails the gate —
       it must be either added to the exemption set with rationale, or
       the disclaimer regex must be extended to cover its phrasing.
       Silent skip is not an option — regulatory disclosure cannot be
       invisible by default.
    """
    skill_name = skill_md.parent.name
    if skill_name in _NINE_TWO_EXEMPT_SKILLS:
        pytest.skip(f"{skill_name} is exempt from §9.2 (config artifact + operator gate)")

    text = skill_md.read_text(encoding="utf-8")
    assert _ANALYSIS_DISCLAIMER_RE.search(text), (
        f"{skill_md.relative_to(_SKILLS_ROOT.parent)} carries the white-label "
        f"sentinel but does not render any recognised analysis disclaimer "
        f"variant. A wired skill is presumed to produce client-facing "
        f"analysis. Resolution: either add the skill to `_NINE_TWO_EXEMPT_SKILLS` "
        f"AND update the exemption rationale in `parallax-conventions.md §9.2` "
        f"in the same PR; or extend `_ANALYSIS_DISCLAIMER_RE` to cover this "
        f"skill's disclaimer phrasing. Silent skip is not permitted."
    )

    assert _NINE_TWO_REF_RE.search(text), (
        f"{skill_md.relative_to(_SKILLS_ROOT.parent)} carries the white-label "
        f"sentinel AND the standard analysis disclaimer but does not reference "
        f"`parallax-conventions.md §9.2` for the AI-interaction disclosure. "
        f"Add the directive immediately above the disclaimer block, e.g.: "
        f"'Render `parallax-conventions.md §9.2` immediately above the "
        f"disclaimer below.'"
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Render `parallax-conventions.md §9.2` above the disclaimer", True),
        ("see parallax-conventions.md §9.2 for the banner", True),
        ("parallax-conventions.md §9.1 (standard disclaimer)", False),
        ("conventions §9.2 (no filename)", False),
        ("This is informational analysis based on Parallax", False),
    ],
)
def test_nine_two_reference_pattern(text: str, expected: bool) -> None:
    """Unit-level coverage for the §9.2 reference detector."""
    assert bool(_NINE_TWO_REF_RE.search(text)) is expected
