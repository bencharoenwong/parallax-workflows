# Parallax House View — Shared Loader & Resolver

JIT-loaded by every `parallax-*` skill that consumes the active house view. Defines: where the view lives, how to validate it, how to apply tilts to MCP tool calls, how to resolve conflicts with explicit user constraints, and how to render conflict banners.

**Schema reference:** `_parallax/house-view/schema.yaml` (canonical YAML structure).

---

## 1. Locating the active view

**Local-filesystem path (current):** `$PARALLAX_HOUSE_VIEW_DIR` if set, else `~/.parallax/active-house-view/`.
- `view.yaml` — canonical structured tilts + metadata
- `prose.md` — verbatim CIO narrative with `paired_yaml_hash` frontmatter
- `audit.jsonl` — append-only log of consume events

On successful load, the loader MUST emit an explicit log line: `"Active house view resolved from: <path>"`.

**No active view:** if the directory or `view.yaml` is missing, behave as today — no tilts, no banners, standard disclaimer. Do not error; do not prompt the user.

**Managed path (roadmap):** Supabase `house_views` table keyed by `org_id`. Loader fetches latest non-expired version. Loader.md is identical from the consumer's perspective — only the resolver mechanism changes.

---

## 2. Load-time validation (always run before applying tilts)

Run these checks in order. On any failure, behave per "Failure handling" below — do NOT silently apply a broken view.

1. **Read** `view.yaml` and `prose.md`. Note `metadata.schema_version` (int) — if absent, treat as `schema_version = 0` (legacy pre-0.5c view written before the field was mandatory). Gate optional-field reads (`calibration_status`, future additions) on schema version: v0 views get default values per each field's "absence-means" rule; v1 views MUST have all v1 fields present and the loader may fail-closed if they are missing.
2. **Recompute** `view_hash = sha256(canonical_yaml_body)` per schema.yaml §"view_hash computation".
3. **Verify** `prose.md` frontmatter `paired_yaml_hash == view_hash`. If mismatch → drift detected (YAML body changed without re-pairing).
3a. **Verify prose body integrity** — recompute `prose_body_hash` per schema.yaml §"prose_body_hash computation" and compare to `prose.md` frontmatter `prose_body_hash`. If mismatch → drift detected (prose body changed without re-pairing). Two narrow backward-compat carve-outs apply when the frontmatter field is **missing**:

    - If `metadata.upload_timestamp < 2026-04-24T00:00:00Z` → legacy view. Skip the check and surface a **visible warning in the load preamble** (not a silent one-time note): "Legacy view: prose body integrity not verified. Re-pair via `/parallax-load-house-view --re-pair` to enable." Do not allow downstream consumers to silently ignore — the warning MUST appear in rendered output alongside the view-active banner.
    - If `metadata.upload_timestamp >= 2026-04-24T00:00:00Z` → **hard drift failure**. The field was required at save time for every post-2026-04-24 view; its absence means the frontmatter was tampered with or the writer skipped the step. Emit the standard drift message and refuse to apply the view. This closes the "legacy-view downgrade attack" where an adversary removes `prose_body_hash` from frontmatter to degrade the gate to a soft warning.
4. **Verify** `metadata.version_id == prose.md frontmatter version_id`.
5. **Verify** `extraction.uploader_confirmed == true`.
6. **Check expiry (delegate to `view_status` helper — operator-agnostic):**
   - Shell out to `python -m view_status --json` (cwd `_parallax/house-view/`, or import `view_status.compute_status()`). The helper is the single source of truth for date math; do NOT recompute days-remaining inline. This keeps the banner identical across operator LLMs (Claude / GPT / Gemini).
   - The helper returns one of: `none | malformed | not_yet_effective | expired | critical | warning | active`. It also returns `banner` (the exact string to surface) and `tilts_apply` (whether downstream multipliers should run).
   - **Hard-block states** (`tilts_apply == false`): `none`, `malformed`, `expired`, `not_yet_effective`. Emit the helper's `banner` verbatim and skip §3-§5 multiplier application.
   - **Soft states** (`tilts_apply == true`): `active`, `warning`, `critical`. Emit the helper's `banner` in the load preamble, then continue with §3.
   - Legacy inline rules (kept for spec completeness — the helper enforces them):
     - Malformed-window guard: both `effective_date` and `valid_through` null → malformed.
     - Effective expiry = `metadata.valid_through` if non-null, else `metadata.effective_date + metadata.auto_expire_days`.
     - `today > effective_expiry` → expired.
     - `today < metadata.effective_date` → not yet effective.
7. **Surface low-confidence warnings**: any `extraction.extraction_confidence[field] < 0.6` → list in load preamble.

### Failure handling

| Check failed | Behavior |
|---|---|
| `view.yaml` missing | No active view. Run skill normally with standard disclaimer. |
| Hash mismatch (drift) | DO NOT apply tilts. Emit: "House view prose and structure are out of sync — re-confirm via `/parallax-load-house-view --re-pair`. Running without view." |
| `uploader_confirmed = false` | DO NOT apply tilts. Emit: "House view extraction was never confirmed by uploader. Run `/parallax-load-house-view` to confirm." |
| Expired | DO NOT apply tilts. Emit: "Active house view '[view_name]' expired [N] days ago. Falling back to neutral. Update via `/parallax-load-house-view --extend`." |
| Not yet effective | DO NOT apply tilts. Emit: "House view '[view_name]' becomes effective on [date]. Running without view until then." |
| Malformed window (both `effective_date` and `valid_through` null) | DO NOT apply tilts. Emit per §2 step 6 guard. |
| Low-confidence fields | Apply tilts, but include in load preamble: "House view loaded with low extraction confidence on: [field list]. Verify before acting." |

### Soft-warning thresholds

The `view_status` helper emits the banner directly; this table documents the tiers it implements. The exact wording in the banner is the helper's responsibility — do not paraphrase, surface the helper's `banner` field verbatim.

| Condition (days_remaining = effective_expiry − today) | Helper state | Banner (gist) | tilts_apply |
|---|---|---|---|
| `< 0` | `expired` | "Expired N day(s) ago. Tilts NOT applied. `--extend` or reload." | false |
| `0 ≤ N < 10` | `critical` | "Expires in N day(s). Have you received an updated CIO view? `/parallax-load-house-view` to refresh." | **true** |
| `10 ≤ N < 14` | `warning` | "Expires in N days; consider refreshing soon." | true |
| `N ≥ 14` | `active` | "Active house view: '...' — N days remaining." | true |
| `tilt_variance < 0.5` across non-zero tilts | (orthogonal warning, emitted in addition to the helper banner) | "Minimal differentiation; tilts will have weak portfolio effect." | n/a |

**Active-view banner is REQUIRED on every consumer skill load preamble.** It is not a "first call per session" courtesy — every load surfaces it. The portfolio-builder gotcha already enforces this for one skill; the helper makes it cheap to enforce everywhere.

**Why the helper, not inline math:** date arithmetic and threshold comparisons in markdown are an operator-LLM trust assumption. Shelling out to `view_status` (pure stdlib + PyYAML, no network) returns the same banner whether the operator is Claude / GPT / Gemini / local model. See `tests/test_view_status.py` for the boundary cases (9 / 10 / 13 / 14 days).

---

## 3. Multiplier mapping

### Framework components

The four components (`econometrics_phase`, `valuation_state`, `market_entropy`, `psychological_wavelength` — kept as field identifiers for data-contract stability) are **encoding-only**. Extractors populate them at ingest from CIO prose (see `skills/load-house-view/SKILL.md`); they are stored in `view.yaml` for forward-compatibility but are NOT translated into factor multipliers, universe effects, or consumer-skill output by the current loader.

Rationale: MCP equity-only scope doesn't yet carry expected-return / volatility inputs needed for a full multi-component composite. Asset-class component weights are deployment-specific judgment calls that downstream users should calibrate themselves. Guessing at a partial formula risks silently miscalibrating portfolio math.

### Factor aliases (canonical vs synonyms)

| Canonical | Synonym | Collapse rule |
|---|---|---|
| `factors.profitability` | `factors.quality` | If both set, canonical wins; emit warning |
| `factors.low_volatility` | `factors.defensive` | If both set, canonical wins; emit warning |

On load, collapse `quality → profitability` and `defensive → low_volatility`. Downstream multiplier math and composite re-ranking should only reference the canonical names. Views written before 2026-04-22 (with only `quality`/`defensive`) continue to work — the loader maps them at read time.

### Sector / region / theme tilts (universe + weight effect)

| Tilt | Universe effect | Weight multiplier | Notes |
|---|---|---|---|
| **+2** (Big OW) | Force-include if absent from candidates | 1.50× | Cap final exposure at 2× neutral to prevent runaway |
| **+1** (OW) | Boost ranking | 1.25× | |
| **0** | No effect | 1.00× | |
| **-1** (UW) | De-rank | 0.75× | |
| **-2** (Big UW) | Exclude unless explicitly named by user | 0.50× | |

**Application:** when calling `build_stock_universe`, prepend tilt context to query (e.g., "exclude tech, overweight defensive sectors and small-cap utilities"). After candidates return, re-rank by `score × tilt_multiplier(holding's sector/region/theme)`.

### Factor tilts (re-weight Parallax composite)

| Tilt | Factor weight in composite re-rank |
|---|---|
| **+2** | 2.00× |
| **+1** | 1.50× |
| **0** | 1.00× |
| **-1** | 0.50× |
| **-2** | 0.25× |

**Application:** For each candidate's factor scores from `get_peer_snapshot` or `quick_portfolio_scores`, compute weighted composite using the canonical factor set (after alias collapse above):
```
composite = (w_v × value + w_p × profitability + w_m × momentum + w_lv × low_volatility + w_ts × trading_signals)
          / (w_v + w_p + w_m + w_lv + w_ts)
```
where `w_x = factor_tilt_multiplier(x)`. Re-rank by composite.

**Factor-to-Parallax mapping:** Parallax tool outputs (from `get_peer_snapshot`, `quick_portfolio_scores`) may use either the canonical factor names (`profitability`, `low_volatility`) or the synonyms (`quality`, `defensive`). The alias rule bridges symmetrically — apply the same `quality↔profitability` / `defensive↔low_volatility` collapse to the Parallax response before matching to view tilts. If the view tilts `profitability` and Parallax returns `quality`, treat them as the same dimension; same for the reverse. `trading_signals` requires a short-horizon technical score — when Parallax does not expose one, fall back to the tool's `momentum` as a proxy and note this in the output so consumers see the substitution.

### Style semantics (per dimension)

| Dimension | Mechanism | Implementation |
|---|---|---|
| `cap_size.{large,mid,small}` | Universe filter | OW small-cap → include small-caps in universe even if NL query doesn't suggest. UW small-cap → filter out unless user explicitly named small-caps. |
| `growth_value.{growth,value}` | Factor tilt | OW value → set `factors.value` += 1 (max +2). OW growth → set `factors.momentum` += 1 AND `factors.value` -= 1 (min -2). Loader warns on conflict if uploader set both `growth_value` and `factors.value` directly. |

### Macro regime mapping (auto-applied at ingest, surfaced for confirmation)

**Absent or null sub-fields are not defaulted to neutral.** If `macro_regime` is absent from the view, OR if `macro_regime.growth` is null, skip the auto-tilt row for that dimension entirely — no delta applied, no rationale shown. Mandate-driven (ESG) and geopolitical views typically have no macro regime; forcing `neutral+neutral` would misrepresent the uploader's thesis.

| `macro_regime.growth` + `inflation` | Auto-tilt deltas applied | Rationale shown to uploader |
|---|---|---|
| `recessionary` + any | `factors.defensive` +2, `factors.momentum` -1 | "Recessionary regime → overweight defensive factor, underweight momentum within equity." |
| `slowing` + `sticky` | `factors.defensive` +1, `factors.quality` +1, `factors.momentum` -1 | "Slowing growth + sticky inflation (stagflation-lite) → quality + defensive bias." |
| `reflationary` + any | `factors.value` +1, `factors.momentum` +1 | "Reflationary regime → value + momentum bias." |
| `expansion` + `benign` | `factors.momentum` +1 | "Healthy expansion → momentum bias." |
| `neutral` + `neutral` | no auto-tilt | "Neutral regime → factor tilts left to explicit settings." |
| `null` / absent | no auto-tilt | "Source did not frame a macro regime — factor tilts left to explicit settings." |

These deltas STACK with explicit factor tilts — uploader can override at confirmation gate.

**Equity-only scope note (always shown at ingest):**
> "This system applies house view within equity portfolios only. Macro regime signals are interpreted as within-equity factor tilts (e.g., recession → overweight DEFENSIVE). Cross-asset allocation (fixed income, FX, credit, commodities, alternatives) is deliberately outside scope. If the source document carries views on non-equity asset classes (full TAA workbooks typically do), those views are NOT captured by this schema and must be applied via a separate allocation layer."

### §3b. Client-side portfolio score aggregation (`PARALLAX_LOADER_V2`)

When `PARALLAX_LOADER_V2=1`, portfolio consumer skills call `get_peer_snapshot` per holding (fanned out in parallel) rather than `quick_portfolio_scores`. Aggregate the per-holding scores client-side as follows:

1. **Collect** `VALUE`, `QUALITY`, `MOMENTUM`, `DEFENSIVE` from each successful `get_peer_snapshot` response. Apply the factor alias collapse from §3 above (`quality → profitability`, `defensive → low_volatility`) before aggregating.
2. **Weight** each factor score by the holding's portfolio weight.
3. **Sum** the weighted scores: `portfolio_VALUE = Σ(weight_i × value_i)` etc.
4. **Partial results**: if one or more holdings timed out or errored, compute the weighted average over successful calls only — renormalise weights to sum to 1.0 over successful holdings and annotate the composite as partial.
5. **Apply tilts**: if an active view is present, apply the §3 factor-tilt multipliers to the composites.

**For 10+ holdings**: parallelise all fan-out calls (cap 8 concurrent calls); if N≥2 calls time out, mark those holdings as "scores unavailable" and fall back to health-flags-only scoring for the missing positions.

---

## 4. Conflict resolution: user constraints vs. view tilts

**Three principles, applied in order:**

1. **Explicit user scope is sovereign.** Names, sectors, themes the user explicitly requests are non-negotiable inclusion/exclusion — except hard excludes (see exception below).
2. **Tilts shape weights and ranking within scope, never membership of explicit requests.**
3. **Conflicts always banner-flag in output. Never silent.**

### Exception: hard excludes

`tilts.excludes` list is honored even over explicit user requests. When user names something on the excludes list:
- Surface a block message: "Cannot include [X]: blocked by house view ([exclude_reason]). Override requires editing the view via `/parallax-load-house-view --edit`."
- Continue building the rest of the request without [X].

### Resolution table

| User input | View | Behavior | Banner |
|---|---|---|---|
| "Build a tech portfolio" | `tech: -2` | Build tech portfolio per request. Within tech, apply other tilts (factor, style). Render conflict banner. | "House view is UW tech (set [date]); built per your explicit scope." |
| "Build a global equity portfolio" | `tech: -2` | Apply tilt fully — tech under-weighted vs. neutral. | None. |
| "Include NVDA" (NVDA not in excludes) | `excludes: [tech]` (NVDA implied) | Include NVDA. | "House view excludes the tech sector; NVDA included per your explicit request." |
| "Include GAZP.MM" (GAZP in excludes list) | `excludes: ["GAZP.MM"]` | Refuse to include. | Block message above. |
| "Exclude X" | `OW X` (sector or theme) | Exclude X. | "House view OW [X]; excluded per your request." |
| Silent on tech | `tech: -2` | Apply tilt. | None. |

---

## 5. Output rendering rules

When an active view is loaded and applied, every consumer skill MUST:

1. **Load preamble** (top of output, above the main result):
   > **House view active:** *[view_name]* — uploaded by [uploader_role] on [upload_date], effective [effective_date] through [valid_through or computed_expiry].
   >
   > [Any low-confidence warnings from §2.]
   > [Any soft-warning thresholds from §2.]
   >
   > [Calibration disclosure from §5.1a — MANDATORY when `metadata.calibration_status == "heuristic_phase0"` or field is absent.]

   ### §5.1a Calibration disclosure (mandatory, unconditional)

   Any time an active view is loaded AND `metadata.calibration_status` is either `"heuristic_phase0"` OR absent (treat absence as heuristic_phase0), the load preamble MUST include this line verbatim:

   > *Tilt multipliers are heuristic and uncalibrated (`calibration_status: heuristic_phase0`). Intended for directional research only — do not use for regulatory capital, fiduciary-grade portfolio construction, or client-facing recommendations.*

   When `metadata.calibration_status == "empirical_phase1"` (after the calibration backtest lands), replace with a one-line pointer to calibration evidence. The disclosure is **not optional** (XAI compliance; SR 11-7 conceptual-soundness; EU AI Act Art 13 transparency-by-design). No client-facing or regulated deployment is permitted while the `heuristic_phase0` disclosure is active.

2. **Conflict banners** — render inline at the section where the conflict arose (e.g., universe selection, allocation), not bundled at the end.

3. **Ground-truth panel** (REQUIRED when any per-holding score is rendered): next to every factor score, show the company name that the scoring tool actually returned (from `get_peer_snapshot.target_company` or `quick_portfolio_scores.holdings_analyzed[].company_name`) and the input ticker. If the returned name does not match the `get_company_info` name-of-record for the input ticker, flag the row **loudly** (e.g., `⚠ MISMATCH: score attributed to <X>, expected <Y>`). Never display scores as authoritative when the name-mismatch is present — the score belongs to a different company.

4. **Divergence assertion on universe composition** (REQUIRED for skills that call `build_stock_universe` with multi-sector or multi-theme tilts): after the call returns, compute the sector distribution of the result. If the caller requested N≥2 sectors/themes in the tilt-prepended query and the returned distribution has `max_sector_share / total > 0.6`, emit a **fail-loud warning** and **by default re-issue the call as N parallel per-sector (or per-theme) queries and merge the results** (deduplicating by symbol, keeping the highest rank). Only fall back to refusing to render the portfolio when the per-sector re-issue *also* produces skewed output (e.g., some sectors return zero results). Do not silently proceed. This does NOT apply to legitimately concentrated tilts where only 1 sector/theme was requested (e.g., "100% energy" from a pure-energy view). *Rationale: in practice the universal-universe query collapses to whichever sector the embedding-based matcher considers most prototypical for the tilt language ("defensive" → biotech-heavy Healthcare), so per-sector re-issue is the only path that actually reflects the view's multi-sector intent.*

5. **View-aware disclaimer** (bottom — replaces the standard parallax-conventions §9.1 disclaimer):
   > *"This analysis reflects active house view '[view_name]' uploaded by [uploader_role] on [upload_date], effective [effective_date]. Tilts and excludes per the loaded view; conflicts with explicit user scope are flagged inline. Outputs should be reviewed against client suitability before any action."*

6. **AI-interaction disclosure** (bottom, immediately above the view-aware disclaimer — REQUIRED whether or not a view is active; applies to every consumer skill output): Render the canonical banner from `_parallax/parallax-conventions.md §9.2`. The banner is rendered by reference, not inlined — a single source of truth in §9.2 lets counsel sign-off and the forthcoming attribution-API endpoint propagate to all consumer skills with one edit.

   The current §9.2 banner accurately distinguishes deterministic quantitative pipelines from LLM-generated qualitative content (including the LLM-backed Parallax MCP services — news synthesis, macro commentary, assessment — as well as the orchestrating model's narrative and recommendations), and points readers at the Provenance footer and the per-output trace ID. It supersedes the earlier "AI generated factor scores" placeholder, which was technically wrong — factor scores come from CG's deterministic pipeline, not from an LLM.

   Skills MUST render this banner even when running without an active view — AI involvement in scoring synthesis and narrative is independent of view state.

When NO active view is loaded, skills run as today — standard output, no preamble, standard disclaimer. Rules 3 and 4 (ground-truth panel and divergence assertion) AND rule 6 (AI-interaction disclosure) apply whether or not a view is active — they are data-integrity / regulatory requirements, not view-specific features.

---

## 6. Audit logging

Every consume event appends one JSONL line to `~/.parallax/active-house-view/audit.jsonl`. The schema below is stable — the managed version promotes this to a Supabase `house_view_audit` table with identical field names and types, so any local audit file can be bulk-loaded without transformation.

### 6.1 Required fields (every line)

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | Currently `1`. Bump on any breaking change to this table. |
| `ts` | string (ISO 8601 UTC, ending `Z`) | Event timestamp. |
| `view_id` | string (uuid v4) OR `null` | Null when `applied=false` AND reason is `no_view`, OR when `action=="extraction_attempt"` (the draft has no assigned `view_id` until saved). |
| `version_id` | string (uuid v4) OR `null` | Null under the same conditions as `view_id`. |
| `skill` | string | `parallax-<name>` of the consuming skill. |
| `action` | string (enum) | One of: `save`, `clear`, `extend`, `re-pair`, `edit`, `consume`, `extraction_attempt`, `stress_test`, `generate`, `judge`. `consume` is the default for any consumer-skill invocation (portfolio-builder, should-i-buy, etc.). `extraction_attempt` logs ingestion drafts whether or not they became saves — captures retries, edits, and rejects. `stress_test` is emitted by `parallax-stress-house-view` once per run (applied=false unless the CIO opts to update the view at the Phase 4 gate, in which case a separate `save` entry from `parallax-load-house-view` follows). `generate` is emitted by `parallax-make-house-view` once per successful synthesis (applied=true on the corresponding save row; the `generate` row itself is logged via the §6.2 fields below and a separate `save` row from `parallax-load-house-view` lands the view). `judge` is emitted by `parallax-judge-house-view` once per run and is always applied=false (judges never modify the view). The others are operational events from `parallax-load-house-view`. Consumers that encounter an unrecognized `action` value MUST skip the row (forward-compatibility). |
| `applied` | bool | True if tilts were actually applied to the skill's output. False if validation failed, single-stock skill (conflict-flag only), or operational action. |

### 6.2 Conditional fields

| Field | Required when | Type | Notes |
|---|---|---|---|
| `query_summary` | `action == "consume"` | string (≤200 chars) | First 200 chars of the user's input or a one-line summary. |
| `failure_reason` | `applied == false` AND validation failed | string | Human-readable reason tied to a specific §2 failure row (drift / uploader_unconfirmed / expired / not_yet_effective). |
| `attempted_version_id` | `applied == false` AND `failure_reason` is non-null | string (uuid v4) OR `null` | Version ID read from `view.yaml` before validation failed; `null` only when `view.yaml` was unreadable or missing. Lets auditors reconstruct "which version was in a broken state at this timestamp" when the top-level `version_id` had to be null. |
| `applied_reason` | `applied == false` AND validation passed | string | Why tilts weren't applied despite a valid view. Typical values: `"single-stock consumer (loader.md §7.1/§7.2/§7.3)"`, `"divergence refusal (loader.md §5 rule 4)"`, `"operational action (no consume)"`. |
| `parent_version_id` | `action == "save"` AND this save supersedes a prior version | string (uuid v4) | Immediate predecessor's `version_id`. |
| `version_diff` | `action == "save"` AND `parent_version_id` is non-null | object | Flat diff of `tilts` + `excludes` subtrees vs parent, keyed by dotted path to `[old_value, new_value]`. Cap 40 entries. |
| `version_diff_truncated` | `version_diff` was truncated | bool | True if diff exceeded 40 entries. |
| `disposition` | `action == "extraction_attempt"` | string (enum) | One of: `confirmed`, `edited`, `re_extracted`, `rejected`. |
| `draft_yaml_hash` | `action == "extraction_attempt"` | string (sha256 hex) | Canonical hash of the draft the uploader saw (same algorithm as `view_hash`). Correlates to a `save`'s `view_hash` when disposition=confirmed/edited and a save actually landed. |
| `extraction_duration_ms` | `action == "extraction_attempt"` (optional) | int ≥ 0 | Wall-clock from extraction start to disposition. |
| `hint` | `action == "extraction_attempt"` AND `disposition == "re_extracted"` | string (≤200 chars) | Uploader's re-extraction hint. |
| `conflicts_count` | `action == "consume"` | int ≥ 0 | Number of user-scope vs. view-tilt conflicts surfaced inline. |
| `conflicts_summary` | `conflicts_count > 0` | string | Compact per-conflict summary. |
| `output_summary_hash` | `action == "consume"` AND output was rendered | string (sha256 hex) | sha256 of first 1000 chars of the skill's user-facing output. |
| `ground_truth_mismatches` | `action == "consume"` AND any mismatch flagged per §5 rule 3 | int ≥ 0 | 0 if none. |
| `ground_truth_mismatch_detail` | `ground_truth_mismatches > 0` | string | Specifics of each mismatch. |
| `destination` | `action == "clear"` | string | Archive path the cleared view was moved to. |
| `reason` | `action == "clear"` | string | Human-readable clear reason. |
| `disposition` | `action == "stress_test"` | string (enum) | One of: `completed`, `halted_internal` (Phase 1 hard stop), `validation_failed` (Closure 3 gate rejected deltas), `schema_unreadable` (schema.yaml unreadable at validation time — install-time failure, distinct from data-level `validation_failed`). Distinct from extraction_attempt's `disposition` — values do not overlap. |
| `validation_errors` | `action == "stress_test"` AND `disposition` ∈ {`validation_failed`, `schema_unreadable`} | list of `{index, field, reason}` objects | Each error: `index` (int delta position or null for schema-level errors), `field` (delta field name or null), `reason` (human-readable string). For `schema_unreadable`, a single error with `index=null, field=null, reason="schema_unreadable: <exc_class>: <message>"`. |
| `stress_summary` | `action == "stress_test"` | object | Counts and aggregate metadata: `{internal_pass, internal_taste_count, cio_age_days, parallax_age_days, age_delta, external_markets_queried, tilted_markets, uncovered_markets_in_view, states, cio_challenges, taste_decisions, cross_dimension_themes}`. |
| `recommended_deltas` | `action == "stress_test"` (optional) | list of objects | One entry per divergent-stale cell. Each: `{kind: "informational" \| "global", path, market (nullable), cio_value, parallax_signal, parallax_summary, stress_state, cio_age_days, parallax_age_days}`. `path` follows the `--why <tilt-path>` convention (`tilts.<category>.<dim>[.<sub>]`). v1 emits only `kind: "informational"`; v2's `/parallax-load-house-view --apply-stress <audit-hash>` will read this field to pre-populate a draft. |
| `source_tools` | `action == "generate"` | list of string | `["tool:arg1:arg2", ...]` summary of MCP calls used in synthesis (e.g., `["macro_analyst:Japan:tactical", "get_telemetry:overview"]`). Identifies which Parallax surfaces fed this generation; pairs with the `generator_synthesis` provenance class in schema.yaml. |
| `calibration_status` | `action == "generate"` | string (enum) | One of: `heuristic_phase0`, `empirical_phase1`. Mirrors `metadata.calibration_status` written into `view.yaml` for the generated view. Until the empirical calibration backtest lands, every `generate` row carries `heuristic_phase0`. |
| (forbidden on `generate`) | `action == "generate"` | — | `composition_formula`, `aggregator_weights_ref`, `source_snippets`, `pillar_missing_inputs` MUST NOT appear on the audit row. They live on the per-leaf `generator_synthesis` entry in `provenance.yaml` (schema.yaml §"Classification taxonomy"). Putting them on the audit row would violate §6.3 (no skill-specific custom keys) and create a second source of truth for synthesis evidence. |
| `judged_view_id` | `action == "judge"` | string (uuid v4) | The `view_id` of the view being judged. Distinct from the row's top-level `view_id` (which is null when the judge runs without an active view target, or matches `judged_view_id` when targeting the currently-loaded view). |
| `judged_version_id` | `action == "judge"` | string (uuid v4) | The `version_id` of the view being judged. Pairs with `judged_view_id`. |
| `view_age_days` | `action == "judge"` | int ≥ 0 | Staleness of the judged view at judgment time: `floor((judge_ts - view.metadata.upload_timestamp) / 86400s)`. |
| `parallax_age_days` | `action == "judge"` | int ≥ 0 | Maximum staleness across all MCP responses queried during the judgment run. Mirrors `stress_summary.parallax_age_days` semantics. |
| `drift_summary` | `action == "judge"` | object | Counts of judgment outcomes across all judged cells: `{aligned_count, drift_minor_count, drift_material_count, drift_breaking_count, parallax_silent_count, uncovered_count}`. All ints ≥ 0. |
| `recommendations` | `action == "judge"` | list of objects | One entry per cell where the judge recommends an edit. Same shape as `stress_test.recommended_deltas`: `{kind, path, market (nullable), cio_value, parallax_signal, parallax_summary, stress_state, cio_age_days, parallax_age_days}`. v1 emits only `kind: "informational"`; future `/parallax-load-house-view --apply-judge <audit-hash>` will read this field to pre-populate a draft and write `judge_recommendation` provenance entries onto accepted cells. |
| `notes` | any | string | Optional free text for anything that doesn't fit a named field. Not relied upon by downstream queries. |

### 6.3 Forbidden

- **Skill-specific custom keys are not permitted.** If a new field is needed, add it to §6.2 as a conditional field with an explicit required-when rule. Drift here blocks future migration to the managed backend.
- **No PII.** `query_summary` is the only user-derived content; truncate at 200 chars and do not log account IDs, client names, or full holdings arrays.

### 6.4 Minimal examples

```json
{"schema_version":1,"ts":"2026-04-24T05:47:00Z","skill":"parallax-load-house-view","action":"extraction_attempt","applied":false,"query_summary":"ubs_hv_monthly_letter_19_March_en_2.pdf","disposition":"edited","draft_yaml_hash":"9b8c7a...","extraction_duration_ms":47213}
{"schema_version":1,"ts":"2026-04-24T06:00:00Z","view_id":"d6c4...","version_id":"e8fb...","skill":"parallax-load-house-view","action":"save","applied":true,"parent_version_id":"54c2...","version_diff":{"tilts.factors.momentum":[null,-1],"tilts.sectors.health_care":[0,1]}}
{"schema_version":1,"ts":"2026-04-24T06:01:00Z","view_id":"d6c4...","version_id":"e8fb...","skill":"parallax-portfolio-builder","action":"consume","applied":true,"query_summary":"Build me a defensive US equity portfolio, 20 holdings","conflicts_count":0,"output_summary_hash":"abc123...","ground_truth_mismatches":0}
{"schema_version":1,"ts":"2026-04-24T06:02:00Z","view_id":"d6c4...","version_id":"e8fb...","skill":"parallax-should-i-buy","action":"consume","applied":false,"applied_reason":"single-stock consumer (loader.md §7.1/§7.2/§7.3)","query_summary":"/parallax-should-i-buy AAPL.O","conflicts_count":1,"conflicts_summary":"info_tech UW vs AAPL sector","output_summary_hash":"def456..."}
{"schema_version":1,"ts":"2026-04-24T06:03:00Z","view_id":null,"version_id":null,"skill":"parallax-portfolio-builder","action":"consume","applied":false,"failure_reason":"drift: prose.md frontmatter paired_yaml_hash != recomputed view_hash","query_summary":"<user input>"}
```

Managed version (roadmap): same fields, persisted to a Supabase `house_view_audit` table. Field names, types, and required-when semantics carry forward unchanged. A backfill of local audit files is a straight `COPY FROM` of the JSONL.

---

## 7. Single-stock skills (read-only consumers)

Skills like `parallax-should-i-buy` and `parallax-deep-dive` operate per-stock and do NOT apply tilts (no rescoring, no rerank, no peer filtering). They MUST still:

1. Load and validate the active view per §2.
2. After producing their normal output, check whether the stock's sector / region / themes conflict with view tilts.
3. Surface a closing flag if so (see §7.1). Surface inline tokens at specific surfaces per §7.2 and §7.3.
4. Append the audit log entry per §6.

**Rendering order.** Load preamble at the very top (per §5.1). In the main body, the House View Note (§7.1) is rendered **immediately after the scores/factor section** — NOT at the bottom of the output — so the reader sees the view lens before reading the rest. Inline tokens (§7.2, §7.3) appear at the surface where they arise. The bottom of the output carries only the AI-interaction disclosure and view-aware disclaimer.

### §7.1 House View Note (blanket summary, rendered after The Scores section)

Render via `render_view_conflict(kind="blanket", ...)` — see `_parallax/house-view/render_helpers.md` for the canonical template. **Do NOT reproduce the template here** — having the string in two places creates drift risk (runtime Claude may match the visible loader-side string rather than invoke the helper). The helper is the single source of truth.

### §7.2 Peer-suggest conflict token (inline, at Peers table)

When the standard output includes a Parallax-surfaced peer suggestion (`get_peer_snapshot.suggestion`) whose **sector** is in a view-UW sector (tilt ≤ -1) or on the excludes list, render an inline token under the Peers table via `render_view_conflict(kind="peer_suggest", ...)` — see `render_helpers.md` for the canonical template.

**Flag, do not filter.** The peer suggestion is NOT removed from the table — the reader sees it with the token attached. This preserves the §7 "read-only, no tilt application" invariant while closing the silent-disagreement gap. If the suggested peer sits outside the view's tilt surface entirely, no token is rendered.

One token per conflicting peer; multiple tokens stack vertically.

### §7.3 Score-vs-view tension banner (inline, at The Scores section)

When the primary stock's Parallax **total score ≥ 7** AND the stock's own **sector tilt ≤ -1** in the active view, render a one-line banner between the scores table and §7.1 note via `render_view_conflict(kind="score_tension", ...)` — see `render_helpers.md` for the canonical template.

Threshold rationale (internal): 7.0 is the high-confidence band in the Parallax total score distribution; tilts of -1 or -2 are non-neutral conviction. Combining both makes the disagreement non-trivial. No banner when only one side is strong (e.g., score 7 in a neutral-sector view → no tension).

---

## 8. Consumer-skill checklist

Skills that consume the view should add to their `gotchas` frontmatter:

```yaml
gotchas:
  - JIT-load _parallax/house-view/loader.md before applying any portfolio logic
  - If active view is present, follow loader.md §3 (multiplier mapping), §4 (conflict resolution), §5 (output rendering)
  - If validation fails per loader.md §2, run without view and emit the appropriate message
  - Append audit log entry per loader.md §6
```

Workflow steps that apply tilts should explicitly cite the loader section (e.g., "apply factor multiplier per loader.md §3"). This keeps the math consistent across skills.
