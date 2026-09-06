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

- Expected Parallax spend: ~54 tokens at 10 symbols (`_parallax/token-costs.md`): 1 per symbol score scan + ~11 per flagged name (news 5 + technicals 5 + outlook 1).
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §0.2 typed integer params, §1 coverage fallback, §3 parallel execution, §4 fallbacks, §11 sensitivity, §14 host primitives.
- Surveillance skill: breadth over depth. `weeks` 4–8 is enough to detect recent change and must be a typed integer (conventions §0.2). Only flagged names get the drill-down.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).
- Not a house-view consumer: no loader step, no audit row.

Surveillance scan across a list of tickers — flag what's changed, what needs attention.

## Usage

```
/parallax-watchlist-monitor AAPL.O MSFT.O GOOGL.O AMZN.O META.O NVDA.O TSLA.O
/parallax-watchlist-monitor AAPL.O JPM.N XOM.N JNJ.N weeks=8
```

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Step 2) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: symbol list; optional `weeks=N` (default 8).
4. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Symbols in RIC form (plain tickers → conventions §1); fund/OEIC identifiers get the §1 not-covered message and are dropped with a note.

### Step 2 — Fetch (parallel batches)

**Batch A — score scan.** `call-tool` `get_score_analysis` for every symbol together, `weeks` as int N (non-default; server default 52).

**Batch B — flagged drill-down.** After Step 3 identifies movers, `call-tool` in ONE batch for flagged symbols only: `get_news_synthesis`, `get_technical_analysis`, `get_stock_outlook` with `aspect="recommendations"`. News and technicals are async; never phase them serially; on timeout apply conventions §4 (no re-wait).

### Step 3 — Verify

- Identity: each `get_score_analysis` `data[0].symbol` against the RIC sent (conventions §2).
- Movers: total score change > 1 point, or any single factor moving > 2 points over the window. A symbol with no score history is reported as `no data`, never as stable.

### Step 4 — Compute

No deterministic helper; score changes are differences of the tool's own figures. Rank by magnitude of change, largest first.

### Step 5 — Compose

Fill **Output Format** below in order; Verdict sensitivity per `parallax-conventions.md` §11 by reference (nearest to the >1 / >2 cutoffs); Branding Header per integration-pattern.md §5; About This Report per §7 as a real `## About This Report` heading; `parallax-conventions.md §9.2` disclosure; standard disclaimer `parallax-conventions.md §9.1`.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/watchlist.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill watchlist-monitor < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. Degraded-state notes go inside their section. If `run-shell` is absent, apply conventions §14.3 (render-gate row). No Step 7.

## Output Format

- **Watchlist Summary** (table: all symbols, current total score, score change, alert flag)
- **Verdict sensitivity** (one line, per `parallax-conventions.md` §11 by reference): the 1-2 symbols nearest the alert boundary (the >1-point total / >2-point single-factor cutoffs in Workflow step 2) and the arithmetic that would flip Alert ↔ Stable.
- **Alerts** (ranked by magnitude of change):
  - **Symbol** — score change, which factors moved, brief catalyst
- **Stable Names** (one-liner each — "no material changes")
- **Recommended Actions** (which names warrant a deeper look via /parallax-deep-dive)
- **About This Report** (always present, even when branding is default):
  - Use a real markdown heading: `## About This Report`
  - First line inside the section: `Branding: default Parallax`
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
- Alerts are ordered by magnitude; each flagged name has news, technicals and consensus or a pending note.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 disclaimer are present; expected spend stated (Gotchas).
