---
name: parallax-stress-house-view
description: "Stress-test the active CIO house view against fresh Parallax macro data and internal consistency. Emits a per-run report and a hash-chained audit entry. Optionally hands off to /parallax-load-house-view --edit to incorporate updates. NOT for portfolio construction (use /parallax-portfolio-builder), not for one-off scenario reactions (use /parallax-scenario-analysis)."
negative-triggers:
  - Building a portfolio from a thesis → use /parallax-portfolio-builder
  - Reacting to a one-off scenario (e.g. rate hike) → use /parallax-scenario-analysis
  - Loading or editing a house view → use /parallax-load-house-view
gotchas:
  - This skill is read-only against the active house view. It never modifies the view directly.
  - The --edit handoff to /parallax-load-house-view is a separate confirmation gate.
  - JIT-load `_parallax/house-view/stress-test-design.md` for the 6 stress-test principles.
  - JIT-load `_parallax/house-view/schema.yaml` for view structure.
  - JIT-load `_parallax/house-view/loader.md` for audit log schema.
  - JIT-load `_parallax/parallax-conventions.md` for MCP tool conventions.
---

# Stress-Test Active House View

This skill compares the active CIO house view against fresh Parallax macro data and internal consistency rules. It produces a structured, CIO-facing report that classifies every divergence and surfaces key decision points.

## Workflow

The stress test runs in four phases, as defined in `skills/_parallax/house-view/stress-test-design.md`.

### Phase 0: Intake and Scoping

1.  **Load Active View**:
    - Invoke the `stress.load_active_view()` function from `skills/stress-house-view/stress.py`.
    - This function reads `~/.parallax/active-house-view/view.yaml`, verifies the `audit.jsonl` hash chain, and computes the initial `view_hash`.
    - If no view is active or the audit chain is broken, the skill will exit with a clear message.
2.  **Enumerate Dimensions**:
    - Invoke `stress.enumerate_dimensions()` to create a list of all non-zero tilts in the view.
    - This determines which markets and dimensions need to be checked.
    - Announce the scope: "Loaded view '<view_name>', age <N>d, <M> non-zero dimensions, <K> markets to query."

### Phase 1: Internal Consistency Check (No MCP)

1.  **Evaluate Rules**:
    - Invoke `stress.evaluate_internal_rules()` from `skills/stress-house-view/stress.py`.
    - This function runs pure-Python checks against the view YAML using the rules defined in `skills/stress-house-view/internal_rules.yaml`.
2.  **Handle Results**:
    - If any `hard_stop` rule is triggered, the process halts. Render the internal consistency report and append a `halted_internal` entry to the audit log using `stress.append_stress_audit()`.
    - If only `taste` rules are triggered or no rules are triggered, announce "Internal consistency checks passed." and proceed to Phase 2.

### Phase 2: External Comparison vs. Parallax (MCP)

1.  **Tool Loading**:
    - Call `ToolSearch` with query `"+Parallax"` once to load all Parallax MCP tool schemas.
2.  **Market Fan-out**:
    - Get the list of tilted markets from Phase 0.
    - Invoke `stress.enforce_fanout_cap()` to check if the number of markets exceeds the cap (12).
    - If it exceeds the cap, use `AskUserQuestion` to prompt the user with the three choices from the design doc (stress all in batches, top-12, or cancel).
3.  **Batch MCP Calls**:
    - For each market to be queried, execute the following MCP calls in parallel:
        - `mcp__claude_ai_Parallax__check_macro_health` (once globally)
        - `mcp__claude_ai_Parallax__get_telemetry`
        - `mcp__claude_ai_Parallax__macro_analyst` (summary)
    - If the view has no region tilts but has macro tilts, fall back to the primary market (per design doc).
4.  **Classify Response Meta-state (Closure 2)**:
    - For each MCP response returned from Step 3's batch fan-out, call `stress.classify_mcp_meta_state(response, market, covered_markets)` where `covered_markets` is the set of market names from `list_macro_countries`.
    - The returned state is one of `"ok"`, `"PARALLAX_SILENT"`, `"UNCOVERED"`, `"UNREACHABLE"`.
    - If state ≠ `"ok"`, propagate that state into every (market × dim) cell resolution for this market — skip per-dim prose interpretation.
    - If state == `"ok"`, proceed with per-dim prose→sign interpretation as today before passing `parallax_view` to `resolve_cell_state`.
5.  **Resolve Cell States**:
    - Compute the age delta ONCE per run: `age_delta = stress.compute_age_delta(cio_age_days, parallax_age_days)` (where `cio_age_days = today − view.metadata.effective_date` and `parallax_age_days = today − check_macro_health.last_updated`).
    - For each (market, dimension) pair, invoke `stress.resolve_cell_state(cio_tilt, parallax_view, age_delta, market=<key>, covered_markets=<set from list_macro_countries>)`. `age_delta` is a required positional argument — there is no internal default; passing the wrong value silently misclassifies every cell.
    - The result will be one of the six states: `ALIGNED`, `DIVERGENT_STALE`, `DIVERGENT_FRESH`, `CIO_SILENT`, `PARALLAX_SILENT`, `UNCOVERED`.

### Phase 3: Synthesis and Audit

1.  **Synthesize Themes**:
    - Analyze the results from Phase 1 and Phase 2 to identify cross-dimension themes (e.g., a dimension flagged by both internal and external checks).
2.  **Build Recommended Deltas**:
    - Invoke `stress.build_recommended_deltas(resolutions, cio_age_days, parallax_age_days)` to produce the structured handoff payload. Pass into the audit append below AND the render call below.
3.  **Validate deltas before audit (Closure 3 gate):**
    - Call `stress.validate_recommended_deltas(deltas, schema_path)` where `schema_path` is `skills/_parallax/house-view/schema.yaml`.
    - On `ok=True`: proceed to audit with `disposition="completed"`; render Phase 4-B normally.
    - On `ok=False` AND no error has `index is None`: audit with `disposition="validation_failed"`, retain `recommended_deltas`, add `validation_errors: errors` field; render emits a "Phase 4-B suppressed — N deltas failed schema validation" callout listing each error.
    - On `ok=False` AND the single error has `index is None` (sentinel for schema-load failure): audit with `disposition="schema_unreadable"`, retain `recommended_deltas`, add the same `validation_errors: errors` field; render emits an install-issue callout naming the schema.yaml path.
4.  **Append Audit Entry**:
    - Invoke `stress.append_stress_audit(view, summary, applied=False, disposition="completed", recommended_deltas=...)`. Capture the returned entry dict.
    - Re-checks the `view_hash` to guard against race conditions.
    - Compute the audit hash short form for the Phase 4-B citation: `audit_hash_short = audit_chain.compute_entry_hash(returned_entry)[:12]`.
5.  **Render Artifact**:
    - Invoke `render.render_artifact(view_meta, internal_results, external_results, themes, view_hash, recommended_deltas=..., audit_hash_short=...)` from `skills/stress-house-view/render.py`.
    - Pass `audit_hash_short` from step 3 so the Phase 4-B section renders the specific `stress_test:<hash>` citation the CIO will paste into `basis_statement`.
    - This creates the detailed markdown report in `~/.parallax/active-house-view/stress-tests/`.

### Phase 4: Final CIO Gate

1.  **Present Summary**:
    - Use `AskUserQuestion` to show the CIO the final summary report, including CIO Challenges, Taste Decisions, and Auto-Decided cells, as templated in the design doc.
2.  **Handle User Choice**:
    - **A) Acknowledge**: Do nothing further. The `applied=false` audit entry is already written.
    - **B) Apply via manual handoff**: The artifact's Phase 4-B section lists the structured deltas. The same deltas are stored in the audit entry's `recommended_deltas` field. To apply, the CIO opens `/parallax-load-house-view --edit` (which opens `view.yaml` in `$EDITOR`), makes the changes, and in the confirmation gate's `basis_statement` cites this stress test by audit hash (`stress_test:<hash[:12]>`). The `load-house-view` skill runs its own confirmation gate and writes a `save` audit entry; this stress entry's `applied` remains `false` (audit chain shows `stress_test → save` on the same view family). **This handoff is documented and manual in v1; Option B in the design doc tracks the automated `--apply-stress <audit-hash>` flag for v2.**
    - **C) Interrogate**: Drill down into the specified cell, showing more data from the `macro_analyst` call, and re-present the gate.
    - **D) Defer**: Note the request and exit. (No scheduling daemon is implemented yet.)

## Output Format

The primary output is the interactive `AskUserQuestion` gate in Phase 4. If the process halts earlier (e.g., no active view, internal contradiction), a clear explanatory message is provided. A detailed markdown report is always saved to the `stress-tests` directory for later review.
