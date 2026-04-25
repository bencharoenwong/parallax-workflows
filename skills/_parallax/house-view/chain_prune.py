#!/usr/bin/env python3
"""Reasoning chain retention CLI (Batch 4 / security audit B-2).

Implements the operator tooling required by chain spec §4.3:

    python3 chain_prune.py --before YYYY-MM-DD              # dry-run
    python3 chain_prune.py --before YYYY-MM-DD --confirm    # actually delete

Default is dry-run (lists candidates without deleting). `--confirm` is
required to perform deletion. Always emits a summary line. Refuses to
follow symlinks outside the chain directory and refuses to delete any
file modified since process start (concurrency guard).

Operators MUST archive chains to their org's compliance store before
running with `--confirm` — this CLI is a filesystem cleanup, not a
compliance disposal flow.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# Module-relative import surface (kept consistent with chain_emit.py).
_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import chain_emit  # noqa: E402

DEFAULT_CHAIN_DIR = chain_emit.DEFAULT_CHAIN_DIR


def _parse_before(s: str) -> datetime:
    """Parse YYYY-MM-DD as the END of that day in UTC.

    Cutoff semantics: a chain dated 2026-04-25 is pruned by --before
    2026-04-26. We use end-of-day so calling `--before 2026-04-25`
    keeps chains FROM 2026-04-25 (matches operator intuition that
    "before X" means "older than X, exclusive").
    """
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
    except ValueError as e:
        raise SystemExit(f"--before must be YYYY-MM-DD, got {s!r}: {e}")
    return d.replace(tzinfo=timezone.utc)


def _iter_chain_files(chain_dir: Path) -> Iterable[Path]:
    """Yield all `*.yaml` files under <chain_dir>/<YYYY-MM>/, walking
    only the expected month directories. Skips any symlinks; refuses
    to descend into a directory that's a symlink itself.
    """
    if not chain_dir.exists():
        return
    if chain_dir.is_symlink():
        raise SystemExit(
            f"refusing to operate on chain_dir={chain_dir} because it is a "
            "symlink. Resolve to the real path or fix the install."
        )
    for entry in sorted(chain_dir.iterdir()):
        # Month dirs are expected to look like YYYY-MM (any other shape
        # is foreign — leave it untouched).
        if not entry.is_dir() or entry.is_symlink():
            continue
        if not _looks_like_month_dir(entry.name):
            continue
        for f in sorted(entry.iterdir()):
            if f.is_symlink():
                continue
            if f.suffix == ".yaml" and not f.name.startswith(".tmp-"):
                yield f


def _looks_like_month_dir(name: str) -> bool:
    """Match `YYYY-MM` shape without false positives."""
    if len(name) != 7 or name[4] != "-":
        return False
    try:
        datetime.strptime(name, "%Y-%m")
    except ValueError:
        return False
    return True


def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prune reasoning-chain files older than --before.",
        epilog=(
            "WARNING: alpha-sensitive content. Archive chains to your org's "
            "compliance store BEFORE running with --confirm. This CLI is a "
            "filesystem cleanup, not a compliance disposal flow."
        ),
    )
    parser.add_argument(
        "--before",
        required=True,
        help="Cutoff date YYYY-MM-DD (UTC). Chains with mtime strictly "
             "before this date are pruned.",
    )
    parser.add_argument(
        "--chain-dir",
        default=str(DEFAULT_CHAIN_DIR),
        help=f"Chain directory (default: {DEFAULT_CHAIN_DIR}).",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete. Without this flag, runs in dry-run mode.",
    )
    args = parser.parse_args(argv)

    cutoff = _parse_before(args.before)
    # Check symlink-ness BEFORE resolve, otherwise resolve() silently
    # follows the link and we lose the ability to refuse.
    chain_dir_user = Path(args.chain_dir)
    if chain_dir_user.is_symlink():
        raise SystemExit(
            f"refusing to operate on chain_dir={chain_dir_user} because it is a "
            "symlink. Resolve to the real path or fix the install."
        )
    chain_dir = chain_dir_user.resolve()
    process_start = time.time()

    # Collect candidates first; do not delete during iteration.
    candidates: list[tuple[Path, int, datetime]] = []
    for f in _iter_chain_files(chain_dir):
        try:
            st = f.stat()
        except OSError as e:
            print(f"  SKIP  {f} (stat failed: {e})")
            continue
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
        if mtime >= cutoff:
            continue
        # Concurrency guard: refuse to delete a file modified since
        # process start (something else is touching it).
        if st.st_mtime > process_start:
            print(f"  SKIP  {f} (modified after prune start)")
            continue
        candidates.append((f, st.st_size, mtime))

    total_bytes = sum(b for _, b, _ in candidates)
    n = len(candidates)
    mode = "DELETE" if args.confirm else "DRY-RUN"
    print(f"[{mode}] chain_dir={chain_dir} cutoff={args.before} (UTC end-of-day)")
    if n == 0:
        print("  no chains older than cutoff.")
        return 0

    # Show first 20 candidates for confirmation/inspection.
    for f, size, mtime in candidates[:20]:
        rel = f.relative_to(chain_dir) if chain_dir in f.parents or f.parent == chain_dir else f
        print(f"  {mode:7s}  {rel}  ({_human_bytes(size)}, mtime={mtime.date()})")
    if n > 20:
        print(f"  ... and {n - 20} more")

    if not args.confirm:
        print(
            f"\nDRY-RUN: would prune {n} chains, {_human_bytes(total_bytes)} total. "
            "Re-run with --confirm to execute."
        )
        return 0

    # Confirmed deletion path.
    deleted = 0
    failed = 0
    for f, _size, _mtime in candidates:
        try:
            os.unlink(f)
            deleted += 1
        except OSError as e:
            print(f"  FAIL  {f}: {e}")
            failed += 1

    # Compute oldest remaining chain for the summary line.
    remaining = [
        datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).date()
        for p in _iter_chain_files(chain_dir)
    ]
    oldest_remaining = min(remaining).isoformat() if remaining else "(none)"
    print(
        f"\npruned {deleted} chains, {_human_bytes(total_bytes)} freed; "
        f"oldest remaining: {oldest_remaining}"
        + (f"  (failed: {failed})" if failed else "")
    )
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
