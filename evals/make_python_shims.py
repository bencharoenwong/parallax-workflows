"""Write the Python start shims for a live journey run.

Usage: python3 evals/make_python_shims.py <bin-dir> <log-file>

For each of python, python3 and python3.N found on PATH, writes an executable
``<bin-dir>/<name>`` that appends one JSON line to ``<log-file>`` and then
execs that interpreter, by the path PATH gave (symlinks kept, so an active
virtual environment stays active), with the same arguments. The runner puts
``<bin-dir>`` first on the run's PATH, so the checker sees every Python start
the model's shell commands make: argv, working directory, and for each
argument its resolved path when it names an existing file (``files``; the
checker decides which argument is the program, evals/README.md § Live
concierge journeys).

The logger runs the real interpreter by absolute path in isolated mode with
stdin from /dev/null, so it never reads the caller's stdin, and a logging
failure never stops the real interpreter from running.
"""
from __future__ import annotations

import os
import shlex
import shutil
import sys

NAMES = ["python", "python3"] + [f"python3.{minor}" for minor in range(9, 16)]

LOGGER = """\
import json, os, sys
name, log, args = sys.argv[1], sys.argv[2], sys.argv[3:]
files = []
for a in args:
    try:
        files.append(os.path.realpath(a) if os.path.isfile(a) else None)
    except (OSError, ValueError):
        files.append(None)
line = json.dumps({"v": 1, "shim": name, "argv": args, "cwd": os.getcwd(), "files": files})
fd = os.open(log, os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0))
try:
    os.write(fd, (line + "\\n").encode("utf-8"))
finally:
    os.close(fd)
"""


def shim_text(name: str, real: str, logger_python: str, log: str) -> str:
    q = shlex.quote
    return (
        "#!/bin/bash\n"
        f"{q(logger_python)} -I -c {q(LOGGER)} {q(name)} {q(log)} \"$@\" < /dev/null 2> /dev/null\n"
        f"exec {q(real)} \"$@\"\n"
    )


def write_shims(bin_dir: str, log: str, path: str | None = None) -> list[str]:
    os.makedirs(bin_dir, exist_ok=True)
    search = os.pathsep.join(p for p in (path or os.environ.get("PATH", "")).split(os.pathsep)
                             if p and os.path.realpath(p) != os.path.realpath(bin_dir))
    logger_python = os.path.realpath(sys.executable)
    written = []
    for name in NAMES:
        real = shutil.which(name, path=search)
        if real is None:
            continue
        target = os.path.join(bin_dir, name)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(shim_text(name, os.path.abspath(real), logger_python, log))
        os.chmod(target, 0o755)
        written.append(name)
    return written


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        sys.stderr.write("usage: make_python_shims.py <bin-dir> <log-file>\n")
        return 2
    if not write_shims(args[0], args[1]):
        sys.stderr.write("make_python_shims.py: no python interpreter found on PATH\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
