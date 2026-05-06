---
name: parallax-cio-letter-prep
description: "Monthly CIO letter prep pack for fund managers: period attribution via daily contribution analysis, top contributors / detractors with evidence-backed drivers, macro snapshot, news themes, and a conditional forward-outlook. Output is Word .docx for the CIO to edit and send. Provide current_portfolio, prior_portfolio, trade_log, period_start, period_end. Symbols in RIC format. NOT for individual stock analysis (use /parallax-deep-dive), not for daily fund-manager check-ins (use /parallax-morning-brief), not for retail/RIA reviews (use /parallax-client-review)."
negative-triggers:
  - Single stock analysis → use /parallax-should-i-buy or /parallax-deep-dive
  - Daily fund manager brief → use /parallax-morning-brief
  - RIA / wealth-advisor client review → use /parallax-client-review
  - Reactive drawdown attribution after a single event → use /parallax-explain-portfolio
  - Backtesting a strategy → use /backtest
  - Period > 365 days → split into quarterly windows manually (export_price_series caps at 365 days)
gotchas:
  - JIT-load `_parallax/parallax-conventions.md` for RIC, symbol cross-validation, parallel exec, fallbacks, news async, macro reasoning, and disclaimer
  - JIT-load `_parallax/house-view/loader.md` ONLY if `house_view` is supplied AND forward-outlook will render. House view is scoped to the forward-outlook section ONLY — retrospective sections (header, attribution, contributors, detractors, trade narrative, macro, news) are always view-agnostic. No view → omit forward-outlook entirely; never retrofit view language onto retrospective prose.
  - Attribution method is "daily contribution analysis" (NOT "time-weighted" / TWR — that's a different industry term for return calculation, and conflating them confuses practitioners). Math: daily weights from `prior_portfolio + trade_log`, sum (daily_weight × daily_return) per holding. Naive `weight × period_return` is silently wrong when positions change mid-period.
  - **Server-side numbers are canonical.** `analyze_portfolio.company_contribution` produces the LP-facing numbers; `scripts/contribution.py` is the local reconciliation audit. If `|local − server| > 25 bps` on total return, halt rendering with an audit-failed error. The 25-bp tolerance accommodates known rebalance-date convention skew between Parallax server-side and local math; tighter agreement would require aligning conventions in v2.
  - `scripts/contribution.py` enforces a 1-bp inner reconciliation gate (`|sum(contributions) − portfolio_total_return| > 1bp` → `ReconciliationError`). On gate fire, surface the diff and abort. Never catch-and-discard.
  - `prior_portfolio` and `trade_log` are HARD-REQUIRED. Reject incomplete invocations with the accepted-shape examples in Inputs. No silent degradation to position-only contribution.
  - `daily_prices` MUST be total-return prices (dividends reinvested). `export_price_series` returns TR-adjusted closes; do not mix in raw closes from any other source.
  - Per-mover fan-out cap: 5 contributors + 5 detractors = 10 names max. Do not exceed.
  - Soft cap on holdings: 40. Auto-truncate to top 40 by current weight; surface "Holdings 41-N (X% weight) excluded from per-position analysis". Daily contribution math runs over the FULL set; only per-mover fan-out is truncated.
  - `macro_analyst` parameter is `market` (not `country`). Cap macro coverage at 3 markets.
  - Period must be ≤ 365 days (`export_price_series` limit). For longer periods, reject with a v2-roadmap note.
  - Output is Word .docx ONLY via the `docx` skill chain. Markdown is an intermediate artifact, never the deliverable.
  - Materiality tiers for excluded holdings: ≤5% total → in-line "Coverage gap" note above contributors table; >5% → high-visibility WARNING banner at top; any single holding >10% → reject the attribution section entirely.
  - Driver-field fallback hierarchy: (1) news event with date from `get_news_synthesis`, (2) factor score change from `get_score_analysis`, (3) sector / peer movement from `analyze_portfolio` (this skill never calls `get_peer_snapshot` directly), (4) default phrase ("Price appreciation in line with [sector / market]" or "Multiple expansion / contraction"). Never render an empty driver slot.
  - Empty contributor / detractor side: if all holdings have positive (negative) contribution, render the populated table only; suppress the empty side rather than rendering "No detractors" prose.
  - Single-holding portfolio: top-5 collapses to top-1 (or top-N for N < 5); render valid for N ∈ [1, 5].
  - Duplicate symbol in input portfolio: reject at validation with "Duplicate symbol {sym}" — no auto-dedup.
  - Mid-period delisting (price series ends before period_end): treat as a coverage gap (drop from rankings + surface per the materiality tiers), not a hard ValueError.
  - This skill is private-beta gated; excluded from default `build-skills.sh` builds. Confirm enablement before running for new customers.
---

# CIO Letter Prep Pack

Generate a structured Word document that a fund-manager CIO can edit and send to LPs as the period letter. The pack covers the period dates, gross return / drawdown / vol, attribution snapshot, top 5 contributors and bottom 5 detractors with evidence-backed drivers, trade-log narrative, macro snapshot, news themes, a conditional forward-outlook (only if a house view is active), coverage gaps, and the standard disclaimer.

## Usage

```
/parallax-cio-letter-prep <inputs.json>
```

Where `inputs.json` provides the structured inputs in the shapes below. The CIO reviews, edits in Word, and sends to LPs. The skill never sends or stores anything externally.

## Inputs

| Field | Required? | Shape | Notes |
|---|---|---|---|
| `current_portfolio` | yes | `[{"symbol":"AAPL.O","weight":0.25}, ...]` | RIC format. Weights sum to ~1.0. |
| `prior_portfolio` | **yes** | `[{"symbol":"AAPL.O","weight":0.20}, ...]` | Period-start snapshot. Hard-required — anchor for trades. |
| `trade_log` | **yes** | `[{"symbol":"NVDA.O","action":"enter","date":"2026-04-15","weight_delta":0.05}, ...]` | Chronologically ordered. Actions ∈ {`add`, `trim`, `enter`, `exit`}. Same-date weight_deltas should sum to zero across symbols. Hard-required — without it, the math is silently wrong when positions change mid-period. |
| `period_start` | yes | ISO `YYYY-MM-DD` | Inclusive. |
| `period_end` | yes | ISO `YYYY-MM-DD` | Inclusive. Period length must be ≤ 365 days. |
| `benchmark` | optional | `"SPY.N"` or RIC | If supplied, attribution snapshot includes excess return. |
| `length_target` | optional | `"short"` (≤ 600 words) \| `"standard"` (≤ 1000) \| `"long"` (≤ 1500) | Default: `"standard"`. Affects narrative density, not table content. |
| `house_view` | optional | view manifest per `_parallax/house-view/loader.md` | Forward-outlook section ONLY. |

If `prior_portfolio` or `trade_log` is missing, reject with a clear error and an accepted-shape example.

## Workflow

JIT-load `_parallax/parallax-conventions.md` for execution-mode, RIC resolution, symbol cross-validation, fallbacks, news async, and macro reasoning. JIT-load `_parallax/house-view/loader.md` ONLY if `house_view` is supplied AND the forward-outlook section will render.

### Batch 0 — Tool loading + house view check

1. Call `ToolSearch` with query `"+Parallax"` to load deferred MCP tool schemas.
2. Validate inputs: weights sum to 1.0 (within 1e-3), period ≤ 365 days, trade_log chronologically ordered, weight_delta sums per date balance to zero, no duplicate symbols.
3. If portfolio has > 40 holdings, truncate to top 40 by current weight and record the truncated tail's combined weight for the excluded-holdings note. Daily contribution math still runs over the FULL set; only per-mover fan-out is truncated.
4. If `house_view` is supplied, load it per loader.md §1-§2. If validation fails, treat as no view (omit forward-outlook). If no `house_view`, skip the forward-outlook section entirely.

### Batch A — Period analytics fan-out (parallel)

Fire all rows below in a single tool-call turn. Every row is independent. Per conventions §2, cross-validate any `target_company` field surfaced in the `analyze_portfolio` peer rollup against `get_company_info.name` for each holding; flag any mismatch and exclude mismatched holdings from aggregate factor calculations.

| Tool | Parameters | Notes |
|---|---|---|
| `mcp__claude_ai_Parallax__get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Market regime context for the period header. |
| `mcp__claude_ai_Parallax__analyze_portfolio` | Construct the `portfolio` array as one entry at `period_start` carrying `prior_portfolio` weights, plus one entry per distinct trade date in `trade_log` carrying the cumulative-post-trade weights as of that date. The final entry's weights MUST equal `current_portfolio`. `start_date=period_start`, `end_date=period_end`, `benchmark=<input or "ACWI.OQ">`, `fields=["portfolio_summary","performance_metrics","drawdown_analysis","portfolio_scores","concentration_metrics","company_contribution","sector_contribution","sector_allocation","time_period_returns","latest_holdings"]`. For the common single-rebalance case (one trade date `D`), the array has 2 entries: `[{date: period_start, ...prior}, {date: D, ...current}]`. | **Single multi-date call.** Server-side `company_contribution` is canonical; current+prior factor exposures via `latest_holdings` + `sector_allocation` over time. `scripts/contribution.py` runs as the reconciliation audit (Batch B step 1). |
| `mcp__claude_ai_Parallax__export_price_series` | `symbol=<each holding>`, `days=<min(period_days, 365)>` | One call per holding (parallel). Returns TR-adjusted closes. Fires for the FULL holdings set (input to local audit) — Batch B fan-out is the truncated set, not this. |
| `mcp__claude_ai_Parallax__get_company_info` | `symbol="<comma-joined RICs>"` | **Single call**, comma-separated. FREE, instant. Returns all holdings' names for cross-validation per conventions §2. |
| `mcp__claude_ai_Parallax__check_portfolio_redundancy` | `holdings=current_portfolio` | Surfaced under coverage gaps if low coverage; otherwise informs trade-narrative quality. |

Asset-class scope: this skill assumes equity legs only (single-stock fund-manager portfolios). `export_price_series` is the correct call for every holding. If a holding resolves to ETF, branch via `etf_daily_price` per the equity-branch convention; equity is the default Pre-classification gate.

If `export_price_series` fails for a holding, mark that holding as price-unavailable and apply materiality-tier handling after Batch B's contribution math.

### Batch B — Top movers + macro fan-out (after Batch A's contribution math)

**Step 1 — Reconciliation audit.** Server-side `analyze_portfolio.company_contribution` provides the canonical LP-facing numbers. Run `scripts/contribution.py` locally as a cross-check:

```bash
# Illustrative — template-fill from JSON inputs at runtime, do not copy {...} literally
python -c "
import json, sys
sys.path.insert(0, 'skills/cio-letter-prep/scripts')
from contribution import daily_contribution, ReconciliationError
result = daily_contribution(
    prior_portfolio=PRIOR_PORTFOLIO,        # dict from prior_portfolio input
    current_portfolio=CURRENT_PORTFOLIO,    # dict from current_portfolio input
    trade_log=TRADES,                       # list from trade_log input
    daily_prices=DAILY_PRICES,              # built from Batch A export_price_series results
    period_start=PERIOD_START,
    period_end=PERIOD_END,
)
print(json.dumps(result))
"
```

Compare local `result['portfolio_total_return']` against server-side `analyze_portfolio.portfolio_summary.total_return`:
- `|local − server| ≤ 25 bps` → render server-side numbers in the pack; note "local audit passed (diff {N} bps)" in Provenance.
- `|local − server| > 25 bps` → halt rendering with "Reconciliation audit failed: local {X} bps vs server {Y} bps (diff {Z} bps exceeds 25-bp tolerance). Investigate before sending to LPs."

The 25-bp tolerance accommodates known rebalance-date convention skew (Parallax server-side rebalances ON date D; `contribution.py` applies trades AFTER D's close). For monthly periods the typical divergence is ~10-25 bps; values outside this band signal a real bug in inputs, prices, or trade log.

The script's own 1-bp inner gate (`ReconciliationError` on `|sum(contributions) − portfolio_total_return| > 1bp`) still fires as the inner safety net.

**Step 2 — Materiality tiers** based on holdings excluded from contribution due to missing prices:

| Total excluded weight | Action |
|---|---|
| 0% < total ≤ 5% | Inline "Coverage gap" note above contributors table listing each excluded `{symbol} ({weight}%)`. |
| Total > 5% | High-visibility **WARNING banner** at the top of the doc: "WARNING: [X.X%] of the portfolio was excluded from contribution analysis due to missing data. Key performance drivers may be missing from this report." |
| Any single holding > 10% weight | Reject the attribution section entirely with an error pointing to the missing symbol. |

**Step 3** — Select top 5 contributors + bottom 5 detractors from server-side `company_contribution`. If a side has fewer than 5 same-signed holdings, render only what exists (suppress empty side).

**Step 4** — Fan out per-mover and macro calls in parallel:

| Tool | Calls | Notes |
|---|---|---|
| `mcp__claude_ai_Parallax__get_assessment` | × ≤ 10 | Async (~30-90s). AI synthesis used for "why" prose. |
| `mcp__claude_ai_Parallax__get_score_analysis` | × ≤ 10 | Weekly factor score history — input to driver fallback step 2. |
| `mcp__claude_ai_Parallax__get_news_synthesis` | × ≤ 10 | Async (~30-90s). Primary input to driver fallback step 1. |
| `mcp__claude_ai_Parallax__macro_analyst` | × ≤ 3 markets | Parameter is `market` (not `country`). Pick relevant markets per conventions §6. Component default — call once per market; the summary call returns all components inline. |

Per conventions §5, the async tools should not block render assembly; if they have not resolved by render time, leave a `[news pending]` placeholder and complete on resolution.

### Batch C — Synthesis (sequential)

Compose the structured pack content with these sections in order. Hand the resulting structured content to the `docx` skill chain to render to Word format.

1. **Period header** — `period_start` to `period_end`, gross return (server-side), max drawdown (`drawdown_analysis.portfolio.max_drawdown`), realized vol (`performance_metrics.portfolio.annualized_volatility`). If `benchmark` was provided, include benchmark return and excess return.
2. **WARNING banner** (only if Step 2 tier 2 fired — total excluded weight > 5%).
3. **Attribution snapshot** — factor and sector deltas from `analyze_portfolio` start-state vs end-state (via `latest_holdings` and `sector_allocation` time series). Two short paragraphs: factor-tilt change, sector-weight change. Reference any redundancy alerts from `check_portfolio_redundancy`.
4. **Top contributors table** — top 5 by `company_contribution`. Row template:
   `{symbol} | {contrib_bps} bps | Driver: {driver_field}`
   Fill `{driver_field}` per the fallback hierarchy:
   1. Notable news event with date (from `get_news_synthesis`) — e.g., `Beat Q1 EPS by 12%, raised guidance (2026-04-22)`.
   2. Significant factor score change (from `get_score_analysis`) — e.g., `MOMENTUM 5.2 → 7.8 over period`.
   3. Sector / peer movement (from `analyze_portfolio` sector-exposure and peer-rollup; no direct `get_peer_snapshot` call) — e.g., `Semis sector +8.4%; SOX leadership`.
   4. Default phrase: `Price appreciation in line with [sector / market]` or `Multiple expansion`.
   Never leave the driver slot blank.
5. **Top detractors table** — bottom 5 by `company_contribution`. Same row template; default-phrase fallback for negative cases is `Multiple contraction` or `Price weakness in line with [sector / market]`. Suppress this section if no holdings have negative contribution.
6. **Trade log integration narrative** — one paragraph weaving the period's trades into the attribution. For each trade, one sentence: which mover the trade enabled or limited (cross-reference contribution_bps for the entered/exited symbol). If trades are minor (< 5% combined weight_delta), summarize as "Limited rebalancing during the period" rather than enumerating.
7. **Macro snapshot** — one bullet per macro market (≤ 3 bullets). Pull headline from each `macro_analyst` summary; ground in the period's regime call from `get_telemetry`.
8. **News themes** — cluster news from `get_news_synthesis` calls by `sector × directional move` (positive vs negative). Max 5 buckets. Each bucket cites ≥ 1 ticker by name. Do NOT repeat the per-mover driver text verbatim; this section is sector-themed.
9. **Forward-outlook** — render ONLY if `house_view` is active and validated. 1 bullet per top-5 holding by current weight, framed in view-language (regime call, tilt direction, conviction notes per loader.md §3-§5). If no active view, OMIT this section entirely.
10. **Coverage gaps** — list any holdings excluded from contribution due to missing data with their weights. List any holdings excluded from per-position analysis due to the 40-holding soft cap. List any tools that returned "data unavailable" per conventions §4.
11. **Provenance** — small footer block (smaller font, italic): generation date, tools used (with versions if available), reconciliation-audit result formatted as `Reconciliation audit: PASS — local total {X} bps vs server {Y} bps; diff {Z} bps; tolerance 25 bps` (or `FAIL` with halt-and-report wording). Skill version + private-beta tag.
12. **Disclaimer** — per conventions §7. If active view: use the view-aware disclaimer per loader.md §5 rule 5; otherwise the standard wording (see Disclaimer section below).

## Output Format

Word .docx ONLY via the `docx` skill chain. The deliverable is a .docx file the CIO can open and edit in Word.

**Render chain:**

1. Batch C composes the structured content (period header, tables as row-arrays, prose paragraphs as strings, conditional banner / forward-outlook flags).
2. Hand the structured content to the `docx` skill: tables become Word tables (branded header row, alternating-row shading), section headers become Word Heading styles (1 / 2), prose becomes Body Text, the WARNING banner (if any) is rendered with a top-of-doc highlight (amber background + dark text).
3. The single deliverable is `.docx`. An internal Markdown intermediate may be produced during development for diffing or review-tool friendliness, but it is NEVER handed to the CIO and NEVER counted as the skill's output. If you find yourself shipping markdown, you've broken the output contract — re-render to `.docx`.

**Default brand palette** (placeholder; the fund's own brand can override):

| Token | Hex | Use |
|---|---|---|
| `cg-navy-900` | `#0C2746` | H1/H2 headings, table header fill |
| `cg-navy-700` | `#154175` | H3/H4 headings, interactive accents |
| `cg-neutral-900` | `#1F2937` | Body text |
| `cg-neutral-500` | `#6B7280` | Muted text (subtitle, provenance, disclaimer) |
| `cg-neutral-100` | `#EAEDF3` | Alternating-row table shading |
| `cg-green-700` | `#15803D` | Positive contributions, "PASS" markers |
| `cg-red-700` | `#B91C1C` | Negative contributions, "FAIL" markers |
| `cg-amber-700` | `#B45309` | Warning banner text |
| `cg-amber-50` | `#F9F1EB` | Warning banner fill |

The render synthesis applies these tokens to: title (navy-900), body (neutral-900), section headings (navy-900 H1/H2 → navy-700 H3/H4 → navy-400 H5/H6), table headers (navy-900 fill + white text), even rows (neutral-100 shading), contributor "+ bps" (green-700), detractor "− bps" (red-700), provenance/disclaimer (neutral-500 + italic + 8-9pt). Funds publishing under their own brand should swap the palette in their config; the default palette is a sensible institutional-finance baseline.

**Golden fixture:** Reference output at `skills/cio-letter-prep/fixtures/golden_pack_2026-04.docx`. Visual + math validation use the same fixture; CI compares structural shape (sections, table row counts, banner presence) against the golden.

## Worked Numerical Example

Hand-verifiable 3-holding 30-day fixture matching `test_held_entire_period_no_trades`. Full derivation in [`references/math-worked-example.md`](references/math-worked-example.md). Summary: AAPL +878.4 bps, JPM −1181.8 bps, MSFT 0, total −303.4 bps. Reconciliation gate clears < 1e-12.

## Math Reference: scripts/contribution.py

Function: `daily_contribution(prior_portfolio, current_portfolio, trade_log, daily_prices, period_start, period_end, reconciliation_tolerance=1e-4)`.

- **Required-input contract:** all six positional arguments are required. The function rejects empty / mismatched / out-of-order / out-of-period inputs with a `ValueError`, including a cross-check that `prior_portfolio + trade_log` reconstructs `current_portfolio` within 10 bps of weight per symbol.
- **Total-return-prices assumption:** `daily_prices` MUST be total-return prices (dividends reinvested). Pass `export_price_series` outputs directly. Passing raw closes breaks reconciliation by the dividend amount; see `test_non_total_return_prices_break_math_negative_control` for the negative control.
- **Reconciliation gate:** the function computes `diff = sum(contributions) − portfolio_total_return` and raises `ReconciliationError(diff, tolerance)` if `|diff| > 1e-4` (1 bp). The skill MUST NOT catch and discard this error — surface it with the diff value and abort rendering.
- **Returns:** `{contributions: {symbol: decimal_contribution}, portfolio_total_return: arithmetic_sum_of_daily_portfolio_returns, reconciliation_diff: signed_diff}`. `contribution_bps = decimal_contribution * 10000`.
- **Arithmetic vs geometric:** the math sums daily contributions arithmetically, not geometrically. The reported `portfolio_total_return` is therefore the arithmetic sum of daily portfolio returns, NOT the geometrically compounded period return. For monthly letter periods the gap is small but non-zero; document it in the pack's footnote if asked.

## MCP Endpoint Contracts: shared `_parallax/scripts/`

Contract tests for this skill live at `scripts/test_mcp_contracts.py` and import the shared validator + schemas from `_parallax/scripts/contract_validator.py` and `_parallax/scripts/contract_schemas.py`. Mock fixtures live at `_parallax/scripts/mcp_mocks/*.json` (shared across all parallax-* skills consuming the same endpoints). The tests assert that each mock conforms to a per-endpoint schema listing the fields the skill is known to read, with required / optional markers and types. Refresh workflow is documented in `_parallax/scripts/mcp_mocks/README.md`. **When this skill begins reading a new field from any endpoint, update the schema in `_parallax/scripts/contract_schemas.py` and the corresponding mock JSON in the same PR.** A red contract test in CI surfaces upstream schema drift before a customer hits it.

## Disclaimer

If active view: use the view-aware disclaimer per `_parallax/house-view/loader.md` §5 rule 5. Otherwise:

> *This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions.*

## Not in scope (v2 candidates)

- **Period > 365 days** — split into quarterly windows manually; v2 will automate.
- **Batch mode for multi-fund firms** — one invocation per fund in v1.
- **Custodian PDF / CSV ingestion** to auto-derive `prior_portfolio` and `trade_log`.
- **Voice synthesis / prose paragraph generation** — v1 produces structured prose; v2 may bake CIO voice templates.
- **Auto-jurisdiction regulatory disclaimers.**
- **House view integration in retrospective sections** — explicitly out of scope to avoid anachronism risk.
- **LP-tier customization** of the same pack.

## Design Lineage

The skill's design choices, summarized inline so the rationale is self-contained:

| Choice | Rationale |
|---|---|
| Daily contribution analysis (not naive `weight × period_return`) | Naive math is silently wrong when positions change mid-period. Daily reconstruction from prior + trade_log is the only correct approach for rebalanced portfolios. |
| Hard-require `prior_portfolio` + `trade_log` | Without both, the math falls back to wrong-by-default. Better to reject than silently degrade. |
| House view scoped to forward-outlook section ONLY | Letter is retrospective; view is forward-looking. Mixing them creates anachronism risk in the LP narrative. |
| Tight composition templates with required evidence slots | Free-form prose drifts into generic platitudes. Templates force evidence-anchored drivers. |
| Materiality tiers for excluded holdings | Drop-with-note is insufficient when the dropped holding is a top contributor. Tiers ensure user-visible warnings scale with materiality. |
| Word .docx output via the `docx` skill chain | Fund managers write LP letters in Word. Native format reduces friction and matches CIO workflow. |
| Server-side `company_contribution` as canonical numbers | Parallax's server-side math is what CIO will defend in LP meetings. Local `contribution.py` is the audit gate. |
| 5+5 contributor/detractor cap with 40-holding soft cap | Async per-mover MCP calls are expensive (~30-90s each). Caps balance cost against narrative depth. |
| Driver fallback hierarchy (news → factor → sector → default phrase) | Real news is best evidence; default phrases prevent broken row rendering when no signal exists. |
| Reconciliation gate + 25-bp audit tolerance | Inner 1-bp gate catches math bugs in `contribution.py`; outer 25-bp gate catches local-vs-server divergence beyond known convention skew. |
| Private-beta gate | Pilot with named customer first; promote after one full letter cycle of feedback. |
| MCP contract tests | Catch upstream Parallax schema drift in CI before customers hit it. |
