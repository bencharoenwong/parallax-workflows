from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest
import yaml


WHITE_LABEL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WHITE_LABEL_DIR))


def _draft(name: str, color: str) -> dict:
    return {
        "client_name": name,
        "extracted_at": "2026-08-29T00:00:00Z",
        "source": {"type": "wizard", "reference": f"synthetic:{name}"},
        "colors": {
            "primary": {"hex": color},
            "background": {"hex": "#FFFFFF"},
            "text": {"hex": "#111111"},
        },
        "fonts": {"header": {"name": "Arial"}},
        "confidence_scores": {"colors.primary": 1.0},
    }


def _live_bytes(root: Path) -> dict[str, bytes]:
    return {
        name: (root / name).read_bytes()
        for name in ("config.yaml", "DESIGN.md", "audit.jsonl")
        if (root / name).exists()
    }


def _assert_one_coherent_commit(root: Path) -> str:
    config = yaml.safe_load((root / "config.yaml").read_text())
    design = (root / "DESIGN.md").read_bytes()
    entries = [json.loads(line) for line in (root / "audit.jsonl").read_text().splitlines()]
    entry = entries[-1]
    config_hash = hashlib.sha256(
        yaml.safe_dump(config["branding"], sort_keys=True).encode()
    ).hexdigest()
    assert entry["config_hash"] == config_hash
    assert entry["design_md_hash"] == hashlib.sha256(design).hexdigest()
    assert entry["client_name"] == config["metadata"]["client_name"]
    return entry["client_name"]


@pytest.mark.parametrize(
    "failure_point",
    [
        "after_config_staged",
        "after_design_staged",
        "after_audit_staged",
        "after_config_replaced",
        "after_design_replaced",
        "after_audit_replaced",
    ],
)
def test_confirmed_save_rolls_back_every_live_artifact_on_failure(tmp_path, failure_point):
    from persistence import PersistenceError, save_confirmed_branding

    root = tmp_path / "client-branding"
    save_confirmed_branding(_draft("Old Brand", "#112233"), branding_root=root)
    before = _live_bytes(root)

    def fail(point: str) -> None:
        if point == failure_point:
            raise OSError(f"injected failure at {point}")

    with pytest.raises(PersistenceError, match=failure_point):
        save_confirmed_branding(
            _draft("New Brand", "#445566"),
            branding_root=root,
            fault_injector=fail,
        )

    assert _live_bytes(root) == before
    assert not list((root / ".staging").iterdir())
    assert _assert_one_coherent_commit(root) == "Old Brand"


@pytest.mark.parametrize("disposition", ["rejected", "re_extracted"])
def test_non_confirming_disposition_records_attempt_without_activation(tmp_path, disposition):
    from persistence import persist_disposition, save_confirmed_branding

    root = tmp_path / "client-branding"
    save_confirmed_branding(_draft("Active Brand", "#112233"), branding_root=root)
    active_before = {
        name: (root / name).read_bytes() for name in ("config.yaml", "DESIGN.md")
    }

    result = persist_disposition(
        _draft("Rejected Draft", "#AABBCC"),
        disposition=disposition,
        branding_root=root,
    )

    assert result["applied"] is False
    assert {
        name: (root / name).read_bytes() for name in ("config.yaml", "DESIGN.md")
    } == active_before
    entry = json.loads((root / "audit.jsonl").read_text().splitlines()[-1])
    assert entry["action"] == "extraction_attempt"
    assert entry["applied"] is False
    assert entry["disposition"] == disposition


def test_two_concurrent_confirmed_saves_never_mix_artifacts(tmp_path):
    from persistence import save_confirmed_branding

    root = tmp_path / "client-branding"
    ready = threading.Barrier(2)
    errors: list[BaseException] = []

    def writer(name: str, color: str) -> None:
        try:
            save_confirmed_branding(
                _draft(name, color),
                branding_root=root,
                fault_injector=lambda point: ready.wait()
                if point == "after_design_staged"
                else None,
            )
        except BaseException as exc:  # surfaced in the parent test thread
            errors.append(exc)

    threads = [
        threading.Thread(target=writer, args=("Brand A", "#AA0000")),
        threading.Thread(target=writer, args=("Brand B", "#0000AA")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    assert _assert_one_coherent_commit(root) in {"Brand A", "Brand B"}
    entries = [json.loads(line) for line in (root / "audit.jsonl").read_text().splitlines()]
    assert [entry["client_name"] for entry in entries] in (
        ["Brand A", "Brand B"],
        ["Brand B", "Brand A"],
    )
    raw_lines = (root / "audit.jsonl").read_bytes().splitlines()
    for previous_line, current in zip(raw_lines, entries[1:]):
        assert current["prev_entry_hash"] == hashlib.sha256(previous_line).hexdigest()


def test_legacy_audit_without_final_newline_remains_valid_jsonl(tmp_path):
    from persistence import save_confirmed_branding

    root = tmp_path / "client-branding"
    root.mkdir()
    legacy = b'{"schema_version":1,"action":"save","legacy":true}'
    (root / "audit.jsonl").write_bytes(legacy)

    save_confirmed_branding(_draft("New Brand", "#445566"), branding_root=root)

    raw_lines = (root / "audit.jsonl").read_bytes().splitlines()
    entries = [json.loads(line) for line in raw_lines]
    assert len(entries) == 2
    assert entries[-1]["prev_entry_hash"] == hashlib.sha256(legacy).hexdigest()


def test_design_md_lint_timeout_cleans_tempdir_even_if_path_unlink_fails(
    tmp_path, monkeypatch
):
    import validator

    monkeypatch.setattr(validator.DesignMdValidator, "is_available", lambda: True)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout", 1))

    monkeypatch.setattr(subprocess, "run", timeout)
    monkeypatch.setattr(Path, "unlink", lambda self, *a, **k: (_ for _ in ()).throw(OSError("no")))

    result = validator.DesignMdValidator.lint("# synthetic")

    assert result["status"] == "skipped"
    assert "timed out" in result["note"]
    assert list(tmp_path.iterdir()) == []


# --- Regressions from the 2026-08-29 live RM brand-ingest exercise ----------


def test_archive_parent_directory_is_not_world_traversable(tmp_path) -> None:
    """mkdir(parents=True, mode=...) applies the mode only to the leaf.

    The intermediate .archive directory was therefore created with the process
    umask (0o755), so superseded client configs sat behind a world-traversable
    container. Only root's own 0o700 masked it.
    """
    import os
    import stat

    import persistence

    root = tmp_path / "branding"
    # Two saves: the second supersedes the first and creates .archive.
    persistence.save_confirmed_branding(
        _draft("First Client", "#111111"), branding_root=root, client_name="First Client"
    )
    persistence.save_confirmed_branding(
        _draft("Second Client", "#222222"), branding_root=root, client_name="Second Client"
    )

    archive = root / ".archive"
    assert archive.is_dir(), "second save should have archived the superseded config"

    def mode(path: Path) -> int:
        return stat.S_IMODE(os.stat(path).st_mode)

    assert mode(archive) == 0o700, f".archive is {oct(mode(archive))}"
    for entry in archive.iterdir():
        assert mode(entry) == 0o700, f"{entry.name} is {oct(mode(entry))}"
        for item in entry.iterdir():
            assert mode(item) == 0o600, f"{item.name} is {oct(mode(item))}"
    assert mode(root) == 0o700
    assert mode(root / ".staging") == 0o700
