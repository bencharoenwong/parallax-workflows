"""Tier-1 deterministic structural checks for /parallax-should-i-buy output.

Pure functions over a parsed Transcript. The only optional I/O is reading the
skill file for the orchestrator-length guard. Every check is current-spec
conformance — the skill's Output Format already mandates it (see
notes/2026-05-29-skillopt-eval-substrate-design.md §4.2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from transcript import Transcript

DEFAULT_SKILL_PATH = (
    Path(__file__).resolve().parents[2] / "skills" / "should-i-buy" / "SKILL.md"
)
ORCHESTRATOR_MAX_LINES = 250

# Calibrated against real should-i-buy output (2026-05-29). "The Company" is
# deliberately NOT required: the live skill folds company identity into the title
# ("## Apple Inc — Should I Buy?") rather than a "The Company" section. That is a
# legitimate rendering, not a structural failure (see learning log).
REQUIRED_SECTIONS = [
    "The Scores",
    "Financial Health",
    "Dividends",
    "Risk vs Peers",
    "Recent News",
    "Analyst View",
    "Bottom Line",
    "Provenance",
]

_REC_PATTERNS = [
    r"\bstrong buy\b", r"\bstrong sell\b",
    r"\bwe recommend (buy|sell)", r"\b(buy|sell) recommendation\b",
    r"\brating:\s*(buy|sell)\b", r"\bi recommend (buying|selling)\b",
]


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def _norm_tokens(text: str) -> list[str]:
    """Lowercase word tokens, punctuation stripped (so 'vs.' == 'vs')."""
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()


def _section_present(prose: str, heading: str) -> bool:
    """True if `heading` labels a line, as a markdown heading OR an emphasis label.

    Calibrated against real output: the live skill renders some sections as
    headings ('### Risk vs. Peers' — note the period) and others as emphasis
    label lines ('*Provenance: ...*'). Match by stripping leading markers
    (#, *, _, >) and comparing punctuation-free token prefixes, so heading depth,
    a trailing 'vs.' period, and italic/bold labels all match.
    """
    target = _norm_tokens(heading)
    if not target:
        return False
    for line in prose.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        content = re.sub(r"^[#>*_\s]+", "", stripped)
        if _norm_tokens(content)[: len(target)] == target:
            return True
    return False


# Section labels the skill can emit, for section-text boundary detection.
# Includes the two-lens headers (Fundamentals/Technicals) so a nested subsection
# is bounded by the next real section, not by bold sub-labels inside its body.
_SECTION_LABELS = [
    "The Company", "Fundamentals", "The Scores", "House View Note",
    "Financial Health", "Technicals", "Macro Context", "Dividends",
    "Risk vs Peers", "Recent News", "Analyst View", "Bottom Line", "Provenance",
]


def _label_prefix(line: str) -> list[str]:
    """Normalized token list of a line after stripping leading #>*_ markers."""
    return _norm_tokens(re.sub(r"^[#>*_\s]+", "", line.strip()))


def _section_text(prose: str, heading: str) -> str:
    """Return one section's text: from its label line to the next section's.

    Consistent with _section_present: the label may be a markdown heading
    ('### The Scores') OR an emphasis label ('**The Scores**') — the live skill
    renders nested lens subsections either way. The end boundary is the next
    line whose token-prefix matches a *different* known section label (so bold
    sub-labels inside the body, e.g. '**Quality**', do not truncate it).
    Returns "" if the heading is absent.
    """
    target = _norm_tokens(heading)
    if not target:
        return ""
    others = [_norm_tokens(s) for s in _SECTION_LABELS if _norm_tokens(s) != target]
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


# Trend-direction phrasings accepted in The Scores section (before/after values).
_TREND_PATTERNS = [
    r"from\s+\d+(?:\.\d+)?\s+to\s+\d+(?:\.\d+)?",            # "from 5.8 to 7.2"
    r"\d+(?:\.\d+)?\s*(?:→|->|—>|–>)\s*\d+(?:\.\d+)?",        # "5.8 → 7.2"
    r"(?:up|down)\s+from\s+\d+(?:\.\d+)?",                    # "up from 5.8"
]


def _c_sections_present(t: Transcript, _skill: Path | None) -> Check:
    missing = [s for s in REQUIRED_SECTIONS if not _section_present(t.final_prose, s)]
    return Check("sections_present", not missing, f"missing={missing}")


def _c_scores_trend_direction(t: Transcript, _skill: Path | None) -> Check:
    # Scope to The Scores section so an unrelated numeric range elsewhere
    # (revenue, dates) cannot satisfy the trend requirement.
    scores = _section_text(t.final_prose, "The Scores")
    ok = any(re.search(p, scores, re.I) for p in _TREND_PATTERNS)
    return Check("scores_trend_direction", ok, "trend direction (X to Y / X → Y / up from X) in The Scores")


def _c_macro_conditional(t: Transcript, _skill: Path | None) -> Check:
    macro_called = t.called("macro_analyst")
    macro_section = _section_present(t.final_prose, "Macro Context")
    ok = macro_called == macro_section
    return Check("macro_conditional", ok, f"macro_called={macro_called} section={macro_section}")


def _c_dividends_explicit(t: Transcript, _skill: Path | None) -> Check:
    ok = _section_present(t.final_prose, "Dividends")
    return Check("dividends_explicit", ok, "Dividends section present")


def _c_provenance_present(t: Transcript, _skill: Path | None) -> Check:
    ok = _section_present(t.final_prose, "Provenance")
    return Check("provenance_present", ok, "Provenance line present")


def _c_ai_disclosure_present(t: Transcript, _skill: Path | None) -> Check:
    # The canonical §9.2 banner opens with "AI-assisted output." — match that
    # first, plus paraphrase fallbacks.
    ok = re.search(
        r"AI[\s-]?assisted|AI assistance|AI-interaction|generated with AI",
        t.final_prose, re.I,
    ) is not None
    return Check("ai_disclosure_present", ok, "AI-interaction disclosure (conventions §9.2)")


def _c_disclaimer_present_correct(t: Transcript, _skill: Path | None) -> Check:
    ok = "not investment advice" in t.final_prose.lower()
    return Check("disclaimer_present_correct", ok, "standard disclaimer present")


def _c_bottom_line_no_rec(t: Transcript, _skill: Path | None) -> Check:
    # Scope the rec-token scan to the Bottom Line section only — live output's
    # Analyst View legitimately carries "Strong Buy/Buy/Hold" consensus counts.
    has_section = _section_present(t.final_prose, "Bottom Line")
    bl_text = _section_text(t.final_prose, "Bottom Line")
    has_rec = any(re.search(p, bl_text, re.I) for p in _REC_PATTERNS)
    return Check("bottom_line_no_rec", has_section and not has_rec, f"rec_token_in_bottom_line={has_rec}")


def _c_orchestrator_length(t: Transcript, skill: Path | None) -> Check:
    path = skill or DEFAULT_SKILL_PATH
    try:
        n = len(Path(path).read_text().splitlines())
    except OSError as exc:
        return Check("orchestrator_length", True, f"skipped (skill unreadable: {exc})")
    return Check("orchestrator_length", n <= ORCHESTRATOR_MAX_LINES, f"{n}/{ORCHESTRATOR_MAX_LINES} lines")


_CHECKS = [
    _c_sections_present,
    _c_scores_trend_direction,
    _c_macro_conditional,
    _c_dividends_explicit,
    _c_provenance_present,
    _c_ai_disclosure_present,
    _c_disclaimer_present_correct,
    _c_bottom_line_no_rec,
    _c_orchestrator_length,
]

CHECK_NAMES = [
    "sections_present", "scores_trend_direction", "macro_conditional",
    "dividends_explicit", "provenance_present", "ai_disclosure_present",
    "disclaimer_present_correct", "bottom_line_no_rec", "orchestrator_length",
]


def grade_tier1(t: Transcript, skill_path: str | Path | None = None) -> list[Check]:
    skill = Path(skill_path) if skill_path else None
    return [fn(t, skill) for fn in _CHECKS]


# --- Two-lens raised-bar gate (Stage 2; design-doc §4.4) ---------------------
# Deliberately NOT in _CHECKS: this is an aspirational target for the upgraded
# skill, kept out of the §5 baseline rubric so the 0.981 noise floor stays an
# honest current-spec number. Run via grade_two_lens() for red/green checks.
TWO_LENS_SECTIONS = ["Technicals", "Fundamentals"]


def _c_two_lenses_present(t: Transcript, _skill: Path | None) -> Check:
    missing = [s for s in TWO_LENS_SECTIONS if not _section_present(t.final_prose, s)]
    return Check("two_lenses_present", not missing, f"missing={missing}")


TWO_LENS_CHECKS = [_c_two_lenses_present]


def grade_two_lens(t: Transcript) -> list[Check]:
    """Raised-bar structural gate for the two-lens upgrade. Separate from the
    baseline grade_tier1() so it never contaminates the §5 noise floor."""
    return [fn(t, None) for fn in TWO_LENS_CHECKS]
