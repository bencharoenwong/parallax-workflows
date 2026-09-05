---
name: parallax-peer-comparison
description: "Research analyst peer comparison: peer snapshot, exported data, score trend analysis, and relative price performance via Parallax MCP tools. Symbol in RIC format. NOT for single stock analysis (use /parallax-deep-dive), not for a quick single-name check (use /parallax-should-i-buy), not for full due diligence (use /parallax-due-diligence), not for portfolio analysis (use /parallax-morning-brief)."
---

<!-- white-label: integration-pattern.md -->

# Peer Comparison

## When not to use

- Single stock deep dive → use /parallax-deep-dive
- Quick single-name check → use /parallax-should-i-buy
- Portfolio analysis → use /parallax-morning-brief
- Full due diligence → use /parallax-due-diligence

## Gotchas

- Expected Parallax spend: ~8 tokens (`_parallax/token-costs.md`): peer snapshot + export + 3 score histories + 3 `etf_profile` probes.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §1 RIC resolution (peer symbols from `get_peer_snapshot` may lack suffixes; `F` fails without `.N`), §2 identity cross-check, §3 parallel execution, §4 fallbacks, §14 host primitives.
- JIT-load `_parallax/coverage-matrix.md`: `export_price_series` is equity-only; ETFs that surface as peers must go through `etf_daily_price`. The Step 2 asset-class pre-classification is mandatory for every price leg.
- JIT-load `_parallax/house-view/loader.md` if a view is present; single-stock consumer per §7 — tilts are NOT applied to scoring or peer ranking. Render the full §7 surface (§7.3 tension banner, §7.2 peer-suggest tokens under the matrix — flag, never filter — §7.1 note after Score Trajectory) via `render_view_conflict()` per `_parallax/house-view/render_helpers.md`; audit per §6.1.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Structured peer comparison analysis for research analysts.

## Usage

```
/parallax-peer-comparison AAPL.O
/parallax-peer-comparison AAPL.O weeks=26
```

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Steps 1–2) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: symbol; optional `weeks=N`.
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture the load preamble, sector tilt vector and excludes for the §7 surface in Step 5. Tilts are NOT applied.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name` (seven-key loader; `branding["voice"]` raises `KeyError` by design).

### Step 1 — Resolve inputs

`call-tool` `get_company_info` with the RIC (plain ticker → conventions §1). Then `call-tool` `get_peer_snapshot` and identify the peer group and the top 2 most relevant peers; `call-tool` `export_peer_comparison` with `format="json"`. Resolve each peer symbol to RIC form per conventions §1 before any further call.

### Step 2 — Fetch (parallel batches)

**Batch A — asset-class pre-classification (mandatory for every price leg).** For each of the 3 legs (primary + 2 peers) `call-tool` `etf_profile(<plain_ticker>)` together. `{"error": "No profile data found", ...}` → equity → route through `export_price_series`; a non-error profile → ETF → route through `etf_daily_price`. Per `_parallax/coverage-matrix.md`; 3 calls at 1 token each.

**Batch B — trends + price series.** `call-tool` all 6 together:
- `get_score_analysis` for primary + 2 peers (3 calls); pass `weeks` as int N when the operator supplied `weeks=N` (non-default — conventions §0.2), else server default 52.
- Each **equity** leg → `export_price_series(symbol=<ric>, days=<N>, format="json")`, default `days=100`.
- Each **ETF** leg → `etf_daily_price(symbol=<plain_ticker>, start_date=<today − days>, end_date=<today>)`.

### Step 3 — Verify

- Identity cross-check per conventions §2: `get_peer_snapshot.target_company` vs `get_company_info.name`; each `get_score_analysis` `data[0].symbol` vs the RIC sent.
- **Halt-and-surface rule:** a leg empty from BOTH price endpoints is excluded from Relative Price Performance with the explicit note `⚠ Could not retrieve price history for <symbol>; relative price chart shows the remaining legs only.` Never drop a leg silently.
- Other failed or empty calls: §0.1 retry classification, then §4. No gate is rendered, so §4.0 does not apply.

### Step 4 — Compute

No deterministic helper; relative returns are read from the exported series, never re-derived. Computed conditions are the house-view flags: §7.3 (`primary.total ≥ 7` AND `view.tilts.sectors[primary.sector] ≤ −1`) and §7.2 (a peer whose sector tilt ≤ −1 or whose ticker is in `view.tilts.excludes`), evaluated exactly as `loader.md` states.

### Step 5 — Compose

Fill **Output Format** below in order: House View Preamble per loader.md §5.1; Branding Header per integration-pattern.md §5; §7.2 tokens under the matrix (one per conflicting peer, stacked), §7.3 banner between the matrix and Score Trajectory, §7.1 note after Score Trajectory — all via `render_view_conflict()`; `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 rule 5 when a view is active, otherwise `parallax-conventions.md §9.1`; audit entry per loader.md §6.1.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/peercomp.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill peer-comparison < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. If `run-shell` is absent, apply conventions §14.3 (render-gate row). This skill has no Step 7.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (banner from Pre-Workflow + low-confidence warnings). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** peer comparison`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **Peer Group** (who the peers are and why they're comparable)
- **Factor Comparison Matrix** (table: all peers x all factors)
  - *If view active*: render §7.2 Peer-suggest conflict tokens immediately under the matrix per Post-Workflow step 2. One token per conflicting peer; multiple stack vertically.
- **Score-vs-View Tension Banner** (only if view active AND primary total ≥ 7 AND sector tilt ≤ -1) — render between the Factor Comparison Matrix and Score Trajectory per Post-Workflow step 1, via `render_view_conflict(kind="score_tension", ...)`.
- **Score Trajectory** (which stock is improving/deteriorating fastest per factor)
- **House View Note** (only if view active) — render after Score Trajectory per loader.md §7.1 rendering order, via `render_view_conflict(kind="blanket", ...)`.
- **Relative Price Performance** (comparative returns)
- **Differentiation** (strengths and weaknesses vs peers)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- Peer symbol unresolvable after conventions §1: that peer is dropped from the comparison with an explicit note naming it; the primary still renders.
- A price leg empty from both endpoints: excluded with the halt-and-surface note above.
- `etf_profile` probe fails for a leg: classify as equity, try `export_price_series`, and if that is empty apply the halt-and-surface note; never guess the asset class.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- Every Output Format section rendered or marked unavailable with its reason; first line is the House View Preamble, the Branding Header, or `## Peer Group`.
- Every leg in Relative Price Performance came from the endpoint matching its asset class; missing legs are named.
- When a view is active: the `view_status` banner appears verbatim; §7.2 tokens, §7.3 banner and §7.1 note are in their documented positions.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present; audit entry appended per loader.md §6.
- Expected spend stated (Gotchas).
