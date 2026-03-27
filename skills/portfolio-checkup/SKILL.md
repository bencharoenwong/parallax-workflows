---
name: parallax-portfolio-checkup
description: "Individual investor portfolio checkup: health flags, factor scores, redundancy, macro context, and plain-language recommendations via Parallax MCP tools. Holdings as [{symbol, weight}]. NOT for fund manager briefs (use /parallax-morning-brief), not for client reviews (use /parallax-client-review)."
user-invocable: true
negative-triggers:
  - Fund manager morning brief → use /parallax-morning-brief
  - Client portfolio review (RIA) → use /parallax-client-review
  - Single stock analysis → use /parallax-should-i-buy
gotchas:
  - JIT-load _parallax/parallax-conventions.md for fallback patterns and parallel execution
  - JIT-load references/health-flags.md for the 5-flag health system, thresholds, and mixed-exchange fallback
  - Holdings must be in RIC format with weights summing to ~1.0
  - Mixed-exchange portfolios may have partial scoring coverage — apply split-and-merge fallback
  - Plain language output — no finance jargon
---

# Portfolio Checkup

Plain-language portfolio health check with health flags for individual investors.

## Usage

```
/parallax-portfolio-checkup [{"symbol":"AAPL.O","weight":0.30},{"symbol":"MSFT.O","weight":0.25},{"symbol":"VZ.N","weight":0.20},{"symbol":"JNJ.N","weight":0.25}]
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns. JIT-load `references/health-flags.md` for the health flag system.

### Batch A — Fire scoring + macro calls in parallel

| Tool | Parameters | Notes |
|---|---|---|
| `quick_portfolio_scores` | `holdings` | Factor scores per holding + portfolio |
| `check_portfolio_redundancy` | `holdings` | Overlap detection |
| `list_macro_countries` | — | Check which markets are covered |

### Batch B — Macro context (after Batch A)

Derive home markets from RIC suffixes across holdings. Call `macro_analyst` with component="tactical" for each unique covered market (cap at 3).

### Batch C — Health flag evaluation

Per `references/health-flags.md`, evaluate all 5 flags:

1. **Low Score** — Overall ≤ 5.0?
2. **Concentration** — Any single holding >15%? Top-3 >45%?
3. **Redundancy** — ≥ 2 redundant pairs? (flag as low-confidence if coverage <60%)
4. **Value Trap** — Portfolio value score ≤ 3.0?
5. **Macro Misalignment** — Overweight in sectors flagged unfavourable?

If `quick_portfolio_scores` coverage <50%: execute mixed-exchange fallback (split by exchange, re-score, merge).

Assign health status: **Healthy** (0 flags) · **Monitor** (1-2) · **Attention** (3+)

### Step 4 — Interpret in plain language

Explain scores and flags in plain terms:
- High VALUE = tilts toward cheaper stocks
- High QUALITY = strong balance sheets and profitability
- High MOMENTUM = stocks with recent price strength
- High DEFENSIVE = lower volatility, stable businesses

## Output Format

- **Portfolio Health Status** (Healthy/Monitor/Attention badge with flag count)
- **Your Portfolio Scorecard** (simple factor table with plain-language labels; flag indicators per holding)
- **Health Flags** (each triggered flag explained in plain language — what it means, why it matters)
- **Overlap Alert** (if redundancy found, explain why; include reliability note if coverage <60%)
- **Macro Context** (2-3 sentences on relevant economic environment — skip if no covered markets)
- **What This Means** (2-3 plain-language paragraphs)
- **Consider** (suggestions prioritized by flag severity, framed as questions not directives)

Keep tone friendly and educational.
