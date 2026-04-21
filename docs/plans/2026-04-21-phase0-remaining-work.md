# Phase 0 — Remaining Work Plan

**Created:** 2026-04-21
**Status:** Active — owns the path to Phase 1 promotion gate
**Parent decision:** `DECISIONS.md` entry 2026-04-21 (council verdict)
**Supersedes:** none
**Expected duration:** 1 sprint + half a week on PDF stress-test

## Context at start

Phase 0 house-view ingestion shipped via PR #3 (merged `9e1554c`). Schema loosening, data-integrity rules in `loader.md` §5, regression corpus (5/5 pass @ mean conf 0.87), concierge skill, decision log — all live on main. Three items remain before Phase 1 promotion gate.

**What's live:**
- `/parallax-load-house-view` ingestion skill + gate
- Schema with nullable `macro_regime`, `taiwan` / `south_korea` regions, `reshoring` theme
- Loader §5 rules 3 (ground-truth panel) and 4 (sector-count divergence assertion) — specified but NOT YET wired into consumer skills beyond `portfolio-builder`
- Regression corpus runner + 5 labeled seed baselines

**What's not live:**
- Upstream Parallax fix ETA (blocks path-flip decision)
- Per-tilt parallel universe calls + per-holding snapshot aggregation (Council item (b))
- Q-E validation against real uncontrolled CIO PDFs (Council item (d))

---

## Item 1 — Send upstream Parallax email

**Owner:** Ben (only you can send).
**Blocks:** sequencing decision between (b) client-side workaround and (c) upstream-wait.
**Reversibility:** fully reversible.
**Effort:** 10 minutes.

### Task breakdown

1. Open draft at `notes/2026-04-21-parallax-upstream-email.md`. (Gitignored — working doc only.)
2. Fill in `[recipient]` and CC list. Suggested routing:
   - Primary recipient: Parallax MCP engineering lead (whoever owns `quick_portfolio_scores` and `check_portfolio_redundancy`).
   - CC: Parallax product owner + yourself.
3. Adjust tone for audience:
   - If recipient is on the CG team directly: keep the direct "I need ETAs" framing.
   - If it's an external vendor or a wider audience: soften the opening, drop the "Happy to jump on a 15-min call" if too informal.
4. Attach or inline the reproduction JSON request (`RGA, APAM.K, GFINBURO.MX, ...`) from Bug 1 — the evidence is the single thing that prevents 20 rounds of "can you show us the inputs?"
5. Send.
6. Log the send in `DECISIONS.md` under the existing 2026-04-21 entry (append a one-line update: `2026-04-21: sent upstream ETA request for Q-B/Q-C; awaiting reply`).

### Success criteria
- Email sent.
- Reply received within 10 business days OR marked "no reply after deadline → assume quarter-plus, proceed with full (b) scope."

### Tip-condition follow-up
Per `DECISIONS.md`: if reply is ≤10 business days, **do not** execute Item 2 (b) in full. Instead:
- Ship a thin divergence-assertion + telemetry layer (already specced in `loader.md` §5 rule 4) wired into consumer skills.
- Wait for upstream.
- Close out Item 2 with a "not required this sprint" amendment to `DECISIONS.md`.

---

## Item 2 — Loader-pattern rewrite (Council item (b))

**Owner:** Ben + Claude Code (implementation session).
**Blocks:** Phase 1 promotion — Q-A needs to go from RED to GREEN before pilot clients touch it.
**Reversibility:** partly reversible — feature-flag it for first 1-2 weeks so rollback is easy.
**Effort estimate:** ~1 sprint (5 working days). Scoped ~300-400 LoC across 8 files.

### Goal

Replace two fragile single-call patterns with multi-call + client-side composition patterns:

| Pattern | Current (broken) | Target (robust) |
|---|---|---|
| Multi-sector universe construction | `build_stock_universe("stocks across financials, industrials, energy, AI")` → 95/100 Financials | N parallel per-sector calls → merge + dedupe by RIC |
| Portfolio factor profile | `quick_portfolio_scores(holdings)` → 6/7 wrong-company mapping | `get_peer_snapshot(symbol)` per holding → weight-aggregate client-side |

### Task breakdown

#### 2.1 Design spec (half day)

Produce `docs/plans/2026-04-21-loader-rewrite-spec.md` with:

- **Before/after pseudocode** for each of the two patterns.
- **Feature-flag approach**: env var `PARALLAX_LOADER_V2=1` or setting in `_parallax/parallax-conventions.md` header. Default off for first 1-2 weeks, default on after.
- **Consumer-skill migration table**: for each of the 6 view-aware skills (`portfolio-builder`, `rebalance`, `thematic-screen`, `morning-brief`, `client-review`, `explain-portfolio`), list which sections invoke which patterns and need edits.
- **Rollback plan**: flip the flag back. Old path stays in code for 1 release.
- **Expected Q-A status** after rewrite: GREEN.

#### 2.2 Implement per-tilt parallel universe construction (1.5 days)

**Files touched (approximate):**
- `skills/_parallax/house-view/loader.md` — add §3a "Per-tilt parallel universe construction" subsection. Document the decomposition: for a view with N non-zero sector tilts and M non-zero theme tilts, issue `N + M` parallel `build_stock_universe` calls with single-scope queries, then merge by RIC, dedupe, re-rank by composite-with-multipliers.
- `skills/portfolio-builder/SKILL.md` — replace step 1 "Build Universe" with "1a: decompose tilts into per-scope queries; 1b: issue N parallel `build_stock_universe` calls; 1c: merge + dedupe + re-rank."
- `skills/thematic-screen/SKILL.md` — same pattern.
- `skills/rebalance/SKILL.md` — rebalance calls universe only to find replacements; same pattern applies but smaller N.
- `skills/explain-portfolio/SKILL.md` — same for rotation candidates.
- `skills/morning-brief/SKILL.md` — morning-brief doesn't build universes, just checks holdings; exempt.
- `skills/client-review/SKILL.md` — same exempt.

**Verification per file:** divergence-assertion from `loader.md` §5 rule 4 should return PASS (max_sector_share ≤ 0.6 for multi-sector queries) on a synthetic reflationary-view run.

#### 2.3 Implement per-holding snapshot aggregation (1 day)

**Files touched:**
- `skills/_parallax/house-view/loader.md` — add §3b "Per-holding factor aggregation." Specify: for each holding, call `get_peer_snapshot(symbol)` in parallel; cross-validate `target_company` against `get_company_info(symbol).name`; if mismatch, flag row as ⚠ MISMATCH and exclude from aggregate; compute `portfolio_factor[f] = Σ(weight_i × snapshot_i.factor[f]) / Σ(weight_i)` across non-mismatched holdings.
- `skills/_parallax/parallax-conventions.md` §2 — update "Symbol Cross-Validation" to mark `quick_portfolio_scores` as "use with explicit cross-validation only; prefer per-holding snapshots for portfolio-level factor profiling when active house view is loaded."
- `skills/portfolio-builder/SKILL.md` — step 5 already says prefer `get_peer_snapshot`; make this unconditional when view active.
- `skills/portfolio-checkup/SKILL.md` — same.
- `skills/client-review/SKILL.md` — same.
- `skills/morning-brief/SKILL.md` — same.

**Verification:** re-run the live scenario from 2026-04-21 dogfooding (the 7-holding reflationary-view portfolio). Expected: all 7 holdings show correct returned_name next to score; factor profile DEFENSIVE score drops from 9.1 (contaminated) to ≤5 (consistent with reflationary view).

#### 2.4 Regression corpus extension (0.5 days)

- Add 2 new test scenarios to `skills/load-house-view/regression-corpus/`:
  - `scenarios/universe-multi-sector.md` — mock input expected universe distribution for reflationary view; assertions on sector-balance.
  - `scenarios/portfolio-scoring-mixed-exchange.md` — hand-constructed portfolio with known-correct company names; assertions on name-cross-validation and factor aggregate.
- Extend `run_regression.py` with a new `--scenarios` flag pointing at these files; scenarios assert on MCP-call outcomes, not extraction labels. Needs MCP access to run; corpus extraction tests remain the pre-merge gate.

#### 2.5 Wire + ship + monitor (1 day)

- Land as one feature-flagged PR.
- Enable the flag for first pilot client after the flag has survived 1 week in test.
- Monitor `~/.parallax/active-house-view/audit.jsonl` for `conflicts_count` regressions over the first 48 hours.

### Success criteria

- [ ] Q-A status upgraded from RED to GREEN in `PHASE_0_TEST_REPORT.md`.
- [ ] Divergence-assertion does not trigger on any reflationary-view run.
- [ ] `quick_portfolio_scores` no longer invoked in any view-aware code path.
- [ ] Regression-corpus runner still passes all 5 seed baselines (extraction behavior unchanged by loader changes).
- [ ] 1 live dogfood run shows all 7 holdings with correct returned_name.

### Decision to defer from this item

- **`excludes_freeform` schema addition** — tracked separately; came up during corpus labeling. Decide whether to add the field to `schema.yaml` canonical structure or drop the concept. Not load-bearing for Phase 1.
- **Prose-first / commitments reframe** (Council Advisor 2 dissent) — revisit ONLY after Phase 1 pilot feedback. Do not preemptively rewrite the schema.

---

## Item 3 — Real CIO PDF stress-test (Council item (d))

**Owner:** Ben (sourcing) + Claude Code (extraction + labeling).
**Blocks:** Phase 1 promotion gate — final Q-E proof that extraction works on uncontrolled input.
**Reversibility:** fully reversible (tests only).
**Effort:** half a day once PDFs are sourced.

### Task breakdown

#### 3.1 Source 2 public CIO PDFs (Ben — 30 min)

Good candidates (all publicly available quarterly outlooks):
- **Bridgewater Daily Observations** — Bridgewater publishes multi-page macro outlooks; dense macro-regime language. Tests `macro_regime` + factor-tilt extraction.
- **GMO 7-Year Forecast** — pure valuation / factor-tilt view; tests `factors` and `styles` extraction on a non-macro-framed document.
- **Oaktree Memos** (Howard Marks) — narrative-heavy, low structure; stress-tests extractor against prose-only views.
- **BlackRock Investment Institute Outlook** — structured quarterly outlook with sector tilts. Tests `sectors` + `regions` extraction.
- **PIMCO Cyclical Outlook** — macro regime explicit. Tests `macro_regime`.

Pick 2 from different view-families (e.g., Bridgewater + GMO, OR BlackRock + Oaktree). Save as `skills/load-house-view/samples/real-pdf-*.pdf`.

#### 3.2 Run extraction against both (1 hour)

- `/parallax-load-house-view skills/load-house-view/samples/real-pdf-1.pdf`
- Walk the confirmation gate as the CIO.
- Save `view.yaml` output as baseline at `regression-corpus/baselines/2026-XX-XX/real-pdf-1.yaml`.

#### 3.3 Hand-label expected extraction (2 hours)

- For each PDF, read slowly and hand-author `corpus.yaml` entry with `view_family`, expected tilts (ranges for hedged language), required excludes, and expected-confidence thresholds.
- Follow the governance rules in `regression-corpus/README.md` — label what a careful human would accept, not what the extractor happened to produce.
- Add both entries to `corpus.yaml` (v2 bump).

#### 3.4 Re-run corpus runner (10 min)

- `python3 run_regression.py --corpus corpus.yaml --baselines baselines/<latest>`
- Expected: 5 markdown seed baselines still PASS; 2 real-PDF baselines produce either PASS or FAIL with meaningful diff.
- If FAIL: the extraction needs tuning OR the label is wrong. Use the governance rule: labels change when defensible against source; extractor changes when labels are rigorous.

### Success criteria

- [ ] 2 real PDFs extracted end-to-end through the live skill.
- [ ] Both entries labeled in `corpus.yaml`.
- [ ] Mean confidence on real PDFs ≥ 0.60 (Q-E pass criterion for uncontrolled input — relaxed from 0.70 threshold for markdown samples).
- [ ] No macro_regime field below 0.5 on either PDF (same critical-tilt rule).

### If this fails

Council dissent path from Advisor 2 kicks in: the YAML schema is fighting real prose, and we should consider prose-first + extracted-commitments before Phase 1. Re-council with evidence from these 2 PDFs.

---

## Recommended sequencing

```
Day 0 (today after this plan is saved):
  └─ Item 1 (send email) — 10 min, unblocks everything

Day 1-2 (while awaiting upstream reply):
  └─ Item 2.1 (loader-rewrite spec) — half day, written before implementation
  └─ Item 3.1 (source 2 PDFs) — 30 min, can do in parallel

Day 2-5 (main sprint work):
  ├─ If upstream reply ≤10 business days:
  │    └─ Ship thin tripwire layer (loader §5 rule 4 wiring into remaining 5 skills).
  │        Skip 2.2 and 2.3. Reopen Item 2 after upstream ships.
  │        → Budget freed for Item 3 end-to-end validation.
  │
  └─ If upstream reply quarter-plus OR no reply:
       └─ Item 2.2-2.5 (full loader rewrite) — 4 days.
          └─ Gate on Item 2 passing before Item 3.4 (extension of corpus).

Day 5-6:
  └─ Item 3.2-3.4 (PDF extraction + labeling + re-run) — half day

Day 7 (Phase 1 gate evaluation):
  ├─ Q-A: expected GREEN
  ├─ Q-B: expected GREEN (per-holding aggregation path proven)
  ├─ Q-C: still YELLOW (concentration-fallback is client-side; bug remains upstream)
  ├─ Q-D: re-run with GREEN universe + GREEN scoring → expected GREEN
  └─ Q-E: GREEN on markdowns; expected YELLOW-or-GREEN on real PDFs
  →  Council re-convenes only if any of A/B/D is not GREEN.
```

## Exit criteria for Phase 0

All of:
- Q-A GREEN (universe no longer collapses)
- Q-B GREEN (per-holding snapshot aggregation or upstream Parallax fix)
- Q-C YELLOW accepted (client-side fallback documented + shipped, upstream tracking)
- Q-D GREEN (end-to-end dogfood with hand-graded expected portfolio — reflationary or recession-defensive view)
- Q-E GREEN on markdown corpus; documented result on 2 real PDFs
- `DECISIONS.md` has a dated "Phase 0 closes → Phase 1 design begins" entry
- Upstream Parallax ticket status documented (ETA received OR marked "indefinite — client-side workarounds shipping")

## Open questions flagged in council (still unanswered by user)

1. **Phase 1 reversibility — is promotion a soft internal label or client-facing contract?** Materially affects go/no-go call when any Q- status is not fully GREEN. Do not close Phase 0 without answering.
2. **Does the schema need an `excludes_freeform` field?** Discovered during corpus labeling. Not blocking Phase 0, but should be resolved before Phase 1 pilot data lands.

---

*Plan document. When a task completes, strike through its success-criteria checkbox and log in `DECISIONS.md` under the existing 2026-04-21 entry. Do not edit this plan to change scope — update via a new plan doc that supersedes this one.*
