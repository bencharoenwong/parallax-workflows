# Scenario: Portfolio Scoring Mixed-Exchange (V2)

**ID:** portfolio-scoring-mixed-exchange
**Description:** Verify that mixed-exchange portfolios trigger per-holding `get_peer_snapshot` calls and ground-truth validation.

## Input Context
- **Active View:** `reflationary-2026Q2`
- **Portfolio:** 
  - `AAPL.O` (0.40)
  - `0700.HK` (0.30)
  - `7203.T` (0.30)
- **V2 Flag:** `PARALLAX_LOADER_V2=1`

## Expected MCP Sequence
1. `mcp_parallax_get_peer_snapshot({ symbol: "AAPL.O" })`
2. `mcp_parallax_get_peer_snapshot({ symbol: "0700.HK" })`
3. `mcp_parallax_get_peer_snapshot({ symbol: "7203.T" })`
4. `mcp_parallax_get_company_info({ symbol: "AAPL.O,0700.HK,7203.T" })` (or parallel individual calls)

## Assertions
- **Aggregation:** Portfolio scores must be weighted average of per-holding scores.
- **Validation:** If `0700.HK` snapshot returns "Tencent" but `get_company_info` says "Meituan" (bug simulation), the row must be flagged `⚠ MISMATCH` and excluded.
- **No V1:** `mcp_parallax_quick_portfolio_scores` MUST NOT be called.
