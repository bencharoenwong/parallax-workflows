---
name: parallax-event-review
description: "Event-triggered portfolio review: after a headline or market event that has already happened (an AI selloff, a rate shock, tariff news), show how a named portfolio did over the event window, where its exposure to the event sits, including look-through into fund holdings, and its factor profile, then frame neutral review questions and options to discuss. Static-weight illustration from one field-limited portfolio analysis; low credit cost, suited to running across many client books. Triggers: 'event review', 'how did this book do in the selloff', 'after the headline, review the portfolio', 'post-event client note', 'event look-through'. NOT for a hypothetical or forward scenario (use parallax-scenario-analysis), a 'why am I down' question with no named event (use parallax-explain-portfolio), a scheduled client meeting review (use parallax-client-review), or a single stock (use parallax-should-i-buy)."
---

<!-- white-label: integration-pattern.md -->

# Event Review

## When not to use

- Hypothetical or forward-looking scenario, stress test or replay → use /parallax-scenario-analysis
- "Why am I down?" with no named event, or a full driver analysis with news → use /parallax-explain-portfolio
- Scheduled client meeting prep → use /parallax-client-review
- Proactive health check with no trigger → use /parallax-portfolio-checkup
- Single stock analysis → use /parallax-should-i-buy

## Gotchas

- Expected Parallax spend (`_parallax/token-costs.md`): `5.1 + 0.15E + 0.1F` credits for one portfolio analysis (5), one score-history read for the ranking date (0.1), E equities scored and name-checked (0.1 + 0.05 each, on either scoring path) and F fund lines looked through. Symbol searches cost 0. Six equities and one fund cost **6.1 credits**. The cost does not depend on window length.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §0.3 field-request integrity, §1 RIC resolution, §2 identity cross-check, §3 parallel execution, §4 fallbacks, §9 disclaimer, §12 framing, §13 audience mode, §14 host primitives.
- JIT-load `_parallax/house-view/loader.md` FIRST. §5 rule 3 (ground-truth check) applies on every run. If a view is present, also apply §2, §3b, §5 and §6. The view does NOT change the window figures; it describes exposure relative to institutional intent. Overweight/underweight tags do not explain a result, establish suitability or imply a trade.
- JIT-load `_parallax/coverage-matrix.md`: factor scores are equity-only. Fund lines get look-through from fund holdings, never a forced score.
- The headline is an input, not a finding. The operator supplies the event and its window. Any added market context must come from a dated source named in the report. Never invent event facts.
- Weights supplied for the window start produce a **static-weight period illustration**: no trading, so each line's weight drifts with its price. It is not realized account performance. Say so next to every portfolio-level figure.
- Scores are weekly. State the ranking date read in Step 2, and say that no score reflects price moves after that date. Never adjust a score for the event.
- Compare every RIC returned by the analysis with the RIC sent. An uncovered symbol can come back mapped to a different listing. Name every difference in Method and Data Notes.
- Fund-holdings responses can carry per-holding labels. Render only weights and names from them; never render a rating or recommendation label in this report.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Reports how a portfolio did over a named event window, using one static-weight portfolio analysis, fund look-through and the weekly factor ranking. Built to run the same way across many books after one event.

## Usage

```
/parallax-event-review "October 2026 AI selloff" 2026-09-30 2026-10-30 [{"symbol":"JNJ.N","weight":0.15},{"symbol":"WMT.O","weight":0.15},{"symbol":"VOO","weight":0.25}] benchmark=SPY
```

Arguments: the event as headline text; window start and end dates; holdings with weights at the window start; optional `benchmark=<symbol>`; optional `audience=client_safe`. With no benchmark, ask the operator; the analysis default may not match the book's market.

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named in Step 1 and Step 2 (`search_stocks`, `search_etfs` and the Step 2 table) to the exact callable and schema exposed now. Read the portfolio-analysis schema for its portfolio, benchmark, date and fields parameters.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: event headline, exact ISO window start and end, holdings, benchmark, audience. If the window is missing, propose the month start to the latest completed session and `ask-operator` to confirm. Never infer a window from news coverage alone. If no benchmark was supplied, `ask-operator` for one; never let the analysis default stand in silently.
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture the tilt vector for the Step 5 framing. `read-config` `PARALLAX_LOADER_V2`; with it set to 1 and a view active, Step 2 takes the V2 scoring path.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Validate holdings: weights sum to about 1.0. Resolve each symbol per conventions §1, using `search_stocks` for a plain ticker; resolve fund lines with `search_etfs`, which `search_stocks` does not cover. Record each line as equity, fund or unsupported. Check every fund's asset class: a bond fund is not an equity fund. A bond fund or multi-asset fund that the analysis covers stays in the analysis for its return; it gets no factor score, and its look-through counts only the event-linked holdings the response returns. Exclude a line only when the analysis does not cover it: rescale the rest, and name the exclusion and its original weight. Never substitute a proxy without operator confirmation.

### Step 2 — Fetch (parallel batches)

**Batch A** — `call-tool` together:

| Tool | Parameters | Purpose |
|---|---|---|
| `analyze_portfolio` | `portfolio=[{date: <window start>, symbol: <ric>, weight: <w>}]` for every supported line, the window end date, the benchmark, `fields=["portfolio_summary","performance_metrics","company_contribution","sector_contribution","drawdown_analysis","data_quality"]` | Window return, benchmark return, drawdown, contributions |
| `quick_portfolio_scores` | verified equity lines only | Factor table. V1 only; not with `PARALLAX_LOADER_V2=1` and a view active |
| `get_peer_snapshot` | each verified equity line, only with `PARALLAX_LOADER_V2=1` and a view active | Factor table (V2): one row per holding from its snapshot's target row |
| `get_company_info` | each verified equity line | **Ground-truth oracle** (loader.md §5 rule 3) |
| `etf_holdings` | each fund line | Event look-through |
| `get_score_analysis` | one verified equity line, `weeks` as int 4 (conventions §0.2) | Ranking date of the current scores |

Call each tool once. Never split the window into shorter runs, and never rerun the analysis with changed weights.

### Step 3 — Verify

- Ground-truth check per conventions §2 and loader.md §5 rule 3: compare the company name each scoring tool returned with the `get_company_info` name of record. A mismatch renders ⚠ MISMATCH, and that holding's scores stay out of any aggregate row. Mismatch recovery follows conventions §2 and loader.md §5 rule 3 by path. On the V2 path, re-derive that holding's scores from its own cached `get_peer_snapshot` `comparison[]` row (the `is_target: true` row, no new call) when that snapshot passed cross-validation, and render them marked `re-derived`; a snapshot that failed cross-validation is never a score source. On the V1 path this skill holds no snapshot, so the holding renders `scores unavailable`. A holding whose `get_company_info` call fails or returns empty, or that has no returned name to compare, is UNCHECKED: its scores stay in Factor Profile with its identity stated as unconfirmed, never treated as a pass. List every ⚠ MISMATCH and UNCHECKED holding in Ground-truth Integrity.
- Compare the RICs the analysis returned with the RICs sent; name every remap.
- Per conventions §2, compare each equity line's `company_contribution[].name`, matched by `ric`, with its `get_company_info` name of record after normalizing both. A mismatch marks that row ⚠ MISMATCH in Contribution: its return is not attributed to the intended company, and the portfolio figures state that they include the line as returned. An equity line with no contribution row, no returned name or no oracle name is UNCHECKED. List both in Ground-truth Integrity.
- Check that `get_score_analysis` `data[0].symbol` equals the RIC sent. If it differs or is missing, state the ranking date as unconfirmed.
- Read `data_quality`. A line with no usable prices is named above the contribution chart with its weight share; the portfolio figures cover the remaining weight and say so.
- The ranking date is the latest score-history date whose scores match that holding's factor-table row (the quick-score row, or its snapshot row on the V2 path). If no row matches, state the ranking date as unconfirmed.
- Fund look-through covers only the holdings the response returns. State that share of the fund; the event exposure is a floor when it is below 100%.

### Step 4 — Compute

Report the analysis output as returned: portfolio return (`performance_metrics.portfolio.total_return`), benchmark return (`performance_metrics.benchmark.total_return`), largest drawdown (`drawdown_analysis.portfolio.max_drawdown`) and its date, and per-line contribution. If a named field is missing, write `unavailable` for that figure; never derive it from another block. Never recompute returns. Shares of a total (for example "three lines produced 85% of the gain") are each contribution divided by the returned total, computed once and shown with the inputs. Event exposure through a fund is the fund's weight in the book times each event-linked holding's share of the fund. The operator's event theme decides which holdings count as event-linked; list them by name in the look-through table.

### Step 5 — Compose

Fill **Output Format** below in order. Apply audience render mode per parallax-conventions.md §13; default internal_analyst. Explain each factor score in the same paragraph, using the scale text the `get_company_info` response returns in `score_scale`. Where that text describes a percentile rank against other covered stocks, a Value score of 8 ranks better than about 80% of them. If no `score_scale` text is returned, describe scores as 0–10 rankings with the plain-language gloss of conventions §13.3 and give no percentile figure. Never give the Overall score a percentile reading: its factor weights shift across market regimes. An equity-weighted average row is optional; it covers verified holdings only (no ⚠ MISMATCH or UNCHECKED), states the share of equity weight it covers, and follows loader.md §3b on the V2 path. Review Questions are neutral questions drawn from numbers in the report. Options to Discuss follow §12: render the informational preface and action-label framing per parallax-conventions.md §12. Title each option as a noun phrase that names a choice ("A sector concentration limit"), give its trade-off with "would", and do not put a named holding next to its weight, contribution or score inside an option. If a view is active, keep institutional exposure alignment separate from the event result and from client objectives. Close the section with: "The reader and their licensed adviser decide which, if any, fit the portfolio's objectives." For a broker or intermediary audience, add that the options are conversation starters for licensed staff.

### Step 6 — Render (deterministic gate, mandatory)

`write-artifact` the complete drafted report to a new `<draft-path>`, then `run-shell` the shared gate with this skill's key, both per conventions §10.3:

```
python3 "<skill-dir>/../_parallax/render_gate.py" --skill event-review --input "<draft-path>"
```

Write the draft once and never modify it in place, not even to fix one word. If the report needs a change after the draft is written, run the command above on that draft unchanged (ignore that output), then write the corrected report to a fresh path and run the command on it (conventions §10.3).

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. Degraded-state notes go inside their section. If `run-shell` is absent, apply conventions §14.3 (render-gate row). No Step 7.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** event review`. Logo handling per integration-pattern.md §5.
- **The Event** — the headline and window as supplied; any added context with its dated source. No portfolio numbers here.
- **The Period in Numbers** — portfolio return, benchmark return (name the benchmark symbol), largest drawdown with date, event exposure estimate; the static-weight illustration label next to the portfolio return.
- **Contribution** — table of every line: return and contribution in percentage points of the book, sorted; excluded lines and remaps noted under it.
- **Event Look-through** — direct event-linked holdings, then per fund: each event-linked holding, its share of the fund and its share of the book, the covered share of the fund, and the total as a floor where coverage is partial.
- **Factor Profile** — equities only, scores as returned, the ranking date and "no score reflects price moves after that date", with the percentile reading for factor scores only. Funds are listed as unscored; ⚠ MISMATCH holdings are named with their re-derived scores marked `re-derived` on the V2 path, or `scores unavailable` on the V1 path; UNCHECKED holdings show their scores marked `identity unconfirmed`.
- **Ground-truth Integrity** (render only if any holding is ⚠ MISMATCH or UNCHECKED) — table: `input_ticker`, `returned_name`, `expected_name`, status (⚠ MISMATCH / UNCHECKED), per loader.md §5 rule 3. Write `unavailable` in any name column the tools did not return.
- **Review Questions** — two or three neutral questions.
- **Options to Discuss** — three or four, per Step 5.
- **Method and Data Notes** — static-weight illustration, no trading, before costs and taxes, not realized account results; who supplied the holdings and their as-of date when stated; benchmark symbol; remaps and exclusions; look-through coverage; data sources by tool name.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column; the audience mode line per conventions §13.4 when client-safe; expected spend.

Append audit log entry per loader.md §6.

Render AI-interaction disclosure per parallax-conventions.md §9.2 immediately above the disclaimer. If active view: end with the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from parallax-conventions.md §9.1.

## Failure modes

- Portfolio analysis fails or returns no performance block: stop; the report cannot state a window return. Name the failure and the lines sent. Never estimate a return in prose.
- A line has no usable prices: named above Contribution with its weight share; portfolio figures cover the remaining weight.
- The factor-table source (quick scores, or snapshots on the V2 path) fails or covers under half the equity weight: Factor Profile renders the §4 unavailable note; the rest of the report renders.
- Fund holdings unavailable for a fund line: its look-through row reads `Look-through unavailable`; the event exposure total is labeled incomplete.
- `get_company_info` fails or returns empty for a holding: that holding is UNCHECKED; its scores render with identity unconfirmed and it is listed in Ground-truth Integrity. Never treated as a pass.
- Ranking date unconfirmed: Factor Profile says so and still states that scores are weekly.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- The first line is the House View Preamble, the Branding Header or `## The Event`; every section of Output Format is present in order.
- Every supported line is in Contribution, and every excluded or remapped line is named; every scored holding passed the ground-truth check or is listed in Ground-truth Integrity as ⚠ MISMATCH or UNCHECKED.
- Portfolio figures carry the static-weight illustration label, and Factor Profile carries the ranking date.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- When a view is active: the `view_status` banner appears verbatim; audit entry appended per loader.md §6.
- The §9.2 disclosure and the §9.1 or view-aware disclaimer are present; expected spend stated in About This Report.
