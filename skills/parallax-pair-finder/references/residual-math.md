# Residual Math Reference — pair-finder

JIT-loaded by `skills/parallax-pair-finder/SKILL.md`. Price-derived formulas are executed by `pair_math.py` through the CLI in SKILL Step 4. Never calculate beta/history in model prose. Factor-net is a descriptive subtraction of verified scores; it is not hedge exposure.

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
| `sector_long == sector_short` | same reported sector; economic neutrality not established |
| `sector_long != sector_short` | sector_residual = "cross-sector: long `<long_sector>` / short `<short_sector>`" |
| `industry_long == industry_short` | same reported industry; economic neutrality not established |
| `industry_long != industry_short` | industry_residual = "cross-industry: long `<long_industry>` / short `<short_industry>`" (only render if sector is also non-neutral; otherwise sub-information) |
| `market_long == market_short` | same verified domicile; currency neutrality not established |
| `market_long != market_short` | different verified domiciles; currencies separately sourced, never inferred: long `<long_market>` / short `<short_market>` |

## 3. Beta computation (180d daily returns)

For each leg `L` and benchmark `B`:

```
returns_L = [(P_L[t] / P_L[t-1]) - 1 for t in 1..N]
returns_B = [(P_B[t] / P_B[t-1]) - 1 for t in 1..N]
```

**Field paths (different per Parallax endpoint):**
- Equity legs (long, short) come from `export_price_series` → `.data[t].price` (observed); legacy `.close` is accepted only when unambiguous
- Benchmark ETFs come from `etf_daily_price` → response is a **list directly** (not nested under `.data`); each row has `.close`

Both endpoints return chronologically-sorted daily bars. Align by both start and end dates of consecutive return intervals; do not match a two-day equity return to a one-day ETF return just because their end dates agree. Need at least 89 common return intervals after the individual 90-price leg threshold; otherwise dollar-neutral only. Reject duplicate/impossible dates, nonpositive/nonfinite prices and conflicting aliases.

Beta:

```
mean_L = sum(returns_L) / N
mean_B = sum(returns_B) / N
cov = sum((returns_L[t] - mean_L) * (returns_B[t] - mean_B) for t in 1..N) / N
var_B = sum((returns_B[t] - mean_B)^2 for t in 1..N) / N
beta_L = cov / var_B
```

Do not divide when benchmark return variance is zero/nonfinite. Compute with full precision in the helper; round only rendered output.

**Insufficient-history rule:** if a leg has fewer than 90 daily observations, do NOT compute beta — flag as "insufficient history for beta" and skip beta-neutral sizing for that pair.

## 3a. Pair-relative regression beta (REFERENCE MATH — NOT A v1 FALLBACK)

> **v1 status:** Documented for completeness. **NOT used at runtime.** When `etf_daily_price` and `search_etfs` both fail to yield a benchmark, the skill HALTS per the SKILL.md output gate (Batch C.5 / B.5). Hedge ratios computed against a non-market benchmark are not interchangeable with market-beta-neutral hedge ratios; substituting silently produces a confidence-building lie. The user-facing failure is honest: "cannot produce hedge ratios — operator action required."
>
> A future v2 may add an explicit `--mode=pair-relative` flag that opts into this method when the user knows what they are buying. Until that flag exists, this section is reference math only.

The variance-minimizing hedge ratio that does not require a benchmark:

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

**If a future `--mode=pair-relative` flag is added**, that mode's output MUST render a "⚠ Benchmark caveat" line above the comparison table or pair-detail block, naming pair-relative regression and noting the interpretive difference vs a market-beta hedge. **This does not apply to v1**: v1 has no pair-relative fallback path at runtime — see the HARD HALT gate in SKILL.md Batch C.5 / B.5, which forbids this exact caveat pattern as a substitution today.

## 4. Hedge ratios

Both ratios are in dollar terms (no share counts — see Plan-agent finding F).

```
dollar_neutral = 1.00  # $1 short per $1 long
beta_neutral   = beta_long / beta_short  # $X short per $1 long
```

If `beta_short` is near zero (<0.1 absolute value), or the ratio is nonpositive/nonfinite, skip beta-neutral and state the reason. Opposite-sign betas cannot produce a positive short-dollar ratio for the requested long/short directions.

## 5. Realized pair stats (--with-history only, 365d window)

```
spread_returns[t] = returns_long[t] - hedge_ratio * returns_short[t]
```

(Use the feasible beta-neutral hedge_ratio if available; else dollar-neutral.) This is a daily-reset synthetic spread index per dollar long, not realized client-account returns. Raw local prices exclude dividends, borrow, fees and FX conversion. Daily-observation support is conservative: any common return interval longer than four calendar days makes daily history unavailable with the interval dates and reason. This can exclude legitimate longer exchange closures; it never silently annualizes monthly/weekly observations with sqrt(252). The four-day check is a frequency-validity guard, not a change to beta sample thresholds or the volatility formula. Require a contiguous chain of common return intervals before compounding spread wealth; a missing interior interval makes cumulative history unavailable rather than silently stitching disjoint segments. Report actual common dates and count; partial-month observations are included in the positive-month fraction.

| Stat | Formula |
|---|---|
| Realized correlation | `corr(returns_long, returns_short)` over 365d |
| Pair vol (annualized) | `stdev(spread_returns) * sqrt(252)` |
| Max drawdown | min over t of: `wealth_t / running_peak_t - 1`, with initial wealth 1 included in the peak and `wealth_t = product(1 + spread_returns[0..t])`; nonpositive wealth makes history unavailable |
| Hit rate | fraction of months where cumulative monthly spread return > 0 |

## 6. Score-comparability flag

| Condition | Flag value |
|---|---|
| Both legs' scores from same `export_peer_comparison` call (suggestion mode always; evaluate mode if `short_ric in long_peer_set`) | `same_universe` (output: "Scores cross-sectionally comparable.") |
| Scores from separate calls (evaluate mode, cross-sector) | `cross_universe` (output: "⚠ Scores from separate Parallax universes — net factor differences are best-effort comparable, not strictly comparable. Treat with caution.") |

ALWAYS render this flag in evaluate-mode output. In suggestion mode it can be suppressed (always same_universe) or rendered as a small footnote.
