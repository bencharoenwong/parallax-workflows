---
name: parallax-rebalance
description: "Portfolio rebalancing with health flags and macro context: analyze current state, flag issues, generate prioritized trade instructions with score rationale via Parallax MCP tools. Holdings as [{symbol, weight}]. NOT for initial portfolio construction (use /parallax-portfolio-builder), not for diagnostic-only review (use /parallax-client-review)."
---

<!-- white-label: integration-pattern.md -->

# Portfolio Rebalance

## When not to use

- Building a new portfolio from scratch → use /parallax-portfolio-builder
- Diagnostic review without trade recommendations → use /parallax-client-review
- Single stock analysis → use /parallax-should-i-buy

## Gotchas

- JIT-load _parallax/parallax-conventions.md for fallback patterns and parallel execution
- JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §3 (multipliers), §4 (conflict resolution), §5 (output rendering), §6 (audit). Tilts in the view become trade-direction signals: rebalancing should move portfolio toward view-tilted weights.
- When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer
- JIT-load ../parallax-client-review/references/recommendation-matrix.md for priority classification. If missing, use inline fallback: High=3+ flags (trim/exit), Medium=2 flags (investigate/trim), Low=1 flag (monitor/hold)
- Health flags feed directly into trade action determination — High priority = strong trim/exit
- analyze_portfolio is called twice with distinct field subsets (performance+risk, then concentration+attribution); see Batch A table for the required `portfolio=` + `fields=` shape. The parameters `holdings` and `lens` do not exist in the deployed schema. WARNING: responses often exceed 180K chars (daily time series). If output is truncated, too large, or MCP raises a schema validation error, fall back to `check_portfolio_redundancy` (concentration) + `quick_portfolio_scores` (factor tilt).
- build_stock_universe can find replacement candidates for positions being trimmed
- Output must include specific buy/sell/trim quantities, not just vague suggestions
- For portfolios with 10+ holdings, prioritize score trend scans for top/bottom 5 by weight to manage latency
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (6-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (Provenance) in Output Format.

Generate prioritized trade recommendations using health flags, macro context, and Parallax scores.

## Usage

```
/parallax-rebalance [{"symbol":"AAPL.O","weight":0.30},{"symbol":"MSFT.O","weight":0.25},{"symbol":"XOM.N","weight":0.20},{"symbol":"JNJ.N","weight":0.25}]
/parallax-rebalance [holdings] target="reduce concentration, improve quality score"
/parallax-rebalance [holdings] constraints="max 25% per position, no energy sector"
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, fallback patterns, and macro reasoning. JIT-load `_parallax/house-view/loader.md` for active-view validation and tilt application. JIT-load `../parallax-client-review/references/recommendation-matrix.md` for the priority system.

### Pre-flight: house-view drift check

JIT-load `_parallax/house-view/auto-on-load-judge-pattern.md` and follow
its protocol. If the protocol surfaces a banner, render it before
proceeding to this skill's main workflow.

Skip this pre-flight if invoked with `--skip-drift-check` or if no active
house view exists.

### Batch 0 — Tool Loading & Active House View

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

Per `loader.md` §1-§2: read view if present, validate hash and expiry. If view present, capture tilt vector + excludes. The view's tilts define **direction of rebalance** — current weights that diverge from view-tilted weights become rebalance candidates beyond the standard health-flag triggers. If validation fails or no view present, run rebalance using only health flags + macro context.

### Batch A — Current state (parallel, best-effort)

| Tool | Parameters | Notes |
|---|---|---|
| `analyze_portfolio` | `portfolio=[{date: <today ISO>, symbol: <ric>, weight: <w>}]`, `fields=["performance_metrics","rolling_metrics","drawdown_analysis","portfolio_summary","time_period_returns"]` | Returns/risk metrics. Build portfolio array from provided holdings; use today's date as as-of date. **Timeout fallback:** skip if exceeds 30s; fall back to `check_portfolio_redundancy` + `quick_portfolio_scores`. If MCP schema validation fails, use fallback immediately. |
| `analyze_portfolio` | `portfolio=[{date: <today ISO>, symbol: <ric>, weight: <w>}]`, `fields=["concentration_metrics","sector_allocation","company_contribution"]` | Concentration and attribution. Two separate field-subset calls to manage response size. **Timeout fallback:** skip if exceeds 30s. |
| `get_peer_snapshot` | per holding | **Primary scoring source** for `PARALLAX_LOADER_V2=1`. **Timeout handling:** fire in parallel; if N≥2 calls timeout, mark those holdings as "scores unavailable" and continue with health-flags-only scoring. Collect successful scores only. Aggregate client-side per `loader.md` §3b. **For 10+ holdings:** prioritize top/bottom 5 by weight; timeout on remaining holdings is acceptable — fall back to health flags for those positions. |
| `get_company_info` | per holding | **Ground-truth check oracle** per loader.md §5 rule 3 — records `expected_name` for mismatch check against `get_peer_snapshot.target_company`. **Timeout handling:** if timeout, mark holding as "name verification unavailable" and flag ⚠ UNVERIFIED. |
| `check_portfolio_redundancy` | `holdings` | Overlap detection. **Timeout fallback:** if exceeds 20s, flag "redundancy check skipped" and continue. |
| `list_macro_countries` | — | Check market coverage. **Timeout fallback:** skip if exceeds 5s. |
| `quick_portfolio_scores`| `holdings` | **Legacy/V1 path only**. Do NOT use if `PARALLAX_LOADER_V2=1` and view active. **Timeout fallback:** if exceeds 10s, degrade to health-flags-only scoring. |

**After Batch A** (best-effort completion):
1. Cross-check returned names against `get_company_info` results per loader.md §5 rule 3. For `PARALLAX_LOADER_V2=1`, any mismatch in `get_peer_snapshot` is flagged ⚠ MISMATCH and excluded from aggregate calculations. Unverified holdings (name check timeout) are flagged ⚠ UNVERIFIED.
2. For holdings with no scores (timeouts), scoring is determined by health flags only — these holdings cannot be ranked by factor scores and must be evaluated by "High/Medium/Low priority" categories based on flags alone.
3. Summary output: "Batch A completed: N/M holdings scored (M-N timeouts on peer snapshots). Rebalance will proceed with health-flag-driven recommendations for scoring-unavailable holdings."

### Batch B — Macro + score trends (after Batch A)

1. Call `macro_analyst` with component="tactical" for each unique covered market (cap 3).
2. Call `get_score_analysis` for each holding (parallel within batch) to identify deteriorating vs. improving positions. For 10+ holdings, prioritize top/bottom 5 by weight.

### Batch C — Health flags + trade decisions

1. Evaluate the 5 health flags **per holding** — binding flag conditions in `../parallax-client-review/references/recommendation-matrix.md` (same taxonomy and threshold values as `parallax-portfolio-checkup/references/health-flags.md`, whose canonical portfolio-level weighted-average definitions apply to portfolio-checkup, not here): Low Score (holding total score ≤5.0), Concentration (holding weight >15%, or holding among the top-3 when their combined weight >45%), Redundancy (holding is part of a redundant pair), Value Trap (holding value score ≤3.0), Macro Misalignment (holding's sector has a negative tactical outlook). Per-holding flag counts drive priority assignment.
2. **House-view alignment check** (if view active): for each holding, compute view-tilted target weight using loader.md §3 multipliers; flag holdings >25% off target as "View Misalignment." For holdings on `tilts.excludes`, flag as "View Excluded — must trim."
3. Assign priority per recommendation-matrix.md (count View Misalignment / View Excluded as flags):
   - **High** (3+ flags or View Excluded): Strong trim/exit candidate
   - **Medium** (2 flags): Investigate + potential trim
   - **Low** (1 flag): Monitor, hold unless constraints violated
4. Determine actions combining flags + score trends + macro + view tilts:
   - **Trim/Exit:** High priority holdings, View Excluded, or declining scores + any flag
   - **Hold:** Stable/improving scores, no flags, view-aligned
   - **Reweight:** Concentration flag only, OR view-tilted toward different weight than current
   - **Investigate:** Medium priority but ambiguous signal (suggest `/parallax-deep-dive`)
5. For trim candidates: Resolve user thesis vs. view per loader.md §4. If `PARALLAX_LOADER_V2=1` and view active, follow `loader.md` §3 "Application (V2)": decompose replacement theme into parallel per-sector calls, merge, and dedupe. If V1, prepend tilt context and call `build_stock_universe` once.
   - **Divergence assertion** (per loader.md §5 rule 4 — required universally): REQUIRED for V1 paths. If the query named N≥2 sectors/themes, compute `max_sector_share/total` in returned candidates. If > 0.6, emit fail-loud warning. If `PARALLAX_LOADER_V2=1`, use to verify merge quality.
   - **Ground-truth check per candidate** (per loader.md §5 rule 3): call `get_peer_snapshot` AND `get_company_info` in parallel. Drop any candidate where `returned_name ≠ expected_name` from the replacement pool (flag ⚠ MISMATCH, do not rank).
   - Filter remaining trusted candidates against `tilts.excludes` and `tilts.excludes_freeform`.

### Batch D — Validation

If `PARALLAX_LOADER_V2=1`, follow `loader.md` §3b: aggregate per-holding `get_peer_snapshot` scores for the proposed new allocation. If V1, call `quick_portfolio_scores`. If view active, verify proposed allocation aligns with view tilts within 10% per sector. Append audit log entry per loader.md §6.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (Provenance) when composing the Output Format. The loader returns exactly six keys; any other access (e.g. `branding["voice"]`) raises `KeyError` — structurally enforced by `loader.py`.

### Render — deterministic gate (LAST step, mandatory)

Compose the complete report per **Output Format** below, then run it through the shared render gate in **one Bash step** before replying. Use a private `mktemp` file (never a fixed/predictable path — `/tmp` symlink hazard). The shared gate is `_parallax/render_gate.py`, a sibling of the directory you loaded this SKILL.md from; pass this skill's key (use the loaded directory's absolute path as `<skill-dir>`):

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/rebal.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill rebalance < "$DRAFT"; rm -f "$DRAFT"
```

**Your entire final message is exactly that command's stdout** — nothing before it (no step/batch-completion notes, no scratch computation, no "no active house view" / white-label config-probe narration), nothing after it.

**Degraded-state rule:** if an async tool (e.g. `get_assessment`, `get_news_synthesis`) times out or returns no data, render the pending/unavailable note INSIDE the relevant section or the Provenance line — NOT as a preamble above the report — so it is part of the rendered body and survives the gate. (The gate also hoists a leaked degraded note as a backstop.)

`_parallax/render_gate.py` is pure-stdlib and deterministically drops anything before the first rendered block (House View Preamble banner / Branding Header / Ground-truth Integrity / this skill's title or first rendered section), preserving the active-house-view banner in every `view_status` state. Same operator-agnostic-helper pattern as `view_status.py` / `loader.py` (a real Bash tool call, not prose).

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** rebalance`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to Provenance.
- **Current Portfolio Assessment** (factor scores, concentration issues, redundancy; if view active, current alignment vs view-tilted target)
- **Health Status** (Healthy/Monitor/Attention badge with flag summary)
- **Verdict sensitivity** (render only when Health Status is Monitor or Attention): the 1-2 nearest-boundary flags and their arithmetic flip condition, per `parallax-portfolio-checkup/references/health-flags.md` "Verdict sensitivity" (renders `parallax-conventions.md` §11 by reference).
- **Health Flags** (table: each triggered flag per holding with priority level; View Misalignment / View Excluded shown as their own flag types)
- **Macro Context** (relevant market outlook, sector tilt implications for rebalancing)
- **Score Momentum** (table: each holding's score trend — improving/stable/declining)
- **Ground-truth Integrity** (only render if any mismatch detected — table: `input_ticker`, `returned_name`, `expected_name`, match status per holding. ⚠ MISMATCH rows are re-scored individually and flagged — scores not trusted from `quick_portfolio_scores` — per loader.md §5 rule 3.)
- **Trade Recommendations** (table: Priority | Action | Symbol | Current Weight | Target Weight | Rationale — every recommendation cites a specific flag or finding; if view active, "Rationale" includes view-tilt direction; any recommendation on a ⚠ MISMATCH holding must note scores were re-derived via `get_peer_snapshot` directly)
- **Replacement Candidates** (if trimming, scored alternatives; filtered against tilts.excludes + tilts.excludes_freeform if view active; all candidates ground-truth-validated per loader.md §5 rule 3; divergence-assertion result for replacement universe per loader.md §5 rule 4)
- **Before/After Comparison** (factor scores: current vs. proposed; if view active, alignment-to-view metric included)
- **Implementation Notes** (suggested execution order, liquidity considerations)
- **Provenance** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second Provenance line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.
