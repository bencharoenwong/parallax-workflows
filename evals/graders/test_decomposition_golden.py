"""Golden-decomposition acceptance for Phase 1 (the Assumption Map).

Every downstream status depends on decomposing the thesis into the RIGHT assumptions, yet the
tier-1 suite only checks that *some* layering happened (`assumption_map_layered` wants ≥2 layer
keywords). This module is stricter: it pins a couple of theses to the layer coverage and the
load-bearing set a correct decomposition must produce, so a Phase-1 regression (a collapsed map, a
missing structural/holder layer, the wrong keystone) fails in CI rather than silently corrupting
everything after it.

The golden maps encode analytical STRUCTURE (which layers, which keystone) — not any Parallax data —
so they are safe as tracked fixtures and stable across live runs.

This is a **contract test over synthetic transcripts**: it validates the checking logic (a flattened
or mis-layered map fails), not that the live model actually produces a correct decomposition. Live
conformance rests on the pending cold-session run — see
`skills/parallax-stress-test-thesis/COMPLIANCE.md`. "golden decomposition test" here means "pins the
grader contract", not "live-behaviour validation".
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "stress-test-thesis"))

from eval_spec import load_spec  # noqa: E402
from tier1_structural import _section_text  # noqa: E402

SPEC = load_spec("stress-test-thesis")


def map_layers(prose: str) -> set[int]:
    """Set of layer numbers present in the Assumption Map's `layer` column."""
    text = _section_text(prose, "Assumption Map", SPEC.section_labels)
    rows = [r for r in text.splitlines() if r.lstrip().startswith("|")]
    layers: set[int] = set()
    for row in rows[2:]:  # skip header + separator
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) >= 2:
            m = re.search(r"\b([1-5])\b", cells[1])
            if m:
                layers.add(int(m.group(1)))
    return layers


def load_bearing_ids(prose: str) -> list[str]:
    """Assumption ids named in the Load-Bearing Vulnerabilities section, in order."""
    text = _section_text(prose, "Pass 1 — Load-Bearing Vulnerabilities", SPEC.section_labels)
    out: list[str] = []
    for m in re.findall(r"\b([a-z]+-\d+)\b", text):
        if m not in out:
            out.append(m)
    return out


# --- golden fixtures: correct decompositions (structure only) --------------

_MACRO_LED = """## Thesis Restatement
A macro-led style rotation: rate cuts re-rate long-duration growth.

## Assumption Map
| id | layer | claim | criticality | testability |
|---|---|---|---|---|
| macro-1 | 1 (macro) | The Fed is starting a rate-cutting cycle | high | direct |
| macro-2 | 1 (macro) | Inflation is decelerating for three quarters | high | direct |
| theme-1 | 2 (sector/theme) | Growth outperforms value after the first cut | high | partial |
| implicit-1 | 4 (structural) | Lower discount rates actually re-rate multiples | high | partial |
| holder-1 | 5 (holder) | The holder can sit through the window | — | needs-client-profile |

## Pass 1 — Load-Bearing Vulnerabilities
macro-1 and implicit-1 carry the thesis; macro-2 is also load-bearing.

## Assumption-by-Assumption
| id | status | break_condition | magnitude | time_to_play_out |
|---|---|---|---|---|
| macro-1 | Contradicted | Fed holds | full regime turn | multi-quarter |
"""

_SINGLE_NAME = """## Thesis Restatement
A single-name bull case on PLTR.O leaning on cheap financing.

## Assumption Map
| id | layer | claim | criticality | testability |
|---|---|---|---|---|
| macro-1 | 1 (macro) | Risk-on backdrop persists | med | partial |
| pos-1 | 3 (position) | Margins expand as the platform scales | high | direct |
| implicit-1 | 4 (structural) | The company keeps funding expansion cheaply | high | partial |
| holder-1 | 5 (holder) | Can hold through a drawdown | — | needs-client-profile |

## Pass 1 — Load-Bearing Vulnerabilities
implicit-1 (cheap financing) and pos-1 are the load-bearing pair.

## Assumption-by-Assumption
| id | status | break_condition | magnitude | time_to_play_out |
|---|---|---|---|---|
| pos-1 | Unconfirmed | — | — | — |
"""

# expected: {thesis: (required_layers_subset, required_load_bearing_ids)}
_GOLDEN = {
    "macro_led_long": (_MACRO_LED, {1, 2, 4, 5}, {"macro-1", "implicit-1"}),
    "single_name_financing": (_SINGLE_NAME, {1, 3, 4, 5}, {"implicit-1", "pos-1"}),
}


def test_layer_coverage_matches_golden():
    for tid, (prose, want_layers, _) in _GOLDEN.items():
        got = map_layers(prose)
        assert want_layers <= got, f"{tid}: missing layers {want_layers - got} (got {got})"


def test_holder_layer_always_present():
    # layer 5 must be populated on every run, profile or not (skill invariant)
    for tid, (prose, _, _) in _GOLDEN.items():
        assert 5 in map_layers(prose), f"{tid}: holder layer (5) missing from the map"


def test_load_bearing_names_the_right_keystone():
    for tid, (prose, _, want_lb) in _GOLDEN.items():
        got = set(load_bearing_ids(prose))
        assert want_lb <= got, f"{tid}: load-bearing set {got} missing keystone(s) {want_lb - got}"


def test_collapsed_map_fails_layer_coverage():
    # a flattened 2-row map (macro only) must not satisfy the golden layer coverage
    flat = _MACRO_LED.replace(
        "| theme-1 | 2 (sector/theme) | Growth outperforms value after the first cut | high | partial |\n"
        "| implicit-1 | 4 (structural) | Lower discount rates actually re-rate multiples | high | partial |\n"
        "| holder-1 | 5 (holder) | The holder can sit through the window | — | needs-client-profile |\n",
        "",
    )
    assert not ({1, 2, 4, 5} <= map_layers(flat))


def test_structural_layer_not_dropped():
    # implicit/structural (layer 4) is the most-often-missed layer — pin it explicitly
    assert 4 in map_layers(_MACRO_LED) and 4 in map_layers(_SINGLE_NAME)
