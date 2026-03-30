---
name: parallax-halal-screen
description: "Shariah-compliant stock screening: filter for halal investments, check compliance flags, explain screening criteria, and suggest compliant alternatives via Parallax MCP tools. NOT for general thematic screening (use /parallax-thematic-screen), not for portfolio construction (use /parallax-portfolio-builder)."
negative-triggers:
  - General thematic screening → use /parallax-thematic-screen
  - Portfolio construction → use /parallax-portfolio-builder
  - Non-compliance screening → use /parallax-earnings-quality
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - explain_methodology does NOT support shariah/halal — valid concepts are value, quality, momentum, defensive, tactical, overall, factor_weighting, scoring
  - Shariah thresholds are hardcoded in this skill (AAOIFI/DJIM standards) — derive compliance from get_financials data
  - get_financial_analysis (Palepu framework) is async ~2-5 min — warn user before calling
  - Financial ratios from get_financials help verify debt/revenue compliance thresholds
---

# Halal / Shariah Screen

Screen stocks and portfolios for Shariah compliance using AAOIFI/DJIM screening thresholds applied to Parallax financial data.

## AAOIFI / DJIM Screening Thresholds

These are the standard Shariah compliance thresholds used in this skill. They are applied to data retrieved from `get_financials`.

| Ratio | Threshold | Pass condition |
|-------|-----------|----------------|
| Total debt / Total assets | < 33% | Low leverage — no excessive interest-bearing debt |
| (Cash + interest-bearing securities) / Total assets | < 33% | Limited exposure to interest-bearing instruments |
| (Interest income + non-permissible revenue) / Total revenue | < 5% | Negligible income from haram activities |

**Business activity screen (qualitative):** The company's primary business must not be in prohibited industries (conventional banking/insurance, alcohol, tobacco, gambling, pork, weapons, adult entertainment). This is assessed from `get_company_info` sector/industry data.

**Purification ratio:** If a stock passes all quantitative screens but has non-zero non-permissible income, the purification percentage = (non-permissible income / total income). Shareholders should donate that percentage of dividends received.

## Usage

```
/parallax-halal-screen AAPL.O
/parallax-halal-screen [{"symbol":"AAPL.O","weight":0.25},{"symbol":"JPM.N","weight":0.25},{"symbol":"JNJ.N","weight":0.25},{"symbol":"XOM.N","weight":0.25}]
/parallax-halal-screen "build halal portfolio in Southeast Asian equities"
```

## Workflow

**For single stock compliance check:**
1. Call `get_company_info` to retrieve sector/industry — check against prohibited industries (banking, alcohol, tobacco, gambling, pork, weapons, adult entertainment).
2. Call `get_financials` with statement "balance_sheet" to retrieve total debt and total assets. Compute: total debt / total assets. **FAIL if >= 33%.**
3. Call `get_financials` with statement "balance_sheet" to retrieve cash and interest-bearing securities. Compute: (cash + interest-bearing securities) / total assets. **FAIL if >= 33%.**
4. Call `get_financials` with statement "ratios" to retrieve interest income and revenue figures. Compute: (interest income + non-permissible revenue) / total revenue. **FAIL if >= 5%.** If >0% but <5%, compute purification ratio.
5. Optionally call `get_financial_analysis` for deeper profitability decomposition (warn user: async ~2-5 min).
6. Call `get_score_analysis` for quality trajectory.
7. Present compliance verdict with all three ratio values and pass/fail per threshold.

**For portfolio screening:**
1. For each holding, run the single-stock compliance check (steps 1-7 above).
2. Call `check_portfolio_redundancy` on compliant holdings only.
3. For non-compliant holdings, call `build_stock_universe` with "[sector]" to find alternatives, then screen those alternatives through the same compliance check.
4. Call `get_peer_snapshot` on compliant alternatives to score them.

## Output Format

- **Screening Criteria** (AAOIFI/DJIM thresholds as listed above)
- **Compliance Results** (table: symbol, compliant Y/N, reason if non-compliant)
- **Key Ratios** (debt/assets %, interest-bearing/assets %, non-permissible revenue %)
- **Purification Amount** (if applicable — percentage of dividends requiring purification)
- **Alternatives** (for non-compliant holdings: scored compliant replacements in same sector)
- **Compliant Portfolio** (if portfolio mode: restructured allocation with only halal holdings)

> These are analytical outputs based on AAOIFI/DJIM screening thresholds applied to Parallax financial data, not investment advice or a fatwa. Consult a qualified Shariah advisor for binding rulings.
