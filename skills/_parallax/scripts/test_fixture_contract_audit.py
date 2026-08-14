"""Audit-layer tests: the properties the three gates leave unpinned.

WHY A SEPARATE FILE. Each existing suite is honest about its own scope and
each one leaves a seam at its edge:

  * ``test_fixture_provenance.py`` drives gate 1's negative cases with STUB
    generators only. Every planted failure is a two-key dict, so the path
    "real ``gen_mock_fixtures.build_fixtures()`` output versus a tampered copy
    of the real tracked tree" is never executed. That path is the one the gate
    actually runs in CI, and a generator whose output could not be compared
    against a mutated real fixture would still pass every existing negative
    test.
  * ``test_fixture_precision.py`` reaches gate 2's CLI only through
    ``fp.main()`` with no arguments, after monkeypatching the module global.
    ``--root`` -- the flag the docstring says exists so a caller can point the
    gate at another tree -- is never passed. The docstring's own complaint is
    that a gate answering a question you did not ask is worse than one that
    refuses; nothing checks that it now answers the one you did.
  * The schema layer marks nearly every ``analyze_portfolio`` block OPTIONAL,
    so structural conformance passes against an empty ``result``. Nothing
    states which blocks the tracked fixture must actually carry, and nothing
    connects the ``fields=`` list a SKILL.md tells a model to send to the
    blocks the fixture returns.

Two conventions carried over from the suites above, because they are what make
a negative test falsifiable here:

  * Every planted violation is a LITERAL, never derived from the constant it is
    meant to trip. A plant built out of the implementation's own table moves
    with the table and can never fail for its stated reason.
  * Every test on real data has a twin driving the same helper with a planted
    input, so "this passes" and "this can fail" are separate observations.

Some tests below are HONESTY PINS in the sense ``test_fixture_precision.py``
uses the term: they assert that a known hole is still open. If one starts
failing, the hole was closed and the pin should be rewritten to assert the new
behaviour -- not deleted.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixture_precision as fp
import gen_mock_fixtures as gen
import test_fixture_provenance as prov
from contract_schemas import ANALYZE_PORTFOLIO_ENVELOPE_SCHEMA
from contract_validator import normalize_company_name, validate

REPO_ROOT = Path(__file__).resolve().parents[3]
MOCKS_DIR = Path(__file__).resolve().parent / "mcp_mocks"

# The block list the fixture ledger (mcp_mocks/README.md) publishes for
# analyze_portfolio, written out here rather than read from result.keys().
# Reading the payload would make the expectation whatever the payload happens
# to be, which is the self-validating loop this layer exists to remove.
DOCUMENTED_ANALYZE_PORTFOLIO_BLOCKS = frozenset({
    "_meta",
    "portfolio_parameters",
    "data_quality",
    "portfolio_summary",
    "performance_metrics",
    "drawdown_analysis",
    "portfolio_scores",
    "concentration_metrics",
    "company_contribution",
    "sector_contribution",
    "sector_allocation",
    "time_period_returns",
    "latest_holdings",
})


def _tracked(name: str) -> Any:
    return json.loads((MOCKS_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tracked_portfolio() -> dict:
    """The tracked FILE, read through the envelope exactly as a consumer must.

    Deliberately not ``gen.build_fixtures()``: gate 1 ties the two together,
    and a test that only ever reads the generator would go green on a tracked
    file that no longer exists.
    """
    return _tracked("analyze_portfolio")["result"]


# ==========================================================================
# Gate 1, driven with the REAL generator against a mutated REAL tree
# ==========================================================================

def _real_tree(tmp_path: Path) -> Path:
    """A byte-for-byte copy of the tracked fixture directory."""
    dest = tmp_path / "mcp_mocks"
    shutil.copytree(MOCKS_DIR, dest)
    return dest


def _rewrite(tree: Path, name: str, payload: Any) -> None:
    (tree / f"{name}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_real_generator_matches_an_untouched_copy_of_the_tracked_tree(tmp_path):
    """The control for every mutation below. Without it, a mutation test that
    fails proves only that something is wrong, not that the mutation caused it.
    """
    tree = _real_tree(tmp_path)
    assert prov.regeneration_errors(gen.build_fixtures(), tree, prov.MANAGED) == []


def test_real_generator_rejects_a_mutated_numeric_value(tmp_path):
    """Gate 1's own negative tests never run the real generator. This one does:
    one float in the real ``analyze_portfolio`` moved in its last place, which
    is the shape of a pasted capture -- same schema, same keys, other numbers.
    """
    tree = _real_tree(tmp_path)
    payload = json.loads((tree / "analyze_portfolio.json").read_text("utf-8"))
    payload["result"]["portfolio_summary"]["total_pl"] += 1e-6
    _rewrite(tree, "analyze_portfolio", payload)

    errors = prov.regeneration_errors(gen.build_fixtures(), tree, prov.MANAGED)
    assert len(errors) == 1
    assert errors[0].startswith("analyze_portfolio:")
    assert "does not match its regenerated form" in errors[0]


def test_real_generator_rejects_a_mutated_string_value(tmp_path):
    """The class gate 2 cannot see: an identity string swapped, no numeric
    change anywhere. Planted value is a synthetic sentinel, never a real name.
    """
    tree = _real_tree(tmp_path)
    payload = json.loads((tree / "get_company_info.json").read_text("utf-8"))
    payload["name"] = "zz-planted-sentinel"
    _rewrite(tree, "get_company_info", payload)

    errors = prov.regeneration_errors(gen.build_fixtures(), tree, prov.MANAGED)
    assert [e.split(":")[0] for e in errors] == ["get_company_info"]
    assert "zz-planted-sentinel" not in "\n".join(errors)


def test_real_generator_rejects_a_flattened_response_envelope(tmp_path):
    """The regression the ledger calls out by name: the ``{success, result}``
    wrapper dropped and the blocks stored bare. Every inner identity still
    holds, the precision budget is still clean, and only the access path
    breaks -- so gate 1 has to be the thing that catches it.
    """
    tree = _real_tree(tmp_path)
    payload = json.loads((tree / "analyze_portfolio.json").read_text("utf-8"))
    _rewrite(tree, "analyze_portfolio", payload["result"])

    errors = prov.regeneration_errors(gen.build_fixtures(), tree, prov.MANAGED)
    assert len(errors) == 1 and errors[0].startswith("analyze_portfolio:")


def test_real_generator_rejects_a_deleted_managed_fixture(tmp_path):
    tree = _real_tree(tmp_path)
    (tree / "get_score_analysis.json").unlink()

    errors = prov.regeneration_errors(gen.build_fixtures(), tree, prov.MANAGED)
    assert len(errors) == 1
    assert "no tracked get_score_analysis.json to compare against" in errors[0]


def test_real_generator_rejects_a_field_added_to_a_managed_fixture(tmp_path):
    """A live capture carries MORE fields than the generator models."""
    tree = _real_tree(tmp_path)
    payload = json.loads((tree / "get_company_info.json").read_text("utf-8"))
    payload["zz_planted_extra_field"] = 1
    _rewrite(tree, "get_company_info", payload)

    errors = prov.regeneration_errors(gen.build_fixtures(), tree, prov.MANAGED)
    assert len(errors) == 1 and errors[0].startswith("get_company_info:")


def test_mutating_an_unmanaged_fixture_is_invisible_to_gate_one(tmp_path):
    """HONESTY PIN. PRE_EXISTING and HAND_AUTHORED files are outside
    regeneration equality by construction, so gate 1 does not see an edit to
    one. Gate 2's precision budget is the only cover they have. If this starts
    failing, the fixture moved into MANAGED and the classification tables --
    not this test -- are what should be updated.
    """
    tree = _real_tree(tmp_path)
    payload = json.loads((tree / "get_telemetry.json").read_text("utf-8"))
    payload["regime_tag"] = "zz-planted-regime"
    _rewrite(tree, "get_telemetry", payload)

    assert prov.regeneration_errors(gen.build_fixtures(), tree, prov.MANAGED) == []


# ==========================================================================
# Gate 2: the --root CLI path
# ==========================================================================

def _write(tree: Path, name: str, payload: Any) -> Path:
    tree.mkdir(parents=True, exist_ok=True)
    path = tree / name
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def test_root_flag_scans_the_directory_it_was_given(tmp_path, capsys):
    """The docstring's stated reason for adding argument parsing: before it,
    ``--root elsewhere`` was accepted, ignored, and the DEFAULT tree scanned --
    reporting a clean result for a directory the caller never asked about.
    Planting the violation only in the alternate tree is what distinguishes
    "scanned the argument" from "scanned the default and agreed by luck".
    """
    planted = tmp_path / "elsewhere"
    _write(planted, "planted.json", {"mktcap": 3812345678901234})
    assert fp.main(["--root", str(planted)]) == 1
    assert "PRECISION" in capsys.readouterr().err


def test_root_flag_reports_clean_for_a_clean_alternate_tree(tmp_path, capsys):
    """The complement, and the one that makes the test above meaningful: the
    flag must not report a violation that lives somewhere else either."""
    clean = tmp_path / "clean"
    _write(clean, "authored.json", {"weight": 0.349378, "close": 189.42})
    assert fp.main(["--root", str(clean)]) == 0
    assert "clean" in capsys.readouterr().out


def test_root_flag_does_not_fall_back_to_the_default_tree(tmp_path, monkeypatch,
                                                          capsys):
    """Point the DEFAULT at a dirty tree and ``--root`` at a clean one. A gate
    that silently ignored its argument would fail here; the one that honours it
    passes. This is the false-assurance case written as an assertion."""
    dirty = tmp_path / "dirty"
    clean = tmp_path / "clean"
    _write(dirty, "planted.json", {"mktcap": 3812345678901234})
    _write(clean, "authored.json", {"score": 7.2})
    monkeypatch.setattr(fp, "MOCKS_DIR", dirty)
    monkeypatch.setattr(fp, "ALLOWLIST", {})

    assert fp.main(["--root", str(clean)]) == 0
    # ... and with no --root it reads the (dirty) default, so the flag is what
    # changed the answer rather than the tree being clean either way.
    assert fp.main([]) == 1


def test_root_flag_on_a_missing_directory_fails_rather_than_scanning_nothing(
        tmp_path, capsys):
    """An unreadable target must not read as clean. Exit 1, with the path
    named -- the path is a caller-supplied argument, not fixture content."""
    missing = tmp_path / "does-not-exist"
    assert fp.main(["--root", str(missing)]) == 1
    assert "not a directory" in capsys.readouterr().err


def test_root_flag_on_the_tracked_tree_agrees_with_the_default(capsys):
    """Both entry points, same tree, same verdict."""
    assert fp.main(["--root", str(MOCKS_DIR)]) == 0
    capsys.readouterr()
    assert fp.main([]) == 0


def test_root_flag_rejects_a_file_masquerading_as_a_directory(tmp_path, capsys):
    target = tmp_path / "one.json"
    target.write_text("{}\n", encoding="utf-8")
    assert fp.main(["--root", str(target)]) == 1
    assert "not a directory" in capsys.readouterr().err


# ==========================================================================
# Structural conformance is weaker than it looks
# ==========================================================================

def test_envelope_schema_accepts_an_empty_result(capsys):
    """HONESTY PIN. Every block under ``result`` is OPTIONAL, so a response
    that lost all thirteen of them still conforms. Schema conformance therefore
    proves the SHAPE of what is present and says nothing about what must be
    present -- which is why the block-presence test below exists as its own
    assertion rather than being folded into the conformance test.
    """
    validate({"success": True, "result": {}},
             ANALYZE_PORTFOLIO_ENVELOPE_SCHEMA, "planted")


def test_tracked_analyze_portfolio_carries_every_documented_block(tracked_portfolio):
    """The ledger's block list, asserted against the tracked file. Expectation
    is the module-level literal set, so dropping a block from the fixture fails
    here instead of shrinking the thing being compared."""
    assert set(tracked_portfolio) == DOCUMENTED_ANALYZE_PORTFOLIO_BLOCKS


def test_documented_block_check_fails_on_a_missing_block():
    """Twin for the test above, driven with a planted payload."""
    list_blocks = {"company_contribution", "sector_allocation",
                   "sector_contribution", "latest_holdings"}
    planted: dict[str, Any] = {
        name: ([] if name in list_blocks else {})
        for name in DOCUMENTED_ANALYZE_PORTFOLIO_BLOCKS
        if name != "company_contribution"}
    planted["_meta"] = {"fields_requested": [], "fields_returned": [],
                        "invalid_fields": None}
    assert set(planted) != DOCUMENTED_ANALYZE_PORTFOLIO_BLOCKS
    # ... and it still passes structural conformance, which is the point.
    validate({"success": True, "result": planted},
             ANALYZE_PORTFOLIO_ENVELOPE_SCHEMA, "planted")


# ==========================================================================
# The identity gate's preconditions, on the tracked fixture
# ==========================================================================
#
# conventions §2 tells a skill to match ``latest_holdings[].name`` and
# ``company_contribution[].name`` to ``get_company_info.name`` by the row's
# ``ric``. Both name fields are OPTIONAL in the schema, so a fixture that
# dropped them would conform, every value test would still pass, and the gate
# the skills describe would have nothing to read.


def identity_pairs(portfolio: dict, oracle: dict) -> dict[str, list[str]]:
    """Names the identity gate would compare for the oracle's RIC.

    Returns ``{"oracle": [...], "candidates": [...]}``. Injectable so the
    negative twins below drive the same lookup with planted payloads.
    """
    ric = oracle["symbol"]
    candidates = []
    for block in ("latest_holdings", "company_contribution"):
        for row in portfolio.get(block, []):
            if row.get("ric") == ric and "name" in row:
                candidates.append(row["name"])
    return {"oracle": [oracle["name"]], "candidates": candidates}


def test_every_holding_row_carries_the_name_the_gate_reads(tracked_portfolio):
    for block in ("latest_holdings", "company_contribution"):
        rows = tracked_portfolio[block]
        assert rows, f"{block} is empty; the identity gate has nothing to read"
        for row in rows:
            assert row.get("ric"), f"{block} row has no ric"
            assert row.get("name", "").strip(), (
                f"{block} row {row.get('ric')!r} has no name — conventions §2 "
                f"names this field as the gate's input")


def test_the_two_holding_blocks_describe_the_same_set_of_rics(tracked_portfolio):
    """Set equality, not order. Order is not a documented property of either
    block, so asserting it would encode an identity the API does not promise --
    but the two existing generator tests pair the blocks with ``zip``, and that
    pairing is only sound while the sets agree."""
    holdings = {row["ric"] for row in tracked_portfolio["latest_holdings"]}
    contribution = {row["ric"] for row in tracked_portfolio["company_contribution"]}
    assert holdings == contribution


def test_company_contribution_name_agrees_with_the_oracle(tracked_portfolio):
    """The field ``parallax-scenario-analysis`` reads at its 2a/2b gate.

    The existing cross-fixture test compares ``get_company_info`` against
    ``latest_holdings`` only, so the block the repaired gate actually reads was
    unchecked.
    """
    oracle = _tracked("get_company_info")
    pairs = identity_pairs(tracked_portfolio, oracle)
    assert len(pairs["candidates"]) == 2, (
        "the oracle's RIC must appear in BOTH holding blocks, or one of the "
        "two documented gate inputs is untested")
    for candidate in pairs["candidates"]:
        assert normalize_company_name(candidate) == normalize_company_name(
            pairs["oracle"][0])


def test_identity_pair_lookup_finds_nothing_for_an_absent_holding():
    """Twin: the UNCHECKED case, driven with a planted payload. An oracle whose
    RIC has no row anywhere yields no candidate at all -- there is nothing to
    compare, which is precisely the state both skills must record as UNCHECKED
    rather than as a pass."""
    portfolio = {"latest_holdings": [{"ric": "ZZAA.O", "name": "Zulu Alpha Corp"}],
                 "company_contribution": [{"ric": "ZZAA.O", "name": "Zulu Alpha Corp"}]}
    oracle = {"symbol": "ZZBB.O", "name": "Zulu Bravo Corp"}
    assert identity_pairs(portfolio, oracle)["candidates"] == []


def test_identity_pair_lookup_flags_a_genuine_divergence():
    """Twin: a wrong-company mapping must survive normalization."""
    portfolio = {"latest_holdings": [{"ric": "ZZAA.O", "name": "Zulu Alpha Corp"}],
                 "company_contribution": [
                     {"ric": "ZZAA.O", "name": "Zulu Alpha Hospitality Trust"}]}
    oracle = {"symbol": "ZZAA.O", "name": "Zulu Alpha Corp."}
    candidates = identity_pairs(portfolio, oracle)["candidates"]
    normalized = [normalize_company_name(c) for c in candidates]
    target = normalize_company_name(oracle["name"])
    assert normalized[0] == target, "punctuation-only difference must not flag"
    assert normalized[1] != target, "a different company must flag"


def test_a_row_without_a_name_is_not_offered_as_a_comparison():
    """A row present but nameless is the same UNCHECKED state as no row: the
    lookup must not hand back an empty string that then compares equal."""
    portfolio = {"latest_holdings": [{"ric": "ZZAA.O"}],
                 "company_contribution": [{"ric": "ZZAA.O", "name": "Zulu Alpha Corp"}]}
    oracle = {"symbol": "ZZAA.O", "name": "Zulu Alpha Corp"}
    assert identity_pairs(portfolio, oracle)["candidates"] == ["Zulu Alpha Corp"]


@pytest.mark.parametrize("blank", ["", "   ", "Inc", "Corp.", "Ltd"])
def test_normalization_folds_a_contentless_name_to_the_empty_string(blank):
    """HONESTY PIN, and the reason the UNCHECKED rule cannot be implemented as
    a plain equality over normalized names.

    ``normalize_company_name`` strips the corporate-form token, so a name that
    is nothing BUT a corporate form -- and a name that is absent or blank --
    all fold to ``""``. Two such sides therefore compare EQUAL, which a naive
    gate would record as a match: the "missing comparison treated as a pass"
    failure, arriving through the normalizer rather than through the lookup.

    Pinned, not fixed: the guard belongs in the normalizer's callers or in the
    normalizer itself, and this file is test-only. See the report accompanying
    this suite.
    """
    assert normalize_company_name(blank) == ""
    assert normalize_company_name(blank) == normalize_company_name("")


def test_a_real_name_never_folds_to_the_empty_string(tracked_portfolio):
    """Bounds the pin above: on the tracked fixture no legitimate name is at
    risk of the collapse, so the hole is reachable only through absent or
    contentless input."""
    oracle = _tracked("get_company_info")
    names = [oracle["name"]]
    for block in ("latest_holdings", "company_contribution"):
        names += [row["name"] for row in tracked_portfolio[block]]
    for name in names:
        assert normalize_company_name(name) != ""


# ==========================================================================
# SKILL.md instructions versus the response the fixture models
# ==========================================================================

FIELDS_CALL_RE = re.compile(r"`fields=\[(?P<body>[^\]]*)\]`")
CIO_SKILL = REPO_ROOT / "skills" / "parallax-cio-letter-prep" / "SKILL.md"


def declared_fields(markdown: str) -> list[str]:
    """Every field name inside a ``fields=[...]`` literal in a SKILL.md.

    This is the only mechanical link between what an instruction tells a model
    to request and what the contract layer models. Injectable so the twin below
    can drive it with planted prose.
    """
    names: list[str] = []
    for match in FIELDS_CALL_RE.finditer(markdown):
        names += re.findall(r'"([a-z_]+)"', match.group("body"))
    return names


def test_cio_letter_prep_requests_only_blocks_the_response_carries(tracked_portfolio):
    """A renamed block is the failure this catches. ``concentration`` was
    renamed to ``concentration_metrics`` once already; an instruction still
    naming the old key would send a field the server rejects, land it in
    ``_meta.invalid_fields``, and silently lose the block.
    """
    requested = declared_fields(CIO_SKILL.read_text(encoding="utf-8"))
    assert requested, "no fields=[...] literal found — the parser has gone stale"
    returned = set(_tracked("analyze_portfolio")["result"]["_meta"]["fields_returned"])
    for name in requested:
        assert name in tracked_portfolio, (
            f"SKILL.md requests {name!r}, which the modelled response does not "
            f"carry as a block")
        assert name in returned, (
            f"SKILL.md requests {name!r}, absent from _meta.fields_returned")


def test_requested_field_check_fails_on_a_planted_stale_block_name(tracked_portfolio):
    """Twin. The pre-rename spelling, planted in prose, must not resolve."""
    planted = 'call with `fields=["portfolio_summary","concentration"]` and read it'
    requested = declared_fields(planted)
    assert requested == ["portfolio_summary", "concentration"]
    assert requested[0] in tracked_portfolio
    assert requested[1] not in tracked_portfolio


def test_the_fixture_models_a_wider_request_than_the_skill_makes(tracked_portfolio):
    """HONESTY PIN on a real divergence, asserted as containment rather than
    equality because closing it would mean editing the fixture or the SKILL.md,
    and both are out of scope for a test-only change.

    ``_meta.fields_requested`` carries two blocks the cio-letter-prep
    instruction does not ask for. The fixture therefore models a response
    slightly richer than the one that skill receives, so a consumer reading a
    block outside the intersection would be exercised by the tests and absent
    at run time.
    """
    skill_fields = set(declared_fields(CIO_SKILL.read_text(encoding="utf-8")))
    fixture_fields = set(
        _tracked("analyze_portfolio")["result"]["_meta"]["fields_requested"])
    assert skill_fields < fixture_fields
    assert fixture_fields - skill_fields == {"portfolio_parameters", "data_quality"}


# ==========================================================================
# The documented conversion identity, on the tracked fixture
# ==========================================================================

def test_contribution_pct_is_a_share_of_total_pl_on_the_tracked_fixture(
        tracked_portfolio):
    """cio-letter-prep's SKILL.md instructs the reader to recompute this
    identity against whatever the fixture currently holds. Nothing did.

    The divisor is asserted non-zero first, so a flat period surfaces as a
    stated precondition rather than as a ZeroDivisionError inside the loop.
    """
    total_pl = tracked_portfolio["portfolio_summary"]["total_pl"]
    assert total_pl != 0, (
        "the fixture's period is flat, so contribution_pct has no defined "
        "value and this identity cannot be checked against it")
    for row in tracked_portfolio["company_contribution"]:
        assert abs(row["contribution_pct"] - row["total_pl"] / total_pl) < 1e-6


def test_the_fixture_period_is_a_winning_one_so_the_sign_trap_is_unexercised(
        tracked_portfolio):
    """HONESTY PIN naming a gap in the DATA, not in a test.

    The SKILL.md sign rule says that over a LOSING period every losing holding
    carries a POSITIVE ``contribution_pct`` (negative over negative), so ranking
    on the raw field inverts the contributors and detractors tables. The tracked
    fixture's period is a winning one, so no assertion anywhere can exercise
    that inversion: on this data the losing holding's raw sign is already
    negative and the wrong code and the right code agree.

    If this pin ever fails, the fixture gained a losing period and the sign rule
    became testable -- write the test at that point.
    """
    summary = tracked_portfolio["portfolio_summary"]
    assert summary["total_pl"] > 0 and summary["total_return"] > 0
    losers = [r for r in tracked_portfolio["company_contribution"]
              if r["total_pl"] < 0]
    assert losers, "no losing holding at all"
    for row in losers:
        assert row["contribution_pct"] < 0, (
            "a losing holding already carries a negative contribution_pct here, "
            "which is the winning-period case")


# ==========================================================================
# Cross-fixture agreement, on the tracked FILES
# ==========================================================================

def test_tracked_fixtures_describe_one_issuer_consistently(tracked_portfolio):
    """The generator-side test asserts this over ``build_fixtures()`` output.
    Consumers load the FILES through ``load_mock``, so the same statement is
    made here against what is on disk."""
    oracle = _tracked("get_company_info")
    score = _tracked("get_score_analysis")
    assert score["symbol"] == oracle["symbol"]

    holding = next(h for h in tracked_portfolio["latest_holdings"]
                   if h["ric"] == oracle["symbol"])
    assert holding["sector"] == oracle["sector"]
    assert holding["industry"] == oracle["industry"]
    assert normalize_company_name(holding["name"]) == normalize_company_name(
        oracle["name"])


def test_cross_fixture_check_fails_on_a_planted_disagreement():
    """Twin, with a planted pair rather than the tracked one."""
    portfolio = {"latest_holdings": [
        {"ric": "ZZAA.O", "name": "Zulu Alpha Corp", "sector": "Energy",
         "industry": "Refining"}]}
    oracle = {"symbol": "ZZAA.O", "name": "Zulu Alpha Corp",
              "sector": "Financials", "industry": "Refining"}
    holding = portfolio["latest_holdings"][0]
    assert holding["industry"] == oracle["industry"]
    assert holding["sector"] != oracle["sector"]
