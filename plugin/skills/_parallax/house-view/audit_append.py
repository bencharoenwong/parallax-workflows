#!/usr/bin/env python3
"""Append one hash-chained row to the active house view's audit.jsonl.

Usage (loader.md §6): the skill writes the row with write-artifact to
`<cwd>/.parallax-render/audit-<8 hex>.json`, then runs one literal command:
    python3 ".../_parallax/house-view/audit_append.py" --input "<that path>"
The row never appears in the shell command, so no character in it (a quote in
a company name, `$(...)`, the `{"` that Claude Code's checker refuses inside a
command) reaches the shell. The draft is read and deleted by
render_gate.read_draft, which accepts only that path shape.

The view directory is resolved here ($PARALLAX_HOUSE_VIEW_DIR, else
~/.parallax/active-house-view/), so the caller never writes a variable into
the command. The existing log is verified before the append, so a row is never
chained onto a log that verify_chain would reject.

Exit codes; every nonzero exit prints one `[audit-append] ERROR:` line:
    0  appended
    2  the draft path or row is unusable: not a draft path, unreadable, over
       64 KB, not a JSON object with the loader.md §6.1 required fields, or it
       sets a chain field (chain_root, prev_entry_hash) the helper owns
    3  the chain helper cannot run on this host (rfc8785 or fcntl missing)
    4  the existing log fails verify_chain; nothing appended
    1  any other failure (I/O, lock); nothing is known to be appended
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REQUIRED_FIELDS = ("ts", "view_id", "version_id", "skill", "action", "applied")
CHAIN_FIELDS = ("chain_root", "prev_entry_hash")
MAX_ROW_BYTES = 64 * 1024
DEFAULT_VIEW_DIR = Path.home() / ".parallax" / "active-house-view"
VIEW_DIR_MODE = 0o700


def _fail(code: int, message: str) -> int:
    sys.stderr.write(f"[audit-append] ERROR: {message}\n")
    return code


def resolve_view_dir() -> Path:
    env = os.environ.get("PARALLAX_HOUSE_VIEW_DIR")
    return Path(env).expanduser() if env else DEFAULT_VIEW_DIR


def _run_trace():
    """The live-journey run trace (``_parallax/run_trace.py``) when
    PARALLAX_E2E_TRACE is set, else None. Loaded by path, so an ordinary run
    imports nothing new (evals/README.md § Live concierge journeys)."""
    if not os.environ.get("PARALLAX_E2E_TRACE"):
        return None
    module = sys.modules.get("_parallax_run_trace")
    if module is None:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "_parallax_run_trace", os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "run_trace.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sys.modules["_parallax_run_trace"] = module
        except Exception:
            return None
    return module


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] != "--input":
        return _fail(2, 'usage: audit_append.py --input "<draft path>" (loader.md §6)')
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here.parent))  # render_gate.py lives in _parallax/
    try:
        from render_gate import read_draft
        text = read_draft(args[1], "audit", ".json")
    except (OSError, ValueError) as exc:
        return _fail(2, f"cannot read the row draft: {exc}")
    if (trace := _run_trace()) is not None:
        trace.note_input(text.encode("utf-8"), role="input", path=args[1])
    if len(text.encode("utf-8")) > MAX_ROW_BYTES:
        return _fail(2, f"row is over {MAX_ROW_BYTES} bytes")
    try:
        entry = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        return _fail(2, f"row is not JSON: {type(exc).__name__}: {exc}")
    if not isinstance(entry, dict):
        return _fail(2, "row must be a JSON object")
    missing = [k for k in REQUIRED_FIELDS if k not in entry]
    if missing:
        return _fail(2, f"row is missing {', '.join(missing)}")
    owned = [k for k in CHAIN_FIELDS if k in entry]
    if owned:
        return _fail(2, f"row must not set {', '.join(owned)}; the helper chains it")

    sys.path.insert(0, str(here))
    try:
        import audit_chain
    except ImportError as exc:
        return _fail(3, f"audit chain unavailable on this host: {exc}")

    try:
        view_dir = resolve_view_dir()
        view_dir.mkdir(parents=True, exist_ok=True)
        if not view_dir.is_symlink():  # never re-mode a symlink's target
            os.chmod(view_dir, VIEW_DIR_MODE)
        audit_path = view_dir / "audit.jsonl"
        try:
            audit_chain.verify_chain(audit_path)
        except audit_chain.AuditChainError as exc:
            return _fail(4, f"existing audit log fails verification: {exc}")
        audit_chain.append_entry(audit_path, entry)
    except Exception as exc:  # report, never traceback: the caller continues
        return _fail(1, f"{type(exc).__name__}: {exc}")
    print(json.dumps({"appended_to": str(audit_path)}))
    return 0


if __name__ == "__main__":
    _trace = _run_trace()
    sys.exit(_trace.run("audit_append.py", __file__, main) if _trace else main())
