#!/usr/bin/env python3
"""Tests for spec-normalize.py — frontmatter normalization to agentskills.io spec."""
import importlib.util
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("spec_normalize", HERE / "spec-normalize.py")
sn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sn)

PORTED = """---
name: fixture-skill
description: Does a thing. NOT for other things (/other-skill).
user-invocable: true
argument-hint: "[target]"
negative-triggers:
  - other things → /other-skill
  - third thing → /third-skill
---

# Fixture Skill

## Overview

Body text.
"""

CLEAN = """---
name: fixture-skill
description: Does a thing.
license: Apache-2.0
metadata:
  author: bc
---

# Fixture Skill

Body.
"""

WITH_SECTION = """---
name: fixture-skill
description: Does a thing.
negative-triggers:
  - other things → /other-skill
  - new thing → /new-skill
---

# Fixture Skill

## When not to use

- other things → /other-skill

## Steps
"""


def test_drops_client_fields_and_folds_triggers():
    out = sn.normalize_text(PORTED)
    assert "user-invocable" not in out
    assert "argument-hint" not in out
    assert "negative-triggers" not in out
    assert "## When not to use" in out
    assert "- other things → /other-skill" in out
    assert "- third thing → /third-skill" in out
    # section lands after the H1, before existing content order is disturbed
    assert out.index("# Fixture Skill") < out.index("## When not to use")
    assert "description: Does a thing." in out


def test_clean_file_is_byte_identical():
    assert sn.normalize_text(CLEAN) == CLEAN


def test_idempotent():
    once = sn.normalize_text(PORTED)
    assert sn.normalize_text(once) == once


def test_existing_section_appends_only_missing_items():
    out = sn.normalize_text(WITH_SECTION)
    assert out.count("- other things → /other-skill") == 1
    assert "- new thing → /new-skill" in out
    # appended inside the section, before the next heading
    assert out.index("- new thing") < out.index("## Steps")


def test_malformed_frontmatter_returns_none():
    assert sn.normalize_text("no frontmatter here\n") is None
    assert sn.normalize_text("---\nname: x\nnever terminated\n") is None


def test_normalized_output_passes_spec_validate(tmp_path):
    d = tmp_path / "fixture-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(sn.normalize_text(PORTED), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(HERE / "spec-validate.py"), str(d)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_cli_rewrites_in_place(tmp_path):
    d = tmp_path / "fixture-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(PORTED, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(HERE / "spec-normalize.py"), str(d)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "normalized" in r.stdout
    assert "negative-triggers" not in (d / "SKILL.md").read_text(encoding="utf-8")
