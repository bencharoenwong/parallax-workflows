"""Unit tests for the stress-test-thesis eval spec's skill-specific checks
(verdict_no_rec, json_no_rec, assumption_map_layered, break_condition_fields, read_time_marker).
Red/green before any live spend. Mirrors the other per-skill test files.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eval_spec import load_spec  # noqa: E402
from tier1_structural import grade_tier1  # noqa: E402
from transcript import Transcript  # noqa: E402

SPEC = load_spec("stress-test-thesis")


def _results(prose: str) -> dict:
    t = Transcript(final_prose=prose)
    return {c.name: c.passed for c in grade_tier1(t, SPEC)}


GOLDEN = """~4 min read

## TL;DR
- Assumption Strength: 🔴 Weak — the keystone macro premise is Contradicted.
- Rates the argument, not the security.

## Thesis Restatement
A macro-led long thesis: rate cuts re-rate long-duration growth.

## Coverage Notice
Full coverage — a US-macro / equity-style thesis; every leg reads directly, no partial or out-of-scope legs.

## Assumption Map
| id | layer | claim | criticality | testability |
|---|---|---|---|---|
| macro-1 | 1 (macro) | Fed cutting | high | direct |
| theme-1 | 2 (sector/theme) | growth outperforms value | high | partial |
| implicit-1 | 4 (structural) | multiples re-rate | high | partial |
| holder-1 | 5 (holder) | can hold through the window | — | needs-client-profile |

## Pass 1 — Load-Bearing Vulnerabilities
macro-1 is load-bearing and Contradicted.

## Assumption-by-Assumption
| id | status | break_condition | magnitude | time_to_play_out |
|---|---|---|---|---|
| macro-1 | Contradicted | Fed holds instead of cutting | full regime turn | multi-quarter |
| theme-1 | Supported | rotation stalls | 25bp surprise | weeks |
| macro-9 | Unconfirmed | — | — | — |

## World Verdict
Assumption Strength: Weak. The chain fails at the entry premise.

## Bias & Conviction Check
🟡 Elevated — narrative fallacy: the "macro shift" story carries the case past a falsifiable step, though the core macro premise stays testable.

## What to Watch
An easing pivot; curve re-steepening.

## Confidence & Caveats
Macro read dated 2026-06-24; two weeks stale. The 🔴/🟡/🟢 Assumption-Strength and Bias & Conviction lights are heuristic reads of argument quality, not outcome-calibrated scores.

---
This analysis was AI-interaction assisted. It is informational analysis, not investment advice.
"""


def test_golden_passes_every_check():
    res = _results(GOLDEN)
    assert all(res.values()), [n for n, p in res.items() if not p]


# --- read_time_marker (NEW) -----------------------------------------------


def test_read_time_marker_red_when_absent():
    no_marker = GOLDEN.replace("~4 min read", "Stress-Test Report")
    assert _results(no_marker)["read_time_marker"] is False


def test_read_time_marker_tolerates_spacing():
    assert _results(GOLDEN.replace("~4 min read", "~ 12  min read"))["read_time_marker"] is True


# --- tldr_strength_light (NEW) ---------------------------------------------


def test_tldr_strength_light_green_on_golden():
    # GOLDEN carries "🔴 Weak" — the matching glyph for the Weak label.
    assert _results(GOLDEN)["tldr_strength_light"] is True


def test_tldr_strength_light_red_when_glyph_missing():
    no_glyph = GOLDEN.replace("🔴 Weak", "Weak")
    assert _results(no_glyph)["tldr_strength_light"] is False


def test_tldr_strength_light_red_on_mismatched_glyph():
    # Weak label with a green light is a contradiction — must trip the check.
    mismatched = GOLDEN.replace("🔴 Weak", "🟢 Weak")
    assert _results(mismatched)["tldr_strength_light"] is False


def test_tldr_strength_light_green_for_strong_label():
    strong = GOLDEN.replace(
        "- Assumption Strength: 🔴 Weak — the keystone macro premise is Contradicted.",
        "- Assumption Strength: 🟢 Strong — the load-bearing set is Supported.",
    )
    assert _results(strong)["tldr_strength_light"] is True


def test_tldr_strength_light_vacuous_when_no_strength_line():
    # A render with no Assumption Strength line in the TL;DR must not fail this check.
    no_line = GOLDEN.replace(
        "- Assumption Strength: 🔴 Weak — the keystone macro premise is Contradicted.\n",
        "",
    )
    assert _results(no_line)["tldr_strength_light"] is True


# --- hype_meter_light (NEW) ------------------------------------------------


def test_hype_meter_light_green_on_golden():
    # GOLDEN's Bias & Conviction Check carries "🟡 Elevated" — the matching glyph.
    assert _results(GOLDEN)["hype_meter_light"] is True


def test_hype_meter_light_red_when_glyph_missing():
    no_glyph = GOLDEN.replace("🟡 Elevated", "Elevated")
    assert _results(no_glyph)["hype_meter_light"] is False


def test_hype_meter_light_red_on_mismatched_glyph():
    # Elevated label wearing the High (🔴) light is a contradiction — must trip.
    mismatched = GOLDEN.replace("🟡 Elevated", "🔴 Elevated")
    assert _results(mismatched)["hype_meter_light"] is False


def test_hype_meter_light_green_for_high_label():
    high = GOLDEN.replace(
        "🟡 Elevated — narrative fallacy: the \"macro shift\" story carries the case past a falsifiable step, though the core macro premise stays testable.",
        "🔴 High — heavy superlatives and no acknowledged bear case.",
    )
    assert _results(high)["hype_meter_light"] is True


def test_hype_meter_light_green_when_sibling_level_named_in_prose():
    # Regression (live-eval finding): a reading may explain itself against a sibling
    # level on the same line ("… it is not 🔴 High …") — only the label's own bound
    # glyph is graded, so the negated 🔴 must NOT trip the check.
    prose = GOLDEN.replace(
        "🟡 Elevated — narrative fallacy: the \"macro shift\" story carries the case past a falsifiable step, though the core macro premise stays testable.",
        "🟡 Elevated — confirmation bias; it is not 🔴 High because the claims stay falsifiable.",
    )
    assert _results(prose)["hype_meter_light"] is True


def test_tldr_strength_light_green_when_sibling_level_named_in_prose():
    # Same regression on the TL;DR strength line.
    prose = GOLDEN.replace(
        "- Assumption Strength: 🔴 Weak — the keystone macro premise is Contradicted.",
        "- Assumption Strength: 🔴 Weak — far from 🟢 Strong; the keystone premise is Contradicted.",
    )
    assert _results(prose)["tldr_strength_light"] is True


def test_hype_meter_light_vacuous_when_no_section():
    # A render without the Bias & Conviction Check section must not fail this check.
    no_sec = GOLDEN.replace(
        "## Bias & Conviction Check\n"
        "🟡 Elevated — narrative fallacy: the \"macro shift\" story carries the case past a falsifiable step, though the core macro premise stays testable.\n\n",
        "",
    )
    assert _results(no_sec)["hype_meter_light"] is True


# --- TL;DR is a required section (standard render) --------------------------


def test_tldr_required():
    no_tldr = GOLDEN.replace("## TL;DR", "## Summary")
    assert _results(no_tldr)["sections_present"] is False


def test_coverage_notice_required():
    # The early full/partial/out-of-scope disclosure is standard render, not optional.
    no_cov = GOLDEN.replace("## Coverage Notice", "## Coverage Info")
    assert _results(no_cov)["sections_present"] is False


def test_bias_conviction_check_required():
    # The "hype meter" is standard render — its omission must trip sections_present.
    no_bias = GOLDEN.replace("## Bias & Conviction Check", "## Vibe Check")
    assert _results(no_bias)["sections_present"] is False


# --- assumption_map_layered (NEW) ------------------------------------------


def test_assumption_map_layered_red_when_flat():
    flat = GOLDEN.replace(
        "| macro-1 | 1 (macro) | Fed cutting | high | direct |\n"
        "| theme-1 | 2 (sector/theme) | growth outperforms value | high | partial |\n"
        "| implicit-1 | 4 (structural) | multiples re-rate | high | partial |\n"
        "| holder-1 | 5 (holder) | can hold through the window | — | needs-client-profile |",
        "| a-1 | 1 | Fed cutting | high | direct |\n"
        "| a-2 | 2 | growth outperforms | high | partial |",
    )
    assert _results(flat)["assumption_map_layered"] is False


def test_assumption_map_layered_ignores_stray_prose_keyword():
    # A layer keyword in surrounding prose (not the table cells) must not by
    # itself satisfy the check — the check is scoped to the id/layer columns.
    stray = GOLDEN.replace(
        "| macro-1 | 1 (macro) | Fed cutting | high | direct |\n"
        "| theme-1 | 2 (sector/theme) | growth outperforms value | high | partial |\n"
        "| implicit-1 | 4 (structural) | multiples re-rate | high | partial |\n"
        "| holder-1 | 5 (holder) | can hold through the window | — | needs-client-profile |",
        "| a-1 | 1 | Fed cutting | high | direct |",
    )
    stray = stray.replace(
        "## Thesis Restatement\nA macro-led long thesis: rate cuts re-rate long-duration growth.",
        "## Thesis Restatement\nA macro sector theme holder position implicit backdrop.",
    )
    assert _results(stray)["assumption_map_layered"] is False


# --- break_condition_fields (NEW) ------------------------------------------


def test_break_condition_fields_red_when_magnitude_missing():
    missing = GOLDEN.replace(
        "| macro-1 | Contradicted | Fed holds instead of cutting | full regime turn | multi-quarter |",
        "| macro-1 | Contradicted | Fed holds instead of cutting | — | multi-quarter |",
    )
    assert _results(missing)["break_condition_fields"] is False


def test_break_condition_fields_red_when_time_missing():
    missing = GOLDEN.replace(
        "| theme-1 | Supported | rotation stalls | 25bp surprise | weeks |",
        "| theme-1 | Supported | rotation stalls | 25bp surprise | |",
    )
    assert _results(missing)["break_condition_fields"] is False


def test_break_condition_fields_exempts_unconfirmed():
    # An Unconfirmed row with empty magnitude/time is legitimate — no break
    # condition to size. The GOLDEN already has one; it must not trip the check.
    assert _results(GOLDEN)["break_condition_fields"] is True


# --- disclaimer wording parity across both variants -------------------------
# The shared `disclaimer_present_correct` check keys off the literal
# "not investment advice". The no-profile path renders §9.1 (which carries the
# token); the stronger profile variant must carry it too, or a profiled run would
# silently fail the disclaimer gate. These guard that parity.

_STRONGER_VARIANT = (
    "This report includes risk observations conditioned on the client profile "
    "supplied in this session. It is not investment advice and not a recommendation "
    "to buy, sell, or hold any security."
)


def test_stronger_disclaimer_variant_carries_investment_advice_token():
    assert "not investment advice" in _STRONGER_VARIANT.lower()


def test_stronger_disclaimer_variant_passes_shared_check():
    prose = GOLDEN.replace(
        "This analysis was AI-interaction assisted. It is informational analysis, not investment advice.",
        "This analysis was AI-interaction assisted.\n\n" + _STRONGER_VARIANT,
    )
    assert _results(prose)["disclaimer_present_correct"] is True


# --- lights_heuristic_disclosed (mandatory heuristic caveat) ----------------


def test_lights_heuristic_disclosed_on_golden():
    assert _results(GOLDEN)["lights_heuristic_disclosed"] is True


def test_lights_heuristic_disclosed_red_when_absent():
    # Drop the heuristic caveat from Confidence & Caveats — the check must fail (mandatory).
    no_caveat = GOLDEN.replace(
        " The 🔴/🟡/🟢 Assumption-Strength and Bias & Conviction lights are heuristic reads of argument quality, not outcome-calibrated scores.",
        "",
    )
    assert _results(no_caveat)["lights_heuristic_disclosed"] is False


def test_lights_heuristic_disclosed_satisfied_by_profile_disclaimer():
    # A profiled run carries "heuristic reasoning … not a calibrated suitability model" in its
    # stronger disclaimer, which satisfies the disclosure even without the C&C line.
    prose = GOLDEN.replace(
        " The 🔴/🟡/🟢 Assumption-Strength and Bias & Conviction lights are heuristic reads of argument quality, not outcome-calibrated scores.",
        "",
    ).replace(
        "This analysis was AI-interaction assisted. It is informational analysis, not investment advice.",
        "This analysis was AI-interaction assisted. The client-conditioned pass is heuristic reasoning "
        "over a partial profile, not a calibrated suitability model. It is not investment advice.",
    )
    assert _results(prose)["lights_heuristic_disclosed"] is True


# --- verdict_no_rec (hardened: casual imperatives, not just formal tokens) --


def test_verdict_no_rec_red_on_casual_imperative():
    rec = GOLDEN.replace("The chain fails at the entry premise.", "You should buy this now.")
    assert _results(rec)["verdict_no_rec"] is False


def test_verdict_no_rec_red_on_formal_rating_token():
    rec = GOLDEN.replace("The chain fails at the entry premise.", "Rating: buy.")
    assert _results(rec)["verdict_no_rec"] is False


def test_verdict_no_rec_red_on_we_recommend():
    rec = GOLDEN.replace("The chain fails at the entry premise.", "We recommend buying the basket.")
    assert _results(rec)["verdict_no_rec"] is False


def test_verdict_no_rec_green_on_legit_market_vocab():
    # Legitimate market vocabulary a verdict may use must NOT trip the guard.
    for phrase in [
        "Institutional buy-side flows keep coming.",
        "A sharp sell-off would flip macro-2.",
        "Sell-side targets sit modestly above spot.",
        "The thesis holds only if the curve steepens.",
        "The holder can hold through the drawdown.",
        "Buying pressure has not materialized.",
    ]:
        prose = GOLDEN.replace("The chain fails at the entry premise.", phrase)
        assert _results(prose)["verdict_no_rec"] is True, phrase


# --- json_no_rec (structured-output recommendation guard) -------------------


def test_json_no_rec_red_on_json_rating_key():
    prose = GOLDEN + '\n```json\n{"rating": "buy"}\n```\n'
    assert _results(prose)["json_no_rec"] is False


def test_json_no_rec_red_on_nested_action_key():
    prose = GOLDEN + '\n```json\n{"positions": [{"action": "sell"}]}\n```\n'
    assert _results(prose)["json_no_rec"] is False


def test_json_no_rec_green_when_no_json():
    assert _results(GOLDEN)["json_no_rec"] is True


def test_json_no_rec_green_on_benign_structured_keys():
    prose = GOLDEN + '\n```\n{"assumptions": ["rate cuts"], "layer": "macro"}\n```\n'
    assert _results(prose)["json_no_rec"] is True


def test_json_no_rec_green_on_invalid_json_fence():
    prose = GOLDEN + '\n```json\n{"rating": "buy",}\n```\n'
    assert _results(prose)["json_no_rec"] is True
