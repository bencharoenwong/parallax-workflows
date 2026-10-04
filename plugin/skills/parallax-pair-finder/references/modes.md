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
| (other) | call `search_etfs(query="MSCI <country name>", market="UNITED STATES")`, keep only **broad matches** (defined below), profile at most 3 via `etf_profile`, pick the highest market cap | Fallback discovery. `<country name>` is the primary leg's `market` field from `get_company_info`, used as-is — known alias: `United States` → `USA` (MSCI fund names read "MSCI USA", not "MSCI United States"); do not invent other aliases. The `market` filter is case-insensitive, so `UNITED STATES` matches a `market` value of `United States`. US-listed, matching the canonical table's own convention. Locally listed funds are not queried by a second pass by default: `search_etfs` has no price-history field, and a locally listed fund may lack the history `etf_daily_price` needs for a stable beta, so the single US-listed pass is the simpler default. No broad match among the results → benchmark unavailable for that market — do not substitute a proxy. |

**Broad match (positive rule, case-insensitive):** any word before "MSCI" in the fund `name` is the issuer and is ignored (iShares, Global X, Franklin, …) — including a multi-word issuer. The words after "MSCI" must be only the country name — the same (aliased) term used in the `search_etfs` query, e.g. "USA" for `United States`, allowing a known country-specific prefix word such as "South" for Korea — optionally followed by one or more suffix words drawn only from: "ETF", "Index Fund", "Capped", "IMI", "25/50", in any combination (e.g. "Capped ETF"). Any word after "MSCI" that is not the country name, its allowed prefix, or one of those suffix words disqualifies the fund. Separately, regardless of position — before or after "MSCI" — the words Ultra, UltraShort, Short, Leveraged, 2x, 3x, Bull, Bear, or Inverse disqualify the fund; this catches an issuer-prefix leverage tag such as "ProShares Ultra MSCI Japan", where the leverage word sits before "MSCI".

Applied to live evidence: "iShares MSCI Japan ETF" passes (Japan + ETF); "iShares MSCI Pacific Ex Japan ETF" fails (Pacific, Ex precede Japan); "ProShares Ultra MSCI Japan" fails (Ultra, before MSCI); "iShares MSCI China" passes; "iShares MSCI China A ETF" fails by default (A is an extra word — see the China A exception below); "iShares MSCI China Multisector Tech ETF" fails (Multisector, Tech); "Global X MSCI Vietnam ETF" passes (two-word issuer "Global X" ignored); "iShares MSCI Thailand ETF", "iShares MSCI Indonesia ETF", and "iShares MSCI Philippines ETF" pass on the same pattern; "iShares MSCI India ETF" passes.

China A exception: the plain "MSCI China" fund (no "A") is the default broad match. "MSCI China A" is not used unless the primary leg's own trading venue is Shanghai or Shenzhen (mainland A-shares) — in that case "MSCI China A" counts as the broad match.

No broad match in the result set → benchmark unavailable → proceed to the Batch C.5 output gate; no silent proxy substitution.

**Shortlist and profile bound:** `search_etfs` uses its default limit (20 rows); do not raise it. From the rows returned, keep the ones that pass the broad-match test, in search-result order — that ordered list (symbol + market cap once profiled) is the shortlist. Profile at most 3 of them via `etf_profile`; pick the one with the highest market cap. If none of the profiled candidates returns a market cap, take the first broad match by search order instead of profiling further. Keep the ordered shortlist (symbol, market cap) in memory — Batch C fallback #1 reuses it instead of re-searching. Cost: up to 1 + 3 credits (one `search_etfs` call plus up to three `etf_profile` calls, 1 credit each).

Compute the start/end dates for a 180d window: `end_date = today`, `start_date = today - 180 days` (calendar; ~125 trading days will be returned).

**API quirk to avoid:** `etf_daily_price` accepts a comma-separated multi-symbol input but returns `[]` if ANY of the listed symbols is missing from coverage. ALWAYS use single-symbol calls for benchmarks — one call per benchmark — so a single coverage gap doesn't silently fail the whole batch.

Fire all in parallel:

- `export_price_series(symbol=primary_ric, days=180, format="json")`
- `export_price_series(symbol=candidate_ric, days=180, format="json")` × N candidates
- `etf_daily_price(symbol=<benchmark_ticker>, start_date=<start_date>, end_date=<end_date>)` — **NOT `export_price_series`**

Compute beta inline per `references/residual-math.md` §"Beta computation". Beta-neutral hedge ratio = `beta_long / beta_short` (dollars short per dollar long).

**Fallbacks (in order):**
1. If `etf_daily_price` returns no data for the chosen benchmark:
   - **Canonical-table market** (Step 1 used the fixed ticker, so no shortlist exists yet): run the "(other)" row's US-listed search once — `search_etfs(query="MSCI <country name>", market="UNITED STATES")` — build the broad-match shortlist, then remove the canonical ticker that just returned empty from that shortlist (a search for the same country name can return the identical fund), profile at most 3 of what remains, and retry with the top pick.
   - **"(other)" market** (the shortlist already exists from Step 1): do NOT rerun the identical search. Retry with the next-highest-market-cap candidate already on the shortlist.
   - **Retry order and cap:** within the shortlist, retry `etf_daily_price` against the profiled candidates (up to 3) ordered by market cap descending, then — if those are exhausted — the remaining, unprofiled broad matches in the order `search_etfs` returned them. Stop after 3 retries total. If none returns ≥ 60 observations, treat the benchmark as unavailable and proceed to the Batch C.5 output gate.
   - If no candidate remains — the canonical-market search above found no broad match, or the "(other)"-market shortlist is exhausted — treat the benchmark as unavailable and proceed to the Batch C.5 output gate.
2. If a leg's price series returns < 90 days of data → flag the affected candidate as "insufficient history for beta" and report **only dollar-neutral sizing** for that pair (do NOT halt the whole skill — this is per-leg degradation, surfaced in the row).

#### Batch C.5 — Output gate (HARD HALT — non-negotiable)

After Batch C completes and BEFORE rendering any beta-neutral hedge ratios, run this gate. The "⚠ Benchmark unavailable" caveat-footnote pattern is **forbidden** for primary deliverables. If the benchmark is genuinely unavailable, the skill HALTS — it does not silently substitute pair-relative regression beta and emit a footnote.

```
HARD GATE — refuse, do not degrade:
  if benchmark_series is null OR len(benchmark_series.observations) < 60:
    ABORT skill output. Render exactly:

      ⚠ Cannot produce beta-neutral hedge ratios.
        Benchmark: <benchmark_ticker, or "none" if the Step-1 search found no broad match> for market <primary_market>
        <Returned: N observations from etf_daily_price (need ≥ 60 for stable beta) — omit this whole line when Benchmark is "none">
        Failure path: <which fallback step ran last — initial-fetch / us-listed-search-discovery / shortlist-exhausted / no-broad-match>

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

Fallbacks (same order and shortlist-reuse rule as suggestion mode Batch C fallback #1):
1. `etf_daily_price` empty → canonical-table market: run the "(other)" row's US-listed search once (build/profile the shortlist, after removing the ticker that just returned empty), retry with the top pick. "(other)" market: retry with the next-highest-market-cap candidate already shortlisted in Step 1 — do not rerun the identical search. Retry order and cap as in suggestion mode Batch C fallback #1 (profiled candidates by market cap descending, then unprofiled broad matches in search order, 3 retries total). No candidate remaining → treat the benchmark as unavailable and proceed to the Batch B.5 output gate.
2. Leg < 90 days → dollar-neutral only for that pair (per-leg degradation, not whole-skill halt)

#### Batch B.5 — Output gate (HARD HALT — non-negotiable)

Same gate as suggestion-mode Batch C.5. If benchmark is genuinely unavailable after fallback #1 above is exhausted, HALT with the operator-action message — do NOT substitute pair-relative regression or emit a "⚠ Benchmark unavailable" caveat. Hedge ratios that cannot be properly computed are not emitted in any form. The pair-relative regression formula is reference math only in v1; not a runtime fallback.

#### Batch C — Macro residual (parallel)

- `macro_analyst(market=<long_market>, component="tactical")`
- `macro_analyst(market=<short_market>, component="tactical")` (only fire if `short_market != long_market`)

The macro residual = long's tactical regime stance MINUS short's tactical regime stance (qualitative — render as "long-leg market regime is X; short-leg market regime is Y; the pair carries a cross-market regime tilt" if different).

#### Batch D — (Optional, with `--with-history`)

Same as suggestion mode Batch E: extend price series to 365d, compute realized correlation, pair vol, max drawdown, hit rate.
