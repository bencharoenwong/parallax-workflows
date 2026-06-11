---
name: parallax-country-deep-dive
description: "Country or region equity discovery: what to buy in a market — macro context, available equity coverage, top-scoring stocks, and investment opportunities via Parallax MCP tools. Anchored on the allocation question. NOT for macro regime reads ('what is the regime in [market]?' — use /parallax-macro-outlook), not for thematic screening (use /parallax-thematic-screen)."
---

<!-- white-label: integration-pattern.md -->

# Country Deep Dive

## When not to use

- Macro regime read ("what is the regime in [market]?") → use /parallax-macro-outlook — that skill answers the regime question for any of the 40+ covered markets (US included); this skill answers "what should I buy in [country/region]?"
- Thematic screening across all markets → use /parallax-thematic-screen
- Single stock analysis → use /parallax-deep-dive

## Gotchas

- JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
- list_macro_countries first to confirm the country is covered
- build_stock_universe can filter by geography via natural language
- Not all 40+ markets have full macro coverage — check_macro_health confirms
- Smaller markets may have fewer scored equities
- JIT-load `_parallax/house-view/loader.md` UNCONDITIONALLY — §5 rule 3 (ground-truth check), rule 6 (AI disclosure), and §6 (audit log) apply whether or not a view is active. When a view IS present: this is a regional-screen skill, so additionally apply §3 (multipliers — region/sector tilts bias the top-opportunities ranking) and §5 (preamble + view-aware sections). The view does NOT override the country-specific macro narrative (the country's own data is sovereign for the macro sections); it biases the equity-selection ranking only.
- Boundary with /parallax-macro-outlook: the view-tilted Top Opportunities ranking is THIS skill's design (discovery/allocation surface). macro-outlook's optional equity census is deliberately untilted (regime exhibit). Same tools, different question — do not "harmonize" the two house-view contracts.
- When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer.
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (6-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (Provenance) in Output Format.

Macro + equity opportunity analysis for a specific country or region.

## Usage

```
/parallax-country-deep-dive Japan
/parallax-country-deep-dive "Southeast Asia"
/parallax-country-deep-dive India top_n=10
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, fallback patterns, and §0.2 (named-parameter discipline — `build_stock_universe` and `macro_analyst` parameters below are named explicitly because LLMs guess these wrong).

### Pre-Workflow — Load Active House View

Per `_parallax/house-view/loader.md` §1 and §2: load and validate any active house view BEFORE running the workflow. If view present, capture the load preamble for rendering at the top of Output Format per §5.1, and capture the tilt vector. Apply §3 multipliers to the Top Opportunities ranking in Batch B (region/sector tilts shift composite scores; the country macro narrative is unchanged). If no active view (or validation failure): run the workflow normally with the standard disclaimer. Loader.md §5 rule 3 (ground-truth check), rule 6 (AI disclosure), and §6 (audit) still apply on the no-view path.

### Batch 0 — Tool Loading

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

### Batch A — Coverage + macro + universe (parallel)

| Tool | Parameters | Notes |
|---|---|---|
| `list_macro_countries` | — | Confirm coverage |
| `check_macro_health` | — | Data freshness |
| `build_stock_universe` | `query="[country] equities"` | Equity universe (named parameter per conventions §0.2) |

### Batch B — Macro depth + scoring (after Batch A)

1. Call `macro_analyst` with `market="[country]"` and NO `component` parameter (summary mode — named parameter per conventions §0.2). The summary call returns all components inline (macro_indicators, tactical, fixed_income, currency, sectors, etc.). Do not make separate per-component calls — they return identical content and waste tokens.
2. For top N universe results (default 5): call `get_peer_snapshot` AND `get_company_info` per symbol (all parallel). `get_company_info` is the **ground-truth oracle** per loader.md §5 rule 3 (required view or no view): cross-check each `get_peer_snapshot.target_company` against the `get_company_info` name-of-record. On mismatch, flag ⚠ MISMATCH and recover per rule 3 (re-derive by symbol match from `peer_list[]`, else mark "scores unavailable") — never rank a mismatched score as authoritative.
3. For top 3: call `get_score_analysis` with 26 weeks (parallel).
4. If view active, apply §3 multipliers to the verified composite scores from `get_peer_snapshot` per loader.md §3 and re-rank Top Opportunities.
5. **Always** append the §6 audit log entry per loader.md §6.1 — view or no view (`applied=false` with `applied_reason: "no_view"` when none; include `ground_truth_mismatches` per §6.2 when any row was flagged).

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (Provenance) when composing the Output Format. The loader returns exactly six keys; any other access (e.g. `branding["voice"]`) raises `KeyError` — structurally enforced by `loader.py`.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (banner from Pre-Workflow + low-confidence warnings). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** country deep dive`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to Provenance.
- **Country Overview** (macro summary, regime context)
- **Economic Indicators** (macro_indicators, fixed_income, tactical highlights)
- **Equity Coverage** (how many scored stocks, key sectors)
- **Ground-truth Integrity** (only render if any mismatch detected — table: `input_ticker`, `returned_name`, `expected_name`, status, per loader.md §5 rule 3; mismatched rows show re-derived scores or "scores unavailable")
- **Top Opportunities** (table: symbol, name, sector, total score, key factor strengths — names are the `get_company_info` names-of-record; ⚠ MISMATCH rows flagged inline)
- **Score Trends** (which top picks are improving vs. declining)
- **Investment Thesis** (synthesis: why this market, what factors favor it, key risks; if view active, frame in view-language — alignment vs misalignment with view tilts)
- **Provenance** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second Provenance line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.
