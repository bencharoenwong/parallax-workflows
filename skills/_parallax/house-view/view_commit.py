"""The only sanctioned writer of canonical house-view artifacts.

``view.yaml`` / ``prose.md`` / ``provenance.yaml`` are written here, always by
staging ``<name>.tmp.<version_id>`` and renaming. ``audit.jsonl`` is NEVER
staged or renamed -- it is append-only, and replacing it is what this module
exists to prevent: a rename swaps the inode out from under ``append_entry``'s
flock, and the resulting truncated chain still verifies green because
``verify_chain`` raises only on MULTIPLE ``chain_root`` entries.

Known residue, deliberately not fixed here:
  * The grouped renames are per-file atomic, not atomic as a group. A crash
    mid-group leaves a new view beside stale prose; ``paired_yaml_hash``
    detects it at load.
  * Nothing is fsynced except each staged file before its rename --
    ``audit.jsonl`` and the directory entry are not.
  * ``flock`` may silently no-op on some network filesystems.

Archiving is caller-side and best-effort; it happens before the commit call and
its failure neither blocks nor rolls back a commit.
"""
from __future__ import annotations

import hashlib
import os
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable

import yaml

_HOUSE_VIEW_DIR = Path(__file__).resolve().parent
if str(_HOUSE_VIEW_DIR) not in sys.path:
    sys.path.insert(0, str(_HOUSE_VIEW_DIR))
# Module-attribute access, NOT `from audit_chain import ...`: a from-import
# binds the name at import time, so `patch("audit_chain.append_entry")` in
# tests/test_e2e_concurrency.py:423-424 would not reach it and the maker/judge
# serialization test would time out at :429 instead of failing loudly.
import audit_chain  # noqa: E402

WRITABLE = frozenset({"view.yaml", "prose.md", "provenance.yaml"})
_AUDIT_FILENAME = "audit.jsonl"
_CLEAR_REQUIRED_FIELDS = ("destination", "reason")


class CommitRejected(audit_chain.AuditChainError):
    """The commit was refused before anything was written.

    Rooted at ``AuditChainError`` so existing ``except AuditChainError``
    handlers keep failing closed rather than letting a rejection escape as an
    unhandled type -- the same reasoning that made ``ViewChangedMidRun``
    multiply-inherit.
    """

    error_code = "commit_rejected"


class CommitWitnessLost(audit_chain.AuditChainError):
    """Artifacts were committed but the audit row could not be appended.

    Unrecoverable by this module: a completed ``os.rename`` cannot be undone,
    and a second rename to restore the old bytes would race any reader that
    already observed the new ones.
    """

    error_code = "commit_witness_lost"


def _is_empty(v: Any) -> bool:
    """Per schema.yaml §view_hash Rule 2. The bool guard and the numeric-zero
    case are both load-bearing: tilts default to 0 across every pillar, sector
    and region, and `False == 0` in Python."""
    if isinstance(v, bool):
        return False
    if v is None:
        return True
    if isinstance(v, (int, float)) and v == 0:
        return True
    return v == "" or v == [] or v == {}


def _strip_empty(obj: Any) -> Any:
    """Post-order: ALWAYS recurse first, THEN decide whether to drop.

    A container that only becomes empty after its children are stripped must
    still be dropped. Testing before recursing (pre-order) leaves residual
    empty containers and yields a different digest.
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            v = _strip_empty(v)
            if _is_empty(v):
                continue
            out[k] = v
        return out
    if isinstance(obj, list):
        result = []
        for x in obj:
            y = _strip_empty(x)
            if _is_empty(y):
                continue
            result.append(y)
        return result
    return obj


def compute_view_hash(view: dict[str, Any]) -> str:
    """Canonical ``view_hash`` over the tilts/excludes subtrees.

    Byte-identical to maker._compute_view_hash, stress.compute_view_hash, and
    the oracle in tests/test_view_hash.py. Keep it that way -- any deviation
    breaks hash round-trip for every view already saved.

    Note the body shape: both keys are ALWAYS present and only their VALUES
    are stripped. Stripping the outer dict instead would drop an empty
    ``excludes`` entirely and change the digest.
    """
    body = {
        "tilts": _strip_empty(view.get("tilts", {})),
        "excludes": _strip_empty(view.get("excludes", []) or []),
    }
    canonical = yaml.safe_dump(
        body,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
        width=1_000_000,
        indent=2,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_prose_body_hash(prose_text: str) -> str:
    """sha256 of the prose body, per schema.yaml "prose_body_hash computation"."""
    data = prose_text.encode("utf-8").replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    marker = b"---\n"
    if data.startswith(marker):
        end = data.find(marker, len(marker))
        if end != -1:
            data = data[end + len(marker):]
    return hashlib.sha256(data).hexdigest()


def validate_write_remove_keys(write: dict[str, Any], remove: frozenset[str]) -> None:
    for key in list(write) + list(remove):
        if key == _AUDIT_FILENAME:
            raise CommitRejected(
                f"{_AUDIT_FILENAME} is append-only; pass the row as `audit_entry`. "
                "It must never be staged, renamed, or removed."
            )
        if any(bad in key for bad in ("/", "\\", "..")) or ".tmp." in key:
            # Redundant with the WRITABLE check below for today's three names.
            # Kept deliberately: it is the guard that still holds if WRITABLE is
            # ever extended carelessly. Do not remove as "dead code".
            raise CommitRejected(f"unsafe artifact name: {key!r}")
        if key not in WRITABLE:
            raise CommitRejected(f"not a writable artifact: {key!r} (allowed: {sorted(WRITABLE)})")
    for key, content in write.items():
        if not isinstance(content, str):
            raise CommitRejected(f"content for {key!r} must be str, got {type(content).__name__}")


def validate_audit_entry(audit_entry: dict[str, Any], write: dict[str, Any]) -> None:
    if not isinstance(audit_entry, dict) or not audit_entry.get("action"):
        raise CommitRejected("audit_entry is required and must carry an `action`")
    if write and not audit_entry.get("version_id"):
        raise CommitRejected(
            "audit_entry.version_id is required whenever artifacts are written "
            "(it names the .tmp.<version_id> staging files)"
        )
    if write:
        vid = str(audit_entry["version_id"])
        if any(bad in vid for bad in ("/", "\\", "..")) or vid != vid.strip():
            raise CommitRejected(f"unsafe version_id for a staging filename: {vid!r}")
    if audit_entry["action"] == "clear":
        for field in _CLEAR_REQUIRED_FIELDS:
            if not audit_entry.get(field):
                raise CommitRejected(f"a clear row requires `{field}` (loader.md §6.2)")


def _load_view(view_dir: Path) -> dict[str, Any]:
    path = view_dir / "view.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _metadata_field(view_dir: Path, field: str) -> str | None:
    return ((_load_view(view_dir).get("metadata")) or {}).get(field)


def _resolve_prose_body_hash(view_dir: Path) -> str | None:
    path = view_dir / "prose.md"
    if not path.exists():
        return None
    # SECURITY: recompute, never read prose_body_hash out of the frontmatter.
    # Trusting the stored field reopens the legacy-view downgrade attack that
    # loader.md §2 step 3a exists to catch.
    return compute_prose_body_hash(path.read_text(encoding="utf-8"))


# Resolvers are lazy and per-key: only the keys actually present in
# `expected_identity` cause a read. --clear asks for version_id alone, so a
# corrupt prose.md must not break the mode most likely to be run against a
# damaged directory.
IDENTITY_RESOLVERS: dict[str, Callable[[Path], str | None]] = {
    # Not a typo. "parent_version_id" means "the version I expect to still be
    # current", so it resolves against the on-disk view's OWN version_id --
    # the asymmetry maker._read_parent_version_id already encodes.
    "parent_version_id": lambda d: _metadata_field(d, "version_id"),
    "version_id": lambda d: _metadata_field(d, "version_id"),
    "view_id": lambda d: _metadata_field(d, "view_id"),
    "view_hash": lambda d: _metadata_field(d, "view_hash"),
    "prose_body_hash": _resolve_prose_body_hash,
}


def _check_identity(view_dir: Path, expected_identity: dict[str, Any]) -> None:
    unknown = set(expected_identity) - set(IDENTITY_RESOLVERS)
    if unknown:
        raise CommitRejected(f"unknown identity keys: {sorted(unknown)}")
    captured = {k: str(v) for k, v in expected_identity.items()}
    committed = {k: str(IDENTITY_RESOLVERS[k](view_dir)) for k in expected_identity}
    moved = audit_chain.identity_diff(captured, committed)
    if moved:
        raise audit_chain.ViewChangedMidRun(
            f"Active house view changed since it was read ({moved}); nothing was written."
        )


def _parse_mapping(text: str, label: str) -> dict[str, Any]:
    """Parse YAML into a mapping, failing closed as ``CommitRejected`` --
    never letting a ``yaml.YAMLError`` or a non-mapping document escape as an
    unhandled type that bypasses ``except AuditChainError`` callers."""
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise CommitRejected(f"{label} is not valid YAML: {exc}") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise CommitRejected(f"{label} must be a mapping, got {type(parsed).__name__}")
    return parsed


def _validate_row_matches_bytes(write: dict[str, str], audit_entry: dict[str, Any]) -> None:
    """Assert the row describes the bytes. Without this, a row can disagree
    with the artifacts it witnesses and the chain still verifies green."""
    if "view.yaml" in write:
        parsed = _parse_mapping(write["view.yaml"], "view.yaml")
        meta = parsed.get("metadata") or {}
        if "view_hash" in audit_entry:
            actual = compute_view_hash(parsed)
            if audit_entry["view_hash"] != actual:
                raise CommitRejected(
                    f"row view_hash {audit_entry['view_hash']!r} != bytes {actual!r}"
                )
        if meta.get("version_id") != audit_entry.get("version_id"):
            raise CommitRejected(
                f"row version_id {audit_entry.get('version_id')!r} != "
                f"view.yaml metadata {meta.get('version_id')!r}"
            )
    if "prose.md" in write:
        text = write["prose.md"]
        # Normalize CRLF the same way compute_prose_body_hash does before
        # looking for the frontmatter marker -- otherwise a CRLF prose.md
        # never matches "---\n", front stays {}, and the body hash below
        # (computed against the normalized+stripped body) is guaranteed to
        # disagree with an empty frontmatter dict: a spurious rejection.
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        front: dict[str, Any] = {}
        if normalized.startswith("---\n"):
            end = normalized.find("---\n", 4)
            if end != -1:
                front = _parse_mapping(normalized[4:end], "prose.md frontmatter")
        if "view_hash" in audit_entry and front.get("paired_yaml_hash") != audit_entry["view_hash"]:
            raise CommitRejected(
                f"prose paired_yaml_hash {front.get('paired_yaml_hash')!r} != "
                f"row view_hash {audit_entry['view_hash']!r}"
            )
        actual_body = compute_prose_body_hash(text)
        if front.get("prose_body_hash") != actual_body:
            raise CommitRejected(
                f"prose frontmatter prose_body_hash {front.get('prose_body_hash')!r} != "
                f"body {actual_body!r}"
            )


def _stage_and_rename(view_dir: Path, write: dict[str, str], version_id: str) -> None:
    staged: list[tuple[Path, Path]] = []
    try:
        for name in ("view.yaml", "prose.md", "provenance.yaml"):
            if name not in write:
                continue
            tmp = view_dir / f"{name}.tmp.{version_id}"
            # O_EXCL: a leftover staging file is a loud error, never a silent
            # overwrite. 0600 at creation, not chmod-after-rename, so the file
            # is never briefly world-readable under a permissive umask.
            fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            # Register BEFORE writing: if write/flush/fsync raises, the tmp
            # file already exists on disk (O_CREAT already ran) and must
            # still be in the cleanup list, or it leaks -- and O_EXCL then
            # wedges every retry with this same version_id permanently.
            staged.append((tmp, view_dir / name))
            with os.fdopen(fd, "wb") as handle:
                handle.write(write[name].encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
        for tmp, final in staged:
            os.rename(tmp, final)
            staged = staged[1:]
    except OSError as exc:
        for tmp, _ in staged:
            with suppress(OSError):
                tmp.unlink()
        raise CommitRejected(f"staging failed, nothing committed: {exc}") from exc


def commit_view_locked(
    view_dir: Path,
    *,
    token: audit_chain.TransactionToken,
    write: dict[str, str],
    remove: frozenset[str],
    audit_entry: dict[str, Any],
    expected_identity: dict[str, Any],
) -> dict[str, Any]:
    """Commit artifacts and their witnessing row. Assumes the lock is HELD.

    The step order IS the contract: nothing touches the filesystem until every
    validation has passed.
    """
    view_dir = Path(view_dir)
    if not isinstance(token, audit_chain.TransactionToken) or token.view_dir != view_dir:
        raise CommitRejected(
            "commit_view_locked requires a TransactionToken for this view_dir; "
            "use commit_view() if you do not already hold the transaction"
        )
    validate_write_remove_keys(write, remove)
    validate_audit_entry(audit_entry, write)
    _check_identity(view_dir, expected_identity)
    _validate_row_matches_bytes(write, audit_entry)
    mutated = False
    if write:
        _stage_and_rename(view_dir, write, str(audit_entry["version_id"]))
        mutated = True
    for name in remove:
        try:
            (view_dir / name).unlink()
            mutated = True
        except FileNotFoundError:
            pass
    try:
        return audit_chain.append_entry(view_dir / _AUDIT_FILENAME, audit_entry)
    except Exception as exc:  # noqa: BLE001
        if not mutated:
            # Nothing reached the filesystem, so the correct action is retry
            # -- not a hand-edit of the chain. Do not claim a commit happened.
            raise
        raise CommitWitnessLost(
            f"artifacts for version_id={audit_entry.get('version_id')!r} were committed "
            f"but the audit row could not be appended ({exc}). The renames cannot be "
            f"undone. Recover by re-appending the row to {view_dir / _AUDIT_FILENAME} "
            "before any further commit."
        ) from exc


def commit_view(
    view_dir: Path,
    *,
    write: dict[str, str],
    remove: frozenset[str],
    audit_entry: dict[str, Any],
    expected_identity: dict[str, Any],
) -> dict[str, Any]:
    """Acquire the view transaction, then commit. Never call from inside one --
    ``view_transaction`` is not re-entrant and nesting blocks forever."""
    view_dir = Path(view_dir)
    with audit_chain.view_transaction(view_dir) as token:
        return commit_view_locked(
            view_dir, token=token, write=write, remove=remove,
            audit_entry=audit_entry, expected_identity=expected_identity,
        )
