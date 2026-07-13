"""Eval spec for /parallax-stress-test-thesis.

DRAFT — spec only, never run live (same status as portfolio-checkup at authoring).
Wired into the structural harness so the skill's output contract is captured and
CI's pure-function grader tests can reference it; live rollouts remain manual and
cost Parallax tokens.

Output family differs from should-i-buy: this skill emits an argument-decomposition
report (Assumption Map, Load-Bearing Vulnerabilities, per-assumption status table,
World Verdict), not a per-stock scorecard. It shares the cross-skill conventions
(§9.2 AI-disclosure, a "not investment advice" disclaimer, ≤250-line orchestrator)
and makes NO buy/sell/hold recommendation — the analogue of should-i-buy's
bottom_line_no_rec is verdict_no_rec here.

The `core.jsonl` tasks are all Pass-1-only (no client_profile). The two-pass
client-conditioning acceptance test (crypto accumulator vs. retiree) is
deliberately NOT in core: it requires a paired-run assertion (identical
Pass-1 statuses across two profiles; divergent client ranking; stronger disclaimer
variant on the retiree run) that the single-transcript generic engine can't express.
Keep it as the manual live acceptance test until the harness grows paired-run support.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "graders"))
from eval_spec import EvalSpec  # noqa: E402
from tier1_structural import Check, _section_text, _REC_PATTERNS  # noqa: E402
from judge_criteria import CRITERIA  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Always-present sections (Pass-1, no-profile path). Profile-only and ticker-only
# sections are intentionally excluded from required_sections — they appear in
# section_labels so section-text boundaries resolve, but a no-profile / no-ticker
# task must still pass.
_REQUIRED_SECTIONS = [
    "TL;DR",                             # standard render — leads every report at every depth
    "Thesis Restatement",
    "Coverage Notice",                   # standard render — early full/partial/out-of-scope disclosure
    "Assumption Map",
    "Pass 1 — Load-Bearing Vulnerabilities",
    "Assumption-by-Assumption",
    "World Verdict",
    "Bias & Conviction Check",           # standard render — the "hype meter", client-invariant
    "What to Watch",
    "Confidence & Caveats",
]
_SECTION_LABELS = [
    "TL;DR",
    "Thesis Restatement",
    "Coverage Notice",                   # early coverage disclosure (full/partial/out-of-scope)
    "Client Profile Summary",            # profile-only
    "Assumption Map",
    "Pass 1 — Load-Bearing Vulnerabilities",
    "Assumption-by-Assumption",
    "Position-Level Read",               # ticker-only
    "World Verdict",
    "Bias & Conviction Check",           # the "hype meter" — client-invariant Pass-1 read, under World Verdict
    "House-View Alignment",              # active-view-only (read-only conflict flag)
    "Pass 2 — Holder-Dependent Assumptions",         # profile-only
    "Pass 2 — Client-Conditioned Vulnerabilities",   # profile-only
    "Suitability-Relevant Flags",        # profile-only
    "Client-Conditioned Verdict",        # profile-only
    "What to Watch",
    "Confidence & Caveats",
]

# Evidence the five-layer decomposition actually ran: the Assumption Map's `layer`
# column should surface the taxonomy vocabulary.
_LAYER_KEYWORDS = ["macro", "sector", "theme", "position", "implicit", "structural", "holder"]


# Shared _REC_PATTERNS catches only FORMAL rating tokens ("strong buy",
# "rating: buy"). This skill's whole premise is that it never issues a directive,
# so the verdict guard is stricter here: it also catches casual imperatives
# ("you should buy this now", "we recommend buying"). Patterns are kept narrow to
# avoid tripping on legitimate market vocabulary a verdict may use — "buy-side
# flows", "a sell-off", "sell-side targets", "the thesis holds", "hold through
# the drawdown" must all pass, so bare buy/sell/hold tokens are NOT matched.
_VERDICT_REC_EXTRA = [
    r"\byou should (buy|sell|hold|avoid|short|trim|add)\b",
    r"\b(buy|sell|short) (this|it|these|them|now|here)\b",
    r"\bwe (recommend|advise|suggest) (buying|selling|holding|you)\b",
    r"\bmy recommendation is\b",
]
_VERDICT_REC_PATTERNS = _REC_PATTERNS + _VERDICT_REC_EXTRA


def _c_verdict_no_rec(t, spec) -> Check:
    """No buy/sell/hold directive in the verdict sections — this skill maps risk in
    an argument, it does not recommend. Stricter than should-i-buy's
    bottom_line_no_rec: catches casual imperatives, not just formal rating tokens."""
    text = (
        _section_text(t.final_prose, "World Verdict", spec.section_labels)
        + "\n"
        + _section_text(t.final_prose, "Client-Conditioned Verdict", spec.section_labels)
    )
    hit = next((p for p in _VERDICT_REC_PATTERNS if re.search(p, text, re.I)), None)
    return Check("verdict_no_rec", hit is None, f"rec_token_in_verdict={hit}")


def _c_assumption_map_layered(t, spec) -> Check:
    """The Assumption Map's id/layer columns reference the layer taxonomy (>=2 distinct
    layer keywords) — a proxy that the argument was decomposed across layers, not
    flattened. Scoped to the table's id+layer cells so a stray keyword in surrounding
    prose (e.g. 'macro backdrop' in a caption) can't satisfy the check; falls back to
    the full section text if the table doesn't parse, to avoid false failures."""
    section = _section_text(t.final_prose, "Assumption Map", spec.section_labels)
    rows = [r for r in section.splitlines() if r.lstrip().startswith("|")]

    def cells(row):
        return [c.strip() for c in row.strip().strip("|").split("|")]

    scoped = ""
    if len(rows) >= 3:  # header + separator + >=1 data row
        header = [c.lower() for c in cells(rows[0])]
        idxs = [i for i, h in enumerate(header) if "id" in h or "layer" in h]
        for row in rows[2:]:
            c = cells(row)
            scoped += " " + " ".join(c[i] for i in idxs if i < len(c))

    haystack = (scoped if scoped.strip() else section).lower()
    hits = sorted({k for k in _LAYER_KEYWORDS if k in haystack})
    return Check("assumption_map_layered", len(hits) >= 2, f"layer_keywords={hits}")


_EMPTY_CELLS = {"", "—", "-", "n/a", "na", "none", "tbd"}


def _c_break_condition_fields(t, spec) -> Check:
    """Every Supported/Contradicted row in the Assumption-by-Assumption table states
    a magnitude AND a time_to_play_out — both mandatory per SKILL.md success
    criterion 3, because Phase 5 cannot re-weight severity without them. Unconfirmed
    rows are exempt (no break condition to size). Header-aware table parse so the
    check is robust to column reordering."""
    text = _section_text(t.final_prose, "Assumption-by-Assumption", spec.section_labels)
    rows = [r for r in text.splitlines() if r.lstrip().startswith("|")]
    if len(rows) < 3:  # need header + separator + >=1 data row
        return Check("break_condition_fields", True, "no assumption rows to check")

    def cells(row):
        return [c.strip() for c in row.strip().strip("|").split("|")]

    header = [c.lower() for c in cells(rows[0])]

    def col(*names):
        for i, h in enumerate(header):
            if any(n in h for n in names):
                return i
        return None

    ci_status = col("status")
    ci_mag = col("magnitude")
    ci_time = col("time_to_play_out", "time-to-play", "time to play", "time_to")
    if None in (ci_status, ci_mag, ci_time):
        return Check("break_condition_fields", False,
                     f"columns_not_found status={ci_status} mag={ci_mag} time={ci_time}")

    bad = []
    for row in rows[2:]:  # skip header + separator
        c = cells(row)
        if ci_status >= len(c):
            continue  # can't read status — not a parseable data row
        status = c[ci_status].lower()
        if "contradict" not in status and "support" not in status:
            continue  # Unconfirmed rows have no break condition to size — exempt
        # Supported/Contradicted: magnitude + time are mandatory. A row that DROPS
        # those columns entirely is the failure we want to catch (a model silently
        # narrowing the table), so flag it rather than skipping it as ragged.
        if max(ci_mag, ci_time) >= len(c):
            bad.append(c[0] or "?")
            continue
        mag = c[ci_mag].strip("* ").lower()
        tim = c[ci_time].strip("* ").lower()
        if mag in _EMPTY_CELLS or tim in _EMPTY_CELLS:
            bad.append(c[0] or "?")
    return Check("break_condition_fields", not bad, f"rows_missing_magnitude_or_time={bad}")


_READ_TIME_RE = re.compile(r"~\s*\d+\s*min\s+read", re.I)


def _c_read_time_marker(t, spec) -> Check:
    """A `~N min read` estimate leads the report — standard render at every depth
    per SKILL.md Output Format (bold-starred, never collapsed away). Searched over
    the whole prose (it's a top-of-report marker, not a titled section)."""
    m = _READ_TIME_RE.search(t.final_prose or "")
    return Check("read_time_marker", m is not None,
                 f"marker={m.group(0) if m else None}")


_STRENGTH_LIGHT = {"weak": "🔴", "mixed": "🟡", "strong": "🟢"}


def _glyph_binding_ok(name: str, line, mapping: dict) -> Check:
    """Verify the traffic-light glyph *bound to the reading's label* is the correct one.

    Binds glyph→label by ADJACENCY (`<glyph> <Label>`, tolerating markdown/whitespace),
    so a line may legitimately name a sibling level in prose (e.g. a reading of
    "🟡 Elevated" that adds "… it is not 🔴 High") without tripping — only the label's own
    leading glyph is graded, not every glyph on the line. Vacuous when the line is absent
    or carries no level word (a non-standard render). Discovered via live eval: the old
    "any sibling glyph anywhere on the line" rule false-positived on natural report prose."""
    if line is None:
        return Check(name, True, "no reading line")
    low = line.lower()
    if not any(re.search(rf"\b{w}\b", low) for w in mapping):
        return Check(name, True, "no label on line")
    glyphs = "".join(mapping.values())
    m = re.search(rf"([{glyphs}])\s*\**\s*\b(" + "|".join(mapping) + r")\b", low)
    if m is None:
        return Check(name, False, "label present but no glyph bound to it")
    glyph, label = m.group(1), m.group(2)
    ok = mapping[label] == glyph
    return Check(name, ok, f"binding={glyph} {label} expected={mapping[label]}")


def _c_tldr_strength_light(t, spec) -> Check:
    """The TL;DR's Assumption Strength label wears its matching traffic-light glyph
    (Weak→🔴, Mixed→🟡, Strong→🟢) — a standard-render visual cue for argument strength.
    Glyph is bound to the label by adjacency (see _glyph_binding_ok). Vacuous only when
    no strength label appears in the TL;DR (e.g. a non-standard render)."""
    tldr = _section_text(t.final_prose, "TL;DR", spec.section_labels)
    line = next((l for l in tldr.splitlines() if "assumption strength" in l.lower()), None)
    return _glyph_binding_ok("tldr_strength_light", line, _STRENGTH_LIGHT)


_HYPE_LIGHT = {"low": "🟢", "elevated": "🟡", "high": "🔴"}


def _c_hype_meter_light(t, spec) -> Check:
    """The Bias & Conviction Check ("hype meter") wears its matching glyph (Low→🟢,
    Elevated→🟡, High→🔴) bound to the reading's own label by adjacency — so a reading may
    explain itself against a sibling level ("… not 🔴 High") without tripping. Vacuous when
    no hype reading is rendered (the section may be absent on a non-standard render)."""
    sec = _section_text(t.final_prose, "Bias & Conviction Check", spec.section_labels)
    line = next((l for l in sec.splitlines()
                 if re.search(r"\b(low|elevated|high)\b", l, re.I)), None)
    return _glyph_binding_ok("hype_meter_light", line, _HYPE_LIGHT)


_NO_HALLUC = next(c for c in CRITERIA if c["id"] == "no_hallucinated_data")  # COPIED

SPEC = EvalSpec(
    name="stress-test-thesis",
    command="/parallax-stress-test-thesis",
    rollout_prefix="stress-test-thesis",
    skill_md_path=_REPO_ROOT / "skills" / "parallax-stress-test-thesis" / "SKILL.md",
    required_sections=_REQUIRED_SECTIONS,
    section_labels=_SECTION_LABELS,
    check_ids=[
        "sections_present",            # GENERIC
        "ai_disclosure_present",       # GENERIC (§9.2 banner, always)
        "disclaimer_present_correct",  # GENERIC ("not investment advice" — both the no-profile §9.1 render and the stronger profile variant carry the literal token)
        "verdict_no_rec",              # NEW (analogue of bottom_line_no_rec)
        "assumption_map_layered",      # NEW (five-layer decomposition ran)
        "break_condition_fields",      # NEW (magnitude + time_to_play_out mandatory)
        "read_time_marker",            # NEW (standard-render ~N min read marker)
        "tldr_strength_light",         # NEW (TL;DR strength carries matching 🔴/🟡/🟢 glyph)
        "hype_meter_light",            # NEW (Bias & Conviction "hype meter" glyph consistency)
        "orchestrator_length",         # GENERIC
    ],
    extra_checks={
        "verdict_no_rec": _c_verdict_no_rec,
        "assumption_map_layered": _c_assumption_map_layered,
        "break_condition_fields": _c_break_condition_fields,
        "read_time_marker": _c_read_time_marker,
        "tldr_strength_light": _c_tldr_strength_light,
        "hype_meter_light": _c_hype_meter_light,
    },
    tier2_criteria=[
        _NO_HALLUC,  # COPIED
        {
            "id": "assumptions_falsifiable",
            "statement": "Each row in the Assumption Map states a falsifiable claim — something that could be shown false — not a vague sentiment.",
            "pass_when": "Every claim could in principle be contradicted by data; none are untestable opinions.",
        },
        {
            "id": "status_grounded_no_fabrication",
            "statement": "No layer-1–4 assumption is marked Supported or Contradicted without a live Parallax read behind it; silent or ambiguous data is marked Unconfirmed rather than guessed.",
            "pass_when": "Supported/Contradicted rows cite a signal; Unconfirmed is used where data is silent, not a forced call.",
        },
        {
            "id": "verdict_names_load_bearing",
            "statement": "The World Verdict identifies which assumptions the thesis most depends on and where it most likely fails first.",
            "pass_when": "The verdict points to specific load-bearing assumptions and a failure sequence, not a generic summary.",
        },
        {
            "id": "pushes_back_on_weak_argument",
            "statement": "Where the thesis rests on non-falsifiable or sentiment-based reasoning (e.g., 'it always comes back', social-media sentiment, authority appeals), the report flags these as unsupported or not testable rather than restating them as findings.",
            "pass_when": "Sentiment/authority claims are called out as low-quality or untestable, not validated — the skill does not rubber-stamp a weak thesis.",
        },
        {
            # Partial single-transcript guard for the skill's core invariant. The
            # full paired-run test (identical Pass-1 across two profiles) still lives
            # in the manual acceptance suite — see the module docstring — but this
            # catches an in-transcript Pass-2 status flip. Vacuously true on the
            # Pass-1-only core tasks (no Pass 2 section present).
            "id": "pass2_preserves_pass1_status",
            "statement": "If the transcript contains a Pass 2 (client-conditioning) section, every layer-1–4 assumption's Supported/Contradicted/Unconfirmed status shown there is identical to its Pass-1 status, and Pass 2 only adds a client_severity re-weighting — it never flips a status. If there is no Pass 2 / client_profile, this criterion is satisfied trivially.",
            "pass_when": "No Pass-1 status is changed by Pass 2; client conditioning changes only severity (client_severity alongside base_severity). Vacuously passes when no client_profile is supplied.",
        },
    ],
    tasks_path="evals/tasks/stress-test-thesis/core.jsonl",
    orchestrator_max_lines=250,
)
