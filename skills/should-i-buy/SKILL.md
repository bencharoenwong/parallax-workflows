---
name: parallax-should-i-buy
description: "Quick stock evaluation: company overview, Parallax factor scores, financial health, score trends, macro context, dividends, news, and analyst outlook. Plain language output. Accepts plain ticker (AAPL) or RIC (AAPL.O). NOT for portfolio analysis (use /parallax-morning-brief), not for full due diligence (use /parallax-due-diligence), not for backtesting (use /backtest)."
negative-triggers:
  - Portfolio-level analysis → use /parallax-morning-brief
  - Full research report → use /parallax-due-diligence
  - Running backtests → use /backtest
  - Peer comparison deep dive → use /parallax-peer-comparison
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallbacks, and HK ambiguity protocol
  - JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §7 (single-stock conflict surfacing), §6 (audit). Do NOT apply tilts — single-stock skills surface conflicts only.
  - When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer
  - get_stock_outlook supports 4 aspects — analyst_targets, recommendations, risk_return, dividends
  - explain_methodology is free/instant — use it for any notably high or low score
  - For non-US tickers, consult the exchange suffix table in shared conventions
  - Always include the disclaimer at the end
---

# Should I Buy

Quick, plain-language stock evaluation using Parallax MCP tools.

## Usage

```
/parallax-should-i-buy AAPL
/parallax-should-i-buy MSFT.O
/parallax-should-i-buy 005930.KS
```

Accepts plain tickers (auto-converts to RIC) or RIC format directly.

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, fallback patterns, and HK ambiguity protocol. JIT-load `_parallax/house-view/loader.md` for active-view validation and single-stock conflict surfacing.

### Step 0 — Load Active House View

Per `loader.md` §1-§2 + §7. If view present, capture tilt vector + excludes. Do NOT apply tilts to scoring. After producing the standard output, check whether the stock's sector / region / themes conflict with view tilts and surface the §7 closing flag if so.

### Step 1 — Resolve Ticker

Use `get_company_info` with the plain ticker or RIC. If empty, retry with exchange suffixes per shared conventions. For `.HK`/numeric codes, apply the HK ambiguity cross-check.

### Step 2 — Fire data calls in parallel

Once RIC is confirmed, call **all of the following simultaneously**:

| Tool | Parameters | Notes |
|---|---|---|
| `get_peer_snapshot` | `symbol` | Factor scores + peer ranking |
| `get_financials` | `symbol`, `statement="summary"` | Revenue/income narrative |
| `get_score_analysis` | `symbol` | 52-week factor trend (server default) |
| `get_stock_outlook` | `symbol`, `aspect="analyst_targets"` | Price targets |
| `get_stock_outlook` | `symbol`, `aspect="recommendations"` | Buy/hold/sell |
| `get_stock_outlook` | `symbol`, `aspect="risk_return"` | Risk/return vs peers |
| `get_stock_outlook` | `symbol`, `aspect="dividends"`, `limit` as int 8 (non-default; default is 20 — see conventions §0.2) | Dividend history |
| `get_news_synthesis` | `symbol` | Async — don't block output |

**Ground-truth check after Step 2** (per loader.md §5 rule 3 — required universally): cross-reference `get_peer_snapshot.target_company` against the `get_company_info.name` resolved in Step 1. If mismatch, flag ⚠ MISMATCH in output; extract scores from `get_peer_snapshot.peer_list[]` by RIC match rather than the target_company field, and note that peer ranking may be against the wrong peer group.

### Step 3 — Macro context

After Step 1 resolves (need company info for market reasoning):

1. Call `list_macro_countries` to check coverage.
2. Identify relevant markets (home market + key revenue geographies). Cap at 2 markets.
3. Call `macro_analyst` with component="tactical" for each relevant covered market.

If no covered markets are relevant, skip macro section.

### Step 4 — Interpret and explain

- Call `explain_methodology` for any notably high (≥8) or low (≤3) factor score.
- Synthesize all data into plain-language output.
- Apply graceful fallback patterns from shared conventions for any missing data.

## Output Format

Present as a friendly, structured report:

- **The Company** (what they do, how big)
- **Ground-truth Integrity** (only if mismatch: `input_ticker` vs `returned_name` vs `expected_name`, with ⚠ MISMATCH flag and note on peer-ranking caveat — per loader.md §5 rule 3.)
- **The Scores** (simple table with plain-English interpretation; include 52-week trend direction — e.g., "Quality trending up from 5.8 to 7.2"; if ⚠ MISMATCH above, scores were extracted by RIC match from peer_list and peer rank should be treated as indicative only)
- **Financial Health** (green/yellow/red traffic light metaphor)
- **Macro Context** (2-3 sentences on the relevant economic environment — skip if no covered markets)
- **Dividends** (yield, consistency, recent changes — or "Not a dividend payer" if none)
- **Risk vs Peers** (risk/return profile relative to peer group)
- **Recent News** (bullets)
- **Analyst View** (price target range, consensus)
- **Bottom Line** (balanced 2-sentence summary — pros and cons, not a recommendation)
- **House View Note** (only if view active and stock conflicts with view) — render per loader.md §7

Append audit log entry per loader.md §6.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise:

> *"This is informational analysis, not investment advice."*
