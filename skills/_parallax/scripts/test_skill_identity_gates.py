"""Doc-conformance for the two repaired identity gates.

WHAT CAN AND CANNOT BE TESTED HERE, STATED PLAINLY. The identity gates in
``parallax-cio-letter-prep`` and ``parallax-scenario-analysis`` are prose in a
SKILL.md, consumed by a model at run time. There is no function to call, no
branch to cover and no return value to assert. The only executable artefact the
repair produced is ``contract_validator.normalize_company_name``, which is the
comparison primitive and not the gate.

So this file checks the one thing that IS mechanically checkable about a prose
gate: that the instruction text still says the things the repair put there, and
no longer says the thing it removed. That is weaker than a behavioural test and
should be read as such -- it catches a revert, a bad merge, a copy that drifts
out of sync with its plugin mirror. It cannot catch a model ignoring a rule it
was correctly given.

BRITTLENESS. String assertions over prose go stale when the prose is reworded
in good faith. The checks below are kept to short phrases that carry the rule
rather than the sentence around them, and each one names the rule it stands for
so a reword can be made deliberately rather than by defeating a test.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_bundle as bb
from contract_validator import normalize_company_name

REPO_ROOT = Path(__file__).resolve().parents[3]

# The two skills whose gate was repaired. Both must state the UNCHECKED rule and
# neither may still instruct reading an identity field that endpoint does not
# return.
GATED_SKILLS = ("parallax-cio-letter-prep", "parallax-scenario-analysis")

# "a missing comparison is never a pass", in the two phrasings the repair used.
# Matching the rule rather than the sentence keeps an honest reword cheap.
NO_PASS_ON_MISSING = re.compile(
    r"(?:rather than treating|never treat)[^.]{0,80}\bpass\b", re.I)

# ``analyze_portfolio`` returns no peer rollup and no ``target_company``. An
# instruction naming that field in one of these skills is the dead gate: the
# check reads nothing and therefore passes on every row.
DEAD_IDENTITY_FIELD = "target_company"

# The fields the endpoint does carry, per conventions §2.
LIVE_IDENTITY_BLOCKS = ("latest_holdings", "company_contribution")


def gate_errors(markdown: str, label: str) -> list[str]:
    """Rule violations in one skill's instruction text.

    Injectable so the negative twins below drive the same checks with planted
    prose rather than re-reading the real files and agreeing with them.
    """
    errors = []
    if "UNCHECKED" not in markdown:
        errors.append(
            f"{label}: no UNCHECKED state — an absent comparison has nowhere "
            f"to be recorded except as a pass")
    if not NO_PASS_ON_MISSING.search(markdown):
        errors.append(
            f"{label}: the rule forbidding a missing comparison from counting "
            f"as a pass is not stated")
    if DEAD_IDENTITY_FIELD in markdown:
        errors.append(
            f"{label}: still instructs reading {DEAD_IDENTITY_FIELD!r} from a "
            f"response that does not carry it — the check cannot execute")
    if not any(block in markdown for block in LIVE_IDENTITY_BLOCKS):
        errors.append(
            f"{label}: names no block that actually carries a per-holding name")
    return errors


def _skill(name: str, mirror: bool = False) -> str:
    base = REPO_ROOT / ("plugin/skills" if mirror else "skills")
    return (base / name / "SKILL.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# The real instruction text
# --------------------------------------------------------------------------

@pytest.mark.parametrize("skill", GATED_SKILLS)
def test_repaired_gate_states_its_rules(skill):
    assert gate_errors(_skill(skill), skill) == []


@pytest.mark.parametrize("skill", GATED_SKILLS)
def test_repaired_gate_matches_names_by_ric_not_by_position(skill):
    """The comparison is per holding, keyed on the row's ``ric``. A gate that
    compared a comma-joined batch, or paired rows positionally, would confirm
    nothing about any individual holding."""
    text = _skill(skill)
    assert "ric" in text.lower()
    assert "get_company_info" in text


def test_conventions_carries_the_per_tool_identity_table():
    """The rules live in the shared conventions file so every skill loads them,
    rather than in a per-skill file whose load trigger cannot fire in the
    failure case."""
    text = (REPO_ROOT / "skills/_parallax/parallax-conventions.md").read_text(
        encoding="utf-8")
    assert gate_errors(text, "conventions") == [
        # conventions legitimately names the dead field: it is the CORRECT
        # identity field for get_peer_snapshot, and the table's whole purpose is
        # that the field differs per tool. The rule is that the two consuming
        # skills must not read it from analyze_portfolio, not that the word is
        # banned repo-wide.
        "conventions: still instructs reading 'target_company' from a response "
        "that does not carry it — the check cannot execute",
    ]
    assert "no top-level identity field and no peer rollup" in text
    assert "normalize_company_name" in text


def test_normalization_rule_and_its_executable_statement_stay_together():
    """conventions §2 step 2 names ``contract_validator.normalize_company_name``
    as the executable statement of the fold. If the function is renamed, moved
    or hollowed out the citation goes stale silently, so the cited module is
    imported and CALLED here rather than read: the citation is only worth
    anything if the thing it points at still folds the pair the rule promises
    it folds."""
    text = (REPO_ROOT / "skills/_parallax/parallax-conventions.md").read_text(
        encoding="utf-8")
    assert "_parallax/scripts/contract_validator.py" in text
    assert callable(normalize_company_name)
    assert (normalize_company_name("Apple Inc")
            == normalize_company_name("Apple Inc."))
    assert (normalize_company_name("Siemens Aktiengesellschaft")
            == normalize_company_name("Siemens AG"))
    assert (normalize_company_name("Acme Holdings")
            != normalize_company_name("Beta Holdings"))


# --------------------------------------------------------------------------
# Negative twins: the checks must fail on prose that lost the rule
# --------------------------------------------------------------------------

def test_gate_check_fails_when_the_unchecked_state_is_missing():
    planted = ("Compare `company_contribution[].name` against "
               "`get_company_info.name` for the same `ric`. Flag mismatches.")
    errors = gate_errors(planted, "planted")
    assert any("no UNCHECKED state" in e for e in errors)


def test_gate_check_fails_when_a_missing_comparison_may_count_as_a_pass():
    """The exact regression the repair was for: an UNCHECKED label present, but
    no rule saying it is not a pass."""
    planted = ("Compare `company_contribution[].name` against "
               "`get_company_info.name`. Holdings with no row are UNCHECKED.")
    errors = gate_errors(planted, "planted")
    assert errors == [
        "planted: the rule forbidding a missing comparison from counting as a "
        "pass is not stated",
    ]


def test_gate_check_fails_on_the_dead_identity_field():
    planted = ("Cross-validate the `target_company` field surfaced in the "
               "`analyze_portfolio` peer rollup. UNCHECKED holdings are listed "
               "rather than treating a missing comparison as a pass. "
               "See `company_contribution`.")
    errors = gate_errors(planted, "planted")
    assert errors == [
        "planted: still instructs reading 'target_company' from a response that "
        "does not carry it — the check cannot execute",
    ]


def test_gate_check_fails_when_no_real_identity_block_is_named():
    planted = ("Holdings with no name pair are UNCHECKED and surfaced as a "
               "coverage gap rather than treating a missing comparison as a "
               "pass.")
    errors = gate_errors(planted, "planted")
    assert any("names no block" in e for e in errors)


def test_repaired_text_passes_the_same_checks_a_planted_regression_fails():
    """Both directions through one helper, so the positive result above is not
    just a helper that returns [] for everything."""
    assert gate_errors(_skill("parallax-scenario-analysis"), "real") == []
    assert gate_errors("Cross-validate names.", "planted") != []


# --------------------------------------------------------------------------
# The plugin mirror
# --------------------------------------------------------------------------

def test_bundled_gate_mirror_carries_the_same_rules():
    """``plugin/`` is generated output. A repair applied to ``skills/`` and not
    rebuilt ships the old gate to every plugin user."""
    assert gate_errors(_skill("parallax-scenario-analysis", mirror=True),
                       "plugin mirror") == []


def test_the_mirror_check_covers_every_gated_skill_that_is_bundled():
    """Scope, asserted rather than assumed. ``parallax-cio-letter-prep`` is not
    in the plugin's skill list, so it has no mirror to check -- and if it is
    ever added, this fails and the mirror test above must grow to cover it."""
    bundled = [name for name in GATED_SKILLS if name in bb.PLUGIN_SKILLS]
    assert bundled == ["parallax-scenario-analysis"]
    assert not (REPO_ROOT / "plugin/skills/parallax-cio-letter-prep").exists()
