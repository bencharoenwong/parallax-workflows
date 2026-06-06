"""
Contract tests for the Parallax MCP endpoints consumed by cio-letter-prep.

Structural conformance via the shared validator; per-skill realistic-values
tests assert plausible content (scores in [0,10], dates ISO, prices > 0).
"""

from __future__ import annotations

import pathlib
import sys


_HERE = pathlib.Path(__file__).resolve().parent
_PARALLAX_SCRIPTS = _HERE.parent.parent / "_parallax" / "scripts"
sys.path.insert(0, str(_PARALLAX_SCRIPTS))

from contract_validator import (  # noqa: E402
    is_iso_date,
    load_mock,
    validate,
)
from contract_schemas import (  # noqa: E402
    ANALYZE_PORTFOLIO_SCHEMA,
    CHECK_PORTFOLIO_REDUNDANCY_SCHEMA,
    EXPORT_PRICE_SERIES_SCHEMA,
    GET_ASSESSMENT_SCHEMA,
    GET_COMPANY_INFO_SCHEMA,
    GET_NEWS_SYNTHESIS_SCHEMA,
    GET_SCORE_ANALYSIS_SCHEMA,
    GET_TELEMETRY_SCHEMA,
    MACRO_ANALYST_SCHEMA,
)


# --------------------------------------------------------------------------
# Schema-conformance tests (one per endpoint)
# --------------------------------------------------------------------------


def test_get_telemetry_mock_conforms_to_schema():
    """get_telemetry mock matches the documented contract."""
    validate(load_mock("get_telemetry"), GET_TELEMETRY_SCHEMA, "get_telemetry")


def test_analyze_portfolio_mock_conforms_to_schema():
    validate(
        load_mock("analyze_portfolio"),
        ANALYZE_PORTFOLIO_SCHEMA,
        "analyze_portfolio",
    )


def test_export_price_series_mock_conforms_to_schema():
    validate(
        load_mock("export_price_series"),
        EXPORT_PRICE_SERIES_SCHEMA,
        "export_price_series",
    )


def test_get_company_info_mock_conforms_to_schema():
    validate(
        load_mock("get_company_info"),
        GET_COMPANY_INFO_SCHEMA,
        "get_company_info",
    )


def test_check_portfolio_redundancy_mock_conforms_to_schema():
    validate(
        load_mock("check_portfolio_redundancy"),
        CHECK_PORTFOLIO_REDUNDANCY_SCHEMA,
        "check_portfolio_redundancy",
    )


def test_get_assessment_mock_conforms_to_schema():
    validate(
        load_mock("get_assessment"),
        GET_ASSESSMENT_SCHEMA,
        "get_assessment",
    )


def test_get_score_analysis_mock_conforms_to_schema():
    validate(
        load_mock("get_score_analysis"),
        GET_SCORE_ANALYSIS_SCHEMA,
        "get_score_analysis",
    )


def test_get_news_synthesis_mock_conforms_to_schema():
    validate(
        load_mock("get_news_synthesis"),
        GET_NEWS_SYNTHESIS_SCHEMA,
        "get_news_synthesis",
    )


def test_macro_analyst_mock_conforms_to_schema():
    validate(
        load_mock("macro_analyst"),
        MACRO_ANALYST_SCHEMA,
        "macro_analyst",
    )


# --------------------------------------------------------------------------
# Realistic-values tests — substantive sanity checks the schema can't catch
# --------------------------------------------------------------------------


def test_get_telemetry_mock_has_realistic_values():
    data = load_mock("get_telemetry")
    assert data["regime_tag"] in {
        "risk-on", "risk-off", "neutral", "mixed", "selective rotation",
    }, f"unrecognized regime_tag {data['regime_tag']!r}"
    assert len(data["commentary"]["headline"]) > 10
    assert len(data["commentary"]["mechanism"]) > 5


def test_analyze_portfolio_mock_has_realistic_values():
    data = load_mock("analyze_portfolio")
    for factor, score in data["factor_exposures"].items():
        assert 0 <= score <= 10, f"{factor} score {score} not in [0,10]"
    sector_total = sum(data["sector_exposures"].values())
    assert abs(sector_total - 1.0) < 0.05, (
        f"sector_exposures sum to {sector_total:.4f}, expected ~1.0"
    )
    if "concentration" in data:
        c = data["concentration"]
        assert 0 <= c["top1_weight"] <= c["top3_weight"] <= 1.0


def test_export_price_series_mock_has_realistic_values():
    data = load_mock("export_price_series")
    assert "." in data["symbol"], "symbol should be RIC format e.g. AAPL.O"
    assert len(data["prices"]) > 0, "prices list is empty"
    prev_date = None
    for entry in data["prices"]:
        assert is_iso_date(entry["date"]), f"date {entry['date']!r} not ISO"
        assert entry["close"] > 0
        if prev_date is not None:
            assert entry["date"] > prev_date, "dates not strictly increasing"
        prev_date = entry["date"]
        if "high" in entry and "low" in entry:
            assert entry["high"] >= entry["low"]


def test_get_company_info_mock_has_realistic_values():
    data = load_mock("get_company_info")
    assert "." in data["symbol"]
    assert len(data["name"]) >= 2
    assert len(data["sector"]) >= 3


def test_check_portfolio_redundancy_mock_has_realistic_values():
    data = load_mock("check_portfolio_redundancy")
    assert isinstance(data["overlap_pairs"], list)
    for pair in data["overlap_pairs"]:
        assert pair["symbol_a"] != pair["symbol_b"]
        assert 0 <= pair["overlap_score"] <= 1.0
    if "coverage_pct" in data:
        assert 0 <= data["coverage_pct"] <= 1.0


def test_get_assessment_mock_has_realistic_values():
    data = load_mock("get_assessment")
    # 50 chars ~= shortest plausible non-stub sentence; tighter would risk
    # false positives on terse-but-real outputs (e.g., "Avoid — deteriorating
    # fundamentals."). Same threshold applies to news summaries below.
    assert len(data["assessment"]) >= 50, (
        "assessment text suspiciously short — likely a stub"
    )


def test_get_score_analysis_mock_has_realistic_values():
    data = load_mock("get_score_analysis")
    assert len(data["history"]) >= 2, "score history should have ≥2 points"
    prev_date = None
    for h in data["history"]:
        assert is_iso_date(h["date"])
        if prev_date is not None:
            assert h["date"] > prev_date, "score dates not strictly increasing"
        prev_date = h["date"]
        for factor in ("VALUE", "QUALITY", "MOMENTUM", "DEFENSIVE"):
            assert 0 <= h[factor] <= 10


def test_get_news_synthesis_mock_has_realistic_values():
    data = load_mock("get_news_synthesis")
    assert len(data["summary"]) >= 50, "news summary suspiciously short"
    if "articles_analyzed" in data:
        assert data["articles_analyzed"] >= 0


def test_macro_analyst_mock_has_realistic_values():
    data = load_mock("macro_analyst")
    assert len(data["market"]) >= 3
    t = data["tactical"]
    assert len(t["stance"]) >= 3
    # 30 chars ≈ shortest plausible tactical headline (e.g., "Constructive on
    # US large-cap growth"); tighter would false-positive on terse-but-real
    # outputs.
    assert len(t["summary"]) >= 30
    if "horizon_months" in t:
        assert t["horizon_months"] > 0


# Validator self-tests live in `_parallax/scripts/test_contract_validator.py`
# so the shared validator's safety net is exercised regardless of which skill
# is being tested. Per-skill test files do not duplicate them.
