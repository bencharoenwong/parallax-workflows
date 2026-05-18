---
name: parallax-macro-outlook
description: "Full macro regime analysis with optional equity screening: country coverage, economic outlook, regime signals, factor tilt implications, and top-scoring equities in the target market via Parallax MCP tools. NOT for portfolio-level morning briefs (use /parallax-morning-brief), not for single stock analysis (use /parallax-deep-dive)."
negative-triggers:
  - Portfolio morning brief → use /parallax-morning-brief
  - Single stock analysis → use /parallax-deep-dive or /parallax-should-i-buy
  - Thematic screening across all markets → use /parallax-thematic-screen
  - Reacting to a specific news event → use /parallax-scenario-analysis
gotchas:
  - list_macro_countries shows available coverage — check before querying a country
  - check_macro_health verifies data freshness — run first to avoid stale analysis
  - macro_analyst summary call returns all 9 components inline — do not make separate per-component calls
  - get_telemetry shows how macro regime affects the scoring engine
  - Smaller/EM markets may have fewer scored equities — set expectations
  - JIT-load `_parallax/house-view/loader.md` if an active CIO view is present. macro-outlook is a pure macro skill (no portfolio holdings, no single-stock anchor), so neither §3 multipliers nor §7 single-stock conflict-surfacing fit cleanly. Apply a **macro-regime-alignment mode** (defined inline below — call it §7.4 by analogy) — render a divergence note when the view's stated macro regime contradicts live `get_telemetry.regime`. No scoring math is altered. Standard surface: §2 (load + validate), §5 (preamble), §6 (audit log).
  - **§7.4 macro-regime-alignment mode (this skill's pattern, not in loader.md):** if the active view's basis_statement or stated macro regime (e.g., "recessionary", "expansion", "stagflation", from `view.macro_regime` if present) materially conflicts with the regime returned by `get_telemetry.regime`, render a "View regime: <X> | Live regime: <Y>" line directly under the House View Preamble at the very top of Output Format. The user is informed of the disagreement; the analytical content still reflects live data (live wins for macro narrative). If no view, or view is silent on macro regime, omit the line.
  - When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer.
  - JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (6-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (Provenance) in Output Format.
---

<!-- white-label: integration-pattern.md -->

# Macro Outlook

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

Per `_parallax/house-view/loader.md` §1 and §2: load and validate any active house view BEFORE running the workflow. If view present, capture the load preamble for rendering at the top of Output Format per §5.1, and capture `view.macro_regime` (or equivalent regime statement from basis_statement) — applied in Post-Workflow §7.4 regime-alignment check. If no active view (or validation failure): run the workflow normally with the standard disclaimer.

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

If requested: call `build_stock_universe` with "[country] equities". For top 5: `get_peer_snapshot` (parallel). For top 3: `get_score_analysis` 26 weeks (parallel).

### Post-Workflow — §7.4 Regime alignment check

If a view was loaded in Pre-Workflow:

1. Extract view's stated macro regime: prefer `view.macro_regime` if present; otherwise scan `basis_statement` for regime keywords ("recessionary", "expansion", "stagflation", "soft landing", "hard landing", "reflationary", "disinflationary"). If no regime statement can be extracted, skip the alignment check (regime alignment is opt-in based on view content).
2. Compare to `get_telemetry.regime_tag` returned in Batch A.
3. If regimes materially diverge (e.g., view says "recessionary" but live says "expansion"), prepare a one-line divergence note for Output Format rendering: `View regime: <view_regime> | Live regime: <live_regime> — note the disagreement; analytical content below reflects live data per loader.md §4 (data sovereignty).`
4. Append the §6 audit log entry per loader.md §6.1.

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
- **Top Equity Opportunities** (if equity screening included: table with symbol, name, sector, score, trend)
- **Data Freshness** (when macro data was last updated)
- **Provenance** (always present): one line stating branding state per integration-pattern.md §7 markdown column (5 error states; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second Provenance line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise:

> *"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*
