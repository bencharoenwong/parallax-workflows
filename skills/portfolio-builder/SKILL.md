---
name: parallax-portfolio-builder
description: "Build a portfolio from a natural language investment thesis. Constructs universe, scores, checks redundancy, and outputs allocation-ready list via Parallax MCP tools. NOT for analyzing existing portfolios (use /parallax-client-review), not for screening without allocation (use /parallax-thematic-screen)."
user-invocable: true
negative-triggers:
  - Analyzing existing portfolio → use /parallax-client-review
  - Screening without allocation → use /parallax-thematic-screen
  - Single stock analysis → use /parallax-should-i-buy
  - Rebalancing existing portfolio → use /parallax-rebalance
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - build_stock_universe uses keyword matching, NOT factor-score filtering. It finds companies by business description relevance. Factor filtering happens in Step 2-3 (re-ranking by scores), not in the universe query.
  - Use sector-level queries ("US large cap consumer staples") rather than abstract factor concepts ("high quality defensive"). Factor concepts return keyword matches, not factor-aware results.
  - Run redundancy check BEFORE finalizing allocation to avoid sector concentration
  - Weights should sum to ~1.0 in final output
  - Include both the allocation table AND the factor rationale for each pick
  - If build_stock_universe returns <3 results, broaden the query and retry once. If still <3, fall back to get_peer_snapshot chain expansion: pick a known name in the target sector, get its peers, score those.
  - If build_stock_universe fails entirely (timeout/error), use the fallback: identify 2-3 anchor stocks that fit the thesis, call get_peer_snapshot for each, union the peer lists, score and rank.
  - If check_portfolio_redundancy finds all picks overlap, suggest diversifying across sectors
---

# Portfolio Builder

Construct a portfolio from a plain-English investment thesis using Parallax MCP tools.

## Usage

```
/parallax-portfolio-builder "defensive dividend-focused Asian equities under $10B market cap"
/parallax-portfolio-builder "US tech companies with strong quality and momentum scores" top_n=10
/parallax-portfolio-builder "ESG leaders in European industrials"
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns.

1. **Build Universe** — Call `build_stock_universe` with a sector-level query derived from the thesis (e.g., "defensive dividend Asian equities" → "Asia large cap consumer staples utilities telecommunications"). If the tool fails or returns <3 results after one retry with a broader query, fall back to peer-chain expansion: identify 2-3 anchor stocks that fit the thesis, call `get_peer_snapshot` for each, and use the union of their peer groups as the candidate universe.
2. **Score Top Picks** — For the top N results (default 10), call `get_peer_snapshot` for each to get factor scores.
3. **Rank & Select** — Re-rank candidates by total score. Select top holdings for the portfolio (default 5-8 positions).
4. **Redundancy Check** — Call `check_portfolio_redundancy` with proposed equal-weight allocation.
5. **Optimize Weights** — Adjust weights based on scores, redundancy flags, and sector balance. Call `quick_portfolio_scores` to verify final factor profile.
6. **Validate** — Call `analyze_portfolio` on the final allocation to confirm it behaves as intended.

## Output Format

- **Investment Thesis** (restate and refine the user's intent)
- **Universe Built** (how many candidates, key sectors)
- **Selected Holdings** (table: symbol, name, sector, total score, weight, key factor strengths)
- **Portfolio Factor Profile** (VALUE, QUALITY, MOMENTUM, DEFENSIVE scores)
- **Redundancy Notes** (any overlap flagged and how it was resolved)
- **Implementation Notes** (liquidity, position sizing, suggested rebalance frequency)

Always end with: *"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*
