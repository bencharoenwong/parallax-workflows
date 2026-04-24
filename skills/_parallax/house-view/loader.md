# Parallax House View — Shared Loader & Resolver

JIT-loaded by every `parallax-*` skill that consumes the active house view. Defines: where the view lives, how to validate it, how to apply tilts to MCP tool calls, how to resolve conflicts with explicit user constraints, and how to render conflict banners.

**Schema reference:** `_parallax/house-view/schema.yaml` (canonical YAML structure).

---

## 1. Locating the active view

**Phase 0 path:** `$PARALLAX_HOUSE_VIEW_DIR` if set, else `~/.parallax/active-house-view/`.
- `view.yaml` — canonical structured tilts + metadata
- `prose.md` — verbatim CIO narrative with `paired_yaml_hash` frontmatter
- `audit.jsonl` — append-only log of consume events

On successful load, the loader MUST emit an explicit log line: `"Active house view resolved from: <path>"`.

**No active view:** if the directory or `view.yaml` is missing, behave as today — no tilts, no banners, standard disclaimer. Do not error; do not prompt the user.

**Phase 1 path:** Supabase `house_views` table keyed by `org_id`. Loader fetches latest non-expired version. Loader.md is identical from this consumer's perspective — only the resolver mechanism changes.

---

## 2. Load-time validation (always run before applying tilts)

Run these checks in order. On any failure, behave per "Failure handling" below — do NOT silently apply a broken view.

1. **Read** `view.yaml` and `prose.md`.
2. **Recompute** `view_hash = sha256(canonical_yaml_body)` per schema.yaml §"view_hash computation".
3. **Verify** `prose.md` frontmatter `paired_yaml_hash == view_hash`. If mismatch → drift detected.
4. **Verify** `metadata.version_id == prose.md frontmatter version_id`.
5. **Verify** `extraction.uploader_confirmed == true`.
6. **Check expiry**:
   - Effective expiry = `metadata.valid_through` if non-null, else `metadata.effective_date + metadata.auto_expire_days`.
   - If `today > effective_expiry` → expired.
   - If `today < metadata.effective_date` → not yet effective.
<!-- METHODOLOGY: sec-confidence-threshold — derivation of the 0.6 threshold is tracked internally. Do not tune without reviewing the internal note. -->
7. **Surface low-confidence warnings**: any `extraction.extraction_confidence[field] < 0.6` → list in load preamble.

### Failure handling

| Check failed | Behavior |
|---|---|
| `view.yaml` missing | No active view. Run skill normally with standard disclaimer. |
| Hash mismatch (drift) | DO NOT apply tilts. Emit: "House view prose and structure are out of sync — re-confirm via `/parallax-load-house-view --re-pair`. Running without view." |
| `uploader_confirmed = false` | DO NOT apply tilts. Emit: "House view extraction was never confirmed by uploader. Run `/parallax-load-house-view` to confirm." |
| Expired | DO NOT apply tilts. Emit: "Active house view '[view_name]' expired [N] days ago. Falling back to neutral. Update via `/parallax-load-house-view --extend`." |
| Not yet effective | DO NOT apply tilts. Emit: "House view '[view_name]' becomes effective on [date]. Running without view until then." |
| Low-confidence fields | Apply tilts, but include in load preamble: "House view loaded with low extraction confidence on: [field list]. Verify before acting." |

### Soft-warning thresholds

<!-- METHODOLOGY: sec-tilt-variance-threshold — derivation of the 0.5 threshold is tracked internally. Do not tune without reviewing the internal note. -->
| Condition | Warning |
|---|---|
| `effective_expiry - today` ≤ 14 days | "House view expires in [N] days; consider updating." |
| `tilt_variance < 0.5` across non-zero tilts | "House view has minimal differentiation; tilts will have weak portfolio effect." |

---

## 3. Multiplier mapping

### Quantum-factor pillars (Ω Φ Ξ Ψ)

The four pillars (`econometrics_phase`, `valuation_state`, `market_entropy`, `psychological_wavelength`) are **encoding-only in Phase 0**. Extractors populate them at ingest from CIO prose (see `skills/load-house-view/SKILL.md`); they are stored in `view.yaml` for forward-compatibility but are NOT translated into factor multipliers, universe effects, or consumer-skill output in Phase 0.

Rationale: MCP equity-only scope doesn't yet carry expected-return / volatility inputs needed for a full multi-pillar composite. Asset-class pillar weights are deployment-specific judgment calls that downstream users should calibrate themselves. Guessing at a partial formula risks silently miscalibrating portfolio math.

### Factor aliases (canonical vs synonyms)

| Canonical | Synonym | Collapse rule |
|---|---|---|
| `factors.profitability` | `factors.quality` | If both set, canonical wins; emit warning |
| `factors.low_volatility` | `factors.defensive` | If both set, canonical wins; emit warning |

On load, collapse `quality → profitability` and `defensive → low_volatility`. Downstream multiplier math and composite re-ranking should only reference the canonical names. Views written before 2026-04-22 (with only `quality`/`defensive`) continue to work — the loader maps them at read time.

### Sector / region / theme tilts (universe + weight effect)

<!-- METHODOLOGY: sec-pillar-multipliers — multiplier values (1.25× / 1.50× / 0.75× / 0.50×) and the 2× neutral cap are tracked internally. Do not change numbers without reviewing the internal note. -->
| Tilt | Universe effect | Weight multiplier | Notes |
|---|---|---|---|
| **+2** (Big OW) | Force-include if absent from candidates | 1.50× | Cap final exposure at 2× neutral to prevent runaway |
| **+1** (OW) | Boost ranking | 1.25× | |
| **0** | No effect | 1.00× | |
| **-1** (UW) | De-rank | 0.75× | |
| **-2** (Big UW) | Exclude unless explicitly named by user | 0.50× | |

**Application:** when calling `build_stock_universe`, prepend tilt context to query (e.g., "exclude tech, overweight defensive sectors and small-cap utilities"). After candidates return, re-rank by `score × tilt_multiplier(holding's sector/region/theme)`.

### Factor tilts (re-weight Parallax composite)

<!-- METHODOLOGY: sec-factor-multipliers — factor multiplier values and their wider spread vs. sector/region multipliers are tracked internally. Do not change numbers without reviewing the internal note. -->
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

<!-- METHODOLOGY: sec-macro-regime-deltas — per-regime factor delta magnitudes (±2, ±1) are tracked internally. Direction of each delta is well-supported by style-investing literature; magnitudes are heuristic pending a regime-conditional Sharpe-differential backtest. Do not change magnitudes without reviewing the internal note. -->

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

2. **Conflict banners** — render inline at the section where the conflict arose (e.g., universe selection, allocation), not bundled at the end.

3. **Ground-truth panel** (REQUIRED when any per-holding score is rendered): next to every factor score, show the company name that the scoring tool actually returned (from `get_peer_snapshot.target_company` or `quick_portfolio_scores.holdings_analyzed[].company_name`) and the input ticker. If the returned name does not match the `get_company_info` name-of-record for the input ticker, flag the row **loudly** (e.g., `⚠ MISMATCH: score attributed to <X>, expected <Y>`). Never display scores as authoritative when the name-mismatch is present — the score belongs to a different company.

4. **Divergence assertion on universe composition** (REQUIRED for skills that call `build_stock_universe` with multi-sector or multi-theme tilts): after the call returns, compute the sector distribution of the result. If the caller requested N≥2 sectors/themes in the tilt-prepended query and the returned distribution has `max_sector_share / total > 0.6`, emit a **fail-loud warning** and either (a) refuse to render the portfolio, or (b) re-issue the call as N parallel per-sector queries and merge. Do not silently proceed. This does NOT apply to legitimately concentrated tilts where only 1 sector/theme was requested (e.g., "100% energy" from a pure-energy view).

5. **View-aware disclaimer** (bottom — replaces the standard parallax-conventions §7 disclaimer):
   > *"This analysis reflects active house view '[view_name]' uploaded by [uploader_role] on [upload_date], effective [effective_date]. Tilts and excludes per the loaded view; conflicts with explicit user scope are flagged inline. Outputs should be reviewed against client suitability before any action."*

When NO active view is loaded, skills run as today — standard output, no preamble, standard disclaimer. Rules 3 and 4 (ground-truth panel and divergence assertion) apply whether or not a view is active — they are data-integrity requirements, not view-specific features.

---

## 6. Audit logging

Every consume event appends one JSONL line to `~/.parallax/active-house-view/audit.jsonl`:

```json
{"ts":"<ISO 8601>","view_id":"<uuid>","version_id":"<uuid>","skill":"parallax-portfolio-builder","query_summary":"<first 200 chars of user input>","applied":true,"conflicts_count":0,"output_summary_hash":"<sha256 of output first 1000 chars>"}
```

`applied: false` when validation fails per §2 — still log the attempt with the failure reason in a `failure_reason` field.

Phase 1: same fields, persisted to Supabase `house_view_audit` table.

---

## 7. Single-stock skills (read-only consumers)

Skills like `parallax-should-i-buy` and `parallax-deep-dive` operate per-stock and do NOT apply tilts. They MUST still:

1. Load and validate the active view per §2.
2. After producing their normal output, check whether the stock's sector / region / themes conflict with view tilts.
3. Surface a single closing flag if so:
   > **House view note:** Active view is UW [sector/theme] (set [date]). Recommendation above is for research purposes; evaluate against your active view before acting.
4. Append the audit log entry per §6.

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
