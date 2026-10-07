# Credit Lens — flagging and assembly rules

JIT-loaded by `parallax-credit-lens/SKILL.md` Step 4. `credit_lens_logic.py` applies every band; this file is the operating manual for calling it correctly.

`build_header` derives the verdict from the legs as they stand when it runs; it does not read `report.overall_flag`. So a leg that resolves late — `altman_flag` needs an external market cap, `quality_flag` arrives in Batch B — is reflected without re-running `finalize_verdict`. Populate every leg before rendering.

That makes `finalize_verdict` optional for rendering: it stores the verdict on the report for any downstream consumer, but the header does not read it. Call it if you need `report.overall_flag`; skip it if you only render. Do not assign `overall_flag` by hand — a stored value that disagrees with the legs is not what the reader will see.

`metric_key` selects the direction and any absolute band. Pass one of the registered keys below for every dashboard row:

**Render one dashboard row per metric — ten rows, not four grouped categories.** `build_header()` counts one leg per metric, so grouping ten metrics into four rows makes the judged-count describe a different set than the verdict, and the coverage caveat then fails to fire on exactly the runs that need it. Use the Category column below as the row's group label, not as the row itself — grouping by category is not the contract.

| Category / Metric | `metric_key` | Direction | Absolute band |
|---|---|---|---|
| Leverage — Debt/EBITDA | `debt_ebitda` | higher is worse | yes |
| Leverage — Debt/Equity | `debt_equity` | higher is worse | peer-relative only |
| Leverage — Debt/Assets | `debt_assets` | higher is worse | peer-relative only |
| Coverage — Interest Coverage | `interest_coverage` | lower is worse | yes |
| Coverage — EBITDA/Interest | `ebitda_interest_coverage` | lower is worse | peer-relative only |
| Liquidity — Current Ratio | `current_ratio` | lower is worse | yes |
| Liquidity — Quick Ratio | `quick_ratio` | lower is worse | peer-relative only |
| Profitability — EBITDA Margin | `ebitda_margin` | lower is worse | peer-relative only |
| Profitability — EBIT Margin | `ebit_margin` | lower is worse | peer-relative only |
| Profitability — FCF Margin | `fcf_margin` | lower is worse | peer-relative only |

`flag_metric` raises `ValueError` on a key outside this table, so a typo stops the run instead of scoring the row. Never invent a key. To flag a metric that is not in the table, add it to `METRIC_DIRECTIONS` in `credit_lens_logic.py` first.

The live `ratios` response carries no `peer_median` / `peer_p75` field for **any** metric — it is target-only data (confirmed by live probe; there is no nested peer object anywhere in the response). No tool in this skill's `tool_sequence` supplies a peer-median/percentile pair for any of the ten registered metrics today. The `peer-relative only` rows (`debt_equity`, `debt_assets`, `ebitda_interest_coverage`, `quick_ratio`, `ebitda_margin`, `ebit_margin`, `fcf_margin`) therefore have neither a peer pair nor an absolute band and are UNAVAILABLE on every run, not merely when a peer pair happens to be missing this run. Of the three remaining keys that do carry an absolute band, `debt_ebitda` (from `total_debt_ebitda`) and `current_ratio` are reliably judged from `ratios`, and only via the absolute rule.

`interest_coverage` has no raw value anywhere in `ratios` either — no interest-expense or coverage field exists there — but it is **not** permanently UNAVAILABLE: compute its value from `get_financials(income)` via `compute_interest_coverage(ebit, interest_expense_net_non_operating)` before calling `flag_metric`, never feed `ratios` into it. `ebit` is `income.operating_income`, the same EBIT proxy production uses elsewhere in this data model. `interest_expense_net_non_operating` is **negative when it is a net expense** and non-negative when the company has net non-operating interest income rather than expense (confirmed against a live probe, 2026-10-06). `compute_interest_expense()` returns the positive expense magnitude on a negative value and `None` — never a fabricated zero — on an absent, non-finite, or non-negative one; `compute_interest_coverage()` then returns `None` rather than dividing by a zero or missing denominator. Call `flag_metric` only when `compute_interest_coverage` returns a real number; render UNAVAILABLE when it returns `None`. This makes `interest_coverage` UNAVAILABLE only on a per-run data gap (the income statement omitting `operating_income`, or reporting net non-operating interest income instead of expense for this name), not on every run.

When a row has neither a peer pair nor a band, or (for `interest_coverage`) no usable income-statement value, `flag_metric` returns UNAVAILABLE rather than GREEN: nothing can judge it, so it must not read as healthy. Render those rows as `➖ UNAVAILABLE` and leave them out of the traffic-light count, which `overall_traffic_light()` already does.

`flag_metric` still accepts `peer_median` / `peer_p75` as parameters — pass `None` for both on every call today, since nothing supplies real values. The function's peer-relative logic is exercised only by the unit tests in `tests/test_credit_lens.py`, not by any live orchestration path. If a future Parallax release adds a peer-percentile field, `peer_p75` is defined to always carry the **adverse** tail, in both directions: numerically above `peer_median` when higher is worse, below it when lower is worse. Pass it through unchanged — do not go looking for a 25th-percentile field, and do not recompute or invert the value yourself. `flag_metric` raises `ValueError` on an inverted pair in **either** direction rather than silently inverting the bands.

Four rules that a hand-computation gets wrong:

- Pass the Quality change through `quality_change_pts()` rather than subtracting the two scores inline. The bands are one-decimal and the raw subtraction is not exact, so a true −0.5 can compute as −0.4999999999999996 and flag GREEN.
- Never compute Interest Coverage as `operating_income / interest_expense_net_non_operating` directly — that field's sign is negative-for-expense, so a hand division without flipping it returns a negative ratio on a perfectly healthy name. Always go through `compute_interest_coverage()`, and never substitute `0` for an absent or non-negative `interest_expense_net_non_operating`: `0` reads as "no debt to service," which a non-negative field value does not prove — it only proves this field cannot supply an expense figure.
- `compute_altman_z` raises on zero `total_assets` or zero `total_liabilities`. A zero, negative or non-finite `market_cap` counts as **absent**, not as a value: with `book_equity` present it falls back to the Z' variant, and with no `book_equity` it raises like any other missing X4. Treat the raise as the Altman leg being unavailable; do not substitute a zero. Report the variant label the function returns rather than assuming `Z`.
- The Altman leg can come back UNAVAILABLE with no raise, when the score itself is non-finite — a large working capital over a near-zero total-assets figure overflows from ordinary finite inputs. When that happens, set `altman_flag` to UNAVAILABLE and leave `altman_z` as `None` — `dashboard_rows()` renders the row for you. **Do not construct an Altman `MetricRow` yourself**; that is what produces a duplicated leg. Skip the §2a sensitivity line entirely (there is no distance-to-boundary to state) and say the score could not be computed.

- `flag_metric` returns UNAVAILABLE, never GREEN, when it cannot judge a value: a non-finite metric value, and a **negative value on a `higher is worse` metric**. A negative Debt/EBITDA or Debt/Equity is either negative EBITDA / negative book equity, which is distress, or a net-cash position on a net-debt convention, which is healthy. The module cannot tell those apart from the number alone, so it refuses to score it. When a row comes back UNAVAILABLE for this reason, say so in Key Flags and explain the sign from the balance sheet — do not silently drop the row, and do not report it as healthy.
