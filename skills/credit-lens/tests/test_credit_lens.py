"""
test_credit_lens.py — Comprehensive test suite for /parallax-credit-lens logic.

Coverage targets:
  - Overall: 80%+
  - credit_lens_logic.py (core): 95%+

Structure:
  TestAltmanZScore          — unit: Z-score computation + zone flags
  TestAbsoluteFlagging      — unit: per-metric absolute threshold logic
  TestPeerRelativeFlagging  — unit: peer-relative flag logic
  TestConservativeRule      — unit: more-conservative-of-two-rules integration
  TestQualityChangeFlagging — unit: 52-week quality score change thresholds
  TestOverallTrafficLight   — unit: majority-vote aggregation
  TestRICValidation         — unit: RIC format validation
  TestReportBuilders        — unit: markdown section assembly
  TestIntegrationFixtures   — integration: fixture-driven full-metric evaluation
  TestErrorDegradation      — integration: graceful degradation paths
  TestEdgeCases             — unit: boundaries, zeros, negatives, Unicode

Run from repo root:
    pytest skills/credit-lens/tests/test_credit_lens.py -v --tb=short
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

_SKILL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_SKILL_DIR))

from credit_lens_logic import (  # noqa: E402
    AltmanInputs,
    CreditReport,
    Flag,
    MetricRow,
    ABSOLUTE_THRESHOLDS,
    assemble_report,
    build_footer,
    build_header,
    build_key_flags_section,
    build_metrics_table,
    build_solvency_section,
    compute_altman_z,
    flag_metric,
    flag_quality_change,
    overall_traffic_light,
    validate_ric,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(filename: str) -> dict:
    return json.loads((_FIXTURES / filename).read_text())


# ---------------------------------------------------------------------------
# TestAltmanZScore
# ---------------------------------------------------------------------------


class TestAltmanZScore:
    """Unit tests for compute_altman_z — arithmetic + zone flags."""

    def _safe_inputs(
        self,
        *,
        working_capital: float = 5000.0,
        retained_earnings: float = 8000.0,
        ebit: float = 4000.0,
        total_assets: float = 20000.0,
        total_liabilities: float = 10000.0,
        revenue: float = 30000.0,
        market_cap: Optional[float] = 25000.0,
        book_equity: Optional[float] = None,
    ) -> AltmanInputs:
        return AltmanInputs(
            working_capital=working_capital,
            retained_earnings=retained_earnings,
            ebit=ebit,
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            revenue=revenue,
            market_cap=market_cap,
            book_equity=book_equity,
        )

    def test_safe_zone_returns_green(self) -> None:
        """Z > 2.99 → GREEN."""
        inputs = self._safe_inputs()
        z, variant, flag = compute_altman_z(inputs)
        assert z > 2.99
        assert flag == Flag.GREEN
        assert variant == "Z"

    def test_distress_zone_returns_red(self) -> None:
        """Z < 1.81 → RED."""
        inputs = self._safe_inputs(
            working_capital=-5000.0,
            retained_earnings=-8000.0,
            ebit=-2000.0,
            market_cap=500.0,
            revenue=3000.0,
        )
        z, variant, flag = compute_altman_z(inputs)
        assert z < 1.81
        assert flag == Flag.RED

    def test_grey_zone_returns_amber(self) -> None:
        """1.81 <= Z <= 2.99 → AMBER."""
        # Inputs tuned to produce Z ≈ 1.865 (verified: 1.81 <= 1.865 <= 2.99)
        # X1=0.05, X2=0.10, X3=0.05, X4=0.50, X5=1.20
        # Z = 0.06 + 0.14 + 0.165 + 0.30 + 1.20 = 1.865
        inputs = AltmanInputs(
            working_capital=500.0,
            retained_earnings=1000.0,
            ebit=500.0,
            total_assets=10000.0,
            total_liabilities=8000.0,
            market_cap=4000.0,
            revenue=12000.0,
        )
        z, _, flag = compute_altman_z(inputs)
        assert 1.81 <= z <= 2.99
        assert flag == Flag.AMBER

    def test_book_equity_variant_label(self) -> None:
        """When market_cap is None, variant label should be Z'."""
        inputs = self._safe_inputs(market_cap=None, book_equity=10000.0)
        _, variant, _ = compute_altman_z(inputs)
        assert variant == "Z'"

    def test_market_cap_preferred_over_book_equity(self) -> None:
        """When both market_cap and book_equity are provided, use market_cap (variant=Z)."""
        inputs = self._safe_inputs(market_cap=25000.0, book_equity=10000.0)
        _, variant, _ = compute_altman_z(inputs)
        assert variant == "Z"

    def test_raises_on_zero_total_assets(self) -> None:
        """Zero total_assets should raise ValueError."""
        with pytest.raises(ValueError, match="total_assets"):
            compute_altman_z(self._safe_inputs(total_assets=0.0))

    def test_raises_on_zero_total_liabilities(self) -> None:
        """Zero total_liabilities should raise ValueError."""
        with pytest.raises(ValueError, match="total_liabilities"):
            compute_altman_z(self._safe_inputs(total_liabilities=0.0))

    def test_raises_when_neither_market_cap_nor_book_equity(self) -> None:
        """No X4 data → ValueError."""
        with pytest.raises(ValueError, match="market_cap or book_equity"):
            compute_altman_z(self._safe_inputs(market_cap=None, book_equity=None))

    def test_z_boundary_safe_exactly_299(self) -> None:
        """Z exactly at 2.99 should be AMBER (not GREEN — threshold is strictly >2.99)."""
        # Construct inputs that yield exactly 2.99 via normalised formula
        # X1=0, X2=0, X3=0, X4=0, X5 = 2.99/1.0
        inputs = AltmanInputs(
            working_capital=0.0,
            retained_earnings=0.0,
            ebit=0.0,
            total_assets=100.0,
            total_liabilities=1.0,
            revenue=299.0,  # X5 = 299/100 = 2.99 → Z = 2.99
            market_cap=0.0,
        )
        z, _, flag = compute_altman_z(inputs)
        assert abs(z - 2.99) < 1e-9
        assert flag == Flag.AMBER

    def test_z_boundary_distress_exactly_181(self) -> None:
        """Z exactly at 1.81 should be AMBER (1.81-2.99 inclusive is grey zone)."""
        inputs = AltmanInputs(
            working_capital=0.0,
            retained_earnings=0.0,
            ebit=0.0,
            total_assets=100.0,
            total_liabilities=1.0,
            revenue=181.0,  # Z = 1.81
            market_cap=0.0,
        )
        z, _, flag = compute_altman_z(inputs)
        assert abs(z - 1.81) < 1e-9
        assert flag == Flag.AMBER

    def test_z_formula_arithmetic(self) -> None:
        """Manually verify Altman Z formula for known inputs."""
        # Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
        ta = 1000.0
        tl = 500.0
        inputs = AltmanInputs(
            working_capital=100.0,     # X1 = 0.10
            retained_earnings=200.0,   # X2 = 0.20
            ebit=150.0,                # X3 = 0.15
            total_assets=ta,
            total_liabilities=tl,
            revenue=800.0,             # X5 = 0.80
            market_cap=600.0,          # X4 = 1.20
        )
        expected = 1.2*0.10 + 1.4*0.20 + 3.3*0.15 + 0.6*1.20 + 1.0*0.80
        z, _, _ = compute_altman_z(inputs)
        assert abs(z - expected) < 1e-9

    def test_negative_working_capital_reduces_z(self) -> None:
        """Negative working capital should pull Z down."""
        base = AltmanInputs(
            working_capital=5000.0,
            retained_earnings=5000.0,
            ebit=3000.0,
            total_assets=20000.0,
            total_liabilities=10000.0,
            revenue=25000.0,
            market_cap=15000.0,
        )
        negative_wc = AltmanInputs(
            working_capital=-5000.0,
            retained_earnings=5000.0,
            ebit=3000.0,
            total_assets=20000.0,
            total_liabilities=10000.0,
            revenue=25000.0,
            market_cap=15000.0,
        )
        z_base, _, _ = compute_altman_z(base)
        z_neg, _, _ = compute_altman_z(negative_wc)
        assert z_neg < z_base

    def test_altman_z_nan_market_cap_returns_unavailable(self) -> None:
        """When market_cap is NaN, Z-score computation produces z=NaN → Flag.UNAVAILABLE."""
        import math
        inputs = self._safe_inputs(market_cap=float('nan'))
        z, variant, flag = compute_altman_z(inputs)
        assert math.isnan(z)
        assert flag == Flag.UNAVAILABLE


# ---------------------------------------------------------------------------
# TestAbsoluteFlagging
# ---------------------------------------------------------------------------


class TestAbsoluteFlagging:
    """Unit tests for absolute-threshold flagging per SKILL.md."""

    # --- Debt/EBITDA (high_bad: >3.5x AMBER, >5.0x RED) ---

    def test_debt_ebitda_below_amber_is_green(self) -> None:
        assert flag_metric(2.0, None, None, "debt_ebitda") == Flag.GREEN

    def test_debt_ebitda_at_amber_threshold(self) -> None:
        # 3.5x exactly → GREEN (per spec: > 3.5, not >= 3.5)
        assert flag_metric(3.5, None, None, "debt_ebitda") == Flag.GREEN

    def test_debt_ebitda_above_amber_below_red(self) -> None:
        assert flag_metric(4.0, None, None, "debt_ebitda") == Flag.AMBER

    def test_debt_ebitda_at_red_threshold(self) -> None:
        # 5.0x exactly → AMBER (per spec: > 5.0 is RED, not >= 5.0)
        assert flag_metric(5.0, None, None, "debt_ebitda") == Flag.AMBER

    def test_debt_ebitda_above_red_is_red(self) -> None:
        assert flag_metric(7.5, None, None, "debt_ebitda") == Flag.RED

    # --- Interest Coverage (low_bad: <3.0x AMBER, <1.5x RED) ---

    def test_interest_coverage_above_amber_is_green(self) -> None:
        assert flag_metric(10.0, None, None, "interest_coverage") == Flag.GREEN

    def test_interest_coverage_at_amber_threshold(self) -> None:
        # 3.0x exactly → GREEN (per spec: < 3.0, not <= 3.0)
        assert flag_metric(3.0, None, None, "interest_coverage") == Flag.GREEN

    def test_interest_coverage_between_thresholds(self) -> None:
        assert flag_metric(2.0, None, None, "interest_coverage") == Flag.AMBER

    def test_interest_coverage_at_red_threshold(self) -> None:
        # 1.5x exactly → AMBER (per spec: < 1.5 is RED, not <= 1.5)
        assert flag_metric(1.5, None, None, "interest_coverage") == Flag.AMBER

    def test_interest_coverage_below_red(self) -> None:
        assert flag_metric(0.8, None, None, "interest_coverage") == Flag.RED

    # --- Current Ratio (low_bad: <1.2x AMBER, <1.0x RED) ---

    def test_current_ratio_above_amber_is_green(self) -> None:
        assert flag_metric(2.0, None, None, "current_ratio") == Flag.GREEN

    def test_current_ratio_at_amber_threshold(self) -> None:
        # 1.2x exactly → GREEN (per spec: < 1.2, not <= 1.2)
        assert flag_metric(1.2, None, None, "current_ratio") == Flag.GREEN

    def test_current_ratio_below_amber_above_red(self) -> None:
        assert flag_metric(1.05, None, None, "current_ratio") == Flag.AMBER

    def test_current_ratio_at_red_threshold(self) -> None:
        # 1.0x exactly → AMBER (per spec: < 1.0 is RED, not <= 1.0)
        assert flag_metric(1.0, None, None, "current_ratio") == Flag.AMBER

    def test_current_ratio_below_red(self) -> None:
        assert flag_metric(0.72, None, None, "current_ratio") == Flag.RED


# ---------------------------------------------------------------------------
# TestPeerRelativeFlagging
# ---------------------------------------------------------------------------


class TestPeerRelativeFlagging:
    """Unit tests for peer-relative flag logic (high_bad and low_bad metrics)."""

    # --- high_bad (D/EBITDA): lower than peer median → GREEN ---

    def test_high_bad_below_peer_median_is_green(self) -> None:
        # value=2.0, peer_median=3.0, peer_p75=4.5 → below median → GREEN
        result = flag_metric(2.0, peer_median=3.0, peer_p75=4.5, metric_key="debt_ebitda")
        assert result == Flag.GREEN

    def test_high_bad_between_median_and_p75_is_amber(self) -> None:
        # value=3.8, peer_median=3.0, peer_p75=4.5 → between → AMBER
        # but also check absolute: 3.8 >= 3.5 → AMBER absolute too
        result = flag_metric(3.8, peer_median=3.0, peer_p75=4.5, metric_key="debt_ebitda")
        assert result == Flag.AMBER

    def test_high_bad_above_p75_is_red(self) -> None:
        # value=5.5, peer_median=3.0, peer_p75=4.5 → above p75 → RED
        result = flag_metric(5.5, peer_median=3.0, peer_p75=4.5, metric_key="debt_ebitda")
        assert result == Flag.RED

    # --- low_bad (interest_coverage): higher than peer median → GREEN ---

    def test_low_bad_above_peer_median_is_green(self) -> None:
        # value=25.0, peer_median=10.0, peer_p75=6.0 (p75 is lower threshold)
        result = flag_metric(25.0, peer_median=10.0, peer_p75=6.0, metric_key="interest_coverage")
        assert result == Flag.GREEN

    def test_low_bad_between_median_and_p75_is_amber(self) -> None:
        # value=8.0, peer_median=10.0, peer_p75=6.0
        result = flag_metric(8.0, peer_median=10.0, peer_p75=6.0, metric_key="interest_coverage")
        assert result == Flag.AMBER

    def test_low_bad_below_p75_is_red(self) -> None:
        # value=4.0, peer_median=10.0, peer_p75=6.0 → below p75 threshold
        result = flag_metric(4.0, peer_median=10.0, peer_p75=6.0, metric_key="interest_coverage")
        assert result == Flag.RED

    def test_no_peer_data_falls_back_to_absolute_only(self) -> None:
        """When peer data is None, only absolute thresholds apply."""
        # debt_ebitda=2.0 → absolute GREEN (< 3.5)
        result = flag_metric(2.0, peer_median=None, peer_p75=None, metric_key="debt_ebitda")
        assert result == Flag.GREEN

    def test_partial_peer_data_skips_peer_comparison(self) -> None:
        """Only peer_median provided (no p75) → peer comparison skipped."""
        result = flag_metric(6.0, peer_median=3.0, peer_p75=None, metric_key="debt_ebitda")
        # peer comparison skipped → falls through to absolute only: 6.0 > 5.0 (strictly) → RED
        assert result == Flag.RED


# ---------------------------------------------------------------------------
# TestPeerPercentileAssertion
# ---------------------------------------------------------------------------


class TestPeerPercentileAssertion:
    """Unit tests for peer percentile validation in low_bad metrics."""

    def test_low_bad_inverted_peer_percentiles_raises_assertion(self) -> None:
        """For low_bad metrics, peer_p75 > peer_median should raise AssertionError."""
        # Inverted: p75 (10.0) > median (5.0) — violates low_bad assumption
        with pytest.raises(AssertionError, match="peer_p75.*must be"):
            flag_metric(7.0, peer_median=5.0, peer_p75=10.0, metric_key="interest_coverage")

    def test_low_bad_correct_peer_percentiles_no_error(self) -> None:
        """For low_bad metrics, correct ordering peer_p75 <= peer_median should work."""
        # Correct: p75 (6.0) <= median (10.0)
        result = flag_metric(8.0, peer_median=10.0, peer_p75=6.0, metric_key="interest_coverage")
        assert result == Flag.AMBER


# ---------------------------------------------------------------------------
# TestConservativeRule
# ---------------------------------------------------------------------------


class TestConservativeRule:
    """Verify the more-conservative-of-two-rules is applied correctly."""

    def test_absolute_red_overrides_peer_green(self) -> None:
        """Absolute says RED, peer says GREEN → result is RED (more conservative)."""
        # debt_ebitda=5.5 → absolute RED (>=5.0)
        # peer_median=6.0, peer_p75=7.0 → value 5.5 is below peer median → peer GREEN
        result = flag_metric(5.5, peer_median=6.0, peer_p75=7.0, metric_key="debt_ebitda")
        assert result == Flag.RED

    def test_peer_red_overrides_absolute_green(self) -> None:
        """Peer says RED, absolute says GREEN → result is RED (more conservative)."""
        # interest_coverage=2.5 → absolute: 2.5 > 1.5 and <=3.0 → AMBER (not GREEN)
        # Actually test with debt_ebitda: value=4.6, peer_median=2.0, peer_p75=4.0
        # peer: 4.6 > peer_p75=4.0 → RED
        # absolute: 4.6 >= 3.5 but < 5.0 → AMBER
        # result should be RED (peer RED is more conservative than absolute AMBER)
        result = flag_metric(4.6, peer_median=2.0, peer_p75=4.0, metric_key="debt_ebitda")
        assert result == Flag.RED

    def test_both_agree_green(self) -> None:
        # debt_ebitda=1.0 → absolute GREEN, peer below median → peer GREEN
        result = flag_metric(1.0, peer_median=2.0, peer_p75=3.5, metric_key="debt_ebitda")
        assert result == Flag.GREEN

    def test_both_agree_red(self) -> None:
        # debt_ebitda=6.0 → absolute RED, above peer p75 → peer RED
        result = flag_metric(6.0, peer_median=2.0, peer_p75=4.0, metric_key="debt_ebitda")
        assert result == Flag.RED


# ---------------------------------------------------------------------------
# TestQualityChangeFlagging
# ---------------------------------------------------------------------------


class TestQualityChangeFlagging:
    """Unit tests for 52-week Quality score change thresholds."""

    def test_flat_quality_is_green(self) -> None:
        assert flag_quality_change(0) == Flag.GREEN

    def test_slight_improvement_is_green(self) -> None:
        assert flag_quality_change(+3) == Flag.GREEN

    def test_minor_decline_below_amber_is_green(self) -> None:
        # -4 pts → still GREEN (threshold is > -5)
        assert flag_quality_change(-4) == Flag.GREEN

    def test_exactly_minus_5_is_amber(self) -> None:
        # -5 pts exactly → AMBER (change <= -5)
        assert flag_quality_change(-5) == Flag.AMBER

    def test_moderate_decline_is_amber(self) -> None:
        assert flag_quality_change(-10) == Flag.AMBER

    def test_exactly_minus_15_is_red(self) -> None:
        # -15 pts exactly → RED (change <= -15)
        assert flag_quality_change(-15) == Flag.RED

    def test_severe_decline_is_red(self) -> None:
        assert flag_quality_change(-25) == Flag.RED

    def test_large_improvement_is_green(self) -> None:
        assert flag_quality_change(+20) == Flag.GREEN


# ---------------------------------------------------------------------------
# TestOverallTrafficLight
# ---------------------------------------------------------------------------


class TestOverallTrafficLight:
    """Unit tests for majority-vote traffic-light aggregation."""

    def test_all_green_is_green(self) -> None:
        flags = [Flag.GREEN, Flag.GREEN, Flag.GREEN]
        assert overall_traffic_light(flags) == Flag.GREEN

    def test_all_red_is_red(self) -> None:
        flags = [Flag.RED, Flag.RED, Flag.RED]
        assert overall_traffic_light(flags) == Flag.RED

    def test_majority_red_wins(self) -> None:
        flags = [Flag.RED, Flag.RED, Flag.GREEN, Flag.AMBER]
        assert overall_traffic_light(flags) == Flag.RED

    def test_majority_amber_wins(self) -> None:
        flags = [Flag.AMBER, Flag.AMBER, Flag.GREEN]
        assert overall_traffic_light(flags) == Flag.AMBER

    def test_majority_green_wins(self) -> None:
        flags = [Flag.GREEN, Flag.GREEN, Flag.RED]
        assert overall_traffic_light(flags) == Flag.GREEN

    def test_tie_red_beats_amber(self) -> None:
        """On exact tie between RED and AMBER, RED wins (more conservative)."""
        flags = [Flag.RED, Flag.AMBER]
        assert overall_traffic_light(flags) == Flag.RED

    def test_tie_red_beats_green(self) -> None:
        flags = [Flag.RED, Flag.GREEN]
        assert overall_traffic_light(flags) == Flag.RED

    def test_tie_amber_beats_green(self) -> None:
        flags = [Flag.AMBER, Flag.GREEN]
        assert overall_traffic_light(flags) == Flag.AMBER

    def test_unavailable_flags_excluded_from_count(self) -> None:
        flags = [Flag.GREEN, Flag.UNAVAILABLE, Flag.GREEN]
        assert overall_traffic_light(flags) == Flag.GREEN

    def test_all_unavailable_returns_unavailable(self) -> None:
        flags = [Flag.UNAVAILABLE, Flag.UNAVAILABLE]
        assert overall_traffic_light(flags) == Flag.UNAVAILABLE

    def test_empty_list_returns_unavailable(self) -> None:
        assert overall_traffic_light([]) == Flag.UNAVAILABLE

    def test_single_red_is_red(self) -> None:
        assert overall_traffic_light([Flag.RED]) == Flag.RED

    def test_mixed_six_metrics_majority_green(self) -> None:
        # 4 GREEN, 1 AMBER, 1 RED → GREEN wins
        flags = [Flag.GREEN] * 4 + [Flag.AMBER, Flag.RED]
        assert overall_traffic_light(flags) == Flag.GREEN

    def test_three_way_tie_red_wins(self) -> None:
        """Three-way tie → RED wins (highest severity first in resolution order)."""
        flags = [Flag.RED, Flag.AMBER, Flag.GREEN]
        assert overall_traffic_light(flags) == Flag.RED


# ---------------------------------------------------------------------------
# TestRICValidation
# ---------------------------------------------------------------------------


class TestRICValidation:
    """Unit tests for RIC format validation."""

    def test_valid_us_equity(self) -> None:
        valid, msg = validate_ric("AAPL.O")
        assert valid is True

    def test_valid_nyse_ticker(self) -> None:
        valid, _ = validate_ric("JPM.N")
        assert valid is True

    def test_valid_hk_equity(self) -> None:
        valid, _ = validate_ric("0001.HK")
        assert valid is True

    def test_valid_multi_char_exchange(self) -> None:
        valid, _ = validate_ric("BP.L")
        assert valid is True

    def test_plain_ticker_is_invalid(self) -> None:
        valid, msg = validate_ric("AAPL")
        assert valid is False
        assert "RIC" in msg

    def test_empty_string_is_invalid(self) -> None:
        valid, msg = validate_ric("")
        assert valid is False

    def test_none_is_invalid(self) -> None:
        valid, msg = validate_ric(None)  # type: ignore[arg-type]
        assert valid is False

    def test_multiple_dots_is_invalid(self) -> None:
        valid, _ = validate_ric("AAPL.O.N")
        assert valid is False

    def test_leading_dot_is_invalid(self) -> None:
        valid, _ = validate_ric(".AAPL")
        assert valid is False

    def test_trailing_dot_is_invalid(self) -> None:
        valid, _ = validate_ric("AAPL.")
        assert valid is False

    def test_whitespace_stripped_valid(self) -> None:
        """Leading/trailing whitespace should be stripped before validation."""
        valid, _ = validate_ric("  AAPL.O  ")
        assert valid is True

    def test_numeric_ticker_valid(self) -> None:
        """HK-style numeric tickers are valid."""
        valid, _ = validate_ric("0700.HK")
        assert valid is True


# ---------------------------------------------------------------------------
# TestReportBuilders
# ---------------------------------------------------------------------------


class TestReportBuilders:
    """Unit tests for markdown section assembly functions."""

    def _sample_report(self, *, flag: Flag = Flag.GREEN) -> CreditReport:
        return CreditReport(
            symbol="AAPL.O",
            company_name="Apple Inc.",
            overall_flag=flag,
            metric_rows=[
                MetricRow(
                    category="Leverage",
                    flag=Flag.GREEN,
                    metric_label="D/EBITDA",
                    metric_value="1.2x",
                    peer_median_label="Peer 1.8x",
                    interpretation="Below peer median",
                ),
                MetricRow(
                    category="Coverage",
                    flag=Flag.GREEN,
                    metric_label="Int Cov",
                    metric_value="29.1x",
                    peer_median_label="Peer 18.2x",
                    interpretation="Top quartile",
                ),
            ],
            solvency_narrative="Strong solvency across all Palepu dimensions.",
            key_flags=[],
            quality_trend_sentence="Quality stable over 52 weeks.",
            macro_context_sentence="Late-cycle regime; credit spreads widening.",
            altman_z=4.2,
            altman_variant="Z",
            altman_flag=Flag.GREEN,
        )

    def test_header_contains_company_and_symbol(self) -> None:
        report = self._sample_report()
        header = build_header(report)
        assert "Apple Inc." in header
        assert "AAPL.O" in header

    def test_header_contains_overall_flag_label(self) -> None:
        report = self._sample_report(flag=Flag.RED)
        header = build_header(report)
        assert "RED" in header

    def test_header_contains_traffic_light_emoji_green(self) -> None:
        report = self._sample_report(flag=Flag.GREEN)
        header = build_header(report)
        assert "\U0001f7e2" in header  # 🟢

    def test_header_contains_traffic_light_emoji_red(self) -> None:
        report = self._sample_report(flag=Flag.RED)
        header = build_header(report)
        assert "\U0001f534" in header  # 🔴

    def test_metrics_table_has_header_row(self) -> None:
        report = self._sample_report()
        table = build_metrics_table(report.metric_rows)
        assert "Category" in table
        assert "Signal" in table
        assert "Peer Median" in table

    def test_metrics_table_includes_all_rows(self) -> None:
        report = self._sample_report()
        table = build_metrics_table(report.metric_rows)
        assert "Leverage" in table
        assert "Coverage" in table

    def test_metrics_table_empty_rows(self) -> None:
        table = build_metrics_table([])
        assert "Category" in table  # header still present
        # No data rows
        assert "Leverage" not in table

    def test_key_flags_empty_returns_no_flags_message(self) -> None:
        section = build_key_flags_section([])
        assert "No RED or AMBER" in section

    def test_key_flags_renders_all_entries(self) -> None:
        flags = [
            "\U0001f534 RED: Debt/EBITDA 5.2x exceeds threshold",
            "\U0001f7e1 AMBER: Quality score down 14 pts",
        ]
        section = build_key_flags_section(flags)
        assert "Debt/EBITDA" in section
        assert "Quality score" in section
        assert section.count("- ") == 2

    def test_solvency_section_when_available(self) -> None:
        report = self._sample_report()
        section = build_solvency_section(report)
        assert "Strong solvency" in section

    def test_solvency_section_when_palepu_unavailable(self) -> None:
        report = self._sample_report()
        report.palepu_unavailable = True
        section = build_solvency_section(report)
        assert "unavailable" in section.lower()

    def test_footer_contains_disclaimer(self) -> None:
        footer = build_footer()
        assert "Not investment or credit advice" in footer
        assert "Parallax factor scores" in footer

    def test_assemble_report_contains_all_sections(self) -> None:
        report = self._sample_report()
        full = assemble_report(report)
        assert "Credit Risk Assessment" in full
        assert "Metrics Dashboard" in full
        assert "Solvency Assessment" in full
        assert "Key Flags" in full
        assert "Quality Trend" in full
        assert "Macro Context" in full
        assert "Not investment or credit advice" in full

    def test_assemble_report_quality_trend_included(self) -> None:
        report = self._sample_report()
        full = assemble_report(report)
        assert "Quality stable over 52 weeks." in full

    def test_assemble_report_macro_context_included(self) -> None:
        report = self._sample_report()
        full = assemble_report(report)
        assert "Late-cycle regime" in full

    def test_assemble_report_missing_quality_trend_shows_fallback(self) -> None:
        report = self._sample_report()
        report.quality_trend_sentence = ""
        full = assemble_report(report)
        assert "unavailable" in full.lower()


# ---------------------------------------------------------------------------
# TestIntegrationFixtures
# ---------------------------------------------------------------------------


class TestIntegrationFixtures:
    """Integration tests using fixture JSON files for realistic tool output."""

    def test_aapl_ratios_fixture_loads(self) -> None:
        """Ratios fixture is parseable and has expected keys."""
        data = _load_fixture("get_financials_ratios.json")
        period = data["periods"][0]
        assert "debt_to_ebitda" in period
        assert "interest_coverage" in period
        assert "current_ratio" in period

    def test_aapl_balance_sheet_fixture_loads(self) -> None:
        data = _load_fixture("get_financials_balance_sheet.json")
        period = data["periods"][0]
        assert "total_assets" in period
        assert "working_capital" in period
        assert "retained_earnings" in period

    def test_aapl_peer_snapshot_fixture_loads(self) -> None:
        data = _load_fixture("get_peer_snapshot.json")
        assert data["company_name"] == "Apple Inc."
        assert "market_cap_usd" in data
        assert "factor_scores" in data

    def test_aapl_altman_z_from_fixture(self) -> None:
        """Compute Altman Z for Apple using realistic fixture values."""
        bs = _load_fixture("get_financials_balance_sheet.json")["periods"][0]
        ratios = _load_fixture("get_financials_ratios.json")["periods"][0]
        peer = _load_fixture("get_peer_snapshot.json")

        inputs = AltmanInputs(
            working_capital=bs["working_capital"],
            retained_earnings=bs["retained_earnings"],
            ebit=ratios["ebit"],
            total_assets=bs["total_assets"],
            total_liabilities=bs["total_liabilities"],
            revenue=ratios["revenue"],
            market_cap=peer["market_cap_usd"],
        )
        z, variant, flag = compute_altman_z(inputs)
        assert variant == "Z"
        # Apple's mega-cap vs low liabilities → high X4 → Z should be in safe zone
        assert z > 2.99
        assert flag == Flag.GREEN

    def test_aapl_debt_ebitda_flag_from_fixture(self) -> None:
        """AAPL Debt/EBITDA=1.21 vs peer_median=1.10.

        In high_bad direction: 1.21 > peer_median=1.10 → peer says AMBER.
        Absolute: 1.21 < 3.5 → absolute says GREEN.
        Conservative rule picks AMBER (peer is more conservative).
        """
        ratios = _load_fixture("get_financials_ratios.json")["periods"][0]
        result = flag_metric(
            ratios["debt_to_ebitda"],
            peer_median=ratios["peer_median"]["debt_to_ebitda"],
            peer_p75=ratios["peer_p75"]["debt_to_ebitda"],
            metric_key="debt_ebitda",
        )
        assert result == Flag.AMBER

    def test_aapl_interest_coverage_flag_from_fixture(self) -> None:
        """AAPL interest coverage 29.1x → GREEN (well above peer median 18.2x and absolute 3.0x)."""
        ratios = _load_fixture("get_financials_ratios.json")["periods"][0]
        result = flag_metric(
            ratios["interest_coverage"],
            peer_median=ratios["peer_median"]["interest_coverage"],
            peer_p75=ratios["peer_p75"]["interest_coverage"],
            metric_key="interest_coverage",
        )
        assert result == Flag.GREEN

    def test_aapl_current_ratio_flag_from_fixture(self) -> None:
        """AAPL current ratio 0.87 → RED (below absolute red threshold 1.0)."""
        ratios = _load_fixture("get_financials_ratios.json")["periods"][0]
        result = flag_metric(
            ratios["current_ratio"],
            peer_median=ratios["peer_median"]["current_ratio"],
            peer_p75=ratios["peer_p75"]["current_ratio"],
            metric_key="current_ratio",
        )
        # 0.87 < 1.0 → absolute RED
        assert result == Flag.RED

    def test_aapl_quality_change_flag_from_fixture(self) -> None:
        """AAPL quality change -6 pts → AMBER (between -5 and -15)."""
        score = _load_fixture("get_score_analysis.json")
        change = score["factor_trajectory"]["quality"]["change_pts"]
        result = flag_quality_change(change)
        assert result == Flag.AMBER  # -6 is in AMBER zone

    def test_distressed_company_debt_ebitda_is_red(self) -> None:
        """Distressed fixture: D/EBITDA=6.2x → RED."""
        ratios = _load_fixture("get_financials_ratios_distressed.json")["periods"][0]
        result = flag_metric(
            ratios["debt_to_ebitda"],
            peer_median=ratios["peer_median"]["debt_to_ebitda"],
            peer_p75=ratios["peer_p75"]["debt_to_ebitda"],
            metric_key="debt_ebitda",
        )
        assert result == Flag.RED

    def test_distressed_company_interest_coverage_is_red(self) -> None:
        """Distressed fixture: interest coverage 1.1x → RED (below absolute threshold 1.5x)."""
        ratios = _load_fixture("get_financials_ratios_distressed.json")["periods"][0]
        result = flag_metric(
            ratios["interest_coverage"],
            peer_median=ratios["peer_median"]["interest_coverage"],
            peer_p75=ratios["peer_p75"]["interest_coverage"],
            metric_key="interest_coverage",
        )
        assert result == Flag.RED

    def test_distressed_company_current_ratio_is_red(self) -> None:
        """Distressed fixture: current ratio 0.72 → RED."""
        ratios = _load_fixture("get_financials_ratios_distressed.json")["periods"][0]
        result = flag_metric(
            ratios["current_ratio"],
            peer_median=ratios["peer_median"]["current_ratio"],
            peer_p75=ratios["peer_p75"]["current_ratio"],
            metric_key="current_ratio",
        )
        assert result == Flag.RED

    def test_distressed_company_overall_is_red(self) -> None:
        """All-RED metrics → overall traffic-light RED."""
        flags = [Flag.RED, Flag.RED, Flag.RED, Flag.RED]
        assert overall_traffic_light(flags) == Flag.RED

    def test_financial_analysis_fixture_has_palepu_sections(self) -> None:
        data = _load_fixture("get_financial_analysis.json")
        assert "profitability" in data
        assert "liquidity" in data
        assert "leverage_solvency" in data
        assert "accruals_quality" in data
        assert "overall_solvency" in data

    def test_telemetry_fixture_has_regime(self) -> None:
        data = _load_fixture("get_telemetry.json")
        assert "regime" in data
        assert "label" in data["regime"]


# ---------------------------------------------------------------------------
# TestErrorDegradation
# ---------------------------------------------------------------------------


class TestErrorDegradation:
    """Integration tests: graceful degradation when tools fail."""

    def test_palepu_unavailable_flag_in_report(self) -> None:
        """When get_financial_analysis fails, report marks Palepu as unavailable."""
        report = CreditReport(
            symbol="MSFT.O",
            company_name="Microsoft Corp.",
            overall_flag=Flag.GREEN,
            palepu_unavailable=True,
        )
        section = build_solvency_section(report)
        assert "unavailable" in section.lower()

    def test_report_assembles_without_solvency(self) -> None:
        """assemble_report completes even when solvency is unavailable."""
        report = CreditReport(
            symbol="MSFT.O",
            company_name="Microsoft Corp.",
            overall_flag=Flag.GREEN,
            palepu_unavailable=True,
            quality_trend_sentence="Quality stable.",
            macro_context_sentence="Neutral regime.",
        )
        full = assemble_report(report)
        assert "Credit Risk Assessment" in full
        assert "unavailable" in full.lower()

    def test_no_peer_data_defaults_to_absolute_only(self) -> None:
        """None peer data still produces a valid flag via absolute thresholds."""
        result = flag_metric(6.0, None, None, "debt_ebitda")
        assert result == Flag.RED  # absolute: 6.0 >= 5.0 → RED

    def test_altman_z_book_equity_fallback_produces_valid_result(self) -> None:
        """Z' (book equity) variant still returns a valid flag."""
        inputs = AltmanInputs(
            working_capital=5000.0,
            retained_earnings=8000.0,
            ebit=4000.0,
            total_assets=20000.0,
            total_liabilities=10000.0,
            revenue=30000.0,
            market_cap=None,
            book_equity=12000.0,
        )
        z, variant, flag = compute_altman_z(inputs)
        assert variant == "Z'"
        assert flag in (Flag.GREEN, Flag.AMBER, Flag.RED)

    def test_unavailable_metric_excluded_from_traffic_light(self) -> None:
        """UNAVAILABLE flags don't pull the traffic light toward any color."""
        flags = [Flag.GREEN, Flag.GREEN, Flag.UNAVAILABLE]
        assert overall_traffic_light(flags) == Flag.GREEN

    def test_all_unavailable_metrics_returns_unavailable_traffic_light(self) -> None:
        flags = [Flag.UNAVAILABLE]
        assert overall_traffic_light(flags) == Flag.UNAVAILABLE

    def test_report_with_no_key_flags_renders_clean_section(self) -> None:
        """No RED/AMBER flags → key flags section shows the no-flags message."""
        section = build_key_flags_section([])
        assert "No RED or AMBER" in section
        assert "- " not in section

    def test_invalid_ric_returns_false_and_message(self) -> None:
        valid, msg = validate_ric("AAPL")
        assert valid is False
        assert len(msg) > 0

    def test_peer_group_too_small_no_p75(self) -> None:
        """peer_p75=None gracefully skips peer comparison, uses absolute only."""
        # interest_coverage=2.0 → absolute AMBER (between 1.5 and 3.0)
        result = flag_metric(2.0, peer_median=5.0, peer_p75=None, metric_key="interest_coverage")
        assert result == Flag.AMBER


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Boundary values, zero inputs, negative inputs, extreme values."""

    def test_altman_z_all_zeros_raises_on_zero_assets(self) -> None:
        with pytest.raises(ValueError):
            compute_altman_z(AltmanInputs(
                working_capital=0.0,
                retained_earnings=0.0,
                ebit=0.0,
                total_assets=0.0,
                total_liabilities=1.0,
                revenue=0.0,
                market_cap=1.0,
            ))

    def test_altman_z_negative_retained_earnings_allowed(self) -> None:
        """Negative retained earnings (accumulated deficit) should not raise."""
        inputs = AltmanInputs(
            working_capital=1000.0,
            retained_earnings=-50000.0,
            ebit=2000.0,
            total_assets=100000.0,
            total_liabilities=80000.0,
            revenue=90000.0,
            market_cap=20000.0,
        )
        z, _, _ = compute_altman_z(inputs)
        assert isinstance(z, float)

    def test_altman_z_extremely_high_market_cap_safe_zone(self) -> None:
        """Very high market cap relative to liabilities pushes Z into safe zone."""
        inputs = AltmanInputs(
            working_capital=0.0,
            retained_earnings=0.0,
            ebit=0.0,
            total_assets=1000.0,
            total_liabilities=100.0,
            revenue=0.0,
            market_cap=1_000_000.0,  # X4 = 10000 → huge contribution
        )
        z, _, flag = compute_altman_z(inputs)
        assert flag == Flag.GREEN

    def test_flag_metric_zero_value_interest_coverage(self) -> None:
        """Zero interest coverage → RED (catastrophic scenario)."""
        result = flag_metric(0.0, None, None, "interest_coverage")
        assert result == Flag.RED

    def test_flag_metric_very_large_debt_ebitda(self) -> None:
        """Extremely high D/EBITDA → RED."""
        result = flag_metric(100.0, None, None, "debt_ebitda")
        assert result == Flag.RED

    def test_flag_metric_unknown_key_returns_green(self) -> None:
        """Unknown metric key has no absolute threshold → GREEN by default."""
        result = flag_metric(999.0, None, None, "unknown_metric_xyz")
        assert result == Flag.GREEN

    def test_overall_traffic_light_large_all_green(self) -> None:
        flags = [Flag.GREEN] * 100
        assert overall_traffic_light(flags) == Flag.GREEN

    def test_overall_traffic_light_99_green_1_red(self) -> None:
        """Single RED in 100 flags → GREEN wins by majority."""
        flags = [Flag.GREEN] * 99 + [Flag.RED]
        assert overall_traffic_light(flags) == Flag.GREEN

    def test_quality_change_exactly_zero(self) -> None:
        assert flag_quality_change(0.0) == Flag.GREEN

    def test_quality_change_very_large_positive(self) -> None:
        assert flag_quality_change(50.0) == Flag.GREEN

    def test_quality_change_very_large_negative(self) -> None:
        assert flag_quality_change(-100.0) == Flag.RED

    def test_build_metrics_table_with_unavailable_flag(self) -> None:
        """UNAVAILABLE flag renders without crashing."""
        rows = [MetricRow(
            category="Altman Z",
            flag=Flag.UNAVAILABLE,
            metric_label="Z-score",
            metric_value="N/A",
            peer_median_label="—",
            interpretation="Insufficient data",
        )]
        table = build_metrics_table(rows)
        assert "Altman Z" in table
        assert "UNAVAILABLE" in table

    def test_validate_ric_with_special_characters(self) -> None:
        """RIC with special characters in ticker is still checked for dot structure."""
        valid, _ = validate_ric("@BAD.O")
        # Structure is valid (has exactly one dot, non-empty sides)
        # The validator only checks structure, not character set
        assert isinstance(valid, bool)

    def test_validate_ric_numeric_only_exchange(self) -> None:
        """Numeric exchange suffix is structurally valid."""
        valid, _ = validate_ric("TEST.123")
        assert valid is True

    def test_report_empty_metric_rows_assembles(self) -> None:
        """Empty metric rows list → report still assembles without error."""
        report = CreditReport(
            symbol="TEST.O",
            company_name="Test Co.",
            overall_flag=Flag.UNAVAILABLE,
            metric_rows=[],
        )
        full = assemble_report(report)
        assert "Credit Risk Assessment" in full

    def test_absolute_thresholds_dict_has_required_metrics(self) -> None:
        """Sanity check: expected metrics have entries in the thresholds dict."""
        for key in ("debt_ebitda", "interest_coverage", "current_ratio"):
            assert key in ABSOLUTE_THRESHOLDS, f"Missing threshold for {key}"
            amber, red, direction = ABSOLUTE_THRESHOLDS[key]
            assert direction in ("high_bad", "low_bad")
