"""Unit tests for pillar_formulas.py.

Per v2 plan §4.2 + MCP_FIELD_INVENTORY.md §4 + §5.1.
"""
from __future__ import annotations

import pytest

from pillar_formulas import (
    MISSING_INPUT_CONFIDENCE_CAP,
    OMEGA_CONFIDENCE_CAP,
    PHI_CONFIDENCE_CAP,
    PSI_CONFIDENCE_CAP,
    XI_CONFIDENCE_CAP,
    PillarResult,
    compute_omega,
    compute_phi,
    compute_psi,
    compute_xi,
    _scan_prose_for_signed_number,
    _VALUATION_PATTERN,
    _ENTROPY_PATTERN,
)


# ---------------------------------------------------------------------------
# Prose-scan primitives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prose, expected",
    [
        ("Valuation metrics at -1.00 across the index.", -1.0),
        ("valuations at +0.5 versus history.", 0.5),
        ("Valuation metric at 1.5; expensive.", 1.5),
        ("Equity valuations are at -2 on a relative basis.", -2.0),
        ("no signal here", None),
    ],
)
def test_valuation_pattern_tolerates_variants(prose, expected):
    result = _scan_prose_for_signed_number(_VALUATION_PATTERN, prose)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        val, snippet = result
        assert val == pytest.approx(expected)
        assert isinstance(snippet, str)


def test_entropy_pattern_matches():
    result = _scan_prose_for_signed_number(_ENTROPY_PATTERN, "Market entropy at 0.50 — orderly.")
    assert result is not None
    val, _ = result
    assert val == pytest.approx(0.5)

    result = _scan_prose_for_signed_number(_ENTROPY_PATTERN, "Entropy reading -1.")
    assert result is not None
    assert result[0] == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# Ω econometrics_phase
# ---------------------------------------------------------------------------


def test_omega_high_confidence_when_regime_and_growth_present():
    telemetry = {"regime_tag": "Selective rotation"}
    aggregated = {"macro_regime": {"growth": "expansion"}}
    p = compute_omega(aggregated, telemetry)
    assert isinstance(p, PillarResult)
    # selective rotation maps to +1; growth expansion nudges +0.5 → +2 after round.
    assert p.value in (1, 2)
    assert p.missing_inputs == []
    assert p.confidence == pytest.approx(OMEGA_CONFIDENCE_CAP)


def test_omega_capped_when_regime_missing():
    telemetry = {}
    aggregated = {"macro_regime": {"growth": "expansion"}}
    p = compute_omega(aggregated, telemetry)
    assert "telemetry.regime_tag" in p.missing_inputs
    assert p.confidence <= MISSING_INPUT_CONFIDENCE_CAP


def test_omega_capped_when_all_inputs_missing():
    p = compute_omega({}, {})
    assert "telemetry.regime_tag" in p.missing_inputs
    assert p.confidence <= MISSING_INPUT_CONFIDENCE_CAP
    assert p.value == 0


def test_omega_recession_maps_negative():
    telemetry = {"regime_tag": "Deep recession"}
    aggregated = {"macro_regime": {"growth": "recessionary"}}
    p = compute_omega(aggregated, telemetry)
    assert p.value < 0


# ---------------------------------------------------------------------------
# Φ valuation_state
# ---------------------------------------------------------------------------


def test_phi_silent_in_all_markets_returns_zero_confidence_with_missing():
    aggregated = {"phi": {"value": None, "coverage_ok": False, "markets_with_data": [], "snippets": []}}
    p = compute_phi(aggregated, None)
    assert p.value == 0
    assert p.confidence <= MISSING_INPUT_CONFIDENCE_CAP
    assert any("silent" in m for m in p.missing_inputs)


def test_phi_coverage_below_threshold_caps_confidence():
    aggregated = {
        "phi": {
            "value": -1.0,
            "coverage_ok": False,
            "markets_with_data": ["us"],
            "snippets": ["[US] valuation metrics at -1.00"],
        }
    }
    p = compute_phi(aggregated, None)
    assert any("majority" in m for m in p.missing_inputs)
    # When coverage fails, confidence is forced to 0 and then capped.
    assert p.confidence <= MISSING_INPUT_CONFIDENCE_CAP


def test_phi_full_coverage_high_confidence():
    aggregated = {
        "phi": {
            "value": -1.0,
            "coverage_ok": True,
            "markets_with_data": ["us", "japan", "china", "germany", "uk", "india"],
            "snippets": ["[US] valuation -1.00"],
        }
    }
    p = compute_phi(aggregated, None)
    assert p.value == -1
    assert p.missing_inputs == []
    assert p.confidence <= PHI_CONFIDENCE_CAP


# ---------------------------------------------------------------------------
# Ξ market_entropy
# ---------------------------------------------------------------------------


def test_xi_combines_prose_and_divergence_proxy():
    aggregated = {
        "xi": {
            "value": 0.5,
            "coverage_ok": True,
            "markets_with_data": ["us"],
            "snippets": ["[US] entropy at 0.5"],
        }
    }
    telemetry = {"divergences": list(range(10))}  # → proxy 0 (8-19 range)
    p = compute_xi(aggregated, telemetry)
    assert p.missing_inputs == []
    # 0.65*0.5 + 0.35*0 = 0.325 → round to 0
    assert p.value == 0
    assert "0.65*prose_entropy" in p.composition_formula
    assert p.confidence <= XI_CONFIDENCE_CAP


def test_xi_divergence_proxy_only_when_prose_silent():
    aggregated = {"xi": {"value": None, "coverage_ok": False, "markets_with_data": [], "snippets": []}}
    telemetry = {"divergences": list(range(45))}  # → -2
    p = compute_xi(aggregated, telemetry)
    assert "entropy_prose_silent_in_all_markets" in p.missing_inputs
    assert p.confidence <= MISSING_INPUT_CONFIDENCE_CAP
    # divergence-only proxy gives -2 value.
    assert p.value == -2
    assert "divergence_proxy_only" in p.composition_formula


def test_xi_missing_divergences_flags_input():
    aggregated = {"xi": {"value": 1.0, "coverage_ok": True, "markets_with_data": ["us"], "snippets": []}}
    p = compute_xi(aggregated, {})  # telemetry has no divergences
    assert "telemetry.divergences" in p.missing_inputs
    assert p.confidence <= MISSING_INPUT_CONFIDENCE_CAP


# ---------------------------------------------------------------------------
# Ψ psychological_wavelength
# ---------------------------------------------------------------------------


def test_psi_silent_when_no_news_and_no_commentary():
    p = compute_psi({}, {})
    assert p.value == 0
    assert p.confidence <= MISSING_INPUT_CONFIDENCE_CAP
    assert any("silent" in m for m in p.missing_inputs)


def test_psi_heuristic_with_news_blobs():
    aggregated = {
        "psi_news_blobs": [
            "[US] Risk-on tone dominates; constructive sentiment across megacaps. "
            "Bullish positioning into year-end seasonals.",
            "[Japan] Optimism around governance reforms — constructive backdrop.",
        ]
    }
    telemetry = {"commentary": {"headline": "Risk-on across DM"}}
    p = compute_psi(aggregated, telemetry)
    assert p.value >= 1  # positive sentiment
    assert p.missing_inputs == []
    assert p.confidence <= PSI_CONFIDENCE_CAP


def test_psi_with_llm_callback_uses_callback_value():
    called = []

    def fake_judge(blobs, headline):
        called.append((blobs, headline))
        return (-1, "fearful tape", 0.55)

    p = compute_psi(
        {"psi_news_blobs": ["whatever"]},
        {"commentary": {"headline": "x"}},
        psi_judge_fn=fake_judge,
    )
    assert called, "psi_judge_fn must be called when supplied"
    assert p.value == -1
    assert p.confidence == pytest.approx(min(PSI_CONFIDENCE_CAP, 0.55))


# ---------------------------------------------------------------------------
# Confidence cap rule (BUG-003)
# ---------------------------------------------------------------------------


def test_missing_input_caps_below_gap_detect_threshold():
    """Cap is strictly less than gap_detect.LOW_CONFIDENCE_THRESHOLD (0.4)."""
    assert MISSING_INPUT_CONFIDENCE_CAP < 0.4
    # Any pillar with missing_inputs must surface as below 0.4.
    p = compute_omega({}, {})  # both inputs missing
    assert p.missing_inputs
    assert p.confidence < 0.4
