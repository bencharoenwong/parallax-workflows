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
---

# Morning Brief

Generate a structured fund manager morning brief by orchestrating Parallax MCP tools.

## Usage

```
/parallax-morning-brief [{"symbol":"AAPL.O","weight":0.25},{"symbol":"MSFT.O","weight":0.20},{"symbol":"JPM.N","weight":0.15},{"symbol":"JNJ.N","weight":0.15},{"symbol":"XOM.N","weight":0.25}]
```

Optional: append `market=Japan` or `top_n=5` after the portfolio JSON.

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, and fallback patterns. JIT-load `_parallax/house-view/loader.md` for active-view validation and integration.

### Batch 0 — Load Active House View (before Batch A)

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
3. For top N holdings by weight (default 3): call `get_news_synthesis` (async — don't block output).
4. Append audit log entry per loader.md §6.

## Output Format

Present as a structured morning brief, under 800 words:

- **House View Preamble** (only if view active) — 1-line summary per loader.md §5
- **Market Regime & Signals** (2-3 sentences; if view active, note alignment/divergence with view's regime call)
- **Macro Snapshot** (bullet points)
- **Portfolio Factor Tilt** (table: VALUE, QUALITY, MOMENTUM, DEFENSIVE scores; if view active, add column showing view-target factor)
- **Redundancy & Alignment Alerts** (only if flagged; include View Misalignment / View Excluded if view active)
- **Holding News** (one paragraph per holding)
- **Action Items** (what deserves attention today; if view active, prioritize toward view rebalance direction)

Lead with what matters.

If active view: use the view-aware disclaimer per loader.md §5. Otherwise:

> These are analytical outputs based on Parallax factor scores, not investment advice.
