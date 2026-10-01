---
name: parallax-client-review
description: "RIA/wealth advisor client portfolio review: full analysis, redundancy, health flags, macro context, per-holding drill-down, prioritized recommendations, and AI assessment via Parallax MCP tools. Holdings as [{symbol, weight}]; optional policy= for SAA/TAA drift diagnostics. NOT for fund manager briefs (use /parallax-morning-brief), not for quick stock checks (use /parallax-should-i-buy), not for retail health checks (use /parallax-portfolio-checkup), not for trade recommendations with target weights (use /parallax-rebalance), not for drawdown attribution (use /parallax-explain-portfolio)."
---

<!-- white-label: integration-pattern.md -->

# Client Portfolio Review

## When not to use

- Fund manager morning brief → use /parallax-morning-brief
- Single stock analysis → use /parallax-should-i-buy
- Retail investor health check → use /parallax-portfolio-checkup
- Trade recommendations with target weights → use /parallax-rebalance
- "Why am I down?" attribution → use /parallax-explain-portfolio

## Gotchas

- Expected Parallax spend: ~105 tokens at 10 holdings (`_parallax/token-costs.md`): 8 drill-downs + 5 news + assessment + 2× `analyze_portfolio`.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §0.3 field-request integrity, §1 RIC resolution, §2 identity cross-check, §3 parallel execution, §4 fallbacks, §11 sensitivity, §12 framing, §13 audience mode, §14 host primitives, §15 translation.
- JIT-load `_parallax/house-view/loader.md` FIRST; if a view is present follow §2, §3, §4, §5, §6. The view shapes suitability AND recommendations: misaligned holdings get higher trim priority, aligned holdings implicit support.
- JIT-load `references/recommendation-matrix.md` for priority classification, flag conditions, and drill-down criteria.
- JIT-load `_parallax/client-policy/policy-loader.md` when `policy=` is present. S1/S2 math via `adaptation.py` only — never inline. Policy sections render in the body after House View Alignment (policy-loader.md §7), never before the first render-gate anchor. No `policy=` means no policy sections and no disclosure line.
- analyze_portfolio called twice — once for performance/returns fields, once for concentration/attribution fields (split to manage response size). **Call shape:** `portfolio=[{date: <as-of ISO>, symbol: <ric>, weight: <w>}, ...]` with `fields=[...]`, subject to the discovered live schema. The date is an as-of date over a price history, not a snapshot key: a deployed connector may need a date early enough that each holding has sufficient prior price history, so today's date can return empty or fail validation. Read the live schema's own description first. When the schema gives no guidance, date every holding at the most recent completed trading day at least 5 calendar days in the past, one date for all holdings, and state the date used in the report — live schema still wins over this default. The parameters `holdings` and `lens` do not exist in the deployed schema. **Fallback** (on MCP schema validation error OR truncated/oversized response): `check_portfolio_redundancy` (concentration) + `quick_portfolio_scores` (factor tilt) + individual `get_stock_outlook` with `aspect="risk_return"` (performance).
- Per-holding drill-down capped at 8; mixed-exchange portfolios may need split scoring (conventions §4).
- Pre-Render uses `_parallax/white-label/rm_consumer.py` → `load_rm_branding_context("portfolio review", audience=<flag or None>)`: it owns source redaction, voice isolation, branding fallback and §13.1 audience resolution; use its `header_lines` and `about_lines` exactly once and read `resolved_audience` from it. Branding Header is `**<client_name>** portfolio review` by design, not the generic §5 template.
- A `lang=` value other than `en` makes Step 7 mandatory (conventions §15).

Presentation-ready portfolio review with health flags and prioritized recommendations for wealth advisors.

## Usage

```
/parallax-client-review [{"symbol":"AAPL.O","weight":0.25},{"symbol":"BRK-B.N","weight":0.20}] client="conservative retiree, income focus, 10yr horizon"
/parallax-client-review [{"symbol":"AAPL.O","weight":0.25},{"symbol":"BRK-B.N","weight":0.20}] client="conservative retiree, income focus, 10yr horizon" lang=zh-CN register=retail policy="/path/to/client-policy.yaml"
/parallax-client-review [{"symbol":"AAPL.O","weight":0.25},{"symbol":"BRK-B.N","weight":0.20}] audience=client_safe
```

Optional after the holdings: `client=`, `lang=<code>` (`en` default; `zh-CN`, `zh-TW`, `zh-HK`, `th`), `register=retail` (translation only), `audience=client_safe | internal_analyst` (§13.1 precedence), `policy=` (file path or inline YAML/JSON: strategic allocation, bands, tactical budget; absent means today's behaviour). **No invocation `k=` flag** — the locked spec allows a firm-level default and a per-mandate override only, both in the policy artifact's `adaptation` block. `benchmark=` is not consumed; a future benchmark-relative revision passes plain ETF tickers through `etf_daily_price`, never `export_price_series`.

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1). Local helpers (`adaptation.py`, `coverage_check.py`, `rm_consumer.py`) run via `run-shell`.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` and `references/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Steps 2 and 4, including the V1 and `analyze_portfolio` fallbacks) to the exact callable and schema exposed now; read `analyze_portfolio`'s live schema for the `portfolio`/`fields` shape before building the call.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: holdings; `client=`; `lang=`; `register=`; `audience=`; `policy=`.
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture tilt vector, excludes and basis_statement (frames Suitability). On §2 failure run without the view.
5. `load-reference` `_parallax/white-label/integration-pattern.md` §2; call `load_rm_branding_context("portfolio review", audience=<flag or None>)` once and keep `header_lines`, `about_lines`, `resolved_audience`.
6. `load-reference` `references/recommendation-matrix.md`.
7. **Policy load (only with `policy=`).** `load-reference` `_parallax/client-policy/policy-loader.md`; `write-artifact` inline input to a private mktemp file; `run-shell` `python3 "<skill-dir>/../_parallax/client-policy/adaptation.py" --policy "$POLICY" --json`; capture `errors`, `fallback_tier`, `resolved_k`, `k_source`, `policy_hash`, `data_quality`. Blocking errors → tier `no_policy` for the run; dimension-scoped errors drop only that dimension to multiplier_fallback (policy-loader.md §2). Render the error list in Policy Data Quality and continue.

### Step 1 — Resolve inputs

Validate holdings: RIC format (plain tickers → conventions §1), weights ~1.0. Home markets from RIC suffixes (needs no tool output). As-of date for `analyze_portfolio` per the Gotchas call-shape note.

### Step 2 — Fetch (parallel batches)

`call-tool` ALL rows in ONE turn, including the macro calls (they need only the RIC suffixes):

| Tool | Parameters | Notes |
|---|---|---|
| `analyze_portfolio` | `portfolio=[{date, symbol, weight}]`, `fields=["performance_metrics","rolling_metrics","drawdown_analysis","portfolio_summary","time_period_returns"]` | Returns/risk. State the as-of date used. |
| `analyze_portfolio` | same portfolio, `fields=["concentration_metrics","sector_allocation","company_contribution"]` | Concentration and attribution; two calls to stay under the 180K-char ceiling. |
| `check_portfolio_redundancy` | `holdings` | Overlap; cross-checked against `sector_allocation` in Step 3. |
| `get_peer_snapshot` | per holding, all in parallel | **Primary scoring source** (V2), aggregated per loader.md §3b. A timeout leaves the holding unscored; a successful call with no data for the listing is a coverage gap → `get_company_info` + `get_score_analysis` for that holding, labelled **profile-derived score**, with the same-scale guard in Step 3. |
| `get_company_info` | per holding, all in parallel | **Ground-truth oracle** (loader.md §5 rule 3); records `expected_name`. |
| `list_macro_countries` | — | Coverage |
| `macro_analyst` | `component="tactical"` per unique covered home market (cap 3) | Fired in the same turn, not after. |
| `quick_portfolio_scores` | `holdings` | V1 only; not with `PARALLAX_LOADER_V2=1` and a view active; the same coverage-gap rule applies. |

After Step 3 selects drill-down holdings (≤ 8), `call-tool` together per holding: `get_score_analysis` (`weeks` as int 26, non-default — §0.2), `get_stock_outlook` (`aspect="risk_return"`), `get_peer_snapshot`; and `get_news_synthesis` (async, cap 5) for holdings >10% weight AND flagged, or in sectors with active macro developments.

### Step 3 — Verify

- Cross-validation per conventions §2 / loader.md §5 rule 3 on Batch A and again at drill-down time (queries can bind differently): V2 mismatches ⚠ MISMATCH and excluded from aggregates, scores read from the `comparison[]` row matching the queried symbol; V1 mismatches re-scored individually and marked UNTRUSTED for the batch profile.
- **Same-scale guard** for every profile-derived score: cross-check against the holding's latest `get_score_analysis` row; agreement (same composite field, 1–10 scale) → renders alongside the composite, tagged; disagreement or a single source → **unverified — not combined with the composite ranking**.
- `_meta.invalid_fields` on each `analyze_portfolio` response (conventions §0.3 item 3). Schema-validation error or oversized response → the Gotchas fallback (`check_portfolio_redundancy` + `quick_portfolio_scores` + `get_stock_outlook` risk_return).
- **Sector cross-check** whenever both `analyze_portfolio.sector_allocation` and redundancy sector weights exist: `write-artifact` each payload to a private mktemp JSON, then `run-shell` `python3 "<skill-dir>/../_parallax/coverage_check.py" --portfolio-sectors "$PORTFOLIO_SECTORS" --redundancy-sectors "$REDUNDANCY_SECTORS" --holdings "$HOLDINGS"` with every `--holdings` entry tagged with its `sector` from the `analyze_portfolio` mapping (the redundancy payload is aggregate-only; without tags `absent_holdings_basis` is `not_computable`). Render from its verdict: `consistent` → normal; `coverage_limited` → label redundancy figures **coverage-limited**, name `diverging_sectors` and any `absent_holdings` (basis-qualified: `sector_inference` → say inferred; `not_computable` → say nothing about absence), prefer the `analyze_portfolio` weights for every concentration figure. Never reproduce the arithmetic in prose (loader.md §2, "Why the helper, not inline math").

### Step 4 — Compute

Health flags **per holding** per `references/recommendation-matrix.md` (Low Score ≤ 5.0, Concentration >15% or in a top-3 >45%, Redundancy pair, Value Trap ≤ 3.0, Macro Misalignment); with a view add View Misalignment (>25% off the view-tilted target) and View Excluded, plus the portfolio view-alignment score. Redundancy low-confidence under 60% coverage. Health status: Healthy (0) · Monitor (1–2) · Attention (3+); View Excluded is Attention regardless. Drill-down selection: weight >10%, any flag, or macro-misaligned; by flag count then weight; cap 8. Priorities and action types per the matrix; every recommendation cites a finding; View Excluded → Exit (High); View Misalignment → Trim/Reweight (Medium unless paired).

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

Then `call-tool` `get_assessment` as soon as recommendations are assigned (a deterministic matrix lookup — do not wait for pending news; include news only if resolved) with: composition, factor scores, flags (incl. View flags), macro, drill-down findings, recommendations, client context, the active view (basis_statement + tilts + excludes), and, with a policy, the SAA drift findings, TAA verdicts, resolved k with source, and fallback tier. Compose all non-assessment sections while it runs; insert on resolve or render the §4 async note.

### Step 5 — Compose

Fill **Output Format** below in order: House View Preamble per loader.md §5.1; the seam's `header_lines` and `about_lines` once each; §11 sensitivity lines (internal_analyst only); §12 preface and `action_labels` per audience; §13 relocation rules exactly as the Output Format states (policy family and ⚠ MISMATCH never relocate); `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 rule 5 when a view is active, otherwise `parallax-conventions.md §9.1`. Audit entry per loader.md §6; with a policy add the §6.2 fields `client_ref`, `client_policy_applied`, `policy_hash`, `policy_fallback_tier` (audit values: `weights_only` / `full` / `partial_dimensions` unchanged; helper `no_policy` → `invalid`; runtime helper failure → `unavailable`; never `no_policy`), `resolved_k`, `k_source`; never a client name.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/clientrev.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill client-review < "$DRAFT"; rm -f "$DRAFT"
```

The entire final English message is that command's stdout, or the sole input to Step 7. The stderr `[render-gate] WARN:` line is diagnostics: never include or translate it. Degraded-state notes go inside their section. If `run-shell` is absent, apply conventions §14.3: render-gate row; and the policy sections are gate-shaped — without `adaptation.py` they render **UNVERIFIED** (`policy_fallback_tier: unavailable`), never a prose approximation.

### Step 7 — Translate (conditional)

Only when `lang=` is present and not `en`. Translate per `parallax-conventions.md` §15 (routing block §15.2, failure footers §15.3, disclaimer boundary check §15.4 with the audit `notes` entry). Body is the gated Step 6 stdout including About This Report, the §9.2 disclosure and the disclaimer; never run the gate on translated text; pass `register: retail` only when supplied.

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
- **Concentration & Redundancy** (flagged issues; coverage reliability note if applicable — label redundancy figures **coverage-limited** with the diverging sectors and absent holdings when `coverage_check.py` returned that verdict, Batch C step 3. Under `audience=client_safe`: the coverage reliability note states the classification and its plain-language meaning — redundancy detection covered only part of the portfolio, so its findings are lower-confidence — and omits the coverage-percentage cutoff arithmetic, per conventions §13.2; the coverage-limited label, its plain-language meaning, and the diverging sector names stay in the body as a data-quality caveat, while the numeric divergence figures from `coverage_check.py` relocate to the Methodology appendix (internal))
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
- **Methodology appendix (internal)** (`audience=client_safe` only, and only when at least one item was relocated into it; renders immediately before About This Report) — the clearly-separable trailing home per conventions §13.2 for this skill's relocated methodology/ops apparatus: the `coverage_check.py` numeric divergence figures (Concentration & Redundancy). Distinct from **Appendix: Methodology** above, which is a client-facing scoring note that renders in both modes — never merge the two. It never receives non-suppressible surfaces (§13.2 list) or policy-family content — those render in place. Under `internal_analyst` this section does not exist; the same material renders inline as specified above.
- **About This Report** (always present): one line stating branding state. Format is the markdown column of integration-pattern.md §7 (render per table; do not collapse) so `schema_unavailable` correctly stays in the white-label branch rather than falling back to default Parallax. The unconditional §7 currency-basis line arrives second in the seam's `about_lines` — do not render it again from the §7 table. If a logo was skipped per the Branding Header rule above, its `Logo on file: <basename>` line likewise arrives in the seam's `about_lines` (third, after the currency-basis line) — do not append it separately. Under `audience=client_safe` the §13.4 mode line and any resolution notice arrive already in the seam's `about_lines` — do not add them separately.

Apply audience render mode per `parallax-conventions.md` §13; default `internal_analyst`. Wherever a health flag or other published-cutoff classification renders under `audience=client_safe` (Concentration & Redundancy flagged issues, Per-Holding Analysis flags, Recommended Actions rationale), state the classification and its plain-language meaning and omit the cutoff arithmetic, per conventions §13.2 — the thresholds are static and published in the reference docs, so nothing about them requires retention and nothing relocates. This wiring is fully conformant with the §13.2 table for this skill: verdict-sensitivity omission (including the SAA Drift §11 flip line), action-label mode, factor gloss, the §13.4 footer line, published-cutoff arithmetic (the health-flag thresholds and the redundancy coverage-confidence cutoff, as above), and methodology/ops apparatus (the coverage cross-check divergence figures — relocated to the Methodology appendix (internal)). The policy section family renders in place, unchanged, in both modes as stated above.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- `analyze_portfolio` schema error or oversized response: the Gotchas fallback; every field the fallback cannot supply is named as unavailable.
- Scoring coverage gaps: profile-derived scores with the same-scale guard; unverified holdings are excluded from the composite ranking and named.
- `get_assessment` pending: Suitability Assessment renders the §4 async note; recommendations still render from the matrix.
- Policy helper failure or invalid payload: `no_policy` / `unavailable` tier per Step 0.7 and Step 5; Policy Data Quality lists every error; the review continues.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- First line is the House View Preamble, the seam's header line, or `## Portfolio Summary`; every Output Format section rendered or marked unavailable with its reason; policy sections present iff `policy=` was supplied.
- Every rendered policy number came from `adaptation.py` and every coverage figure from `coverage_check.py`; nothing was recomputed inline.
- Every recommendation cites a finding; under `client_safe`, action labels are neutral and cutoff arithmetic is omitted.
- When a view is active: the `view_status` banner appears verbatim; audit entry appended per loader.md §6 (every consume event, policy fields when applicable, never a client name).
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present; expected spend stated (Gotchas).
- Translation (if requested) completed per §15, or the §15.3 footer explains why not.
