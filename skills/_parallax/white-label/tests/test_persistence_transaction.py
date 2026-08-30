from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
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


# --- Crash recovery: the three-file commit must never half-apply -------------


_CRASH_CHILD = '''
import importlib.util, os, sys
from pathlib import Path
WL = Path(sys.argv[4])
spec = importlib.util.spec_from_file_location("p", WL / "persistence.py")
P = importlib.util.module_from_spec(spec)
sys.modules["p"] = P
spec.loader.exec_module(P)
draft = {
    "client_name": "T", "extracted_at": "2026-08-29T00:00:00Z",
    "source": {"type": "wizard", "reference": "synthetic:t"},
    "colors": {"primary": {"hex": sys.argv[3]}, "background": {"hex": "#FFFFFF"},
               "text": {"hex": "#111111"}},
    "fonts": {"header": {"name": "Arial"}}, "confidence_scores": {}, "logos": {},
    "voice_corpus": {"text": "x", "word_count": 1, "truncated": False},
}
def inj(point):
    if point == sys.argv[2]:
        os._exit(9)
P.save_confirmed_branding(draft, branding_root=Path(sys.argv[1]),
                          client_name="T", fault_injector=inj)
'''

_NAMES = ("config.yaml", "DESIGN.md", "audit.jsonl")


def _run_child(root: Path, kill_at: str, color: str, tmp_path: Path):
    script = tmp_path / "crash_child.py"
    script.write_text(_CRASH_CHILD, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script), str(root), kill_at, color, str(WHITE_LABEL_DIR)],
        capture_output=True,
    )


def _digests(root: Path) -> dict:
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        if (root / name).exists()
        else None
        for name in _NAMES
    }


def _chain_is_intact(root: Path) -> bool:
    lines = [
        line for line in (root / "audit.jsonl").read_text().splitlines() if line.strip()
    ]
    entries = [json.loads(line) for line in lines]
    return all(
        entries[i]["prev_entry_hash"]
        == ("0" * 64 if i == 0 else hashlib.sha256(lines[i - 1].strip().encode()).hexdigest())
        for i in range(len(entries))
    )


@pytest.mark.parametrize(
    "kill_at",
    [
        "after_journal_published",
        "after_config_replaced",
        "after_design_replaced",
        "after_audit_replaced",
    ],
)
def test_hard_kill_mid_commit_recovers_to_a_consistent_state(tmp_path, kill_at: str) -> None:
    """A killed process must never leave the three files describing two saves.

    os.replace is atomic per file, but the commit replaces three. Before the
    commit journal existed, a kill after the first replacement left config.yaml
    on the new brand, DESIGN.md on the old one, and audit.jsonl with no record
    of the change: branding live that the audit log did not describe.
    """
    import persistence

    root = tmp_path / "branding"
    _run_child(root, "never", "#111111", tmp_path)
    before = _digests(root)

    _run_child(root, kill_at, "#222222", tmp_path)
    assert (root / persistence._COMMIT_JOURNAL).exists(), "crash left no journal"

    result = persistence.recover_interrupted_save(root)
    assert result is not None and result["recovered"] is True

    after = _digests(root)
    changed = sum(1 for name in _NAMES if before[name] != after[name])
    assert changed in (0, 3), f"torn state: only {changed}/3 files moved"
    assert _chain_is_intact(root)
    assert not (root / persistence._COMMIT_JOURNAL).exists()
    assert not list((root / ".staging").iterdir())


def test_recovery_leaves_the_live_config_recorded_in_the_audit_log(tmp_path) -> None:
    import persistence

    root = tmp_path / "branding"
    _run_child(root, "never", "#111111", tmp_path)
    _run_child(root, "after_config_replaced", "#222222", tmp_path)
    persistence.recover_interrupted_save(root)

    config = yaml.safe_load((root / "config.yaml").read_text())
    live_hash = hashlib.sha256(
        yaml.safe_dump(config["branding"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    audited = [
        json.loads(line)["config_hash"]
        for line in (root / "audit.jsonl").read_text().splitlines()
        if line.strip()
    ]

    assert live_hash in audited, "live branding is not described by any audit entry"


def test_recovery_rolls_back_when_staged_replacements_are_gone(tmp_path) -> None:
    """With the forward copies destroyed, recovery must undo, not half-apply."""
    import persistence

    root = tmp_path / "branding"
    _run_child(root, "never", "#111111", tmp_path)
    before = _digests(root)
    _run_child(root, "after_config_replaced", "#222222", tmp_path)

    journal = json.loads((root / persistence._COMMIT_JOURNAL).read_bytes())
    staging = root / ".staging" / journal["transaction_id"]
    for name in _NAMES:
        (staging / name).unlink(missing_ok=True)

    result = persistence.recover_interrupted_save(root)

    assert result["outcome"] == "rolled_back"
    assert _digests(root) == before
    assert not (root / persistence._COMMIT_JOURNAL).exists()


def test_next_save_self_heals_a_torn_root(tmp_path) -> None:
    """The common path must repair itself without an explicit recovery call."""
    import persistence

    root = tmp_path / "branding"
    _run_child(root, "never", "#111111", tmp_path)
    _run_child(root, "after_config_replaced", "#222222", tmp_path)
    assert (root / persistence._COMMIT_JOURNAL).exists()

    persistence.save_confirmed_branding(
        _draft("Third", "#333333"), branding_root=root, client_name="Third"
    )

    assert not (root / persistence._COMMIT_JOURNAL).exists()
    assert _chain_is_intact(root)
    config = yaml.safe_load((root / "config.yaml").read_text())
    assert config["branding"]["colors"]["primary"] == "#333333"


def test_recovery_fails_loudly_when_neither_copy_survives(tmp_path) -> None:
    """Silently guessing at a half-applied transaction is worse than failing."""
    import persistence

    root = tmp_path / "branding"
    _run_child(root, "never", "#111111", tmp_path)
    _run_child(root, "after_config_replaced", "#222222", tmp_path)

    journal = json.loads((root / persistence._COMMIT_JOURNAL).read_bytes())
    staging = root / ".staging" / journal["transaction_id"]
    for name in _NAMES:
        (staging / name).unlink(missing_ok=True)
        (staging / ".rollback" / name).unlink(missing_ok=True)

    with pytest.raises(persistence.RecoveryError) as excinfo:
        persistence.recover_interrupted_save(root)

    assert ".staging" in str(excinfo.value)


def test_retrying_an_unresolvable_root_keeps_its_recovery_evidence(tmp_path) -> None:
    """A save must not delete the journal of a transaction it did not publish.

    The failure handler used to unlink the journal unconditionally. On the
    ordinary retry path, the pre-commit repair raises RecoveryError for an
    earlier torn commit, the handler erased that journal, and the next
    recover_interrupted_save() reported "nothing needed repair" on a root whose
    live files were still inconsistent.
    """
    import persistence

    root = tmp_path / "branding"
    _run_child(root, "never", "#111111", tmp_path)
    _run_child(root, "after_config_replaced", "#222222", tmp_path)

    journal_path = root / persistence._COMMIT_JOURNAL
    journal = json.loads(journal_path.read_bytes())
    staging = root / ".staging" / journal["transaction_id"]
    for name in _NAMES:
        (staging / name).unlink(missing_ok=True)
        (staging / ".rollback" / name).unlink(missing_ok=True)

    with pytest.raises(persistence.RecoveryError):
        persistence.save_confirmed_branding(
            _draft("Third", "#333333"), branding_root=root, client_name="Third"
        )

    assert json.loads(journal_path.read_bytes()) == journal
    with pytest.raises(persistence.RecoveryError):
        persistence.recover_interrupted_save(root)


def test_recording_a_disposition_settles_an_interrupted_commit_first(tmp_path) -> None:
    """A non-activating disposition must not strand a landed save.

    audit.jsonl is a transaction file. record_extraction_attempt appended to it
    without settling an outstanding commit first, so a save that had fully
    landed stopped matching its journal's forward digests while the .rollback
    copies still matched the backward ones. The next recovery therefore chose
    ROLLBACK, reverting config.yaml and DESIGN.md to the pre-crash brand and
    discarding the operator's entry — with the hash chain left internally
    consistent, so nothing recorded that either had existed.
    """
    import persistence

    root = tmp_path / "branding"
    _run_child(root, "never", "#111111", tmp_path)
    _run_child(root, "after_audit_replaced", "#222222", tmp_path)
    assert (root / persistence._COMMIT_JOURNAL).exists()
    landed = _digests(root)

    persistence.record_extraction_attempt(
        _draft("Third", "#333333"), disposition="re_extracted", branding_root=root
    )

    assert persistence.recover_interrupted_save(root) is None
    config = yaml.safe_load((root / "config.yaml").read_text())
    assert config["branding"]["colors"]["primary"] == "#222222"
    assert _digests(root)["config.yaml"] == landed["config.yaml"]
    assert _digests(root)["DESIGN.md"] == landed["DESIGN.md"]

    dispositions = [
        json.loads(line)["disposition"]
        for line in (root / "audit.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert dispositions[-1] == "re_extracted"
    assert _chain_is_intact(root)


def test_recovery_is_a_noop_on_a_clean_or_absent_root(tmp_path) -> None:
    import persistence

    root = tmp_path / "branding"
    assert persistence.recover_interrupted_save(root) is None  # absent
    _run_child(root, "never", "#111111", tmp_path)
    assert persistence.recover_interrupted_save(root) is None  # clean


def test_successful_save_leaves_no_journal(tmp_path) -> None:
    import persistence

    root = tmp_path / "branding"
    persistence.save_confirmed_branding(
        _draft("Only", "#111111"), branding_root=root, client_name="Only"
    )

    assert not (root / persistence._COMMIT_JOURNAL).exists()


def test_failed_save_leaves_no_journal(tmp_path) -> None:
    """An in-process failure settles the transaction, so its journal must go."""
    import persistence

    root = tmp_path / "branding"
    persistence.save_confirmed_branding(
        _draft("First", "#111111"), branding_root=root, client_name="First"
    )
    before = _digests(root)

    def inject(point: str) -> None:
        if point == "after_design_replaced":
            raise RuntimeError("injected")

    with pytest.raises(persistence.PersistenceError):
        persistence.save_confirmed_branding(
            _draft("Second", "#222222"),
            branding_root=root,
            client_name="Second",
            fault_injector=inject,
        )

    assert not (root / persistence._COMMIT_JOURNAL).exists()
    assert _digests(root) == before


def test_rollback_failure_preserves_recovery_evidence(tmp_path, monkeypatch) -> None:
    """A double fault must leave the root repairable, not permanently wedged.

    The commit's `finally` used to discard staging unconditionally. When the
    in-process rollback ALSO failed (say ENOSPC), the journal survived while
    the staged and snapshot copies it names were deleted, so every later save
    began with recovery and raised RecoveryError forever.
    """
    import persistence

    root = tmp_path / "branding"
    persistence.save_confirmed_branding(
        _draft("First", "#111111"), branding_root=root, client_name="First"
    )
    before = _digests(root)

    def broken_restore(*args, **kwargs):
        raise OSError("no space left on device")

    def fault(point: str) -> None:
        if point == "after_design_replaced":
            raise RuntimeError("injected mid-commit failure")

    monkeypatch.setattr(persistence, "_restore", broken_restore)
    with pytest.raises(persistence.PersistenceError):
        persistence.save_confirmed_branding(
            _draft("Second", "#222222"),
            branding_root=root,
            client_name="Second",
            fault_injector=fault,
        )
    monkeypatch.undo()

    # The transaction is unsettled, so its evidence must still be on disk.
    assert (root / persistence._COMMIT_JOURNAL).exists()
    assert list((root / ".staging").iterdir())

    result = persistence.recover_interrupted_save(root)
    assert result is not None
    after = _digests(root)
    assert sum(1 for name in _NAMES if before[name] != after[name]) in (0, 3)

    # And the root must accept writes again.
    assert persistence.save_confirmed_branding(
        _draft("Third", "#333333"), branding_root=root, client_name="Third"
    )["applied"]


def test_staging_orphaned_before_journal_publish_is_swept_when_stale(
    tmp_path,
) -> None:
    """A crash before the journal exists leaves nothing to recover, only litter."""
    import os

    import persistence

    root = tmp_path / "branding"
    persistence.save_confirmed_branding(
        _draft("First", "#111111"), branding_root=root, client_name="First"
    )
    for kill_at in ("after_config_staged", "after_design_staged", "after_audit_staged"):
        _run_child(root, kill_at, "#222222", tmp_path)

    orphans = sorted(p.name for p in (root / ".staging").iterdir())
    assert len(orphans) == 3
    assert not (root / persistence._COMMIT_JOURNAL).exists()

    # Fresh directories are left alone: they may belong to a live peer, because
    # staging runs outside the writer lock by design.
    assert persistence._sweep_orphan_staging(root) == []

    stale = time.time() - persistence.STAGING_ORPHAN_GRACE_SECONDS - 60
    for name in orphans:
        os.utime(root / ".staging" / name, (stale, stale))

    assert sorted(persistence._sweep_orphan_staging(root)) == orphans
    assert list((root / ".staging").iterdir()) == []


def test_sweep_never_removes_the_callers_own_or_a_journalled_transaction(
    tmp_path,
) -> None:
    import os

    import persistence

    root = tmp_path / "branding"
    persistence.save_confirmed_branding(
        _draft("First", "#111111"), branding_root=root, client_name="First"
    )
    stale = time.time() - persistence.STAGING_ORPHAN_GRACE_SECONDS - 60
    for name in ("mine", "someone-else"):
        target = root / ".staging" / name
        target.mkdir(parents=True)
        os.utime(target, (stale, stale))

    assert persistence._sweep_orphan_staging(root, keep="mine") == ["someone-else"]
    assert (root / ".staging" / "mine").is_dir()


def test_concurrent_savers_stage_in_parallel_and_serialize_at_commit(
    tmp_path,
) -> None:
    """Staging must stay OUTSIDE the writer lock.

    Two savers rendezvous at a staging fault point. If staging were moved under
    the writer lock, the first saver would hold the lock while waiting for the
    second, which could never reach the rendezvous, and both would hang.
    """
    import persistence

    root = tmp_path / "branding"
    rendezvous = threading.Barrier(2, timeout=10)
    errors: list[BaseException] = []

    def writer(name: str, color: str) -> None:
        try:
            persistence.save_confirmed_branding(
                _draft(name, color),
                branding_root=root,
                client_name=name,
                fault_injector=lambda point: (
                    rendezvous.wait() if point == "after_design_staged" else None
                ),
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=writer, args=("Brand A", "#AA0000"), daemon=True),
        threading.Thread(target=writer, args=("Brand B", "#0000AA"), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not errors
    assert all(not thread.is_alive() for thread in threads), "staging serialized"
    assert _chain_is_intact(root)
    assert not (root / persistence._COMMIT_JOURNAL).exists()


def test_concurrent_savers_never_see_a_half_executed_sibling_module() -> None:
    """_load_sibling publishes only after exec_module returns.

    Registering the module in sys.modules before execution is required for a
    sibling dataclass, but a concurrent caller reading sys.modules directly
    would get a module whose attributes do not exist yet.
    """
    import persistence

    persistence._LOADED_SIBLINGS.clear()
    sys.modules.pop("parallax_white_label_concurrency_probe", None)
    seen: list[bool] = []
    errors: list[BaseException] = []

    def load() -> None:
        try:
            module = persistence._load_sibling(
                "parallax_white_label_concurrency_probe", "loader.py"
            )
            seen.append(hasattr(module, "build_config_from_draft"))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not errors
    assert seen == [True] * 8
