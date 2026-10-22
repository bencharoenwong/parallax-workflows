"""
Schema-conformance tests for shared mocks that no per-skill contract test
loads: the insufficient-coverage redundancy fixture and the macro_analyst
overview mock.

Run from repo root::

    pytest skills/_parallax/scripts/test_shared_mock_contracts.py -v
"""

from __future__ import annotations

import copy
import pathlib
import sys

import pytest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from contract_validator import load_mock, validate  # noqa: E402
from contract_schemas import (  # noqa: E402
    CHECK_PORTFOLIO_REDUNDANCY_SCHEMA,
    MACRO_ANALYST_OVERVIEW_SCHEMA,
    MACRO_ANALYST_SCHEMA,
)


HAS_ISSUES_STATES = (True, False, "unknown")

REDUNDANCY_MOCKS = (
    "check_portfolio_redundancy",
    "check_portfolio_redundancy_silent_fail",
    "check_portfolio_redundancy_insufficient_coverage",
)


@pytest.mark.parametrize("name", REDUNDANCY_MOCKS)
def test_redundancy_mocks_conform_to_schema(name):
    mock = load_mock(name)
    validate(mock, CHECK_PORTFOLIO_REDUNDANCY_SCHEMA, name)
    if "has_issues" in mock:
        assert mock["has_issues"] in HAS_ISSUES_STATES, mock["has_issues"]


def test_insufficient_coverage_mock_models_unknown_branch():
    mock = load_mock("check_portfolio_redundancy_insufficient_coverage")
    assert mock["has_issues"] == "unknown"
    assert mock["coverage_weight_fraction"] < 0.5
    unresolved = mock["holdings_unresolved"]
    assert unresolved and all(isinstance(h, dict) for h in unresolved)
    assert len(unresolved) == mock["holdings_failed"]


def test_redundancy_schema_rejects_symbol_string_unresolved():
    mock = copy.deepcopy(
        load_mock("check_portfolio_redundancy_insufficient_coverage")
    )
    mock["holdings_unresolved"] = [h["symbol"] for h in mock["holdings_unresolved"]]
    with pytest.raises(AssertionError, match="holdings_unresolved"):
        validate(mock, CHECK_PORTFOLIO_REDUNDANCY_SCHEMA, "redundancy")


def test_macro_analyst_overview_mock_conforms_to_schema():
    mock = load_mock("macro_analyst_overview")
    validate(mock, MACRO_ANALYST_OVERVIEW_SCHEMA, "macro_analyst_overview")
    components = mock["components"]
    assert components
    for name, entry in components.items():
        validate(
            entry,
            {"content": str, "truncated": bool},
            f"macro_analyst_overview.components.{name}",
        )
    assert mock["component_count"] == len(components)


def test_macro_analyst_overview_mock_is_not_drilldown_shape():
    with pytest.raises(AssertionError, match="content"):
        validate(
            load_mock("macro_analyst_overview"),
            MACRO_ANALYST_SCHEMA,
            "macro_analyst_overview",
        )
