# Parallax AI Investor Profiles — Design Spec

**Date:** 2026-04-06
**Author:** Ben Charoenwong (with Claude Code brainstorming + council)
**Status:** Draft for user review
**Repo:** `parallax-workflows`

---

## TL;DR

Build a family of standalone Claude Code skills under the umbrella **Parallax AI Investor Profiles**, each implementing a famous investor's *workflow shape* (not just rubric thresholds) over Parallax MCP tools, anchored in published academic or biographical sources, framed in third person ("Buffett-style"), and prefixed `parallax-AI-*` to flag them clearly as AI interpretations.

**Launch set (v1, four profiles + one meta-skill):**

| Skill | Anchor | Workflow shape |
|---|---|---|
| `parallax-AI-buffett` | Frazzini, Kabiller, Pedersen, "Buffett's Alpha", *FAJ* 2018 | Bottom-up single-stock; +Quality +Value −Momentum +Defensive |
| `parallax-AI-soros` | Soros, *The Alchemy of Finance* (1987); Drobny, *Inside the House of Money* (2006) | Top-down macro → geography → industry → ranked trade ideas; multi-asset |
| `parallax-AI-greenblatt` | Greenblatt, *The Little Book That Beats the Market* (2006); Gray & Carlisle, *Quantitative Value* (2012) | Mechanical screen: ROC + earnings yield → top-decile basket |
| `parallax-AI-klarman` | Klarman, *Margin of Safety* (1991) | Bottom-up special situations: balance sheet stress + cash rationality + patient verdict |
| `parallax-AI-consensus` | (meta) | Runs all installed profiles in parallel, returns unanimity matrix; super-majority agreement = high-conviction signal |

All five skills:
- Use **only public data** (no `get_assessment`, no proprietary `score_total`, no `get_stock_report`).
- Are **deterministic** given Parallax data — no LLM in the loop, no temperature drift.
- Output **third-person methodology-first language** with mandatory citation footer + non-advice disclaimer.
- Are **standalone but share a thin core** at `skills/_parallax/AI-profiles/` for the profile spec format and the output template.
- Map cleanly to MAS Project MindForge's seven GenAI risk dimensions; full mapping in §7.

**Legal posture:** Profiles are *not* gated on a legal review before invocation. The disclaimer and naming conventions (AI prefix, -style suffix, mandatory citation, "not financial advice", "consult a qualified financial advisor") do the legal work at runtime. Counsel review is an ongoing quality process that may tighten wording but does not block the skills from running. See §6.1.

---

## 1. Goals and non-goals

### Goals
1. **Showcase more Parallax use cases** — exercise tools that existing skills underuse (`macro_analyst` chained, `get_telemetry`, `build_stock_universe` for thematic universes).
2. **Provide a public-friendly product surface** that the retail MCP can wrap without exposing proprietary endpoints.
3. **Pedagogically teach factor literacy** — a retail user running `parallax-AI-buffett` learns *why* quality and value matter, not just a number.
4. **Generate cross-profile consensus signals** — the meta-skill surfaces stocks where multiple AI profiles agree, which is more actionable than any single profile.
5. **Be defensible** — academic/biographical anchors, AI prefix, third-person framing, citation footer, disclaimer, no impersonation.

### Non-goals
- **Personalized advice.** No user portfolio ingestion in the public version. No "given your risk tolerance" framing. Identical output for any user querying the same ticker.
- **Discretionary judgment investors without a public anchor.** No Druckenmiller, no Burry — for v1 — until and unless we identify a public source documenting their workflow at the same level of specificity as Soros's *Alchemy*.
- **Replicating proprietary `score_total`.** The lens IS the opinion; we do not need (and must not have) a top-line "Buffett Score: 7/10 Buy."
- **Backtesting the profiles.** That's a follow-on for `paper-to-signal` / the trading repo, not part of v1. Out of scope here but the spec format is designed to make it possible later.
- **Internationalization.** v1 ships in English only.

---

## 2. Architecture

### 2.1 File layout

```
parallax-workflows/
└── skills/
    ├── _parallax/
    │   ├── parallax-conventions.md          (existing — JIT-loaded by all skills)
    │   ├── token-costs.md                   (existing)
    │   └── AI-profiles/                     (NEW shared core)
    │       ├── README.md                    (scope boundary, in/out list)
    │       ├── profile-schema.md            (frontmatter + body contract for any profile)
    │       ├── output-template.md           (required output structure + disclaimer language)
    │       └── profiles/
    │           ├── buffett.md               (profile spec for Buffett)
    │           ├── soros.md                 (profile spec for Soros)
    │           ├── greenblatt.md            (profile spec for Greenblatt)
    │           └── klarman.md               (profile spec for Klarman)
    ├── AI-buffett/
    │   └── SKILL.md                         (~80 lines, dispatcher; JIT-loads buffett.md)
    ├── AI-soros/
    │   └── SKILL.md
    ├── AI-greenblatt/
    │   └── SKILL.md
    ├── AI-klarman/
    │   └── SKILL.md
    └── AI-consensus/
        └── SKILL.md                         (meta-skill, fans out to all installed profiles)
```

### 2.2 Why this layout

- **Each `AI-*/SKILL.md` is standalone** (B2 decision) — users can install one profile without the others, and each gets its own `/parallax-AI-<name>` slash command for discoverability.
- **Profile *specs* live in shared `_parallax/AI-profiles/profiles/`** as data, not code. A profile spec is a markdown file with YAML frontmatter — grep-able, diff-friendly, reviewable. Adding a profile is a new spec file plus a 60-80 line skill dispatcher.
- **The output template is centralized.** No skill can deviate from the disclosure footer or the citation block. Compliance posture is enforced by structure, not by hoping each skill author remembers.
- **The schema is the contract.** A profile spec without a citation, factor loadings, and tool sequence cannot pass schema validation and will not render.

### 2.3 Profile spec format

Each `profiles/<name>.md` file conforms to this schema:

```markdown
---
profile_id: buffett
display_name: Buffett-style
status: active                              # active | draft | retired
public_anchor:
  type: academic_paper                      # academic_paper | book | sec_filing
  citation: "Frazzini, A., Kabiller, D., Pedersen, L.H. (2018). Buffett's Alpha. Financial Analysts Journal, 74(4), 35-55."
  doi_or_url: "https://doi.org/10.2469/faj.v74.n4.3"
  retrieved: 2026-04-06
  notes: "Peer-reviewed factor decomposition of Berkshire Hathaway 1976-2017."
direction: bottom_up                        # bottom_up | top_down
asset_class: equity                         # equity | multi_asset
factor_tilts:
  quality: positive_strong
  value: positive_strong
  momentum: negative_slight
  defensive: positive                       # low-beta proxy in BKP 2018
leverage_overlay: 1.6                       # disclosed but not applied per-stock
output_shape: single_stock_verdict          # single_stock_verdict | ranked_basket | trade_ideas | screened_universe
tool_sequence:
  - get_company_info
  - get_peer_snapshot
  - get_financials:summary
  - get_score_analysis:weeks=52
  - explain_methodology               # for any factor used
required_factors_present: [quality, value, momentum, defensive]
owner: cg-quant-team
last_legal_review: PENDING                  # ISO date of last counsel review — informational, does not gate invocation
last_anchor_test: PENDING                   # ISO date of last BRK.B sanity test — gates active status if stale/failed
---

# Buffett-style profile

[Plain-prose narrative: who BKP 2018 is, what factor profile they document,
what the workflow does, what it does NOT capture (no leverage at stock level,
no qualitative moat assessment beyond Quality factor), and how to interpret
output. ~300-500 words.]
```

The `status` field (`active` | `draft` | `retired`) is informational for the registry but does NOT gate invocation — profiles in any status can be invoked, with the disclaimer doing the legal work. The `status` field DOES gate automated anchor-test failure handling: if a quarterly anchor test fails, the profile flips to `retired` and the dispatcher surfaces a strong warning in the output (the skill still runs, the user still gets output, but they see that the rubric failed its last sanity check). The `last_legal_review` and `last_anchor_test` fields are surfaced in every output footer for transparency.

### 2.4 Skill dispatcher pattern

Each `AI-<name>/SKILL.md` is thin: it JIT-loads `_parallax/parallax-conventions.md`, `_parallax/AI-profiles/profile-schema.md`, `_parallax/AI-profiles/output-template.md`, and its own `profiles/<name>.md`. It then executes the `tool_sequence` from the profile spec, formats the output through the template, and emits.

The dispatcher does NOT contain investor-specific logic. All differentiation lives in the profile spec. This means: rebranding, threshold tuning, citation correction, and adding new profiles are all spec edits, not code changes.

---

## 3. Per-profile workflow detail

### 3.1 `parallax-AI-buffett`

**Anchor:** Frazzini, Kabiller, Pedersen, "Buffett's Alpha", *FAJ* 2018.

**Workflow:**
1. Resolve ticker via shared conventions (RIC suffix table).
2. Fire in parallel: `get_company_info`, `get_peer_snapshot`, `get_financials(summary)`, `get_score_analysis(weeks=52)`.
3. Score against profile thresholds: Quality ≥ 7, Value ≥ 6, Momentum ≤ 6 (the "slight negative momentum" tilt), Defensive ≥ 6.
4. For any score in the threshold zone, call `explain_methodology` to provide the factor definition.
5. Render through output template.

**Token cost:** ~4 tokens (1 + 1 + 1 + 1 + 0). Cheaper than `parallax-should-i-buy` (24) by design — no async tools, no `get_assessment`.

**Output shape:** `single_stock_verdict`. Four-row scorecard (one per factor) plus pass/partial/fail summary plus disclosure footer. No "buy/sell" language; the verdict is "matches BKP 2018 profile / partially matches / does not match."

**Worked example output:**
```
Buffett-style profile applied to AAPL.O
Source: Frazzini, Kabiller, Pedersen (2018), "Buffett's Alpha", FAJ 74(4):35-55.

Factor profile (per BKP 2018): +Quality, +Value, −Momentum, +Defensive
                               (leverage overlay ~1.6x at portfolio level — not applied per-stock)

| Factor    | Profile target | AAPL.O score | 52-wk trend | Match |
|-----------|----------------|--------------|-------------|-------|
| Quality   | High (≥7)      | 8.4          | ↑ stable    | YES   |
| Value     | High (≥6)      | 5.2          | ↓           | NO    |
| Momentum  | Low (≤6)       | 7.1          | ↑           | NO    |
| Defensive | High (≥6)      | 6.8          | → stable    | YES   |

Profile fit: 2 of 4 factor criteria met. AAPL.O does not match the BKP-2018
characterization of Berkshire's historical exposures, primarily on value and
momentum.

Methodology footer + non-advice disclaimer (see §6.2).
```

### 3.2 `parallax-AI-soros`

**Anchor:** Soros, *The Alchemy of Finance* (1987); Drobny, *Inside the House of Money* (2006). Soros's own published book is the primary source — most defensible non-Buffett profile precisely because the investor wrote down his own approach.

**Two modes: basket (primary) and single-ticker (inferred exposure).**

**Basket / screening mode (no ticker or multi-ticker input):**
1. `list_macro_countries` to confirm coverage.
2. `macro_analyst(component=tactical)` for top 3-5 covered markets in parallel.
3. `get_telemetry` for cross-market regime divergence signals.
4. Identify regime breaks / reflexivity setups: macro stress + price action divergence.
5. For top 1-2 regimes, call `build_stock_universe` with a thematic query derived from the regime (e.g., "energy exporters benefiting from regime X").
6. For top 3-5 names per universe, call `get_peer_snapshot` to filter for momentum + macro sensitivity.
7. Render as ranked trade-idea list with regime thesis.

**Single-ticker mode (when invoked with one ticker, e.g., `/parallax-AI-soros AAPL.O`):**
1. Run the same macro workflow: `list_macro_countries` → `macro_analyst` × top markets → `get_telemetry`.
2. `get_company_info` for the ticker to retrieve its sector and industry classification.
3. `build_stock_universe` for themes surfaced by the current regime analysis (as above) — the "industry-exposure channel."
4. **Check the ticker against TWO independent exposure channels:**
   - **(a) Industry-exposure channel:** does the ticker appear in any surfaced theme's `build_stock_universe` output (either directly, or via its sector/industry classification)?
   - **(b) Telemetry basket theme channel:** does the ticker fall into any of the basket themes surfaced by `get_telemetry` regime signals (e.g., "growth-over-value rotation," "defensive quality," "dollar regime beneficiaries")?
5. Map the combined result to a verdict:
   - **`match`** — ticker is flagged by BOTH channels (industry-exposure AND a telemetry basket theme)
   - **`partial_match`** — ticker is flagged by ONE of the two channels
   - **`no_match`** — ticker is flagged by NEITHER channel
6. Render with regime thesis paragraph + per-channel explanation ("industry exposure: <detail>, telemetry basket: <detail>") + combined verdict.

This is explicitly a *partial signal* on single tickers: the Soros profile is fundamentally top-down, so single-ticker mode answers "does the current regime analysis and telemetry signal agree that this stock is in a themed area?" — not "does this stock individually match a bottom-up quality/value profile?" The dual-channel check (industry AND telemetry) is what distinguishes a genuine thematic exposure from incidental sector membership. The output makes this scoping explicit so users don't over-interpret.

**Token cost:**
- Basket/screening mode: ~25-35 tokens (5 macro × 5 + telemetry 1 + universe 5 + 5 snapshots × 1 = 36)
- Single-ticker mode: ~25-30 tokens (same macro + telemetry + universe; one `get_company_info` + 1-2 `get_peer_snapshot` for exposed names)

**Output shapes:**
- Basket/screening mode: `trade_ideas` — regime thesis paragraph, ranked idea list with rationale per idea. Multi-asset is signaled by including currency/rate context per regime, not by trading FX directly (Parallax is equity-centric).
- Single-ticker mode: `inferred_exposure_verdict` — regime thesis paragraph, then ticker-to-theme mapping + match/partial/no-match verdict.

**Why this is the most defensible non-Buffett profile:** Reflexivity is Soros's *own published framework*. He wrote a book about it. Citing the book and applying its methodology to Parallax data is reporting on a public source, not impersonation. The output never says "Soros would buy X" — it says "A reflexivity-style top-down lens applied to today's macro signals identifies regime Y; under that regime, the framework typically targets industry Z, and <ticker> is/isn't exposed to industry Z."

### 3.3 `parallax-AI-greenblatt`

**Anchor:** Greenblatt, *The Little Book That Beats the Market* (2006). Greenblatt published his exact formula. Academic replications by Gray & Carlisle (2012) provide secondary support.

**Workflow:**
1. `build_stock_universe` with a broad equity universe filter.
2. For each candidate, fetch `get_financials(ratios)` to compute ROC and earnings yield.
3. Rank by combined score (Greenblatt's exact methodology).
4. Top decile = the basket.
5. Render as `ranked_basket` output.

**Token cost:** depends on universe size. ~5-15 tokens for a small thematic universe; the output template caps at top 20-30 names.

**Why defensible:** Greenblatt published the formula explicitly. Implementing it exactly is reporting on a public methodology. Cite the book, show the formula, show the factor pulls, show the ranking. Zero discretion.

### 3.4 `parallax-AI-klarman`

**Anchor:** Klarman, *Margin of Safety* (1991). Out of print but publicly available via libraries; widely cited in academic value-investing literature.

**Workflow:**
1. Resolve ticker.
2. Parallel: `get_company_info`, `get_financials(balance_sheet, periods=4)`, `get_financials(cash_flow, periods=4)`, `get_peer_snapshot`.
3. Compute margin-of-safety checks: net cash position, debt/equity, FCF stability, valuation discount to peer median.
4. Render single-stock verdict with explicit "margin of safety: present / partial / absent" headline.
5. Output may include "no position warranted; cash is a valid stance" — Klarman's distinctive output mode.

**Token cost:** ~5 tokens.

**Output shape:** `single_stock_verdict` with the special-situation framing. Distinctive from Buffett-style because the threshold logic is balance-sheet-first (can it survive?) rather than factor-loading-first (is it the right shape?).

### 3.5 `parallax-AI-consensus` (meta-skill)

**Purpose:** Cross-profile agreement is the high-conviction signal. This skill exists because no single profile is reliable in isolation, but agreement across structurally different profiles is informative.

**Workflow:**
1. Accept a ticker or short basket — capped at **5 tickers per call** to control token cost.
2. For each installed AI profile, run its `tool_sequence` against the ticker (single-ticker mode) or basket (screening mode). All v1 profiles are applicable in both modes — Soros runs its single-ticker inferred-exposure mode on single-ticker input.
3. Collect each profile's verdict as a structured tag: `match` / `partial_match` / `no_match`. A profile only returns `skipped` if the tool sequence actually fails (e.g., Parallax outage, unrecognized ticker, cross-validation failure). Successful runs always return a match tag.
4. **Collect factor-level agreement detail:** for every matching profile, record which specific factors or criteria drove the match (e.g., Buffett matched on Quality + Defensive; Greenblatt matched on ROC + earnings yield). This is surfaced in the output — see §3.5.1.
5. **Super-majority threshold and minimum applicable count** (configurable in `_parallax/AI-profiles/consensus-config.md`):
   - Default super-majority threshold: **75%** of applicable profiles return `match`
   - Default minimum applicable count: **3** profiles (consensus is meaningless with fewer)
   - Rounding rule: **ceiling** — required matches = `ceil(threshold × applicable_count)`
   - Worked: 4 applicable → need 3 matches (75% of 4 = 3.0). 3 applicable → need 3 matches (75% of 3 = 2.25 → ceil 3, effectively unanimous). 2 applicable → fails minimum applicable check; consensus signal returns `INSUFFICIENT_PROFILES`.
6. Render the consensus matrix, the factor-level agreement summary, and the super-majority verdict.

With Soros running single-ticker inferred-exposure mode, v1 single-ticker consensus queries see 4 applicable profiles and super-majority = 3 of 4. Basket/screening mode also sees 4 applicable profiles.

#### 3.5.1 Factor-level agreement surfacing

When two or more profiles return `match` or `partial_match`, the consensus output includes a "shared factor signal" section listing the factors or criteria flagged by multiple profiles. This is the highest-value signal in the output — it tells the user not just that the profiles agreed, but *on what dimension*.

Example: "3 of 4 matching profiles flagged Quality as strong (Buffett, Greenblatt, Klarman). All 3 matching profiles noted low debt / strong balance sheet. Value was flagged by 2 of 4 (Greenblatt, Klarman). Momentum was NOT flagged by any matching profile — this stock is not a momentum trade under any of the cited frameworks."

This is pedagogy by construction: the user learns which factor dimensions the cited academic/biographical sources consider decisive, and sees cross-source convergence on the dimensions where it exists.

**Output shape (single-ticker example):**
```
Parallax AI Investor Profiles — Consensus matrix for AAPL.O

| Profile               | Verdict       | Driving factors/criteria                  |
|-----------------------|---------------|-------------------------------------------|
| AI-buffett            | partial_match | Quality ✓, Defensive ✓, Value ✗, Mom ✗    |
| AI-greenblatt         | match         | ROC top decile, earnings yield top decile |
| AI-klarman            | no_match      | No margin of safety at current valuation  |
| AI-soros              | partial_match | In theme: "AI infrastructure / mega-cap"  |

Applicable profiles: 4 (minimum for consensus: 3)
Matches: 1 full match + 2 partial matches = 1 of 4 full (25%)
Super-majority threshold: 75% → required matches = ceil(0.75 × 4) = 3
Consensus signal: NO — 1 full match falls short of required 3

Shared factor signal (across matching + partially-matching profiles):
  - Quality: flagged by 2 of 3 (Buffett, Greenblatt)
  - ROC / profitability: flagged by 2 of 3 (Greenblatt, Buffett via Quality)
  - Value: flagged by 1 of 3 (Greenblatt)
  - Momentum: NOT flagged by any profile
  - Balance sheet / margin of safety: flagged by 0 of 3 (Klarman explicitly no)
  - Macro theme exposure: flagged by 1 of 3 (Soros)

Interpretation: profiles converge on profitability/Quality but diverge on
valuation and margin of safety. No profile found a momentum case.

Methodology + disclaimer footer.
```

**Why this matters:** The consensus matrix is the marketing hook — "stocks where Parallax AI Investor Profiles agree today" — but the factor-level agreement section is where retail users actually learn. It gives them a framework for building their own views: they see which factor dimensions the cited sources consider decisive, where the sources converge, and where they diverge. Parallax's own house view emerges from this same data, so the consensus output naturally complements the broader Parallax product without duplicating or exposing proprietary endpoints.

---

## 4. Shared output template

Defined in `_parallax/AI-profiles/output-template.md`. Every profile output MUST include:

1. **Header:** `<Profile display_name> applied to <ticker>`
2. **Citation block:** Full academic citation with DOI/URL.
3. **Factor profile statement:** What loadings the source documents (verbatim from spec).
4. **Data table:** Factor / target / actual / trend / match.
5. **Verdict:** match / partial_match / no_match. **Never** uses words like "buy", "sell", "recommend", "would buy", "endorses".
6. **Methodology footer:** "Workflow derived from <citation>. Last anchor-tested <date>. Last legal review <date>."
7. **Standard disclaimer:** *"This output is an AI-inferred interpretation of [Investor]'s approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is **not financial advice**, not personalized, not endorsed by [Investor] or their representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. **Please consult a qualified financial advisor before making investment decisions.**"*

The disclaimer language is **the same across every profile** so it can be reviewed once by counsel and not re-litigated per profile. The key phrases — "AI-inferred," "solely from publicly available information," "not financial advice," and "consult a qualified financial advisor" — are load-bearing and cannot be removed or softened in any profile's output.

---

## 5. Naming and copy conventions

| Where | Allowed | Forbidden |
|---|---|---|
| Skill name | `parallax-AI-buffett` | `parallax-buffett`, `parallax-buffett-2026`, `buffett-bot` |
| Display name | "Buffett-style" | "Buffett's pick", "What Buffett would buy", "Buffett says" |
| Verdict language | "matches profile", "partial match", "does not match" | "buy", "sell", "recommend", "Buffett rates this" |
| First/third person | Always third person about the investor | First person quoting or paraphrasing the investor |
| Citation | Mandatory in every output | (cannot be omitted) |

The `AI-` infix in the skill name is the visible, non-removable signal that this is an AI-generated interpretation. It is part of the legal defense; it is not a stylistic choice and cannot be dropped for marketing.

---

## 6. Risks and mitigations

### 6.1 Right-of-publicity / false endorsement (legal — out of band, no invocation gate)

**Risk:** Using a living investor's name on financial content can be construed as false endorsement under NY Civil Rights §50-51, similar statutes in other US states, and Singapore passing-off doctrine.

**Mitigations baked into design:**
- "AI-" prefix in every public-facing handle — clearly flags every output as AI-inferred, not authored or endorsed by the named investor
- "-style" suffix in every output ("Buffett-style", never "Buffett says")
- Mandatory citation of a public source on every output — the inference is tethered to a specific published document the investor cannot credibly disavow
- No first-person impersonation anywhere in the output
- Standard disclaimer (see §4) that explicitly states: "AI-inferred," "solely from publicly available information," "not financial advice," "not endorsed by [Investor]," "consult a qualified financial advisor"
- Cited source must be the investor's own publication OR a peer-reviewed paper — not interview clips, tweets, or third-party speculation

**Legal review is continuous, not a gate.** Per user direction, profiles are *not* gated on a legal review before invocation. The disclaimer and naming conventions do the legal work at runtime; counsel review is an ongoing quality process that may surface improvements (e.g., tightened disclaimer wording, additional mitigations) but does not block the skills from running. The spec's `last_legal_review` field is retained as an informational audit trail (so users and counsel can see when a profile was last reviewed) but its value does not affect whether the skill is invokable.

The rationale: a gate-based model creates a false sense of binary safety ("signed off → safe forever"), whereas a disclaimer-based model acknowledges that the mitigation IS the disclaimer + naming + citation, and that these mitigations are present in every output regardless of when counsel last looked.

### 6.2 MAS FAA / SEC IA Act / FINRA 2210 — personalized advice line

**Risk:** A skill that ingests personal data and outputs "you should buy X" crosses into the regulated personalized-advice category in multiple jurisdictions.

**Mitigations:**
- Public version takes only a ticker — no user portfolio, no risk tolerance, no holdings, no personalization
- Output is identical for any user querying the same ticker on the same day
- No buy/sell language in output
- Disclaimer explicitly states "not personalized advice"
- Consensus meta-skill takes a ticker (or short basket) — never a user portfolio in the public version

The institutional version (Claude Code skills used by CG fund managers) can take portfolio context, but those are not public-facing and are subject to different disclosure requirements via the existing institutional workflow.

### 6.3 Anchor drift

**Risk:** A profile's cited paper says "Buffett's Alpha is X factor combination," but Parallax's factor scores are not exactly the same construct as Compustat-derived factors used in the paper. Over time, Parallax's factor methodology may evolve away from the paper's definitions.

**Mitigations:**
- Quarterly anchor test: run each profile against the namesake's known holdings (BRK.B for Buffett, Greenblatt's published Magic Formula picks for Greenblatt, etc.) and check that the profile produces sensible output. If the profile says BRK.B is a `no_match` for Buffett-style, something is broken.
- Anchor test results logged in `last_anchor_test` field of the spec.
- If anchor test fails, profile flips to `status: draft` automatically (manual flip in v1; CI-automated in v2).
- `explain_methodology` is called inside the workflow so the user sees what Parallax means by "quality" and can compare to what BKP 2018 means.

### 6.4 The wrong-company-mapping bug

**Risk:** Parallax conventions §2 documents that scoring tools occasionally return data for a different company than intended, especially for numeric tickers (.HK, .T, .TW, .KS). At scale, "Buffett-style profile applied to WRONG_COMPANY" is a brand-damaging output.

**Mitigations:**
- All profile dispatchers MUST apply the §2 cross-validation procedure from `parallax-conventions.md` (cross-check scoring tool name field against `get_company_info` name field) **before** rendering.
- On mismatch, the dispatcher refuses to render and surfaces a clear error: "Symbol cross-validation failed for <ticker>. Cannot render profile."
- This check lives in the dispatcher's pre-render step (codified in `_parallax/AI-profiles/profile-schema.md` as a required workflow step), not in the output template — the output template never receives an unverified payload.

### 6.5 Persona sprawl

**Risk:** Once Buffett ships, requests for Munger, Lynch, Druckenmiller, Burry, Wood, Ackman, Dalio, Marks, Howard, etc. arrive within weeks. Each new profile multiplies legal surface, anchor-test burden, and the chance of confident nonsense.

**Mitigations:**
- The schema is the gate. No public anchor → no profile. "I read about him in a Bloomberg article" is not an anchor; a peer-reviewed paper, the investor's own published book, or a long-form SEC filing is.
- The README in `_parallax/AI-profiles/` lists in-scope and out-of-scope profiles with reasons. Every cut decision is documented to prevent re-litigation.
- v1 ships 4 profiles + 1 meta. v2 candidates: Munger (anchor: *Poor Charlie's Almanack* 2005, plus academic work on quality investing), Lynch (anchor: *One Up on Wall Street* 1989, GARP framework). Both have public anchors. Druckenmiller and Burry remain out until a public anchor exists.

### 6.6 Output fatigue / "everything is partial match"

**Risk:** With strict thresholds, most stocks produce `partial_match` and the consensus matrix is mostly meaningless. Users tune out.

**Mitigations:**
- Anchor test catches this: if the profile's namesake's own holdings come back as `partial_match` instead of `match`, thresholds are wrong.
- Partial match categories are graded: 1/4, 2/4, 3/4 — not all "partial."
- Consensus skill surfaces the unanimity score numerically (33%, 75%, 100%), not just the binary super-majority verdict.

---

## 7. MAS Project MindForge mapping

MAS Project MindForge Phase 1 (concluded November 2025) defines seven GenAI risk dimensions for financial services. Mapping:

| # | Dimension | Design treatment |
|---|---|---|
| 1 | Accountability and Governance | Profile specs are versioned files with mandatory `owner`, `last_legal_review`, `last_anchor_test`, and `status` fields. Every change goes through git review. Profile cannot ship without these fields populated. CG quant team owns specs; CG counsel owns legal review. |
| 2 | Monitoring and Stability | Output is deterministic (no LLM in the rendering loop, no temperature drift). Quarterly anchor test against namesake holdings. Quarterly check that cited paper is not retracted. Drift > threshold → profile flips to `status: draft`. |
| 3 | Transparency and Explainability | Every output shows: citation, factor loadings used, actual factor scores pulled, threshold tests, match decision, methodology footer. `explain_methodology` is called in-workflow for any factor used so users see Parallax's definition next to the cited source's definition. |
| 4 | Fairness and Bias | No user profiling, no personalization, identical output for identical ticker query. Each profile's narrative explicitly publishes what it CANNOT see (e.g., "Buffett-style profile cannot evaluate growth-stage no-dividend companies; Soros-style cannot catch bottom-up stories") so absence is not confused with negative signal. |
| 5 | Legal and Regulatory | "AI-" prefix + "-style" suffix + mandatory citation + standard disclaimer language (AI-inferred, public-information-only, not financial advice, consult a qualified advisor — see §4) + no buy/sell language + no portfolio ingestion in public version. Legal review is continuous (not a gate) — the disclaimer and naming do the legal work at runtime; counsel review is an ongoing quality process that may tighten wording but does not block invocation. |
| 6 | Ethics and Impact | Pedagogy-first framing — output teaches the WHY of factor exposures, not just the WHAT. Right-of-correction policy: if a named investor or estate requests changes to characterization, honored within 5 business days. Policy publicly disclosed on the product page. |
| 7 | Cyber and Data Security | Existing Parallax MCP security baseline (RLS, rate limiting, CORS allowlist, ticker-symbol input sanitization). Profiles do not store user inputs. |
| + | Proportionality | Risk class: medium-high (public-facing + financial domain + named third parties). Governance proportional to risk: legal sign-off + monitoring + versioning + correction policy, but not full FI-grade controls. |

**Verification still required (out-of-band):** The verbatim section text in MindForge's *Operationalisation Handbook* (released Jan 2026) and the parallel *MAS Guidelines on AI Risk Management* (consultation Nov 2025) should be cross-checked by CG counsel against this mapping. WebFetch could not render the Handbook PDF in this design session; counsel should pull it directly and confirm disclaimer language and governance artifact templates match the handbook's expected forms.

---

## 8. Implementation plan (sketch — full plan in writing-plans phase)

The implementation plan will be written in the writing-plans phase. Sketch:

1. **Scaffold shared core** — create `_parallax/AI-profiles/` directory with `README.md`, `profile-schema.md`, `output-template.md`, and `consensus-config.md`. No skill files yet.
2. **Build `AI-buffett` end-to-end first** as the reference implementation. This is the proof that the schema and template work and that the dispatcher pattern is sustainable.
3. **Anchor-test `AI-buffett`** against BRK.B, KO, AXP, AAPL.O. If BRK.B doesn't return `match` or strong `partial_match`, the rubric is wrong — fix before proceeding.
4. **Port `AI-greenblatt`** as the second profile — if it takes more than ~1 hour given the working Buffett scaffold, the schema is wrong and needs revision.
5. **Add `AI-klarman`** — third profile, balance-sheet-flavored, validates that the schema handles non-factor-driven workflows.
6. **Add `AI-soros`** — fourth profile, top-down, multi-tool. Validates that the schema handles multi-step tool sequences and `trade_ideas` output shape. Most distinct from the others; if it doesn't fit the schema, the schema needs revision (not the profile).
7. **Build `AI-consensus`** meta-skill. Test with all 4 profiles installed.
8. **Documentation pass** — README, scope boundary list, schema reference.
9. **Hand to counsel for legal review** (out-of-band) before any profile flips from `status: draft` to `status: active`.

Per CLAUDE.md "Programmatic verification, not LLM eyeballing": each step has an executable success criterion (e.g., `assert anchor_test_BRK_B == "match"`, not "review the output").

---

## 9. Open questions — RESOLVED

All five questions were answered by the user during spec review and locked into the design.

1. **Soros single-ticker mode → Option B.** Soros runs the full macro+telemetry workflow on single-ticker input and reports whether the ticker is exposed to current regime themes via two independent channels: industry-exposure (`build_stock_universe` theme membership) AND telemetry basket themes (`get_telemetry` regime signals). Dual-channel match = `match`; single-channel = `partial_match`; neither = `no_match`. Soros is therefore applicable in BOTH single-ticker and basket consensus modes. See §3.2 for full workflow.

2. **Consensus skill scope → both modes.** Single ticker or short basket, capped at 5 tickers per call. See §3.5.

3. **Draft-status visibility → no invocation gate.** Profiles are invokable regardless of legal review status. The disclaimer in §4 does the legal work at runtime. Required disclaimer language includes: "not financial advice," "AI-inferred from publicly available information," and "please consult a qualified financial advisor before making investment decisions." See §4, §6.1.

4. **Monitoring cadence → quarterly.** Confirmed — anchor tests and citation-retraction checks run quarterly. Not over-engineered into monthly or real-time. See §6.3.

5. **Factor-level agreement surfacing in consensus output → yes.** The consensus output includes a "shared factor signal" section enumerating which factors/criteria drove agreement across matching profiles, which diverged, and which were not flagged by any profile. This gives users a framework for building their own views — and complements Parallax's own house view without duplicating proprietary endpoints. See §3.5.1.

---

## 10. Out of scope for v1

- **Backtesting profiles as signals.** The spec format makes this possible later via `paper-to-signal` / the trading repo, but no backtests in v1.
- **Persona profiles without public anchors** (Druckenmiller, Burry, Soros's individual trades, Wood, Ackman, Dalio's specific calls). Add when public anchor identified.
- **User portfolio ingestion in public version.** Institutional version (Claude Code skill, not retail MCP) can take portfolio context — that's a separate spec.
- **Internationalization.** English only for v1.
- **Profile customization by end users.** Profiles are versioned, vetted, and immutable from the user's perspective. Custom rubrics are a v2 feature with its own legal review.
- **Real-time monitoring of profile output.** Anchor tests are quarterly batch in v1.

---

## Appendix A — Why workflow-as-primitive (not rubric-as-primitive)

Brainstorming and council initially converged on "rubrics with shared core." User intervention reframed: lenses are characterized by *workflow shape*, not by threshold tuning on a fixed factor table. This is a strictly better framing because:

1. **It actually showcases more Parallax tools.** A pure rubric primitive uses `get_peer_snapshot` and threshold checks. A workflow primitive uses different Parallax tools per profile — Soros uses `macro_analyst` + `get_telemetry` + `build_stock_universe`, which no existing skill chains in this way.
2. **Cross-profile consensus is more meaningful.** When structurally different workflows agree, that's information. When the same workflow with different thresholds agrees, that's tautology.
3. **It's pedagogically richer.** A retail user running Buffett vs Soros learns that bottom-up and top-down are real, different processes — not just different ways to score the same numbers.
4. **Defensibility scales better.** Each profile's defense rests on a *workflow* that is documented in a public source, not on a threshold tuning that we made up. The threshold could be challenged ("why is your Buffett quality cutoff 7 not 6.5?"); the workflow is what the source actually says to do.

---

## Appendix B — Brainstorming and council provenance

This spec was developed via:
1. `superpowers:brainstorming` skill — surfaced the initial scoping question (single skill vs persona family).
2. `/council` skill (Standard scope, MCP domain) — dispatched 5 advisors (Threat Modeler, First Principles, Platform Thinker, End User, Ship-It Engineer) and 1 peer review round. Council was running on the rubric framing when the user reframed mid-deliberation to workflow-as-primitive. The reframe made the council's specific verdict moot but the design considerations the council surfaced are reflected throughout this spec — particularly the legal/right-of-publicity analysis (Threat Modeler), the workflow-not-rubric primitive (First Principles + the user's reframe), the multi-surface platform play (Platform Thinker), the screen-mock + retail-vs-institutional distinction (End User), and the actual feasibility check against existing Parallax tools (Ship-It Engineer).
3. MAS Project MindForge Phase 1 framework mapping based on public sources cited in the brainstorming session.

---

*End of design spec.*
