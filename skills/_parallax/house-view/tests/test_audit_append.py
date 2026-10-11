"""Tests for the audit_append.py command (loader.md §6)."""
from __future__ import annotations

import builtins
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HOUSE_VIEW_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import audit_append  # noqa: E402
import audit_chain  # noqa: E402

_counter = iter(range(1, 10_000))


def _row(**over) -> dict:
    row = {"schema_version": 1, "ts": "2026-10-11T05:50:00Z", "view_id": None,
           "version_id": None, "skill": "parallax-should-i-buy", "action": "consume",
           "applied": False, "applied_reason": "no_view",
           "query_summary": "/parallax-should-i-buy AAPL.O"}
    row.update(over)
    return row


@pytest.fixture
def work(tmp_path, monkeypatch):
    """A session cwd with its .parallax-render dir, and a scratch view dir."""
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(tmp_path / "hv"))
    (tmp_path / ".parallax-render").mkdir()
    return tmp_path


def _draft(work: Path, content) -> str:
    path = work / ".parallax-render" / f"audit-{next(_counter):08x}.json"
    path.parent.mkdir(exist_ok=True)  # the helper removes it once empty
    path.write_bytes(content if isinstance(content, bytes) else json.dumps(content).encode())
    return str(path)


def test_appends_chained_rows_and_deletes_each_draft(work, capsys):
    first, second = _draft(work, _row()), _draft(work, _row(ts="2026-10-11T05:51:00Z"))
    assert audit_append.main(["--input", first]) == 0
    assert audit_append.main(["--input", second]) == 0
    log = work / "hv" / "audit.jsonl"
    rows = audit_chain.verify_chain(log)
    assert rows[0]["chain_root"] is True
    assert rows[1]["prev_entry_hash"] == audit_chain.compute_entry_hash(rows[0])
    assert not Path(first).exists() and not Path(second).exists()
    assert ((work / "hv").stat().st_mode & 0o777) == 0o700
    assert json.loads(capsys.readouterr().out.splitlines()[0])["appended_to"] == str(log)


def test_default_dir_without_env(work, monkeypatch):
    monkeypatch.delenv("PARALLAX_HOUSE_VIEW_DIR")
    monkeypatch.setattr(audit_append, "DEFAULT_VIEW_DIR", work / "default")
    assert audit_append.main(["--input", _draft(work, _row())]) == 0
    assert (work / "default" / "audit.jsonl").exists()


def test_tightens_an_existing_loose_dir(work):
    (work / "hv").mkdir(mode=0o755)
    (work / "hv").chmod(0o755)
    assert audit_append.main(["--input", _draft(work, _row())]) == 0
    assert ((work / "hv").stat().st_mode & 0o777) == 0o700


def test_symlinked_view_dir_target_mode_is_left_alone(work, monkeypatch):
    target = work / "real"
    target.mkdir(mode=0o755)
    target.chmod(0o755)
    (work / "hvlink").symlink_to(target, target_is_directory=True)
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(work / "hvlink"))
    assert audit_append.main(["--input", _draft(work, _row())]) == 0
    assert (target.stat().st_mode & 0o777) == 0o755


@pytest.mark.parametrize("content", [
    b"not json",
    b"[1]",
    b'{"ts": "x"}',
    b"\xff\xfe",
    b"[" * 50_000,
    json.dumps(_row(query_summary="x" * 70_000)).encode(),
    _row(chain_root=True),
    _row(prev_entry_hash="0" * 64),
])
def test_bad_rows_exit_2_and_write_nothing(work, capsys, content):
    assert audit_append.main(["--input", _draft(work, content)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("[audit-append] ERROR") and "Traceback" not in err
    assert not (work / "hv" / "audit.jsonl").exists()


@pytest.mark.parametrize("args", [[], ["--input"], ["row.json"], ["--input", "a", "b"]])
def test_usage_errors_exit_2(work, capsys, args):
    assert audit_append.main(args) == 2
    assert "usage" in capsys.readouterr().err


@pytest.mark.parametrize("rel", ["holdings.json", ".parallax-render/audit-1.json",
                                 ".parallax-render/should-i-buy-0000000a.md"])
def test_refuses_paths_that_are_not_audit_drafts_and_keeps_them(work, capsys, rel):
    path = work / rel
    path.write_text(json.dumps(_row()))
    assert audit_append.main(["--input", str(path)]) == 2
    assert "cannot read the row draft" in capsys.readouterr().err
    assert path.exists()


def test_refuses_to_chain_onto_a_broken_log(work, capsys):
    assert audit_append.main(["--input", _draft(work, _row())]) == 0
    log = work / "hv" / "audit.jsonl"
    with open(log, "a") as fh:  # a raw row inside the chained section
        fh.write(json.dumps({"action": "consume", "raw": True}) + "\n")
    before = log.read_text()
    assert audit_append.main(["--input", _draft(work, _row(ts="2026-10-11T06:00:00Z"))]) == 4
    assert "fails verification" in capsys.readouterr().err
    assert log.read_text() == before


def test_missing_chain_dependency_exits_3(work, capsys, monkeypatch):
    real_import = builtins.__import__

    def no_audit_chain(name, *a, **k):
        if name == "audit_chain":
            raise ImportError("No module named 'rfc8785'")
        return real_import(name, *a, **k)

    monkeypatch.delitem(sys.modules, "audit_chain", raising=False)
    monkeypatch.setattr(builtins, "__import__", no_audit_chain)
    assert audit_append.main(["--input", _draft(work, _row())]) == 3
    assert "unavailable on this host" in capsys.readouterr().err
    assert not (work / "hv" / "audit.jsonl").exists()


def test_other_failures_exit_1_without_traceback(work, capsys, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(audit_chain, "append_entry", boom)
    assert audit_append.main(["--input", _draft(work, _row())]) == 1
    assert "OSError: disk full" in capsys.readouterr().err


def test_documented_command_runs_in_bash_with_hostile_text(work):
    """loader.md §6, run as written: quotes, $(...) and backticks in a value
    stay data, because the row is a file and never part of the command."""
    loader = (HOUSE_VIEW_DIR / "loader.md").read_text(encoding="utf-8")
    blocks = [b for b in re.findall(r"^```bash\n(.*?)^```$", loader, re.S | re.M)
              if "audit_append.py" in b]
    assert len(blocks) == 1, "loader §6 must document exactly one append command"
    command = blocks[0].strip()
    assert "\n" not in command and len(command) < 300
    for banned in ("$(", "${", "<<", "|", "`", '{"'):
        assert banned not in command, f"{banned!r} in the documented command"
    assert command.endswith('--input "<draft-path>"')
    text = "McDonald's $(touch PWNED) L'Oreal `id` ${HOME} {\"x\": 1}"
    draft = _draft(work, _row(query_summary=text))
    skill_dir = HOUSE_VIEW_DIR.parent.parent / "parallax-should-i-buy"
    script = command.replace("<skill-dir>", str(skill_dir)).replace("<draft-path>", draft)
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          cwd=work, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert audit_chain.verify_chain(work / "hv" / "audit.jsonl")[-1]["query_summary"] == text
    assert not (work / "PWNED").exists() and not Path(draft).exists()


def test_no_documented_bash_block_puts_json_in_a_heredoc():
    """Claude Code checks a heredoc body and refuses `{` followed by a quote
    (conventions §14.1), so JSON must reach a helper as a file, never inline."""
    skills_root = HOUSE_VIEW_DIR.parent.parent
    offenders = []
    for md in skills_root.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        for m in re.finditer(r"^\s*```(?:bash|sh)\n(.*?)^\s*```", text, re.S | re.M):
            if "<<" in m.group(1) and re.search(r"\{[^}]*['\"]", m.group(1)):
                offenders.append(f"{md.relative_to(skills_root)}:{text[:m.start()].count(chr(10)) + 1}")
    assert offenders == []
