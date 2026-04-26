"""Cryptographic audit-log chaining logic for House View (Approach B).

Implements JCS-canonicalized (RFC 8785) SHA-256 hash chains for tamper-evident
audit trails.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import rfc8785

logger = logging.getLogger(__name__)

AUDIT_SCHEMA_VERSION = 1
_AUDIT_FILE_MODE = 0o600


class AuditChainError(Exception):
    error_code: str = "audit_chain_error"


class AuditChainBroken(AuditChainError):
    error_code = "audit_chain_broken"


class AuditFileMalformed(AuditChainError):
    error_code = "audit_file_malformed"


def compute_entry_hash(entry: dict[str, Any]) -> str:
    """Compute SHA-256 hash of a JCS-canonicalized audit entry."""
    canonical = rfc8785.dumps(entry)
    return hashlib.sha256(canonical).hexdigest()


def verify_chain(audit_path: Path) -> list[dict[str, Any]]:
    """Verify the integrity of a hash-chained audit log.

    Returns:
        List of all verified audit entries.

    Raises:
        AuditChainBroken: if a prev_entry_hash mismatch is detected.
        AuditFileMalformed: if JSON parsing fails.
    """
    if not audit_path.exists():
        return []

    entries: list[dict[str, Any]] = []
    prev_hash: str | None = None
    in_chained_section = False

    with open(audit_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                raise AuditFileMalformed(f"Line {i} is not valid JSON: {e}")

            # Migration boundary: chain_root anchors the start of validation
            if entry.get("chain_root") is True:
                if in_chained_section:
                    # Spec §1.4: chain_root must be present only on the first entry
                    raise AuditChainBroken(
                        f"Line {i}: Multiple chain_root entries detected. "
                        "Chain can only have one root."
                    )
                in_chained_section = True
                prev_hash = compute_entry_hash(entry)
                entries.append(entry)
                continue

            if in_chained_section:
                stored_prev_hash = entry.get("prev_entry_hash")
                if stored_prev_hash is None:
                    # In a chained section, every entry must carry the link
                    raise AuditChainBroken(
                        f"Line {i}: Missing prev_entry_hash in chained section."
                    )
                
                if stored_prev_hash != prev_hash:
                    raise AuditChainBroken(
                        f"Line {i}: Hash chain break. Expected {prev_hash}, "
                        f"found {stored_prev_hash}."
                    )
                
                # Advance the chain anchor
                prev_hash = compute_entry_hash(entry)
            
            entries.append(entry)

    return entries


def _get_tail_entries(f: Any, n: int = 10) -> list[dict[str, Any]]:
    """Efficiently read the last N entries from an open BINARY file handle."""
    f.seek(0, 2)
    file_size = f.tell()
    if file_size == 0:
        return []

    # Read last 32KB
    offset = min(file_size, 32 * 1024)
    f.seek(file_size - offset)
    chunk_bytes = f.read(offset)
    try:
        chunk = chunk_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # If we hit a partial character at the start of the chunk, 
        # try decoding from the first newline
        first_nl = chunk_bytes.find(b"\n")
        if first_nl != -1:
            chunk = chunk_bytes[first_nl+1:].decode("utf-8")
        else:
            return []

    lines = chunk.splitlines()

    # The first line is partial IF we seeked into the middle of the file
    valid_lines = lines[1:] if (offset < file_size and len(lines) > 1) else lines
    
    entries: list[dict[str, Any]] = []
    for line in valid_lines:
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries[-n:]


def append_entry(
    audit_path: Path,
    entry_data: dict[str, Any],
    ensure_chained: bool = True
) -> dict[str, Any]:
    """Append an entry to the audit log, chaining it to the previous entry.

    Atomic read-compute-append cycle using file locking (fcntl).
    Strict JCS serialization on disk.
    """
    # Open in binary update mode (rb+) to allow tail read + atomic append
    # If file doesn't exist, 'ab+' would create it.
    mode = "rb+" if audit_path.exists() else "wb+"
    
    with open(audit_path, mode) as f:
        # Acquire exclusive lock
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            # Defense in depth: enforce 0600 on every append so the file stays
            # tight even if (a) created externally with umask perms (Phase 0
            # SKILL.md "create empty if missing" path, security audit Finding 5),
            # (b) chmod'd looser between appends, or (c) the first-write chmod
            # below was skipped due to a prior empty-file create.
            try:
                audit_path.chmod(_AUDIT_FILE_MODE)
            except OSError:
                # Best effort — non-POSIX filesystems may reject chmod.
                pass
            # 1. Resolve anchor from tail
            tail = _get_tail_entries(f, n=2)
            last_entry = tail[-1] if tail else None
            
            # Check if the log is already chained
            is_chained = any(e.get("chain_root") is True or "prev_entry_hash" in e for e in tail)
            
            final_entry = dict(entry_data)
            final_entry.setdefault("schema_version", AUDIT_SCHEMA_VERSION)

            if not is_chained:
                if ensure_chained:
                    # Start the chain!
                    final_entry["chain_root"] = True
            else:
                # Continue the chain
                if last_entry:
                    final_entry["prev_entry_hash"] = compute_entry_hash(last_entry)
                else:
                    final_entry["chain_root"] = True

            # 2. Strict JCS write
            line_bytes = rfc8785.dumps(final_entry) + b"\n"
            f.seek(0, 2) # Ensure at end
            f.write(line_bytes)
            f.flush()
            
            # Set permissions on first write
            if f.tell() == len(line_bytes):
                audit_path.chmod(_AUDIT_FILE_MODE)

            return final_entry
        finally:
            # Release lock
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
