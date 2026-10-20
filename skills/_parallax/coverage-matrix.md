# Parallax MCP Coverage Matrix

<!-- authority: observation -->
<!-- verified: 2026-10-06 -->
<!-- overrides: live schema and live responses win -->

**Purpose.** Document which Parallax MCP tool covers which asset class. Skills must consult this before adding a new MCP call. Mismatched tool/asset-class pairs (e.g., `export_price_series(SPY)`) silently fail-empty and would cause silent data drops in downstream computation.

Credit prices updated from direct connector metadata on 2026-10-19; asset coverage observations retain their original dates.

**Last empirical sweep:** 2026-05-02. Re-verify quarterly or after Parallax MCP releases.

> If you are authoring or modifying a skill that calls any tool below, run `skills/_parallax/scripts/coverage-lint.sh` before committing. The lint flags `export_price_series` and similar calls that are not preceded by an asset-class pre-classification step (per `parallax-pair-finder/SKILL.md` Batch C, `parallax-explain-portfolio/SKILL.md` Step 1a).

## Asset class × Tool

| Tool | Equity (e.g., AAPL.O, JPM.N) | ETF (e.g., SPY, EWJ, QQQ) | Notes |
|---|---|---|---|
| `export_price_series` | ✓ supported | ✗ historically returns `{success:false, error}` | Equity-only, **0.05 credits per successful symbol read**. Pass a verified RIC. Current JSON rows use `data[].price` with dates, not guaranteed `close` fields. A failure alone does not identify an ETF: transport, authorization and unsupported symbols remain separate failures. |
| `etf_daily_price` | ✗ returns `[]` | ✓ supported | ETF-only. Pass plain ticker (no `.X` suffix). Returns per-row `date` + `changepercent` — move AND date in one call. 0.05 credits per successfully read symbol. |
| `etf_profile` | ✗ explicit not-in-ETF-universe response for a tested equity | ✓ rich profile | **Classification evidence, not a generic-error oracle.** Current tested AAPL negative is `success:false`, `status:400`, with an explicit ETF-not-found reason; historical `No profile data found` is another observed shape. A recognized negative requires independently verified listed-equity identity before equity routing. Use dated `etf_daily_price` for an ETF move; profile `change_percent` alone has no verified date. 0.1 credits per successful probe; HTTP 4xx/5xx probes cost zero. |
| `etf_search` | n/a | ✓ supported | Discovery by market/keyword, query required. Deprecated alias of `search_etfs`; prefer `search_etfs`. |
| `etf_holdings` | n/a | ✓ supported | Underlying holdings of an ETF. |
| `get_company_info` | ✓ supported | ✓ partial (returns equity-shaped record for some ETFs) | **Does NOT include an `asset_class` field**; cannot be used to distinguish equity from ETF. Use `etf_profile` for that. |
| `get_peer_snapshot` | ✓ supported | partial — peer set may include both | Sector ETFs occasionally appear as peers; classify each before downstream price calls. |
| `export_peer_comparison` | ✓ (peer set may include ETFs) | partial | Same caveat as `get_peer_snapshot`. |
| `get_score_analysis` | ✓ supported | unverified | Likely equity-only; needs probe before using on ETF. |
| `get_financials`, `get_stock_outlook`, `get_news_synthesis` | ✓ equity | unverified | Used in equity workflows; not validated for ETFs. |
| `analyze_portfolio` | ✓ mixed-asset OK | ✓ mixed-asset OK | Holdings can be equity + ETF; tool aggregates correctly. |
| `quick_portfolio_scores` | ✓ partial | unverified | Symbol-mapping quirks (see `parallax-conventions.md` §2). |
| `macro_analyst`, `list_macro_countries` | n/a | n/a | Market-level, not symbol-level. |

## Verified benchmark ETFs (single-symbol probes, 2026-05-02)

| Market | Ticker | Status | Verified field |
|---|---|---|---|
| United States | `SPY` | ✓ in coverage | NYSE Arca, ric `SPY.P` |
| United States (tech) | `QQQ` | ✓ in coverage (assumed; not yet probed) | — |
| Japan | `EWJ` | ✓ in coverage | confirmed via pair-finder Toyota smoke test |
| United Kingdom | `EWU` | ✓ in coverage | NYSE Arca |
| Hong Kong | `EWH` | ✓ in coverage | NYSE Arca |
| South Korea | `EWY` | ✓ in coverage | NYSE Arca |
| Germany | `EWG` | ✓ in coverage (re-probed 2026-09-06 via `etf_search`; was empty on 2026-05-02) | NYSE Arca, ric `EWG.P` |
| Singapore | `EWS` | unverified | — |
| Taiwan | `EWT` | unverified | — |
| Canada | `EWC` | unverified | — |
| Australia | `EWA` | unverified | — |

Markets with a fixed ticker in the pair-finder canonical table (`parallax-pair-finder/references/modes.md`) — including the "unverified" rows above — use that ticker first and fall back to search only on failure (empty or < 60 observations). For a market not in that canonical table at all (the "(other)" catch-all), call `search_etfs(query="MSCI <country name>", market="UNITED STATES")` to discover available benchmarks at runtime — US-listed, matching this table's own convention; do NOT assume the iShares MSCI country ETF is in coverage. `query` is required — a call without it is rejected. See `parallax-pair-finder/references/modes.md` for the broad-match filter and the `etf_profile` market-cap tie-break (bounded to 3 profile calls).

## Known API quirks

1. **Multi-symbol calls fail-empty on partial coverage.** `etf_daily_price("SPY,EWJ,EWG")` returns `[]` (empty array) instead of returning the two valid symbols + an error for the missing one. Same behavior on `get_company_info` (the missing symbol is silently dropped from the response). **Always use single-symbol calls when coverage might be partial.**

2. **Classify from explicit evidence.** A populated, identity-matched ETF profile supports ETF routing. On 2026-10-19 a direct-connector AAPL probe returned `success:false`, `status:400`, and `Invalid ETF symbol: ETF symbol 'AAPL' not found in the ETF universe`; older responses used `No profile data found`. These explicit coverage negatives are not the same as timeout, authorization, rate-limit, malformed or unrelated errors. A negative does not alone prove equity: require independently verified listed-equity identity/context before equity-only enrichment. Otherwise the instrument remains unknown. Never count a generic `success:false` as proof of ETF or equity. Company-info presence alone is insufficient because it also covers some ETFs.

3. **Symbols are hints, not verified asset classes.** A `.P` or suffix-less symbol can guide a bounded ETF coverage lookup, but does not authorize a claimed instrument type. If classification is unavailable, retain the instrument and its original weight as unverified; use supported diagnostic evidence only. A successful dated ETF-price response may support that price leg; an unsuccessful price request does not classify the instrument. Never silently drop an unknown holding or assign it equity factors.

**Partial live recheck, 2026-10-19:** direct-connector probes confirmed company-info `data.name`/`data.currency`, snapshot `comparison[]`, equity-export `data[].price`, ETF-profile positive and explicit negative shapes, and bare ETF-price rows with `date`/`close`. Other rows retain their historical verification status; this is not a full coverage recertification.

## How to add a new entry

1. Run a single-symbol probe of the tool against a representative input from each asset class.
2. Record the empirical result (data shape / empty / error) in this matrix.
3. If a tool is unverified for an asset class, default to "unverified" — never assume coverage. Either probe before adding, or document the assumption explicitly.

## Required pattern for skills

Any skill that:
- Accepts user-supplied symbols as input (holdings, peers, benchmarks), AND
- Calls `export_price_series` or any other equity-only tool downstream

MUST include a pre-classification step (a la `parallax-pair-finder/SKILL.md` Batch C / `parallax-explain-portfolio/SKILL.md` Step 1a). The lint at `scripts/coverage-lint.sh` enforces this.

## Failure-handling contracts: atomic vs aggregation

When a tool returns empty/error after the right routing, the skill's response depends on its TYPE — failure is not one-size-fits-all:

| Skill type | Examples | Contract on per-component failure |
|---|---|---|
| **Sizing / construction** | `parallax-pair-finder` (hedge ratios), `parallax-rebalance` (trade list) | **Atomic gate.** Refuse to render the primary deliverable. A partially-computed hedge ratio is a confidence-building lie. Halt with named failure + operator-action options (see `parallax-pair-finder/SKILL.md` Batch C.5). |
| **Aggregation / attribution** | `parallax-explain-portfolio` (return decomposition), `parallax-portfolio-checkup` (health flags), `parallax-morning-brief` (per-holding news) | **Partial render with explicit MISSING blocks.** Compute the aggregate on the remaining weight; surface each missing component by name. Never silently zero or drop. (See `parallax-explain-portfolio/SKILL.md` Step 1c.) |
| **Per-symbol research** | `parallax-should-i-buy`, `parallax-deep-dive`, `parallax-due-diligence` | **Per-section partial.** If one tool fails (e.g., news), render the section as "Analysis pending — tool unavailable" and continue with other sections. Per `_parallax/parallax-conventions.md` §4. |

The lint enforces routing correctness (right tool for the asset class). It does NOT enforce the failure contract — that is per-skill design judgment. When authoring or reviewing, ask: "if tool X returns empty for one input, does the user want a halt, a partial, or a per-section fallback?"

## Deferred: upstream `supported_asset_classes` schema field

A request to add a `supported_asset_classes` field to each MCP tool's schema was considered and deferred 2026-05-03. Rationale:

- `etf_profile` already serves as the asset-class oracle (see Known API quirks #2). Each probe costs 1 token; classification behavior is solved client-side.
- Coverage-lint enforces routing at build time, which is a stronger guarantee than runtime metadata (fails the merge, not the user).
- An upstream metadata field would not address the deeper instruction-execution gap — a model can ignore schema metadata the same way it can ignore SKILL.md prose. The structural fix for that is a deterministic dispatch layer (client-side), not a server schema change.

Re-open if/when: (a) we add asset classes beyond equity/ETF (futures, FX, fixed income — probe count grows), or (b) we want protocol-level refusal at the MCP layer.
