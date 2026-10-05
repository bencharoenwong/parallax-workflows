"""build-skills.sh must refuse to package a translate-*-finance skill whose
description exceeds claude.ai's 200-character cap, must package the translate
skills, and must leave every other skill's build unaffected."""
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml

SKILLS = Path(__file__).resolve().parents[2]
SCRIPT = SKILLS / "build-skills.sh"
TRANSLATE = [
    "translate-arabic-finance",
    "translate-chinese-finance",
    "translate-thai-finance",
    "translate-vietnamese-finance",
]

pytestmark = pytest.mark.skipif(shutil.which("zip") is None, reason="zip not on PATH")


def _run(script, out_dir, *names):
    return subprocess.run(
        ["bash", str(script), "--no-lint", *names],
        capture_output=True, text=True,
        env={**os.environ, "SKILL_BUILD_OUT_DIR": str(out_dir)},
    )


def test_translate_skills_package_within_cap(tmp_path):
    res = _run(SCRIPT, tmp_path, *TRANSLATE)
    assert res.returncode == 0, res.stderr
    for name in TRANSLATE:
        with zipfile.ZipFile(tmp_path / f"{name}.skill") as zf:
            text = zf.read(f"{name}/SKILL.md").decode("utf-8")
        desc = yaml.safe_load(text.split("---\n", 2)[1])["description"]
        assert 0 < len(desc) <= 200, (name, len(desc))


def _skill_root(tmp_path, *skills):
    root = tmp_path / "skills"
    root.mkdir()
    shutil.copy(SCRIPT, root / "build-skills.sh")
    for name, desc_len in skills:
        d = root / name
        d.mkdir()
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {'x' * desc_len}\n---\n\nbody\n",
            encoding="utf-8",
        )
    return root


def test_over_cap_translate_description_blocks_packaging(tmp_path):
    root = _skill_root(tmp_path, ("translate-test-finance", 201))
    out = tmp_path / "out"
    res = _run(root / "build-skills.sh", out, "translate-test-finance")
    assert res.returncode != 0
    assert "201 chars" in res.stderr
    assert not (out / "translate-test-finance.skill").exists()


def test_over_cap_non_translate_skill_still_packages(tmp_path):
    root = _skill_root(tmp_path, ("long-desc-skill", 201))
    out = tmp_path / "out"
    res = _run(root / "build-skills.sh", out, "long-desc-skill")
    assert res.returncode == 0, res.stderr
    assert (out / "long-desc-skill.skill").exists()


def test_private_beta_cio_letter_prep_still_builds(tmp_path):
    res = _run(SCRIPT, tmp_path, "parallax-cio-letter-prep")
    assert res.returncode == 0, res.stderr
    assert (tmp_path / "parallax-cio-letter-prep.skill").exists()


def test_mixed_run_not_blocked_by_non_translate_skill(tmp_path):
    res = _run(SCRIPT, tmp_path, "translate-thai-finance", "parallax-cio-letter-prep")
    assert res.returncode == 0, res.stderr
    assert (tmp_path / "translate-thai-finance.skill").exists()
    assert (tmp_path / "parallax-cio-letter-prep.skill").exists()
