"""
Drift gate for `loader.md §X[.Y]` cross-references in high-churn SKILL.md files.

The 6 most-edited consumer skills cite `_parallax/house-view/loader.md` subsection
numbers (e.g., "per loader.md §5 rule 3", "per loader.md §7.1"). If loader.md is
restructured and a section is renamed or removed, those references silently
break — the runtime LLM would try to apply a rule that no longer exists.

This test extracts the loader.md heading set and asserts every reference in the
high-churn SKILL.md files resolves to either:
  - an exact heading match (e.g., "§7.1" → `### §7.1 ...`), OR
  - a valid parent section (e.g., "§5.1" → `## 5. ...` since loader.md uses the
    "§5 rule 1" convention where rule numbers within §5 are written as `§5.N`
    rather than promoted to dedicated subsections).

Failing the test produces an actionable error: the skill file, line number, the
unresolved section ID, and the full set of valid IDs.

Co-located under the existing pytest discovery root for `_parallax/white-label`
because that's where the cross-skill drift gates already live; this is just
another such gate (loader.md is the canonical spec; SKILL.md files are
consumers; the test prevents silent drift between them).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# This file lives at skills/_parallax/white-label/tests/, so the repo root is
# four levels up. The loader and SKILL.md files are addressed from that root.
# ---------------------------------------------------------------------------

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_LOADER_MD: Path = _REPO_ROOT / "skills" / "_parallax" / "house-view" / "loader.md"

# The six most-edited consumer skills. Update this list (and add a test case)
# when a new skill becomes load-bearing for loader.md references.
_HIGH_CHURN_SKILLS: tuple[str, ...] = (
    "morning-brief",
    "portfolio-builder",
    "should-i-buy",
    "deep-dive",
    "client-review",
    "rebalance",
)

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------
# Heading extractor — matches loader.md lines like:
#   "## 5. Output rendering rules"            → captures "5"
#   "### 6.1 Required fields (every line)"    → captures "6.1"
#   "### §7.1 House View Note ..."            → captures "7.1"
#   "### §5.1a Calibration disclosure ..."    → captures "5.1a"
# The `§` is optional because loader.md mixes styles (§6.x has no `§` prefix
# in its headings, but §7.x and §5.1a do).
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(
    r"^#{2,4}\s+(?:§)?(\d+(?:\.\d+[a-z]?)*)\b",
    re.MULTILINE,
)

# Reference extractor in SKILL.md files. Matches:
#   "loader.md §5"
#   "loader.md §5.1"
#   "loader.md §7.1"
#   "_parallax/house-view/loader.md §6" (path-prefixed, defensive)
# The "rule N" qualifier that appears in some references (e.g., "§5 rule 3")
# is NOT part of the section ID and is left for `re.finditer` to skip over.
# ---------------------------------------------------------------------------

_REF_RE = re.compile(
    r"(?:[\w/_-]*?)loader\.md\s+§(\d+(?:\.\d+[a-z]?)*)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _loader_sections() -> set[str]:
    """Return the set of heading IDs extracted from loader.md."""
    text = _LOADER_MD.read_text(encoding="utf-8")
    return set(_HEADING_RE.findall(text))


def _resolves(section_id: str, headings: set[str]) -> bool:
    """A reference resolves if it matches a heading exactly OR its top-level
    parent section (the integer before the first dot) is a heading.

    Rationale: loader.md uses the "§N rule M" convention inside §5 and §6,
    where rule numbers are sometimes written as "§N.M" rather than promoted
    to dedicated subsection headings. Treating the top-level parent as a
    fallback prevents these legitimate references from tripping the gate
    while still catching the real drift case (a typo'd or removed section).
    """
    if section_id in headings:
        return True
    parent = section_id.split(".", 1)[0]
    return parent in headings


def _collect_refs(skill: str) -> list[tuple[int, str]]:
    """Return a list of (line_number, section_id) for each loader.md §X ref."""
    path = _REPO_ROOT / "skills" / skill / "SKILL.md"
    refs: list[tuple[int, str]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for m in _REF_RE.finditer(line):
            refs.append((lineno, m.group(1)))
    return refs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_loader_md_is_readable() -> None:
    """Smoke check: loader.md exists and yields a non-empty heading set."""
    assert _LOADER_MD.is_file(), f"loader.md not found at {_LOADER_MD}"
    sections = _loader_sections()
    assert sections, (
        "loader.md heading extraction returned an empty set. Either loader.md "
        "is empty or the _HEADING_RE pattern is broken."
    )
    # Sanity: §1-§8 top-level sections must be present. If this fails the
    # extractor is mis-anchored; downstream parametric tests would all pass
    # vacuously, so guard here.
    for top in ("1", "2", "3", "4", "5", "6", "7", "8"):
        assert top in sections, (
            f"Top-level section §{top} not extracted from loader.md headings. "
            f"Got: {sorted(sections)}"
        )


@pytest.mark.parametrize("skill", _HIGH_CHURN_SKILLS)
def test_loader_md_refs_resolve(skill: str) -> None:
    """Every `loader.md §X` reference in a high-churn SKILL.md must resolve.

    Resolution succeeds if the section ID is an exact heading or its top-level
    parent is. See `_resolves` for the rationale on parent-section fallback.
    """
    sections = _loader_sections()
    refs = _collect_refs(skill)
    missing = [(line, sid) for line, sid in refs if not _resolves(sid, sections)]
    assert not missing, (
        f"skills/{skill}/SKILL.md has unresolved loader.md references: "
        + ", ".join(f"§{sid} (line {line})" for line, sid in missing)
        + f". Valid section IDs in loader.md: {sorted(sections)}. "
        "Either fix the reference (typo / renamed section) or add the missing "
        "section to loader.md."
    )


# ---------------------------------------------------------------------------
# Unit tests for the regex / resolver — guard against silent drift in the
# gate itself.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line,expected_ids",
    [
        ("per loader.md §5 rule 3", ["5"]),
        ("per loader.md §7.1 and elsewhere", ["7.1"]),
        ("see _parallax/house-view/loader.md §6.2", ["6.2"]),
        ("loader.md §5.1a is mandatory", ["5.1a"]),
        ("loader.md §1-§2", ["1"]),
        ("no loader-style references here", []),
    ],
)
def test_ref_regex_extracts_section_ids(line: str, expected_ids: list[str]) -> None:
    """Unit coverage for `_REF_RE` against representative SKILL.md phrasings."""
    got = [m.group(1) for m in _REF_RE.finditer(line)]
    assert got == expected_ids


@pytest.mark.parametrize(
    "section_id,headings,expected",
    [
        ("5", {"5"}, True),                    # exact
        ("5.1", {"5"}, True),                  # parent fallback (§5 rule 1)
        ("5.1a", {"5", "5.1a"}, True),         # exact wins
        ("9", {"1", "2", "3"}, False),         # neither exact nor parent
        ("7.1", {"7", "7.1"}, True),           # exact
        ("7.99", {"7"}, True),                 # parent fallback
    ],
)
def test_resolves_logic(section_id: str, headings: set[str], expected: bool) -> None:
    """Unit coverage for the exact-or-parent resolution rule."""
    assert _resolves(section_id, headings) is expected
