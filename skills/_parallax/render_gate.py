#!/usr/bin/env python3
"""Shared deterministic render gate for the Parallax portfolio-family skills.

Strips any pre-report scaffold the orchestrating model may emit before the rendered
output (step/batch-completion notes, scratch computation, cross-validation status,
white-label config probes, "no active house view" narration). Pure stdlib; no network.

Mirrors the _parallax/house-view/view_status.py pattern: a deterministic helper the
skill shells out to as its final step, so behaviour is identical across operator LLMs
and not a generation-under-prior trust assumption. The skill pipes its complete drafted
report through this gate; the gate's stdout IS the response.

Design (one engine, per-skill allowlist):
- COMMON_ANCHORS: blocks that legitimately precede the body for ANY skill and MUST
  survive the strip — the House View Preamble banner (every real `view_status` banner
  state) and the Ground-truth Integrity table.
- SKILL_ANCHORS[<skill>]: that skill's title, first rendered section, and Branding
  Header (matched on the skill's own header noun).
- The gate keeps from the EARLIEST line matching ANY anchor (preamble/branding, when
  present, precede the body), so anchor precedence is by line position.
- Degraded-state notes (async-timeout / pending / unavailable) found in the stripped
  preamble are HOISTED to a trailing status line, never silently dropped.
- Fail-open: if NO anchor is found the input is returned unchanged — the gate never
  destroys a report it cannot positively locate.

Usage:
    python3 render_gate.py --skill client-review < draft.md     # clean report -> stdout
    echo "$DRAFT" | python3 render_gate.py --skill morning-brief
"""
from __future__ import annotations

import argparse
import re
import sys

# --- COMMON anchors: must survive the strip for every skill (C1, C4) ---------

# House View Preamble banner — matches EVERY real `view_status.py` banner state
# (verified against the helper): active "Active house view: ...", warning/critical
# "Active view ..." / "⚠ Active view ...", not_yet_effective/expired/malformed
# "House view ..." / "! House view ...", and the "Legacy view:" warning. Optional
# leading blockquote, status emoji or "!", and bold.
_HOUSE_VIEW = (
    r"^\s{0,3}>?\s*(?:🟢|🟡|🔴|⚠|ℹ️|!)?\s*\*{0,2}\s*"
    r"(?:active\s+(?:house\s+)?view|house\s+view|legacy\s+view)\b"
)
# Ground-truth Integrity table — renders first on a holding-name mismatch (C4).
_GROUND_TRUTH = r"^\s{0,3}(?:#{1,4}\s*.*\b|\*\*\s*)ground-?truth\b"

COMMON_ANCHORS = [_HOUSE_VIEW, _GROUND_TRUTH]


def _branding(noun: str) -> str:
    """Branding Header anchor for a skill: `(## )(> )**<client>** <noun>` (C4).
    Matched on the skill's own header noun, never a hardcoded one."""
    return rf"^\s{{0,3}}(?:#{{1,4}}\s+)?>?\s*\*\*[^*]+\*\*\s+{noun}\b"


# --- Per-skill anchors: title + first rendered section + Branding Header ------
# Title/section anchors accept a markdown HEADER (^#{1,4}) with the keyword anywhere on
# the line (titles carry descriptive suffixes / emojis, e.g. "## Why am I down —
# Portfolio Attribution"), OR a BOLD line with the keyword IMMEDIATELY after the `**`
# (a bold title like "**Watchlist scan — ...**"). The bold branch requires the keyword
# right after the marker so a bold SCAFFOLD sentence ("**Batch D ... rebalance works**")
# does NOT match. The Branding Header is handled separately (_branding, noun-specific).
# Mirrors each eval-config _OK_START exactly (gate and grader agree on "valid opening").
SKILL_ANCHORS: dict[str, list[str]] = {
    "portfolio-checkup": [
        r"^\s{0,3}(?:#{1,4}\s*.*\b|\*\*\s*)(?:portfolio health|health status)\b",
        r"^\s{0,3}#\s*(?:your\s+)?portfolio checkup\b",
        _branding("portfolio checkup"),
    ],
    "client-review": [
        r"^\s{0,3}(?:#{1,4}\s*.*\b|\*\*\s*)(?:client portfolio review|portfolio review|portfolio summary)\b",
        _branding("portfolio review"),
    ],
    "morning-brief": [
        r"^\s{0,3}(?:#{1,4}\s*.*\b|\*\*\s*)(?:(?:fund manager )?morning brief|market regime)\b",
        _branding("morning brief"),
    ],
    "explain-portfolio": [
        r"^\s{0,3}(?:#{1,4}\s*.*\b|\*\*\s*)(?:explain portfolio|(?:portfolio |performance |drawdown )?attribution|what happened|market & regime)\b",
        _branding("portfolio attribution"),
    ],
    "rebalance": [
        r"^\s{0,3}(?:#{1,4}\s*.*\b|\*\*\s*)(?:portfolio rebalance|rebalance|current portfolio(?: assessment)?)\b",
        _branding("rebalance"),
    ],
    "watchlist-monitor": [
        r"^\s{0,3}(?:#{1,4}\s*.*\b|\*\*\s*)watchlist (?:monitor|summary|scan)\b",
        _branding("watchlist scan"),
    ],
    "portfolio-builder": [
        r"^\s{0,3}(?:#{1,4}\s*.*\b|\*\*\s*)(?:portfolio builder|portfolio construction|investment thesis)\b",
        _branding("portfolio construction"),
    ],
}

# Degraded-state markers worth preserving if the model leaked them into the preamble
# (C2): async-tool timeouts, pending/unavailable analyses, partial coverage. The gate
# hoists these to a trailing status line rather than dropping them with the scaffold.
_DEGRADED = re.compile(
    r"(?i)\b(timed out|timeout|pending|unavailable|could not (?:be )?comput|"
    r"partial(?:ly)?|degraded|not (?:yet )?available)\b"
)


def gate(draft: str, skill: str) -> str:
    """Return ``draft`` from its first rendered-block anchor onward (else unchanged),
    hoisting any degraded-state note out of the stripped preamble.

    Unknown skill -> COMMON anchors only (still strips to a surviving preamble block;
    fail-open if none). Raises nothing; never destroys an unlocatable report."""
    patterns = COMMON_ANCHORS + SKILL_ANCHORS.get(skill, [])
    anchor_re = re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)
    lines = draft.splitlines()
    for i, line in enumerate(lines):
        if anchor_re.search(line):
            body = "\n".join(lines[i:]).strip()
            notes = [ln.strip() for ln in lines[:i] if ln.strip() and _DEGRADED.search(ln)]
            if notes:
                body += "\n\n> _Status note (preserved): " + " ".join(notes) + "_"
            return body + "\n"
    return draft  # fail-open: no anchor -> never strip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Shared Parallax render gate.")
    ap.add_argument("--skill", required=True, help="skill key, e.g. client-review")
    args = ap.parse_args(argv)
    sys.stdout.write(gate(sys.stdin.read(), args.skill))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
