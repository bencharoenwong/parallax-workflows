# Parallax AI Investor Profiles — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Prerequisite:** Phase 1 complete. The shared core at `skills/_parallax/AI-profiles/` exists, `parallax-AI-buffett` passes its anchor test, and the pattern is proven.

**Goal:** Port three additional profiles — Greenblatt (mechanical screen), Klarman (special situations / balance-sheet-first), Soros (top-down macro / dual-channel single-ticker) — following the Phase 1 pattern. Each profile is tested against its namesake's known picks before commit.

**Architecture:** Each profile = one spec file under `skills/_parallax/AI-profiles/profiles/<name>.md` + one thin dispatcher at `skills/AI-<name>/SKILL.md`. The dispatchers differ only where the profile's workflow shape differs from Buffett's. Greenblatt uses `build_stock_universe` as its primary tool; Klarman is balance-sheet-first using `get_financials` heavily; Soros has TWO modes (basket + single-ticker dual-channel) and is the most structurally distinct profile.

**Tech Stack:** Same as Phase 1 — Claude Code skills, Parallax MCP tools, JIT-loaded shared conventions. No new dependencies.

**Phase boundary:** Phase 2 ships 3 additional profiles. At the end of Phase 2, all 4 v1 profiles are invokable individually. Phase 3 adds the `parallax-AI-consensus` meta-skill that consumes all 4.

**Spec reference:** `docs/superpowers/specs/2026-04-06-parallax-AI-investor-profiles-design.md`. Sections: §3.2 (Soros), §3.3 (Greenblatt), §3.4 (Klarman), §2.3 (profile schema), §4 (output template).

**Order rationale:** Greenblatt first (simplest — mechanical formula), then Klarman (middle — balance-sheet logic but still bottom-up single stock), then Soros (most complex — top-down, dual-mode). If the schema doesn't accommodate Soros's dual-mode case cleanly, fix the schema (and Phase 1's buffett.md if needed), not the profile.

---

## File Structure for Phase 2

Creating 6 new files. No existing files modified (except phase-1 shared core extensions if needed to accommodate Soros's dual mode — flagged as a checkpoint).

```
skills/
├── _parallax/
│   └── AI-profiles/
│       └── profiles/
│           ├── greenblatt.md                       (NEW)
│           ├── klarman.md                          (NEW)
│           └── soros.md                            (NEW)
├── AI-greenblatt/
│   └── SKILL.md                                    (NEW)
├── AI-klarman/
│   └── SKILL.md                                    (NEW)
└── AI-soros/
    └── SKILL.md                                    (NEW)
```

---

## Task 1: Scaffold Phase 2 directories

**Files:**
- Create: `skills/AI-greenblatt/.gitkeep`
- Create: `skills/AI-klarman/.gitkeep`
- Create: `skills/AI-soros/.gitkeep`

- [ ] **Step 1: Create directories**

```bash
mkdir -p skills/AI-greenblatt skills/AI-klarman skills/AI-soros
touch skills/AI-greenblatt/.gitkeep skills/AI-klarman/.gitkeep skills/AI-soros/.gitkeep
```

- [ ] **Step 2: Verify**

```bash
ls skills/AI-greenblatt/ skills/AI-klarman/ skills/AI-soros/
```

Expected: `.gitkeep` in each.

- [ ] **Step 3: Commit**

```bash
git add skills/AI-greenblatt/.gitkeep skills/AI-klarman/.gitkeep skills/AI-soros/.gitkeep
git commit -m "scaffold: Phase 2 skill directories"
```

---

## Task 2: Write the Greenblatt profile spec

**Files:**
- Create: `skills/_parallax/AI-profiles/profiles/greenblatt.md`

Greenblatt's Magic Formula from *The Little Book That Beats the Market* (2006). The formula: rank stocks by ROC (return on capital) and earnings yield, combine the two ranks, take the top decile. Academically replicated by Gray & Carlisle's *Quantitative Value* (2012).

- [ ] **Step 1: Write the Greenblatt profile spec**

Create `skills/_parallax/AI-profiles/profiles/greenblatt.md` with this exact content:

````markdown
---
profile_id: greenblatt
display_name: Greenblatt-style
status: active
public_anchor:
  type: book
  citation: "Greenblatt, J. (2006). The Little Book That Beats the Market. John Wiley & Sons. ISBN 978-0471733065. Secondary: Gray, W., Carlisle, T. (2012). Quantitative Value. John Wiley & Sons."
  doi_or_url: "N/A — book source. Academic replication: Gray & Carlisle 2012."
  retrieved: 2026-04-06
  notes: "Greenblatt's Magic Formula is a mechanical screen: rank by return on capital (ROC) and earnings yield (EY), combine ranks, take top decile. Greenblatt published the exact formula; Gray & Carlisle provide academic replication and extension."
direction: bottom_up
asset_class: equity
factor_tilts: {}
leverage_overlay: null
output_shape: ranked_basket
tool_sequence:
  - build_stock_universe
  - get_financials:statement=ratios
  - get_peer_snapshot
required_factors_present: []
thresholds:
  roc_percentile: ">= 90"
  earnings_yield_percentile: ">= 90"
  combined_rank_percentile: ">= 90"
owner: cg-quant-team
last_legal_review: PENDING
last_anchor_test: PENDING
---

# Greenblatt-style profile

## What the anchor documents

Joel Greenblatt's 2006 book *The Little Book That Beats the Market* documents an exact mechanical screen known as the "Magic Formula." The formula ranks stocks on two dimensions: (1) return on capital (ROC), computed as EBIT divided by net working capital plus net fixed assets, and (2) earnings yield (EY), computed as EBIT divided by enterprise value. Each stock gets a rank on each dimension; the two ranks are summed; stocks are sorted by the combined rank. The top decile (typically top 30-50 names out of a ~1000-stock universe) is the "magic formula portfolio."

Gray & Carlisle's 2012 *Quantitative Value* provides academic replication: they test the formula on US equities 1974-2011 and find it delivers persistent outperformance, with the biggest gains coming from the combination of the two metrics (neither alone is as strong as both together).

## What this profile does

Runs the Magic Formula against a defined equity universe using Parallax's `build_stock_universe` and `get_financials(ratios)` tools. Computes ROC and EY for each candidate, combines ranks, and returns the top decile as the profile's "basket."

Because Greenblatt's formula is explicitly mechanical, this profile has zero discretion. Every decision is codified in the formula. Output is a ranked basket, not a single-stock verdict.

## Two usage modes

1. **Universe mode (default):** `/parallax-AI-greenblatt` with no ticker or a universe description runs the formula on a broad US equity universe and returns the top decile.
2. **Ticker-check mode:** `/parallax-AI-greenblatt AAPL.O` runs the formula on a peer universe and reports whether the specified ticker falls in the top decile (`match`), top quartile (`partial_match`), or below (`no_match`).

Ticker-check mode is the primary mode invoked by the Phase 3 consensus meta-skill, since consensus is single-ticker-focused.

## What this profile does NOT capture

- **Greenblatt's value-investor judgment beyond the formula.** Greenblatt is a discretionary value investor at Gotham Capital; the Magic Formula is explicitly a simplified systematic version for his book's retail audience. The formula is NOT a complete replica of how Greenblatt actually invests.
- **Small-cap and micro-cap effects.** Gray & Carlisle (2012) show the formula's outperformance is stronger in small-caps. This profile runs on whatever universe the user specifies or defaults to (mid-to-large-cap US equities); the small-cap premium is not automatic.
- **Exclusion rules.** Greenblatt's original book excludes financials and utilities due to incompatible capital-structure metrics. This profile DOES exclude those sectors in its default universe build to remain faithful to the source.
- **Holding period.** The formula implies annual rebalancing in Greenblatt's original framing. This profile is stateless — it reports current rankings, not a rebalanced portfolio.

## How to interpret the output

In **universe mode**, the output is a ranked list of the top-decile names with their ROC rank, EY rank, and combined rank. This is what the formula says passes the screen as of today.

In **ticker-check mode**, the verdict is one of:
- `match` — ticker is in the top decile of the peer universe by combined Greenblatt rank
- `partial_match` — ticker is in the top quartile but not the top decile
- `no_match` — ticker is below the top quartile

## Thresholds (tuned during anchor test)

- ROC and EY percentiles are computed within the queried universe, not against absolute values
- Top decile = combined rank in the top 10% of the universe
- These thresholds are the formula itself — they are not tunable
- What CAN be tuned is the universe definition (US equities? US + developed international? market cap cutoff?). Anchor test will establish a sensible default universe.

## Anchor test plan

Greenblatt's Magic Formula is publicly replicated — anchor tests can compare this profile's top decile against:

1. **Gray & Carlisle (2012) published results** — their tests show certain sector/style concentrations. The profile's output should look similar in aggregate.
2. **Current Magic Formula web replications.** Multiple third-party sites publish current Magic Formula rankings; the profile should produce substantially similar top-decile names (exact match is not expected due to different data sources and universes, but large divergence indicates a bug).
3. **Individual ticker spot-checks.** Known value names should cluster toward the top; known high-multiple growth names should cluster toward the bottom.
````

- [ ] **Step 2: Verify frontmatter and narrative**

Run:
```bash
grep -c '^profile_id: greenblatt' skills/_parallax/AI-profiles/profiles/greenblatt.md
grep -c '^display_name: Greenblatt-style' skills/_parallax/AI-profiles/profiles/greenblatt.md
grep -c '^output_shape: ranked_basket' skills/_parallax/AI-profiles/profiles/greenblatt.md
grep -c 'Greenblatt, J. (2006)' skills/_parallax/AI-profiles/profiles/greenblatt.md
grep -c 'Gray, W., Carlisle, T. (2012)' skills/_parallax/AI-profiles/profiles/greenblatt.md
grep -c '^## What the anchor documents' skills/_parallax/AI-profiles/profiles/greenblatt.md
grep -c '^## Two usage modes' skills/_parallax/AI-profiles/profiles/greenblatt.md
```

Expected: Each `1`.

- [ ] **Step 3: Commit**

```bash
git add skills/_parallax/AI-profiles/profiles/greenblatt.md
git commit -m "feat: Greenblatt Magic Formula profile spec"
```

---

## Task 3: Write the AI-greenblatt dispatcher

**Files:**
- Create: `skills/AI-greenblatt/SKILL.md`
- Delete: `skills/AI-greenblatt/.gitkeep`

- [ ] **Step 1: Write the dispatcher**

Create `skills/AI-greenblatt/SKILL.md` with this exact content:

````markdown
---
name: parallax-AI-greenblatt
description: "Applies Joel Greenblatt's Magic Formula (per 'The Little Book That Beats the Market', 2006; academically replicated by Gray & Carlisle 2012) to Parallax data. Two modes: universe mode returns the top-decile ranked basket; ticker-check mode reports whether a single stock falls in the top decile of its peer universe. Third-person framing, book citation, AI-inferred from public information. NOT financial advice. Accepts plain tickers or RIC; no ticker = universe mode."
negative-triggers:
  - Bottom-up factor scoring without the mechanical formula → use /parallax-AI-buffett
  - Balance-sheet-first special situations → use /parallax-AI-klarman
  - Top-down macro analysis → use /parallax-AI-soros
  - Cross-profile consensus → use /parallax-AI-consensus
  - Full due diligence → use /parallax-due-diligence
  - Running backtests → use /backtest
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallback patterns
  - JIT-load _parallax/AI-profiles/profile-schema.md for dispatcher workflow and cross-validation gate
  - JIT-load _parallax/AI-profiles/output-template.md for the required output structure and verbatim disclaimer
  - JIT-load _parallax/AI-profiles/profiles/greenblatt.md for the profile spec
  - Universe mode is the default when no ticker is provided; ticker-check mode activates with a ticker argument
  - build_stock_universe is 5 tokens — budget accordingly
  - Exclude financials and utilities from default universe per Greenblatt's original rule
  - NEVER use first-person impersonation ("Greenblatt would buy"); always third person "Greenblatt-style"
  - Disclaimer language is verbatim — do not soften "not financial advice," "AI-inferred," or "consult a qualified financial advisor"
---

# Parallax AI Greenblatt Profile

Applies Joel Greenblatt's Magic Formula (ROC rank + earnings yield rank, combined, top-decile) to Parallax data.

## Usage

```
/parallax-AI-greenblatt                    # universe mode — default US equity universe
/parallax-AI-greenblatt AAPL               # ticker-check mode — is AAPL in the top decile?
/parallax-AI-greenblatt --universe "emerging market industrials"   # universe mode with custom query
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools.

### Step 0 — JIT-load dependencies

Same as `parallax-AI-buffett` Step 0, but load `profiles/greenblatt.md` instead of `buffett.md`.

### Step 1 — Determine mode

- If input is a single ticker → **ticker-check mode**
- If input is empty or a universe description → **universe mode**
- If input is more than one ticker → reject: "Greenblatt profile takes zero or one ticker. For multi-ticker checks use /parallax-AI-consensus."

### Step 2 — Universe mode workflow

1. Call `build_stock_universe` with the query (default: "US large-cap and mid-cap equities, excluding financials and utilities"). Cost: 5 tokens.
2. For the returned universe (typically 30-100 names), call `get_financials(statement=ratios)` in parallel batches to pull EBIT, invested capital, and EV for each. Cost: 1 token per name.
3. Compute ROC = EBIT / (net working capital + net fixed assets) — use the ratios returned by Parallax where possible; substitute return-on-invested-capital if direct ROC is not available.
4. Compute EY = EBIT / EV.
5. Rank each name on ROC and EY independently. Combine ranks by summing. Sort by combined rank.
6. Take the top 10% as the "magic formula basket."
7. For the top 5 basket members, call `get_peer_snapshot` to surface Parallax factor scores as pedagogy (Cost: 1 token each).

### Step 3 — Ticker-check mode workflow

1. Resolve ticker per shared conventions.
2. Call `get_company_info` to identify the ticker's sector/industry.
3. Call `build_stock_universe` with a peer-universe query based on the ticker's sector (e.g., if AAPL is in "Technology Hardware," query for that peer group).
4. Proceed with Step 2 sub-steps 2-5 on the peer universe.
5. Check where the target ticker ranks in the combined rank distribution.

### Step 4 — Cross-validation gate

For ticker-check mode, after `get_peer_snapshot` on the target ticker, cross-check `name` returned by `get_peer_snapshot` against `name` returned by `get_company_info`. Refuse to render on mismatch per `profile-schema.md §2 Step 2`.

For universe mode, cross-validation is per-name on the top-5 basket members that get `get_peer_snapshot` calls in Step 2 sub-step 7.

### Step 5 — Compute verdict (ticker-check mode)

- **Top 10% of combined rank → `match`**
- **Top 25% but below top 10% → `partial_match`**
- **Below top 25% → `no_match`**

### Step 6 — Render through output template

**Universe mode output:**

```
Greenblatt-style basket (Magic Formula)
Source: Greenblatt, J. (2006). The Little Book That Beats the Market.
Secondary: Gray, W., Carlisle, T. (2012). Quantitative Value.

Universe: <query>
Universe size: <N>

Top decile by combined ROC + EY rank:

| Rank | Ticker  | ROC rank | EY rank | Combined | Sector          |
|------|---------|----------|---------|----------|-----------------|
| 1    | XXX.N   | 2        | 5       | 7        | Consumer Disc.  |
| 2    | YYY.O   | 4        | 3       | 7        | Technology      |
| ...  | ...     | ...      | ...     | ...      | ...             |

Methodology footer (tool sequence, token cost, anchor-test date)

---
[Standard disclaimer — see output-template.md — substituting "Joel Greenblatt"]
```

**Ticker-check mode output:**

```
Greenblatt-style profile applied to <ticker>
Source: [same citation block]

Peer universe: <sector peers>
Universe size: <N>

<Ticker> ranking:
  ROC rank: <R> of <N> (<percentile>th percentile)
  Earnings yield rank: <R> of <N> (<percentile>th percentile)
  Combined rank: <R> of <N> (<percentile>th percentile)

Profile fit: <match/partial/no> — <ticker> is in the [top 10%|top 25%|below top 25%] of the peer universe by Greenblatt combined rank.

Methodology footer + verbatim disclaimer
```

### Step 7 — Emit

## Graceful fallback

If `build_stock_universe` returns fewer than 10 names, the top-decile calculation is unreliable. Expand the universe query once (broader sector, looser constraints) or — if expansion fails — return `INSUFFICIENT_UNIVERSE` and decline to render a verdict. In ticker-check mode, this means the consensus meta-skill (Phase 3) should treat the profile as `skipped` for that ticker.

If `get_financials(ratios)` fails for a subset of universe members, drop those names from the ranking rather than failing the whole call. Note the coverage loss in the methodology footer: "X of Y universe members had financial data available."
````

- [ ] **Step 2: Remove placeholder and verify structure**

```bash
rm skills/AI-greenblatt/.gitkeep
grep -c '^name: parallax-AI-greenblatt' skills/AI-greenblatt/SKILL.md
grep -c 'gotchas:' skills/AI-greenblatt/SKILL.md
grep -c '^### Step [0-7]' skills/AI-greenblatt/SKILL.md
grep -c 'not financial advice' skills/AI-greenblatt/SKILL.md
```

Expected: Each `1` (steps ≥ 7).

- [ ] **Step 3: Commit**

```bash
git add skills/AI-greenblatt/SKILL.md skills/AI-greenblatt/.gitkeep
git commit -m "feat: parallax-AI-greenblatt dispatcher skill"
```

---

## Task 4: Anchor test Greenblatt profile

**Files:**
- Modify: `skills/_parallax/AI-profiles/profiles/greenblatt.md` (update `last_anchor_test`)

Same gate pattern as Phase 1 Task 8. Requires a live Claude Code session with the Parallax MCP server.

- [ ] **Step 1: Run universe mode**

In the Claude Code session:
```
/parallax-AI-greenblatt
```

Expected output: A ranked basket of ~30-50 names sorted by combined Greenblatt rank. The top names should skew toward:
- Mature, profitable companies with modest valuations (high ROC, high EY)
- NOT high-multiple growth names (those have low EY)
- NOT cyclical bottoms with beaten-down earnings (those have low ROC currently)

Cross-reference with a public Magic Formula replication site (there are several free ones). The top names should overlap substantially — not exact match, but the aggregate "looks" similar (ratio-heavy mature-industry names clustering toward the top).

**If the top names are obviously wrong** (e.g., all high-multiple tech, or all distressed financials): the universe query or ROC/EY computation is wrong. Debug in Step 3.

- [ ] **Step 2: Run ticker-check mode**

Pick 3 tickers with known Magic Formula behavior:
1. **A known mature value name** (e.g., `/parallax-AI-greenblatt CSCO.O`) — expect `match` or `partial_match`
2. **A known high-multiple growth name** (e.g., `/parallax-AI-greenblatt NVDA.O`) — expect `no_match`
3. **A known quality compounder** (e.g., `/parallax-AI-greenblatt MSFT.O`) — expect varies; MSFT is historically mid-pack on Magic Formula due to high valuation but high ROC

The precise outcome depends on the peer universe selected and current market prices. What matters: names 1 and 3 should NOT both land in the same bucket as name 2.

- [ ] **Step 3: Debug if needed**

Common failure modes:
- **ROC computation uses the wrong formula.** Parallax's `get_financials(ratios)` may return "return on capital" computed differently from Greenblatt's EBIT/(NWC+NFA). If so, either (a) compute ROC from raw components if Parallax exposes them, or (b) document the substitution in the profile narrative and proceed with Parallax's definition as the closest available proxy.
- **EY computation is off.** EY = EBIT/EV. If Parallax only returns earnings yield as net-income-based, substitute EBIT-based where possible.
- **Universe is too narrow.** If the default US equity universe returns <30 names, the percentile calculations are noisy. Broaden the universe.

Fix the dispatcher or the profile narrative as needed and re-run Steps 1-2.

- [ ] **Step 4: Update the profile's `last_anchor_test` field**

```bash
# Edit the file to change last_anchor_test: PENDING to last_anchor_test: 2026-04-06
```

- [ ] **Step 5: Commit**

```bash
git add skills/_parallax/AI-profiles/profiles/greenblatt.md
git commit -m "test: anchor-test Greenblatt profile; universe + ticker-check modes verified"
```

---

## Task 5: Write the Klarman profile spec

**Files:**
- Create: `skills/_parallax/AI-profiles/profiles/klarman.md`

Klarman's *Margin of Safety* (1991) is balance-sheet-first: survival before returns. The profile's logic centers on net cash position, debt sustainability, FCF stability, and valuation discount — not factor sub-scores.

- [ ] **Step 1: Write the Klarman profile spec**

Create `skills/_parallax/AI-profiles/profiles/klarman.md` with this exact content:

```markdown
---
profile_id: klarman
display_name: Klarman-style
status: active
public_anchor:
  type: book
  citation: "Klarman, S. (1991). Margin of Safety: Risk-Averse Value Investing Strategies for the Thoughtful Investor. HarperBusiness. ISBN 978-0887305108."
  doi_or_url: "N/A — out of print. Widely cited in academic value-investing literature and available through major libraries."
  retrieved: 2026-04-06
  notes: "Klarman's own published book on his investment philosophy. Core thesis: margin of safety (buy well below intrinsic value), balance-sheet strength (can the company survive?), willingness to hold cash when nothing qualifies, and patience. Focus on downside protection over upside maximization."
direction: bottom_up
asset_class: equity
factor_tilts:
  value: positive_strong
  quality: positive
factor_tilts_notes: "Klarman's approach is dominated by valuation discount and balance-sheet quality, not factor loadings per se."
leverage_overlay: null
output_shape: single_stock_verdict
tool_sequence:
  - get_company_info
  - get_peer_snapshot
  - get_financials:statement=balance_sheet,periods=4
  - get_financials:statement=cash_flow,periods=4
  - get_financials:statement=ratios,periods=4
required_factors_present: []
thresholds:
  net_cash_to_market_cap: ">= 0"            # Net cash (cash - debt) positive OR small negative
  debt_to_equity: "<= peer_median"           # Lower leverage than peers
  fcf_positive_periods: ">= 3 of 4"          # FCF positive in 3 of last 4 periods
  pe_vs_peer_median: "<= 0.85"               # Trading at 15%+ discount to peer median P/E
  value_score: ">= 6"                        # Parallax Value sub-score as a backup check
owner: cg-quant-team
last_legal_review: PENDING
last_anchor_test: PENDING
---

# Klarman-style profile

## What the anchor documents

Seth Klarman's 1991 book *Margin of Safety* is his own articulation of a deep-value, risk-averse investment philosophy. The book is out of print (original hardcover prices reach $1000+) but remains widely available through libraries and is heavily cited in academic value-investing literature. Klarman's core principles, as stated in the book:

1. **Margin of safety** — buy at a significant discount to estimated intrinsic value, so that even if your analysis is imperfect, downside is limited
2. **Balance-sheet strength** — can the company survive adverse conditions? This comes before growth or returns
3. **Willingness to hold cash** — when nothing meets the margin-of-safety criteria, hold cash. Do not force trades
4. **Patience** — positions are meant to be held through drawdowns; turnover is expensive
5. **Special situations** — spin-offs, distressed debt, risk arbitrage, and other catalyst-driven value opportunities

## What this profile does

Applies Klarman's balance-sheet-first test to a single stock using four checks:

1. **Net cash position:** cash minus total debt, as a fraction of market cap. Target: positive, or small negative.
2. **Debt to equity vs peers:** the stock's D/E ratio vs its peer group median. Target: at or below median.
3. **FCF stability:** free cash flow positive in at least 3 of the last 4 periods. Target: ≥3 of 4.
4. **Valuation discount:** the stock's P/E (or P/B for financials) vs peer median. Target: ≥15% discount.

A stock passes the Klarman test (verdict `match`) if it meets at least 3 of the 4 checks AND has a Parallax Value sub-score ≥6 as a backup sanity check. Meeting 2 of 4 = `partial_match`. Meeting ≤1 = `no_match`.

## Distinctive output mode: "no position warranted"

Klarman's philosophy explicitly includes "hold cash when nothing qualifies." If the stock meets 0 of the 4 balance-sheet checks AND has low Parallax Value score, the output includes a secondary note: "No position warranted on this ticker per margin-of-safety principles. Cash is a valid stance." This is not available in other profiles — Klarman is the only v1 profile where the framework says "do nothing" is a real answer.

## What this profile does NOT capture

- **Intrinsic value estimation.** Klarman's actual investment process involves detailed intrinsic-value analysis (DCF, asset liquidation value, sum-of-parts). This profile uses peer-relative valuation as a tractable proxy. A true intrinsic-value calculation would require much more data and judgment than Parallax exposes.
- **Special situations.** Klarman heavily utilizes spin-offs, distressed debt, risk arbitrage, and similar catalyst-driven opportunities. This profile is bottom-up valuation-focused and does NOT flag special situations.
- **Qualitative moat and management assessment.** Klarman writes extensively about skepticism of management, accounting games, and industry structure. The profile uses numeric balance-sheet checks as a proxy.
- **Position sizing and portfolio construction.** Klarman runs a concentrated book with position sizes determined by conviction and margin of safety. This profile is per-ticker only.

## How to interpret the output

A `match` verdict means the stock currently passes Klarman's balance-sheet and valuation checks — it's the kind of stock Klarman's framework would flag as eligible for deeper diligence. It does NOT mean Klarman or Baupost holds the stock, and it does NOT mean any external analyst has validated the margin of safety. It means the stock is balance-sheet-healthy and valuation-discounted right now.

A `partial_match` is informative: look at WHICH of the 4 checks passed. A stock that has a strong balance sheet but trades at peer median is balance-sheet-defensible but lacks the discount Klarman's framework requires.

A `no_match` with the "no position warranted" footer is itself useful output — it tells the user explicitly that the Klarman framework would not flag this stock regardless of narrative interest.

## Anchor test plan

Klarman's fund (Baupost) publishes 13F filings quarterly. Known historical Baupost positions (via 13F archives) can be checked against this profile:
- Baupost historical holdings should mostly return `match` or `partial_match`
- High-multiple growth names that were never in Baupost's book should return `no_match`
```

- [ ] **Step 2: Verify**

```bash
grep -c '^profile_id: klarman' skills/_parallax/AI-profiles/profiles/klarman.md
grep -c '^display_name: Klarman-style' skills/_parallax/AI-profiles/profiles/klarman.md
grep -c 'Klarman, S. (1991)' skills/_parallax/AI-profiles/profiles/klarman.md
grep -c 'no position warranted' skills/_parallax/AI-profiles/profiles/klarman.md
grep -c 'margin of safety' skills/_parallax/AI-profiles/profiles/klarman.md
```

Expected: Each ≥ 1.

- [ ] **Step 3: Commit**

```bash
git add skills/_parallax/AI-profiles/profiles/klarman.md
git commit -m "feat: Klarman profile spec — margin-of-safety balance-sheet checks"
```

---

## Task 6: Write the AI-klarman dispatcher

**Files:**
- Create: `skills/AI-klarman/SKILL.md`
- Delete: `skills/AI-klarman/.gitkeep`

- [ ] **Step 1: Write the dispatcher**

Create `skills/AI-klarman/SKILL.md` with this exact content:

````markdown
---
name: parallax-AI-klarman
description: "Applies Seth Klarman's margin-of-safety framework (per 'Margin of Safety', 1991) to a single stock's current financials via Parallax. Checks: net cash position, debt vs peers, FCF stability, valuation discount. Includes a distinctive 'no position warranted; cash is valid' output when nothing qualifies. Third-person framing, book citation, AI-inferred from public information. NOT financial advice."
negative-triggers:
  - Bottom-up factor scoring → use /parallax-AI-buffett
  - Mechanical formula screen → use /parallax-AI-greenblatt
  - Top-down macro analysis → use /parallax-AI-soros
  - Cross-profile consensus → use /parallax-AI-consensus
  - Full due diligence → use /parallax-due-diligence
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallback patterns
  - JIT-load _parallax/AI-profiles/profile-schema.md and output-template.md
  - JIT-load _parallax/AI-profiles/profiles/klarman.md for the profile spec
  - Klarman profile is balance-sheet-first — requires get_financials(balance_sheet) AND get_financials(cash_flow) AND get_financials(ratios), 4 periods each
  - 4 periods × 3 statements = 12 get_financials calls → token cost ~12-15 tokens
  - Compute net cash from balance sheet (cash - total debt), not from ratios summary
  - The "no position warranted" output IS valid output — don't treat it as a failure
  - NEVER use first-person impersonation; always "Klarman-style"
  - Disclaimer verbatim
---

# Parallax AI Klarman Profile

Applies Seth Klarman's margin-of-safety framework to a single stock's current balance sheet, cash flow, and peer-relative valuation.

## Usage

```
/parallax-AI-klarman AAPL.O
/parallax-AI-klarman BRK.B
/parallax-AI-klarman 7203.T
```

## Workflow

### Step 0 — JIT-load dependencies

Same as other AI-* profiles, loading `profiles/klarman.md`.

### Step 1 — Resolve ticker

Per shared conventions.

### Step 2 — Fire data calls in parallel

| Tool | Parameters | Purpose |
|---|---|---|
| `get_company_info` | `symbol` | Sector, market cap, for peer group selection |
| `get_peer_snapshot` | `symbol` | Factor sub-scores (Value is used as backup check) |
| `get_financials` | `symbol`, `statement="balance_sheet"`, `periods=4` | Cash, total debt, equity |
| `get_financials` | `symbol`, `statement="cash_flow"`, `periods=4` | FCF across 4 periods |
| `get_financials` | `symbol`, `statement="ratios"`, `periods=4` | D/E ratio, P/E, P/B, peer medians if Parallax provides them |

### Step 3 — Cross-validation gate

After `get_peer_snapshot` returns, cross-check name against `get_company_info` name. Refuse on mismatch.

### Step 4 — Compute the four Klarman checks

1. **Net cash check:**
   - Net cash = (cash and equivalents) − (total debt)
   - Net cash ratio = net cash / market cap
   - **Pass** if net cash ratio ≥ 0 (positive net cash, no leverage)
   - **Partial** if net cash ratio ≥ −0.2 (small net debt, manageable)
   - **Fail** if net cash ratio < −0.2 (meaningful net debt)

2. **Debt vs peers check:**
   - Debt-to-equity ratio from most recent period
   - Compare against peer median from Parallax's ratios if available; otherwise flag "peer data unavailable — cannot compute"
   - **Pass** if D/E ≤ peer median × 1.1
   - **Fail** otherwise

3. **FCF stability check:**
   - Count the periods (out of 4) where free cash flow was positive
   - **Pass** if ≥ 3 of 4
   - **Partial** if 2 of 4
   - **Fail** if ≤ 1 of 4

4. **Valuation discount check:**
   - P/E ratio vs peer median (or P/B if negative earnings make P/E meaningless)
   - **Pass** if stock P/E ≤ peer median × 0.85 (15%+ discount)
   - **Partial** if stock P/E ≤ peer median × 1.0 (at peer)
   - **Fail** if stock P/E > peer median × 1.0

5. **Backup check: Parallax Value score**
   - This is a sanity check, not a primary criterion
   - If Parallax Value sub-score < 6, flag the output: "⚠️ Parallax Value sub-score suggests valuation may not be attractive even if peer-relative metrics pass"

### Step 5 — Compute verdict

- **Passes ≥ 3 of 4 checks AND Parallax Value ≥ 6 → `match`**
- **Passes 2 of 4 → `partial_match`**
- **Passes 0-1 of 4 → `no_match`**

If the verdict is `no_match` AND Parallax Value < 6, the output includes the distinctive "no position warranted; cash is a valid stance" footer.

### Step 6 — Render through output template

```
Klarman-style profile applied to <ticker>

Source: Klarman, S. (1991). Margin of Safety: Risk-Averse Value Investing Strategies for the Thoughtful Investor.

Klarman's framework prioritizes survival over return: balance-sheet strength, downside protection via valuation discount, and willingness to hold cash when nothing qualifies.

| Check                        | Target                    | Actual              | Result  |
|------------------------------|---------------------------|---------------------|---------|
| Net cash position            | Net cash ≥ 0              | <value>             | PASS/FAIL |
| Debt vs peer median          | D/E ≤ peer median × 1.1   | <value> vs <peer>   | PASS/FAIL |
| FCF stability                | Positive ≥ 3 of 4 periods | <count> of 4        | PASS/FAIL |
| Valuation discount           | P/E ≤ peer median × 0.85  | <value> vs <peer>   | PASS/FAIL |

Parallax Value sub-score (backup check): <score> / 10

Profile fit: <match/partial/no> — <count> of 4 checks passed.

[Optional: "No position warranted on this ticker per margin-of-safety principles. Cash is a valid stance."]

Methodology footer + verbatim disclaimer (substituting "Seth Klarman")
```

### Step 7 — Emit

## Graceful fallback

If balance-sheet data is unavailable for 4 periods, compute the check on whatever is available (minimum 2 periods) and flag the coverage loss. If peer-median data is unavailable, skip the debt-vs-peers check and note "Peer comparison unavailable — check computed on absolute ratios only."
````

- [ ] **Step 2: Remove placeholder and verify**

```bash
rm skills/AI-klarman/.gitkeep
grep -c '^name: parallax-AI-klarman' skills/AI-klarman/SKILL.md
grep -c 'no position warranted' skills/AI-klarman/SKILL.md
grep -c '### Step [0-7]' skills/AI-klarman/SKILL.md
```

Expected: First two = 1, step count ≥ 7.

- [ ] **Step 3: Commit**

```bash
git add skills/AI-klarman/SKILL.md skills/AI-klarman/.gitkeep
git commit -m "feat: parallax-AI-klarman dispatcher skill"
```

---

## Task 7: Anchor test Klarman profile

**Files:**
- Modify: `skills/_parallax/AI-profiles/profiles/klarman.md` (update `last_anchor_test`)

- [ ] **Step 1: Identify 2-3 known historical Baupost holdings**

Baupost's 13F filings are public via SEC EDGAR. Pick 2-3 names that have appeared in Baupost's portfolio historically. Examples from publicly available 13Fs (verify these are still traded and current):
- Equity positions in special situations / deep value names
- Do NOT pick positions that are currently distressed or delisted

- [ ] **Step 2: Run Klarman profile against each**

In the Claude Code session:
```
/parallax-AI-klarman <baupost_historical_pick_1>
/parallax-AI-klarman <baupost_historical_pick_2>
/parallax-AI-klarman <baupost_historical_pick_3>
```

Expected: At least 2 of 3 should return `match` or `partial_match`. A historical Baupost holding that returns `no_match` today is possible (conditions change) but all three failing suggests the profile is too strict.

- [ ] **Step 3: Negative control — run against a high-multiple growth name**

```
/parallax-AI-klarman NVDA.O
```

Expected: `no_match` with the "no position warranted" footer. NVDA has high multiples, negative net cash is plausible, and would not meet Klarman's margin-of-safety test.

- [ ] **Step 4: Sanity control — run against a balance-sheet-rich name**

```
/parallax-AI-klarman BRK.B
```

Expected: Should return `partial_match` at least (Berkshire has strong net cash and low debt but trades near peer multiples due to size). The FCF and balance-sheet checks should pass; the valuation check may be borderline.

- [ ] **Step 5: Tune if needed**

If results are way off, the most common issue is the peer-median lookups. Parallax may or may not expose peer-median ratios directly; if it doesn't, the dispatcher may need to compute them from a separate peer universe call. Consider: is the debt-vs-peers check computable with currently available Parallax data? If not, either skip the check and document the limitation, or add a peer-pull step to the workflow.

- [ ] **Step 6: Update last_anchor_test field and commit**

```bash
# Edit klarman.md: last_anchor_test: PENDING → 2026-04-06
git add skills/_parallax/AI-profiles/profiles/klarman.md
git commit -m "test: anchor-test Klarman profile against historical Baupost holdings"
```

---

## Task 8: Write the Soros profile spec — most structurally distinct

**Files:**
- Create: `skills/_parallax/AI-profiles/profiles/soros.md`

Soros is the most structurally different profile in v1. It has two modes (basket/screening and single-ticker dual-channel), uses `macro_analyst` and `get_telemetry` (which no other profile uses), and its verdict in single-ticker mode depends on theme-exposure mapping. This is the profile that stress-tests whether the schema generalizes.

- [ ] **Step 1: Write the Soros profile spec**

Create `skills/_parallax/AI-profiles/profiles/soros.md` with this exact content:

````markdown
---
profile_id: soros
display_name: Soros-style
status: active
public_anchor:
  type: book
  citation: "Soros, G. (1987). The Alchemy of Finance. Simon & Schuster. ISBN 978-0471445494. Secondary: Drobny, S. (2006). Inside the House of Money: Top Hedge Fund Traders on Profiting in the Global Markets. John Wiley & Sons."
  doi_or_url: "N/A — book sources."
  retrieved: 2026-04-06
  notes: "Soros's own published book articulates his reflexivity framework: macro regime identification, feedback loops between market prices and fundamentals, identification of regime breaks as high-conviction opportunities. Most defensible non-Buffett v1 profile because the investor himself wrote the source."
direction: top_down
asset_class: multi_asset
factor_tilts: {}
factor_tilts_notes: "Soros-style is not characterized by factor loadings. It is characterized by top-down macro regime analysis and thematic exposure."
leverage_overlay: null
output_shape: trade_ideas
output_shape_single_ticker: inferred_exposure_verdict
tool_sequence_basket:
  - list_macro_countries
  - macro_analyst:component=tactical
  - get_telemetry
  - build_stock_universe
  - get_peer_snapshot
tool_sequence_single_ticker:
  - list_macro_countries
  - macro_analyst:component=tactical
  - get_telemetry
  - get_company_info
  - build_stock_universe
required_factors_present: []
thresholds:
  markets_analyzed: "3 to 5"
  themes_surfaced: "1 to 3"
  exposure_channels_for_match: "2 of 2"
owner: cg-quant-team
last_legal_review: PENDING
last_anchor_test: PENDING
---

# Soros-style profile

## What the anchor documents

George Soros's 1987 book *The Alchemy of Finance* is his own articulation of the reflexivity framework: markets don't simply reflect fundamentals; prices and fundamentals influence each other through feedback loops. Regime breaks occur when a dominant market narrative diverges sharply from underlying fundamentals, creating a window where the narrative either collapses or the fundamentals are forced to catch up. Identifying such regime breaks is Soros's core framework.

Steven Drobny's 2006 *Inside the House of Money* provides secondary context: interviews with macro traders including Soros's collaborators describe the top-down workflow — start with a macro thesis about regime change, identify which markets/industries are most exposed to that regime, and concentrate high-conviction positions on the highest-expected-value trades.

## What this profile does

Unlike the other v1 profiles, Soros operates top-down in two distinct modes:

### Basket/screening mode (primary)

Invoked with no ticker or a universe description. The workflow:

1. Enumerate covered macro markets via `list_macro_countries`.
2. Run `macro_analyst(component=tactical)` on 3-5 top markets in parallel to surface regime signals, currency/rate views, and tactical tilts.
3. Pull `get_telemetry` for cross-market regime divergence signals.
4. Identify 1-3 regime themes where macro + telemetry agree on a directional view (e.g., "dollar weakening → emerging market equities," "rate cuts → small-cap industrials," "dollar strengthening → EM risk off").
5. For each theme, call `build_stock_universe` with a thematic query to surface exposed names.
6. For the top 3-5 names per theme, call `get_peer_snapshot` to filter for momentum and macro-sensitivity.
7. Render as a ranked trade-idea list with regime thesis.

### Single-ticker mode (inferred exposure)

Invoked with one ticker. The workflow:

1. Steps 1-5 from basket mode — surface current regime themes.
2. `get_company_info` for the ticker — retrieve sector and industry classification.
3. **Dual-channel exposure check:**
   - **Channel A (industry-exposure):** does the ticker's sector/industry appear in any theme's `build_stock_universe` output? Either directly (ticker is a top candidate in the universe) or indirectly (ticker's industry classification matches a theme's target industry).
   - **Channel B (telemetry basket theme):** does the ticker fall into any of the basket themes surfaced by `get_telemetry` regime signals (e.g., "growth-over-value rotation," "defensive-to-cyclical rotation," "dollar regime beneficiaries")?
4. Map the combined result:
   - **Both channels flagged → `match`**
   - **One channel flagged → `partial_match`**
   - **Neither → `no_match`**
5. Render with regime thesis, per-channel explanation, and combined verdict.

## What this profile does NOT capture

- **Individual trade judgment.** Soros's actual trades involve specific entry/exit timing, position sizing, and stop-loss logic that this profile does not replicate. The profile identifies regime themes and ticker exposure; it does not generate trade execution instructions.
- **Currency and rate positions.** Soros famously trades FX and rates alongside equities. Parallax is equity-centric; this profile cites currency/rate context from `macro_analyst` output but does not recommend FX or rate trades.
- **Leverage and concentration.** Macro traders run concentrated high-conviction positions with significant leverage. This profile is a signal, not a position-sizing recommendation.
- **Reflexivity loop timing.** Soros's "regime break" identification is a judgment call about when a narrative-fundamentals divergence is about to resolve. The profile can surface current tactical signals but cannot predict regime break timing.
- **Single-stock bottom-up analysis.** Single-ticker mode is explicitly a partial signal. Soros does not care about a single stock's factor profile; he cares whether it rides the right macro wave.

## How to interpret the output

**Basket mode output:** A ranked list of trade ideas organized by regime theme. Each idea includes the regime thesis, the theme's directional view, and why the named ticker is exposed. This is the mode closest to what macro traders actually produce.

**Single-ticker mode output:** A dual-channel verdict. The user learns:
1. What regime themes are currently prominent (the macro thesis)
2. Whether the ticker is exposed to those themes via industry classification (channel A)
3. Whether the ticker fits a current telemetry-surfaced basket (channel B)
4. A combined verdict indicating the strength of exposure

A single-ticker `match` means the ticker is independently flagged by BOTH channels — a genuine thematic exposure, not incidental sector membership. A `partial_match` means one channel flagged it but not the other — either the telemetry doesn't see the theme yet, or the industry classification is too broad to qualify.

A `no_match` is informative: the macro regime analysis doesn't see this ticker as thematically exposed today. It's not saying the ticker is bad — it's saying the Soros-style top-down lens doesn't currently have a view on it.

## Anchor test plan

Basket mode is self-consistent and can be spot-checked:
1. Run basket mode. The surfaced regime themes should match current market conditions in a qualitatively plausible way (e.g., if the Fed is cutting rates, themes involving rate-sensitive sectors should surface).
2. Cross-reference the surfaced themes with recent macro commentary from Bloomberg, Reuters, or similar public sources. Exact match is not expected but the THEMES should be recognizable.

Single-ticker mode is harder to anchor-test because it depends on current regime themes. Test by:
1. Pick a ticker clearly in a current theme (e.g., if energy is the theme, pick XOM.N). Single-ticker mode should return `match`.
2. Pick a ticker clearly NOT in any current theme (e.g., a boring consumer staple). Should return `no_match`.
3. Pick a ticker in one but not both channels (harder to find intentionally — let the test surface one and document).
````

- [ ] **Step 2: Verify the profile spec**

```bash
grep -c '^profile_id: soros' skills/_parallax/AI-profiles/profiles/soros.md
grep -c '^direction: top_down' skills/_parallax/AI-profiles/profiles/soros.md
grep -c '^asset_class: multi_asset' skills/_parallax/AI-profiles/profiles/soros.md
grep -c 'Soros, G. (1987)' skills/_parallax/AI-profiles/profiles/soros.md
grep -c 'dual-channel' skills/_parallax/AI-profiles/profiles/soros.md
grep -c 'Basket/screening mode' skills/_parallax/AI-profiles/profiles/soros.md
grep -c 'Single-ticker mode' skills/_parallax/AI-profiles/profiles/soros.md
```

Expected: Each ≥ 1.

- [ ] **Step 3: Schema extensibility checkpoint**

Read `skills/_parallax/AI-profiles/profile-schema.md`. The Soros spec introduces three new frontmatter fields: `output_shape_single_ticker`, `tool_sequence_basket`, and `tool_sequence_single_ticker`. These are dual-mode extensions not present in the Buffett profile.

These should already be documented as OPTIONAL fields in the schema per Phase 1 Task 3 (the schema allows optional descriptive fields, with these specific field names listed as examples). If they are NOT in the schema, update the schema file to document them as OPTIONAL fields for profiles with two modes. Do not remove the original `tool_sequence` field — it remains the default for single-mode profiles. This is a backward-compatible schema extension.

If the schema needs updating, include that edit in the same commit as the Soros profile spec.

- [ ] **Step 4: Commit (profile spec + schema extension if needed)**

```bash
git add skills/_parallax/AI-profiles/profiles/soros.md
# If schema was extended:
# git add skills/_parallax/AI-profiles/profile-schema.md
git commit -m "feat: Soros profile spec — dual-mode top-down macro"
```

---

## Task 9: Write the AI-soros dispatcher

**Files:**
- Create: `skills/AI-soros/SKILL.md`
- Delete: `skills/AI-soros/.gitkeep`

The Soros dispatcher is the longest because it handles two modes. Both modes share the macro workflow; only the final consumption of the data differs.

- [ ] **Step 1: Write the dispatcher**

Create `skills/AI-soros/SKILL.md` with this exact content:

````markdown
---
name: parallax-AI-soros
description: "Applies George Soros's top-down reflexivity framework (per 'The Alchemy of Finance', 1987) to current Parallax data. Two modes: basket mode surfaces regime themes and ranked trade ideas; single-ticker mode runs the same macro workflow and checks ticker exposure via dual channels (industry-exposure AND telemetry basket theme). Third-person framing, book citation, AI-inferred from public information. NOT financial advice."
negative-triggers:
  - Bottom-up factor scoring → use /parallax-AI-buffett
  - Mechanical formula → use /parallax-AI-greenblatt
  - Balance-sheet-first checks → use /parallax-AI-klarman
  - Cross-profile consensus → use /parallax-AI-consensus
  - Full macro outlook without a persona lens → use /parallax-macro-outlook
  - Morning brief for a portfolio → use /parallax-morning-brief
gotchas:
  - JIT-load _parallax/parallax-conventions.md, profile-schema.md, output-template.md, profiles/soros.md
  - Soros has TWO modes — basket (no ticker) and single-ticker — that share a macro workflow
  - list_macro_countries is 1 token; macro_analyst is 5 tokens per market; cap at 5 markets
  - get_telemetry is 1 token but important — it's what distinguishes Soros-style from other profiles
  - Single-ticker mode requires BOTH the macro workflow AND a ticker-exposure check via 2 independent channels
  - DO NOT say "Soros would buy"; always "Soros-style" / "reflexivity lens identifies"
  - The dual-channel logic is load-bearing — a single-channel flag is partial, not full match
  - Disclaimer verbatim
---

# Parallax AI Soros Profile

Top-down reflexivity lens: regime identification → thematic exposure → ranked trade ideas OR single-ticker dual-channel check.

## Usage

```
/parallax-AI-soros                         # basket mode — surfaces regime themes and ranked ideas
/parallax-AI-soros AAPL.O                  # single-ticker mode — dual-channel exposure check
/parallax-AI-soros --markets US,JP,EU      # basket mode with explicit market list
```

## Workflow

### Step 0 — JIT-load dependencies

Same as other profiles, loading `profiles/soros.md`.

### Step 1 — Determine mode

- Zero tickers → **basket mode**
- Exactly one ticker → **single-ticker mode**
- Multiple tickers → reject with "Soros profile takes zero or one ticker. Use /parallax-AI-consensus for multi-ticker."

### Step 2 — Macro workflow (runs in BOTH modes)

1. Call `list_macro_countries` to get covered markets (1 token).
2. Select 3-5 tactically interesting markets. Default: US, JP, EU, and top-2 EM based on telemetry divergence signals from Step 3. If the user passed `--markets`, use that list.
3. Call `macro_analyst(component=tactical)` for each selected market IN PARALLEL (5 tokens each × 3-5 = 15-25 tokens).
4. Call `get_telemetry` for cross-market regime divergence signals (1 token).
5. Identify 1-3 regime themes where `macro_analyst` outputs and `get_telemetry` outputs agree on directional views. Examples:
   - "Fed cutting + dollar weakening → EM equities and commodities"
   - "Rates higher for longer → financials and defensive dividend payers"
   - "Fiscal divergence US vs EU → US cyclicals overweight vs EU cyclicals"

### Step 3 — Basket mode completion (skip if single-ticker)

1. For each identified theme, call `build_stock_universe` with a thematic query (5 tokens each). Example queries:
   - "EM equities benefiting from dollar weakness"
   - "US cyclicals with operating leverage to rate cuts"
2. For top 3-5 names per theme, call `get_peer_snapshot` (1 token each).
3. Apply cross-validation gate per `profile-schema.md §2 Step 2` for each ticker surfaced.
4. Rank names within each theme by momentum score + macro sensitivity.
5. Render as `trade_ideas` output shape (see Step 5).

### Step 4 — Single-ticker mode completion (skip if basket)

1. Call `get_company_info` on the input ticker (1 token) — retrieve sector, industry.
2. For each identified theme, call `build_stock_universe` with the theme's query (5 tokens each).
3. **Dual-channel exposure check:**

   **Channel A — Industry exposure:**
   - Does the ticker appear directly in any theme's `build_stock_universe` result?
   - OR does the ticker's sector/industry classification match a theme's target industry (e.g., ticker is Energy, theme is "Energy benefiting from dollar weakness")?
   - Output: `FLAGGED` or `NOT_FLAGGED` for channel A.

   **Channel B — Telemetry basket theme:**
   - Does the ticker fall into any of the regime baskets surfaced by `get_telemetry`?
   - Telemetry baskets are typically named (e.g., "growth-over-value rotation," "dollar regime beneficiaries," "defensive quality rotation").
   - Output: `FLAGGED` or `NOT_FLAGGED` for channel B.

4. Cross-validation gate: after `get_peer_snapshot` (if called during `build_stock_universe` resolution), cross-check name per conventions.

5. Combine:
   - Both channels `FLAGGED` → verdict `match`
   - Exactly one channel `FLAGGED` → verdict `partial_match`
   - Neither channel flagged → verdict `no_match`

### Step 5 — Render through output template

**Basket mode output:**

```
Soros-style regime themes and trade ideas

Source: Soros, G. (1987). The Alchemy of Finance. | Drobny, S. (2006). Inside the House of Money.

Reflexivity framework: identify regime break or narrative-fundamentals divergence → surface exposed industries → concentrate on high-conviction names.

Markets analyzed: <list>

## Theme 1: <name>
Macro thesis: <one paragraph — regime break or tactical opportunity>
Directional view: <long / short / rotation>
Currency/rate context: <brief>

Ranked trade ideas:
| Rank | Ticker | Industry | Momentum score | Rationale |
|------|--------|----------|----------------|-----------|
| 1    | XXX.N  | ...      | 7.2            | ...       |
| ...  | ...    | ...      | ...            | ...       |

## Theme 2: <name>
[same structure]

Methodology footer + verbatim disclaimer (substituting "George Soros")
```

**Single-ticker mode output:**

```
Soros-style profile applied to <ticker>

Source: [same citation]

Reflexivity framework: top-down regime identification → thematic exposure check. Single-ticker mode answers "is this stock in an industry and basket theme the current regime analysis flags?"

Current regime themes (1-3): <list with one-line theses>

Ticker exposure check (dual-channel):

  Channel A — Industry exposure
    <ticker>'s sector/industry: <sector>
    Industry appears in theme(s): <theme names or NONE>
    Status: FLAGGED / NOT FLAGGED

  Channel B — Telemetry basket theme
    Telemetry baskets surfaced: <list>
    <ticker> falls in basket(s): <basket names or NONE>
    Status: FLAGGED / NOT FLAGGED

Profile fit: <match/partial/no>
  - match: both channels flagged (genuine thematic exposure)
  - partial_match: one channel flagged (either industry or basket, not both)
  - no_match: neither channel flagged (Soros-style lens has no current view)

Methodology footer + verbatim disclaimer (substituting "George Soros")
```

### Step 6 — Emit

## Graceful fallback

If `list_macro_countries` fails, derive covered markets from RIC suffix defaults per `parallax-conventions.md §6` and note the degradation.

If `macro_analyst` fails for a subset of markets, proceed with the remaining markets as long as ≥2 markets succeeded. Note which markets were unavailable.

If `get_telemetry` fails, single-ticker mode cannot perform Channel B. Fall back to industry-exposure-only: verdict becomes `match` (channel A only, noted as "telemetry unavailable"), `partial_match`, or `no_match`. Document the degradation in the output.

If `build_stock_universe` returns no names for any theme, the themes are genuine but no current names are exposed. For basket mode, report the themes without names. For single-ticker mode, channel A is `NOT_FLAGGED`.
````

- [ ] **Step 2: Remove placeholder and verify**

```bash
rm skills/AI-soros/.gitkeep
grep -c '^name: parallax-AI-soros' skills/AI-soros/SKILL.md
grep -c 'basket mode' skills/AI-soros/SKILL.md
grep -c 'single-ticker mode' skills/AI-soros/SKILL.md
grep -c 'Channel A' skills/AI-soros/SKILL.md
grep -c 'Channel B' skills/AI-soros/SKILL.md
grep -c '### Step [0-6]' skills/AI-soros/SKILL.md
```

Expected: Each ≥ 1; step count ≥ 7.

- [ ] **Step 3: Commit**

```bash
git add skills/AI-soros/SKILL.md skills/AI-soros/.gitkeep
git commit -m "feat: parallax-AI-soros dispatcher — dual-mode top-down + ticker exposure"
```

---

## Task 10: Anchor test Soros profile — both modes

**Files:**
- Modify: `skills/_parallax/AI-profiles/profiles/soros.md` (update `last_anchor_test`)

- [ ] **Step 1: Basket mode qualitative test**

In the Claude Code session:
```
/parallax-AI-soros
```

Expected:
- 3-5 markets analyzed
- 1-3 regime themes surfaced
- Each theme has a plausible macro thesis
- Trade ideas are ranked per theme

**Qualitative check:** Do the themes match recent market narratives? Cross-reference with the last 2-3 days of Bloomberg/Reuters/FT macro coverage. The themes should be recognizable — not identical, but in the same conceptual space. If the themes are completely disconnected from current market conversation, the `macro_analyst` output may be stale or the dispatcher is not synthesizing it correctly.

- [ ] **Step 2: Single-ticker mode — ticker in a clear theme**

Pick a ticker whose sector is likely to be in a current regime theme. Example: if rates are the dominant theme, pick a rate-sensitive name like JPM.N. If energy/commodities are prominent, pick XOM.N.

```
/parallax-AI-soros <sector_tilted_ticker>
```

Expected: `match` or strong `partial_match`. Both channels or one channel should flag.

- [ ] **Step 3: Single-ticker mode — ticker NOT in any theme**

Pick a boring consumer staple or similar name unlikely to be in any current theme. Example: KO.N, PG.N, WMT.N.

```
/parallax-AI-soros PG.N
```

Expected: `no_match` or weak `partial_match`. Staples rarely ride macro regime themes.

- [ ] **Step 4: Validate dual-channel behavior**

Check that the output explicitly shows both Channel A and Channel B status, and that the verdict is consistent with the combination. The two most important cases:
1. A ticker flagged by Channel A only should render `partial_match`, not `match`
2. A ticker flagged by Channel B only should render `partial_match`, not `match`

If the dispatcher is collapsing these cases to `match`, the dual-channel logic is broken — fix in the dispatcher.

- [ ] **Step 5: Cross-validation gate test**

Pick a numeric HK/TW ticker (known risk per conventions §2). Example:
```
/parallax-AI-soros 0700.HK
```

Confirm that the cross-validation gate either (a) passes cleanly with matching names or (b) refuses to render with the expected error message on name mismatch. Either outcome is acceptable — a silent wrong-company render is NOT acceptable.

- [ ] **Step 6: Update `last_anchor_test` and commit**

```bash
# Edit soros.md: last_anchor_test: PENDING → 2026-04-06
git add skills/_parallax/AI-profiles/profiles/soros.md
git commit -m "test: anchor-test Soros profile in both basket and single-ticker modes"
```

---

## Task 11: Phase 2 complete — summary verification

- [ ] **Step 1: Verify all Phase 2 files exist and have real anchor-test dates**

```bash
ls skills/_parallax/AI-profiles/profiles/
ls skills/AI-greenblatt/ skills/AI-klarman/ skills/AI-soros/
grep -r 'last_anchor_test: PENDING' skills/_parallax/AI-profiles/profiles/
```

Expected:
- `profiles/` contains `buffett.md`, `greenblatt.md`, `klarman.md`, `soros.md` (4 files)
- Each skill directory contains `SKILL.md`
- The last grep returns NO matches (all profiles have real dates)

- [ ] **Step 2: Update the README's "In-scope profiles" table**

Open `skills/_parallax/AI-profiles/README.md`. The table already lists all 4 v1 profiles from Phase 1, so no changes should be needed. Verify by rerunning:

```bash
grep -c '| `buffett` |' skills/_parallax/AI-profiles/README.md
grep -c '| `soros` |' skills/_parallax/AI-profiles/README.md
grep -c '| `greenblatt` |' skills/_parallax/AI-profiles/README.md
grep -c '| `klarman` |' skills/_parallax/AI-profiles/README.md
```

Expected: Each `1`. If any return `0`, add the missing row and commit.

- [ ] **Step 3: Cross-profile smoke test**

Run all 4 profiles against the same ticker (pick something liquid and well-covered, e.g., BRK.B) and eyeball the outputs:

```
/parallax-AI-buffett BRK.B
/parallax-AI-greenblatt BRK.B
/parallax-AI-klarman BRK.B
/parallax-AI-soros BRK.B
```

Expected:
- Buffett: `match` (this was the Phase 1 anchor test)
- Greenblatt: varies — BRK.B is huge, may or may not be in top decile depending on universe
- Klarman: likely `match` or strong `partial_match` (strong balance sheet)
- Soros: varies — depends on current regime themes

The important check: all 4 outputs are rendered correctly with citation + verdict + disclaimer. No crashes, no missing sections, no "buy/sell" language anywhere. Each output identifies Berkshire Hathaway by name (cross-validation passed).

- [ ] **Step 4: Phase 2 handoff summary**

Phase 2 is complete when:
- ✅ Greenblatt, Klarman, Soros profile specs all exist and have been anchor-tested
- ✅ Three new dispatcher skills (`parallax-AI-greenblatt`, `parallax-AI-klarman`, `parallax-AI-soros`) are committed and invokable
- ✅ Soros handles both basket and single-ticker modes correctly
- ✅ All profiles render the verbatim disclaimer
- ✅ Cross-profile smoke test on BRK.B produces 4 consistent, well-formatted outputs

Proceed to Phase 3 (`parallax-AI-consensus` meta-skill + docs) once all the above are confirmed.
