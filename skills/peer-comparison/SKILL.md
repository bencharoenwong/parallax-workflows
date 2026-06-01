---
name: parallax-peer-comparison
description: "Research analyst peer comparison: peer snapshot, exported data, score trend analysis, and relative price performance via Parallax MCP tools. Symbol in RIC format. NOT for single stock analysis (use /parallax-deep-dive), not for portfolio analysis (use /parallax-morning-brief)."
negative-triggers:
  - Single stock deep dive → use /parallax-deep-dive
  - Portfolio analysis → use /parallax-morning-brief
  - Full due diligence → use /parallax-due-diligence
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - Identifies top 2 peers automatically from get_peer_snapshot
  - "Peer symbols from get_peer_snapshot may lack RIC suffixes. Before passing to Batch B tools, resolve each peer symbol to RIC format using the exchange suffix table in parallax-conventions.md (e.g., GM → GM.N, F → F.N). Single-letter symbols will fail without the suffix."
  - Makes 3 calls each for score trends and price series (primary + 2 peers)
  - export_peer_comparison and export_price_series return structured JSON
  - JIT-load `_parallax/house-view/loader.md` if an active CIO view is present. Peer-comparison is single-stock per `loader.md` §7 (read-only consumers): tilts are NOT applied to factor scoring or peer ranking. Render the FULL §7 surface: (a) §7.3 Score-vs-View Tension Banner inline between the Factor Comparison Matrix and Score Trajectory when primary stock total ≥ 7 AND its sector tilt ≤ -1; (b) §7.2 Peer-suggest conflict token under the Factor Comparison Matrix for any peer in a view-UW sector (tilt ≤ -1) or on the excludes list — flag, do not filter; the peer stays in the matrix; (c) §7.1 House View Note after Score Trajectory via `render_view_conflict(kind="blanket", ...)`; (d) §6 audit log entry per loader.md §6.1.
  - When rendering §7.1/§7.2/§7.3 tokens, JIT-load `_parallax/house-view/render_helpers.md` and route every token through `render_view_conflict()`.
  - When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer.
  - JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (6-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (Provenance) in Output Format.
---

<!-- white-label: integration-pattern.md -->

# Peer Comparison

Structured peer comparison analysis for research analysts.

## Usage

```
/parallax-peer-comparison AAPL.O
/parallax-peer-comparison AAPL.O weeks=26
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, and fallback patterns.

### Pre-Workflow — Load Active House View

Per `_parallax/house-view/loader.md` §1 and §2: load and validate any active house view BEFORE running the workflow. If view present, capture the load preamble for rendering at the top of Output Format per §5.1, and capture the sector tilt vector + excludes — these feed §7.2 + §7.3 + §7.1 surfacing during Output Format composition. Tilts are NOT applied to scores or peer ranking; the §7 surface is read-only conflict signals. If no active view (or validation failure): run the workflow normally with the standard disclaimer.

### Batch 0 — Tool Loading

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

### Batch A — Peer identification

1. Call `get_peer_snapshot`. Identify the peer group and top 2 most relevant peers.
2. Call `export_peer_comparison` with `format="json"`.

### RIC Resolution — Resolve peer symbols before Batch B

Peer symbols from `get_peer_snapshot` may lack exchange suffixes (e.g., `GM` instead of `GM.N`). Before proceeding, resolve each peer symbol to RIC format using the exchange suffix table in `parallax-conventions.md`. Single-letter tickers like `F` will trigger "Symbol too short" errors without the suffix.

### Batch B — Trends + price series (parallel, after Batch A identifies peers)

#### B.0 — Asset-class pre-classification (parallel, MANDATORY for price legs)

`export_price_series` is the **equity-only** price endpoint; sector/country ETFs (which `get_peer_snapshot` can occasionally surface as peers) silently return empty from it and would otherwise be dropped from the relative-price-performance comparison. Before Batch B, classify each leg (primary + top 2 peers):

- For each of the 3 legs, call `etf_profile(<plain_ticker>)` in parallel.
- `{"error": "No profile data found", ...}` → equity, route through `export_price_series`.
- Non-error response → ETF, route through `etf_daily_price`.

This adds 3 FREE/instant calls (per `_parallax/coverage-matrix.md`).

#### B.1 — Trends + price series (parallel)

Fire all 6 calls simultaneously:
- `get_score_analysis` for primary + top 2 peers (3 calls). If the user supplied `weeks=N` in the invocation, pass it as `weeks` as int N (non-default — see conventions §0.1); otherwise rely on the server default of 52.
- For each leg classified as **equity** in B.0 → `export_price_series(symbol=<ric>, days=<N>, format="json")`. Default `days=100`.
- For each leg classified as **ETF** in B.0 → `etf_daily_price(symbol=<plain_ticker>, start_date=<today − days>, end_date=<today>)`.

**Halt-and-surface rule:** if a leg returns empty from BOTH endpoints, exclude it from the price-performance section and render an explicit note: "⚠ Could not retrieve price history for `<symbol>`; relative price chart shows the remaining legs only." Never silently drop a leg without disclosure.

### Post-Workflow — House View consumer obligations

If a view was loaded in Pre-Workflow:

1. **§7.3 tension check** (primary stock): if `primary.total >= 7.0 AND view.tilts.sectors[primary.sector] <= -1`, compose the tension banner via `render_view_conflict(kind="score_tension", ...)`. Render between the Factor Comparison Matrix and Score Trajectory in Output Format.
2. **§7.2 peer-suggest tokens** (each peer): for every peer in the Factor Comparison Matrix whose sector has `view.tilts.sectors[peer.sector] <= -1`, or whose ticker appears in `view.tilts.excludes`, compose an inline token via `render_view_conflict(kind="peer_suggest", ...)`. Render under the Factor Comparison Matrix. **Flag, do not filter** — the peer stays in the matrix; multiple tokens stack vertically.
3. **§7.1 House View Note** (blanket summary): compose via `render_view_conflict(kind="blanket", ...)` and render after Score Trajectory, before Relative Price Performance.
4. Append the §6 audit log entry per loader.md §6.1.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (Provenance) when composing the Output Format. The loader returns exactly six keys; any other access (e.g. `branding["voice"]`) raises `KeyError` — structurally enforced by `loader.py`.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (banner from Pre-Workflow + low-confidence warnings). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** peer comparison`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to Provenance.
- **Peer Group** (who the peers are and why they're comparable)
- **Factor Comparison Matrix** (table: all peers x all factors)
  - *If view active*: render §7.2 Peer-suggest conflict tokens immediately under the matrix per Post-Workflow step 2. One token per conflicting peer; multiple stack vertically.
- **Score-vs-View Tension Banner** (only if view active AND primary total ≥ 7 AND sector tilt ≤ -1) — render between the Factor Comparison Matrix and Score Trajectory per Post-Workflow step 1, via `render_view_conflict(kind="score_tension", ...)`.
- **Score Trajectory** (which stock is improving/deteriorating fastest per factor)
- **House View Note** (only if view active) — render after Score Trajectory per loader.md §7.1 rendering order, via `render_view_conflict(kind="blanket", ...)`.
- **Relative Price Performance** (comparative returns)
- **Differentiation** (strengths and weaknesses vs peers)
- **Provenance** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second Provenance line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise:

> *"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*
