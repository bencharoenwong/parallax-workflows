---
name: parallax-morning-brief
description: "Fund manager morning brief: market regime, macro outlook, portfolio health, and key holding news via Parallax MCP tools. Provide portfolio as [{symbol, weight}] in RIC format. NOT for individual stock analysis (use /parallax-should-i-buy), not for backtesting (use /backtest)."
negative-triggers:
  - Single stock analysis → use /parallax-should-i-buy or /parallax-deep-dive
  - Running backtests → use /backtest
  - Client portfolio review → use /parallax-client-review
  - Thematic screening → use /parallax-thematic-screen
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallbacks, and HK ambiguity protocol
  - JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §3 (multipliers), §4 (conflict resolution), §5 (output rendering), §6 (audit). Morning brief uses the view to (a) frame the macro snapshot in view-language, (b) flag holdings misaligned with view tilts, (c) prioritize action items toward view rebalance direction.
  - When active view is present, use the view-aware disclaimer per loader.md §5; otherwise use the standard disclaimer
  - get_telemetry and macro_analyst are fast-response (low latency) but not free — macro_analyst costs 5 tokens; get_news_synthesis may take 30-90s per holding
  - macro_analyst parameter is `market` (not `country`); e.g., `macro_analyst(market="United States")`
  - The macro_analyst summary call returns all components inline including tactical — do not make separate per-component calls
  - Health flags (from portfolio-checkup/references/health-flags.md) apply here too — flag portfolios needing attention
  - Per Phase 0.5f architecture (notes/2026-04-26-step-2-5-validation.md): the saved house view never carries Parallax-derived overlays. When the active view is silent on a dimension THIS brief needs (e.g., portfolio has Brazil/Mexico exposure but view silent), EITHER (a) treat as neutral for alignment computation [default — non-blocking, RM-fan-out-safe] OR (b) JIT-augment via --augment-silent flag with provenance tagged per holding [auditable]. Never fold augmentation back into the saved view.
  - **Operator verification:** see [examples/testing-posture.md](../../examples/testing-posture.md)
---

# Morning Brief

Generate a structured fund manager morning brief by orchestrating Parallax MCP tools.

## Usage

```
/parallax-morning-brief [{"symbol":"AAPL.O","weight":0.25},{"symbol":"MSFT.O","weight":0.20},{"symbol":"JPM.N","weight":0.15},{"symbol":"JNJ.N","weight":0.15},{"symbol":"XOM.N","weight":0.25}]
```

Optional: append `market=Japan`, `top_n=5`, or `--augment-silent` (JIT-augment dimensions the active view is silent on; default off — non-blocking) after the portfolio JSON.

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, and fallback patterns. JIT-load `_parallax/house-view/loader.md` for active-view validation and integration.

### Batch 0 — Tool Loading & Active House View

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

Per `loader.md` §1-§2. If view present, capture tilt vector, excludes, prose excerpt for narrative voice, and macro_regime. The brief's "Macro Snapshot" should explicitly reference the view's regime call where relevant ("Tactical macro shows X — consistent / divergent with active view's [regime] stance"). If validation fails or no view present, run brief without view.

### Batch A — Market context + portfolio scoring (parallel)

| Tool | Parameters | Notes |
|---|---|---|
| `get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Market regime |
| `macro_analyst` | market (default: US), no component | Macro summary (returns all components inline including tactical — do not make separate per-component calls) |
| `quick_portfolio_scores` | `holdings` | Factor scores |
| `check_portfolio_redundancy` | `holdings` | Overlap detection |

### Batch B — Conditional + news (after Batch A)

1. Evaluate health flags: Low Score (overall ≤5.0), Concentration (>15% single / >45% top-3), Redundancy (≥2 pairs), Value Trap (value ≤3.0).
2. **House-view alignment** (if view active): flag holdings misaligned with view tilts (>25% off view-tilted target), holdings on `tilts.excludes`, and any active-view conflicts to highlight in Action Items.
2b. **Phase 0.5f — JIT augmentation gate (opt-in)** — Identify holdings whose region/sector is silent in the saved view. **Default:** treat silent dimensions as neutral for alignment computation; one-line note in output disclosing what was skipped + how to enable. **Opt-in `--augment-silent`:** JIT-load `_parallax/house-view/gap_detect` + `gap_suggest`. Use the holdings' regions and sectors as the relevant scope. Call `gap_detect.detect_gaps()`, `gap_suggest.plan_calls(gaps, available_markets=...)` (Batch A's `macro_analyst` already pulled coverage; reuse `list_macro_countries()` if needed), fire planned calls in parallel. Apply Suggestions ONLY for THIS brief's alignment computation — saved view never mutates. Tag each augmented dimension with `[parallax_jit, <tool>[<args>]@<data_as_of>]` for the alignment-alerts table. Per `examples/phase-0.5f-jit-policies.md`: enforce 7d/30d staleness gates on each Suggestion's `data_as_of`.
3. For top N holdings by weight (default 3): call `get_news_synthesis` (async — don't block output).
4. Append audit log entry per loader.md §6. **When `--augment-silent` was applied:** the entry MUST carry `augmented_dimensions: [{path, source_tool, source_call_args, data_as_of}]` and `augment_silent_flag: true`. When NOT applied but silent dimensions existed, log `silent_dimensions_skipped: [...]` and `augment_silent_flag: false`.

## Output Format

Present as a structured morning brief, under 800 words:

- **House View Preamble** (only if view active) — 1-line summary per loader.md §5
- **Market Regime & Signals** (2-3 sentences; if view active, note alignment/divergence with view's regime call)
- **Macro Snapshot** (bullet points)
- **Portfolio Factor Tilt** (table: VALUE, QUALITY, MOMENTUM, DEFENSIVE scores; if view active, add column showing view-target factor)
- **Redundancy & Alignment Alerts** (only if flagged; include View Misalignment / View Excluded if view active; when `--augment-silent` was applied, alignment-misalignment rows show "Tilt Source" tag — `[house_view]` / `[parallax_jit, <tool>@<date>]` / `[neutral]` — so the RM can see whether the misalignment is bank-view-driven or JIT-data-driven)
- **Holding News** (one paragraph per holding)
- **Action Items** (what deserves attention today; if view active, prioritize toward view rebalance direction)

Lead with what matters.

If active view: use the view-aware disclaimer per loader.md §5. Otherwise:

> These are analytical outputs based on Parallax factor scores, not investment advice.
