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

### Batch 0 — Tool Loading

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

### Batch A — Peer identification

1. Call `get_peer_snapshot`. Identify the peer group and top 2 most relevant peers.
2. Call `export_peer_comparison` with `format="json"`.

### RIC Resolution — Resolve peer symbols before Batch B

Peer symbols from `get_peer_snapshot` may lack exchange suffixes (e.g., `GM` instead of `GM.N`). Before proceeding, resolve each peer symbol to RIC format using the exchange suffix table in `parallax-conventions.md`. Single-letter tickers like `F` will trigger "Symbol too short" errors without the suffix.

### Batch B — Trends + price series (parallel, after Batch A identifies peers)

#### B.0 — Asset-class pre-classification (parallel, MANDATORY for price legs)

`export_price_series` is the **equity-only** price endpoint; sector/country ETFs (which `get_peer_snapshot` can occasionally surface as peers) silently return empty from it and would otherwise be dropped from the relative-price-performance comparison. Before Batch B, classify each leg (primary + top 2 peers):

- For each of the 3 legs, call `etf_profile(<plain_ticker>)` in parallel.
- `{"error": "No profile data found", ...}` → equity, route through `export_price_series`.
- Non-error response → ETF, route through `etf_daily_price`.

This adds 3 FREE/instant calls (per `_parallax/token-costs.md`).

#### B.1 — Trends + price series (parallel)

Fire all 6 calls simultaneously:
- `get_score_analysis` for primary + top 2 peers (3 calls). If the user supplied `weeks=N` in the invocation, pass it as `weeks` as int N (non-default — see conventions §0.1); otherwise rely on the server default of 52.
- For each leg classified as **equity** in B.0 → `export_price_series(symbol=<ric>, days=<N>, format="json")`. Default `days=100`.
- For each leg classified as **ETF** in B.0 → `etf_daily_price(symbol=<plain_ticker>, start_date=<today − days>, end_date=<today>)`.

**Halt-and-surface rule:** if a leg returns empty from BOTH endpoints, exclude it from the price-performance section and render an explicit note: "⚠ Could not retrieve price history for `<symbol>`; relative price chart shows the remaining legs only." Never silently drop a leg without disclosure.

## Output Format

- **Peer Group** (who the peers are and why they're comparable)
- **Factor Comparison Matrix** (table: all peers x all factors)
- **Score Trajectory** (which stock is improving/deteriorating fastest per factor)
- **Relative Price Performance** (comparative returns)
- **Differentiation** (strengths and weaknesses vs peers)

> These are analytical outputs based on Parallax factor scores, not investment advice.
