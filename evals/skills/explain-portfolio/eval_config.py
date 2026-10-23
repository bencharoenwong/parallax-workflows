"""Eval spec for /parallax-explain-portfolio.

explain-portfolio is reactive drawdown attribution. Its core deliverables — a
observational price/score divergence summary and an explicitly labeled
period-return illustration — have no analogues in the other portfolio skills, so it uses several
skill-specific checks. Macro/regime is attribution layer 1 (get_telemetry + macro_analyst
always run), rendered as a standalone "Market & Regime Context".

Checks: sections_present, regime_context_grounded, ai_disclosure_present,
disclaimer_present_correct, provenance_present, return_quantified, divergence_verdict, return_method_stated,
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
from judge_criteria import CRITERIA  # noqa: E402
from tier1_structural import Check, _section_text  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Unconditional sections in the PINNED state (no view, no white-label). "Market &
# Regime" / "The Key Question" use token-prefix matching to tolerate the "Context" /
# ": Noise or Signal?" trailers.
_REQUIRED_SECTIONS = [
    "What Happened",
    "Performance Attribution",
    "Market & Regime",
    "Factor Exposure",
    "Top Detractors",
    "The Key Question",
    "What To Do",
    "About This Report",
]
_SECTION_LABELS = [
    "House View Preamble",
    "Branding Header",
    "What Happened",
    "Performance Attribution",
    "Market & Regime Context",
    "Factor Exposure",
    "Top Detractors",
    "The Key Question: Noise or Signal?",
    "What To Do",
    "About This Report",
]

_REGIME_TERMS = re.compile(
    r"\b(regime|risk-?off|risk-?on|rotation|macro|tactical|sell-?off|selloff|"
    r"rally|drawdown|volatility|rates?|inflation|defensive|cyclical)\b",
    re.I,
)
_VERDICT_TOKENS = re.compile(
    r"\b(observed divergence|observed co-decline|mixed / insufficient evidence)\b", re.I
)
_PCT = re.compile(r"-?\d+(?:\.\d+)?\s*%")


def _c_regime_context_grounded(t, spec) -> Check:
    """Checks that the Market & Regime Context section is present and contains regime terms
    when get_telemetry or macro_analyst was called. Passes vacuously if neither ran."""
    if not (t.called("get_telemetry") or t.called("macro_analyst")):
        return Check("regime_context_grounded", True, "no regime tool called (vacuous)")
    sec = _section_text(t.final_prose, "Market & Regime", spec.section_labels)
    body = "\n".join(sec.splitlines()[1:]) if sec else ""  # drop header line
    ok = bool(body.strip()) and _REGIME_TERMS.search(body) is not None
    return Check(
        "regime_context_grounded",
        ok,
        f"section_present={bool(sec)} body_terms={bool(_REGIME_TERMS.search(body))}",
    )


def _c_divergence_verdict(t, spec) -> Check:
    """Checks that 'The Key Question: Noise or Signal?' section is present and contains
    an observational pattern, rather than treating the heading itself as evidence."""
    sec = _section_text(t.final_prose, "The Key Question", spec.section_labels)
    if not sec:
        return Check("divergence_verdict", False, "Key Question section absent")
    body = "\n".join(sec.splitlines()[1:])
    ok = _VERDICT_TOKENS.search(body) is not None
    return Check(
        "divergence_verdict", ok, f"verdict_token={bool(_VERDICT_TOKENS.search(body))}"
    )


def _c_return_method_stated(t, spec) -> Check:
    """Require a method label beside returns, not a disclaimer elsewhere.

    This checks explicit presentation only; the tier-2 criterion verifies whether
    the claimed method is supported by the supplied history and price evidence.
    """
    sec = _section_text(t.final_prose, "What Happened", spec.section_labels)
    pattern = re.compile(
        r"current-weight period illustration|static-weight period illustration|"
        r"verified account return|reconstructed (?:account|trading-history) return", re.I
    )
    ok = bool(sec) and pattern.search(sec) is not None
    return Check("return_method_stated", ok, f"method_label={ok}")


def _c_return_quantified(t, spec) -> Check:
    """Checks that 'What Happened' states a computed numeric portfolio return (a %).
    A qualitative description with no percentage figure fails."""
    sec = _section_text(t.final_prose, "What Happened", spec.section_labels)
    ok = bool(sec) and _PCT.search(sec) is not None
    return Check(
        "return_quantified",
        ok,
        f"section_present={bool(sec)} pct={bool(_PCT.search(sec))}",
    )


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
        "sections_present",  # COPIED
        "regime_context_grounded",  # ADAPTED
        "ai_disclosure_present",  # COPIED (§9.2)
        "disclaimer_present_correct",  # COPIED (§9.1)
        "provenance_present",  # COPIED
        "return_quantified",  # NEW
        "return_method_stated",
        "divergence_verdict",  # NEW
        "clean_start",  # NEW
        "orchestrator_length",  # COPIED
    ],
    extra_checks={
        "regime_context_grounded": _c_regime_context_grounded,
        "return_quantified": _c_return_quantified,
        "return_method_stated": _c_return_method_stated,
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
            "statement": "Price/score patterns are descriptive observations with dates, lag, competing explanations and unresolved evidence.",
            "pass_when": "Stable scores plus a loss are observed divergence, not proof of unchanged fundamentals or temporary loss. Co-decline does not establish causation. Missing/stale scores and news are stated; driver tags remain qualitative hypotheses unless a measured method supports them.",
        },
        {
            "id": "advice_matches_verdict",
            "statement": "What To Do addresses unresolved evidence and risk/mandate checks without deriving trading actions from price/score patterns.",
            "pass_when": "No hold/add/trim instruction follows solely from score stability, score decline or absent news; any optional investigation answers a stated unresolved question. Institutional view alignment does not establish client suitability.",
        },
        {
            "id": "return_reconciled_with_client",
            "statement": "Return method, weight dates, currency/price basis and coverage are explicit before comparison with a client loss figure.",
            "pass_when": "Current/end weights alone receive the current-weight period illustration label, never a realized account claim. A known entry date alone is insufficient. Realized claims require verified account returns or supported reconstruction of positions/trades/cash flows. Gaps greater than 1 percentage point and incompatible/unknown bases are disclosed, not called verified discrepancies. Unadjusted closes are not asserted as total returns.",
        },
    ],
    tasks_path="evals/tasks/explain-portfolio/core.jsonl",
    orchestrator_max_lines=250,
)
