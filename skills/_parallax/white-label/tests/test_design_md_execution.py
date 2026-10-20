"""Execution and result contracts for the optional local DESIGN.md linter."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validator


@pytest.fixture
def configured_cli(design_md_cli):
    return design_md_cli


def test_no_configuration_never_starts_a_process(monkeypatch):
    monkeypatch.delenv('PARALLAX_DESIGN_MD_CLI', raising=False)
    monkeypatch.delenv('PARALLAX_DESIGN_MD_SHA256', raising=False)
    monkeypatch.setattr(validator.DesignMdValidator, '_availability_cache', None, raising=False)
    monkeypatch.setattr('shutil.which', lambda name: '/usr/bin/' + name)
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout='{"findings": []}')
    monkeypatch.setattr('subprocess.run', run)
    result = validator.DesignMdValidator.lint('# private draft')
    assert result['status'] == 'skipped'
    assert result['available'] is False
    assert calls == []


def test_only_the_verified_executable_receives_the_input(configured_cli, monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert command[0] == str(configured_cli)
        assert command[1] == 'lint'
        assert Path(command[2]).read_text() == '# sample brand'
        return SimpleNamespace(returncode=0, stdout='{"findings": []}')
    monkeypatch.setattr('subprocess.run', run)
    result = validator.DesignMdValidator.lint('# sample brand')
    assert result['status'] == 'pass'
    assert len(calls) == 1
    assert not Path(calls[0][2]).exists()


def test_changed_executable_is_rejected_after_availability_check(configured_cli, monkeypatch):
    monkeypatch.setattr('subprocess.run', lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='{"findings": []}'))
    assert validator.DesignMdValidator.is_available()
    configured_cli.write_text('#!/bin/sh\necho changed\n')
    calls = []
    monkeypatch.setattr('subprocess.run', lambda *args, **kwargs: calls.append(args))
    result = validator.DesignMdValidator.lint('# sample')
    assert result['available'] is False
    assert result['status'] == 'skipped'
    assert calls == []


@pytest.mark.parametrize('payload', [None, [], 'text', {}, {'findings': None}, {'findings': 'bad'}, {'findings': [False]}])
def test_malformed_result_never_passes(configured_cli, monkeypatch, payload):
    monkeypatch.setattr('subprocess.run', lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(payload)))
    result = validator.DesignMdValidator.lint('# sample')
    assert result['status'] == 'skipped'
    assert result['available'] is True
    assert result['findings'] == []


@pytest.mark.parametrize('invalid', ['relative', 'missing_hash', 'wrong_hash', 'invalid_hash', 'missing_file', 'not_executable', 'directory'])
def test_invalid_dependency_configuration_skips_without_execution(configured_cli, monkeypatch, invalid):
    if invalid == 'relative':
        monkeypatch.setenv('PARALLAX_DESIGN_MD_CLI', 'tools/design-md')
    elif invalid == 'missing_hash':
        monkeypatch.delenv('PARALLAX_DESIGN_MD_SHA256')
    elif invalid == 'wrong_hash':
        monkeypatch.setenv('PARALLAX_DESIGN_MD_SHA256', '0' * 64)
    elif invalid == 'invalid_hash':
        monkeypatch.setenv('PARALLAX_DESIGN_MD_SHA256', 'z' * 64)
    elif invalid == 'missing_file':
        configured_cli.unlink()
    elif invalid == 'not_executable':
        configured_cli.chmod(0o644)
    else:
        monkeypatch.setenv('PARALLAX_DESIGN_MD_CLI', str(configured_cli.parent))
    calls = []
    monkeypatch.setattr('subprocess.run', lambda *args, **kwargs: calls.append(args))
    result = validator.DesignMdValidator.lint('# sample')
    assert result['status'] == 'skipped'
    assert result['available'] is False
    assert calls == []


def test_local_executable_in_a_path_with_spaces_runs_end_to_end(tmp_path, monkeypatch):
    command = tmp_path / 'local CLI'
    command.write_text(
        '#!' + sys.executable + '\n'
        'import json,sys\n'
        'from pathlib import Path\n'
        'assert sys.argv[1] == "lint"\n'
        'assert sys.argv[3:] == ["--format", "json"]\n'
        'assert Path(sys.argv[2]).read_text() == "# fixture brand"\n'
        'print(json.dumps({"findings": []}))\n'
    )
    command.chmod(0o755)
    monkeypatch.setenv('PARALLAX_DESIGN_MD_CLI', str(command))
    monkeypatch.setenv('PARALLAX_DESIGN_MD_SHA256', hashlib.sha256(command.read_bytes()).hexdigest())
    result = validator.DesignMdValidator.lint('# fixture brand')
    assert result['status'] == 'pass'
    assert result['available'] is True
    assert result['raw_exit_code'] == 0


def test_temp_directory_failure_skips_optional_lint(configured_cli, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError('synthetic private path')
    monkeypatch.setattr('tempfile.TemporaryDirectory', unavailable)
    result = validator.DesignMdValidator.lint('# sample')
    assert result['status'] == 'skipped'
    assert result['available'] is True
    assert 'synthetic private path' not in result['note']
