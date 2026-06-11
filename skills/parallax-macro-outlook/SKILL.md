---
name: parallax-macro-outlook
description: "Full macro regime analysis with optional equity screening: country coverage, economic outlook, regime signals, factor tilt implications, and top-scoring equities in the target market via Parallax MCP tools. Anchored on the regime question ('what is the regime in [market]?'). NOT for country/region equity discovery ('what should I buy in [country]?' — use /parallax-country-deep-dive), not for portfolio-level morning briefs (use /parallax-morning-brief), not for single stock analysis (use /parallax-deep-dive)."
---

<!-- white-label: integration-pattern.md -->

# Macro Outlook

## When not to use

- Country/region equity discovery ("what should I buy in [country]?") → use /parallax-country-deep-dive — that skill answers the allocation question with a view-tilted ranking; this skill answers the regime question, and its optional equity census is deliberately untilted
- Portfolio morning brief → use /parallax-morning-brief
- Single stock analysis → use /parallax-deep-dive or /parallax-should-i-buy
- Thematic screening across all markets → use /parallax-thematic-screen
- Reacting to a specific news event → use /parallax-scenario-analysis
- Regime-driven directional trade ideas for a specific ticker → use /parallax-ai-soros

## Gotchas

- list_macro_countries shows available coverage — check before querying a country
- check_macro_health verifies data freshness — run first to avoid stale analysis
- macro_analyst summary call returns all 9 components inline — do not make separate per-component calls
- get_telemetry shows how macro regime affects the scoring engine
- Smaller/EM markets may have fewer scored equities — set expectations
- JIT-load `_parallax/house-view/loader.md` UNCONDITIONALLY — §5 rule 3 (ground-truth check), rule 6 (AI disclosure), and §6 (audit log) apply whether or not a view is active. macro-outlook answers the regime question, so neither §3 multipliers nor §7 single-stock conflict-surfacing apply: the macro narrative reflects live data, and the optional Batch C equity census is **deliberately untilted** — it is an illustrative exhibit of which equities score well in this regime, not a discovery ranking. A user who wants the view-tilted "what should I buy in [country]" ranking belongs in /parallax-country-deep-dive (that skill applies §3 to its Top Opportunities by design). Apply a **macro-regime-alignment mode** (defined inline below — call it §7.4 by analogy) — render a divergence note when the view's stated macro regime contradicts live `get_telemetry.regime_tag`. No scoring math is altered. Standard surface: §2 (load + validate), §5 (preamble), §6 (audit log).
- **§7.4 macro-regime-alignment mode (this skill's pattern, not in loader.md):** if the active view's basis_statement or stated macro regime (e.g., "recessionary", "expansion", "stagflation", from `view.macro_regime` if present) materially conflicts with the regime returned by `get_telemetry.regime_tag`, render a "View regime: <X> | Live regime: <Y>" line directly under the House View Preamble at the very top of Output Format. The user is informed of the disagreement; the analytical content still reflects live data (live wins for macro narrative). If no view, or view is silent on macro regime, omit the line.
- When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer.
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (6-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (Provenance) in Output Format.

Deep macro regime analysis with optional equity opportunity screening. Covers any of Parallax's 40+ global markets.

## Usage

```
/parallax-macro-outlook "United States"
/parallax-macro-outlook "Japan" equities=true
/parallax-macro-outlook "China" component=tactical
/parallax-macro-outlook — compare US, Europe, Japan
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns.

### Pre-Workflow — Load Active House View

Per `_parallax/house-view/loader.md` §1 and §2: load and validate any active house view BEFORE running the workflow. If view present, capture the load preamble for rendering at the top of Output Format per §5.1, and capture `view.macro_regime` (or equivalent regime statement from basis_statement) — applied in Post-Workflow §7.4 regime-alignment check. If no active view (or validation failure): run the workflow normally with the standard disclaimer. Loader.md §5 rule 3 (ground-truth check), rule 6 (AI disclosure), and §6 (audit) still apply on the no-view path.

### Batch 0 — Tool Loading

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

### Batch A — Coverage + regime (parallel)

| Tool | Parameters | Notes |
|---|---|---|
| `list_macro_countries` | — | Confirm markets |
| `check_macro_health` | — | Data freshness |
| `get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Market regime |

### Batch B — Macro depth (after Batch A)

1. Call `macro_analyst` for the target country (summary — no component parameter). The summary call returns all 9 components inline (macro_indicators, tactical, fixed_income, currency, sectors, sector_positioning, liquidity, news, factors). Do not make separate per-component calls.
2. Call `get_score_analysis` for a market bellwether stock (e.g., AAPL.O for US, 7203.T for Japan). ETFs are not in the scoring universe.
3. If multiple countries: repeat for each and compare.

### Batch C — Equity opportunities (optional, after Batch B)

If requested: call `build_stock_universe` with `query="[country] equities"`. For top 5: `get_peer_snapshot` AND `get_company_info` per symbol (all parallel — `get_company_info` is the ground-truth oracle per loader.md §5 rule 3, required view or no view whenever per-holding scores render). Cross-check each `get_peer_snapshot.target_company` against the name-of-record; on mismatch, flag ⚠ MISMATCH and recover per rule 3. For top 3: `get_score_analysis` 26 weeks (parallel). The census stays untilted regardless of view state (see Gotchas — tilted discovery is /parallax-country-deep-dive's job).

### Post-Workflow — §7.4 Regime alignment check + §6 audit

If a view was loaded in Pre-Workflow:

1. Extract view's stated macro regime: prefer `view.macro_regime` if present; otherwise scan `basis_statement` for regime keywords ("recessionary", "expansion", "stagflation", "soft landing", "hard landing", "reflationary", "disinflationary"). If no regime statement can be extracted, skip the alignment check (regime alignment is opt-in based on view content).
2. Compare to `get_telemetry.regime_tag` returned in Batch A.
3. If regimes materially diverge (e.g., view says "recessionary" but live says "expansion"), prepare a one-line divergence note for Output Format rendering: `View regime: <view_regime> | Live regime: <live_regime> — note the disagreement; analytical content below reflects live data.`

**Always** append the §6 audit log entry per loader.md §6.1 — view or no view (`applied=false` with `applied_reason: "no_view"` when none, `view_id`/`version_id` null per §6.1; include `ground_truth_mismatches` per §6.2 when any Batch C row was flagged).

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (Provenance) when composing the Output Format. The loader returns exactly six keys; any other access (e.g. `branding["voice"]`) raises `KeyError` — structurally enforced by `loader.py`.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (banner from Pre-Workflow + low-confidence warnings). If §7.4 regime-alignment check produced a divergence note (Post-Workflow step 3), append it as a sub-line under the preamble. Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** macro outlook`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to Provenance.
- **Regime Status** (current regime tag, key signals, headline)
- **Macro Summary** (country-level economic overview)
- **Deep Dive** (macro indicators, fixed income, tactical components as requested)
- **Factor Regime Interaction** (which factors are favored/disfavored in this environment)
- **Positioning Implications** (what this means for portfolio construction)
- **Ground-truth Integrity** (only if equity screening included AND any mismatch detected — table: `input_ticker`, `returned_name`, `expected_name`, status, per loader.md §5 rule 3)
- **Top Equity Opportunities** (if equity screening included: table with symbol, name, sector, score, trend — names are the `get_company_info` names-of-record; ⚠ MISMATCH rows flagged inline; untilted by design)
- **Data Freshness** (when macro data was last updated)
- **Provenance** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second Provenance line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.
