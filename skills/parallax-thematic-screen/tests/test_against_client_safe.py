"""--against must stay suppressed under audience=client_safe (audit SEC-12 gap).

The skill is prompt-only, so this checks the SKILL.md text that carries the
rule. Each place `--against` changes the run must name the client_safe
exception: the step that builds against_query, the Thesis Works Against output
section, and the Done-when line. Both the skills/ and plugin/ copies ship.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parents[1]
COPIES = [
    SKILL_DIR / "SKILL.md",
    REPO_ROOT / "plugin" / "skills" / SKILL_DIR.name / "SKILL.md",
]

# Each line's opening clause is pinned exactly. A looser pattern stayed green
# when the rule was inverted ("unless ... is not `client_safe`", "never
# omitted when ..."). If you reword a clause on purpose, update it here.
_CLAUSES = [
    ("against_query step", r"^\d+\. With `--against`",
     "With `--against`, unless the resolved audience mode (conventions §13.1) is `client_safe`: set `against_query`"),
    ("Thesis Works Against section", r"^- \*\*Thesis Works Against\*\*",
     "- **Thesis Works Against** (only with `--against`; omitted when the resolved audience mode per conventions §13.1 is `client_safe`)"),
    ("Done-when line", r"^- With `--against` \(",
     "- With `--against` (resolved audience mode not `client_safe`): "),
]


def _line(text: str, pattern: str) -> str:
    matches = [ln for ln in text.splitlines() if re.search(pattern, ln)]
    assert len(matches) == 1, f"expected one line matching {pattern!r}, found {len(matches)}"
    return matches[0]


@pytest.mark.parametrize("path", COPIES, ids=["skills", "plugin"])
@pytest.mark.parametrize("where, locator, clause", _CLAUSES, ids=[c[0] for c in _CLAUSES])
def test_against_keeps_client_safe_exception(path: Path, where: str, locator: str, clause: str):
    line = _line(path.read_text(encoding="utf-8"), locator)
    assert clause in line, f"{path}: {where} no longer opens with the client_safe exception"
