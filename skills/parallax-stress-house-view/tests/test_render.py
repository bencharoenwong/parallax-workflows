"""Tests for the Parallax Data Age header in render.render_artifact."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import render  # noqa: E402

META = {"view_name": "Test View", "version_id": "v-1"}


def _header(**kwargs) -> str:
    report = render.render_artifact(META, [], {}, [], "hash123", **kwargs)
    return report.split("\n---\n", 1)[0]


@pytest.mark.parametrize(
    "kwargs, expected, absent",
    [
        (
            {"age_delta": "unverifiable", "parallax_age_days": None},
            ["**Parallax Data Age:** unverifiable", "CIO Challenges are suppressed"],
            ["day(s)"],
        ),
        (
            {"age_delta": "fresh", "parallax_age_days": 12},
            ["**Parallax Data Age:** 12 day(s)"],
            ["unverifiable", "CIO Challenges are suppressed"],
        ),
        (
            {},
            [],
            ["Parallax Data Age"],
        ),
    ],
    ids=["unverifiable", "dated", "omitted"],
)
def test_render_parallax_data_age_header(kwargs, expected, absent):
    header = _header(**kwargs)
    for text in expected:
        assert text in header
    for text in absent:
        assert text not in header
