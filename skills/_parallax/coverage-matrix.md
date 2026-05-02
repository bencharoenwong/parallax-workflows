# Parallax MCP Coverage Matrix

**Purpose.** Document which Parallax MCP tool covers which asset class. Skills must consult this before adding a new MCP call. Mismatched tool/asset-class pairs (e.g., `export_price_series(SPY)`) silently fail-empty and would cause silent data drops in downstream computation.

**Last empirical sweep:** 2026-05-02. Re-verify quarterly or after Parallax MCP releases.

> If you are authoring or modifying a skill that calls any tool below, run `skills/_parallax/scripts/coverage-lint.sh` before committing. The lint flags `export_price_series` and similar calls that are not preceded by an asset-class pre-classification step (per `pair-finder/SKILL.md` Batch C, `explain-portfolio/SKILL.md` Step 1a).

## Asset class × Tool

| Tool | Equity (e.g., AAPL.O, JPM.N) | ETF (e.g., SPY, EWJ, QQQ) | Notes |
|---|---|---|---|
| `export_price_series` | ✓ supported | ✗ returns `[]` | Equity-only. Pass RIC with exchange suffix. |
| `etf_daily_price` | ✗ returns `[]` | ✓ supported | ETF-only. Pass plain ticker (no `.X` suffix). |
| `etf_profile` | ✗ returns `{"error":"No profile data found"}` | ✓ rich profile (name, exchange, scores, recommendation) | **Use as asset-class oracle.** Single-symbol probe; FREE/instant per `token-costs.md`. |
| `etf_search` | n/a | ✓ supported | Discovery by market/keyword/score. |
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
| **Germany** | **`EWG`** | **✗ NOT IN COVERAGE** | empty response from `etf_daily_price` |
| Singapore | `EWS` | unverified | — |
| Taiwan | `EWT` | unverified | — |
| Canada | `EWC` | unverified | — |
| Australia | `EWA` | unverified | — |

For unverified markets, call `etf_search(market="<market>")` to discover available benchmarks at runtime; do NOT assume the iShares MSCI country ETF is in coverage.

## Known API quirks

1. **Multi-symbol calls fail-empty on partial coverage.** `etf_daily_price("SPY,EWJ,EWG")` returns `[]` (empty array) instead of returning the two valid symbols + an error for the missing one. Same behavior on `get_company_info` (the missing symbol is silently dropped from the response). **Always use single-symbol calls when coverage might be partial.**

2. **`etf_profile` returns explicit error on equities.** Useful as a clean asset-class oracle: response shape `{"error": "No profile data found", "ric": ...}` → equity; non-error response → ETF. Single FREE call per symbol.

3. **`.P` exchange suffix on RIC == NYSE Arca == ETF.** Static heuristic available without an API call: if a symbol has no exchange suffix or ends in `.P`, it is likely an ETF. Use this for first-pass classification when latency matters; confirm with `etf_profile` when the cost of being wrong is high.

## How to add a new entry

1. Run a single-symbol probe of the tool against a representative input from each asset class.
2. Record the empirical result (data shape / empty / error) in this matrix.
3. If a tool is unverified for an asset class, default to "unverified" — never assume coverage. Either probe before adding, or document the assumption explicitly.

## Required pattern for skills

Any skill that:
- Accepts user-supplied symbols as input (holdings, peers, benchmarks), AND
- Calls `export_price_series` or any other equity-only tool downstream

MUST include a pre-classification step (a la `pair-finder/SKILL.md` Batch C / `explain-portfolio/SKILL.md` Step 1a). The lint at `scripts/coverage-lint.sh` enforces this.

## Failure-handling contracts: atomic vs aggregation

When a tool returns empty/error after the right routing, the skill's response depends on its TYPE — failure is not one-size-fits-all:

| Skill type | Examples | Contract on per-component failure |
|---|---|---|
| **Sizing / construction** | `pair-finder` (hedge ratios), `rebalance` (trade list) | **Atomic gate.** Refuse to render the primary deliverable. A partially-computed hedge ratio is a confidence-building lie. Halt with named failure + operator-action options (see `pair-finder/SKILL.md` Batch C.5). |
| **Aggregation / attribution** | `explain-portfolio` (return decomposition), `portfolio-checkup` (health flags), `morning-brief` (per-holding news) | **Partial render with explicit MISSING blocks.** Compute the aggregate on the remaining weight; surface each missing component by name. Never silently zero or drop. (See `explain-portfolio/SKILL.md` Step 1c.) |
| **Per-symbol research** | `should-i-buy`, `deep-dive`, `due-diligence` | **Per-section partial.** If one tool fails (e.g., news), render the section as "Analysis pending — tool unavailable" and continue with other sections. Per `_parallax/parallax-conventions.md` §4. |

The lint enforces routing correctness (right tool for the asset class). It does NOT enforce the failure contract — that is per-skill design judgment. When authoring or reviewing, ask: "if tool X returns empty for one input, does the user want a halt, a partial, or a per-section fallback?"
