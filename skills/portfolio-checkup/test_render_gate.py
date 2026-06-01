"""Unit tests for the portfolio-checkup render gate.

Run: python3 -m pytest skills/portfolio-checkup/test_render_gate.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_gate import gate  # noqa: E402

HEADER = "## Portfolio Health Status: 🟢 **Healthy** — 0 of 5 flags raised"
BODY = HEADER + "\n\nbody line\n\n## Consider\n- a question?\n"

# Pre-report scaffold prefixes the skill can emit before the report header.
LEAKS = [
    "**Step A.5 → Batch C complete.** Verified-holdings aggregates...\n\n| t |\n\n",
    "**White-label:** `config_not_found` → not active. No branding header.\n\n",
    "All data gathered and cross-validated. Composing the report.\n\n---\n\n",
    "All data in. **Step A.5** cleared all 7 holdings (100% V2 coverage).\n\n",
    "**Weighted aggregates (verified set):** Overall **6.3**\n**Health flags:** Low Score ✗\n\n",
]


def test_strips_each_observed_leak():
    for leak in LEAKS:
        out = gate(leak + BODY)
        assert out.lstrip().startswith("## Portfolio Health Status"), out[:80]


def test_clean_output_unchanged_modulo_trailing_ws():
    assert gate(BODY).strip() == BODY.strip()


def test_failsafe_no_anchor_returns_input():
    junk = "no recognizable header here\nmore text\n"
    assert gate(junk) == junk  # never destroy an unlocatable report


def test_idempotent():
    once = gate(LEAKS[0] + BODY)
    assert gate(once).strip() == once.strip()


def test_does_not_anchor_on_bold_scaffold():
    # "**Health flags:**" is scaffold, not a heading — must be stripped, not kept.
    draft = "**Health flags:** Low Score ✗\n\n" + HEADER + "\nbody\n"
    assert gate(draft).lstrip().startswith("## Portfolio Health Status")


def test_label_variants_anchor():
    # pre-fix the model dropped "Status"/"Portfolio" inconsistently; gate still anchors.
    for hdr in [
        "## Health Status: 🔴 **Attention** — 2 of 5 flags raised",
        "## 🟢 Portfolio Health: **Healthy** — 0 flags",
        "# Your Portfolio Checkup",
    ]:
        out = gate("**Step A.5 complete.**\n\n" + hdr + "\nbody\n")
        assert out.lstrip().startswith(hdr.split("\n")[0][:6]), out[:60]


def test_branding_header_anchors_and_is_preserved():
    # White-label: scaffold precedes the Branding Header, no health-status line yet.
    # The gate must anchor on the branding header (not strip it), in plain and
    # heading-prefixed forms.
    for hdr in ["**Acme Capital** portfolio checkup",
                "## **Acme Capital** portfolio checkup",
                "> **Acme Capital** portfolio checkup"]:
        draft = "**Step A.5 complete.** scratch\n\n" + hdr + "\n\n" + HEADER + "\nbody\n"
        out = gate(draft)
        assert "Acme Capital" in out.split("\n", 1)[0], (hdr, out[:80])


def test_preamble_preserved_when_active():
    # House View Preamble legitimately precedes the health-status line.
    draft = "**Step A.5 complete.**\n\n> 🟡 House view: Q2 tilt active (12d left)\n\n" + HEADER + "\n"
    out = gate(draft)
    assert "House view" in out.split("\n", 1)[0]
