# Pair Finder — per-mode batches

JIT-loaded by `parallax-pair-finder/SKILL.md` Step 2. Suggestion mode (one leg given) and evaluate mode (both legs given) share the same asset-class routing (equities via `export_price_series`, the benchmark ETF via `etf_daily_price`) and the same HARD HALT output gate, which stays in SKILL.md Step 3.

### Mode 1 / Mode 2 — Suggestion mode (one leg given)

Inputs: primary RIC + side (`long` | `short`). Optional: `--candidates=N` (default 3), `--with-history`.

#### Batch A — Identification + peer set + macro coverage (parallel)

Fire all three simultaneously:

| Tool | Parameters | Notes |
|---|---|---|
| `get_company_info` | symbol = primary RIC | Validates RIC, returns sector, industry, market cap, market |
| `export_peer_comparison` | symbol = primary RIC, format = "json" | **Workhorse call.** Returns peer set with cross-sectionally comparable factor scores (value, quality, momentum, defensive, tactical, total), sector, industry, market, market cap, P/E, EV/EBITDA, ROE, YTD return, recommendation. Single-call comparability — DO NOT use independent `get_peer_snapshot` calls in this mode |
| `list_macro_countries` | (none) | Gates macro coverage for Batch D |

If `export_peer_comparison` fails: retry once. If it still fails, fall back to `get_peer_snapshot(primary)` and note in output that score comparability across candidates is "best-effort" (Plan-agent finding D).

If `get_company_info` returns empty: apply RIC resolution per `_parallax/parallax-conventions.md` §1 (try `.O`, then `.N`, then escalate to user).

#### Step A.5 — In-process candidate selection (no MCP calls)

From the `export_peer_comparison.data` array, exclude the row where `is_target == true` (that's the primary leg). For the remaining peers:

- **`long` side given** → user wants a SHORT candidate. Sort peers ascending by `total` score. Take the bottom N (default 3). These are the lowest-scoring peers — the v1 mode-B candidates.
- **`short` side given** → user wants a LONG candidate. Sort peers descending by `total` score. Take the top N.

Record each candidate's: ric, company_name, sector, industry, market, all 5 factor scores, total, market cap, recommendation, ytd return.

#### Batch C — Beta computation (parallel, default path — NOT gated by --with-history)

Per spec scope-cut: beta-neutral sizing is in the default path because PMs act on beta-neutral, not dollar-neutral.

**Equities go through `export_price_series`. ETFs (benchmarks) go through `etf_daily_price` — a SEPARATE endpoint.** `export_price_series` does not return ETF data; using it for benchmarks returns empty. Use the right tool for each leg.

**Canonical benchmark mapping by `market` field:**

| Primary leg's `market` | Benchmark ticker (plain, no RIC suffix) | Notes |
|---|---|---|
| `United States` | `SPY` | S&P 500. For tech-heavy pairs, can substitute `QQQ` |
| `Japan` | `EWJ` | iShares MSCI Japan |
| `United Kingdom` | `EWU` | iShares MSCI UK |
| `Hong Kong` | `EWH` | iShares MSCI Hong Kong |
| `Singapore` | `EWS` | iShares MSCI Singapore |
| `Germany` | `EWG` | iShares MSCI Germany (RIC `EWG.P`) — in Parallax coverage as of 2026-09-06 (`etf_search`, `report_supported: true`); if coverage lapses, the Batch C.5 output gate HALTs rather than substituting a proxy |
| `Taiwan` | `EWT` | iShares MSCI Taiwan |
| `Korea` | `EWY` | iShares MSCI South Korea |
| `Canada` | `EWC` | iShares MSCI Canada |
| `Australia` | `EWA` | iShares MSCI Australia |
| (other) | call `etf_search(market="<market>", query="MSCI", recommendation="HOLD")` and pick highest-AUM result | Fallback discovery |

Compute the start/end dates for a 180d window: `end_date = today`, `start_date = today - 180 days` (calendar; ~125 trading days will be returned).

**API quirk to avoid:** `etf_daily_price` accepts a comma-separated multi-symbol input but returns `[]` if ANY of the listed symbols is missing from coverage. ALWAYS use single-symbol calls for benchmarks — one call per benchmark — so a single coverage gap doesn't silently fail the whole batch.

Fire all in parallel:

- `export_price_series(symbol=primary_ric, days=180, format="json")`
- `export_price_series(symbol=candidate_ric, days=180, format="json")` × N candidates
- `etf_daily_price(symbol=<benchmark_ticker>, start_date=<start_date>, end_date=<end_date>)` — **NOT `export_price_series`**

Compute beta inline per `references/residual-math.md` §"Beta computation". Beta-neutral hedge ratio = `beta_long / beta_short` (dollars short per dollar long).

**Fallbacks (in order):**
1. If `etf_daily_price` returns no data for the chosen benchmark → call `etf_search(market="<market>")` to find an alternative; retry with the top result.
2. If a leg's price series returns < 90 days of data → flag the affected candidate as "insufficient history for beta" and report **only dollar-neutral sizing** for that pair (do NOT halt the whole skill — this is per-leg degradation, surfaced in the row).

#### Batch C.5 — Output gate (HARD HALT — non-negotiable)

After Batch C completes and BEFORE rendering any beta-neutral hedge ratios, run this gate. The "⚠ Benchmark unavailable" caveat-footnote pattern is **forbidden** for primary deliverables. If the benchmark is genuinely unavailable, the skill HALTS — it does not silently substitute pair-relative regression beta and emit a footnote.

```
HARD GATE — refuse, do not degrade:
  if benchmark_series is null OR len(benchmark_series.observations) < 60:
    ABORT skill output. Render exactly:

      ⚠ Cannot produce beta-neutral hedge ratios.
        Benchmark: <benchmark_ticker> for market <primary_market>
        Returned: <N> observations from etf_daily_price (need ≥ 60 for stable beta)
        Failure path: <which fallback step ran last — initial-fetch / etf_search-discovery>

      Operator action — pick one:
        (a) Re-run with explicit benchmark: /parallax-pair-finder <symbol> <side> --benchmark=<alt-ticker>
        (b) Run with --no-beta to get dollar-neutral suggestions only (factor / sector residuals still computed)
        (c) Escalate to API team if etf_daily_price coverage for this market is genuinely missing

    DO NOT render Batch D, Batch E, the comparison table, or any per-pair detail.
    DO NOT emit hedge ratios under any other label (no "pair-relative regression" substitution).
```

Rationale: a hedge ratio computed against the wrong benchmark is a confidence-building lie. PMs reading a footnote do not adjust their downstream sizing decision; they adjust their footnote-tolerance. Refusing to emit primary deliverables when the underlying assumption fails is the only honest harm-reduction.

The pair-relative regression formula in `references/residual-math.md` §3a is NOT used in v1. It is documented for v2 if a deliberate "pair-relative mode" flag is added; until then, treat the formula as reference math only.

#### Batch D — Macro residual (parallel, after Batch A confirms primary's market)

Both legs are within-sector in suggestion mode → both legs share the same primary `market`. So one `macro_analyst` call covers both:

- `macro_analyst(market=<primary_market>, component="tactical")`

If `list_macro_countries` does not include `<primary_market>`: skip macro and render "macro context unavailable for this market" in output.

#### Batch E — (Optional, with `--with-history`)

If `--with-history` flag passed, extend Batch C: re-call `export_price_series` with `days=365` for primary + each candidate (skip benchmark — already have it from Batch C). Compute realized correlation, pair vol, max drawdown of the spread, hit rate per `references/residual-math.md` §"Realized pair stats".

(If skill latency is a concern, do this as a single 365-day call per leg in Batch C and slice; revisit if a future audit shows it matters.)

### Mode 3 — Evaluate mode (both legs given)

Inputs: `long=<RIC>` + `short=<RIC>`. Optional: `--with-history`.

#### Batch A — Identification + scores (parallel)

Fire all in parallel:

| Tool | Parameters | Notes |
|---|---|---|
| `get_company_info` | symbol = `<long_ric>,<short_ric>` (comma-separated) | Single multi-symbol call per MCP schema. Returns sector, industry, market cap, market for both legs |
| `export_peer_comparison` | symbol = long_ric, format = "json" | Get long's peer set. If short_ric appears in this peer set → both legs scored in same universe (safe to subtract) |
| `list_macro_countries` | (none) | For Batch C |

#### Step A.5 — Score comparability resolution (in-process)

Inspect the long's peer-comparison `data` array:

- **If `short_ric` IS in the peer set** (`peer.ric == short_ric` for some peer) → use the long's and short's scores directly from the peer-comparison response. Both scores are in the same universe; net subtraction is safe. Set `score_comparability_flag = "same_universe"`.
- **If `short_ric` is NOT in the peer set** (cross-sector or distant peer) → fire one fallback call: `get_peer_snapshot(short_ric)` to retrieve the short's scores. Set `score_comparability_flag = "cross_universe — best-effort comparable"`. The output MUST surface this flag prominently. Per spec: "Evaluate mode accepts cross-sector pairs but flags them."

#### Batch B — Beta computation (parallel, default path)

Same tool-split as suggestion mode Batch C: equity legs use `export_price_series`, the benchmark ETF uses `etf_daily_price`. 3 calls:

- `export_price_series(long_ric, days=180, format="json")`
- `export_price_series(short_ric, days=180, format="json")`
- `etf_daily_price(symbol=<benchmark_ticker>, start_date=<start_date>, end_date=<end_date>)`

Benchmark selection: use the canonical mapping in suggestion mode Batch C. If both legs share a `market`, use that market's benchmark. If markets differ, use the long-leg's market benchmark and flag the cross-market exposure in the residual section.

Fallbacks (same order as suggestion mode):
1. `etf_daily_price` empty → `etf_search(market=...)` discovery → retry
2. Leg < 90 days → dollar-neutral only for that pair (per-leg degradation, not whole-skill halt)

#### Batch B.5 — Output gate (HARD HALT — non-negotiable)

Same gate as suggestion-mode Batch C.5. If benchmark is genuinely unavailable after fallback #1 above, HALT with the operator-action message — do NOT substitute pair-relative regression or emit a "⚠ Benchmark unavailable" caveat. Hedge ratios that cannot be properly computed are not emitted in any form. The pair-relative regression formula is reference math only in v1; not a runtime fallback.

#### Batch C — Macro residual (parallel)

- `macro_analyst(market=<long_market>, component="tactical")`
- `macro_analyst(market=<short_market>, component="tactical")` (only fire if `short_market != long_market`)

The macro residual = long's tactical regime stance MINUS short's tactical regime stance (qualitative — render as "long-leg market regime is X; short-leg market regime is Y; the pair carries a cross-market regime tilt" if different).

#### Batch D — (Optional, with `--with-history`)

Same as suggestion mode Batch E: extend price series to 365d, compute realized correlation, pair vol, max drawdown, hit rate.
