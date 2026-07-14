"""Tier-1 deterministic structural checks — spec-driven, skill-agnostic engine.

Pure functions over a parsed Transcript. Each check reads what it needs from an
EvalSpec (required sections, section labels, orchestrator path/limit), so the
same engine grades any skill. `grade_tier1(t, spec)` runs exactly the checks in
`spec.check_ids`. With no spec it defaults to should-i-buy (backward compat).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from eval_spec import EvalSpec, load_spec
from transcript import Transcript

_DEFAULT_SKILL = "should-i-buy"


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


_REC_PATTERNS = [
    r"\bstrong buy\b", r"\bstrong sell\b",
    r"\bwe recommend (buy|sell)", r"\b(buy|sell) recommendation\b",
    r"\brating:\s*(buy|sell)\b", r"\bi recommend (buying|selling)\b",
]

# Trend-direction phrasings accepted in a scores section (before/after values).
_TREND_PATTERNS = [
    r"from\s+\d+(?:\.\d+)?\s+to\s+\d+(?:\.\d+)?",            # "from 5.8 to 7.2"
    r"\d+(?:\.\d+)?\s*(?:→|->|—>|–>)\s*\d+(?:\.\d+)?",        # "5.8 → 7.2"
    r"(?:up|down)\s+from\s+\d+(?:\.\d+)?",                    # "up from 5.8"
]


def _norm_tokens(text: str) -> list[str]:
    """Lowercase word tokens, punctuation stripped (so 'vs.' == 'vs')."""
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()


def _label_prefix(line: str) -> list[str]:
    """Normalized token list of a line after stripping leading #>*_ markers."""
    return _norm_tokens(re.sub(r"^[#>*_\s]+", "", line.strip()))


def _section_present(prose: str, heading: str) -> bool:
    """True if `heading` labels a line, as a markdown heading OR an emphasis label.

    Match by stripping leading markers (#, *, _, >) and comparing punctuation-free
    token prefixes, so heading depth, a trailing 'vs.' period, and italic/bold
    labels all match.
    """
    target = _norm_tokens(heading)
    if not target:
        return False
    for line in prose.splitlines():
        if _label_prefix(line)[: len(target)] == target:
            return True
    return False


def _section_text(prose: str, heading: str, labels: list[str]) -> str:
    """Return one section's text: from its label line to the next section's.

    Consistent with _section_present (label may be heading OR emphasis label).
    The end boundary is the next line whose token-prefix matches a *different*
    known section label in `labels` (so bold sub-labels inside the body, e.g.
    '**Quality**', do not truncate it). Returns "" if the heading is absent.
    """
    target = _norm_tokens(heading)
    if not target:
        return ""
    others = [_norm_tokens(s) for s in labels if _norm_tokens(s) != target]
    lines = prose.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _label_prefix(line)[: len(target)] == target:
            start = i
            break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start + 1, len(lines)):
        pref = _label_prefix(lines[j])
        if any(pref[: len(o)] == o for o in others):
            end = j
            break
    return "\n".join(lines[start:end])


# --- Checks: each takes (transcript, spec) ----------------------------------

def _c_sections_present(t: Transcript, spec: EvalSpec) -> Check:
    missing = [s for s in spec.required_sections if not _section_present(t.final_prose, s)]
    return Check("sections_present", not missing, f"missing={missing}")


def _c_scores_trend_direction(t: Transcript, spec: EvalSpec) -> Check:
    scores = _section_text(t.final_prose, "The Scores", spec.section_labels)
    ok = any(re.search(p, scores, re.I) for p in _TREND_PATTERNS)
    return Check("scores_trend_direction", ok, "trend direction (X to Y / X → Y / up from X) in The Scores")


def _c_macro_conditional(t: Transcript, spec: EvalSpec) -> Check:
    macro_called = t.called("macro_analyst")
    macro_section = _section_present(t.final_prose, "Macro Context")
    ok = macro_called == macro_section
    return Check("macro_conditional", ok, f"macro_called={macro_called} section={macro_section}")


def _c_dividends_explicit(t: Transcript, spec: EvalSpec) -> Check:
    ok = _section_present(t.final_prose, "Dividends")
    return Check("dividends_explicit", ok, "Dividends section present")


def _c_provenance_present(t: Transcript, spec: EvalSpec) -> Check:
    # Legacy label accepted so stored baseline transcripts stay re-gradable.
    ok = _section_present(t.final_prose, "About This Report") or _section_present(t.final_prose, "Provenance")
    return Check("provenance_present", ok, "About This Report line present")


def _c_ai_disclosure_present(t: Transcript, spec: EvalSpec) -> Check:
    ok = re.search(
        r"AI[\s-]?assisted|AI assistance|AI-interaction|generated with AI",
        t.final_prose, re.I,
    ) is not None
    return Check("ai_disclosure_present", ok, "AI-interaction disclosure (conventions §9.2)")


def _c_disclaimer_present_correct(t: Transcript, spec: EvalSpec) -> Check:
    ok = "not investment advice" in t.final_prose.lower()
    return Check("disclaimer_present_correct", ok, "standard disclaimer present")


def _c_bottom_line_no_rec(t: Transcript, spec: EvalSpec) -> Check:
    has_section = _section_present(t.final_prose, "Bottom Line")
    bl_text = _section_text(t.final_prose, "Bottom Line", spec.section_labels)
    has_rec = any(re.search(p, bl_text, re.I) for p in _REC_PATTERNS)
    return Check("bottom_line_no_rec", has_section and not has_rec, f"rec_token_in_bottom_line={has_rec}")


def _c_orchestrator_length(t: Transcript, spec: EvalSpec) -> Check:
    try:
        n = len(Path(spec.skill_md_path).read_text().splitlines())
    except OSError as exc:
        return Check("orchestrator_length", True, f"skipped (skill unreadable: {exc})")
    ok = n <= spec.orchestrator_max_lines
    return Check("orchestrator_length", ok, f"{n}/{spec.orchestrator_max_lines} lines")


CHECK_REGISTRY = {
    "sections_present": _c_sections_present,
    "scores_trend_direction": _c_scores_trend_direction,
    "macro_conditional": _c_macro_conditional,
    "dividends_explicit": _c_dividends_explicit,
    "provenance_present": _c_provenance_present,
    "ai_disclosure_present": _c_ai_disclosure_present,
    "disclaimer_present_correct": _c_disclaimer_present_correct,
    "bottom_line_no_rec": _c_bottom_line_no_rec,
    "orchestrator_length": _c_orchestrator_length,
}

CHECK_NAMES = list(CHECK_REGISTRY)


def grade_tier1(t: Transcript, spec: EvalSpec | None = None) -> list[Check]:
    """Run the checks in spec.check_ids. Defaults to should-i-buy when spec=None.

    Resolves each id against the generic CHECK_REGISTRY overlaid with the spec's
    skill-specific `extra_checks`.
    """
    if spec is None:
        spec = load_spec(_DEFAULT_SKILL)
    registry = {**CHECK_REGISTRY, **spec.extra_checks}
    return [registry[cid](t, spec) for cid in spec.check_ids]


# --- Two-lens raised-bar gate (Stage 2; design-doc §4.4) ---------------------
# Deliberately NOT in CHECK_REGISTRY: aspirational target for the upgraded skill,
# kept out of the §5 baseline rubric so the noise floor stays an honest
# current-spec number. Run via grade_two_lens() for red/green checks.
TWO_LENS_SECTIONS = ["Technicals", "Fundamentals"]


def _c_two_lenses_present(t: Transcript, _spec: EvalSpec | None = None) -> Check:
    missing = [s for s in TWO_LENS_SECTIONS if not _section_present(t.final_prose, s)]
    return Check("two_lenses_present", not missing, f"missing={missing}")


TWO_LENS_CHECKS = [_c_two_lenses_present]


def grade_two_lens(t: Transcript) -> list[Check]:
    """Raised-bar structural gate for the two-lens upgrade. Separate from the
    baseline grade_tier1() so it never contaminates the §5 noise floor."""
    return [fn(t) for fn in TWO_LENS_CHECKS]
