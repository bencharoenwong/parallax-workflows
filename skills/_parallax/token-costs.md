# Parallax Credit Cost Reference

<!-- authority: observation -->
<!-- verified: 2026-10-19 -->
<!-- overrides: live schema and live responses win -->

Parallax bills **credits**. These are separate from the model's input/output tokens.
The filename remains `token-costs.md` for existing references.

Prices below match the direct MCP tool descriptions discovered on 2026-10-19
and the published tool credit contract. These are advertised prices, not measured
account deductions. Another connector can expose an older contract: read its full
`Cost:` clause before spending and preserve the operator's chosen account.
Never infer account identity or billing correctness from a health response.

## Tool credit costs

All 36 tools are priced. Each row states its billing unit; batching symbols
reduces request overhead, not the number of billable symbols.

| Tool | Credits | Basis |
|---|---|---|
| `check_api_health` | 0 | Service liveness only |
| `check_job_status` | 0 | Poll an existing job; preserve its identifier |
| `check_macro_health` | 0 | Deprecated; use health for liveness or countries for coverage |
| `explain_methodology` | 0 | Methodology lookup |
| `get_docs` | 0 | Documentation lookup |
| `list_docs` | 0 | Documentation index |
| `search_stocks` | 0 | Stock resolution |
| `search_etfs` | 0 | ETF resolution |
| `etf_search` | 0 | Deprecated ETF search alias |
| `list_macro_countries` | 0 | Covered macro markets |
| `submit_feedback` | 0 | Submission; still requires authorization to send |
| `get_company_info` | 0.05 per symbol | Every requested symbol in a successful batch |
| `export_price_series` | 0.05 per symbol | Equity prices; adjustment basis must be verified separately |
| `etf_daily_price` | 0.05 per symbol | ETF price history |
| `get_telemetry` | 0.05 | One global request, never one per market |
| `explore_telemetry` | 0.05–0.2 | 0.05 per call; 0.1 for a stock lookup; a basket lookup adds 0.05 per basket opened; at most 0.2 |
| `get_financials` | 0.05–0.1 per symbol | Per statement; `latest=true` doubles income, balance_sheet and cash_flow only |
| `get_stock_outlook` | 0.05–0.1 | Targets/recommendations 0.05 per call; risk_return 0.1 per call; dividends 0.05 per symbol |
| `get_peer_snapshot` | 0.1 | Per call |
| `export_peer_comparison` | 0.1 | Per call |
| `get_score_analysis` | 0.1 | Per call |
| `get_score_summary` | 0.1 | Per call |
| `etf_profile` | 0.1 | Per successful profile call |
| `etf_holdings` | 0.1 | Per call |
| `quick_portfolio_scores` | 0.1 per holding | Selected holdings, default 50, maximum 100 |
| `check_portfolio_redundancy` | 0.1 per holding | Selected holdings, maximum 100 |
| `get_performance_history` | up to 0.2 | Always attempts calendar and risk/return reads at 0.1 each; all-success total 0.2 |
| `build_stock_universe` | 5 | Per successful universe job |
| `analyze_portfolio` | 5 | Per successful analysis job |
| `get_news_synthesis` | 5 | Per successful news job |
| `get_technical_analysis` | 5 | Per successful technical job |
| `get_financial_analysis` | 5 | Per successful Palepu job |
| `macro_analyst` | 5–50 | Explicit component 5; omitted-component overview normally 5, up to 50 on reassembly |
| `get_stock_report` | 10 | Per successful report job |
| `get_etf_report` | 10 | Symbol resolution is free |
| `get_assessment` | 10 | Deep research tier |

### Billing and estimate rules

- Three symbols at 0.05 each cost 0.15, even in one request. Count symbols, not batches.
- Financial comparisons issue two reads only for `latest=true` income, balance_sheet or cash_flow. Ratios and summary remain 0.05 per symbol.
- Per-holding tools bill selected successful lookups, including zero-weight holdings. Trimmed holdings cause no lookup. An all-zero book fails validation before lookups; selected zero-weight rows in a valid positive-weight book still bill. A quick score at 50 holdings costs 5, equal to portfolio analysis; the outputs have different purposes and are not interchangeable.
- A macro overview can make its initial request plus nine component requests. Its maximum is 50 when all ten return HTTP 2xx. Explicit components never fan out. Do not replace an overview with a component unless that component answers the workflow's question.
- HTTP 4xx/5xx reads and failed async jobs do not bill. A successful empty response can bill. An unsupported ETF probe returning HTTP 4xx costs zero; reserve 0.1 per probe when planning without response evidence.
- Polling a pending job costs zero. Repeating a successful report or synthesis request can bill again, including server-cached results. Re-rendering a saved local response adds no MCP spend.
- Preserve decimal balances and fractional 402 amounts. Sum using decimal-safe arithmetic; round only for display.
- Input-only evaluation estimates assume successful requests. They cannot reconstruct partial request failures, actual deductions, or historical rates. Preserve historical ledgers under their original price assumptions.

## Estimated cost per workflow

These are **planning estimates**, not bills. Count each actual successful request
once. Identity checks, coverage gates and asset routing remain required. Reuse only
validated same-run responses with identical symbols, arguments and observation dates.
Baseline statement reads do not set `latest=true`; comparisons add 0.05 per eligible
statement and symbol. Additional successful retries, expansions and requested branches
add their own costs. Country discovery, symbol resolution and job polling add zero.

In mixed-asset rows, P denotes successful ETF profile probes, not attempted probes.
Row-specific definitions override this notation. For an N-holding
book, reserve up to 0.1N credits for classification; failed HTTP probes do not bill.
Macro overview totals below show normal and conditional maximum prices separately.

### Single stock and research workflows

| Workflow | Credits | Baseline and conditional calls |
|---|---|---|
| `/parallax-score-explainer` | **0 / 0.25 / 5.15** | Methodology-only 0, or 0.05 with symbol identity; current-score explanation 0.25; change explanation 5.15. Explicitly requested report +10. |
| `/parallax-peer-comparison` | **0.8 automatic / 0.9 explicit** | Three verified equities, with unsuccessful HTTP ETF probes. For L priced legs and E equity histories: automatic `0.2 + 0.1L + 0.1E + 0.1P`; explicit `0.2L + 0.1E + 0.1P`. |
| `/parallax-halal-screen` | **0.25 per full screen** | Identity + balance + income + history; prohibited activity can stop at 0.05. Optional Palepu +5/name; portfolio redundancy +0.1/selected compliant holding; alternatives add universe and screening calls. |
| `/parallax-should-i-buy` | **10.55–20.55** | Baseline 10.55 plus 5 per explicit tactical market, up to two. |
| `/parallax-earnings-quality` | **20.3** | Identity, three financial statements, history, Palepu, news and assessment. |
| `/parallax-credit-lens` | **5.5** | Identity 0.05 + four statements/snapshot 0.3 + Palepu/history/telemetry 5.15. |
| `/parallax-due-diligence` | **15.35 / 25.35** | Core financials, history, technicals, news and Palepu; confirmed full report +10. |
| `/parallax-deep-dive` | **20.6–35.6** | Core 20.6 including assessment; up to three explicit tactical markets at 5 each. |
| `/parallax-country-deep-dive` | **11.05 normally** | Default five names: universe5 + identity/snapshot0.75 + three histories0.3 + one overview5. Up to56.05 if that overview reassembles; each extra market adds5 normally/up to50. |
| `/parallax-macro-outlook` | **5.05 normally / 11.1 with equities** | Coverage free, telemetry0.05, overview5 normally/up to50. Optional equities add universe5 + five identity/snapshot pairs0.75 + three histories0.3=6.05. |
| `/parallax-pair-finder` | **5.55 suggestion / 5.35–5.45 evaluate** | One explicit tactical market and a canonical benchmark. Suggestion four legs: identity/export/beta prices/benchmark0.55 + macro5. Evaluate two legs0.35 + macro5; short snapshot can add0.1. Other-market benchmark discovery adds up to0.3 profile credits; history, fallback and no-beta modes change price reads. |
| `/parallax-watchlist-monitor` | **41.2** | `0.1N + 10.05F`, for N=10 watched names and F=4 flagged names; no flags costs1. |
| `/parallax-stress-test-thesis` | **0.05 + 5C + 5.4N + 10A** | C distinct explicit macro market/component requests, N evaluated names, A optional assessments from0–2. Do not assume a fixed position count. |
| `/parallax-white-label-stock-report` | **0 / 10** | Supplied report/local valid response0; successful new report10; repeated successful POST adds10. |
| `/parallax-weekly-themes` | **0.05** | One global telemetry request; ranking and clustering use that response. No automatic macro, equity or research fan-out. |

### Portfolio and desk workflows

| Workflow | Credits | Baseline and conditional calls |
|---|---|---|
| `/parallax-thematic-screen` | **11.05 / 6.05 no-macro** | Default five picks: universe5 + identity/snapshot0.75 + three summaries0.15 + telemetry0.05 + export0.1 + one tactical market5. Three markets21.05. Each candidate changes paired cost by0.15. |
| `/parallax-portfolio-builder` | **12–12.3** | Ten candidates: universe5 + identity/snapshot1.5 + final redundancy0.1H for H=5–8 + validation5. H=10 costs12.5. |
| `/parallax-portfolio-checkup` | **7.5–17.5** | Ten holdings, identity/snapshot1.5, redundancy1, one-to-three tactical markets5 each. With no macro markets,2.5. Scoring/redundancy fallbacks add actual selected holding requests. |
| `/parallax-morning-brief` | **22.55–32.55 normally** | Ten holdings, three top-name news jobs, one-to-three macro overviews. Each overview costs5 normally/up to50; mover news and scoring fallbacks add calls. |
| `/parallax-explain-portfolio` | **28.05 + 0.1P** | Ten equity identities, scores, trends and prices; telemetry; two tactical markets; three news jobs. Reuse matching existing detractor snapshots. |
| `/parallax-scenario-analysis` | **41.55 + 0.1P** | Ten equity holdings, two sector news jobs, one tactical market, two assessments and analysis. Requested additions add universe/candidate/financial reads. |
| `/parallax-rebalance` | **23.5 + 0.1P** | Ten equity holdings, three tactical markets, snapshots, trends, redundancy and portfolio analysis. Proposed V2 scoring is local; V1 quick scoring and replacement/repair calls add costs. |
| `/parallax-client-review` | **64.1 + 0.1P** | Ten equities, three tactical markets, eight drill-downs, five news jobs, one assessment and two analyses. Reuse verified matching snapshots. |
| `/parallax-desk-call-list` | **32.55 example** | `0.05 + 0.05Q + 0.25E + 0.15F + 5·min(E,K)`. Q successful price-symbol reads; E/F equity/ETF movers; K news cap. Pure-equity U20/E6/K10 costs32.55. Classification-success price retries can increase Q. |

> **Desk bound:** `/parallax-desk-call-list` limits movers to40, but still scans the full deduplicated universe U. Pure-equity cost at E=40 is `0.05 + 0.05U + 10 + 5·min(40,K)`; U40/K10 costs62.05. The mover cap does not cap universe scan spend.

### House view and CIO workflows

| Workflow | Credits | Baseline and conditional calls |
|---|---|---|
| `/parallax-load-house-view` | **0** | Local file operations only. |
| `/parallax-house-view-diff` | **sum of both child legs** | Independently price Leg A and Leg B, including child branches; identical12.5-credit builder legs total25. |
| `/parallax-stress-house-view` | **5K + 0.05 normally** | K selected-market overviews plus telemetry. Conditional maximum50K+0.05; top12 costs60.05 normally/up to600.05. Internal stop/cancel before fetch0. |
| `/parallax-make-house-view` | **280.05 at 14 markets** | Four explicit components per market:20M + telemetry0.05; free coverage. |
| `/parallax-judge-house-view` | **280.05 at 14 markets** | Same four-component recipe; dry mode retains fetch costs. |
| `/parallax-house-view-attribution` | **1 at 10 holdings before extras** | `0.1H + 0.1P + 5A`: identity and price per holding, optional P snapshots and A comparable portfolio cross-checks. Reuse validated metadata. |
| `/parallax-cio-letter-prep` | **181.05 normally in example** | `5.05 + 0.15H + 0.1R + 15.1L + Σ macro`: H full audit-union holdings including exited/traded names, R selected successful redundancy lookups≤100, L distinct letter movers≤10. H40/R40/L10/M3 costs181.05 normally/up to316.05 on overview reassembly. |
| `/parallax-white-label-onboard` | **0** | Local extraction/validation; third-party model or hosting costs are separate. |

> **Auto-trigger surcharge:** `/parallax-portfolio-builder`, `/parallax-rebalance` and `/parallax-thematic-screen` can invoke `/parallax-judge-house-view --dry` when an eligible view is at least30 days old. Budget the actual judge recipe separately:280.05 credits at14 markets, even in dry mode. The consuming workflow pays for this fan-out. Preserve its age gate.

### AI investor profile workflows

| Workflow | Credits | Baseline and conditional calls |
|---|---|---|
| `parallax-ai-buffett` | **0.30** | Identity, snapshot, summary financials and history. |
| `parallax-ai-greenblatt` (ticker-check) | **8.15 at R=K=30** | `5 + 0.05R + 0.05K + 0.1P + 0.05I`; R candidate metadata reads before cap, K ratios≤30, P1, I1. |
| `parallax-ai-greenblatt` (universe mode) | **8.30 at R=K=30** | Same formula with P3 and I0. Candidate count before the cap and expansions can increase cost; batch metadata bills per symbol. |
| `parallax-ai-klarman` | **0.30** | Identity, balance sheet, cash flow, ratios and snapshot. |
| `parallax-ai-soros` (single-ticker) | **0.20 + 5M + 5T** | M tactical markets≤5, T theme universe builds1–3; at M5 costs30.20–40.20. |
| `parallax-ai-soros` (basket mode) | **0.05 + 5M + 5T + 0.15H** | H unique surfaced names3–15; identity/snapshot per name, macro/universe per shared basket. |
| `parallax-ai-ptj` (single-ticker) | **10.30–20.30** | Base5.30 plus one-to-three tactical market components at5 each. |
| `parallax-ai-consensus` (single ticker) | **49.25–69.25 example before reuse** | All five: `11.25 + 0.05R + 0.05K + 5(Ms + T + Mp)`; R=K30, Soros Ms5/T1–3, PTJ Mp1–3. Exact same-run response reuse reduces duplicate successful calls. |
| `parallax-ai-consensus` (basket) | **sum of selected ticker plans before reuse** | Up to five selected tickers. Price distinct actual successful requests with symbol multipliers; no unverified fixed basket discount. |

### Navigation, translations and cost context

The concierge adds no paid data calls of its own. Free health and symbol-resolution
calls can run; price the chosen workflow separately. The four
translation skills add no Parallax MCP credits when translating supplied reports.
Model token charges, third-party services and hosting costs are separate.

Plan prices, included allocations and dollar conversion rates are not verified by
this tool contract. Use the operator's current plan before quoting dollars or monthly
allowances. A per-workflow credit estimate is not evidence of a current subscription price.

Examples at22 runs per month, before optional branches or view surcharges:

- `/parallax-desk-call-list` (~32.55 credits for U20/E6/K10) uses716.1 credits monthly.
- `/parallax-morning-brief` (~22.55 credits for ten holdings, three news jobs and one normal overview) uses496.1 credits monthly; overview reassembly increases it.
- `/parallax-should-i-buy` (20.55 credits with two tactical markets), twenty checks, uses411 credits.
