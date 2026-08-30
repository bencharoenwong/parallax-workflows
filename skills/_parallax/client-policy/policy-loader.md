# Parallax Client Policy — Shared Loader & Resolver

JIT-loaded by any `parallax-*` skill that accepts an optional client-policy input (`policy=`). Defines: how a policy is supplied, how it is validated, how S0-S2 adaptation math is delegated to `adaptation.py`, how conflicts are surfaced, and how the resulting sections render.

**Schema reference:** `_parallax/client-policy/schema.yaml` (canonical YAML structure).

Not part of the house view. The house view is firm-level and carries no client policy; this artifact is client-level and carries no tilts. They meet only at consume time, inside `_parallax/client-policy/adaptation.py`.

---

## 1. Input acceptance

The RM supplies the policy inline (YAML or JSON) or as a file path via `policy=` at invocation. There is no default on-disk location, no on-disk resolution, and no platform fetch. Absence means fallback tier `no_policy` and today's unchanged behavior — no policy sections render.

Inline input is written to a private `mktemp` file before invoking the helper, using the `mktemp "${TMPDIR:-/tmp}/..."` form already used by the render-gate step of `parallax-client-review/SKILL.md` (the step headed "Render — deterministic gate", whose draft file is written as `DRAFT="$(mktemp "${TMPDIR:-/tmp}/clientrev.XXXXXX")"`). Never a fixed or predictable path — `/tmp` symlink hazard.

---

## 2. Validation

Shell out to `_parallax/client-policy/adaptation.py`; never validate in prose. Errors are collect-all and row-level (`validate_policy` never raises on a data problem and never stops at the first failure).

**Two-class error model (binding).** Every `PolicyError` carries a `severity` of `blocking` or `dimension`:

- **Blocking** — a structural failure (`mandate` or `sub_allocations.dimensions` not a mapping, wrong `schema_version`), a non-numeric or out-of-range weight, a band with `min > max`, a policy weight lying outside its own band, a dimension weight-sum violation, or an unrecognized or absent `code_list` on a dimension. A blocking error puts the **whole policy** on tier `no_policy`: nothing applies, no dimension partially computes.
- **Dimension** — a missing `basis`, or `basis: total` without a usable `strategic_allocation.equity`. A dimension-scoped error drops **only that dimension** to `multiplier_fallback`; every other covered dimension proceeds normally.

The two classes never overlap and the tier resolution never mixes them: any blocking error anywhere in the document forces `no_policy` regardless of how many dimension-scoped errors also exist; with zero blocking errors, dimension-scoped errors are partitioned per dimension per the fallback ladder in §4.

`severity: dimension` also covers one case with no dimension attached: a malformed `adaptation` block (`adaptation` not a mapping, `k` out of range, or an unknown `k_preset`) is reported with `dimension: null`. No dimension drops to `multiplier_fallback` for this case — `resolve_k` falls back preset-then-default instead, and the error row still renders in Policy Data Quality.

On a schema-invalid policy (i.e. at least one blocking error), do **not** partially apply: run the review without the policy and surface the full error list in Policy Data Quality. This mirrors the fail-loud posture of `_parallax/house-view/loader.md` §2. A stale policy (`today > review_due`) is a Data Quality row, never a block.

Failure-handling table, in the shape of `loader.md:51-59`. The two `validate_policy` rows are split explicitly by severity class per the two-class model above — they are not alternative descriptions of the same event:

| Condition | Behavior |
|---|---|
| No `policy=` supplied | Tier `no_policy`. Run exactly as today. No policy sections render. |
| Policy file unreadable or unparseable (CLI exit 2) | Tier `no_policy`. Render one Policy Data Quality line naming the failure. Never guess at the content. |
| Policy parsed but is not a mapping | Tier `no_policy`, `policy_hash` empty (this is itself a **blocking** error — "policy document is not a mapping"). Render the error row. |
| `validate_policy` returned a **blocking** error (see class definition above) | Tier `no_policy`. Render every error row. Do not partially apply any dimension. |
| A dimension declares an unrecognized or absent `code_list` | **Blocking.** Tier `no_policy`. Render the error row. The segment-key check is never silently disabled by a typo'd or missing code list — the whole policy falls back rather than guessing the key set. |
| `validate_policy` returned only **dimension-scoped** errors (missing `basis`; `basis: total` without a usable equity weight) | Only the affected dimension(s) fall to `multiplier_fallback`. Every other covered dimension proceeds normally. Emit the error row per affected dimension. Never assume `sleeve`. |
| `review_due` passed | Apply normally. Emit a `stale_policy` row. Never a block. |
| Helper invocation itself fails (non-validation runtime failure) | Render the policy sections as unavailable with the reason. Do not compute any figure inline. |

---

## 3. Normalization (S0)

The house view loads per `_parallax/house-view/loader.md`, unchanged.

Holdings map to region by RIC suffix per `_parallax/parallax-conventions.md` §1. Holdings map to sector from `analyze_portfolio`'s `sector_allocation` block (client-review already calls `analyze_portfolio` in its Batch A parallel block), with `get_peer_snapshot` / `get_company_info` as a per-holding backstop. An unmapped holding produces an `unmapped_holding` Data Quality row and is excluded from that dimension's denominator; the exclusion is disclosed. All weights convert to sleeve basis; every conversion is disclosed as a `basis_converted` row.

**Classification basis (binding disclosure).** Region is classified by listing venue (the RIC suffix), not by issuer domicile or economic exposure; ADR and fund look-through is not applied in phase 1. The rendered output states this basis (§7.4).

**`--exposures` payload schema (pinned; stated identically in `adaptation.py`'s module docstring, here, and in `parallax-client-review/SKILL.md` Batch C — this is one of the three places that must agree):**

```json
{
  "basis": "sleeve",
  "dimensions": {
    "region": {"us": 0.62, "europe": 0.20, "japan": 0.08, "em_ex_china": 0.10},
    "sector": {"information_technology": 0.34, "financials": 0.18,
               "health_care": 0.30, "energy": 0.18}
  },
  "coverage": {"region": 0.97, "sector": 1.00},
  "unmapped": [{"symbol": "ABC.L", "weight": 0.03, "dimension": "region"}],
  "holdings": [{"symbol": "AAPL.O", "isin": "US0378331005", "weight": 0.25,
                "region": "us", "sector": "information_technology"}]
}
```

- `basis` must be `"sleeve"` — Phase 1 accepts sleeve-relative exposures only; the producer converts before calling. A missing or non-`"sleeve"` `basis` is rejected at the CLI (exit 2, naming the file and the offending value), the same operator-mistake class as a non-object payload; no conversion is implemented in Phase 1.
- The whole payload is checked by `validate_exposures` against this contract (known dimensions, finite weights in [0, 1], per-dimension sums, coverage consistent with the `unmapped` weight it implies). At the CLI a violation is an operator mistake: exit 2, naming the file and every violation. Called as a library the helper proceeds WITHOUT exposures and discloses one `invalid_exposures` Data Quality row per violation; it never certifies an impossible payload with a band verdict.
- Per dimension, weights are renormalized over MAPPED holdings and sum to 1.0 within 1e-6. Every dimension in the example above sums to 1.0.
- `coverage[dim]` is the mapped weight fraction BEFORE renormalization. A coverage below 1.0 emits `unmapped_holding` rows and is disclosed in the rendered table. `coverage` passes through onto the result unchanged so the consumer can caveat a conditional diagnostic.
- `unmapped` lists every holding excluded from a dimension's denominator.
- `holdings` is required only for the exclude and prohibited-product conflict checks. Absent `holdings` suppresses those two conflict kinds and emits nothing; the check is a disclosure, not a gate.
- `isin` on a holding is OPTIONAL. When present it is matched against `mandate.prohibited_products` alongside `symbol` (case-insensitive). An ISIN-shaped prohibition with any holding lacking an `isin` emits a `hard_constraint_not_checkable` row: the check ran on partial identifiers.

**`--view-tilts` payload schema (pinned).** Produced from the loaded house view after the `loader.md` §3 alias collapse. Factors, styles, and themes are deliberately absent — they are tactical-only and never enter band math:

```json
{"regions": {"us": 1, "japan": -1}, "sectors": {"information_technology": -2},
 "excludes": ["tobacco", "GAZP.MM", "russia"]}
```

---

## 4. Fallback ladder

Binding behavior contract, applied per dimension:

| Condition | `fallback_tier` | Per-row `semantics` |
|---|---|---|
| No policy supplied, or `validate_policy` returned a **blocking** error set (§2) | `no_policy` | (no rows; consumer runs today's behavior) |
| ≥1 covered dimension, no covered segment has any band | `weights_only` | `multiplier_fallback` on every row |
| Both `region` and `sector` covered, and every covered segment has a two-sided band | `full` | `policy` on every row |
| Anything else (one dimension covered, sparse bands, one-sided bands, or a dimension forced to fallback by a **dimension-scoped** error) | `partial_dimensions` | `policy` per banded segment, `multiplier_fallback` per unbanded or error-forced segment |

"Covered" means the dimension exists under `sub_allocations.dimensions` with a non-empty `strategic_allocation`. An uncovered dimension is absent from `drift` and `taa` and appears as an `uncovered_dimension` Data Quality row.

**Ladder row 2 semantics** (`multiplier_fallback`, no room exists): `current_active = current - policy` is still reported. `desired_active` is `None`. Alignment is by `sign(current_active)` against `sign(tilt)`, using the same order as the room-based classifier with the room branches skipped. The budget line becomes a diagnostic comparing `Σ|current − policy|` against `max_total_tilt` when one is given; no cap is applied because there is nothing to scale.

---

## 5. S1 + S2 math

One Bash step, delegated entirely to `_parallax/client-policy/adaptation.py`. Never inline arithmetic. Cite the operator-agnostic-helper rationale by reference to `_parallax/house-view/loader.md` §2 ("Why the helper, not inline math") — the same argument applies here: allocation arithmetic and threshold comparisons must be identical across operator LLMs (Claude / GPT / Gemini).

```
python3 "<skill-dir>/../_parallax/client-policy/adaptation.py" \
  --policy "$POLICY" --exposures "$EXPOSURES" --view-tilts "$TILTS" --json
```

When only a policy is available (no exposures assembled yet), omit `--exposures`/`--view-tilts`; the tier still resolves from policy structure alone (`drift` and `taa` are empty). Capture the full JSON result. Every rendered number comes from it — do not recompute, round, or re-derive any figure inline.

---

## 6. Conflict rules

Precedence: excludes and prohibited products outrank bands and user constraints, which outrank tilts. Conflicts are surfaced for human decision, never auto-resolved — the helper never drops, nets out, or silently reweights a colliding row.

- `tilt_vs_band` — a nonzero tilt with no room in the tilt direction, or a band already breached in the tilt direction.
- `exclude_vs_holding` — a holding whose symbol, region, or sector matches a view-tilts excludes entry.
- `prohibited_vs_holding` — a holding whose `symbol` **or** optional `isin` matches `mandate.prohibited_products`. Both sides normalize to upper case before comparison; `detail.matched_on` names which identifier matched.

**What the helper cannot match (binding).** Two hard-constraint classes have no field to match against, so they are disclosed rather than silently missed, as `hard_constraint_not_checkable` Data Quality rows (§7.4):

- a view exclude entry that is neither a known region key, nor a known sector key, nor a held symbol — a theme or category entry. Theme-class excludes are enforced by the house-view flow at skill level, not by this helper.
- an ISIN-shaped `prohibited_products` entry while one or more holdings carry no `isin`; the prohibition check then ran on incomplete ISIN coverage.

**An empty Conflicts table means "checked clean" ONLY when no `hard_constraint_not_checkable` row is present.** With such a row present, the empty table means "no collision among the constraints this helper can match."

An RM band override is permitted but must be written into `governance.human_review_recorded` (`{ts, by, segment, override, rationale}`) and surfaced in the rendered output (Policy Conflicts, §7). A silent override is a contract violation.

Factors, styles, and themes never enter band math — they are tactical-only per the house view and are deliberately absent from the `--view-tilts` payload (§3).

---

## 7. Output rendering

Renders as four additive section families in the consumer skill's Output Format, plus a resolved-k / calibration disclosure line. Field sources are the `AdaptationResult` returned by `adaptation.py`; nothing here is computed by the consumer.

**Placement rule (binding).** `render_gate.py` keeps from the earliest line matching any anchor and drops everything above it (`render_gate.py:139-154`). For `client-review` the anchors are the common House View Preamble and Ground-truth patterns plus `SKILL_ANCHORS["client-review"]` (`render_gate.py:81-84`): a heading or bold line containing "client portfolio review", "portfolio review", or "portfolio summary", and the Branding Header `**<client>** portfolio review`. Therefore: policy status renders **after** the first anchored block in every state combination — after the House View Preamble when a view is active, after the Branding Header when white-label only, otherwise inside or below the report's first anchored heading. Never above the first anchor. Do not add a new anchor regex to `SKILL_ANCHORS`, and do not rely on the degraded-note hoist as a safety net (it hoists only lines matching `_DEGRADED`, which policy content does not).

### §7.1 SAA Drift (only if policy supplied)

One row per covered segment: dimension, segment, current, policy, drift, band, band status, breach kind. Source: `drift[]`. When `coverage[dim] < 1.0`, the drift table for that dimension carries a caveat line — "diagnostics conditional on N% mapped coverage" — because `current` is renormalized over mapped holdings and is not the known full-sleeve exposure. Source for N: `coverage[]`. Disclose the near-edge threshold (`near_edge_fraction`, default 20% of the room on that side) under the table. Render **Verdict sensitivity** per `_parallax/parallax-conventions.md` §11 — band status is a published-numeric-cutoff verdict, so name the nearest-boundary segment (`distance_to_edge`) and the arithmetic flip condition, third person, no advice language.

### §7.2 TAA Alignment (only if policy supplied)

One row per covered segment: tilt, room in the tilt direction, desired active, current active, alignment (`aligned` / `opposed` / `capped_by_band` / `not_evaluable` / `no_view`). Source: `taa[]`. Below the table: the budget line (`budget.sum_abs_desired` vs `budget.max_total_tilt`, and `budget.scale` if `budget.cap_applied`). The budget sums |desired active| gross across region and sector independently, and one overlapping holding may satisfy both a region and a sector active at once — a phase-1 heuristic characteristic, resolved by the phase-2 holdings-level optimizer; state this with the budget line. Tag every `multiplier_fallback`-semantics row whose alignment is `aligned` / `opposed` / `no_view` (a genuine sign read) visibly as **sign-only alignment — not sized (no band benchmark)**. A `multiplier_fallback`-semantics row whose alignment is `not_evaluable` instead means the dimension was forced to fallback by an unresolved basis (§2): even the sign is not trustworthy there, so tag it **not evaluable — basis unconfirmed, see Policy Data Quality** and point the reader to the paired `basis_unconfirmed_drift` row (§7.4) rather than the sign-only caption. Under `weights_only` (§4 ladder row 2), `budget.sum_abs_desired` is `Σ|current − policy|` — a drift diagnostic, not a sizing total — because there is nothing to scale; see §4's Ladder row 2 semantics note.

**`tactical_overlay.enabled: false` (binding, no exceptions).** S1 drift is unaffected — it still renders per §7.1. S2 emits no rows at all. TAA Alignment renders exactly one line: "tactical overlay disabled by mandate." No budget line is rendered in this state.

### §7.3 Policy Conflicts (only if policy supplied)

`tilt_vs_band` rows and `exclude_vs_holding` / `prohibited_vs_holding` rows. Source: `conflicts[]`. Framed per `_parallax/parallax-conventions.md` §12: an informational preface above the table, no imperative trade verbs. Any recorded RM band override (`governance.human_review_recorded`, §6) renders here with its rationale.

An empty table means "checked clean" ONLY when no `hard_constraint_not_checkable` row is present in §7.4 (§6). When one is present, say so here in one line: the table covers the constraints this helper can match, and the named theme-class or partially-identified constraints are not among them. Theme-class excludes are enforced by the house-view flow at skill level, not by this helper.

### §7.4 Policy Data Quality (only if policy supplied)

Source: `data_quality[]`, plus **every** `errors[]` row the run produced, whatever its severity or scope: blocking errors that forced tier `no_policy`, dimension-scoped errors that forced a dimension to `multiplier_fallback`, and the `dimension: null` k-configuration class of §2 (`adaptation` not a mapping, `k` out of range, unknown `k_preset`) — that class forces no dimension to fallback and would otherwise render nowhere. Kinds rendered here: `uncovered_dimension`, `unmapped_holding` (with the coverage fraction), `basis_converted`, `basis_unconfirmed_drift`, `stale_policy`, `te_budget_not_evaluated`, `missing_bands`, `unknown_segment_key`, `ambiguous_broad_tilt`, `invalid_exposures`, `hard_constraint_not_checkable`, and `off_policy_exposure`.

**Section intro (binding).** The standing intro to this section states the classification basis: region is classified by listing venue (RIC suffix), and ADR/fund look-through is not applied in phase 1 (§3). This is a standing disclosure, not a row kind — it renders whenever the section renders, with or without any row.

**`ambiguous_broad_tilt` (rendering guidance).** A region segment key can belong to more than one broad tilt bucket (e.g. `india` is a member of both `apac_ex_japan` and `em_ex_china`). When the key carries no specific tilt of its own: if every containing tilted bucket agrees on the same tilt value, the segment inherits that shared tilt silently — no disclosure row, because there is nothing ambiguous to report. If the containing buckets disagree, the segment's tilt resolves to `0` (never picked by map order or first-match) and an `ambiguous_broad_tilt` Data Quality row is rendered naming the segment, the conflicting bucket/tilt pairs, and pointing the reader to add a specific tilt on that segment to settle it. Render this row in Policy Data Quality, not as a `conflicts[]` row — it is a resolution disclosure on the tilt input, not a precedence collision between policy artifacts.

### §7.5 Resolved-k and calibration disclosure

Under the section group, render one disclosure line stating the resolved `k` with its source and `calibration_status`. Reuse the wording pattern of `_parallax/house-view/loader.md` §5.1a. Suggested text:

> *Policy adaptation figures are heuristic and uncalibrated (`calibration_status: heuristic_phase0`); resolved sizing factor k = 0.50 (source: preset "balanced"). Band status uses a near-edge threshold of 20% of the room on that side. Directional research only.*

---

## 8. Audit logging

Reference `_parallax/house-view/loader.md` §6 and its §6.2 conditional fields `client_ref`, `client_policy_applied`, `policy_hash`, `policy_fallback_tier`, `resolved_k` / `k_source`. Never log client names: `client_ref` (the pseudonymous `metadata.client_ref` from the policy) and `policy_hash` only, per `loader.md` §6.3's no-PII rule.

**Tier translation (binding).** The helper's `no_policy` tier is not an audit value: a supplied-but-unusable policy records `policy_fallback_tier: invalid` in the audit row, and a valid policy whose helper invocation failed at runtime (§2's last failure row) records `unavailable`.

---

**Public-repo wording.** No platform names, no vendor names, no external-standard names, no issue references. Say "wealth-platform mandate-document conventions" where a name would otherwise go.
