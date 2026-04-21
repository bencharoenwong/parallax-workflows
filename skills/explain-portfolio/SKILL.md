---
name: parallax-explain-portfolio
description: "Reactive portfolio performance attribution: decompose a drawdown into market/regime, factor/thematic, and stock-specific components. Uses score-vs-price divergence to determine if the loss is fundamental or transient, then gives conditional advice. Triggered when a client asks 'why am I down X%?'. Holdings as [{symbol, weight}]. NOT for proactive health checks (use /parallax-portfolio-checkup), not for forward-looking reviews (use /parallax-client-review), not for hypothetical scenarios (use /parallax-scenario-analysis)."
negative-triggers:
  - Proactive portfolio health check → use /parallax-portfolio-checkup
  - Scheduled client meeting prep → use /parallax-client-review
  - Hypothetical scenario / news event → use /parallax-scenario-analysis
  - Rebalancing trade recommendations → use /parallax-rebalance
  - Single stock analysis → use /parallax-should-i-buy
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallbacks
  - JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §5 (output rendering), §6 (audit). For attribution, the view provides additional context: a drawdown in a view-tilted-overweight sector is "expected pain from view exposure"; a drawdown in a view-tilted-underweight sector raises "why was this still held?" — surface in the verdict.
  - When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer
  - Holdings must be in RIC format with weights summing to ~1.0
  - export_price_series returns daily OHLCV — use close prices for return calculation
  - get_telemetry regime_tag and mechanism fields are the key attribution inputs
  - Score-vs-price divergence is the core insight — scores stable + price down = transient; scores falling + price down = fundamental
  - Score data is weekly (get_score_analysis) vs daily price data — there may be a ~7 day lag. Acknowledge this gap in the divergence analysis, especially if major news broke after the last score data point.
  - The client said a number ("down 4%") — verify it against actual computed returns before attributing
  - Cap news calls at top 3 detractors to manage token cost
  - `PARALLAX_LOADER_V2=1` is MANDATORY when a house view is active: use per-holding `get_peer_snapshot` aggregation (§3b), not batch `quick_portfolio_scores`. V1 path (`quick_portfolio_scores` primary, `get_score_analysis` fallback) is only for no-view sessions and is NOT the primary factor source under V2.
  - get_peer_snapshot may return a different company as target (see Convention #2 and loader.md §5 rule 3) — extract the queried stock's scores from the peer list, not from the target_company field. Under V2, mismatches are flagged ⚠ MISMATCH and excluded from aggregate calculations.
  - Rules 3 (ground-truth panel) and 4 (divergence assertion) in loader.md §5 apply UNIVERSALLY to this skill — ground-truth panel in Step 2/Step 4, divergence assertion in Step 6 whenever rotation candidates are generated via `build_stock_universe`.
---

# Explain Portfolio

Reactive performance attribution when a client asks "why am I down?" Decomposes the loss into market/regime, factor/thematic, and stock-specific layers, then determines if the drawdown is fundamental or noise.

## Usage

```
/parallax-explain-portfolio [{"symbol":"AAPL.O","weight":0.25},{"symbol":"JPM.N","weight":0.20},{"symbol":"MSFT.O","weight":0.30},{"symbol":"JNJ.N","weight":0.25}] "I'm down about 4% this month"
```

The second argument is the client's stated concern — used to anchor the lookback period and validate against actual returns.

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, fallback patterns, and macro reasoning. JIT-load `_parallax/house-view/loader.md` for active-view validation and output rendering.

### Step 0 — Load Active House View

Per `loader.md` §1-§2. If view present, capture tilt vector. The view does NOT change attribution math (Steps 1-5) — it shapes the Step 6 verdict and the framing of Step 4 stock-specific findings. Specifically: when a top detractor is in a view-OW sector, the loss is "expected from view exposure"; when in a view-UW sector that wasn't trimmed, the loss raises a portfolio-management question.

### Step 1 — Measure actual performance

Infer lookback period from the client's statement ("this month" → ~21 trading days, "this week" → 5 days, "this quarter" → ~63 days). Default to 21 days if ambiguous.

Call `export_price_series` for each holding (parallel) with the inferred period. Compute:
- Per-holding return over the period (close-to-close)
- Weighted contribution to portfolio return: holding return × weight
- Total portfolio return (sum of weighted contributions)
- Rank holdings by contribution (biggest detractors first)

Compare computed return against the client's stated figure. If they diverge significantly (>1%), note the discrepancy.

### Step 2 — Attribution layer 1: Market and regime (parallel)

**Path selection first (per conventions §0 — choose exactly ONE scoring path, never fire both):**

- **V2 path** (active view, multi-sector portfolio, or per-holding factor rendering — attribution renders per-holding tags, so V2 is typical): add `get_peer_snapshot` per holding + `get_company_info` per holding. Do NOT call `quick_portfolio_scores`.
- **V1 path** (no view AND portfolio-level aggregate only): add `quick_portfolio_scores` once + `get_company_info` per holding. Do NOT call `get_peer_snapshot` here (Step 4 calls it ad-hoc for top detractors).

Then fire Step 2 in parallel. Common calls (both paths):

| Tool | Parameters | Purpose |
|---|---|---|
| `get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Current market regime — is the whole market down? |
| `list_macro_countries` | — | Check coverage for home markets |

Path-specific calls:

| Tool | Path | Parameters | Notes |
|---|---|---|---|
| `get_peer_snapshot` | **V2 only** | per holding | Aggregate client-side per loader.md §3b. |
| `get_company_info` | V1 + V2 | per holding | Ground-truth oracle per loader.md §5 rule 3 — records `expected_name`. |
| `quick_portfolio_scores` | **V1 only** | `holdings` | Legacy batch path. Forbidden when any V2 selection rule fires. |

**After Step 2**: cross-check returned names against `get_company_info` names per loader.md §5 rule 3. On V2, any mismatch in `get_peer_snapshot` is flagged ⚠ MISMATCH and excluded from aggregates. On V1, any mismatch in `quick_portfolio_scores` is re-scored individually.

After Batch: call `macro_analyst` with component="tactical" for each home market (cap at 2). This establishes the macro backdrop: is this a market-wide drawdown, sector rotation, or idiosyncratic?

**V1-path only** (no active view, no `PARALLAX_LOADER_V2=1`): if `quick_portfolio_scores` fails or returns <50% coverage, don't retry — Step 3's `get_score_analysis` per holding is the more reliable factor source. Under V2, the per-holding `get_peer_snapshot` aggregation above is already the primary source; `get_score_analysis` in Step 3 adds the time-series trend, not a fallback factor source.

### Step 3 — Attribution layer 2: Factor and thematic

Call `get_score_analysis` for each holding (parallel) with `weeks` as int 13 (lookback window, non-default — see conventions §0.2). This is the **primary factor data source** — more reliable than `quick_portfolio_scores` for score trend analysis.

Analyze:
- Which factor scores changed most across the portfolio? (e.g., momentum collapsed across the board → factor rotation)
- Are score changes correlated across holdings? (yes → systematic/thematic; no → stock-specific)
- Portfolio-level factor tilt: is the portfolio concentrated in a factor that's out of favor per the regime?

Cross-reference with `get_telemetry` divergences — do any thematic baskets in the telemetry data match the portfolio's exposure?

### Step 4 — Attribution layer 3: Stock-specific

For the **top 3 detractors** by weighted contribution (parallel):

| Tool | Parameters |
|---|---|
| `get_news_synthesis` | `symbol` |
| `get_peer_snapshot` | `symbol` |

**Note on `get_peer_snapshot`:** The tool may return a different company as the "target" (see Convention #2). Extract the queried stock's scores from wherever it appears in the peer list — do not trust the `target_company` field blindly. Cross-check against `get_company_info` if the name looks wrong.

Determine for each: is this stock down because of (a) broad market, (b) sector/factor rotation, or (c) company-specific news?

### Step 5 — Score-vs-price divergence (the key insight)

For each holding, compare:
- **Price change** over the period (from Step 1 — daily data, up to today)
- **Score change** over the period (from Step 3 — weekly data, may lag by up to 7 days)

**Important:** If a major event occurred after the last score data point (e.g., earnings miss, indictment, regulatory action), note that scores may not yet reflect this development. The divergence classification still applies but should be flagged as provisional for affected holdings.

Classify each holding:

| Price | Scores | Interpretation | Advice |
|---|---|---|---|
| Down | Stable/Up | **Transient** — market mispricing, fundamentals intact | Hold or add |
| Down | Down | **Fundamental** — deterioration confirmed by scores | Investigate, consider trim |
| Down | Mixed | **Ambiguous** — some factors deteriorating, others stable | Monitor, dig deeper |

Portfolio-level verdict: if majority of weighted holdings show "Transient" → overall drawdown is likely noise. If majority show "Fundamental" → drawdown reflects real deterioration.

### Step 6 — Custom advice

Based on the verdict:

**If transient (scores stable, regime-driven):**
- "Your portfolio's fundamentals haven't changed. Quality scores are still [X], defensive scores are [Y]. The drawdown is driven by [regime: risk-off / factor rotation / sector selloff]. Historically these reversals take [timeframe context from macro tactical]. Stay the course unless your risk tolerance has changed."

**If fundamental (scores declining):**
- Identify which holdings have deteriorating scores. For each, suggest: deeper analysis (`/parallax-deep-dive`), trim, or replacement.
- If the factor tilt is the problem (e.g., heavy momentum in a mean-reversion regime), suggest rebalancing toward favored factors per the macro tactical outlook.

**Rotation candidate generation (optional — only if the client asks for specific replacements inline rather than being redirected to `/parallax-rebalance`):**

- **V2 path** (active view OR the replacement theme names ≥2 sectors/themes): decompose into N parallel `build_stock_universe` calls, one per sector/theme, merge by RIC, dedupe, re-rank by composite score — per loader.md §3a "Application (V2)". Do NOT issue a single `build_stock_universe` call spanning multiple sectors.
- **V1 path** (no view AND single-sector replacement): one `build_stock_universe` call is acceptable.
- **Divergence assertion** (required on both paths, per loader.md §5 rule 4): if the caller intent named N≥2 sectors/themes, compute `max_sector_share / total` on the returned (or merged) candidate set. If > 0.6, emit a fail-loud warning and either refuse or re-issue as parallel per-sector queries (V2 path already does this by construction).
- **Ground-truth check per candidate** (per loader.md §5 rule 3): call `get_peer_snapshot` + `get_company_info` in parallel for each top-ranked candidate; drop any row where `returned_name ≠ expected_name`.
- If an active view is loaded, filter candidates against `tilts.excludes` and `tilts.excludes_freeform` per loader.md §3.

**If mixed:**
- Separate the transient holdings (hold) from the fundamental ones (investigate). Prioritize by weighted contribution to the loss.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble)
- **What Happened** (computed portfolio return over the period, compared to client's stated figure; 1-sentence summary of the loss magnitude)
- **Performance Attribution** (table: each holding with return, weighted contribution, and primary driver tag — Market / Factor / Stock-Specific; if view active, add "View Exposure" tag — OW / Neutral / UW per the view)
- **Market & Regime Context** (regime tag, mechanism, 2-3 sentences on what's driving markets; is the broad market down too?)
- **Factor Exposure** (which factor tilts helped/hurt; connection to the current regime; if view active, note whether realized factor exposure matched view's intended tilts)
- **Top Detractors** (for each of top 3: what happened, why, and whether scores agree with the price move; flag whether the holding's view-exposure tag means the loss was expected pain from the view)
- **The Key Question: Noise or Signal?** (score-vs-price divergence summary — portfolio-level verdict with per-holding classification table)
- **What To Do** (conditional advice based on the verdict; if view active, separate "stay-the-course-per-view" actions from "view says trim anyway" actions)

Append audit log entry per loader.md §6.

Keep tone calm and explanatory. The client is worried — the output should reduce anxiety with clarity, not amplify it with jargon.

If active view: end with the view-aware disclaimer per loader.md §5 rule 5. Otherwise:

> *"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*
