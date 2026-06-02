---
name: parallax-make-house-view
description: "Synthesize a draft Parallax house view by orchestrating macro_analyst + get_telemetry MCP outputs across the 14 covered markets, route the draft through the shared confirmation gate, and save through the same path /parallax-load-house-view uses. The synthesized view carries `generator_synthesis` provenance (distinct from ingested views' `prose_extraction`) and lands in `~/.parallax/active-house-view/` like any other house view. Use when the bank has no CIO take to ingest, when prepping a Parallax baseline for shadow-comparison against an active bank view, or to populate a fresh deployment. NOT for ingesting an existing CIO PDF (use /parallax-load-house-view), not for stress-testing an active view (use /parallax-stress-house-view), not for judging an active view against current Parallax signals (use /parallax-judge-house-view)."
negative-triggers:
  - Ingesting a CIO PDF / URL / wizard input → use /parallax-load-house-view
  - Judging an active view against live signals → use /parallax-judge-house-view
  - Stress-testing for internal consistency → use /parallax-stress-house-view
  - Per-cell diff of two saved views → use /parallax-house-view-diff
gotchas:
  - JIT-load `_parallax/house-view/MCP_FIELD_INVENTORY.md` BEFORE assuming any component input is available. `valuation_state` / `market_entropy` are prose-extracted; `psychological_wavelength` is LLM-judged. Confidence caps differ per component.
  - The shared gate (`_parallax/house-view/gate_present.py`) is REQUIRED — there is no save path that bypasses it. `--shadow-diff` skips the gate AND the save.
  - Fan-out budget is 14 markets × 5 components = 70 macro_analyst calls + 1 list_macro_countries + 1 get_telemetry. Concurrency cap 8. Per-market timeout 45s. Hard abort when unreachable_share > 30%.
  - Reuse `audit_chain.append_entry`, `chain_emit.emit_phase_0_chain`, `provenance_classes.validate_provenance_entry`. NEVER reimplement.
  - The `generate` audit row carries ONLY: schema_version, ts, view_id, version_id, view_hash, skill, action, applied, parent_version_id, provenance_hash, source_tools, calibration_status. composition_formula / aggregator_weights_ref / source_snippets / pillar_missing_inputs MUST go in `provenance.yaml`, NOT on the audit row.
  - `psychological_wavelength` judgment is Claude-only (data perimeter — telemetry contains CG-proprietary signals, do NOT dispatch to external models).
  - Synthesized views carry `auto_expire_days: 30` (shorter than ingested views' 90) because the underlying macro fan-out is point-in-time.
---

# Make House View

Synthesize a draft Parallax house view by orchestrating Parallax MCP tools (`list_macro_countries` + `macro_analyst` × 14 markets × 5 components + `get_telemetry`), aggregate cross-country, compose the four framework components (macro backdrop, valuation, market state, sentiment), route through the shared confirmation gate, and save through the same path `/parallax-load-house-view` uses.

The synthesized view lives in `~/.parallax/active-house-view/` and is consumed by every downstream skill (portfolio-builder, rebalance, thematic-screen, etc.) exactly like an ingested view — the only difference is the provenance class (`generator_synthesis` vs `prose_extraction`) and a shorter default `auto_expire_days`.

## Usage

```
/parallax-make-house-view                              # synthesize, route to gate, save
/parallax-make-house-view --shadow-diff                # synthesize, DO NOT save; diff vs active view
/parallax-make-house-view --basis "<hint>"             # bias synthesis with a textual hint
/parallax-make-house-view --markets us,japan,uk        # restrict fan-out scope (cost / debug)
/parallax-make-house-view --status                     # show last-generated view metadata
```

## Workflow

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call. JIT-load `_parallax/house-view/MCP_FIELD_INVENTORY.md` (per-pillar input availability), `_parallax/house-view/schema.yaml` (view shape + `classification_taxonomy.generator_synthesis`), and `_parallax/house-view/loader.md` (esp. §6 audit format with the new `generate` action).

### Step 1 — Resolve covered markets

Call `list_macro_countries()`. Expect 15 entries (14 country reports + "Global"). Exclude "Global" from per-country fan-out (it's an aggregate, would double-count). When `--markets` filter is set, intersect with the live coverage.

Fallback: if `list_macro_countries` fails, use the hardcoded `HARDCODED_COVERAGE` tuple in `maker.py` (14 markets matching `aggregator_weights.yaml`).

### Step 2 + 3 — Parallel fan-out

Fire in parallel (concurrency cap 8, per-call timeout 45s):

- **Step 2 (batch):** `macro_analyst(market=M, component=C)` for every (M, C) pair where M ∈ covered_markets and C ∈ {`macro_indicators`, `tactical`, `sectors`, `fixed_income`, `news`}. Budget: 14 × 5 = 70 calls.
- **Step 3 (single call, parallel with Step 2):** `get_telemetry(fields=["regime_tag", "divergences", "factor_view.factors", "factor_view.commentary", "signals", "commentary"])`.

Per-market timeout: 45s. A market that doesn't respond on ANY component within timeout is `UNREACHABLE` (use `stress.classify_mcp_meta_state` semantics). A market that returns a successful response with content like "Sector ranking data remains unavailable for this reporting period" is treated as **silent for that component**, not UNREACHABLE for the market (per MCP_FIELD_INVENTORY.md §5.4).

If `unreachable_share > 0.30` of the fan-out, HARD ABORT (v2 plan §2.2). Aggregation can't recover from that level of degradation.

### Step 4 — Cross-country aggregation

Call `cross_country.aggregate(per_market_responses, telemetry, weights)`. Outputs:

- `phi.value` / `phi.coverage_ok` / `phi.markets_with_data`: weighted-median of per-market `valuation_state` prose-extracted values when ≥ 60% of weight responded; else NULL + coverage_warning.
- `xi.value` etc.: same shape for `market_entropy`.
- `psi_news_blobs`: concatenated per-country news content for `psychological_wavelength` judgment.
- `regions.<schema_key>`: single-market region tilts (bypass coverage threshold per BUG-009).
- `sectors.<sector>`: cross-country weighted-median, coverage-gated.
- `macro_regime`: inferred growth/risk tokens from telemetry.regime_tag.
- `fan_out_summary`: market counts.

### Step 5 — Component composition

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

### Step 6 — Optional gap-fill finishing pass

OPTIONAL. After Steps 4-5, any residually silent leaves (e.g., sectors where coverage was below threshold but a single anchor market had a strong signal) MAY be folded via `gap_suggest.fold_responses`. Step 4-5 results win on conflict. **Skip in v0 — leave the hook for follow-up integration.**

### Step 7 — Shared confirmation gate

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

Bridge `dispose_fn` and `edit_fn` to `AskUserQuestion` exactly as `/parallax-load-house-view` Step 3 does — the module is shared.

Branch on `GateResult.disposition`:
- **`confirm`** / **`edited`** → Step 8 (save).
- **`regenerate`** → re-run from Step 2 with the basis hint updated; return to Step 7.
- **`abandon`** → no save, no audit `generate` row. Done.

### Step 8 — Save (reuses load-house-view Step 4 path)

Call `maker.MakerOrchestrator.save_view(...)`. This:

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

### Step 9 — Confirmation summary

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

## Shadow-diff mode

`/parallax-make-house-view --shadow-diff` runs Steps 1-6, then short-circuits Step 7/8. Instead of routing through the gate, it loads the currently-active bank view and renders an ADDITIVE diff via `shadow_diff.render_shadow_diff`. No save. The framing is critical — the bank's view is sovereign, the synthesis is offered as data to consider, never as a correction.

## Status mode

`/parallax-make-house-view --status` shows last-generated view metadata + the standard `view_status.banner` (same banner the loader emits). No MCP calls.

## Modules

- `maker.py` — orchestrator + save path. `MakerOrchestrator.execute_synthesis(mcp, dispose_fn, edit_fn)` is the entry point.
- `cross_country.py` — `aggregate(per_market_responses, telemetry, weights)` with 60% coverage rule.
- `pillar_compose.py` — `compute_pillars(aggregated, telemetry)` packaging.
- `pillar_formulas.py` — `compute_omega / compute_phi / compute_xi / compute_psi` (function names kept as field identifiers). Prose-based `valuation_state` / `market_entropy` per A0 findings. Confidence caps + missing-input rule.
- `prose_synth.py` — deterministic YAML → markdown narrative (no LLM).
- `shadow_diff.py` — `--shadow-diff` rendering.

## Hard constraints

- DO NOT modify any existing skill (load-house-view, house-view-diff, stress-house-view).
- DO NOT modify any shared infra (`audit_chain.py`, `manifest_cache.py`, `chain_emit.py`, `view_status.py`, `gate_present.py`, `provenance_classes.py`). Reuse only.
- DO NOT dispatch to external models for `psychological_wavelength` — Claude only (data perimeter).
- The `generate` audit row format is fixed by loader.md §6.2 — adding fields requires a loader.md spec update first.
