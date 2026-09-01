---
name: parallax-client-review
description: "RIA/wealth advisor client portfolio review: full analysis, redundancy, health flags, macro context, per-holding drill-down, prioritized recommendations, and AI assessment via Parallax MCP tools. Holdings as [{symbol, weight}]. NOT for fund manager briefs (use /parallax-morning-brief), not for quick stock checks (use /parallax-should-i-buy)."
---

<!-- white-label: integration-pattern.md -->

# Client Portfolio Review

## When not to use

- Fund manager morning brief → use /parallax-morning-brief
- Single stock analysis → use /parallax-should-i-buy

## Gotchas

- JIT-load _parallax/parallax-conventions.md for fallback patterns and parallel execution
- JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §3 (multipliers), §4 (conflict resolution), §5 (output rendering), §6 (audit). The view shapes the suitability assessment AND the recommendations: holdings misaligned with view get higher priority for trimming, view-aligned holdings get implicit support.
- When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer
- JIT-load references/recommendation-matrix.md for priority classification and drill-down criteria
- JIT-load _parallax/client-policy/policy-loader.md when `policy=` is present. Fallback ladder per that file. S1/S2 math via adaptation.py only — never inline.
- Policy sections never precede the first render-gate anchor. Render them in the body, after House View Alignment, per policy-loader.md §7 placement rule.
- No `policy=` supplied means today's behavior, unchanged. No policy sections, no disclosure line.
- Holdings in RIC format, weights sum to ~1.0
- analyze_portfolio called twice — once for performance/returns fields, once for concentration/attribution fields (split to manage response size). **Call shape:** `portfolio=[{date: <as-of ISO>, symbol: <ric>, weight: <w>}, ...]` with `fields=[...]`, subject to the discovered live schema. The date is an as-of date over a price history, not a snapshot key: a deployed connector may need a date early enough that each holding has sufficient prior price history, so today's date can return empty or fail validation. Read the live schema's own description first. When the schema gives no guidance, date every holding at the most recent completed trading day at least 5 calendar days in the past, one date for all holdings, and state the date used in the report — live schema still wins over this default. The parameters `holdings` and `lens` do not exist in the deployed schema. **Fallback** (on MCP schema validation error OR truncated/oversized response): `check_portfolio_redundancy` (concentration) + `quick_portfolio_scores` (factor tilt) + individual `get_stock_outlook` with `aspect="risk_return"` (performance).
- Per-holding drill-down capped at 8 holdings to manage latency
- Mixed-exchange portfolios may need split scoring (see shared conventions)
- Output should be presentation-ready for client meetings
- LANGUAGE HAND-OFF — if `lang=` is present and ≠ `en`, the terminal Translate step is mandatory. Route `zh-CN`/`zh-TW`/`zh-HK` → `/translate-chinese-finance`, `th` → `/translate-thai-finance`, using the delimited routing-directive block (never a prose sentence the translator could echo). Unsupported values → English output with the standard warning footer.
- get_assessment prompt should incorporate all findings including macro, flags, and recommendations
- Pre-Render calls `_parallax/white-label/rm_consumer.py` → `load_rm_branding_context("portfolio review", audience=<flag or None>)`. This executable visual-only seam owns source redaction, voice isolation, branding fallback, AND the §13.1 audience-mode resolution — pass the parsed `audience=` flag (or `None`) into the call and read `resolved_audience` off the returned context; never inspect the branding mapping directly for this. Use its `header_lines` and `about_lines` exactly once. The state mapping follows `_parallax/white-label/integration-pattern.md` §5 + §7. The context's `about_lines` already carry the §13.4 mode line and any unrecognized-value notice — do not append a second mode line.
- Branding Header uses `**<client_name>** portfolio review` (skill-specific framing), not the generic `**<client_name>** report` template in integration-pattern.md §5. Intentional divergence — do not "fix" to match the generic template.

Presentation-ready portfolio review with health flags and prioritized recommendations for wealth advisors.

## Usage

```
/parallax-client-review [{"symbol":"AAPL.O","weight":0.25},{"symbol":"BRK-B.N","weight":0.20}] client="conservative retiree, income focus, 10yr horizon"
/parallax-client-review [{"symbol":"AAPL.O","weight":0.25},{"symbol":"BRK-B.N","weight":0.20}] client="conservative retiree, income focus, 10yr horizon" lang=zh-CN register=retail policy="/path/to/client-policy.yaml"
/parallax-client-review [{"symbol":"AAPL.O","weight":0.25},{"symbol":"BRK-B.N","weight":0.20}] audience=client_safe
```

Optional: append `lang=<code>` (`en` default; `zh-CN`, `zh-TW`, `zh-HK`, `th`) and `register=retail` after the existing parameters. `register=retail` is passed only when translation is requested; absent means institutional register.

Optional `audience=` argument: `client_safe | internal_analyst`; precedence follows `parallax-conventions.md` §13.1.

Optional: append `policy=` after the existing parameters. `policy=` accepts a file path or inline YAML/JSON describing the client's strategic allocation, bands, and tactical budget. Absent means the review runs exactly as today. **Do not add an invocation `k=` flag.** The locked spec allows a firm-level default and a per-mandate override only; both live in the policy artifact's `adaptation` block.

**Note on `benchmark=` parameter.** The current workflow body does NOT consume a `benchmark=` parameter — the example above intentionally omits it. If a future revision adds benchmark-relative attribution: pass benchmarks as **plain ETF tickers** (e.g., `SPY`, `QQQ`, `EWJ`) and route through `etf_daily_price` — NOT `export_price_series`. The two endpoints are separate. Equity tickers (with RIC suffix like `.O` or `.N`) go through `export_price_series`; ETFs (plain ticker) go through `etf_daily_price`. Mixing them silently fails-empty.

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, fallback patterns, and macro reasoning. JIT-load `_parallax/house-view/loader.md` for active-view validation and integration. JIT-load `references/recommendation-matrix.md` for priority system.

### Batch 0 — Tool Loading & Active House View

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

Per `loader.md` §1-§2. If view present, capture tilt vector, excludes, basis_statement (used to frame Suitability Assessment in firm voice). The view's tilts become an additional layer of recommendation justification: when trimming, "view tilts UW [sector]" is cited alongside health flags. If validation fails or no view present, run review without view.

### Batch 0.5 — Client policy load (only if `policy=` present)

JIT-load `_parallax/client-policy/policy-loader.md`. Write inline policy input to a
private mktemp file first. Then, in one Bash step:

python3 "<skill-dir>/../_parallax/client-policy/adaptation.py" --policy "$POLICY" --json

Capture `errors`, `fallback_tier`, `resolved_k`, `k_source`, `policy_hash`, and
`data_quality`. Blocking errors mean tier `no_policy` for the rest of the run;
dimension-scoped errors (missing basis, total-basis without equity weight) drop only
that dimension to multiplier_fallback — policy-loader.md §2 defines the classes.
Render the error list in Policy Data Quality and continue the review unchanged.
Exposure-dependent S1/S2 runs after Batch A, in Batch C.

### Batch A — Portfolio-level analysis (parallel)

| Tool | Parameters | Notes |
|---|---|---|
| `analyze_portfolio` | `portfolio=[{date: <as-of ISO>, symbol: <ric>, weight: <w>}]`, `fields=["performance_metrics","rolling_metrics","drawdown_analysis","portfolio_summary","time_period_returns"]` | Returns/risk metrics. Build portfolio array from provided holdings; use an as-of date with sufficient prior price history per the Gotchas call-shape note; state the date used. |
| `analyze_portfolio` | `portfolio=[{date: <as-of ISO>, symbol: <ric>, weight: <w>}]`, `fields=["concentration_metrics","sector_allocation","company_contribution"]` | Concentration and attribution analysis. Two separate calls with distinct field subsets to stay under the 180K-char response ceiling. |
| `check_portfolio_redundancy` | `holdings` | Overlap detection. When `analyze_portfolio.sector_allocation` also came back, cross-check the two sector breakdowns per Batch C step 3 before rendering either. |
| `get_peer_snapshot` | per holding | **Primary scoring source** for `PARALLAX_LOADER_V2=1`. Aggregate scores client-side per `loader.md` §3b. **Distinguish a timeout from an empty response:** a timeout leaves the holding unscored, per existing handling. A successful call that carries no data for the listing is a coverage gap, not a timeout — fall back to `get_company_info` plus `get_score_analysis` for that holding, label every figure derived this way a **profile-derived score**, and name every profile-derived holding in the report. **Same-scale guard:** before ranking or combining a profile-derived score with a peer/batch composite score, cross-check it against the holding's latest `get_score_analysis` row. If the two agree (same composite field, same 1–10 scale), the profile-derived score is same-scale by construction and renders alongside the composite normally, tagged profile-derived. If they disagree, or only one source returned, do NOT blend a guessed value into the ranking: flag the holding's score **unverified — not combined with the composite ranking** in Factor Analysis and Per-Holding Analysis instead. |
| `get_company_info` | per holding (parallel) | **Ground-truth oracle** per loader.md §5 rule 3 (required universally). Records `expected_name`. |
| `list_macro_countries` | — | Check market coverage |
| `quick_portfolio_scores` | `holdings` | **Legacy/V1 path only**. Do NOT use if `PARALLAX_LOADER_V2=1` and view active. A successful call with no data for a listing (distinct from a timeout) is the same coverage-gap case as the `get_peer_snapshot` row above — fall back to `get_company_info` plus `get_score_analysis` for that holding, label it a **profile-derived score**, and apply the same same-scale guard before combining it into any ranking. |

**After Batch A**: cross-check returned names against `get_company_info` names per loader.md §5 rule 3. For `PARALLAX_LOADER_V2=1`, any mismatch in `get_peer_snapshot` is flagged ⚠ MISMATCH and excluded from aggregate calculations. For V1, any mismatch in `quick_portfolio_scores` is re-scored individually and flagged as UNTRUSTED for the batch factor profile.

### Batch B — Macro context (concurrent with Batch A)

Derive home markets from RIC suffixes (available from the input holdings before any call — no Batch A output is required). Fire `macro_analyst` with component="tactical" for each unique covered market (cap 3) in the SAME tool-call turn as the Batch A calls, rather than as a separate stage after them. Batch C still requires BOTH Batch A and these macro calls to have completed.

### Batch C — Health flags + drill-down (after A + B)

1. Evaluate the 5 health flags **per holding** — binding flag conditions in `references/recommendation-matrix.md` (same taxonomy and threshold values as `parallax-portfolio-checkup/references/health-flags.md`, whose canonical portfolio-level weighted-average definitions apply to portfolio-checkup, not here): Low Score (holding total score ≤5.0), Concentration (holding weight >15%, or holding among the top-3 when their combined weight >45%), Redundancy (holding is part of a redundant pair), Value Trap (holding value score ≤3.0), Macro Misalignment (holding's sector has a negative tactical outlook). Per-holding flag counts drive priority and drill-down selection.
2. **House-view alignment** (if view active): add View Misalignment (>25% off view-tilted target) and View Excluded (on tilts.excludes) as additional flags. Surface a portfolio-level "view alignment score" (% of weight in view-aligned positions). <!-- "view-tilted target" wording debt is assigned to Phase 2 per the rollout sequencing; this flag keeps its Phase 1 semantics unchanged, do not "fix" the wording here -->
3. Flag redundancy as low-confidence if coverage <60%. Independently of that threshold, when both `analyze_portfolio.sector_allocation` and `check_portfolio_redundancy` sector weights are available, cross-check them via `_parallax/coverage_check.py` rather than reproducing the arithmetic in prose: write each sector-weights payload to a private mktemp JSON file, then one Bash step — `python3 "<skill-dir>/../_parallax/coverage_check.py" --portfolio-sectors "$PORTFOLIO_SECTORS" --redundancy-sectors "$REDUNDANCY_SECTORS" --holdings "$HOLDINGS"` — and render from its JSON verdict. Tag every `--holdings` entry with its `sector` from the `analyze_portfolio` sector mapping (per-holding backstop as usual): the live redundancy payload is aggregate-only, and without sector tags the helper cannot infer absent holdings and resolves `absent_holdings_basis` to `not_computable`. Cite the operator-agnostic-helper rationale by reference to `_parallax/house-view/loader.md` §2 ("Why the helper, not inline math") — the same argument applies here: the coverage arithmetic must be identical across operator LLMs. On `coverage_limited`, label the redundancy figures **coverage-limited** in Concentration & Redundancy, name the `diverging_sectors` and any `absent_holdings`, and prefer the `analyze_portfolio` sector weights for every rendered concentration figure. `absent_holdings` is basis-qualified via `absent_holdings_basis`: when it is `sector_inference`, note that the absent-holdings list is inferred from diverging sectors (the redundancy payload carried no per-holding data) rather than confirmed directly; when it is `not_computable`, render nothing about absent holdings at all — do not claim absence and do not claim confirmed coverage. On `consistent`, render normally.
4. Assign health status: **Healthy** (0) · **Monitor** (1-2) · **Attention** (3+). View Excluded counts as Attention regardless of other flags.
5. Select up to 8 holdings for drill-down per `references/recommendation-matrix.md`: weight >10%, any flag (including View flags), or macro-misaligned. Prioritize by flag count then weight.

For each drill-down holding (parallel):

| Tool | Parameters |
|---|---|
| `get_score_analysis` | `symbol`, `weeks` as int 26 (26-week lookback, non-default — see conventions §0.2) |
| `get_stock_outlook` | `symbol`, `aspect="risk_return"` |
| `get_peer_snapshot` | `symbol` |

**Ground-truth re-verification per drill-down holding** (per loader.md §5 rule 3): cross-check `get_peer_snapshot.target_company` against the `get_company_info.name` already captured in Batch A. If mismatch at drill-down time (can occur when the Batch A and Batch C queries bind differently), flag ⚠ MISMATCH and extract the queried stock's scores from the `get_peer_snapshot.comparison[]` row whose `symbol` matches the queried symbol, not from the target_company field.

News (selective, async): `get_news_synthesis` for holdings >10% weight AND flagged, or in sectors with active macro developments. Cap at 5.

**Client policy S1 + S2** (only if `policy=` present and tier is not `no_policy`)

1. Assemble current sleeve exposures: region from RIC suffixes per `_parallax/parallax-conventions.md` §1; sector from the Batch A `analyze_portfolio` `sector_allocation` block, with `get_peer_snapshot` / `get_company_info` as a per-holding backstop. Region is therefore classified by listing venue, not by issuer domicile or economic exposure; ADR/fund look-through is not applied in phase 1, and the Policy Data Quality intro states this basis. Renormalize each dimension's weights over MAPPED holdings only and record `coverage` plus every `unmapped` holding. Carry each holding's `isin` when one is available. Payload shape is pinned in policy-loader.md §3; these clauses of it bind the producer and are stated identically in `adaptation.py`'s module docstring and policy-loader.md §3 — one of the three copies that must agree:
   - `basis` must be `"sleeve"` — Phase 1 accepts sleeve-relative exposures only; the producer converts before calling. A missing or non-`"sleeve"` `basis` is rejected at the CLI (exit 2, naming the file and the offending value), the same operator-mistake class as a non-object payload; no conversion is implemented in Phase 1.
   - The whole payload is checked by `validate_exposures` against this contract (known dimensions, finite weights in [0, 1], per-dimension sums, coverage consistent with the `unmapped` weight it implies). At the CLI a violation is an operator mistake: exit 2, naming the file and every violation. Called as a library the helper proceeds WITHOUT exposures and discloses one `invalid_exposures` Data Quality row per violation; it never certifies an impossible payload with a band verdict.
   - `coverage[dim]` is the mapped weight fraction BEFORE renormalization. A coverage below 1.0 emits `unmapped_holding` rows and is disclosed in the rendered table. `coverage` passes through onto the result unchanged so the consumer can caveat a conditional diagnostic.
   - `isin` on a holding is OPTIONAL. When present it is matched against `mandate.prohibited_products` alongside `symbol` (case-insensitive). An ISIN-shaped prohibition with any holding lacking an `isin` emits a `hard_constraint_not_checkable` row: the check ran on partial identifiers.
2. Assemble view tilts from the loaded view after the loader.md §3 alias collapse:
   regions, sectors, and excludes only. Factors, styles, and themes are tactical-only
   and never enter band math.
3. Write both to private mktemp JSON files, then in one Bash step:

python3 "<skill-dir>/../_parallax/client-policy/adaptation.py" \
  --policy "$POLICY" --exposures "$EXPOSURES" --view-tilts "$TILTS" --json

4. Capture the full result. Every rendered number comes from it. Do not recompute,
   round, or re-derive any figure inline.

### Batch D — Recommendations + Assessment (after A + B + C)

1. Per `references/recommendation-matrix.md`, assign each flagged holding a priority (High/Medium/Low) and action type (trim/exit/hold/investigate/reweight). Every recommendation must cite a specific finding. View Excluded → Exit (priority High). View Misalignment → Trim or Reweight (priority Medium unless paired with other flags).
2. Call `get_assessment` with comprehensive prompt incorporating: portfolio composition, factor scores, health flags (including View flags), macro context, per-holding drill-down findings, recommendations, client context, AND active house view (basis_statement + tilt vector + excludes if present), AND, when a client policy is present, the SAA drift findings, TAA alignment verdicts, the resolved k with its source, and the fallback tier. Fire this call as soon as recommendations are assigned (a deterministic matrix lookup — do not wait for pending `get_news_synthesis` calls; include news highlights only if already resolved). While `get_assessment` runs, proceed to compose all non-assessment sections; insert the assessment result into the Suitability Assessment section when it resolves, or render the degraded-state note per the existing rule on timeout.
3. Append audit log entry per loader.md §6. When a client policy was supplied, include the §6.2 conditional fields `client_ref`, `client_policy_applied`, `policy_hash`, `policy_fallback_tier`, `resolved_k`, and `k_source`. Never log a client name; `client_ref` (the policy's own pseudonymous `metadata.client_ref`) and `policy_hash` only. `policy_fallback_tier` takes an audit value, not the helper's tier string: `weights_only` / `full` / `partial_dimensions` carry over unchanged, the helper's `no_policy` tier (a policy supplied but unusable) is written as `invalid`, and a valid policy whose helper invocation failed at runtime is written as `unavailable`. Never write `no_policy` into the row.

### Pre-Render — Load white-label branding

Before composing the Output Format, JIT-load `_parallax/white-label/integration-pattern.md`. Import `load_rm_branding_context` from `_parallax/white-label/rm_consumer.py`. Call `load_rm_branding_context("portfolio review", audience=<flag or None>)` once, passing the parsed `audience=` flag (or `None` if absent). Place its `header_lines` below any House View Preamble. Place its `about_lines` in About This Report — the context's `about_lines` already carry the unconditional §7 currency-basis line (second, after the branding line), any `Logo on file:` line, the §13.1-resolved mode line, and any notice, so place them once — do not render the currency line again from the §7 table, and never append a second mode line (double-render hazard). Read `resolved_audience` off the returned context for the Output Format branches below; do not inspect the branding mapping directly. The helper preserves the RM analysis and selects default Parallax if branding is corrupt.

### Render — deterministic gate (LAST step, mandatory)

Compose the complete report per **Output Format** below, then run it through the shared render gate in **one Bash step** before replying. Use a private `mktemp` file (never a fixed/predictable path — `/tmp` symlink hazard). The shared gate is `_parallax/render_gate.py`, a sibling of the directory you loaded this SKILL.md from; pass this skill's key (use the loaded directory's absolute path as `<skill-dir>`):

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/clientrev.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill client-review < "$DRAFT"; rm -f "$DRAFT"
```

**Your entire final message is exactly that command's stdout** — unless `lang=` ≠ `en`, in which case the Translate step below consumes that stdout and the translated result is the entire final message. Never run the render gate on translated text; its anchors are English. Nothing before it (no step/batch-completion notes, no scratch computation, no "no active house view" / white-label config-probe narration), nothing after it.

The Bash result may show a `[render-gate] WARN:` line above the report. That line is stderr diagnostics, not stdout. Never include it in the reply and never pass it to the Translate step. It means the drafted opening drifted from the documented Output Format start; fix the opening and re-run the gate.

**Degraded-state rule:** if an async tool (e.g. `get_assessment`, `get_news_synthesis`) times out or returns no data, render the pending/unavailable note INSIDE the relevant section or the About This Report line — NOT as a preamble above the report — so it is part of the rendered body and survives the gate. (The gate also hoists a leaked degraded note as a backstop.)

`_parallax/render_gate.py` is pure-stdlib and deterministically drops anything before the first rendered block (House View Preamble banner / Branding Header / Ground-truth Integrity / this skill's title or first rendered section), preserving the active-house-view banner in every `view_status` state. Same operator-agnostic-helper pattern as `view_status.py` / `loader.py` (a real Bash tool call, not prose).

### Translate — conditional, after the render gate

This step runs ONLY when `lang=` is present and not `en`. Capture the render gate's stdout as the full body, including all Output Format sections, About This Report, the §9.2 AI-interaction disclosure, and the disclaimer. Record which disclaimer variant rendered (view-aware per `loader.md §5` vs standard `parallax-conventions.md §9.1`) for the boundary check.

Invoke the appropriate translator skill with the input shaped as follows:

```
ROUTING DIRECTIVE — DO NOT TRANSLATE OR ECHO THIS BLOCK:
  target_variant: <variant>
  register: retail
  source_language: en
  begin_content_below_separator: true
---

<render gate stdout>
```

Pass `register: retail` iff `register=retail` was supplied; otherwise omit the `register:` line so the translator defaults to institutional register. Route `zh-CN`, `zh-TW`, and `zh-HK` to `/translate-chinese-finance` with the matching `target_variant`. Route `th` to `/translate-thai-finance`; omit `target_variant` for Thai, but keep the routing block marker and `---` separator.

Translator-failure handling:
- If the translator fails or returns an empty/partial result, output the original English with a one-line warning footer: `> Translation to <lang> failed; output shown in English. Re-run if the issue is transient.`
- If the language arg is unrecognized, output the original English with: `> Language '<arg>' not supported; output shown in English. Supported: en, zh-CN, zh-TW, zh-HK, th.`
- Translator output replaces the English output in the chat; do not show both.

**Disclaimer boundary check.** If the disclaimer is missing from the translated output, first attempt a single-section re-translation pass on just the original English disclaimer text using the same routing-directive shape. Append that result if non-empty. If the pass fails or returns empty, append the English disclaimer variant that was actually rendered. Record the event in the loader.md §6 audit entry's `notes` field (`disclaimer boundary check fired — re-translated` or `disclaimer boundary check fired — english fallback`). Do not add a user-visible footer.

## Output Format

Client-ready report:
- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble). Per loader.md §5.1, the load preamble goes "at the very top" — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view active): `**<client_name>** portfolio review`. For the logo: if `branding["logos"]["primary"]` is empty (`""`, e.g., on the `logo_missing` partial-success path), render the text line only — no image, no extra About This Report note. If it is a URL (starts with `http://` / `https://`), embed `![<client_name>](<url>)` above the text line. If it starts with `/` or `~` (absolute local path, not embeddable in chat-delivered markdown per integration-pattern.md §5), skip the image embed — the seam's `about_lines` already carry the `Logo on file: <basename>` About This Report line (third, after the currency-basis line); do not append it separately.
- **Ground-truth Integrity** (only render if any mismatch detected — table: `input_ticker`, `returned_name`, `expected_name`, status. Mismatched holdings had scores re-derived via `get_peer_snapshot` symbol-match — per loader.md §5 rule 3.)
- **Portfolio Summary** (AUM breakdown, sector allocation, top 5 holdings; if view active, view-alignment score)
- **Health Status** (Healthy/Monitor/Attention badge with flag summary)
- **Verdict sensitivity**: the 1-2 nearest-boundary flags and their arithmetic flip condition for moving Health Status to the adjacent tier, per `parallax-portfolio-checkup/references/health-flags.md` "Verdict sensitivity" (renders `parallax-conventions.md` §11 by reference; internal_analyst mode only — omitted under `audience=client_safe` per conventions §13.2; the Health Status verdict itself renders in both modes).
- **Performance vs Benchmark** (key metrics)
- **Factor Analysis** (scores with macro context interpretation for this client type; if view active, compare against view-target factor — tag any **profile-derived score** and its same-scale guard outcome per the Batch A `get_peer_snapshot` row; an unverified holding is not combined with the composite ranking; factor names render with the §13.3 plain-language gloss by reference under `audience=client_safe`)
- **Concentration & Redundancy** (flagged issues; coverage reliability note if applicable — label redundancy figures **coverage-limited** with the diverging sectors and absent holdings when `coverage_check.py` returned that verdict, Batch C step 3)
- **House View Alignment** (only if view active) — table of view tilt direction vs current portfolio exposure per sector/region/factor; flagged misalignments
- The policy section family (SAA Drift, TAA Alignment, Policy Conflicts, Policy Data Quality, Resolved-k Disclosure) carries mandate-compliance content and §4.0 gate states; it renders in place, unchanged, in both audience modes — §13.2's relocation rule does not apply to it.
- **SAA Drift** (only if policy supplied) — one row per covered segment: dimension, segment, current, policy, drift, band, band status, breach kind. When `coverage[dim] < 1.0`, carry a caveat line for that dimension — "diagnostics conditional on N% mapped coverage" — because `current` is renormalized over mapped holdings and is not the known full-sleeve exposure. Disclose the near-edge threshold under the table. Render **Verdict sensitivity** per `_parallax/parallax-conventions.md` §11 — band status is a published-numeric-cutoff verdict, so name the nearest-boundary segment and the arithmetic flip condition, third person, no advice language. Under `audience=client_safe`, the §11 flip-condition line is omitted per conventions §13.2 — the band status verdict, the coverage caveat, and the near-edge threshold disclosure still render.
- **TAA Alignment** (only if policy supplied) — one row per covered segment: tilt, room in the tilt direction, desired active, current active, alignment (aligned / opposed / capped-by-band / not evaluable / no view). Below the table: the budget line (Σ|desired| vs max_total_tilt, and the cap scale if one fired). State with the budget line that it sums |desired active| gross across region and sector independently, and that one overlapping holding may satisfy both a region and a sector active at once — a phase-1 heuristic characteristic, resolved by the phase-2 holdings-level optimizer. Tag every `multiplier_fallback` row whose alignment is aligned / opposed / no-view (a genuine sign read) visibly as **sign-only alignment — not sized (no band benchmark)**. A `multiplier_fallback` row whose alignment is `not evaluable` means the dimension was forced to fallback by an unresolved basis — tag it **not evaluable — basis unconfirmed, see Policy Data Quality** instead, pointing to the paired `basis_unconfirmed_drift` row. When `tactical_overlay.enabled` is `false`, SAA Drift renders unaffected but TAA Alignment renders exactly one line — "tactical overlay disabled by mandate" — with no budget line.
- **Policy Conflicts** (only if policy supplied) — tilt-vs-band rows and excludes / prohibited-vs-holding rows. Framed per `_parallax/parallax-conventions.md` §12: informational preface above the table, no imperative trade verbs. Any recorded RM band override renders here with its rationale. An empty table means "checked clean" ONLY when no `hard_constraint_not_checkable` row is present in Policy Data Quality; when one is present, say in one line that the table covers the constraints this helper can match and that the named theme-class or partially-identified constraints are not among them. Theme-class excludes are enforced by the house-view flow at skill level, not by the policy helper.
- **Policy Data Quality** (only if policy supplied) — uncovered dimensions, unmapped holdings and the coverage fraction, basis conversions, dimensions with an unresolved basis whose drift and TAA alignment are not basis-comparable (`basis_unconfirmed_drift`), policy staleness, tracking-error budget present but not evaluated, mandate position cap present but not evaluated at this layer (`position_cap_not_evaluated` — it binds only in rebalance's S3 solve), missing or one-sided bands, unknown segment keys, rejected exposure payloads (`invalid_exposures`), unclassifiable hard constraints (`hard_constraint_not_checkable`), exposure weight outside the policy (`off_policy_exposure`), and any validation errors that forced tier `no_policy`. The section intro states the classification basis: region by listing venue (RIC suffix), ADR/fund look-through not applied in phase 1.
- **Resolved-k Disclosure** (only if policy supplied) — under the section group, one disclosure line stating the resolved k with its source and `calibration_status: heuristic_phase0`, per policy-loader.md §7.
- **Per-Holding Analysis** (for drill-down holdings: score trend, risk profile, flags, news highlights; view conflicts called out; tag any **profile-derived score** and its same-scale guard outcome as in Factor Analysis; factor names render with the §13.3 plain-language gloss by reference under `audience=client_safe`)
- **Suitability Assessment** (alignment with client goals AND with active house view if present; cite basis_statement)
- **Recommended Actions** (prioritized High/Medium/Low per recommendation-matrix.md, with specific action types; rationale cites view tilts where applicable), framed per conventions §12 (informational preface required; `action_labels=plain` supported). Under `audience=client_safe`, `action_labels=plain` is implied per conventions §13.2 — action labels always render neutral status descriptions, and any accompanying magnitude renders as distance-to-threshold arithmetic per §12.3, not a suggested trade size.
- **Appendix: Methodology** (brief Parallax scoring note)
- **About This Report** (always present): one line stating branding state. Format is the markdown column of integration-pattern.md §7 (render per table; do not collapse) so `schema_unavailable` correctly stays in the white-label branch rather than falling back to default Parallax. The unconditional §7 currency-basis line arrives second in the seam's `about_lines` — do not render it again from the §7 table. If a logo was skipped per the Branding Header rule above, its `Logo on file: <basename>` line likewise arrives in the seam's `about_lines` (third, after the currency-basis line) — do not append it separately. Under `audience=client_safe` the §13.4 mode line and any resolution notice arrive already in the seam's `about_lines` — do not add them separately.

Apply audience render mode per `parallax-conventions.md` §13; default `internal_analyst`. This wiring covers verdict-sensitivity omission, action-label mode, factor gloss, and the §13.4 footer line; body-prose cutoff arithmetic and ops apparatus are not yet swept for this skill.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.
