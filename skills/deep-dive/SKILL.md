---
name: parallax-deep-dive
description: "Deep dive on a single position: company profile, peer comparison, financials, score trends, macro context, technicals, dividends, news, and AI assessment via Parallax MCP tools. Symbol in RIC format. NOT for quick stock checks (use /parallax-should-i-buy), not for portfolio-level analysis (use /parallax-morning-brief)."
negative-triggers:
  - Quick stock check → use /parallax-should-i-buy
  - Portfolio analysis → use /parallax-morning-brief
  - Full due diligence with Palepu → use /parallax-due-diligence
  - Peer comparison only → use /parallax-peer-comparison
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallbacks, and HK ambiguity protocol
  - JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §7 (single-stock conflict surfacing), §6 (audit). Do NOT apply tilts — single-stock skills surface conflicts only. The get_assessment prompt should include the active view (basis_statement + relevant tilts) so the AI assessment can address view alignment.
  - When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer
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

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, fallback patterns, and HK ambiguity protocol. JIT-load `_parallax/house-view/loader.md` for active-view validation and single-stock conflict surfacing.

### Step 0 — Load Active House View

Per `loader.md` §1-§2 + §7. If view present, capture tilt vector + excludes + basis_statement. Do NOT apply tilts to scoring. The Step 0 capture feeds Batch C's `get_assessment` prompt (so the AI can address view alignment) and the closing flag in Output.

### Batch A — Fire all data calls in parallel

| Tool | Parameters | Notes |
|---|---|---|
| `get_company_info` | `symbol` | Sector, market cap, description |
| `get_peer_snapshot` | `symbol` | Factor scores + peer ranking |
| `get_financials` | `symbol`, `statement="summary"` | Revenue/income narrative |
| `get_financials` | `symbol`, `statement="ratios"`, `periods` as int 1 (latest period only, non-default — see conventions §0.2) | Key ratios: margins, ROE, P/E |
| `get_score_analysis` | `symbol` | 52-week factor trend (server default) |
| `get_technical_analysis` | `symbol` | Trend, momentum, support/resistance |
| `get_stock_outlook` | `symbol`, `aspect="analyst_targets"` | Price targets |
| `get_stock_outlook` | `symbol`, `aspect="recommendations"` | Buy/hold/sell |
| `get_stock_outlook` | `symbol`, `aspect="risk_return"` | Risk/return vs peers |
| `get_stock_outlook` | `symbol`, `aspect="dividends"`, `limit` as int 8 (non-default; default is 20 — see conventions §0.2) | Dividend history |
| `get_news_synthesis` | `symbol` | Async — don't block output |

**Ground-truth check after Batch A** (per loader.md §5 rule 3 — required universally): cross-reference `get_peer_snapshot.target_company` against `get_company_info.name`. If mismatch, flag ⚠ MISMATCH in output; extract this stock's scores from `get_peer_snapshot.peer_list[]` by RIC match rather than the target_company field, and note that the peer comparison may be against the wrong peer group. Proceed but surface the caveat loudly.

### Batch B — Macro context (after Batch A)

Needs company info for market reasoning:

1. Call `list_macro_countries` to check coverage.
2. Identify relevant markets (home market + revenue geographies + commodity/supply chain). Cap at 3 markets.
3. Call `macro_analyst` with component="tactical" for each relevant covered market.

### Batch C — AI Assessment (after A + B)

Call `get_assessment` with a comprehensive prompt incorporating **all** findings: factor scores, score trends, key ratios, technical stance, macro context, dividend profile, risk/return vs peers, the user's specific question/thesis if provided, AND the active house view if present (basis_statement + tilts on this stock's sector/region/themes). Ask the assessor to address whether the position aligns with the view.

Apply graceful fallback patterns from shared conventions for any missing data.

## Output Format

- **Company Overview** (3 sentences)
- **Ground-truth Integrity** (only if mismatch: `input_ticker` vs `returned_name` (from get_peer_snapshot.target_company) vs `expected_name` (from get_company_info.name), with ⚠ MISMATCH flag and note on score-extraction fallback — per loader.md §5 rule 3.)
- **Macro Environment** (regime context for relevant markets, factor implications)
- **Factor Profile** (table: each factor score with peer rank + 52-week trend direction; if ⚠ MISMATCH above, scores extracted from peer_list by RIC — flag uncertainty on peer rank)
- **Financial Highlights** (key ratios, trends)
- **Dividend Profile** (yield, payout ratio, consistency — or "Not a dividend payer")
- **Risk/Return Profile** (volatility, Sharpe context vs peers)
- **Technical Stance** (trend, key levels, momentum)
- **News Catalyst Watch** (material items only)
- **Assessment** (AI deep-research synthesis — includes macro + trend data; if view active, includes view-alignment commentary)
- **Risk Factors** (what could go wrong)
- **House View Note** (only if view active and stock conflicts with view) — render per loader.md §7

Append audit log entry per loader.md §6.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise:

> These are analytical outputs based on Parallax factor scores, not investment advice.
