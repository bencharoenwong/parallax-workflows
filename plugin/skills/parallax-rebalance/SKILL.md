---
name: parallax-rebalance
description: "Portfolio rebalancing with health flags and macro context: analyze current state, flag issues, generate a prioritized, information-framed rebalancing analysis (candidate actions per conventions §12) with score rationale via Parallax MCP tools. Holdings as [{symbol, weight}]. NOT for initial portfolio construction (use /parallax-portfolio-builder), not for diagnostic-only review (use /parallax-client-review)."
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
- Call `analyze_portfolio` at most once. Build its request from the discovered live schema and request only compact current-state/concentration blocks; never request rolling, drawdown, return-period, benchmark-price, or other daily time-series blocks in the normal rebalance path. If the capability is absent, the request cannot be mapped unambiguously, the response is oversized/truncated, or schema/field validation fails, do not retry it with a guessed shape — use discovered concentration/scoring fallbacks.
- build_stock_universe can find replacement candidates for positions being trimmed
- Output must include specific candidate weight changes, framed per conventions §12 (analysis, not instructions), not just vague suggestions
- For portfolios with 10+ holdings, prioritize score trend scans for top/bottom 5 by weight to manage latency
- When `policy=` is supplied, JIT-load `_parallax/client-policy/policy-loader.md` and run Batch C2. The S3 solver (`_parallax/client-policy/reconcile.py`) needs scipy and **fails closed** without it — `solver_unavailable` renders UNVERIFIED per conventions §4.0, never a partial trade list. Deterministic math lives in the helper; never reproduce the LP in prose.
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (7-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (About This Report) in Output Format. Audience mode resolution (§13.1) is a separate seam call, not a dict read of `branding["render"]`: this skill does not use the RM seam (`rm_consumer.py::load_rm_branding_context`) for branding, but it DOES call that module's `resolve_audience()` function directly, via the one Bash `python3 -c` step documented under Pre-Render — never re-derive the §13.1 precedence in prose.

Generate prioritized trade recommendations using health flags, macro context, and Parallax scores.

## Usage

```
/parallax-rebalance [{"symbol":"AAPL.O","weight":0.30},{"symbol":"MSFT.O","weight":0.25},{"symbol":"XOM.N","weight":0.20},{"symbol":"JNJ.N","weight":0.25}]
/parallax-rebalance [holdings] target="reduce concentration, improve quality score"
/parallax-rebalance [holdings] constraints="max 25% per position, no energy sector"
/parallax-rebalance [holdings] policy=path/to/client-policy.yaml
/parallax-rebalance [holdings] audience=client_safe
```

`policy=` accepts the same client-policy artifact `parallax-client-review`
consumes (inline YAML/JSON or a file path; schema in
`_parallax/client-policy/schema.yaml`). When supplied, Batch C2 runs the S3
reconciliation optimizer and its targets replace the multiplier-derived ones.

Optional `audience=` argument: `client_safe | internal_analyst`; precedence follows `parallax-conventions.md` §13.1.

## Workflow

Execute with the exact Parallax callables and input schemas exposed by live capability discovery in the current runtime. Logical tool names below describe intent; they are not a fixed MCP namespace or permission to use a stale request shape. JIT-load `_parallax/parallax-conventions.md` for discovery, execution mode, fallback patterns, and macro reasoning. JIT-load `_parallax/house-view/loader.md` for active-view validation and tilt application. JIT-load `../parallax-client-review/references/recommendation-matrix.md` for the priority system.

### Pre-flight: house-view drift check

JIT-load `_parallax/house-view/auto-on-load-judge-pattern.md` and follow
its protocol. If the protocol surfaces a banner, render it before
proceeding to this skill's main workflow.

Skip this pre-flight if invoked with `--skip-drift-check` or if no active
house view exists.

### Batch 0 — Live Capability Discovery & Active House View

Use the host's live discovery surface per conventions §0.1 (`ToolSearch` with `"+Parallax"` in Claude Code). Build a session-local map from each logical capability used below to the exact callable name and live input schema returned now. Live discovery overrides every namespace, parameter, and schema example in this file. Do not synthesize missing callables from a remembered server alias.

Classify failures before any retry: a transient transport/cancellation/empty-success may retry only the affected call once; tool-not-found, schema-validation, or response `invalid_fields` failures do not permit a same-payload or guessed-shape retry. Use a discovered fallback and record the affected coverage instead.

Per `loader.md` §1-§2: read view if present, validate hash and expiry. If view present, capture tilt vector + excludes. The view's tilts define **direction of rebalance** — current weights that diverge from view-tilted weights become rebalance candidates beyond the standard health-flag triggers. If validation fails or no view present, run rebalance using only health flags + macro context.

### Batch A — Current state (parallel, best-effort)

The parameter column states the semantic intent. Construct every payload from that callable's discovered live schema, using only advertised keys and types. If the schema cannot represent the intent unambiguously, treat that logical capability as unavailable and follow its fallback without probing guessed variants.

| Tool | Parameters | Notes |
|---|---|---|
| `analyze_portfolio` | Map the supplied symbol/weight holdings into the live schema. If `fields` is advertised, request the compact intersection of `portfolio_summary`, `concentration_metrics`, `sector_allocation`, and `company_contribution`; omit time-series blocks. | **Exactly one call maximum.** Supply a `date` per holding only when the discovered live schema requires one. The date is an as-of date over a price history, not a snapshot key: a deployed connector may need a date early enough that each holding has sufficient prior price history, so today's date can return empty or fail validation. Read the live schema's own description first. When the schema gives no guidance, date every holding at the most recent completed trading day at least 5 calendar days in the past, one date for all holdings, and state the date used in the report — live schema still wins over this default. Skip after 30s, oversized/truncated output, schema validation, or any non-empty `result._meta.invalid_fields`; do not retry this capability. Use discovered `check_portfolio_redundancy` for overlap/concentration and per-holding score aggregation for factor context. |
| `get_peer_snapshot` | per holding | **Primary scoring source** for `PARALLAX_LOADER_V2=1`. **Timeout handling:** fire in parallel; if N≥2 calls timeout, mark those holdings as "scores unavailable" and continue with health-flags-only scoring. Collect successful scores only. Aggregate client-side per `loader.md` §3b. **For 10+ holdings:** prioritize top/bottom 5 by weight; timeout on remaining holdings is acceptable — fall back to health flags for those positions. **Distinguish a timeout from an empty response:** a timeout leaves the holding unscored and health-flag-driven per the handling above. A successful call that carries no data for the listing is a coverage gap, not a timeout — fall back to `get_company_info` plus `get_score_analysis` for that holding, label every figure derived this way a **profile-derived score**, and name every profile-derived holding in the report. See the Batch C2 coefficient bullet for the same-scale guard required before a profile-derived score enters the solver. |
| `get_company_info` | per holding | **Ground-truth check oracle** per loader.md §5 rule 3 — records `expected_name` for mismatch check against `get_peer_snapshot.target_company`. **Timeout handling:** if timeout, mark holding as "name verification unavailable" and flag ⚠ UNVERIFIED. |
| `get_score_analysis` | per holding | Score trend (improving/stable/declining) for the Score Momentum table and the Exit classification. Input is symbol + weeks only — no Batch A dependency, so it fires here in parallel. **For 10+ holdings:** prioritize top/bottom 5 by weight. **Timeout handling:** mark the holding's trend "unavailable" and continue. |
| `check_portfolio_redundancy` | Map the normalized holdings into the live schema. | Overlap detection and the compact fallback when `analyze_portfolio` is unavailable. **Timeout fallback:** if exceeds 20s, flag "redundancy check skipped" and continue. When `analyze_portfolio.sector_allocation` also came back, cross-check the two sector breakdowns per "After Batch A" item 4 before rendering either. |
| `list_macro_countries` | — | Check market coverage. **Timeout fallback:** skip if exceeds 5s. |
| `quick_portfolio_scores`| Map the normalized holdings into the live schema. | **Discovered Legacy/V1 fallback only.** Do NOT use if `PARALLAX_LOADER_V2=1` and view active. **Timeout fallback:** if exceeds 10s, degrade to health-flags-only scoring. A successful call with no data for a listing (distinct from a timeout) is the same coverage-gap case as the `get_peer_snapshot` row above — fall back to `get_company_info` plus `get_score_analysis` for that holding and label it a **profile-derived score**. |

**After Batch A** (best-effort completion):
1. Cross-check returned names against `get_company_info` results per loader.md §5 rule 3. For `PARALLAX_LOADER_V2=1`, any mismatch in `get_peer_snapshot` is flagged ⚠ MISMATCH and excluded from aggregate calculations. Unverified holdings (name check timeout) are flagged ⚠ UNVERIFIED.
2. For holdings with no scores (timeouts), scoring is determined by health flags only — these holdings cannot be ranked by factor scores and must be evaluated by "High/Medium/Low priority" categories based on flags alone.
3. Summary output: "Batch A completed: N/M holdings scored (M-N unavailable or timed out). Portfolio snapshot: available/fallback/unavailable. Rebalance will proceed with health-flag-driven recommendations for scoring-unavailable holdings." Keep this execution receipt inside the rendered report only where the Output Format calls for the information; never leak it as pre-report scaffold. Under `audience=client_safe`, this receipt is ops apparatus per conventions §13.2 — relocate the receipt line to the Methodology appendix (internal) defined in Output Format, and keep in the body only a plain-language note naming the holdings whose scores were unavailable.
4. **Redundancy coverage cross-check** (only when both `analyze_portfolio.sector_allocation` and `check_portfolio_redundancy` sector weights came back): write each sector-weights payload to a private mktemp JSON file, then one Bash step — `python3 "<skill-dir>/../_parallax/coverage_check.py" --portfolio-sectors "$PORTFOLIO_SECTORS" --redundancy-sectors "$REDUNDANCY_SECTORS" --holdings "$HOLDINGS"` — and render from its JSON verdict. Tag every `--holdings` entry with its `sector` from the `analyze_portfolio` sector mapping (per-holding backstop as usual): the live redundancy payload is aggregate-only, and without sector tags the helper cannot infer absent holdings and resolves `absent_holdings_basis` to `not_computable`. Cite the operator-agnostic-helper rationale by reference to `_parallax/house-view/loader.md` §2 ("Why the helper, not inline math") — the same argument applies here: the coverage arithmetic must be identical across operator LLMs, so it is never reproduced in prose. On `coverage_limited`, label the redundancy output **coverage-limited** in Current Portfolio Assessment, name the `diverging_sectors` and any `absent_holdings`, and prefer the `analyze_portfolio` sector weights for every rendered concentration figure. `absent_holdings` is basis-qualified via `absent_holdings_basis`: when it is `sector_inference`, note that the absent-holdings list is inferred from diverging sectors (the redundancy payload carried no per-holding data) rather than confirmed directly; when it is `not_computable`, render nothing about absent holdings at all — do not claim absence and do not claim confirmed coverage. On `consistent`, render normally.

### Batch B — Macro (after Batch A)

1. Call the discovered `macro_analyst` capability for each unique covered market (cap 3), using the live schema's tactical-component value when advertised — fire all calls in one parallel batch. (Score trends moved into Batch A: `get_score_analysis` has no Batch A dependency, so it no longer waits behind the portfolio snapshot.)

### Batch C — Health flags + trade decisions

1. **Parse mandate parameters** (if `constraints=` and/or `target=` were passed):
   - `constraints=`: split on commas; match each clause against two recognized patterns — "max N% per position" (a per-position weight cap, applied to Target Weight in step 5) and "no <sector>" (a sector/name exclusion, applied to Replacement Candidates in step 6 exactly like `tilts.excludes`).
   - `target=`: match against recognized phrases — "reduce concentration" (prioritize Reweight/Trim of concentration-flagged holdings in step 5) and "improve quality score" (rank Replacement Candidates by quality sub-score in step 6). Any other phrase is unrecognized.
   - **Fail-loud rule:** any `constraints=` clause that matches neither recognized pattern is never silently dropped — it renders "constraint not recognized — not applied" in the Mandate Constraints Applied output block. Any unrecognized `target=` phrase is echoed verbatim there with a statement of how the standard recommendations already address it.
2. Evaluate the 5 health flags **per holding** — binding flag conditions in `../parallax-client-review/references/recommendation-matrix.md` (same taxonomy and threshold values as `parallax-portfolio-checkup/references/health-flags.md`, whose canonical portfolio-level weighted-average definitions apply to portfolio-checkup, not here): Low Score (holding total score ≤5.0), Concentration (holding weight >15%, or holding among the top-3 when their combined weight >45%), Redundancy (holding is part of a redundant pair), Value Trap (holding value score ≤3.0), Macro Misalignment (holding's sector has a negative tactical outlook). Per-holding flag counts drive priority assignment.
3. **House-view alignment check** (if view active): for each holding, compute view-tilted target weight using loader.md §3 multipliers; flag holdings >25% off target as "View Misalignment." For holdings on `tilts.excludes`, flag as "View Excluded — must trim." The multiplier-derived target is benchmark-free — it tilts current weights, not a policy. When a client policy is supplied, Batch C2's optimizer targets (computed against the policy benchmark) supersede it in Trade Recommendations; the multiplier target then serves only this flag check.
4. Assign priority per recommendation-matrix.md (count View Misalignment / View Excluded as flags):
   - **High** (3+ flags or View Excluded): Strong trim/exit candidate
   - **Medium** (2 flags): Investigate + potential trim
   - **Low** (1 flag): Monitor, hold unless constraints violated
5. Determine actions combining flags + score trends + macro + view tilts + parsed target bias:
   - **Trim/Exit:** High priority holdings, View Excluded, or declining scores + any flag
   - **Hold:** Stable/improving scores, no flags, view-aligned
   - **Reweight:** Concentration flag only, OR view-tilted toward different weight than current, OR prioritized by a parsed "reduce concentration" target bias
   - **Investigate:** Medium priority but ambiguous signal (suggest `/parallax-deep-dive`)
   - Apply any parsed per-position weight cap (from `constraints=`) to Target Weight for every recommended position.
6. For trim candidates: Resolve user thesis vs. view per loader.md §4. If `PARALLAX_LOADER_V2=1` and view active, follow `loader.md` §3 "Application (V2)": decompose replacement theme into parallel per-sector calls, merge, and dedupe. If V1, prepend tilt context and call `build_stock_universe` once.
   - **Divergence assertion** (per loader.md §5 rule 4 — required universally): REQUIRED for V1 paths. If the query named N≥2 sectors/themes, compute `max_sector_share/total` in returned candidates. If > 0.6, emit fail-loud warning. If `PARALLAX_LOADER_V2=1`, use to verify merge quality.
   - **Ground-truth check per candidate** (per loader.md §5 rule 3): call `get_peer_snapshot` AND `get_company_info` in parallel. Drop any candidate where `returned_name ≠ expected_name` after normalizing both per conventions §2 step 2 from the replacement pool (flag ⚠ MISMATCH, do not rank).
   - Filter remaining trusted candidates against `tilts.excludes`, `tilts.excludes_freeform`, and any sector/name exclusion parsed from `constraints=`. If an "improve quality score" target bias was parsed, rank remaining candidates by quality sub-score.

### Batch C2 — Policy reconciliation (S3; only when `policy=` was supplied)

JIT-load `_parallax/client-policy/policy-loader.md`. Run the S0–S2 adaptation
first (`adaptation.py`, same contract as `parallax-client-review`), then the
S3 optimizer — a real Bash tool call, never prose arithmetic:

1. **Assemble the payload** (JSON file via a private `mktemp` path):
   - `basis`: the basis the adaptation result normalized to (`sleeve`); every
     weight and band edge in the payload must share it. Declared explicitly,
     never assumed.
   - `holdings[*].symbol` / `weight`: the current holdings in that basis.
   - `holdings[*].coefficient`: the tilt-weighted composite score — the
     holding's aggregated composite score (loader.md §3b) × its region tilt
     multiplier × its sector tilt multiplier (loader.md §3; each 1.0 with no
     active view). Every non-excluded holding needs one; a holding whose score
     is unavailable must be either excluded from the solve or given an
     explicit disclosed treatment — the solver rejects a missing coefficient
     rather than guessing. **The explicit disclosed treatment for a
     profile-derived score** (Batch A coverage-gap fallback, `get_peer_snapshot`
     row): before using it as a coefficient here, cross-check it against the
     holding's latest `get_score_analysis` row. If the two agree — same
     composite field, same 1–10 scale — the coefficient is same-scale by
     construction and enters the solve with the profile-derived disclosure. If
     they disagree, or only one source returned, do NOT solve with a guessed
     value: exclude the holding from the solve instead, using the
     excluded-holding disclosure named above (mixed-scale coefficients change
     the LP optimum itself, so a guessed value is never an acceptable
     substitute). State the same-scale verification outcome for every
     profile-derived holding in Policy Reconciliation.
   - `excludes`: the subset of `tilts.excludes` that matches a held symbol,
     plus held symbols matching a parsed "no <sector>" exclusion. The solver
     hard-rejects an excludes entry that matches no holding, so intersect
     BEFORE assembling the payload; a `tilts.excludes` entry naming a symbol
     the client does not hold is vacuously satisfied — list it in the Policy
     Reconciliation section as "excluded, not held" rather than passing it.
   - `position_cap`: the most restrictive of the parsed "max N% per position"
     cap and the adaptation result's `max_position_weight` — `min()` of the
     two, never the looser. Both are sleeve-basis fractions; convert before
     comparing if the parsed cap was stated on a different basis. Name which
     bound applied in Mandate Constraints Applied. A mandate cap below a
     segment floor carried by a single holding is jointly infeasible by
     construction — the solver returns `infeasible` with the smallest
     violation and the step-3 routing below applies unchanged.
   - `bands`: one entry per adaptation segment carrying band edges —
     `{dimension, key, symbols: [members by the holding→region/sector
     mapping], min, max}`.
   - `turnover_penalty`: omit (the module's disclosed default) unless the
     mandate states one.
2. **Solve**: `python3 "<skill-dir>/../_parallax/client-policy/reconcile.py"
   --input "$PAYLOAD"` and parse the JSON result.
3. **Route by `status` — the trade list is gate-shaped (conventions §4.0)**:
   - `optimal`: the result's `target_weights`/`trades` become the Target
     Weights in Trade Recommendations. Carry `binding`, `turnover_penalty` +
     `penalty_source`, `basis`, `calibration_status`, and `total_turnover`
     into the Policy Reconciliation section. Render `total_turnover`
     prominently: it is **two-sided** turnover — the sum of the absolute
     weight changes across every holding, so a one-way trade of 20 points
     contributes 40. State the two-sided basis on the same line, or the
     figure reads as twice the trading it represents. State with it that the
     turnover penalty is `heuristic_phase0` and uncalibrated, so the figure is
     a disclosure and not a threshold verdict — do not render an advisory
     turnover limit, a "high/low" judgement, or any comparison against a
     target. If `basis` is `sleeve` and the report renders total-portfolio
     weights, convert visibly (state the equity sleeve weight used) — a
     sleeve delta read as a total delta is a wrong trade size, and the same
     visible conversion applies to `total_turnover` when rendered in
     total-portfolio terms.
   - **Single-name floor disclosure.** For every payload band with a `min`
     above 0 whose `symbols` list holds exactly one member, render one line
     in Policy Reconciliation naming the segment, the floor, and the single
     holding that carries it: a segment floor met by one position forces
     that position to at least the floor, whatever its score. Add "and the
     floor is binding in this solve" when `binding` also carries
     `band:<dimension>:<key>:min` for that band. A symbol that is the sole
     member of two floored bands gets two lines, each naming its own
     segment, floor, and binding state. Derived from the payload the skill
     assembled and the result it received; no solver change.
   - `infeasible`: render the `violations` table (the exact smallest
     relaxations) and NO optimizer targets — no target weights, no trade
     list, not even labeled "suggested". Never silently relax. Trade
     Recommendations fall back to the flag-based path, labeled "not
     policy-reconciled — constraints jointly infeasible, see Policy
     Reconciliation". When the smallest-violation table names a bound on a
     holding that is the sole member of a floored band, state that the
     mandate is internally contradictory (cap against floor) — distinct from
     ordinary infeasibility.
   - `conflict`: render each named conflict (e.g. an exclude against a user
     minimum) for human decision — precedence collisions are never
     auto-resolved (design guardrail 5). Same fallback labeling as
     `infeasible`.
   - `solver_unavailable` / `invalid_input` / `solver_error`: the
     reconciliation verdict is **UNVERIFIED** — state the reason from the
     result, render no optimizer targets, and label the flag-based fallback
     "not policy-checked". Never substitute model judgement for the solve.

### Batch D — Validation

If `PARALLAX_LOADER_V2=1`, follow `loader.md` §3b: aggregate per-holding `get_peer_snapshot` scores for the proposed new allocation. If V1, call `quick_portfolio_scores`. If view active, verify proposed allocation aligns with view tilts within 10% per sector. Append audit log entry per loader.md §6.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format. The loader returns exactly seven keys; any other access (e.g. `branding["voice"]`) raises `KeyError` — structurally enforced by `loader.py`.

Resolve the §13.1 audience mode in the same step, via one Bash call into the
same seam function `parallax-client-review` uses — never a prose read of
`branding["render"]`:

```
python3 -c "import sys; sys.path.insert(0, '<skill-dir>/../_parallax/white-label'); \
  from loader import load_visual_branding; from rm_consumer import resolve_audience; \
  import json; b = load_visual_branding(); mode, notice = resolve_audience(b, <flag or None>); \
  print(json.dumps({'mode': mode, 'notice': notice}))"
```

Substitute the parsed `audience=` flag (or `None` if none was supplied) for
`<flag or None>`. Record the returned `mode` for the Output Format branches
below, and if `notice` is non-null, append it verbatim to About This Report.
`resolve_audience` is a pure function — this is a real Bash tool call, never
prose arithmetic reproducing its precedence logic.

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

The Bash result may show a `[render-gate] WARN:` line above the report. That line is stderr diagnostics, not stdout. Never include it in the reply. It means the drafted opening drifted from the documented Output Format start; fix the opening and re-run the gate.

**Degraded-state rule:** if an async tool (e.g. `get_assessment`, `get_news_synthesis`) times out or returns no data, render the pending/unavailable note INSIDE the relevant section or the About This Report line — NOT as a preamble above the report — so it is part of the rendered body and survives the gate. (The gate also hoists a leaked degraded note as a backstop.)

`_parallax/render_gate.py` is pure-stdlib and deterministically drops anything before the first rendered block (House View Preamble banner / Branding Header / Ground-truth Integrity / this skill's title or first rendered section), preserving the active-house-view banner in every `view_status` state. Same operator-agnostic-helper pattern as `view_status.py` / `loader.py` (a real Bash tool call, not prose).

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** rebalance`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **Current Portfolio Assessment** (factor scores, concentration issues, redundancy — label the redundancy figures **coverage-limited** with the diverging sectors and absent holdings when `coverage_check.py` returned that verdict (After Batch A item 4); if view active, current alignment vs view-tilted target; factor names render with the §13.3 plain-language gloss by reference under `audience=client_safe`. Under `audience=client_safe` the coverage-limited label, its plain-language meaning, and the diverging sector names stay in the body — the label is a data-quality caveat and qualifies the figures it sits next to — while the numeric divergence figures from `coverage_check.py` relocate to the Methodology appendix (internal) per conventions §13.2)
- **Health Status** (Healthy/Monitor/Attention badge with flag summary)
- **Verdict sensitivity**: the 1-2 nearest-boundary flags and their arithmetic flip condition for moving Health Status to the adjacent tier, per `parallax-portfolio-checkup/references/health-flags.md` "Verdict sensitivity" (renders `parallax-conventions.md` §11 by reference; internal_analyst mode only — omitted under `audience=client_safe` per conventions §13.2; the Health Status verdict itself renders in both modes).
- **Health Flags** (table: each triggered flag per holding with priority level; View Misalignment / View Excluded shown as their own flag types)
- **Macro Context** (relevant market outlook, sector tilt implications for rebalancing)
- **Score Momentum** (table: each holding's score trend — improving/stable/declining)
- **Ground-truth Integrity** (only render if any mismatch detected — table: `input_ticker`, `returned_name`, `expected_name`, match status per holding. ⚠ MISMATCH rows are re-scored individually and flagged — scores not trusted from `quick_portfolio_scores` — per loader.md §5 rule 3.)
- The policy section family (Policy Reconciliation and, when constraints/target/mandate `max_position_weight` triggers it, Mandate Constraints Applied) carries mandate-compliance content and §4.0 gate states; it renders in place, unchanged, in both audience modes — §13.2's relocation rule does not apply to it.
- **Policy Reconciliation** (only if `policy=` was supplied) — the S3 result: status; on `optimal` the binding constraints, resolved turnover penalty with its source, basis, `calibration_status` disclosure, and the two-sided total turnover with its uncalibrated-penalty note; on `infeasible` the smallest-violations table with an explicit "no targets rendered — constraints not silently relaxed" line; on `conflict` the named conflicts awaiting human decision; on any other status the UNVERIFIED statement with the reason. Also list any `tilts.excludes` entries not matched to a held symbol as "excluded, not held" (Batch C2 step 1). List every profile-derived holding used as a coefficient, with its same-scale verification outcome (verified same-scale-by-construction, or excluded from the solve on disagreement/single-source) per the Batch C2 coefficient bullet. Follows conventions §4.0: this section never converts an unknown into a pass.
- **Mandate Constraints Applied** (only if `constraints=` or `target=` was provided, or a mandate `max_position_weight` is present) — echoes each parsed constraint/target and its effect (weight cap, exclusion, priority bias, quality-score ranking); any unparsed `constraints=` clause renders "constraint not recognized — not applied"; any unrecognized `target=` phrase is echoed with a statement of how the standard recommendations already address it. When a mandate `max_position_weight` is present, state it, state the parsed per-position cap if any, and state which of the two bound (Batch C2 step 1 `position_cap` bullet).
- **Trade Recommendations** (table: Priority | Action | Symbol | Current Weight | Target Weight | Rationale — every recommendation cites a specific flag or finding; if view active, "Rationale" includes view-tilt direction; any recommendation on a ⚠ MISMATCH holding must note scores were re-derived via `get_peer_snapshot` directly). Render a one-line informational preface above this table per conventions §12.2; framed per conventions §12 (candidate actions, not instructions) and supports `action_labels=plain` per §12.3 for retail-suitable rendering. Under `audience=client_safe`, `action_labels=plain` is implied per conventions §13.2 — the Action labels always render neutral status descriptions, and any accompanying magnitude renders as distance-to-threshold arithmetic per §12.3, not a suggested trade size.
- **Replacement Candidates** (if trimming, scored alternatives; filtered against tilts.excludes + tilts.excludes_freeform if view active; all candidates ground-truth-validated per loader.md §5 rule 3; divergence-assertion result for replacement universe per loader.md §5 rule 4. Under `audience=client_safe` the divergence-assertion result is ops apparatus per conventions §13.2: the body keeps only a plain-language caveat when the assertion fired — the candidate list is concentrated in one sector — and the numeric assertion detail relocates to the Methodology appendix (internal); ⚠ MISMATCH ground-truth results are non-suppressible and render unchanged in both modes)
- **Before/After Comparison** (factor scores: current vs. proposed; if view active, alignment-to-view metric included; factor names render with the §13.3 plain-language gloss by reference under `audience=client_safe`)
- **Implementation Notes** (suggested execution order, liquidity considerations)
- **Methodology appendix (internal)** (`audience=client_safe` only, and only when at least one item was relocated into it; renders immediately before About This Report) — the clearly-separable trailing home per conventions §13.2 for this skill's relocated methodology/ops apparatus: the Batch A execution receipt (After Batch A item 3), the coverage cross-check numeric divergence figures (Current Portfolio Assessment), and the divergence-assertion numeric detail (Replacement Candidates). It never receives non-suppressible surfaces (§13.2 list) or policy-family content — those render in place. Under `internal_analyst` this section does not exist; the same material renders inline as specified above.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line. Under `audience=client_safe`, append the §13.4 mode line `Audience mode: client-safe`; if `resolve_audience` returned a notice, append it too — place both once, in that order, never duplicated.

Apply audience render mode per `parallax-conventions.md` §13; default `internal_analyst`. Wherever a health flag or other published-cutoff classification renders under `audience=client_safe` (Health Flags, Current Portfolio Assessment concentration issues, Trade Recommendations rationale), state the classification and its plain-language meaning and omit the cutoff arithmetic, per conventions §13.2 — the thresholds are static and published in the reference docs, so nothing about them requires retention and nothing relocates. This wiring is fully conformant with the §13.2 table for this skill: verdict-sensitivity omission, action-label mode, factor gloss, the §13.4 footer line, published-cutoff arithmetic (the health-flag and View Misalignment thresholds, as above), and methodology/ops apparatus (the Batch A execution receipt, the coverage cross-check divergence figures, and the divergence-assertion detail — relocated to the Methodology appendix (internal)). The policy section family renders in place, unchanged, in both modes as stated above; `total_turnover` and its two-sided label render inside it, untouched.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.
