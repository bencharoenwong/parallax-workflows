#!/usr/bin/env python3
"""Precision budget for mock fixtures — a HEURISTIC proxy for machine origin.

WHAT THIS IS FOR. The leak class this repo is guarding against is *provenance*,
not identity. ``AAPL.O`` with invented numbers is benign and already exists
throughout main; a renamed issuer carrying an API-emitted float is not. "Is this
a real company" is not mechanically checkable. "Did a machine emit this number"
largely is: a human authoring a fixture types ``0.35`` or ``189.42``, while a
serialiser round-tripping an IEEE double emits ``0.34937812345678901`` and a
market cap accurate to the dollar.

WHAT THIS IS NOT. This is a proxy, and a leaky one:

  * Large ROUND values slip through. A market cap of ``3810000000000`` is one
    significant figure under this rule and passes, even though it may have been
    rounded down from a live capture by hand.
  * Low-precision live values slip through. A recommendation string, an exact
    ``numshrs`` that happens to end in many zeros, a distinctive ``industry``
    label, or a real score on a real date carry no float precision at all and
    are entirely invisible here.
  * Conversely, a legitimately high-precision authored value (a test of
    float-formatting behaviour) is a false positive and must be allowlisted.

So this gate is a *backstop for hand-authored fixtures only*, where regeneration
equality (``test_fixture_provenance.py``, gate 1) cannot help. Gate 1 is the real
coverage: it fails on ANY value a machine emitted, round or not, string or float.
That asymmetry is the standing argument for keeping the MANAGED set as large as
possible and the HAND_AUTHORED set as small as possible.

THE RULE, AND WHERE THE NUMBER COMES FROM. One budget, MEASURED off the shape of
the real captures rather than chosen for tidiness:

    a value above 9 significant figures fails.

No legitimate non-integer value in the captured payload exceeded 9 significant
figures. The three fields that carry unrounded machine floats -- ``changepercent``
(15-19 figures), ``change`` (2-17, reaching 17 when a subtraction leaves float
dust) and ``mktcap`` (14-16 figures), all under ``company_info`` -- sit far above
that line. DO NOT TIGHTEN IT. 6 was the first guess and it false-positives on
ordinary authored content: an authored weight of ``0.349378`` is six figures and
six decimals, and a 4-decimal budget fails it.

There is deliberately NO separate decimal-place rule. Legitimate fields were
measured to cap at 8 decimals, which reads like a second budget, but below
magnitude 1 the two measures collide: ``0.123456789`` is 9 significant figures --
legitimate by the measured separation -- and unavoidably 9 decimals. A
decimals>8 rule would fail exactly the boundary value the measurement says is
fine. Above magnitude 1 a decimals rule is subsumed by the figure rule anyway
(9 figures with 9 decimals needs a 10-figure number), so it would add
false positives and no coverage.

Integers are counted with trailing zeros stripped, so ``47`` is two figures and
``2000000000`` is one. That strip is deliberate and it is also the round-number
hole: a share count or a market cap rounded by hand passes. THE PRECISION GATE
IS NOT SUFFICIENT ON ITS OWN -- gate 1 is what covers those.

ALLOWLISTING IS BY JSON PATH, NEVER BY VALUE. Keying on the value would silently
re-admit the exact number a future leak re-introduces at that path. A path entry
is a reviewed statement that "high precision is expected HERE", and it is
rejected as stale when nothing at that path trips any more.

Exit 0 clean, 1 on any violation.
Run: python3 skills/_parallax/scripts/fixture_precision.py [--root DIR]
"""
from __future__ import annotations

import argparse
import decimal
import json
import math
import pathlib
import sys
from typing import Any, Iterator, NamedTuple

MOCKS_DIR = pathlib.Path(__file__).parent / "mcp_mocks"

# Measured, not chosen. Read the docstring before changing it.
MAX_SIG_FIGS = 9

# path -> reason. Path form is "<fixture>.json:<dotted.path>", with "[]" standing
# in for any list index (so a 500-row series needs one entry, not 500). Add an
# entry ONLY with a written justification for why a machine-grade value belongs
# in a hand-authored fixture; an entry that no longer matches anything is a
# failure, not a no-op.
ALLOWLIST: dict[str, str] = {}


class Violation(NamedTuple):
    path: str          # "<fixture>.json:<dotted.path>"
    rule: str          # "sig-figs"
    measured: int
    budget: int

    def render(self) -> str:
        """Deliberately does NOT include the offending value. This repo's rule is
        that naming a term to prove its presence publishes it; a 16-figure market
        cap echoed into CI output is the leak, restated."""
        return (f"  PRECISION [{self.rule}]: {self.path} "
                f"({self.measured} > {self.budget})")


def _walk(node: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Yield (dotted_path, scalar) for every scalar. List indices collapse to
    "[]" so per-row series share one path."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value, f"{prefix}[]")
    else:
        yield prefix, node


def sig_figs_float(value: float) -> int:
    """Significant figures in the shortest repr that round-trips ``value``.

    ``normalize()`` strips trailing zeros, so ``2.0`` is one figure rather than
    the two that ``Decimal("2.0")`` reports."""
    return len(decimal.Decimal(repr(value)).normalize().as_tuple().digits)


def sig_figs_int(value: int) -> int:
    """Significant figures in an integer, trailing zeros stripped.

    This is why the docstring's round-number caveat exists: the strip is what
    makes ``2000000000`` benign, and it is also what lets a rounded live capture
    through."""
    digits = str(abs(value)).rstrip("0")
    return len(digits) if digits else 1


def check_value(path: str, value: Any) -> list[Violation]:
    """Violations for one scalar. Non-numbers and bools are out of scope --
    ``isinstance(True, int)`` is true in Python and a bool has no precision."""
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, int):
        measured = sig_figs_int(value)
        if measured > MAX_SIG_FIGS:
            return [Violation(path, "sig-figs", measured, MAX_SIG_FIGS)]
        return []
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return []
        sig = sig_figs_float(value)
        if sig > MAX_SIG_FIGS:
            return [Violation(path, "sig-figs", sig, MAX_SIG_FIGS)]
        return []
    return []


def scan_dir(mocks_dir: pathlib.Path | None = None,
             allowlist: dict[str, str] | None = None,
             ) -> tuple[list[Violation], list[str]]:
    """Returns (violations, stale_allowlist_paths).

    A stale allowlist path is one that matched nothing: the value it excused was
    fixed or removed and the exemption should go with it."""
    base = MOCKS_DIR if mocks_dir is None else mocks_dir
    allowed = ALLOWLIST if allowlist is None else allowlist

    violations: list[Violation] = []
    used: set[str] = set()

    # rglob, not glob: a capture dropped at mcp_mocks/<subdir>/capture.json is
    # exactly the "newly dropped fixture" move this gate exists to catch, and a
    # flat walk would step straight over it. On the current flat tree the
    # relative path equals the file name, so nothing else changes.
    for fixture in sorted(base.rglob("*.json")):
        rel = fixture.relative_to(base).as_posix()
        try:
            payload = json.loads(fixture.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{rel}: unreadable fixture ({type(exc).__name__})")
        for dotted, value in _walk(payload):
            path = f"{rel}:{dotted}"
            found = check_value(path, value)
            if not found:
                continue
            if path in allowed:
                used.add(path)
                continue
            violations.extend(found)

    stale = sorted(set(allowed) - used)
    return violations, stale


def main(argv: list[str] | None = None) -> int:
    # There was no argument parsing here at all, so `--root somewhere/else` and
    # `--help` were both accepted, silently ignored, and the default tree was
    # scanned instead -- reporting a clean result for a directory the caller
    # never asked about. A gate that answers a question you did not ask is worse
    # than one that refuses: it hands back false assurance under the name of the
    # thing you were checking.
    parser = argparse.ArgumentParser(
        description="Check mock fixtures against the precision budget "
                    f"({MAX_SIG_FIGS} significant figures).",
        epilog="Exit 0 clean, 1 on any violation or stale allowlist entry.")
    parser.add_argument(
        "--root", type=pathlib.Path, default=MOCKS_DIR, metavar="DIR",
        help="directory to scan, searched recursively "
             "(default: the tracked mcp_mocks/ next to this script)")
    # ``main()`` with no argument means NO command-line arguments, not "go read
    # sys.argv". Defaulting to sys.argv here would make the function pick up
    # whatever flags the surrounding process was launched with -- under pytest
    # that is the pytest command line, which argparse then rejects. The real
    # entry point passes sys.argv[1:] explicitly at the bottom of this file.
    args = parser.parse_args([] if argv is None else argv)

    if not args.root.is_dir():
        print(f"FAIL: {args.root} is not a directory", file=sys.stderr)
        return 1

    try:
        violations, stale = scan_dir(args.root)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    for violation in violations:
        print(violation.render(), file=sys.stderr)
    for path in stale:
        print(f"  STALE ALLOWLIST ENTRY: {path}", file=sys.stderr)

    if violations or stale:
        if violations:
            print(f"FAIL: {len(violations)} value(s) exceed the fixture precision "
                  "budget — these look machine-emitted. Re-author them, or add the "
                  "JSON path to ALLOWLIST with a written reason.", file=sys.stderr)
        if stale:
            print(f"FAIL: {len(stale)} ALLOWLIST entr(y/ies) matched nothing — "
                  "remove them.", file=sys.stderr)
        return 1

    print(f"  ✓ fixture precision budget clean "
          f"(max {MAX_SIG_FIGS} significant figures)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
