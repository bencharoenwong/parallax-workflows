---
name: parallax-peer-comparison
description: "Research analyst peer comparison: peer snapshot, exported data, score trend analysis, and relative price performance via Parallax MCP tools. Compare two named companies, an explicit set of up to three names, or one stock against automatic peers. Symbols in RIC format. NOT for single stock analysis (use /parallax-deep-dive), not for a quick single-name check (use /parallax-should-i-buy), not for full due diligence (use /parallax-due-diligence), not for portfolio analysis (use /parallax-morning-brief)."
---

<!-- white-label: integration-pattern.md -->

# Peer Comparison

## When not to use

- Single stock deep dive → use /parallax-deep-dive
- Quick single-name check → use /parallax-should-i-buy
- Portfolio analysis → use /parallax-morning-brief
- Full due diligence → use /parallax-due-diligence

## Gotchas

- Expected Parallax spend: default automatic mode ~14 credits for three resolved legs (1 primary company-info + 1 snapshot + 1 export + 2 peer company-info + 3 histories + 3 asset probes + 3 price calls); explicit mode ~5 credits per resolved leg (company-info + own snapshot + history + asset probe + price), excluding resolution/recovery. Check current tool descriptions; price calls are billed, not free. Fewer available legs reduce calls. ETFs have unverified score-history coverage; do not request unsupported equity scores.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §1 RIC resolution (peer symbols from `get_peer_snapshot` may lack suffixes; `F` fails without `.N`), §2 identity cross-check, §3 parallel execution, §4 fallbacks, §14 host primitives.
- JIT-load `_parallax/coverage-matrix.md`: `export_price_series` is equity-only; ETFs that surface as peers must go through `etf_daily_price`. The Step 2 asset-class pre-classification is mandatory for every price leg.
- JIT-load `_parallax/house-view/loader.md` if a view is present; single-stock consumer per §7 — tilts are NOT applied to scoring or peer ranking. Render the full §7 surface (§7.3 tension banner, §7.2 peer-suggest tokens under the matrix — flag, never filter — §7.1 note after Score Trajectory) via `render_view_conflict()` per `_parallax/house-view/render_helpers.md`; audit per §6.1.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Structured peer comparison analysis for research analysts.

## Usage

```
/parallax-peer-comparison AAPL.O
/parallax-peer-comparison AAPL.O weeks=26
/parallax-peer-comparison AAPL.O peers=MSFT.O
/parallax-peer-comparison AAPL.O peers=MSFT.O,GOOGL.O weeks=26
```

`peers=` is skill-local selection syntax, not an MCP parameter. Accept one or two distinct requested peers; the primary plus peers is at most three names. Natural-language "A vs B" maps to `A peers=B`; resolve plain tickers per conventions §1. Reject empty/malformed peer lists, repeated names (including primary repeated as peer), extra positional symbols and more than two peers with a compact clarification before billed analysis. Never silently truncate or substitute the server's favorite peer. A single primary without `peers=` keeps automatic mode.

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Steps 1–2) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse and validate args: primary symbol; optional `peers=RIC[,RIC]`; optional `weeks=N` as integer 1–200. Preserve requested spellings alongside resolved RICs and detect duplicates after resolution. Missing or conflicting selections require clarification before analysis.
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture the load preamble, sector tilt vector and excludes for the §7 surface in Step 5. Tilts are NOT applied.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name` (the §2 command prints visual keys only; voice is excluded by design).

### Step 1 — Resolve inputs

Resolve every requested identity per conventions §1; keep the requested name, resolved RIC and coverage status. An unresolved primary stops for clarification. An unresolved explicit peer stays named as unavailable; do not replace it, and do not describe a one-leg partial result as a completed comparison.

**Automatic mode:** `call-tool` `get_company_info` and `get_peer_snapshot` for the primary; verify identity per §2 before selecting up to two relevant non-target peers. `call-tool` `export_peer_comparison(symbol=<primary>, format="json")` for that automatic set. Resolve selected peer symbols and fetch their `get_company_info` identities before rendering their snapshot rows. Exclude a mismatched row with an explicit note.

**Explicit mode:** for each resolved requested leg, `call-tool` its own `get_company_info(symbol=<ric>)` and `get_peer_snapshot(symbol=<ric>)` in parallel. Build the requested comparison from each leg's own verified target row (`is_target: true`, or matching resolved symbol per conventions §2); never take an unrelated row or a display-only `target_score` string as a factor breakdown. If that leg's snapshot fails identity validation, mark its scores unavailable. The snapshot and export tools accept an anchor symbol, not a caller-selected peer list: do not pass `peers` to them. Skip `export_peer_comparison` in explicit mode; an anchor's automatic export is not an export of the requested set. Get any other profile fields from that leg's company-info response, keeping source/date and missing-field notes. Do not invent absent P/E, return or factor values.

Keep the selected legs fixed for Steps 2–5. Default peers and user-requested peers are different selection methods; state which was used. Different sectors or asset classes may limit comparability; disclose that limitation rather than changing the user's selection.

### Step 2 — Fetch (parallel batches)

**Batch A — asset-class pre-classification (mandatory for every price leg).** For each resolved selected leg `call-tool` `etf_profile(<plain_ticker>)` together. A verified ETF profile → ETF → `etf_daily_price`. The legacy explicit `No profile data found` result, or a current `success:false`, `status:400`, `Invalid ETF symbol: ... not found in the ETF universe` result, establishes only that the symbol was not found as an ETF; route through `export_price_series` only with the independently verified equity identity. Transport/auth/schema/other errors never prove equity. Per `_parallax/coverage-matrix.md`; one billed probe per resolved leg. A positive ETF profile does not establish equity-factor or score-history coverage.

**Batch B — trends + price series.** `call-tool` independent requests together for resolved selected legs only:
- `get_score_analysis` for each supported equity leg; pass `weeks` as int N when the operator supplied `weeks=N` (non-default — conventions §0.2), else server default 52.
- Each **equity** leg → `export_price_series(symbol=<ric>, days=<N>, format="json")`, default `days=100`.
- Each **ETF** leg → `etf_daily_price(symbol=<plain_ticker>, start_date=<today − days>, end_date=<today>)`.

### Step 3 — Verify

- Identity cross-check per conventions §2 for every rendered scored leg: its snapshot `target_company` vs its own `get_company_info.data.name`; automatic peer rows must also match their peer company-info identity. Each `get_score_analysis` `data[0].symbol` must match the RIC sent. Empty or mismatched data remains unavailable, never a successful check. ETF scores and histories remain unavailable unless current discovered coverage explicitly supports them.
- **Halt-and-surface rule:** a leg empty from BOTH price endpoints is excluded from Relative Price Performance with the explicit note `⚠ Could not retrieve price history for <symbol>; relative price chart shows the remaining legs only.` Never drop a leg silently.
- Other failed or empty calls: §0.1 retry classification, then §4. No gate is rendered, so §4.0 does not apply.

### Step 4 — Compute

No deterministic return helper is provided. Use server-computed period returns only when their dates, currency and price basis are explicit and comparable across the selected legs. A raw price series is not a supplied return. Equity `export_price_series.data[].price` must be labeled **reported price — close/adjustment basis unverified** unless the response explicitly establishes that basis; do not call it a daily close or adjusted close merely because dates are daily. An ETF `etf_daily_price` row may be labeled close only when its returned field is `close`; adjustment basis remains unverified unless supplied. Preserve each leg's endpoint and actual returned field in the rendered price-history note. If no comparable return fields are available, mark comparative returns unavailable and identify the available price histories; do not invent returns or calculate them in prose. Computed conditions are the house-view flags: §7.3 (`primary.total ≥ 7` AND `view.tilts.sectors[primary.sector] ≤ −1`) and §7.2 (a peer whose sector tilt ≤ −1 or whose ticker is in `view.tilts.excludes`), evaluated exactly as `loader.md` states.

### Step 5 — Compose

Fill **Output Format** below in order: House View Preamble per loader.md §5.1; Branding Header per integration-pattern.md §5; §7.2 tokens under the matrix (one per conflicting peer, stacked), §7.3 banner between the matrix and Score Trajectory, §7.1 note after Score Trajectory — all via `render_view_conflict()`; `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 rule 5 when a view is active, otherwise `parallax-conventions.md §9.1`; audit entry per loader.md §6.1.

### Step 6 — Render (deterministic gate, mandatory)

`write-artifact` the complete drafted report to a new `<draft-path>`, then `run-shell` the shared gate with this skill's key, both per conventions §10.3:

```
python3 "<skill-dir>/../_parallax/render_gate.py" --skill peer-comparison --input "<draft-path>"
```

Write the draft once and never modify it in place, not even to fix one word. If the report needs a change after the draft is written, run the command above on that draft unchanged (ignore that output), then write the corrected report to a fresh path and run the command on it (conventions §10.3).

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. If `run-shell` is absent, apply conventions §14.3 (render-gate row). This skill has no Step 7.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (banner from Pre-Workflow + low-confidence warnings). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** peer comparison`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **Peer Group** — selection method (automatic or explicitly requested), every requested identity and coverage status, why the names are comparable and any sector/asset-class limits. Keep unresolved peers named here and in unavailable matrix rows; never claim a complete named-pair comparison when one leg is missing.
- **Factor Comparison Matrix** (table: all peers x all factors)
  - *If view active*: render §7.2 Peer-suggest conflict tokens immediately under the matrix per Post-Workflow step 2. One token per conflicting peer; multiple stack vertically.
- **Score-vs-View Tension Banner** (only if view active AND primary total ≥ 7 AND sector tilt ≤ -1) — render between the Factor Comparison Matrix and Score Trajectory per Post-Workflow step 1, via `render_view_conflict(kind="score_tension", ...)`.
- **Score Trajectory** (which stock is improving/deteriorating fastest per factor)
- **House View Note** (only if view active) — render after Score Trajectory per loader.md §7.1 rendering order, via `render_view_conflict(kind="blanket", ...)`.
- **Relative Price Performance** — comparable supplied returns when available; otherwise unavailable with the reason and per-leg price provenance. Label equity `.price` as reported price with close/adjustment basis unverified; use ETF close only when that is its returned field. Never rename `.price` to closing price.
- **Differentiation** (strengths and weaknesses vs peers)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- Explicit peer unresolvable, absent or identity-mismatched: retain its requested identity with unavailable fields and a reason; render the supported partial result without a relative ranking against the missing leg. Do not auto-fill from the server peer list. Automatic peer unresolvable: exclude with a named coverage note; do not invent a replacement.
- A price leg empty from both endpoints: excluded with the halt-and-surface note above.
- `etf_profile` transport failure, timeout or unrelated error: asset class remains unverified; do not treat it as the explicit `No profile data found` response or route to an equity endpoint by default. Use separately verified instrument-type evidence if available; otherwise mark that price leg unavailable with the reason.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- Every Output Format section rendered or marked unavailable with its reason; first line is the House View Preamble, the Branding Header, or `## Peer Group`.
- Every explicitly requested identity is retained or clarified, no automatic peer substituted; each rendered score passed its identity check. A partial result states which requested comparison remains unanswered.
- Every leg in Relative Price Performance came from the endpoint matching its asset class; missing legs are named.
- When a view is active: the `view_status` banner appears verbatim; §7.2 tokens, §7.3 banner and §7.1 note are in their documented positions.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present; audit entry appended per loader.md §6.
- Expected spend stated (Gotchas).
