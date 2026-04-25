---
name: parallax-earnings-quality
description: "Forensic earnings quality analysis: revenue recognition patterns, accruals, quality sub-scores, manipulation risk, and hidden risk detection via Parallax MCP tools. Symbol in RIC format. NOT for general stock analysis (use /parallax-deep-dive), not for full due diligence (use /parallax-due-diligence)."
negative-triggers:
  - General stock analysis → use /parallax-deep-dive
  - Full due diligence → use /parallax-due-diligence
  - Quick stock check → use /parallax-should-i-buy
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - get_financial_analysis (Palepu framework) is async ~2-5 min — this is the core of the forensic analysis
  - Quality score of 10 doesn't mean no risk — dig into sub-components
  - Cross-reference news for context on any red flags found
  - Focus output on actionable risk flags, not comprehensive financial review
---

# Earnings Quality Analysis

Forensic-focused earnings quality and hidden risk detection.

## Usage

```
/parallax-earnings-quality AAPL.O
/parallax-earnings-quality 7203.T "concerned about revenue recognition"
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, and fallback patterns.

### Batch 0 — Tool Loading

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

### Batch A — Data gathering (parallel)

Fire all simultaneously:

| Tool | Parameters | Notes |
|---|---|---|
| `get_score_analysis` | `symbol` | Quality score trajectory (default 52-week lookback) |
| `get_financials` | `symbol`, `statement="income"` | Revenue/margin trends (default 4 periods) |
| `get_financials` | `symbol`, `statement="cash_flow"` | Cash conversion (default 4 periods) |
| `get_financials` | `symbol`, `statement="ratios"` | Accrual ratios |
| `get_financial_analysis` | `symbol` | Async ~2-5 min — Palepu forensic analysis |
| `get_news_synthesis` | `symbol` | Async — accounting news, auditor changes |

### Batch B — AI synthesis (after Batch A)

Call `get_assessment` with a prompt focused on: earnings quality concerns, revenue recognition patterns, accrual anomalies, cash flow vs. earnings divergence, and any specific concerns the user raised. Feed in all findings from Batch A.

## Output Format

- **Risk Summary** (red/yellow/green traffic light for overall earnings quality)
- **Quality Score Trend** (52-week trajectory with inflection points flagged)
- **Forensic Findings** (from Palepu analysis — accruals, revenue quality, cash conversion)
- **Red Flags** (specific items that warrant investigation)
- **News Context** (any accounting-related developments)
- **AI Assessment** (synthesized risk opinion)
- **Recommended Actions** (what to monitor, what warrants deeper investigation)

> These are analytical outputs based on Parallax factor scores, not investment advice.
