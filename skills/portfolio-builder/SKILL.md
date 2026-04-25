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
  - analyze_portfolio responses often exceed 180K chars. If output is truncated, fall back to `check_portfolio_redundancy` + `quick_portfolio_scores` for validation
  - Weights should sum to ~1.0 in final output
  - Include both the allocation table AND the factor rationale for each pick
---

# Portfolio Builder

Construct a portfolio from a plain-English investment thesis using Parallax MCP tools.

## Usage

```
/parallax-portfolio-builder "defensive dividend-focused Asian equities under $10B market cap"
/parallax-portfolio-builder "US tech companies with strong quality and momentum scores" top_n=10
/parallax-portfolio-builder "ESG leaders in European industrials"
```

## Workflow

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call. Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns. JIT-load `_parallax/house-view/loader.md` for active-view validation, tilt application, and conflict-resolution rules.

0. **Load Active House View** — Per `loader.md` §1-§2: read view if present, validate hash and expiry, capture tilt vector + excludes + extraction-confidence warnings. If validation fails, run without view per loader.md §2 "Failure handling." If no view present, proceed normally.
1. **Build Universe** — Resolve user thesis vs. view per loader.md §4. If view present, prepend tilt context to the query (e.g., "exclude tech, overweight defensive sectors"). Call `build_stock_universe`. Force-include any sectors/themes with view tilt = +2 if absent from initial candidates.
1a. **Divergence assertion** (per loader.md §5 rule 4) — if the tilt-prepended query named N≥2 sectors/themes, compute `max_sector_share / total` in returned candidates. If > 0.6, emit fail-loud warning: "universe collapsed to single sector despite multi-sector request." Do NOT proceed with a collapsed universe. **Default action** (per loader.md §5 rule 4 post-2026-04-24): re-issue as N parallel per-sector `build_stock_universe` calls and merge/dedupe by symbol (keep highest-rank hit on collisions). **Fall back to refusing to render** only if the per-sector re-issue is itself skewed (e.g., some requested sectors return zero results). Known upstream limitation on the single-call path.
2. **Score Top Picks** — For top N (default 10), call `get_peer_snapshot` per candidate. **Prefer per-holding `get_peer_snapshot` aggregation over batch `quick_portfolio_scores`** for portfolio factor profile — the batch tool has a symbol-mapping bug (see parallax-conventions.md §2) that mis-attributes scores to the wrong company for most non-US tickers. Only use `quick_portfolio_scores` after every returned `company_name` has been cross-validated against `get_company_info`.
3. **Rank & Select** — If view present, re-rank by `composite × multiplier(holding's sector/region/theme)` per loader.md §3 multiplier tables. Apply factor tilt re-weighting per loader.md §3 "Factor tilts." Drop candidates that match `tilts.excludes` (surface block message per loader.md §4 exception). Select top holdings (default 5-8).
4. **Redundancy Check** — Call `check_portfolio_redundancy` with proposed equal-weight allocation. **Sanity-check the response**: if the portfolio has >60% concentration in a single sector but `sector_concentration: {}` is empty and `"well-diversified"` is returned, the tool's concentration detection has silently failed — fall back to computing concentration client-side from per-holding sectors and flag the tool bug in output.
5. **Optimize Weights** — Adjust weights based on scores, redundancy flags, sector balance, AND tilt multipliers. Cap any single sector at 2× its neutral exposure when view is +2 (loader.md §3 cap rule). For factor profile verification, aggregate per-holding `get_peer_snapshot` scores weighted by portfolio weight (do NOT rely on `quick_portfolio_scores` unless all company names validated).
6. **Validate** — Call `analyze_portfolio` on the final allocation. Append audit log entry per loader.md §6.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5
- **Investment Thesis** (restate and refine the user's intent; note any view-vs-thesis conflicts inline per loader.md §4)
- **Universe Built** (how many candidates, key sectors; note force-includes from +2 tilts and excludes applied; surface divergence-assertion result per loader.md §5 rule 4)
- **Selected Holdings** (table: `input_ticker`, `returned_name` (from scoring-tool response), `expected_name` (from get_company_info), sector, total score, weight, key factor strengths; if view active, include a "Tilt Effect" column showing the multiplier applied to each holding. **Flag any row where `returned_name ≠ expected_name` with ⚠ MISMATCH and do not treat that row's scores as authoritative** — per loader.md §5 rule 3.)
- **Portfolio Factor Profile** (VALUE, QUALITY, MOMENTUM, DEFENSIVE scores — computed as weighted aggregate of per-holding `get_peer_snapshot` scores; note `quick_portfolio_scores` batch output only if all names cross-validated)
- **Redundancy Notes** (any overlap flagged and how it was resolved; include client-computed sector concentration if `check_portfolio_redundancy` returned an empty concentration map on a clearly-concentrated portfolio)
- **Implementation Notes** (liquidity, position sizing, suggested rebalance frequency)

If active view: use the view-aware disclaimer per loader.md §5. Otherwise:

> These are analytical outputs based on Parallax factor scores, not investment advice.
