"""Structural regressions for the runtime-discovered Parallax tool contract.

The contract is consumed as prose, so these tests can only prove that the
load-bearing instructions remain present in both source and plugin copies. They
cannot prove that an orchestrating model obeys them at runtime.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOTS = ("skills", "plugin/skills")
FIXED_NAMESPACE = "mcp__claude_ai_Parallax__"


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _batch_a(markdown: str) -> str:
    return markdown.split("### Batch A", 1)[1].split("**After Batch A**", 1)[0]


@pytest.mark.parametrize("skill_root", SKILL_ROOTS)
def test_shared_contract_makes_live_discovery_authoritative(skill_root: str) -> None:
    text = _read(f"{skill_root}/_parallax/parallax-conventions.md")

    assert "Live capability discovery is authoritative" in text
    assert "exact callable name" in text
    assert "live input schema" in text
    assert "do not try guessed aliases or argument variants" in text
    assert "Do not re-fire an entire batch" in text
    assert FIXED_NAMESPACE not in text


@pytest.mark.parametrize("skill_root", SKILL_ROOTS)
def test_rebalance_uses_one_compact_portfolio_call(skill_root: str) -> None:
    text = _read(f"{skill_root}/parallax-rebalance/SKILL.md")
    batch = _batch_a(text)

    rows = re.findall(r"^\| `analyze_portfolio` \|", batch, flags=re.MULTILINE)
    assert len(rows) == 1
    assert "Exactly one call maximum" in batch
    assert "omit time-series blocks" in batch
    assert "do not retry this capability" in batch
    assert "check_portfolio_redundancy" in batch


@pytest.mark.parametrize("skill_root", SKILL_ROOTS)
def test_rebalance_is_namespace_neutral_and_schema_bound(skill_root: str) -> None:
    text = _read(f"{skill_root}/parallax-rebalance/SKILL.md")

    assert FIXED_NAMESPACE not in text
    assert "Live discovery overrides every namespace" in text
    assert "Construct every payload" in text
    assert "discovered live schema" in text
    assert "schema-validation" in text
    assert "guessed-shape retry" in text


def test_repo_instruction_does_not_require_a_fixed_alias() -> None:
    text = _read("CLAUDE.md")

    assert "Do not require a fixed server alias" in text
    assert "must be connected as `claude_ai_Parallax`" not in text


def test_double_call_regression_would_fail_the_row_guard() -> None:
    planted = """### Batch A
| Tool | Parameters | Notes |
|---|---|---|
| `analyze_portfolio` | risk fields | first call |
| `analyze_portfolio` | concentration fields | second call |
**After Batch A**
"""

    rows = re.findall(
        r"^\| `analyze_portfolio` \|", _batch_a(planted), flags=re.MULTILINE
    )
    assert len(rows) == 2
