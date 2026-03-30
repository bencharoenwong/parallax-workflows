---
name: parallax-watchlist-monitor
description: "Monitor a watchlist of tickers: flag score changes, news alerts, technical shifts, and analyst updates via Parallax MCP tools. Provide list of symbols. NOT for single stock analysis (use /parallax-deep-dive), not for portfolio diagnostics (use /parallax-morning-brief)."
negative-triggers:
  - Single stock deep dive → use /parallax-deep-dive
  - Portfolio with weights → use /parallax-morning-brief or /parallax-client-review
  - Building a portfolio → use /parallax-portfolio-builder
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - This is a surveillance skill — optimized for breadth over depth
  - get_score_analysis with 4-8 weeks is sufficient for detecting recent changes — fire all in parallel
  - Only call get_news_synthesis for names with significant score changes (saves API calls)
  - Rank output by magnitude of change — most-changed at top
---

# Watchlist Monitor

Surveillance scan across a list of tickers — flag what's changed, what needs attention.

## Usage

```
/parallax-watchlist-monitor AAPL.O MSFT.O GOOGL.O AMZN.O META.O NVDA.O TSLA.O
/parallax-watchlist-monitor AAPL.O JPM.N XOM.N JNJ.N weeks=8
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools:

1. **Score Scan** — For each symbol, call `get_score_analysis` with 4-8 weeks of history. Compute change in total score over the period.
2. **Flag Movers** — Identify symbols with significant score changes (>1 point total score change or any factor moving >2 points).
3. **News Check** — For flagged symbols only, call `get_news_synthesis` to identify catalysts.
4. **Technical Check** — For flagged symbols, call `get_technical_analysis` for trend changes.
5. **Analyst Check** — For flagged symbols, call `get_stock_outlook` with aspect "recommendations" for consensus shifts.

## Output Format

- **Watchlist Summary** (table: all symbols, current total score, score change, alert flag)
- **Alerts** (ranked by magnitude of change):
  - **Symbol** — score change, which factors moved, brief catalyst
- **Stable Names** (one-liner each — "no material changes")
- **Recommended Actions** (which names warrant a deeper look via /parallax-deep-dive)

Keep it scannable. Lead with what changed.

> These are analytical outputs based on Parallax factor scores, not investment advice.
