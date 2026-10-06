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
