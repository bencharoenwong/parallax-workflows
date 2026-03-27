---
name: parallax-rebalance
description: "Portfolio rebalancing with health flags and macro context: analyze current state, flag issues, generate prioritized trade instructions with score rationale via Parallax MCP tools. Holdings as [{symbol, weight}]. NOT for initial portfolio construction (use /parallax-portfolio-builder), not for diagnostic-only review (use /parallax-client-review)."
user-invocable: true
negative-triggers:
  - Building a new portfolio from scratch → use /parallax-portfolio-builder
  - Diagnostic review without trade recommendations → use /parallax-client-review
  - Single stock analysis → use /parallax-should-i-buy
gotchas:
  - JIT-load _parallax/parallax-conventions.md for fallback patterns and parallel execution
  - JIT-load client-review/references/recommendation-matrix.md for priority classification. If missing, use inline fallback: High=3+ flags (trim/exit), Medium=2 flags (investigate/trim), Low=1 flag (monitor/hold)
  - Health flags feed directly into trade action determination — High priority = strong trim/exit
  - analyze_portfolio with lens "performance" and "concentration" gives the full diagnostic
  - build_stock_universe can find replacement candidates for positions being trimmed
  - Output must include specific buy/sell/trim quantities, not just vague suggestions
  - For portfolios with 10+ holdings, prioritize score trend scans for top/bottom 5 by weight to manage latency
---

# Portfolio Rebalance

Generate prioritized trade recommendations using health flags, macro context, and Parallax scores.

## Usage

```
/parallax-rebalance [{"symbol":"AAPL.O","weight":0.30},{"symbol":"MSFT.O","weight":0.25},{"symbol":"XOM.N","weight":0.20},{"symbol":"JNJ.N","weight":0.25}]
/parallax-rebalance [holdings] target="reduce concentration, improve quality score"
/parallax-rebalance [holdings] constraints="max 25% per position, no energy sector"
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, fallback patterns, and macro reasoning. JIT-load `client-review/references/recommendation-matrix.md` for the priority system.

### Batch A — Current state (parallel)

| Tool | Parameters | Notes |
|---|---|---|
| `analyze_portfolio` | `holdings`, lens="performance" | Returns/risk metrics |
| `analyze_portfolio` | `holdings`, lens="concentration" | Concentration analysis |
| `quick_portfolio_scores` | `holdings` | Factor scores (apply mixed-exchange fallback if needed) |
| `check_portfolio_redundancy` | `holdings` | Overlap detection |
| `list_macro_countries` | — | Check market coverage |

### Batch B — Macro + score trends (after Batch A)

1. Call `macro_analyst` with component="tactical" for each unique covered market (cap 3).
2. Call `get_score_analysis` for each holding (parallel within batch) to identify deteriorating vs. improving positions. For 10+ holdings, prioritize top/bottom 5 by weight.

### Batch C — Health flags + trade decisions

1. Evaluate 5 health flags per holding: Low Score (≤5.0), Concentration (>15%), Redundancy (≥2 pairs), Value Trap (value ≤3.0), Macro Misalignment.
2. Assign priority per recommendation-matrix.md:
   - **High** (3+ flags): Strong trim/exit candidate
   - **Medium** (2 flags): Investigate + potential trim
   - **Low** (1 flag): Monitor, hold unless constraints violated
3. Determine actions combining flags + score trends + macro:
   - **Trim/Exit:** High priority holdings, or declining scores + any flag
   - **Hold:** Stable/improving scores, no flags
   - **Reweight:** Concentration flag only, scores otherwise healthy
   - **Investigate:** Medium priority but ambiguous signal (suggest `/parallax-deep-dive`)
4. For trim candidates: call `build_stock_universe` with a theme matching the portfolio's factor profile. Score candidates with `get_peer_snapshot`.

### Batch D — Validation

Call `quick_portfolio_scores` on the proposed new allocation to verify improvement.

## Output Format

- **Current Portfolio Assessment** (factor scores, concentration issues, redundancy)
- **Health Status** (Healthy/Monitor/Attention badge with flag summary)
- **Health Flags** (table: each triggered flag per holding with priority level)
- **Macro Context** (relevant market outlook, sector tilt implications for rebalancing)
- **Score Momentum** (table: each holding's score trend — improving/stable/declining)
- **Trade Recommendations** (table: Priority | Action | Symbol | Current Weight | Target Weight | Rationale — every recommendation cites a specific flag or finding)
- **Replacement Candidates** (if trimming, scored alternatives)
- **Before/After Comparison** (factor scores: current vs. proposed)
- **Implementation Notes** (suggested execution order, liquidity considerations)

Always end with: *"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*
