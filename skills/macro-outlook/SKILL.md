---
name: parallax-macro-outlook
description: "Full macro regime analysis with optional equity screening: country coverage, economic outlook, regime signals, factor tilt implications, and top-scoring equities in the target market via Parallax MCP tools. NOT for portfolio-level morning briefs (use /parallax-morning-brief), not for single stock analysis (use /parallax-deep-dive)."
user-invocable: true
negative-triggers:
  - Portfolio morning brief → use /parallax-morning-brief
  - Single stock analysis → use /parallax-deep-dive or /parallax-should-i-buy
  - Thematic screening across all markets → use /parallax-thematic-screen
  - Reacting to a specific news event → use /parallax-scenario-analysis
gotchas:
  - list_macro_countries shows available coverage — check before querying a country
  - check_macro_health verifies data freshness — run first to avoid stale analysis
  - macro_analyst without component gives summary; with component gives detail (monetary, fiscal, tactical, etc.)
  - get_telemetry shows how macro regime affects the scoring engine
  - Smaller/EM markets may have fewer scored equities — set expectations
---

# Macro Outlook

Deep macro regime analysis with optional equity opportunity screening. Covers any of Parallax's 40+ global markets.

## Usage

```
/parallax-macro-outlook "United States"
/parallax-macro-outlook "Japan" equities=true
/parallax-macro-outlook "China" component=tactical
/parallax-macro-outlook — compare US, Europe, Japan
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_shared/parallax-conventions.md` for execution mode and fallback patterns.

### Batch A — Coverage + regime (parallel)

| Tool | Parameters | Notes |
|---|---|---|
| `list_macro_countries` | — | Confirm markets |
| `check_macro_health` | — | Data freshness |
| `get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Market regime |

### Batch B — Macro depth (after Batch A)

1. Call `macro_analyst` for the target country without component (summary), then with monetary, fiscal, tactical.
2. Call `get_score_analysis` for a representative ETF or index for factor trends in this regime.
3. If multiple countries: repeat for each and compare.

### Batch C — Equity opportunities (optional, after Batch B)

If requested: call `build_stock_universe` with "[country] equities". For top 5: `get_peer_snapshot` (parallel). For top 3: `get_score_analysis` 26 weeks (parallel).

## Output Format

- **Regime Status** (current regime tag, key signals, headline)
- **Macro Summary** (country-level economic overview)
- **Deep Dive** (monetary, fiscal, tactical components as requested)
- **Factor Regime Interaction** (which factors are favored/disfavored in this environment)
- **Positioning Implications** (what this means for portfolio construction)
- **Top Equity Opportunities** (if equity screening included: table with symbol, name, sector, score, trend)
- **Data Freshness** (when macro data was last updated)
