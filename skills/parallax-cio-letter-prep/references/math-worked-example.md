# Worked Numerical Example — held-entire-period

This example mirrors `scripts/test_contribution.py::test_held_entire_period_no_trades`
so the math is verifiable without running the script.

## Inputs

- Period: `2026-01-01` to `2026-01-31` (30 return-days, 31 calendar dates)
- 3 equally-weighted holdings, no trades, no `dividend_schedule` — this fixture
  is a plain price-return computation. The reported total below is therefore a
  price-only return, not a total return before FX; it is NOT directly
  comparable to a real period's `total_price_pl` (which includes dividends —
  see the Step 3 reconciliation gotcha in SKILL.md and
  `test_vz_single_holding_with_dividend_schedule_matches_server_total_return`
  for a worked example that DOES include a dividend via `dividend_schedule`).
- Price-return prices (linear paths — the path shape does not matter below,
  only the endpoints do; see "Why only the endpoints matter"):

| Symbol | Day 0 | Day 30 |
|---|---|---|
| `AAPL.O` | 100.0 | 130.0 |
| `MSFT.O` | 100.0 | 100.0 |
| `JPM.N` | 100.0 | 70.0 |

- `prior_portfolio = current_portfolio = {AAPL.O: 1/3, MSFT.O: 1/3, JPM.N: 1/3}`
- `trade_log = []`

## Why only the endpoints matter

`contribution.py` compounds each holding's own value daily:
`value[d] = value[d-1] * (1 + r[d])`, where `r[d] = price[d]/price[d-1] - 1`.
With no trades, no rebalance ever reweights a holding against the others, so
a single holding's value telescopes exactly:

```
value[30] = value[0] * prod_{d=1..30}(1 + r[d])
          = value[0] * prod_{d=1..30}(price[d] / price[d-1])
          = value[0] * price[30] / price[0]
```

The product of consecutive price ratios collapses to the end/start ratio
regardless of the path between them (a round trip through a dip or a spike
nets out exactly the same). Per-holding contribution is
`value[30] - value[0] = weight * (price[30]/price[0] - 1)`.

## Contributions

- AAPL: `(1/3) × (130.0/100.0 − 1) = (1/3) × 0.30 = +0.10` (`+1000 bps`)
- MSFT: `(1/3) × (100.0/100.0 − 1) = 0` (`0 bps`)
- JPM: `(1/3) × (70.0/100.0 − 1) = (1/3) × (−0.30) = −0.10` (`−1000 bps`)

## Portfolio total return

`+0.10 + 0 + (−0.10) = 0.0` (`0 bps`). Sum of contributions equals the
portfolio total exactly — not approximately — because no rebalance ever
transferred value between holdings in this fixture; see the reconciliation-
gate section of `contribution.py`'s module docstring for the general case
(one that includes a rebalance and a dividend; see
`test_one_rebalance_and_one_dividend` in `test_contribution.py`).

## Reconciliation

`sum(contributions) − portfolio_total_return = 0.0` (well below the 1-bp
tolerance). The reconciliation gate passes.

## Pack rendering (synthesized; not from a real run)

- Top contributor: `AAPL.O +1000 bps`
- Top detractor: `JPM.N −1000 bps`
- Period total: `0 bps`

Driver fields would be filled per the fallback hierarchy in SKILL.md (defaults
to "Price appreciation / contraction in line with [stock-level move]" for this
synthetic data because no real news / factor / peer signal exists).
