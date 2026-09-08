"""Gates for `_parallax/manifest.json` and its reader.

Two jobs. First, prove the manifest still agrees with every consumer that has a
literal left (only `render_gate.py`, deliberately — see the reader docstring and
DECISIONS.md 2026-09-07). Second, stop the manifest rotting the way the literals
it replaced did: its key set is reconciled against the filesystem in BOTH
directions, so a new skill directory fails here until it has a row.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

SHARED = Path(__file__).resolve().parent
SKILLS = SHARED.parent
MANIFEST = SHARED / "manifest.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sm():
    return _load("sm_under_test", SHARED / "skill_manifest.py")


@pytest.fixture(scope="module")
def rg():
    return _load("rg_under_test", SHARED / "render_gate.py")


@pytest.fixture(scope="module")
def bb():
    return _load("bb_under_test", SHARED / "scripts" / "build_bundle.py")


# --- the one remaining literal -------------------------------------------------

def test_render_gate_anchors_match_manifest(sm, rg):
    """`render_gate.py` keeps its literal on purpose; this is what makes that safe.

    The gate is the last step of every skill on every host and has no other file
    dependency, so it must not gain one. Equality here gives the same mechanical
    trust a runtime read would, without the failure mode.
    """
    assert rg.SKILL_ANCHORS == sm.skill_anchors()


def test_gate_anchor_keys_are_the_prefix_stripped_skill_dirs(sm, rg):
    dirs = {p.parent.name for p in SKILLS.glob("*/SKILL.md")}
    for key in rg.SKILL_ANCHORS:
        assert f"parallax-{key}" in dirs, key


def test_manifest_anchors_compile_and_behave_identically(sm, rg):
    """Round-trip guard: JSON escaping must not alter a single pattern."""
    for key, patterns in sm.skill_anchors().items():
        live = rg.SKILL_ANCHORS[key]
        assert len(patterns) == len(live)
        for from_json, from_py in zip(patterns, live):
            assert from_json == from_py
            re.compile(from_json)  # must not raise


# --- build_bundle now reads the manifest --------------------------------------

def test_build_bundle_constants_come_from_the_manifest(sm, bb):
    assert bb.PLUGIN_SKILLS == sm.plugin_skills()
    assert bb.WEB_SKILLS == sm.web_skills()
    assert bb.WEB_DESCRIPTIONS == sm.web_descriptions()
    assert bb.RESOLUTION_EXEMPT_DOCS == sm.exempt_docs()


def test_flipped_constants_keep_their_original_types(bb):
    """`test_build_bundle.py` does `bb.PLUGIN_SKILLS + [...]`; a set would break it."""
    assert isinstance(bb.PLUGIN_SKILLS, list)
    assert isinstance(bb.WEB_SKILLS, list)
    assert isinstance(bb.WEB_DESCRIPTIONS, dict)
    assert isinstance(bb.RESOLUTION_EXEMPT_DOCS, set)


# --- anti-rot: the manifest must track the filesystem, both directions ---------

def test_manifest_covers_every_skill_directory(sm):
    on_disk = {p.parent.name for p in SKILLS.glob("*/SKILL.md")}
    in_manifest = set(sm.skills())
    assert in_manifest - on_disk == set(), "manifest rows with no SKILL.md"
    assert on_disk - in_manifest == set(), (
        "skill directories with no manifest row — rerun "
        "scripts/bootstrap_manifest.py and review the new rows"
    )


def test_web_rows_carry_a_capped_description(sm):
    for name, desc in sm.web_descriptions().items():
        assert desc.strip(), name
        assert len(desc) <= sm.WEB_DESCRIPTION_MAX, (name, len(desc))


def test_plugin_is_a_superset_of_web(sm):
    """A skill shipped to claude.ai but not the plugin would be unbuildable."""
    assert set(sm.web_skills()) <= set(sm.plugin_skills())


# --- the reader refuses a manifest it cannot trust -----------------------------

def _reader_on(tmp_path: Path, payload: dict):
    """Load a private copy of the reader pointed at a scratch manifest."""
    mod = _load(f"sm_{tmp_path.name}", SHARED / "skill_manifest.py")
    target = tmp_path / "manifest.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    mod.MANIFEST_PATH = target
    mod.reload()
    return mod


def test_missing_manifest_names_the_fix(tmp_path):
    mod = _load("sm_missing", SHARED / "skill_manifest.py")
    mod.MANIFEST_PATH = tmp_path / "absent.json"
    mod.reload()
    with pytest.raises(FileNotFoundError, match="bootstrap_manifest.py"):
        mod.skills()


def test_web_row_without_a_description_is_rejected(tmp_path):
    mod = _reader_on(tmp_path, {"skills": {"parallax-x": {"web": True}}, "exempt_docs": []})
    with pytest.raises(ValueError, match="no web_description"):
        mod.skills()


def test_over_cap_description_is_rejected(tmp_path):
    mod = _reader_on(
        tmp_path,
        {"skills": {"parallax-x": {"web": True, "web_description": "x" * 201}}, "exempt_docs": []},
    )
    with pytest.raises(ValueError, match="over the 200-char"):
        mod.skills()


def test_anchors_without_a_key_is_rejected(tmp_path):
    mod = _reader_on(
        tmp_path, {"skills": {"parallax-x": {"anchors": ["^x"]}}, "exempt_docs": []}
    )
    with pytest.raises(ValueError, match="anchors and anchors_key together"):
        mod.skills()


def test_empty_skills_object_is_rejected(tmp_path):
    mod = _reader_on(tmp_path, {"skills": {}, "exempt_docs": []})
    with pytest.raises(ValueError, match="non-empty"):
        mod.skills()


# --- the generator stays the only author --------------------------------------

def test_manifest_rows_and_anchors_are_in_sync():
    """`--check`'s two DERIVED properties: row coverage and gate anchors.

    It deliberately does NOT check the editorial fields. `build_bundle.py` reads
    those from the manifest, so re-deriving them from `build_bundle` would be a
    tautology that passes on a hand-edited value — which is exactly what an
    earlier version of this test did.
    """
    boot = _load("boot_under_test", SHARED / "scripts" / "bootstrap_manifest.py")
    assert MANIFEST.read_text(encoding="utf-8") == boot.render(boot.build())


def test_editorial_edits_are_preserved_not_reverted(tmp_path, monkeypatch):
    """A hand-edited description is a legitimate change, and must survive.

    The manifest is the authority for editorial fields. If the maintenance
    script re-derived them, every deliberate copy edit would silently revert.
    """
    boot = _load("boot_editorial", SHARED / "scripts" / "bootstrap_manifest.py")
    scratch = tmp_path / "manifest.json"
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data["skills"]["parallax-rebalance"]["web_description"] = "EDITED BY HAND"
    scratch.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    monkeypatch.setattr(boot, "MANIFEST", scratch)
    rebuilt = boot.build()
    assert rebuilt["skills"]["parallax-rebalance"]["web_description"] == "EDITED BY HAND"


def test_manifest_declares_its_authority():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["_authority"]["kind"] == "registry"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["_authority"]["verified"])
