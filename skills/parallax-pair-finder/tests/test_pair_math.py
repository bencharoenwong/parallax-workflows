"""Arithmetic and malformed-input controls; no model or connector execution."""
from datetime import date, timedelta
import json
import math
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pair_math import compute, history_stats, main, max_drawdown, prices, returns


def series(beta=1, count=100, offset=0, field="price"):
    value = 100.0
    out = []
    for n in range(count):
        out.append({"date": str(date(2026, 1, 1) + timedelta(days=n+offset)), field: value})
        value *= 1 + beta * ([.01, -.005, .003, -.008][n % 4])
    return out


def payload(bl=2, bs=1):
    return {"long_prices": {"success": True, "data": series(bl)},
            "short_prices": {"success": True, "data": series(bs)},
            "benchmark_prices": series(field="close")}


def test_feasible_beta_ratio_uses_observed_equity_price_field():
    result = compute(payload())
    assert result["beta_long"] == pytest.approx(2)
    assert result["beta_short"] == pytest.approx(1)
    assert result["beta_neutral_ratio"] == pytest.approx(2)
    assert result["common_return_intervals"] == 99


def test_legacy_close_and_reverse_order_have_same_evidence():
    p = payload()
    p["long_prices"] = list(reversed(series(2, field="close")))
    assert compute(p)["beta_neutral_ratio"] == pytest.approx(2)


def test_explicit_no_beta_does_not_require_or_read_benchmark():
    p = payload(); p["benchmark_prices"] = "not a benchmark"
    result = compute(p, no_beta=True, history=True)
    assert result["dollar_neutral_ratio"] == 1
    assert result["beta_neutral_ratio"] is None
    assert result["history"]["available"]


def test_short_benchmark_is_a_gate_failure():
    p = payload(); p["benchmark_prices"] = series(count=59, field="close")
    with pytest.raises(ValueError, match="60"):
        compute(p)


def test_individually_long_series_without_joint_history_does_not_produce_beta():
    p = payload(); p["short_prices"] = series(offset=50)
    result = compute(p)
    assert result["beta_neutral_ratio"] is None
    assert "insufficient common" in result["beta_status"]


def test_align_both_return_interval_endpoints_not_only_end_date():
    s = prices(series(count=4)); t = dict(s); t.pop(sorted(t)[1])
    assert len(returns(s).keys() & returns(t).keys()) == 1


@pytest.mark.parametrize("beta", [0.0, 0.01, -0.5])
def test_unstable_or_opposite_sign_short_beta_has_no_hedge_ratio(beta):
    result = compute(payload(bs=beta))
    assert result["beta_neutral_ratio"] is None
    assert "dollar-neutral only" in result["beta_status"]


def test_zero_benchmark_variance_is_not_a_beta():
    p = payload(); p["benchmark_prices"] = series(beta=0, field="close")
    result = compute(p)
    assert result["beta_neutral_ratio"] is None
    assert "variance" in result["beta_status"]


def test_max_drawdown_is_relative_to_peak_and_includes_initial_wealth():
    assert max_drawdown([1, 2, 1.5]) == pytest.approx(-.25)
    assert max_drawdown([1, .8, .9]) == pytest.approx(-.2)


def test_constant_returns_correlation_is_unavailable_not_nan():
    p = prices(series(beta=0))
    assert history_stats(p, p, 1)["correlation"] is None


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True, "100"])
def test_invalid_prices_cannot_become_sizing_evidence(value):
    with pytest.raises(ValueError, match="finite and positive"):
        prices([{"date": "2026-01-01", "price": value}])


def test_duplicate_and_impossible_dates_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        prices(series(count=1)*2)
    with pytest.raises(ValueError):
        prices([{"date": "2026-02-30", "price": 1}])


def test_conflicting_price_aliases_are_rejected():
    with pytest.raises(ValueError, match="conflicting"):
        prices([{"date": "2026-01-01", "price": 1, "close": 2}])


def test_cli_controls_and_strict_json(tmp_path, capsys):
    path = tmp_path / "pair.json"; path.write_text(json.dumps(payload()))
    assert main(["--input", str(path), "--history"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["history"]["available"]
    assert output["history"]["max_drawdown"] == pytest.approx(0, abs=1e-12)
    path.write_text(json.dumps({"long_prices": [], "short_prices": []}))
    assert main(["--input", str(path)]) == 2
    assert capsys.readouterr().out == ""


def test_no_beta_without_history_needs_no_price_evidence():
    result = compute({}, no_beta=True)
    assert result["dollar_neutral_ratio"] == 1.0
    assert result["beta_neutral_ratio"] is None
    assert "prices and benchmark not read" in result["beta_status"]


def test_disjoint_common_intervals_cannot_hide_intervening_drawdown():
    long = [{"date": f"2026-01-0{i}", "price": value}
            for i, value in enumerate([100, 100, 20, 20, 20], 1)]
    short = [{"date": f"2026-01-0{i}", "price": 100} for i in [1, 2, 4, 5]]
    result = compute({"long_prices": long, "short_prices": short}, no_beta=True, history=True)
    assert result["history"]["available"] is False
    assert result["history"]["gaps"] == [{"after": "2026-01-02", "before": "2026-01-04"}]
    assert "max_drawdown" not in result["history"]


def test_contiguous_history_retains_the_eighty_percent_drawdown():
    long = [{"date": f"2026-01-0{i}", "price": value}
            for i, value in enumerate([100, 100, 20, 20, 20], 1)]
    short = [{"date": f"2026-01-0{i}", "price": 100} for i in range(1, 6)]
    result = compute({"long_prices": long, "short_prices": short}, no_beta=True, history=True)
    assert result["history"]["available"] is True
    assert result["history"]["max_drawdown"] == pytest.approx(-.8)


@pytest.mark.parametrize("dates", [["2026-01-01", "2026-02-01", "2026-03-01"],
                                   ["2026-01-01", "2026-01-08", "2026-01-15"]])
def test_sparse_monthly_or_weekly_prices_are_not_annualized_as_daily(dates):
    long = [{"date": stamp, "price": value} for stamp, value in zip(dates, [100, 110, 99])]
    short = [{"date": stamp, "price": 100} for stamp in dates]
    result = compute({"long_prices": long, "short_prices": short}, no_beta=True, history=True)
    assert result["history"]["available"] is False
    assert "daily-observation support unverified" in result["history"]["reason"]
    assert "annualized_spread_volatility" not in result["history"]


def test_normal_weekend_interval_remains_supported_as_daily_observations():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
    long = [{"date": stamp, "price": value} for stamp, value in zip(dates, [100, 101, 100])]
    short = [{"date": stamp, "price": 100} for stamp in dates]
    result = compute({"long_prices": long, "short_prices": short}, no_beta=True, history=True)
    assert result["history"]["available"] is True
    assert result["history"]["max_daily_interval_calendar_days"] == 4
    assert result["history"]["annualized_spread_volatility"] > 0
