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
    """Assign GREEN/AMBER/RED by applying both peer-relative and absolute rules; use more conservative result."""
    peer_flag = _peer_relative_flag(value, peer_median, peer_p75, metric_key)
    abs_flag = _absolute_flag(value, metric_key)

    # More conservative = higher severity
    return _worse_flag(peer_flag, abs_flag)


def _direction(metric_key: str) -> Optional[str]:
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


def flag_quality_change(change_pts: float) -> Flag:
    """AMBER: change ≤ -5 pts, RED: change ≤ -15 pts (52w deterioration)."""
    if change_pts <= -15:
        return Flag.RED
    if change_pts <= -5:
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


def build_footer() -> str:
    return (
        "*Analytical output based on Parallax factor scores and public "
        "financial data. Not investment or credit advice.*"
    )


def assemble_report(report: CreditReport) -> str:
    sections = [
        build_header(report),
        "",
        "### Metrics Dashboard",
        build_metrics_table(report.metric_rows),
        "",
        "### Solvency Assessment",
        build_solvency_section(report),
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
