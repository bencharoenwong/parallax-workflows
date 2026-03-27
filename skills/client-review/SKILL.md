---
name: parallax-client-review
description: "RIA/wealth advisor client portfolio review: full analysis, redundancy, health flags, macro context, per-holding drill-down, prioritized recommendations, and AI assessment via Parallax MCP tools. Holdings as [{symbol, weight}]. NOT for fund manager briefs (use /parallax-morning-brief), not for quick stock checks (use /parallax-should-i-buy)."
user-invocable: true
negative-triggers:
  - Fund manager morning brief → use /parallax-morning-brief
  - Single stock analysis → use /parallax-should-i-buy
gotchas:
  - JIT-load _parallax/parallax-conventions.md for fallback patterns and parallel execution
  - JIT-load references/recommendation-matrix.md for priority classification and drill-down criteria
  - Holdings in RIC format, weights sum to ~1.0
  - analyze_portfolio called twice — once with lens "performance", once with "concentration"
  - Per-holding drill-down capped at 8 holdings to manage latency
  - Mixed-exchange portfolios may need split scoring (see shared conventions)
  - Output should be presentation-ready for client meetings
  - get_assessment prompt should incorporate all findings including macro, flags, and recommendations
---

# Client Portfolio Review

Presentation-ready portfolio review with health flags and prioritized recommendations for wealth advisors.

## Usage

```
/parallax-client-review [{"symbol":"AAPL.O","weight":0.25},{"symbol":"BRK-B.N","weight":0.20}] client="conservative retiree, income focus, 10yr horizon" benchmark=SPY.O
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, fallback patterns, and macro reasoning. JIT-load `references/recommendation-matrix.md` for priority system.

### Batch A — Portfolio-level analysis (parallel)

| Tool | Parameters | Notes |
|---|---|---|
| `analyze_portfolio` | `holdings`, lens="performance" | Returns/risk metrics |
| `analyze_portfolio` | `holdings`, lens="concentration" | Concentration analysis |
| `check_portfolio_redundancy` | `holdings` | Overlap detection |
| `quick_portfolio_scores` | `holdings` | Factor scores (apply mixed-exchange fallback if coverage <50%) |
| `list_macro_countries` | — | Check market coverage |

### Batch B — Macro context (after Batch A)

Derive home markets from RIC suffixes. Call `macro_analyst` with component="tactical" for each unique covered market (cap 3).

### Batch C — Health flags + drill-down (after A + B)

1. Evaluate 5 health flags per holding: Low Score (≤5.0), Concentration (>15%), Redundancy (≥2 pairs), Value Trap (value ≤3.0), Macro Misalignment.
2. Flag redundancy as low-confidence if coverage <60%.
3. Assign health status: **Healthy** (0) · **Monitor** (1-2) · **Attention** (3+).
4. Select up to 8 holdings for drill-down per `references/recommendation-matrix.md`: weight >10%, any flag, or macro-misaligned. Prioritize by flag count then weight.

For each drill-down holding (parallel):

| Tool | Parameters |
|---|---|
| `get_score_analysis` | `symbol`, weeks=26 |
| `get_stock_outlook` | `symbol`, aspect="risk_return" |
| `get_peer_snapshot` | `symbol` |

News (selective, async): `get_news_synthesis` for holdings >10% weight AND flagged, or in sectors with active macro developments. Cap at 5.

### Batch D — Recommendations + Assessment (after A + B + C)

1. Per `references/recommendation-matrix.md`, assign each flagged holding a priority (High/Medium/Low) and action type (trim/exit/hold/investigate/reweight). Every recommendation must cite a specific finding.
2. Call `get_assessment` with comprehensive prompt incorporating: portfolio composition, factor scores, health flags, macro context, per-holding drill-down findings, recommendations, and client context.

## Output Format

Client-ready report:
- **Portfolio Summary** (AUM breakdown, sector allocation, top 5 holdings)
- **Health Status** (Healthy/Monitor/Attention badge with flag summary)
- **Performance vs Benchmark** (key metrics)
- **Factor Analysis** (scores with macro context interpretation for this client type)
- **Concentration & Redundancy** (flagged issues; coverage reliability note if applicable)
- **Per-Holding Analysis** (for drill-down holdings: score trend, risk profile, flags, news highlights)
- **Suitability Assessment** (alignment with client goals)
- **Recommended Actions** (prioritized High/Medium/Low per recommendation-matrix.md, with specific action types)
- **Appendix: Methodology** (brief Parallax scoring note)
