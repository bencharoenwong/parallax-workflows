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
  - When active view is present, use the view-aware disclaimer per loader.md §5; otherwise use the standard disclaimer
  - JIT-load ../client-review/references/recommendation-matrix.md for priority classification. If missing, use inline fallback: High=3+ flags (trim/exit), Medium=2 flags (investigate/trim), Low=1 flag (monitor/hold)
  - Health flags feed directly into trade action determination — High priority = strong trim/exit
  - analyze_portfolio with lens "performance" and "concentration" gives the full diagnostic. WARNING: responses often exceed 180K chars (daily time series). If output is truncated or too large, fall back to `check_portfolio_redundancy` (concentration) + `quick_portfolio_scores` (factor tilt)
  - build_stock_universe can find replacement candidates for positions being trimmed
  - Output must include specific buy/sell/trim quantities, not just vague suggestions
  - For portfolios with 10+ holdings, prioritize score trend scans for top/bottom 5 by weight to manage latency
  - Per Phase 0.5f architecture (notes/2026-04-26-step-2-5-validation.md): the saved house view never carries Parallax-derived overlays. When the active view is silent on a dimension THIS rebalance decision needs (replacement candidate's sector/region not in the view), EITHER (a) treat as neutral [default — non-blocking, RM-fan-out-safe] OR (b) JIT-augment via --augment-silent flag with provenance tagged per holding [auditable]. Never fold augmentation back into the saved view.
  - **Operator verification:** see [examples/testing-posture.md](../../examples/testing-posture.md)
---

# Portfolio Rebalance

Generate prioritized trade recommendations using health flags, macro context, and Parallax scores.

## Usage

```
/parallax-rebalance [{"symbol":"AAPL.O","weight":0.30},{"symbol":"MSFT.O","weight":0.25},{"symbol":"XOM.N","weight":0.20},{"symbol":"JNJ.N","weight":0.25}]
/parallax-rebalance [holdings] target="reduce concentration, improve quality score"
/parallax-rebalance [holdings] constraints="max 25% per position, no energy sector"
/parallax-rebalance [holdings] target="EM tilt" --augment-silent   # JIT-augment dimensions the active view is silent on (default: off)
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, fallback patterns, and macro reasoning. JIT-load `_parallax/house-view/loader.md` for active-view validation and tilt application. JIT-load `../client-review/references/recommendation-matrix.md` for the priority system.

### Batch 0 — Tool Loading & Active House View

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

Per `loader.md` §1-§2: read view if present, validate hash and expiry. If view present, capture tilt vector + excludes. The view's tilts define **direction of rebalance** — current weights that diverge from view-tilted weights become rebalance candidates beyond the standard health-flag triggers. If validation fails or no view present, run rebalance using only health flags + macro context.

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

### Batch B-2 — Phase 0.5f JIT augmentation gate (opt-in, after Batch B)

After macro + score trends land, identify dimensions THIS rebalance decision depends on but the active view is silent on. Scope: regions and sectors of (a) current holdings, and (b) any rebalance target/constraint dimensions the user specified. Examples: holdings include a Brazil position but view is silent on `tilts.regions.brazil`; user target says "EM tilt" but view is silent on em_ex_china and the LatAm/SEA countries. **Default behavior (non-blocking, RM-fan-out-safe):** treat silent dimensions as neutral, render a one-line note in output: `Active view is silent on <dim list>; using neutral. Run with --augment-silent to fill from Parallax data for THIS rebalance.` **Opt-in `--augment-silent`:** JIT-load `_parallax/house-view/gap_detect` + `gap_suggest`. Construct a synthetic draft view from the active view but with the rebalance-relevant silent dimensions enumerated. Call `gap_detect.detect_gaps()` scoped to those dimensions. Call `gap_suggest.plan_calls(gaps, available_markets=mcp__claude_ai_Parallax__list_macro_countries()["markets"])` (Batch A already cached this response — reuse). Fire the planned MCP calls in parallel. `gap_suggest.fold_responses()` → list of Suggestions. Apply each Suggestion as a tilt **only for THIS rebalance decision** — do NOT write back to `~/.parallax/active-house-view/`. Tag each augmented dimension with `[parallax_jit, <tool>[<args>]@<data_as_of>]` for the Trade Recommendations table's "Tilt Source" column. Per `examples/phase-0.5f-jit-policies.md`: enforce 7d/30d staleness gates on each Suggestion's `data_as_of`.

### Batch C — Health flags + trade decisions

1. Evaluate 5 health flags per holding: Low Score (≤5.0), Concentration (>15%), Redundancy (≥2 pairs), Value Trap (value ≤3.0), Macro Misalignment.
2. **House-view alignment check** (if view active): for each holding, compute view-tilted target weight using loader.md §3 multipliers (treating any JIT-augmented dimension from Batch B-2 as if it were a view tilt for THIS rebalance only); flag holdings >25% off target as "View Misalignment." For holdings on `tilts.excludes`, flag as "View Excluded — must trim."
3. Assign priority per recommendation-matrix.md (count View Misalignment / View Excluded as flags):
   - **High** (3+ flags or View Excluded): Strong trim/exit candidate
   - **Medium** (2 flags): Investigate + potential trim
   - **Low** (1 flag): Monitor, hold unless constraints violated
4. Determine actions combining flags + score trends + macro + view tilts:
   - **Trim/Exit:** High priority holdings, View Excluded, or declining scores + any flag
   - **Hold:** Stable/improving scores, no flags, view-aligned
   - **Reweight:** Concentration flag only, OR view-tilted toward different weight than current
   - **Investigate:** Medium priority but ambiguous signal (suggest `/parallax-deep-dive`)
5. For trim candidates: call `build_stock_universe` with a theme matching the portfolio's factor profile AND view tilts (e.g., "high-quality defensive names" if view tilts +2 quality / +2 defensive). Score candidates with `get_peer_snapshot`. Filter against `tilts.excludes`.

### Batch D — Validation

Call `quick_portfolio_scores` on the proposed new allocation to verify improvement. If view active, verify proposed allocation aligns with view tilts within 10% per sector. Append audit log entry per loader.md §6. **When `--augment-silent` was applied:** the audit entry MUST carry `augmented_dimensions: [{path, source_tool, source_call_args, data_as_of}]` and `augment_silent_flag: true` so the per-rebalance JIT augmentation provenance is on the audit chain and recoverable for compliance review. When `--augment-silent` was NOT applied but silent dimensions existed, log `silent_dimensions_skipped: [...]` and `augment_silent_flag: false`.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5
- **Current Portfolio Assessment** (factor scores, concentration issues, redundancy; if view active, current alignment vs view-tilted target)
- **Health Status** (Healthy/Monitor/Attention badge with flag summary)
- **Health Flags** (table: each triggered flag per holding with priority level; View Misalignment / View Excluded shown as their own flag types)
- **Macro Context** (relevant market outlook, sector tilt implications for rebalancing)
- **Score Momentum** (table: each holding's score trend — improving/stable/declining)
- **Trade Recommendations** (table: Priority | Action | Symbol | Current Weight | Target Weight | Tilt Source | Rationale — every recommendation cites a specific flag or finding; "Tilt Source" tags the dimension's source: `[house_view]` when the multiplier comes from the saved view, `[parallax_jit, <tool>@<date>]` when from `--augment-silent` JIT lookup, `[neutral]` when silent + not augmented; if view active, "Rationale" includes view-tilt direction)
- **Replacement Candidates** (if trimming, scored alternatives; filtered against tilts.excludes if view active)
- **Before/After Comparison** (factor scores: current vs. proposed; if view active, alignment-to-view metric included)
- **Implementation Notes** (suggested execution order, liquidity considerations)

If active view: use the view-aware disclaimer per loader.md §5. Otherwise:

> These are analytical outputs based on Parallax factor scores, not investment advice.
