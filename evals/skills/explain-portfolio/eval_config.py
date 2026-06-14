"""Eval spec for /parallax-explain-portfolio.

explain-portfolio is reactive drawdown attribution. Its core deliverables — a
score-vs-price divergence verdict (Transient/Fundamental/Ambiguous) and a computed
portfolio return — have no analogues in the other portfolio skills, so it uses several
skill-specific checks. Macro/regime is attribution layer 1 (get_telemetry + macro_analyst
always run), rendered as a standalone "Market & Regime Context".

Checks: sections_present, regime_context_grounded, ai_disclosure_present,
disclaimer_present_correct, provenance_present, return_quantified, divergence_verdict,
clean_start, orchestrator_length.
Tier-2: no_hallucinated_data, regime_specific, divergence_logic_sound,
advice_matches_verdict, return_reconciled_with_client.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "graders"))
from eval_spec import EvalSpec  # noqa: E402
from tier1_structural import Check, _section_text, _section_present  # noqa: E402
from judge_criteria import CRITERIA  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Unconditional sections in the PINNED state (no view, no white-label). "Market &
# Regime" / "The Key Question" use token-prefix matching to tolerate the "Context" /
# ": Noise or Signal?" trailers.
_REQUIRED_SECTIONS = [
    "What Happened", "Performance Attribution", "Market & Regime",
    "Factor Exposure", "Top Detractors", "The Key Question",
    "What To Do", "Provenance",
]
_SECTION_LABELS = [
    "House View Preamble", "Branding Header", "What Happened",
    "Performance Attribution", "Market & Regime Context", "Factor Exposure",
    "Top Detractors", "The Key Question: Noise or Signal?", "What To Do", "Provenance",
]

_REGIME_TERMS = re.compile(
    r"\b(regime|risk-?off|risk-?on|rotation|macro|tactical|sell-?off|selloff|"
    r"rally|drawdown|volatility|rates?|inflation|defensive|cyclical)\b", re.I,
)
_VERDICT_TOKENS = re.compile(r"\b(transient|fundamental|ambiguous|noise|signal|mixed)\b", re.I)
_PCT = re.compile(r"-?\d+(?:\.\d+)?\s*%")


def _c_regime_context_grounded(t, spec) -> Check:
    """Checks that the Market & Regime Context section is present and contains regime terms
    when get_telemetry or macro_analyst was called. Passes vacuously if neither ran."""
    if not (t.called("get_telemetry") or t.called("macro_analyst")):
        return Check("regime_context_grounded", True, "no regime tool called (vacuous)")
    sec = _section_text(t.final_prose, "Market & Regime", spec.section_labels)
    body = "\n".join(sec.splitlines()[1:]) if sec else ""  # drop header line
    ok = bool(body.strip()) and _REGIME_TERMS.search(body) is not None
    return Check("regime_context_grounded", ok, f"section_present={bool(sec)} body_terms={bool(_REGIME_TERMS.search(body))}")


def _c_divergence_verdict(t, spec) -> Check:
    """Checks that 'The Key Question: Noise or Signal?' section is present and contains
    a divergence classification (Transient/Fundamental/Ambiguous/noise/signal/mixed)."""
    sec = _section_text(t.final_prose, "The Key Question", spec.section_labels)
    if not sec:
        return Check("divergence_verdict", False, "Key Question section absent")
    body = "\n".join(sec.splitlines()[1:])
    ok = _VERDICT_TOKENS.search(body) is not None
    return Check("divergence_verdict", ok, f"verdict_token={bool(_VERDICT_TOKENS.search(body))}")


def _c_return_quantified(t, spec) -> Check:
    """Checks that 'What Happened' states a computed numeric portfolio return (a %).
    A qualitative description with no percentage figure fails."""
    sec = _section_text(t.final_prose, "What Happened", spec.section_labels)
    ok = bool(sec) and _PCT.search(sec) is not None
    return Check("return_quantified", ok, f"section_present={bool(sec)} pct={bool(_PCT.search(sec))}")


# Scaffold tokens that must NOT open the response; headers/titles that legitimately may.
_LEAK_START = re.compile(
    r"(?i)^\s*(?:\*\*)?(step\b|batch\b|all data\b|quick comp|cross-valid|"
    r"verified-holdings|white-?label\b|branding state|config_not_found|composing\b|"
    r"no active (house )?view|audit log|asset-?class|pre-?classif|"
    r"get_(news|assessment|telemetry|peer|score|company)|export_price|etf_profile|"
    r"tool (search|loading)|holdings? (loaded|parsed|classified|priced))"
)
# The skill titles the report with any of these (its description names "drawdown
# attribution" / "performance attribution" as synonyms); all are clean titles.
# Require a heading marker (#) OR bold (**) before the keyword (blocks bare-prose
# scaffold that opens with a section keyword, e.g. "what happened during init...").
_OK_START = re.compile(
    r"(?i)^\s*(?:#{1,4}\s*.*\b|\*\*\s*)"
    r"(explain portfolio|(portfolio |performance |drawdown )?attribution|"
    r"what happened|market & regime)\b"
)
_HR_OR_BLANK = re.compile(r"^[-*_ ]{0,}$|^[-*_ ]{3,}$")


def _c_clean_start(t, spec) -> Check:
    """Checks that the output begins with the rendered report title or the 'What Happened'
    section, not with internal scaffold (step announcements, tool/probe status, config-probes,
    audit-log narration). Leading blank/horizontal-rule lines are skipped."""
    first = ""
    for line in t.final_prose.splitlines():
        s = line.strip()
        if _HR_OR_BLANK.fullmatch(s):
            continue
        first = s
        break
    if _LEAK_START.search(first):
        ok = False
    elif _OK_START.search(first):
        ok = True
    else:
        ok = False
    return Check("clean_start", ok, f"first_line={first[:70]!r}")


_NO_HALLUC = next(c for c in CRITERIA if c["id"] == "no_hallucinated_data")  # COPIED

SPEC = EvalSpec(
    name="explain-portfolio",
    command="/parallax-explain-portfolio",
    rollout_prefix="explain-portfolio",
    skill_md_path=_REPO_ROOT / "skills" / "parallax-explain-portfolio" / "SKILL.md",
    required_sections=_REQUIRED_SECTIONS,
    section_labels=_SECTION_LABELS,
    check_ids=[
        "sections_present",             # COPIED
        "regime_context_grounded",      # ADAPTED
        "ai_disclosure_present",        # COPIED (§9.2)
        "disclaimer_present_correct",   # COPIED (§9.1)
        "provenance_present",           # COPIED
        "return_quantified",            # NEW
        "divergence_verdict",           # NEW
        "clean_start",                  # NEW
        "orchestrator_length",          # COPIED
    ],
    extra_checks={
        "regime_context_grounded": _c_regime_context_grounded,
        "return_quantified": _c_return_quantified,
        "divergence_verdict": _c_divergence_verdict,
        "clean_start": _c_clean_start,
    },
    tier2_criteria=[
        _NO_HALLUC,  # COPIED (generic)
        {
            "id": "regime_specific",  # ADAPTED
            "statement": "The Market & Regime Context is specific to the actual market(s) in the portfolio, not generic boilerplate.",
            "pass_when": "It names the real regime tag / mechanism for the relevant market, not 'markets are volatile' filler.",
        },
        {
            "id": "divergence_logic_sound",
            "statement": "Each holding's Transient/Fundamental/Ambiguous classification correctly follows from its score-vs-price pattern.",
            "pass_when": "price-down + scores-stable -> Transient; price-down + scores-down -> Fundamental; mixed -> Ambiguous. The label matches the evidence shown for that holding.",
        },
        {
            "id": "advice_matches_verdict",
            "statement": "The 'What To Do' advice is consistent with the portfolio-level Noise/Signal verdict.",
            "pass_when": "Transient verdict -> hold/stay-the-course; Fundamental -> investigate/trim the deteriorating names; Mixed -> separates the two. Advice does not contradict the verdict.",
        },
        {
            "id": "return_reconciled_with_client",
            "statement": "When the client stated a loss figure, the brief reconciles the COMPUTED return against it (confirming or flagging a >1% discrepancy).",
            "pass_when": "The computed portfolio return is compared to the client's stated number; a material gap is surfaced. If the client gave no number, the computed figure stands and this passes vacuously.",
        },
    ],
    tasks_path="evals/tasks/explain-portfolio/core.jsonl",
    orchestrator_max_lines=250,
)
