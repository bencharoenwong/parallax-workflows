---
name: parallax-thematic-screen
description: "Thematic stock screen and idea analysis: build a stock universe from a theme, score top picks, layer optional macro context and regime signals, compare peers, and check financials via Parallax MCP tools. Triggers: 'screen for [theme]', 'trade ideas around X', 'thematic ideas for Y', 'stocks in Z theme', 'new ideas in [sector]', 'which stocks does this theme work against', 'names this thesis hurts'. NOT for single stock analysis (use /parallax-should-i-buy), not for portfolio review (use /parallax-client-review), not for a country or region screen (use /parallax-country-deep-dive), not for allocation-ready construction (use /parallax-portfolio-builder)."
---

<!-- white-label: integration-pattern.md -->

# Thematic Screen

## When not to use

- Single stock analysis → use /parallax-should-i-buy
- Portfolio review → use /parallax-client-review
- Peer comparison of known stock → use /parallax-peer-comparison
- Country or region equity screen → use /parallax-country-deep-dive
- Allocation-ready portfolio from a thesis → use /parallax-portfolio-builder

## Gotchas

- Expected Parallax spend (`_parallax/token-costs.md`): `5U + 0.15N + 0.05F + 0.05 + 0.1X + 5M` credits for U universe jobs, N candidate snapshot/identity pairs, F summary financial reads (≤3), telemetry, X peer exports (0 or 1) and M tactical markets (0–3). With U=1, N=5, F=3, X=1: **11.05 credits at one market, 16.05 at two, 21.05 at three, 6.05 with `--no-macro`**; country discovery is free. Each extra candidate adds 0.15; above three trusted picks the financial-read count stays capped. `--against` adds one universe job and one snapshot/identity pair per top-N against-name not already in the main top N: at most +5 + 0.15N (**16.8 credits at one market** with the defaults, less when the two universes overlap). V2 per-sector universe calls cost 5 each; add the conditional Step 0 drift-check cost separately. Failed/pending paths only incur their successful reads/jobs.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §0.2 (`macro_analyst` needs the exact market name from `list_macro_countries`), §1 RIC resolution, §2 identity cross-check, §3/§3.1 parallel execution and the Concurrent Annotation Pattern (this skill is its reference implementation), §4 fallbacks, §13 audience mode, §14 host primitives.
- JIT-load `_parallax/house-view/loader.md` FIRST. §5 rules 3 (ground-truth check) and 4 (divergence assertion) apply universally; rules 1–2 and 5 when a view is active. The user's theme is sovereign per §4 — conflicts render as banners, never as silent re-ranking. Drift check per `_parallax/house-view/auto-on-load-judge-pattern.md` (this skill builds a candidate set).
- Macro context is a SOFT annotation: with a view, tilts stay sovereign; without one, macro may drive emphasis in the Output Format only. Rank is always composite-driven.
- Macro-self-confirming theme banner (deterministic, case-insensitive): the theme contains any of `rates`, `inflation`, `recession`, `tariff`, `tariffs`, `yield curve`, `currency`, `USD`, `dollar`, `credit spread`, `GDP`, `monetary policy`, `fiscal`, `Fed`, `central bank`, `regime`, `cycle` AND no sector/industry word (`tech`, `energy`, `healthcare`, `financials`, `industrials`, `materials`, `utilities`, `staples`, `discretionary`, `REIT`, `biotech`, `software`, …) → render the banner suggesting /parallax-macro-outlook, then proceed.
- `get_telemetry` is BASKET-level (`regime_tag`, `divergences[]`, `commentary.headline`): render only those three in Macro Context; never tag individual Top Picks with a confidence derived from it; never propagate raw framework-component names or factor-decomposition values it may expose. "Admin org not configured" or any failure → `telemetry = None`, no Regime Signal sub-line, never abort.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).
- Output consumption contract: downstream consumers parse Output Format by section header name, never by position.

Discover investment opportunities by theme using Parallax's semantic universe builder.

## Usage

```
/parallax-thematic-screen "AI infrastructure companies"
/parallax-thematic-screen "trade ideas around energy transition"
/parallax-thematic-screen "thematic ideas for onshoring beneficiaries" top_n=10
/parallax-thematic-screen "clean energy utilities" --no-macro
/parallax-thematic-screen "gene therapy pure plays"
/parallax-thematic-screen "AI infrastructure companies" audience=client_safe
/parallax-thematic-screen "AI infrastructure companies" --against
```

Optional: `top_n=` (default 5), `--no-macro`, `--skip-drift-check`, `--against` (also list names the thesis works against), `audience=client_safe | internal_analyst` (precedence per conventions §13.1).

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Step 2, all batches) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: nonempty theme (query 2–500 characters); `top_n=` integer 1–20 (default 5); `--no-macro`; `--skip-drift-check`; `--against`; `audience=`. Reject invalid count/query before calls.
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture tilt vector + excludes and resolve the theme against it per §4 (theme sovereign; conflict banner, e.g. theme "AI infrastructure" with `tech: -2` → "House view is UW tech; screen run per your explicit theme"). Then the drift pre-flight: `load-reference` `_parallax/house-view/auto-on-load-judge-pattern.md` and follow it; a surfaced banner renders before the report. Skip this pre-flight if invoked with `--skip-drift-check` or if no active house view exists.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Apply the macro-self-confirming test to the theme (Gotchas). Record `user_markets`: the single countries or markets the request names explicitly, up to 3. A country or market named inside the theme string counts as named ("India infrastructure" → India; "Japanese robotics" → Japan). A region, bloc or aggregate (Europe, ASEAN, Latin America, Asia, emerging markets, Global, worldwide) is not a market, even when it matches a 3a entry: leave it out of `user_markets` and never list it as not covered. Do not guess markets the request does not name, such as a geography a sector implies (semiconductors → Taiwan); step 3b derives them from the universe when `user_markets` is empty.

**Thesis tests and universe query.** `build_stock_universe` ranks names by how well their descriptions match the query text; it does not test the thesis. Before Batch A:
1. Write 2–4 tests the thesis must pass. Each test is about the companies' business (revenue source, input, customer, cost exposure), never about this run's output. State each so that data could prove it false.
2. Write one line: what would disprove this thesis.
3. Set `universe_query`. Rewrite the theme when its main noun is an umbrella word: `infrastructure`, `ecosystem`, `economy`, `beneficiaries`, `winners`, `plays`, `names`, `companies`, `stocks`, `ideas`, `exposure`, `transition`, `revolution`, `boom`, `theme`, or a sector name alone. To rewrite, name the 2–4 specific products, inputs or revenue sources the tests depend on (e.g. "AI infrastructure companies" → "data center GPU accelerators, high-bandwidth memory, data center networking"). If the main noun is not on that list, send the theme exactly as the user typed it and set `query_verbatim = true`. Do not add synonyms, adjacent products or wider wording. Keep every constraint the user stated (market, size, sector). Never add a constraint the user did not state.

4. With `--against`, unless the resolved audience mode (conventions §13.1) is `client_safe`: set `against_query`, a plain description of the products or revenue sources the thesis damages (e.g. "legacy on-premise server and storage hardware"). Describe what those companies sell. Never phrase it as a negation ("companies hurt by X"); the universe builder matches descriptions, so a negated query returns noise.

`universe_query` is the base query for Batch A step 1. The theme phrase stays the user's verbatim words everywhere it renders.

### Step 2 — Fetch (parallel batches)

**Batch A — setup.** `call-tool` steps 1, 2 and 3a together; with non-empty `user_markets`, 3b fires when 3a returns, otherwise in the Batch C turn:
1. **Universe** — start from `universe_query` (Step 1). With a view and `PARALLAX_LOADER_V2=1`, follow loader.md §3 "Application (V2)": parallel per-sector calls built from `universe_query`, merge, dedupe; V1: prepend tilt context to `universe_query` and call `build_stock_universe` once. Record every query string sent. Filter against `tilts.excludes`. **Failure/timeout/pending:** retain any job identifier/status; do not launch a replacement universe job or silently narrow the theme. Set `universe = []`, `universe_status = "pending"` (or the specific failure), continue and disclose it under Universe Built. A replacement with changed scope needs an explicit new user request; never call `check_portfolio_redundancy` as a placeholder.
1b. **Against universe** (only when `against_query` is set) — `build_stock_universe(query=against_query)` in the same turn as step 1. No tilt context, no V2 split. Failure/pending → `against_universe = []` with its status; disclose it in the section; never retry with a changed query.
2. **Telemetry** — `get_telemetry` (basket-level; failure → `telemetry = None`).
3. **Macro** (skip with `--no-macro`) — 3a `list_macro_countries`; 3b `macro_analyst(market=<m>, component="tactical")` per selected market whose name matches the 3a list verbatim ("United States", not "US"). Normalize every candidate market name to its 3a name first ("US" → "United States"). Select markets this way: when `user_markets` is present, query every normalized user-named market, up to 3, with no candidate-count filter. Otherwise use the universe-derived path: count `get_company_info.data.market` across the trusted main top-N candidates only; against-names never count. On the universe-derived path, select every market that holds at least 2 of those candidates, most frequent first, up to 3 (ties → the market of the higher-ranked main candidate first). On the universe-derived path, if no market holds 2, select only the single most frequent market, with the same tie rule. A user-named market with no 3a match goes in `uncovered_markets` and is disclosed as not covered; an unmatched universe-derived market is dropped silently. None left, or all unavailable → `macro_context = None`. Cap 3.

**Batch B — scoring (C1).** For the top N candidates, `call-tool` `get_peer_snapshot` AND `get_company_info` per candidate together. Record `returned_name` (`target_company`) and `expected_name` (`get_company_info.data.name` — nested under the response's `data` object, not a top-level field). When `against_universe` is non-empty, run the same pair in the same turn for each of its top N names not already in the main top N; an against-name already in the main top N reuses that name's main C1 result. Against-names get no C2 or C3 calls.

**Batch C — after Step 4 establishes rank, in one turn:** **C2** `export_peer_comparison` (`format="json"`) for the highest-scored TRUSTED row; **C3** `get_financials` (`statement="summary"`) for the top 3 trusted picks; **3b** macro for the universe-derived markets when `user_markets` is empty (Batch A step 3). Issue 3b, C2 and C3 together; C1.5 starts once rank is set and 3b has returned, and never gates C2 or C3.

### Step 3 — Verify

- **Divergence assertion** (loader.md §5 rule 4, universal): if the user's theme or the house-view tilts named N ≥ 2 sectors/themes and `max_sector_share / total > 0.6`, warn "universe collapsed to single sector despite multi-sector request" (V2: use it to verify merge quality). Count N from the user's theme and the tilts only; the products a Step 1 rewrite lists in `universe_query` never count, so a single-theme request rewritten into 2–4 products gets no warning.
- **Freeform excludes** — with a view and non-empty `tilts.excludes_freeform`, drop candidates matching any pattern against `get_company_info.data.name`/`.data.description`/`.data.sector` (loader.md §3).
- **Ground-truth check** (loader.md §5 rule 3, universal): any row where `returned_name ≠ expected_name` after normalization per conventions §2 step 2 is UNTRUSTED — ⚠ MISMATCH, not ranked. Apply the same check to against-names.

### Step 4 — Compute

**C1 rank:** composite-driven; with a view, re-rank trusted rows by `composite × multiplier(sector)` per loader.md §3.

**C1.5 — Annotation (Phase C1.5; reference implementation of conventions §3.1; starts once rank is set and 3b has returned; never gates C2/C3):** if `macro_context` is present, tag each trusted row `macro_tag ∈ {with-regime, against-regime, orthogonal, not-assessed}` from the row's primary market — read `get_company_info.data.market` (there is no `country` field anywhere in the response; every identity field, including `market`, lives under `data` — only `success`, `symbol`, and `score_scale` are top-level), normalize to the canonical market name from `list_macro_countries`; missing or unmatched → `not-assessed`, with the missing-evidence reason; a market outside the 3b selection → `not-assessed`, reason `market not queried`; never infer regime alignment from sector or judgement. Use `orthogonal` only when assessed evidence supports no material relationship. Tags annotate the Output Format only: **they MUST NOT change rank order, alter membership, or override the composite score**, and downstream consumers must preserve every annotated row (Macro Tag is never a filter predicate).

### Step 5 — Compose

Fill **Output Format** below in order: House View Preamble per loader.md §5.1; Branding Header per integration-pattern.md §5; theme conflict and macro-self-confirming banners inline; audience mode per §13 (Plain-Language Summary under `client_safe`; §13.3 gloss); `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 rule 5 when a view is active, otherwise `parallax-conventions.md §9.1`; audit entry per loader.md §6 (every consume event).

### Step 6 — Render (deterministic gate, mandatory)

`write-artifact` the complete drafted report to a new `<draft-path>`, then `run-shell` the shared gate with this skill's key, both per conventions §10.3:

```
python3 "<skill-dir>/../_parallax/render_gate.py" --skill thematic-screen --input "<draft-path>"
```

Write the draft once and never modify it in place, not even to fix one word. If the report needs a change after the draft is written, run the command above on that draft unchanged (ignore that output), then write the corrected report to a fresh path and run the command on it (conventions §10.3).

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. Degraded-state notes go inside their section. If `run-shell` is absent, apply conventions §14.3 (render-gate row). No Step 7.

## Output Format

**Begin the response immediately with the rendered report — no preamble.** The first expected line is `## Theme: <theme>`, or the House View Preamble / Branding Header when active.

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** thematic screen`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **Theme: [theme]** (theme in the user's verbatim words; brief investment thesis; the Step 1 tests as a short list; one line `What would disprove this thesis: <line>`; note view conflict inline if applicable; if theme string is itself a macro-condition phrase, render the macro-self-confirming banner per gotchas and suggest `/parallax-macro-outlook`)
- **Macro Context** (rendered if `macro_context` from step 3b, `telemetry` from Batch A, or `uncovered_markets` is present) — one line per covered market (max 3) from macro_analyst: `<market>: <tactical takeaway from macro_analyst>`, then one line per entry in `uncovered_markets`: `<market as named>: not covered`. State explicitly whether this is supplementary (house view active, view is sovereign) or primary (no view active). If `telemetry` is present, append a "Regime Signal" sub-line: `<regime_tag> | top divergence baskets: <basket names with sign, max 3> | <commentary.headline>`. Do NOT extend beyond what the tools returned — no LLM-confabulated narrative bridging the macro view to the theme.
- **Plain-Language Summary** (under `audience=client_safe` only): 2-3 sentences describing the theme read and top-pick rationale for a non-specialist reader; factor names carry the §13.3 gloss, no cutoff arithmetic, framed per §12 as informational with no directives.
- **Universe Built** (first line `Query sent: "<query>"`, one per query under V2, marked `(theme used verbatim)` when `query_verbatim` is true; how many stocks found, key sectors; note any exclusions applied; surface divergence-assertion result per loader.md §5 rule 4; when `universe_status` is success, one line `Widely held name not in Top Picks: <name> — <reason>`. The name is one widely held name associated with the theme, chosen by the model. The reason must be one this run's tool output supports: not returned by the universe; or returned at relevance rank k, outside the scored top N. Never give any other reason, and never frame the line as an omission to act on. When every widely held name associated with the theme is already in Top Picks, the line reads `Widely held name not in Top Picks: none — every widely held name for this theme is in Top Picks`; never name a marginal company to fill the line. When the universe failed or is pending, omit this line)
- **Top Picks** (table: `input_ticker`, `returned_name` (from scoring tool), `expected_name` (from get_company_info), sector, overall score, key factor strengths; under `audience=client_safe`, factor-strength cells carry the §13.3 gloss; if view active, add "Tilt Effect" column; if `macro_context` present, add "Macro Tag" column showing `with-regime / against-regime / orthogonal / not-assessed`. **Flag any row where `returned_name ≠ expected_name` after normalizing both per conventions §2 step 2 with ⚠ MISMATCH and exclude its scores from ranking** — per loader.md §5 rule 3. **Rank is composite-driven regardless of Macro Tag** — that column annotates, not sorts. Do NOT add a per-name Confidence column — telemetry is basket-level only and any per-row confidence would be hallucinated.)
- **Thesis Works Against** (only with `--against`; omitted when the resolved audience mode per conventions §13.1 is `client_safe`) — first line `Query sent (against): "<against_query>"`; the informational preface per `parallax-conventions.md` §12; a table of the scored against-names in universe relevance order with columns `input_ticker`, `returned_name`, `expected_name`, sector, overall score, key factor strengths. No rank column; scores are shown, never ranked. ⚠ MISMATCH rows flagged as in Top Picks. Mark a row `(also in Top Picks)` when that name also appears in Top Picks. Below the table, state that membership comes from description match to the against query and does not show that the thesis damages a company's revenue; name any listed company whose `get_company_info.data.description` also describes products the thesis favors. Close with one line: to test a long/short pair from this list, run `/parallax-pair-finder`. If the against universe failed or returned nothing, the section states that and shows no table.
- **Comparison Matrix** (peer comparison for lead candidate)
- **Financial Snapshot** (revenue, margins, growth for top 3 trusted picks)
- **Implementation Notes** (liquidity considerations, concentration/threshold arithmetic per conventions §12 — no position-sizing instructions; concentration/threshold arithmetic renders in internal_analyst mode only per §13.2)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- Universe unavailable or pending after its one job: Universe Built states it; no Top Picks table; audit row notes the abort.
- Universe collapsed to one sector: the divergence warning renders; the screen still runs on what returned.
- Macro or telemetry unavailable: Macro Context degrades or is omitted per the rules above; the screen never aborts on either.
- ⚠ MISMATCH rows: kept in the table, unranked, scores excluded.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive (drift check: the judge pattern's skipped line).

## Done when

- First line is `## Theme: <theme>` or the House View Preamble / Branding Header; every Output Format section rendered or marked unavailable with its reason.
- Top Picks rank is composite-driven; the Macro Tag column (when present) changed no order and no membership; ⚠ MISMATCH rows are marked.
- The divergence-assertion result appears under Universe Built.
- Theme carries the thesis tests and the disprove line; Universe Built opens with every query sent and, when the universe returned, carries the widely-held-name line (a named widely held name with an allowed reason, or the `none` form).
- With `--against` (resolved audience mode not `client_safe`): Thesis Works Against follows Top Picks, opens with its query line and the §12 preface, and has no rank column; Top Picks is unchanged by it.
- When a view is active: the `view_status` banner appears verbatim; audit entry appended per loader.md §6 (every consume event).
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present; expected spend stated (Gotchas).
