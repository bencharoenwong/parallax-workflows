---
name: parallax-halal-screen
description: "Shariah-compliant stock screening: filter for halal investments, check compliance flags, explain screening criteria, and suggest compliant alternatives via Parallax MCP tools. NOT for general thematic screening (use /parallax-thematic-screen), not for portfolio construction (use /parallax-portfolio-builder)."
user-invocable: true
negative-triggers:
  - General thematic screening → use /parallax-thematic-screen
  - Portfolio construction → use /parallax-portfolio-builder
  - Non-compliance screening → use /parallax-earnings-quality
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - explain_methodology does NOT support "shariah" or "halal" — use list_docs + get_docs("methodology/shariah-screening") instead
  - get_financial_analysis (Palepu framework) is async ~2-5 min — warn user before calling
  - Financial ratios from get_financials help verify debt/revenue compliance thresholds
  - Not all markets may have Shariah screening data — check documentation first
---

# Halal / Shariah Screen

Screen stocks and portfolios for Shariah compliance using Parallax methodology.

## Usage

```
/parallax-halal-screen AAPL.O
/parallax-halal-screen [{"symbol":"AAPL.O","weight":0.25},{"symbol":"JPM.N","weight":0.25},{"symbol":"JNJ.N","weight":0.25},{"symbol":"XOM.N","weight":0.25}]
/parallax-halal-screen "build halal portfolio in Southeast Asian equities"
```

## Workflow

**For single stock compliance check:**
1. Call `list_docs` to find Shariah screening documentation, then call `get_docs("methodology/shariah-screening")` to retrieve criteria.
2. Call `get_financials` with statement "ratios" and "balance_sheet" to check debt ratios, interest income, and non-compliant revenue streams.
3. Call `get_financial_analysis` for deeper profitability decomposition.
4. Call `get_score_analysis` for quality trajectory.
5. Assess compliance against Shariah criteria (debt/assets, interest income/revenue, non-permissible revenue).

**For portfolio screening:**
1. Retrieve Shariah methodology as above.
2. For each holding, run the single-stock compliance check.
3. Call `check_portfolio_redundancy` on compliant holdings only.
4. For non-compliant holdings, call `build_stock_universe` with "[sector] shariah compliant" to find alternatives.
5. Call `get_peer_snapshot` on alternatives to score them.

## Output Format

- **Shariah Screening Criteria** (brief summary of methodology used)
- **Compliance Results** (table: symbol, compliant Y/N, reason if non-compliant)
- **Key Ratios** (debt/assets, interest income %, non-permissible revenue %)
- **Purification Amount** (if applicable — percentage of dividends requiring purification)
- **Alternatives** (for non-compliant holdings: scored Shariah-compliant replacements in same sector)
- **Compliant Portfolio** (if portfolio mode: restructured allocation with only halal holdings)

Always end with: *"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*
