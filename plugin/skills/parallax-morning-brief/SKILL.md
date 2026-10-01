---
name: parallax-morning-brief
description: "Fund manager morning brief: market regime, macro outlook, portfolio health, and key holding news via Parallax MCP tools. Provide portfolio as [{symbol, weight}] in RIC format. NOT for individual stock analysis (use /parallax-should-i-buy), not for client portfolio review (use /parallax-client-review), not for a desk-wide call list across many books (use /parallax-desk-call-list), not for retail health checks (use /parallax-portfolio-checkup), not for backtesting (use /backtest)."
---

<!-- white-label: integration-pattern.md -->

# Morning Brief

## When not to use

- Single stock analysis → use /parallax-should-i-buy or /parallax-deep-dive
- Running backtests → use /backtest
- Client portfolio review → use /parallax-client-review
- Retail investor health check → use /parallax-portfolio-checkup
- Multiple client books / desk-wide morning call list → use /parallax-desk-call-list
- Thematic screening → use /parallax-thematic-screen

## Gotchas

- Expected Parallax spend: ~50 tokens at 10 holdings (`_parallax/token-costs.md`): telemetry + macro (5) + 2× per-holding fan-out + 3 news (15).
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §0.2 (`macro_analyst` takes `market`, not `country`), §1 RIC resolution and coverage fallback, §2 identity cross-check, §3 parallel execution, §4/§5 fallbacks, §11 sensitivity, §14 host primitives, §15 translation.
- JIT-load `_parallax/house-view/loader.md` FIRST; if a view is present follow §2, §3, §4, §5, §6. The brief uses the view to (a) frame the Macro Snapshot in view language, (b) flag holdings misaligned with tilts, (c) prioritize Action Items toward the view's rebalance direction.
- The `macro_analyst` summary call returns every component inline including tactical — never make per-component calls.
- Health flags per `parallax-portfolio-checkup/references/health-flags.md` apply here (flag-level only; no Health Status badge).
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report, with the unconditional currency line).
- A `lang=` value other than `en` makes Step 7 mandatory (conventions §15).

Generate a structured fund manager morning brief by orchestrating Parallax MCP tools.

## Usage

```
/parallax-morning-brief [{"symbol":"AAPL.O","weight":0.25},{"symbol":"MSFT.O","weight":0.20},{"symbol":"JPM.N","weight":0.15},{"symbol":"JNJ.N","weight":0.15},{"symbol":"XOM.N","weight":0.25}]
/parallax-morning-brief [{"symbol":"AAPL.O","weight":0.25},{"symbol":"MSFT.O","weight":0.20}] market=Japan top_n=5 lang=th register=retail
```

Optional after the portfolio JSON: `market=Japan`, `top_n=5`, `lang=<code>` (`en` default; `zh-CN`, `zh-TW`, `zh-HK`, `th`), `register=retail` (passed only when translation is requested).

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Step 2, including the V1 fallback) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: holdings JSON; `market=` (default United States); `top_n=` (default 3); `lang=`; `register=`.
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture tilt vector, excludes, prose excerpt (narrative voice) and macro_regime. On §2 failure run without the view.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Validate holdings: RIC format (plain tickers → conventions §1), weights ~1.0; fund/OEIC identifiers get the §1 not-covered message and are dropped with a note. Top-N news set = the N largest input weights (needs no tool output).

### Step 2 — Fetch (parallel batches)

**Batch A** — `call-tool` ALL rows in ONE turn; per-holding rows fan out N-wide inside the same turn so the 30–90 s news calls overlap everything else (a sequential loop is the largest latency leak in this skill):

| Tool | Parameters | Notes |
|---|---|---|
| `get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Market regime |
| `macro_analyst` | `market` (default United States), no component | Macro summary with tactical inline |
| `get_peer_snapshot` | per holding, all N in parallel | **Primary scoring source** (V2); aggregated client-side per loader.md §3b |
| `get_company_info` | per holding, all N in parallel | **Ground-truth oracle** (loader.md §5 rule 3; conventions §2); records `expected_name` |
| `get_news_synthesis` | per top-N holding, all in parallel | Async 30–90 s; never blocks output (§5) |
| `check_portfolio_redundancy` | `holdings` | Overlap detection |
| `quick_portfolio_scores` | `holdings` | **V1 path only**; not used when `PARALLAX_LOADER_V2=1` and a view is active |

### Step 3 — Verify

- Cross-validation per conventions §2 / loader.md §5 rule 3: `get_peer_snapshot.target_company` vs `get_company_info.name`; V2 mismatches are ⚠ MISMATCH and excluded from aggregates; V1 mismatches are re-scored individually via `get_peer_snapshot`.
- Failed or empty calls: §0.1 retry classification, then §4. News still pending at compose time: the pending note goes inside that holding's paragraph (§5), never above the report.

### Step 4 — Compute

No deterministic helper. Evaluate the five health flags over trusted holdings per `parallax-portfolio-checkup/references/health-flags.md` (Low Score ≤ 5.0, Concentration >15% / >45% top-3, Redundancy ≥ 2 pairs, Value Trap ≤ 3.0, Macro Misalignment). If a view is active: flag holdings >25% off the view-tilted target, holdings on `tilts.excludes`, and view conflicts for Action Items. **Conditional drift pointer:** if the alignment check above finds ≥3 holdings whose factor exposure conflicts with the view's tilts, append one line to Action Items: "Consider running /parallax-judge-house-view for a full drift analysis (≥3 holdings show view-conflict signals)." Do NOT auto-invoke the judge from morning-brief — the one-liner is a pointer, not an action; this brief already fans out the macro call the judge would repeat.

### Step 5 — Compose

Fill **Output Format** below in order, under 800 words: House View Preamble per loader.md §5.1; Branding Header per integration-pattern.md §5; Verdict sensitivity per §11 by reference (flag-level wording only); `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 rule 5 when a view is active, otherwise `parallax-conventions.md §9.1`; audit entry per loader.md §6.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/mbrief.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill morning-brief < "$DRAFT"; rm -f "$DRAFT"
```

The entire final English message is that command's stdout, or the sole input to Step 7. The stderr `[render-gate] WARN:` line is diagnostics: never include or translate it. Degraded-state notes go inside their section. If `run-shell` is absent, apply conventions §14.3 (render-gate row).

### Step 7 — Translate (conditional)

Only when `lang=` is present and not `en`. Translate per `parallax-conventions.md` §15 (routing block §15.2, failure footers §15.3, disclaimer boundary check §15.4, audit `notes` on a boundary event). Body is the gated Step 6 stdout including About This Report, the §9.2 disclosure and the disclaimer; never run the gate on translated text; pass `register: retail` only when supplied.

## Output Format

Present as a structured morning brief, under 800 words:

- **House View Preamble** (only if view active) — 1-line summary per loader.md §5 rule 1 (preamble). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** morning brief`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **Market Regime & Signals** (2-3 sentences; if view active, note alignment/divergence with view's regime call)
- **Macro Snapshot** (bullet points)
- **Ground-truth Integrity** (only render if any mismatch detected — table: `input_ticker`, `returned_name`, `expected_name`, status. Mismatched holdings had scores re-derived via `get_peer_snapshot` — per loader.md §5 rule 3.)
- **Portfolio Factor Tilt** (table: VALUE, QUALITY, MOMENTUM, DEFENSIVE scores aggregated over TRUSTED holdings only; mismatched holdings' re-derived scores included when available; if view active, add column showing view-target factor)
- **Redundancy & Alignment Alerts** (only if flagged; include View Misalignment / View Excluded if view active)
- **Verdict sensitivity** (render when any numeric health flag sits near its published cutoff): the 1-2 nearest-boundary flags and their trigger/clear arithmetic per `parallax-portfolio-checkup/references/health-flags.md` "Verdict sensitivity" (§11 by reference). Morning-brief renders no Health Status badge — state flag-level conditions only; do not use the tier-ladder language.
- **Holding News** (one paragraph per holding)
- **Action Items** (what deserves attention today; if view active, prioritize toward view rebalance direction)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse), plus the unconditional §7 currency line: `Currency: figures as reported by source data; no base-currency conversion applied.` If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a further About This Report line.

Lead with what matters.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- `get_telemetry` or `macro_analyst` unavailable: Market Regime & Signals / Macro Snapshot render the §4 unavailable note; the portfolio sections still render.
- V2 scoring gaps: mismatched or unscored holdings are excluded from the Factor Tilt aggregate and named in Ground-truth Integrity.
- News pending or timed out: pending note inside the holding's paragraph; the brief is not delayed.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- Every Output Format section rendered or marked unavailable with its reason, under 800 words; first line is the House View Preamble, the Branding Header, or `## Market Regime & Signals`.
- Factor Tilt is computed over trusted holdings only and says so when any were excluded.
- When a view is active: the `view_status` banner appears verbatim; Action Items are ordered toward the view; audit entry appended per loader.md §6 (every consume event).
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present; expected spend stated (Gotchas).
- Translation (if requested) completed per §15, or the §15.3 footer explains why not.
