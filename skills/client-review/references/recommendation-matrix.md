# Recommendation Priority Matrix

## Priority Levels

Priority is determined by the number of overlapping health flags on a single holding.

| Priority | Condition | Typical Actions |
|---|---|---|
| **High** | 3+ flags overlap on one holding | Trim, Exit, Reweight |
| **Medium** | 2 flags overlap on one holding | Investigate, Trim |
| **Low** | 1 flag only | Monitor, Hold |

## Health Flags (same 5 as health-flags.md)

| Flag | Holding-Level Condition |
|---|---|
| Low Score | Holding total score ≤ 5.0 |
| Concentration | Holding weight >15% |
| Redundancy | Holding is part of a redundant pair |
| Value Trap | Holding value score ≤ 3.0 |
| Macro Misalignment | Holding's sector flagged unfavourable by `macro_analyst` tactical |

## Recommendation Types

| Type | When to Use | Description |
|---|---|---|
| **Trim** | Concentration + other flags | Reduce weight to below threshold |
| **Exit** | 3+ flags + deteriorating score trend | Full sell — multiple converging negatives |
| **Hold** | Stable/improving scores, no flags | No action needed |
| **Investigate** | 2 flags but ambiguous signal | Suggest `/parallax-deep-dive` for full analysis |
| **Reweight** | Concentration without other flags | Adjust allocation to reduce concentration risk |

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
| `get_score_analysis` | `symbol`, weeks=26 | Score trend — improving or deteriorating? |
| `get_stock_outlook` | `symbol`, aspect="risk_return" | Risk profile vs peers |
| `get_peer_snapshot` | `symbol` | Current factor scores + peer context |

### News (selective)

Call `get_news_synthesis` only for holdings that are:
- Weight >10% **AND** flagged, OR
- In a sector with active macro developments

Cap news calls at 5 holdings. News is async — don't block output.
