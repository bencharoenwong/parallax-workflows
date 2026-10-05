"""build-skills.sh must refuse to package a skill whose description exceeds
claude.ai's 200-character cap, and must package the translate skills."""
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


def test_over_cap_description_blocks_packaging(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    shutil.copy(SCRIPT, root / "build-skills.sh")
    skill = root / "long-desc-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        f"---\nname: long-desc-skill\ndescription: {'x' * 201}\n---\n\nbody\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    res = _run(root / "build-skills.sh", out, "long-desc-skill")
    assert res.returncode != 0
    assert "201 chars" in res.stderr
    assert not (out / "long-desc-skill.skill").exists()
