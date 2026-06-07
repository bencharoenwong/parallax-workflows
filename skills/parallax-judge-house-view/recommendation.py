"""LLM-as-judge per-cell recommendation builder + citation validator.

Pure-Python utilities for /parallax-judge-house-view Phase 5. This module
does NOT call Claude directly — the orchestrator in ``judge.py`` is the
LLM-bearing surface (Claude-the-skill-runtime drives the actual
recommendation generation against the prompt this module builds). The
module owns:

1. ``build_recommendation_prompt`` — assembles the system + input prompt
   from a single per-cell payload. Returned as a structured dict the
   orchestrator hands to the LLM.

2. ``validate_citation`` — POST-CALL hallucination control. Given the
   source snippet shown to the LLM and the recommendation object the LLM
   returned, asserts the recommendation cites a >= 30 char verbatim
   substring of the snippet either in ``rationale`` or in any
   ``evidence_refs``. On failure, the orchestrator drops the recommendation
   and substitutes a "judge declined to recommend (citation check failed)"
   placeholder.

3. ``apply_recommendation_or_decline`` — the orchestration convenience
   that calls validate_citation and returns either the LLM's
   recommendation or the declined-placeholder, alongside a structured
   audit trail of why the decision was made.

Hard constraints (mirrored from notes/2026-05-24-house-view-v2-plan.md §3
and the judge skill task brief):

- Citation check runs every time. No bypass flag, no debug knob.
- Substring match is verbatim against the snippet shown to the LLM. We
  cannot weaken to "semantic match" — that would re-introduce the
  hallucination surface the validator exists to close.
- The validator returns ``(ok, reason)``; the orchestrator owns the
  drop-vs-keep policy. We deliberately do not raise on failure so the
  audit row can record the rejection rather than abort the whole run.
"""
from __future__ import annotations

from typing import Any

# Minimum verbatim-substring length the LLM's rationale / evidence_refs
# must reproduce from the source snippet. 30 chars is comfortably above
# the false-positive rate of common boilerplate ("the price of " etc.)
# while still being short enough that a faithful paraphrase + one verbatim
# clause can satisfy it. Per task brief Phase 5.
MIN_CITATION_SUBSTRING_LEN = 30

# Truncation cap on the snippet shown to the LLM. The plan says 200 chars;
# any future bump should be paired with a corresponding bump in the
# citation-substring length so the substring rule remains meaningful.
SNIPPET_TRUNCATE_LEN = 200

# The decline marker the orchestrator inserts when citation check fails.
# Pinned as a constant so renderers / tests can match exactly.
DECLINE_MARKER = "judge declined to recommend (citation check failed)"

# Bounded magnitude for ``recommended_value``. Mirrors the schema.yaml
# tilt scale (-2..+2). Returned values outside this range fail validation.
_TILT_MIN, _TILT_MAX = -2, 2

# Maximum lengths for the LLM-provided strings (mirrors prompt contract).
_RATIONALE_MAX = 300
_ADDENDUM_MAX = 100


SYSTEM_PROMPT = (
    "You are an institutional research analyst writing a model-validation "
    "note for a bank's investment committee. Be concise, evidence-anchored, "
    "and conservative. NEVER fabricate a number or a citation. If the source "
    "snippet doesn't support a clear recommendation, return recommended_value=null "
    'with rationale="insufficient evidence in source".'
)


def _truncate(text: str, limit: int) -> str:
    if text is None:
        return ""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit]


def build_recommendation_prompt(
    *,
    path: str,
    cio_value: Any,
    parallax_value: Any,
    effective_date: str | None,
    tool: str,
    args: dict | None,
    parallax_date: str | None,
    source_snippet: str,
    state: str,
    severity: str,
) -> dict[str, Any]:
    """Assemble the recommendation prompt + structured-output schema.

    Returns a dict the orchestrator hands to Claude:
        {
            "system": <SYSTEM_PROMPT>,
            "user": <fully-rendered input block>,
            "schema": <JSON schema for the expected response>,
            "snippet_for_validation": <truncated snippet that the post-call
                                       validator must find a substring of>,
        }

    The snippet shown to the LLM and the snippet held back for validation
    are byte-identical — we cannot validate against a string the model
    never saw.
    """
    snippet_capped = _truncate(source_snippet or "", SNIPPET_TRUNCATE_LEN)

    user = (
        f"  - CIO tilt: {path} = {cio_value} "
        f"(set {effective_date or 'unknown'})\n"
        f"  - Parallax current signal: {parallax_value} "
        f"(from {tool}:{args or {}}, dated {parallax_date or 'unknown'})\n"
        f'  - Source snippet: "{snippet_capped}"\n'
        f"  - Stress state: {state}\n"
        f"  - Severity: {severity}"
    )

    schema = {
        "type": "object",
        "required": [
            "recommended_value",
            "confidence",
            "rationale",
            "suggested_basis_statement_addendum",
        ],
        "properties": {
            "recommended_value": {
                "type": ["integer", "null"],
                "minimum": _TILT_MIN,
                "maximum": _TILT_MAX,
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "rationale": {"type": "string", "maxLength": _RATIONALE_MAX},
            "suggested_basis_statement_addendum": {
                "type": "string",
                "maxLength": _ADDENDUM_MAX,
            },
            # Optional explicit citation slot. When present, the validator
            # checks it FIRST before falling back to substring-in-rationale.
            "evidence_refs": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    }

    return {
        "system": SYSTEM_PROMPT,
        "user": user,
        "schema": schema,
        "snippet_for_validation": snippet_capped,
    }


def _longest_common_substring_len(a: str, b: str) -> int:
    """Length of the longest common substring of `a` and `b`.

    Pure O(len(a)*len(b)) DP — fine for snippet sizes (<= 200) and
    rationale sizes (<= 300). Avoids pulling in `difflib` which has
    different matching semantics for our use-case (we want raw
    verbatim, not "junky" matches).
    """
    if not a or not b:
        return 0
    m, n = len(a), len(b)
    # Use two rolling rows to keep memory at O(n).
    prev = [0] * (n + 1)
    best = 0
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        ai = a[i - 1]
        for j in range(1, n + 1):
            if ai == b[j - 1]:
                curr[j] = prev[j - 1] + 1
                if curr[j] > best:
                    best = curr[j]
        prev = curr
    return best


def validate_citation(
    snippet: str,
    recommendation: dict[str, Any],
    *,
    min_len: int = MIN_CITATION_SUBSTRING_LEN,
) -> tuple[bool, str]:
    """Verify the LLM's recommendation cites the source snippet verbatim.

    Acceptance rule (per task brief Phase 5):

      The recommendation passes IFF either
        (a) ``rationale`` contains a verbatim substring of >= ``min_len``
            characters from ``snippet``, OR
        (b) any entry in the optional ``evidence_refs`` list contains
            such a substring.

    Snippet is normalized only by stripping outer whitespace — we
    deliberately do NOT collapse internal whitespace, lowercase, or
    remove punctuation. The substring must appear as the LLM was shown
    it. This is the hard hallucination control; loosening it requires a
    fresh adversarial round-trip.

    Args:
        snippet: The source snippet the LLM was shown (the value of
            ``snippet_for_validation`` from ``build_recommendation_prompt``).
        recommendation: The dict the LLM returned. Must contain at least
            ``rationale``; ``evidence_refs`` is optional.
        min_len: Override the verbatim-substring length. Default
            ``MIN_CITATION_SUBSTRING_LEN``.

    Returns:
        ``(ok, reason)``. ``ok=True`` when the citation check passes.
        ``reason`` is a short human-readable diagnostic the orchestrator
        attaches to the audit row when ``ok=False``.

    Note on null recommendations: per the system prompt, the LLM may
    return ``recommended_value=null`` with rationale "insufficient
    evidence in source" when the snippet is too thin. We treat that as a
    valid output — the LLM is honestly declining — and pass the citation
    check by special case. The substring requirement applies only when
    the LLM is asserting a concrete recommendation.
    """
    if not isinstance(recommendation, dict):
        return False, "recommendation must be a dict"

    snippet_n = (snippet or "").strip()
    if not snippet_n:
        return False, "empty source snippet — cannot validate citation"

    # Honest decline: null recommended_value with the canonical decline
    # message is allowed without citation. (The system prompt invites it.)
    if recommendation.get("recommended_value") is None:
        rationale_lower = (recommendation.get("rationale") or "").lower()
        if "insufficient evidence" in rationale_lower:
            return True, "honest decline accepted (null + insufficient-evidence)"
        # If the model returned null without the canonical phrase, still
        # require a citation so we know they actually read the snippet.

    rationale = recommendation.get("rationale", "") or ""
    if isinstance(rationale, str) and rationale:
        if _longest_common_substring_len(snippet_n, rationale) >= min_len:
            return True, f"rationale contains >={min_len}-char verbatim substring"

    evidence_refs = recommendation.get("evidence_refs") or []
    if isinstance(evidence_refs, list):
        for i, ref in enumerate(evidence_refs):
            if not isinstance(ref, str):
                continue
            if _longest_common_substring_len(snippet_n, ref) >= min_len:
                return True, f"evidence_refs[{i}] contains >={min_len}-char verbatim substring"

    return (
        False,
        f"no verbatim substring of >={min_len} chars found in rationale or evidence_refs",
    )


def make_decline_placeholder(
    *,
    path: str,
    state: str,
    severity: str,
    reason: str,
) -> dict[str, Any]:
    """Build the "judge declined" placeholder the orchestrator substitutes
    when validate_citation fails. Same surface fields as a successful
    recommendation so the renderer can treat the list uniformly.
    """
    return {
        "recommended_value": None,
        "confidence": 0.0,
        "rationale": DECLINE_MARKER,
        "suggested_basis_statement_addendum": "",
        "evidence_refs": [],
        "path": path,
        "stress_state": state,
        "severity": severity,
        "declined": True,
        "decline_reason": reason,
    }


def apply_recommendation_or_decline(
    *,
    snippet: str,
    recommendation: dict[str, Any],
    path: str,
    state: str,
    severity: str,
) -> tuple[dict[str, Any], bool]:
    """Run the citation check and return either the LLM's recommendation
    (annotated with ``declined=False``) or the decline placeholder.

    Returns ``(record, ok)``. ``ok`` mirrors the citation check result; a
    False value means the substitute placeholder was used.
    """
    ok, reason = validate_citation(snippet, recommendation)
    if not ok:
        return (
            make_decline_placeholder(
                path=path, state=state, severity=severity, reason=reason
            ),
            False,
        )
    annotated = dict(recommendation)
    annotated.setdefault("evidence_refs", [])
    annotated["path"] = path
    annotated["stress_state"] = state
    annotated["severity"] = severity
    annotated["declined"] = False
    annotated["citation_check_reason"] = reason
    return annotated, True
