---
name: parallax-macro-outlook
description: "Full macro regime analysis with optional equity screening: country coverage, economic outlook, regime signals, factor tilt implications, and top-scoring equities in the target market via Parallax MCP tools. Anchored on the regime question ('what is the regime in [market]?'). NOT for country/region equity discovery ('what should I buy in [country]?' — use /parallax-country-deep-dive), not for portfolio-level morning briefs (use /parallax-morning-brief), not for single stock analysis (use /parallax-deep-dive), not for thematic screening (use /parallax-thematic-screen), not for reacting to a specific event (use /parallax-scenario-analysis)."
---

<!-- white-label: integration-pattern.md -->

# Macro Outlook

## When not to use

- Country/region equity discovery ("what should I buy in [country]?") → use /parallax-country-deep-dive — that skill answers the allocation question with a view-tilted ranking; this skill answers the regime question, and its optional equity census is deliberately untilted
- Portfolio morning brief → use /parallax-morning-brief
- Single stock analysis → use /parallax-deep-dive or /parallax-should-i-buy
- Thematic screening across all markets → use /parallax-thematic-screen
- Reacting to a specific news event → use /parallax-scenario-analysis

## Gotchas

- Expected Parallax spend: ~46 tokens with `equities=true`, ~28 without (`_parallax/token-costs.md`); `check_macro_health` is 5 of that.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §0.2 (`macro_analyst` takes `market`; summary mode returns all components inline — never per-component calls), §2 identity cross-check, §3 parallel execution, §4 fallbacks, §13 audience mode, §14 host primitives.
- JIT-load `_parallax/house-view/loader.md` UNCONDITIONALLY: §5 rule 3 (ground-truth), rule 6 (AI disclosure) and §6 (audit) apply with or without a view. This skill answers the regime question, so neither §3 multipliers nor §7 apply: the macro narrative reflects live data and the optional equity census is **deliberately untilted** (tilted discovery is /parallax-country-deep-dive's job). Regime-alignment mode (this skill's own §7.4): when the view's stated regime conflicts with live `get_telemetry.regime_tag`, render `View regime: <X> | Live regime: <Y>` directly under the preamble; live wins for the narrative.
- Smaller/EM markets may have fewer scored equities — set expectations. ETFs are not in the scoring universe.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report, with the unconditional currency line).

Deep macro regime analysis with optional equity opportunity screening. Covers any of Parallax's 40+ global markets.

## Usage

```
/parallax-macro-outlook "United States"
/parallax-macro-outlook "Japan" equities=true
/parallax-macro-outlook "China" component=tactical
/parallax-macro-outlook — compare US, Europe, Japan
/parallax-macro-outlook "United States" audience=client_safe
```

Optional `audience=` argument: `client_safe | internal_analyst`; precedence follows `parallax-conventions.md` §13.1.

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Step 2, all batches) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: one or more markets; `equities=`; `component=`; `audience=`.
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture the load preamble and `view.macro_regime` (or a regime keyword from `basis_statement`: recessionary, expansion, stagflation, soft landing, hard landing, reflationary, disinflationary) for the Step 4 alignment check.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Market names must match `list_macro_countries` verbatim (conventions §0.2); a bellwether RIC per market for the score read (e.g. AAPL.O for United States, 7203.T for Japan).

### Step 2 — Fetch (parallel batches)

**Batch A** — `call-tool` together: `list_macro_countries`; `check_macro_health`; `get_telemetry` (fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences).

**Batch B** — after A: `macro_analyst(market=<country>)` in summary mode (all components inline); `get_score_analysis` for the bellwether. Repeat per market when comparing.

**Batch C** (only with `equities=true`) — `build_stock_universe(query="[country] equities")`; for the top 5, `get_peer_snapshot` AND `get_company_info` together; for the top 3, `get_score_analysis` with `weeks` as int 26 (conventions §0.2).

### Step 3 — Verify

- Coverage: a market absent from `list_macro_countries` is reported as not covered; no `macro_analyst` call for it.
- Freshness: `check_macro_health` result drives the Data Freshness section; stale data is stated, not hidden.
- Batch C identity per loader.md §5 rule 3 / conventions §2: `get_peer_snapshot.target_company` vs `get_company_info.name`; ⚠ MISMATCH rows recover per rule 3 or read "scores unavailable".

### Step 4 — Compute

No deterministic helper; the census stays untilted regardless of view state. Regime alignment (§7.4): compare the view's stated regime with `get_telemetry.regime_tag`; on a material divergence prepare the one-line note for the preamble; no regime statement in the view → skip.

### Step 5 — Compose

Fill **Output Format** below in order: House View Preamble per loader.md §5.1 with the §7.4 note as a sub-line; Branding Header per integration-pattern.md §5; audience mode per §13; §12 informational framing in Regime Implications; `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 rule 5 when a view is active, otherwise `parallax-conventions.md §9.1`; audit entry per loader.md §6.1 always (`applied=false`, `applied_reason: "no_view"` when none; `ground_truth_mismatches` per §6.2 when any).

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/macro.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill macro-outlook < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. Degraded-state notes go inside their section. If `run-shell` is absent, apply conventions §14.3 (render-gate row). No Step 7.

## Output Format

**Begin the response immediately with the rendered report — no preamble.** The first expected line is `## Regime Status`, or the House View Preamble / Branding Header when active.

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (banner from Pre-Workflow + low-confidence warnings). If §7.4 regime-alignment check produced a divergence note (Post-Workflow step 3), append it as a sub-line under the preamble. Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** macro outlook`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **Regime Status** (current regime tag, key signals, headline)
- **Plain-Language Summary** (under `audience=client_safe` only): 2-3 sentences restating the regime read in plain language for a non-specialist reader; factor names carry the §13.3 gloss, no cutoff arithmetic, framed per §12 as informational with no directives.
- **Macro Summary** (country-level economic overview)
- **Deep Dive** (macro indicators, fixed income, tactical components as requested)
- **Factor Regime Interaction** (which factors are favored/disfavored in this environment; under `audience=client_safe`, factor names carry the §13.3 gloss)
- **Regime Implications** (which factors and sectors the regime read favors/disfavors — informational per conventions §12)
- **Ground-truth Integrity** (only if equity screening included AND any mismatch detected — table: `input_ticker`, `returned_name`, `expected_name`, status, per loader.md §5 rule 3)
- **Top Equity Opportunities** (if equity screening included: table with symbol, name, sector, score, trend — names are the `get_company_info` names-of-record; ⚠ MISMATCH rows flagged inline; untilted by design). Universe caveat: rankings cover listed equities with Parallax factor coverage only — funds/OEICs are not screened.
- **Data Freshness** (when macro data was last updated)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line. Always append the §7 currency line: `Currency: figures as reported by source data; no base-currency conversion applied.` Under `audience=client_safe`, append the §13.4 mode line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- Market not covered: say so under Regime Status and stop the macro depth for that market; other markets still render.
- `check_macro_health` reports stale data: Data Freshness states the date; the analysis proceeds with the caveat.
- `get_telemetry` unavailable: Regime Status renders from `macro_analyst` only and says the regime tag was unavailable; the §7.4 check is skipped.
- Equity census unavailable or thin: Top Equity Opportunities states the coverage limit.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- First line is `## Regime Status` or the House View Preamble / Branding Header; every Output Format section rendered or marked unavailable with its reason.
- Data Freshness carries the `check_macro_health` date; the census (when requested) is untilted and every ⚠ MISMATCH row is marked.
- When a view is active: the `view_status` banner appears verbatim and the §7.4 line renders when regimes diverge.
- Audit entry appended per loader.md §6 (every run, including no-view).
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present; expected spend stated (Gotchas).
