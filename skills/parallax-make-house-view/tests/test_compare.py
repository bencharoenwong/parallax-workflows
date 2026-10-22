"""Tests for --compare mode: diff_excludes, render_compare, and maker.run_compare.

Compare is a NEUTRAL per-cell diff of two saved views. It reuses the symmetric
diff_views core UNCHANGED; these tests pin both the symmetry guarantees and the
neutral framing (no synthesis/sovereign/pillar language).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from shadow_diff import diff_views, diff_excludes, render_compare
from maker import run_compare, _load_view_bundle

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _anchor() -> dict:
    return _load("bank_view_anchor.yaml")


def _goldman() -> dict:
    return _load("goldman_view_b.yaml")


# --------------------------------------------------------------------------- #
# diff_views semantic mapping (compare reads added=right_only, bank_only=left_only)
# --------------------------------------------------------------------------- #

def test_diff_views_semantic_mapping():
    diff = diff_views(_anchor(), _goldman())
    # added == present in RIGHT (goldman), silent in LEFT (anchor) -> right_only
    assert "tilts.sectors.health_care" in diff["added"]
    assert "tilts.regions.india" in diff["added"]
    assert "tilts.factors.value" in diff["added"]
    assert "tilts.pillars.market_entropy" in diff["added"]
    # bank_only == present in LEFT (anchor), silent in RIGHT (goldman) -> left_only
    assert "tilts.factors.momentum" in diff["bank_only"]
    # agree
    assert "tilts.sectors.energy" in diff["agree"]
    assert "tilts.regions.us" in diff["agree"]
    assert "tilts.pillars.econometrics_phase" in diff["agree"]
    # disagree carries {bank: left_value, synthesized: right_value}
    assert "tilts.sectors.information_technology" in diff["disagree"]
    d = diff["disagree"]["tilts.sectors.information_technology"]
    assert d["bank"] == 1 and d["synthesized"] == -1


def test_diff_views_buckets_unchanged_regression():
    """Guard: diff_views must still emit the original bucket keys (not renamed)."""
    diff = diff_views(_anchor(), _goldman())
    assert "added" in diff and "bank_only" in diff
    assert "left_only" not in diff and "right_only" not in diff


def test_symmetry_invariant():
    ab = diff_views(_anchor(), _goldman())
    ba = diff_views(_goldman(), _anchor())
    assert set(ab["agree"]) == set(ba["agree"])
    assert set(ab["disagree"]) == set(ba["disagree"])
    # left/right swap when the operands swap
    assert set(ab["added"]) == set(ba["bank_only"])
    assert set(ab["bank_only"]) == set(ba["added"])


# --------------------------------------------------------------------------- #
# diff_excludes
# --------------------------------------------------------------------------- #

def test_diff_excludes_inline():
    ex = diff_excludes(
        {"tilts": {"excludes": ["weapons", "tobacco"]}},
        {"tilts": {"excludes": ["weapons", "fossil_fuels"]}},
    )
    assert ex["common"] == ["weapons"]
    assert "tobacco" in ex["left_only"] and "weapons" not in ex["left_only"]
    assert "fossil_fuels" in ex["right_only"]


def test_diff_excludes_symmetry():
    a = {"tilts": {"excludes": ["weapons", "tobacco"]}}
    b = {"tilts": {"excludes": ["weapons", "fossil_fuels"]}}
    ab = diff_excludes(a, b)
    ba = diff_excludes(b, a)
    assert ab["common"] == ba["common"]
    assert ab["left_only"] == ba["right_only"]
    assert ab["right_only"] == ba["left_only"]


def test_diff_excludes_top_level_fallback():
    ex = diff_excludes({"excludes": ["x"]}, {"excludes": ["x", "y"]})
    assert ex["common"] == ["x"]
    assert ex["right_only"] == ["y"]


def test_diff_excludes_empty_views():
    ex = diff_excludes(_anchor(), _goldman())  # anchor has none, goldman has 2
    assert ex["common"] == []
    assert ex["left_only"] == []
    assert "weapons" in ex["right_only"] and "fossil_fuels" in ex["right_only"]


# --------------------------------------------------------------------------- #
# render_compare
# --------------------------------------------------------------------------- #

def test_render_compare_neutral_framing():
    text = render_compare(_anchor(), _goldman())
    assert "COMPARE" in text
    assert "AGREE" in text
    assert "LEFT ONLY" in text
    assert "RIGHT ONLY" in text
    assert "DISAGREE" in text
    low = text.lower()
    # MUST NOT carry shadow-diff's asymmetric / sovereign framing
    assert "sovereign" not in low
    assert "additive" not in low
    assert "bank's view" not in low
    assert "informational" not in low


def test_render_compare_no_pillar_block_ever():
    """Compare never emits the pillar-confidence/computation block.

    Pillar TILT cells (tilts.pillars.*) are legitimate view data and may appear;
    what must NOT appear is the shadow-diff confidence block (confidence scores +
    missing_inputs), which exposes computation internals.
    """
    text = render_compare(_anchor(), _goldman())
    assert "PILLAR CONFIDENCE" not in text.upper()
    assert "confidence=" not in text
    assert "missing=" not in text


def test_render_compare_disagree_shows_both_values():
    text = render_compare(_anchor(), _goldman())
    it_lines = [ln for ln in text.splitlines() if "information_technology" in ln]
    assert it_lines, f"expected an information_technology line, got:\n{text}"
    assert "left=1" in it_lines[0] and "right=-1" in it_lines[0]


def test_render_compare_excludes_section():
    text = render_compare(_anchor(), _goldman())
    assert "EXCLUDES" in text
    assert "weapons" in text and "fossil_fuels" in text


def test_render_compare_filters_raw_tilts_excludes_path():
    """tilts.excludes is a list leaf; it must NOT leak into the tilt sections."""
    text = render_compare(_anchor(), _goldman())
    assert "tilts.excludes" not in text


def test_render_compare_names_from_metadata():
    text = render_compare(_anchor(), _goldman())
    assert "Anchor bank view Q2 2026" in text
    assert "Goldman Test View Q2 2026" in text


def test_render_compare_name_fallback_to_param():
    bare = {"tilts": {"sectors": {"energy": 1}}}
    text = render_compare(bare, bare, left_name="UBS", right_name="JPM")
    assert "UBS" in text and "JPM" in text


def test_render_compare_handles_none_left():
    text = render_compare(None, _goldman())
    assert "COMPARE" in text
    # everything goldman holds is RIGHT ONLY when left is empty
    assert "tilts.sectors.health_care" in text


# --------------------------------------------------------------------------- #
# _load_view_bundle + run_compare
# --------------------------------------------------------------------------- #

def test_load_view_bundle_file_direct():
    view = _load_view_bundle(FIXTURES / "bank_view_anchor.yaml")
    assert "tilts" in view


def test_load_view_bundle_dir(tmp_path):
    (tmp_path / "view.yaml").write_text(
        yaml.safe_dump(_anchor()), encoding="utf-8"
    )
    view = _load_view_bundle(tmp_path)
    assert "tilts" in view


def test_load_view_bundle_missing_path():
    with pytest.raises(ValueError, match="does not exist"):
        _load_view_bundle(Path("/nonexistent/nope/view.yaml"))


def test_load_view_bundle_missing_tilts_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump({"metadata": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="tilts"):
        _load_view_bundle(p)


def test_load_view_bundle_non_dict_tilts_raises(tmp_path):
    """A 'tilts' key whose value is not a mapping is not a valid bundle."""
    p = tmp_path / "bad2.yaml"
    p.write_text(yaml.safe_dump({"tilts": 42}), encoding="utf-8")
    with pytest.raises(ValueError, match="tilts"):
        _load_view_bundle(p)


def test_render_compare_tolerates_non_dict_metadata():
    """A non-dict metadata must not crash name resolution; fall back gracefully."""
    left = {"metadata": "oops-not-a-dict", "tilts": {"sectors": {"energy": 1}}}
    right = {"metadata": {"view_name": "Right Firm"}, "tilts": {"sectors": {"energy": -1}}}
    text = render_compare(left, right, left_name="LEFT_FALLBACK")
    assert "COMPARE" in text
    assert "LEFT_FALLBACK" in text  # used because left metadata is non-dict
    assert "Right Firm" in text


def test_run_compare_end_to_end():
    out = run_compare(
        FIXTURES / "bank_view_anchor.yaml",
        FIXTURES / "goldman_view_b.yaml",
    )
    assert "COMPARE" in out
    assert len(out) > 0
    assert "PILLAR CONFIDENCE" not in out.upper()
    # no MCP / synthesis was involved — pure file diff
    assert "tilts.sectors.information_technology" in out
