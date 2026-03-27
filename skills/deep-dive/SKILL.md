---
name: parallax-deep-dive
description: "Deep dive on a single position: company profile, peer comparison, financials, score trends, macro context, technicals, dividends, news, and AI assessment via Parallax MCP tools. Symbol in RIC format. NOT for quick stock checks (use /parallax-should-i-buy), not for portfolio-level analysis (use /parallax-morning-brief)."
user-invocable: true
negative-triggers:
  - Quick stock check → use /parallax-should-i-buy
  - Portfolio analysis → use /parallax-morning-brief
  - Full due diligence with Palepu → use /parallax-due-diligence
  - Peer comparison only → use /parallax-peer-comparison
gotchas:
  - JIT-load _shared/parallax-conventions.md for RIC resolution, parallel execution, fallbacks, and HK ambiguity protocol
  - get_assessment is async and uses Perplexity — may take 30-90s
  - get_assessment prompt should incorporate macro context, score trends, and dividend profile alongside existing data
  - For non-US symbols, apply HK ambiguity cross-check from shared conventions
---

# Position Deep Dive

Thorough single-position analysis for fund managers using Parallax MCP tools.

## Usage

```
/parallax-deep-dive AAPL.O
/parallax-deep-dive MSFT.O "Is the AI capex cycle sustainable?"
```

Accepts RIC format. For plain tickers, resolve per shared conventions.

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_shared/parallax-conventions.md` for execution mode, RIC resolution, fallback patterns, and HK ambiguity protocol.

### Batch A — Fire all data calls in parallel

| Tool | Parameters | Notes |
|---|---|---|
| `get_company_info` | `symbol` | Sector, market cap, description |
| `get_peer_snapshot` | `symbol` | Factor scores + peer ranking |
| `get_financials` | `symbol`, statement="summary" | Revenue/income narrative |
| `get_financials` | `symbol`, statement="ratios", periods=1 | Key ratios: margins, ROE, P/E |
| `get_score_analysis` | `symbol`, weeks=52 | 52-week factor trend |
| `get_technical_analysis` | `symbol` | Trend, momentum, support/resistance |
| `get_stock_outlook` | `symbol`, aspect="analyst_targets" | Price targets |
| `get_stock_outlook` | `symbol`, aspect="recommendations" | Buy/hold/sell |
| `get_stock_outlook` | `symbol`, aspect="risk_return" | Risk/return vs peers |
| `get_stock_outlook` | `symbol`, aspect="dividends", limit=8 | Dividend history |
| `get_news_synthesis` | `symbol` | Async — don't block output |

### Batch B — Macro context (after Batch A)

Needs company info for market reasoning:

1. Call `list_macro_countries` to check coverage.
2. Identify relevant markets (home market + revenue geographies + commodity/supply chain). Cap at 3 markets.
3. Call `macro_analyst` with component="tactical" for each relevant covered market.

### Batch C — AI Assessment (after A + B)

Call `get_assessment` with a comprehensive prompt incorporating **all** findings: factor scores, score trends, key ratios, technical stance, macro context, dividend profile, risk/return vs peers, and the user's specific question/thesis if provided.

Apply graceful fallback patterns from shared conventions for any missing data.

## Output Format

- **Company Overview** (3 sentences)
- **Macro Environment** (regime context for relevant markets, factor implications)
- **Factor Profile** (table: each factor score with peer rank + 52-week trend direction)
- **Financial Highlights** (key ratios, trends)
- **Dividend Profile** (yield, payout ratio, consistency — or "Not a dividend payer")
- **Risk/Return Profile** (volatility, Sharpe context vs peers)
- **Technical Stance** (trend, key levels, momentum)
- **News Catalyst Watch** (material items only)
- **Assessment** (AI deep-research synthesis — includes macro + trend data)
- **Risk Factors** (what could go wrong)
