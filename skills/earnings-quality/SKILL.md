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
  - JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (6-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (Provenance) in Output Format.
---

<!-- white-label: integration-pattern.md -->

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
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top: `**<client_name>** earnings quality review`. Logo handling per integration-pattern.md §5.
- **Provenance** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second Provenance line.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (Provenance) when composing the Output Format.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

> *"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*
