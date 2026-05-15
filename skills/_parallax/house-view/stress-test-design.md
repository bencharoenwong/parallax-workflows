# House View Stress Test — Feature Design

Method: autoplan-style review structure, adapted to a CIO setting. Pulled from
`https://github.com/garrytan/gstack/blob/main/autoplan/SKILL.md` and trimmed of
tooling that doesn't apply here (codex CLI, brain-sync, telemetry, plan files).

The natural "dual voice" in this feature is **CIO view ↔ Parallax macro** — two
independent perspectives already present in the data, with no external model
dispatch needed for the design.

---

## The 6 Stress-Test Principles (adapted from autoplan's 6 decision principles)

These auto-answer mechanical cells. Taste and CIO Challenges escalate to the Final Gate.

1. **Recency wins on data, not on conviction.** If Parallax data post-dates the CIO view by >30d on a divergent cell, default to "revisit." Conviction (basis_statement) overrides only with explicit override.
2. **Coverage gaps are not agreement.** `PARALLAX_SILENT` / `UNCOVERED` ≠ confirmation. Mark as "unverifiable," never as aligned.
3. **Internal consistency before external comparison.** Never run the MCP phase if the view contradicts itself. Fix-then-test.
4. **Explicit divergence over implicit drift.** Surface every divergent cell at the gate. Never silently downgrade a CIO tilt because Parallax disagreed.
5. **Bias toward an updated view, not a frozen one.** When the CIO confirms stress-test recommendations, default option is "save as new version with `manual_edit` provenance citing the stress test entry."
6. **Auditability over autonomy.** Every stress-test run writes one entry to `audit.jsonl` (`action="stress_test"`). The view doesn't change unless the CIO confirms; the audit shows we asked.

Tiebreakers:
- **Internal consistency phase:** P3 + P5 (explicit) dominate. Hard-stop on contradiction.
- **External comparison phase:** P1 (recency) + P2 (coverage ≠ agreement) dominate.
- **Synthesis phase:** P4 (explicit) + P5 (bias toward update) dominate.

---

## Decision Classification (from autoplan)

| Class | Meaning | Resolution |
|---|---|---|
| **Mechanical** | one clearly right answer | auto-decide silently, log in audit |
| **Taste** | reasonable disagreement (e.g., both view & data are fresh and conflict) | auto-recommend, surface at gate |
| **CIO Challenge** | data has moved past the CIO (stale-divergent, >30d delta) | NEVER auto-decided; surface with the autoplan User Challenge frame: what you said / what data says now / why / what you might know that data doesn't / cost-if-wrong |
| **Hard stop** | internal contradiction in the view | refuse to proceed to external phase; require fix |

---

## Per-Codepath Production Failure (one realistic scenario per new codepath)

Per `plan-eng-review` Section 1 rule: every new codepath needs a named realistic
production failure. Plan-level failure modes (M1–M8) below cover cross-cutting
errors; this section covers *codepath-specific* failure semantics that drive
implementation choices.

| Codepath | Realistic prod failure | Why it matters | Mitigation owned by this design |
|---|---|---|---|
| Phase 0 intake (load active view) | View missing because user is on a fresh install / `--clear`'d earlier this session | Stress test launched from a portfolio skill auto-trigger sees no view | Exit cleanly with "no active view; nothing to stress test"; suggest `/parallax-load-house-view`; do NOT write audit |
| Phase 1 rule evaluation | Rule config is stale — e.g., empirical evidence post-2026 changes the rate-cutting + momentum pairing, but the rule still hard-stops | False hard-stop locks every CIO out of stress-testing until a rule update ships | Rules carry `last_reviewed: <date>` and `confidence` in config. Warn (not hard-stop) when `last_reviewed > 6mo`. Hard-stop downgrades to Taste in that case. |
| Phase 2 per-market fan-out | One market's `macro_analyst` times out at 30s while others return | Naive `await all` blocks the whole run on the slowest market | Per-market degrade: a timed-out market resolves as `PARALLAX_SILENT`, not as a run failure. Captured in the artifact, not as an exception. |
| Phase 2 fan-out under heavy tilt count | CIO has tilts on 20+ markets → 40-60 concurrent MCP calls | MCP rate-limit / cost spike; some calls 429 and degrade silently as `PARALLAX_SILENT` | Hard cap at 12 markets per run. If > 12 tilted markets, prompt user once: stress all (chunk into 2 batches), stress top-12 by `|tilt|`, or cancel. No silent truncation. |
| Phase 3 audit append | `view_hash` re-read at Phase 3 differs from Phase 0 (concurrent save in another terminal) | Audit would attach to a view version that wasn't the one stress-tested | Already in M3/M7: abort with "view changed mid-run, retry." Phase 3 work discarded; no partial audit. |
| Phase 4 handoff to `load-house-view --edit` | User picks B (update view), `load-house-view` then rejects the draft at its own confirmation gate (uploader edits and cancels) | Stress-test audit shows `applied=false` but user thought they were saving | Surface this explicitly: stress-test audit entry stays `applied=false` regardless; `load-house-view` writes its own `save` (or absence-of-save). UX text on Phase 4 makes the two-gate sequence visible: "your stress test is logged; the view update is a separate confirmation." |
| Phase 4 handoff produces a draft that fails schema validation | Proposed delta produces a YAML that `load-house-view` rejects as malformed | Stress-test "recommendation" can't actually be applied | Validate proposed delta against `_parallax/house-view/schema.yaml` *before* handoff. If invalid, downgrade Phase 4 to A-only and log the diagnostic. |

---

## Phase 0 — Intake + Restore Point

(Restore point already exists. The `--clear`/edit flows archive to
`.archive/<view_id>-<version_id>/`. Stress test does not modify the view itself —
only writes an audit entry and a `stress-tests/<date>.md` artifact — so no separate
restore point is needed. If the CIO chooses "update view" at the Final Gate, that
goes through the standard save path, which already archives.)

Read context (no MCP yet):

- `~/.parallax/active-house-view/view.yaml` — required; abort with clear message if absent
- `~/.parallax/active-house-view/audit.jsonl` — verify hash-chain integrity; refuse to run if broken
- Compute `cio_age = today − metadata.effective_date`
- Compute `view_hash` of the live view and pin it; re-check at the Final Gate (race-condition guard)
- Enumerate dimensions to test:
  - All non-zero `tilts.macro_regime.*`
  - All non-zero `tilts.factors.*`
  - All non-zero `tilts.sectors.*`
  - All non-zero `tilts.regions.*` (these drive Phase 2 market selection)
  - All non-zero `tilts.pillars.*`
  - `excludes`

Output: "Loaded view <name>, age <N>d, <M> non-zero dimensions, <K> markets to query."

---

## Phase 1 — Internal Consistency (no MCP)

Pure-Python checks against the live YAML. Cheap, deterministic, runs before any
network call. Fails hard on contradiction (Principle 3).

Cell categories and the auto-decision rule for each:

| Check | Trigger | Class | Auto-action |
|---|---|---|---|
| `macro_regime.rates == "cutting"` & `factors.momentum ≥ +1` | regime-favored low-vol historically | Hard stop | refuse; emit fix suggestion |
| `macro_regime.growth == "slowing"` & cyclical sectors (`financials`, `industrials`, `materials`) overweight | growth-slowing favors defensives | Taste | surface; do not block |
| `excludes: [energy]` & EM commodity-exporter regions (`brazil`, `indonesia`, `mexico`, etc.) overweight | implicit re-introduction of energy beta | Taste | surface |
| `pillars.Ω (econometrics_phase) ≤ −1` & `macro_regime.risk_appetite == "risk_on"` | regime-RORO contradiction | Hard stop | refuse |
| Any cell flagged at extraction with `extraction_confidence < 0.6` and now driving a non-zero tilt | fragile extraction collapsed to directional bet | Taste | surface as "fragile" |

(All trigger thresholds and pairings live in a config so the rule set is auditable
and editable without code change. Avoid encoding any new PRISM multiplier
relationships — these are *value*-level folk-quant checks, not pillar→factor mapping
extensions.)

Output of Phase 1: "PASS" (proceed to Phase 2) or "HARD STOP" (render table, exit
with audit entry `action="stress_test", disposition="halted_internal"`).

---

## Phase 2 — External Comparison vs Parallax (per market)

**Tool loading.** Call `ToolSearch` with query `"+Parallax"` once before the first MCP call.

**Parallel by market.** For each market with a non-zero `regions` tilt, fire in
parallel (CIO-confirmed: tilted-markets-only; no always-check majors). If the CIO
view has zero `regions` tilts but non-zero `macro_regime` tilts, fall back to one
call against the view's primary market (inferred from `basis_statement` heuristic, or
default to US if ambiguous) so the macro_regime dimensions still get a comparison
anchor. Document this fallback explicitly in the run artifact.

**Fan-out cap.** The schema's `regions` block has 27 keys. Worst-case naive fan-out
is `27 markets × 3 tools (telemetry + macro_analyst + score_analysis-bellwether) ≈
80 concurrent MCP calls`, which exceeds reasonable per-run MCP budget and may trip
rate limits. Cap: **12 tilted markets per run** (covers the typical CIO view; an
"EM-overweight, granular" view rarely exceeds this). If `tilted_markets > 12`,
prompt the user once with three options: (a) stress all, chunk into ceil(N/12)
sequential batches; (b) stress top-12 by `|tilt|`, surface remainder as "deferred,
re-run for full coverage"; (c) cancel. Never silently truncate. `check_macro_health`
is one global call regardless of market count.

| Tool | Purpose |
|---|---|
| `check_macro_health` (once, not per market) | freshness of macro data across markets |
| `get_telemetry` | per-market regime tag + signals + commentary |
| `macro_analyst` (summary) | per-market 9-component macro view |

Bail on tool failure with explicit `PARALLAX_SILENT` / `UNCOVERED` marking
(Principle 2). Never let a fail-empty silently look like agreement.

For each (market × dimension) cell, resolve to one of six states:

| State | CIO has view? | Parallax has view? | Aligned? | Class |
|---|---|---|---|---|
| **ALIGNED** | yes | yes | yes | Mechanical |
| **DIVERGENT — stale CIO** (cio_age − parallax_age > 30d) | yes (old) | yes (fresh) | no | **CIO Challenge** |
| **DIVERGENT — fresh CIO** (delta ≤ 30d) | yes | yes | no | Taste |
| **CIO_SILENT** (no tilt, Parallax has high-conviction signal) | no | yes | n/a | Taste (suggest taking a view) |
| **PARALLAX_SILENT** | yes | no | n/a | Mechanical (note as unverifiable) |
| **UNCOVERED** (market not in `list_macro_countries`) | yes | n/a | n/a | Mechanical (note as no-second-opinion-possible) |

Stale-divergent cutoff: **flat 30d across all dimensions** (CIO-confirmed). Simpler
to reason about than per-dimension tiers; revisit if macro_regime cells produce
chronic false-Taste (escalations that should have been Challenges) or excludes
cells produce chronic false-Challenge (escalations that the CIO routinely overrides).
The single threshold is config-driven, not hard-coded.

---

## Phase 3 — Synthesis + Audit

Roll up Phase 1 (internal) and Phase 2 (external) into:

**(a) Cross-dimension themes.** Anything flagged in 2+ dimensions independently
becomes a high-confidence signal. Example: macro_regime says rates=cutting +
sector tilt overweights financials (Phase 1 taste) + Parallax for US says rates
"holding-with-cut-risk" (Phase 2 stale divergent) → cross-phase theme: "rate trajectory
disagreement compounds into financial-sector exposure."

**(b) Audit entry.**

```jsonc
{
  "schema_version": 1,
  "ts": "...",
  "view_id": "...",
  "version_id": "...",
  "view_hash": "...",       // re-read at this point; abort if changed since Phase 0
  "skill": "parallax-stress-house-view",
  "action": "stress_test",
  "applied": false,         // applied=true only if user approves an update at gate
  "disposition": "completed", // or "halted_internal" on Phase 1 hard stop
  "stress_summary": {
    "internal_pass": true,
    "external_markets_queried": ["US","EU","JP","BR"],
    "states": {"aligned": 8, "divergent_stale": 2, "divergent_fresh": 1, "cio_silent": 3, "parallax_silent": 0, "uncovered": 1},
    "cio_challenges": 2,
    "taste_decisions": 4
  },
  "recommended_deltas": [   // structured handoff payload; one entry per divergent-stale cell
    {
      "kind": "informational",
      "path": "tilts.sectors.utilities",
      "market": "japan",
      "cio_value": 1,
      "parallax_signal": -1,
      "parallax_summary": "Parallax: Japan utilities rank 4, dropped 2 ranks",
      "stress_state": "DIVERGENT_STALE",
      "cio_age_days": 56,
      "parallax_age_days": 1
    }
  ]
}
```

`recommended_deltas` is the structural primitive enabling future
`/parallax-load-house-view --apply-stress <audit-hash>` automation (Option B
below). v1 ships only `kind: "informational"` entries — manual application
by the CIO via `--edit` with `basis_statement` citing this audit's hash.

Append via the existing `audit_chain.append_entry()` so the hash chain stays intact.
This is the same machinery `load-house-view` uses for `save` entries.

**(c) Run artifact** to
`~/.parallax/active-house-view/stress-tests/<YYYY-MM-DD>-<view_hash[:8]>.md`. Same
permissions as the active-house-view dir (0700/0600).

---

## Phase 4-B Handoff — Design Decision (manual, v1)

**Confirmed approach: Option A (manual handoff) + structured `recommended_deltas` in audit (Option B preparation).**

Decision rationale:
- `load-house-view --edit` does NOT accept a pre-populated input file in its current spec — it opens `$EDITOR` on the live `view.yaml`. The earlier design language implying a "pre-populate" call was fictional.
- v1 manual handoff: the CIO reads the report's Phase 4-B section (markdown table) and the structured `recommended_deltas` in the audit entry, edits `view.yaml` via `--edit`, and cites the stress entry by its audit hash in `basis_statement`.
- Audit chain shows `stress_test → save` on the same view family. The link is via the cited audit hash in the new save's `basis_statement`, not via a structured cross-reference (kept soft to avoid coupling).
- v2 (deferred): add `/parallax-load-house-view --apply-stress <audit-hash>` operational mode that reads `recommended_deltas` from the audit entry, applies them to a draft, opens the existing confirmation gate, and writes `manual_edit` provenance with a hard `source_audit_hash` field. This requires:
  - New mode in `load-house-view/SKILL.md`
  - Extending the `manual_edit` provenance class in `schema.yaml §Classification taxonomy` with optional `source_audit_hash`
  - One unit test on each side verifying the round-trip

Until v2 ships, the `recommended_deltas` field is consumer-side dead weight — but it is forward-compatible: the audit chain already carries the data, so v2 is a pure consumer-side addition with no migration.

---

## Phase 4 — Final CIO Gate

One `AskUserQuestion`. Frame from autoplan, adapted:

```
## Stress Test Complete

### View Summary
<view_name> | Effective <date> | Age <N>d | Calibration: <heuristic_phase0 | empirical_phase1>

### Decisions Made: <T> total (<M> auto-decided, <K> taste, <J> CIO challenges)

### CIO Challenges (data has moved past your view)
[For each:]
**Challenge <n>: <market> · <dimension>**  (cio_age <a>d / parallax_age <b>d / delta +<d>d)
You said:        <tilt value> · <basis excerpt>
Parallax says now: <regime / signal>
Why it diverges: <one-line mechanism from macro_analyst.commentary>
What you might know that data doesn't: <one line — invite override>
If we change and you were right: <cost — e.g., "you'd be selling at the bottom of a regime that's about to mean-revert">

Your call — your original tilt stands unless you explicitly change it.

### Taste Decisions
[For each:]
**<market> · <dimension>** — recommend <X> (P<principle>). But <Y> also viable: <one-line downstream impact>.

### Auto-Decided
<M> cells (see stress-tests/<date>.md and audit.jsonl entry <hash>).

### Cross-Dimension Themes
[Only if any cell flagged in 2+ dimensions. Else: "No cross-dimension themes."]
```

Options (mirrors autoplan, adapted to a view update):

- **A) Acknowledge — no view change.** Write `applied=false` audit. View stays.
- **B) Update view incorporating all recommendations.** Hand off to `load-house-view --edit` pre-populated with proposed deltas, `manual_edit` provenance citing this stress-test audit entry hash. Re-confirm at the standard load-house-view gate.
- **C) Update with overrides.** Ask which CIO Challenges to accept; partial update via same handoff.
- **D) Interrogate one cell.** Drill into provenance + the macro_analyst commentary excerpt; re-present.
- **E) Defer.** Schedule a re-run in <N> days (write a reminder to `stress-tests/scheduled.jsonl`; no daemon yet).

---

## What Already Exists (don't reinvent)

| Need | Existing primitive | Use as-is? |
|---|---|---|
| Active view loading | `~/.parallax/active-house-view/view.yaml` + loader.md | yes |
| Audit append + hash chain | `audit_chain.append_entry()` | yes (new `action` value) |
| Restore / version archive | `.archive/<view_id>-<version_id>/` | yes (no extra work needed; stress test doesn't mutate) |
| Macro data | `get_telemetry`, `macro_analyst`, `check_macro_health` | yes |
| Country coverage | `list_macro_countries` | yes (drives UNCOVERED classification) |
| Provenance taxonomy | `manual_edit` class in schema.yaml §"Classification taxonomy" | yes (for the Phase 4-B handoff) |
| Status banner | `view_status.py` | extend later to surface "stale vs Parallax data" — not in this scope |
| View ↔ portfolio diff | `house-view-diff` SKILL | unrelated; that diffs portfolio output, this diffs view ↔ data |

---

## Failure Modes Registry

| ID | Mode | Mitigation |
|---|---|---|
| M1 | `check_macro_health` returns no `last_updated` | mark cell `UNVERIFIABLE_DATA` (separate from `UNCOVERED`); proceed |
| M2 | Parallax MCP not connected | fail loud, no audit write, exit |
| M3 | `view_hash` at Phase 3 ≠ `view_hash` captured at Phase 0 | abort with "view changed mid-run, retry"; partial work discarded |
| M4 | Every tilted market is `UNCOVERED` | render full UNCOVERED report; audit entry with `applied=false`; suggest expanding region tilts to broader keys covered by Parallax |
| M5 | Hash chain broken when reading `audit.jsonl` | refuse to run; user must restore from `.archive/` or `--re-pair` (existing flow) |
| M6 | User picks B/C at gate but `load-house-view` confirmation fails | stress-test audit entry already written with `applied=false`; load-house-view writes its own `save` entry; no state corruption |
| M7 | Two stress-test runs concurrently (parallel terminals) | second run sees `view_hash` unchanged at Phase 0 + 3 (no view mutation); both audits append safely via hash-chain serialisation; CIO sees two artifacts |
| M8 | Parallax `last_updated` is present but stale (e.g., `parallax_age_days >> 30`) | `compute_age_delta` returns `"fresh"` when CIO is younger than Parallax-age + 30d, so a 90-day-old Parallax signal vs. fresh CIO renders as `DIVERGENT_FRESH` (Taste) — not flagged as a data-quality issue. v1 limitation; CIO must inspect `last_updated` directly via `check_macro_health` before treating divergences as substantive (the artifact's header does not yet surface Parallax age — v2 dependency). v2 will add a `PARALLAX_DATA_STALE` sentinel above an absolute age threshold and surface `parallax_age_days` in the artifact header. Surfaced by adversarial-reviewer post-implementation. |

---

## NOT in Scope (deferred to a follow-up)

- Continuous monitoring / cron daemon
- Stale-vs-data warning in `view_status.banner` (extend `view_status.py` separately)
- Cross-asset stress test (FI / FX / credit / commodities) — schema already drops these at extraction; no new pipe
- Auto-update view without explicit CIO confirmation
- Stress against non-Parallax data (Bloomberg / FactSet / internal)
- ETF-universe-level stress (Parallax `etf_*` tools) — different problem
- Multi-CIO ensembles (compare two house views to each other) — different problem

---

## Test Coverage (formal diagram, plan-eng-review §3 format)

Legend: `★★★` = behavior + edge + error  ·  `★★` = happy path  ·  `★` = smoke  ·  `[GAP]` = no coverage yet  ·  `[→AUDIT]` = needs adversarial-reviewer pass

```
CODE PATHS                                              CIO FLOWS (stress test run)
[+] stress-house-view/intake.py                         [+] /parallax-stress-house-view (no args)
  ├── load_active_view()                                  ├── [GAP] ★★★  active view present, all systems go
  │   ├── [GAP] ★★  view present, hash chain ok             ├── [GAP] ★★   no view → exit clean with suggestion
  │   ├── [GAP] ★   view absent → clean exit                └── [GAP] ★★   view present, audit chain broken → refuse
  │   └── [GAP] ★★★ audit chain broken at head → refuse
  └── enumerate_dimensions()                            [+] /parallax-stress-house-view --markets us,jp
      ├── [GAP] ★★  non-zero tilts pulled                 ├── [GAP] ★★   explicit subset override (skips cap prompt)
      └── [GAP] ★   schema_v0 legacy view handling        └── [GAP] ★    invalid market name → error before fan-out

[+] stress-house-view/internal_consistency.py           [+] Fan-out cap prompt (>12 tilted markets)
  ├── rule_rates_cutting_momentum_pos()                   ├── [GAP] ★★★  prompt fires, user picks (a) chunked
  │   ├── [GAP] ★★★ triggers + downgrades on stale config ├── [GAP] ★★   user picks (b) top-12 by |tilt|
  │   └── [GAP] ★   passes when no contradiction          └── [GAP] ★    user picks (c) cancel
  ├── rule_growth_slowing_cyclicals()                   [+] Phase 4 gate
  │   ├── [GAP] ★★  triggers as Taste, not Hard           ├── [GAP] ★★★  option A (acknowledge, no view change)
  │   └── [GAP] ★   passes when no contradiction          ├── [GAP] ★★   option B (update view via load-house-view)
  ├── rule_excludes_energy_em_commodity()                 ├── [GAP] ★★   option C (update with overrides)
  │   └── [GAP] ★★  triggers as Taste                     └── [GAP] ★    option E (defer + schedule)
  └── rule_pillar_omega_riskoff_riskon()                  [+] Audit integrity
      └── [GAP] ★★★ triggers as Hard stop, downgrade-       ├── [GAP] ★★★  stress_test entry hash-chains correctly
                     able with stale-rule-warning            ├── [GAP] ★★   view_hash mismatch Phase 0↔3 aborts
                                                             └── [GAP] ★★   concurrent stress-test runs both audit
                                                                              cleanly without chain corruption

[+] stress-house-view/external_comparison.py
  ├── compute_age_delta()                               [+] MCP failure paths
  │   ├── [GAP] ★★★ stale/fresh/both-fresh classifier     ├── [GAP] ★★★  market times out → PARALLAX_SILENT, run completes
  │   └── [GAP] ★★  parallax_age=null → UNVERIFIABLE_     ├── [GAP] ★★   429 rate-limit on one market → same handling
  │                  DATA path                            ├── [GAP] ★★   Parallax MCP unreachable → fail-loud, no audit
  ├── resolve_cell_state()                                └── [GAP] ★    market not in list_macro_countries → UNCOVERED
  │   ├── [GAP] ★★★ ALIGNED                                              with explicit note (no proxy)
  │   ├── [GAP] ★★★ DIVERGENT_STALE → CIO Challenge     [+] Schema validation gate
  │   ├── [GAP] ★★★ DIVERGENT_FRESH → Taste               └── [GAP] ★★★  Phase 4-B handoff with invalid draft →
  │   ├── [GAP] ★★  CIO_SILENT (Parallax high-conv only)                   downgrade to A-only, log diagnostic
  │   ├── [GAP] ★★  PARALLAX_SILENT                       [→AUDIT] adversarial-reviewer pass after first
  │   └── [GAP] ★★  UNCOVERED (no proxy)                            implementation lands — Hunter/Skeptic/Referee
  └── fanout_cap_enforce()                                          on Phase 1 rule pairings (factor-multiplier
      └── [GAP] ★★★ >12 markets → prompt branch                    sensitivity surface) + audit append hash-chain

[+] stress-house-view/audit.py
  └── append_stress_entry()
      ├── [GAP] ★★★ writes via existing audit_chain.append_entry()
      └── [GAP] ★★  applied=false on all run-only paths

[+] stress-house-view/render.py (run artifact)
  ├── [GAP] ★★  full report renders for typical 6-market run
  ├── [GAP] ★   empty-divergence report (everything aligned)
  └── [GAP] ★   all-uncovered report

COVERAGE: 0/35 code paths tested  |  0/20 CIO flows tested  |  35 GAPS (1 needs [→AUDIT])
TARGET FOR FIRST IMPLEMENTATION: ★★ minimum on every path; ★★★ on the 6 Hard/Stale-Challenge paths.
```

Reuses `_parallax/house-view/tests/` patterns (pytest, fixture-based). Adversarial-
reviewer pass scheduled after first green run — Phase 1 rule pairings touch
factor-multiplier sensitivity surface and need depth review.

---

## Premises — Confirmed

These were the only items that needed CIO judgment before implementation. Settled:

1. **Stale threshold:** flat 30d across all dimensions (config-driven).
2. **Always-check markets:** none. Only markets with a non-zero `regions` tilt are queried. Fallback: if no `regions` tilts but `macro_regime` tilts exist, query the view's primary market (inferred from basis_statement, default US).
3. **UNCOVERED fallback:** silent skip with explicit note. No regional proxy.
4. **Phase 4 default action:** A — Acknowledge, no view change. Conservative posture; CIO opts in to updates.
5. **Run artifact retention:** keep indefinitely (deferred — easy to add a `--prune` flag later if `stress-tests/` grows unwieldy).

Everything downstream is mechanical or surfaced at the Phase 4 gate.

---

## Review surfaces

The design touches a few areas worth depth-review beyond a swarm-style breadth pass:

- Pillar vocabulary used by the loader (`schema.yaml` documents the canonical set)
- Internal-consistency rule pairings that gate Phase 1
- Audit-chain extensions (new disposition values, new `validation_errors` field)

Depth review for the implementation rounds was handled by `adversarial-reviewer`
(Hunter/Skeptic/Referee) and `code-reviewer` passes; final pre-merge clean-state
review confirmed `ready-to-ship`.
