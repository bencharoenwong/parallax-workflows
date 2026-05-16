---
name: parallax-country-deep-dive
description: "Country or region deep dive: macro environment, available equity coverage, top-scoring stocks, and investment opportunities via Parallax MCP tools. NOT for US-centric analysis (use /parallax-macro-outlook), not for thematic screening (use /parallax-thematic-screen)."
negative-triggers:
  - US macro analysis → use /parallax-macro-outlook
  - Thematic screening across all markets → use /parallax-thematic-screen
  - Single stock analysis → use /parallax-deep-dive
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - list_macro_countries first to confirm the country is covered
  - build_stock_universe can filter by geography via natural language
  - Not all 40+ markets have full macro coverage — check_macro_health confirms
  - Smaller markets may have fewer scored equities
  - JIT-load `_parallax/house-view/loader.md` if an active CIO view is present; this is a regional-screen skill, so apply §3 (multipliers — region/sector tilts bias the top-opportunities ranking) and §5 (preamble + view-aware sections) and §6 (audit). The view does NOT override the country-specific macro narrative (the country's own data is sovereign for the macro sections); it biases the equity-selection ranking only.
  - When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer.
  - JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (6-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (Provenance) in Output Format.
---

<!-- white-label: integration-pattern.md -->

# Country Deep Dive

Macro + equity opportunity analysis for a specific country or region.

## Usage

```
/parallax-country-deep-dive Japan
/parallax-country-deep-dive "Southeast Asia"
/parallax-country-deep-dive India top_n=10
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns.

### Pre-Workflow — Load Active House View

Per `_parallax/house-view/loader.md` §1 and §2: load and validate any active house view BEFORE running the workflow. If view present, capture the load preamble for rendering at the top of Output Format per §5.1, and capture the tilt vector. Apply §3 multipliers to the Top Opportunities ranking in Batch B (region/sector tilts shift composite scores; the country macro narrative is unchanged). If no active view (or validation failure): run the workflow normally with the standard disclaimer.

### Batch 0 — Tool Loading

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

### Batch A — Coverage + macro + universe (parallel)

| Tool | Parameters | Notes |
|---|---|---|
| `list_macro_countries` | — | Confirm coverage |
| `check_macro_health` | — | Data freshness |
| `build_stock_universe` | "[country] equities" | Equity universe |

### Batch B — Macro depth + scoring (after Batch A)

1. Call `macro_analyst` for the country without component parameter (summary mode). The summary call returns all components inline (macro_indicators, tactical, fixed_income, currency, sectors, etc.). Do not make separate per-component calls — they return identical content and waste tokens.
2. For top N universe results (default 5): call `get_peer_snapshot` (parallel).
3. For top 3: call `get_score_analysis` with 26 weeks (parallel).
4. If view active, apply §3 multipliers to the composite scores from `get_peer_snapshot` per loader.md §3, re-rank Top Opportunities, and append the §6 audit log entry per loader.md §6.1.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (Provenance) when composing the Output Format. The loader returns exactly six keys; any other access (e.g. `branding["voice"]`) raises `KeyError` — structurally enforced by `loader.py`.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (banner from Pre-Workflow + low-confidence warnings). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** country deep dive`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to Provenance.
- **Country Overview** (macro summary, regime context)
- **Economic Indicators** (macro_indicators, fixed_income, tactical highlights)
- **Equity Coverage** (how many scored stocks, key sectors)
- **Top Opportunities** (table: symbol, name, sector, total score, key factor strengths)
- **Score Trends** (which top picks are improving vs. declining)
- **Investment Thesis** (synthesis: why this market, what factors favor it, key risks; if view active, frame in view-language — alignment vs misalignment with view tilts)
- **Provenance** (always present): one line stating branding state per integration-pattern.md §7 markdown column (5 error states; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second Provenance line.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise:

> *"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*
