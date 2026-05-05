---
name: parallax-cio-letter-prep
description: "Monthly CIO letter prep pack for fund managers: period attribution via daily contribution analysis, top contributors / detractors with evidence-backed drivers, macro snapshot, news themes, and a conditional forward-outlook. Output is Word .docx for the CIO to edit and send. Provide current_portfolio, prior_portfolio, trade_log, period_start, period_end. Symbols in RIC format. NOT for individual stock analysis (use /parallax-deep-dive), not for daily fund-manager check-ins (use /parallax-morning-brief), not for retail/RIA reviews (use /parallax-client-review)."
negative-triggers:
  - Single stock analysis → use /parallax-should-i-buy or /parallax-deep-dive
  - Daily fund manager brief → use /parallax-morning-brief
  - RIA / wealth-advisor client review → use /parallax-client-review
  - Reactive drawdown attribution after a single event → use /parallax-explain-portfolio
  - Backtesting a strategy → use /backtest
  - Period > 365 days → split into quarterly windows manually; v2 will automate (export_price_series caps at 365 days)
gotchas:
  - JIT-load `_parallax/parallax-conventions.md` for RIC resolution (§1), symbol cross-validation (§2), parallel execution (§3), graceful fallbacks (§4), news async handling (§5), macro reasoning (§6), and disclaimer (§7).
  - JIT-load `_parallax/house-view/loader.md` ONLY if the user supplies an active view AND the forward-outlook section is being rendered. Per decision 3B-modified, the house view is scoped to the forward-outlook section ONLY — retrospective sections (period header, attribution, contributors, detractors, trade narrative, macro, news) are always view-agnostic. If no active view is present, omit the forward-outlook section entirely; do not retrofit view language onto retrospective prose.
  - Attribution uses **daily contribution analysis** (decision 1A, Amendment B): daily weight reconstruction from `prior_portfolio + trade_log`, then `sum_d (daily_weight × daily_return)` per holding. Naive `weight × period_return` is silently wrong when positions change mid-period. Per Amendment B, do NOT call this "time-weighted contribution" or TWR in any output — TWR is a different industry term (return calculation that strips cash flows) and conflating the two confuses practitioners; "daily contribution analysis" or "daily contribution" is the correct phrase throughout the pack.
  - Daily contribution math is computed by `scripts/contribution.py` (decision 7A, Amendment A). The skill MUST invoke the script via Bash; the LLM does not hand-compute weighted returns. The script enforces a 1-bp reconciliation gate — `sum(contributions) ≈ portfolio_total_return` — and raises `ReconciliationError` on violation. If the gate fires, do not render the pack; surface the error to the user with the offending diff.
  - `prior_portfolio` and `trade_log` are HARD-REQUIRED (decision 2A). If either is missing, reject the invocation with the accepted-shape examples in the Inputs section. Do NOT degrade to a position-only contribution computation — the math is silently wrong when positions change mid-period (the failure mode this skill exists to prevent).
  - `daily_prices` passed to `contribution.py` MUST be total-return prices (dividends reinvested). `export_price_series` returns total-return-adjusted closes; do not pass raw closes from any other source.
  - Per-position fan-out for movers is capped at 5 contributors + 5 detractors = 10 names (decision 4A). Do not exceed this even if the user asks for more — it inflates token cost on async tools (`get_news_synthesis`, `get_assessment` are 30-90s each) without improving the LP narrative.
  - Soft cap on holdings: 40 (decision 10B). For larger portfolios, auto-truncate to top 40 by current weight and surface an "Holdings 41-N (X% combined weight) excluded from per-position analysis" note. Daily contribution math still runs over the full set; only per-mover fan-out is truncated.
  - macro_analyst parameter is `market` (not `country`); cap macro coverage at 3 markets per the conventions (§6).
  - export_price_series is bounded to 365 days. For period > 365 days, reject with a v2-roadmap note: "Period > 365 days not yet supported. Split into quarterly windows and aggregate manually; native multi-quarter aggregation is on the v2 roadmap."
  - Output is Word .docx ONLY (decision 6D). Markdown is an intermediate artifact, not the deliverable. The final hand-off goes through the `docx` skill chain.
  - Materiality tiers for excluded holdings (Amendment C): ≤5% total excluded → in-line "Coverage gap" note above the contributors table; >5% → high-visibility WARNING banner at the top of the doc; any single excluded holding >10% weight → reject the attribution section entirely with an error pointing to the missing symbol.
  - Driver-field fallback hierarchy (Amendment D): when filling the `Driver:` slot in a contributor / detractor row, look in order — (1) notable news event with date from `get_news_synthesis`, (2) significant factor score change from `get_score_analysis`, (3) sector/peer movement from `get_peer_snapshot`, (4) default phrase ("Price appreciation in line with [sector / market]" or "Multiple expansion / contraction"). Never render a row with an empty driver slot.
  - This skill is private-beta gated (decision 9A); it is excluded from default `build-skills.sh` builds. Confirm enablement before running for new customers.
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
| `prior_portfolio` | **yes** (decision 2A) | `[{"symbol":"AAPL.O","weight":0.20}, ...]` | Period-start snapshot. Hard-required — anchor for trades. Reject if absent. |
| `trade_log` | **yes** (decision 2A) | `[{"symbol":"NVDA.O","action":"enter","date":"2026-04-15","weight_delta":0.05}, ...]` | Chronologically ordered. Actions ∈ {`add`, `trim`, `enter`, `exit`}. Same-date weight_deltas should sum to zero across symbols. Hard-required — without it, the math is silently wrong when positions change mid-period. |
| `period_start` | yes | ISO `YYYY-MM-DD` | Inclusive. |
| `period_end` | yes | ISO `YYYY-MM-DD` | Inclusive. Period length must be ≤ 365 days (export_price_series limit). |
| `benchmark` | optional | `"SPY.N"` or RIC | If supplied, attribution snapshot includes excess return; otherwise gross-only. |
| `length_target` | optional | `"short"` (≤ 600 words pack body) \| `"standard"` (≤ 1000) \| `"long"` (≤ 1500) | Default: `"standard"`. Affects narrative density, not table content. |
| `house_view` | optional | view manifest per `_parallax/house-view/loader.md` | Forward-outlook section ONLY (decision 3B-modified). |

If `prior_portfolio` or `trade_log` is missing, reject with a clear error and an accepted-shape example. Do NOT silently degrade to a position-only contribution.

## Workflow

JIT-load `_parallax/parallax-conventions.md` for execution-mode, RIC resolution, symbol cross-validation, fallbacks, news async, and macro reasoning. JIT-load `_parallax/house-view/loader.md` ONLY if `house_view` is supplied AND the forward-outlook section will render (per Amendment 3B-modified scope).

### Batch 0 — Tool loading + house view check

1. Call `ToolSearch` with query `"+Parallax"` to load deferred MCP tool schemas.
2. Validate inputs: weights sum to 1.0 (within 1e-3), period ≤ 365 days, trade_log chronologically ordered, weight_delta sums per date balance to zero.
3. If portfolio has > 40 holdings, truncate to top 40 by current weight and record the truncated tail's combined weight for the excluded-holdings note (decision 10B). Daily contribution math still runs over the FULL set; only per-mover fan-out is truncated.
4. If `house_view` is supplied, load it per loader.md §1-§2. If validation fails, treat as no view (omit forward-outlook). If no `house_view`, skip the forward-outlook section entirely (decision 3B-modified).

### Batch A — Period analytics fan-out (parallel)

Fire all rows below in a single tool-call turn. Every row is independent. Per conventions §2, cross-validate `target_company` returned by `get_peer_snapshot` (called inside `analyze_portfolio` summary) against `get_company_info.name` for each holding; flag any mismatch and exclude mismatched holdings from aggregate factor calculations.

| Tool | Parameters | Notes |
|---|---|---|
| `mcp__claude_ai_Parallax__get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Market regime context for the period header. |
| `mcp__claude_ai_Parallax__analyze_portfolio` | `holdings=current_portfolio` | Current factor / sector / concentration. |
| `mcp__claude_ai_Parallax__analyze_portfolio` | `holdings=prior_portfolio` | Prior factor / sector / concentration — used to compute period deltas (the attribution snapshot). |
| `mcp__claude_ai_Parallax__export_price_series` | `symbol=<each holding>`, `days=<min(period_days, 365)>` | One call per holding. Returns total-return-adjusted closes. Fan out **all N calls in parallel** within Batch A. Asset class is implicitly equity for this skill — single-stock fund-manager portfolios; if a holding resolves to ETF (`etf_profile` would surface this), branch on asset class via `etf_daily_price` instead per the equity branch convention. <!-- coverage-lint: ignore-next --> The Pre-classification gate is "this skill assumes equity legs only — the CIO letter is for stock funds." |
| `mcp__claude_ai_Parallax__get_company_info` | per holding | Ground-truth name oracle for cross-validation (per conventions §2). Fan out in parallel. |
| `mcp__claude_ai_Parallax__check_portfolio_redundancy` | `holdings=current_portfolio` | Surfaced under coverage gaps if low coverage; otherwise informs trade-narrative quality. |

If `export_price_series` fails for a holding, mark that holding as price-unavailable and apply Amendment C tiering after Batch B's contribution math.

### Batch B — Top movers + macro fan-out (after Batch A's contribution math)

Step 1 — daily contribution math (Bash invocation of `scripts/contribution.py`):

```bash
python -c "
import json, sys
sys.path.insert(0, 'skills/cio-letter-prep/scripts')
from contribution import daily_contribution
result = daily_contribution(
    prior_portfolio={...},        # from prior_portfolio input
    current_portfolio={...},      # from current_portfolio input
    trade_log=[...],              # from trade_log input
    daily_prices={...},           # built from Batch A export_price_series results
    period_start='YYYY-MM-DD',
    period_end='YYYY-MM-DD',
)
print(json.dumps(result))
"
```

The script returns `{contributions: {symbol: decimal}, portfolio_total_return: float, reconciliation_diff: float}` and raises `ReconciliationError` if `|sum(contributions) − portfolio_total_return| > 1bp` (Amendment A reconciliation gate). On `ReconciliationError`, surface the diff to the user and abort rendering the pack — do NOT ship a misreconciled letter.

Step 2 — apply Amendment C materiality tiers based on holdings excluded from contribution due to missing prices:

| Total excluded weight | Action |
|---|---|
| 0% < total ≤ 5% | Inline "Coverage gap" note above contributors table listing each excluded `{symbol} ({weight}%)`. |
| Total > 5% | High-visibility **WARNING banner** at the top of the doc: "WARNING: [X.X%] of the portfolio was excluded from contribution analysis due to missing data. Key performance drivers may be missing from this report." |
| Any single holding > 10% weight | Reject the attribution section entirely with an error pointing to the missing symbol; the user must retry or supply data. |

Step 3 — select top 5 contributors (highest positive contribution_bps) and bottom 5 detractors (most negative contribution_bps), giving a max of 10 names for per-mover fan-out.

Step 4 — fan out per-mover and macro calls in parallel:

| Tool | Calls | Notes |
|---|---|---|
| `mcp__claude_ai_Parallax__get_assessment` | × 10 (5 contributors + 5 detractors) | Async (~30-90s). AI synthesis used for "why" prose. |
| `mcp__claude_ai_Parallax__get_score_analysis` | × 10 | Weekly factor score history — input to Amendment D fallback (2). |
| `mcp__claude_ai_Parallax__get_news_synthesis` | × 10 | Async (~30-90s). Primary input to Amendment D fallback (1). |
| `mcp__claude_ai_Parallax__macro_analyst` | × ≤ 3 markets | Parameter is `market` (not `country`). Pick relevant markets per conventions §6: home markets, revenue geographies, commodity / supply-chain exposures. Cap at 3. Component default — call once per market, no separate `tactical` request (the summary call returns all components inline). |

Per conventions §5, the async tools (`get_assessment`, `get_news_synthesis`) should not block render assembly; if they have not resolved by render time, leave a `[news pending]` placeholder and complete on resolution.

### Batch C — Synthesis (sequential)

Compose the structured pack content with these sections in order. Hand the resulting structured content to the `docx` skill chain to render to Word format (see Output Format below).

1. **Period header** — `period_start` to `period_end` (calendar days), gross return (from `portfolio_total_return`), max drawdown (computed locally from the daily portfolio return path), realized vol (annualized from daily portfolio returns). If `benchmark` was provided, include benchmark return and excess return.
2. **WARNING banner** (only if Amendment C tier 2 fired — total excluded weight > 5%).
3. **Attribution snapshot** — factor and sector deltas (current vs prior `analyze_portfolio` output). Two short paragraphs: factor-tilt change, sector-weight change. Reference any redundancy alerts from `check_portfolio_redundancy`.
4. **Top contributors table** — top 5 by contribution_bps. One row per holding using the Amendment 4A template:
   `{symbol} | {contrib_bps} bps | Driver: {driver_field}`
   Fill `{driver_field}` per the Amendment D fallback hierarchy:
   1. Notable news event with date (from `get_news_synthesis`) — e.g., `Beat Q1 EPS by 12%, raised guidance (2026-04-22)`.
   2. Significant factor score change (from `get_score_analysis`) — e.g., `MOMENTUM 5.2 → 7.8 over period`.
   3. Sector / peer movement (from `get_peer_snapshot` via `analyze_portfolio`) — e.g., `Semis sector +8.4%; SOX leadership`.
   4. Default phrase: `Price appreciation in line with [sector / market]` or `Multiple expansion`.
   Never leave the driver slot blank.
5. **Top detractors table** — bottom 5 by contribution_bps. Same row template; default-phrase fallback for negative cases is `Multiple contraction` or `Price weakness in line with [sector / market]`.
6. **Trade log integration narrative** — one paragraph weaving the period's trades into the attribution. For each trade, one sentence: which mover the trade enabled or limited (cross-reference contribution_bps for the entered/exited symbol). If trades are minor (< 5% combined weight_delta), summarize as "Limited rebalancing during the period" rather than enumerating.
7. **Macro snapshot** — one bullet per macro market (≤ 3 bullets). Pull headline from each `macro_analyst` summary; ground in the period's regime call from `get_telemetry`.
8. **News themes** — cluster news from `get_news_synthesis` calls by `sector × directional move` (positive vs negative). Max 5 buckets. Each bucket cites ≥ 1 ticker by name. Do NOT repeat the per-mover driver text verbatim; this section is sector-themed.
9. **Forward-outlook** — render ONLY if `house_view` is active and validated (decision 3B-modified). 1 bullet per top-5 holding by current weight, framed in view-language (regime call, tilt direction, conviction notes per loader.md §3-§5). If no active view, OMIT this section entirely. Do not retrofit view-language onto retrospective sections.
10. **Coverage gaps** (Amendment C tier 1 / Amendment 5A baseline) — list any holdings excluded from contribution due to missing data with their weights. List any holdings excluded from per-position analysis due to the 40-holding soft cap (decision 10B). List any tools that returned "data unavailable" per conventions §4 fallback policy.
11. **Disclaimer** — per conventions §7. If active view: use the view-aware disclaimer per loader.md §5 rule 5; otherwise the standard wording (see Disclaimer section below).

## Output Format

Word .docx ONLY (decision 6D). Markdown is an intermediate format; the deliverable is a .docx file the CIO can open and edit in Word.

**Render chain:**

1. Batch C composes the structured content (period header, tables as row-arrays, prose paragraphs as strings, conditional banner / forward-outlook flags).
2. Hand the structured content to the `docx` skill: tables become Word tables (Heading 1 row, fixed-width columns), section headers become Word Heading styles (1 / 2), prose becomes Body Text, the WARNING banner (if any) is rendered with a top-of-doc highlight (background color or boxed Heading 1).
3. The `docx` skill's create-new-document path uses `docx-js` (npm) to assemble and validate the .docx, writing the output file to a path the user can open. See `~/.claude/skills/docx/SKILL.md` for the invocation pattern.
4. The single deliverable is `.docx`. An internal Markdown intermediate may be produced during development for diffing or review-tool friendliness, but it is NEVER handed to the CIO and NEVER counted as the skill's output. If you find yourself shipping markdown, you've broken decision 6D — re-render to `.docx`.

**Golden fixture:** Decision 8A pins a reference output at `skills/cio-letter-prep/fixtures/golden_pack_2026-04.docx` (produced in Task 4 against live MCP). Visual + math validation use the same fixture; CI compares structural shape (sections, table row counts, banner presence) against the golden.

## Worked Numerical Example (held-entire-period)

This example mirrors `scripts/test_contribution.py::test_held_entire_period_no_trades` so the math is verifiable without running the script.

**Inputs:**
- Period: `2026-01-01` to `2026-01-31` (30 return-days, 31 calendar dates).
- 3 equally-weighted holdings, no trades.
- Total-return prices (linear paths for clean hand-computation):

| Symbol | Day 0 | Day 30 | Daily price formula |
|---|---|---|---|
| `AAPL.O` | 100.0 | 130.0 | `price[d] = 100 + d` |
| `MSFT.O` | 100.0 | 100.0 | flat |
| `JPM.N` | 100.0 | 70.0 | `price[d] = 100 - d` |

- `prior_portfolio = current_portfolio = {AAPL.O: 1/3, MSFT.O: 1/3, JPM.N: 1/3}`
- `trade_log = []`

**Per-holding daily-return formulas (arithmetic):**
- AAPL: `r[d] = (100+d)/(99+d) - 1 = 1/(99+d)` for d ∈ [1, 30]
- MSFT: `r[d] = 0`
- JPM: `r[d] = (100-d)/(101-d) - 1 = -1/(101-d)` for d ∈ [1, 30]

**Per-holding sum of arithmetic daily returns:**
- AAPL: `Σ_{k=100..129} 1/k ≈ 0.26336`
- MSFT: `0`
- JPM: `−Σ_{k=71..100} 1/k ≈ −0.34988`

**Contributions (weight × sum-of-daily-returns, since weights are constant):**
- AAPL contribution ≈ `(1/3) × 0.26336 ≈ +0.08779` (`+877.9 bps`)
- MSFT contribution ≈ `0` (`+0 bps`)
- JPM contribution ≈ `(1/3) × (−0.34988) ≈ −0.11663` (`−1166.3 bps`)

**Portfolio total return (arithmetic sum of daily portfolio returns):**
- ≈ `+0.08779 + 0 + (−0.11663) ≈ −0.02883` (`−288.3 bps`)

**Reconciliation:** `sum(contributions) − portfolio_total_return ≈ 0` (well below the 1-bp tolerance). Amendment A's gate passes.

**Pack rendering** (synthesized; not from a real run): top contributor `AAPL.O +877.9 bps`; top detractor `JPM.N −1166.3 bps`; period total `−288.3 bps`. Driver fields would be filled per Amendment D fallback (defaults to "Price appreciation / contraction in line with [stock-level move]" for this synthetic data because no real news / factor / peer signal exists).

## Math Reference: scripts/contribution.py

Function: `daily_contribution(prior_portfolio, current_portfolio, trade_log, daily_prices, period_start, period_end, reconciliation_tolerance=1e-4)`.

- **Required-input contract (Amendment 2A):** all six positional arguments are required. The function rejects empty / mismatched / out-of-order / out-of-period inputs with a `ValueError`, including a cross-check that `prior_portfolio + trade_log` reconstructs `current_portfolio` within 10 bps of weight per symbol.
- **Total-return-prices assumption:** `daily_prices` MUST be total-return prices (dividends reinvested). Pass `export_price_series` outputs directly. Passing raw closes breaks reconciliation by the dividend amount; see `test_non_total_return_prices_break_math_negative_control` for the negative control.
- **Reconciliation gate (Amendment A):** the function computes `diff = sum(contributions) − portfolio_total_return` and raises `ReconciliationError(diff, tolerance)` if `|diff| > 1e-4` (1 bp). The skill MUST NOT catch and discard this error — surface it to the user with the diff value and abort rendering.
- **Returns:** `{contributions: {symbol: decimal_contribution}, portfolio_total_return: arithmetic_sum_of_daily_portfolio_returns, reconciliation_diff: signed_diff}`. `contribution_bps = decimal_contribution * 10000`.
- **Arithmetic vs geometric:** the math sums daily contributions arithmetically, not geometrically. The reported `portfolio_total_return` is therefore the arithmetic sum of daily portfolio returns, NOT the geometrically compounded period return. For monthly letter periods the gap is small but non-zero; document it in the pack's footnote if asked.

## MCP Endpoint Contracts: scripts/mcp_mocks/

Contract tests live at `scripts/test_mcp_contracts.py` (Amendment E). Mocks for each Parallax MCP endpoint the skill calls live at `scripts/mcp_mocks/*.json`. The tests assert that each mock conforms to a per-endpoint schema listing the fields the skill is known to read, with required / optional markers and types. Refresh workflow is documented in `scripts/mcp_mocks/README.md`. **When this skill begins reading a new field from any endpoint, update the schema in `test_mcp_contracts.py` and the corresponding mock JSON in the same PR.** A red contract test in CI surfaces upstream schema drift before a customer hits it.

## Disclaimer

If active view: use the view-aware disclaimer per `_parallax/house-view/loader.md` §5 rule 5. Otherwise:

> *This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions.*

## Not in scope (v2 candidates)

- **Period > 365 days:** v2 will split into quarterly windows and aggregate. v1 rejects with the v2-roadmap note.
- **Batch mode for multi-fund firms** — one invocation per fund in v1.
- **Custodian PDF / CSV ingestion** to auto-derive `prior_portfolio` and `trade_log`.
- **Voice synthesis / prose paragraph generation** — v1 produces structured prose; v2 may bake CIO voice templates.
- **Auto-jurisdiction regulatory disclaimers.**
- **House view integration in retrospective sections** — explicitly out of scope per decision 3B-modified to avoid anachronism risk.
- **LP-tier customization** of the same pack.
