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
import threading
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


def _load_sibling(module_name: str, filename: str):
    path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load white-label module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
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
    transaction_id = uuid.uuid4().hex
    staging = staging_root / transaction_id
    staging.mkdir(mode=0o700)

    originals: dict[str, bytes | None] = {}
    replacements_started = False
    archive_created: Path | None = None
    current_point = "before_staging"
    try:
        _write_staged(staging / "config.yaml", config_bytes)
        current_point = "after_config_staged"
        _inject(fault_injector, current_point)
        _write_staged(staging / "DESIGN.md", design_bytes)
        current_point = "after_design_staged"
        _inject(fault_injector, current_point)

        with _writer_lock(root):
            for name in ("config.yaml", "DESIGN.md", "audit.jsonl"):
                live = root / name
                originals[name] = live.read_bytes() if live.exists() else None

            # Preserve the superseded canonical config for traceability. As in
            # the documented workflow, archive failure is non-blocking.
            if originals["config.yaml"] is not None:
                try:
                    archive = root / ".archive" / (
                        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                        + f"-{transaction_id[:8]}"
                    )
                    archive.mkdir(parents=True, mode=0o700)
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
    except Exception as exc:
        if archive_created is not None:
            shutil.rmtree(archive_created, ignore_errors=True)
        if replacements_started:
            try:
                _restore(root, originals, transaction_id)
            except Exception as rollback_exc:
                raise PersistenceError(
                    f"{current_point}: save failed and rollback failed: {rollback_exc}"
                ) from exc
        raise PersistenceError(f"{current_point}: {exc}") from exc
    finally:
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
