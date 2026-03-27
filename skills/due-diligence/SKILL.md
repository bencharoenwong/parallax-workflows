---
name: parallax-due-diligence
description: "Full research analyst due diligence: all financial statements, Palepu framework, technicals, news, score trends, and full CG research report via Parallax MCP tools. Symbol in RIC format. NOT for quick checks (use /parallax-should-i-buy), not for position deep dives without Palepu (use /parallax-deep-dive)."
user-invocable: true
negative-triggers:
  - Quick stock evaluation → use /parallax-should-i-buy
  - Position deep dive (no Palepu) → use /parallax-deep-dive
  - Peer comparison only → use /parallax-peer-comparison
gotchas:
  - JIT-load _shared/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - get_financial_analysis (Palepu) is async ~2-5 min
  - get_stock_report is async ~1-2 min and is a PAID endpoint
  - Wait for each async step before proceeding
  - This is the most thorough and expensive workflow — use for serious research only
---

# Full Due Diligence

Comprehensive analyst-grade due diligence using all available Parallax tools.

## Usage

```
/parallax-due-diligence AAPL.O
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_shared/parallax-conventions.md` for execution mode, RIC resolution, and fallback patterns.

### Batch A — All instant + async data calls (parallel)

Fire all simultaneously:

| Tool | Parameters | Notes |
|---|---|---|
| `get_company_info` | `symbol` | Company profile |
| `get_financials` | `symbol`, statement="income", periods=4 | Income statement |
| `get_financials` | `symbol`, statement="balance_sheet", periods=4 | Balance sheet |
| `get_financials` | `symbol`, statement="cash_flow", periods=4 | Cash flow |
| `get_financials` | `symbol`, statement="ratios", periods=4 | Key ratios |
| `get_technical_analysis` | `symbol` | Trend, momentum, support/resistance |
| `get_score_analysis` | `symbol`, weeks=52 | Factor score trajectory |
| `get_news_synthesis` | `symbol` | Async — don't block output |
| `get_financial_analysis` | `symbol` | Async ~2-5 min — Palepu framework |

### Batch B — Full report (after Batch A, user confirmation recommended)

Call `get_stock_report` for comprehensive CG research report with PDF/HTML links. This is a **PAID endpoint** (~1-2 min async).

## Output Format

Analyst-grade research report. Precision over brevity. Include raw data tables.

- **Company Overview** (business, sector, market cap, key thesis)
- **Income Statement Analysis** (4-year trends: revenue, margins, EPS)
- **Balance Sheet Analysis** (leverage, liquidity, asset quality)
- **Cash Flow Analysis** (FCF, capex, cash conversion)
- **Key Ratios** (valuation, profitability, efficiency — table format)
- **Palepu Framework** (profitability decomposition, accruals quality, solvency assessment)
- **Technical Stance** (trend, momentum, support/resistance, volume)
- **News Intelligence** (material developments only)
- **Factor Score Trajectory** (52-week trend: which factors improving/declining)
- **CG Research Report** (link to PDF/HTML from get_stock_report)
- **Synthesis & Key Risks** (bull case, bear case, key uncertainties)

Note: `get_financial_analysis` (~2-5 min) and `get_stock_report` (~1-2 min, paid) are async. Begin assembling output from instant tools while async calls resolve.
