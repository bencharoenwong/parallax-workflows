"""Snapshot a live journey's scratch tree before the runner deletes it.

Usage: python3 evals/scratch_snapshot.py <scratch-dir>  (JSON on stdout)

Lists every entry under the scratch directory with its path relative to that
directory, its type ("file", "dir", "link" or "other"), its mode, and for a
regular file its size and sha256. Symbolic links are recorded with their
target text and never followed: the scratch home/ holds links to the real
~/.claude. The checker (concierge_journeys_check.py) compares this listing
with the files the model wrote through the Write tool (evals/README.md
§ Live concierge journeys).
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as handle:
        while chunk := handle.read(1 << 16):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(root: str) -> list[dict]:
    entries = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in sorted(dirnames) + sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            st = os.lstat(full)
            entry: dict = {"path": rel, "mode": stat.S_IMODE(st.st_mode)}
            if stat.S_ISLNK(st.st_mode):
                entry.update(type="link", target=os.readlink(full))
            elif stat.S_ISDIR(st.st_mode):
                entry["type"] = "dir"
            elif stat.S_ISREG(st.st_mode):
                entry.update(type="file", size=st.st_size)
                try:
                    entry["sha256"] = _sha256(full)
                except OSError as exc:
                    entry["error"] = type(exc).__name__
            else:
                entry["type"] = "other"
            entries.append(entry)
        # os.walk lists a symlink to a directory in dirnames but does not descend.
    entries.sort(key=lambda e: e["path"])
    return entries


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or not os.path.isdir(args[0]):
        sys.stderr.write("usage: scratch_snapshot.py <scratch-dir>\n")
        return 2
    json.dump({"v": 1, "entries": snapshot(args[0])}, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
