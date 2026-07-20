---
name: parallax-explain-portfolio
description: "Reactive portfolio performance attribution: decompose a drawdown into market/regime, factor/thematic, and stock-specific components. Also called 'drawdown attribution' or 'performance attribution' in PM/RIA vocabulary. Uses score-vs-price divergence to determine if the loss is fundamental or transient, then gives conditional advice. Triggered when a client asks 'why am I down X%?'. Holdings as [{symbol, weight}]. NOT for proactive health checks (use /parallax-portfolio-checkup), not for forward-looking reviews (use /parallax-client-review), not for hypothetical scenarios (use /parallax-scenario-analysis)."
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
- quick_portfolio_scores may fail for concentrated/niche portfolios — fall back to get_score_analysis (Step 3) as the primary factor source
- get_peer_snapshot may return a different company as target (see Convention #2) — extract the queried stock's scores from the peer list, not from the target_company field
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (7-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (About This Report) in Output Format.

Reactive performance attribution when a client asks "why am I down?" Decomposes the loss into market/regime, factor/thematic, and stock-specific layers, then determines if the drawdown is fundamental or noise.

## Usage

```
/parallax-explain-portfolio [{"symbol":"AAPL.O","weight":0.25},{"symbol":"JPM.N","weight":0.20},{"symbol":"MSFT.O","weight":0.30},{"symbol":"JNJ.N","weight":0.25}] "I'm down about 4% this month"
```

The second argument is the client's stated concern — used to anchor the lookback period and validate against actual returns.

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, fallback patterns, and macro reasoning. JIT-load `_parallax/house-view/loader.md` for active-view validation and output rendering.

### Step 0 — Tool Loading & Active House View

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

Per `loader.md` §1-§2. If view present, capture tilt vector. The view does NOT change attribution math (Steps 1-5) — it shapes the Step 6 verdict and the framing of Step 4 stock-specific findings. Specifically: when a top detractor is in a view-OW sector, the loss is "expected from view exposure"; when in a view-UW sector that wasn't trimmed, the loss raises a portfolio-management question.

### Step 1 — Measure actual performance

Infer lookback period from the client's statement ("this month" → ~21 trading days, "this week" → 5 days, "this quarter" → ~63 days). Default to 21 days if ambiguous.

#### Step 1a — Asset-class pre-classification (parallel, MANDATORY)

`export_price_series` is the **equity-only** price endpoint; ETFs (SPY, QQQ, IEFA, EWJ, etc.) silently return empty from it and would otherwise be dropped from portfolio-return attribution — a HIGH-IMPACT bias. Before pulling price history, classify each holding:

- For each holding, call `etf_profile(<plain_ticker>)` in parallel.
- If response is `{"error": "No profile data found", ...}` → treat as **equity**, route through `export_price_series`.
- If response returns an ETF profile (non-error) → treat as **ETF**, route through `etf_daily_price`.

This adds N calls with UNVERIFIED token cost (one per holding) — see `_parallax/token-costs.md`.

#### Step 1b — Pull price history (parallel, split by asset class)

Fire ALL of the following in a single tool-call turn:

- For each EQUITY holding → `export_price_series(symbol=<ric>, days=<inferred_period>, format="json")`
- For each ETF holding → `etf_daily_price(symbol=<plain_ticker>, start_date=<today − period>, end_date=<today>)`

#### Step 1c — Compute attribution + halt rule

Compute:
- Per-holding return over the period (close-to-close)
- Weighted contribution to portfolio return: holding return × weight
- Total portfolio return (sum of weighted contributions)
- Rank holdings by contribution (biggest detractors first)

**Halt rule (no silent drops):** if any holding returns empty/error from BOTH `etf_profile` AND its routed endpoint, the skill MUST surface this explicitly:

> ⚠ Cannot compute return for `<holding_symbol>` — neither `export_price_series` nor `etf_daily_price` returned data. This holding is **not** included in the attribution below; the reported portfolio return is computed on the remaining `<X>%` of weight. Operator decision required: supply prices externally, or remove from the portfolio for this analysis.

Render this banner above the attribution table — never silently zero or skip a holding.

Compare computed return against the client's stated figure. If they diverge significantly (>1%), note the discrepancy.

### Step 2 — Attribution layer 1: Market and regime (parallel)

| Tool | Parameters | Purpose |
|---|---|---|
| `get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Current market regime — is the whole market down? |
| `list_macro_countries` | — | Check coverage for home markets |
| `get_peer_snapshot` | per holding | **Primary scoring source** for `PARALLAX_LOADER_V2=1`. Aggregate scores client-side per `loader.md` §3b. |
| `get_company_info` | per holding (parallel) | **Ground-truth oracle** per loader.md §5 rule 3 (required universally). Records `expected_name` for mismatch check. |
| `quick_portfolio_scores` | `holdings` | **Legacy/V1 path only**. Do NOT use if `PARALLAX_LOADER_V2=1` and view active. |

**After Step 2**: cross-check returned names against `get_company_info` names per loader.md §5 rule 3. For `PARALLAX_LOADER_V2=1`, any mismatch in `get_peer_snapshot` is flagged ⚠ MISMATCH and excluded from aggregate calculations. For V1, any mismatch in `quick_portfolio_scores` is re-scored individually.

After Batch: call `macro_analyst` with component="tactical" for each home market (cap at 2). This establishes the macro backdrop: is this a market-wide drawdown, sector rotation, or idiosyncratic?

If `quick_portfolio_scores` fails or returns <50% coverage, don't retry — Step 3's `get_score_analysis` per holding is the more reliable factor source and will provide all needed score data.

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

Fire `get_news_synthesis` non-blocking per conventions §5: overlap it with the branding load, macro reasoning, and the price/score computations that feed the divergence math, and begin assembling those sections immediately. The top-3 detractors' divergence classification (Step 5) and their advice (Step 6) MUST wait for their news to resolve (or its absence be confirmed) — Step 5's provisional-flag rule keys on whether a major event (earnings miss, indictment, regulatory action) broke after the last score data point, which only the news synthesis reveals; finalizing a "Transient — hold or add" verdict on a freshly-adverse detractor before its news lands is the exact failure that flag exists to prevent. If news is still pending when the rest of the report is drafted, render "Analysis pending — service temporarily unavailable" inside Top Detractors AND mark the affected detractors' divergence rows provisional-pending-news, per the Render step's degraded-state rule. Then determine for each: is this stock down because of (a) broad market, (b) sector/factor rotation, or (c) company-specific news?

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

**If mixed:**
- Separate the transient holdings (hold) from the fundamental ones (investigate). Prioritize by weighted contribution to the loss.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format. The loader returns exactly seven keys; any other access (e.g. `branding["voice"]`) raises `KeyError` — structurally enforced by `loader.py`.

### Render — deterministic gate (LAST step, mandatory)

Compose the complete report per **Output Format** below, then run it through the shared render gate in **one Bash step** before replying. Use a private `mktemp` file (never a fixed/predictable path — `/tmp` symlink hazard). The shared gate is `_parallax/render_gate.py`, a sibling of the directory you loaded this SKILL.md from; pass this skill's key (use the loaded directory's absolute path as `<skill-dir>`):

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/explain.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill explain-portfolio < "$DRAFT"; rm -f "$DRAFT"
```

**Your entire final message is exactly that command's stdout** — nothing before it (no step/batch-completion notes, no scratch computation, no "no active house view" / white-label config-probe narration), nothing after it.

**Degraded-state rule:** if an async tool (e.g. `get_assessment`, `get_news_synthesis`) times out or returns no data, render the pending/unavailable note INSIDE the relevant section or the About This Report line — NOT as a preamble above the report — so it is part of the rendered body and survives the gate. (The gate also hoists a leaked degraded note as a backstop.)

`_parallax/render_gate.py` is pure-stdlib and deterministically drops anything before the first rendered block (House View Preamble banner / Branding Header / Ground-truth Integrity / this skill's title or first rendered section), preserving the active-house-view banner in every `view_status` state. Same operator-agnostic-helper pattern as `view_status.py` / `loader.py` (a real Bash tool call, not prose).

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** portfolio attribution`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **What Happened** (computed portfolio return over the period, compared to client's stated figure; 1-sentence summary of the loss magnitude)
- **Performance Attribution** (table: each holding with return, weighted contribution, and primary driver tag — Market / Factor / Stock-Specific; if view active, add "View Exposure" tag — OW / Neutral / UW per the view)
- **Market & Regime Context** (regime tag, mechanism, 2-3 sentences on what's driving markets; is the broad market down too?)
- **Factor Exposure** (which factor tilts helped/hurt; connection to the current regime; if view active, note whether realized factor exposure matched view's intended tilts)
- **Top Detractors** (for each of top 3: what happened, why, and whether scores agree with the price move; flag whether the holding's view-exposure tag means the loss was expected pain from the view)
- **The Key Question: Noise or Signal?** (score-vs-price divergence summary — portfolio-level verdict with per-holding classification table)
- **What To Do** (conditional advice based on the verdict; if view active, separate "stay-the-course-per-view" actions from "view says trim anyway" actions)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line.

Append audit log entry per loader.md §6.

Keep tone calm and explanatory. The client is worried — the output should reduce anxiety with clarity, not amplify it with jargon.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: end with the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.
