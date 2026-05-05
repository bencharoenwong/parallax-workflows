"""
Contract tests for the Parallax MCP endpoints consumed by the
cio-letter-prep skill.

Why this file exists
--------------------

The cio-letter-prep workflow orchestrates ~9 Parallax MCP endpoints (Batches A
and B in the SKILL plan). The skill reads specific fields from each response.
If an upstream endpoint changes its response shape (drops a field, renames,
changes type), the skill silently degrades until a customer hits it.

These tests pin a "contract" per endpoint:

    1. A schema describing the fields the skill is KNOWN to read, with
       a required/optional marker and an expected type.
    2. A representative happy-path mock JSON file (one per endpoint) under
       ``mcp_mocks/``.
    3. Two tests per endpoint: (a) the mock conforms to the schema,
       (b) the values are realistic (dates ISO, scores in [0,10], prices > 0,
       weights in [0,1], etc.).

When the live MCP server changes a response shape, refresh the relevant mock
(see ``mcp_mocks/README.md``) and update the schema below in the same commit.
A red contract test in CI surfaces drift before the customer does.

Implementation notes
--------------------

We use a hand-rolled validator instead of ``jsonschema`` to keep the skill
stdlib-only (consistent with ``contribution.py``). The validator is small
(~40 lines) and supports nested dicts, lists-of-dicts, and a small "any of
these types" form via tuples — sufficient for these contracts.

Schemas use this Python-dict DSL:

    SCHEMA = {
        "field_name": <type spec>,
        ...
    }

    <type spec> ::= type                       # required, single type
                  | (type, ...)                # required, any of these types
                  | (type, "optional")         # optional, single type
                  | dict (nested schema)       # required nested object
                  | (dict, "optional")         # optional nested object
                  | [<type spec>]              # required list; element schema
                  | ([<type spec>], "optional") # optional list

For list elements that are dicts, use ``[nested_schema]`` (a one-element
list whose only element is a dict).
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Any

import pytest


# --------------------------------------------------------------------------
# Mock loading
# --------------------------------------------------------------------------

MOCKS_DIR = pathlib.Path(__file__).parent / "mcp_mocks"


def _load_mock(name: str) -> Any:
    """Load mock JSON file ``mcp_mocks/<name>.json`` and return parsed value."""
    path = MOCKS_DIR / f"{name}.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# Hand-rolled schema validator
# --------------------------------------------------------------------------

_OPTIONAL = "optional"


def _is_optional_spec(spec: Any) -> bool:
    """True iff ``spec`` is a ``(inner, "optional")`` tuple marker."""
    return (
        isinstance(spec, tuple)
        and len(spec) == 2
        and spec[1] == _OPTIONAL
    )


def _validate(value: Any, spec: Any, path: str) -> None:
    """Validate ``value`` against ``spec``. Raise AssertionError on mismatch.

    See module docstring for the spec DSL. ``path`` is a dotted JSON path
    used in error messages.
    """
    # Optional wrapper: unwrap and validate inner
    if _is_optional_spec(spec):
        _validate(value, spec[0], path)
        return

    # Nested dict schema
    if isinstance(spec, dict):
        assert isinstance(value, dict), (
            f"{path}: expected dict, got {type(value).__name__}"
        )
        for field, field_spec in spec.items():
            child_path = f"{path}.{field}" if path else field
            optional = _is_optional_spec(field_spec)
            if field not in value:
                assert optional, f"{child_path}: missing required field"
                continue
            _validate(value[field], field_spec, child_path)
        return

    # List schema: spec is a one-element list whose element is the elt spec
    if isinstance(spec, list):
        assert isinstance(value, list), (
            f"{path}: expected list, got {type(value).__name__}"
        )
        assert len(spec) == 1, (
            f"{path}: list spec must have exactly one element schema"
        )
        elt_spec = spec[0]
        for i, item in enumerate(value):
            _validate(item, elt_spec, f"{path}[{i}]")
        return

    # Tuple-of-types: any of these types
    if isinstance(spec, tuple):
        assert all(isinstance(t, type) for t in spec), (
            f"{path}: malformed tuple spec {spec!r}"
        )
        assert isinstance(value, spec), (
            f"{path}: expected one of {[t.__name__ for t in spec]}, "
            f"got {type(value).__name__}"
        )
        return

    # Single type
    if isinstance(spec, type):
        # bool is subclass of int in Python — disallow accidental bool-for-int
        if spec is int and isinstance(value, bool):
            raise AssertionError(f"{path}: expected int, got bool")
        assert isinstance(value, spec), (
            f"{path}: expected {spec.__name__}, got {type(value).__name__}"
        )
        return

    raise AssertionError(f"{path}: malformed schema spec {spec!r}")


def _is_iso_date(s: str) -> bool:
    """True iff ``s`` parses as an ISO 'YYYY-MM-DD' date."""
    try:
        _dt.date.fromisoformat(s)
        return True
    except (ValueError, TypeError):
        return False


def _is_iso_datetime(s: str) -> bool:
    """True iff ``s`` parses as an ISO datetime, with or without trailing Z."""
    try:
        normalised = s.replace("Z", "+00:00") if s.endswith("Z") else s
        _dt.datetime.fromisoformat(normalised)
        return True
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------
# Schemas — one per endpoint the skill consumes
# --------------------------------------------------------------------------

# Number is "int or float"; Parallax may return either depending on the value.
NUM = (int, float)


GET_TELEMETRY_SCHEMA = {
    "regime_tag": str,
    "signals": dict,  # opaque blob; skill reads opportunistically
    "commentary": {
        "headline": str,
        "mechanism": str,
    },
    "divergences": [{
        "ticker": str,
        "factor": str,
        "magnitude": NUM,
    }],
}


ANALYZE_PORTFOLIO_SCHEMA = {
    "factor_exposures": {
        "VALUE": NUM,
        "QUALITY": NUM,
        "MOMENTUM": NUM,
        "DEFENSIVE": NUM,
    },
    "sector_exposures": dict,  # sector name -> weight; arbitrary keys
    "concentration": ({
        "top1_weight": NUM,
        "top3_weight": NUM,
        "hhi": (NUM, _OPTIONAL),
    }, _OPTIONAL),
    "risk_metrics": (dict, _OPTIONAL),
    "holdings_count": (int, _OPTIONAL),
    "as_of": (str, _OPTIONAL),
}


EXPORT_PRICE_SERIES_SCHEMA = {
    "symbol": str,
    "currency": (str, _OPTIONAL),
    "prices": [{
        "date": str,
        "open": (NUM, _OPTIONAL),
        "high": (NUM, _OPTIONAL),
        "low": (NUM, _OPTIONAL),
        "close": NUM,
        "volume": (NUM, _OPTIONAL),
    }],
}


GET_COMPANY_INFO_SCHEMA = {
    "symbol": str,
    "name": str,
    "exchange": (str, _OPTIONAL),
    "sector": str,
    "industry": (str, _OPTIONAL),
    "country": (str, _OPTIONAL),
    "market_cap_usd": (NUM, _OPTIONAL),
    "currency": (str, _OPTIONAL),
    "description": (str, _OPTIONAL),
    "website": (str, _OPTIONAL),
}


# PROVISIONAL — see README. The skill plan refers to this endpoint but
# field-level usage is not yet documented in any existing SKILL.md. The
# schema below is best-inference from the function name and conventions.
CHECK_PORTFOLIO_REDUNDANCY_SCHEMA = {
    "overlap_pairs": [{
        "symbol_a": str,
        "symbol_b": str,
        "overlap_score": NUM,
        "shared_factors": ([str], _OPTIONAL),
        "shared_sector": (str, _OPTIONAL),
    }],
    "coverage_pct": (NUM, _OPTIONAL),
    "holdings_analyzed": (int, _OPTIONAL),
    "holdings_total": (int, _OPTIONAL),
}


GET_ASSESSMENT_SCHEMA = {
    "symbol": str,
    "name": (str, _OPTIONAL),
    "assessment": str,
    "rationale": (str, _OPTIONAL),
    "confidence": (str, _OPTIONAL),
    "generated_at": (str, _OPTIONAL),
}


GET_SCORE_ANALYSIS_SCHEMA = {
    "symbol": str,
    "name": (str, _OPTIONAL),
    "weeks": (int, _OPTIONAL),
    "history": [{
        "date": str,
        "VALUE": NUM,
        "QUALITY": NUM,
        "MOMENTUM": NUM,
        "DEFENSIVE": NUM,
        "OVERALL": (NUM, _OPTIONAL),
    }],
}


GET_NEWS_SYNTHESIS_SCHEMA = {
    "symbol": str,
    "name": (str, _OPTIONAL),
    "summary": str,
    "key_themes": ([str], _OPTIONAL),
    "sentiment": (str, _OPTIONAL),
    "articles_analyzed": (int, _OPTIONAL),
    "period_start": (str, _OPTIONAL),
    "period_end": (str, _OPTIONAL),
    "generated_at": (str, _OPTIONAL),
}


MACRO_ANALYST_SCHEMA = {
    "market": str,
    "component": (str, _OPTIONAL),
    "regime": (str, _OPTIONAL),
    "tactical": {
        "stance": str,
        "horizon_months": (int, _OPTIONAL),
        "summary": str,
        "key_drivers": ([str], _OPTIONAL),
        "factor_tilts": (dict, _OPTIONAL),
    },
    "generated_at": (str, _OPTIONAL),
}


# --------------------------------------------------------------------------
# Schema-conformance tests (one per endpoint)
# --------------------------------------------------------------------------

def test_get_telemetry_mock_conforms_to_schema():
    """get_telemetry mock matches the documented contract."""
    _validate(_load_mock("get_telemetry"), GET_TELEMETRY_SCHEMA, "get_telemetry")


def test_analyze_portfolio_mock_conforms_to_schema():
    """analyze_portfolio mock matches the documented contract."""
    _validate(
        _load_mock("analyze_portfolio"),
        ANALYZE_PORTFOLIO_SCHEMA,
        "analyze_portfolio",
    )


def test_export_price_series_mock_conforms_to_schema():
    """export_price_series mock matches the documented contract."""
    _validate(
        _load_mock("export_price_series"),
        EXPORT_PRICE_SERIES_SCHEMA,
        "export_price_series",
    )


def test_get_company_info_mock_conforms_to_schema():
    """get_company_info mock matches the documented contract."""
    _validate(
        _load_mock("get_company_info"),
        GET_COMPANY_INFO_SCHEMA,
        "get_company_info",
    )


def test_check_portfolio_redundancy_mock_conforms_to_schema():
    """check_portfolio_redundancy mock matches the (provisional) contract."""
    _validate(
        _load_mock("check_portfolio_redundancy"),
        CHECK_PORTFOLIO_REDUNDANCY_SCHEMA,
        "check_portfolio_redundancy",
    )


def test_get_assessment_mock_conforms_to_schema():
    """get_assessment mock matches the documented contract."""
    _validate(
        _load_mock("get_assessment"),
        GET_ASSESSMENT_SCHEMA,
        "get_assessment",
    )


def test_get_score_analysis_mock_conforms_to_schema():
    """get_score_analysis mock matches the documented contract."""
    _validate(
        _load_mock("get_score_analysis"),
        GET_SCORE_ANALYSIS_SCHEMA,
        "get_score_analysis",
    )


def test_get_news_synthesis_mock_conforms_to_schema():
    """get_news_synthesis mock matches the documented contract."""
    _validate(
        _load_mock("get_news_synthesis"),
        GET_NEWS_SYNTHESIS_SCHEMA,
        "get_news_synthesis",
    )


def test_macro_analyst_mock_conforms_to_schema():
    """macro_analyst mock matches the documented contract."""
    _validate(
        _load_mock("macro_analyst"),
        MACRO_ANALYST_SCHEMA,
        "macro_analyst",
    )


# --------------------------------------------------------------------------
# Realistic-values tests — sanity checks on numeric ranges, ISO dates, etc.
# --------------------------------------------------------------------------

def test_get_telemetry_mock_has_realistic_values():
    """Telemetry divergences carry plausible factor names and magnitudes."""
    data = _load_mock("get_telemetry")
    assert data["regime_tag"], "regime_tag must be non-empty"
    assert data["commentary"]["headline"], "commentary.headline must be non-empty"
    assert data["commentary"]["mechanism"], "commentary.mechanism must be non-empty"
    for div in data["divergences"]:
        # Factor scores live on a 0-10 scale; divergence magnitudes are
        # bounded changes in that scale.
        assert -10.0 <= div["magnitude"] <= 10.0, (
            f"divergence magnitude out of range: {div}"
        )
        assert div["ticker"], "divergence ticker must be non-empty"


def test_analyze_portfolio_mock_has_realistic_values():
    """Factor scores in [0,10]; sector weights in [0,1] and approximately sum to 1."""
    data = _load_mock("analyze_portfolio")
    for factor, score in data["factor_exposures"].items():
        assert 0.0 <= score <= 10.0, f"{factor} score out of [0,10]: {score}"
    sector_total = sum(data["sector_exposures"].values())
    for sector, weight in data["sector_exposures"].items():
        assert 0.0 <= weight <= 1.0, f"{sector} weight out of [0,1]: {weight}"
    assert abs(sector_total - 1.0) < 0.05, (
        f"sector exposures should sum to ~1.0, got {sector_total}"
    )
    if "concentration" in data:
        c = data["concentration"]
        assert 0.0 <= c["top1_weight"] <= 1.0
        assert 0.0 <= c["top3_weight"] <= 1.0
        assert c["top1_weight"] <= c["top3_weight"], (
            "top1 cannot exceed top3"
        )


def test_export_price_series_mock_has_realistic_values():
    """Prices positive; dates ISO and strictly increasing."""
    data = _load_mock("export_price_series")
    assert data["symbol"], "symbol must be non-empty"
    assert len(data["prices"]) > 0, "prices must be non-empty"
    prev_date: _dt.date | None = None
    for row in data["prices"]:
        assert _is_iso_date(row["date"]), f"non-ISO date: {row['date']}"
        d = _dt.date.fromisoformat(row["date"])
        if prev_date is not None:
            assert d > prev_date, (
                f"dates must be strictly increasing; {prev_date} -> {d}"
            )
        prev_date = d
        assert row["close"] > 0, f"non-positive close on {row['date']}"
        if "open" in row:
            assert row["open"] > 0
        if "high" in row and "low" in row:
            assert row["high"] >= row["low"], (
                f"high < low on {row['date']}"
            )


def test_get_company_info_mock_has_realistic_values():
    """Company-info fields are non-empty and market cap (if present) positive."""
    data = _load_mock("get_company_info")
    assert data["symbol"]
    assert data["name"]
    assert data["sector"]
    if "market_cap_usd" in data:
        assert data["market_cap_usd"] > 0


def test_check_portfolio_redundancy_mock_has_realistic_values():
    """Overlap scores in [0,1]; pair symbols differ; coverage in [0,1]."""
    data = _load_mock("check_portfolio_redundancy")
    for pair in data["overlap_pairs"]:
        assert 0.0 <= pair["overlap_score"] <= 1.0, (
            f"overlap_score out of [0,1]: {pair}"
        )
        assert pair["symbol_a"] != pair["symbol_b"], (
            f"overlap pair must reference distinct symbols: {pair}"
        )
    if "coverage_pct" in data:
        assert 0.0 <= data["coverage_pct"] <= 1.0


def test_get_assessment_mock_has_realistic_values():
    """Assessment prose is substantive (not a stub) and timestamp ISO."""
    data = _load_mock("get_assessment")
    assert data["symbol"]
    assert len(data["assessment"]) >= 50, (
        "assessment text suspiciously short — likely a stub"
    )
    if "generated_at" in data:
        assert _is_iso_datetime(data["generated_at"]), (
            f"non-ISO generated_at: {data['generated_at']}"
        )


def test_get_score_analysis_mock_has_realistic_values():
    """Score history dates ISO + ascending; all factor scores in [0,10]."""
    data = _load_mock("get_score_analysis")
    assert len(data["history"]) >= 2, "score history needs ≥2 points to be useful"
    prev_date: _dt.date | None = None
    for row in data["history"]:
        assert _is_iso_date(row["date"]), f"non-ISO date: {row['date']}"
        d = _dt.date.fromisoformat(row["date"])
        if prev_date is not None:
            assert d > prev_date, (
                f"score-history dates must be ascending; {prev_date} -> {d}"
            )
        prev_date = d
        for factor in ("VALUE", "QUALITY", "MOMENTUM", "DEFENSIVE"):
            assert 0.0 <= row[factor] <= 10.0, (
                f"{factor} on {row['date']} out of [0,10]: {row[factor]}"
            )


def test_get_news_synthesis_mock_has_realistic_values():
    """News summary is non-trivial; period dates ISO if present."""
    data = _load_mock("get_news_synthesis")
    assert data["symbol"]
    assert len(data["summary"]) >= 50, "news summary suspiciously short"
    for f in ("period_start", "period_end"):
        if f in data:
            assert _is_iso_date(data[f]), f"non-ISO {f}: {data[f]}"
    if "period_start" in data and "period_end" in data:
        start = _dt.date.fromisoformat(data["period_start"])
        end = _dt.date.fromisoformat(data["period_end"])
        assert start <= end, "period_start must be <= period_end"
    if "articles_analyzed" in data:
        assert data["articles_analyzed"] >= 0


def test_macro_analyst_mock_has_realistic_values():
    """Tactical stance non-empty; horizon positive if present."""
    data = _load_mock("macro_analyst")
    assert data["market"]
    assert data["tactical"]["stance"]
    assert len(data["tactical"]["summary"]) >= 30
    if "horizon_months" in data["tactical"]:
        assert data["tactical"]["horizon_months"] > 0


# --------------------------------------------------------------------------
# Validator self-tests — guard against the validator silently passing
# --------------------------------------------------------------------------

def test_validator_rejects_missing_required_field():
    """A missing required field must raise AssertionError."""
    schema = {"a": str, "b": int}
    with pytest.raises(AssertionError, match="missing required"):
        _validate({"a": "hi"}, schema, "")


def test_validator_accepts_missing_optional_field():
    """A missing optional field must NOT raise."""
    schema = {"a": str, "b": (int, _OPTIONAL)}
    _validate({"a": "hi"}, schema, "")  # should not raise


def test_validator_rejects_wrong_type():
    """A wrong-typed field must raise AssertionError."""
    schema = {"a": int}
    with pytest.raises(AssertionError, match="expected int"):
        _validate({"a": "not-an-int"}, schema, "")


def test_validator_rejects_bool_for_int():
    """bool is a subclass of int — explicitly disallow accidental bool-for-int."""
    schema = {"a": int}
    with pytest.raises(AssertionError, match="expected int, got bool"):
        _validate({"a": True}, schema, "")


def test_validator_validates_list_elements():
    """List-of-dicts schema must validate every element."""
    schema = {"items": [{"x": int}]}
    _validate({"items": [{"x": 1}, {"x": 2}]}, schema, "")
    with pytest.raises(AssertionError):
        _validate({"items": [{"x": 1}, {"x": "bad"}]}, schema, "")
