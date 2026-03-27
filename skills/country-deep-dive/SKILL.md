---
name: parallax-country-deep-dive
description: "Country or region deep dive: macro environment, available equity coverage, top-scoring stocks, and investment opportunities via Parallax MCP tools. NOT for US-centric analysis (use /parallax-macro-outlook), not for thematic screening (use /parallax-thematic-screen)."
user-invocable: true
negative-triggers:
  - US macro analysis → use /parallax-macro-outlook
  - Thematic screening across all markets → use /parallax-thematic-screen
  - Single stock analysis → use /parallax-deep-dive
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - list_macro_countries first to confirm the country is covered
  - build_stock_universe can filter by geography via natural language
  - Not all 40+ markets have full macro coverage — check_macro_health confirms
  - Smaller markets may have fewer scored equities
---

# Country Deep Dive

Macro + equity opportunity analysis for a specific country or region.

## Usage

```
/parallax-country-deep-dive Japan
/parallax-country-deep-dive "Southeast Asia"
/parallax-country-deep-dive India top_n=10
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns.

### Batch A — Coverage + macro + universe (parallel)

| Tool | Parameters | Notes |
|---|---|---|
| `list_macro_countries` | — | Confirm coverage |
| `check_macro_health` | — | Data freshness |
| `build_stock_universe` | "[country] equities" | Equity universe |

### Batch B — Macro depth + scoring (after Batch A)

1. Call `macro_analyst` for the country without component (summary), then with "monetary" and "tactical".
2. For top N universe results (default 5): call `get_peer_snapshot` (parallel).
3. For top 3: call `get_score_analysis` with 26 weeks (parallel).

## Output Format

- **Country Overview** (macro summary, regime context)
- **Economic Indicators** (monetary, fiscal, tactical highlights)
- **Equity Coverage** (how many scored stocks, key sectors)
- **Top Opportunities** (table: symbol, name, sector, total score, key factor strengths)
- **Score Trends** (which top picks are improving vs. declining)
- **Investment Thesis** (synthesis: why this market, what factors favor it, key risks)
