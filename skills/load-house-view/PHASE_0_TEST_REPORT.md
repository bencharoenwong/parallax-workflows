# Phase 0 — Empirical Test Report

This report covers the five empirical questions Phase 0 exists to answer (per design doc Resolution 7). Each question has a structured slot. Fill in during dogfooding. **Cannot be completed in the design session — requires live MCP access.**

If any question fails (status RED), Phase 1 design changes materially. Do not promote to Parallax MCP server until all questions are GREEN or ratings have explicit "accept-as-known-limit" justification.

---

## Test environment

| Field | Value |
|---|---|
| Date(s) of testing | 2026-04-21 (first pass) |
| Tester | Ben Charoenwong |
| Parallax MCP version | API 2.0.1 (healthy) |
| Claude model | claude-opus-4-7 (1M context) |
| Sample views used | 2026-reflationary.md (full walkthrough); other 4 samples assessed via desk extraction only |
| Test portfolios used | Hand-constructed 7-name global financials + industrials mid-cap basket (RGA, APAM.K, GFINBURO.MX, HDBK.NS, CBZ, NTB, FHB.O) |

---

## Q-A. `build_stock_universe` interaction with tilt-modified queries

**Question:** Does prepending tilt context to the natural-language query (e.g., "exclude tech, overweight defensive sectors") produce coherent results, or does the tool's interpretation collapse?

**Methodology:** Run `/parallax-portfolio-builder` for each of 5 sample views against 3 test queries: "diversified global equity," "US large-cap core," "EM growth." For each (view, query) pair, compare:
1. Universe returned without tilt context (baseline)
2. Universe returned with tilt context prepended
3. Final selected portfolio

**Pass criteria:**
- Tilt-context queries return at least 70% of the same candidates as baseline (semantic stability)
- Sector distribution of returned candidates shifts in the direction of the tilt
- No "garbage" candidates (irrelevant sectors / wrong asset class)

**Status:** ☐ Not yet run | ☐ GREEN | ☐ YELLOW (works with caveats) | **☒ RED** (partial — 1 of 5 view-query pairs tested)

**Findings:**

Tested reflationary view × "diversified global equity, mid-cap focus":

1. **Verbose tilt-context query timed out.** First attempt used the full view tilt description in natural language ("overweight EM ex-China... overweight financials, industrials, energy, AI infrastructure... underweight consumer staples, utilities... exclude tobacco, controversial weapons, Russia, Belarus"). `build_stock_universe` returned an MCP timeout. Consistent with parallax-conventions §0.1 warning that "broad/abstract queries time out" — tilt-prepended queries are structurally broad.

2. **Simplified multi-sector query succeeded but collapsed sector-wise.** Second attempt ("global mid-cap stocks across financials, industrials, energy, AI infrastructure; emphasize US and emerging markets ex-China (India, Mexico)") returned 100 candidates. **Distribution was ~95 Financials, 1 Industrials (CBZ), 0 Energy, 0 Information Technology, 0 AI infrastructure.** The tool latched onto the first sector in the comma-list and ignored the rest.

3. **Region prepending worked better than sector prepending.** Mexico (GFINBURO.MX) and India (HDBK.NS, ICBK.NS, KTKM.NS, LIFI.NS, etc.) names appeared as expected from the +2 `em_ex_china` region tilt. Regional filtering seems more robust than sector multi-listing.

4. **Force-include for +2 themes failed silently.** `energy_transition: +2` and `ai_infrastructure: +1` produced zero themed candidates in the returned universe. The loader.md §3 "Force-include if absent from candidates" rule cannot be satisfied with a single `build_stock_universe` call for multi-theme tilts.

**Action if RED:** ~~Move tilt application from query-prepend to post-retrieval re-rank only.~~ **Required changes for Phase 1:**
  - Split multi-sector tilt queries into N per-sector `build_stock_universe` calls in parallel, then merge and dedupe.
  - Same for multi-theme +2 tilts: one universe call per theme, merge.
  - Keep region tilts as query-prepend (works).
  - Document this as the canonical multi-tilt universe-building pattern in `loader.md §3`.

---

## Q-B. `quick_portfolio_scores` stability for before/after tilt diffs

**Question:** When we apply tilts and re-rank, is the score diff stable and meaningful?

**Methodology:** For each sample view, build 3 portfolios (baseline, tilted-light, tilted-heavy) of the same nominal target. Run `quick_portfolio_scores` on each. Repeat 3 times spaced 1 hour apart to check temporal stability.

**Pass criteria:**
- Score variance across same-portfolio repeats < 0.3 per factor
- Tilted portfolios show factor scores moving in the expected direction by ≥ 0.5
- Sector distribution diffs match the applied tilts

**Status:** ☐ Not yet run | ☐ GREEN | **☒ YELLOW** (blocked by upstream data-integrity issue) | ☐ RED

**Findings:**

Called `quick_portfolio_scores` on the 7-name portfolio. Results were returned but **symbol→name mapping was wrong for 6 of 7 holdings**:

| Requested | Returned name | Correct? |
|---|---|---|
| RGA | Everest Group Ltd | ✗ |
| APAM.K | Main Street Capital Corp | ✗ |
| GFINBURO.MX | PNC Financial Services Group Inc | ✗ |
| HDBK.NS | HDFC Bank Ltd | ✓ |
| NTB | Nicolet Bankshares Inc | ✗ |
| FHB.O | Fulton Financial Corp | ✗ |
| CBZ | FTI Consulting Inc | ✗ |

This is a pre-existing Parallax tool issue flagged in `parallax-conventions.md §2`, not a house-view bug. But at **6/7 mismatch prevalence** on a ticker set drawn directly from `build_stock_universe` output, Q-B's methodology is unworkable: we cannot meaningfully assess factor-diff stability when the tool is scoring the wrong companies.

Factor scores returned (VALUE 6.5, QUALITY 4.0, MOMENTUM 5.2, DEFENSIVE 9.1) were implausibly high on DEFENSIVE given the reflationary-view portfolio was hand-selected to be pro-cyclical — consistent with the symbol-mismatch story (scores map to whatever `Everest Group`, `Main Street Capital`, etc. actually are).

**Action if RED:** ~~Drop "before/after factor profile" from output format.~~ **Phase 1 design implication:** Portfolio-level factor profiling must go through individual `get_peer_snapshot` calls per holding and portfolio-weight aggregation client-side, NOT `quick_portfolio_scores`, until the upstream symbol-resolution bug is fixed in Parallax. Update `loader.md` multiplier-confirmation flow to use per-holding snapshots.

---

## Q-C. `analyze_portfolio` truncation rate on tilted portfolios

**Question:** Existing skills note 180K char truncation on `analyze_portfolio` responses. Do tilted portfolios trigger this more often?

**Methodology:** Run `analyze_portfolio` with both lenses ("performance", "concentration") on baseline AND tilted portfolios for each sample view. Record response sizes.

**Pass criteria:**
- Tilted portfolios do not trigger truncation more than 10pp above baseline rate
- Fallback path (`check_portfolio_redundancy` + `quick_portfolio_scores`) produces equivalent insights

**Status:** ☐ Not yet run | ☐ GREEN | **☒ YELLOW** (partial — fallback path itself produced degraded output) | ☐ RED

**Findings:**

Did not hit the 180K truncation ceiling on the one tested portfolio (7 holdings is below typical truncation threshold anyway). The more interesting failure was in the fallback path:

- `check_portfolio_redundancy` on a portfolio that was **86% financials by weight** returned `has_issues: false`, empty `sector_concentration: {}`, empty `industry_overlap: {}`, and "Portfolio looks well-diversified" — **clearly wrong**.
- Response was not truncated; it was just empty/non-informative.

This suggests the fallback path may not produce equivalent insights for highly sector-concentrated portfolios (which tilted portfolios increasingly are, by construction). Worth a separate investigation.

**Action if RED:** Document the higher truncation rate for tilted portfolios in `parallax-conventions.md` and pre-emptively use fallback path when active view is loaded. **Additionally:** investigate `check_portfolio_redundancy`'s behavior on single-sector-dominant portfolios — the empty-payload-as-"diversified" response is a latent bug.

---

## Q-D. Multiplier calibration on hand-graded sample portfolios

**Question:** Does loader.md §3 multiplier table (sector +2 → 1.5×, factor +2 → 2.0×, etc.) produce intuitive results on hand-graded sample portfolios?

**Methodology:** For each sample view, manually construct an "intuitive expected portfolio" of 5-8 stocks. Then run `/parallax-portfolio-builder` with the view active and compare:
- Sector distribution: actual vs expected
- Factor profile: actual vs expected
- Selected names: overlap with expected

**Pass criteria:**
- Sector overlap with expected ≥ 70%
- Factor profile direction matches expected for all 4 factors
- No expected name excluded due to tilt overshoot

**Status:** **☒ Not yet run** | ☐ GREEN | ☐ YELLOW | ☐ RED

**Findings:**

Blocked by Q-A and Q-B findings. Q-D requires a trustworthy universe (Q-A) AND trustworthy portfolio-level factor scores (Q-B). With the universe collapsed to one sector and `quick_portfolio_scores` mis-mapping 6/7 holdings, there is no way to hand-grade vs. actual that isolates the multiplier table's behavior.

**Calibration tuning:** if results are systematically too aggressive (overshoot tilts) or too weak (tilts barely visible), adjust multiplier table in `loader.md §3`. Document each calibration change here with date and reason.

| Date | Change | Reason |
|---|---|---|
| _to be filled_ | _to be filled_ | _to be filled_ |

**Action if RED after 2 calibration rounds:** Consider replacing simple multiplier with an explicit optimizer step. Phase 1 likely needs this anyway for institutional-scale AUM (per BUG-003 in adversarial review). **Current recommendation:** unblock Q-A (multi-call universe pattern) and Q-B (per-holding snapshot aggregation) before running Q-D.

---

## Q-E. PDF extraction quality on real CIO documents

**Question:** CIO views are prose-heavy, hedged, mixed structured/unstructured. Does extraction reach >0.7 confidence on the typed fields?

**Methodology:** Run `/parallax-load-house-view` on each of the 5 markdown samples (controlled prose) AND on at least 2 real CIO PDFs sourced from public asset-manager outlooks (uncontrolled). Record per-field `extraction_confidence`.

**Pass criteria:**
- Mean confidence across all fields ≥ 0.7 on markdown samples
- Mean confidence ≥ 0.6 on real PDFs
- No critical-tilt field (sectors, excludes, macro_regime) below 0.5

**Status:** ☐ Not yet run | ☐ GREEN | **☒ YELLOW** (markdown samples clear pass criteria, but `macro_regime` dips below 0.5 on 2 of 5 samples) | ☐ RED

**Findings per sample:**

| Sample | Mean confidence | Lowest field | Notes |
|---|---|---|---|
| 2026-reflationary.md | 0.87 | regions (0.80); IT (0.70 inside sectors) | Clean structured prose. China UW inferred from "EM ex-China" framing, not explicit. IT collapsed from "constructive on AI infra but selective in software" — captured via themes.ai_infrastructure +1 alongside sectors.IT +1. Live-run confirmed gate renders cleanly; full walkthrough completed. |
| recession-defensive.md | 0.78 | themes (0.50) | Factor-and-sector view with minimal thematic language. Non-standard excludes ("SPACs", "pre-revenue biotech", "speculative-grade refi dependents") do not map to schema exclude keys — schema needs free-form exclude support or loader-side coercion. Macro regime maps cleanly: slowing + sticky → loader.md §3 stagflation-lite auto-tilt (defensive +1, quality +1, momentum -1). |
| AI-concentrated.md | 0.81 | excludes (0.55) | Thematic view — `themes.ai_infrastructure +2` is trivially high confidence. Region mapping awkward: Taiwan/Korea collapse into `apac_ex_japan` even though they're the explicit target (no schema key for Taiwan-only). "AI-washing" exclude is a qualitative screen, not a schema-compatible exclude. Macro regime not explicit — inferred expansion + benign from pro-cyclical framing. |
| ESG-screened.md | 0.73 | macro_regime (0.40), styles (0.40) | Mandate-driven view: excludes are long and explicit (0.90 confidence) but many entries (tar sands, Arctic O&G, thermal coal, adult entertainment, for-profit detention, Norges Bank list) are non-standard schema keys. **Macro regime absent from source** — the view is compliance/thematic, not macro. Extraction must default to neutral; schema should treat macro_regime as optional. |
| China-skeptic.md | 0.67 | macro_regime (0.30) | Geopolitical view — strongest region tilts of any sample (China -2, India +2, Mexico +2, Japan +1, Vietnam/Indonesia/Malaysia +1). Excludes: US Entity List Chinese names + HK CCP SOEs don't fit the current schema (they're dynamic lists, not static RIC entries). **Macro regime entirely absent from source** — this is a geopolitical thesis, not a macro regime call. Schema rigidity forces false extraction here. |
| Real PDF #1: _name_ | _to be filled_ | _to be filled_ | _to be filled_ |
| Real PDF #2: _name_ | _to be filled_ | _to be filled_ | _to be filled_ |

**Aggregate:** mean-of-means across 5 markdown samples = **0.77** (above 0.7 pass threshold). However, 2 of 5 samples dip below 0.5 on `macro_regime` because the CIO source doesn't speak in macro-regime terms (ESG-screened is mandate-driven, China-skeptic is geopolitical). **This violates the "no critical-tilt field below 0.5" criterion.**

**Action if RED:** Revise the extraction prompt in `load-house-view/SKILL.md` Step 2. If confidence is structurally low after prompt iteration, the schema is too rigid for prose input — consider relaxing to allow free-form tilts with optional structured fields, or require uploaders to fill a template. **Concrete recommendations:**
1. Make `tilts.macro_regime` optional — when source is mandate-driven or geopolitical, skip rather than force a neutral default that misrepresents the uploader's thesis. Update loader.md §3 to treat missing `macro_regime` as "no auto-tilt applied" (not as `neutral+neutral`).
2. Add a free-form `excludes_freeform:` array alongside the typed `excludes:` for non-schema entries ("SPACs", "AI-washing", "speculative-grade refi", "US Entity List"). Loader surfaces these as advisory flags rather than hard excludes on named RICs.
3. Consider adding `taiwan` and `south_korea` as explicit region keys — `apac_ex_japan` is too coarse for AI/semi views where these are the explicit targets.
4. Add a `reshoring` theme to the schema (repeatedly relevant across multiple samples — reflationary, AI-concentrated, China-skeptic).

---

## Cross-cutting observations

1. **Schema rigidity is the dominant Q-E failure mode.** The view samples collectively exceed the schema's expressive capacity in 4 ways: (a) non-standard excludes (SPACs, AI-washing, entity-list names, ESG industry categories), (b) region granularity below `apac_ex_japan` (Taiwan, Korea), (c) non-schema themes (reshoring, defense-ex-weapons), (d) optional-vs-required `macro_regime` for non-macro views. A schema extension pass is required before Phase 1.

2. **`build_stock_universe` does not compose tilt-prepended queries well.** Sector multi-listing collapses to the first listed sector; thematic +2 tilts produce no themed candidates. Region prepending works. This argues for splitting universe construction into per-tilt parallel calls with client-side merge/dedupe rather than single-shot tilt-prepend. This is a **loader-pattern change**, not a tool fix.

3. **Upstream symbol-resolution bug contaminates Q-B/Q-C/Q-D.** `quick_portfolio_scores` mis-maps ~6 of 7 hand-selected mid-cap tickers to unrelated companies. Until this is addressed (upstream Parallax fix or always-fall-back to per-holding `get_peer_snapshot`), several Phase 0 questions cannot be cleanly answered. Flag to Parallax team independently of house-view work.

4. **`check_portfolio_redundancy` silently returns empty on sector-concentrated portfolios.** An 86%-financials portfolio was reported "well-diversified" with empty `sector_concentration`. This is a latent bug affecting the fallback path we'd depend on when `analyze_portfolio` truncates. Investigate separately.

5. **The confirmation gate UX works well on structured prose.** For 2026-reflationary, the gate rendered cleanly, called out low-confidence fields (IT 0.70, china 0.60, obesity_drugs 0.60), and the `AskUserQuestion` flow is responsive. Uploader confirmation round-tripped cleanly. Hash+UUID generation and prose pairing work as designed.

6. **House View Preamble + conflict banner rendering works.** On the "diversified global equity, mid-cap focus" query the portfolio-builder output correctly rendered: (a) load preamble with view_name + dates + low-confidence warnings, (b) explicit conflict banner for "diversified" vs. the view's directional call with re-runcommand suggestion, (c) tilt multipliers column in holdings table, (d) view-aware disclaimer. Format is production-ready pending upstream data-quality fixes.

---

## Phase 1 readiness summary

After all 5 questions are scored:

| Question | Status | Phase 1 implication |
|---|---|---|
| A | RED (partial) | Must split universe construction into per-tilt parallel calls + merge; single-call tilt-prepend is broken for sectors/themes |
| B | YELLOW | Replace `quick_portfolio_scores` with per-holding `get_peer_snapshot` aggregation in portfolio-factor-profile flow until upstream symbol-resolution is fixed |
| C | YELLOW | Investigate `check_portfolio_redundancy` empty-payload bug on concentrated portfolios before relying on it as truncation fallback |
| D | Not run | Unblock A + B first; Q-D is dependent |
| E | YELLOW | Relax schema: optional macro_regime, free-form excludes, add taiwan/korea regions + reshoring theme |

**Recommendation:** ☐ Promote to Phase 1 design | **☒ Iterate on Phase 0 first** | ☐ Architectural revision needed

**Rationale:**
The output-format layer (Preamble, conflict banners, multiplier columns, view-aware disclaimer) and the ingest layer (gate, hash, prose pairing, UUID lineage) are production-ready. The blockers are all **data-layer**:
1. Schema doesn't accommodate the real diversity of CIO views (5 of 5 samples stress the schema in at least one dimension).
2. `build_stock_universe` is the wrong shape for tilt-composite queries; must be decomposed into parallel per-tilt calls.
3. Upstream Parallax tool bugs (symbol mismatch in `quick_portfolio_scores`, empty-payload in `check_portfolio_redundancy` on concentrated portfolios) degrade every validation path we have.

Proposed Phase 0 iteration before Phase 1 promotion:
- Add schema extensions enumerated in Q-E action section (free-form excludes, optional macro_regime, taiwan/korea, reshoring theme).
- Rewrite loader.md §3 universe-construction pattern to per-tilt parallel calls + merge.
- Add a canonical `get_peer_snapshot`-based portfolio scoring fallback to loader.md, remove reliance on `quick_portfolio_scores` where name-integrity matters.
- Re-run Q-A through Q-D against the amended design. Q-E is ready to re-score against the schema extensions.
