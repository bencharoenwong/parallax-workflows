---
name: parallax-thematic-screen
description: "Thematic stock screen: build a universe from natural language, score top picks, compare peers, and check financials via Parallax MCP tools. NOT for single stock analysis (use /parallax-should-i-buy), not for portfolio review (use /parallax-client-review)."
user-invocable: true
negative-triggers:
  - Single stock analysis → use /parallax-should-i-buy
  - Portfolio review → use /parallax-client-review
  - Peer comparison of known stock → use /parallax-peer-comparison
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - build_stock_universe uses keyword matching on ~65K company descriptions — NOT semantic similarity or factor-score filtering
  - Use sector-level queries ("US large cap [sector]") rather than abstract concepts ("high quality momentum") for better results
  - Default top_n is 5 — adjust for broader or narrower screens
  - get_peer_snapshot called once per top pick (N calls) — fire in parallel
  - get_financials called for top 3 only
  - If build_stock_universe returns zero results, rephrase with broader sector terms and retry once
  - If still zero or tool fails, fall back to peer-chain expansion: identify 1-2 anchor stocks that represent the theme, call get_peer_snapshot for each, use their combined peer lists as the screen universe
  - Review results for relevance before presenting — filter out companies that don't match the theme even if the tool returned them
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

1. **Build Universe** — Call `build_stock_universe` with a sector-level query derived from the theme (e.g., "AI infrastructure" → "US semiconductor data center hardware"). If the tool fails or returns zero results after one retry with broader terms, fall back to peer-chain expansion: identify 1-2 well-known stocks in the theme (e.g., NVDA.O for AI infrastructure), call `get_peer_snapshot` for each, and use their combined peer groups as the screen. Review all results for relevance — filter out companies that don't match the theme.
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

Always end with: *"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*
