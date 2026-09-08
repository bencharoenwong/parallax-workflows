---
name: parallax-thematic-screen
description: "Thematic stock screen and idea analysis: build a stock universe from a theme, score top picks, layer optional macro context and regime signals, compare peers, and check financials via Parallax MCP tools. Triggers: 'screen for [theme]', 'trade ideas around X', 'thematic ideas for Y', 'stocks in Z theme', 'new ideas in [sector]'. NOT for single stock analysis (use /parallax-should-i-buy), not for portfolio review (use /parallax-client-review), not for a country or region screen (use /parallax-country-deep-dive), not for allocation-ready construction (use /parallax-portfolio-builder)."
---

<!-- white-label: integration-pattern.md -->

# Thematic Screen

## When not to use

- Single stock analysis → use /parallax-should-i-buy
- Portfolio review → use /parallax-client-review
- Peer comparison of known stock → use /parallax-peer-comparison
- Country or region equity screen → use /parallax-country-deep-dive
- Allocation-ready portfolio from a thesis → use /parallax-portfolio-builder
- Regime-first or reflexivity-driven trade ideas (e.g., "trade ideas in current rates regime") → use /parallax-ai-soros

## Gotchas

- Expected Parallax spend: ~19 tokens default, ~14 with `--no-macro` (`_parallax/token-costs.md`).
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
```

Optional: `top_n=` (default 5), `--no-macro`, `--skip-drift-check`, `audience=client_safe | internal_analyst` (precedence per conventions §13.1).

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Step 2, all batches) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: theme; `top_n=`; `--no-macro`; `--skip-drift-check`; `audience=`.
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture tilt vector + excludes and resolve the theme against it per §4 (theme sovereign; conflict banner, e.g. theme "AI infrastructure" with `tech: -2` → "House view is UW tech; screen run per your explicit theme"). Then the drift pre-flight: `load-reference` `_parallax/house-view/auto-on-load-judge-pattern.md` and follow it; a surfaced banner renders before the report. Skip this pre-flight if invoked with `--skip-drift-check` or if no active house view exists.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Apply the macro-self-confirming test to the theme (Gotchas). Infer up to 3 relevant markets from the theme for Batch A step 3b (geo-agnostic themes → United States plus one other relevant covered market).

### Step 2 — Fetch (parallel batches)

**Batch A — setup.** `call-tool` steps 1, 2 and 3a together; 3b fires when 3a returns:
1. **Universe** — with a view and `PARALLAX_LOADER_V2=1`, follow loader.md §3 "Application (V2)": parallel per-sector calls, merge, dedupe; V1: prepend tilt context and call `build_stock_universe` once. Filter against `tilts.excludes`. **Timeout:** retry once with a narrower query; then `universe = []`, `universe_status = "unavailable"`, continue and flag it under Universe Built; never call `check_portfolio_redundancy` as a placeholder.
2. **Telemetry** — `get_telemetry` (basket-level; failure → `telemetry = None`).
3. **Macro** (skip with `--no-macro`) — 3a `list_macro_countries`; 3b `macro_analyst(market=<m>, component="tactical")` per inferred market whose name matches the 3a list verbatim ("United States", not "US"); unmatched inferences are dropped silently; none left, or all unavailable → `macro_context = None`. Cap 3.

**Batch B — scoring (C1).** For the top N candidates, `call-tool` `get_peer_snapshot` AND `get_company_info` per candidate together. Record `returned_name` (`target_company`) and `expected_name` (`name`).

**Batch C — after Step 4 establishes rank, in one turn:** **C2** `export_peer_comparison` (`format="json"`) for the highest-scored TRUSTED row; **C3** `get_financials` (`statement="summary"`) for the top 3 trusted picks. C1.5 annotation runs concurrently with these and never gates them.

### Step 3 — Verify

- **Divergence assertion** (loader.md §5 rule 4, universal): if the query named N ≥ 2 sectors/themes and `max_sector_share / total > 0.6`, warn "universe collapsed to single sector despite multi-sector request" (V2: use it to verify merge quality).
- **Freeform excludes** — with a view and non-empty `tilts.excludes_freeform`, drop candidates matching any pattern against `get_company_info` name/description/sector (loader.md §3).
- **Ground-truth check** (loader.md §5 rule 3, universal): any row where `returned_name ≠ expected_name` after normalization per conventions §2 step 2 is UNTRUSTED — ⚠ MISMATCH, not ranked.

### Step 4 — Compute

**C1 rank:** composite-driven; with a view, re-rank trusted rows by `composite × multiplier(sector)` per loader.md §3.

**C1.5 — Annotation (Phase C1.5; reference implementation of conventions §3.1, concurrent with C2/C3):** if `macro_context` is present, tag each trusted row `macro_tag ∈ {with-regime, against-regime, orthogonal}` from the row's primary market — read `get_company_info.country`, normalize to the canonical market name from `list_macro_countries`; missing or unmatched → `orthogonal`, never inferred from sector or judgement. Tags annotate the Output Format only: **they MUST NOT change rank order, alter membership, or override the composite score**, and downstream consumers must preserve every annotated row (Macro Tag is never a filter predicate).

### Step 5 — Compose

Fill **Output Format** below in order: House View Preamble per loader.md §5.1; Branding Header per integration-pattern.md §5; theme conflict and macro-self-confirming banners inline; audience mode per §13 (Plain-Language Summary under `client_safe`; §13.3 gloss); `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 rule 5 when a view is active, otherwise `parallax-conventions.md §9.1`; audit entry per loader.md §6 (every consume event).

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/thematic.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill thematic-screen < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. Degraded-state notes go inside their section. If `run-shell` is absent, apply conventions §14.3 (render-gate row). No Step 7.

## Output Format

**Begin the response immediately with the rendered report — no preamble.** The first expected line is `## Theme: <theme>`, or the House View Preamble / Branding Header when active.

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** thematic screen`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **Theme: [theme]** (brief investment thesis; note view conflict inline if applicable; if theme string is itself a macro-condition phrase, render the macro-self-confirming banner per gotchas and suggest `/parallax-macro-outlook`)
- **Macro Context** (rendered if `macro_context` OR `telemetry` is present from Phase A) — one line per covered market (max 3) from macro_analyst: `<market>: <tactical takeaway from macro_analyst>`. State explicitly whether this is supplementary (house view active, view is sovereign) or primary (no view active). If `telemetry` is present, append a "Regime Signal" sub-line: `<regime_tag> | top divergence baskets: <basket names with sign, max 3> | <commentary.headline>`. Do NOT extend beyond what the tools returned — no LLM-confabulated narrative bridging the macro view to the theme.
- **Plain-Language Summary** (under `audience=client_safe` only): 2-3 sentences describing the theme read and top-pick rationale for a non-specialist reader; factor names carry the §13.3 gloss, no cutoff arithmetic, framed per §12 as informational with no directives.
- **Universe Built** (how many stocks found, key sectors; note any exclusions applied; surface divergence-assertion result per loader.md §5 rule 4)
- **Top Picks** (table: `input_ticker`, `returned_name` (from scoring tool), `expected_name` (from get_company_info), sector, overall score, key factor strengths; under `audience=client_safe`, factor-strength cells carry the §13.3 gloss; if view active, add "Tilt Effect" column; if `macro_context` present, add "Macro Tag" column showing `with-regime / against-regime / orthogonal`. **Flag any row where `returned_name ≠ expected_name` after normalizing both per conventions §2 step 2 with ⚠ MISMATCH and exclude its scores from ranking** — per loader.md §5 rule 3. **Rank is composite-driven regardless of Macro Tag** — that column annotates, not sorts. Do NOT add a per-name Confidence column — telemetry is basket-level only and any per-row confidence would be hallucinated.)
- **Comparison Matrix** (peer comparison for lead candidate)
- **Financial Snapshot** (revenue, margins, growth for top 3 trusted picks)
- **Implementation Notes** (liquidity considerations, concentration/threshold arithmetic per conventions §12 — no position-sizing instructions; concentration/threshold arithmetic renders in internal_analyst mode only per §13.2)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- Universe unavailable after the retry: Universe Built states it; no Top Picks table; audit row notes the abort.
- Universe collapsed to one sector: the divergence warning renders; the screen still runs on what returned.
- Macro or telemetry unavailable: Macro Context degrades or is omitted per the rules above; the screen never aborts on either.
- ⚠ MISMATCH rows: kept in the table, unranked, scores excluded.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive (drift check: the judge pattern's skipped line).

## Done when

- First line is `## Theme: <theme>` or the House View Preamble / Branding Header; every Output Format section rendered or marked unavailable with its reason.
- Top Picks rank is composite-driven; the Macro Tag column (when present) changed no order and no membership; ⚠ MISMATCH rows are marked.
- The divergence-assertion result appears under Universe Built.
- When a view is active: the `view_status` banner appears verbatim; audit entry appended per loader.md §6 (every consume event).
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present; expected spend stated (Gotchas).
