"""Tests for the BUILT (plugin-distribution) concierge's new-here surface —
on generated output (bb.transform_concierge of the source), never on source
prose alone. A test whose only evidence is that a natural-language skill file
contains particular strings does not prove behavior (see
global-constraints.md's test-quality rule); these check the output
build_bundle.py actually emits.

Presence of the "## New here?" heading, presence of both markers, and
absence of the Investor-profile branch are already covered by
test_build_bundle.py::test_concierge_keeps_new_here_block and
::test_concierge_removes_excluded_routes — not repeated here. These tests
cover what isn't: the markers appear exactly once each (not duplicated by a
future edit), the six state labels stay in declaration order, and the
opening block actually offers the new-here path in the built output.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import build_bundle as bb  # noqa: E402 -- path insert must precede this import

SRC = (SCRIPTS_DIR.parents[1] / "parallax-concierge" / "SKILL.md").read_text(encoding="utf-8")
BUILT = bb.transform_concierge(SRC)

STATE_ORDER = ["Check", "Role", "Integrator", "Input", "Run", "After the result"]


def test_built_concierge_new_here_markers_appear_exactly_once():
    sec = BUILT[BUILT.index("## New here?"):BUILT.index("## Nudging after each skill runs")]
    assert sec.count("<!-- new-here:begin -->") == 1
    assert sec.count("<!-- new-here:end -->") == 1
    assert sec.index("<!-- new-here:begin -->") < sec.index("<!-- new-here:end -->")


def test_built_concierge_new_here_states_in_order():
    sec = BUILT[BUILT.index("## New here?"):BUILT.index("## Nudging after each skill runs")]
    positions = [sec.index(f"**{s}**") for s in STATE_ORDER]
    assert positions == sorted(positions)


def test_built_concierge_offers_new_here_in_the_opening():
    opening = BUILT[BUILT.index("**Hi — where are we looking today?**"):BUILT.index("## 🔍 Stock branch")]
    assert "New here?" in opening
