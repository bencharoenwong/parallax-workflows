"""
Contracts for the renamed fields of get_company_info, get_financials and
export_peer_comparison (json). The payloads below are synthetic; they model the
live response shapes, including the edge cases skills must handle.

Run from repo root::

    pytest skills/_parallax/scripts/test_field_contracts.py -v
"""

from __future__ import annotations

import copy
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from contract_validator import is_iso_date, load_mock, validate  # noqa: E402
from contract_schemas import (  # noqa: E402
    EXPORT_PEER_COMPARISON_JSON_SCHEMA,
    FINANCIALS_FREQUENCIES,
    GET_COMPANY_INFO_SCHEMA,
    GET_FINANCIALS_SCHEMA,
)


def _peer_row(symbol: str, *, target: bool = False, **overrides):
    row = {
        "symbol": symbol,
        "company": f"{symbol} Synthetic Co",
        "market": "United States",
        "sector": "Technology",
        "industry": "Computer Hardware",
        "total": 6.1,
        "quality": 10,
        "value": 3,
        "momentum": 7,
        "defensive": 8,
        "tactical": 1,
        "pe_ratio": 24.3,
        "ev_ebitda": 16.2,
        "roe": None,
        "ytd_return": 12.5,
        "mtd_return": 0,
        "debt_to_equity": None,
        "market_cap_b": 133.8,
        "is_target": target,
    }
    row.update(overrides)
    return row


PEERS = {
    "success": True,
    "symbol": "AXCM.O",
    "format": "json",
    "data": [
        _peer_row("AXCM.O", target=True, recommendation="HOLD"),
        _peer_row("BRVX", roe=23.3, debt_to_equity=0.7),
    ],
    "pe_basis": "pe_ratio is trailing when available, otherwise fiscal-year.",
}

FINANCIALS = {
    "success": True,
    "symbol": "AXCM.O",
    "statement": "balance_sheet",
    "data": [
        {"frequency": "annual", "period_end": "2025-09-27", "currency": "USD",
         "total_assets": 1.0e11},
        {"frequency": None, "period_end": "2024-09-28", "currency": "USD",
         "total_assets": 9.0e10},
    ],
}


# get_company_info ---------------------------------------------------------

def test_company_info_mock_conforms_and_uses_the_renamed_fields():
    mock = load_mock("get_company_info")
    validate(mock, GET_COMPANY_INFO_SCHEMA, "get_company_info")
    data = mock["data"]
    assert int(data["market_cap"]) > 0
    assert int(data["shares_outstanding"]) > 0
    assert "listing line" in mock["field_notes"]["market_cap"]


def test_company_info_rejects_a_field_outside_the_contract():
    mock = copy.deepcopy(load_mock("get_company_info"))
    mock["data"]["cap_raw"] = mock["data"].pop("market_cap")
    with pytest.raises(AssertionError, match=r"data: unknown field\(s\) \['cap_raw'\]"):
        validate(mock, GET_COMPANY_INFO_SCHEMA, "get_company_info")


# get_financials -----------------------------------------------------------

def check_financials_periods(payload):
    """Validate the schema plus the period-label values the schema cannot express."""
    validate(payload, GET_FINANCIALS_SCHEMA, "get_financials")
    for i, row in enumerate(payload["data"]):
        assert is_iso_date(row["period_end"]), (
            f"data[{i}].period_end: not an ISO date: {row['period_end']!r}"
        )
        assert row["frequency"] is None or row["frequency"] in FINANCIALS_FREQUENCIES, (
            f"data[{i}].frequency: unexpected value {row['frequency']!r}"
        )


def test_financials_rows_carry_period_labels():
    check_financials_periods(FINANCIALS)


def test_financials_rejects_an_unknown_frequency_value():
    bad = copy.deepcopy(FINANCIALS)
    bad["data"][0]["frequency"] = "monthly"
    with pytest.raises(AssertionError, match=r"data\[0\]\.frequency: unexpected value 'monthly'"):
        check_financials_periods(bad)


def test_financials_rejects_a_non_iso_period_end():
    bad = copy.deepcopy(FINANCIALS)
    bad["data"][1]["period_end"] = "09/28/2024"
    with pytest.raises(AssertionError, match=r"data\[1\]\.period_end: not an ISO date"):
        check_financials_periods(bad)


def test_financials_row_without_period_end_fails():
    bad = copy.deepcopy(FINANCIALS)
    del bad["data"][0]["period_end"]
    with pytest.raises(AssertionError, match=r"data\[0\]\.period_end: missing required field"):
        validate(bad, GET_FINANCIALS_SCHEMA, "")


def test_financials_row_must_state_frequency_even_when_unknown():
    bad = copy.deepcopy(FINANCIALS)
    del bad["data"][1]["frequency"]
    with pytest.raises(AssertionError, match=r"data\[1\]\.frequency: missing required field"):
        validate(bad, GET_FINANCIALS_SCHEMA, "")


# export_peer_comparison (json) ---------------------------------------------

def test_peer_rows_conform():
    validate(PEERS, EXPORT_PEER_COMPARISON_JSON_SCHEMA, "export_peer_comparison")


@pytest.mark.parametrize("targets", [0, 2])
def test_peer_rows_conform_with_zero_or_several_flagged_rows(targets):
    # Live peer sets can carry no flagged row, so the contract must not require one.
    rows = copy.deepcopy(PEERS)
    for i, row in enumerate(rows["data"]):
        row["is_target"] = i < targets
    validate(rows, EXPORT_PEER_COMPARISON_JSON_SCHEMA, "")


def test_peer_row_missing_value_must_be_null_not_absent():
    bad = copy.deepcopy(PEERS)
    del bad["data"][1]["roe"]
    with pytest.raises(AssertionError, match=r"data\[1\]\.roe: missing required field"):
        validate(bad, EXPORT_PEER_COMPARISON_JSON_SCHEMA, "")


@pytest.mark.parametrize("field", ["ticker", "name", "pe", "ytd"])
def test_peer_row_rejects_names_outside_the_allowlist(field):
    bad = copy.deepcopy(PEERS)
    bad["data"][1][field] = 1
    with pytest.raises(AssertionError, match=r"data\[1\]: unknown field"):
        validate(bad, EXPORT_PEER_COMPARISON_JSON_SCHEMA, "")


def test_peer_recommendation_is_optional():
    payload = copy.deepcopy(PEERS)
    assert "recommendation" in payload["data"][0]
    del payload["data"][0]["recommendation"]
    validate(payload, EXPORT_PEER_COMPARISON_JSON_SCHEMA, "")
