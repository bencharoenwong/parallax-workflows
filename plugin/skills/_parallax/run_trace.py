"""Run trace for the live concierge journeys (evals/README.md § Live concierge journeys).

When the environment variable ``PARALLAX_E2E_TRACE`` names the journey
runner's trace file, a helper run appends one JSON line to it: the helper's
name, the resolved path of the script that ran, its exit code, and for each
input it read the argument role, where it came from (a file, stdin, or an
inline argument value), the file's base name, and the sha256 and size of the
bytes. The render gate also records its skill key and the sha256 and size of
its output. No input or output text is ever written, only digests.

The runner creates the file before the run. This module never creates a file
and appends only to a regular, single-link file named ``journey-trace.jsonl``,
owned by the current user with mode 0600, opened without following a symlink.
A trace failure never changes a helper's exit code or output: every error here
is swallowed.

Helpers load this module by file path, under the module name
``_parallax_run_trace``, only when the variable is set, so an ordinary run
imports nothing new and a helper and a module it imports share one copy.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from typing import Any, Callable

ENV = "PARALLAX_E2E_TRACE"
TRACE_NAME = "journey-trace.jsonl"
_SKILL_KEY = re.compile(r"[a-z0-9-]{1,64}")

_inputs: list[dict[str, Any]] = []
_roles: dict[str, str] = {}
_output: dict[str, Any] | None = None
_skill: str | None = None


def _digest(data: bytes) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def note_input(data: bytes, *, role: str | None = None, path: str | None = None,
               source: str = "file") -> None:
    """Record one input's digest. ``source`` is "file", "stdin" or "inline".
    When only ``path`` is known, ``note_roles`` supplies the role later."""
    _inputs.append({"role": role, "path": path, "source": source, **_digest(data)})


def note_roles(roles: dict[str, str | None]) -> None:
    """Map argument roles to the values they were given (``{"policy": args.policy}``)."""
    _roles.update({role: value for role, value in roles.items() if isinstance(value, str)})


def note_output(data: bytes) -> None:
    global _output
    _output = _digest(data)


def note_skill(key: str) -> None:
    global _skill
    _skill = key if isinstance(key, str) and _SKILL_KEY.fullmatch(key) else None


def _entry(helper: str, script: str, exit_code: int) -> dict[str, Any]:
    inputs = []
    for item in _inputs:
        role = item["role"]
        if role is None and item["path"] is not None:
            role = next((r for r, value in _roles.items() if value == item["path"]), None)
        name = os.path.basename(item["path"]) if item["source"] == "file" and item["path"] else None
        inputs.append({"role": role, "source": item["source"], "name": name,
                       "sha256": item["sha256"], "size": item["size"]})
    return {"v": 1, "helper": helper, "script": os.path.realpath(script), "exit": exit_code,
            "inputs": inputs, "output": _output, "skill": _skill}


def finish(helper: str, script: str, exit_code: int) -> None:
    """Append this run's line to the trace file. Never raises."""
    try:
        path = os.environ.get(ENV)
        if not path or os.path.basename(path) != TRACE_NAME:
            return
        line = (json.dumps(_entry(helper, script, exit_code), sort_keys=True) + "\n").encode("utf-8")
        flags = (os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
        fd = os.open(path, flags)  # no O_CREAT: the runner made the file
        try:
            st = os.fstat(fd)
            if (stat.S_ISREG(st.st_mode) and st.st_nlink == 1
                    and stat.S_IMODE(st.st_mode) == 0o600
                    and st.st_uid == getattr(os, "getuid", lambda: st.st_uid)()):
                os.write(fd, line)
        finally:
            os.close(fd)
    except Exception:  # a trace failure must never change the helper's result
        pass


def _exit_code(code: object) -> int:
    if code is None:
        return 0
    return code if isinstance(code, int) else 1


def run(helper: str, script: str, main: Callable[[], object]) -> int:
    """Run ``main()``, append the trace line, and return the exit code
    (``SystemExit`` from argparse is recorded and re-raised)."""
    code: object = 1
    try:
        code = main()
    except SystemExit as exc:
        code = exc.code
        raise
    finally:
        finish(helper, script, _exit_code(code))
    return _exit_code(code)
