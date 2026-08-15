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
    ANALYZE_PORTFOLIO_ENVELOPE_SCHEMA,
    ANALYZE_PORTFOLIO_ERROR_SCHEMA,
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
        ANALYZE_PORTFOLIO_ENVELOPE_SCHEMA,
        "analyze_portfolio",
    )


def test_analyze_portfolio_mock_carries_the_response_envelope():
    """Pins the ACCESS PATH, not merely the block shapes.

    The live response wraps its analytics blocks in ``result``. A fixture that
    stored them bare would still satisfy the inner schema and still pass every
    value test below — while teaching consumers to read
    ``response["portfolio_summary"]``, which returns nothing against the real
    API. That is the mock-agrees-with-its-own-schema failure this suite exists
    to prevent, so the envelope gets its own assertion instead of riding along
    inside another test."""
    mock = load_mock("analyze_portfolio")
    assert "result" in mock, (
        "analyze_portfolio mock lost its response envelope — the blocks belong "
        "under 'result', and consumers read response['result'][<block>]"
    )
    assert isinstance(mock["result"], dict)

    # The blocks live INSIDE result, never alongside it.
    for block in ("portfolio_summary", "latest_holdings",
                  "company_contribution", "_meta"):
        assert block in mock["result"], f"{block} missing from result"
        assert block not in mock, (
            f"{block} sits at the top level — the envelope has been flattened"
        )


def test_analyze_portfolio_error_envelope_has_no_result():
    """``success`` is not a status flag.

    A credit-exhausted call returns ``success: true`` with a ``detail`` object
    and no ``result`` key at all. Code guarded by ``if payload["success"]``
    passes here and then raises KeyError, so the only sound guard is the
    presence of ``result`` — which is what this fixture keeps honest."""
    mock = load_mock("analyze_portfolio_credit_exhausted")
    validate(mock, ANALYZE_PORTFOLIO_ERROR_SCHEMA,
             "analyze_portfolio_credit_exhausted")
    assert mock["success"] is True, "the failure envelope reports success: true"
    assert "result" not in mock, "result must be ABSENT, not null"
    assert mock["detail"]["required"] > mock["detail"]["balance"]


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
    # Read through the envelope, exactly as a consumer must.
    data = load_mock("analyze_portfolio")["result"]

    holdings = data["latest_holdings"]
    assert holdings, "latest_holdings is empty"
    for h in holdings:
        assert "." in h["ric"], f"{h['ric']!r} is not RIC form"
        # Per-security factor scores are 0-10, NOT 0-100.
        for factor in ("value", "quality", "momentum", "defensive", "tactical"):
            assert 0 <= h[factor] <= 10, f"{h['ric']} {factor} not in [0,10]"
        assert 0 <= h["total"] <= 10

    # Portfolio-level scores are 0-100 integers — a different scale from the
    # per-security scores above, and the single most-confused fact in this
    # payload. ``coverage`` is the exception: it is a 0-1 fraction.
    scores = data["portfolio_scores"]
    for factor in ("value", "quality", "momentum", "defensive", "tactical",
                   "total"):
        assert isinstance(scores[factor], int), f"{factor} must be an int"
        assert 0 <= scores[factor] <= 100, f"{factor} not on the 0-100 scale"
    assert 0 <= scores["coverage"] <= 1

    # The money identity that actually holds. Note which one is NOT asserted:
    # quantity * close_local != ending_value, because ending_value rides a
    # dividend-inclusive path while close_local is the raw price.
    summary = data["portfolio_summary"]
    assert abs(sum(h["ending_value"] for h in holdings)
               - summary["final_value"]) < 1e-9
    assert abs(sum(r["total_pl"] for r in data["company_contribution"])
               - summary["total_pl"]) < 1e-9
    assert abs(sum(r["contribution_pct"] for r in data["company_contribution"])
               - 1.0) < 1e-9

    # sector_allocation is a LIST of (date x sector) rows, not a dict. Weights
    # within a date sum to 1 only to rounding — they are not force-balanced.
    by_date: dict[str, float] = {}
    for row in data["sector_allocation"]:
        assert is_iso_date(row["date"])
        by_date[row["date"]] = by_date.get(row["date"], 0.0) + row["weight"]
    assert by_date, "sector_allocation is empty"
    for day, total in by_date.items():
        assert abs(total - 1.0) < 5e-6, f"{day} weights sum to {total}"


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
    rows = data["data"]
    assert len(rows) >= 2, "score history should have ≥2 points"
    if "weeks" in data:
        assert data["weeks"] == len(rows), "weeks disagrees with the row count"

    prev_date = None
    for row in rows:
        assert is_iso_date(row["date"])
        if prev_date is not None:
            assert row["date"] > prev_date, "score dates not strictly increasing"
        prev_date = row["date"]
        # Sub-scores are 0-10 integers; the composite is 0-10 with one decimal.
        for factor in ("value", "quality", "momentum", "defensive", "tactical"):
            assert 0 <= row[factor] <= 10, f"{factor} not in [0,10]"
        assert 0 <= row["total"] <= 10
        # ``total`` is a separately-computed composite. If it ever equals the
        # mean of the five sub-scores on every row, the fixture has drifted into
        # modelling a relation the API does not have.
        assert row["symbol"] == data["symbol"]

    means = [round(sum(row[f] for f in ("value", "quality", "momentum",
                                        "defensive", "tactical")) / 5, 1)
             for row in rows]
    assert any(row["total"] != m for row, m in zip(rows, means)), (
        "total is the mean of the sub-scores on every row — the live composite "
        "is not a mean, so this fixture is modelling a false identity"
    )


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
