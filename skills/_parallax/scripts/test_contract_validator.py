"""
Self-tests for the shared MCP contract validator.

These guard against the validator silently accepting bad data — the rejection
paths that would otherwise make every per-skill schema-conformance test
vacuous. They live in `_parallax/scripts/` (not in any per-skill test file)
so the validator's safety net is exercised regardless of which skill's tests
are running.

Run from repo root::

    pytest skills/_parallax/scripts/test_contract_validator.py -v
"""

from __future__ import annotations

import pathlib
import sys

import pytest


# Self-test runs from the validator's own directory; just import directly.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from contract_validator import OPTIONAL, validate


def test_validator_rejects_missing_required_field():
    with pytest.raises(AssertionError, match="missing required field"):
        validate({}, {"foo": str}, "root")


def test_validator_accepts_missing_optional_field():
    # Should not raise.
    validate({}, {"foo": (str, OPTIONAL)}, "root")


def test_validator_rejects_wrong_type():
    with pytest.raises(AssertionError, match="expected int"):
        validate({"foo": "bar"}, {"foo": int}, "root")


def test_validator_rejects_bool_for_int():
    # Python footgun: isinstance(True, int) is True, but bool ≠ int for the
    # contract's purposes.
    with pytest.raises(AssertionError, match="expected int, got bool"):
        validate({"foo": True}, {"foo": int}, "root")


def test_validator_validates_list_elements():
    with pytest.raises(AssertionError, match="expected int"):
        validate(
            {"foo": [1, 2, "three"]},
            {"foo": [int]},
            "root",
        )


def test_validator_rejects_null_for_optional_field():
    """OPTIONAL means 'may be absent', not 'may be null'. Negative control:
    explicit null in an OPTIONAL slot should fail because None does not match
    the inner type. See contract_validator.py docstring 'OPTIONAL semantics'.
    """
    with pytest.raises(AssertionError, match="expected str"):
        validate({"foo": None}, {"foo": (str, OPTIONAL)}, "root")
