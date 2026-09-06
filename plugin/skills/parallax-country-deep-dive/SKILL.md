---
name: parallax-country-deep-dive
description: "Country or region equity discovery: which equities screen strongest in a market — macro context, available equity coverage, top-scoring stocks, and investment opportunities via Parallax MCP tools. Anchored on the allocation question. NOT for macro regime reads ('what is the regime in [market]?' — use /parallax-macro-outlook), not for thematic screening (use /parallax-thematic-screen), not for single stock analysis (use /parallax-deep-dive)."
---

<!-- white-label: integration-pattern.md -->

# Country Deep Dive

## When not to use

- Macro regime read ("what is the regime in [market]?") → use /parallax-macro-outlook — that skill answers the regime question for any of the 40+ covered markets (US included); this skill answers "what should I buy in [country/region]?"
- Thematic screening across all markets → use /parallax-thematic-screen
- Single stock analysis → use /parallax-deep-dive

## Gotchas

- Expected Parallax spend: ~29 tokens (`_parallax/token-costs.md`): one macro summary + universe + 5 snapshots + 5 info checks + 3 score trends.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §0.2 named-parameter discipline (`build_stock_universe(query=…)`, `macro_analyst(market=…)` with no `component`), §2 identity cross-check, §3 parallel execution, §4 fallbacks, §12 framing, §14 host primitives.
- JIT-load `_parallax/house-view/loader.md` UNCONDITIONALLY: §5 rule 3, rule 6 and §6 apply with or without a view. With a view: §3 multipliers bias the Top Opportunities ranking (region/sector tilts) and §5 rendering applies; the country's own macro narrative is sovereign and untouched. Boundary with /parallax-macro-outlook: that skill's census is untilted by design — do not "harmonize" the two contracts.
- Smaller markets may have fewer scored equities; `check_macro_health` confirms macro coverage.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report, with the unconditional currency line).

Macro + equity opportunity analysis for a specific country or region.

## Usage

```
/parallax-country-deep-dive Japan
/parallax-country-deep-dive "Southeast Asia"
/parallax-country-deep-dive India top_n=10
```

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Step 2) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: country or region; `top_n=` (default 5).
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture the load preamble and the tilt vector for Step 4.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

The market name must match `list_macro_countries` verbatim; a region maps to its covered member markets.

### Step 2 — Fetch (parallel batches)

**Batch A** — `call-tool` together: `list_macro_countries`; `check_macro_health`; `build_stock_universe(query="[country] equities")`.

**Batch B** — after A: `macro_analyst(market="[country]")` summary mode (no `component`; all components inline); for the top N universe results, `get_peer_snapshot` AND `get_company_info` per symbol together; for the top 3, `get_score_analysis` with `weeks` as int 26.

### Step 3 — Verify

- Coverage: an uncovered market is stated under Country Overview; no `macro_analyst` call for it.
- Identity per loader.md §5 rule 3 / conventions §2: `get_peer_snapshot.target_company` vs `get_company_info.name`; on mismatch flag ⚠ MISMATCH and recover from the `comparison[]` row whose `symbol` matches, else "scores unavailable"; never rank a mismatched score.

### Step 4 — Compute

No deterministic helper. With a view, apply loader.md §3 multipliers to the verified composite scores and re-rank Top Opportunities; without one, rank by composite.

### Step 5 — Compose

Fill **Output Format** below in order: House View Preamble per loader.md §5.1; Branding Header per integration-pattern.md §5; §12 preface above Top Opportunities; `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 rule 5 when a view is active, otherwise `parallax-conventions.md §9.1`; audit entry per loader.md §6.1 always (`applied=false`, `applied_reason: "no_view"` when none; `ground_truth_mismatches` per §6.2 when any).

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/country.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill country-deep-dive < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. Degraded-state notes go inside their section. If `run-shell` is absent, apply conventions §14.3 (render-gate row). No Step 7.

## Output Format

**Begin the response immediately with the rendered report — no preamble.** The first expected line is `## Country Overview`, or the House View Preamble / Branding Header when active.

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (banner from Pre-Workflow + low-confidence warnings). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** country deep dive`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **Country Overview** (macro summary, regime context)
- **Economic Indicators** (macro_indicators, fixed_income, tactical highlights)
- **Equity Coverage** (how many scored stocks, key sectors)
- **Ground-truth Integrity** (only render if any mismatch detected — table: `input_ticker`, `returned_name`, `expected_name`, status, per loader.md §5 rule 3; mismatched rows show re-derived scores or "scores unavailable")
- **Top Opportunities** (one-line informational preface per conventions §12 — this is an analytical ranking, not a trade instruction — then a table: symbol, name, sector, total score, key factor strengths — names are the `get_company_info` names-of-record; ⚠ MISMATCH rows flagged inline). Universe caveat: rankings cover listed equities with Parallax factor coverage only — funds/OEICs are not screened.
- **Score Trends** (which top picks are improving vs. declining)
- **Investment Thesis** (synthesis: why this market, what factors favor it, key risks; if view active, frame in view-language — alignment vs misalignment with view tilts)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line. Always append the §7 currency line: `Currency: figures as reported by source data; no base-currency conversion applied.`

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- Market not covered: Country Overview states it; Economic Indicators is unavailable; the equity sections still render if the universe returned.
- Universe empty or thin: Equity Coverage states the count; Top Opportunities may be short and says so.
- ⚠ MISMATCH rows: recovered per rule 3 or shown as "scores unavailable", never ranked as authoritative.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- First line is `## Country Overview` or the House View Preamble / Branding Header; every Output Format section rendered or marked unavailable with its reason.
- Top Opportunities carries the §12 preface and names-of-record; ⚠ MISMATCH rows are marked; the ranking is tilt-adjusted only when a view is active.
- When a view is active: the `view_status` banner appears verbatim; the Investment Thesis is framed in view language.
- Audit entry appended per loader.md §6 (every run, including no-view).
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present; expected spend stated (Gotchas).
