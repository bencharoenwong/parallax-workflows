# Scenario: Multi-Sector Universe Construction

**ID:** universe-multi-sector
**Description:** Verify that a reflationary house view (4 sectors) triggers parallel `build_stock_universe` calls and merge/dedupe logic.

## Input Context
- **Active View:** `reflationary-2026Q2`
- **User Query:** "US mid-cap value names"
- **V2 Flag:** `PARALLAX_LOADER_V2=1`

## Expected MCP Sequence
1. `mcp_parallax_build_stock_universe({ query: "financials US mid-cap value names" })`
2. `mcp_parallax_build_stock_universe({ query: "industrials US mid-cap value names" })`
3. `mcp_parallax_build_stock_universe({ query: "energy US mid-cap value names" })`
4. `mcp_parallax_build_stock_universe({ query: "AI infrastructure US mid-cap value names" })`

## Assertions
- **Parallelism:** All 4 calls should be issued in the same turn.
- **Merge Integrity:** Final universe must contain unique RICs from all 4 responses.
- **Divergence:** `max_sector_share / total <= 0.6`.
