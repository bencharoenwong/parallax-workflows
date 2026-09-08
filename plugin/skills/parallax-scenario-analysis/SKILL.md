---
name: parallax-scenario-analysis
description: "React to a news event or scenario: assess portfolio exposure, macro regime shift, sector impact, identify most-exposed holdings, find rotation candidates, and output an information-framed action analysis via Parallax MCP tools. Also surfaces under PM/RIA vocabulary: 'stress book', 'scenario suite', 'stress test' (e.g., rates +100bps, USD shock, 2008 / 2020 / 2022 replays). Requires a portfolio and a scenario description. NOT for routine morning briefs (use /parallax-morning-brief), not for macro outlook without a triggering event (use /parallax-macro-outlook), not for testing the reasoning of a written thesis (use /parallax-stress-test-thesis), not for stress-testing the house view itself (use /parallax-stress-house-view)."
---

<!-- white-label: integration-pattern.md -->

# Scenario Analysis

## When not to use

- Routine morning brief → use /parallax-morning-brief
- General macro outlook → use /parallax-macro-outlook
- Pressure-testing a written thesis's reasoning → use /parallax-stress-test-thesis
- Stress-testing the active house view for contradictions → use /parallax-stress-house-view
- Single stock analysis → use /parallax-deep-dive
- Portfolio rebalancing without a trigger event → use /parallax-rebalance

## Gotchas

- Expected Parallax spend: ~78 tokens at 10 equity holdings including the 10 classification probes (`_parallax/token-costs.md`); roughly linear per holding; the >20-holding cap in Step 2 bounds large books.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §0.3 field-request integrity, §1 RIC resolution, §2 identity cross-check, §3 parallel execution, §4/§5 fallbacks, §12 framing, §14 host primitives.
- JIT-load `_parallax/coverage-matrix.md`: factor scores are equity-only; every holding is classified via `etf_profile` before the per-equity fan-out.
- JIT-load `_parallax/house-view/loader.md` if a view is present: portfolio-level consumer — §3 multipliers on replacement-candidate scoring, §4 (the user-supplied scenario is sovereign: a contradicting scenario surfaces a banner and the Action Analysis follows the scenario), §5, §6.
- `get_assessment` with a scenario-focused prompt is the core analytical engine; `get_news_synthesis` may already surface the event — check before assuming the user's framing is complete; for a breaking event scores have not moved yet, for a historical one `get_score_analysis` shows what did.
- FORWARD-LOOKING analysis — always caveat uncertainty.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Something happened (or might happen). What's exposed? What shifts? What do I do?

## Usage

```
/parallax-scenario-analysis "China announces 25% tariff on US semiconductors" portfolio=[{"symbol":"NVDA.O","weight":0.15},{"symbol":"AAPL.O","weight":0.20},{"symbol":"TSM.N","weight":0.10},{"symbol":"JPM.N","weight":0.15},{"symbol":"XOM.N","weight":0.20},{"symbol":"JNJ.N","weight":0.20}]
/parallax-scenario-analysis "Fed cuts rates 50bps emergency" portfolio=[holdings]
/parallax-scenario-analysis "Oil spikes to $120 on Middle East escalation" portfolio=[holdings]
```

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Steps 2 and 4) to the exact callable and schema exposed now; read `analyze_portfolio`'s live schema for the `portfolio`/`fields` shape.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: scenario text; `portfolio=` holdings.
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture the load preamble, tilt vector + excludes, and whether the scenario aligns with or contradicts the view per §4.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Holdings in RIC form (plain tickers → conventions §1), weights ~1.0; the 2–3 sectors most affected by the scenario; a beneficiary theme derived from the scenario text alone (e.g. "domestic US semiconductor manufacturers" for a tariff on imports) — if not derivable yet, defer it to after Batch B; the as-of date for `analyze_portfolio` per the schema note below.

### Step 2 — Fetch (parallel batches)

**Fan-out cap:** for >20 holdings, restrict Batch B's `get_score_analysis` and the cost-bearing per-holding fan-outs to the top 20 by weight plus any already-flagged holding; classification stays uncapped; render the degraded-coverage note listing skipped symbols.

**Batch A — event + classification + ground truth.** `call-tool` ALL together in one turn:

| Tool | Parameters | Notes |
|---|---|---|
| `get_news_synthesis` | 2–3 most affected sectors | Async 30–90 s; never gates anything (§5) |
| `get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Starting macro environment |
| `macro_analyst` | relevant markets; `component="tactical"` for a macro event | Positioning implications |
| `analyze_portfolio` | `portfolio=[{date: <as-of ISO>, symbol: <ric>, weight: <w>}]`, `fields=["concentration_metrics","sector_allocation","company_contribution"]` | Sector and concentration exposure. Supply a `date` per holding only when the live schema requires one; it is an as-of date over a price history, so today's date can return empty — when the schema gives no guidance, date every holding at the most recent completed trading day at least 5 calendar days back and state the date used. Returns **no** factor-exposure block; `fields` is a passthrough, so check `result._meta.invalid_fields` (§0.3). `holdings` and `lens` do not exist. May exceed 180K chars — fall back to `check_portfolio_redundancy` if truncated or on a schema-validation error. |
| `etf_profile` | per holding, plain ticker, all N in parallel | **Asset-class oracle**: non-error → ETF; `{"error": "No profile data found"}` → equity. 1 token each. |
| `get_company_info` | per holding, all N in parallel | **Ground-truth name oracle** (conventions §2). Per-holding only — a comma-joined call fails empty on partial coverage. |
| `build_stock_universe` | the beneficiary theme | Hoisted here (theme is scenario-derived) to overlap the rest |

**Batch B — after Step 3 clears the gate**, in one turn: `get_score_analysis` (4–8 weeks, typed int) per **equity, non-mismatched** holding; `get_peer_snapshot` for the top 5 beneficiary candidates from the universe. Then `get_financials(statement="summary")` for the top 2–3 replacement candidates.

### Step 3 — Verify

**Gate between Batch A and Batch B** — perform the following checks on Batch A results before firing Batch B:

1. **Asset-class routing**: partition holdings into `equities` (etf_profile error) and `etfs` (etf_profile non-error). Batch B's `get_score_analysis` runs ONLY on the `equities` set.
2. **Name cross-validation** (per conventions §2): for each holding, find the `analyze_portfolio` `company_contribution[]` row whose `ric` equals that holding's RIC and compare the row's `name` against `get_company_info.name`, normalizing both sides first per conventions §2 step 2 — `Apple Inc` and `Apple Inc.` are the same company and must not flag ⚠ MISMATCH. `analyze_portfolio` has no top-level identity field and no peer rollup — `company_contribution[]` is the per-holding identity 2a requests, so it is the only one available at this gate. A holding with no `company_contribution` row, or whose `get_company_info` call fails or returns empty, has no name pair to compare and therefore cannot be identity-checked at all — record it as UNCHECKED and surface it in the Ground-truth Integrity table rather than treating a missing comparison as a pass. Do not defer such a holding to Batch B's `get_score_analysis` `data[0].symbol` as a substitute: per conventions §2 step 2 the RIC is the input to both calls, so it agrees by construction and confirms nothing. UNCHECKED is not ⚠ MISMATCH — the holding stays in Batch B and in the assessment prompt, and the output states that its identity was never confirmed. Mismatches are flagged ⚠ MISMATCH and the holding is **fully excluded** from downstream analysis — both from Batch B's `get_score_analysis` and from Step 4's `get_assessment` prompt construction. Do not include mismatched holdings with empty profiles; that produces hallucinated factor profiles in the assessor's output.

### Step 4 — Compute

No deterministic helper. Two `call-tool` `get_assessment` passes, both async (fire early; compose other sections while they run):
1. **Exposure ranking** — prompt: the scenario; each equity, non-mismatched holding with sector and factor profile; ETF holdings with symbol + sector exposure from `analyze_portfolio` only; ⚠ MISMATCH holdings excluded entirely; ask: "Rank these holdings from most-exposed to least-exposed to this scenario. For each, explain the transmission mechanism (direct revenue impact, supply chain, regulatory, sentiment)."
2. **Synthesis** — prompt: the scenario and its transmission mechanisms; the exposure ranking; macro regime and tactical outlook; replacement candidates and scores (with loader.md §3 multipliers applied to candidate scoring when a view is active); the active view (basis_statement + relevant tilts + the alignment-vs-contradiction flag); ask: "Given this scenario, which holdings' exposure the scenario most affects and what adjustment candidates follow, framed as information. Prioritize by urgency and magnitude of exposure."

### Step 5 — Compose

Fill **Output Format** below in order: House View Preamble per loader.md §5.1 with the "Scenario contradicts house view" line when applicable; Branding Header per integration-pattern.md §5; §12 preface and action-label framing in Action Analysis; `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 rule 5 when a view is active, otherwise the bespoke scenario disclaimer below; audit entry per loader.md §6.1 (every consume event).

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/scenario.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill scenario-analysis < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. Degraded-state notes go inside their section. If `run-shell` is absent, apply conventions §14.3 (render-gate row). No Step 7.

## Output Format

**Begin the response immediately with the rendered report — no preamble.** The first expected line is `## Scenario Summary`, or the House View Preamble / Branding Header when active.

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (banner from Pre-Workflow + low-confidence warnings). If user-supplied scenario CONTRADICTS view tilts, append a "Scenario contradicts house view" line stating which tilt(s) disagree — per loader.md §4, the user's scenario is sovereign. Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** scenario analysis`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **Scenario Summary** (what happened, why it matters — 2-3 sentences)
- **Ground-truth Integrity** *(only render if Phase 2a flagged any mismatches OR recorded any holding UNCHECKED OR ETFs were excluded from per-position trajectory)* — table: `symbol`, `returned_name`, `expected_name`, status (⚠ MISMATCH / UNCHECKED / ETF — sector exposure only / TRUSTED). Mismatched holdings were fully excluded from the assessment prompt; ETF holdings are present in `analyze_portfolio` sector exposure but not in per-position factor trajectories. An UNCHECKED row fills whichever name is missing with `no row` (absent from `company_contribution[]`) or `no oracle` (`get_company_info` failed or returned empty); it was NOT excluded from the assessment, so state plainly that its identity could not be confirmed.
- **Macro Regime Impact** (how this shifts the current regime, which factors are affected)
- **Exposure Heat Map** (table: each equity holding ranked by exposure level — High/Medium/Low — with transmission mechanism. ETF holdings appear with sector-level exposure only; mismatched holdings are excluded.)
- **Most Exposed** (the 2-3 holdings at greatest risk, with specific reasoning)
- **Least Affected** (safe positions — brief explanation why)
- **Sector Rotation Thesis** (what benefits from this scenario)
- **Replacement Candidates** (table: symbol, name, sector, total score, why it fits)
- **Action Analysis** (prioritized, per conventions §12: exposure-reduction candidates, addition candidates, hold rationale — weight arithmetic framed as analysis, not instructions). Render the informational preface and action-label framing per `parallax-conventions.md` §12.
- **What to Watch** (2-3 signals that would confirm or invalidate this thesis)
- **Confidence & Caveats** (how certain is this analysis, what could go wrong with the rotation)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise:

*"This is scenario-based analysis, not investment advice. Forward-looking assessments are inherently uncertain."*


## Failure modes

- `analyze_portfolio` truncated or schema-rejected: `check_portfolio_redundancy` fallback; sector exposure is coarser and says so.
- A holding UNCHECKED (no `company_contribution` row, or no oracle): stays in the analysis with its identity stated as unconfirmed in Ground-truth Integrity; never treated as a pass.
- ⚠ MISMATCH holding: fully excluded from Batch B and both assessment prompts; listed in Ground-truth Integrity.
- >20 holdings: the fan-out cap with the skipped symbols named.
- `get_assessment` pending or failed: Exposure Heat Map and Action Analysis render the §4 async note; Scenario Summary, Macro Regime Impact and Replacement Candidates still render.
- News pending: placeholder per §5; never waited on.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- First line is `## Scenario Summary` or the House View Preamble / Branding Header; every Output Format section rendered or marked pending/unavailable with its reason.
- Every holding is in the Exposure Heat Map (equity), listed as ETF sector-only, or in Ground-truth Integrity as ⚠ MISMATCH or UNCHECKED; none silently dropped.
- Action Analysis carries the §12 preface; no imperative trade verbs.
- When a view is active: the `view_status` banner appears verbatim; a contradicting scenario is stated; audit entry appended per loader.md §6.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the view-aware or scenario disclaimer are present; expected spend stated (Gotchas).
