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
import zipfile
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import build_bundle as bb  # noqa: E402 -- path insert must precede this import
from canary_fixture import hermetic_extra_terms  # noqa: E402,F401 -- autouse fixture

SRC = (SCRIPTS_DIR.parents[1] / "parallax-concierge" / "SKILL.md").read_text(encoding="utf-8")
BUILT = bb.transform_concierge(SRC)

STATE_ORDER = ["Check", "Role", "Integrator", "Input", "Run", "After the result"]

PLUGIN_CONCIERGE = Path(__file__).resolve().parents[3] / "plugin/skills/parallax-concierge/SKILL.md"


def _block(text):
    return text[text.index("<!-- new-here:begin -->"):text.index("<!-- new-here:end -->")]


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


def test_source_new_here_block_matches_the_repo_rendering():
    """The source copy's generated block must equal render_new_here for a
    full clone ("repo" distribution, every manifest skill available) — a
    staleness check, like the bundle staleness gate, so a clone works
    unbuilt and this region cannot silently drift from the generator."""
    expected = bb.render_new_here(set(bb.skill_manifest.skills()), "repo")
    assert _block(SRC) == f"<!-- new-here:begin -->\n{expected}"


def test_plugin_concierge_connect_steps_name_the_plugin_tab():
    if not PLUGIN_CONCIERGE.is_file():
        pytest.skip("plugin bundle not built in this checkout")
    block = _block(PLUGIN_CONCIERGE.read_text(encoding="utf-8"))
    assert "Customize → Plugins → Parallax → Connectors" in block
    assert "/mcp" in block
    assert "upload" not in block.lower()


def test_plugin_concierge_names_only_shipped_skills():
    if not PLUGIN_CONCIERGE.is_file():
        pytest.skip("plugin bundle not built in this checkout")
    text = PLUGIN_CONCIERGE.read_text(encoding="utf-8")
    assert not (bb.named_skills(text) - set(bb.PLUGIN_SKILLS) - bb.HOUSE_VIEW_OPERATORS)


def test_zip_concierge(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "WEB_OUT_DIR", tmp_path)
    bb.build_web(["parallax-concierge"])
    text = zipfile.ZipFile(tmp_path / "parallax-concierge.skill").read(
        "parallax-concierge/SKILL.md").decode()
    avail = set(bb.WEB_SKILLS) | set(bb.skill_manifest.standalone_skills("release"))
    assert not (bb.named_skills(text) - avail)
    block = _block(text)
    assert "Customize → Skills" in block and bb.PARALLAX_MCP_URL in block
    assert "parallax-desk-call-list" not in block


def test_render_new_here_lists_each_role_once_with_its_first_run():
    block = bb.render_new_here(set(bb.PLUGIN_SKILLS), "plugin")
    for role in bb.skill_manifest.roles():
        assert block.count(f"| {role['label']} |") == 1
    assert "| Wealth advisor | `/parallax-client-review`" in block


def test_filter_concierge_drops_a_bullet_with_its_continuation_line():
    text = ("- Desk phrasing →\n    `/parallax-desk-call-list`, then nudges\n"
            "- Single ticker → `/parallax-should-i-buy`\n")
    out = bb.filter_concierge(text, {"parallax-should-i-buy"})
    assert "desk" not in out.lower() and "/parallax-should-i-buy" in out


def test_filter_concierge_fails_on_an_unshipped_name_in_prose():
    with pytest.raises(bb.BuildError):
        bb.filter_concierge("Try /parallax-desk-call-list next.\n", set())


def test_fill_new_here_is_idempotent_and_needs_both_markers():
    src = "a\n<!-- new-here:begin -->\nold\n<!-- new-here:end -->\nb\n"
    once = bb.fill_new_here(src, "NEW")
    assert bb.fill_new_here(once, "NEW") == once and "old" not in once
    with pytest.raises(bb.BuildError):
        bb.fill_new_here("no markers", "NEW")
