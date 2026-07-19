"""Tests for build_bundle.py transforms and reference rewriting.

Transforms run against the real source files (they are anchor-asserted, so a
drifted source fails here before it fails a distribution build)."""
import sys
import unicodedata
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


# The branding canaries are assembled from codepoints so this public repo never
# carries them as literals (see build_bundle.py). These tests therefore assert
# their SHAPE, never their value — a wrong hex digit would otherwise silently
# drop a term from the leak gate while the scan kept passing. Nothing below may
# spell a canary out, including in assertion messages.
_EXPECTED_GLYPH_NAMES = [
    "GREEK CAPITAL LETTER OMEGA",
    "GREEK CAPITAL LETTER PHI",
    "GREEK CAPITAL LETTER XI",
    "GREEK CAPITAL LETTER PSI",
]


def test_branding_canaries_have_expected_shape():
    canaries = bb._BRANDING_CANARIES
    assert len(canaries) == len(_EXPECTED_GLYPH_NAMES) + 1
    for i, expected in enumerate(_EXPECTED_GLYPH_NAMES):
        glyph = canaries[i]
        assert len(glyph) == 1, f"canary {i} is not a single character"
        assert unicodedata.name(glyph) == expected, f"canary {i} name mismatch"
    code_name = canaries[-1]
    assert len(code_name) == 5, "code-name canary is not 5 characters"
    assert code_name.isascii() and code_name.isalpha() and code_name.isupper(), (
        "code-name canary is not ASCII uppercase letters")


def test_branding_canaries_are_wired_into_the_scan(tmp_path):
    for i, term in enumerate(bb._BRANDING_CANARIES):
        planted = tmp_path / f"planted_{i}"
        planted.mkdir()
        (planted / "doc.md").write_text(f"prefix {term} suffix", encoding="utf-8")
        with pytest.raises(bb.BuildError):
            bb.canary_scan(planted)


def test_canary_scan_passes_on_clean_tree(tmp_path):
    (tmp_path / "doc.md").write_text("nothing to see here\n", encoding="utf-8")
    bb.canary_scan(tmp_path)


def test_plugin_skill_dirs_exist_and_have_skill_md():
    for name in bb.PLUGIN_SKILLS:
        assert (SKILLS / name / "SKILL.md").is_file(), name


def test_parallax_allowlist_paths_exist():
    for entry in bb.PARALLAX_INCLUDE:
        assert (SKILLS / "_parallax" / entry).exists(), entry


# --------------------------------------------------------------------------
# Web-only transforms
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rel", sorted(bb.WEB_TRANSFORMS))
def test_web_transform_applies_to_current_source(rel):
    """Anchor-asserted like the shared transforms: a drifted source file fails
    here before it fails a distribution build."""
    src = (SKILLS / rel).read_text(encoding="utf-8")
    assert bb.WEB_TRANSFORMS[rel](src) != src


def test_web_conventions_transform_removes_unvendored_doc_ref():
    """The web build excludes skill-structure-conventions.md, so the shared
    conventions doc must not send a web agent to it (all 12 zips shipped that
    dangling directive before this transform existed)."""
    out = bb.transform_conventions_web(
        (SKILLS / "_parallax/parallax-conventions.md").read_text(encoding="utf-8"))
    assert "skill-structure-conventions.md" not in out
    assert "self-contained" in out


# --------------------------------------------------------------------------
# Resolution gates
# --------------------------------------------------------------------------

def test_web_resolution_check_flags_dangling_vendored_ref(tmp_path):
    skill = tmp_path / "parallax-demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "see `_vendored/_parallax/missing-doc.md` for details\n", encoding="utf-8")
    with pytest.raises(bb.BuildError):
        bb.web_resolution_check(skill)


def test_web_resolution_check_passes_when_vendored_ref_resolves(tmp_path):
    skill = tmp_path / "parallax-demo"
    (skill / "_vendored" / "_parallax").mkdir(parents=True)
    (skill / "_vendored" / "_parallax" / "present.md").write_text("x", encoding="utf-8")
    (skill / "SKILL.md").write_text(
        "see `_vendored/_parallax/present.md`\n", encoding="utf-8")
    bb.web_resolution_check(skill)


def test_bundled_skill_docs_covers_shared_parallax_tree(tmp_path):
    """The shared tree carries cross-skill refs nothing else validates; it must
    not be skipped wholesale (it was, so the plugin could ship a broken ref)."""
    (tmp_path / "_parallax" / "house-view").mkdir(parents=True)
    shared = tmp_path / "_parallax" / "house-view" / "loader.md"
    shared.write_text("x", encoding="utf-8")
    assert shared in bb.bundled_skill_docs(tmp_path)


def test_authoring_guide_placeholder_refs_are_exempt(tmp_path):
    """Authoring guides use illustrative placeholder paths (references/X.md)
    that are examples, not real refs — exempt, but only that ref class (the
    guides themselves stay under resolution_check; see the scoping test below)."""
    (tmp_path / "_parallax").mkdir(parents=True)
    for rel in bb.RESOLUTION_EXEMPT_DOCS:
        p = tmp_path / rel
        p.write_text("load references/X.md before Step 3\n", encoding="utf-8")
        assert p in bb.bundled_skill_docs(tmp_path)
    bb.resolution_check(tmp_path)


def test_resolution_check_flags_broken_shared_tree_ref(tmp_path):
    (tmp_path / "_parallax" / "house-view").mkdir(parents=True)
    (tmp_path / "_parallax" / "house-view" / "loader.md").write_text(
        "cross-ref: parallax-portfolio-checkup/references/gone.md\n", encoding="utf-8")
    with pytest.raises(bb.BuildError):
        bb.resolution_check(tmp_path)


def test_resolution_check_ignores_author_only_script_refs(tmp_path):
    """_parallax/scripts/ is repo tooling, never bundled by design."""
    (tmp_path / "_parallax").mkdir(parents=True)
    (tmp_path / "_parallax" / "coverage-matrix.md").write_text(
        "run `_parallax/scripts/coverage-lint.sh` before committing\n",
        encoding="utf-8")
    bb.resolution_check(tmp_path)


# --------------------------------------------------------------------------
# Canary scan: case-insensitivity
# --------------------------------------------------------------------------

def test_canary_scan_catches_case_variant_leaks(tmp_path):
    """Warehouse/schema identifiers are listed upper-case but leak lower-case
    (SQL, prose); a case-sensitive scan waved those through.

    Terms are read from the loaded scan list at RUNTIME and never written as
    literals. This file is tracked in a public repo, so a hand-written "realistic
    leak" fixture would itself be the leak it tests for — the same reason the
    branding-canary tests above assert shape rather than value."""
    terms = [t for t in bb.load_canary_terms() if t.isascii() and len(t) > 3]
    assert terms, "no scan terms loaded"
    checked = 0
    for i, term in enumerate(terms):
        for j, variant in enumerate({term.lower(), term.upper(), term.swapcase()}
                                    - {term}):
            planted = tmp_path / f"planted_{i}_{j}"
            planted.mkdir()
            (planted / "doc.md").write_text(
                f"prefix {variant} suffix", encoding="utf-8")
            with pytest.raises(bb.BuildError):
                bb.canary_scan(planted)
            checked += 1
    # A term with no cased letters yields an empty variant set and contributes
    # nothing; without this the test can go green while asserting nothing.
    assert checked, "no case variants exercised — test is vacuous"


def test_canary_scan_catches_glyph_case_variants(tmp_path):
    """Case-insensitive matching is new behavior, and the single-character
    branding terms are excluded from the ASCII case-variant test above — so
    without this they have zero coverage for it. Selected by shape, never
    spelled out."""
    glyphs = [t for t in bb.CANARY_TERMS if len(t) == 1]
    assert glyphs, "no single-character terms found"
    for i, term in enumerate(glyphs):
        for j, variant in enumerate({term.lower(), term.upper()}):
            planted = tmp_path / f"glyph_{i}_{j}"
            planted.mkdir()
            (planted / "doc.md").write_text(
                f"prefix {variant} suffix", encoding="utf-8")
            with pytest.raises(bb.BuildError):
                bb.canary_scan(planted)


def test_canary_scan_allows_public_contract_fields(tmp_path):
    """Allowlist entries are published MCP response fields, not the internal
    identifiers whose terms they happen to contain as a substring."""
    for i, allowed in enumerate(bb.CANARY_ALLOWLIST):
        planted = tmp_path / f"allowed_{i}"
        planted.mkdir()
        (planted / "doc.md").write_text(
            f"| `{allowed}` | bool | documented public response field |\n",
            encoding="utf-8")
        bb.canary_scan(planted)


# --------------------------------------------------------------------------
# Bundle freshness
# --------------------------------------------------------------------------

def test_tracked_plugin_bundle_matches_source(tmp_path, monkeypatch):
    """plugin/ is a tracked build artifact, so a source edit that is not
    followed by a rebuild silently ships a stale bundle (commit 2e344f8 dropped
    an unused import from a source test and left the bundle copy behind). Build
    into a temp dir and diff against the tracked tree."""
    built = tmp_path / "plugin"
    built_marketplace = tmp_path / "marketplace.json"
    monkeypatch.setattr(bb, "PLUGIN_DIR", built)
    monkeypatch.setattr(bb, "MARKETPLACE_FILE", built_marketplace)
    bb.build_plugin()

    # marketplace.json is a tracked build output too — and it is the file the
    # marketplace installer reads. Its name/owner/source/description exist
    # nowhere else, so plugin.json does not cover a stale copy.
    tracked_marketplace = bb.REPO_ROOT / ".claude-plugin" / "marketplace.json"
    assert built_marketplace.read_bytes() == tracked_marketplace.read_bytes(), (
        ".claude-plugin/marketplace.json is stale — run: "
        "python3 skills/_parallax/scripts/build_bundle.py plugin")

    tracked = bb.REPO_ROOT / "plugin"
    built_files = {p.relative_to(built) for p in built.rglob("*") if p.is_file()}
    tracked_files_ = {p.relative_to(tracked) for p in tracked.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts}

    assert built_files == tracked_files_, (
        "plugin/ file list is stale — run: "
        "python3 skills/_parallax/scripts/build_bundle.py plugin")
    stale = [str(rel) for rel in sorted(built_files)
             if (built / rel).read_bytes() != (tracked / rel).read_bytes()]
    assert stale == [], (
        f"plugin/ content is stale in {len(stale)} file(s) — run: "
        f"python3 skills/_parallax/scripts/build_bundle.py plugin\n" +
        "\n".join(stale[:10]))


def test_canary_allowlist_does_not_mask_sibling_identifiers(tmp_path):
    """An allowlist entry can END with a scan term (the published field does).
    Unbounded `str.replace` masking then stripped that term out of every sibling
    identifier sharing the prefix — `<field>_raw`, `<field>_internal` — and
    shipped a real leak clean. Masking must be token-bounded.

    Siblings are constructed from the allowlist at runtime; nothing is spelled
    out, so this stays safe to track in a public repo."""
    terms = [t.lower() for t in bb.load_canary_terms()]
    checked = 0
    for i, allowed in enumerate(bb.CANARY_ALLOWLIST):
        # Only entries that actually contain a scan term can exhibit the bug.
        if not any(t in allowed.lower() for t in terms):
            continue
        for j, sibling in enumerate((f"{allowed}_raw", f"{allowed}_internal",
                                     f"{allowed}Override")):
            planted = tmp_path / f"sibling_{i}_{j}"
            planted.mkdir()
            (planted / "doc.md").write_text(
                f"value = {sibling}\n", encoding="utf-8")
            with pytest.raises(bb.BuildError):
                bb.canary_scan(planted)
            checked += 1
    assert checked, "no allowlist entry overlaps a scan term — test is vacuous"


def test_canary_allowlist_masking_cannot_manufacture_a_hit(tmp_path, monkeypatch):
    """Masking substitutes a sentinel instead of deleting. Deleting would splice
    the neighbours together and can synthesize a term the file never contained.

    Uses SYNTHETIC allowlist/term values so no real term enters this tracked
    file. The splice needs a term containing two consecutive non-word characters;
    no current real term has that shape, but the term list is externally
    extensible (a partner name with a ' & ' or ' - ' separator supplies it), so
    the sentinel becomes load-bearing the moment one is added."""
    monkeypatch.setattr(bb, "CANARY_ALLOWLIST", ["public_field"])
    monkeypatch.setattr(bb, "CANARY_TERMS", ["alpha -- beta"])
    # Synthetic term list only — opt out of the real extra list, which
    # load_canary_terms now hard-requires.
    monkeypatch.setattr(bb, "EXTRA_CANARY_FILE", tmp_path / "absent.txt")
    monkeypatch.setenv(bb.PARTIAL_SCAN_ENV, "1")

    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "doc.md").write_text("alpha -public_field- beta", encoding="utf-8")
    bb.canary_scan(clean)   # sentinel keeps the neighbours apart

    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / "doc.md").write_text("alpha -- beta", encoding="utf-8")
    with pytest.raises(bb.BuildError):   # control: really present, still caught
        bb.canary_scan(planted)


def test_authoring_guide_exemption_is_scoped_to_placeholder_refs(tmp_path):
    """Both authoring guides ship in the plugin. Their references/ placeholders
    are exempt, but a broken _parallax/ ref in them is a real break."""
    (tmp_path / "_parallax").mkdir(parents=True)
    guide = tmp_path / sorted(bb.RESOLUTION_EXEMPT_DOCS)[0]
    guide.write_text(
        "load references/X.md before Step 3\n"
        "see `_parallax/house-view/loader-RENAMED.md`\n", encoding="utf-8")
    with pytest.raises(bb.BuildError):
        bb.resolution_check(tmp_path)


def test_load_canary_terms_fails_closed_without_extra_file(tmp_path, monkeypatch):
    """The extra list carries most of the terms. A missing file silently halved
    the scan and the build still reported success — on a public repo that means
    publishing under a weakened gate from any machine lacking the file."""
    monkeypatch.setattr(bb, "EXTRA_CANARY_FILE", tmp_path / "absent.txt")
    monkeypatch.delenv(bb.PARTIAL_SCAN_ENV, raising=False)
    with pytest.raises(bb.BuildError):
        bb.load_canary_terms()


def test_load_canary_terms_allows_explicit_partial_scan(tmp_path, monkeypatch):
    """Degrading is allowed, but only as a deliberate act."""
    monkeypatch.setattr(bb, "EXTRA_CANARY_FILE", tmp_path / "absent.txt")
    monkeypatch.setenv(bb.PARTIAL_SCAN_ENV, "1")
    assert bb.load_canary_terms() == list(bb.CANARY_TERMS)


def test_load_canary_terms_includes_extra_file_when_present():
    """Guards the real machine path: the local list must actually be picked up,
    not just tolerated."""
    if not bb.EXTRA_CANARY_FILE.exists():
        pytest.skip("extra scan-term file not present on this machine")
    assert len(bb.load_canary_terms()) > len(bb.CANARY_TERMS)
