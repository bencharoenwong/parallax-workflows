"""build-skills.sh packaging: which skills build by default, what a package
may contain, and that a failed package fails the run."""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_bundle as bb
from canary_fixture import hermetic_extra_terms  # noqa: F401 -- autouse fixture

SKILLS = Path(__file__).resolve().parents[2]
SCRIPT = SKILLS / "build-skills.sh"
# The subprocess reads the real home-directory file; the autouse fixture only
# re-points the in-process attribute, so capture the real path before it runs.
REAL_EXTRA_CANARY_FILE = bb.EXTRA_CANARY_FILE

pytestmark = pytest.mark.skipif(shutil.which("zip") is None, reason="zip not on PATH")


def _env(out_dir):
    env = {**os.environ, "SKILL_BUILD_OUT_DIR": str(out_dir)}
    if not REAL_EXTRA_CANARY_FILE.is_file():
        env[bb.PARTIAL_SCAN_ENV] = "1"
    return env


def _run(script, out_dir, *args):
    return subprocess.run(["bash", str(script), "--no-lint", *args],
                          capture_output=True, text=True, env=_env(out_dir))


def test_manifest_standalone_tiers():
    sm = bb.skill_manifest
    assert sm.standalone_skills("release") == ["translate-chinese-finance", "translate-thai-finance"]
    assert sm.standalone_skills("beta") == ["parallax-cio-letter-prep"]
    assert sm.standalone_skills("held") == ["translate-arabic-finance", "translate-vietnamese-finance"]


def test_default_build_is_the_release_tier_only(tmp_path):
    res = _run(SCRIPT, tmp_path)
    assert res.returncode == 0, res.stderr
    assert sorted(p.name for p in tmp_path.glob("*.skill")) == [
        "translate-chinese-finance.skill", "translate-thai-finance.skill"]


def test_held_skill_builds_only_when_named_and_warns(tmp_path):
    res = _run(SCRIPT, tmp_path, "translate-vietnamese-finance")
    assert res.returncode == 0, res.stderr
    assert "held" in res.stderr and "translate-vietnamese-finance" in res.stderr
    assert (tmp_path / "translate-vietnamese-finance.skill").is_file()


def test_packages_ship_no_tests_or_maintenance_scripts(tmp_path):
    res = _run(SCRIPT, tmp_path, "translate-chinese-finance", "translate-thai-finance")
    assert res.returncode == 0, res.stderr
    for pkg in tmp_path.glob("*.skill"):
        names = zipfile.ZipFile(pkg).namelist()
        assert not [n for n in names if "/tests/" in n or Path(n).name.startswith("test_")
                    or Path(n).name == "conftest.py" or "normalize_runtime" in n], pkg.name
        assert any(n.endswith("references/translation_common.py") for n in names)


def test_verify_package_rejects_dev_files(tmp_path):
    pkg = tmp_path / "demo"
    (pkg / "references").mkdir(parents=True)
    (pkg / "SKILL.md").write_text("ok\n", encoding="utf-8")
    bb.verify_package(pkg)
    (pkg / "references" / "test_x.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(bb.BuildError, match="test_x.py"):
        bb.verify_package(pkg)


def _synthetic_root(tmp_path, body):
    root = tmp_path / "skills"
    root.mkdir()
    shutil.copy(SCRIPT, root / "build-skills.sh")
    (root / "_parallax").symlink_to(SKILLS / "_parallax")
    skill = root / "parallax-demo-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        f"---\nname: parallax-demo-skill\ndescription: Demo.\n---\n\n{body}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "skills/parallax-demo-skill"], cwd=tmp_path, check=True)
    return root


def test_leak_scan_blocks_the_package(tmp_path):
    term = bb.load_canary_terms()[0]
    root = _synthetic_root(tmp_path, f"mentions {term} here")
    out = tmp_path / "out"
    res = _run(root / "build-skills.sh", out, "parallax-demo-skill")
    assert res.returncode != 0
    assert "term scan failed" in res.stderr
    assert term not in res.stdout
    assert not (out / "parallax-demo-skill.skill").exists()


def test_a_failed_package_fails_the_run(tmp_path):
    res = _run(SCRIPT, tmp_path, "no-such-skill")
    assert res.returncode != 0


def test_failed_zip_fails_the_run_and_leaves_no_package(tmp_path):
    root = _synthetic_root(tmp_path, "clean body")
    out = tmp_path / "out"
    out.mkdir()
    (out / "parallax-demo-skill.skill").write_text("old package", encoding="utf-8")
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "zip").write_text("#!/bin/sh\nexit 12\n", encoding="utf-8")
    (shim / "zip").chmod(0o755)
    env = _env(out)
    env["PATH"] = f"{shim}:{env['PATH']}"
    res = subprocess.run(["bash", str(root / "build-skills.sh"), "--no-lint", "parallax-demo-skill"],
                         capture_output=True, text=True, env=env)
    assert res.returncode != 0
    assert not (out / "parallax-demo-skill.skill").exists()


def test_trailing_slash_names_the_same_skill(tmp_path):
    res = _run(SCRIPT, tmp_path, "translate-vietnamese-finance/")
    assert res.returncode == 0, res.stderr
    assert "held" in res.stderr
    names = zipfile.ZipFile(tmp_path / "translate-vietnamese-finance.skill").namelist()
    assert any(n.endswith("references/translation_common.py") for n in names)


def test_tracked_symlink_fails_the_package(tmp_path):
    root = _synthetic_root(tmp_path, "clean body")
    outside = tmp_path / "outside.txt"
    outside.write_text("private\n", encoding="utf-8")
    (root / "parallax-demo-skill" / "link.md").symlink_to(outside)
    subprocess.run(["git", "add", "skills/parallax-demo-skill/link.md"], cwd=tmp_path, check=True)
    out = tmp_path / "out"
    res = _run(root / "build-skills.sh", out, "parallax-demo-skill")
    assert res.returncode != 0
    assert not (out / "parallax-demo-skill.skill").exists()


def test_term_in_a_file_name_fails_the_scan(tmp_path):
    term = bb.load_canary_terms()[0]
    (tmp_path / f"notes-{term}.md").write_text("clean\n", encoding="utf-8")
    with pytest.raises(bb.BuildError, match="term scan"):
        bb.canary_scan(tmp_path)


@pytest.mark.parametrize("variant", ["fullwidth", "zero_width", "soft_hyphen"])
def test_scan_matches_unicode_variants(tmp_path, variant):
    term = next(t for t in bb.load_canary_terms() if t.isascii() and len(t) > 3)
    if variant == "fullwidth":
        text = "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in term)
    else:
        sep = "​" if variant == "zero_width" else "­"
        text = term[:2] + sep + term[2:]
    (tmp_path / "a.md").write_text(f"see {text}\n", encoding="utf-8")
    with pytest.raises(bb.BuildError, match="term scan"):
        bb.canary_scan(tmp_path)


@pytest.mark.parametrize("name,data", [
    ("pack.docx", b"PK\x03\x04binary"),
    ("notes.md", "utf16 text".encode("utf-16")),
    ("nb.ipynb", b"{}"),
])
def test_verify_package_rejects_non_text_files(tmp_path, name, data):
    (tmp_path / "SKILL.md").write_text("ok\n", encoding="utf-8")
    (tmp_path / name).write_bytes(data)
    with pytest.raises(bb.BuildError):
        bb.verify_package(tmp_path)


@pytest.mark.parametrize("rel", ["test/check.py", "__tests__/a.md", "scripts/foo_test.py",
                                 "tests.py", "PLANS.md", "HANDOFF.md", "fixtures/a.md"])
def test_dev_paths_are_development_files(rel):
    assert bb.is_dev_path(rel)


@pytest.mark.parametrize("rel", ["SKILL.md", "references/validate-translation.py",
                                 "scripts/contribution.py", "references/testing-notes.md"])
def test_runtime_paths_are_not_development_files(rel):
    assert not bb.is_dev_path(rel)


def test_skill_with_only_development_files_names_the_real_problem(tmp_path):
    root = _synthetic_root(tmp_path, "body")
    (root / "parallax-demo-skill" / "tests").mkdir()
    (root / "parallax-demo-skill" / "tests" / "test_x.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "rm", "-q", "--cached", "skills/parallax-demo-skill/SKILL.md"],
                   cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "skills/parallax-demo-skill/tests"], cwd=tmp_path, check=True)
    res = _run(root / "build-skills.sh", tmp_path / "out", "parallax-demo-skill")
    assert res.returncode != 0
    assert "no tracked SKILL.md" in res.stderr
