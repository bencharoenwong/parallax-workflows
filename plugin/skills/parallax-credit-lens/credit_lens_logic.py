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
    # Screened for finiteness, not just for zero, and for the same reason the
    # market cap is: a non-finite denominator silently fabricates a term rather
    # than failing. total_liabilities=inf drives X4 to 0.0 and yields a
    # confident GREEN; total_assets=inf zeroes X1, X2, X3 and X5 alike.
    if not math.isfinite(inputs.total_assets) or inputs.total_assets == 0:
        raise ValueError(
            f"total_assets must be non-zero and finite (got {inputs.total_assets!r})"
        )

    x1 = inputs.working_capital / inputs.total_assets
    x2 = inputs.retained_earnings / inputs.total_assets
    x3 = inputs.ebit / inputs.total_assets
    x5 = inputs.revenue / inputs.total_assets

    # `is not None` alone accepted 0.0, which is how a missing market cap is
    # commonly coded. That selected the Z variant, set X4 to zero, discarded a
    # supplied book_equity and mislabelled the result "Z". With negative book
    # equity the substitution raised the score and softened the verdict, so the
    # output both misreported which formula ran and understated the risk.
    # A listed issuer cannot have a zero or negative market cap; treat it as
    # absent and fall through to the documented Z' path.
    market_cap_usable = (
        inputs.market_cap is not None
        and math.isfinite(inputs.market_cap)
        and inputs.market_cap > 0
    )
    if market_cap_usable:
        x4_numerator = inputs.market_cap
        variant = "Z"
    elif inputs.book_equity is not None:
        x4_numerator = inputs.book_equity
        variant = "Z'"
    else:
        # Covers an absent cap and an unusable one (zero, negative, non-finite)
        # with no book equity behind it. Both used to fabricate X4 and label the
        # result "Z", which downstream cannot tell from a real market-cap Z.
        # SKILL.md already tells the orchestrator to treat the raise as the
        # Altman leg being unavailable, so raising is the documented contract.
        raise ValueError(
            "Either market_cap or book_equity must be provided for X4 "
            f"(market_cap={inputs.market_cap!r} is not usable: a listed issuer "
            f"cannot have a zero, negative or non-finite market cap)"
        )

    if not math.isfinite(inputs.total_liabilities) or inputs.total_liabilities == 0:
        raise ValueError(
            "total_liabilities must be non-zero and finite for X4 computation "
            f"(got {inputs.total_liabilities!r})"
        )

    x4 = x4_numerator / inputs.total_liabilities

    z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5

    flag = _altman_zone_flag(z)
    return z, variant, flag


def _altman_zone_flag(z: float) -> Flag:
    """Map Altman Z value to credit flag per SKILL.md thresholds.

    Screens every non-finite z, not just NaN. `inf > 2.99` is True, so an
    infinite z used to return GREEN — "Safe Zone" on a score that overflowed.
    It does not take a non-finite input to get there: a large working capital
    over a tiny total-assets figure overflows from entirely finite inputs.
    `-inf` is treated the same way rather than left as RED, because an
    overflowed score is not a distress reading, it is an absent one.
    """
    if not math.isfinite(z):
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

    # A non-finite peer bound is a peer-data gap, not an inverted ordering.
    # Treated as absent so it degrades the same way a missing row does, rather
    # than raising with a message that misdescribes the cause.
    if peer_median is not None and not math.isfinite(peer_median):
        peer_median = None
    if peer_p75 is not None and not math.isfinite(peer_p75):
        peer_p75 = None

    direction = _direction(metric_key)

    # Ordering is validated ahead of BOTH early-return guards below. Either one
    # returns before the peer rule runs, so a guard placed first swallows a
    # corrupt peer row — and it does so on the distressed and missing-data
    # inputs where a mis-mapped peer field is most likely. The same pair used to
    # raise on a healthy value and pass silently on a negative or NaN one.
    if peer_median is not None and peer_p75 is not None:
        _validate_peer_ordering(peer_median, peer_p75, direction, metric_key)

    if not math.isfinite(value):
        # Every IEEE-754 comparison against NaN is False, so a NaN fell through
        # both threshold tests in _absolute_flag and landed on its trailing
        # `return GREEN`. json.loads accepts a bare NaN token, so this can
        # arrive straight off a tool response. compute_altman_z already treats
        # a non-finite result as UNAVAILABLE; this matches it.
        return Flag.UNAVAILABLE

    if direction == "high_bad" and value < 0:
        # A negative debt ratio does not mean "better than every peer", which
        # is what the high_bad rule concluded: any negative sits below any
        # positive median, and it also fails every `value > threshold` test, so
        # both legs returned GREEN on a distress signature.
        #
        # It is not safely scoreable either. A negative Debt/EBITDA is negative
        # EBITDA against positive debt, which is distress; but on a net-debt
        # convention it is net cash, which is healthy. The sign inverts the
        # economic meaning and this module cannot tell the two apart, so it
        # refuses to guess. The orchestrator must explain the sign in the
        # narrative — see SKILL.md Batch C.
        return Flag.UNAVAILABLE

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


def _validate_peer_ordering(
    peer_median: float,
    peer_p75: float,
    direction: Optional[str],
    metric_key: str,
) -> None:
    """Raise when the peer pair is inverted for its direction.

    `peer_p75` carries the adverse tail either way: numerically above the
    median when high is worse, below it when low is worse. An inverted pair
    means the caller mapped the fields wrong or the peer row is corrupt, and
    the bands would silently invert — so it must raise, not score.

    Equality is degenerate but not inverted. It collapses the AMBER band while
    leaving the GREEN/RED partition correctly oriented, so it stays allowed.
    """
    if direction == "low_bad" and not (peer_p75 <= peer_median):
        raise ValueError(
            f"peer_p75 ({peer_p75}) must be <= peer_median ({peer_median}) for {metric_key} (low_bad direction)"
        )
    if direction == "high_bad" and not (peer_p75 >= peer_median):
        raise ValueError(
            f"peer_p75 ({peer_p75}) must be >= peer_median ({peer_median}) for {metric_key} (high_bad direction)"
        )


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

    # Validate peer percentile ordering in BOTH directions. `peer_p75` carries
    # the adverse tail either way: numerically above the median when high is
    # worse, below it when low is worse. An inverted pair means the caller
    # mapped the fields wrong or the peer row is corrupt, and the bands would
    # silently invert — so it must raise, not score.
    #
    # This guard was low_bad-only until debt_equity and debt_assets were
    # registered. Those two are high_bad with no entry in ABSOLUTE_THRESHOLDS,
    # so there is no absolute rule to fall back on and _worse_flag cannot
    # rescue the verdict: an inverted pair returned GREEN on a value sitting
    # between the two percentiles. Equality is degenerate but not inverted, so
    # it stays allowed on both sides.
    _validate_peer_ordering(peer_median, peer_p75, direction, metric_key)

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
    if not math.isfinite(change_pts):
        # Same NaN fall-through as flag_metric: both comparisons are False, so
        # a NaN reached the trailing `return GREEN` and a missing trend read as
        # a healthy one.
        return Flag.UNAVAILABLE
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
    # Which leg this row IS, by registry key — not by its display label.
    # An earlier version identified the reserved Altman and Quality legs by
    # matching `category` against a tuple of strings. That failed open on every
    # near miss ("Altman", "altman z", "Altman Z " with a trailing space,
    # "Solvency"), and its coverage was anti-correlated with the failure: it
    # fired only on a caller who copied the SKILL.md example verbatim, while
    # the caller who duplicates a leg is by definition one who deviated from it.
    # `metric_key` is the same identifier `flag_metric` already validates and
    # already raises on, so duplication becomes detectable rather than guessed.
    metric_key: Optional[str] = None


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
    # The Quality-trend leg votes in the traffic-light like any other, but had
    # no field — only the rendered sentence. That made it uncountable, so a
    # coverage figure taken off this report silently omitted it.
    quality_flag: Flag = Flag.UNAVAILABLE
    palepu_unavailable: bool = False


# Sentinel keys for the two legs that live in their own report fields rather
# than in `metric_rows`. They are not metrics in METRIC_DIRECTIONS — they have
# no peer bands — so they get reserved keys instead of registry entries.
# Dashboard category label per registered metric, used when the module renders
# a row the caller omitted. Matches the four groupings in SKILL.md §2.
_METRIC_CATEGORY = {
    "debt_ebitda": "Leverage",
    "debt_equity": "Leverage",
    "debt_assets": "Leverage",
    "interest_coverage": "Coverage",
    "ebitda_interest_coverage": "Coverage",
    "current_ratio": "Liquidity",
    "quick_ratio": "Liquidity",
    "ebitda_margin": "Profitability",
    "ebit_margin": "Profitability",
    "fcf_margin": "Profitability",
}

ALTMAN_LEG_KEY = "__altman_z__"
QUALITY_LEG_KEY = "__quality_trend__"
RESERVED_LEG_KEYS = (ALTMAN_LEG_KEY, QUALITY_LEG_KEY)


def dashboard_rows(report: CreditReport) -> list[MetricRow]:
    """Every row the dashboard renders: the peer/absolute metrics the caller
    supplied, plus the Altman and Quality rows built from their own flags.

    The module renders those two so the caller never has to add them, which is
    what stops them being counted twice.
    """
    rows = list(report.metric_rows)

    # Render a row for every registered metric the caller omitted, so the
    # dashboard shows the same twelve legs the verdict is voted over. Without
    # this the caller controls the row set, and dropping the rows it could not
    # compute made the dashboard look complete while the caveat went quiet.
    # Same validation report_flags applies, so a duplicated key cannot render
    # twice here just because the caller skipped the header path.
    supplied = _validated_row_keys(report)
    for key in METRIC_DIRECTIONS:
        if key in supplied:
            continue
        # The module knows the metric was not supplied; it does NOT know why.
        # Asserting "no absolute band" was false for the three keys that have
        # one, and it told the reader a metric failing to arrive was a benign
        # structural gap rather than an anomaly worth chasing.
        if key in ABSOLUTE_THRESHOLDS:
            why = "Not supplied for this run; this metric has an absolute band"
        else:
            why = "Not supplied for this run; no absolute band for this metric"
        rows.append(MetricRow(
            _METRIC_CATEGORY.get(key, key), Flag.UNAVAILABLE, key,
            "—", "—", why,
            metric_key=key,
        ))

    if report.altman_z is None or not math.isfinite(report.altman_z):
        # "Z = inf" / "Z = nan" is not a value a reader should see in a score
        # cell; a non-finite score means the computation did not produce one.
        z = "—"
    else:
        z = f"{report.altman_variant} = {report.altman_z:.2f}"
    rows.append(MetricRow(
        "Altman Z", report.altman_flag, "Altman Z", z, "—",
        _ALTMAN_ZONE_TEXT.get(report.altman_flag, "Not computed"),
        metric_key=ALTMAN_LEG_KEY,
    ))
    rows.append(MetricRow(
        "Quality Trend", report.quality_flag, "Quality Trend",
        _cell(report.quality_trend_sentence), "—",
        "52-week factor change",
        metric_key=QUALITY_LEG_KEY,
    ))
    return rows


def _cell(text: str) -> str:
    """Make a string safe to drop into a markdown table cell.

    Two characters break a row, not one. An unescaped pipe splits it into extra
    columns; a newline ENDS it, so the remainder of the sentence becomes a
    fabricated row with no Category and no Signal cell — a table line the reader
    sees but no leg produced. An earlier version escaped only the pipe while its
    docstring claimed the cell was safe.

    Whitespace is collapsed before the emptiness test, so a sentence of only
    spaces or a bare newline yields the em dash rather than a blank cell.
    """
    if not text:
        return "—"
    # Zero-width characters are not whitespace to str.split(), so a sentence
    # of only U+200B passed both emptiness tests and rendered an invisible
    # cell instead of the em dash. Strip them before folding.
    text = text.translate({0x200B: None, 0x200C: None, 0x200D: None, 0xFEFF: None})
    collapsed = " ".join(text.split())          # folds \n, \r and \t alike
    if not collapsed:
        return "—"
    # Backslash first, then pipe — the standard escaping order, and it matters.
    # Escaping only the pipe turns an already-escaped `\|` into `\\|`, which GFM
    # reads as a literal backslash followed by a LIVE separator, so text that
    # arrived correctly escaped was the one input that still broke the row.
    return collapsed.replace("\\", "\\\\").replace("|", "\\|")


_ALTMAN_ZONE_TEXT = {
    Flag.GREEN: "Safe Zone",
    Flag.AMBER: "Grey Zone",
    Flag.RED: "Distress Zone",
    Flag.UNAVAILABLE: "Not computed",
}


def _validated_row_keys(report: CreditReport) -> set[str]:
    """Validate `metric_rows` and return the set of keys it supplies.

    Shared by `report_flags` and `dashboard_rows` so BOTH entry points are
    guarded. `report_flags` used to hold these four checks inline while
    `dashboard_rows` did its own unvalidated `{row.metric_key for row in ...}`,
    so a duplicated key rendered twice — thirteen rows against twelve legs —
    and only the header path caught it. SKILL.md documents `finalize_verdict`
    as optional when merely rendering, so that protection was a rule about
    call order rather than a property of the code. Every guarantee in this
    module that rested on call order has failed at least once.
    """
    seen: set[str] = set()
    for row in report.metric_rows:
        key = row.metric_key
        if key is None:
            raise ValueError(
                f"MetricRow(category={row.category!r}) has no metric_key. Set it "
                f"to the registry key the row was flagged with, so the leg can "
                f"be identified by what it IS rather than by how it is labelled. "
                f"Known keys: {sorted(set(METRIC_DIRECTIONS) | set(ABSOLUTE_THRESHOLDS))}"
            )
        if key in RESERVED_LEG_KEYS:
            raise ValueError(
                f"metric_rows must not carry the reserved leg {key!r}: it is held "
                f"by report.altman_flag / report.quality_flag and rendered by "
                f"dashboard_rows(). Supplying it as a row as well makes that leg "
                f"vote twice, which can flip the verdict."
            )
        if key not in METRIC_DIRECTIONS and key not in ABSOLUTE_THRESHOLDS:
            raise ValueError(
                f"MetricRow metric_key {key!r} is not registered; the same check "
                f"flag_metric applies. Known keys: "
                f"{sorted(set(METRIC_DIRECTIONS) | set(ABSOLUTE_THRESHOLDS))}"
            )
        if key in seen:
            raise ValueError(
                f"metric_rows carries {key!r} more than once, so that leg would "
                f"vote twice. SKILL.md requires one row per metric."
            )
        seen.add(key)
    return seen


def report_flags(report: CreditReport) -> list[Flag]:
    """The canonical leg list — every flag the verdict is computed from.

    Exists because the verdict and the coverage count were read off two
    different lists and nothing reconciled them. `build_header` counted
    `metric_rows`, while the vote ran over the per-metric flags; SKILL.md
    groups ten metrics into four rendered category rows, so a routine run
    counted 6 of 6 judged while the vote saw 5 of 10, and the coverage caveat
    never rendered on exactly the run that needed it.

    Two legs also sat outside `metric_rows` entirely: `altman_flag`, which
    defaults to UNAVAILABLE on a bare report, and the Quality trend, which had
    no field at all. Both vote, so both are counted here.

    Derive BOTH the verdict and the coverage figure from this one list — that
    is what `finalize_verdict` is for.

    Raises if `metric_rows` carries an Altman or Quality row. Those two legs
    live in their own fields and are rendered by `dashboard_rows`; a caller
    following SKILL.md's example dashboard would otherwise supply them as rows
    as well, and each would then vote TWICE. That is not merely a miscount —
    doubling two legs flips a real verdict: three RED metrics against two GREEN
    is RED, but with both GREEN legs doubled it becomes 3 RED against 4 GREEN
    and reports GREEN. Loud is the only safe behaviour.
    """
    seen = _validated_row_keys(report)

    # Pad every registered metric the caller did not supply. The denominator is
    # the registry, not the row list, because otherwise omission is silent:
    # dropping the unjudgeable rows turned "7 of 12 judged" into "7 of 7" and
    # the coverage caveat — the whole point of the last three fixes —
    # disappeared. Dropping two RED rows likewise turned RED into GREEN with no
    # caveat to show a leg had gone missing.
    #
    # Over-supply already raises four ways; under-supply used to raise none.
    # A metric with no row IS unjudged, so counting it as UNAVAILABLE is simply
    # true, and it keeps the caveat honest without failing a legitimately
    # partial tool response.
    missing = [k for k in METRIC_DIRECTIONS if k not in seen]
    return (
        [row.flag for row in report.metric_rows]
        + [Flag.UNAVAILABLE] * len(missing)
        + [report.altman_flag, report.quality_flag]
    )


def finalize_verdict(report: CreditReport) -> CreditReport:
    """Set `overall_flag` from the canonical leg list and return the report.

    Call this instead of assigning `overall_flag` by hand. It makes the header
    verdict and the header's judged-count arithmetically inseparable: both read
    `report_flags(report)`, so they cannot describe different metric sets.
    """
    report.overall_flag = overall_traffic_light(report_flags(report))
    return report


def coverage(flags: list[Flag]) -> tuple[int, int]:
    """Return (judged, total). `judged` excludes UNAVAILABLE legs.

    `overall_traffic_light` drops those legs from the vote, which is right for
    the arithmetic and silent in the output: a GREEN header can rest on a small
    minority of the metrics and still read as a full clean bill. This is not a
    corner case — seven of the ten registered keys carry no absolute band, and
    the `ratios` response supplies peer percentiles for only five metrics, so
    the five keys with neither are UNAVAILABLE on a routine run.

    Pass `report_flags(report)`, not a hand-assembled list. Counting a
    different list than the one the verdict was computed from is the bug this
    docstring used to describe incorrectly.
    """
    return sum(1 for f in flags if f != Flag.UNAVAILABLE), len(flags)


def build_header(report: CreditReport) -> str:
    """Render the header from the legs as they stand NOW.

    Deliberately does NOT read `report.overall_flag`. That field is a snapshot
    taken when `finalize_verdict` ran, while the judged count was computed
    live, so a leg resolving afterwards — `altman_flag` needs an external market
    cap, `quality_flag` arrives in Batch B — refreshed the count and left the
    verdict stale. The caveat then vanished while the verdict stayed green,
    which is the failure mode disappearing exactly when it was needed.

    Both halves now read one list, at one instant, so they cannot disagree.
    """
    legs = report_flags(report)
    flag = overall_traffic_light(legs)
    emoji = EMOJI.get(flag, "")
    line = (
        f"## Credit Risk Assessment: {report.company_name} ({report.symbol})"
        f" | Traffic-Light: {emoji} {flag.value}"
    )
    judged, total = coverage(legs)
    if judged < total:
        line += f" | Judged: {judged} of {total} metrics"
    return line


def build_metrics_table(rows: list[MetricRow]) -> str:
    header = (
        "| Category | Signal | Metric Value | Peer Median | Interpretation |\n"
        "|----------|--------|--------------|-------------|----------------|\n"
    )
    lines = []
    for row in rows:
        emoji = EMOJI.get(row.flag, "")
        # EVERY caller-supplied cell goes through _cell, not just one of them.
        # An earlier version sanitised only the quality sentence, leaving four
        # columns raw. The worst variant is a pipe in `category`: the cells
        # shift right, the flag leaves the Signal column, and the header still
        # counts that leg as judged. The Signal cell is module-generated from a
        # Flag enum, so it needs no escaping.
        lines.append(
            f"| {_cell(row.category)} | {emoji} {row.flag.value} "
            f"| {_cell(row.metric_value)} | {_cell(row.peer_median_label)} "
            f"| {_cell(row.interpretation)} |"
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
        build_metrics_table(dashboard_rows(report)),
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
