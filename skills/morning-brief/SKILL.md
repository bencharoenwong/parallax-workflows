---
name: parallax-morning-brief
description: "Fund manager morning brief: market regime, macro outlook, portfolio health, and key holding news via Parallax MCP tools. Provide portfolio as [{symbol, weight}] in RIC format. NOT for individual stock analysis (use /parallax-should-i-buy), not for backtesting."
user-invocable: true
negative-triggers:
  - Single stock analysis → use /parallax-should-i-buy or /parallax-deep-dive
  - Running backtests → not covered by this workflow set
  - Client portfolio review → use /parallax-client-review
  - Thematic screening → use /parallax-thematic-screen
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallbacks, and HK ambiguity protocol
  - get_telemetry and macro_analyst are free/instant; get_news_synthesis may take 30-90s per holding
  - If regime suggests stress, also pull macro tactical component
  - Health flags (from parallax-portfolio-checkup/references/health-flags.md) apply here too — flag portfolios needing attention
---

# Morning Brief

Generate a structured fund manager morning brief by orchestrating Parallax MCP tools.

## Usage

```
/parallax-morning-brief [{"symbol":"AAPL.O","weight":0.25},{"symbol":"MSFT.O","weight":0.20},{"symbol":"JPM.N","weight":0.15},{"symbol":"JNJ.N","weight":0.15},{"symbol":"XOM.N","weight":0.25}]
```

Optional: append `market=Japan` or `top_n=5` after the portfolio JSON.

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, and fallback patterns.

### Batch A — Market context + portfolio scoring (parallel)

| Tool | Parameters | Notes |
|---|---|---|
| `get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Market regime |
| `macro_analyst` | market (default: US), no component | Macro summary |
| `quick_portfolio_scores` | `holdings` | Factor scores |
| `check_portfolio_redundancy` | `holdings` | Overlap detection |

### Batch B — Conditional + news (after Batch A)

1. If regime suggests stress: call `macro_analyst` with component "tactical".
2. Evaluate health flags: Low Score (overall ≤5.0), Concentration (>15% single / >45% top-3), Redundancy (≥2 pairs), Value Trap (value ≤3.0).
3. For top N holdings by weight (default 3): call `get_news_synthesis` (async — don't block output).

## Output Format

Present as a structured morning brief, under 800 words:

- **Market Regime & Signals** (2-3 sentences)
- **Macro Snapshot** (bullet points)
- **Portfolio Factor Tilt** (table: VALUE, QUALITY, MOMENTUM, DEFENSIVE scores)
- **Redundancy Alerts** (only if flagged)
- **Holding News** (one paragraph per holding)
- **Action Items** (what deserves attention today)

Lead with what matters.
