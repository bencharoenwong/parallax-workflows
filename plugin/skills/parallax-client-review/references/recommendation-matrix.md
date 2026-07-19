# Recommendation Priority Matrix

## Priority Levels

Priority is determined by the number of overlapping health flags on a single holding.

| Priority | Condition | Typical Actions |
|---|---|---|
| **High** | 3+ flags overlap on one holding | Trim, Exit, Reweight |
| **Medium** | 2 flags overlap on one holding | Investigate, Trim |
| **Low** | 1 flag only | Monitor, Hold |

## Health Flags

Same taxonomy and threshold values as `parallax-portfolio-checkup/references/health-flags.md`, applied at **holding level** so flags can be counted per holding for priority assignment. health-flags.md's canonical definitions are portfolio-level (verified-holdings weighted averages) and apply to parallax-portfolio-checkup; the holding-level conditions below are binding for parallax-client-review and parallax-rebalance.

| Flag | Holding-Level Condition |
|---|---|
| Low Score | Holding total score ≤ 5.0 |
| Concentration | Holding weight >15%, OR holding among the top-3 when their combined weight >45% |
| Redundancy | Holding is part of a redundant pair |
| Value Trap | Holding value score ≤ 3.0 |
| Macro Misalignment | Holding's sector flagged unfavourable by `macro_analyst` tactical |

## Threshold calibration scope

The 15% single-holding / 45% top-3 concentration cutoffs (and the <7-holding structural caveat in `parallax-conventions.md`) are calibrated for concentrated advisor/retail-scale books; on institutional-scale books they rarely trigger. Scale-aware (percentile/HHI) thresholds and per-mandate overrides are a documented roadmap item — until then, state this calibration scope in output when the book exceeds ~30 holdings.

## Recommendation Types

Action types are analytical classifications per `parallax-conventions.md` §12 — informational, not trade instructions; the §12.3 plain-label mode maps each type to a neutral status description for retail-suitable rendering.

| Type | When to Use | Description |
|---|---|---|
| **Trim** | Concentration + other flags | Classification: flagged for partial-position review — weight above threshold |
| **Exit** | 3+ flags + deteriorating score trend | Classification: flagged for full-position review — multiple converging negatives |
| **Hold** | Stable/improving scores, no flags | Classification: no threshold breach |
| **Investigate** | 2 flags but ambiguous signal | Classification: flagged for further review — ambiguous signal, see `/parallax-deep-dive` |
| **Reweight** | Concentration without other flags | Classification: flagged for allocation review — concentration risk without other flags |

Every recommendation must cite a **specific flag or data finding**. No generic advice like "consider diversifying."

## Per-Holding Drill-Down Prioritization

When deciding which holdings to analyze in detail:

### Selection Criteria (any of)
- Weight > 10% of portfolio
- Flagged by any health flag
- In a sector with macro misalignment

### Constraints
- **Cap at 8 holdings** to manage API call volume and latency
- Prioritize by: (1) flag count descending, (2) weight descending

### Drill-Down Data Per Holding

| Tool | Parameters | Purpose |
|---|---|---|
| `get_score_analysis` | `symbol`, `weeks` as int 26 (26-week lookback, non-default — see conventions §0.2) | Score trend — improving or deteriorating? |
| `get_stock_outlook` | `symbol`, `aspect="risk_return"` | Risk profile vs peers |
| `get_peer_snapshot` | `symbol` | Current factor scores + peer context |

### News (selective)

Call `get_news_synthesis` only for holdings that are:
- Weight >10% **AND** flagged, OR
- In a sector with active macro developments

Cap news calls at 5 holdings. News is async — don't block output.
