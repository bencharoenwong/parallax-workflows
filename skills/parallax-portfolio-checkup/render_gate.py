#!/usr/bin/env python3
"""Deterministic render gate for /parallax-portfolio-checkup.

Strips any pre-report scaffold the orchestrating model may emit before the
rendered output (step-completion notes, scratch computation tables, cross-
validation status lines, white-label config probes). Pure stdlib; no network.

Mirrors the _parallax/house-view/view_status.py pattern: a deterministic helper
the skill shells out to so the behaviour is identical across operator LLMs and
not a generation-under-prior trust assumption. The skill's final step pipes its
complete drafted report through this gate; the gate's stdout IS the response.

The strip anchor is the first line that opens a *rendered* block, in priority
order: House View Preamble banner, Branding Header, Portfolio Health Status, or
the '# Portfolio Checkup' title. Everything before it is internal scaffold and
is dropped. If NO anchor is found the input is returned unchanged (fail-safe —
the gate never destroys a report it cannot positively locate).

Usage:
    python3 render_gate.py < draft.md        # clean report -> stdout
    echo "$DRAFT" | python3 render_gate.py
"""
from __future__ import annotations

import re
import sys

# First-line anchors for a rendered block, highest-precedence first. The gate
# keeps from the EARLIEST matching line onward (a Preamble/Branding Header, when
# active, legitimately precedes the Health Status line).
# Header-form only (^#{1,4}) so the gate never anchors on bold scaffold lines
# like "**Health flags:**" or "**Health flag evaluation**" — only on a rendered
# section heading. Covers the observed label variants: "Portfolio Health Status",
# "Health Status", and "Portfolio Health" (the model drops "Status"/"Portfolio"
# inconsistently pre-fix; the prompt fix standardises to the first form).
_ANCHORS = [
    r"^\s{0,3}#{1,4}\s*.*\b(?:portfolio health|health status)\b",   # ## (Portfolio) Health (Status): ...
    r"^\s{0,3}#\s*(?:your\s+)?portfolio checkup\b",                  # # (Your) Portfolio Checkup
    r"^\s{0,3}(?:#{1,4}\s+)?>?\s*\*\*[^*]+\*\*\s+portfolio checkup\b",  # Branding Header: (## )**<client>** portfolio checkup
    r"^\s{0,3}>?\s*(?:🟢|🟡|🔴|⚠|ℹ️)?\s*\*?\*?house view\b",          # House View Preamble banner
]
_ANCHOR_RE = re.compile("|".join(f"(?:{p})" for p in _ANCHORS), re.IGNORECASE)


def gate(draft: str) -> str:
    """Return draft from its first rendered-block anchor onward (else unchanged)."""
    lines = draft.splitlines()
    for i, line in enumerate(lines):
        if _ANCHOR_RE.search(line):
            return "\n".join(lines[i:]).strip() + "\n"
    return draft  # fail-safe: no anchor -> never strip


def main() -> int:
    sys.stdout.write(gate(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
