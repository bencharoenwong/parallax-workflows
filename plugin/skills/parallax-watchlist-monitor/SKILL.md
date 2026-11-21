---
name: parallax-watchlist-monitor
description: "Monitor a watchlist of tickers: flag score changes, news alerts, technical shifts, and analyst updates via Parallax MCP tools. Provide list of symbols. NOT for single stock analysis (use /parallax-deep-dive), not for portfolio diagnostics (use /parallax-morning-brief), not for weighted client books ranked by who to call (use /parallax-desk-call-list), not for building a portfolio (use /parallax-portfolio-builder)."
---

<!-- white-label: integration-pattern.md -->

# Watchlist Monitor

## When not to use

- Single stock deep dive → use /parallax-deep-dive
- Portfolio with weights → use /parallax-morning-brief or /parallax-client-review
- Weighted client books ranked by who to call → use /parallax-desk-call-list
- Building a portfolio → use /parallax-portfolio-builder

## Gotchas

- Expected Parallax spend: `0.1N + 10.05F` credits, where N is scanned symbols and F is score movers (price-only moves add no drill-down): score history 0.1 per symbol; news 5 + technicals 5 + recommendations 0.05 per score mover. Ten symbols with four score movers cost 41.2; with none, 1. With `price_check=true`, add 0.1 per symbol for the `etf_profile` asset-class probe (HTTP 4xx/5xx probes cost zero) and 0.05 per verified equity for the price series. Excludes resolution/recovery; current discovered prices win (`_parallax/token-costs.md`).
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §0.2 typed integer params, §1 coverage fallback, §3 parallel execution, §4 fallbacks, §11 sensitivity, §14 host primitives, §16 scores against live prices.
- Surveillance skill: breadth over depth. `weeks` 4–8 is enough to detect recent change and must be a typed integer (conventions §0.2). Only score movers get the drill-down.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).
- Not a house-view consumer: no loader step, no audit row.

Surveillance scan across a list of tickers — flag what's changed, what needs attention.

## Usage

```
/parallax-watchlist-monitor AAPL.O MSFT.O GOOGL.O AMZN.O META.O NVDA.O TSLA.O
/parallax-watchlist-monitor AAPL.O JPM.N XOM.N JNJ.N weeks=8
/parallax-watchlist-monitor AAPL.O MSFT.O NVDA.O price_check=true
```

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Step 2) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: nonempty symbol list; optional `weeks=N` integer 1–200 (default 8); optional `price_check=true|false` (default false); optional `price_move=N`, a percentage 1–100 (default 15), accepted only with `price_check=true` (reject it otherwise). Reject invalid values and clarify a weighted holdings payload instead of discarding weights.
4. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Symbols in RIC form (plain tickers → conventions §1); fund/OEIC identifiers get the §1 not-covered message and are dropped with a note.

### Step 2 — Fetch (parallel batches)

**Batch A — score scan and asset-class pre-classification.** `call-tool` `get_score_analysis` for every symbol together, `weeks` as int N (non-default; server default 52). Only when the user passed `price_check=true`: in the same batch, `call-tool` `etf_profile(<plain_ticker>)` for every symbol, per `_parallax/coverage-matrix.md` § "Required pattern for skills". A validated ETF profile establishes ETF. The explicit not-found-in-ETF-universe response plus the Step 3 identity cross-check of `get_score_analysis` `data[0].symbol` against the RIC sent establishes equity; that cross-check is the listed-equity identity evidence for a RIC input. A symbol with no score-history row is asset-class unknown. Transport, auth, schema or other errors leave the asset class unknown; never classify a generic failure as equity.

**Batch A2 — price series.** Only with `price_check=true`, after Batch A returns: `call-tool` `export_price_series(symbol=<ric>, days=<D>, format="json")` for each verified equity that returned verified score history, where `D = min(365, 7 × weeks + 7)` as a typed integer (conventions §0.2). When the clamp binds and the series does not reach a symbol's ranking date, report that symbol's move as not checked with the reason "ranking date older than the 365-day price window"; this is not a failed call. ETF, unknown and no-score-history symbols get no price call; mark their price movement unavailable and state the reason (ETF, asset class unverified, or no verified score history). A verified equity whose price call fails after the §0.1 retry is also marked unavailable, with the reason "price series call failed".

**Batch B — score-mover drill-down.** After Step 3 identifies score movers, `call-tool` in ONE batch for score movers only: `get_news_synthesis`, `get_technical_analysis`, `get_stock_outlook` with `aspect="recommendations"`. Price-only movers get no drill-down. News and technicals are async; never phase them serially; on timeout apply conventions §4 (no re-wait).

### Step 3 — Verify

- Identity: each `get_score_analysis` `data[0].symbol` against the RIC sent (conventions §2).
- Movers: absolute total score change > 1 point, or any single factor changing by an absolute > 2 points over the window. A symbol with no score history is reported as `no data`, never as stable. Change requires at least two verified dated observations with comparable score fields; otherwise report `insufficient history` and do not rank or mark stable. State the actual first/last dates and observation count; a shorter available window is not the full requested lookback. Missing factor endpoints remain unavailable; they do not become zero change.
- Price moves, only with `price_check=true`: per conventions §16.2, record each verified equity's ranking date and price change since it; every other symbol shows `unavailable` with its Batch A2 reason. A symbol whose absolute price change since the ranking date is at least `price_move` percent is listed under **Price moves since ranking**. This list is reported, not flagged: it adds no drill-down and no alert.

### Step 4 — Compute

No deterministic helper; score changes are differences of the tool's own figures. Rank score movers by absolute total score change, largest first; break ties by the largest absolute single-factor change, then by symbol. Rank the price-move list by absolute price change since the ranking date, largest first; break ties by symbol.

### Step 5 — Compose

Fill **Output Format** below in order; Verdict sensitivity per `parallax-conventions.md` §11 by reference (nearest to the >1 / >2 cutoffs); Branding Header per integration-pattern.md §5; About This Report per §7 as a real `## About This Report` heading; `parallax-conventions.md §9.2` disclosure; standard disclaimer `parallax-conventions.md §9.1`.

### Step 6 — Render (deterministic gate, mandatory)

`write-artifact` the complete drafted report to a new `<draft-path>`, then `run-shell` the shared gate with this skill's key, both per conventions §10.3:

```
python3 "<skill-dir>/../_parallax/render_gate.py" --skill watchlist-monitor --input "<draft-path>"
```

Write the draft once and never modify it in place, not even to fix one word. If the report needs a change after the draft is written, run the command above on that draft unchanged (ignore that output), then write the corrected report to a fresh path and run the command on it (conventions §10.3).

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. Degraded-state notes go inside their section. If `run-shell` is absent, apply conventions §14.3 (render-gate row). No Step 7.

## Output Format

- **Watchlist Summary** (table: all symbols, current total score with its ranking date, score change, alert flag; with `price_check=true`, also the move since the ranking date)
- **Verdict sensitivity** (one line, per `parallax-conventions.md` §11 by reference): the 1-2 symbols nearest the alert boundary (the >1-point total / >2-point single-factor cutoffs in Step 3) and the arithmetic that would flip Alert ↔ Stable. This line covers the score Alert only, not the `price_move` list.
- **Alerts** (score movers only, ranked per Step 4):
  - **Symbol** — score change, which factors moved, brief catalyst, ranking date.
- **Price moves since ranking** (only with `price_check=true`; ranked per Step 4): **Symbol** — ranking date, price change since it labeled per conventions §16.2 step 2, and the line "Scores do not reflect this move." No factor directions and no adjusted scores (conventions §16).
- **Stable Names** (one-liner each — "no score changes")
- **Recommended Actions** (which score movers warrant a deeper look via /parallax-deep-dive; price-only symbols are not named here)
- **About This Report** (always present, even when branding is default):
  - Use a real markdown heading: `## About This Report`
  - First line inside the section: render the loaded branding-state line from integration-pattern.md §7 (default Parallax only when the loader reports default; preserve custom/suppressed state).
  - Unconditional second line, per integration-pattern.md §7: `Currency: figures as reported by source data; no base-currency conversion applied.`
  - If a logo was skipped under white-label, add `Logo on file: <basename>`

Keep it scannable. Lead with what changed.

## Output additions

- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top: `**<client_name>** watchlist scan`. Logo handling per integration-pattern.md §5.
- **About This Report** (always present): render a `## About This Report` section with the branding-state line above. Place it before the AI disclosure/disclaimer footer. If a logo was skipped, include `Logo on file: <basename>` as a second line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- A symbol's score scan fails after the §0.1 retry: listed as `no data` in the summary table, excluded from ranking.
- News or technicals pending for a flagged name: the Alerts entry carries the pending note (conventions §5); the alert itself still renders from the score change.
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- Watchlist Summary lists every input symbol with a score, a change, and an alert flag (or `no data`); first line is the Branding Header or `## Watchlist Summary`.
- Alerts are ordered per Step 4; each flagged name has news, technicals and consensus or a pending note.
- With `price_check=true`, every symbol shows a ranking date and a move since it or `unavailable`, and the Price moves since ranking section is present (possibly empty).
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 disclaimer are present; expected spend stated (Gotchas).
