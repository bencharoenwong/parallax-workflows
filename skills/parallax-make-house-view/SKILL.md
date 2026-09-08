---
name: parallax-make-house-view
description: "Synthesize a draft Parallax house view by orchestrating macro_analyst + get_telemetry MCP outputs across the 14 covered markets, route the draft through the shared confirmation gate, and save through the same path /parallax-load-house-view uses. The synthesized view carries `generator_synthesis` provenance (distinct from ingested views' `prose_extraction`) and lands in `~/.parallax/active-house-view/` like any other house view. Use when the bank has no CIO take to ingest, when prepping a Parallax baseline for shadow-comparison against an active bank view, or to populate a fresh deployment. NOT for ingesting an existing CIO PDF (use /parallax-load-house-view), not for stress-testing an active view (use /parallax-stress-house-view), not for judging an active view against current Parallax signals (use /parallax-judge-house-view). Pass --compare <view_a> <view_b> to diff two saved view bundles cell-by-cell (e.g. UBS vs Goldman) with no synthesis."
---

# Make House View

## When not to use

- Ingesting a CIO PDF / URL / wizard input → use /parallax-load-house-view
- Judging an active view against live signals → use /parallax-judge-house-view
- Stress-testing for internal consistency → use /parallax-stress-house-view
- Per-cell **tilt** diff of two saved views (e.g. UBS vs Goldman) → use /parallax-make-house-view --compare
- Diff of two **portfolio outputs** (view vs baseline) → use /parallax-house-view-diff

## Gotchas

- JIT-load `_parallax/house-view/MCP_FIELD_INVENTORY.md` BEFORE assuming any component input is available. `valuation_state` / `market_entropy` are prose-extracted; `psychological_wavelength` is LLM-judged. Confidence caps differ per component.
- The shared gate (`_parallax/house-view/gate_present.py`) is REQUIRED — there is no save path that bypasses it. `--shadow-diff` skips the gate AND the save.
- `--compare` is a pure structural file diff of two saved bundles: it skips MCP, synthesis, the gate, the save, the audit row, AND all output disclaimers. It never emits a pillar-confidence block (keep pillar internals out of any cross-firm output).
- Expected Parallax spend: ~282 tokens at the default market set (`_parallax/token-costs.md`); `--markets` scales it proportionally. Fan-out budget is 14 markets × 4 components = 56 macro_analyst calls + 1 list_macro_countries + 1 get_telemetry. Concurrency cap 8. Per-market timeout 45s. Hard abort when unreachable_share > 30%.
- Every host interaction is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Persistence fails closed: nothing is saved without an explicit `ask-operator` confirmation this session.
- Reuse `audit_chain.append_entry`, `chain_emit.emit_phase_0_chain`, `provenance_classes.validate_provenance_entry`. NEVER reimplement.
- The `generate` audit row carries ONLY: schema_version, ts, view_id, version_id, view_hash, skill, action, applied, parent_version_id, provenance_hash, source_tools, calibration_status. composition_formula / aggregator_weights_ref / source_snippets / pillar_missing_inputs MUST go in `provenance.yaml`, NOT on the audit row.
- `psychological_wavelength` judgment is Claude-only (data perimeter — telemetry contains CG-proprietary signals, do NOT dispatch to external models).
- Synthesized views carry `auto_expire_days: 30` (shorter than ingested views' 90) because the underlying macro fan-out is point-in-time.
- §9.2 exemption: this skill does NOT render the AI-interaction disclosure banner. It emits configuration artifacts (`view.yaml` + `prose.md`) whose LLM-synthesized content is gated by the Step 5 operator confirmation gate before any downstream consumer can load the view — and every downstream consumer renders §9.2 in its own output per loader.md §5 rule 6. Rationale and conditions: `parallax-conventions.md` §9.2 "Exemption". Registered in `_NINE_TWO_EXEMPT_SKILLS` in the white-label test gate.

Synthesize a draft Parallax house view by orchestrating Parallax MCP tools (`list_macro_countries` + `macro_analyst` × 14 markets × 4 components + `get_telemetry`), aggregate cross-country, compose the four framework components (macro backdrop, valuation, market state, sentiment), route through the shared confirmation gate, and save through the same path `/parallax-load-house-view` uses.

The synthesized view lives in `~/.parallax/active-house-view/` and is consumed by every downstream skill (portfolio-builder, rebalance, thematic-screen, etc.) exactly like an ingested view — the only difference is the provenance class (`generator_synthesis` vs `prose_extraction`) and a shorter default `auto_expire_days`.

## Usage

```
/parallax-make-house-view                              # synthesize, route to gate, save
/parallax-make-house-view --shadow-diff                # synthesize, DO NOT save; diff vs active view
/parallax-make-house-view --basis "<hint>"             # bias synthesis with a textual hint
/parallax-make-house-view --markets us,japan,uk        # restrict fan-out scope (cost / debug)
/parallax-make-house-view --status                     # show last-generated view metadata
/parallax-make-house-view --compare <path_a> <path_b>  # diff two saved view bundles; no MCP, no synthesis, no save
```

## Workflow

Config-producer shape (authoring conventions, "Canonical step spine"): Steps 0–4, then `Step 5 — Confirm` and `Step 6 — Persist`. No render gate. Modes that skip synthesis are under `## Modes`.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `load-reference` `_parallax/house-view/MCP_FIELD_INVENTORY.md` (per-pillar input availability), `_parallax/house-view/schema.yaml` (view shape + `classification_taxonomy.generator_synthesis`), and `_parallax/house-view/loader.md` (esp. §6 audit format for the `generate` action).
3. `discover-tools`: bind `list_macro_countries`, `macro_analyst`, `get_telemetry` to the exact callables and schemas exposed now (conventions §0.0–§0.1).
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call; `ask-operator` = `AskUserQuestion`; `run-shell` = `Bash`.
   <!-- /host-note -->
4. `read-config`: `$PARALLAX_HOUSE_VIEW_DIR`, else `~/.parallax/active-house-view/`.
5. Bind `ask-operator` and `run-shell`. Without `ask-operator` the synthesis can render as a draft but never saves (Failure modes).

### Step 1 — Resolve inputs

Parse flags: `--compare` and `--status` short-circuit to `## Modes` before any Parallax call; `--shadow-diff`, `--basis`, `--markets` set the synthesis mode, hint, and scope.

Then resolve covered markets: `call-tool` `list_macro_countries()`. Expect 15 entries (14 country reports + "Global"). Exclude "Global" from per-country fan-out (it's an aggregate, would double-count). When `--markets` filter is set, intersect with the live coverage.

Fallback: if `list_macro_countries` fails, use the hardcoded `HARDCODED_COVERAGE` tuple in `maker.py` (14 markets matching `aggregator_weights.yaml`).

### Step 2 — Fetch (parallel batches)

`call-tool` in parallel (concurrency cap 8, per-call timeout 45s):

- **Batch A:** `macro_analyst(market=M, component=C)` for every (M, C) pair where M ∈ covered_markets and C ∈ {`macro_indicators`, `tactical`, `sectors`, `news`}. Budget: 14 × 4 = 56 calls. (`fixed_income` is out of scope — no formula consumes it yet.)
- **Batch B (single call, parallel with Batch A):** `get_telemetry(fields=["regime_tag", "divergences", "factor_view.factors", "factor_view.commentary", "signals", "commentary"])`.

### Step 3 — Verify

Per-market timeout: 45s. A market is `UNREACHABLE` when no component returns a response whose shape can be interpreted — absent, not a mapping, or carrying neither a `success` nor an `error` key. That rule is `_parallax/house-view/mcp_meta.py` (`carries_data`), the same predicate backing `stress.classify_mcp_meta_state`'s UNREACHABLE branch, so the maker and the stress classifier cannot disagree about what counts as a dead market. A market that returns a successful response with content like "Sector ranking data remains unavailable for this reporting period" — or an explicit `success: false` — is treated as **silent for that component**, not UNREACHABLE for the market (per MCP_FIELD_INVENTORY.md §5.4): the server answered, and only an uninterpretable shape fails closed.

If `unreachable_share > 0.30` of the fan-out, HARD ABORT. Aggregation can't recover from that level of degradation.

### Step 4 — Compute

#### Step 4a — Cross-country aggregation

Call `cross_country.aggregate(per_market_responses, telemetry, weights)`. Outputs:

- `phi.value` / `phi.coverage_ok` / `phi.markets_with_data`: weighted-median of per-market `valuation_state` prose-extracted values when ≥ 60% of weight responded; else NULL + coverage_warning.
- `xi.value` etc.: same shape for `market_entropy`.
- `psi_news_blobs`: concatenated per-country news content for `psychological_wavelength` judgment.
- `regions.<schema_key>`: single-market region tilts (bypass the coverage threshold — a single-market region has no cross-country weighting to gate on).
- `sectors.<sector>`: cross-country weighted-median, coverage-gated.
- `macro_regime`: inferred growth/risk tokens from telemetry.regime_tag.
- `fan_out_summary`: market counts.

#### Step 4b — Component composition

Call `pillar_compose.compute_pillars(aggregated, telemetry)`. Returns four `PillarResult(value, confidence, missing_inputs, composition_formula, source_snippets)` objects (module/class names kept as field identifiers for data-contract stability).

Component confidence caps (MCP_FIELD_INVENTORY.md §4):
- **`econometrics_phase` (macro backdrop)**: ≤ 0.80 (regime_tag + cross-country growth nudge).
- **`valuation_state` (valuation)**: ≤ 0.70 (prose-extracted from per-country macro_indicators). PROSE-BASED — assumed `telemetry.signals.valuation_z` does NOT exist (verified A0).
- **`market_entropy` (market state)**: ≤ 0.50 (composite: prose entropy + normalized `len(telemetry.divergences)` as fallback proxy; `composition_formula` documents the weighting).
- **`psychological_wavelength` (sentiment)**: ≤ 0.60. Default is heuristic bag-of-words; SKILL.md flow injects a Claude structured-output prompt via `psychological_judge_fn` for production.

When `missing_inputs` is non-empty, confidence is capped at 0.35 (strictly below `gap_detect.LOW_CONFIDENCE_THRESHOLD = 0.4`) so the gap branch fires.

**`psychological_wavelength` judgment is Claude-only.** Telemetry contains CG-proprietary signals — do NOT dispatch to external models. Structured-output schema:

```json
{"value": -2..+2, "reasoning": "≤200 chars", "confidence": 0.0-1.0}
```

#### Step 4c — Optional gap-fill finishing pass

OPTIONAL. After Steps 4a–4b, any residually silent leaves (e.g., sectors where coverage was below threshold but a single anchor market had a strong signal) MAY be folded via `gap_suggest.fold_responses`. Step 4a–4b results win on conflict. **Not implemented — skip this step.**

### Step 5 — Confirm (shared gate)

Build the `GateContext` and call `gate_present.run_gate_loop(draft, context, dispose_fn, edit_fn)`:

```python
GateContext(
    source_label=f"Parallax synthesis {iso_timestamp}",
    uploader_present=False,
    confidence_map={
        "pillars": mean([omega.confidence, phi.confidence, xi.confidence, psi.confidence]),
        "sectors": <aggregated sector confidence>,
        "regions": <aggregated region confidence>,
        "factors": <factor confidence>,    # 0.0 in v0 — maker doesn't populate factors
        "macro_regime": <macro_regime confidence>,
    },
    extraction_attempt_action=True,
    disposition_options=["confirm", "edit", "regenerate", "abandon"],
)
```

Bridge `dispose_fn` and `edit_fn` to `ask-operator` exactly as `/parallax-load-house-view` Step 5 does — the module is shared.

Branch on `GateResult.disposition`:
- **`confirm`** / **`edited`** → Step 6 (persist).
- **`regenerate`** → re-run from Step 2 with the basis hint updated; return to Step 5.
- **`abandon`** → no save, no audit `generate` row. Done.

### Step 6 — Persist (reuses load-house-view Step 6 path)

`run-shell` the helper: `maker.MakerOrchestrator.save_view(...)`. This:

1. Computes `view_hash` per schema.yaml §"view_hash computation" (pinned algorithm).
2. Builds `provenance.yaml` with one `generator_synthesis` entry per non-neutral leaf (per `schema.yaml § classification_taxonomy.generator_synthesis`). Validates via `provenance_classes.validate_provenance_entry`.
3. Computes `provenance_hash = sha256(JCS(provenance_data))`.
4. Sets `extraction.uploader_confirmed = true`, `metadata.upload_timestamp`, `metadata.calibration_status = "heuristic_phase0"`.
5. Renders `prose.md` via `prose_synth.render_prose` (deterministic, no LLM). Computes `prose_body_hash`.
6. Writes `view.yaml`, `prose.md` (with frontmatter `paired_yaml_hash` / `prose_body_hash` / `view_id` / `version_id`), `provenance.yaml`. chmod 0600.
7. Appends `action: "generate"` audit row via `audit_chain.append_entry` — fields per loader.md §6.1/§6.2:

   ```json
   {
     "schema_version": 1,
     "ts": "...",
     "view_id": "...",
     "version_id": "...",
     "view_hash": "...",
     "skill": "parallax-make-house-view",
     "action": "generate",
     "applied": true,
     "parent_version_id": null,
     "provenance_hash": "...",
     "source_tools": ["macro_analyst:United_States:macro_indicators", ...],
     "calibration_status": "heuristic_phase0"
   }
   ```

   **FORBIDDEN on the audit row** (per loader.md §6.2): `composition_formula`, `aggregator_weights_ref`, `source_snippets`, `pillar_missing_inputs`. These live in `provenance.yaml`. The maker raises if any forbidden key appears.

8. Emits reasoning chain via `chain_emit.emit_phase_0_chain`:
   - `skill_version="parallax-make-house-view@1.0.0"`
   - `base_scores={"response_inline": <aggregated MCP responses>, "response_hash": <sha256 of sorted JCS concat>}`
   - `final_portfolio={"weights": {}}` (dummy — maker produces no portfolio)
   - `run_id=<new uuid>`

## Modes

### Shadow-diff mode

`/parallax-make-house-view --shadow-diff` runs Steps 1–4, then short-circuits Steps 5–6. Instead of routing through the gate, it loads the currently-active bank view and renders an ADDITIVE diff via `shadow_diff.render_shadow_diff`. No save. The framing is critical — the bank's view is sovereign, the synthesis is offered as data to consider, never as a correction.

### Compare mode

`/parallax-make-house-view --compare <path_a> <path_b>` loads two **saved** view bundles from disk (each arg may be a bundle directory or a `view.yaml` path) and renders a NEUTRAL per-cell diff of their tilts and excludes. It short-circuits **before Step 1** — no MCP calls, no synthesis, no gate, no save, no audit row. Invoke `maker.run_compare(Path(path_a), Path(path_b))` and render the returned string.

Unlike `--shadow-diff` (which synthesizes a Parallax view and frames it as *additive* against the *sovereign* active bank view), `--compare` treats both inputs as equally sovereign: symmetric `left_only` / `right_only` / `agree` / `disagree` buckets, no synthesis, and **no pillar-confidence block** (pillar tilt cells appear like any other cell, but the confidence/computation internals never do).

Disambiguation: `--shadow-diff` = synth-vs-active (synthesis runs); `/parallax-judge-house-view` = active-view-vs-live-signals; `/parallax-house-view-diff` = portfolio-OUTPUT diff (Leg A vs Leg B weights, not a tilt-cell diff).

### Status mode

`/parallax-make-house-view --status` shows last-generated view metadata + the standard `view_status.banner` (same banner the loader emits). No MCP calls.

## Output Format

### Post-save summary

After a successful Step 6:

```
✓ House view synthesized and saved.
  view_name:      Parallax synthesis YYYY-MM-DD
  view_id:        <uuid>
  version_id:     <uuid>
  effective:      <today> through <today + 30d>
  components:     econometrics_phase <e>  valuation_state <v>  market_entropy <m>  psychological_wavelength <p>
  component conf: econometrics_phase <c>  valuation_state <c>  market_entropy <c>  psychological_wavelength <c>  (avg <avg>)
  tilts active:   <count of non-zero tilts>
  unreachable markets: <count>

Active in: portfolio-builder, rebalance, thematic-screen, morning-brief, client-review, explain-portfolio.
Conflict-flag only in: should-i-buy, deep-dive.

Try it:
  /parallax-portfolio-builder "<your thesis>"     # build a portfolio with this view applied
  /parallax-judge-house-view                      # compare this synthesis against live signals later

Audit & inspect:
  /parallax-load-house-view --status              # active view summary
  /parallax-load-house-view --why <tilt-path>     # why is this tilt set to what it is?
  /parallax-load-house-view --export <view_id>    # regulator-grade compliance bundle

To clear:  /parallax-load-house-view --clear
```

Shadow-diff renders `shadow_diff.render_shadow_diff`; compare renders `maker.run_compare`; status renders the `view_status.banner` first, verbatim.

## Modules

- `maker.py` — orchestrator + save path. `MakerOrchestrator.execute_synthesis(mcp, dispose_fn, edit_fn)` is the entry point.
- `cross_country.py` — `aggregate(per_market_responses, telemetry, weights)` with 60% coverage rule.
- `pillar_compose.py` — `compute_pillars(aggregated, telemetry)` packaging.
- `pillar_formulas.py` — `compute_omega / compute_phi / compute_xi / compute_psi` (function names kept as field identifiers). Prose-based `valuation_state` / `market_entropy` per A0 findings. Confidence caps + missing-input rule.
- `prose_synth.py` — deterministic YAML → markdown narrative (no LLM).
- `shadow_diff.py` — `--shadow-diff` rendering (`render_shadow_diff`) + `--compare` rendering (`render_compare` / `diff_excludes`). `maker.run_compare(left, right)` is the `--compare` entry point.

## Hard constraints

- Reuse (do not reimplement) shared infra: `audit_chain.py`, `manifest_cache.py`, `chain_emit.py`, `view_status.py`, `gate_present.py`, `provenance_classes.py`.
- DO NOT dispatch to external models for `psychological_wavelength` — Claude only (data perimeter).
- The `generate` audit row format is fixed by loader.md §6.2 — adding fields requires a loader.md spec update first.

## Failure modes

- `list_macro_countries` fails: `HARDCODED_COVERAGE` from `maker.py`, noted in the summary.
- `unreachable_share > 0.30`: HARD ABORT before Step 4; no draft, no gate, no audit row.
- `ask-operator` absent, or no explicit confirmation this session: render the gate in prose and stop; nothing is saved (fails closed, conventions §14.3).
- `run-shell` absent: no save path; say so at Step 0.
- `abandon` at the gate: no save, no `generate` row.
- Forbidden key on the audit row: the maker raises; move the field to `provenance.yaml`.

## Done when

- The operator answered the shared gate through `ask-operator`, or the run ended at `abandon` / `--shadow-diff` / `--compare` / `--status` with no write.
- On confirm: `view.yaml`, `prose.md`, `provenance.yaml` written `0600`; one `generate` audit row appended with exactly the permitted fields; the reasoning chain emitted; the post-save summary rendered.
