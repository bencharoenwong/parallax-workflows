"""Unit tests for the redundancy-coverage cross-check helper.

Run: python3 -m pytest skills/_parallax/test_coverage_check.py -q
Placed beside the module, same convention as test_render_gate.py -- no
tests/ subdirectory exists directly under skills/_parallax/.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from coverage_check import (  # noqa: E402
    COVERAGE_TOTAL_MIN,
    MAX_DIVERGENCE_PP,
    VERDICT_CONSISTENT,
    VERDICT_COVERAGE_LIMITED,
    check_coverage,
)

MODULE = HERE / "coverage_check.py"


# --------------------------------------------------------------------------
# check_coverage() -- dict-shape sector payloads
# --------------------------------------------------------------------------


def test_consistent_when_totals_and_sectors_match():
    portfolio = {"Technology": 0.40, "Financials": 0.35, "Health Care": 0.25}
    redundancy = {"Technology": 0.40, "Financials": 0.35, "Health Care": 0.25}
    result = check_coverage(portfolio, redundancy)
    assert result.verdict == VERDICT_CONSISTENT
    assert result.redundancy_total == 1.0
    assert result.diverging_sectors == []
    assert result.absent_holdings == []


def test_coverage_limited_when_total_below_min():
    portfolio = {"Technology": 0.60, "Financials": 0.40}
    # Redundancy total is 0.90, below COVERAGE_TOTAL_MIN (0.98).
    redundancy = {"Technology": 0.55, "Financials": 0.35}
    result = check_coverage(portfolio, redundancy)
    assert result.redundancy_total < COVERAGE_TOTAL_MIN
    assert result.verdict == VERDICT_COVERAGE_LIMITED


def test_coverage_limited_when_single_sector_diverges_more_than_threshold():
    portfolio = {"Technology": 0.50, "Financials": 0.50}
    # Financials off by 6pp (> MAX_DIVERGENCE_PP), total still sums to 1.0.
    redundancy = {"Technology": 0.56, "Financials": 0.44}
    result = check_coverage(portfolio, redundancy)
    assert result.verdict == VERDICT_COVERAGE_LIMITED
    assert result.max_divergence_pp > MAX_DIVERGENCE_PP
    tech_rows = [d for d in result.diverging_sectors if d["sector"] == "financials"]
    assert len(tech_rows) == 1
    assert tech_rows[0]["unmatched"] is False


def test_divergence_exactly_at_threshold_is_not_flagged():
    portfolio = {"Technology": 0.50, "Financials": 0.50}
    redundancy = {"Technology": 0.55, "Financials": 0.45}  # exactly 5pp
    result = check_coverage(portfolio, redundancy)
    assert result.verdict == VERDICT_CONSISTENT
    assert result.diverging_sectors == []


def test_unmatched_sector_name_flagged_and_forces_coverage_limited():
    portfolio = {"Technology": 0.60, "Utilities": 0.40}
    redundancy = {"Technology": 0.60, "Energy": 0.40}
    result = check_coverage(portfolio, redundancy)
    assert result.verdict == VERDICT_COVERAGE_LIMITED
    sectors_flagged = {d["sector"]: d for d in result.diverging_sectors}
    assert sectors_flagged["utilities"]["unmatched"] is True
    assert sectors_flagged["utilities"]["redundancy_weight"] is None
    assert sectors_flagged["energy"]["unmatched"] is True
    assert sectors_flagged["energy"]["portfolio_weight"] is None


def test_sector_name_comparison_is_case_and_whitespace_insensitive():
    portfolio = {"  Health Care ": 1.0}
    redundancy = {"health   care": 1.0}
    result = check_coverage(portfolio, redundancy)
    assert result.verdict == VERDICT_CONSISTENT
    assert result.diverging_sectors == []


def test_accepts_list_shape_sector_payload():
    portfolio = [
        {"sector": "Technology", "weight": 0.6},
        {"sector": "Financials", "weight": 0.4},
    ]
    redundancy = [
        {"sector": "Technology", "weight": 0.6},
        {"sector": "Financials", "weight": 0.4},
    ]
    result = check_coverage(portfolio, redundancy)
    assert result.verdict == VERDICT_CONSISTENT
    assert result.redundancy_total == 1.0


def test_non_numeric_weight_is_dropped_not_guessed():
    portfolio = {"Technology": 0.6, "Financials": "n/a"}
    redundancy = {"Technology": 0.6}
    result = check_coverage(portfolio, redundancy)
    # "Financials" weight was unusable and dropped -- not treated as 0 divergence.
    assert result.redundancy_total == 0.6


# --------------------------------------------------------------------------
# absent_holdings -- only computed when holdings is supplied
# --------------------------------------------------------------------------


def test_absent_holdings_empty_when_holdings_not_supplied():
    portfolio = {"Technology": 1.0}
    redundancy = {"Technology": 1.0}
    result = check_coverage(portfolio, redundancy, holdings=None)
    assert result.absent_holdings == []


def test_absent_holdings_names_symbol_missing_from_redundancy_payload():
    portfolio = {"Technology": 1.0}
    redundancy = {"Technology": 1.0, "pairs": [["AAPL.O", "MSFT.O"]]}
    holdings = ["AAPL.O", "MSFT.O", "XOM.N"]
    result = check_coverage(portfolio, redundancy, holdings=holdings)
    assert result.absent_holdings == ["XOM.N"]
    assert result.verdict == VERDICT_COVERAGE_LIMITED


def test_absent_holdings_accepts_symbol_object_shape():
    portfolio = {"Technology": 1.0}
    redundancy = {"Technology": 1.0, "covered": ["AAPL.O"]}
    holdings = [{"symbol": "AAPL.O"}, {"symbol": "XOM.N"}]
    result = check_coverage(portfolio, redundancy, holdings=holdings)
    assert result.absent_holdings == ["XOM.N"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _run_cli(args, **kwargs):
    return subprocess.run(
        [sys.executable, str(MODULE), *args],
        capture_output=True, text=True, **kwargs,
    )


def test_cli_accepts_inline_json():
    proc = _run_cli([
        "--portfolio-sectors", json.dumps({"Technology": 1.0}),
        "--redundancy-sectors", json.dumps({"Technology": 1.0}),
    ])
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["verdict"] == VERDICT_CONSISTENT


def test_cli_accepts_file_path(tmp_path):
    portfolio_file = tmp_path / "portfolio.json"
    redundancy_file = tmp_path / "redundancy.json"
    portfolio_file.write_text(json.dumps({"Technology": 1.0}))
    redundancy_file.write_text(json.dumps({"Technology": 0.5}))
    proc = _run_cli([
        "--portfolio-sectors", str(portfolio_file),
        "--redundancy-sectors", str(redundancy_file),
    ])
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["verdict"] == VERDICT_COVERAGE_LIMITED


def test_cli_holdings_round_trip(tmp_path):
    proc = _run_cli([
        "--portfolio-sectors", json.dumps({"Technology": 1.0}),
        "--redundancy-sectors", json.dumps({"Technology": 1.0}),
        "--holdings", json.dumps(["AAPL.O"]),
    ])
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["absent_holdings"] == ["AAPL.O"]
    assert payload["verdict"] == VERDICT_COVERAGE_LIMITED


def test_cli_exits_2_on_empty_portfolio_sectors():
    proc = _run_cli([
        "--portfolio-sectors", "{}",
        "--redundancy-sectors", json.dumps({"Technology": 1.0}),
    ])
    assert proc.returncode == 2
    assert "error" in json.loads(proc.stdout)


def test_cli_exits_2_on_neither_inline_json_nor_readable_file(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    proc = _run_cli([
        "--portfolio-sectors", str(missing),
        "--redundancy-sectors", json.dumps({"Technology": 1.0}),
    ])
    assert proc.returncode == 2
    assert "error" in json.loads(proc.stdout)


def test_cli_exits_2_on_malformed_json_file(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not json")
    proc = _run_cli([
        "--portfolio-sectors", str(bad_file),
        "--redundancy-sectors", json.dumps({"Technology": 1.0}),
    ])
    assert proc.returncode == 2
    assert "error" in json.loads(proc.stdout)
