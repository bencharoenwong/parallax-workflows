"""Pure-logic layer for /parallax-credit-lens skill — MCP-free, fully unit-testable."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Flag(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"
    UNAVAILABLE = "UNAVAILABLE"


EMOJI = {
    Flag.GREEN: "\U0001f7e2",   # 🟢
    Flag.AMBER: "\U0001f7e1",   # 🟡
    Flag.RED: "\U0001f534",     # 🔴
    Flag.UNAVAILABLE: "➖", # ➖
}


# (amber_threshold, red_threshold, direction)
# direction="high_bad"  → higher value is worse (e.g. D/EBITDA)
# direction="low_bad"   → lower value is worse  (e.g. Interest Coverage)
ABSOLUTE_THRESHOLDS: dict[str, tuple[float, float, str]] = {
    "debt_ebitda":         (3.5, 5.0, "high_bad"),
    "interest_coverage":   (3.0, 1.5, "low_bad"),
    "current_ratio":       (1.2, 1.0, "low_bad"),
    # Altman Z handled separately via zone logic
    # Quality score change handled separately (sign-aware)
}


# Direction for every metric the dashboard flags, including the ones that carry
# no absolute credit band. A metric is peer-comparable whether or not the market
# publishes a fixed threshold for it, so direction lives here rather than being
# read off ABSOLUTE_THRESHOLDS; keys absent from both get no peer comparison.
METRIC_DIRECTIONS: dict[str, str] = {
    "debt_ebitda":              "high_bad",
    "debt_equity":              "high_bad",
    "debt_assets":              "high_bad",
    "interest_coverage":        "low_bad",
    "ebitda_interest_coverage": "low_bad",
    "current_ratio":            "low_bad",
    "quick_ratio":              "low_bad",
    "ebitda_margin":            "low_bad",
    "ebit_margin":              "low_bad",
    "fcf_margin":               "low_bad",
}


@dataclass
class AltmanInputs:
    """All values in consistent currency units; market_cap=None triggers Z' variant."""
    working_capital: float
    retained_earnings: float
    ebit: float
    total_assets: float
    total_liabilities: float
    revenue: float
    market_cap: Optional[float] = None   # None → use book equity variant (Z')
    book_equity: Optional[float] = None  # fallback for X4


def compute_altman_z(inputs: AltmanInputs) -> tuple[float, str, Flag]:
    """Return (z_score, variant_label, flag).

    variant_label is "Z" (market-cap) or "Z'" (book-equity fallback).
    Raises ValueError if total_assets is zero.
    """
    if inputs.total_assets == 0:
        raise ValueError("total_assets must be non-zero")

    x1 = inputs.working_capital / inputs.total_assets
    x2 = inputs.retained_earnings / inputs.total_assets
    x3 = inputs.ebit / inputs.total_assets
    x5 = inputs.revenue / inputs.total_assets

    if inputs.market_cap is not None:
        x4_numerator = inputs.market_cap
        variant = "Z"
    elif inputs.book_equity is not None:
        x4_numerator = inputs.book_equity
        variant = "Z'"
    else:
        raise ValueError(
            "Either market_cap or book_equity must be provided for X4"
        )

    if inputs.total_liabilities == 0:
        raise ValueError("total_liabilities must be non-zero for X4 computation")

    x4 = x4_numerator / inputs.total_liabilities

    z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5

    flag = _altman_zone_flag(z)
    return z, variant, flag


def _altman_zone_flag(z: float) -> Flag:
    """Map Altman Z value to credit flag per SKILL.md thresholds."""
    if math.isnan(z):
        return Flag.UNAVAILABLE
    if z > 2.99:
        return Flag.GREEN
    if z >= 1.81:
        return Flag.AMBER
    return Flag.RED


# ---------------------------------------------------------------------------
# Per-metric flagging
# ---------------------------------------------------------------------------


def flag_metric(
    value: float,
    peer_median: Optional[float],
    peer_p75: Optional[float],
    metric_key: str,
) -> Flag:
    """Assign GREEN/AMBER/RED by applying both peer-relative and absolute rules; use more conservative result.

    Raises ValueError for a key in neither registry, and returns UNAVAILABLE
    when the key is registered but nothing can actually be applied to it. Both
    guard the same failure: a metric no rule can judge must not report as
    healthy. On a credit tool the silent direction is the dangerous one.
    """
    known = metric_key in METRIC_DIRECTIONS or metric_key in ABSOLUTE_THRESHOLDS
    if not known:
        # A mistyped key is the realistic case, and it used to return GREEN on
        # any value at all. Fail loudly instead of scoring a metric that was
        # never registered.
        raise ValueError(
            f"unregistered metric_key {metric_key!r}; add it to "
            f"METRIC_DIRECTIONS (and ABSOLUTE_THRESHOLDS if it has a fixed "
            f"band) before flagging it. Known keys: "
            f"{sorted(set(METRIC_DIRECTIONS) | set(ABSOLUTE_THRESHOLDS))}"
        )

    has_peer = peer_median is not None and peer_p75 is not None
    has_absolute = metric_key in ABSOLUTE_THRESHOLDS
    if not has_peer and not has_absolute:
        # Registered, but this run has no peer row and the metric carries no
        # fixed band — so there is no rule to apply. Five of the registered
        # keys hit this whenever the peer response omits them.
        return Flag.UNAVAILABLE

    peer_flag = _peer_relative_flag(value, peer_median, peer_p75, metric_key)
    abs_flag = _absolute_flag(value, metric_key)

    # More conservative = higher severity
    return _worse_flag(peer_flag, abs_flag)


def _direction(metric_key: str) -> Optional[str]:
    if metric_key in METRIC_DIRECTIONS:
        return METRIC_DIRECTIONS[metric_key]
    if metric_key in ABSOLUTE_THRESHOLDS:
        return ABSOLUTE_THRESHOLDS[metric_key][2]
    return None


def _peer_relative_flag(
    value: float,
    peer_median: Optional[float],
    peer_p75: Optional[float],
    metric_key: str,
) -> Flag:
    if peer_median is None or peer_p75 is None:
        return Flag.GREEN  # No peer data → neutral, let absolute rule decide

    direction = _direction(metric_key)
    if direction is None:
        return Flag.GREEN  # Unknown metric → neutral

    # Validate peer percentile ordering for low_bad metrics
    if direction == "low_bad":
        if not (peer_p75 <= peer_median):
            raise ValueError(
                f"peer_p75 ({peer_p75}) must be <= peer_median ({peer_median}) for {metric_key} (low_bad direction)"
            )

    if direction == "high_bad":
        if value <= peer_median:
            return Flag.GREEN
        if value <= peer_p75:
            return Flag.AMBER
        return Flag.RED
    else:
        if value >= peer_median:
            return Flag.GREEN
        if value >= peer_p75:
            return Flag.AMBER
        return Flag.RED


def _absolute_flag(value: float, metric_key: str) -> Flag:
    if metric_key not in ABSOLUTE_THRESHOLDS:
        return Flag.GREEN  # No absolute threshold defined

    amber_thresh, red_thresh, direction = ABSOLUTE_THRESHOLDS[metric_key]

    if direction == "high_bad":
        if value > red_thresh:
            return Flag.RED
        if value > amber_thresh:
            return Flag.AMBER
        return Flag.GREEN
    else:
        # low_bad: below amber_thresh → AMBER, below red_thresh → RED
        if value < red_thresh:
            return Flag.RED
        if value < amber_thresh:
            return Flag.AMBER
        return Flag.GREEN


def _flag_rank(flag: Flag) -> int:
    return {Flag.GREEN: 0, Flag.AMBER: 1, Flag.RED: 2, Flag.UNAVAILABLE: -1}[flag]


def _worse_flag(a: Flag, b: Flag) -> Flag:
    """Return whichever flag has higher severity."""
    if a == Flag.UNAVAILABLE:
        return b
    if b == Flag.UNAVAILABLE:
        return a
    return a if _flag_rank(a) >= _flag_rank(b) else b


# ---------------------------------------------------------------------------
# Quality score change flag
# ---------------------------------------------------------------------------


# The bands below are stated to one decimal place, and a caller reaches them by
# subtracting two scores, which is not exact in IEEE-754. 3.6 - 4.1 is
# -0.49999999999999956, not -0.5, so a true -0.5 decline would test as outside
# the AMBER band and flag GREEN. 14 of the 10,201 one-decimal pairs in 0-10 land
# one ULP outside their band this way.
#
# Which series reaches this matters. `get_score_analysis.data[].quality` is an
# integer 0-10, so a quality-on-quality subtraction is exact and never trips
# this. The one-decimal series is `data[].total`, and any caller comparing
# totals — or a rebased/interpolated quality series — does trip it. The
# tolerance is six orders of magnitude below the 0.1 grid and four below the
# 0.05 half-band, so it cannot pull a genuinely different value across a
# boundary; it is cheap enough to keep for the callers that need it.
_BAND_TOL = 1e-9


def quality_change_pts(current: float, prior: float) -> float:
    """52-week change in a score, snapped back onto the one-decimal grid.

    Prefer this over a bare ``current - prior`` when feeding
    ``flag_quality_change``: the scores are published to one decimal, so the
    difference is a one-decimal quantity and the extra binary digits are an
    artifact of the subtraction, not signal.
    """
    return round(current - prior, 10)


def flag_quality_change(change_pts: float) -> Flag:
    """AMBER: change ≤ -0.5 pts, RED: change ≤ -1.5 pts (52w deterioration).

    Bands are on the 0-10 per-security scale that `get_score_analysis` returns.
    The previous -5 / -15 bands were on a 0-100 basis. The largest possible
    decline on a 0-10 score is -10, so the RED band could never fire and the
    AMBER band fired only on a catastrophic decline of 5 points or more.

    Boundary values are inclusive and are compared with ``_BAND_TOL`` so that a
    change arriving one ULP outside its band still lands in it.
    """
    if change_pts <= -1.5 + _BAND_TOL:
        return Flag.RED
    if change_pts <= -0.5 + _BAND_TOL:
        return Flag.AMBER
    return Flag.GREEN


# ---------------------------------------------------------------------------
# Overall traffic-light (majority wins)
# ---------------------------------------------------------------------------


def overall_traffic_light(flags: list[Flag]) -> Flag:
    """Aggregate flags by majority count (RED > AMBER > GREEN on tie).

    UNAVAILABLE flags are excluded from the count.
    If all flags are UNAVAILABLE, return UNAVAILABLE.
    """
    counts = {Flag.GREEN: 0, Flag.AMBER: 0, Flag.RED: 0}
    for f in flags:
        if f in counts:
            counts[f] += 1

    total = sum(counts.values())
    if total == 0:
        return Flag.UNAVAILABLE

    # Majority wins; on tie, RED beats AMBER beats GREEN
    max_count = max(counts.values())
    for severity in [Flag.RED, Flag.AMBER, Flag.GREEN]:
        if counts[severity] == max_count:
            return severity

    return Flag.UNAVAILABLE  # unreachable


def validate_ric(symbol: str) -> tuple[bool, str]:
    """Return (is_valid, message).

    A valid RIC must contain exactly one dot separating a non-empty ticker
    from a non-empty exchange suffix.
    Examples: AAPL.O, JPM.N, 0001.HK
    """
    if not isinstance(symbol, str) or not symbol.strip():
        return False, "Symbol must be a non-empty string"
    parts = symbol.strip().split(".")
    if len(parts) != 2:
        return False, f"'{symbol}' is not in RIC format (expected TICKER.EXCHANGE)"
    ticker, exchange = parts
    if not ticker or not exchange:
        return False, f"'{symbol}' has empty ticker or exchange suffix"
    return True, "OK"


@dataclass
class MetricRow:
    category: str
    flag: Flag
    metric_label: str
    metric_value: str
    peer_median_label: str
    interpretation: str


@dataclass
class CreditReport:
    symbol: str
    company_name: str
    overall_flag: Flag
    metric_rows: list[MetricRow] = field(default_factory=list)
    solvency_narrative: str = ""
    # `get_financial_analysis` returns a liquidity read alongside the solvency
    # one. Both come from the same call, so both share `palepu_unavailable`.
    liquidity_narrative: str = ""
    key_flags: list[str] = field(default_factory=list)       # RED + AMBER bullets
    quality_trend_sentence: str = ""
    macro_context_sentence: str = ""
    altman_z: Optional[float] = None
    altman_variant: str = "Z"
    altman_flag: Flag = Flag.UNAVAILABLE
    palepu_unavailable: bool = False


def build_header(report: CreditReport) -> str:
    emoji = EMOJI.get(report.overall_flag, "")
    return (
        f"## Credit Risk Assessment: {report.company_name} ({report.symbol})"
        f" | Traffic-Light: {emoji} {report.overall_flag.value}"
    )


def build_metrics_table(rows: list[MetricRow]) -> str:
    header = (
        "| Category | Signal | Metric Value | Peer Median | Interpretation |\n"
        "|----------|--------|--------------|-------------|----------------|\n"
    )
    lines = []
    for row in rows:
        emoji = EMOJI.get(row.flag, "")
        lines.append(
            f"| {row.category} | {emoji} {row.flag.value} "
            f"| {row.metric_value} | {row.peer_median_label} "
            f"| {row.interpretation} |"
        )
    return header + "\n".join(lines)


def build_key_flags_section(flags: list[str]) -> str:
    if not flags:
        return "No RED or AMBER flags."
    return "\n".join(f"- {line}" for line in flags)


def build_solvency_section(report: CreditReport) -> str:
    if report.palepu_unavailable:
        return "[Solvency assessment unavailable — tool error]"
    return report.solvency_narrative or "[Solvency assessment not provided]"


def build_liquidity_section(report: CreditReport) -> str:
    """The Palepu liquidity read, not the current/quick ratio.

    The ratio is already a row in the metrics table; this section is the
    qualitative half of the same `get_financial_analysis` call that supplies
    the solvency narrative, which is why one failure marks both.
    """
    if report.palepu_unavailable:
        return "[Liquidity assessment unavailable — tool error]"
    return report.liquidity_narrative or "[Liquidity assessment not provided]"


def build_footer() -> str:
    return (
        "*Analytical output based on Parallax factor scores and public "
        "financial data. Not investment or credit advice.*"
    )


def assemble_report(report: CreditReport) -> str:
    """Reference/test-only renderer. The skill orchestrator (SKILL.md) owns the
    client-facing output, including the §9.2 AI-interaction disclosure and the
    §9.1 disclaimer; this helper emits neither. Do NOT wire into client output.
    """
    sections = [
        build_header(report),
        "",
        "### Metrics Dashboard",
        build_metrics_table(report.metric_rows),
        "",
        "### Solvency Assessment",
        build_solvency_section(report),
        "",
        "### Liquidity Assessment",
        build_liquidity_section(report),
        "",
        "### Key Flags",
        build_key_flags_section(report.key_flags),
        "",
        "### Quality Trend",
        report.quality_trend_sentence or "[Quality trend unavailable]",
        "",
        "### Macro Context",
        report.macro_context_sentence or "[Macro context unavailable]",
        "",
        build_footer(),
    ]
    return "\n".join(sections)
