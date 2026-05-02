# Residual Math Reference — pair-finder

JIT-loaded by `skills/pair-finder/SKILL.md`. All formulas described here are executed inline by the model; no Python module exists.

## 1. Factor net (long − short)

For each factor pillar `f` in {value, quality, momentum, defensive, tactical}:

```
net_f = score_long.f - score_short.f
```

Total: `net_total = score_long.total - score_short.total`.

**Comparability precondition:** both `score_long` and `score_short` MUST come from the same `export_peer_comparison` call (same universe). If they came from independent calls, the subtraction is "best-effort comparable" and the output MUST flag this.

## 2. Sector / industry / domicile residual

From each leg's `sector`, `industry`, `market` fields (returned by `export_peer_comparison` or `get_company_info`):

| Comparison | Residual |
|---|---|
| `sector_long == sector_short` | sector_residual = 0 (sector-neutral) |
| `sector_long != sector_short` | sector_residual = "cross-sector: long `<long_sector>` / short `<short_sector>`" |
| `industry_long == industry_short` | industry_residual = 0 (industry-neutral) |
| `industry_long != industry_short` | industry_residual = "cross-industry: long `<long_industry>` / short `<short_industry>`" (only render if sector is also non-neutral; otherwise sub-information) |
| `market_long == market_short` | domicile_residual = 0 (currency-neutral) |
| `market_long != market_short` | domicile_residual = "cross-currency: long `<long_market>` / short `<short_market>`" |

## 3. Beta computation (180d daily returns)

For each leg `L` and benchmark `B`:

```
returns_L = [(P_L[t] / P_L[t-1]) - 1 for t in 1..N]
returns_B = [(P_B[t] / P_B[t-1]) - 1 for t in 1..N]
```

where `P_L[t]` is the close price on day `t` from `export_price_series.data[t].close` (or whatever the actual field name is — verify in the response).

Beta:

```
mean_L = sum(returns_L) / N
mean_B = sum(returns_B) / N
cov = sum((returns_L[t] - mean_L) * (returns_B[t] - mean_B) for t in 1..N) / N
var_B = sum((returns_B[t] - mean_B)^2 for t in 1..N) / N
beta_L = cov / var_B
```

Round to 2 decimal places for output.

**Insufficient-history rule:** if a leg has fewer than 90 daily observations, do NOT compute beta — flag as "insufficient history for beta" and skip beta-neutral sizing for that pair.

## 3a. Pair-relative regression beta (benchmark-unavailable fallback)

When `export_price_series(<benchmark_ric>)` returns no data (Parallax price universe is equity-only and does not carry SPY / IVV / VOO / EWJ / EWU and similar ETFs), use pair-relative regression beta directly. This is the variance-minimizing hedge ratio that does not require a benchmark:

```
returns_long  = [(P_long[t]  / P_long[t-1])  - 1 for t in 1..N]
returns_short = [(P_short[t] / P_short[t-1]) - 1 for t in 1..N]

mean_L = sum(returns_long)  / N
mean_S = sum(returns_short) / N
cov_LS = sum((returns_long[t] - mean_L) * (returns_short[t] - mean_S) for t in 1..N) / N
var_S  = sum((returns_short[t] - mean_S)^2 for t in 1..N) / N
hedge_ratio_pair_relative = cov_LS / var_S
```

This gives `$X short per $1 long` that minimizes residual spread variance over the 180d window. Mathematically defensible for sector-neutral pairs; semantically different from a market-beta hedge.

**Output requirement:** when this fallback is used, the skill MUST render a "⚠ Benchmark caveat" line above the comparison table or pair-detail block, naming pair-relative regression and noting the interpretive difference vs a market-beta hedge.

## 4. Hedge ratios

Both ratios are in dollar terms (no share counts — see Plan-agent finding F).

```
dollar_neutral = 1.00  # $1 short per $1 long
beta_neutral   = beta_long / beta_short  # $X short per $1 long
```

If `beta_short` is near zero (<0.1 absolute value): skip beta-neutral as numerically unstable; flag in output.

## 5. Realized pair stats (--with-history only, 365d window)

```
spread_returns[t] = returns_long[t] - hedge_ratio * returns_short[t]
```

(Use beta-neutral hedge_ratio if available; else dollar-neutral.)

| Stat | Formula |
|---|---|
| Realized correlation | `corr(returns_long, returns_short)` over 365d |
| Pair vol (annualized) | `stdev(spread_returns) * sqrt(252)` |
| Max drawdown | min over t of: `cumret_t - max(cumret_0..t)` where `cumret_t = product(1 + spread_returns[0..t]) - 1` |
| Hit rate | fraction of months where cumulative monthly spread return > 0 |

## 6. Score-comparability flag

| Condition | Flag value |
|---|---|
| Both legs' scores from same `export_peer_comparison` call (suggestion mode always; evaluate mode if `short_ric in long_peer_set`) | `same_universe` (output: "Scores cross-sectionally comparable.") |
| Scores from separate calls (evaluate mode, cross-sector) | `cross_universe` (output: "⚠ Scores from separate Parallax universes — net factor differences are best-effort comparable, not strictly comparable. Treat with caution.") |

ALWAYS render this flag in evaluate-mode output. In suggestion mode it can be suppressed (always same_universe) or rendered as a small footnote.
