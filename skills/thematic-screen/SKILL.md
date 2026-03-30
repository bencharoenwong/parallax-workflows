---
name: parallax-thematic-screen
description: "Thematic stock screen: build a universe from natural language, score top picks, compare peers, and check financials via Parallax MCP tools. NOT for single stock analysis (use /parallax-should-i-buy), not for portfolio review (use /parallax-client-review)."
negative-triggers:
  - Single stock analysis → use /parallax-should-i-buy
  - Portfolio review → use /parallax-client-review
  - Peer comparison of known stock → use /parallax-peer-comparison
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - build_stock_universe searches ~65K company descriptions by semantic similarity
  - Default top_n is 5 — adjust for broader or narrower screens
  - get_peer_snapshot called once per top pick (N calls) — fire in parallel
  - get_financials called for top 3 only
---

# Thematic Screen

Discover investment opportunities by theme using Parallax's semantic universe builder.

## Usage

```
/parallax-thematic-screen "AI infrastructure companies"
/parallax-thematic-screen "clean energy utilities" top_n=10
/parallax-thematic-screen "gene therapy pure plays"
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns.

1. **Build Universe** — Call `build_stock_universe` with the theme query. Returns stocks ranked by relevance from ~65K company descriptions.
2. **Score Top Picks** — For the top N results, call `get_peer_snapshot` for each to get factor scores.
3. **Compare Peers** — For the highest-scored stock, call `export_peer_comparison` with format "json".
4. **Quick Financials** — For the top 3 picks, call `get_financials` with statement "summary".

## Output Format

- **Theme: [theme]** (brief investment thesis)
- **Universe Built** (how many stocks found, key sectors)
- **Top Picks** (table: symbol, name, sector, overall score, key factor strengths)
- **Comparison Matrix** (peer comparison for lead candidate)
- **Financial Snapshot** (revenue, margins, growth for top 3)
- **Implementation Notes** (liquidity considerations, position sizing guidance)

> These are analytical outputs based on Parallax factor scores, not investment advice.
