# Parallax Response Schemas — Nested Field Reference

JIT-load when you need to know what's inside an `analyze_portfolio` response field. These are observed schemas from a probe run on 2026-05-07 (5-holding US large-cap, 2024-01-02 → present). Schemas may vary by portfolio composition; treat as guide, not contract. Authoritative source is the upstream OpenAPI spec once nested examples are published.

> **Caveat:** A multi-asset or illiquid portfolio may surface fields not shown here. If you see an unfamiliar field in a response, add it to this file rather than assuming it's an error.

---

## `analyze_portfolio` top-level keys

```
[
  "_meta",
  "company_contribution",
  "company_info",
  "concentration_metrics",
  "data_quality",
  "drawdown_analysis",
  "latest_holdings",
  "portfolio_parameters",
  "portfolio_scores",
  "rolling_metrics"
]
```

(Plus more if requested via `fields=`: `portfolio_input`, `portfolio_summary`, `turnover_analysis`, `performance_metrics`, `transactions`, `market_allocation`, `sector_allocation`, `currency_allocation`, `sector_contribution`, `market_contribution`, `time_period_returns`, `monthly_returns`, `annual_returns`, `benchmark_prices`, `daily_summary`.)

---

## `rolling_metrics`

Three sub-windows. Each has a daily `timeseries` array.

```
{
  "window_30d": { "timeseries": [ { ... }, ... ] },
  "window_60d": { "timeseries": [ ... ] },
  "window_90d": { "timeseries": [ ... ] }
}
```

Per-day entry:

| Field | Type | Notes |
|---|---|---|
| `date` | string (YYYY-MM-DD) | Trading day |
| `sharpe_ratio` | float | Rolling annualized Sharpe over the window |
| `volatility` | float | Rolling annualized vol over the window |
| `beta` | float | Rolling beta vs. benchmark |
| `correlation` | float | Rolling correlation vs. benchmark |

---

## `drawdown_analysis`

```
{
  "portfolio": { ... summary stats ... },
  "benchmark": { ... summary stats ... },
  "episode_details": [ ... ],
  "timeseries": [ ... per-day ... ]
}
```

### `portfolio` and `benchmark` summary block

| Field | Type | Notes |
|---|---|---|
| `current_drawdown` | float | Current drawdown from peak (0 if at peak) |
| `at_peak` | bool | True iff current drawdown is exactly 0 |
| `max_drawdown` | float | Worst peak-to-trough drawdown over period |
| `num_underwater_periods` | int | Distinct drawdown episodes |
| `avg_duration_days` | float | Mean episode length in trading days |
| `max_duration_days` | int | Longest episode length |
| `total_days_underwater` | int | Cumulative days below previous peak |
| `avg_recovery_days` | float | Mean days from trough to recovery |
| `max_recovery_days` | int | Longest recovery |

### `timeseries` per-day entry

| Field | Type | Notes |
|---|---|---|
| `date` | string | Trading day |
| `portfolio_drawdown` | float | Negative or zero |
| `benchmark_drawdown` | float | Negative or zero |
| `portfolio_episode` | int / null | Episode ID; null if at peak |
| `benchmark_episode` | int / null | Same |

### `episode_details`

Array of episodes (not yet field-mapped here — extend when used).

---

## `concentration_metrics`

```
{
  "weight_statistics": { ... },
  "concentration": { ... },
  "higher_moments": { ... },
  "diversification": { ... }
}
```

### `weight_statistics`

`mean`, `median`, `std_dev`, `maximum`, `minimum` of holding weights.

### `concentration`

| Field | Type | Notes |
|---|---|---|
| `herfindahl_index` | float | Sum of squared weights |
| `effective_positions` | float | 1/HHI; **weight-based**, not risk-weighted |
| `top_5_share` | float | Cumulative weight of top 5 |
| `top_10_share` | float | Cumulative weight of top 10 |
| `gini_coefficient` | float | Weight inequality |

### `higher_moments`

`skewness`, `kurtosis` of weight distribution.

### `diversification`

| Field | Type | Notes |
|---|---|---|
| `num_markets` | int | Distinct markets |
| `market_hhi` | float | Market-level concentration |
| `num_sectors` | int | Distinct sectors |
| `sector_hhi` | float | Sector-level concentration |
| `num_industries` | int | Distinct industries |

---

## `company_contribution`

Array indexed by integer rank. Each entry:

| Field | Type | Notes |
|---|---|---|
| `ric` | string | Reuters code |
| `name` | string | Company name |
| `total_pl` | float | Cumulative P&L attributed to holding |
| `avg_weight` | float | Mean portfolio weight over period |
| `contribution_pct` | float | Share of total portfolio P&L |
| `return_pct` | float | Holding's own return |
| `avg_allocation` | float | Mean dollar allocation |

> **This is RETURN contribution, NOT risk contribution.** Per-holding marginal volatility / component VaR is not currently exposed.

---

## `portfolio_scores`

Aggregate (point-in-time) scoring at portfolio level.

| Field | Type | Notes |
|---|---|---|
| `value` | int (0-100) | Value pillar |
| `quality` | int | Quality pillar |
| `momentum` | int | Momentum pillar |
| `defensive` | int | Defensive pillar |
| `tactical` | int | Tactical pillar |
| `total` | int | Aggregate |
| `coverage` | float (0-1) | Fraction of portfolio weight that received scores |

> Returned as scalars only. Portfolio-level score history is **not** in this response — for time series, aggregate per-symbol `get_score_analysis` calls client-side.

---

## `latest_holdings`

Array of holdings as-of `end_date`.

| Field | Type | Notes |
|---|---|---|
| `ric` | string | |
| `quantity`, `weight`, `close_local`, `close_base`, `currency_local`, `ending_value` | float | Holding economics |
| `market`, `sector`, `industry`, `name` | string | Classification |
| `value`, `quality`, `momentum`, `defensive`, `tactical`, `total` | int / float | Per-holding pillar scores |
| `pick_toscore` | bool | Was this holding eligible for scoring |
| `recommendation` | string | `BUY` / `HOLD` / `SELL` (per-holding signal) |

---

## `company_info`

Per-symbol metadata (entries keyed by RIC).

Fields seen: `ric`, `name`, `activity`, `market`, `exchange`, `exchangecode`, `sector`, `industry`, `currency`, `close`, `changepercent`, `change`, `volume` (single-day), `mktcap`, `numshrs`, `pick_toscore`, pillar scores, `recommendation`, `description`, `type`.

> **Liquidity gap:** `volume` is the most recent trading-day volume only. There is no 30-day ADV, days-to-liquidate, or bid-ask spread field.

---

## `data_quality`

| Field | Type | Notes |
|---|---|---|
| `total_rics_requested` | int | |
| `rics_found_in_database` | int | |
| `missing_rics` | string[] | Symbols not resolved by `bulk_resolve_symbols` |
| `missing_rics_count` | int | |
| `data_completeness_pct` | float | Resolved / requested |
| `removed_positions_due_to_missing_prices` | object | `count`, `unique_rics`, `details[]` |
| `portfolio_data_quality` | object | `total_positions`, `missing_quantities[_pct]`, `missing_prices[_pct]`, `missing_values[_pct]` |

> **`missing_rics` is a graceful-degradation signal**, not a hard error. If a symbol you expect to resolve appears here (e.g., common Bloomberg-style class-share notation like `BRK.B`), it is missing from the upstream IDENTIFIERS table — escalate as a data-coverage issue, not a tool failure. The fuzzy `search_stocks` MCP tool can be used to suggest the correct RIC.

---

## How to extend this file

When you encounter a field not documented here:

1. Probe with a representative portfolio (mix of compositions if possible).
2. Add the field, type, and a one-line note to the relevant section.
3. If the section is new, follow the structure above (top heading → sub-blocks → field tables).
4. If the field is genuinely a new top-level key on `analyze_portfolio`, also add it to the top-level key list at the top.

Do not delete fields when upstream changes — mark them deprecated with a date instead. Skills depend on stability here.
