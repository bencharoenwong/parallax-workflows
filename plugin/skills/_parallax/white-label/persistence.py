"""Transactional persistence for confirmed white-label branding drafts.

The onboarding skill is interactive, but activation is deliberately exposed as
a callable boundary so tests and other callers cannot accidentally reproduce
the save algorithm.  A save stages every derived artifact, serializes writers,
and restores the complete prior state if any replacement or audit step fails.
"""
from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import yaml


FaultInjector = Callable[[str], None]
_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class PersistenceError(RuntimeError):
    """A branding transaction failed and its prior live state was restored."""


_SIBLING_LOCK = threading.Lock()
_LOADED_SIBLINGS: dict[str, Any] = {}


def _load_sibling(module_name: str, filename: str):
    # Publish into _LOADED_SIBLINGS only after exec_module returns. sys.modules
    # must hold the module DURING execution so a sibling defining a dataclass
    # can resolve its own __module__, but a concurrent caller reading
    # sys.modules directly would get a half-executed module and fail on a
    # missing attribute. The lock plus the separate completed-module map means
    # a second thread either waits or sees a fully initialised module.
    module = _LOADED_SIBLINGS.get(module_name)
    if module is not None:
        return module
    with _SIBLING_LOCK:
        module = _LOADED_SIBLINGS.get(module_name)
        if module is not None:
            return module
        path = Path(__file__).resolve().parent / filename
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load white-label module: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
        _LOADED_SIBLINGS[module_name] = module
        return module


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _branding_root(value: str | Path | None) -> Path:
    if value is None:
        return Path.home() / ".parallax" / "client-branding"
    return Path(value).expanduser()


def _inject(fault_injector: FaultInjector | None, point: str) -> None:
    if fault_injector is not None:
        fault_injector(point)


def _canonical_line(entry: dict[str, Any]) -> bytes:
    return json.dumps(entry, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _prior_entry_hash(audit_bytes: bytes) -> str:
    lines = [line.strip() for line in audit_bytes.splitlines() if line.strip()]
    return hashlib.sha256(lines[-1]).hexdigest() if lines else "0" * 64


def _append_audit_line(audit_bytes: bytes, entry: dict[str, Any]) -> bytes:
    """Append one JSONL record even when a legacy file lacks a final newline."""
    separator = b"" if not audit_bytes or audit_bytes.endswith((b"\n", b"\r")) else b"\n"
    return audit_bytes + separator + _canonical_line(entry) + b"\n"


def _draft_hash(draft: dict[str, Any]) -> str:
    serialized = yaml.safe_dump(draft, sort_keys=True, allow_unicode=True).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _validation_status(validation_summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        group: {
            key: value.get("status") if isinstance(value, dict) else None
            for key, value in (validation_summary.get(group, {}) or {}).items()
        }
        for group in ("colors", "logos", "fonts")
    }


@contextmanager
def _writer_lock(root: Path) -> Iterator[None]:
    key = str(root.resolve())
    with _THREAD_LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(key, threading.Lock())
    with thread_lock:
        lock_path = root / ".save.lock"
        with lock_path.open("a+b") as lock_file:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write_staged(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    os.chmod(path, 0o600)


def _restore(root: Path, originals: dict[str, bytes | None], transaction_id: str) -> None:
    """Restore snapshotted bytes using same-directory atomic replacements."""
    for name, content in originals.items():
        live = root / name
        if content is None:
            live.unlink(missing_ok=True)
            continue
        rollback = root / f".{name}.{transaction_id}.rollback"
        _write_staged(rollback, content)
        os.replace(rollback, live)


# --- Crash recovery --------------------------------------------------------
#
# Each individual os.replace is atomic, but the commit replaces THREE files and
# the set is not. A process killed between two replacements left config.yaml
# describing the new brand while DESIGN.md still described the old one, and
# audit.jsonl carrying no entry for the change at all: branding active that the
# audit log does not record. The in-process rollback cannot help, because a hard
# kill never unwinds.
#
# The commit therefore publishes an intent journal before the first replacement
# and removes it after the last. A journal found on disk means some earlier
# process died mid-commit, and recovery drives that transaction to one end or
# the other so the three files always describe the same save.

_COMMIT_JOURNAL = ".commit-journal"
_TRANSACTION_FILES = ("config.yaml", "DESIGN.md", "audit.jsonl")


class RecoveryError(PersistenceError):
    """An interrupted transaction could not be completed or undone."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _publish_journal(root: Path, staging: Path, entry: dict[str, Any]) -> Path:
    """Atomically place the intent journal so a crash is always detectable."""
    journal = root / _COMMIT_JOURNAL
    staged = staging / _COMMIT_JOURNAL
    _write_staged(staged, json.dumps(entry, separators=(",", ":")).encode("utf-8"))
    os.replace(staged, journal)
    os.chmod(journal, 0o600)
    return journal


def _recover_interrupted_commit(root: Path) -> dict[str, Any] | None:
    """Complete or undo a transaction whose process died mid-commit.

    Roll forward when every staged replacement is still present and intact,
    because that reaches the state the operator confirmed. Otherwise roll back
    to the snapshot taken before the commit began. Never mix the two: a partial
    application is the one outcome that must not survive.

    Caller must already hold the writer lock.
    """
    journal_path = root / _COMMIT_JOURNAL
    if not journal_path.exists():
        return None

    try:
        journal = json.loads(journal_path.read_bytes())
    except (OSError, ValueError) as exc:
        raise RecoveryError(f"unreadable commit journal at {journal_path}: {exc}") from exc

    staging = root / ".staging" / str(journal.get("transaction_id", ""))
    files: dict[str, Any] = journal.get("files") or {}
    rollback_dir = staging / ".rollback"

    def _matches(path: Path, expected: str | None) -> bool:
        if expected is None:
            return not path.exists()
        return path.exists() and _sha256(path.read_bytes()) == expected

    def _resolve(name: str, expected: str | None, spare: Path) -> Path | None:
        """Locate content hashing to ``expected``, or None if unavailable.

        The commit loop MOVES each staged file onto the live path, so a file
        already replaced before the crash has its target content at the live
        path while its spare copy is gone. Both locations must be considered
        or a partially-applied transaction looks unrecoverable.
        """
        live = root / name
        if _matches(live, expected):
            return live
        if _matches(spare, expected):
            return spare
        return None

    forward = {
        name: _resolve(name, spec.get("new_sha256"), staging / name)
        for name, spec in files.items()
    }
    backward = {
        name: _resolve(name, spec.get("original_sha256"), rollback_dir / name)
        for name, spec in files.items()
    }

    def _complete(sources: dict[str, Path | None], key: str) -> bool:
        return all(
            sources[name] is not None or files[name].get(key) is None
            for name in files
        )

    if _complete(forward, "new_sha256"):
        sources, key, outcome = forward, "new_sha256", "rolled_forward"
    elif _complete(backward, "original_sha256"):
        sources, key, outcome = backward, "original_sha256", "rolled_back"
    else:
        raise RecoveryError(
            f"interrupted transaction {journal.get('transaction_id')} cannot be "
            f"completed or undone: neither the staged replacements nor the "
            f"pre-commit snapshot are intact. Inspect {staging} before retrying."
        )

    for name, spec in files.items():
        live = root / name
        if spec.get(key) is None:
            live.unlink(missing_ok=True)
            continue
        source = sources[name]
        assert source is not None  # guaranteed by _complete
        if source == live:
            continue  # already carries the target content
        # Land in the same directory first, so the visible swap is one rename
        # on one filesystem and cannot half-apply a single file.
        landing = root / f".{name}.recover"
        shutil.copyfile(source, landing)
        os.chmod(landing, 0o600)
        os.replace(landing, live)

    journal_path.unlink(missing_ok=True)
    shutil.rmtree(staging, ignore_errors=True)
    return {
        "recovered": True,
        "outcome": outcome,
        "transaction_id": journal.get("transaction_id"),
    }


def _discard_own_journal(root: Path, transaction_id: str) -> bool:
    """Retire the commit journal only when it names ``transaction_id``.

    A failed save settles its own transaction, so its journal must go. It must
    never touch a journal it did not publish: the pre-commit recovery call
    raises RecoveryError exactly when an EARLIER commit left a state that can
    be neither completed nor undone, and that journal is the only pointer to
    the staged and snapshot copies an operator needs to repair the root.

    Returns True when a journal belonging to this transaction may still be on
    disk, so the caller keeps the staging directory that journal names.

    Caller must already hold the writer lock. Retiring the journal is one half
    of settling a failed commit and restoring the snapshot is the other, so
    both run under the single lock acquisition that guarded the commit itself.
    """
    journal_path = root / _COMMIT_JOURNAL
    try:
        if not journal_path.exists():
            return False
        try:
            owner = json.loads(journal_path.read_bytes()).get("transaction_id")
        except (OSError, ValueError):
            # Ownership is unknowable, so assume the journal is this
            # transaction's and keep both it and the staging it names.
            # Recovery reports an unreadable journal loudly; discarding
            # either side here would make that report unactionable.
            return True
        if owner != transaction_id:
            return False
        journal_path.unlink(missing_ok=True)
        return False
    except OSError:
        return True


#: A staging directory older than this belongs to a process that is gone. Saves
#: are interactive and complete in well under a second, so the margin is vast.
STAGING_ORPHAN_GRACE_SECONDS = 6 * 60 * 60


def _sweep_orphan_staging(
    root: Path,
    *,
    keep: str = "",
    now: float | None = None,
) -> list[str]:
    """Remove staging directories left by processes that died before committing.

    A crash BEFORE the journal is published touches no live file, so there is
    nothing to recover, but it strands a ``.staging/<txid>`` directory that no
    journal names and no later save reclaims. Without this sweep, the leak the
    commit journal was added to close would keep growing, one directory per
    crash.

    Staging is written outside the writer lock so concurrent savers can prepare
    in parallel, which means a directory seen here may belong to a live peer.
    Age is therefore the discriminator: only directories untouched for
    ``STAGING_ORPHAN_GRACE_SECONDS`` are reclaimed. ``keep`` protects the
    caller's own transaction, and a directory named by a surviving journal is
    never swept because recovery still needs it.
    """
    staging_root = root / ".staging"
    if not staging_root.is_dir():
        return []

    protected = {keep} if keep else set()
    journal_path = root / _COMMIT_JOURNAL
    if journal_path.exists():
        try:
            protected.add(
                str(json.loads(journal_path.read_bytes()).get("transaction_id", ""))
            )
        except (OSError, ValueError):
            # An unreadable journal is recovery's problem, and recovery runs
            # first. Sweep nothing rather than discard its evidence.
            return []

    cutoff = (time.time() if now is None else now) - STAGING_ORPHAN_GRACE_SECONDS
    swept: list[str] = []
    for entry in staging_root.iterdir():
        if not entry.is_dir() or entry.name in protected:
            continue
        try:
            if entry.stat().st_mtime > cutoff:
                continue
        except OSError:
            continue
        shutil.rmtree(entry, ignore_errors=True)
        swept.append(entry.name)
    return swept


def recover_interrupted_save(
    branding_root: str | Path | None = None,
) -> dict[str, Any] | None:
    """Public entry point for repairing a branding root after a crash.

    Returns None when nothing needed repair. Every save calls this first, so
    the common path is self-healing; readers can call it explicitly when they
    want to fail loudly rather than read a torn state.
    """
    root = _branding_root(branding_root)
    if not root.exists():
        return None
    with _writer_lock(root):
        return _recover_interrupted_commit(root)


def save_confirmed_branding(
    draft: dict[str, Any],
    *,
    branding_root: str | Path | None = None,
    validation_summary: dict[str, Any] | None = None,
    client_name: str = "",
    extracted_by: str = "",
    notes: str = "",
    disposition: str = "confirmed",
    lint_status: str = "skipped",
    fault_injector: FaultInjector | None = None,
) -> dict[str, Any]:
    """Build and atomically activate one confirmed branding state.

    ``disposition`` is restricted to the two confirmation-gate outcomes that
    authorize activation.  Rejections and re-extractions must go through
    :func:`persist_disposition`, which records audit evidence without writing
    either active artifact.
    """
    if disposition not in {"confirmed", "edited"}:
        raise ValueError("only confirmed or edited drafts may be activated")

    root = _branding_root(branding_root)
    # Build both representations before creating staging state. Validation or
    # emission failures therefore cannot leave filesystem residue.
    loader = _load_sibling("parallax_white_label_persistence_loader", "loader.py")
    emitter = _load_sibling("parallax_white_label_persistence_emitter", "emit_design_md.py")
    validation = validation_summary or {}

    config = loader.build_config_from_draft(
        draft,
        validation_summary=validation_summary,
        client_name=client_name,
        extracted_by=extracted_by,
        notes=notes,
        schema_version=2,
    )
    actual_client_name = config.get("metadata", {}).get("client_name", "")
    source = config.get("metadata", {}).get("source", {})
    source_ref = source.get("reference", "") if isinstance(source, dict) else ""
    design_text = emitter.emit_design_md(
        draft,
        client_name=actual_client_name,
        extracted_at=config.get("metadata", {}).get("extracted_at", ""),
        source_refs=[source_ref] if source_ref else [],
    )
    config_bytes = yaml.safe_dump(
        config, sort_keys=False, allow_unicode=True
    ).encode("utf-8")
    design_bytes = design_text.encode("utf-8")
    config_hash = hashlib.sha256(
        yaml.safe_dump(config["branding"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    design_hash = hashlib.sha256(design_bytes).hexdigest()

    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    staging_root = root / ".staging"
    staging_root.mkdir(exist_ok=True, mode=0o700)
    os.chmod(staging_root, 0o700)
    transaction_id = uuid.uuid4().hex
    staging = staging_root / transaction_id
    staging.mkdir(mode=0o700)
    os.chmod(staging, 0o700)

    originals: dict[str, bytes | None] = {}
    replacements_started = False
    journal_published = False
    archive_created: Path | None = None
    current_point = "before_staging"
    try:
        # Staging deliberately runs OUTSIDE the writer lock so concurrent
        # writers prepare in parallel and serialize only at the commit. Moving
        # it under the lock deadlocks any caller that coordinates between two
        # savers at a staging fault point.
        _write_staged(staging / "config.yaml", config_bytes)
        current_point = "after_config_staged"
        _inject(fault_injector, current_point)
        _write_staged(staging / "DESIGN.md", design_bytes)
        current_point = "after_design_staged"
        _inject(fault_injector, current_point)

        with _writer_lock(root):
            try:
                # Repair any transaction a previous process died inside before
                # reading originals, otherwise this save would snapshot torn state
                # and make it permanent.
                _recover_interrupted_commit(root)
                _sweep_orphan_staging(root, keep=transaction_id)

                for name in _TRANSACTION_FILES:
                    live = root / name
                    originals[name] = live.read_bytes() if live.exists() else None

                # Preserve the superseded canonical config for traceability. As in
                # the documented workflow, archive failure is non-blocking.
                if originals["config.yaml"] is not None:
                    try:
                        # mkdir(parents=True, mode=...) applies the mode ONLY to the
                        # final component; intermediate parents are created with the
                        # process umask (0o755 by default). Create and chmod the
                        # .archive parent explicitly so superseded client configs are
                        # never listed through a world-readable directory.
                        archive_parent = root / ".archive"
                        archive_parent.mkdir(exist_ok=True, mode=0o700)
                        os.chmod(archive_parent, 0o700)
                        archive = archive_parent / (
                            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                            + f"-{transaction_id[:8]}"
                        )
                        archive.mkdir(mode=0o700)
                        os.chmod(archive, 0o700)
                        _write_staged(archive / "config.yaml", originals["config.yaml"])
                        archive_created = archive
                    except OSError:
                        pass

                audit_before = originals["audit.jsonl"] or b""
                entry = {
                    "schema_version": 1,
                    "ts": _now(),
                    "skill": "parallax-white-label-onboard",
                    "action": "save",
                    "applied": True,
                    "source": source,
                    "config_hash": config_hash,
                    "client_name": actual_client_name,
                    "prev_entry_hash": _prior_entry_hash(audit_before),
                    "validation_status": _validation_status(validation),
                    "disposition": disposition,
                    "draft_yaml_hash": _draft_hash(draft),
                    "design_md_hash": design_hash,
                    "lint_status": lint_status,
                }
                audit_bytes = _append_audit_line(audit_before, entry)
                _write_staged(staging / "audit.jsonl", audit_bytes)
                current_point = "after_audit_staged"
                _inject(fault_injector, current_point)

                # Snapshot the pre-commit state next to the staged replacements so
                # recovery can undo the transaction without this process running.
                rollback_dir = staging / ".rollback"
                rollback_dir.mkdir(mode=0o700)
                os.chmod(rollback_dir, 0o700)
                staged_bytes = {
                    "config.yaml": config_bytes,
                    "DESIGN.md": design_bytes,
                    "audit.jsonl": audit_bytes,
                }
                for name, original in originals.items():
                    if original is not None:
                        _write_staged(rollback_dir / name, original)

                _publish_journal(
                    root,
                    staging,
                    {
                        "transaction_id": transaction_id,
                        "ts": _now(),
                        "files": {
                            name: {
                                "new_sha256": _sha256(staged_bytes[name]),
                                "original_sha256": (
                                    None if originals[name] is None
                                    else _sha256(originals[name])
                                ),
                            }
                            for name in _TRANSACTION_FILES
                        },
                    },
                )
                journal_published = True
                current_point = "after_journal_published"
                _inject(fault_injector, current_point)

                replacements_started = True
                for name, point in (
                    ("config.yaml", "after_config_replaced"),
                    ("DESIGN.md", "after_design_replaced"),
                    ("audit.jsonl", "after_audit_replaced"),
                ):
                    os.replace(staging / name, root / name)
                    os.chmod(root / name, 0o600)
                    current_point = point
                    _inject(fault_injector, point)

                # Every file now carries the new content. Retiring the journal is
                # what marks the transaction complete; a crash before this point
                # leaves a journal that recovery drives forward.
                (root / _COMMIT_JOURNAL).unlink(missing_ok=True)
                journal_published = False
            except Exception as commit_exc:
                # Settling a failed commit must happen under the SAME lock
                # acquisition that guarded it. Restoring the snapshot from the
                # released-lock path let a waiting saver acquire the lock and
                # run recovery while these files were still being rewritten,
                # so recovery chose a direction from a state that changed
                # underneath it and could publish the mixed result the journal
                # exists to prevent.
                if archive_created is not None:
                    shutil.rmtree(archive_created, ignore_errors=True)
                    archive_created = None
                if replacements_started:
                    try:
                        _restore(root, originals, transaction_id)
                    except Exception as rollback_exc:
                        # The transaction is UNSETTLED: live state is torn and
                        # this process cannot repair it. Leave the journal AND
                        # the staging copies it points at, so the next save or
                        # an explicit recover_interrupted_save() can still
                        # finish the job.
                        raise PersistenceError(
                            f"{current_point}: save failed and rollback "
                            f"failed: {rollback_exc}"
                        ) from commit_exc
                # Live state matches the snapshot again, so the transaction is
                # settled and its journal must not outlive it.
                journal_published = _discard_own_journal(root, transaction_id)
                if isinstance(commit_exc, PersistenceError):
                    # RecoveryError from the pre-commit repair names a torn
                    # state this process did not create and cannot resolve.
                    # Surface it unwrapped so callers can tell "your save
                    # failed" from "this root needs an operator".
                    raise
                raise PersistenceError(f"{current_point}: {commit_exc}") from commit_exc
    except Exception as exc:
        # Only the staging phase and the lock acquisition itself reach here;
        # neither has touched a live file or published a journal.
        if archive_created is not None:
            shutil.rmtree(archive_created, ignore_errors=True)
        if isinstance(exc, PersistenceError):
            raise
        raise PersistenceError(f"{current_point}: {exc}") from exc
    finally:
        # Discarding staging while a journal still points at it would strand the
        # branding root: every later save begins with recovery, and recovery
        # would find a journal whose staged and snapshot copies are both gone,
        # raising RecoveryError forever. The flag is settled inside the writer
        # lock, so a concurrent transaction's journal cannot be mistaken for
        # this one's.
        if staging is not None and not journal_published:
            shutil.rmtree(staging, ignore_errors=True)

    return {
        "applied": True,
        "config_hash": config_hash,
        "design_md_hash": design_hash,
        "client_name": actual_client_name,
    }


def record_extraction_attempt(
    draft: dict[str, Any],
    *,
    disposition: str,
    branding_root: str | Path | None = None,
) -> dict[str, Any]:
    """Record a non-activating confirmation-gate outcome atomically."""
    if disposition not in {"rejected", "re_extracted"}:
        raise ValueError("non-activating disposition must be rejected or re_extracted")
    root = _branding_root(branding_root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    with _writer_lock(root):
        # audit.jsonl is a transaction file, so appending to it while a commit
        # journal is outstanding invalidates the digests recovery reads to
        # choose its direction: a landed save would look half-applied and get
        # rolled back, taking this entry with it. Settle any interrupted
        # commit first, exactly as every other write path does.
        _recover_interrupted_commit(root)
        audit_path = root / "audit.jsonl"
        before = audit_path.read_bytes() if audit_path.exists() else b""
        source = draft.get("source", {}) or {}
        entry = {
            "schema_version": 1,
            "ts": _now(),
            "skill": "parallax-white-label-onboard",
            "action": "extraction_attempt",
            "applied": False,
            "source": source,
            "prev_entry_hash": _prior_entry_hash(before),
            "disposition": disposition,
            "draft_yaml_hash": _draft_hash(draft),
        }
        staged = root / f".audit.{uuid.uuid4().hex}.staging"
        try:
            _write_staged(staged, _append_audit_line(before, entry))
            os.replace(staged, audit_path)
            os.chmod(audit_path, 0o600)
        finally:
            staged.unlink(missing_ok=True)
    return {"applied": False, "disposition": disposition}


def persist_disposition(
    draft: dict[str, Any],
    *,
    disposition: str,
    branding_root: str | Path | None = None,
    **save_options: Any,
) -> dict[str, Any]:
    """Route a confirmation-gate disposition without ambiguous activation."""
    if disposition in {"confirmed", "edited"}:
        return save_confirmed_branding(
            draft,
            disposition=disposition,
            branding_root=branding_root,
            **save_options,
        )
    return record_extraction_attempt(
        draft, disposition=disposition, branding_root=branding_root
    )
