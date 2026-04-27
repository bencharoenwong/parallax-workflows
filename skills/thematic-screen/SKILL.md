---
name: parallax-thematic-screen
description: "Thematic stock screen: build a universe from natural language, score top picks, compare peers, and check financials via Parallax MCP tools. NOT for single stock analysis (use /parallax-should-i-buy), not for portfolio review (use /parallax-client-review)."
negative-triggers:
  - Single stock analysis → use /parallax-should-i-buy
  - Portfolio review → use /parallax-client-review
  - Peer comparison of known stock → use /parallax-peer-comparison
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §3 (multipliers), §4 (conflict resolution), §5 (output rendering), §6 (audit). The user-supplied theme is sovereign per §4 "Explicit user scope is sovereign" — render conflict banner if theme contradicts view tilts.
  - When active view is present, use the view-aware disclaimer per loader.md §5; otherwise use the standard disclaimer
  - build_stock_universe searches ~65K company descriptions by semantic similarity
  - Default top_n is 5 — adjust for broader or narrower screens
  - get_peer_snapshot called once per top pick (N calls) — fire in parallel
  - get_financials called for top 3 only
  - Per Phase 0.5f architecture (notes/2026-04-26-step-2-5-validation.md): the saved house view never carries Parallax-derived overlays. When the active view is silent on a dimension THIS thematic screen depends on (theme touches sectors/regions not in view), EITHER (a) treat as neutral [default — non-blocking, RM-fan-out-safe] OR (b) JIT-augment via --augment-silent flag with provenance tagged per pick [auditable]. Never fold augmentation back into the saved view.
---

# Thematic Screen

Discover investment opportunities by theme using Parallax's semantic universe builder.

## Usage

```
/parallax-thematic-screen "AI infrastructure companies"
/parallax-thematic-screen "clean energy utilities" top_n=10
/parallax-thematic-screen "gene therapy pure plays"
/parallax-thematic-screen "ASEAN reshoring beneficiaries" --augment-silent   # JIT-augment dimensions the active view is silent on (default: off)
```

## Workflow

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call. Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns. JIT-load `_parallax/house-view/loader.md` for active-view validation and conflict resolution.

0. **Load Active House View** — Per `loader.md` §1-§2. If view present, capture tilt vector + excludes. Resolve user theme vs view per §4: theme is sovereign, but conflicts surface as banners (e.g., theme="AI infrastructure" + view says `tech: -2` → screen runs as requested with "House view is UW tech; screen run per your explicit theme" banner).
1. **Build Universe** — Call `build_stock_universe` with the theme query. If view active and theme is silent on a sector with view tilt = -2, append "exclude [sector]" to the query. Filter results against `tilts.excludes`.
1b. **Phase 0.5f — JIT augmentation gate (opt-in)** — After universe is built, identify dimensions THIS theme depends on but the active view is silent on. Theme parsing yields target sectors/regions/countries (e.g., "ASEAN reshoring" → regions = {malaysia, thailand, vietnam, indonesia, philippines}, sectors = {industrials, materials}). **Default:** treat silent dimensions as neutral; one-line note in output. **Opt-in `--augment-silent`:** JIT-load `_parallax/house-view/gap_detect` + `gap_suggest`. Construct draft view with theme-relevant silent dimensions enumerated. Call `gap_detect.detect_gaps()` scoped to those dimensions. Call `gap_suggest.plan_calls(gaps, available_markets=mcp__claude_ai_Parallax__list_macro_countries()["markets"])`. Fire planned MCP calls in parallel. `gap_suggest.fold_responses()` → list of Suggestions. Apply each Suggestion as a tilt **only for THIS screen** — saved view never mutates. Tag each augmented dimension with `[parallax_jit, <tool>[<args>]@<data_as_of>]` for the Top Picks table's "Tilt Source" column. Per `examples/phase-0.5f-jit-policies.md`: enforce 7d/30d staleness gates on each Suggestion's `data_as_of`.
2. **Score Top Picks** — For the top N results, call `get_peer_snapshot` for each to get factor scores. If view active, re-rank by `composite × multiplier(holding's sector)` per loader.md §3 AND apply factor-tilt re-weighting per loader.md §3 "Factor tilts."
3. **Compare Peers** — For the highest-scored stock, call `export_peer_comparison` with format "json".
4. **Quick Financials** — For the top 3 picks, call `get_financials` with statement "summary". Append audit log entry per loader.md §6. **When `--augment-silent` was applied:** the audit entry MUST carry `augmented_dimensions: [{path, source_tool, source_call_args, data_as_of}]` and `augment_silent_flag: true`. When NOT applied but silent dimensions existed, log `silent_dimensions_skipped: [...]` and `augment_silent_flag: false`.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5
- **Theme: [theme]** (brief investment thesis; note view conflict inline if applicable)
- **Universe Built** (how many stocks found, key sectors; note any exclusions applied)
- **Top Picks** (table: symbol, name, sector, overall score, key factor strengths; if view active, add "Tilt Effect" column AND a "Tilt Source" column tagging each pick's dominant theme-dimension source: `[house_view]` when the multiplier comes from the saved view, `[parallax_jit, <tool>@<date>]` when from `--augment-silent` JIT lookup, `[neutral]` when silent + not augmented)
- **Comparison Matrix** (peer comparison for lead candidate)
- **Financial Snapshot** (revenue, margins, growth for top 3)
- **Implementation Notes** (liquidity considerations, position sizing guidance)

If active view: use the view-aware disclaimer per loader.md §5. Otherwise:

> These are analytical outputs based on Parallax factor scores, not investment advice.
