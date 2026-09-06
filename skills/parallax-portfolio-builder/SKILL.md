---
name: parallax-portfolio-builder
description: "Build a portfolio from a natural language investment thesis. Constructs universe, scores, checks redundancy, and outputs allocation-ready list via Parallax MCP tools. Supports `--augment-silent` mode to fill active house view gaps from Parallax data for the current portfolio (saved view never mutates). Trigger for that mode: 'fill house view gaps from Parallax data for this portfolio'. NOT for analyzing existing portfolios (use /parallax-client-review), not for screening without allocation (use /parallax-thematic-screen), not for rebalancing an existing portfolio (use /parallax-rebalance), not for single stocks (use /parallax-should-i-buy)."
---

<!-- white-label: integration-pattern.md -->

# Portfolio Builder

## When not to use

- Analyzing existing portfolio → use /parallax-client-review
- Screening without allocation → use /parallax-thematic-screen
- Single stock analysis → use /parallax-should-i-buy
- Rebalancing existing portfolio → use /parallax-rebalance

## Gotchas

- Expected Parallax spend: ~36 tokens at N=10 (`_parallax/token-costs.md`): universe 5 + 10 snapshots + redundancy + validation 5.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §1 RIC resolution, §2 identity cross-check, §3 parallel execution, §4 fallbacks, §13 audience mode, §14 host primitives.
- JIT-load `_parallax/house-view/loader.md` FIRST; if a view is present follow §2, §3 (multipliers), §4 (conflict resolution), §5, §6. **The view-status banner is REQUIRED first in output** — never buried after the holdings table; if output gets compressed, keep it and drop other sections first.
- Drift check: JIT-load `_parallax/house-view/auto-on-load-judge-pattern.md` in Step 0 (this skill builds a portfolio); `--skip-drift-check` bypasses it.
- The saved view never carries Parallax-derived overlays. A dimension the view is silent on is neutral by default (non-blocking, RM-fan-out-safe) or JIT-augmented with `--augment-silent`, provenance-tagged per holding, never written back.
- `build_stock_universe` returns relevance-ranked results — re-rank by factor scores. Run the redundancy check before finalizing weights. Weights sum to ~1.0; include the allocation table AND the factor rationale.
- `analyze_portfolio` responses often exceed 180K chars — use streaming extraction (Step 3) and progressive validation.
- **Operator verification:** see [examples/testing-posture.md](../../examples/testing-posture.md)
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Construct a portfolio from a plain-English investment thesis using Parallax MCP tools.

## Usage

```
/parallax-portfolio-builder "defensive dividend-focused Asian equities under $10B market cap"
/parallax-portfolio-builder "US tech companies with strong quality and momentum scores" top_n=10
/parallax-portfolio-builder "ESG leaders in European industrials"
/parallax-portfolio-builder "EM-tilt balanced" --augment-silent   # JIT-augment dimensions the active view is silent on (default: off)
/parallax-portfolio-builder "defensive dividend-focused Asian equities" audience=client_safe
```

Optional `audience=` argument: `client_safe | internal_analyst`; precedence follows `parallax-conventions.md` §13.1.

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1). This is a multi-mode skill (`--augment-silent`); the mode branch lives inside Step 2.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Steps 1–3 and the `--augment-silent` branch) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: thesis; `top_n=` (default 10 scored, 5–8 selected); `--augment-silent`; `--skip-drift-check`; `audience=`.
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2 (hash, expiry, extraction-confidence warnings); capture tilt vector + excludes. On §2 failure or timeout run without the view (non-blocking). Then the drift pre-flight: `load-reference` `_parallax/house-view/auto-on-load-judge-pattern.md` and follow it; a surfaced banner renders before the report (`invoke-skill` unavailable → its documented skipped line). Skip this pre-flight if invoked with `--skip-drift-check` or if no active house view exists.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Resolve the thesis against the view per loader.md §4; if a view is present, prepend tilt context to the universe query (e.g. "exclude tech, overweight defensive sectors") and note any thesis-vs-view conflict for the Investment Thesis section.

### Step 2 — Fetch (parallel batches)

**Batch A — universe (runs in parallel with the Step 0 view load; both complete before Step 3).** `call-tool` `build_stock_universe`; force-include sectors/themes with tilt +2 if absent. **Divergence assertion** (loader.md §5 rule 4): if the query named N ≥ 2 sectors/themes and `max_sector_share / total > 0.6`, warn "universe collapsed to single sector despite multi-sector request" and re-issue as N parallel per-sector calls merged and deduped by symbol (highest rank wins); refuse to render only if the per-sector re-issue is itself skewed. **Timeout:** retry once with a narrower query; then `universe = []`, `universe_status = "unavailable"` — never call `check_portfolio_redundancy` as a placeholder.

**Batch A (mode `--augment-silent`).** After the universe: identify dimensions the THESIS depends on but the view is silent on. Default: treat as neutral and render the one-line note `Active view is silent on <dims>; using neutral. Run with --augment-silent to fill from Parallax data for THIS portfolio.` (and the ℹ invitation line between Universe Built and Selected Holdings when ≥ 1 thesis-relevant silent dimension exists). With the flag: `load-reference` `_parallax/house-view/gap_detect` + `gap_suggest`; build a synthetic draft view enumerating the silent dimensions; `gap_detect.detect_gaps()` scoped to them; `gap_suggest.plan_calls(gaps, available_markets=<list_macro_countries()["markets"]>)`; `call-tool` the planned calls together; `gap_suggest.fold_responses()` → Suggestions applied as tilts for THIS portfolio only, each tagged `[parallax_jit, <tool>[<args>]@<data_as_of>]` for the Tilt Source column. Never write back to `~/.parallax/active-house-view/`.

**Batch B — scoring.** For the top N candidates, `call-tool` all N `get_peer_snapshot` AND all N `get_company_info` in ONE turn (2N calls; a one-at-a-time loop is the dominant latency leak). Per-holding aggregation is the factor-profile source; `quick_portfolio_scores` only after every returned name is cross-validated. **Timeout:** N > 5 → retry with top 5 and flag; persistent → degrade to `quick_portfolio_scores` with name validation.

### Step 3 — Verify

- **Empty-universe gate (first check):** `universe_status = "unavailable"` → skip Steps 4–5's selection, render Universe Built as unavailable with no Selected Holdings table, append the audit row noting the abort, and call none of `check_portfolio_redundancy` / `analyze_portfolio` / `quick_portfolio_scores`.
- Cross-validation per conventions §2 / loader.md §5 rule 3: `returned_name` vs `expected_name` after normalization; ⚠ MISMATCH rows keep their place but their scores are not authoritative.
- Redundancy sanity check: >60% in one sector with `sector_concentration: {}` and "well-diversified" returned means the tool's detection failed — compute concentration client-side and flag the tool bug. Applies to Step 4's call and to the validation fallback alike.

### Step 4 — Compute

Sequential. **Rank & select:** with a view, re-rank by `composite × multiplier(sector/region/theme)` per loader.md §3 and apply factor-tilt re-weighting; drop `tilts.excludes` (surface the §4 block message); select 5–8. **Redundancy:** `call-tool` `check_portfolio_redundancy` on the equal-weight proposal; apply the Step 3 sanity check. **Weights:** adjust for scores, redundancy, sector balance and tilt multipliers; cap any sector at 2× neutral when the view is +2 (loader.md §3); factor profile = weight-aggregated per-holding snapshots. **Validate:** `call-tool` `analyze_portfolio` on the final allocation with `stream=true`; if streaming is unavailable or times out, fall back to `check_portfolio_redundancy` + `quick_portfolio_scores` (name-validated; ⚠ MISMATCH excluded) and flag every `analyze_portfolio` field the fallback cannot recover — rolling metrics, drawdown, contribution, performance series — as "unavailable in fallback path", never silently omitted.

### Step 5 — Compose

Fill **Output Format** below in order: House View Preamble FIRST when a view is active (short view_id, view_name, `effective_date → valid_through`, `Applying tilts: …`, `JIT-augmented: …` when used); Branding Header per integration-pattern.md §5; the Tilt Source compliance contract on every row × dimension; audience mode per §13 (Tilt Effect / Tilt Source relocate to the Methodology appendix under `client_safe`; ⚠ MISMATCH never relocates); `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 when a view is active, otherwise `parallax-conventions.md §9.1`. Audit entry per loader.md §6 with `augmented_dimensions: [{path, source_tool, source_call_args, data_as_of}]` when augmentation ran, else `silent_dimensions_skipped: [...]` when silent dimensions existed.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/builder.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill portfolio-builder < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. Degraded-state notes go inside their section. If `run-shell` is absent, apply conventions §14.3 (render-gate row). No Step 7.

## Output Format

- **House View Preamble** (REQUIRED FIRST when view active — render BEFORE any other section, never bury after the holdings table) — Per loader.md §5. MUST include: short view_id (first 8 chars), view_name, `effective_date → valid_through`, and a one-line summary `Applying tilts: <comma list of non-zero tilt names with values>`. If `--augment-silent` was used, append `JIT-augmented: <list of dim paths>`. This preamble is the user's primary signal that the view is active and what it's doing. If execution gets token-compressed, KEEP this section — drop other sections first if needed.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** portfolio construction`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **Investment Thesis** (restate and refine the user's intent; note any view-vs-thesis conflicts inline per loader.md §4)
- **Universe Built** (how many candidates, key sectors; note force-includes from +2 tilts and excludes applied; surface divergence-assertion result per loader.md §5 rule 4)
- **Why These Holdings**: 2-3 plain-language sentences summarizing why the selected names fit the stated thesis; no factor jargon without the §13.3 gloss. Rendered in both audience modes.
- **Selected Holdings** (table: `input_ticker`, `returned_name` (from scoring-tool response), `expected_name` (from get_company_info), sector, total score, weight, key factor strengths; if view active, include a "Tilt Effect" column showing the multiplier applied to each holding AND a "Tilt Source" column tagging the dimension's source. Under `audience=client_safe`, move the `Tilt Effect` / `Tilt Source` columns out of the primary table into a trailing **Methodology appendix (internal)** section that reproduces the full row × dimension tag map. **Tilt Source enforcement (compliance contract):** EVERY row × dimension cell MUST carry a non-empty tag in `{[house_view: <path>=<value>], [parallax_jit, <tool>[<args>]@<date>], [neutral, <reason>]}`. If any cell would be empty, that's a runtime bug — emit `⚠ Tilt Source missing for <row> × <dim>; verify before relying on this output` and refuse to claim the output is compliance-ready. This compliance contract applies to the appendix identically — relocation never deletes or weakens it. **Flag any row where `returned_name ≠ expected_name` after normalizing both per conventions §2 step 2 with ⚠ MISMATCH and do not treat that row's scores as authoritative** — per loader.md §5 rule 3. `⚠ MISMATCH` flags stay in the primary table in both modes because data-integrity warnings are non-suppressible per §13.2.)
- **View-Effect Summary** (only when view active AND ≥1 holding's ranking shifted vs raw-score order) — One paragraph: `Without the active view, the top-N ranking would have been [list]. With the view's tilts applied, ranking is [list]. The biggest change: <name> moved from #X to #Y because <view tilt that drove it: e.g., 'US +1 region multiplier + Defensive 10 × low_vol +2 factor re-weight'>.` This section is the auditability story made tangible per portfolio — it lets the RM defend "the view materially affected this allocation" rather than asserting it.
- **Portfolio Factor Profile** (VALUE, QUALITY, MOMENTUM, DEFENSIVE scores — computed as weighted aggregate of per-holding `get_peer_snapshot` scores; note `quick_portfolio_scores` batch output only if all names cross-validated)
- **Redundancy Notes** (any overlap flagged and how it was resolved; include client-computed sector concentration if `check_portfolio_redundancy` returned an empty concentration map on a clearly-concentrated portfolio)
- **Implementation Notes** (liquidity, position sizing, suggested rebalance frequency)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line. Under `audience=client_safe`, append the §13.4 mode line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- Universe unavailable after the retry: the empty-universe gate; no holdings table, audit row notes the abort.
- Universe collapsed to one sector: per-sector re-issue; refuse to render only if that is skewed too.
- Scoring timeouts: top-5 retry, then `quick_portfolio_scores` with name validation.
- `analyze_portfolio` too large or timed out: the light validation fallback with every unrecoverable field named.
- Any Tilt Source cell empty: `⚠ Tilt Source missing for <row> × <dim>; verify before relying on this output` and no compliance-ready claim.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive (drift check: the judge pattern's skipped line).

## Done when

- When a view is active the House View Preamble is the first line; otherwise the Branding Header or `## Investment Thesis`.
- Selected Holdings weights sum to ~1.0; every row carries `returned_name`, `expected_name`, and (view active) a non-empty Tilt Source per dimension; ⚠ MISMATCH rows are marked.
- View-Effect Summary present whenever a view changed the ranking.
- Audit entry appended per loader.md §6 with the augmentation or silent-dimension fields (every consume event, including the abort case).
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present; expected spend stated (Gotchas).
