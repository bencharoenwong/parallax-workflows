"""
Canonical per-endpoint contracts for Parallax MCP: fields skills are known to
read, marked required/optional with expected types. Schema DSL documented in
``contract_validator.py``.
"""

from __future__ import annotations

from contract_validator import NUM, OPTIONAL


GET_TELEMETRY_SCHEMA = {
    "regime_tag": str,
    "signals": dict,  # opaque blob; skill reads opportunistically
    "commentary": {
        "headline": str,
        "mechanism": str,
    },
    "divergences": [{
        "ticker": str,
        "factor": str,
        "magnitude": NUM,
    }],
}


ANALYZE_PORTFOLIO_SCHEMA = {
    "factor_exposures": ({
        "VALUE": NUM,
        "QUALITY": NUM,
        "MOMENTUM": NUM,
        "DEFENSIVE": NUM,
    }, OPTIONAL),
    "sector_exposures": (dict, OPTIONAL),  # sector name -> weight; arbitrary keys
    "concentration_metrics": (dict, OPTIONAL),
    "risk_metrics": (dict, OPTIONAL),
    "holdings_count": (int, OPTIONAL),
    "as_of": (str, OPTIONAL),
    # --- new fields required by cio-letter-prep ---
    "portfolio_summary": ({
        "total_return": (NUM, OPTIONAL),
        "annualized_return": (NUM, OPTIONAL),
        "benchmark_return": (NUM, OPTIONAL),
    }, OPTIONAL),
    "performance_metrics": ({
        "portfolio": {
            "annualized_volatility": (NUM, OPTIONAL),
            "sharpe_ratio": (NUM, OPTIONAL),
        },
    }, OPTIONAL),
    "drawdown_analysis": ({
        "portfolio": {
            "max_drawdown": (NUM, OPTIONAL),
            "recovery_days": (int, OPTIONAL),
        },
    }, OPTIONAL),
    "company_contribution": ([{
        "symbol": str,
        "name": (str, OPTIONAL),
        "contribution": NUM,
        "weight": NUM,
    }], OPTIONAL),
    "sector_allocation": (dict, OPTIONAL),
    "sector_contribution": (dict, OPTIONAL),
    "time_period_returns": (dict, OPTIONAL),
    "latest_holdings": ([{
        "symbol": str,
        "name": (str, OPTIONAL),
        "weight": NUM,
    }], OPTIONAL),
    "portfolio_scores": (dict, OPTIONAL),
    "rolling_metrics": (dict, OPTIONAL),
}


EXPORT_PRICE_SERIES_SCHEMA = {
    "symbol": str,
    "currency": (str, OPTIONAL),
    "prices": [{
        "date": str,
        "open": (NUM, OPTIONAL),
        "high": (NUM, OPTIONAL),
        "low": (NUM, OPTIONAL),
        "close": NUM,
        "volume": (NUM, OPTIONAL),
    }],
}


GET_COMPANY_INFO_SCHEMA = {
    "symbol": str,
    "name": str,
    "exchange": (str, OPTIONAL),
    "sector": str,
    "industry": (str, OPTIONAL),
    "country": (str, OPTIONAL),
    "market_cap_usd": (NUM, OPTIONAL),
    "currency": (str, OPTIONAL),
    "description": (str, OPTIONAL),
    "website": (str, OPTIONAL),
}


# PROVISIONAL — see mcp_mocks/README.md. The skill plans refer to this endpoint
# but field-level usage is not yet documented in any existing SKILL.md. The
# schema below is best-inference from the function name and conventions; refresh
# against the live MCP response when wiring it into a new skill's contract test.
CHECK_PORTFOLIO_REDUNDANCY_SCHEMA = {
    "overlap_pairs": [{
        "symbol_a": str,
        "symbol_b": str,
        "overlap_score": NUM,
        "shared_factors": ([str], OPTIONAL),
        "shared_sector": (str, OPTIONAL),
    }],
    "coverage_pct": (NUM, OPTIONAL),
    "holdings_analyzed": (int, OPTIONAL),
    "holdings_total": (int, OPTIONAL),
}


GET_ASSESSMENT_SCHEMA = {
    "symbol": str,
    "name": (str, OPTIONAL),
    "assessment": str,
    "rationale": (str, OPTIONAL),
    "confidence": (str, OPTIONAL),
    "generated_at": (str, OPTIONAL),
}


GET_SCORE_ANALYSIS_SCHEMA = {
    "symbol": str,
    "name": (str, OPTIONAL),
    "weeks": (int, OPTIONAL),
    "history": [{
        "date": str,
        "VALUE": NUM,
        "QUALITY": NUM,
        "MOMENTUM": NUM,
        "DEFENSIVE": NUM,
        "OVERALL": (NUM, OPTIONAL),
    }],
}


GET_NEWS_SYNTHESIS_SCHEMA = {
    "symbol": str,
    "name": (str, OPTIONAL),
    "summary": str,
    "key_themes": ([str], OPTIONAL),
    "sentiment": (str, OPTIONAL),
    "articles_analyzed": (int, OPTIONAL),
    "period_start": (str, OPTIONAL),
    "period_end": (str, OPTIONAL),
    "generated_at": (str, OPTIONAL),
}


MACRO_ANALYST_SCHEMA = {
    "market": str,
    "component": (str, OPTIONAL),
    "regime": (str, OPTIONAL),
    "tactical": {
        "stance": str,
        "horizon_months": (int, OPTIONAL),
        "summary": str,
        "key_drivers": ([str], OPTIONAL),
        "factor_tilts": (dict, OPTIONAL),
    },
    "generated_at": (str, OPTIONAL),
}
