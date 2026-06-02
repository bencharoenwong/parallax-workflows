"""Pillar formulas: compute the four component scores from aggregated MCP outputs.

Each `compute_*` function returns a `PillarResult(value, confidence, missing_inputs)`.

Critical context (MCP_FIELD_INVENTORY.md §3.2 + §4):
- valuation_state and market_entropy inputs are NOT discrete telemetry fields.
  They live in `macro_analyst.content` prose as patterns like "Valuation metrics at -1.00".
- valuation_state extraction is PROSE-BASED with regex tolerance for the live shape.
- market_entropy is COMPOSITE: prose-extracted entropy + normalized divergence count
  proxy as fallback. Confidence ≤ 0.5.
- psychological_wavelength is LLM-judged from news + telemetry.commentary tone.
  Confidence ≤ 0.6. Default implementation here is a heuristic prose scan
  (Claude-side); a caller passing `psi_judge_fn` callback can substitute richer judgment.

Confidence cap rule (BUG-003 resolution / v2 plan §4.2):
- If missing_inputs is non-empty: confidence = min(confidence, 0.35).
- 0.35 is strictly below gap_detect.LOW_CONFIDENCE_THRESHOLD = 0.4, so
  missing-input pillars surface as low-confidence in the gate.

DOES NOT call MCP. Pure compute. Caller fans-out, aggregates, then
passes to these functions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

# Strictly below gap_detect.LOW_CONFIDENCE_THRESHOLD (0.4) so the gap
# branch fires on any pillar with missing inputs. See v2 plan §4.2.
MISSING_INPUT_CONFIDENCE_CAP = 0.35

# Per-pillar hard caps from MCP_FIELD_INVENTORY.md §4.
OMEGA_CONFIDENCE_CAP = 0.8
PHI_CONFIDENCE_CAP = 0.7
XI_CONFIDENCE_CAP = 0.5
PSI_CONFIDENCE_CAP = 0.6


@dataclass(frozen=True)
class PillarResult:
    """Output of one compute_* function.

    Attributes:
        value: -2..+2 integer (rounded toward zero on ties).
        confidence: 0.0-1.0. Capped at MISSING_INPUT_CONFIDENCE_CAP when
            `missing_inputs` is non-empty.
        missing_inputs: List of MCP field names that were unavailable at
            compute time. Surface in provenance so an auditor can re-run
            once the inputs become available.
        composition_formula: Short identifier describing the formula used.
            Captured in provenance.yaml `generator_synthesis.composition_formula`.
        source_snippets: Verbatim prose spans cited at compute time. Each
            ≤ 200 chars per provenance class spec.
    """

    value: int
    confidence: float
    missing_inputs: list[str] = field(default_factory=list)
    composition_formula: str = ""
    source_snippets: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Prose extraction primitives
# ---------------------------------------------------------------------------

# Tolerant regex for "Valuation metric(s) at X" or "Valuations at X" where
# X is a signed decimal. Anchored case-insensitive to tolerate "Valuation
# metric at +1.0", "valuation metrics at -1.00", "Valuations at 0.5",
# "Equity valuations are at -2".
_VALUATION_PATTERN = re.compile(
    r"valuation(?:s|\s+metrics?)?\s+"
    r"(?:are\s+|is\s+)?"
    r"(?:at|of|read[-\s]*through)?\s*"
    r"[:=]?\s*"
    r"([-+]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

# "entropy at X" / "market entropy of X" / "entropy reading X"
_ENTROPY_PATTERN = re.compile(
    r"(?:market\s+)?entropy\s+(?:at|of|reading)?\s*[:=]?\s*([-+]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

# Risk-on / risk-off / fear / greed words for the heuristic fallback.
# Hand-tuned conservative list — only fires when language is unambiguous.
_PSI_POSITIVE = (
    "risk-on", "risk on", "constructive", "bullish", "greed",
    "optimism", "complacent", "euphoric", "roro on",
)
_PSI_NEGATIVE = (
    "risk-off", "risk off", "fear", "capitulation", "bearish",
    "panic", "pessimism", "flight to quality", "haven bid",
    "stressed", "stress",
)


def _scan_prose_for_signed_number(
    pattern: re.Pattern[str], prose: str
) -> tuple[float, str] | None:
    """Return (value, snippet) for the first match, or None."""
    if not prose:
        return None
    m = pattern.search(prose)
    if m is None:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    # Cap snippet to ±100 chars around the match for context.
    start = max(0, m.start() - 60)
    end = min(len(prose), m.end() + 60)
    snippet = prose[start:end].strip().replace("\n", " ")
    snippet = re.sub(r"\s+", " ", snippet)[:200]
    return val, snippet


def _round_to_scale(x: float) -> int:
    """Round to nearest int, clipped to -2..+2, sign-preserving."""
    if x is None:
        return 0
    if x > 0:
        return min(2, int(round(x)))
    if x < 0:
        return max(-2, int(round(x)))
    return 0


def _apply_missing_cap(confidence: float, missing_inputs: list[str]) -> float:
    """Cap confidence per BUG-003 rule when inputs are missing."""
    if missing_inputs:
        return min(confidence, MISSING_INPUT_CONFIDENCE_CAP)
    return confidence


# ---------------------------------------------------------------------------
# econometrics_phase — HIGH confidence (regime_tag + growth)
# ---------------------------------------------------------------------------

# regime_tag → omega value map. Conservative; ambiguous tags → 0.
_REGIME_TO_OMEGA = {
    "expansion": 2,
    "selective rotation": 1,
    "reflationary": 1,
    "soft landing": 1,
    "neutral": 0,
    "mixed": 0,
    "slowing": -1,
    "stagflation": -1,
    "recession": -2,
    "recessionary": -2,
    "contraction": -2,
    "stress": -2,
}


def _omega_from_regime(regime_tag: str | None) -> int | None:
    """Map regime_tag to omega value. Conservative substring match."""
    if not regime_tag:
        return None
    tag = regime_tag.lower()
    for key, val in _REGIME_TO_OMEGA.items():
        if key in tag:
            return val
    return None


def compute_omega(
    aggregated: dict[str, Any],
    telemetry: dict[str, Any] | None,
    inventory: dict[str, Any] | None = None,
) -> PillarResult:
    """econometrics_phase.

    Primary input: telemetry.regime_tag (always present in healthy telemetry).
    Secondary: cross_country growth signal from aggregated.macro_regime.growth.

    Conservative blend — regime_tag dominates; growth signal nudges by ±1
    when present and pointing the same way.
    """
    missing: list[str] = []
    snippets: list[str] = []

    telemetry = telemetry or {}
    regime_tag = telemetry.get("regime_tag")
    omega_from_regime = _omega_from_regime(regime_tag)

    if omega_from_regime is None:
        missing.append("telemetry.regime_tag")
        regime_value: float = 0.0
    else:
        regime_value = float(omega_from_regime)
        if regime_tag:
            snippets.append(f"regime_tag={regime_tag!r}"[:200])

    # Cross-country growth nudge.
    growth_token = (aggregated or {}).get("macro_regime", {}).get("growth")
    growth_nudge = 0.0
    if growth_token in ("expansion", "reflationary"):
        growth_nudge = 0.5
    elif growth_token in ("slowing",):
        growth_nudge = -0.5
    elif growth_token in ("recessionary",):
        growth_nudge = -1.0
    elif growth_token is None:
        missing.append("aggregated.macro_regime.growth")
    if growth_token:
        snippets.append(f"growth={growth_token!r}")

    blended = regime_value + growth_nudge
    value = _round_to_scale(blended)

    # Confidence: high when both sources present, halved when only regime_tag.
    if not missing:
        confidence = OMEGA_CONFIDENCE_CAP
    elif len(missing) == 1 and "growth" in missing[0]:
        confidence = OMEGA_CONFIDENCE_CAP * 0.75
    else:
        confidence = OMEGA_CONFIDENCE_CAP * 0.4

    confidence = _apply_missing_cap(confidence, missing)

    return PillarResult(
        value=value,
        confidence=confidence,
        missing_inputs=missing,
        composition_formula="pillar_formulas.compute_omega@v1:round(regime+growth_nudge)",
        source_snippets=snippets,
    )


# ---------------------------------------------------------------------------
# valuation_state — PROSE-EXTRACTED from macro_analyst.content
# ---------------------------------------------------------------------------


def compute_phi(
    aggregated: dict[str, Any],
    telemetry: dict[str, Any] | None,
    inventory: dict[str, Any] | None = None,
) -> PillarResult:
    """valuation_state.

    Reads `aggregated.phi_per_market` — a dict
    {market_name: {value: float, prose_snippet: str}} produced by
    cross_country.aggregate, which scanned each market's macro_indicators
    prose for "Valuation metrics at X" patterns.

    Aggregation rule:
    - If `aggregated.phi_coverage_ok` is False (60% coverage rule failed):
      return value=0, confidence=0.0, missing_inputs=[
          "valuation_prose_silent_in_majority_of_markets"
      ].
    - Else: take aggregated.phi (weighted median value, already scaled to
      -2..+2 by cross_country.aggregate).
    """
    phi_block = (aggregated or {}).get("phi") or {}
    coverage_ok = phi_block.get("coverage_ok")
    value_float = phi_block.get("value")
    snippets = list(phi_block.get("snippets") or [])
    markets_with_data = phi_block.get("markets_with_data") or []

    missing: list[str] = []

    if value_float is None or not markets_with_data:
        missing.append("valuation_prose_silent_in_all_markets")
        return PillarResult(
            value=0,
            confidence=_apply_missing_cap(0.0, missing),
            missing_inputs=missing,
            composition_formula="pillar_formulas.compute_phi@v1:prose_extract_aggregated",
            source_snippets=snippets,
        )

    if coverage_ok is False:
        missing.append("valuation_prose_silent_in_majority_of_markets")
        confidence = 0.0
    else:
        # Confidence scales with coverage breadth: more markets with prose
        # data → higher confidence, capped at PHI_CONFIDENCE_CAP.
        n_markets = len(markets_with_data)
        # 1 market → 0.3, 3 markets → 0.55, 6+ → 0.7.
        confidence = min(PHI_CONFIDENCE_CAP, 0.2 + 0.10 * n_markets)

    confidence = _apply_missing_cap(confidence, missing)

    return PillarResult(
        value=_round_to_scale(value_float),
        confidence=confidence,
        missing_inputs=missing,
        composition_formula="pillar_formulas.compute_phi@v1:prose_extract_aggregated",
        source_snippets=snippets[:5],
    )


# ---------------------------------------------------------------------------
# market_entropy — COMPOSITE: prose + divergence-count proxy
# ---------------------------------------------------------------------------


def _divergence_count_to_xi(n_div: int) -> int:
    """Map normalized divergence count to xi value (more = more disorder = lower xi).

    Documented thresholds (per spec):
      n >= 40 → -2
      n >= 20 → -1
      n >= 8  → 0
      n >= 3  → +1
      n < 3   → +2
    """
    if n_div >= 40:
        return -2
    if n_div >= 20:
        return -1
    if n_div >= 8:
        return 0
    if n_div >= 3:
        return 1
    return 2


def compute_xi(
    aggregated: dict[str, Any],
    telemetry: dict[str, Any] | None,
    inventory: dict[str, Any] | None = None,
) -> PillarResult:
    """market_entropy (COMPOSITE).

    Two inputs:
    (a) `aggregated.xi.value` (float, scaled -2..+2): cross-country prose-
        extracted entropy where present, weighted-median aggregated.
    (b) `telemetry.divergences` count as fallback proxy where prose silent.

    Composition:
      - If prose value is available (any market): weight prose 0.65,
        divergence-proxy 0.35.
      - If prose silent everywhere: rely on divergence-proxy entirely
        (still capped at XI_CONFIDENCE_CAP).
      - If telemetry.divergences missing: missing_inputs += ['telemetry.divergences'].

    composition_formula notes the proxy weighting explicitly.
    """
    missing: list[str] = []
    snippets: list[str] = []

    xi_block = (aggregated or {}).get("xi") or {}
    prose_value = xi_block.get("value")  # float or None
    markets_with_data = xi_block.get("markets_with_data") or []
    prose_snippets = xi_block.get("snippets") or []

    telemetry = telemetry or {}
    divs = telemetry.get("divergences")
    if divs is None:
        missing.append("telemetry.divergences")
        proxy_value: float | None = None
    else:
        n_div = len(divs) if isinstance(divs, list) else 0
        proxy_value = float(_divergence_count_to_xi(n_div))
        snippets.append(f"divergence_count={n_div}")

    if prose_value is not None and proxy_value is not None:
        blended = 0.65 * float(prose_value) + 0.35 * proxy_value
        formula = (
            "pillar_formulas.compute_xi@v1:"
            "0.65*prose_entropy + 0.35*divergence_proxy"
        )
        # More markets present → higher confidence within the XI cap.
        n = len(markets_with_data)
        confidence = min(XI_CONFIDENCE_CAP, 0.25 + 0.08 * n)
    elif prose_value is not None:
        blended = float(prose_value)
        formula = "pillar_formulas.compute_xi@v1:prose_entropy_only(no_proxy)"
        confidence = min(XI_CONFIDENCE_CAP, 0.20 + 0.06 * len(markets_with_data))
    elif proxy_value is not None:
        blended = proxy_value
        formula = "pillar_formulas.compute_xi@v1:divergence_proxy_only"
        confidence = min(XI_CONFIDENCE_CAP, 0.30)
        missing.append("entropy_prose_silent_in_all_markets")
    else:
        blended = 0.0
        formula = "pillar_formulas.compute_xi@v1:no_inputs"
        missing.append("entropy_prose_silent_in_all_markets")
        confidence = 0.0

    snippets.extend([s for s in prose_snippets[:3]])
    confidence = _apply_missing_cap(confidence, missing)

    return PillarResult(
        value=_round_to_scale(blended),
        confidence=confidence,
        missing_inputs=missing,
        composition_formula=formula,
        source_snippets=snippets[:5],
    )


# ---------------------------------------------------------------------------
# psychological_wavelength — LLM-judged (default: heuristic prose scan)
# ---------------------------------------------------------------------------


def _heuristic_psi_score(prose_blobs: list[str], commentary_headline: str | None) -> tuple[int, str]:
    """Conservative bag-of-words sentiment. Returns (value, snippet).

    Default implementation when no llm callback is supplied. Counts
    positive vs negative tokens across all prose; maps net to -2..+2.
    """
    pos = neg = 0
    snippet_bits: list[str] = []
    for blob in prose_blobs:
        if not blob:
            continue
        lowered = blob.lower()
        for tok in _PSI_POSITIVE:
            if tok in lowered:
                pos += 1
        for tok in _PSI_NEGATIVE:
            if tok in lowered:
                neg += 1
    if commentary_headline:
        snippet_bits.append(f"commentary.headline={commentary_headline!r}"[:200])
        lowered = commentary_headline.lower()
        for tok in _PSI_POSITIVE:
            if tok in lowered:
                pos += 1
        for tok in _PSI_NEGATIVE:
            if tok in lowered:
                neg += 1

    score = pos - neg
    if score >= 4:
        value = 2
    elif score >= 1:
        value = 1
    elif score <= -4:
        value = -2
    elif score <= -1:
        value = -1
    else:
        value = 0
    snippet_bits.insert(0, f"psi_token_count(pos={pos},neg={neg},score={score})")
    return value, " | ".join(snippet_bits)[:200]


def compute_psi(
    aggregated: dict[str, Any],
    telemetry: dict[str, Any] | None,
    inventory: dict[str, Any] | None = None,
    *,
    psi_judge_fn: Callable[[list[str], str | None], tuple[int, str, float]] | None = None,
) -> PillarResult:
    """psychological_wavelength.

    Args:
        aggregated: must carry `aggregated.psi_news_blobs` (list[str]) — the
            per-country news component content concatenations.
        telemetry: optional, used for `commentary.headline`.
        psi_judge_fn: optional callback returning (value, snippet, confidence).
            When None, falls back to a conservative bag-of-words heuristic
            (kept simple to avoid silently disagreeing with a richer judgment
            chain — the maker SKILL is expected to inject a Claude-side
            structured-output prompt that calls this with a real judgment).

    The heuristic intentionally yields a low confidence (0.3-0.4) so the gate
    surfaces it; the SKILL.md flow swaps in a Claude judge for production.
    """
    missing: list[str] = []
    telemetry = telemetry or {}
    commentary = telemetry.get("commentary") or {}
    headline = commentary.get("headline") if isinstance(commentary, dict) else None
    news_blobs = list((aggregated or {}).get("psi_news_blobs") or [])

    if not news_blobs and headline is None:
        missing.append("psi_news_and_commentary_silent")
        return PillarResult(
            value=0,
            confidence=_apply_missing_cap(0.0, missing),
            missing_inputs=missing,
            composition_formula="pillar_formulas.compute_psi@v1:no_inputs",
            source_snippets=[],
        )

    if psi_judge_fn is not None:
        value, snippet, raw_conf = psi_judge_fn(news_blobs, headline)
        confidence = min(PSI_CONFIDENCE_CAP, max(0.0, raw_conf))
        formula = "pillar_formulas.compute_psi@v1:llm_judged"
    else:
        value, snippet = _heuristic_psi_score(news_blobs, headline)
        # Heuristic is intentionally weak — cap below PSI cap.
        confidence = min(PSI_CONFIDENCE_CAP * 0.6, 0.35)
        formula = "pillar_formulas.compute_psi@v1:bag_of_words_heuristic"

    if not news_blobs:
        missing.append("aggregated.psi_news_blobs")
    if headline is None:
        missing.append("telemetry.commentary.headline")

    confidence = _apply_missing_cap(confidence, missing)

    return PillarResult(
        value=_round_to_scale(float(value)),
        confidence=confidence,
        missing_inputs=missing,
        composition_formula=formula,
        source_snippets=[snippet] if snippet else [],
    )


__all__ = [
    "PillarResult",
    "MISSING_INPUT_CONFIDENCE_CAP",
    "OMEGA_CONFIDENCE_CAP",
    "PHI_CONFIDENCE_CAP",
    "XI_CONFIDENCE_CAP",
    "PSI_CONFIDENCE_CAP",
    "compute_omega",
    "compute_phi",
    "compute_xi",
    "compute_psi",
    "_VALUATION_PATTERN",
    "_ENTROPY_PATTERN",
    "_scan_prose_for_signed_number",
]
