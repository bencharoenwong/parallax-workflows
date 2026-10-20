"""Literal-path regression for the policy/coverage draft commands.

Claude Code's permission checker refuses a Bash command holding a shell
variable or a `mktemp` expansion even inside its own sandbox (conventions
§14.1), so every documented `adaptation.py` / `coverage_check.py` /
`reconcile.py` command across the client-policy docs must be one line with
every path written literally. This file extracts each documented command
SPAN (never the surrounding prose) from the four converted docs and runs it
through bash with a real draft file at the literal path it names, mirroring
`test_render_gate.py`'s `test_gate_commands_pass_the_report_by_file`. A
leftover `mktemp`, `${...}` or `$VAR` in the doc would expand to an empty or
wrong value and the helper would exit on a read/parse failure instead of
succeeding.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
CLIENT_POLICY_DIR = HERE.parent
SKILLS_ROOT = CLIENT_POLICY_DIR.parent.parent  # client-policy -> _parallax -> skills
FIXTURES = HERE / "fixtures"

CLIENT_REVIEW_DIR = SKILLS_ROOT / "parallax-client-review"
REBALANCE_DIR = SKILLS_ROOT / "parallax-rebalance"

DOCS = {
    "policy-loader.md": CLIENT_POLICY_DIR / "policy-loader.md",
    "client-review/SKILL.md": CLIENT_REVIEW_DIR / "SKILL.md",
    "rebalance/SKILL.md": REBALANCE_DIR / "SKILL.md",
    "policy-reconciliation.md": REBALANCE_DIR / "references" / "policy-reconciliation.md",
}
# policy-loader.md is JIT-loaded by both consumer skills; either skill-dir
# resolves its relative `../_parallax/...` paths identically, so the test
# picks one per doc rather than re-running the same command under both.
SKILL_DIR_FOR_DOC = {
    "policy-loader.md": CLIENT_REVIEW_DIR,
    "client-review/SKILL.md": CLIENT_REVIEW_DIR,
    "rebalance/SKILL.md": REBALANCE_DIR,
    "policy-reconciliation.md": REBALANCE_DIR,
}

# A documented helper INVOCATION: an inline backtick span, or a bare line
# inside a fenced ```-block, that names one of the three helpers (optionally
# followed by a closing quote) and then whitespace plus either `--` or a
# trailing backslash continuation. A bare mention with no flags, like
# "S1/S2 math via `adaptation.py` only", never matches. The span is captured
# exactly as written, so an unprefixed, unquoted or line-continued command
# reaches the exec test below and fails there.
_FENCED_BLOCK = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
_INLINE_SPAN = re.compile(r"`([^`\n]+)`")
_INVOCATION = re.compile(r'(?:adaptation|coverage_check|reconcile)\.py"?[ \t]+(?:--|\\$)')


def _command_spans(text: str) -> list[str]:
    fenced_lines = [
        line for block in _FENCED_BLOCK.findall(text) for line in block.splitlines()
    ]
    # Outside fences, a bare line starting with `python3` is itself a command
    # span; any other line contributes only its inline backtick spans.
    unfenced = []
    for line in _FENCED_BLOCK.sub("\n", text).splitlines():
        if line.strip().startswith("python3"):
            unfenced.append(line)
        else:
            unfenced.extend(_INLINE_SPAN.findall(line))
    return [span.strip() for span in fenced_lines + unfenced if _INVOCATION.search(span.strip())]


# --------------------------------------------------------------------------
# Exec: run each documented command through bash with a real draft file.
# --------------------------------------------------------------------------

_HEX = "0a1b2c3d"


def _draft(tmp_path: Path, label: str, ext: str, content: str) -> Path:
    d = tmp_path / "with space" / ".parallax-policy"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{label}-{_HEX}.{ext}"
    path.write_text(content, encoding="utf-8")
    return path


_RECONCILE_PAYLOAD = {
    "basis": "sleeve",
    "holdings": [
        {"symbol": "AAA.X", "weight": 0.5, "coefficient": 3.0},
        {"symbol": "BBB.X", "weight": 0.3, "coefficient": 2.0},
        {"symbol": "CCC.X", "weight": 0.2, "coefficient": 1.0},
    ],
    "position_cap": 0.6,
    "bands": [{"dimension": "region", "key": "north", "symbols": ["AAA.X", "BBB.X"], "max": 0.7}],
    "turnover_penalty": 0.0,
}


def _placeholders(tmp_path: Path) -> dict[str, str]:
    policy = _draft(tmp_path, "policy", "yaml", (FIXTURES / "policy_full.yaml").read_text())
    exposures = _draft(tmp_path, "exposures", "json", (FIXTURES / "exposures_sample.json").read_text())
    tilts = _draft(tmp_path, "tilts", "json", (FIXTURES / "view_tilts_sample.json").read_text())
    portfolio_sectors = _draft(tmp_path, "portfolio-sectors", "json", json.dumps({"Technology": 1.0}))
    redundancy_sectors = _draft(tmp_path, "redundancy-sectors", "json", json.dumps({"Technology": 1.0}))
    holdings = _draft(tmp_path, "holdings", "json", json.dumps(["AAPL.O"]))
    reconcile_payload = _draft(tmp_path, "reconcile", "json", json.dumps(_RECONCILE_PAYLOAD))
    return {
        "<comparison-date>": "2026-10-16",
        "<policy-path>": str(policy),
        "<exposures-path>": str(exposures),
        "<tilts-path>": str(tilts),
        "<portfolio-sectors-path>": str(portfolio_sectors),
        "<redundancy-sectors-path>": str(redundancy_sectors),
        "<holdings-path>": str(holdings),
        "<reconcile-payload-path>": str(reconcile_payload),
    }


def _which_helper(command: str) -> str:
    for helper in ("adaptation.py", "coverage_check.py", "reconcile.py"):
        if helper in command:
            return helper
    raise AssertionError(f"no known helper in command: {command!r}")


def _run(command: str, skill_dir: Path, placeholders: dict[str, str]) -> subprocess.CompletedProcess:
    script = command.replace("<skill-dir>", str(skill_dir))
    for placeholder, path in placeholders.items():
        script = script.replace(placeholder, path)
    assert "<" not in script, f"unsubstituted placeholder remains: {script!r}"
    # reconcile.py imports scipy; a cold scipy import under full-suite load can exceed 30s.
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=180,
    )


@pytest.mark.parametrize("name", sorted(DOCS))
def test_documented_commands_run_against_a_real_literal_draft(name, tmp_path):
    """Every documented command, run exactly as written with its placeholders
    substituted for real draft files, succeeds -- proving no `$VAR` is left
    for bash to expand into an empty or wrong path."""
    doc = DOCS[name]
    skill_dir = tmp_path / "with space" / SKILL_DIR_FOR_DOC[name].name
    skill_dir.parent.mkdir(parents=True, exist_ok=True)
    skill_dir.symlink_to(SKILL_DIR_FOR_DOC[name], target_is_directory=True)
    placeholders = _placeholders(tmp_path)
    spans = _command_spans(doc.read_text(encoding="utf-8"))
    assert spans
    ran = 0
    for command in spans:
        helper = _which_helper(command)
        proc = _run(command, skill_dir, placeholders)
        ran += 1
        if helper == "adaptation.py":
            assert proc.returncode == 0, f"{name}: {command!r}: {proc.stderr}"
            payload = json.loads(proc.stdout)
            assert "fallback_tier" in payload, f"{name}: {command!r}: {payload}"
        elif helper == "coverage_check.py":
            assert proc.returncode == 0, f"{name}: {command!r}: {proc.stderr}"
            payload = json.loads(proc.stdout)
            assert "verdict" in payload, f"{name}: {command!r}: {payload}"
        else:  # reconcile.py — status depends on scipy availability, but a
            # broken literal path can only produce "invalid_input" (the one
            # status reconcile.py's CLI emits on a read/parse failure).
            payload = json.loads(proc.stdout)
            assert payload.get("status") != "invalid_input", f"{name}: {command!r}: {payload}"
    assert ran >= 1
