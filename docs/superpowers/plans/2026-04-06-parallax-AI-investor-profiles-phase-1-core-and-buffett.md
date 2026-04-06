# Parallax AI Investor Profiles — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared core under `skills/_parallax/AI-profiles/` and the first reference profile (`AI-buffett`), then anchor-test the Buffett profile against Berkshire Hathaway holdings to prove the rubric works before porting the pattern to other profiles.

**Architecture:** Parallax AI Investor Profiles are Claude Code skills that orchestrate Parallax MCP tools. Each profile lives as a data file (YAML frontmatter + markdown body) under `skills/_parallax/AI-profiles/profiles/<name>.md`. A thin dispatcher at `skills/AI-<name>/SKILL.md` JIT-loads the profile spec, the profile schema, the shared output template, and the shared Parallax conventions, then runs the profile's declared `tool_sequence` and renders output through the template. No executable code — everything is markdown + YAML consumed by Claude Code at invocation time.

**Tech Stack:** Claude Code skills (markdown files with YAML frontmatter), Parallax MCP (`mcp__claude_ai_Parallax__*` tools, deferred — require `ToolSearch` load before first call), JIT-loaded shared conventions at `skills/_parallax/parallax-conventions.md`.

**Phase boundary:** Phase 1 ships the shared core + one working profile. Phases 2 and 3 port additional profiles and add the consensus meta-skill respectively. This phase produces a working, shippable `/parallax-AI-buffett` slash command.

**Spec reference:** `docs/superpowers/specs/2026-04-06-parallax-AI-investor-profiles-design.md`. Sections referenced in this plan: §2 (architecture), §3.1 (Buffett workflow), §4 (output template), §5 (naming/copy conventions), §6 (risks and mitigations).

**"Testing" note for this repo:** `parallax-workflows` has no pytest/jest equivalent. Skills are validated by (a) file-level grep checks on required frontmatter fields and (b) manual invocation in a Claude Code session with an expected-output comparison. Every verification step in this plan is one of those two things. Anchor tests in Task 8 are executed manually by the engineer running the skill in Claude Code and inspecting the output against declared expectations.

---

## File Structure for Phase 1

Creating 7 new files. No existing files modified.

```
skills/
├── _parallax/
│   └── AI-profiles/                                     (NEW directory)
│       ├── README.md                                    (NEW — scope boundary, profile registry, in/out list)
│       ├── profile-schema.md                            (NEW — YAML frontmatter contract, workflow for dispatchers)
│       ├── output-template.md                           (NEW — required output structure, disclaimer, citation format)
│       ├── consensus-config.md                          (NEW — thresholds used by Phase 3 meta-skill; created now so it exists)
│       └── profiles/                                    (NEW directory)
│           └── buffett.md                               (NEW — Buffett profile spec per §3.1)
└── AI-buffett/                                          (NEW directory)
    └── SKILL.md                                         (NEW — Buffett dispatcher, ~100 lines)
```

Every file in Phase 1 is created; nothing is modified. Total LOC: ~800 markdown lines across 7 files.

---

## Task 1: Scaffold directories and commit empty placeholder

**Files:**
- Create: `skills/_parallax/AI-profiles/.gitkeep`
- Create: `skills/_parallax/AI-profiles/profiles/.gitkeep`
- Create: `skills/AI-buffett/.gitkeep`

Directory scaffolding gives a clean commit boundary between "directories exist" and "content is written." Also makes later edits cleaner because the parent directories are already tracked.

- [ ] **Step 1: Create the three new directories with placeholder files**

Run from the repo root:
```bash
mkdir -p skills/_parallax/AI-profiles/profiles skills/AI-buffett
touch skills/_parallax/AI-profiles/.gitkeep
touch skills/_parallax/AI-profiles/profiles/.gitkeep
touch skills/AI-buffett/.gitkeep
```

- [ ] **Step 2: Verify the directories exist**

Run:
```bash
ls -la skills/_parallax/AI-profiles/ skills/_parallax/AI-profiles/profiles/ skills/AI-buffett/
```

Expected: Each directory lists `.gitkeep`.

- [ ] **Step 3: Commit scaffolding**

```bash
git add skills/_parallax/AI-profiles/.gitkeep skills/_parallax/AI-profiles/profiles/.gitkeep skills/AI-buffett/.gitkeep
git commit -m "scaffold: Parallax AI Investor Profiles directory structure"
```

---

## Task 2: Write the scope-boundary README

**Files:**
- Create: `skills/_parallax/AI-profiles/README.md`

This file is the entry point for anyone (human or subagent) opening the `AI-profiles/` directory. It states what profiles are in-scope, what's explicitly out-of-scope, and what the inclusion criteria are. Per spec §6.5, this file is the gate against persona sprawl.

- [ ] **Step 1: Write the README**

Create `skills/_parallax/AI-profiles/README.md` with this exact content:

```markdown
# Parallax AI Investor Profiles

Shared core for the `parallax-AI-*` skill family. Each profile is a markdown spec under `profiles/` that declares a workflow over Parallax MCP tools, anchored to a published academic paper or book, and consumed by a thin dispatcher skill at `skills/AI-<name>/SKILL.md`.

## What a profile is

A profile is **not** a celebrity impersonator. It is a **workflow specification** derived from a public source (academic paper, investor's own book, or equivalent) that applies that source's documented methodology to current Parallax data. The output is always framed in third person ("Buffett-style") and cites the source on every render.

## Inclusion criteria (hard gate)

A profile can ship ONLY if:

1. **Public anchor:** Peer-reviewed academic paper, the investor's own published book, or an equivalently concrete public document. NOT: interview clips, tweets, third-party profiles, or "commonly known style."
2. **Workflow specificity:** The anchor documents a concrete workflow (e.g., factor exposures, screening rules, decision process) that can be mechanically applied to Parallax data.
3. **Parallax tool coverage:** The workflow's data requirements can be satisfied by Parallax's public tools (no `get_assessment`, no `score_total`, no `get_stock_report`).
4. **Defensibility test:** If the named investor saw this profile, could they reasonably object that it misrepresents their approach? If yes, the profile is not ready. If the anchor is the investor's own book, this test is automatically passed.

## In-scope profiles (v1 launch set)

| Profile | Anchor | Workflow shape |
|---|---|---|
| `buffett` | Frazzini, Kabiller, Pedersen, "Buffett's Alpha", *Financial Analysts Journal* 2018 | Bottom-up single-stock; +Quality +Value −Momentum +Defensive |
| `soros` | Soros, *The Alchemy of Finance* (1987); Drobny, *Inside the House of Money* (2006) | Top-down macro → regime themes → ticker exposure (dual-channel) |
| `greenblatt` | Greenblatt, *The Little Book That Beats the Market* (2006); Gray & Carlisle, *Quantitative Value* (2012) | Mechanical screen: ROC + earnings yield → top-decile basket |
| `klarman` | Klarman, *Margin of Safety* (1991) | Bottom-up special situations: balance sheet + cash rationality |

## In-scope v2 candidates (not implemented in v1)

- `munger` — anchor: *Poor Charlie's Almanack* (2005). Workflow: quality-first screen with higher moat threshold than Buffett.
- `lynch` — anchor: *One Up on Wall Street* (1989). Workflow: GARP screen using PEG ratio, sector rotation bias.

## Out of scope (insufficient public anchor)

- `druckenmiller` — no published factor decomposition or workflow document with comparable specificity to Soros's *Alchemy*. Revisit if such a source emerges.
- `burry` — concentrated distressed-value discretionary judgment. SEC filings show holdings but not a replicable workflow.
- `soros_specific_trades` — individual trade calls are not a systematic profile.
- `wood`, `ackman`, `dalio`, `marks`, `howard`, generic "hedge fund manager X" profiles — none meet the public-anchor test at the level of specificity required for mechanical replication.

Re-litigating any of the above requires a new public anchor that meets the inclusion criteria.

## How to add a new profile

1. Identify a public anchor meeting the inclusion criteria above.
2. Create `profiles/<name>.md` conforming to `profile-schema.md`.
3. Run the profile manually against the namesake's known holdings (anchor test). If the namesake's own holdings don't return `match`, the rubric is wrong — fix before proceeding.
4. Create `skills/AI-<name>/SKILL.md` as a thin dispatcher following the pattern in `skills/AI-buffett/SKILL.md`.
5. Commit profile + dispatcher together.
6. Update the "In-scope profiles" table in this README.

## Legal posture

Profiles are not gated on legal review before invocation. The disclaimer language in `output-template.md` does the legal work at runtime: "not financial advice," "AI-inferred from publicly available information," "consult a qualified financial advisor." Every profile output carries this disclaimer. Counsel review is a continuous quality process that may tighten wording but does not block the skills from running. See design spec §6.1 for rationale.

## Related files

- `profile-schema.md` — the YAML frontmatter contract every profile must conform to
- `output-template.md` — the required output structure, disclaimer, and citation format
- `consensus-config.md` — thresholds and applicable-count floor for the `parallax-AI-consensus` meta-skill (Phase 3)
```

- [ ] **Step 2: Verify the file exists and contains the required sections**

Run:
```bash
grep -c '^## ' skills/_parallax/AI-profiles/README.md
```

Expected: `8` (eight H2 sections: "What a profile is", "Inclusion criteria", "In-scope profiles", "In-scope v2 candidates", "Out of scope", "How to add a new profile", "Legal posture", "Related files").

- [ ] **Step 3: Commit**

```bash
git add skills/_parallax/AI-profiles/README.md
git commit -m "feat: Parallax AI Investor Profiles scope-boundary README"
```

---

## Task 3: Write the profile schema contract

**Files:**
- Create: `skills/_parallax/AI-profiles/profile-schema.md`

This file defines the YAML frontmatter contract every profile must conform to AND the workflow steps every dispatcher must execute. Dispatchers JIT-load this file to know what to do; profile specs must pass its schema.

- [ ] **Step 1: Write the schema contract**

Create `skills/_parallax/AI-profiles/profile-schema.md` with this exact content:

```markdown
# Parallax AI Investor Profile — Schema Contract

This file is JIT-loaded by every `skills/AI-<name>/SKILL.md` dispatcher. It defines:
1. The YAML frontmatter contract a profile spec must conform to
2. The dispatcher workflow steps every profile runs at invocation time
3. The pre-render cross-validation check required by spec §6.4

## 1. Profile frontmatter contract

Every `profiles/<name>.md` MUST begin with YAML frontmatter containing the following fields. Profiles missing any required field are considered invalid and the dispatcher MUST refuse to render.

```yaml
---
profile_id: <short-name>                    # REQUIRED. Lowercase, alphanumeric + underscore. Matches filename.
display_name: <Display Name-style>          # REQUIRED. Example: "Buffett-style". Always ends in "-style".
status: active | draft | retired            # REQUIRED. Informational; does not gate invocation (see design spec §6.1).
public_anchor:
  type: academic_paper | book | sec_filing  # REQUIRED.
  citation: "<full citation>"               # REQUIRED. Full academic citation with authors, year, title, journal/publisher.
  doi_or_url: "<DOI or URL>"                # REQUIRED if available; otherwise "N/A — book/out-of-print source".
  retrieved: <YYYY-MM-DD>                   # REQUIRED. Date the anchor was last verified to exist.
  notes: "<one-line note>"                  # REQUIRED. Why this anchor is defensible.
direction: bottom_up | top_down             # REQUIRED.
asset_class: equity | multi_asset           # REQUIRED.
factor_tilts:                               # REQUIRED for factor-driven profiles. Empty dict {} for non-factor profiles.
  <factor>: positive_strong | positive | neutral | negative | negative_strong
leverage_overlay: <float or null>           # REQUIRED. null if not applicable. Disclosed, not applied per-stock.
output_shape: single_stock_verdict | ranked_basket | trade_ideas | inferred_exposure_verdict  # REQUIRED.
tool_sequence:                              # REQUIRED. List of Parallax tools to call, in order. Use `tool:param=value` format for parameters.
  - <tool_name>
  - <tool_name>:<param>=<value>
required_factors_present: [<list>]          # REQUIRED for factor-driven profiles. Empty [] otherwise.
thresholds:                                 # REQUIRED if the profile uses score thresholds. Dict of factor -> comparison.
  <factor>: ">= 7"                          # Example: "quality: '>= 7'"
owner: <team>                               # REQUIRED.
last_legal_review: <YYYY-MM-DD or PENDING>  # REQUIRED. Informational; does not gate invocation.
last_anchor_test: <YYYY-MM-DD or PENDING>   # REQUIRED. Gates auto-flip to retired on failure.
---
```

After the frontmatter, the body of the profile spec contains a 300-500 word prose narrative describing:
- Who the anchor is and what it documents
- What the workflow does
- What the workflow does NOT capture (explicit gaps)
- How to interpret the output

### Optional additional fields

Profiles MAY include additional descriptive frontmatter fields beyond the required set above, e.g.:
- `factor_tilts_notes` — free-text note when `factor_tilts` alone doesn't tell the whole story
- `output_shape_single_ticker` — alternate output shape when the profile supports two modes (used by Soros)
- `tool_sequence_basket` / `tool_sequence_single_ticker` — alternate tool sequences for dual-mode profiles (used by Soros)

Optional fields are ignored by dispatchers unless the dispatcher explicitly consumes them. They exist for human readability and future extensibility. Adding an optional field is a schema-compatible change; removing or renaming a REQUIRED field is not.

## 2. Dispatcher workflow

Every `skills/AI-<name>/SKILL.md` dispatcher runs this exact sequence. The dispatcher is generic — all differentiation lives in the profile spec.

### Step 0: JIT-load dependencies

Before any Parallax tool call in the session:
- JIT-load `skills/_parallax/parallax-conventions.md` (RIC resolution, parallel execution, fallback patterns, HK ambiguity)
- JIT-load `skills/_parallax/AI-profiles/profile-schema.md` (this file)
- JIT-load `skills/_parallax/AI-profiles/output-template.md` (render contract)
- JIT-load `skills/_parallax/AI-profiles/profiles/<profile_id>.md` (the specific profile)

Before the first Parallax tool call, call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas.

### Step 1: Parse input

Accept a ticker (or short basket for profiles whose `output_shape` is `ranked_basket` or `trade_ideas`; capped at 5 tickers per call). Resolve RIC per shared conventions.

### Step 2: Pre-render cross-validation gate (spec §6.4)

After any scoring tool call (`get_peer_snapshot`, `get_score_analysis`, `quick_portfolio_scores`), cross-check the `name` field returned by the scoring tool against the `name` field returned by `get_company_info` for the same symbol. If names diverge, the dispatcher MUST refuse to render and emit exactly this error:

```
Error: Symbol cross-validation failed for <ticker>.
  get_company_info returned: "<name_a>"
  <scoring_tool> returned:   "<name_b>"
Cannot render <display_name> profile — possible wrong-company mapping (see parallax-conventions.md §2).
```

This check is NON-BYPASSABLE. No profile may render output on unverified data.

### Step 3: Execute the profile's tool_sequence

Run the tools declared in the profile's `tool_sequence` frontmatter field. Fire independent calls in parallel per `parallax-conventions.md §3`. Apply graceful fallback patterns per §4.

### Step 4: Apply profile thresholds / logic

For factor-driven profiles (`factor_tilts` non-empty), compare each returned factor score against the profile's `thresholds` and mark pass/fail per factor. For non-factor profiles (e.g., Greenblatt, Klarman, Soros), apply the profile's custom logic as specified in its body narrative.

### Step 5: Compute verdict

Map pass/fail results to a verdict tag:
- `match` — all threshold criteria met (or profile-specific "full fit" criteria)
- `partial_match` — some but not all criteria met; graded by count (e.g., "2 of 4")
- `no_match` — zero criteria met or explicit fail condition triggered
- `skipped` — profile explicitly non-applicable (rare — see Soros for the only v1 case, and even that one runs in both modes per §3.2)

### Step 6: Render through output template

Pass all collected data (profile metadata, factor scores, threshold results, verdict, citation) to the output template at `output-template.md`. The template enforces the header, data table, verdict, methodology footer, and standard disclaimer.

### Step 7: Emit

Output the rendered template content. No additional commentary from the dispatcher.

## 3. Schema validation checklist for new profiles

Before committing a new profile spec:

- [ ] Frontmatter has ALL required fields listed in §1
- [ ] `profile_id` matches the filename (e.g., `buffett.md` has `profile_id: buffett`)
- [ ] `display_name` ends with "-style"
- [ ] `public_anchor.citation` is a full academic/book citation
- [ ] `public_anchor.doi_or_url` is a real URL or "N/A — book/out-of-print source"
- [ ] `tool_sequence` only contains Parallax tool names listed in `skills/_parallax/token-costs.md`
- [ ] `tool_sequence` does NOT contain `get_assessment`, `get_stock_report`, or `score_total`
- [ ] Body narrative is 300-500 words and includes "what this does not capture"
- [ ] `last_anchor_test` will be updated after the anchor test in the PR that introduces this profile
```

- [ ] **Step 2: Verify the schema file is well-formed**

Run:
```bash
grep -c '^## ' skills/_parallax/AI-profiles/profile-schema.md
```

Expected: `3` (three H2 sections: "Profile frontmatter contract", "Dispatcher workflow", "Schema validation checklist for new profiles").

Also verify the validation checklist is present:
```bash
grep -c '^- \[ \]' skills/_parallax/AI-profiles/profile-schema.md
```

Expected: `8` (eight checklist items in §3).

- [ ] **Step 3: Commit**

```bash
git add skills/_parallax/AI-profiles/profile-schema.md
git commit -m "feat: profile schema contract for Parallax AI Investor Profiles"
```

---

## Task 4: Write the shared output template

**Files:**
- Create: `skills/_parallax/AI-profiles/output-template.md`

Centralized output contract. Every profile dispatcher JIT-loads this and renders output through it. The disclaimer language is load-bearing — per spec §4, it cannot be removed or softened by any profile.

- [ ] **Step 1: Write the output template**

Create `skills/_parallax/AI-profiles/output-template.md` with this exact content:

```markdown
# Parallax AI Investor Profile — Output Template

This file is JIT-loaded by every `skills/AI-<name>/SKILL.md` dispatcher. It defines the REQUIRED structure of any profile's output. No profile may deviate from this structure. No profile may remove or soften the disclaimer language.

## Required output structure

Every profile rendering MUST include, in order:

### 1. Header

```
<display_name> profile applied to <ticker>
```

Example: `Buffett-style profile applied to AAPL.O`

### 2. Citation block

```
Source: <citation>
(<doi_or_url>)
```

Full citation from the profile's `public_anchor.citation` frontmatter field. URL on second line if available.

### 3. Profile characterization statement

One sentence stating what the cited source documents. Example:

> Frazzini, Kabiller, Pedersen (2018) decompose Berkshire Hathaway's 1976-2017 returns into factor exposures: strong Quality, strong Value, slight negative Momentum, positive Defensive (low-beta), with ~1.6x leverage overlay at portfolio level.

### 4. Data table (for factor-driven profiles)

Markdown table with columns: Factor | Profile target | Actual score | Trend | Match.

For profiles with non-factor logic (Greenblatt, Klarman, Soros), substitute the relevant data structure (rank table for Greenblatt; balance-sheet checklist for Klarman; theme-exposure table for Soros).

### 5. Verdict

Exactly one of:
- `Profile fit: match` — with count, e.g., "4 of 4 factor criteria met"
- `Profile fit: partial match` — with count, e.g., "2 of 4 factor criteria met"
- `Profile fit: no match` — with explanation

**FORBIDDEN verdict language:** "buy", "sell", "recommend", "would buy", "endorses", "rates", "likes", "hates", any first-person impersonation. See spec §5.

### 6. Methodology footer

```
Workflow derived from: <citation>
Last anchor-tested: <last_anchor_test> | Last legal review: <last_legal_review>
Tool sequence: <tool_sequence from profile frontmatter>
Token cost: <N> tokens
```

### 7. Standard disclaimer (REQUIRED, VERBATIM)

Every profile output MUST end with this exact disclaimer. Substitute `[Investor]` with the named investor (e.g., "Warren Buffett"). No other substitutions are permitted. The phrases "AI-inferred," "solely from publicly available information," "not financial advice," and "consult a qualified financial advisor" are load-bearing and MUST NOT be removed, softened, or replaced:

```
---
This output is an AI-inferred interpretation of [Investor]'s approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by [Investor] or their representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

## Rendering rules

1. **Cross-validation gate first.** Before rendering anything, the dispatcher must have passed the pre-render cross-validation check from `profile-schema.md §2 Step 2`. The output template never receives an unverified payload.
2. **No freelancing.** The dispatcher fills in data; it does not add opinions, extra context, or "helpful clarifications" beyond what the profile spec specifies.
3. **Citation mandatory.** A profile without a valid `public_anchor.citation` cannot render. This is checked at dispatcher load time.
4. **Disclaimer is verbatim.** The dispatcher substitutes `[Investor]` and nothing else. The rest of the disclaimer is copy-pasted verbatim.
5. **Third person only.** Nothing in the output may paraphrase, quote, or speak as the investor. "Buffett-style" is allowed. "Buffett would say" is not.

## Why this template is centralized

Per spec §4 and §6.1: the disclaimer is the legal mitigation. Centralizing it means counsel reviews the language once (not N times per profile) and every profile inherits any future tightening automatically. A profile cannot accidentally drift from the approved language because the profile does not control the template.
```

- [ ] **Step 2: Verify the template file has required sections and the verbatim disclaimer**

Run:
```bash
grep -c '^### ' skills/_parallax/AI-profiles/output-template.md
```

Expected: `7` (seven required output sections).

Verify the disclaimer key phrases are present:
```bash
grep -c 'AI-inferred interpretation' skills/_parallax/AI-profiles/output-template.md
grep -c 'solely from publicly available information' skills/_parallax/AI-profiles/output-template.md
grep -c 'not financial advice' skills/_parallax/AI-profiles/output-template.md
grep -c 'consult a qualified financial advisor' skills/_parallax/AI-profiles/output-template.md
```

Expected: Each `1` or more.

- [ ] **Step 3: Commit**

```bash
git add skills/_parallax/AI-profiles/output-template.md
git commit -m "feat: shared output template with load-bearing disclaimer"
```

---

## Task 5: Write the consensus config (used in Phase 3)

**Files:**
- Create: `skills/_parallax/AI-profiles/consensus-config.md`

This file is technically consumed by the Phase 3 meta-skill, but it's written in Phase 1 so the config lives next to the schema and can be reviewed/adjusted as profiles are added in Phase 2. Writing it now also forces us to think through the consensus math before we have multiple profiles.

- [ ] **Step 1: Write the consensus config**

Create `skills/_parallax/AI-profiles/consensus-config.md` with this exact content:

```markdown
# Parallax AI Investor Profile — Consensus Config

Consumed by `skills/AI-consensus/SKILL.md` (Phase 3). Defines the super-majority threshold and minimum-applicable-count floor for the cross-profile consensus calculation.

## Default configuration

```yaml
super_majority_threshold: 0.75      # 75% of applicable profiles must return match
minimum_applicable_count: 3         # consensus meaningless below this floor
rounding: ceiling                   # required_matches = ceil(threshold * applicable_count)
```

## How the math works

Let `A` = number of applicable profiles (profiles that successfully ran their tool_sequence and returned a verdict of `match`, `partial_match`, or `no_match`; excludes `skipped`).

Let `M` = number of applicable profiles that returned `match` (NOT `partial_match`).

The super-majority signal is `YES` if and only if:
- `A >= minimum_applicable_count` AND
- `M >= ceil(super_majority_threshold * A)`

If `A < minimum_applicable_count`, the signal is `INSUFFICIENT_PROFILES` (not `NO`).

## Worked examples (v1 launch set: 4 profiles)

| Applicable (A) | Matches (M) | required_matches = ceil(0.75 × A) | Signal |
|---|---|---|---|
| 4 | 4 | 3 | YES |
| 4 | 3 | 3 | YES |
| 4 | 2 | 3 | NO |
| 4 | 1 | 3 | NO |
| 3 | 3 | 3 | YES (effectively unanimous for 3-profile case) |
| 3 | 2 | 3 | NO |
| 2 | 2 | 3 | INSUFFICIENT_PROFILES |
| 1 | 1 | 3 | INSUFFICIENT_PROFILES |

## Why these defaults

- **75% super-majority** — High enough to be informative (random-chance consensus is ~25% with 4 independent binary verdicts), low enough to survive one profile disagreeing in a structurally different way.
- **Minimum 3 applicable** — With only 2 profiles returning verdicts, "consensus" is just agreement between 2 sources, which is not informative. 3 is the lowest count where structural diversity can meaningfully be observed.
- **Ceiling rounding** — Rounds UP the required matches. This makes the threshold strictly conservative: 75% of 3 = 2.25 rounds to 3 (unanimity), not 2. Prevents the threshold from silently weakening when the applicable count is small.

## Partial matches

`partial_match` verdicts are NOT counted toward `M`. Only full `match` verdicts count. Partial matches are surfaced in the consensus output matrix but do not contribute to the super-majority signal.

This is intentional: if a stock is "partially Buffett-like and partially Klarman-like," that's not the same signal as "fully matches both Buffett and Klarman."

## Factor-level agreement surfacing

Separately from the super-majority math, the meta-skill surfaces a "shared factor signal" section listing factors/criteria that were flagged by multiple profiles (match OR partial_match). See design spec §3.5.1. The shared factor signal is informative regardless of whether the super-majority threshold is met.

## Tuning notes

Do NOT tune these defaults without rerunning all anchor tests across all profiles. If the threshold changes, the meaning of "consensus signal: YES" changes with it.

If future experience shows the threshold is too strict (nothing ever hits YES) or too loose (everything hits YES), the tuning conversation should start with: "What's the base rate of YES across a sample of 50 large-cap stocks over the last quarter?" Target ~10-20% of stocks hitting the signal. If it's 0% or 80%, the threshold is wrong.
```

- [ ] **Step 2: Verify the config file parses and contains the math**

Run:
```bash
grep -c 'super_majority_threshold: 0.75' skills/_parallax/AI-profiles/consensus-config.md
grep -c 'minimum_applicable_count: 3' skills/_parallax/AI-profiles/consensus-config.md
grep -c '^| 4 | 3 | 3 | YES |' skills/_parallax/AI-profiles/consensus-config.md
```

Expected: Each `1`.

- [ ] **Step 3: Commit**

```bash
git add skills/_parallax/AI-profiles/consensus-config.md
git commit -m "feat: consensus config for Phase 3 meta-skill"
```

---

## Task 6: Write the Buffett profile spec

**Files:**
- Create: `skills/_parallax/AI-profiles/profiles/buffett.md`
- Delete: `skills/_parallax/AI-profiles/profiles/.gitkeep`

The reference profile. Conforms to `profile-schema.md`, grounded in BKP 2018, ready to be consumed by the dispatcher in Task 7. Thresholds here are initial guesses; Task 8 (anchor test) will tune them.

- [ ] **Step 1: Write the Buffett profile spec**

Create `skills/_parallax/AI-profiles/profiles/buffett.md` with this exact content:

```markdown
---
profile_id: buffett
display_name: Buffett-style
status: active
public_anchor:
  type: academic_paper
  citation: "Frazzini, A., Kabiller, D., Pedersen, L. H. (2018). Buffett's Alpha. Financial Analysts Journal, 74(4), 35-55."
  doi_or_url: "https://doi.org/10.2469/faj.v74.n4.3"
  retrieved: 2026-04-06
  notes: "Peer-reviewed factor decomposition of Berkshire Hathaway's 1976-2017 returns. Documents +Quality, +Value, −Momentum (slight), +Defensive (low-beta) factor loadings with ~1.6x leverage overlay."
direction: bottom_up
asset_class: equity
factor_tilts:
  quality: positive_strong
  value: positive_strong
  momentum: negative
  defensive: positive
leverage_overlay: 1.6
output_shape: single_stock_verdict
tool_sequence:
  - get_company_info
  - get_peer_snapshot
  - get_financials:statement=summary
  - get_score_analysis:weeks=52
  - explain_methodology
required_factors_present: [quality, value, momentum, defensive]
thresholds:
  quality: ">= 7"
  value: ">= 6"
  momentum: "<= 6"
  defensive: ">= 6"
owner: cg-quant-team
last_legal_review: PENDING
last_anchor_test: PENDING
---

# Buffett-style profile

## What the anchor documents

Frazzini, Kabiller, and Pedersen's 2018 *Financial Analysts Journal* paper "Buffett's Alpha" is the canonical peer-reviewed decomposition of Berkshire Hathaway's historical returns. Using 1976-2017 data, the authors show that Berkshire's abnormal returns are largely explained by four factor exposures: strong Quality (per their Quality Minus Junk factor), strong Value (HML), slight negative Momentum, and strong Defensive (low-beta, per Betting Against Beta). On top of these exposures, Berkshire runs approximately 1.6x leverage via insurance float. After controlling for these factors and the leverage overlay, Berkshire's alpha is significantly reduced — meaning Buffett's outperformance can be largely replicated by systematically tilting toward these factors and levering up.

## What this profile does

Applies the BKP 2018 factor profile to a single stock's current Parallax factor scores. For each of the four factors documented in the paper, the profile compares the stock's Parallax score against a threshold representing the "strong" or "slight" tilt the paper describes. The verdict is a count of how many of the four factor criteria are met, rendered as `match` (4 of 4), `partial_match` (1-3 of 4), or `no_match` (0 of 4).

The profile does NOT apply the leverage overlay at the stock level — leverage is a portfolio-construction choice, not a stock attribute. The leverage value is disclosed in the output footer for transparency but does not affect any individual stock's verdict.

## What this profile does NOT capture

- **Qualitative moat assessment beyond the Quality factor.** BKP 2018 uses the Quality Minus Junk factor as a proxy for Buffett's "economic moat" selection. Parallax's Quality sub-score is a close analog but may not fully capture every dimension of moat quality that Buffett discusses in shareholder letters. Users seeking a deeper moat analysis should cross-reference with Parallax's financial-analysis tools.
- **Management quality.** BKP 2018 implicitly attributes some of Buffett's alpha to stock selection skill within the factor framework. The profile does not attempt to replicate selection skill — it only checks factor exposures.
- **Insurance float advantage.** Berkshire's structural access to cheap leverage via insurance float is not replicable at the individual stock level.
- **Buffett's evolving style.** BKP 2018 decomposes returns over a 40-year window. Buffett's approach in the 1970s (cigar-butts) differs from his approach post-1990 (quality compounders). The profile reflects the full-period factor profile, which leans more toward the latter.
- **Current Berkshire-specific holdings.** The profile does not check whether a stock is currently held by Berkshire. 13F data is available elsewhere but is not part of this profile.

## How to interpret the output

A `match` verdict means the stock currently exhibits the factor profile BKP 2018 documents Berkshire's historical portfolio had. It does NOT mean Buffett would buy the stock today, does NOT mean Berkshire holds the stock, and is NOT investment advice. It is a statement about factor exposures, nothing more.

A `partial_match` is informative — users should look at *which* factors matched and which didn't. A stock that matches Quality and Defensive but not Value is factor-adjacent to Berkshire's profile but lacks the valuation discipline the paper documents.

A `no_match` on Berkshire-like stocks (e.g., KO, AXP) would be a signal that the profile thresholds are wrong or Parallax's factor definitions have drifted from BKP 2018's constructs — trigger an anchor test.

## Thresholds (initial, tuned during anchor test)

- **Quality ≥ 7** — "strong" quality tilt per BKP 2018
- **Value ≥ 6** — "strong" value tilt (slightly lower threshold than Quality because Buffett's valuation discipline varies by era)
- **Momentum ≤ 6** — "slight negative" momentum tilt (threshold is an inverted "not-too-high" constraint)
- **Defensive ≥ 6** — "strong" low-beta tilt per BKP 2018's BAB loading

These thresholds are initial guesses based on a 0-10 Parallax score scale. Task 8 (anchor test) tunes them by running the profile against known Berkshire core holdings (BRK.B, KO, AXP) and adjusting until those names return `match` or strong `partial_match`.
```

- [ ] **Step 2: Remove the .gitkeep placeholder**

```bash
rm skills/_parallax/AI-profiles/profiles/.gitkeep
```

- [ ] **Step 3: Verify the profile spec has all required frontmatter fields**

Run:
```bash
grep -c '^profile_id: buffett' skills/_parallax/AI-profiles/profiles/buffett.md
grep -c '^display_name: Buffett-style' skills/_parallax/AI-profiles/profiles/buffett.md
grep -c '^status: active' skills/_parallax/AI-profiles/profiles/buffett.md
grep -c 'Frazzini, A., Kabiller, D., Pedersen' skills/_parallax/AI-profiles/profiles/buffett.md
grep -c '^direction: bottom_up' skills/_parallax/AI-profiles/profiles/buffett.md
grep -c '^output_shape: single_stock_verdict' skills/_parallax/AI-profiles/profiles/buffett.md
grep -c '^last_anchor_test: PENDING' skills/_parallax/AI-profiles/profiles/buffett.md
```

Expected: Each `1`.

Verify the narrative has the required sections:
```bash
grep -c '^## What the anchor documents' skills/_parallax/AI-profiles/profiles/buffett.md
grep -c '^## What this profile does' skills/_parallax/AI-profiles/profiles/buffett.md
grep -c '^## What this profile does NOT capture' skills/_parallax/AI-profiles/profiles/buffett.md
grep -c '^## How to interpret the output' skills/_parallax/AI-profiles/profiles/buffett.md
grep -c '^## Thresholds' skills/_parallax/AI-profiles/profiles/buffett.md
```

Expected: Each `1`.

- [ ] **Step 4: Commit**

```bash
git add skills/_parallax/AI-profiles/profiles/buffett.md skills/_parallax/AI-profiles/profiles/.gitkeep
git commit -m "feat: Buffett profile spec grounded in BKP 2018"
```

---

## Task 7: Write the AI-buffett dispatcher SKILL.md

**Files:**
- Create: `skills/AI-buffett/SKILL.md`
- Delete: `skills/AI-buffett/.gitkeep`

The dispatcher skill. Thin — all logic lives in the shared core and the profile spec. This skill file follows the same pattern as existing Parallax skills (`skills/should-i-buy/SKILL.md`, `skills/earnings-quality/SKILL.md`).

- [ ] **Step 1: Write the Buffett dispatcher**

Create `skills/AI-buffett/SKILL.md` with this exact content:

```markdown
---
name: parallax-AI-buffett
description: "Applies the Buffett-style factor profile (per Frazzini-Kabiller-Pedersen 2018, 'Buffett's Alpha', FAJ) to a single stock's current Parallax factor scores. Returns a match/partial/no-match verdict based on Quality, Value, Momentum, and Defensive factor criteria. Third-person framing, academic citation, AI-inferred from public information. NOT financial advice. NOT personalized. Accepts plain tickers or RIC format."
negative-triggers:
  - Portfolio-level analysis → use /parallax-morning-brief or /parallax-portfolio-checkup
  - Full due diligence → use /parallax-due-diligence
  - Quick stock evaluation without a specific investor lens → use /parallax-should-i-buy
  - Peer comparison → use /parallax-peer-comparison
  - Running backtests → use /backtest
  - Other investor profiles → use /parallax-AI-soros, /parallax-AI-greenblatt, /parallax-AI-klarman
  - Cross-profile consensus → use /parallax-AI-consensus
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallbacks, and HK ambiguity protocol
  - JIT-load _parallax/AI-profiles/profile-schema.md for the dispatcher workflow and cross-validation gate
  - JIT-load _parallax/AI-profiles/output-template.md for the required output structure and disclaimer
  - JIT-load _parallax/AI-profiles/profiles/buffett.md for the profile spec (frontmatter + narrative)
  - Cross-validation gate (spec §6.4) is NON-BYPASSABLE — refuse to render on name mismatch
  - Disclaimer language is verbatim — do NOT paraphrase "not financial advice," "AI-inferred," or "consult a qualified financial advisor"
  - NEVER use first-person impersonation of Buffett (no "Buffett would buy," "Buffett likes," etc.)
  - Profile is derived from public academic source only (BKP 2018) — no private data, no get_assessment
---

# Parallax AI Buffett Profile

Applies the Buffett-style factor profile documented in Frazzini, Kabiller, and Pedersen's 2018 *Financial Analysts Journal* paper "Buffett's Alpha" to a single stock's current Parallax factor scores.

## Usage

```
/parallax-AI-buffett AAPL
/parallax-AI-buffett BRK.B
/parallax-AI-buffett 005930.KS
```

Accepts plain tickers (auto-resolved to RIC via `get_company_info`) or RIC format directly.

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. This dispatcher is generic — all differentiation for the Buffett profile lives in `skills/_parallax/AI-profiles/profiles/buffett.md`.

### Step 0 — JIT-load dependencies

Before the first Parallax tool call in the session:

1. Load `skills/_parallax/parallax-conventions.md` — RIC resolution, parallel execution, fallback patterns, HK ambiguity.
2. Load `skills/_parallax/AI-profiles/profile-schema.md` — dispatcher workflow + cross-validation gate.
3. Load `skills/_parallax/AI-profiles/output-template.md` — required output structure and disclaimer.
4. Load `skills/_parallax/AI-profiles/profiles/buffett.md` — Buffett profile spec.

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

### Step 1 — Resolve ticker

Use `get_company_info` with the input ticker. If empty, retry with exchange suffixes per shared conventions. For `.HK`/numeric codes, apply the HK ambiguity cross-check from conventions §2.

### Step 2 — Fire data calls in parallel

Once the RIC is confirmed, call all of the following simultaneously (per conventions §3):

| Tool | Parameters | Purpose |
|---|---|---|
| `get_peer_snapshot` | `symbol` | Factor sub-scores: quality, value, momentum, defensive |
| `get_financials` | `symbol`, `statement="summary"` | Revenue/income narrative for context |
| `get_score_analysis` | `symbol`, `weeks=52` | 52-week factor trend direction |

### Step 3 — Pre-render cross-validation gate (MANDATORY per spec §6.4)

After `get_peer_snapshot` returns, cross-check the `name` field returned by `get_peer_snapshot` against the `name` field returned by `get_company_info` for the same symbol.

**If names diverge:** refuse to render and emit exactly:

```
Error: Symbol cross-validation failed for <ticker>.
  get_company_info returned: "<name_a>"
  get_peer_snapshot returned:   "<name_b>"
Cannot render Buffett-style profile — possible wrong-company mapping (see parallax-conventions.md §2).
```

Do not proceed to Step 4 on mismatch. This check is non-bypassable.

### Step 4 — Apply Buffett thresholds

From the profile spec `buffett.md` frontmatter, the thresholds are:

- Quality ≥ 7
- Value ≥ 6
- Momentum ≤ 6
- Defensive ≥ 6

For each factor, compare the score returned by `get_peer_snapshot` against the threshold. Record pass/fail per factor.

For any factor score in the threshold zone (≥7 or ≤3 — notably strong or weak), call `explain_methodology` for that factor to include the Parallax definition in the output. This is the pedagogy hook from spec §7 row 3.

### Step 5 — Compute verdict

Count passed factors (out of 4):
- **4 of 4 → `match`**
- **1-3 of 4 → `partial_match`** (specify the count, e.g., "2 of 4")
- **0 of 4 → `no_match`**

### Step 6 — Render through output template

Format the output per `skills/_parallax/AI-profiles/output-template.md`. The template requires, in order:

1. Header: `Buffett-style profile applied to <ticker>`
2. Citation block (full BKP 2018 citation + DOI)
3. Profile characterization statement (one sentence from the profile spec body)
4. Data table: Factor | Target | Score | 52-wk trend | Match
5. Verdict: "Profile fit: <match/partial/no> — N of 4 factor criteria met"
6. Methodology footer (workflow derivation, anchor-test date, legal-review date, tool sequence, token cost)
7. Standard disclaimer (VERBATIM — substitute `[Investor]` with `Warren Buffett` and nothing else)

### Step 7 — Emit

Output the rendered template. No additional commentary.

## Output example

```
Buffett-style profile applied to BRK.B

Source: Frazzini, A., Kabiller, D., Pedersen, L. H. (2018). Buffett's Alpha. Financial Analysts Journal, 74(4), 35-55.
(https://doi.org/10.2469/faj.v74.n4.3)

Frazzini, Kabiller, Pedersen (2018) decompose Berkshire Hathaway's 1976-2017 returns into factor exposures: strong Quality, strong Value, slight negative Momentum, positive Defensive (low-beta), with ~1.6x leverage overlay at portfolio level.

| Factor    | Target    | BRK.B score | 52-wk trend | Match |
|-----------|-----------|-------------|-------------|-------|
| Quality   | ≥ 7       | 8.1         | ↑ stable    | YES   |
| Value     | ≥ 6       | 6.8         | → stable    | YES   |
| Momentum  | ≤ 6       | 5.4         | → stable    | YES   |
| Defensive | ≥ 6       | 7.9         | ↑ stable    | YES   |

Profile fit: match — 4 of 4 factor criteria met.

Workflow derived from: Frazzini, Kabiller, Pedersen (2018), "Buffett's Alpha", FAJ 74(4):35-55.
Last anchor-tested: 2026-04-06 | Last legal review: PENDING
Tool sequence: get_company_info, get_peer_snapshot, get_financials(summary), get_score_analysis(52w), explain_methodology
Token cost: 4 tokens

---
This output is an AI-inferred interpretation of Warren Buffett's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by Warren Buffett or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

Note: the 52-week trend column uses arrows (↑ up, ↓ down, → stable). The scores shown are illustrative — actual BRK.B scores will come from live Parallax data.

## Graceful fallback

Apply the graceful fallback patterns from `parallax-conventions.md §4`. If any required tool call fails after retry, mark the relevant section as "Data unavailable" and compute the verdict using available factors only. A verdict computed on <4 factors must be flagged as "partial data — N of M factor criteria available" and CANNOT be rendered as `match` even if all available factors pass. Consumers downstream (e.g., the Phase 3 consensus meta-skill) should treat such outputs as `partial_match` at best.
```

- [ ] **Step 2: Remove the .gitkeep placeholder**

```bash
rm skills/AI-buffett/.gitkeep
```

- [ ] **Step 3: Verify the skill file has required frontmatter and sections**

Run:
```bash
grep -c '^name: parallax-AI-buffett' skills/AI-buffett/SKILL.md
grep -c 'negative-triggers:' skills/AI-buffett/SKILL.md
grep -c 'gotchas:' skills/AI-buffett/SKILL.md
grep -c '^## Usage' skills/AI-buffett/SKILL.md
grep -c '^## Workflow' skills/AI-buffett/SKILL.md
grep -c '^### Step [0-7]' skills/AI-buffett/SKILL.md
grep -c '^## Output example' skills/AI-buffett/SKILL.md
grep -c 'not financial advice' skills/AI-buffett/SKILL.md
grep -c 'consult a qualified financial advisor' skills/AI-buffett/SKILL.md
```

Expected: frontmatter fields = 1 each; sections = 1 each; step headers ≥ 8 (Steps 0-7); disclaimer phrases ≥ 1 each.

- [ ] **Step 4: Commit**

```bash
git add skills/AI-buffett/SKILL.md skills/AI-buffett/.gitkeep
git commit -m "feat: parallax-AI-buffett dispatcher skill"
```

---

## Task 8: Anchor test against Berkshire Hathaway (BRK.B) — the critical go/no-go gate

**Files:**
- Modify: `skills/_parallax/AI-profiles/profiles/buffett.md:123` (update `last_anchor_test` field)

This is the go/no-go gate for Phase 1. Per spec §6.3, if the profile's namesake's own stock does not return `match`, the profile is broken and we do not proceed to Phase 2 without fixing.

**IMPORTANT:** This task requires invoking the skill in a Claude Code session with the Parallax MCP server connected. It cannot be automated in shell. The engineer running this task must:
1. Have a Claude Code session open with `claude_ai_Parallax` MCP server connected
2. Invoke `/parallax-AI-buffett BRK.B` and inspect the output
3. Compare against the expected result below

- [ ] **Step 1: Verify the Parallax MCP server is connected**

In the Claude Code session, check that the `mcp__claude_ai_Parallax__*` tools are visible. If they aren't, the test cannot proceed — fix the MCP server connection first.

- [ ] **Step 2: Invoke the Buffett profile against BRK.B**

In the Claude Code session, run:
```
/parallax-AI-buffett BRK.B
```

Wait for the output.

- [ ] **Step 3: Inspect the output for expected result**

**Expected outcome (go gate):**
- The header reads `Buffett-style profile applied to BRK.B` (not a different company — if it says something other than Berkshire Hathaway, the cross-validation gate should have tripped; if it didn't, that's a bug)
- The data table shows 4 factors: Quality, Value, Momentum, Defensive
- **Quality ≥ 7** (should be YES)
- **Value ≥ 6** (should be YES or within 0.5 of threshold)
- **Momentum ≤ 6** (should be YES — BRK.B is not a momentum stock)
- **Defensive ≥ 6** (should be YES — Berkshire is the archetypal low-beta stock)
- Verdict: `match` (4 of 4) or strong `partial_match` (3 of 4)
- Citation block shows BKP 2018 with DOI
- Methodology footer present
- Disclaimer present verbatim, substituting "Warren Buffett"

**If the verdict is `match` or strong `partial_match`:** The profile works. Proceed to Step 4.

**If the verdict is weak `partial_match` (2 of 4) or `no_match`:** The thresholds are wrong, or Parallax's factor definitions differ from BKP 2018's constructs more than expected. DO NOT proceed to Phase 2. Go to Task 8a (threshold tuning).

- [ ] **Step 4: Run sanity tests on other Berkshire core holdings**

In the same session, run:
```
/parallax-AI-buffett KO
```
```
/parallax-AI-buffett AXP
```

Expected: Both should return `match` or strong `partial_match` (3 of 4). KO (Coca-Cola) and AXP (American Express) are archetypal long-held Berkshire positions; if they don't match the Buffett profile, something is wrong.

- [ ] **Step 5: Run one negative-control test**

Run:
```
/parallax-AI-buffett NVDA
```

Expected: `no_match` or weak `partial_match` (at most 2 of 4). NVIDIA is a high-momentum, high-growth name that should NOT match a historical Buffett profile. If it returns `match` (4 of 4), the thresholds are too loose.

- [ ] **Step 6: Update the profile's `last_anchor_test` field**

Open `skills/_parallax/AI-profiles/profiles/buffett.md` and change:

From:
```yaml
last_anchor_test: PENDING
```

To:
```yaml
last_anchor_test: 2026-04-06
```

(Substitute today's actual date.)

- [ ] **Step 7: Commit the anchor-test completion**

```bash
git add skills/_parallax/AI-profiles/profiles/buffett.md
git commit -m "test: anchor-test Buffett profile against BRK.B, KO, AXP (all match); NVDA as negative control (no match)"
```

---

## Task 8a: Threshold tuning (ONLY if Task 8 anchor test failed)

**Files:**
- Modify: `skills/_parallax/AI-profiles/profiles/buffett.md` (threshold values in frontmatter)

Skip this task if Task 8 passed. Execute only if BRK.B, KO, or AXP failed to return `match` or strong `partial_match`.

- [ ] **Step 1: Collect the actual factor scores**

From the outputs in Task 8, record the actual Parallax scores for each of the 4 factors for BRK.B, KO, and AXP. You have 12 data points.

- [ ] **Step 2: Identify which factor threshold is wrong**

Compare the 12 data points against the current thresholds (Quality ≥ 7, Value ≥ 6, Momentum ≤ 6, Defensive ≥ 6). Identify the factor(s) where multiple Berkshire holdings fail the threshold.

Common failure modes:
- **Parallax Value scores run lower than expected.** BKP 2018 uses HML as the value factor; Parallax may be calibrated differently. If BRK.B, KO, AXP all have Value scores in the 4-6 range, lower the threshold to 5.
- **Parallax Momentum scores run higher than expected.** If all three have Momentum 6-8, raise the upper bound to 7.
- **Parallax Defensive runs lower than expected.** If all three are 5-6, lower the threshold to 5.

DO NOT lower thresholds so aggressively that NVDA starts matching. The negative control must still fail.

- [ ] **Step 3: Update thresholds in the profile spec**

Edit `skills/_parallax/AI-profiles/profiles/buffett.md` frontmatter. Example (if Value threshold needs to drop from 6 to 5):

From:
```yaml
thresholds:
  quality: ">= 7"
  value: ">= 6"
  momentum: "<= 6"
  defensive: ">= 6"
```

To:
```yaml
thresholds:
  quality: ">= 7"
  value: ">= 5"
  momentum: "<= 6"
  defensive: ">= 6"
```

Also update the "Thresholds" section in the body narrative to match the new values, with a one-line explanation of why the original threshold was wrong.

- [ ] **Step 4: Re-run the anchor test**

Go back to Task 8 Step 2. If the second pass still fails, STOP. Do not tune a third time — the problem is likely structural (Parallax factor definitions are too different from BKP 2018), not a threshold tuning issue. Escalate to the spec author.

- [ ] **Step 5: Commit the tuning**

```bash
git add skills/_parallax/AI-profiles/profiles/buffett.md
git commit -m "tune: Buffett profile thresholds after anchor test on Berkshire holdings"
```

---

## Task 9: Phase 1 complete — summary verification

- [ ] **Step 1: Verify all Phase 1 files exist**

Run:
```bash
ls -la skills/_parallax/AI-profiles/
ls -la skills/_parallax/AI-profiles/profiles/
ls -la skills/AI-buffett/
```

Expected: README.md, profile-schema.md, output-template.md, consensus-config.md in `_parallax/AI-profiles/`; buffett.md in `profiles/`; SKILL.md in `AI-buffett/`.

- [ ] **Step 2: Verify no PENDING anchor test**

Run:
```bash
grep 'last_anchor_test: PENDING' skills/_parallax/AI-profiles/profiles/buffett.md
```

Expected: No output (zero matches). If the grep returns a line, Task 8 was skipped — go back and complete it.

- [ ] **Step 3: Verify the git history is clean and the phase is committed**

Run:
```bash
git log --oneline -10
git status
```

Expected: Commits for each task in order; `git status` shows clean working tree.

- [ ] **Step 4: Phase 1 handoff summary**

Phase 1 is complete when all of the following are true:
- ✅ Shared core files exist (`README.md`, `profile-schema.md`, `output-template.md`, `consensus-config.md`)
- ✅ Buffett profile spec is committed and has `last_anchor_test: <real date>`
- ✅ `parallax-AI-buffett` skill dispatcher is committed
- ✅ Anchor test passed on BRK.B, KO, AXP
- ✅ Negative control (NVDA) did NOT pass — confirming thresholds aren't too loose
- ✅ Cross-validation gate behavior verified (any name mismatch refuses render)
- ✅ Output template renders correctly with verbatim disclaimer

After confirming all of the above, Phase 2 (Greenblatt + Klarman + Soros) is ready to start. Proceed to `docs/superpowers/plans/2026-04-06-parallax-AI-investor-profiles-phase-2-greenblatt-klarman-soros.md`.

---

## Appendix — Troubleshooting

### The cross-validation gate keeps tripping

Check the name-normalization rules in `parallax-conventions.md §2`. Some names differ between `get_company_info` and `get_peer_snapshot` by punctuation or suffix (e.g., "Apple Inc." vs "Apple Inc"). The gate should tolerate minor formatting differences but flag substantive mismatches. If the gate is too strict, improve the comparison (e.g., case-insensitive, strip punctuation, normalize whitespace) in the conventions file, not in the dispatcher.

### `get_peer_snapshot` returns no factor scores

Confirm the Parallax MCP server has current data for the ticker. Run `mcp__claude_ai_Parallax__check_api_health` to verify service status. If the service is healthy but the symbol returns empty, apply the graceful fallback: mark the verdict as "Data unavailable — cannot render profile."

### `explain_methodology` times out

This is a free, instant tool per `token-costs.md` — timeout is unusual. Retry once. If it still fails, skip the pedagogy enhancement and render the profile with just the numerical data. Note "Methodology explanation unavailable this session" in the output.

### The anchor test on BRK.B works but KO doesn't match

KO's factor profile may have drifted over time. Check the 52-week trend in the output: if Quality is trending down, KO may be in a temporary degradation. Verify by checking Parallax's raw scores for KO against peer averages; if KO is genuinely below peers on Quality this quarter, the profile correctly returns `partial_match` and that's informative, not a bug.

### I want to add a Munger profile right now

No. Phase 2 is Greenblatt + Klarman + Soros. Munger is a v2 candidate. Do not add it in Phase 1 or Phase 2.
