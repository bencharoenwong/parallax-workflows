# Design Spec: Loader-Pattern Rewrite (Council Item (b))

**Date:** 2026-04-21
**Status:** Draft
**Related Plan:** `docs/plans/2026-04-21-phase0-remaining-work.md`

## 1. Executive Summary

This rewrite addresses two critical failures identified in Phase 0 testing:
1. **Universe Collapse (Q-A):** `build_stock_universe` fails to handle multi-sector/multi-theme tilt-prepended queries, often collapsing to a single sector.
2. **Symbol Mapping Bug (Q-B):** `quick_portfolio_scores` mis-maps non-US symbols to incorrect companies at a ~85% rate.

The solution is to move composition and aggregation logic from the upstream Parallax tools to the client-side (Gemini CLI) using parallel atomic calls.

## 2. Technical Designs

### 2.1 Multi-sector Parallel Universe Construction

#### Before (Broken)
```javascript
// Single call with complex natural language query
const result = await mcp_parallax_build_stock_universe({
  query: "overweight financials, industrials, energy, AI infrastructure; exclude tech; mid-cap dividend focus"
});
// Result: 95% Financials, 0% AI Infrastructure.
```

#### After (Robust)
```javascript
// 1. Identify N active tilts from house-view (tilts with value != 0)
// 2. Issue N parallel calls with narrow, sector-specific queries
const [fin, ind, ene, ai] = await Promise.all([
  mcp_parallax_build_stock_universe({ query: "mid-cap financials dividend focus" }),
  mcp_parallax_build_stock_universe({ query: "mid-cap industrials dividend focus" }),
  mcp_parallax_build_stock_universe({ query: "mid-cap energy dividend focus" }),
  mcp_parallax_build_stock_universe({ query: "mid-cap AI infrastructure dividend focus" })
]);

// 3. Merge results by RIC
// 4. Deduplicate
// 5. Re-rank using composite_score * tilt_multiplier
```

### 2.2 Per-Holding Snapshot Aggregation

#### Before (Broken)
```javascript
// Batch call with symbol-mapping risk
const result = await mcp_parallax_quick_portfolio_scores({ holdings });
// Result: 6/7 companies mis-mapped; portfolio scores are contaminated.
```

#### After (Robust)
```javascript
// 1. Issue parallel calls per holding (bounded by concurrency limits)
const snapshots = await Promise.all(
  holdings.map(h => mcp_parallax_get_peer_snapshot({ symbol: h.symbol }))
);

// 2. Cross-validate names against get_company_info (Batch A)
const infos = await Promise.all(
  holdings.map(h => mcp_parallax_get_company_info({ symbol: h.symbol }))
);

// 3. Filter/Flag mismatches
const validSnapshots = snapshots.filter((s, i) => s.target_company === infos[i].name);

// 4. Compute weighted average for portfolio scores
const portfolioScores = {
  VALUE: sum(s.VALUE * weight_i) / sum(weight_i),
  QUALITY: sum(s.QUALITY * weight_i) / sum(weight_i),
  // ... etc
};
```

## 3. Implementation Plan

### 3.1 Feature Flag
- **Env Var:** `PARALLAX_LOADER_V2=1`
- **Conventions:** Update `_parallax/parallax-conventions.md` to document V2 as the preferred path when a house view is active.

### 3.2 File Changes
| File | Change Description |
|---|---|
| `_parallax/house-view/loader.md` | Add §3a (Parallel Universe) and §3b (Snapshot Aggregation) specs. |
| `_parallax/parallax-conventions.md` | Update "Symbol Cross-Validation" and "Parallel Execution" sections. |
| `portfolio-builder/SKILL.md` | Rewrite Step 1 (Universe) and Step 4/7 (Scoring). |
| `thematic-screen/SKILL.md` | Rewrite Step 1 (Universe) and Step 4 (Scoring). |
| `rebalance/SKILL.md` | Rewrite replacement search and factor verification. |
| `client-review/SKILL.md` | Replace `quick_portfolio_scores` with per-holding aggregation. |
| `morning-brief/SKILL.md` | Replace `quick_portfolio_scores` with per-holding aggregation. |
| `explain-portfolio/SKILL.md` | Replace `quick_portfolio_scores` with per-holding aggregation. |

### 3.3 Rollback Plan
Toggle `PARALLAX_LOADER_V2=0`. The skills will detect the flag and use the legacy (V1) single-call paths. Legacy paths will be deprecated and removed in Phase 1.

## 4. Verification

### 4.1 Q-A Verification
- **Test:** Run `portfolio-builder` with the "Reflationary" view (4 sectors).
- **Metric:** `max_sector_share / total <= 0.6`.
- **Expected:** Success.

### 4.2 Q-B Verification
- **Test:** Run `morning-brief` on the 7-holding dogfood portfolio.
- **Metric:** 0/7 mismatches (or mismatches are flagged and handled without contamination).
- **Expected:** Success.

### 4.3 Regression Extension
- Extend `run_regression.py` to support mocking parallel tool calls or validating that N calls were made for N tilts.
