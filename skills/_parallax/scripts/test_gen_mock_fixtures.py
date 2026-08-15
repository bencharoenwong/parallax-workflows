"""Arithmetic and trap coverage for the seeded fixture generator.

WHY THIS EXISTS SEPARATELY FROM GATE 1. ``test_fixture_provenance.py`` pins the
tracked fixture to the generator's output byte for byte. That catches a hand-
edited or pasted fixture, which is the leak it was built for -- but it cannot
catch a change to the GENERATOR, because then both sides move together and the
comparison still agrees. Regenerate after breaking an identity and gate 1 goes
green on a fixture that now teaches the wrong contract.

So these tests assert the relations INDEPENDENTLY, recomputing each one from the
emitted payload rather than trusting the code that produced it. They are the
reason a future edit to ``gen_mock_fixtures.py`` cannot quietly turn
``sector_contribution.avg_weight`` back into a sum.

TWO KINDS OF ASSERTION, AND THE DIFFERENCE MATTERS.

  * Identities the live API satisfies EXACTLY are asserted at 1e-9 or with
    ``==``. Money here rides an exact binary lattice, so these are bit-exact.
  * Relations that hold only TO ROUNDING are asserted inside their own decimal
    budget, and are separately asserted NOT to be exact. Tightening one of those
    to equality would be encoding a false identity, which is the failure mode
    the do-not-assert list exists to prevent.

The traps get positive tests too: it is not enough that the fixture happens to
have a two-member sector, the test must fail if that sector ever collapses to
one member and the mean-vs-sum distinction stops being observable.
"""
import datetime as dt
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixture_precision as fp
import gen_mock_fixtures as gen


@pytest.fixture(scope="module")
def fixtures():
    return gen.build_fixtures()


@pytest.fixture(scope="module")
def portfolio(fixtures):
    """The analytics block map, reached THROUGH the envelope.

    Indexing ``["result"]`` here rather than taking the payload bare is
    deliberate: if the wrapper is ever dropped, every test using this fixture
    fails loudly instead of quietly passing against a flattened payload."""
    return fixtures["analyze_portfolio"]["result"]


# --------------------------------------------------------------------------
# The generator contract itself
# --------------------------------------------------------------------------

def test_build_fixtures_is_deterministic():
    """Two calls, byte-identical. A generator that drifts between calls would
    fail gate 1 intermittently, which is worse than failing it every time."""
    first = json.dumps(gen.build_fixtures(), sort_keys=True)
    second = json.dumps(gen.build_fixtures(), sort_keys=True)
    assert first == second


def test_pinned_seed_satisfies_every_structural_constraint():
    """The pin is only meaningful while it still produces the structure the
    traps need. If this fails, re-pin with ``--find-seed`` rather than deleting
    the constraint that broke."""
    assert gen._seed_constraints(gen.build_paths(gen.SEED)) == []


def test_generator_output_is_within_the_precision_budget(fixtures):
    """Gate 2, applied to the in-memory payload rather than to the file, so a
    regression is caught before anything is written."""
    violations = []
    for name, payload in fixtures.items():
        for dotted, value in fp._walk(payload):
            violations.extend(fp.check_value(f"{name}.json:{dotted}", value))
    assert violations == [], [v.path for v in violations]


def test_analyze_portfolio_carries_the_response_envelope(fixtures):
    """FAILS IF THE WRAPPER IS DROPPED.

    An earlier generator emitted the block map bare. Everything else still
    passed — the identities, the traps, the precision budget — because a
    flattened payload is internally consistent. What it broke was the ACCESS
    PATH: consumers read ``response["result"][<block>]``, and a bare fixture
    teaches ``response[<block>]``, which returns nothing live.

    So this asserts the envelope directly rather than trusting that some other
    test would notice."""
    payload = fixtures["analyze_portfolio"]
    assert set(payload) == {"success", "result"}
    assert payload["success"] is True
    assert isinstance(payload["result"], dict)

    # _meta belongs inside result, alongside the analytics blocks.
    assert "_meta" in payload["result"]
    for block in ("portfolio_summary", "latest_holdings",
                  "company_contribution", "sector_allocation", "_meta"):
        assert block in payload["result"]
        assert block not in payload, (
            f"{block} leaked to the top level — the envelope is flattened")


def test_envelope_conventions_are_per_endpoint(fixtures):
    """The envelope is NOT uniform across endpoints, and assuming it is has
    burned this fixture set in both directions. Pin each one separately."""
    # Wrapped.
    assert "result" in fixtures["analyze_portfolio"]
    # Flat — adding a wrapper here would be just as wrong as removing one above.
    score = fixtures["get_score_analysis"]
    assert "result" not in score
    assert {"success", "symbol", "weeks", "data"} <= set(score)
    # Flat. The ledger documents company_info only as a BLOCK inside an
    # analyze_portfolio response and is silent on this standalone endpoint, so
    # it is emitted unwrapped rather than by analogy with its sibling.
    assert "result" not in fixtures["get_company_info"]


def test_credit_exhausted_envelope_reports_success_with_no_result(fixtures):
    """``success`` is true on a call that FAILED, and ``result`` is absent
    rather than null. Guard on presence of ``result``, never on ``success``."""
    payload = fixtures["analyze_portfolio_credit_exhausted"]
    assert payload["success"] is True
    assert "result" not in payload
    detail = payload["detail"]
    assert set(detail) == {"error", "balance", "required", "endpoint"}
    assert detail["required"] > detail["balance"]
    assert detail["endpoint"] == "analyze_portfolio"

    # The bug this models, written out: the naive guard passes.
    assert bool(payload["success"]) is True
    with pytest.raises(KeyError):
        payload["result"]


def test_no_real_issuer_identity_survives(fixtures):
    """The rule in one assertion. Tickers and names of actual listed companies
    must not appear anywhere in generated output."""
    blob = json.dumps(fixtures)
    for term in ("AAPL", "Apple", "MSFT", "Microsoft", "NVDA", "NVIDIA",
                 "apple.com", "ACWI", "JPM"):
        assert term not in blob, f"{term!r} reached a generated fixture"


# --------------------------------------------------------------------------
# Identities that hold EXACTLY
# --------------------------------------------------------------------------

def test_ending_values_sum_to_final_value(portfolio):
    total = sum(h["ending_value"] for h in portfolio["latest_holdings"])
    assert abs(total - portfolio["portfolio_summary"]["final_value"]) < 1e-9


def test_company_pl_sums_to_total_pl(portfolio):
    total = sum(r["total_pl"] for r in portfolio["company_contribution"])
    assert abs(total - portfolio["portfolio_summary"]["total_pl"]) < 1e-9


def test_contribution_pct_sums_to_exactly_one(portfolio):
    """Exact, not approximate. The server force-balances this one, and the
    fixture does too -- unlike the per-date allocation weights below, which are
    NOT balanced. Do not generalise from one to the other."""
    assert sum(r["contribution_pct"]
               for r in portfolio["company_contribution"]) == 1.0


def test_ending_value_minus_pl_recovers_the_initial_allocation(portfolio):
    initial = portfolio["portfolio_parameters"]["initial_value"]
    by_ric = {r["ric"]: r for r in portfolio["company_contribution"]}
    weights = {spec["ric"]: spec["weight"] for spec in gen.HOLDINGS}
    for holding in portfolio["latest_holdings"]:
        allocation = holding["ending_value"] - by_ric[holding["ric"]]["total_pl"]
        assert abs(allocation - initial * weights[holding["ric"]]) < 1e-9


def test_portfolio_summary_internal_identities(portfolio):
    summary = portfolio["portfolio_summary"]
    initial = portfolio["portfolio_parameters"]["initial_value"]
    assert summary["final_value"] == initial + summary["total_pl"]
    assert summary["total_price_pl"] + summary["total_fx_pl"] == summary["total_pl"]
    assert summary["total_return"] == round(summary["final_value"] / initial - 1, 6)


def test_performance_final_value_matches_the_summary(portfolio):
    assert (portfolio["performance_metrics"]["portfolio"]["final_value"]
            == portfolio["portfolio_summary"]["final_value"])


def test_portfolio_scores_are_floor_of_ten_times_the_weighted_score(portfolio):
    weights = [h["weight"] for h in portfolio["latest_holdings"]]
    for factor in gen.FACTORS + ["total"]:
        weighted = math.fsum(w * h[factor] for w, h
                             in zip(weights, portfolio["latest_holdings"]))
        assert portfolio["portfolio_scores"][factor] == math.floor(10.0 * weighted)


def test_floor_is_distinguishable_from_rounding(portfolio):
    """Guards the guard. If no factor's weighted score lands above the .5
    boundary, the test above passes just as well against round-half-up and
    proves nothing about which the API does."""
    weights = [h["weight"] for h in portfolio["latest_holdings"]]
    fractions = [
        (10.0 * math.fsum(w * h[factor] for w, h
                          in zip(weights, portfolio["latest_holdings"]))) % 1.0
        for factor in gen.FACTORS + ["total"]
    ]
    assert any(f > 0.5 for f in fractions), (
        "no factor lands above .5, so floor and round agree everywhere")


def test_sector_contribution_sums_pl_and_contribution(portfolio):
    members: dict[str, list[dict]] = {}
    for holding, row in zip(portfolio["latest_holdings"],
                            portfolio["company_contribution"]):
        members.setdefault(holding["sector"], []).append(row)
    for row in portfolio["sector_contribution"]:
        group = members[row["sector"]]
        assert abs(row["total_pl"] - sum(r["total_pl"] for r in group)) < 1e-9
        assert abs(row["contribution_pct"]
                   - sum(r["contribution_pct"] for r in group)) < 1e-9


# --------------------------------------------------------------------------
# Relations that hold only TO ROUNDING -- and must not be tightened
# --------------------------------------------------------------------------

def test_avg_allocation_matches_only_to_rounding(portfolio):
    """``avg_allocation == avg_weight * initial_value`` is computed from the
    UNROUNDED weight and rounded independently, so it is close but never equal.
    Asserted both ways: inside the budget, and NOT exact."""
    initial = portfolio["portfolio_parameters"]["initial_value"]
    inexact = 0
    for row in portfolio["company_contribution"]:
        diff = abs(row["avg_allocation"] - row["avg_weight"] * initial)
        assert diff < initial * 5e-7
        if diff > 0:
            inexact += 1
    assert inexact, ("every avg_allocation matched exactly — the fixture is now "
                     "modelling an identity the API does not have")


def test_return_pct_is_pl_over_avg_allocation_to_six_decimals(portfolio):
    for row in portfolio["company_contribution"]:
        assert abs(row["return_pct"]
                   - row["total_pl"] / row["avg_allocation"]) < 1e-6


def test_contribution_pct_matches_the_ratio_within_its_budget(portfolio):
    total_pl = portfolio["portfolio_summary"]["total_pl"]
    for row in portfolio["company_contribution"]:
        assert abs(row["contribution_pct"] - row["total_pl"] / total_pl) < 1e-6


def test_per_date_weights_sum_to_one_only_to_rounding(portfolio):
    """Unlike contribution_pct, these are NOT force-balanced."""
    by_date: dict[str, float] = {}
    for row in portfolio["sector_allocation"]:
        by_date[row["date"]] = by_date.get(row["date"], 0.0) + row["weight"]
    assert by_date
    for day, total in by_date.items():
        assert abs(total - 1.0) < 5e-6, f"{day}: {total}"


# --------------------------------------------------------------------------
# The traps
# --------------------------------------------------------------------------

def test_sector_avg_weight_is_the_mean_not_the_sum(portfolio):
    """The highest-risk aggregation trap in the payload: within ONE row,
    total_pl and contribution_pct sum while avg_weight averages."""
    members: dict[str, list[dict]] = {}
    for holding, row in zip(portfolio["latest_holdings"],
                            portfolio["company_contribution"]):
        members.setdefault(holding["sector"], []).append(row)

    multi = [s for s, g in members.items() if len(g) > 1]
    assert multi, ("no sector holds more than one member, so mean and sum "
                   "coincide everywhere and this trap is untested")

    for row in portfolio["sector_contribution"]:
        group = members[row["sector"]]
        assert row["avg_weight"] == round(
            sum(r["avg_weight"] for r in group) / len(group), 6)
    for sector in multi:
        row = next(r for r in portfolio["sector_contribution"]
                   if r["sector"] == sector)
        assert row["avg_weight"] != sum(r["avg_weight"] for r in members[sector])


def test_invalid_fields_is_null_not_an_empty_list(portfolio):
    invalid = portfolio["_meta"]["invalid_fields"]
    assert invalid is None
    assert invalid != []


def test_meta_field_lists_share_a_set_but_not_an_order(portfolio):
    requested = portfolio["_meta"]["fields_requested"]
    returned = portfolio["_meta"]["fields_returned"]
    assert set(requested) == set(returned)
    assert requested != returned


def test_win_rate_divides_by_calendar_days(portfolio):
    perf = portfolio["performance_metrics"]["portfolio"]
    assert perf["win_rate"] == round(perf["positive_days"] / perf["days"], 4)
    # The remainder are zero-return carry-forward days on the calendar grid.
    assert perf["positive_days"] + perf["negative_days"] < perf["days"]


def test_daily_grid_is_calendar_not_trading_days(portfolio):
    dates = sorted({row["date"] for row in portfolio["sector_allocation"]})
    parsed = [dt.date.fromisoformat(d) for d in dates]
    assert any(d.weekday() >= 5 for d in parsed), "no weekend rows on the grid"
    span = (parsed[-1] - parsed[0]).days + 1
    assert len(parsed) == span, "grid has gaps, so it is not a calendar grid"


def test_top_5_share_is_not_clamped_to_one(portfolio):
    share = portfolio["concentration_metrics"]["concentration"]["top_5_share"]
    assert share > 1.0, (
        "top_5_share is not above 1, so a `<= 1.0` assertion would pass here "
        "and fail against the live payload")


def test_quantity_times_close_does_not_equal_ending_value(portfolio):
    """The divergence is real, always positive, and ordered by dividend yield.
    Never assert the product identity at any tolerance."""
    yields = {spec["ric"]: spec["dividend_yield"] for spec in gen.HOLDINGS}
    gaps = []
    for holding in portfolio["latest_holdings"]:
        product = holding["quantity"] * holding["close_local"]
        assert holding["ending_value"] != product
        assert holding["ending_value"] > product
        gaps.append((yields[holding["ric"]],
                     holding["ending_value"] / product - 1.0))
    by_yield = [gap for _, gap in sorted(gaps)]
    assert by_yield == sorted(by_yield), (
        "the dividend gap is not monotone in yield, so it is no longer "
        "modelling a dividend-inclusive value path")


def test_benchmark_metrics_are_a_strict_subset_of_portfolio(portfolio):
    perf = portfolio["performance_metrics"]
    assert set(perf["benchmark"]) < set(perf["portfolio"])
    assert len(perf["portfolio"]) - len(perf["benchmark"]) == 8


def test_short_period_buckets_are_present_and_null(portfolio):
    buckets = portfolio["time_period_returns"]
    assert len(buckets) == 12
    for key in ("3yr", "5yr", "10yr"):
        assert key in buckets, "the bucket must be present, not absent"
        assert all(value is None for value in buckets[key].values())
    assert buckets["inception"]["portfolio_return"] is not None


def test_inception_return_differs_from_the_value_ratio(portfolio):
    """Two computations: a chain of rounded daily returns versus a value ratio.
    They disagree in the last decimals, and code must not treat them as one."""
    chained = portfolio["time_period_returns"]["inception"]["portfolio_return"]
    ratio = portfolio["performance_metrics"]["portfolio"]["total_return"]
    assert chained != ratio
    assert abs(chained - ratio) < 1e-4


def test_final_drawdown_episode_is_open(portfolio):
    episodes = portfolio["drawdown_analysis"]["episode_details"]["portfolio"]
    assert episodes
    last = episodes[-1]
    assert last["end_date"] is None
    assert last["recovery_days"] is None
    assert last["recovered"] is False


def test_deepest_drawdown_episode_recovered(portfolio):
    """So ``recovery_days_from_max_dd`` is a real integer rather than a stand-in
    for an unrecovered path."""
    episodes = portfolio["drawdown_analysis"]["episode_details"]["portfolio"]
    deepest = min(episodes, key=lambda e: e["max_drawdown"])
    assert deepest["recovered"] is True
    assert portfolio["performance_metrics"]["portfolio"][
        "recovery_days_from_max_dd"] > 0


def test_drawdown_episode_column_is_null_when_not_underwater(portfolio):
    rows = portfolio["drawdown_analysis"]["timeseries"]
    assert any(row["portfolio_episode"] is None for row in rows)
    for row in rows:
        if row["portfolio_episode"] is None:
            assert row["portfolio_drawdown"] == 0.0
        else:
            assert row["portfolio_drawdown"] < 0.0


def test_total_positions_counts_position_days(portfolio):
    dates = {row["date"] for row in portfolio["sector_allocation"]}
    holdings = portfolio["latest_holdings"]
    assert (portfolio["data_quality"]["portfolio_data_quality"]["total_positions"]
            == len(dates) * len(holdings))


# --------------------------------------------------------------------------
# concentration_metrics: the estimator split
# --------------------------------------------------------------------------

def test_weight_statistics_use_the_sample_standard_deviation(portfolio):
    weights = [h["weight"] for h in portfolio["latest_holdings"]]
    stats = portfolio["concentration_metrics"]["weight_statistics"]
    assert stats["mean"] == round(math.fsum(weights) / len(weights), 6)
    assert stats["median"] == round(gen.median(weights), 6)
    assert stats["std_dev"] == round(gen.sample_std(weights), 6)
    assert stats["maximum"] == round(max(weights), 6)
    assert stats["minimum"] == round(min(weights), 6)

    mu = math.fsum(weights) / len(weights)
    population = math.sqrt(math.fsum((w - mu) ** 2 for w in weights) / len(weights))
    assert stats["std_dev"] != round(population, 6), (
        "sample and population std agree here, so the n-1 choice is untested")


def test_higher_moments_use_population_estimators(portfolio):
    weights = [h["weight"] for h in portfolio["latest_holdings"]]
    moments = portfolio["concentration_metrics"]["higher_moments"]
    assert moments["skewness"] == round(gen.population_skew(weights), 4)
    assert moments["kurtosis"] == round(
        gen.population_excess_kurtosis(weights), 1)


def test_effective_positions_comes_from_the_unrounded_hhi(portfolio):
    weights = [h["weight"] for h in portfolio["latest_holdings"]]
    concentration = portfolio["concentration_metrics"]["concentration"]
    hhi = math.fsum(w * w for w in weights)
    assert concentration["herfindahl_index"] == round(hhi, 4)
    assert concentration["effective_positions"] == round(1.0 / hhi, 2)
    assert concentration["gini_coefficient"] == round(gen.gini(weights), 3)


def test_diversification_counts_match_the_holdings(portfolio):
    holdings = portfolio["latest_holdings"]
    diversification = portfolio["concentration_metrics"]["diversification"]
    assert diversification["num_sectors"] == len({h["sector"] for h in holdings})
    assert diversification["num_markets"] == len({h["market"] for h in holdings})
    assert diversification["num_industries"] == len({h["industry"] for h in holdings})


# --------------------------------------------------------------------------
# Structural richness -- the fixture must stay hard enough to be useful
# --------------------------------------------------------------------------

def test_fixture_has_a_losing_holding(portfolio):
    """A portfolio where everything wins never exercises the negative sign path
    through contribution, sector rollup or attribution."""
    assert any(r["total_pl"] < 0 for r in portfolio["company_contribution"])
    assert any(r["total_pl"] > 0 for r in portfolio["company_contribution"])
    assert any(r["total_pl"] < 0 for r in portfolio["sector_contribution"])


def test_fixture_spans_several_sectors_and_dates(portfolio):
    holdings = portfolio["latest_holdings"]
    assert len({h["sector"] for h in holdings}) >= 3
    assert len({row["date"] for row in portfolio["sector_allocation"]}) >= 3
    assert len(holdings) >= 4


def test_rics_carry_valid_exchange_suffixes(portfolio):
    """Per the RIC table in parallax-conventions.md §1."""
    valid = {"O", "N", "L", "DE", "PA", "T", "HK", "TW", "AX", "OL", "KS"}
    for holding in portfolio["latest_holdings"]:
        stem, _, suffix = holding["ric"].partition(".")
        assert stem and suffix in valid, holding["ric"]


# --------------------------------------------------------------------------
# get_score_analysis
# --------------------------------------------------------------------------

def test_score_analysis_is_flat_with_a_data_list(fixtures):
    payload = fixtures["get_score_analysis"]
    assert "result" not in payload, "this endpoint has no result wrapper"
    assert isinstance(payload["data"], list) and payload["data"]
    assert payload["weeks"] == len(payload["data"])


def test_score_analysis_cadence_is_weekly(fixtures):
    rows = fixtures["get_score_analysis"]["data"]
    dates = [dt.date.fromisoformat(r["date"]) for r in rows]
    assert all((b - a).days == 7 for a, b in zip(dates, dates[1:]))


def test_score_analysis_subscores_are_integers_on_zero_to_ten(fixtures):
    payload = fixtures["get_score_analysis"]
    for row in payload["data"]:
        assert row["symbol"] == payload["symbol"]
        for factor in gen.FACTORS:
            assert isinstance(row[factor], int) and not isinstance(row[factor], bool)
            assert 0 <= row[factor] <= 10
        assert isinstance(row["total"], float) and 0 <= row["total"] <= 10
        assert round(row["total"], 1) == row["total"]


def test_score_analysis_total_is_not_the_mean(fixtures):
    """A separately-computed composite. It differed from the arithmetic mean on
    every captured row, in both directions."""
    rows = fixtures["get_score_analysis"]["data"]
    means = [round(sum(row[f] for f in gen.FACTORS) / 5, 1) for row in rows]
    assert all(row["total"] != m for row, m in zip(rows, means))


# --------------------------------------------------------------------------
# Cross-fixture consistency
# --------------------------------------------------------------------------

def test_company_info_agrees_with_the_portfolio_holding(fixtures, portfolio):
    """One synthetic issuer, one identity, across every fixture that names it."""
    info = fixtures["get_company_info"]
    holding = next(h for h in portfolio["latest_holdings"]
                   if h["ric"] == info["symbol"])
    assert info["name"] == holding["name"]
    assert info["sector"] == holding["sector"]
    assert info["industry"] == holding["industry"]
    assert fixtures["get_score_analysis"]["symbol"] == info["symbol"]
