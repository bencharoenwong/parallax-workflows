"""Tests for build_bundle.py transforms and reference rewriting.

Transforms run against the real source files (they are anchor-asserted, so a
drifted source fails here before it fails a distribution build)."""
import sys
from pathlib import Path

import pytest

# Self-test runs from the script's own directory; just import directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_bundle as bb

SKILLS = bb.SKILLS_DIR


@pytest.mark.parametrize("rel", sorted(bb.TRANSFORMS))
def test_transform_applies_to_current_source(rel):
    src = (SKILLS / rel).read_text(encoding="utf-8")
    out = bb.TRANSFORMS[rel](src)
    assert out != src
    assert len(out) < len(src)


@pytest.mark.parametrize("rel", sorted(bb.TRANSFORMS))
def test_transform_output_is_canary_clean(rel):
    out = bb.TRANSFORMS[rel]((SKILLS / rel).read_text(encoding="utf-8"))
    hits = [t for t in bb.CANARY_TERMS if t in out]
    assert hits == []


def test_transform_fails_loudly_on_missing_anchor():
    with pytest.raises(bb.BuildError):
        bb.transform_hv_loader("no anchors here")


def test_concierge_removes_excluded_routes():
    out = bb.transform_concierge(
        (SKILLS / "parallax-concierge/SKILL.md").read_text(encoding="utf-8"))
    for gone in ("parallax-ai-", "cio-letter-prep", "load-house-view",
                 "judge-house-view", "make-house-view", "stress-house-view",
                 "house-view-diff", "Investor profile"):
        assert gone not in out
    # surviving branches intact
    for kept in ("parallax-should-i-buy", "parallax-portfolio-checkup",
                 "parallax-macro-outlook", "Three buckets"):
        assert kept in out


def test_output_template_subset_keeps_section_headings():
    out = bb.transform_output_template(
        (SKILLS / "_parallax/AI-profiles/output-template.md").read_text(encoding="utf-8"))
    # §5 / §8 headings must survive so `output-template.md §N` refs resolve.
    assert "### 5. Verdict" in out
    assert "### 8. Standard disclaimer (REQUIRED, VERBATIM)" in out
    assert "FORBIDDEN verdict language" in out
    assert "consult a qualified financial advisor" in out
    # per-profile gate table does not ship
    assert "6.5" not in out
    assert "Greenblatt" not in out


def test_schema_transform_removes_all_component_keys():
    out = bb.transform_hv_schema(
        (SKILLS / "_parallax/house-view/schema.yaml").read_text(encoding="utf-8"))
    assert "pillars" not in out
    # surviving data contract intact
    for kept in ("sectors:", "regions:", "factors:", "tilt_conviction:",
                 "extraction_confidence:"):
        assert kept in out


def test_rewrite_refs_forms():
    text = (
        "JIT-load _parallax/parallax-conventions.md and `_parallax/house-view/loader.md`.\n"
        'python3 "<skill-dir>/../_parallax/render_gate.py" --skill x\n'
        "See ../parallax-client-review/references/recommendation-matrix.md and\n"
        "parallax-portfolio-checkup/references/health-flags.md for flags.\n"
    )
    out = bb.rewrite_refs(text)
    assert "_vendored/_parallax/parallax-conventions.md" in out
    assert "`_vendored/_parallax/house-view/loader.md`" in out
    assert '"<skill-dir>/_vendored/_parallax/render_gate.py"' in out
    assert "_vendored/parallax-client-review/references/recommendation-matrix.md" in out
    assert "_vendored/parallax-portfolio-checkup/references/health-flags.md" in out
    assert "../parallax-client-review" not in out
    # idempotent — a second pass changes nothing
    assert bb.rewrite_refs(out) == out


def test_rewrite_refs_maps_self_reference_to_own_files():
    text = "See parallax-client-review/references/recommendation-matrix.md §2."
    out = bb.rewrite_refs(text, "parallax-client-review")
    assert out == "See references/recommendation-matrix.md §2."


def test_rewrite_refs_leaves_repo_layout_prose_alone():
    text = "the shared tree lives at skills/_parallax/ in the repo"
    assert bb.rewrite_refs(text) == text


def test_web_descriptions_cover_shortlist_within_limits():
    for name in bb.WEB_SKILLS:
        assert name in bb.WEB_DESCRIPTIONS
        assert len(name) <= 64
        assert len(bb.WEB_DESCRIPTIONS[name]) <= 200


def test_plugin_skill_dirs_exist_and_have_skill_md():
    for name in bb.PLUGIN_SKILLS:
        assert (SKILLS / name / "SKILL.md").is_file(), name


def test_parallax_allowlist_paths_exist():
    for entry in bb.PARALLAX_INCLUDE:
        assert (SKILLS / "_parallax" / entry).exists(), entry
