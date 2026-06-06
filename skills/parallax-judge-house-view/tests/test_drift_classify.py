"""Tests for drift_classify.classify_severity + summarize_states."""
from __future__ import annotations

import drift_classify


def _res(state: str, dim: str = "tilts.sectors.health_care", cio=1, plx=-1, market=None) -> dict:
    return {
        "state": state,
        "dim": dim,
        "cio_tilt": cio,
        "parallax_view": plx,
        "market": market,
    }


def test_no_divergence_returns_minor():
    resolutions = [_res("ALIGNED"), _res("ALIGNED")]
    severity, details = drift_classify.classify_severity(resolutions, view_age_days=5, denominator=2)
    assert severity == "drift_minor"
    assert details["divergent_count"] == 0
    assert details["divergent_pct"] == 0.0


def test_below_20pct_minor():
    # 1 divergent out of 6 = 16.67% < 20%
    resolutions = [_res("DIVERGENT_FRESH")] + [_res("ALIGNED") for _ in range(5)]
    severity, _ = drift_classify.classify_severity(resolutions, view_age_days=5, denominator=6)
    assert severity == "drift_minor"


def test_20_to_50_moderate():
    # 2 divergent out of 6 = 33% in [20%, 50%]
    resolutions = [_res("DIVERGENT_FRESH"), _res("DIVERGENT_STALE")] + [_res("ALIGNED") for _ in range(4)]
    severity, _ = drift_classify.classify_severity(resolutions, view_age_days=5, denominator=6)
    assert severity == "drift_moderate"


def test_over_50pct_material():
    resolutions = [_res("DIVERGENT_FRESH") for _ in range(4)] + [_res("ALIGNED")]
    severity, _ = drift_classify.classify_severity(resolutions, view_age_days=5, denominator=5)
    assert severity == "drift_material"


def test_pillar_divergence_forces_material():
    # 1 divergent out of 10 (10%) — would be minor — but it's a pillar.
    resolutions = [_res("DIVERGENT_FRESH", dim="tilts.pillars.econometrics_phase")] + [
        _res("ALIGNED") for _ in range(9)
    ]
    severity, details = drift_classify.classify_severity(resolutions, view_age_days=5, denominator=10)
    assert severity == "drift_material"
    assert details["pillar_divergence"] is True
    assert "tilts.pillars.econometrics_phase" in details["pillar_cells"]


def test_macro_regime_sign_flip_forces_material():
    # Sign flip on macro_regime.growth — small percentage but escalates.
    resolutions = [_res(
        "DIVERGENT_FRESH",
        dim="tilts.macro_regime.growth",
        cio=2, plx=-2,
    )] + [_res("ALIGNED") for _ in range(9)]
    severity, details = drift_classify.classify_severity(resolutions, view_age_days=5, denominator=10)
    assert severity == "drift_material"
    assert details["macro_sign_flip"] is True


def test_magnitude_escalation_minor_to_moderate():
    # 1 divergent out of 10 (10%) — would be minor.
    # But |cio - plx| = 4 (>= 3) bumps it one tier → moderate.
    resolutions = [_res(
        "DIVERGENT_FRESH",
        dim="tilts.sectors.health_care",
        cio=2, plx=-2,
    )] + [_res("ALIGNED") for _ in range(9)]
    severity, details = drift_classify.classify_severity(resolutions, view_age_days=5, denominator=10)
    assert severity == "drift_moderate"
    assert details["magnitude_escalated"] is True
    assert details["max_magnitude"] == 4


def test_magnitude_escalation_caps_at_material():
    # Already material via pct; magnitude shouldn't double-bump beyond.
    resolutions = [_res("DIVERGENT_FRESH", cio=2, plx=-2) for _ in range(4)] + [_res("ALIGNED")]
    severity, _ = drift_classify.classify_severity(resolutions, view_age_days=5, denominator=5)
    assert severity == "drift_material"


def test_zero_denominator_safe():
    severity, details = drift_classify.classify_severity([], view_age_days=5, denominator=0)
    assert severity == "drift_minor"
    assert details["divergent_pct"] == 0.0


def test_summarize_states_buckets_correctly():
    resolutions = [
        _res("ALIGNED"),
        _res("ALIGNED"),
        _res("DIVERGENT_FRESH"),
        _res("DIVERGENT_STALE"),
        _res("PARALLAX_SILENT"),
        _res("UNCOVERED"),
        _res("CIO_SILENT"),
    ]
    summary = drift_classify.summarize_states(resolutions)
    assert summary["aligned_count"] == 2
    assert summary["drift_minor_count"] == 2  # FRESH + STALE
    assert summary["parallax_silent_count"] == 1
    assert summary["uncovered_count"] == 1
    assert summary["cio_silent_count"] == 1
    assert summary["drift_material_count"] == 0


def test_summarize_handles_unknown_state_gracefully():
    summary = drift_classify.summarize_states([_res("WAT")])
    # No bucket bumps; counts all 0.
    assert sum(summary.values()) == 0
