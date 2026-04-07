---
name: parallax-AI-consensus
description: "Runs all installed Parallax AI Investor Profiles (Buffett, Greenblatt, Klarman, Soros) against a single ticker or short basket (cap 5). Returns the per-profile verdict matrix, the super-majority consensus signal per consensus-config.md, and a factor-level agreement detail showing which factors/criteria were flagged by multiple profiles. Cross-profile agreement IS the high-conviction signal. Third-person framing throughout, AI-inferred from public information. NOT financial advice. NOT personalized."
negative-triggers:
  - Single profile only → use /parallax-AI-buffett, /parallax-AI-greenblatt, /parallax-AI-klarman, or /parallax-AI-soros
  - Broader macro outlook → use /parallax-macro-outlook
  - Portfolio analysis → use /parallax-morning-brief or /parallax-portfolio-checkup
  - Full due diligence → use /parallax-due-diligence
  - Running backtests → use /backtest
gotchas:
  - JIT-load _parallax/parallax-conventions.md, profile-schema.md, output-template.md, consensus-config.md
  - JIT-load ALL installed profile specs under _parallax/AI-profiles/profiles/ — buffett.md, greenblatt.md, klarman.md, soros.md
  - Do NOT re-implement profile logic — invoke each profile dispatcher's workflow as documented in skills/AI-<name>/SKILL.md
  - Cap basket input at 5 tickers per call. For single-ticker queries, all 4 profiles are applicable (Soros runs single-ticker dual-channel mode)
  - Super-majority math uses ceiling rounding per consensus-config.md — required = ceil(0.75 × applicable)
  - Partial matches do NOT count toward the super-majority signal but DO count toward factor-level agreement surfacing
  - Factor-level agreement is the highest-value section — do not skip it
  - Disclaimer verbatim; use umbrella phrasing "Parallax AI Investor Profiles framework" rather than any single investor name
  - If a profile fails (cross-validation, timeout, missing data) mark as `skipped` and continue with remaining profiles
  - INSUFFICIENT_PROFILES if applicable count < 3 (per consensus-config.md minimum_applicable_count)
---

# Parallax AI Investor Profiles — Consensus Meta-Skill

Runs all installed AI Investor Profiles in parallel against a ticker (or short basket), aggregates the verdicts, computes the super-majority consensus signal, and surfaces factor-level agreement detail.

## Usage

```
/parallax-AI-consensus AAPL.O                         # single ticker — all 4 profiles run
/parallax-AI-consensus BRKb.N,KO.N,AXP.N              # basket mode — cap 5 tickers
/parallax-AI-consensus --only buffett,greenblatt AAPL # subset (rare; min 3 still required)
```

## Workflow

### Step 0 — JIT-load dependencies

1. `skills/_parallax/parallax-conventions.md`
2. `skills/_parallax/AI-profiles/profile-schema.md`
3. `skills/_parallax/AI-profiles/output-template.md`
4. `skills/_parallax/AI-profiles/consensus-config.md`
5. ALL installed profile specs:
   - `skills/_parallax/AI-profiles/profiles/buffett.md`
   - `skills/_parallax/AI-profiles/profiles/greenblatt.md`
   - `skills/_parallax/AI-profiles/profiles/klarman.md`
   - `skills/_parallax/AI-profiles/profiles/soros.md`
6. Each profile's dispatcher (`skills/AI-<name>/SKILL.md`) for workflow reference.

Call `ToolSearch` with query `"+Parallax"` to load deferred MCP tool schemas before the first Parallax call.

### Step 1 — Parse input

- Single ticker → **single-ticker mode**, 4 profiles applicable
- Comma-separated list of 2-5 tickers → **basket mode**
- > 5 tickers → reject: "Consensus skill takes at most 5 tickers per call. Please split your request."
- Optional `--only <profile1>,<profile2>` flag restricts which profiles run (minimum 3 still required for a valid consensus signal)

### Step 2 — Run all applicable profiles in parallel

For each installed profile, execute its workflow per its dispatcher:

- **Buffett** — `get_company_info` + `get_peer_snapshot` + `get_financials(summary)` + `get_score_analysis(52w)` + apply 4 factor thresholds
- **Greenblatt** — `get_company_info` + `build_stock_universe` (peer universe) + `get_financials(ratios)` for peers + rank
- **Klarman** — `get_company_info` + `get_peer_snapshot` + `get_financials(balance_sheet/cash_flow/ratios, 4 periods)` + 4 balance-sheet checks
- **Soros** — `list_macro_countries` + `macro_analyst(tactical) × N` + `get_telemetry` + `get_company_info` + `build_stock_universe` per theme + dual-channel exposure check

Profiles run IN PARALLEL where their tool sequences don't share dependencies. Do NOT sequentialize — the whole point is independent cross-profile execution.

Each profile returns:
- `verdict`: `match` | `partial_match` | `no_match` | `skipped`
- `verdict_detail`: e.g., "3 of 4 factor criteria met" | "top 15% of peer universe" | "both channels flagged"
- `factor_flags`: dict of factor/criterion → `FLAGGED` | `NOT_FLAGGED` | `NOT_APPLICABLE`
- `fallback_notes`: any graceful fallback that affected the result

### Step 3 — Cross-validation gate (each profile self-checks)

Each profile runs its own pre-render cross-validation per `profile-schema.md §2 Step 2`. If ANY profile refuses to render due to name mismatch, the meta-skill emits:

```
Warning: Profile <name> refused to render for <ticker> due to cross-validation failure. This profile is marked as `skipped` for this ticker. Proceeding with remaining applicable profiles.
```

If NO profiles render successfully, the meta-skill returns `INSUFFICIENT_PROFILES` and does not compute consensus.

### Step 4 — Compute consensus per `consensus-config.md`

- `A` = applicable profiles (returned `match` | `partial_match` | `no_match`; excludes `skipped`)
- `M` = profiles that returned `match` (NOT `partial_match`)
- `required_matches = ceil(0.75 × A)`
- `minimum_applicable_count = 3`

Consensus signal:
- **`INSUFFICIENT_PROFILES`** if `A < 3`
- **`YES`** if `A ≥ 3` AND `M ≥ required_matches`
- **`NO`** if `A ≥ 3` AND `M < required_matches`

### Step 5 — Compute factor-level agreement

For each unique factor/criterion across all profiles' `factor_flags`:
- Count profiles (matching + partially-matching) where it is `FLAGGED`
- Sort by count descending

Surface three buckets:
- **Shared signals** — flagged by ≥ 2 matching/partial profiles
- **Single-profile signals** — flagged by 1 profile
- **Absence signals** — NOT flagged by any matching profile (informative — collective blind spot)

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
| AI-klarman            | <verdict>     | <N of 4 balance-sheet checks passed>      |
| AI-soros              | <verdict>     | <dual-channel: A=<status> B=<status>>     |

## Super-majority consensus signal

Applicable profiles (A): <count>
Full matches (M):        <count>
Super-majority threshold: 75%
Required matches:        ceil(0.75 × <A>) = <required>
Consensus signal:        YES / NO / INSUFFICIENT_PROFILES

## Shared factor signal (factors/criteria flagged across profiles)

Factors flagged by ≥ 2 matching profiles:
  - <Factor>: flagged by <N> of <M> (<profile names>)
  - <Factor>: flagged by <N> of <M> (<profile names>)

Single-profile signals:
  - <Factor>: flagged by 1 profile (<profile name>)

NOT flagged by any matching profile (collective blind spot):
  - <Factor>: no profile currently flags this dimension

Interpretation: <2-3 sentence plain-language summary — where profiles
converge, where they diverge, what dimensions are collectively absent.>

## Methodology footer

Profiles executed: <list with token costs>
Total token cost: <sum>
Cross-validation gate: PASSED for all rendered profiles
Consensus config: 75% super-majority, minimum 3 applicable profiles, ceiling rounding

---
This output is an AI-inferred synthesis produced by the Parallax AI Investor Profiles framework. Each individual profile is derived solely from publicly available information — peer-reviewed academic sources or the investors' own published books, as cited per profile. It is not financial advice, not personalized, not endorsed by any of the named investors or their representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

**Basket mode output:** same structure per ticker, with the per-profile matrix, super-majority signal, and factor-level agreement computed per-ticker. Output is organized ticker-by-ticker.

### Step 7 — Emit

## Graceful fallback

- 3 of 4 profiles run successfully → consensus proceeds with `A=3` (effectively requiring unanimity per ceiling rule)
- 2 of 4 profiles run successfully → return `INSUFFICIENT_PROFILES` (do NOT compute a 2-profile signal)
- Any single profile's tool calls fail after retry → that profile is `skipped` (with fallback note) and consensus continues
- Input ticker not resolvable → emit standard conventions §1 error and exit, do not run profiles

## Token cost estimate (single ticker)

- Buffett: ~4 tokens
- Greenblatt ticker-check: ~10-15 tokens (universe build + peer ratios)
- Klarman: ~5-7 tokens (balance sheet + cash flow + ratios + peer snapshot)
- Soros single-ticker: ~25-30 tokens (macro + telemetry + universe)

**Total per single-ticker consensus call: ~45-55 tokens.** Most expensive skill in the family, but the value is the cross-profile agreement signal no single profile provides.

For basket mode (5 tickers), Buffett/Klarman/Greenblatt run per-ticker; Soros's macro workflow runs once and only the per-ticker exposure check repeats. Approximate basket-of-5 cost: ~150-200 tokens.

## Why this meta-skill exists

The consensus is the product's value proposition, not a convenience feature. Individual profiles are interesting but noisy — each reflects a single investor's framework and may flag for reasons unrelated to the investor's actual behavior today. Cross-profile consensus is informative precisely because the profiles are structurally different: Buffett is factor-tilted, Greenblatt is mechanical, Klarman is balance-sheet, Soros is top-down. When three or four agree, the agreement is unlikely coincidental.

The factor-level agreement section is pedagogically load-bearing. It tells users:
- **Where the profiles converge** (the high-conviction shared signal)
- **Where they diverge** (informative tension)
- **What dimensions are collectively absent** (the profiles' shared blind spots)

This gives users a framework for building their own views using Parallax data — the stated product goal.
