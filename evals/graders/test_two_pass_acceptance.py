"""Offline paired-run acceptance for the two-pass client-conditioning invariant.

The single-transcript tier-1 engine cannot express the core two-pass guarantee — that the SAME
thesis under two different `client_profile`s keeps IDENTICAL Pass-1 statuses while diverging only in
client-conditioned severity/ranking. This module grades that guarantee over a PAIR of transcripts
(synthetic accumulator vs. retiree renders built from one thesis), so the riskiest rule — a client's
situation never rewrites what is true about the world — is covered by CI, not just prose and one
manual live run. It also confirms a profiled run carries the stronger disclaimer variant and a
no-profile run carries the standard one.

Pure helpers (pass1_status_map / client_conditioned_text / uses_stronger_disclaimer) take prose only.
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


def pass1_status_map(prose: str) -> dict:
    """{assumption_id: status} from the Assumption-by-Assumption table — the Pass-1 record that
    Pass 2 must never rewrite."""
    text = _section_text(prose, "Assumption-by-Assumption", SPEC.section_labels)
    out: dict[str, str] = {}
    for row in text.splitlines():
        if not row.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        cid, status = cells[0], cells[1].lower()
        st = next((s for s in ("contradicted", "supported", "unconfirmed") if s in status), None)
        if re.match(r"[a-z]+-\d+$", cid) and st:
            out[cid] = st
    return out


def client_conditioned_text(prose: str) -> str:
    return _section_text(prose, "Pass 2 — Client-Conditioned Vulnerabilities", SPEC.section_labels)


def uses_stronger_disclaimer(prose: str) -> bool:
    low = prose.lower()
    return "heuristic reasoning over a partial profile" in low or "not a calibrated" in low


# --- synthetic paired transcripts: ONE thesis, two profiles ----------------
# Identical Assumption Map + identical Pass-1 status table; only the Pass-2
# client-conditioning diverges (retiree harsher). This is exactly the shape a
# correct run must produce.

_SHARED_PASS1 = """~4 min read

## TL;DR
- Assumption Strength: 🔴 Weak — the keystone macro premise is Contradicted.

## Thesis Restatement
A macro-led long thesis: rate cuts re-rate long-duration growth.

## Coverage Notice
Full coverage — a US macro / equity-style thesis; every leg reads directly.

## Assumption Map
| id | layer | claim | criticality | testability |
|---|---|---|---|---|
| macro-1 | 1 (macro) | Fed cutting | high | direct |
| theme-1 | 2 (sector/theme) | growth outperforms value | high | partial |
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
🟡 Elevated — confirmation bias; premises asserted as settled fact.
"""

_STRONGER_DISC = (
    "\n\n---\nThis analysis was AI-interaction assisted. This report includes risk observations "
    "conditioned on the client profile supplied in this session. It is not investment advice and not "
    "a recommendation. The client-conditioned pass is heuristic reasoning over a partial profile, not "
    "a calibrated suitability model.\n"
)

_ACCUMULATOR = _SHARED_PASS1 + """
## Pass 2 — Client-Conditioned Vulnerabilities
Re-ranked by client_severity: macro-1 client_severity **med** — a 20+ year horizon absorbs the
multi-quarter break condition; the accumulator is not withdrawing, so the recovery path is intact.
Ranking unchanged vs. the Pass-1 world ranking.

## What to Watch
An easing pivot.
""" + _STRONGER_DISC

_RETIREE = _SHARED_PASS1 + """
## Pass 2 — Client-Conditioned Vulnerabilities
Re-ranked by client_severity: macro-1 client_severity **high** — a 2–3 year horizon is shorter than
the multi-quarter break, and drawing income during the drawdown removes the recovery path. Moved to
#1, a divergence from the Pass-1 world ranking.

## What to Watch
An easing pivot.
""" + _STRONGER_DISC

_NO_PROFILE = _SHARED_PASS1 + """
## What to Watch
An easing pivot.

---
This analysis was AI-interaction assisted. It is informational analysis, not investment advice.
This maps risk in an argument; it does not make a recommendation.
"""


# --- the paired-run acceptance assertions ----------------------------------

def test_pass1_statuses_identical_across_profiles():
    acc, ret = pass1_status_map(_ACCUMULATOR), pass1_status_map(_RETIREE)
    assert acc == ret and acc, f"Pass-1 statuses diverged: {acc} vs {ret}"


def test_pass1_matches_the_no_profile_baseline():
    # the profile must not change what Pass-1 found relative to the world (no-profile) run
    assert pass1_status_map(_ACCUMULATOR) == pass1_status_map(_NO_PROFILE)


def test_client_conditioning_diverges_between_profiles():
    acc, ret = client_conditioned_text(_ACCUMULATOR), client_conditioned_text(_RETIREE)
    assert acc.strip() and ret.strip() and acc != ret
    # the retiree read must be the harsher one on the shared load-bearing assumption
    assert "high" in ret.lower() and "med" in acc.lower()


def test_both_profiled_runs_use_stronger_disclaimer():
    assert uses_stronger_disclaimer(_ACCUMULATOR) and uses_stronger_disclaimer(_RETIREE)


def test_no_profile_run_uses_standard_disclaimer():
    assert not uses_stronger_disclaimer(_NO_PROFILE)
    assert "not investment advice" in _NO_PROFILE.lower()


def test_pass2_status_flip_is_caught():
    # a corrupted retiree run where Pass 2 rewrote macro-1 Contradicted -> Supported must be
    # detectable as a Pass-1 divergence (this is the failure the invariant exists to prevent)
    corrupted = _RETIREE.replace(
        "| macro-1 | Contradicted | Fed holds instead of cutting | full regime turn | multi-quarter |",
        "| macro-1 | Supported | Fed holds instead of cutting | full regime turn | multi-quarter |",
    )
    assert pass1_status_map(corrupted) != pass1_status_map(_ACCUMULATOR)
