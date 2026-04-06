# Parallax AI Investor Profiles — Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Prerequisite:** Phases 1 and 2 complete. All four v1 profiles (`parallax-AI-buffett`, `parallax-AI-greenblatt`, `parallax-AI-klarman`, `parallax-AI-soros`) are invokable, anchor-tested, and rendering correctly.

**Goal:** Build the `parallax-AI-consensus` meta-skill that runs all installed profiles in parallel against a ticker (or short basket) and surfaces (a) the per-profile verdict matrix, (b) the super-majority signal per `_parallax/AI-profiles/consensus-config.md`, and (c) the factor-level agreement detail that gives users a framework for building their own views.

Also: update the root-level project README and scope-boundary README to reflect the shipped v1 feature set.

**Architecture:** The consensus meta-skill is structurally different from individual profile dispatchers. Instead of running one profile's workflow, it fans out to N profile dispatchers and aggregates their verdicts. The aggregation logic lives in the meta-skill. Factor-level agreement is computed by parsing each profile's factor-flag output and looking for overlaps.

**Tech Stack:** Same as Phases 1-2. No new dependencies.

**Phase boundary:** Phase 3 is the final v1 phase. At the end of Phase 3, the complete `parallax-AI-*` family is shippable: 4 standalone profile skills + 1 meta-skill + shared core + docs.

**Spec reference:** §3.5 (consensus meta-skill workflow), §3.5.1 (factor-level agreement surfacing), consensus-config.md (created in Phase 1 Task 5).

---

## File Structure for Phase 3

Creating 3 new files and updating 1 existing file.

```
skills/
└── AI-consensus/
    └── SKILL.md                                                (NEW — meta-skill)

docs/
└── superpowers/
    └── plans/
        └── 2026-04-06-...-phase-3-...md                        (this plan)

README.md                                                       (MODIFY — add AI Investor Profiles section)
skills/_parallax/AI-profiles/README.md                          (MODIFY — add launch confirmation + v2 roadmap)
```

---

## Task 1: Scaffold AI-consensus directory

**Files:**
- Create: `skills/AI-consensus/.gitkeep`

- [ ] **Step 1: Create directory**

```bash
mkdir -p skills/AI-consensus
touch skills/AI-consensus/.gitkeep
```

- [ ] **Step 2: Commit**

```bash
git add skills/AI-consensus/.gitkeep
git commit -m "scaffold: AI-consensus meta-skill directory"
```

---

## Task 2: Write the AI-consensus meta-skill dispatcher

**Files:**
- Create: `skills/AI-consensus/SKILL.md`
- Delete: `skills/AI-consensus/.gitkeep`

This is the most structurally different skill in the family. It does NOT run a single profile — it orchestrates multiple profile invocations and aggregates their results.

- [ ] **Step 1: Write the consensus meta-skill**

Create `skills/AI-consensus/SKILL.md` with this exact content:

````markdown
---
name: parallax-AI-consensus
description: "Runs all installed Parallax AI Investor Profiles (Buffett, Greenblatt, Klarman, Soros) against a single ticker or short basket (cap 5). Returns the per-profile verdict matrix, the super-majority consensus signal per consensus-config.md, and a factor-level agreement detail showing which factors/criteria were flagged by multiple profiles. Cross-profile agreement IS the high-conviction signal. Third-person framing throughout, AI-inferred from public information. NOT financial advice."
negative-triggers:
  - Single profile only → use /parallax-AI-<name>
  - Broader macro outlook → use /parallax-macro-outlook
  - Portfolio analysis → use /parallax-morning-brief or /parallax-portfolio-checkup
  - Full due diligence → use /parallax-due-diligence
  - Running backtests → use /backtest
gotchas:
  - JIT-load _parallax/parallax-conventions.md, profile-schema.md, output-template.md, consensus-config.md
  - JIT-load ALL installed profile specs: profiles/buffett.md, profiles/greenblatt.md, profiles/klarman.md, profiles/soros.md
  - Do NOT re-implement profile logic — invoke each profile dispatcher by delegating to its workflow
  - Cap basket input at 5 tickers. For single-ticker queries, all 4 profiles are applicable (Soros runs single-ticker dual-channel mode)
  - Super-majority math uses ceiling rounding per consensus-config.md — do not drift from that spec
  - Partial matches do NOT count toward the super-majority signal, but they DO count toward the factor-level agreement surfacing
  - Factor-level agreement is the highest-value section of the output — do not skip it
  - Disclaimer verbatim; use umbrella phrasing "Parallax AI Investor Profiles framework" rather than any single investor name
---

# Parallax AI Investor Profiles — Consensus Meta-Skill

Runs all installed profiles in parallel against a ticker (or short basket), aggregates the verdicts, computes the super-majority consensus signal, and surfaces factor-level agreement detail.

## Usage

```
/parallax-AI-consensus AAPL.O                         # single ticker — all 4 profiles run
/parallax-AI-consensus BRK.B,KO,AXP                   # basket mode — cap 5 tickers
/parallax-AI-consensus --only buffett,greenblatt AAPL # subset of profiles only (rare; skip Soros/Klarman)
```

## Workflow

### Step 0 — JIT-load dependencies

1. `skills/_parallax/parallax-conventions.md`
2. `skills/_parallax/AI-profiles/profile-schema.md`
3. `skills/_parallax/AI-profiles/output-template.md`
4. `skills/_parallax/AI-profiles/consensus-config.md`
5. ALL installed profile specs under `skills/_parallax/AI-profiles/profiles/`:
   - `profiles/buffett.md`
   - `profiles/greenblatt.md`
   - `profiles/klarman.md`
   - `profiles/soros.md`

Also JIT-load each profile's dispatcher (`skills/AI-<name>/SKILL.md`) for reference on how that profile computes its verdict — the meta-skill reuses the same logic rather than re-implementing.

Call `ToolSearch` with query `"+Parallax"` to load deferred MCP tool schemas before the first Parallax call.

### Step 1 — Parse input

- Single ticker → **single-ticker mode**
- Comma-separated list of 2-5 tickers → **basket mode**
- >5 tickers → reject: "Consensus skill takes at most 5 tickers per call. Please split your request."
- Optional `--only <profile1>,<profile2>` flag restricts which profiles run

### Step 2 — Run all applicable profiles in parallel

For each installed profile, execute its workflow from `skills/AI-<name>/SKILL.md` against the input ticker(s). Profiles run IN PARALLEL where their tool sequences don't share dependencies.

Do NOT sequentialize. The whole point of the consensus meta-skill is that cross-profile execution is independent; sequentializing would multiply latency by N.

Each profile returns:
- `verdict`: one of `match`, `partial_match`, `no_match`, `skipped`
- `verdict_detail`: e.g., "3 of 4 factor criteria met" or "top 15% of peer universe" or "both channels flagged"
- `factor_flags`: a dict of factor/criterion → `FLAGGED` | `NOT_FLAGGED` | `NOT_APPLICABLE`
- `fallback_notes`: any graceful fallback that affected the result

### Step 3 — Cross-validation gate (each profile self-checks, meta-skill aggregates)

Each profile runs its own pre-render cross-validation gate per `profile-schema.md §2 Step 2`. If ANY profile refuses to render due to name mismatch, the meta-skill emits:

```
Warning: Profile <name> refused to render for <ticker> due to cross-validation failure. This profile is marked as `skipped` for this ticker. Proceeding with remaining applicable profiles.
```

The meta-skill continues with whatever profiles did render successfully. If NO profiles render successfully, the meta-skill returns `INSUFFICIENT_PROFILES` and does not compute consensus.

### Step 4 — Compute consensus

Per `consensus-config.md`:
- `A` = count of profiles that returned `match` | `partial_match` | `no_match` (exclude `skipped`)
- `M` = count of profiles that returned `match` (NOT `partial_match`)
- Required matches = `ceil(0.75 × A)` (per config's ceiling rounding rule)
- Minimum applicable floor = 3 (per config)

Consensus signal:
- **`INSUFFICIENT_PROFILES`** if `A < 3`
- **`YES`** if `A ≥ 3` AND `M ≥ required_matches`
- **`NO`** if `A ≥ 3` AND `M < required_matches`

### Step 5 — Compute factor-level agreement

For each factor or criterion that appears in any profile's `factor_flags`, count how many matching or partially-matching profiles flagged it:

- Collect the set of all unique factors/criteria across all profiles' `factor_flags`
- For each factor, count the number of matching+partial-matching profiles where it is `FLAGGED`
- Sort by count descending
- Surface factors flagged by ≥2 matching profiles as "shared signals"
- Surface factors flagged by 1 profile as "single-profile signals"
- Surface factors NOT flagged by any matching profile as "absence signals" (informative — tells user no profile sees this dimension)

### Step 6 — Render consensus output

```
Parallax AI Investor Profiles — Consensus for <ticker>

Profiles run: <N> of <total installed>
<any skipped profiles and why>

## Per-profile verdict matrix

| Profile               | Verdict       | Detail                                    |
|-----------------------|---------------|-------------------------------------------|
| AI-buffett            | <verdict>     | <N of 4 factor criteria met>              |
| AI-greenblatt         | <verdict>     | <top X% of peer universe / no match>      |
| AI-klarman            | <verdict>     | <N of 4 checks passed>                    |
| AI-soros              | <verdict>     | <dual-channel: A=<status> B=<status>>     |

## Super-majority consensus signal

Applicable profiles (A): <count>
Full matches (M):        <count>
Super-majority threshold: 75%
Required matches:        ceil(0.75 × <A>) = <required>
Consensus signal:        YES / NO / INSUFFICIENT_PROFILES

## Shared factor signal (factors/criteria flagged across profiles)

Factors flagged by ≥2 matching profiles:
  - <Factor>: flagged by <N> of <M matching profiles> (<profile names>)
  - <Factor>: flagged by <N> of <M matching profiles> (<profile names>)

Single-profile signals:
  - <Factor>: flagged by 1 profile (<profile name>)
  - <Factor>: flagged by 1 profile (<profile name>)

NOT flagged by any matching profile:
  - <Factor>: no profile currently flags this dimension for this ticker

Interpretation: <2-3 sentence plain-language summary that says where the
profiles converge, where they diverge, and what dimensions are collectively
absent. This is the highest-value section for building a view.>

## Methodology footer

Profiles executed: <list with token costs>
Total token cost: <sum>
Cross-validation gate: PASSED for all rendered profiles
Consensus config: 75% super-majority, minimum 3 applicable profiles, ceiling rounding

---
This output is an AI-inferred synthesis produced by the Parallax AI Investor Profiles framework. Each individual profile is derived solely from publicly available information — peer-reviewed academic sources or the investors' own published books, as cited per profile. It is not financial advice, not personalized, not endorsed by any of the named investors or their representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

**Basket mode output:** Same structure as single-ticker mode, but the per-profile verdict matrix has one row per ticker within each profile, and the super-majority signal is computed per-ticker (not across tickers). The factor-level agreement section is computed per-ticker. Output is organized ticker-by-ticker.

### Step 7 — Emit

## Graceful fallback

- If 3 of 4 profiles run successfully, consensus proceeds with A=3 (effectively requiring unanimity per the ceiling rule)
- If 2 of 4 profiles run successfully, consensus returns `INSUFFICIENT_PROFILES` — do NOT compute a signal from 2 profiles
- If any single profile's tool calls fail after retry, that profile is marked `skipped` (with fallback note) and consensus continues with remaining profiles
- If the input ticker is not resolvable (no exchange suffix match), emit the standard conventions §1 error and exit — do not run any profiles

## Token cost estimate

- Buffett: ~4 tokens
- Greenblatt ticker-check mode: ~10-15 tokens (universe build + ratios for peers)
- Klarman: ~12-15 tokens (balance sheet + cash flow + ratios, 4 periods each)
- Soros single-ticker mode: ~25-30 tokens (macro + telemetry + universe)

**Total per consensus call (single ticker): ~51-64 tokens.** This is the most expensive skill in the family, but the value is the cross-profile agreement signal that no single profile provides.

For basket mode of 5 tickers, multiply by 5 for ticker-specific calls (Buffett, Klarman, Greenblatt ticker-check) but Soros's macro workflow runs ONCE and only the per-ticker exposure check runs per-ticker. Approximate basket-of-5 cost: ~180-220 tokens.

## Why this meta-skill exists

The consensus is the product's value proposition, not just a convenience feature. Individual profiles are interesting but noisy — each one reflects a single investor's framework and may flag a stock for reasons unrelated to the investor's actual behavior today. Cross-profile consensus is informative precisely because the profiles are structurally different: Buffett is factor-tilted, Greenblatt is mechanical, Klarman is balance-sheet, Soros is top-down. When three or four agree, the agreement is unlikely to be coincidental.

The factor-level agreement section is pedagogically load-bearing. It tells users:
- **Where the profiles converge** (the high-conviction shared signal)
- **Where they diverge** (informative tension — the stock is partially in one framework but not another)
- **What dimensions are collectively absent** (the profiles' shared blind spots for this ticker)

This gives users a framework for building their own views using Parallax data, which is the stated product goal.
````

- [ ] **Step 2: Remove placeholder and verify**

```bash
rm skills/AI-consensus/.gitkeep
grep -c '^name: parallax-AI-consensus' skills/AI-consensus/SKILL.md
grep -c 'Super-majority consensus signal' skills/AI-consensus/SKILL.md
grep -c 'Shared factor signal' skills/AI-consensus/SKILL.md
grep -c '### Step [0-7]' skills/AI-consensus/SKILL.md
grep -c 'ceil(0.75' skills/AI-consensus/SKILL.md
grep -c 'not financial advice' skills/AI-consensus/SKILL.md
```

Expected: Each ≥ 1; step count ≥ 8.

- [ ] **Step 3: Commit**

```bash
git add skills/AI-consensus/SKILL.md skills/AI-consensus/.gitkeep
git commit -m "feat: parallax-AI-consensus meta-skill with factor-level agreement surfacing"
```

---

## Task 3: End-to-end consensus test on a known Berkshire holding

**Files:**
- None (test-only task; results inform any bug fixes)

Berkshire's own holdings are the natural first test because Buffett should return `match` by construction.

- [ ] **Step 1: Run consensus on BRK.B**

```
/parallax-AI-consensus BRK.B
```

Expected output structure:
1. Per-profile verdict matrix with 4 rows (one per profile)
2. Super-majority signal with applicable count, match count, threshold, verdict
3. Shared factor signal section with factors flagged by ≥2 profiles
4. Interpretation paragraph
5. Methodology footer with per-profile token costs and total
6. Verbatim umbrella disclaimer

Expected verdicts for BRK.B:
- Buffett: `match` (from Phase 1 anchor test)
- Greenblatt: varies by universe and current market prices
- Klarman: likely `match` or strong `partial_match`
- Soros: varies by current regime themes

The consensus signal may or may not be YES — BRK.B is in the right factor zone but may not currently pass all four structurally different profiles. Either outcome is acceptable; what matters is that the OUTPUT is well-formed.

- [ ] **Step 2: Run consensus on a diverse basket**

```
/parallax-AI-consensus BRK.B,KO,NVDA,XOM,JPM
```

Expected: Five ticker-by-ticker sections, each with per-profile matrix, super-majority signal, and factor-level agreement. The signals should differ across tickers (KO probably passes Buffett but not NVDA; XOM may be Soros-themed depending on current macro).

- [ ] **Step 3: Check for consistency bugs**

Cross-check that the factor-level agreement section and the per-profile matrix are internally consistent. If Buffett returns `match` on Quality + Value + Defensive and Greenblatt returns `match` on top-decile ROC, the shared factor signal should show Quality flagged by both (Quality and ROC overlap conceptually). If the shared signal section shows something different, there's an aggregation bug.

- [ ] **Step 4: Test INSUFFICIENT_PROFILES behavior**

Temporarily force 2 profiles to fail (easiest: invoke with `--only` restricted to 2 profiles):

```
/parallax-AI-consensus --only buffett,klarman BRK.B
```

Expected: Either the consensus returns `INSUFFICIENT_PROFILES` explicitly (because A=2 < minimum_applicable=3) OR the dispatcher rejects the `--only` flag with a message "Consensus requires at least 3 profiles; use individual profile skills for 2-profile comparison." Either behavior is acceptable as long as it doesn't silently compute a 2-profile "consensus."

- [ ] **Step 5: Fix any bugs found and re-test**

If the output is well-formed and consistent, proceed. Otherwise, fix the meta-skill dispatcher and re-run Steps 1-4.

- [ ] **Step 6: Commit any fixes**

```bash
# If fixes were needed:
git add skills/AI-consensus/SKILL.md
git commit -m "fix: consensus meta-skill <specific bug fixed>"
```

---

## Task 4: Update the scope-boundary README with launch confirmation

**Files:**
- Modify: `skills/_parallax/AI-profiles/README.md`

The Phase 1 README lists the 4 profiles in scope. At Phase 3 completion, mark them as launched.

- [ ] **Step 1: Read the current README**

```bash
cat skills/_parallax/AI-profiles/README.md
```

Locate the "In-scope profiles (v1 launch set)" section.

- [ ] **Step 2: Add a launch status column**

Update the table to include a status column. The new table should look like this:

```markdown
## In-scope profiles (v1 launch set)

| Profile | Status | Anchor | Workflow shape |
|---|---|---|---|
| `buffett` | SHIPPED (Phase 1) | Frazzini, Kabiller, Pedersen, "Buffett's Alpha", *Financial Analysts Journal* 2018 | Bottom-up single-stock; +Quality +Value −Momentum +Defensive |
| `soros` | SHIPPED (Phase 2) | Soros, *The Alchemy of Finance* (1987); Drobny, *Inside the House of Money* (2006) | Top-down macro → regime themes → ticker exposure (dual-channel) |
| `greenblatt` | SHIPPED (Phase 2) | Greenblatt, *The Little Book That Beats the Market* (2006); Gray & Carlisle, *Quantitative Value* (2012) | Mechanical screen: ROC + earnings yield → top-decile basket |
| `klarman` | SHIPPED (Phase 2) | Klarman, *Margin of Safety* (1991) | Bottom-up special situations: balance sheet + cash rationality |
| `AI-consensus` | SHIPPED (Phase 3) | — | Meta-skill: runs all profiles in parallel, surfaces super-majority + factor-level agreement |
```

Also add a new section after "In-scope profiles":

```markdown
## v1 shipped feature set

As of 2026-04-06:

- 4 profile dispatchers: `parallax-AI-buffett`, `parallax-AI-soros`, `parallax-AI-greenblatt`, `parallax-AI-klarman`
- 1 meta-skill: `parallax-AI-consensus`
- Shared core: schema, output template, consensus config, scope boundary
- All profiles anchor-tested against their namesakes' known positions or published replications
- All outputs carry the verbatim disclaimer and mandatory citation
- Cross-validation gate enforced on every profile

## v1 token cost summary

| Skill | Typical cost per invocation |
|---|---|
| `parallax-AI-buffett` | ~4 tokens |
| `parallax-AI-greenblatt` (ticker-check) | ~10-15 tokens |
| `parallax-AI-greenblatt` (universe mode) | ~15-30 tokens |
| `parallax-AI-klarman` | ~12-15 tokens |
| `parallax-AI-soros` (single-ticker) | ~25-30 tokens |
| `parallax-AI-soros` (basket mode) | ~30-40 tokens |
| `parallax-AI-consensus` (single ticker) | ~51-64 tokens |
| `parallax-AI-consensus` (basket of 5) | ~180-220 tokens |
```

- [ ] **Step 3: Make the edit**

Use the Edit tool to add the Status column to the existing table and add the two new sections. Do not remove any existing content.

- [ ] **Step 4: Verify**

```bash
grep -c 'SHIPPED' skills/_parallax/AI-profiles/README.md
grep -c '## v1 shipped feature set' skills/_parallax/AI-profiles/README.md
grep -c '## v1 token cost summary' skills/_parallax/AI-profiles/README.md
```

Expected: SHIPPED count ≥ 5; new section counts = 1 each.

- [ ] **Step 5: Commit**

```bash
git add skills/_parallax/AI-profiles/README.md
git commit -m "docs: Phase 3 launch — mark all v1 profiles SHIPPED"
```

---

## Task 5: Update the root project README

**Files:**
- Modify: `README.md` (root of `parallax-workflows` repo)

- [ ] **Step 1: Read the current root README**

```bash
cat README.md
```

(If there is no root README.md, create one per Step 3 below. If there is one, find a good place to add the AI Investor Profiles section.)

- [ ] **Step 2: Verify whether a root README exists**

```bash
ls README.md
```

If it exists, proceed to Step 3a. If not, proceed to Step 3b.

- [ ] **Step 3a: Add an "AI Investor Profiles" section (if README exists)**

Insert a new section into the existing README, after whatever "Skills" or "Features" list already exists, with this content:

```markdown
## Parallax AI Investor Profiles

A family of standalone skills that apply famous investors' workflow shapes (not just rubric thresholds) to current Parallax data, each anchored in published academic or biographical sources.

**Launch set (v1):**

| Command | Workflow | Anchor |
|---|---|---|
| `/parallax-AI-buffett <ticker>` | Bottom-up single-stock; Quality + Value + Defensive factor profile | Frazzini, Kabiller, Pedersen (2018), *FAJ* |
| `/parallax-AI-greenblatt [ticker]` | Magic Formula: ROC + earnings yield → top-decile basket | Greenblatt (2006); Gray & Carlisle (2012) |
| `/parallax-AI-klarman <ticker>` | Balance-sheet-first margin-of-safety checks | Klarman, *Margin of Safety* (1991) |
| `/parallax-AI-soros [ticker]` | Top-down macro → regime themes → dual-channel exposure | Soros, *Alchemy of Finance* (1987); Drobny (2006) |
| `/parallax-AI-consensus <ticker or basket>` | Runs all 4 profiles in parallel; surfaces super-majority + factor-level agreement | Meta-skill |

**Framing and legal posture:**

- All profiles are framed in third person ("Buffett-style," never "Buffett says")
- Each output cites its academic/book source and includes a mandatory non-advice disclaimer
- Output is AI-inferred from publicly available information only — no proprietary data, no `score_total`, no `get_assessment`
- Not financial advice, not personalized, not endorsed by any named investor
- See `skills/_parallax/AI-profiles/README.md` for inclusion criteria, v2 candidates, and the full design rationale
- Design spec: `docs/superpowers/specs/2026-04-06-parallax-AI-investor-profiles-design.md`
```

- [ ] **Step 3b: Create a root README (if none exists)**

Create `README.md` at the repo root with this exact content:

```markdown
# parallax-workflows

Claude Code skills for Parallax equity research. Each skill in `skills/` orchestrates Parallax MCP tools via structured workflows.

## Skill catalog

Existing diagnostic and task workflows:
- `/parallax-should-i-buy` — quick stock evaluation
- `/parallax-deep-dive` — position deep dive
- `/parallax-due-diligence` — full research analyst workflow
- `/parallax-client-review` — RM meeting prep
- `/parallax-portfolio-checkup` — individual investor health check
- `/parallax-morning-brief` — fund manager daily brief
- `/parallax-rebalance` — portfolio rebalancing with macro context
- `/parallax-scenario-analysis` — news-driven portfolio scenario
- `/parallax-thematic-screen` — natural-language thematic stock screen
- `/parallax-portfolio-builder` — thesis-to-portfolio construction
- `/parallax-peer-comparison` — research analyst peer analysis
- `/parallax-earnings-quality` — forensic earnings quality
- `/parallax-halal-screen` — Shariah-compliant screening
- `/parallax-explain-portfolio` — reactive performance attribution
- `/parallax-country-deep-dive` — country/region equity coverage
- `/parallax-macro-outlook` — macro regime + equity implications
- `/parallax-watchlist-monitor` — watchlist scoring
- `/parallax-score-explainer` — methodology explanations

## Parallax AI Investor Profiles

A family of standalone skills that apply famous investors' workflow shapes (not just rubric thresholds) to current Parallax data, each anchored in published academic or biographical sources.

**Launch set (v1):**

| Command | Workflow | Anchor |
|---|---|---|
| `/parallax-AI-buffett <ticker>` | Bottom-up single-stock; Quality + Value + Defensive factor profile | Frazzini, Kabiller, Pedersen (2018), *FAJ* |
| `/parallax-AI-greenblatt [ticker]` | Magic Formula: ROC + earnings yield → top-decile basket | Greenblatt (2006); Gray & Carlisle (2012) |
| `/parallax-AI-klarman <ticker>` | Balance-sheet-first margin-of-safety checks | Klarman, *Margin of Safety* (1991) |
| `/parallax-AI-soros [ticker]` | Top-down macro → regime themes → dual-channel exposure | Soros, *Alchemy of Finance* (1987); Drobny (2006) |
| `/parallax-AI-consensus <ticker or basket>` | Runs all 4 profiles in parallel; surfaces super-majority + factor-level agreement | Meta-skill |

**Framing and legal posture:**

- All profiles are framed in third person ("Buffett-style," never "Buffett says")
- Each output cites its academic/book source and includes a mandatory non-advice disclaimer
- Output is AI-inferred from publicly available information only — no proprietary data, no `score_total`, no `get_assessment`
- Not financial advice, not personalized, not endorsed by any named investor
- See `skills/_parallax/AI-profiles/README.md` for inclusion criteria, v2 candidates, and the full design rationale
- Design spec: `docs/superpowers/specs/2026-04-06-parallax-AI-investor-profiles-design.md`

## Conventions

- Symbols use RIC format (AAPL.O, JPM.N). Most skills auto-resolve plain tickers.
- Independent MCP tool calls fire in parallel per `skills/_parallax/parallax-conventions.md`.
- Cross-validate company names after scoring tool calls (conventions §2).
- Handle tool failures gracefully — mark sections as "unavailable" rather than erroring out.

## Prerequisites

The Parallax MCP server must be connected as `claude_ai_Parallax`. If tools return "not found", the server is not configured.

## Repository layout

```
skills/
├── _parallax/                   # shared conventions, token costs, AI profile core
│   ├── parallax-conventions.md
│   ├── token-costs.md
│   └── AI-profiles/
│       ├── README.md
│       ├── profile-schema.md
│       ├── output-template.md
│       ├── consensus-config.md
│       └── profiles/
├── should-i-buy/                # individual skills ...
├── deep-dive/
├── ...
├── AI-buffett/                  # AI Investor Profile skills
├── AI-greenblatt/
├── AI-klarman/
├── AI-soros/
└── AI-consensus/

docs/superpowers/
├── specs/                       # design specs
└── plans/                       # implementation plans
```
```

- [ ] **Step 4: Verify**

```bash
cat README.md | head -30
grep -c 'Parallax AI Investor Profiles' README.md
grep -c 'parallax-AI-buffett' README.md
grep -c 'parallax-AI-consensus' README.md
```

Expected: README exists, contains the AI section, all 5 commands are listed.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: root README includes AI Investor Profiles family"
```

---

## Task 6: Final cross-profile consistency sweep

**Files:**
- None (read-only validation task; results may drive a cleanup commit)

Walk through all 5 skill files and the 4 profile specs with fresh eyes to catch drift before shipping.

- [ ] **Step 1: Verify all 4 profile specs have real anchor-test dates**

```bash
grep 'last_anchor_test' skills/_parallax/AI-profiles/profiles/*.md
```

Expected: 4 lines, all with dates (none with `PENDING`).

- [ ] **Step 2: Verify all 5 skill files carry the correct disclaimer phrases**

```bash
for f in skills/AI-buffett/SKILL.md skills/AI-greenblatt/SKILL.md skills/AI-klarman/SKILL.md skills/AI-soros/SKILL.md skills/AI-consensus/SKILL.md; do
  echo "=== $f ==="
  grep -c 'not financial advice' "$f"
  grep -c 'consult a qualified financial advisor' "$f"
done
```

Expected: Each skill returns `1` or more for both phrases.

- [ ] **Step 3: Verify no skill uses forbidden first-person impersonation**

```bash
grep -rn 'would buy\|would sell\|rates this\|endorses\|Buffett says\|Soros says\|Greenblatt says\|Klarman says' skills/AI-*/SKILL.md
```

Expected: NO matches. If any appear, fix them — these are forbidden per spec §5.

- [ ] **Step 4: Verify schema-schema alignment**

Ensure every profile spec's `tool_sequence` field references only Parallax tools that exist per `skills/_parallax/token-costs.md`. Spot-check for forbidden tools:

```bash
grep -l 'get_assessment\|get_stock_report\|score_total' skills/_parallax/AI-profiles/profiles/*.md
```

Expected: NO matches. If any profile references these, remove them — spec §1 non-goals forbid them.

- [ ] **Step 5: Verify the root README links to all 5 AI skills**

```bash
for skill in AI-buffett AI-greenblatt AI-klarman AI-soros AI-consensus; do
  grep -c "parallax-$skill" README.md
done
```

Expected: Each returns ≥ 1.

- [ ] **Step 6: Run the full consensus once more as final smoke test**

```
/parallax-AI-consensus BRK.B,JPM.N,XOM.N
```

Walk through the output and confirm:
- [ ] All 4 profile dispatcher blocks rendered
- [ ] Per-profile verdict matrix is populated for all 3 tickers
- [ ] Super-majority signal computed per ticker
- [ ] Shared factor signal section populated per ticker
- [ ] No "buy/sell" language anywhere in the output
- [ ] Verbatim disclaimer at the end
- [ ] Citation block for each profile visible

If ALL of these are true, the v1 feature is shipped. If any are false, fix and re-run.

- [ ] **Step 7: Commit any cleanup from Steps 1-6**

```bash
# Only if cleanup edits were needed:
git add <modified files>
git commit -m "cleanup: final cross-profile consistency sweep"
```

---

## Task 7: Phase 3 complete — full v1 shipped

- [ ] **Step 1: Verify git history is clean**

```bash
git status
git log --oneline -30
```

Expected: Clean working tree; git log shows all Phase 1 / Phase 2 / Phase 3 commits.

- [ ] **Step 2: Final file inventory**

```bash
find skills/_parallax/AI-profiles skills/AI-buffett skills/AI-greenblatt skills/AI-klarman skills/AI-soros skills/AI-consensus -type f -name '*.md' | sort
```

Expected (exact file list):
```
skills/AI-buffett/SKILL.md
skills/AI-consensus/SKILL.md
skills/AI-greenblatt/SKILL.md
skills/AI-klarman/SKILL.md
skills/AI-soros/SKILL.md
skills/_parallax/AI-profiles/README.md
skills/_parallax/AI-profiles/consensus-config.md
skills/_parallax/AI-profiles/output-template.md
skills/_parallax/AI-profiles/profile-schema.md
skills/_parallax/AI-profiles/profiles/buffett.md
skills/_parallax/AI-profiles/profiles/greenblatt.md
skills/_parallax/AI-profiles/profiles/klarman.md
skills/_parallax/AI-profiles/profiles/soros.md
```

13 files total. If the count or names differ, investigate before shipping.

- [ ] **Step 3: Phase 3 handoff summary**

Phase 3 and the full v1 Parallax AI Investor Profiles feature are complete when:

- ✅ `parallax-AI-consensus` meta-skill exists and aggregates all 4 profiles correctly
- ✅ Factor-level agreement section is computed and surfaced in consensus output
- ✅ Super-majority math follows `consensus-config.md` (75% threshold, ceiling rounding, minimum 3 applicable)
- ✅ `INSUFFICIENT_PROFILES` case is handled correctly (does not silently "compute" consensus from 2 profiles)
- ✅ Root README lists all 5 AI skills
- ✅ Scope-boundary README marks all 4 profiles as SHIPPED with v1 token cost summary
- ✅ Final consistency sweep passed (no forbidden first-person language, no forbidden tools, disclaimer verbatim in all skills)
- ✅ End-to-end smoke test on a 3-ticker basket produces well-formed output with all required sections

The v1 Parallax AI Investor Profiles family is now shippable. Users can invoke any of the 4 profile skills individually for a single-investor lens, or the meta-skill for cross-profile consensus and factor-level agreement surfacing.

## Next steps after v1 ship

Not part of this plan, but captured for visibility:

1. **Marketing and documentation.** A proper product page explaining the framework, the legal posture, and the citation chain (every paper and book referenced). This is out of scope for the implementation plan but should happen before external announcement.
2. **Retail MCP wrapping.** The profile workflows are designed to be wrappable into the retail MCP. That wrapping is a separate project.
3. **v2 candidates.** Munger and Lynch profiles are designated v2 candidates in the scope-boundary README. Neither is in this plan; each would require its own spec + plan cycle.
4. **Backtest integration.** Each profile's thresholds and workflow can be converted into a systematic signal and passed to `paper-to-signal` / `backtest` in the trading repo. Out of scope for v1.
5. **Monitoring automation.** Quarterly anchor-test schedule is documented in the spec but is not automated in v1. CI-driven anchor tests would be a v2 enhancement.
