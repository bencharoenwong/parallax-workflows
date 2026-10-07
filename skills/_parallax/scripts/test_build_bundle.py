"""Tests for build_bundle.py transforms and reference rewriting.

Transforms run against the real source files (they are anchor-asserted, so a
drifted source fails here before it fails a distribution build)."""
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path

import json

import pytest

# Self-test runs from the script's own directory; just import directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_bundle as bb
from canary_fixture import hermetic_extra_terms  # noqa: F401 -- autouse fixture

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
        with pytest.raises(bb.BuildError, match="term scan failed"):
            bb.canary_scan(planted)


def test_canary_scan_passes_on_clean_tree(tmp_path):
    (tmp_path / "doc.md").write_text("nothing to see here\n", encoding="utf-8")
    bb.canary_scan(tmp_path)


def test_plugin_skill_dirs_exist_and_have_skill_md():
    # effective_plugin_skills() filters to this repo's dirs (the tap output
    # excludes translate-*). Only KNOWN_OPTIONAL_SKILLS may be filtered out —
    # anything else absent is a typo and must already have raised.
    effective = bb.effective_plugin_skills()
    assert effective == [
        name for name in bb.PLUGIN_SKILLS
        if (SKILLS / name / "SKILL.md").is_file()
    ]
    for name in bb.PLUGIN_SKILLS:
        if name not in effective:
            assert name in bb.KNOWN_OPTIONAL_SKILLS, name
    assert len(effective) >= 20


def test_plugin_skills_typo_fails_the_build(monkeypatch):
    """A renamed/mistyped entry must abort the build, not silently drop the
    skill from the bundle (both built and tracked trees would then agree on a
    bundle that is missing a skill)."""
    monkeypatch.setattr(
        bb, "PLUGIN_SKILLS", bb.PLUGIN_SKILLS + ["parallax-typoed-skill"])
    with pytest.raises(bb.BuildError, match="KNOWN_OPTIONAL_SKILLS"):
        bb.effective_plugin_skills()


def test_plugin_description_tracks_the_bundled_skill_set():
    with_translate = bb.plugin_description(["parallax-deep-dive",
                                            "translate-thai-finance"])
    without_translate = bb.plugin_description(["parallax-deep-dive"])
    assert "screening, translation, and client-review" in with_translate
    # Was pinned as "screening, and client-review" -- the dangling comma a
    # translate-less build actually emitted. The assertion encoded the defect
    # instead of catching it, so the marketplace description shipped with it.
    assert "screening and client-review" in without_translate
    assert ", and client-review" not in without_translate


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


def test_web_loader_transform_removes_unvendored_doc_ref():
    out = bb.transform_loader_web(
        (SKILLS / "_parallax/house-view/loader.md").read_text(encoding="utf-8"))
    assert "skill-structure-conventions.md" not in out
    assert "house content such as gotchas lives in the body" in out


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


def test_web_resolution_check_skips_author_time_script_refs(tmp_path):
    """Same policy as resolution_check: _parallax/scripts/ is never bundled."""
    skill = tmp_path / "parallax-demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "see `_vendored/_parallax/scripts/contract_validator.py`\n", encoding="utf-8")
    bb.web_resolution_check(skill)


def test_web_resolution_check_skips_the_bare_scripts_dir_ref(tmp_path):
    skill = tmp_path / "parallax-demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "shared `_vendored/_parallax/scripts/`\n", encoding="utf-8")
    bb.web_resolution_check(skill)


def test_resolution_check_skips_the_bare_scripts_dir_ref(tmp_path):
    (tmp_path / "_parallax").mkdir()
    (tmp_path / "parallax-demo").mkdir()
    (tmp_path / "parallax-demo" / "SKILL.md").write_text(
        "shared `_parallax/scripts/`\n", encoding="utf-8")
    bb.resolution_check(tmp_path)


def test_web_resolution_check_flags_an_excluded_meta_doc_ref(tmp_path):
    skill = tmp_path / "parallax-demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "see `_vendored/_parallax/skill-structure-conventions.md`\n", encoding="utf-8")
    with pytest.raises(bb.BuildError):
        bb.web_resolution_check(skill)


def test_web_resolution_check_does_not_skip_a_path_that_leaves_scripts(tmp_path):
    skill = tmp_path / "parallax-demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "see `_vendored/_parallax/scripts/../missing-doc.md`\n", encoding="utf-8")
    with pytest.raises(bb.BuildError):
        bb.web_resolution_check(skill)


def test_resolution_check_does_not_skip_a_path_that_leaves_scripts(tmp_path):
    (tmp_path / "_parallax").mkdir()
    (tmp_path / "parallax-demo").mkdir()
    (tmp_path / "parallax-demo" / "SKILL.md").write_text(
        "see `_parallax/scripts/../missing-doc.md`\n", encoding="utf-8")
    with pytest.raises(bb.BuildError):
        bb.resolution_check(tmp_path)


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
            with pytest.raises(bb.BuildError, match="term scan failed"):
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
            with pytest.raises(bb.BuildError, match="term scan failed"):
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
    tracked = bb.REPO_ROOT / "plugin"
    tracked_marketplace = bb.REPO_ROOT / ".claude-plugin" / "marketplace.json"
    if not tracked.is_dir() or not tracked_marketplace.is_file():
        pytest.skip("this checkout does not track plugin build artifacts")

    built = tmp_path / "plugin"
    built_marketplace = tmp_path / "marketplace.json"
    monkeypatch.setattr(bb, "PLUGIN_DIR", built)
    monkeypatch.setattr(bb, "MARKETPLACE_FILE", built_marketplace)
    bb.build_plugin()

    # marketplace.json is a tracked build output too — and it is the file the
    # marketplace installer reads. Its name/owner/source/description exist
    # nowhere else, so plugin.json does not cover a stale copy.
    assert built_marketplace.read_bytes() == tracked_marketplace.read_bytes(), (
        ".claude-plugin/marketplace.json is stale — run: "
        "python3 skills/_parallax/scripts/build_bundle.py plugin")

    built_files = {p.relative_to(built) for p in built.rglob("*") if p.is_file()}
    # Ask git for the tracked set rather than walking the working tree: any
    # local untracked artifact under plugin/ (a stray .pytest_cache, .DS_Store,
    # an editor swap file) would otherwise be reported as bundle staleness.
    listing = subprocess.run(
        ["git", "-C", str(bb.REPO_ROOT), "ls-files", "-z", "--", "plugin"],
        capture_output=True, text=True)
    if listing.returncode != 0:
        pytest.skip("git is unavailable; cannot enumerate tracked plugin files")
    tracked_files_ = {Path(rel).relative_to("plugin")
                      for rel in listing.stdout.split("\0") if rel}

    assert built_files == tracked_files_, (
        "plugin/ file list is stale — run: "
        "python3 skills/_parallax/scripts/build_bundle.py plugin")
    stale = [str(rel) for rel in sorted(built_files)
             if (built / rel).read_bytes() != (tracked / rel).read_bytes()]
    assert stale == [], (
        f"plugin/ content is stale in {len(stale)} file(s) — run: "
        f"python3 skills/_parallax/scripts/build_bundle.py plugin\n" +
        "\n".join(stale[:10]))


@pytest.mark.parametrize("lang", bb.UNSHIPPED_LANGUAGES, ids=lambda lang: lang.code)
def test_plugin_bundle_hides_a_language_while_its_translator_is_unshipped(
        tmp_path, monkeypatch, lang):
    """A language routes to its translate skill; while that skill is held out of
    the plugin (manifest "plugin": false), the built bundle's documentation and
    data must not advertise the language, though the source tree still does."""
    if lang.skill in bb.PLUGIN_SKILLS:
        pytest.skip(f"{lang.skill} ships in the plugin")
    built = tmp_path / "plugin"
    monkeypatch.setattr(bb, "PLUGIN_DIR", built)
    monkeypatch.setattr(bb, "MARKETPLACE_FILE", tmp_path / "marketplace.json")
    bb.build_plugin()

    leaks = [str(p.relative_to(built)) for p in built.rglob("*")
             if p.is_file() and p.suffix in (".md", ".html", ".json")
             and lang.code in p.read_text(errors="ignore")]
    assert leaks == []
    for rel in lang.transforms:
        assert lang.code in (SKILLS / rel).read_text(encoding="utf-8")


def test_plugin_conventions_list_only_shipped_languages(tmp_path, monkeypatch):
    built = tmp_path / "plugin"
    monkeypatch.setattr(bb, "PLUGIN_DIR", built)
    monkeypatch.setattr(bb, "MARKETPLACE_FILE", tmp_path / "marketplace.json")
    bb.build_plugin()
    conventions = (built / "skills/_parallax/parallax-conventions.md").read_text(
        encoding="utf-8")
    if all(lang.skill not in bb.PLUGIN_SKILLS for lang in bb.UNSHIPPED_LANGUAGES):
        assert "Supported: en, zh-CN, zh-TW, zh-HK, th.`" in conventions
        assert "`th` → `translate-thai-finance`; the marker line" in conventions


@pytest.mark.parametrize("lang", bb.UNSHIPPED_LANGUAGES, ids=lambda lang: lang.code)
def test_language_strip_is_a_no_op_when_its_translator_ships(tmp_path, lang):
    doc = tmp_path / "parallax-deep-dive" / "SKILL.md"
    doc.parent.mkdir()
    doc.write_text(f"lang=<code> (`en`; `th`, `{lang.code}`)\n", encoding="utf-8")
    shipped = ["parallax-deep-dive"] + [other.skill for other in bb.UNSHIPPED_LANGUAGES]
    bb.strip_unshipped_languages(tmp_path, shipped)
    assert f"`{lang.code}`" in doc.read_text(encoding="utf-8")


@pytest.mark.parametrize("lang", bb.UNSHIPPED_LANGUAGES, ids=lambda lang: lang.code)
def test_language_strip_fails_closed_on_an_unhandled_mention(tmp_path, lang):
    doc = tmp_path / "parallax-new-skill" / "SKILL.md"
    doc.parent.mkdir()
    doc.write_text(f"lang={lang.code} is supported\n", encoding="utf-8")
    with pytest.raises(bb.BuildError, match="parallax-new-skill"):
        bb.strip_unshipped_languages(tmp_path, ["parallax-new-skill"])


@pytest.mark.parametrize("lang", bb.UNSHIPPED_LANGUAGES, ids=lambda lang: lang.code)
def test_language_strip_fails_closed_on_a_held_skill_name(tmp_path, lang):
    doc = tmp_path / "_parallax" / "notes.md"
    doc.parent.mkdir()
    doc.write_text(f"Pattern used by `{lang.skill}`.\n", encoding="utf-8")
    with pytest.raises(bb.BuildError, match="notes.md"):
        bb.strip_unshipped_languages(tmp_path, [])


def test_manifest_may_list_held_skill_names(tmp_path):
    doc = tmp_path / "_parallax" / "manifest.json"
    doc.parent.mkdir()
    doc.write_text(json.dumps({lang.skill: {"plugin": False} for lang in bb.UNSHIPPED_LANGUAGES}),
                   encoding="utf-8")
    bb.strip_unshipped_languages(tmp_path, [])


def test_language_strips_do_not_depend_on_each_other(tmp_path):
    """Two held languages share one lang= list; stripping one must not break the
    anchor the other relies on, in either combination."""
    assert {"ar-SA", "vi-VN"} <= {lang.code for lang in bb.UNSHIPPED_LANGUAGES}
    line = "lang=<code> (`en` default; `zh-CN`, `th`, `vi-VN`, `ar-SA`)\n"
    doc = tmp_path / "parallax-deep-dive" / "SKILL.md"
    doc.parent.mkdir()

    doc.write_text(line, encoding="utf-8")
    bb.strip_unshipped_languages(tmp_path, ["parallax-deep-dive"])
    assert doc.read_text(encoding="utf-8") == "lang=<code> (`en` default; `zh-CN`, `th`)\n"

    arabic = next(lang.skill for lang in bb.UNSHIPPED_LANGUAGES if lang.code == "ar-SA")
    doc.write_text(line, encoding="utf-8")
    bb.strip_unshipped_languages(tmp_path, ["parallax-deep-dive", arabic])
    assert doc.read_text(encoding="utf-8") == (
        "lang=<code> (`en` default; `zh-CN`, `th`, `ar-SA`)\n")


def test_dropping_note_paragraphs_leaves_one_blank_line_in_any_order():
    text = "Intro.\n\n`ar-SA` routes to `x`.\n\n`vi-VN` routes to `y`.\n\n### Next\n"
    for order in (("`ar-SA` routes", "`vi-VN` routes"), ("`vi-VN` routes", "`ar-SA` routes")):
        out = text
        for prefix in order:
            out = bb._drop_paragraph_line(out, prefix, "test")
        assert out == "Intro.\n\n### Next\n"


def test_canary_allowlist_does_not_mask_sibling_identifiers(
        tmp_path, monkeypatch):
    """An allowlist entry can END with a scan term (the published field does).
    Unbounded `str.replace` masking then stripped that term out of every sibling
    identifier sharing the prefix — `<field>_raw`, `<field>_internal` — and
    shipped a real leak clean. Masking must be token-bounded.

    Siblings are constructed from the allowlist at runtime; nothing is spelled
    out, so this stays safe to track in a public repo."""
    overlap = bb.CANARY_ALLOWLIST[0].rsplit("_", 1)[-1]
    monkeypatch.setattr(bb, "CANARY_TERMS", [overlap])
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
            with pytest.raises(bb.BuildError, match="term scan failed"):
                bb.canary_scan(planted)
            checked += 1
    assert checked, "synthetic allowlist overlap was not exercised"


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
    with pytest.raises(bb.BuildError, match="term scan failed"):
        bb.canary_scan(planted)   # control: really present, still caught


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


def test_load_canary_terms_includes_extra_file_when_present(tmp_path, monkeypatch):
    """An available extra list is loaded in addition to built-in terms."""
    extra_file = tmp_path / "extra-terms.txt"
    extra_file.write_text("# comment\nprivate_marker\n", encoding="utf-8")
    monkeypatch.setattr(bb, "EXTRA_CANARY_FILE", extra_file)
    assert len(bb.load_canary_terms()) > len(bb.CANARY_TERMS)


def test_no_unbundled_operator_command_is_priced_in_the_public_bundle():
    """A token-costs row for a command absent from PLUGIN_SKILLS advertises a
    workflow the plugin user cannot run.

    This happened: /parallax-house-view-attribution was added to
    token-costs.md and shipped into the public bundle priced at "~7 tokens,
    the cheapest house-view workflow", while no such command exists there. Its
    five siblings were stripped by name; the new one was simply not on the list.

    The staleness check cannot catch it — a wholly-new, self-consistent row
    regenerates identically. This asserts the property directly: every command
    priced in the BUNDLE's token-costs must be a skill the bundle ships.
    """
    import re
    bundle = Path(__file__).resolve().parents[3] / "plugin/skills/_parallax/token-costs.md"
    if not bundle.exists():
        import pytest
        pytest.skip("plugin bundle not built in this checkout")
    priced = set(re.findall(r"^\|\s*`/?((?:parallax|translate)-[a-z0-9-]*[a-z0-9])`",
                            bundle.read_text(), re.M))
    orphans = sorted(priced - set(bb.PLUGIN_SKILLS))
    assert not orphans, (
        f"token-costs in the PUBLIC bundle prices skills the bundle does not "
        f"ship: {orphans}")


def test_collect_deps_ignores_the_ellipsis_placeholder():
    """Step 0 prose says "Resolve every `_parallax/...` path"; the ellipsis
    names no file, so it is not a dependency and must not fail the build."""
    shared, cross = bb.collect_deps("1. Resolve every `_parallax/...` path named here.", strict=True)
    assert shared == set() and cross == set()


def test_collect_deps_still_rejects_a_real_ref_outside_the_set():
    with pytest.raises(bb.BuildError):
        bb.collect_deps("Load `_parallax/no-such-shared-file.md` first.", strict=True)


@pytest.fixture(scope="module")
def web_build(tmp_path_factory):
    """All web packages, built once per module: (zip dir, unzipped dir).
    Module scope runs before the function-scoped term fixture, so a machine
    without the extra term file builds with the built-in terms only."""
    out = tmp_path_factory.mktemp("web")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(bb, "WEB_OUT_DIR", out / "zips")
        if not bb.EXTRA_CANARY_FILE.is_file():
            mp.setenv(bb.PARTIAL_SCAN_ENV, "1")
        bb.build_web(bb.WEB_SKILLS)
    for pkg in (out / "zips").glob("*.skill"):
        with zipfile.ZipFile(pkg) as zf:
            zf.extractall(out / "unzipped" / pkg.stem)
    return out / "zips", out / "unzipped"


def test_web_build_succeeds_for_the_shortlist(web_build):
    zips, _ = web_build
    assert sorted(p.stem for p in zips.glob("*.skill")) == sorted(bb.WEB_SKILLS)
    for name in bb.WEB_SKILLS:
        with zipfile.ZipFile(zips / f"{name}.skill") as zf:
            assert f"{name}/SKILL.md" in zf.namelist()


def test_rewrite_refs_handles_single_quoted_skill_dir():
    text = "sys.path.insert(0, '<skill-dir>/../_parallax/white-label')"
    out = bb.rewrite_refs(text)
    assert "'<skill-dir>/_vendored/_parallax/white-label'" in out
    assert bb.rewrite_refs(out) == out


def test_web_resolution_check_rejects_unrewritten_skill_dir(tmp_path):
    skill = tmp_path / "parallax-demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "run `python3 '<skill-dir>/../_parallax/x.py'`\n", encoding="utf-8")
    with pytest.raises(bb.BuildError):
        bb.web_resolution_check(skill)


def test_missing_python_siblings_reports_an_unshipped_companion(tmp_path):
    root = tmp_path / "parallax-demo" / "_vendored" / "_parallax" / "pkg"
    root.mkdir(parents=True)
    (root / "a.py").write_text(
        'from pathlib import Path\nP = Path(__file__).with_name("b.py")\n', encoding="utf-8")
    assert bb.missing_python_siblings(tmp_path / "parallax-demo") == ["_vendored/_parallax/pkg/b.py"]
    (root / "b.py").write_text("x = 1\n", encoding="utf-8")
    assert bb.missing_python_siblings(tmp_path / "parallax-demo") == []


@pytest.mark.parametrize("ref", [
    'Path(__file__).parent / "b.yaml"',
    "Path(__file__).resolve().parent/'b.yaml'",
    'pathlib.Path( __file__ ).resolve( ).parent  /  "b.yaml"',
])
def test_missing_python_siblings_reports_a_file_parent_companion(tmp_path, ref):
    root = tmp_path / "parallax-demo" / "_vendored" / "_parallax" / "pkg"
    root.mkdir(parents=True)
    (root / "a.py").write_text(
        f"import pathlib\nfrom pathlib import Path\nP = {ref}\n", encoding="utf-8")
    assert bb.missing_python_siblings(tmp_path / "parallax-demo") == ["_vendored/_parallax/pkg/b.yaml"]
    (root / "b.yaml").write_text("x: 1\n", encoding="utf-8")
    assert bb.missing_python_siblings(tmp_path / "parallax-demo") == []


def test_web_build_fails_when_loader_schema_companion_is_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "WEB_OUT_DIR", tmp_path)
    companions = dict(bb.RUNTIME_COMPANIONS)
    del companions["white-label/loader.py"]
    monkeypatch.setattr(bb, "RUNTIME_COMPANIONS", companions)
    with pytest.raises(bb.BuildError, match="schema.yaml"):
        bb.build_web(["parallax-rebalance"])
    assert not (tmp_path / "parallax-rebalance.skill").exists()


def test_web_rebalance_ships_only_the_white_label_files_it_uses(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "WEB_OUT_DIR", tmp_path)
    bb.build_web(["parallax-rebalance"])
    with zipfile.ZipFile(tmp_path / "parallax-rebalance.skill") as zf:
        names = zf.namelist()
        docs = [zf.read(n).decode("utf-8") for n in names if n.endswith(".md")]
    prefix = "parallax-rebalance/_vendored/_parallax/white-label/"
    assert sorted(n[len(prefix):] for n in names if n.startswith(prefix)) == [
        "integration-pattern.md", "loader.py", "rm_consumer.py", "schema.yaml"]
    assert not any("/tests/" in n or "/extract/" in n for n in names)
    assert not any("<skill-dir>/../_parallax" in d for d in docs)


def test_missing_anchor_modules_reports_a_module_a_one_liner_imports(tmp_path):
    """A one-liner adds a shared dir to sys.path and imports from it; every
    module it imports from that dir must ship (replays a reviewer mutation)."""
    skill = tmp_path / "parallax-demo"
    wl = skill / "_vendored" / "_parallax" / "white-label"
    wl.mkdir(parents=True)
    (wl / "rm_consumer.py").write_text("x = 1\n", encoding="utf-8")
    (skill / "SKILL.md").write_text(
        "python3 -c \"import sys; sys.path.insert(0, '<skill-dir>/_vendored/_parallax/white-label'); "
        "from rm_consumer import resolve_audience; from validator import validate\"\n",
        encoding="utf-8")
    assert bb.missing_anchor_modules(skill, {"white-label"}) == [
        "_vendored/_parallax/white-label/validator.py"]
    (wl / "validator.py").write_text("x = 1\n", encoding="utf-8")
    assert bb.missing_anchor_modules(skill, {"white-label"}) == []


def test_web_packages_with_the_house_view_loader_ship_view_status(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "WEB_OUT_DIR", tmp_path)
    bb.build_web(["parallax-should-i-buy"])
    with zipfile.ZipFile(tmp_path / "parallax-should-i-buy.skill") as zf:
        names = set(zf.namelist())
    base = "parallax-should-i-buy/_vendored/_parallax/house-view/"
    assert base + "loader.md" in names
    assert base + "view_status.py" in names


def test_web_token_costs_prices_only_web_skills(tmp_path, monkeypatch):
    import re
    monkeypatch.setattr(bb, "WEB_OUT_DIR", tmp_path)
    bb.build_web(["parallax-should-i-buy"])
    with zipfile.ZipFile(tmp_path / "parallax-should-i-buy.skill") as zf:
        text = zf.read("parallax-should-i-buy/_vendored/_parallax/token-costs.md").decode()
    named = set(re.findall(r"(?<![\w-])/?((?:parallax|translate)-[a-z0-9-]*[a-z0-9])", text))
    assert named & set(bb.skill_manifest.skills()) <= set(bb.WEB_SKILLS)
    assert "/parallax-should-i-buy" in text


def test_token_costs_filter_drops_rows_callouts_and_empty_sections():
    text = (
        "# T\n\n### Kept\n\n| Workflow | Tokens |\n|---|---|\n"
        "| `/parallax-should-i-buy` | 29 |\n| `/parallax-deep-dive` | 45 |\n\n"
        "> **Note:** `/parallax-deep-dive` is dearer.\n\n"
        "### Gone\n\n| Workflow | Tokens |\n|---|---|\n| `parallax-ai-buffett` | 4 |\n\n"
        "### After\n\nplain\n")
    out = bb.filter_token_costs(text, {"parallax-should-i-buy"})
    assert "/parallax-should-i-buy" in out
    assert "deep-dive" not in out and "ai-buffett" not in out
    assert "### Gone" not in out and "### After" in out


def test_token_costs_filter_fails_on_a_mention_it_cannot_remove():
    text = ("### S\n\n| Workflow | Tokens |\n|---|---|\n| `/parallax-should-i-buy` | 29 |\n\n"
            "Prose names /parallax-deep-dive here.\n")
    with pytest.raises(bb.BuildError):
        bb.filter_token_costs(text, {"parallax-should-i-buy"})


def test_web_packages_do_not_advertise_held_languages(web_build):
    zips, _ = web_build
    held = ("vi-VN", "ar-SA", "translate-vietnamese-finance", "translate-arabic-finance")
    for pkg in zips.glob("*.skill"):
        with zipfile.ZipFile(pkg) as zf:
            for n in zf.namelist():
                if n.endswith((".md", ".json")) and not n.endswith("manifest.json"):
                    text = zf.read(n).decode("utf-8")
                    assert not [h for h in held if h in text], (pkg.name, n)
    with zipfile.ZipFile(zips / "parallax-should-i-buy.skill") as zf:
        conv = zf.read("parallax-should-i-buy/_vendored/_parallax/parallax-conventions.md").decode()
    assert "translate-chinese-finance" in conv and "translate-thai-finance" in conv


def test_annotate_unavailable_commands():
    avail = {"parallax-should-i-buy"}
    note = bb.PLUGIN_NOTE
    text = ("- Calls → use /parallax-desk-call-list\n"
            "Run `/parallax-pair-finder AAPL.O long` first.\n"
            "Then /parallax-should-i-buy.\n")
    out = bb.annotate_unavailable_commands(text, avail)
    assert f"/parallax-desk-call-list{note}" in out
    assert f"`/parallax-pair-finder AAPL.O long`{note}" in out
    assert "/parallax-should-i-buy." in out
    assert bb.annotate_unavailable_commands(out, avail) == out


def _command_matches(root, pattern):
    """(path, line, match, rest) for each `pattern` match in staged .md and
    .yaml files outside fenced blocks. `rest` is the text after the match, or
    after its closing backtick when the match sits in a code span. Only the
    fence and span bookkeeping is shared; each caller classifies matches with
    its own rule, independent of the build's annotator."""
    for p in root.rglob("*"):
        if not (p.is_file() and p.suffix in (".md", ".yaml")):
            continue
        fenced = False
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            for m in pattern.finditer(line):
                rest = line[m.end():]
                if line[:m.start()].count("`") % 2:
                    rest = rest[rest.find("`") + 1:]
                yield p, line, m, rest


def _unannotated(root, available, note):
    """Independent of the annotator's regex: a case-insensitive scan for any
    `/<skill>` naming a real, unshipped, non-operator skill outside a fenced
    block, not followed by the note (after its code span, if in one)."""
    import re
    known = set(bb.skill_manifest.skills())
    pat = re.compile(r"/((?:parallax|translate)-[a-z0-9-]*[a-z0-9])", re.I)
    bad = []
    for p, line, m, rest in _command_matches(root, pat):
        name = m.group(1).lower()
        if (name not in known or name in available
                or name in bb.HOUSE_VIEW_OPERATORS
                or line[:m.start()].endswith("](")
                or (m.start() and (line[m.start() - 1].isalnum()
                                   or line[m.start() - 1] in "/.~-_"))):
            continue
        if not rest.startswith(note):
            bad.append(f"{p}: {line.strip()[:90]}")
    return bad


def test_web_packages_mark_every_unavailable_command(web_build):
    _, unzipped = web_build
    avail = set(bb.WEB_SKILLS) | set(bb.skill_manifest.standalone_skills("release"))
    for d in sorted(unzipped.iterdir()):
        assert not _unannotated(d, avail, bb.WEB_NOTE), d.name


def test_plugin_bundle_marks_every_unavailable_command():
    root = Path(__file__).resolve().parents[3] / "plugin" / "skills"
    if not root.exists():
        pytest.skip("plugin bundle not built in this checkout")
    assert not _unannotated(root, set(bb.PLUGIN_SKILLS), bb.PLUGIN_NOTE)


_NOT_COMMANDS = {
    "host-note": "closing marker of the <!-- /host-note --> comment",
    "tmp": "the /tmp directory, named as a path hazard",
    "slash": "the `/slash` chaining syntax, named as a host primitive",
    "name": "the `/name` placeholder in the host-primitive table",
    "numeric": "the `.HK`/numeric ambiguity, not a command",
}


def _unresolved_commands(root, note):
    """Every `/<command>` outside a fenced block that is neither a manifest
    skill, followed by the note, nor in _NOT_COMMANDS."""
    import re
    known = set(bb.skill_manifest.skills()) | set(_NOT_COMMANDS)
    pat = re.compile(r"(?:^|(?<=[\s`(]))(?<!\]\()/([a-z][a-z0-9-]*)(?=[\s`).,;]|$)")
    return [f"{p}: /{m.group(1)}" for p, _, m, rest in _command_matches(root, pat)
            if m.group(1) not in known and not rest.startswith(note)]


def test_built_skills_route_only_to_commands_that_exist(web_build):
    plugin = Path(__file__).resolve().parents[3] / "plugin" / "skills"
    if plugin.exists():
        assert not _unresolved_commands(plugin, bb.PLUGIN_NOTE)
    _, unzipped = web_build
    for d in sorted(unzipped.iterdir()):
        assert not _unresolved_commands(d, bb.WEB_NOTE), d.name


def test_unresolved_command_scan_catches_a_private_route(tmp_path):
    skill = tmp_path / "parallax-should-i-buy" / "SKILL.md"
    skill.parent.mkdir()
    src = (Path(__file__).resolve().parents[3] / "plugin" / "skills"
           / "parallax-should-i-buy" / "SKILL.md")
    if not src.exists():
        pytest.skip("plugin bundle not built in this checkout")
    skill.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    assert not _unresolved_commands(tmp_path, bb.PLUGIN_NOTE)
    with skill.open("a", encoding="utf-8") as f:
        f.write("\nThen run /backtest.\n")
    assert _unresolved_commands(tmp_path, bb.PLUGIN_NOTE) == [f"{skill}: /backtest"]


def test_house_view_operators_match_the_manifest_family():
    family = {n for n in bb.skill_manifest.skills() if "house-view" in n}
    assert bb.HOUSE_VIEW_OPERATORS == family


def test_house_view_operator_mentions_are_not_marked():
    text = "Run /parallax-judge-house-view for the full report.\n"
    assert bb.annotate_unavailable_commands(text, set()) == text


def test_fenced_examples_are_not_marked():
    text = "```\n/parallax-desk-call-list --desk a\n```\nThen /parallax-desk-call-list.\n"
    out = bb.annotate_unavailable_commands(text, set())
    assert "/parallax-desk-call-list --desk a\n" in out
    assert f"Then /parallax-desk-call-list{bb.PLUGIN_NOTE}." in out


def test_link_targets_are_not_marked():
    text = "See [desk](/parallax-desk-call-list) and /parallax-desk-call-list.\n"
    out = bb.annotate_unavailable_commands(text, set())
    assert "](/parallax-desk-call-list)" in out
    assert out.count(bb.PLUGIN_NOTE) == 1


def test_web_due_diligence_names_only_workflows_claude_ai_offers(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "WEB_OUT_DIR", tmp_path)
    bb.build_web(["parallax-due-diligence"])
    with zipfile.ZipFile(tmp_path / "parallax-due-diligence.skill") as zf:
        text = zf.read("parallax-due-diligence/SKILL.md").decode()
    assert "white-label-stock-report" not in text
    assert "for a client-facing deliverable use /parallax-client-review." in text


def test_cost_bullets_follow_the_distribution():
    text = (bb.SKILLS_DIR / "_parallax" / "token-costs.md").read_text(encoding="utf-8")
    web = bb.filter_token_costs(text, set(bb.WEB_SKILLS))
    plugin = bb.filter_token_costs(text, set(bb.PLUGIN_SKILLS))
    assert "desk-call-list" not in web
    assert "/parallax-desk-call-list` (~69 tokens" in plugin
