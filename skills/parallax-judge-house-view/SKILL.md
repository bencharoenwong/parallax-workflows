---
name: parallax-judge-house-view
description: "Read-only LLM-as-judge that compares the saved CIO house view against current Parallax macro signals, classifies drift severity (minor / moderate / material), and recommends per-cell updates with cited rationale. Emits a self-contained report bundle and a single audit row; NEVER modifies the active view. NOT for synthesizing a view from scratch (use /parallax-make-house-view), not for portfolio construction (use /parallax-portfolio-builder), not for one-off scenario reactions (use /parallax-scenario-analysis)."
---

# Judge Active House View

## When not to use

- Synthesizing a new house view from MCP signals → use /parallax-make-house-view
- Building a portfolio from a thesis → use /parallax-portfolio-builder
- Editing the saved view → use /parallax-load-house-view --edit
- One-off scenario / what-if → describe inline to the portfolio skill, don't run the judge
- Internal-consistency stress test (CIO contradictions inside the view itself) → use /parallax-stress-house-view

## Gotchas

- This skill is READ-ONLY against the active house view. It never writes to view.yaml or provenance.yaml. Only audit.jsonl gets a new row (action="judge", applied=false ALWAYS) and the judge-reports bundle directory gets a new entry.
- JIT-load `_parallax/house-view/loader.md` for the audit-row schema (§6.1 / §6.2) and the conditional fields for action="judge".
- JIT-load `_parallax/house-view/schema.yaml` for the view structure + `classification_taxonomy.judge_recommendation` (judge does NOT write this class into provenance.yaml — it only emits it in the report; promotion happens via /parallax-load-house-view --edit).
- JIT-load `_parallax/house-view/MCP_FIELD_INVENTORY.md` to understand what the maker can actually extract — informs which cells the judge can confidently recommend on.
- JIT-load `_parallax/parallax-conventions.md` for MCP tool conventions and batch patterns.
- Phase 5 LLM recommendations go through `recommendation.validate_citation` post-call. Recommendations whose rationale does NOT contain a >=30-char verbatim substring of the source snippet are DROPPED and replaced with a "judge declined to recommend (citation check failed)" placeholder. This is the single biggest hallucination control — do NOT bypass it.
- The judge does NOT use `gate_present.run_gate_loop` — there is no confirmation gate. It's a read-only report.
- Maker shared modules (`cross_country`, `pillar_compose`, `pillar_formulas`) are imported lazily; if Phase B1 hasn't shipped, the orchestrator surfaces the gap in diagnostics and falls back to PARALLAX_SILENT for cells where the imputed view can't be computed.
- Server-side `house_view_judge` MCP tool: CANCELLED (2026-05-24). The judge is client-side permanently — bank clients run this skill / CLI on their own side. See v2 plan §3.2 for rationale (transparency for model-validation review, zero cross-tenant blast radius). Do NOT resurrect the server-side framing without a new architectural decision.
- Auto-on-load triggers (portfolio-builder, rebalance, thematic-screen) suppress the run when `view_age_days < cadence.AUTO_ON_LOAD_MIN_AGE_DAYS` (30 days). Banner only at drift_material.

This skill compares the active CIO house view against fresh Parallax macro signals, classifies drift severity, and recommends per-cell updates with cited rationale. It is **read-only**: the active view is never modified. The output is one append-only audit row, one report bundle, and one reasoning chain.

## When to use

- Bank CIO wants to know if the loaded house view has gone stale relative to current Parallax signals.
- Consumer skill (portfolio-builder, rebalance, thematic-screen) auto-invokes when the active view is older than 30 days (banner only at `drift_material`).
- Scheduled / cron job (bank-side) runs `/parallax-judge-house-view --json` against a locally-mounted view and pipes the output to a downstream monitor.

## When NOT to use

- Synthesizing a view from scratch — use `/parallax-make-house-view`.
- Editing the saved view — use `/parallax-load-house-view --edit`.
- Checking internal consistency of the view itself (without comparing to Parallax) — use `/parallax-stress-house-view`.

## CLI

```
/parallax-judge-house-view                # full judgment of active view
/parallax-judge-house-view --pillars-only # skip per-cell table; pillar drift only
/parallax-judge-house-view --json         # structured output for cron/automation
/parallax-judge-house-view --dry          # use mocked MCP responses (CI/tests)
```

The `--dry` flag skips the LLM Phase 5 recommendation step and returns deterministic drift severity from MCP signals alone. `--mock-mcp <path>` is independent — it replaces the live MCP fan-out with a canned JSON payload keyed by `tool:arg1:arg2:...` summary strings (for tests or CI). Either flag can be used alone or together.

**Cost:** ~352 tokens at the default market set (~14 markets × 5 components; see `_parallax/token-costs.md`). `--dry` skips the Phase 5 LLM step but NOT the Phase 1 macro fan-out — the full ~352-token cost is still incurred.

## Workflow (Phases 0-8 per v2 plan §3.1)

### Phase 0 — Load active view

Invoke `judge.phase_0_load_view()`, which wraps `stress.load_active_view()`. This:

- Reads `~/.parallax/active-house-view/view.yaml`.
- Verifies the `audit.jsonl` hash chain (raises on broken chain).
- Computes `view_hash`.

**Halt conditions:** view directory missing → exit with the standard "no active view" message. Chain broken → propagate the audit_chain error.

### Phase 1 — MCP fan-out

Same recipe as the maker: 14 markets × 5 components (`macro_indicators`, `tactical`, `sectors`, `fixed_income`, `news`) + 1 `get_telemetry` call. Concurrency capped at 8.

**Per-market timeout:** 45s. UNREACHABLE markets are classified via `stress.classify_mcp_meta_state` and weighted to 0 by the maker's aggregator. If unreachable_share > 30% across markets, the maker raises; the judge surfaces this in `diagnostics` and falls back to PARALLAX_SILENT.

**PARTIAL responses** (`success=True` with prose like "data unavailable"): treat as silent — not UNREACHABLE.

When `mock_mcp_responses` is provided (via `--mock-mcp <path>` or programmatic injection), it replaces the live MCP fan-out verbatim regardless of `--dry`; otherwise the runtime delegates to the injected `mcp_call_fn`. `--dry` is orthogonal — it only suppresses the Phase 5 LLM recommendation call, not the MCP source.

### Phase 2 — Per-cell diff

For each non-zero cell in the active view (enumerated via `stress.enumerate_dimensions`), call `stress.resolve_cell_state(cio_tilt, parallax_view, age_delta, market=..., covered_markets=...)`. States:

- `ALIGNED`
- `DIVERGENT_FRESH` (sign mismatch; views are not stale)
- `DIVERGENT_STALE` (sign mismatch; view is stale relative to Parallax)
- `CIO_SILENT` (uploader has no view; Parallax does)
- `PARALLAX_SILENT` (uploader has a view; Parallax silent)
- `UNCOVERED` (market not in Parallax coverage)

`parallax_view` per cell comes from the **imputed view** — `cross_country.aggregate` + `pillar_compose.compute_pillars` applied to the MCP fan-out. If the maker modules aren't installed yet, the orchestrator returns PARALLAX_SILENT for every cell and notes the gap in diagnostics.

### Phase 3 — Severity classification

Run `drift_classify.classify_severity(resolutions, view_age_days, denominator)`. Tiers:

- `drift_minor`: < 20% of non-zero cells in `DIVERGENT_*`
- `drift_moderate`: 20-50%
- `drift_material`: > 50%, OR any `DIVERGENT_*` on a pillar, OR sign-flip on `tilts.macro_regime.*`

**Magnitude escalation:** any `|cio_value - parallax_value| >= 3` bumps severity one tier (minor → moderate → material). Capped at `drift_material` (the `drift_breaking` slot is reserved for future tightening).

### Phase 4 — Build recommended deltas

Call `stress.build_recommended_deltas(resolutions, cio_age, parallax_age, include_fresh=True)`. Per A1 work:

- DIVERGENT_FRESH cells get `kind="informational_fresh"`
- DIVERGENT_STALE cells get `kind="informational"` (unchanged)
- All pass `stress.validate_recommended_deltas` (allowlist already extended).

### Phase 5 — LLM-as-judge recommendations (material+ severity only)

For the cells at `drift_material` (or stricter), the orchestrator:

1. Calls `recommendation.build_recommendation_prompt(...)` for EVERY material cell first — each prompt is built only from its own cell's snippet, so the cells are mutually independent.
2. Dispatches those cells to Claude via the runtime-injected `llm_call_fn` in parallel where the runtime supports concurrent dispatch; ordering within the batch is immaterial because no cell reads another's output and Phase 6/7 consume the completed set. Each response is validated by `recommendation.validate_citation` (step 3 below) as it returns — parallelism does NOT touch or weaken the per-cell >=30-char verbatim-substring check.
3. **Validates the citation via `recommendation.validate_citation`.** The LLM's `rationale` (or any `evidence_refs` entry) MUST contain a >=30-char verbatim substring of the source snippet. Honest declines (`recommended_value=null` + "insufficient evidence" rationale) bypass the substring check.
4. On validation failure, the recommendation is dropped and replaced with `recommendation.make_decline_placeholder(...)`. The decline marker (`"judge declined to recommend (citation check failed)"`) is visible in both the report and the audit row.

**Prompt template:** see `recommendation.SYSTEM_PROMPT` + `build_recommendation_prompt`. The structured-output schema constrains `recommended_value ∈ {-2,-1,0,1,2,null}`, `confidence ∈ [0,1]`, `rationale ≤ 300 chars`, `suggested_basis_statement_addendum ≤ 100 chars`.

**Do not weaken the citation validator.** No bypass flag, no debug knob. Loosening to "semantic match" would re-introduce the hallucination surface the validator exists to close.

### Phase 6 — Render report bundle

Write to `~/.parallax/judge-reports/<judged_version_id>-<judged_at>/`:

- `report.md` — client-facing markdown (severity verdict, per-cell table, recommendations)
- `report.json` — structured form for cron / automation consumption
- `mcp_responses.jsonl` — one line per MCP call: `{call: "tool:args", response: ...}`
- `reasoning_chain.yaml` — written by `chain_emit` (Phase 8), lives under `~/.parallax/reasoning-chains/`
- `audit_entry.json` — copy of the appended audit row for offline auditors

### Phase 7 — Append single audit row

Per `loader.md §6.1/§6.2`, append exactly one row with:

```json
{
  "schema_version": 1,
  "ts": "...",
  "view_id": "...",
  "version_id": "...",
  "view_hash": "...",
  "skill": "parallax-judge-house-view",
  "action": "judge",
  "applied": false,
  "judged_view_id": "...",
  "judged_version_id": "...",
  "view_age_days": 42,
  "parallax_age_days": 3,
  "drift_summary": {
    "aligned_count": 7,
    "drift_minor_count": 3,
    "drift_material_count": 0,
    "drift_breaking_count": 0,
    "parallax_silent_count": 2,
    "uncovered_count": 0
  },
  "recommendations": [/* deltas from Phase 4 */]
}
```

`applied` is ALWAYS `false` for `action="judge"`. The judge never modifies the view. Acceptance happens later, manually, via `/parallax-load-house-view --edit` citing the judge's audit hash in the `basis_statement` (a future `--apply-judge <audit-hash>` flag will automate this).

### Phase 8 — Emit reasoning chain

Call `chain_emit.emit_phase_0_chain` with:

- `skill_version="parallax-judge-house-view@1.0.0"`
- `skill="parallax-judge-house-view"`
- `base_scores={"response_inline": <mcp responses dict>, "response_hash": <sha256 of sorted JCS concat>}`
- `final_portfolio={"weights": {}}` (judge produces no portfolio; chain spec §3.5 allows empty weights)

The chain artifact lands in `~/.parallax/reasoning-chains/<YYYY-MM>/<run_id>.yaml`. Replayable: the `response_hash` is the determinism anchor.

## Trigger sources (`cadence.py`)

| Trigger | When | Notes |
|---|---|---|
| `on_demand` | explicit `/parallax-judge-house-view` | full pipeline always runs |
| `auto_on_load` | consumer skill (portfolio-builder, rebalance, thematic-screen) auto-invokes | gated on `view_age_days >= 30`; banner only at `drift_material`; cache TTL 1h |
| `scheduled` | bank cron via `--json` | same pipeline, JSON-only output |

## Output

Primary output is the markdown report at `~/.parallax/judge-reports/<bundle>/report.md`. In `--json` mode, the JSON sidecar is also written to stdout for downstream consumption. The audit row is the canonical machine surface.

**AI-interaction disclosure:** `report.md` ends with the banner rendered per `parallax-conventions.md` §9.2. The per-cell judgments and Phase 5 recommendations are LLM-generated and the report is read directly by a natural person (the CIO/operator), so §9.2 applies even though this is an operator-facing artifact — the skill does NOT qualify for the config-artifact exemption (it emits an analysis report, not a gated configuration bundle; see conventions §9.2 exemption rationale). The `--json` sidecar is machine-consumed and carries no banner.

## Not on the roadmap

- **Server-side `house_view_judge` MCP tool** — **CANCELLED, not deferred.** The judge runs client-side only. Bank clients schedule their own cron against `/parallax-judge-house-view --json` on their side. Rationale: methodology transparency for model-validation review (same reason maker is client-side), and zero cross-tenant blast radius from a broken judge run. See v2 plan §3.2.

## Deferred (still on roadmap)

- **`/parallax-load-house-view --apply-judge <audit-hash>`** — the future flag that auto-populates an edit draft from the audit row's `recommendations` field. Schema is already in place (`recommendations` carries the same shape as stress's `recommended_deltas`).

## Calibration disclosure

This skill operates against views in `calibration_status: heuristic_phase0`. The per-cell recommendations and severity thresholds are heuristic; intended for directional research only — do not use for regulatory capital, fiduciary-grade portfolio construction, or client-facing recommendations without further validation.
