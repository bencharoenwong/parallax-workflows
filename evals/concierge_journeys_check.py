"""evals/concierge_journeys_check.py — expect/forbid/expect_any substring
checker for the live concierge journeys (see evals/concierge_journeys.sh and
evals/tasks/concierge/journeys.jsonl).

Pure function, no I/O: feed it a journey's transcript text plus its journey
dict, get back (passed, reasons). The shell runner calls this file's CLI
entry point; evals/graders/test_concierge_journeys_check.py pytests the pure
function directly on canned text (no model, no network — CI-safe).
"""
from __future__ import annotations

import json
import sys


def check_journey(output: str, journey: dict) -> tuple[bool, list[str]]:
    """Check ``output`` against one journey's expect/forbid/expect_any lists.

    - expect: every substring must appear (case-insensitive substring match).
      Each missing one is a failure reason.
    - forbid: no substring may appear (case-insensitive). Each present one is
      a failure reason.
    - expect_any: if the list is non-empty, at least one substring must
      appear; none present is a single failure reason.

    Returns (passed, reasons). reasons is empty iff passed is True, and lists
    every failure found, not just the first, so a FAIL line can say exactly
    what broke.
    """
    text = (output or "").lower()
    reasons: list[str] = []

    for phrase in journey.get("expect") or []:
        if phrase.lower() not in text:
            reasons.append(f"missing expect: {phrase!r}")

    for phrase in journey.get("forbid") or []:
        if phrase.lower() in text:
            reasons.append(f"found forbidden: {phrase!r}")

    expect_any = journey.get("expect_any") or []
    if expect_any and not any(phrase.lower() in text for phrase in expect_any):
        reasons.append(f"none of expect_any present: {expect_any!r}")

    return (len(reasons) == 0, reasons)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``concierge_journeys_check.py '<journey-json-line>' < transcript.txt``.

    Prints PASS or one FAIL line per broken check; exits 0/1 accordingly.
    """
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(
            "usage: concierge_journeys_check.py '<journey-json-line>' < output.txt",
            file=sys.stderr,
        )
        return 2

    journey = json.loads(argv[0])
    output = sys.stdin.read()
    passed, reasons = check_journey(output, journey)
    if passed:
        print("PASS")
        return 0
    for reason in reasons:
        print(f"FAIL: {reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
