"""Unit tests for the shared Parallax render gate.

Run: python3 -m pytest skills/_parallax/test_render_gate.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_gate import gate, SKILL_ANCHORS  # noqa: E402

SCAFFOLD = "**Step A.5 → Batch C complete.** Verified-holdings aggregates...\n\n"

# Real view_status.py banner strings, one per state (verified against the helper's
# f-string templates). The PREVIOUS per-skill gate test used a hand-written
# "> 🟡 House view: ..." banner that does NOT match production output — that false
# confidence let the active/warning/critical banners be stripped. These are the
# strings the gate must actually preserve.
REAL_BANNERS = {
    "active":            "Active house view: 'Q2 Defensive Tilt' — effective 2026-05-01 through 2026-08-01 (45 days remaining).",
    "warning":           "Active view 'Q2 Defensive Tilt' expires in 12 days (2026-06-20); consider refreshing soon.",
    "critical":          "⚠ Active view 'Q2 Defensive Tilt' expires in 5 day(s) (2026-06-13). Have you received an updated CIO view? Run /parallax-load-house-view to refresh.",
    "not_yet_effective": "House view 'Q3 View' becomes effective on 2026-07-01. Running without view until then.",
    "expired":           "! House view 'Q1 View' expired 3 day(s) ago (2026-06-01). Tilts NOT applied.",
}

PC_HEADER = "## Portfolio Health Status: 🟢 **Healthy** — 0 of 5 flags raised"
PC_BODY = PC_HEADER + "\n\nbody line\n\n## Consider\n- a question?\n"


# --- C1: every real house-view banner SURVIVES the strip ---------------------

def test_all_real_banners_survive_strip():
    for state, banner in REAL_BANNERS.items():
        draft = SCAFFOLD + banner + "\n\n" + PC_BODY
        out = gate(draft, "portfolio-checkup")
        first = out.lstrip().split("\n", 1)[0]
        assert banner[:25] in first, f"{state}: banner stripped -> {first!r}"


def test_regression_active_banner_not_eaten():
    # The exact bug: active banner begins "Active house view" (not "house view"),
    # so the old anchor missed it and stripped to the health-status line.
    draft = SCAFFOLD + REAL_BANNERS["active"] + "\n\n" + PC_BODY
    out = gate(draft, "portfolio-checkup")
    assert out.lstrip().startswith("Active house view:"), out[:80]


# --- C2: degraded-state note is HOISTED, not dropped -------------------------

def test_async_timeout_note_hoisted_not_deleted():
    draft = ("get_assessment timed out (~3 min) — AI assessment marked pending.\n\n"
             + PC_BODY)
    out = gate(draft, "portfolio-checkup")
    assert out.lstrip().startswith("## Portfolio Health Status"), out[:60]
    assert "timed out" in out, "degraded-state note was dropped (C2 violation)"
    assert "Status note (preserved)" in out


def test_pure_scaffold_not_hoisted():
    # Non-degraded scaffold must NOT produce a spurious status note.
    out = gate(SCAFFOLD + PC_BODY, "portfolio-checkup")
    assert "Status note" not in out


# --- C4: Branding Header (per-skill noun) + Ground-truth Integrity survive ----

def test_branding_header_survives_per_skill_noun():
    cases = {
        "client-review": "**Acme Capital** portfolio review",
        "morning-brief": "**Acme Capital** morning brief",
        "watchlist-monitor": "**Acme Capital** watchlist scan",
        "rebalance": "**Acme Capital** rebalance",
        "portfolio-builder": "**Acme Capital** portfolio construction",
        "explain-portfolio": "**Acme Capital** portfolio attribution",
    }
    for skill, hdr in cases.items():
        draft = SCAFFOLD + hdr + "\n\nbody\n"
        out = gate(draft, skill)
        assert "Acme Capital" in out.split("\n", 1)[0], (skill, out[:80])


def test_branding_logo_image_survives_above_text_line():
    # integration-pattern.md §5: a URL logo renders as `![client](url)` on its own line
    # ABOVE the branding text line. Both must survive the strip (regression for the
    # gemini-gate finding `branding-logo-stripped`).
    draft = (SCAFFOLD
             + "![Acme Capital](https://cdn.example.com/acme/logo.png)\n"
             + "**Acme Capital** portfolio review\n\n" + PC_BODY)
    out = gate(draft, "client-review")
    first = out.lstrip().split("\n", 1)[0]
    assert first.startswith("![Acme Capital]"), f"logo image stripped -> {first!r}"
    assert "Acme Capital" in out


def test_logo_url_with_pending_not_hoisted_as_status():
    # A pure image/link line whose URL contains a degraded token ("logo-pending.png")
    # must not be hoisted as a status note (gemini finding `degraded-regex-too-broad`).
    # The logo anchor preserves it anyway; assert no spurious status note is appended.
    draft = ("![Acme](https://cdn.example.com/acme/logo-pending.png)\n"
             + "**Acme** portfolio review\n\n" + PC_BODY)
    out = gate(draft, "client-review")
    assert "Status note (preserved)" not in out


def test_ground_truth_integrity_survives():
    draft = SCAFFOLD + "## Ground-truth Integrity\n| input | name |\n\n" + PC_BODY
    out = gate(draft, "client-review")
    assert out.lstrip().startswith("## Ground-truth Integrity"), out[:60]


# --- C5: fail-open ----------------------------------------------------------

def test_failopen_no_anchor_returns_input():
    junk = "no recognizable header here\nmore text\n"
    assert gate(junk, "portfolio-checkup") == junk


# --- per-skill: first rendered section anchors; scaffold stripped -------------

FIRST_SECTION = {
    "portfolio-checkup": "## Portfolio Health Status: 🔴 **Attention** — 2 flags",
    "client-review": "## Portfolio Summary",
    "morning-brief": "## Market Regime & Signals",
    "explain-portfolio": "## What Happened",
    "rebalance": "## Current Portfolio Assessment",
    "watchlist-monitor": "## Watchlist Summary",
    "portfolio-builder": "## Investment Thesis",
}


def test_each_skill_strips_scaffold_keeps_first_section():
    for skill, hdr in FIRST_SECTION.items():
        draft = SCAFFOLD + "No active house view, white-label inactive.\n\n" + hdr + "\nbody\n"
        out = gate(draft, skill)
        assert out.lstrip().startswith(hdr), (skill, out[:70])


def test_title_form_anchors_each_skill():
    titles = {
        "client-review": "# Client Portfolio Review — Conservative Retiree",
        "morning-brief": "# Fund Manager Morning Brief — 2026-06-14",
        "explain-portfolio": "# Drawdown Attribution",
        "rebalance": "# Portfolio Rebalance",
        "watchlist-monitor": "# Watchlist Scan — 7 names",
        "portfolio-builder": "# Portfolio Builder — US Tech",
    }
    for skill, title in titles.items():
        out = gate(SCAFFOLD + title + "\nbody\n", skill)
        assert out.lstrip().startswith("# "), (skill, out[:50])


def test_idempotent():
    draft = SCAFFOLD + REAL_BANNERS["active"] + "\n\n" + PC_BODY
    once = gate(draft, "portfolio-checkup")
    assert gate(once, "portfolio-checkup").strip() == once.strip()


def test_every_skill_has_anchors():
    for skill in ["portfolio-checkup", "client-review", "morning-brief",
                  "explain-portfolio", "rebalance", "watchlist-monitor",
                  "portfolio-builder"]:
        assert SKILL_ANCHORS.get(skill), f"no anchors for {skill}"
