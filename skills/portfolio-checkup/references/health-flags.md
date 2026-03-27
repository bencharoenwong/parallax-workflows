# Portfolio Health Flag System

## Health Flags

5 flags evaluated against portfolio data. Each flag is binary (triggered or not).

| Flag | Condition | Source | Threshold |
|---|---|---|---|
| **Low Score** | Portfolio overall score is weak | `quick_portfolio_scores` | Overall ≤ 5.0 |
| **Concentration** | Single holding too large or top-3 dominate | Holdings weights | Any single >15% OR top-3 >45% |
| **Redundancy** | Multiple overlapping positions | `check_portfolio_redundancy` | ≥ 2 redundant pairs |
| **Value Trap** | Portfolio-weighted value score is low | `quick_portfolio_scores` | Portfolio value score ≤ 3.0 |
| **Macro Misalignment** | Overweight in sectors with negative tactical outlook | `macro_analyst` (tactical) | Holdings overweight in unfavourable sectors |

## Health Status Labels

| Status | Flag Count | Plain-Language Frame |
|---|---|---|
| **Healthy** | 0 flags | "Your portfolio looks solid." |
| **Monitor** | 1-2 flags | "A couple of items to keep an eye on." |
| **Attention** | 3+ flags | "Some areas need a closer look." |

## Mixed-Exchange Fallback

When `quick_portfolio_scores` returns coverage for **<50% of holdings by weight**:

1. Split holdings by exchange suffix (group `.O`/`.N` together as US, `.L` as UK, etc.).
2. Call `quick_portfolio_scores` for each exchange group separately.
3. Merge results into portfolio-weighted scores.
4. Note in output: "Scoring used split-and-merge due to partial coverage for [X, Y] symbols."

If coverage remains below 50% after split-and-merge, report available scores but flag: "Scoring coverage is limited — health flags may not reflect the full portfolio."

## Coverage Reliability Flags

- **Redundancy**: If `check_portfolio_redundancy` covers <60% of holdings, flag redundancy results as **"Low confidence — limited coverage."** Do not present redundancy pairs as definitive findings.
- **Scoring**: If any holding could not be scored after fallback, list unscored symbols explicitly.

## Macro Misalignment Check

Derive home markets from RIC suffixes across all holdings:
- `.O`, `.N` → United States
- `.L` → United Kingdom
- `.T` → Japan
- `.HK` → China/Hong Kong
- `.DE` → Germany
- `.PA` → France
- `.AX` → Australia
- `.OL` → Norway
- `.TW` → Taiwan
- `.KS` → South Korea

Call `list_macro_countries` to check coverage, then `macro_analyst` with component="tactical" for each unique covered market (cap at 3). Compare sector weights against tactical sector tilts to identify misalignment.
