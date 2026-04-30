---
name: parallax-portfolio-builder
description: "Build a portfolio from a natural language investment thesis. Constructs universe, scores, checks redundancy, and outputs allocation-ready list via Parallax MCP tools. NOT for analyzing existing portfolios (use /parallax-client-review), not for screening without allocation (use /parallax-thematic-screen)."
negative-triggers:
  - Analyzing existing portfolio → use /parallax-client-review
  - Screening without allocation → use /parallax-thematic-screen
  - Single stock analysis → use /parallax-should-i-buy
  - Rebalancing existing portfolio → use /parallax-rebalance
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §3 (multipliers), §4 (conflict resolution), §5 (output rendering), §6 (audit)
  - When active view is present, use the view-aware disclaimer per loader.md §5; otherwise use the standard disclaimer
  - build_stock_universe returns relevance-ranked results — re-rank by factor scores for quality
  - Run redundancy check BEFORE finalizing allocation to avoid sector concentration
  - analyze_portfolio responses often exceed 180K chars. Use streaming JSON extraction (Step 6) instead of waiting for full response; stream validation results progressively to user as they arrive.
  - Weights should sum to ~1.0 in final output
  - Include both the allocation table AND the factor rationale for each pick
  - The saved house view never carries Parallax-derived overlays. When the active view is silent on a dimension this portfolio decision needs, EITHER (a) treat as neutral [default — non-blocking, RM-fan-out-safe] OR (b) JIT-augment via --augment-silent flag with provenance tagged per holding [auditable]. Never fold augmentation back into the saved view.
  - **View-status banner is REQUIRED first thing in output when active view exists** — never bury after the holdings table. If execution gets compressed, this is the section that must NOT be dropped. RM uses the banner as the primary signal that the view is active and what's being applied.
  - **Phase A Parallelization:** View load and universe build run in parallel (view load is fast; universe build is the latency bottleneck). Both complete before Phase B begins.
  - **Operator verification:** see [examples/testing-posture.md](../../examples/testing-posture.md)
---

# Portfolio Builder

Construct a portfolio from a plain-English investment thesis using Parallax MCP tools.

## Usage

```
/parallax-portfolio-builder "defensive dividend-focused Asian equities under $10B market cap"
/parallax-portfolio-builder "US tech companies with strong quality and momentum scores" top_n=10
/parallax-portfolio-builder "ESG leaders in European industrials"
/parallax-portfolio-builder "EM-tilt balanced" --augment-silent   # JIT-augment dimensions the active view is silent on (default: off)
```

## Workflow

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call. Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns. JIT-load `_parallax/house-view/loader.md` for active-view validation, tilt application, and conflict-resolution rules.

### Phase A — Parallel Initialization & Scoring

Execute Steps 0–2 in parallel. All three must complete before Phase B begins. Best-effort error handling: if any step fails (timeout, validation error), flag it, continue with fallback, and proceed to Phase B.

**Step 0: Load Active House View** (parallel with Step 1 & 2)
- Per `loader.md` §1-§2: read view if present, validate hash and expiry, capture tilt vector + excludes + extraction-confidence warnings. If validation fails, run without view per loader.md §2 "Failure handling." If no view present, proceed normally.
- **Fallback on timeout (rare):** log warning, continue with empty view. Non-blocking.

**Step 1: Build Universe** (parallel with Step 0 & 2)
- Resolve user thesis vs. view per loader.md §4. If view present, prepend tilt context to the query (e.g., "exclude tech, overweight defensive sectors"). Call `build_stock_universe`. Force-include any sectors/themes with view tilt = +2 if absent from initial candidates.
- **Step 1a: Divergence assertion** (per loader.md §5 rule 4) — if the tilt-prepended query named N≥2 sectors/themes, compute `max_sector_share / total` in returned candidates. If > 0.6, emit fail-loud warning: "universe collapsed to single sector despite multi-sector request." Do NOT proceed with a collapsed universe. **Default action** (per loader.md §5 rule 4 post-2026-04-24): re-issue as N parallel per-sector `build_stock_universe` calls and merge/dedupe by symbol (keep highest-rank hit on collisions). **Fall back to refusing to render** only if the per-sector re-issue is itself skewed (e.g., some requested sectors return zero results). Known upstream limitation on the single-call path.
- **Fallback on timeout:** retry once with narrower query (e.g., single sector from thesis). If still times out, use check_portfolio_redundancy placeholder and flag output.
- **Step 1b: JIT augmentation gate (opt-in)** — After universe is built, identify dimensions the THESIS depends on but the active view is silent on. **Default behavior (non-blocking, RM-fan-out-safe):** treat silent dimensions as neutral, render a one-line note in output: `Active view is silent on <dim list>; using neutral. Run with --augment-silent to fill from Parallax data for THIS portfolio.` **Opt-in `--augment-silent`:** JIT-load `_parallax/house-view/gap_detect` + `gap_suggest`. Construct a synthetic "draft view" from the active view but with the THESIS-relevant silent dimensions explicitly enumerated. Call `gap_detect.detect_gaps()` scoped to those dimensions. Call `gap_suggest.plan_calls(gaps, available_markets=mcp__claude_ai_Parallax__list_macro_countries()["markets"])`. Fire the planned MCP calls in parallel. `gap_suggest.fold_responses()` → list of Suggestions. Apply each Suggestion as a tilt **only for THIS portfolio decision** — do NOT write back to `~/.parallax/active-house-view/`. Tag each augmented dimension with `[parallax_jit, <tool>[<args>]@<data_as_of>]` for the output table's "Tilt Source" column.
- **Step 1b-bis: Augmentation-not-used invitation** — If the user did NOT pass `--augment-silent` AND Step 1b's gap detection found ≥1 thesis-relevant silent dimension, render this single line in output (between the universe-built section and the Selected Holdings table): `ℹ Active view is silent on <comma list of silent dim paths> (relevant to your thesis). Re-run with --augment-silent to fill these from current Parallax data for THIS portfolio (saved view never mutates).` Single line, no AskUserQuestion (RM-fan-out-safe — does not block invocation). Skip if no silent dims found OR if --augment-silent was already passed.

**Step 2: Score Top Picks** (parallel with Step 0 & 1)
- For top N (default 10), call `get_peer_snapshot` per candidate **in parallel**. **Prefer per-holding `get_peer_snapshot` aggregation over batch `quick_portfolio_scores`** for portfolio factor profile — the batch tool has a symbol-mapping bug (see parallax-conventions.md §2) that mis-attributes scores to the wrong company for most non-US tickers. Only use `quick_portfolio_scores` after every returned `company_name` has been cross-validated against `get_company_info`.
- **Fallback on timeout:** if N > 5, retry with top 5 only and flag in output. If single-call timeouts persist, degrade to quick_portfolio_scores with name validation.

### Phase B — Sequential Selection, Validation & Optimization

Begin only after Phase A completes. Steps 3–6 have tight dependencies; execute sequentially.

**Step 3: Rank & Select**
- If view present, re-rank by `composite × multiplier(holding's sector/region/theme)` per loader.md §3 multiplier tables. Apply factor tilt re-weighting per loader.md §3 "Factor tilts." Drop candidates that match `tilts.excludes` (surface block message per loader.md §4 exception). Select top holdings (default 5-8).

**Step 4: Redundancy Check**
- Call `check_portfolio_redundancy` with proposed equal-weight allocation. **Sanity-check the response**: if the portfolio has >60% concentration in a single sector but `sector_concentration: {}` is empty and `"well-diversified"` is returned, the tool's concentration detection has silently failed — fall back to computing concentration client-side from per-holding sectors and flag the tool bug in output.

**Step 5: Optimize Weights**
- Adjust weights based on scores, redundancy flags, sector balance, AND tilt multipliers. Cap any single sector at 2× its neutral exposure when view is +2 (loader.md §3 cap rule). For factor profile verification, aggregate per-holding `get_peer_snapshot` scores weighted by portfolio weight (do NOT rely on `quick_portfolio_scores` unless all company names validated).

**Step 6: Validate** (streaming)
- Call `analyze_portfolio` on the final allocation with `stream=true` to enable streaming JSON extraction. **Fallback for large responses:** use streaming; if streaming unavailable or times out, fall back to `check_portfolio_redundancy` + `quick_portfolio_scores` for light validation. 
- **When `--augment-silent` was applied:** the audit entry MUST carry `augmented_dimensions: [{path, source_tool, source_call_args, data_as_of}]` so the per-portfolio JIT augmentation provenance is on the audit chain and recoverable for compliance review. When `--augment-silent` was NOT applied but silent dimensions existed, log `silent_dimensions_skipped: [...]` so the auditor can see what wasn't filled.
- Append audit log entry per loader.md §6.

## Output Format

- **House View Preamble** (REQUIRED FIRST when view active — render BEFORE any other section, never bury after the holdings table) — Per loader.md §5. MUST include: short view_id (first 8 chars), view_name, `effective_date → valid_through`, and a one-line summary `Applying tilts: <comma list of non-zero tilt names with values>`. If `--augment-silent` was used, append `JIT-augmented: <list of dim paths>`. This preamble is the user's primary signal that the view is active and what it's doing. If execution gets token-compressed, KEEP this section — drop other sections first if needed.
- **Investment Thesis** (restate and refine the user's intent; note any view-vs-thesis conflicts inline per loader.md §4)
- **Universe Built** (how many candidates, key sectors; note force-includes from +2 tilts and excludes applied; surface divergence-assertion result per loader.md §5 rule 4)
- **Selected Holdings** (table: `input_ticker`, `returned_name` (from scoring-tool response), `expected_name` (from get_company_info), sector, total score, weight, key factor strengths; if view active, include a "Tilt Effect" column showing the multiplier applied to each holding AND a "Tilt Source" column tagging the dimension's source. **Tilt Source enforcement (compliance contract):** EVERY row × dimension cell MUST carry a non-empty tag in `{[house_view: <path>=<value>], [parallax_jit, <tool>[<args>]@<date>], [neutral, <reason>]}`. If any cell would be empty, that's a runtime bug — emit `⚠ Tilt Source missing for <row> × <dim>; verify before relying on this output` and refuse to claim the output is compliance-ready. **Flag any row where `returned_name ≠ expected_name` with ⚠ MISMATCH and do not treat that row's scores as authoritative** — per loader.md §5 rule 3.)
- **View-Effect Summary** (only when view active AND ≥1 holding's ranking shifted vs raw-score order) — One paragraph: `Without the active view, the top-N ranking would have been [list]. With the view's tilts applied, ranking is [list]. The biggest change: <name> moved from #X to #Y because <view tilt that drove it: e.g., 'US +1 region multiplier + Defensive 10 × low_vol +2 factor re-weight'>.` This section is the auditability story made tangible per portfolio — it lets the RM defend "the view materially affected this allocation" rather than asserting it.
- **Portfolio Factor Profile** (VALUE, QUALITY, MOMENTUM, DEFENSIVE scores — computed as weighted aggregate of per-holding `get_peer_snapshot` scores; note `quick_portfolio_scores` batch output only if all names cross-validated)
- **Redundancy Notes** (any overlap flagged and how it was resolved; include client-computed sector concentration if `check_portfolio_redundancy` returned an empty concentration map on a clearly-concentrated portfolio)
- **Implementation Notes** (liquidity, position sizing, suggested rebalance frequency)

If active view: use the view-aware disclaimer per loader.md §5. Otherwise:

> These are analytical outputs based on Parallax factor scores, not investment advice.
