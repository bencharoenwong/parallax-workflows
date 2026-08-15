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

from contract_validator import (  # noqa: E402
    NULLABLE,
    NUM,
    OPTIONAL,
    normalize_company_name,
    validate,
)


# Written out here rather than imported from contract_validator on purpose.
# Parametrizing over the implementation's own table would make the pair test
# pass by construction — the self-validating loop this contract layer exists to
# remove. Declared independently, dropping a pair from the implementation makes
# the expectation fail instead of silently shrinking the parametrization.
EXPECTED_CORPORATE_FORM_PAIRS = (
    ("inc", "incorporated"),
    ("corp", "corporation"),
    ("ltd", "limited"),
    ("co", "company"),
    ("ag", "aktiengesellschaft"),
)


# Forms documented as having no single-token expansion. Anything stripped that
# is not here or in a pair above is an undocumented addition.
EXPECTED_UNPAIRED_CORPORATE_FORMS = frozenset({"plc", "sa", "nv"})


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


def test_validator_rejects_bool_for_a_numeric_tuple_slot():
    """``NUM`` is a tuple of types, and every tuple carrying ``int`` inherits
    the same bool footgun. A fixture emitting ``true`` where a number belongs is
    drift, so the tuple branch has to refuse it exactly as the single-type
    branch does."""
    with pytest.raises(AssertionError, match="got bool"):
        validate({"foo": True}, {"foo": NUM}, "root")


def test_validator_rejects_bool_for_a_nullable_numeric_slot():
    """``(NUM, NULLABLE)`` unwraps to the tuple branch, so it must refuse bool
    too — otherwise the marker would be a way to smuggle one back in."""
    with pytest.raises(AssertionError, match="got bool"):
        validate({"foo": True}, {"foo": (NUM, NULLABLE)}, "root")


def test_validator_accepts_bool_when_the_tuple_names_bool():
    """The guard keys on the spec, not on the value: a field that genuinely may
    be a bool says so, and still passes."""
    validate({"foo": True}, {"foo": (bool, NULLABLE)}, "root")
    validate({"foo": False}, {"foo": (int, bool)}, "root")


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


def test_validator_accepts_null_for_nullable_field():
    # NULLABLE is the complement of OPTIONAL: null passes, absence does not.
    validate({"foo": None}, {"foo": (str, NULLABLE)}, "root")


def test_validator_accepts_typed_value_for_nullable_field():
    validate({"foo": ["a", "b"]}, {"foo": ([str], NULLABLE)}, "root")


def test_validator_rejects_missing_nullable_field():
    """A NULLABLE field must be PRESENT — that is the whole point of the marker.

    `analyze_portfolio._meta.invalid_fields` is null when every requested field
    name was valid; a response that drops the key entirely is real drift.
    """
    with pytest.raises(AssertionError, match="missing required field"):
        validate({}, {"foo": ([str], NULLABLE)}, "root")


def test_validator_rejects_wrong_type_for_nullable_field():
    with pytest.raises(AssertionError, match="expected list"):
        validate({"foo": "oops"}, {"foo": ([str], NULLABLE)}, "root")


def test_normalize_treats_legal_form_punctuation_as_the_same_company():
    """The pair that made the identity gate flag on its own reference capture."""
    assert normalize_company_name("Apple Inc") == normalize_company_name("Apple Inc.")
    assert normalize_company_name("Microsoft Corp") == normalize_company_name(
        "Microsoft Corporation"
    )
    assert normalize_company_name("APPLE  INC.") == normalize_company_name("Apple Inc")


def test_normalize_strips_repeatedly_until_stable():
    # One strip exposes the next: dropping "ltd" leaves a trailing comma.
    assert normalize_company_name("Samsung Electronics Co., Ltd.") == (
        normalize_company_name("Samsung Electronics Co")
    )


def test_normalize_strips_corporate_forms_token_wise_not_by_substring():
    assert normalize_company_name("Maytag") == "maytag"
    assert normalize_company_name("Saga plc") == "saga"


@pytest.mark.parametrize("abbreviation,expansion", EXPECTED_CORPORATE_FORM_PAIRS)
def test_normalize_folds_an_abbreviation_onto_its_expanded_form(abbreviation, expansion):
    """Both halves of every documented legal-form pair reduce to the same stem.

    A strip set holding only one half is a false MISMATCH generator: "Acme Ltd"
    folds to "acme" while "Acme Limited" stays "acme limited", and the identity
    gate then drops a real holding as a different company.

    Scope of this check: dropping either half from the implementation, or
    misspelling an expansion there. It cannot see an undocumented token added
    to the strip set — that direction is covered by the probe below.
    """
    abbreviated = normalize_company_name(f"Acme {abbreviation}")
    assert abbreviated == normalize_company_name(f"Acme {expansion}")
    assert abbreviated == "acme"


@pytest.mark.parametrize(
    "candidate",
    ["gmbh", "kk", "oyj", "spa", "pte", "llc", "holdings", "group"],
)
def test_normalize_leaves_undocumented_legal_forms_alone(candidate):
    """A token stripped without a documented expansion is a MISMATCH generator.

    The realistic way half a pair enters is a bare token appended to the
    unpaired set, which the pair parametrization never iterates. Probing
    through the public function keeps the expectation independent of the
    implementation's table.

    Scope of this check: the named candidates only. It is a sample, not a
    proof that the strip set equals the documented one.
    """
    documented = {
        token for pair in EXPECTED_CORPORATE_FORM_PAIRS for token in pair
    } | EXPECTED_UNPAIRED_CORPORATE_FORMS
    assert candidate not in documented, "probe candidate is itself documented"
    assert normalize_company_name(f"Acme {candidate}") == f"acme {candidate}"


def test_normalize_folds_dotted_abbreviations_like_their_bare_form():
    # The candidate token is matched with its own periods removed, so the
    # dotted rendering of a legal form is not read as part of the name.
    assert normalize_company_name("Acme S.A.") == normalize_company_name("Acme SA")
    assert normalize_company_name("Acme Co., Ltd.") == normalize_company_name("Acme")


def test_normalize_keeps_genuinely_different_companies_apart():
    assert normalize_company_name("Apple Inc") != normalize_company_name(
        "Apple Hospitality REIT"
    )


# ---------------------------------------------------------------------------
# names_match: the undecidable case must not read as a match
# ---------------------------------------------------------------------------


def test_two_contentless_names_do_not_compare_equal():
    """The fail-open this function exists to close.

    Both inputs are nothing but a corporate form, so both normalize to "".
    Comparing normalized forms with == reports a match between two different
    companies, in the one check whose job is catching a wrong-company mapping.
    """
    from contract_validator import names_match, normalize_company_name

    assert normalize_company_name("Inc.") == normalize_company_name("Ltd") == ""
    assert names_match("Inc.", "Ltd") is None


def test_one_contentless_side_is_undecidable_not_a_mismatch():
    """An empty side is missing evidence, not evidence of divergence.

    Returning False here would flag a genuine holding as a wrong-company
    mapping; returning None routes it to UNCHECKED, which is the disposition
    conventions section 2 requires when a comparison cannot be performed.
    """
    from contract_validator import names_match

    assert names_match("Acme Test Corp", "Inc.") is None
    assert names_match("Ltd", "Acme Test Corp") is None


def test_formatting_difference_still_matches():
    from contract_validator import names_match

    assert names_match("Acme Test Corp", "Acme Test Corp.") is True


def test_genuine_divergence_still_flags():
    from contract_validator import names_match

    assert names_match("Acme Test Corp", "Beta Holdings Trust") is False
