"""Shared pytest fixtures for /parallax-judge-house-view tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
REPO_ROOT = SKILL_DIR.parent.parent

# Make the local skill modules importable when pytest is launched from
# anywhere in the repo (mirrors stress.py's sys.path bootstrap).
for p in (
    SKILL_DIR,
    REPO_ROOT / "skills" / "_parallax" / "house-view",
    REPO_ROOT / "skills" / "stress-house-view",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


@pytest.fixture
def fixtures_dir() -> Path:
    return HERE / "fixtures"


@pytest.fixture
def fresh_aligned_responses(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir / "fresh_macro_aligned.json").read_text())


@pytest.fixture
def fresh_divergent_responses(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir / "fresh_macro_divergent.json").read_text())
