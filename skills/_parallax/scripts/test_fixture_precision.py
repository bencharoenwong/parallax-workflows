"""Tests for the fixture precision budget (gate 2).

Every planted value in this file is a HARDCODED LITERAL, never derived from
``fixture_precision.MAX_SIG_FIGS`` / ``MAX_DECIMALS``. A negative test that
builds its violation out of the implementation's own constants passes by
construction: raise the budget to 40 and the test raises its plant to match,
so it can never fail for the reason it claims to test. That defect -- a gate
whose tests cannot fail -- is the thing this whole effort is correcting.

The literals encode the intended judgement directly, against the MEASURED budget
of 9 significant figures — see fixture_precision.__doc__ for where that number
came from and why a tighter one was wrong:

  0.349378          authored weight, 6 figures / 6 decimals  must PASS
  47 / 189.42       authored count / price                   must PASS
  0.123456789       9 figures, exactly at the boundary       must PASS
  0.123456789012345 API-emitted ratio, 15 figures            must FAIL
  3812345678901234  market cap to the dollar, 16 figures     must FAIL
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixture_precision as fp


def _write(mocks: Path, name: str, payload: object) -> Path:
    mocks.mkdir(parents=True, exist_ok=True)
    path = mocks / name
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# The gate itself, against the tracked fixtures
# --------------------------------------------------------------------------

def test_tracked_fixtures_are_within_the_precision_budget():
    violations, stale = fp.scan_dir()
    assert violations == [], "\n".join(v.render() for v in violations)
    assert stale == [], f"stale ALLOWLIST entries: {stale}"


def test_tracked_fixture_dir_is_not_empty():
    """Guards against the gate passing because it scanned nothing -- a rename of
    mcp_mocks/ would otherwise turn this suite green and silent."""
    assert list(fp.MOCKS_DIR.glob("*.json")), "no fixtures found; gate is vacuous"


# --------------------------------------------------------------------------
# Negative cases: planted machine-grade values must FAIL
# --------------------------------------------------------------------------

def test_api_emitted_ratio_trips_the_gate(tmp_path):
    """A 15-significant-figure ratio is a serialised IEEE double, not a typed
    number."""
    _write(tmp_path, "planted.json", {"quality_ratio": 0.123456789012345})
    violations, _ = fp.scan_dir(tmp_path, allowlist={})
    assert [v.path for v in violations] == ["planted.json:quality_ratio"]
    assert "sig-figs" in {v.rule for v in violations}


def test_market_cap_to_the_dollar_trips_the_gate(tmp_path):
    """The hardest identity field to spot by eye: a 16-figure integer market
    cap re-identifies an issuer even after the ticker is renamed. Integers must
    be in scope, not just floats."""
    _write(tmp_path, "planted.json", {"mktcap": 3812345678901234})
    violations, _ = fp.scan_dir(tmp_path, allowlist={})
    assert [v.path for v in violations] == ["planted.json:mktcap"]


def test_share_count_to_the_share_trips_the_gate(tmp_path):
    _write(tmp_path, "planted.json", {"numshrs": 15728003241})
    violations, _ = fp.scan_dir(tmp_path, allowlist={})
    assert [v.path for v in violations] == ["planted.json:numshrs"]


def test_boundary_is_inclusive_and_one_figure_past_it_fails(tmp_path):
    """The budget is the observed maximum of legitimate content, so a value
    sitting exactly on it is legitimate and the very next figure is not. Pins the
    off-by-one that a re-tune would most easily get wrong."""
    _write(tmp_path, "at_boundary.json", {"ratio": 0.123456789})
    _write(tmp_path, "past_boundary.json", {"ratio": 0.1234567891})
    violations, _ = fp.scan_dir(tmp_path, allowlist={})
    assert [v.path for v in violations] == ["past_boundary.json:ratio"]


def test_violation_nested_in_a_list_is_found_with_a_collapsed_path(tmp_path):
    _write(tmp_path, "planted.json",
           {"history": [{"score": 7.2}, {"score": 6.283185307179586}]})
    violations, _ = fp.scan_dir(tmp_path, allowlist={})
    assert [v.path for v in violations] == ["planted.json:history[].score"]
    assert len(violations) == 1, "one over-precise value must yield one report"


def test_violation_in_a_subdirectory_is_found(tmp_path):
    """A capture dropped one directory down is the same "newly dropped fixture"
    move the gate exists to catch. A flat glob steps straight over it."""
    _write(tmp_path / "new_endpoint", "capture.json", {"mktcap": 3812345678901234})
    violations, _ = fp.scan_dir(tmp_path, allowlist={})
    assert [v.path for v in violations] == ["new_endpoint/capture.json:mktcap"]


def test_subdirectory_allowlist_is_keyed_on_the_relative_path(tmp_path):
    _write(tmp_path / "new_endpoint", "capture.json", {"mktcap": 3812345678901234})
    violations, stale = fp.scan_dir(
        tmp_path,
        allowlist={"new_endpoint/capture.json:mktcap": "reviewed: intentional"})
    assert violations == [] and stale == []


def test_main_exits_nonzero_on_a_planted_violation(tmp_path, monkeypatch, capsys):
    """End-to-end: the CLI entry point, not just the helper, must fail."""
    _write(tmp_path, "planted.json", {"mktcap": 3812345678901234})
    monkeypatch.setattr(fp, "MOCKS_DIR", tmp_path)
    monkeypatch.setattr(fp, "ALLOWLIST", {})
    assert fp.main() == 1
    captured = capsys.readouterr()
    assert "PRECISION" in captured.err


def test_output_never_echoes_the_offending_value(tmp_path, monkeypatch, capsys):
    """Naming a value to prove its presence publishes it. The report carries the
    path and the measurement, never the number."""
    _write(tmp_path, "planted.json", {"mktcap": 3812345678901234})
    monkeypatch.setattr(fp, "MOCKS_DIR", tmp_path)
    monkeypatch.setattr(fp, "ALLOWLIST", {})
    fp.main()
    captured = capsys.readouterr()
    assert "3812345678901234" not in captured.out + captured.err


# --------------------------------------------------------------------------
# Positive cases: ordinary authored values must NOT trip
# --------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    {"weight": 0.349378},
    {"holdings_count": 47},
    {"close": 189.42},
    {"score": 7.2},
    {"beta": 1.0},
    {"shares_outstanding": 2000000000},
    {"weights": [0.35, 0.25, 0.4]},
    {"tiny": 0.0},
    # At and just inside the measured ceiling. A gate that fired here is the
    # over-tight first-guess rule coming back, or a stray decimal-place rule:
    # 0.123456789 is 9 figures (legitimate) and unavoidably 9 decimals.
    {"ratio": 0.12345678},
    {"ratio_9sf": 0.123456789},
    {"eight_decimals": 1.12345678},
    # Few figures, many decimals. No decimal-place rule exists, by design.
    {"drift": 0.0000000123},
])
def test_authored_values_do_not_trip_the_gate(tmp_path, payload):
    _write(tmp_path, "authored.json", payload)
    violations, _ = fp.scan_dir(tmp_path, allowlist={})
    assert violations == [], "\n".join(v.render() for v in violations)


def test_ordinary_weight_with_six_decimals_passes(tmp_path):
    """0.349378 is six decimals and six figures. This is the value that killed
    the first-guess budget: a 4-decimal rule failed an ordinary authored weight.
    A genuinely over-precise small number is still caught, by figures."""
    _write(tmp_path, "authored.json", {"ok": 0.349378})
    _write(tmp_path, "machine.json", {"bad": 0.00000012345678901234})
    violations, _ = fp.scan_dir(tmp_path, allowlist={})
    assert [v.path for v in violations] == ["machine.json:bad"]


def test_measured_machine_float_shapes_all_trip(tmp_path):
    """The three fields observed carrying unrounded machine floats, at the low
    end of each observed range. Field names are the public MCP contract; the
    values are synthetic stand-ins with the measured figure counts."""
    _write(tmp_path, "company_info.json", {
        "changepercent": 0.12345678901234,   # 14 figures (observed 15-19)
        "change": 1.2345678901234,           # 14 figures (observed up to 17)
        "mktcap": 3812345678901.2,           # 14 figures (observed 14-16)
    })
    violations, _ = fp.scan_dir(tmp_path, allowlist={})
    assert sorted(v.path for v in violations) == [
        "company_info.json:change",
        "company_info.json:changepercent",
        "company_info.json:mktcap",
    ]


def test_null_values_are_out_of_scope(tmp_path):
    """`_meta.invalid_fields` is null when every requested field name was valid
    and a list of rejected names otherwise. Null carries no precision, and the
    walker must not choke on either shape."""
    _write(tmp_path, "clean.json", {"_meta": {"invalid_fields": None}})
    _write(tmp_path, "rejected.json", {"_meta": {"invalid_fields": ["nope"]}})
    violations, _ = fp.scan_dir(tmp_path, allowlist={})
    assert violations == []


# --------------------------------------------------------------------------
# Allowlist behaviour
# --------------------------------------------------------------------------

def test_allowlist_excuses_by_path(tmp_path):
    _write(tmp_path, "planted.json", {"mktcap": 3812345678901234})
    violations, stale = fp.scan_dir(
        tmp_path, allowlist={"planted.json:mktcap": "reviewed: intentional"})
    assert violations == []
    assert stale == []


def test_allowlist_is_scoped_to_its_own_path(tmp_path):
    """An exemption at one path must not excuse a sibling. Allowlisting by value
    would -- both fields below carry the same number."""
    _write(tmp_path, "planted.json",
           {"mktcap": 3812345678901234, "mktcap_prior": 3812345678901234})
    violations, _ = fp.scan_dir(
        tmp_path, allowlist={"planted.json:mktcap": "reviewed: intentional"})
    assert [v.path for v in violations] == ["planted.json:mktcap_prior"]


def test_allowlist_is_scoped_to_its_own_fixture(tmp_path):
    _write(tmp_path, "one.json", {"mktcap": 3812345678901234})
    _write(tmp_path, "two.json", {"mktcap": 3812345678901234})
    violations, _ = fp.scan_dir(
        tmp_path, allowlist={"one.json:mktcap": "reviewed: intentional"})
    assert [v.path for v in violations] == ["two.json:mktcap"]


def test_stale_allowlist_entry_is_reported(tmp_path):
    """The exemption outlived the value it excused. Left in place it silently
    pre-authorises the next leak at that path."""
    _write(tmp_path, "planted.json", {"mktcap": 3810000000000})
    violations, stale = fp.scan_dir(
        tmp_path, allowlist={"planted.json:mktcap": "reviewed: intentional"})
    assert violations == []
    assert stale == ["planted.json:mktcap"]


# --------------------------------------------------------------------------
# Honesty: the documented misses are real misses
# --------------------------------------------------------------------------

def test_large_round_integers_slip_through_as_documented(tmp_path):
    """Pins the acknowledged hole so it stays acknowledged. A live market cap
    rounded by hand passes this gate; only gate 1 catches it. If this test ever
    starts failing, the docstring's honesty clause needs rewriting -- not the
    test deleting."""
    _write(tmp_path, "rounded.json", {"mktcap": 3810000000000})
    violations, _ = fp.scan_dir(tmp_path, allowlist={})
    assert violations == []


def test_string_valued_leaks_slip_through_as_documented(tmp_path):
    """A recommendation string or a distinctive industry label carries no float
    precision at all. Same reason: gate 1 is the coverage."""
    _write(tmp_path, "strings.json",
           {"recommendation": "OVERWEIGHT", "industry": "a very distinctive one"})
    violations, _ = fp.scan_dir(tmp_path, allowlist={})
    assert violations == []
