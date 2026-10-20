---
name: parallax-explain-portfolio
description: "Reactive portfolio performance attribution: describe a drawdown using measured holding contributions and qualitative market/regime, factor/thematic, and stock-specific context. Also called 'drawdown attribution' or 'performance attribution' in PM/RIA vocabulary. Reports price/score divergence as an observation, competing explanations and unresolved evidence; it does not infer transience or investment actions from score stability. Triggered when a client asks 'why am I down X%?'. Holdings as [{symbol, weight}]. NOT for proactive health checks (use /parallax-portfolio-checkup), not for forward-looking reviews (use /parallax-client-review), not for hypothetical scenarios (use /parallax-scenario-analysis), not for trade recommendations (use /parallax-rebalance)."
---

<!-- white-label: integration-pattern.md -->

# Explain Portfolio

## When not to use

- Proactive portfolio health check → use /parallax-portfolio-checkup
- Scheduled client meeting prep → use /parallax-client-review
- Hypothetical scenario / news event → use /parallax-scenario-analysis
- Rebalancing trade recommendations → use /parallax-rebalance
- Single stock analysis → use /parallax-should-i-buy

## Gotchas

- Expected Parallax spend: ~80 tokens at 10 holdings (`_parallax/token-costs.md`): 10 info + 10 scoring + 10 trends + telemetry + 2 macro + 3 news + 3 detractor snapshots + 10 `etf_profile` probes + 10 per-holding price-series calls (`export_price_series` or `etf_daily_price`, 1 credit each).
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §0.2 typed integers, §1 RIC resolution, §2 identity cross-check, §3 parallel execution, §4/§5 fallbacks, §6 macro reasoning, §14 host primitives.
- JIT-load `_parallax/coverage-matrix.md`: `export_price_series` is equity-only; every holding is classified via `etf_profile` before any price call, and ETFs price via `etf_daily_price`.
- JIT-load `_parallax/house-view/loader.md` FIRST if a view is present: §2, §5, §6. The view does NOT change the attribution math; it describes exposure relative to institutional intent. Overweight/underweight tags do not identify the cause of a loss, prove it was expected, establish suitability or imply a trade.
- Score data is weekly (`get_score_analysis`), prices daily: up to ~7 days of lag. Say so in the divergence analysis, and mark a holding provisional when a major event broke after its last score point.
- Current weights alone produce a period illustration, not realized account performance. State the method before comparing to the client's number; a gap greater than 1 percentage point is a basis difference to investigate, not a verified account discrepancy.
- `get_peer_snapshot` may return a different target; read the queried symbol's row from `comparison[]` (conventions §2), never `target_company` blindly.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Reactive performance attribution when a client asks "why am I down?" Separates measured holding contributions from qualitative market/regime, factor/thematic and company context; identifies what evidence is still needed to explain the loss.

## Usage

```
/parallax-explain-portfolio [{"symbol":"AAPL.O","weight":0.25},{"symbol":"JPM.N","weight":0.20},{"symbol":"MSFT.O","weight":0.30},{"symbol":"JNJ.N","weight":0.25}] "I'm down about 4% this month"
```

The second argument is the client's stated concern — it anchors the lookback period and is compared only on an explicitly stated, compatible return basis.

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Step 2, all batches, including the V1 fallback) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: holdings JSON; the client's statement → exact ISO start/end dates and stated timezone. Calendar-to-date language means the start of that calendar week/month/quarter through the latest completed session as of the request; rolling periods require their actual calendar boundaries. If period is missing or materially ambiguous, ask for it; do not substitute 21 trading days for 21 calendar days.
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture the tilt vector for the Step 4/5 framing.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Validate holdings: RIC format (plain tickers → conventions §1), weights ~1.0. Home markets from RIC suffixes (conventions §6). Classify instrument type from supplied verified identifiers and a discovered asset-type capability when needed: only a validated successful ETF profile establishes ETF; only the documented explicit no-profile/not-in-ETF-universe coverage response plus independently verified listed-equity identity supports the equity route. Timeout, generic error, null/empty or malformed response means type unknown, never equity by default. Fund/OEIC identifiers remain unsupported per conventions §1. Name unknown/unsupported holdings and original weight share; do not call equity-only enrichment for ETF/fund/unknown holdings or invent look-through. Establish the exact common requested start/end dates, whether weights are current/end weights or verified start weights, and whether trades, cash flows, fees, dividends and currency affect the client’s number. Do not invent missing history. Current/end weights use the current-weight illustration below; verified start weights without intervening-history evidence support only a stated static-weight illustration. A realized account return requires verified account returns or an explicitly supported dated-position/trade/cash-flow reconstruction; this workflow has no history-reconstruction engine and must not simulate one from final weights.

### Step 2 — Fetch (parallel batches)

**Batch A — asset-class pre-classification (mandatory).** `call-tool` the discovered `etf_profile` capability for unclassified holdings together. Apply Step 1’s validated-profile / explicit-negative-plus-equity-identity / unknown distinction; never classify arbitrary failure as equity. Verified equities price via `export_price_series`, ETFs via `etf_daily_price`; unknown/fund holdings have unavailable price coverage unless another discovered supported price capability establishes it.

**Batch B — prices, regime, scoring.** `call-tool` ALL together in one turn:

| Tool | Parameters | Purpose |
|---|---|---|
| `export_price_series` | each equity holding: `symbol=<ric>`, `days=<calendar lookback sufficient to include a close on or before requested start>` as int, `format="json"` | close-to-close returns |
| `etf_daily_price` | each ETF holding: `symbol=<plain_ticker>`, `start_date=<common requested start minus bounded anchor lookback>`, `end_date=<common requested end>` | ETF returns |
| `get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Is the whole market down? |
| `list_macro_countries` | — | coverage for home markets |
| `get_peer_snapshot` | per verified equity holding | **Primary scoring source** (V2); aggregated client-side per loader.md §3b |
| `get_company_info` | per holding | **Ground-truth oracle** (loader.md §5 rule 3) |
| `get_score_analysis` | per verified equity holding, `weeks` as int 13 (non-default — conventions §0.2) | **Primary factor-trend source** |
| `quick_portfolio_scores` | verified equity holdings only | V1 only; not with `PARALLAX_LOADER_V2=1` and a view active; if it fails or covers <50%, do not retry — `get_score_analysis` is the factor source |

**Batch C — after Batch B.** `macro_analyst` with `component="tactical"` for each covered home market (cap 2). Then for the top 3 detractors by weighted contribution (Step 4), together: `get_news_synthesis` and `get_peer_snapshot` for verified-equity detractors only (ETF/unknown enrichment unavailable) — non-blocking per §5. Compose from resolved evidence; pending/failed news remains explicitly unknown and never triggers a duplicate job or a claim that no company event occurred. Mark post-score developments and pending news in the observational summary.

### Step 3 — Verify

- Cross-validation per conventions §2 / loader.md §5 rule 3: V2 mismatches ⚠ MISMATCH and excluded from aggregates; V1 mismatches re-scored individually.
- **Halt rule (no silent drops):** any holding lacking usable prices from its supported routed endpoint, regardless of whether its profile succeeded is surfaced above the attribution table with the ⚠ banner naming it, the weight share the reported return covers, and the operator decision required (supply prices, or drop the holding); never zero or skip it silently.
- Report the computed method, price-return/currency basis and coverage before comparing to the client's figure. A gap >1 percentage point is stated in What Happened with basis/history differences; if the account basis is unknown, say reconciliation is not possible, never confirm the client's realized return from current weights.

### Step 4 — Compute

Use the same exact requested start/end calendar boundaries for every return. For each holding choose the latest supported close on or before each boundary, disclose both actual close dates and any nontrading-day carry; reject missing start anchors, stale/undated/future prices or incompatible currency/adjustment bases. Never aggregate 21 trading days for equities with 21 calendar days for ETFs. A longer exchange closure or material date mismatch remains a named coverage gap unless the user accepts an explicit partial illustration; no fabricated zero return.

Per-holding close-to-close price return; static-weight contribution (return × supplied weight); sum and rank detractors. With current/end weights label every total and contribution table **Current-weight period illustration — not realized account performance**. With verified period-start weights label **Static-weight period illustration — not verified realized account performance**, disclosing the no-rebalancing/flow assumption; with true period-start weights and a consistent return basis this arithmetic represents a no-trade buy-and-hold illustration, not a reconstructed traded account. End-weight arithmetic does not recover that starting book. State actual price treatment (including whether adjusted/dividends are available), dates, currency and missing coverage; do not assert total return from unadjusted closes.

Report observed score changes and price changes separately, with dates and the weekly-score lag. Price down / scores stable-or-up = **Observed divergence**; price down / scores down = **Observed co-decline**; mixed or missing evidence = **Mixed / insufficient evidence**. These are descriptive patterns, not transient/fundamental diagnoses, causes or hold/add/trim instructions. Summarize the patterns without a weighted-majority causal verdict. For top detractors, state supported facts, competing explanations (market/sector repricing, company developments, stale scores or omitted information as applicable) and what evidence would distinguish them. Market / Factor / Stock-Specific driver tags are **qualitative hypotheses — not measured attribution** unless a documented measured method supports them; correlated score changes and telemetry alone do not identify causal contributions. News can inform hypotheses but cannot prove that all other fundamentals are unchanged.

### Step 5 — Compose

Fill **Output Format** below in order. What To Do names unresolved evidence, relevant risk/mandate checks and optional further investigation; stable scores, missing news or a price decline alone cannot justify hold/add/trim. If a view is active, distinguish institutional exposure alignment from evidence about returns or client objectives. House View Preamble per loader.md §5.1; Branding Header per integration-pattern.md §5; `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 rule 5 when a view is active, otherwise `parallax-conventions.md §9.1`; audit entry per loader.md §6. Tone calm and explanatory.

### Step 6 — Render (deterministic gate, mandatory)

`write-artifact` the complete drafted report to a new `<draft-path>`, then `run-shell` the shared gate with this skill's key, both per conventions §10.3:

```
python3 "<skill-dir>/../_parallax/render_gate.py" --skill explain-portfolio --input "<draft-path>"
```

Write the draft once and never modify it in place, not even to fix one word. If the report needs a change after the draft is written, run the command above on that draft unchanged (ignore that output), then write the corrected report to a fresh path and run the command on it (conventions §10.3).

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. Degraded-state notes go inside their section. If `run-shell` is absent, apply conventions §14.3 (render-gate row). No Step 7.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** portfolio attribution`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **What Happened** (period, price-return method, weight date and coverage; the current-weight/static-weight illustration label next to the computed percentage; compare to the client’s figure only with basis limitations, or state why realized-account reconciliation is unavailable)
- **Performance Attribution** (table: each holding with return, weighted contribution, and possible driver tag — Market / Factor / Stock-Specific / Unknown, explicitly qualitative hypotheses rather than measured causal attribution; repeat the illustration method label above the table; if view active, add "View Exposure" tag — OW / Neutral / UW per the view)
- **Market & Regime Context** (regime tag, mechanism, 2-3 sentences on what's driving markets; is the broad market down too?)
- **Factor Exposure** (observed factor-score changes and possible regime connections, without quantitative factor-return claims unsupported by a measured method; if view active, compare observed exposure to intended tilts)
- **Top Detractors** (for each of top 3: observed return and score dates, supported news, competing explanations and unresolved evidence; view-exposure tags describe institutional positioning only)
- **The Key Question: Noise or Signal?** (observational price/score summary with a per-holding pattern table, competing explanations, unknowns and the score-lag caveat; explicitly say the observations do not establish whether the loss is temporary or its cause)
- **What To Do** (prioritized evidence checks and optional investigation grounded in the unresolved question; no hold/add/trim inference from price/score patterns; institutional alignment is separate from client objectives)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line.

Append audit log entry per loader.md §6.

Keep tone calm and explanatory. The client is worried — the output should reduce anxiety with clarity, not amplify it with jargon.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: end with the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- A holding with no price from either endpoint: the Step 3 halt banner; the attribution proceeds on the remaining weight and says so.
- News pending for a top detractor: `Analysis pending — service temporarily unavailable` inside Top Detractors and that holding's divergence row marked provisional-pending-news; retain the observational pattern and name the missing evidence; news absence never proves a temporary loss.
- `quick_portfolio_scores` failure or <50% coverage: no retry; `get_score_analysis` is the factor source.
- Telemetry or macro unavailable: Market & Regime Context renders the §4 note; the layer-1 attribution is stated as unavailable, layers 2–3 still render.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- What Happened states the computed illustration, method, period, coverage and limits of comparison to the client’s figure; first line is the House View Preamble, the Branding Header, or `## What Happened`.
- Every holding is in the attribution table or in the halt banner; the pattern table describes every priced holding, including missing-score evidence.
- The Key Question section carries observed patterns, competing explanations, unresolved evidence and the score-lag caveat; no pattern is promoted to a causal diagnosis or trading instruction.
- When a view is active: the `view_status` banner appears verbatim; audit entry appended per loader.md §6 (every consume event).
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present; expected spend stated (Gotchas).
