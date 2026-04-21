# Phase 0 — Empirical Test Report

This report covers the five empirical questions Phase 0 exists to answer (per design doc Resolution 7). Each question has a structured slot. Fill in during dogfooding. **Cannot be completed in the design session — requires live MCP access.**

If any question fails (status RED), Phase 1 design changes materially. Do not promote to Parallax MCP server until all questions are GREEN or ratings have explicit "accept-as-known-limit" justification.

---

## Test environment

| Field | Value |
|---|---|
| Date(s) of testing | _to be filled_ |
| Tester | _to be filled_ |
| Parallax MCP version | _to be filled_ |
| Claude model | _to be filled_ |
| Sample views used | All 5 in `samples/` |
| Test portfolios used | _list of portfolio JSONs_ |

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

**Status:** ☐ Not yet run | ☐ GREEN | ☐ YELLOW (works with caveats) | ☐ RED

**Findings:**
_to be filled_

**Action if RED:** Move tilt application from query-prepend to post-retrieval re-rank only. Document this as a known limitation.

---

## Q-B. `quick_portfolio_scores` stability for before/after tilt diffs

**Question:** When we apply tilts and re-rank, is the score diff stable and meaningful?

**Methodology:** For each sample view, build 3 portfolios (baseline, tilted-light, tilted-heavy) of the same nominal target. Run `quick_portfolio_scores` on each. Repeat 3 times spaced 1 hour apart to check temporal stability.

**Pass criteria:**
- Score variance across same-portfolio repeats < 0.3 per factor
- Tilted portfolios show factor scores moving in the expected direction by ≥ 0.5
- Sector distribution diffs match the applied tilts

**Status:** ☐ Not yet run | ☐ GREEN | ☐ YELLOW | ☐ RED

**Findings:**
_to be filled_

**Action if RED:** Drop "before/after factor profile" from output format. Use `get_peer_snapshot` per holding instead.

---

## Q-C. `analyze_portfolio` truncation rate on tilted portfolios

**Question:** Existing skills note 180K char truncation on `analyze_portfolio` responses. Do tilted portfolios trigger this more often?

**Methodology:** Run `analyze_portfolio` with both lenses ("performance", "concentration") on baseline AND tilted portfolios for each sample view. Record response sizes.

**Pass criteria:**
- Tilted portfolios do not trigger truncation more than 10pp above baseline rate
- Fallback path (`check_portfolio_redundancy` + `quick_portfolio_scores`) produces equivalent insights

**Status:** ☐ Not yet run | ☐ GREEN | ☐ YELLOW | ☐ RED

**Findings:**
_to be filled_

**Action if RED:** Document the higher truncation rate for tilted portfolios in `parallax-conventions.md` and pre-emptively use fallback path when active view is loaded.

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

**Status:** ☐ Not yet run | ☐ GREEN | ☐ YELLOW | ☐ RED

**Findings:**
_to be filled_

**Calibration tuning:** if results are systematically too aggressive (overshoot tilts) or too weak (tilts barely visible), adjust multiplier table in `loader.md §3`. Document each calibration change here with date and reason.

| Date | Change | Reason |
|---|---|---|
| _to be filled_ | _to be filled_ | _to be filled_ |

**Action if RED after 2 calibration rounds:** Consider replacing simple multiplier with an explicit optimizer step. Phase 1 likely needs this anyway for institutional-scale AUM (per BUG-003 in adversarial review).

---

## Q-E. PDF extraction quality on real CIO documents

**Question:** CIO views are prose-heavy, hedged, mixed structured/unstructured. Does extraction reach >0.7 confidence on the typed fields?

**Methodology:** Run `/parallax-load-house-view` on each of the 5 markdown samples (controlled prose) AND on at least 2 real CIO PDFs sourced from public asset-manager outlooks (uncontrolled). Record per-field `extraction_confidence`.

**Pass criteria:**
- Mean confidence across all fields ≥ 0.7 on markdown samples
- Mean confidence ≥ 0.6 on real PDFs
- No critical-tilt field (sectors, excludes, macro_regime) below 0.5

**Status:** ☐ Not yet run | ☐ GREEN | ☐ YELLOW | ☐ RED

**Findings per sample:**

| Sample | Mean confidence | Lowest field | Notes |
|---|---|---|---|
| 2026-reflationary.md | _to be filled_ | _to be filled_ | _to be filled_ |
| recession-defensive.md | _to be filled_ | _to be filled_ | _to be filled_ |
| AI-concentrated.md | _to be filled_ | _to be filled_ | _to be filled_ |
| ESG-screened.md | _to be filled_ | _to be filled_ | _to be filled_ |
| China-skeptic.md | _to be filled_ | _to be filled_ | _to be filled_ |
| Real PDF #1: _name_ | _to be filled_ | _to be filled_ | _to be filled_ |
| Real PDF #2: _name_ | _to be filled_ | _to be filled_ | _to be filled_ |

**Action if RED:** Revise the extraction prompt in `load-house-view/SKILL.md` Step 2. If confidence is structurally low after prompt iteration, the schema is too rigid for prose input — consider relaxing to allow free-form tilts with optional structured fields, or require uploaders to fill a template.

---

## Cross-cutting observations

_Patterns or issues that span multiple questions; behaviors not anticipated in the design._

_to be filled_

---

## Phase 1 readiness summary

After all 5 questions are scored:

| Question | Status | Phase 1 implication |
|---|---|---|
| A | _ | _ |
| B | _ | _ |
| C | _ | _ |
| D | _ | _ |
| E | _ | _ |

**Recommendation:** ☐ Promote to Phase 1 design | ☐ Iterate on Phase 0 first | ☐ Architectural revision needed

**Rationale:**
_to be filled_
