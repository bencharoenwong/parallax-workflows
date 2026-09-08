---
name: parallax-stress-house-view
description: "Stress-test the active CIO house view against fresh Parallax macro data and internal consistency. Emits a per-run report and a hash-chained audit entry. Optionally hands off to /parallax-load-house-view --edit to incorporate updates. NOT for portfolio construction (use /parallax-portfolio-builder), not for one-off scenario reactions (use /parallax-scenario-analysis)."
---

# Stress-Test Active House View

## When not to use

- Building a portfolio from a thesis → use /parallax-portfolio-builder
- Reacting to a one-off scenario (e.g. rate hike) → use /parallax-scenario-analysis
- Loading or editing a house view → use /parallax-load-house-view

## Gotchas

- This skill is read-only against the active house view. It never modifies the view directly.
- The --edit handoff to /parallax-load-house-view is a separate confirmation gate.
- JIT-load `_parallax/house-view/stress-test-design.md` for the 6 stress-test principles.
- JIT-load `_parallax/house-view/schema.yaml` for view structure.
- JIT-load `_parallax/house-view/loader.md` for audit log schema.
- JIT-load `_parallax/parallax-conventions.md` for MCP tool conventions.
- Every host interaction is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). The final CIO gate needs `ask-operator`; without it, render the summary in prose and stop at the four choices.
- The saved report and `stress.py` use the design doc's phase names (`Phase 0`–`Phase 4`, `Phase 4-B`); this file cites them as identifiers under the spine headings.

This skill compares the active CIO house view against fresh Parallax macro data and internal consistency rules. It produces a structured, CIO-facing report that classifies every divergence and surfaces key decision points.

## Workflow

Report-producer shape: the spine headings below. The four phases in `skills/_parallax/house-view/stress-test-design.md` are cited as identifiers because `stress.py`, `render.py`, and the saved report use them. There is no render-gate script: `render.render_artifact` writes the deterministic artifact.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `load-reference` `_parallax/house-view/stress-test-design.md`, `_parallax/house-view/schema.yaml`, `_parallax/house-view/loader.md`, `_parallax/parallax-conventions.md`.
3. `discover-tools`: bind `list_macro_countries`, `check_macro_health`, `get_telemetry`, `macro_analyst` to the exact callables and schemas exposed now (conventions §0.0–§0.1).
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` once before the first Parallax call; `ask-operator` = `AskUserQuestion`; `run-shell` = `Bash`.
   <!-- /host-note -->
4. Bind `run-shell` (`stress.py`, `render.py`), `ask-operator` (fan-out cap choice, final CIO gate), `read-config` (`$PARALLAX_HOUSE_VIEW_DIR`, else `~/.parallax/active-house-view/`).

### Step 1 — Resolve inputs (design Phase 0 and Phase 1)

1. **Load active view** — `run-shell` `stress.load_active_view()` from `skills/parallax-stress-house-view/stress.py`. It reads `view.yaml`, verifies the `audit.jsonl` hash chain, and computes the initial `view_hash`. No active view or a broken chain: exit with the clear message.
2. **Enumerate dimensions** — `stress.enumerate_dimensions()` lists every non-zero tilt; this fixes the markets and dimensions to check. Announce the scope: "Loaded view '<view_name>', age <N>d, <M> non-zero dimensions, <K> markets to query."
3. **Internal consistency (no MCP)** — `stress.evaluate_internal_rules()` runs the pure-Python checks in `skills/parallax-stress-house-view/internal_rules.yaml`. Any `hard_stop` rule: halt, render the internal consistency report, append a `halted_internal` entry via `stress.append_stress_audit()`. Only `taste` rules or none: announce "Internal consistency checks passed." and continue.

### Step 2 — Fetch (parallel batches)

1. **Market fan-out cap** — `stress.enforce_fanout_cap()` on the tilted markets from Step 1. Over the cap (12): `ask-operator` with the three choices from the design doc (stress all in batches, top-12, or cancel).
2. **Batch** — `call-tool` `list_macro_countries` once (the `covered_markets` set for Step 3), `check_macro_health` once globally, and per market together: `get_telemetry` and `macro_analyst` (summary). A view with macro tilts but no region tilts falls back to the primary market (per design doc).

### Step 3 — Verify (Closure 2: response meta-state)

    - For each MCP response returned from the Step 2 batch, call `stress.classify_mcp_meta_state(response, market, covered_markets)` where `covered_markets` is the set of market names from `list_macro_countries`.
    - The returned state is one of `"ok"`, `"PARALLAX_SILENT"`, `"UNCOVERED"`, `"UNREACHABLE"`.
    - If state ≠ `"ok"`, propagate that state into every (market × dim) cell resolution for this market — skip per-dim prose interpretation.
    - If state == `"ok"`, proceed with per-dim prose→sign interpretation as today before passing `parallax_view` to `resolve_cell_state`.

### Step 4 — Compute

1. **Resolve cell states**
    - Compute the age delta ONCE per run: `age_delta = stress.compute_age_delta(cio_age_days, parallax_age_days)` (where `cio_age_days = today − view.metadata.effective_date` and `parallax_age_days = today − check_macro_health.last_updated`).
    - For each (market, dimension) pair, invoke `stress.resolve_cell_state(cio_tilt, parallax_view, age_delta, market=<key>, covered_markets=<set from list_macro_countries>)`. `age_delta` is a required positional argument — there is no internal default; passing the wrong value silently misclassifies every cell.
    - The result will be one of the six states: `ALIGNED`, `DIVERGENT_STALE`, `DIVERGENT_FRESH`, `CIO_SILENT`, `PARALLAX_SILENT`, `UNCOVERED`.
2.  **Synthesize Themes**:
    - Analyze the results from Steps 1 and 3 to identify cross-dimension themes (e.g., a dimension flagged by both internal and external checks).
3.  **Build Recommended Deltas**:
    - Invoke `stress.build_recommended_deltas(resolutions, cio_age_days, parallax_age_days)` to produce the structured handoff payload. Pass into the audit append below AND the render call below.
4.  **Validate deltas before audit (Closure 3 gate):**
    - Call `stress.validate_recommended_deltas(deltas, schema_path)` where `schema_path` is `skills/_parallax/house-view/schema.yaml`.
    - On `ok=True`: proceed to audit with `disposition="completed"`; render the Phase 4-B section normally.
    - On `ok=False` AND no error has `index is None`: audit with `disposition="validation_failed"`, retain `recommended_deltas`, add `validation_errors: errors` field; render emits a "Phase 4-B suppressed — N deltas failed schema validation" callout listing each error.
    - On `ok=False` AND the single error has `index is None` (sentinel for schema-load failure): audit with `disposition="schema_unreadable"`, retain `recommended_deltas`, add the same `validation_errors: errors` field; render emits an install-issue callout naming the schema.yaml path.

### Step 5 — Compose (audit row + artifact)

1. **Append audit entry**
    - Invoke `stress.append_stress_audit(view, summary, applied=False, disposition="completed", recommended_deltas=...)`. Capture the returned entry dict.
    - Re-checks the full view identity (`view_hash` plus `view_id`/`version_id`) under the view transaction lock to guard against race conditions — see the `stress.append_stress_audit` docstring.
    - Compute the audit hash short form for the Phase 4-B citation: `audit_hash_short = audit_chain.compute_entry_hash(returned_entry)[:12]`.
2. **Render artifact**
    - Invoke `render.render_artifact(view_meta, internal_results, external_results, themes, view_hash, recommended_deltas=..., audit_hash_short=...)` from `skills/parallax-stress-house-view/render.py`.
    - Pass `audit_hash_short` from item 1 so the Phase 4-B section renders the specific `stress_test:<hash>` citation the CIO will paste into `basis_statement`.
    - This creates the detailed markdown report in `~/.parallax/active-house-view/stress-tests/`.

### Step 6 — Render (final CIO gate, design Phase 4)

1. **Present summary** — `ask-operator` shows the CIO the final summary report, including CIO Challenges, Taste Decisions, and Auto-Decided cells, as templated in the design doc.
2. **Handle the choice**
    - **A) Acknowledge**: Do nothing further. The `applied=false` audit entry is already written.
    - **B) Apply via manual handoff**: The artifact's Phase 4-B section lists the structured deltas. The same deltas are stored in the audit entry's `recommended_deltas` field. To apply, the CIO opens `/parallax-load-house-view --edit` (which opens `view.yaml` in `$EDITOR`), makes the changes, and in the confirmation gate's `basis_statement` cites this stress test by audit hash (`stress_test:<hash[:12]>`). The `load-house-view` skill runs its own confirmation gate and writes a `save` audit entry; this stress entry's `applied` remains `false` (audit chain shows `stress_test → save` on the same view family). **This handoff is documented and manual in v1; Option B in the design doc tracks the automated `--apply-stress <audit-hash>` flag for v2.**
    - **C) Interrogate**: Drill down into the specified cell, showing more data from the `macro_analyst` call, and re-present the gate.
    - **D) Defer**: Note the request and exit. (No scheduling daemon is implemented yet.)

## Failure modes

- No active view, or broken audit chain: exit at Step 1 with the standard message; no audit row.
- `hard_stop` internal rule: halt at Step 1 with the internal report and a `halted_internal` row; no MCP spend.
- Market over the fan-out cap and `ask-operator` unavailable: take the top-12 default and say so.
- `list_macro_countries` fails: `covered_markets` empty → every cell `UNCOVERED`; state it in the report.
- Delta validation `ok=False`: audit `validation_failed` or `schema_unreadable` (Step 4 item 4); never drop the deltas.
- View identity moved between Step 1 and the audit append: `append_stress_audit` refuses; re-run from Step 1.
- Host lacks a primitive: conventions §14.3, per primitive; the saved artifact is still written when `run-shell` exists.

## Done when

- One `stress_test` audit row appended with `applied=false` and a disposition; the markdown report exists under `stress-tests/` with the Phase 4-B citation `stress_test:<hash[:12]>`.
- The CIO saw the summary through `ask-operator` and chose A–D, or the run halted with its explanatory message.
- §9.2 disclosure and the disclaimer rendered in both the report and the summary.

## Output Format

The primary output is the interactive `ask-operator` gate in Step 6 (design Phase 4). If the process halts earlier (e.g., no active view, internal contradiction), a clear explanatory message is provided. A detailed markdown report is always saved to the `stress-tests` directory for later review.

**AI-interaction disclosure:** the saved markdown report and the Step 6 summary render AI-interaction disclosure per `parallax-conventions.md` §9.2 immediately above the standard disclaimer (§9.1, or the view-aware disclaimer per `house-view/loader.md` §5 rule 5/6 when an active view is loaded). The internal-consistency and drift classifications are LLM-interpreted and the report is read directly by the CIO/operator, so §9.2 applies — this skill does not qualify for the config-artifact exemption (see conventions §9.2 exemption rationale and judge-house-view's identical directive).

**Calibration disclosure:** this skill operates against views in `calibration_status: heuristic_phase0`. Cell resolutions and recommended deltas are heuristic; intended for directional research only — do not use for regulatory capital, fiduciary-grade portfolio construction, or client-facing recommendations without further validation.
