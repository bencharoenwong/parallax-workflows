---
name: parallax-peer-comparison
description: "Research analyst peer comparison: peer snapshot, exported data, score trend analysis, and relative price performance via Parallax MCP tools. Symbol in RIC format. NOT for single stock analysis (use /parallax-deep-dive), not for portfolio analysis (use /parallax-morning-brief)."
negative-triggers:
  - Single stock deep dive → use /parallax-deep-dive
  - Portfolio analysis → use /parallax-morning-brief
  - Full due diligence → use /parallax-due-diligence
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - Identifies top 2 peers automatically from get_peer_snapshot
  - "Peer symbols from get_peer_snapshot may lack RIC suffixes. Before passing to Batch B tools, resolve each peer symbol to RIC format using the exchange suffix table in parallax-conventions.md (e.g., GM → GM.N, F → F.N). Single-letter symbols will fail without the suffix."
  - Makes 3 calls each for score trends and price series (primary + 2 peers)
  - export_peer_comparison and export_price_series return structured JSON
---

# Peer Comparison

Structured peer comparison analysis for research analysts.

## Usage

```
/parallax-peer-comparison AAPL.O
/parallax-peer-comparison AAPL.O weeks=26
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, and fallback patterns.

### Batch A — Peer identification

1. Call `get_peer_snapshot`. Identify the peer group and top 2 most relevant peers.
2. Call `export_peer_comparison` with format "json".

### RIC Resolution — Resolve peer symbols before Batch B

Peer symbols from `get_peer_snapshot` may lack exchange suffixes (e.g., `GM` instead of `GM.N`). Before proceeding, resolve each peer symbol to RIC format using the exchange suffix table in `parallax-conventions.md`. Single-letter tickers like `F` will trigger "Symbol too short" errors without the suffix.

### Batch B — Trends + price series (parallel, after Batch A identifies peers)

Fire all 6 calls simultaneously:
- `get_score_analysis` for primary + top 2 peers (3 calls)
- `export_price_series` for primary + top 2 peers (3 calls, 100 days, format "json")

## Output Format

- **Peer Group** (who the peers are and why they're comparable)
- **Factor Comparison Matrix** (table: all peers x all factors)
- **Score Trajectory** (which stock is improving/deteriorating fastest per factor)
- **Relative Price Performance** (comparative returns)
- **Differentiation** (strengths and weaknesses vs peers)

> These are analytical outputs based on Parallax factor scores, not investment advice.
