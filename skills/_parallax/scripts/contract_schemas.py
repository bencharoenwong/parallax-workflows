"""
Canonical per-endpoint contracts for Parallax MCP: fields skills are known to
read, marked required/optional with expected types. Schema DSL documented in
``contract_validator.py``.
"""

from __future__ import annotations

from contract_validator import NULLABLE, NUM, OPTIONAL

# Several blocks carry JSON null in a numeric or string slot, and null is NOT
# the same as absent -- see the OPTIONAL semantics note in
# ``contract_validator``. Those fields are spelled ``(inner, NULLABLE)``, which
# is the one notation for "present, and may be null". Writing ``type(None)``
# into a tuple of types would say it a second way AND lose the bool rule, since
# the marker unwraps to a spec the validator checks in full.


GET_TELEMETRY_SCHEMA = {
    "regime_tag": str,
    "signals": dict,  # opaque blob; skill reads opportunistically
    "commentary": {
        "headline": str,
        "mechanism": str,
    },
    # Corrected 2026-10-06 against a live probe. There is no "ticker"/"factor"/
    # "magnitude" shape and no "basket_name" field anywhere in this array --
    # three different wrong shapes were in play across this schema, the old
    # mock and parallax-ai-soros's SKILL.md before this fix. Per-ticker basket
    # membership exists only as an upstream baskets[].members field this tool
    # does not expose; best-effort matching is on "name" (a sector/industry
    # theme label), not a ticker-level field.
    "divergences": [
        {
            "name": str,
            "type": str,
            "market": str,
            "daily": NUM,
            "mtd": NUM,
            "basket_id": (str, OPTIONAL),
        }
    ],
}


# Corrected 2026-08-13 to the shape the live endpoint actually returns.
#
# The previous version of this schema described a shape the API does not emit --
# ``factor_exposures``, ``sector_exposures``, dict-valued ``sector_allocation``
# and ``sector_contribution``, ``symbol``/``contribution``/``weight`` rows in
# ``company_contribution``. That divergence was already on record in
# ``response-schemas.md`` (the observed live shape, dated 2026-05-07/2026-08-11)
# and in ``DECISIONS.md`` 2026-08-15 (the hand-authored mock "is the wrong
# artifact"). The mock and this schema now follow the live shape.
#
# THREE STRUCTURAL POINTS THAT BIT PEOPLE, restated here because a schema is
# where the next reader looks:
#
#   * ``sector_allocation`` is a LIST of (date x sector) rows, not a
#     ``{sector: weight}`` dict. Modelling it as a dict silently discards the
#     entire time dimension and collapses the value column.
#   * ``sector_contribution`` is a LIST of one row per sector, and it mixes
#     aggregations column by column: ``total_pl`` and ``contribution_pct`` SUM
#     over their members while ``avg_weight`` is the MEAN.
#   * Holdings are keyed by ``ric``, not ``symbol``.
ANALYZE_PORTFOLIO_SCHEMA = {
    # Present whenever the call passed ``fields=``. ``invalid_fields`` is null
    # on a clean request -- NOT [] -- and a non-empty list is a CALLER error,
    # not unavailable data (parallax-conventions.md §0 item 2).
    "_meta": (
        {
            # Same SET in a different ORDER — compare as sets, never as lists.
            "fields_requested": [str],
            "fields_returned": [str],
            # A list of the offending names, or null on a clean request.
            "invalid_fields": ([str], NULLABLE),
        },
        OPTIONAL,
    ),
    "portfolio_parameters": (
        {
            "start_date": (str, OPTIONAL),
            "end_date": (str, OPTIONAL),
            "base_currency": (str, OPTIONAL),
            "benchmark": (str, OPTIONAL),
            "initial_value": (NUM, OPTIONAL),
        },
        OPTIONAL,
    ),
    "data_quality": (dict, OPTIONAL),
    "concentration_metrics": (dict, OPTIONAL),
    "portfolio_summary": (
        {
            "final_value": (NUM, OPTIONAL),
            "total_return": (NUM, OPTIONAL),
            "total_pl": (NUM, OPTIONAL),
            "total_price_pl": (NUM, OPTIONAL),
            "total_fx_pl": (NUM, OPTIONAL),
        },
        OPTIONAL,
    ),
    "performance_metrics": (
        {
            "portfolio": (
                {
                    "total_return": (NUM, OPTIONAL),
                    "annualized_return": (NUM, OPTIONAL),
                    "annualized_volatility": (NUM, OPTIONAL),
                    "max_drawdown": (NUM, OPTIONAL),
                    "sharpe_ratio": (NUM, OPTIONAL),
                    "win_rate": (NUM, OPTIONAL),
                    "days": (int, OPTIONAL),
                },
                OPTIONAL,
            ),
            # A strict SUBSET of ``portfolio`` -- eight keys narrower. Iterating
            # the portfolio dict's keys over this one raises KeyError.
            "benchmark": (dict, OPTIONAL),
            "relative": (dict, OPTIONAL),
        },
        OPTIONAL,
    ),
    "drawdown_analysis": (
        {
            "portfolio": (
                {
                    "max_drawdown": (NUM, OPTIONAL),
                    "current_drawdown": (NUM, OPTIONAL),
                    "at_peak": (bool, OPTIONAL),
                    "max_recovery_days": (int, OPTIONAL),
                },
                OPTIONAL,
            ),
            "benchmark": (dict, OPTIONAL),
            "timeseries": (
                [
                    {
                        "date": str,
                        "portfolio_drawdown": NUM,
                        # Null whenever not underwater, not 0.
                        "portfolio_episode": (int, NULLABLE),
                    }
                ],
                OPTIONAL,
            ),
            "episode_details": (
                {
                    "portfolio": (
                        [
                            {
                                "episode": int,
                                "start_date": str,
                                "trough_date": str,
                                # The still-open final episode carries nulls
                                # here and ``recovered: false``.
                                "end_date": (str, NULLABLE),
                                "max_drawdown": NUM,
                                "recovery_days": (NUM, NULLABLE),
                                "recovered": bool,
                            }
                        ],
                        OPTIONAL,
                    ),
                    "benchmark": ([dict], OPTIONAL),
                },
                OPTIONAL,
            ),
        },
        OPTIONAL,
    ),
    "company_contribution": (
        [
            {
                "ric": str,
                "name": (str, OPTIONAL),
                "total_pl": NUM,
                "avg_weight": NUM,
                "contribution_pct": NUM,
                "avg_allocation": (NUM, OPTIONAL),
                "return_pct": (NUM, OPTIONAL),
            }
        ],
        OPTIONAL,
    ),
    # One row per (date x sector). NOT a {sector: weight} dict.
    "sector_allocation": (
        [
            {
                "date": str,
                "sector": str,
                "value": NUM,
                "weight": NUM,
            }
        ],
        OPTIONAL,
    ),
    # One row per sector, no date column. ``avg_weight`` is a MEAN while
    # ``total_pl`` and ``contribution_pct`` are SUMS.
    "sector_contribution": (
        [
            {
                "sector": str,
                "total_pl": NUM,
                "avg_weight": NUM,
                "contribution_pct": NUM,
            }
        ],
        OPTIONAL,
    ),
    # Twelve fixed buckets. A bucket the window cannot cover is PRESENT with all
    # four sub-keys null -- never absent.
    "time_period_returns": (dict, OPTIONAL),
    "latest_holdings": (
        [
            {
                "ric": str,
                "name": (str, OPTIONAL),
                "quantity": NUM,
                "weight": NUM,
                "close_local": NUM,
                # Rides a dividend-inclusive value path, so
                # quantity * close_local != ending_value. Confirmed API
                # behaviour, not a bug -- never assert that identity.
                "ending_value": NUM,
                "sector": (str, OPTIONAL),
                "industry": (str, OPTIONAL),
                "market": (str, OPTIONAL),
                # Per-security factor scores are ints on 0-10; ``total`` is a
                # one-decimal float on 0-10.
                "value": (int, OPTIONAL),
                "quality": (int, OPTIONAL),
                "momentum": (int, OPTIONAL),
                "defensive": (int, OPTIONAL),
                "tactical": (int, OPTIONAL),
                "total": (NUM, OPTIONAL),
                "pick_toscore": (bool, OPTIONAL),
                "recommendation": (str, OPTIONAL),
            }
        ],
        OPTIONAL,
    ),
    # Portfolio-level factor scores are ints on 0-100 (per-security scores are
    # 0-10; the factor of ten is the whole conversion). ``coverage`` is 0-1.
    "portfolio_scores": (dict, OPTIONAL),
    "rolling_metrics": (dict, OPTIONAL),
}


# The schema above describes the INNER block map. The live response WRAPS it:
# the analytics blocks, ``_meta`` included, live under ``result``, so the
# consumer path is ``response["result"]["portfolio_summary"]`` and a bare
# ``response["portfolio_summary"]`` returns nothing. Validate a whole response
# against this; validate an already-unwrapped block map against
# ANALYZE_PORTFOLIO_SCHEMA directly.
ANALYZE_PORTFOLIO_ENVELOPE_SCHEMA = {
    "success": bool,
    "result": ANALYZE_PORTFOLIO_SCHEMA,
}


# The credit-exhausted envelope: ``success: true`` on a call that FAILED, a
# ``detail`` object, and NO ``result`` key at all -- absent, not null. That is
# why ``"result" in payload`` is the only sound guard, and why
# ``if payload["success"]:`` is a bug that then raises KeyError on ``result``.
ANALYZE_PORTFOLIO_ERROR_SCHEMA = {
    "success": bool,
    "detail": {
        "error": str,
        "balance": NUM,
        "required": NUM,
        "endpoint": (str, OPTIONAL),
    },
}


# Corrected 2026-10-06 against a live probe. "prices"/"close" never existed;
# the real top-level shape is {success, symbol, format, data_points, data}.
# "json" format rows carry open/high/low/volume beyond "price"; list/csv rows
# expose "price" only (format changes the row schema, not just serialization).
# "price" is the raw daily close, NOT a dividend-adjusted or total-return
# series -- do not assume TR convention for this endpoint.
EXPORT_PRICE_SERIES_SCHEMA = {
    "success": bool,
    "symbol": str,
    "format": (str, OPTIONAL),
    "data_points": (int, OPTIONAL),
    "data": [
        {
            "date": str,
            "price": NUM,
            "open": (NUM, OPTIONAL),
            "high": (NUM, OPTIONAL),
            "low": (NUM, OPTIONAL),
            "volume": (NUM, OPTIONAL),
        }
    ],
}


# Corrected 2026-10-06 against a live probe. The live endpoint wraps every
# identity/pricing/score field under "data", keyed by {success, symbol, data,
# score_scale} -- there is no top-level "name"/"sector"/"market_cap_usd", and
# the live field is "data.market" (a country/region name), never "country".
# Price, volume, market cap and the five factor scores + composite are all
# returned as STRINGS by the live endpoint, not numbers -- a real consumer
# trap, modelled here rather than "corrected" into the nicer type.
GET_COMPANY_INFO_SCHEMA = {
    "success": bool,
    "symbol": str,
    "data": {
        "ric": (str, OPTIONAL),
        "name": str,
        "sector": str,
        "industry": (str, OPTIONAL),
        "market": (str, OPTIONAL),
        "exchange": (str, OPTIONAL),
        "currency": (str, OPTIONAL),
        "description": (str, OPTIONAL),
        "activity": (str, OPTIONAL),
        "close": (str, OPTIONAL),
        "change": (str, OPTIONAL),
        "changepercent": (str, OPTIONAL),
        "volume": (str, OPTIONAL),
        "mktcap": (str, OPTIONAL),
        "value": (str, OPTIONAL),
        "quality": (str, OPTIONAL),
        "momentum": (str, OPTIONAL),
        "defensive": (str, OPTIONAL),
        "tactical": (str, OPTIONAL),
        "total": (str, OPTIONAL),
        "recommendation": (str, OPTIONAL),
    },
    "score_scale": (
        {
            "range": (str, OPTIONAL),
            "weighting": (str, OPTIONAL),
            "more": (str, OPTIONAL),
        },
        OPTIONAL,
    ),
}


# Corrected 2026-10-06 against a live probe (no longer PROVISIONAL): the live
# shape is sector_concentration (dict of sector -> weight FRACTION, 0-1) +
# industry_overlap + warnings + recommendations. There is no overlap_pairs,
# coverage_pct, holdings_analyzed or holdings_total field anywhere live.
CHECK_PORTFOLIO_REDUNDANCY_SCHEMA = {
    "success": bool,
    "has_issues": (bool, OPTIONAL),
    "holdings_input": (int, OPTIONAL),
    "holdings_resolved": (int, OPTIONAL),
    "holdings_failed": (int, OPTIONAL),
    "holdings_trimmed": (int, OPTIONAL),
    "holdings_unresolved": ([str], OPTIONAL),
    "coverage_weight_fraction": (NUM, OPTIONAL),
    "sector_concentration": dict,
    "industry_overlap": (dict, OPTIONAL),
    "warnings": ([str], OPTIONAL),
    "recommendations": ([str], OPTIONAL),
}


GET_ASSESSMENT_SCHEMA = {
    "symbol": str,
    "name": (str, OPTIONAL),
    "assessment": str,
    "rationale": (str, OPTIONAL),
    "confidence": (str, OPTIONAL),
    "generated_at": (str, OPTIONAL),
}


# Corrected 2026-08-13 to the live shape. Three shapes were in play here at
# once -- a credit-lens fixture on ``factor_trajectory``, this canonical mock on
# ``history[]`` with uppercase keys, and the live API on ``data[]`` with
# lowercase keys. The live response wins.
#
# The payload is FLAT: there is no ``result`` wrapper, unlike analyze_portfolio.
# ``success`` is not a reliable status flag -- a credit-exhausted call returns
# ``success: true`` with a ``detail`` object and no payload -- so branch on the
# presence of ``data``, never on ``success``.
GET_SCORE_ANALYSIS_SCHEMA = {
    "success": (bool, OPTIONAL),
    "symbol": str,
    "weeks": (int, OPTIONAL),
    "data": [
        {
            # Repeated on every row as well as at the top level.
            "symbol": (str, OPTIONAL),
            "date": str,
            # Sub-scores are ints on 0-10.
            "value": int,
            "quality": int,
            "momentum": int,
            "defensive": int,
            "tactical": int,
            # A separately-computed composite on 0-10, one decimal. NOT the
            # mean of the five sub-scores -- it differs in both directions.
            "total": (NUM, OPTIONAL),
        }
    ],
}


# Corrected 2026-10-06 against a live probe. There is no "summary"/
# "key_themes"/"sentiment"/"articles_analyzed" shape -- the live endpoint
# returns a FIXED 3-bullet shape every time, not a variable-length synthesis.
# "sources" was an empty array in the probed sample despite the tool
# description's "sources used" framing; do not assume it is ever populated.
GET_NEWS_SYNTHESIS_SCHEMA = {
    "success": (bool, OPTIONAL),
    "symbol": str,
    "title": str,
    "bullet1": str,
    "bullet2": str,
    "bullet3": str,
    "sources": ([str], OPTIONAL),
    "generation_time_ms": (int, OPTIONAL),
}


# Corrected 2026-10-06 against a live probe. There is no structured "regime"/
# "tactical.stance"/"factor_tilts" object -- the live endpoint returns free
# prose in "content" plus a pre-signed, time-limited storage URL in
# "file_url" for the fuller report. "truncated" flags server-side truncation
# of the "content" field itself, not completeness of the underlying report.
MACRO_ANALYST_SCHEMA = {
    "success": (bool, OPTIONAL),
    "report_date": (str, OPTIONAL),
    "market": str,
    "component": (str, OPTIONAL),
    "component_name": (str, OPTIONAL),
    "content": str,
    "file_url": (str, OPTIONAL),
    "truncated": (bool, OPTIONAL),
    "next_steps": (dict, OPTIONAL),
}
