"""
Schema-load smoke tests for the competitor-intelligence ground truth referenced
by `parallax-conventions.md` §8 (Marketing & Competitive Integrity).

Run from repo root::

    pytest skills/_parallax/scripts/test_marketing_schema.py -v
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SCHEMA_PATH = _REPO_ROOT / "skills" / "_parallax" / "competitor-intelligence" / "schema.yaml"
_COMPETITORS_DIR = _REPO_ROOT / "skills" / "_parallax" / "competitor-intelligence" / "competitors"


def test_schema_loads():
    with _SCHEMA_PATH.open() as f:
        schema = yaml.safe_load(f)
    assert "competitor" in schema, "schema must declare top-level 'competitor' block"
    assert "intelligence" in schema, "schema must declare top-level 'intelligence' block"


@pytest.mark.parametrize("path", sorted(_COMPETITORS_DIR.glob("*.yaml")))
def test_competitor_file_conforms(path):
    with path.open() as f:
        entry = yaml.safe_load(f)
    assert entry["competitor"]["name"], f"{path.name}: competitor.name is required"
    intel = entry["intelligence"]
    for key in ("teardown", "pricing", "win_loss_vectors", "verifiable_claims", "who_should_choose"):
        assert key in intel, f"{path.name}: intelligence.{key} is required"
    assert intel["who_should_choose"], f"{path.name}: who_should_choose must be populated (no hollow competitors)"
