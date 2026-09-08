---
name: parallax-explain-portfolio
description: "Reactive portfolio performance attribution: decompose a drawdown into market/regime, factor/thematic, and stock-specific components. Also called 'drawdown attribution' or 'performance attribution' in PM/RIA vocabulary. Uses score-vs-price divergence to determine if the loss is fundamental or transient, then gives conditional advice. Triggered when a client asks 'why am I down X%?'. Holdings as [{symbol, weight}]. NOT for proactive health checks (use /parallax-portfolio-checkup), not for forward-looking reviews (use /parallax-client-review), not for hypothetical scenarios (use /parallax-scenario-analysis), not for trade recommendations (use /parallax-rebalance)."
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

- Expected Parallax spend: ~70 tokens at 10 holdings (`_parallax/token-costs.md`): 10 info + 10 scoring + 10 trends + telemetry + 2 macro + 3 news + 3 detractor snapshots + 10 `etf_profile` probes.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §0.2 typed integers, §1 RIC resolution, §2 identity cross-check, §3 parallel execution, §4/§5 fallbacks, §6 macro reasoning, §14 host primitives.
- JIT-load `_parallax/coverage-matrix.md`: `export_price_series` is equity-only; every holding is classified via `etf_profile` before any price call, and ETFs price via `etf_daily_price`.
- JIT-load `_parallax/house-view/loader.md` FIRST if a view is present: §2, §5, §6. The view does NOT change the attribution math; it shapes the verdict — a loss in a view-OW sector is "expected pain from view exposure", a loss in a view-UW sector still held raises a portfolio-management question.
- Score data is weekly (`get_score_analysis`), prices daily: up to ~7 days of lag. Say so in the divergence analysis, and mark a holding provisional when a major event broke after its last score point.
- The client's stated number is verified against computed returns before anything is attributed; a >1% gap is stated.
- `get_peer_snapshot` may return a different target; read the queried symbol's row from `comparison[]` (conventions §2), never `target_company` blindly.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Reactive performance attribution when a client asks "why am I down?" Decomposes the loss into market/regime, factor/thematic, and stock-specific layers, then determines if the drawdown is fundamental or noise.

## Usage

```
/parallax-explain-portfolio [{"symbol":"AAPL.O","weight":0.25},{"symbol":"JPM.N","weight":0.20},{"symbol":"MSFT.O","weight":0.30},{"symbol":"JNJ.N","weight":0.25}] "I'm down about 4% this month"
```

The second argument is the client's stated concern — it anchors the lookback period and is validated against actual returns.

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Step 2, all batches, including the V1 fallback) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: holdings JSON; the client's statement → lookback ("this week" 5 trading days, "this month" ~21, "this quarter" ~63; default 21).
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture the tilt vector for the Step 4/5 framing.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Validate holdings: RIC format (plain tickers → conventions §1), weights ~1.0. Home markets from RIC suffixes (conventions §6).

### Step 2 — Fetch (parallel batches)

**Batch A — asset-class pre-classification (mandatory).** `call-tool` `etf_profile(<plain_ticker>)` for every holding together: `{"error": "No profile data found"}` → equity → `export_price_series`; a profile → ETF → `etf_daily_price`. N calls at 1 token each.

**Batch B — prices, regime, scoring.** `call-tool` ALL together in one turn:

| Tool | Parameters | Purpose |
|---|---|---|
| `export_price_series` | each equity holding: `symbol=<ric>`, `days=<period>` as int, `format="json"` | close-to-close returns |
| `etf_daily_price` | each ETF holding: `symbol=<plain_ticker>`, `start_date=<today − period>`, `end_date=<today>` | ETF returns |
| `get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Is the whole market down? |
| `list_macro_countries` | — | coverage for home markets |
| `get_peer_snapshot` | per holding | **Primary scoring source** (V2); aggregated client-side per loader.md §3b |
| `get_company_info` | per holding | **Ground-truth oracle** (loader.md §5 rule 3) |
| `get_score_analysis` | per holding, `weeks` as int 13 (non-default — conventions §0.2) | **Primary factor-trend source** |
| `quick_portfolio_scores` | `holdings` | V1 only; not with `PARALLAX_LOADER_V2=1` and a view active; if it fails or covers <50%, do not retry — `get_score_analysis` is the factor source |

**Batch C — after Batch B.** `macro_analyst` with `component="tactical"` for each covered home market (cap 2). Then for the top 3 detractors by weighted contribution (Step 4), together: `get_news_synthesis` and `get_peer_snapshot` — non-blocking per §5, but Step 5's divergence verdict for those three WAITS for their news (or its confirmed absence), because the provisional flag keys on whether a major event broke after the last score point.

### Step 3 — Verify

- Cross-validation per conventions §2 / loader.md §5 rule 3: V2 mismatches ⚠ MISMATCH and excluded from aggregates; V1 mismatches re-scored individually.
- **Halt rule (no silent drops):** a holding empty from BOTH `etf_profile` and its routed price endpoint is surfaced above the attribution table with the ⚠ banner naming it, the weight share the reported return covers, and the operator decision required (supply prices, or drop the holding); never zero or skip it silently.
- Computed portfolio return vs the client's figure: a gap > 1% is stated in What Happened.

### Step 4 — Compute

Per-holding close-to-close return; weighted contribution (return × weight); total; rank by contribution (detractors first). Layer 2: which factor scores moved most, whether moves are correlated across holdings (systematic) or not (stock-specific), and whether the portfolio's factor tilt is out of favour per the regime and telemetry divergences. Layer 3: for each top-3 detractor, broad market / sector-factor rotation / company-specific. Divergence classification per holding — Down/Stable-or-Up = **Transient** (hold or add); Down/Down = **Fundamental** (investigate, consider trim); Down/Mixed = **Ambiguous** (monitor) — with the provisional flag where news post-dates the last score point. Portfolio verdict = the weighted majority class.

### Step 5 — Compose

Fill **Output Format** below in order; conditional advice by verdict: transient → fundamentals unchanged, regime-driven, stay the course unless risk tolerance changed; fundamental → name the deteriorating holdings and suggest deeper analysis (`/parallax-deep-dive`), trim, or replacement, and rebalance toward favoured factors when the tilt is the problem; mixed → separate hold from investigate, prioritized by weighted contribution. House View Preamble per loader.md §5.1; Branding Header per integration-pattern.md §5; view-exposure tags where a view is active; `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 rule 5 when a view is active, otherwise `parallax-conventions.md §9.1`; audit entry per loader.md §6. Tone calm and explanatory.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/explain.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill explain-portfolio < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. Degraded-state notes go inside their section. If `run-shell` is absent, apply conventions §14.3 (render-gate row). No Step 7.

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


## Failure modes

- A holding with no price from either endpoint: the Step 3 halt banner; the attribution proceeds on the remaining weight and says so.
- News pending for a top detractor: `Analysis pending — service temporarily unavailable` inside Top Detractors and that holding's divergence row marked provisional-pending-news; never finalize a Transient verdict on a freshly adverse name without its news.
- `quick_portfolio_scores` failure or <50% coverage: no retry; `get_score_analysis` is the factor source.
- Telemetry or macro unavailable: Market & Regime Context renders the §4 note; the layer-1 attribution is stated as unavailable, layers 2–3 still render.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- What Happened states the computed return, the period, and the gap to the client's figure; first line is the House View Preamble, the Branding Header, or `## What Happened`.
- Every holding is in the attribution table or in the halt banner; the verdict table classifies every priced holding.
- The Key Question section carries a portfolio-level verdict and the score-lag caveat.
- When a view is active: the `view_status` banner appears verbatim; audit entry appended per loader.md §6 (every consume event).
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present; expected spend stated (Gotchas).
