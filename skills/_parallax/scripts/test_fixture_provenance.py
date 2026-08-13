"""Fixture provenance gate (gate 1) — regenerate and compare, byte for byte.

THE TEST IS PROVENANCE, NOT IDENTITY. ``AAPL.O`` with invented numbers is benign
and already exists throughout main. A *renamed* issuer carrying an API-emitted
value is not. "Is this a real company" is not mechanically checkable; "did a
machine emit this number" largely is. So this gate never looks at tickers, names
or plausibility. It asks one question of every managed fixture:

    can a seeded generator reproduce this file exactly?

If yes, every byte in it came from code in this repo that anyone can read. If no
-- a pasted live capture, a hand-tweak, a re-run against the live API -- it fails
immediately, and it fails on values a precision heuristic cannot see: a
``recommendation`` string, a distinctive ``industry`` label, a real score on a
real date, a market cap that happens to be round.

This is the strong gate. ``fixture_precision.py`` (gate 2) is a heuristic
backstop for the fixtures NOT under regeneration equality -- those in
HAND_AUTHORED and PRE_EXISTING. Every fixture moved into MANAGED converts a
heuristic into a proof, which is why MANAGED should grow where it honestly can.

THREE CATEGORIES, ONE UNION. Every ``.json`` in ``mcp_mocks/`` must appear in
exactly one of MANAGED, HAND_AUTHORED or PRE_EXISTING, and the union must equal
the directory listing. The categories differ in what they claim:

  * MANAGED       -- regenerable byte-exact from the seeded generator. Proof.
  * HAND_AUTHORED -- deliberately not regenerable (it models a failure mode
                     with no generator to run against). Reason mandatory.
  * PRE_EXISTING  -- authored before the generator and before the live
                     captures; outside the generator's scope. Reason mandatory.

The third category is a classification, NOT a loophole. A fixture nobody has
classified still belongs to none of them and still fails -- which is the move
that committed the live captures in the first place.

GENERATOR CONTRACT. ``gen_mock_fixtures.py`` exposes::

    build_fixtures() -> dict[str, Any]

mapping fixture basename (no ``.json``) to the parsed fixture object, built from
a fixed seed with no network access. The keys must equal MANAGED exactly.

The generator has landed, so the regeneration tests below RUN rather than skip.
They still skip if the module is absent -- but a module that is present and
broken raises, because the window in which the generator is half-written is
exactly the window in which a silent skip is most dangerous.

WHAT "BYTE-EXACT" MEANS HERE. Both sides are re-serialised through ``canonical``
before comparison, so indentation and key order cannot fail the gate. Formatting
is not provenance, and a gate that failed on a two-space diff would train people
to regenerate instead of investigate. Values, types, structure and float
round-trip are all exact.
"""
import json
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

MOCKS_DIR = Path(__file__).resolve().parent / "mcp_mocks"

# Reproducible from gen_mock_fixtures.build_fixtures(). Grow this set.
#
# Scoped to the three fixtures that were ever rebuilt from live API captures --
# the actual leak -- plus the error-envelope companion the generator emits
# alongside analyze_portfolio. Regenerating the other six would churn
# known-clean files that predate the incident, for no provenance gain and a real
# chance of breaking consumers, so they sit in PRE_EXISTING below.
MANAGED = {
    "analyze_portfolio",
    "analyze_portfolio_credit_exhausted",
    "get_company_info",
    "get_score_analysis",
}

# name -> why regeneration equality cannot cover it. A reason is mandatory: it is
# the record of a deliberate decision to fall back to the weaker gate.
HAND_AUTHORED = {
    "check_portfolio_redundancy_silent_fail":
        "Models a documented empty-payload silent failure that the live endpoint "
        "emits only for sector-concentrated portfolios. The shape is authored "
        "from the failure description in mcp_mocks/README.md, not produced by a "
        "generator, so there is nothing to regenerate against. Covered by the "
        "gate 2 precision budget instead.",
}

# name -> why this fixture is outside the generator's scope. A reason is
# mandatory here for the same purpose it is in HAND_AUTHORED: an unclassified
# fixture must never become classifiable by accident.
#
# These are authored fixtures that predate the generator and predate the live
# captures. They were already public on main, carry no live provenance, and were
# never touched by the incident. Teaching the generator to emit them byte-exact
# would mean transcribing their current contents into Python -- which produces a
# regeneration test that passes by construction and proves nothing. The honest
# classification is that they are authored, and gate 2's precision budget is
# what covers them, exactly as it covers HAND_AUTHORED.
#
# This is not a permanent parking space. Any of these that acquires a real
# derivation should move into MANAGED.
_PRE_EXISTING_REASON = (
    "Authored fixture predating the generator; no live provenance -- it was "
    "already public on main before the live captures landed and was not one of "
    "the three files they touched. Covered by the gate 2 precision budget.")

PRE_EXISTING = {
    "check_portfolio_redundancy": _PRE_EXISTING_REASON,
    "export_price_series": _PRE_EXISTING_REASON,
    "get_assessment": _PRE_EXISTING_REASON,
    "get_news_synthesis": _PRE_EXISTING_REASON,
    "get_telemetry": _PRE_EXISTING_REASON,
    "macro_analyst": _PRE_EXISTING_REASON,
}


def canonical(payload: Any) -> bytes:
    """Deterministic serialisation of a parsed fixture.

    ``sort_keys`` normalises key order and ``allow_nan=False`` rejects the
    non-JSON floats a naive capture-and-dump can produce. Float repr round-trips
    exactly, so a value differing in the last bit is a byte difference here."""
    return (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True,
                       allow_nan=False) + "\n").encode("utf-8")


def tracked_fixtures(mocks_dir: Path | None = None) -> set[str]:
    base = MOCKS_DIR if mocks_dir is None else mocks_dir
    return {path.stem for path in base.glob("*.json")}


def classification_errors(mocks_dir: Path | None = None,
                          managed: set[str] | None = None,
                          hand_authored: dict[str, str] | None = None,
                          pre_existing: dict[str, str] | None = None,
                          ) -> list[str]:
    """Every tracked fixture must be classified, and classified exactly once.

    Three categories, and the union across ALL of them must equal the directory
    listing. Adding the third category does not widen the escape hatch: a newly
    dropped fixture still belongs to none of them and still fails here."""
    managed = MANAGED if managed is None else managed
    hand_authored = HAND_AUTHORED if hand_authored is None else hand_authored
    pre_existing = PRE_EXISTING if pre_existing is None else pre_existing
    on_disk = tracked_fixtures(mocks_dir)
    reasoned = {"HAND_AUTHORED": hand_authored, "PRE_EXISTING": pre_existing}
    declared = managed | set(hand_authored) | set(pre_existing)

    errors = []
    for name in sorted(on_disk - declared):
        errors.append(
            f"{name}.json is not classified — add it to MANAGED (preferred: "
            f"teach gen_mock_fixtures.build_fixtures() to produce it), or to "
            f"HAND_AUTHORED or PRE_EXISTING with a written reason")
    for name in sorted(declared - on_disk):
        errors.append(
            f"{name} is classified but no {name}.json exists — remove the "
            f"stale entry")
    # Every pairing, so a fixture cannot hide in two categories at once.
    for label, table in sorted(reasoned.items()):
        for name in sorted(managed & set(table)):
            errors.append(f"{name} is in both MANAGED and {label}")
    for name in sorted(set(hand_authored) & set(pre_existing)):
        errors.append(f"{name} is in both HAND_AUTHORED and PRE_EXISTING")
    for label, table in sorted(reasoned.items()):
        for name, reason in sorted(table.items()):
            if not (reason or "").strip():
                errors.append(f"{name} is {label} with no reason given")
    return errors


def regeneration_errors(generated: dict[str, Any],
                        mocks_dir: Path | None = None,
                        managed: set[str] | None = None) -> list[str]:
    """Compare each managed fixture against its regenerated counterpart.

    Reports the fixture name and nothing else. A diff of the offending values
    would print the captured payload into CI logs, which is the leak restated."""
    base = MOCKS_DIR if mocks_dir is None else mocks_dir
    managed = MANAGED if managed is None else managed

    errors = []
    missing = sorted(managed - set(generated))
    for name in missing:
        errors.append(f"{name}: generator produced no fixture under this name")
    extra = sorted(set(generated) - managed)
    for name in extra:
        errors.append(f"{name}: generator produced a fixture that is not in MANAGED")

    for name in sorted(managed & set(generated)):
        path = base / f"{name}.json"
        if not path.is_file():
            errors.append(f"{name}: no tracked {name}.json to compare against")
            continue
        try:
            tracked = canonical(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: tracked fixture unreadable ({type(exc).__name__})")
            continue
        try:
            rebuilt = canonical(generated[name])
        except (TypeError, ValueError) as exc:
            errors.append(f"{name}: generated fixture is not serialisable "
                          f"({type(exc).__name__})")
            continue
        if rebuilt != tracked:
            errors.append(
                f"{name}: tracked fixture does not match its regenerated form — "
                f"it was not produced by gen_mock_fixtures.py. If this is a live "
                f"API capture, do not commit it; if the generator changed, "
                f"regenerate and commit the generator change with it")
    return errors


def load_generator() -> tuple[Callable[[], dict[str, Any]] | None, str | None]:
    """Returns (build_fixtures, skip_reason).

    Absence of the module is a skip. A module that is PRESENT but broken --
    syntax error, bad import, wrong signature at call time -- must raise, not
    skip: the generator is under active development and a silently-skipped gate
    during exactly that window is how the leak got in."""
    try:
        import gen_mock_fixtures  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        if exc.name != "gen_mock_fixtures":
            raise
        return None, ("gen_mock_fixtures.py is not present in this checkout — "
                      "fixture regeneration is UNVERIFIED; only the "
                      "classification and precision gates are active")
    builder = getattr(gen_mock_fixtures, "build_fixtures", None)
    if not callable(builder):
        return None, ("gen_mock_fixtures.py exists but exposes no callable "
                      "build_fixtures() — see this module's docstring for the "
                      "generator contract; regeneration is UNVERIFIED")
    return builder, None


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------

def test_every_tracked_fixture_is_classified():
    """Runs with or without the generator. A newly dropped fixture -- the exact
    move that committed the live captures -- fails here until someone states
    where it came from."""
    errors = classification_errors()
    assert errors == [], "\n".join(errors)


def test_no_fixture_hides_below_the_top_level():
    """Classification is keyed on the file STEM, so it deliberately stays flat --
    nesting would let mcp_mocks/a/x.json and mcp_mocks/b/x.json collide on one
    MANAGED entry. The cost of that choice is that a nested file would be
    invisible to classification, which is exactly how an unclassified capture
    would hide. So nesting is forbidden outright rather than half-handled."""
    nested = sorted(p.relative_to(MOCKS_DIR).as_posix()
                    for p in MOCKS_DIR.rglob("*.json")
                    if p.parent != MOCKS_DIR)
    assert nested == [], (
        "fixtures below the top level are not classified by this gate — move "
        "them to mcp_mocks/ and add them to MANAGED or HAND_AUTHORED:\n" +
        "\n".join(nested))


def test_nesting_check_fails_on_a_planted_subdirectory(tmp_path):
    """Same check, driven with a planted tree so it is shown to fail."""
    _fake_tracked(tmp_path, "known", {"a": 1})
    (tmp_path / "new_endpoint").mkdir()
    _fake_tracked(tmp_path / "new_endpoint", "capture", {"a": 1})
    nested = sorted(p.relative_to(tmp_path).as_posix()
                    for p in tmp_path.rglob("*.json") if p.parent != tmp_path)
    assert nested == ["new_endpoint/capture.json"]
    # and the flat classification really is blind to it, which is why the
    # nesting check has to exist as its own assertion
    assert classification_errors(tmp_path, {"known"}, {}, {}) == []


def test_classification_covers_a_non_empty_directory():
    """Guards against a vacuous pass if mcp_mocks/ is renamed or emptied."""
    assert tracked_fixtures(), "no fixtures found; the provenance gate is vacuous"
    assert MANAGED, "MANAGED is empty; nothing is under regeneration equality"


def test_managed_fixtures_regenerate_byte_exact():
    builder, reason = load_generator()
    if builder is None:
        pytest.skip(reason)
    errors = regeneration_errors(builder())
    assert errors == [], "\n".join(errors)


def test_generator_produces_exactly_the_managed_set():
    """Covered inside regeneration_errors too, but asserted separately so the
    failure reads as a classification problem rather than a leak."""
    builder, reason = load_generator()
    if builder is None:
        pytest.skip(reason)
    assert set(builder()) == MANAGED


# --------------------------------------------------------------------------
# Negative cases: the gate must fail when it should
# --------------------------------------------------------------------------
#
# These drive the comparison helpers directly with planted inputs rather than
# with the real fixture set. A negative test that walked MANAGED and the real
# mcp_mocks/ would be re-running the implementation against its own inputs and
# could only ever agree with it.

def _fake_tracked(mocks: Path, name: str, payload: Any) -> None:
    mocks.mkdir(parents=True, exist_ok=True)
    (mocks / f"{name}.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_faithful_generator_passes(tmp_path):
    payload = {"symbol": "TESTCO.X", "score": 7.2, "as_of": "2026-01-05"}
    _fake_tracked(tmp_path, "widget", payload)
    errors = regeneration_errors({"widget": payload}, tmp_path, {"widget"})
    assert errors == []


def test_tampered_value_fails(tmp_path):
    """One float changed in the last place. This is the shape of a pasted live
    capture: same schema, same keys, different numbers."""
    _fake_tracked(tmp_path, "widget", {"symbol": "TESTCO.X", "score": 7.2})
    errors = regeneration_errors(
        {"widget": {"symbol": "TESTCO.X", "score": 7.2000000001}},
        tmp_path, {"widget"})
    assert len(errors) == 1 and errors[0].startswith("widget:")


def test_tampered_string_fails(tmp_path):
    """The class gate 2 cannot see at all: a recommendation string swapped for
    the live one, with no numeric change anywhere."""
    _fake_tracked(tmp_path, "widget", {"recommendation": "PLACEHOLDER"})
    errors = regeneration_errors(
        {"widget": {"recommendation": "OVERWEIGHT"}}, tmp_path, {"widget"})
    assert len(errors) == 1 and errors[0].startswith("widget:")


def test_added_field_fails(tmp_path):
    """A live capture usually carries MORE fields than the generator models --
    the identity fields nobody meant to commit."""
    _fake_tracked(tmp_path, "widget", {"symbol": "TESTCO.X", "numshrs": 15728003241})
    errors = regeneration_errors(
        {"widget": {"symbol": "TESTCO.X"}}, tmp_path, {"widget"})
    assert len(errors) == 1 and errors[0].startswith("widget:")


def test_round_number_leak_that_gate_two_misses_still_fails_here(tmp_path):
    """gate 2 passes a large round integer by construction (see
    test_large_round_integers_slip_through_as_documented). Gate 1 does not."""
    _fake_tracked(tmp_path, "widget", {"mktcap": 3810000000000})
    errors = regeneration_errors(
        {"widget": {"mktcap": 1000}}, tmp_path, {"widget"})
    assert len(errors) == 1


def test_reordered_keys_and_reindented_file_still_pass(tmp_path):
    """Formatting is not provenance."""
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "widget.json").write_text(
        '{"b": 2,\n    "a": 1}\n', encoding="utf-8")
    errors = regeneration_errors({"widget": {"a": 1, "b": 2}}, tmp_path, {"widget"})
    assert errors == []


def test_failure_message_does_not_echo_the_payload(tmp_path):
    """Same rule as the term scanner: naming the value to prove it is there
    publishes it."""
    _fake_tracked(tmp_path, "widget", {"industry": "zz-distinctive-sentinel"})
    errors = regeneration_errors(
        {"widget": {"industry": "placeholder"}}, tmp_path, {"widget"})
    assert errors
    assert "zz-distinctive-sentinel" not in "\n".join(errors)


def test_generator_missing_a_managed_fixture_fails(tmp_path):
    _fake_tracked(tmp_path, "widget", {"a": 1})
    errors = regeneration_errors({}, tmp_path, {"widget"})
    assert len(errors) == 1 and "produced no fixture" in errors[0]


def test_generator_emitting_an_unmanaged_fixture_fails(tmp_path):
    _fake_tracked(tmp_path, "widget", {"a": 1})
    errors = regeneration_errors(
        {"widget": {"a": 1}, "stowaway": {"a": 1}}, tmp_path, {"widget"})
    assert len(errors) == 1 and "not in MANAGED" in errors[0]


def test_unclassified_fixture_fails(tmp_path):
    """The newly-dropped-file case, driven with a planted directory."""
    _fake_tracked(tmp_path, "known", {"a": 1})
    _fake_tracked(tmp_path, "dropped_in", {"a": 1})
    errors = classification_errors(tmp_path, {"known"}, {}, {})
    assert len(errors) == 1 and errors[0].startswith("dropped_in.json is not classified")


def test_classification_of_a_nonexistent_fixture_fails(tmp_path):
    _fake_tracked(tmp_path, "known", {"a": 1})
    errors = classification_errors(tmp_path, {"known", "ghost"}, {}, {})
    assert len(errors) == 1 and "no ghost.json exists" in errors[0]


def test_double_classification_fails(tmp_path):
    _fake_tracked(tmp_path, "known", {"a": 1})
    errors = classification_errors(tmp_path, {"known"}, {"known": "a reason"}, {})
    assert any("both MANAGED and HAND_AUTHORED" in e for e in errors)


def test_hand_authored_without_a_reason_fails(tmp_path):
    _fake_tracked(tmp_path, "known", {"a": 1})
    errors = classification_errors(tmp_path, set(), {"known": "   "}, {})
    assert len(errors) == 1 and "no reason given" in errors[0]


def test_pre_existing_without_a_reason_fails(tmp_path):
    """Same rule as HAND_AUTHORED. A category you can join without stating why
    is an escape hatch, not a classification."""
    _fake_tracked(tmp_path, "known", {"a": 1})
    errors = classification_errors(tmp_path, set(), {}, {"known": "  "})
    assert len(errors) == 1 and "no reason given" in errors[0]


def test_double_classification_across_the_new_category_fails(tmp_path):
    _fake_tracked(tmp_path, "known", {"a": 1})
    errors = classification_errors(tmp_path, {"known"}, {}, {"known": "a reason"})
    assert any("both MANAGED and PRE_EXISTING" in e for e in errors)

    errors = classification_errors(
        tmp_path, set(), {"known": "a reason"}, {"known": "another reason"})
    assert any("both HAND_AUTHORED and PRE_EXISTING" in e for e in errors)


def test_pre_existing_does_not_widen_the_escape_hatch(tmp_path):
    """The point of the union assertion: a newly dropped fixture is still
    unclassified even though a third category now exists."""
    _fake_tracked(tmp_path, "known", {"a": 1})
    _fake_tracked(tmp_path, "dropped_in", {"a": 1})
    errors = classification_errors(tmp_path, set(), {}, {"known": "a reason"})
    assert len(errors) == 1
    assert errors[0].startswith("dropped_in.json is not classified")


def test_real_classification_union_covers_the_tracked_directory():
    """Drives the REAL three category tables against the REAL directory, so a
    fixture added without classification fails even if nobody edits a test."""
    on_disk = tracked_fixtures()
    declared = MANAGED | set(HAND_AUTHORED) | set(PRE_EXISTING)
    assert on_disk == declared
    assert not (MANAGED & set(HAND_AUTHORED))
    assert not (MANAGED & set(PRE_EXISTING))
    assert not (set(HAND_AUTHORED) & set(PRE_EXISTING))


def test_fully_classified_planted_directory_passes(tmp_path):
    _fake_tracked(tmp_path, "one", {"a": 1})
    _fake_tracked(tmp_path, "two", {"a": 1})
    assert classification_errors(tmp_path, {"one"}, {"two": "a stated reason"}, {}) == []


# --------------------------------------------------------------------------
# Generator loading
# --------------------------------------------------------------------------

def test_absent_generator_skips_rather_than_erroring(monkeypatch):
    monkeypatch.delitem(sys.modules, "gen_mock_fixtures", raising=False)
    monkeypatch.setattr(
        sys, "meta_path",
        [_BlockImport("gen_mock_fixtures")] + list(sys.meta_path))
    builder, reason = load_generator()
    assert builder is None and "not present" in reason


def test_generator_without_the_contract_does_not_silently_pass(monkeypatch):
    import types
    stub = types.ModuleType("gen_mock_fixtures")
    monkeypatch.setitem(sys.modules, "gen_mock_fixtures", stub)
    builder, reason = load_generator()
    assert builder is None and "build_fixtures" in reason


def test_broken_generator_raises_instead_of_skipping(monkeypatch):
    """A module that fails to import must not read as 'generator absent'. The
    window in which the generator is half-written is exactly the window in which
    a silent skip is most dangerous."""
    monkeypatch.delitem(sys.modules, "gen_mock_fixtures", raising=False)
    monkeypatch.setattr(
        sys, "meta_path",
        [_RaiseOnImport("gen_mock_fixtures")] + list(sys.meta_path))
    with pytest.raises(ModuleNotFoundError):
        load_generator()


def _stub_generator(monkeypatch, fixtures):
    import types
    stub = types.ModuleType("gen_mock_fixtures")
    stub.build_fixtures = lambda: fixtures
    monkeypatch.setitem(sys.modules, "gen_mock_fixtures", stub)


def test_wired_gate_passes_with_a_faithful_stub_generator(tmp_path, monkeypatch):
    """The two gate tests above SKIP in this checkout, so the path from
    load_generator() into regeneration_errors() would otherwise never run. Stub
    the module and drive it end to end."""
    payload = {"symbol": "TESTCO.X", "score": 7.2}
    _fake_tracked(tmp_path, "widget", payload)
    _stub_generator(monkeypatch, {"widget": payload})
    builder, reason = load_generator()
    assert reason is None and builder is not None
    assert regeneration_errors(builder(), tmp_path, {"widget"}) == []


def test_wired_gate_fails_with_a_live_capture_stub(tmp_path, monkeypatch):
    """Same wiring, one value replaced as a pasted capture would replace it."""
    _fake_tracked(tmp_path, "widget", {"symbol": "TESTCO.X", "score": 7.2})
    _stub_generator(monkeypatch, {"widget": {"symbol": "TESTCO.X", "score": 6.83}})
    builder, reason = load_generator()
    assert reason is None
    assert regeneration_errors(builder(), tmp_path, {"widget"}) != []


class _BlockImport:
    """Meta-path finder that makes one module name unimportable."""

    def __init__(self, name: str):
        self.name = name

    def find_spec(self, fullname, path=None, target=None):
        if fullname == self.name:
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
        return None


class _RaiseOnImport:
    """Meta-path finder simulating a present-but-broken module: the module fails
    on one of ITS OWN imports, so the raised name is not gen_mock_fixtures."""

    def __init__(self, name: str):
        self.name = name

    def find_spec(self, fullname, path=None, target=None):
        if fullname == self.name:
            raise ModuleNotFoundError("No module named 'numpy'", name="numpy")
        return None
