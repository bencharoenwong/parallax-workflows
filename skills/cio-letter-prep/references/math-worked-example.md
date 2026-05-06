# Worked Numerical Example — held-entire-period

This example mirrors `scripts/test_contribution.py::test_held_entire_period_no_trades`
so the math is verifiable without running the script.

## Inputs

- Period: `2026-01-01` to `2026-01-31` (30 return-days, 31 calendar dates)
- 3 equally-weighted holdings, no trades
- Total-return prices (linear paths for clean hand-computation):

| Symbol | Day 0 | Day 30 | Daily price formula |
|---|---|---|---|
| `AAPL.O` | 100.0 | 130.0 | `price[d] = 100 + d` |
| `MSFT.O` | 100.0 | 100.0 | flat |
| `JPM.N` | 100.0 | 70.0 | `price[d] = 100 - d` |

- `prior_portfolio = current_portfolio = {AAPL.O: 1/3, MSFT.O: 1/3, JPM.N: 1/3}`
- `trade_log = []`

## Per-holding daily-return formulas (arithmetic)

- AAPL: `r[d] = (100+d)/(99+d) - 1 = 1/(99+d)` for d ∈ [1, 30]
- MSFT: `r[d] = 0`
- JPM: `r[d] = (100-d)/(101-d) - 1 = -1/(101-d)` for d ∈ [1, 30]

## Per-holding sum of arithmetic daily returns

- AAPL: `Σ_{k=100..129} 1/k ≈ 0.2635215`
- MSFT: `0`
- JPM: `−Σ_{k=71..100} 1/k ≈ −0.3545408`

## Contributions (weight × sum-of-daily-returns, since weights are constant)

- AAPL contribution ≈ `(1/3) × 0.2635215 ≈ +0.0878405` (`+878.4 bps`)
- MSFT contribution ≈ `0` (`+0 bps`)
- JPM contribution ≈ `(1/3) × (−0.3545408) ≈ −0.1181803` (`−1181.8 bps`)

## Portfolio total return (arithmetic sum of daily portfolio returns)

`+0.0878405 + 0 + (−0.1181803) ≈ −0.0303397` (`−303.4 bps`)

## Reconciliation

`sum(contributions) − portfolio_total_return ≈ 0` (well below the 1-bp tolerance).
Amendment A's gate passes.

## Pack rendering (synthesized; not from a real run)

- Top contributor: `AAPL.O +878.4 bps`
- Top detractor: `JPM.N −1181.8 bps`
- Period total: `−303.4 bps`

Driver fields would be filled per Amendment D fallback (defaults to "Price
appreciation / contraction in line with [stock-level move]" for this synthetic
data because no real news / factor / peer signal exists).
