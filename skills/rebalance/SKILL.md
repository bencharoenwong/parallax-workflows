---
name: parallax-rebalance
description: "Portfolio rebalancing with health flags and macro context: analyze current state, flag issues, generate prioritized trade instructions with score rationale via Parallax MCP tools. Holdings as [{symbol, weight}]. NOT for initial portfolio construction (use /parallax-portfolio-builder), not for diagnostic-only review (use /parallax-client-review)."
negative-triggers:
  - Building a new portfolio from scratch → use /parallax-portfolio-builder
  - Diagnostic review without trade recommendations → use /parallax-client-review
  - Single stock analysis → use /parallax-should-i-buy
gotchas:
  - JIT-load _parallax/parallax-conventions.md for fallback patterns and parallel execution
  - JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §3 (multipliers), §4 (conflict resolution), §5 (output rendering), §6 (audit). Tilts in the view become trade-direction signals: rebalancing should move portfolio toward view-tilted weights.
  - When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer
  - JIT-load ../client-review/references/recommendation-matrix.md for priority classification. If missing, use inline fallback: High=3+ flags (trim/exit), Medium=2 flags (investigate/trim), Low=1 flag (monitor/hold)
  - Health flags feed directly into trade action determination — High priority = strong trim/exit
  - analyze_portfolio with lens "performance" and "concentration" gives the full diagnostic. WARNING: responses often exceed 180K chars (daily time series). If output is truncated or too large, fall back to `check_portfolio_redundancy` (concentration) + `quick_portfolio_scores` (factor tilt)
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

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, fallback patterns, and macro reasoning. JIT-load `_parallax/house-view/loader.md` for active-view validation and tilt application. JIT-load `../client-review/references/recommendation-matrix.md` for the priority system.

### Batch 0 — Tool Loading & Active House View

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

Per `loader.md` §1-§2: read view if present, validate hash and expiry. If view present, capture tilt vector + excludes. The view's tilts define **direction of rebalance** — current weights that diverge from view-tilted weights become rebalance candidates beyond the standard health-flag triggers. If validation fails or no view present, run rebalance using only health flags + macro context.

### Batch A — Current state (parallel, best-effort)

| Tool | Parameters | Notes |
|---|---|---|
| `analyze_portfolio` | `holdings`, lens="performance" | Returns/risk metrics. **Timeout fallback:** skip if exceeds 30s. |
| `analyze_portfolio` | `holdings`, lens="concentration" | Concentration analysis. **Timeout fallback:** skip if exceeds 30s. |
| `get_peer_snapshot` | per holding | **Primary scoring source** for `PARALLAX_LOADER_V2=1`. **Timeout handling:** fire in parallel; if N≥2 calls timeout, mark those holdings as "scores unavailable" and continue with health-flags-only scoring. Collect successful scores only. Aggregate client-side per `loader.md` §3b. **For 10+ holdings:** prioritize top/bottom 5 by weight; timeout on remaining holdings is acceptable — fall back to health flags for those positions. |
| `get_company_info` | per holding | **Ground-truth panel oracle** per loader.md §5 rule 3 — records `expected_name` for mismatch check against `get_peer_snapshot.target_company`. **Timeout handling:** if timeout, mark holding as "name verification unavailable" and flag ⚠ UNVERIFIED. |
| `check_portfolio_redundancy` | `holdings` | Overlap detection. **Timeout fallback:** if exceeds 20s, flag "redundancy check skipped" and continue. |
| `list_macro_countries` | — | Check market coverage. **Timeout fallback:** skip if exceeds 5s. |
| `quick_portfolio_scores`| `holdings` | **Legacy/V1 path only**. Do NOT use if `PARALLAX_LOADER_V2=1` and view active. **Timeout fallback:** if exceeds 10s, degrade to health-flags-only scoring. |

**After Batch A** (best-effort completion):
1. Cross-check returned names against `get_company_info` results per loader.md §5 rule 3. For `PARALLAX_LOADER_V2=1`, any mismatch in `get_peer_snapshot` is flagged ⚠ MISMATCH and excluded from aggregate calculations. Unverified holdings (name check timeout) are flagged ⚠ UNVERIFIED.
2. For holdings with no scores (timeouts), scoring is determined by health flags only — these holdings cannot be ranked by factor scores and must be evaluated by "High/Medium/Low priority" categories based on flags alone.
3. Summary output: "Batch A completed: N/M holdings scored (M-N timeouts on peer snapshots). Rebalance will proceed with health-flag-driven recommendations for scoring-unavailable holdings."

### Batch B — Macro + score trends (after Batch A)

1. Call `macro_analyst` with component="tactical" for each unique covered market (cap 3).
2. Call `get_score_analysis` for each holding (parallel within batch) to identify deteriorating vs. improving positions. For 10+ holdings, prioritize top/bottom 5 by weight.

### Batch C — Health flags + trade decisions

1. Evaluate 5 health flags per holding: Low Score (≤5.0), Concentration (>15%), Redundancy (≥2 pairs), Value Trap (value ≤3.0), Macro Misalignment.
2. **House-view alignment check** (if view active): for each holding, compute view-tilted target weight using loader.md §3 multipliers; flag holdings >25% off target as "View Misalignment." For holdings on `tilts.excludes`, flag as "View Excluded — must trim."
3. Assign priority per recommendation-matrix.md (count View Misalignment / View Excluded as flags):
   - **High** (3+ flags or View Excluded): Strong trim/exit candidate
   - **Medium** (2 flags): Investigate + potential trim
   - **Low** (1 flag): Monitor, hold unless constraints violated
4. Determine actions combining flags + score trends + macro + view tilts:
   - **Trim/Exit:** High priority holdings, View Excluded, or declining scores + any flag
   - **Hold:** Stable/improving scores, no flags, view-aligned
   - **Reweight:** Concentration flag only, OR view-tilted toward different weight than current
   - **Investigate:** Medium priority but ambiguous signal (suggest `/parallax-deep-dive`)
5. For trim candidates: Resolve user thesis vs. view per loader.md §4. If `PARALLAX_LOADER_V2=1` and view active, follow `loader.md` §3 "Application (V2)": decompose replacement theme into parallel per-sector calls, merge, and dedupe. If V1, prepend tilt context and call `build_stock_universe` once.
   - **Divergence assertion** (per loader.md §5 rule 4 — required universally): REQUIRED for V1 paths. If the query named N≥2 sectors/themes, compute `max_sector_share/total` in returned candidates. If > 0.6, emit fail-loud warning. If `PARALLAX_LOADER_V2=1`, use to verify merge quality.
   - **Ground-truth check per candidate** (per loader.md §5 rule 3): call `get_peer_snapshot` AND `get_company_info` in parallel. Drop any candidate where `returned_name ≠ expected_name` from the replacement pool (flag ⚠ MISMATCH, do not rank).
   - Filter remaining trusted candidates against `tilts.excludes` and `tilts.excludes_freeform`.

### Batch D — Validation

If `PARALLAX_LOADER_V2=1`, follow `loader.md` §3b: aggregate per-holding `get_peer_snapshot` scores for the proposed new allocation. If V1, call `quick_portfolio_scores`. If view active, verify proposed allocation aligns with view tilts within 10% per sector. Append audit log entry per loader.md §6.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble)
- **Current Portfolio Assessment** (factor scores, concentration issues, redundancy; if view active, current alignment vs view-tilted target)
- **Health Status** (Healthy/Monitor/Attention badge with flag summary)
- **Health Flags** (table: each triggered flag per holding with priority level; View Misalignment / View Excluded shown as their own flag types)
- **Macro Context** (relevant market outlook, sector tilt implications for rebalancing)
- **Score Momentum** (table: each holding's score trend — improving/stable/declining)
- **Ground-truth Integrity** (table: `input_ticker`, `returned_name`, `expected_name`, match status per holding. ⚠ MISMATCH rows are re-scored individually and flagged — scores not trusted from `quick_portfolio_scores` — per loader.md §5 rule 3.)
- **Trade Recommendations** (table: Priority | Action | Symbol | Current Weight | Target Weight | Rationale — every recommendation cites a specific flag or finding; if view active, "Rationale" includes view-tilt direction; any recommendation on a ⚠ MISMATCH holding must note scores were re-derived via `get_peer_snapshot` directly)
- **Replacement Candidates** (if trimming, scored alternatives; filtered against tilts.excludes + tilts.excludes_freeform if view active; all candidates ground-truth-validated per loader.md §5 rule 3; divergence-assertion result for replacement universe per loader.md §5 rule 4)
- **Before/After Comparison** (factor scores: current vs. proposed; if view active, alignment-to-view metric included)
- **Implementation Notes** (suggested execution order, liquidity considerations)

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise:

> These are analytical outputs based on Parallax factor scores, not investment advice.
