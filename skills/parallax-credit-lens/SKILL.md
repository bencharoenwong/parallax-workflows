---
name: parallax-credit-lens
description: "Credit risk assessment for publicly traded companies: leverage, coverage, liquidity, solvency (Palepu), Altman Z-score, and credit health signals vs. peer medians. Symbol in RIC format (AAPL.O, JPM.N). NOT for portfolio credit risk (use /parallax-scenario-analysis), not for private companies (use /parallax-credit-risk when available)."
---

<!-- white-label: integration-pattern.md -->

# Credit Lens

## When not to use

- Private company credit analysis → use /parallax-credit-risk (document ingestion)
- Portfolio credit concentration → use /parallax-scenario-analysis
- Single stock fundamental analysis → use /parallax-deep-dive

## Gotchas

- RIC format required (AAPL.O, not AAPL). Exchange suffix is critical.
- JIT-load _parallax/parallax-conventions.md for parallel execution patterns and RIC resolution.
- get_financial_analysis is async (2-5 min) — do not block on other calls.
- Quality factor is a credit health proxy — deteriorating Quality score is an early warning signal for credit stress.
- Altman Z-score computed using market-cap-based formula for public companies (Z, not Z'). Thresholds: >2.99 Safe, 1.81–2.99 Grey, <1.81 Distress.
- If Palepu solvency section is unavailable (tool error), degrade gracefully — output remaining metrics and flag Palepu as unavailable.
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (6-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (Provenance) in Output Format.

Credit risk assessment for publicly traded companies using Parallax MCP tools.

## Usage

```
/parallax-credit-lens AAPL.O
/parallax-credit-lens JPM.N
/parallax-credit-lens 0001.HK "Hong Kong banking"
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for RIC resolution, batch patterns, and fallback behaviors.

### Batch 0 — Validation

1. Verify input symbol is in RIC format (ticker.exchange). If plain ticker provided (AAPL), resolve to RIC using parallax-conventions.md suffix table (→ AAPL.O).
2. Call `ToolSearch` with query `"+Parallax"` to load MCP tool schemas before first `mcp__claude_ai_Parallax__*` call.

### Batch A — Core financials (parallel, 4 tokens)

Fire all 4 calls simultaneously:

```
get_financials(symbol=<RIC>, statement="balance_sheet")   # Total debt, equity, total assets
get_financials(symbol=<RIC>, statement="cash_flow")       # Operating CF, Capex, FCF
get_financials(symbol=<RIC>, statement="ratios")          # D/E, D/EBITDA, Interest Cov, margins, peer medians
get_peer_snapshot(symbol=<RIC>)                           # D/E peer median, factor scores
```

Extract from these calls:
- Leverage: Debt/EBITDA, Debt/Equity, Debt/Assets (compare to peer medians from `ratios` and `peer_snapshot`)
- Coverage: Interest Coverage Ratio, EBITDA/Interest (from `ratios`)
- Liquidity: Current Ratio, Quick Ratio (from `balance_sheet` + `ratios`)
- Profitability: EBITDA Margin, EBIT Margin, FCF Margin (from `ratios`)

### Batch B — Solvency, trend, macro (parallel, 6 tokens, async)

Fire all 3 calls simultaneously. Note: `get_financial_analysis` is async (2-5 min) and should not block the workflow — execute in parallel.

```
get_financial_analysis(symbol=<RIC>)   # Palepu solvency assessment (5 tokens, async)
get_score_analysis(symbol=<RIC>)       # Quality score 52-week trajectory
get_telemetry()                        # Market regime tag (no symbol parameter)
```

From these:
- Solvency (Palepu): accruals quality, profitability, liquidity, leverage solvency assessment
- Quality Trend: 52-week Quality factor score change (deterioration is a red flag)
- Macro Regime: current market regime context for credit environment

### Altman Z-Score Computation

Compute market-cap-based Altman Z-score (public company variant) from Batch A + publicly available market cap:

```
Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5

where:
  X1 = Working Capital / Total Assets
  X2 = Retained Earnings / Total Assets
  X3 = EBIT / Total Assets
  X4 = Market Cap / Total Liabilities  ← use closing market cap from latest trading data
  X5 = Revenue / Total Assets

Thresholds:
  Z > 2.99  → Safe Zone (low distress probability)
  1.81–2.99 → Grey Zone (moderate risk)
  Z < 1.81  → Distress Zone (high distress probability)
```

If market cap unavailable, compute with book equity instead (Z' variant) and note the substitution.

### Flagging Logic

For each metric, compare against peer median and peer 75th percentile:

| Signal | Condition |
|--------|-----------|
| 🟢 GREEN | Better than peer median |
| 🟡 AMBER | Between peer median and 75th percentile |
| 🔴 RED | Worse than peer 75th percentile |

Also apply absolute credit thresholds (use the more conservative of peer-relative and absolute):

| Metric | Amber | Red |
|--------|-------|-----|
| Debt/EBITDA | > 3.5x | > 5.0x |
| Interest Coverage | < 3.0x | < 1.5x |
| Current Ratio | < 1.2x | < 1.0x |
| Altman Z | Grey zone (1.81–2.99) | Distress zone (< 1.81) |
| Quality Score Change | > –5 pts | > –15 pts (52w) |

Quality score deterioration is a primary credit health warning signal.

## Output Format

Structure output in markdown with the following sections:

### 1. **Header** (1 line)
```
## Credit Risk Assessment: [Company] ([RIC]) | Traffic-Light: 🟢/🟡/🔴
```
Overall traffic-light determined by: count of RED flags (→ Red), count of AMBER flags (→ Amber), count of GREEN (→ Green). Majority color wins.

### 2. **Metrics Dashboard** (table)
```
| Category      | Signal | Metric Value | Peer Median | Interpretation |
|---------------|--------|--------------|-------------|-----------------|
| Leverage      | 🔴 RED  | D/E 2.1x     | Peer 1.2x   | 75% above peer |
| Coverage      | 🟢 GREEN| Int Cov 5.2x | Peer 3.1x   | Top quartile |
| Liquidity     | 🟡 AMBER| Curr Ratio 1.3x | Peer 1.8x | Below median |
| Profitability | 🟢 GREEN| EBITDA Margin 28% | Peer 22% | Above peer |
| Altman Z      | 🟡 AMBER| Z = 2.1      | —           | Grey Zone |
| Quality Trend | 🔴 RED  | –14 pts (52w) | —          | Deteriorating |
```

### 2a. **Verdict sensitivity** (one line)
State whether the Altman Z-score sits within 10% of a band boundary (2.99 Safe/Grey or 1.81 Grey/Distress) and the arithmetic flip condition, per `parallax-conventions.md` §11. Example: "Altman Z = 2.85 is within the Grey Zone, 0.14 below the 2.99 Safe threshold; a Z rise above 2.99 would move this leg to Safe." Applies only to the Altman Z band — the overall traffic-light header is a multi-metric majority vote, not a single published numeric cutoff, and is out of scope for this line.

### 3. **Solvency Assessment** (narrative)
Output the Palepu solvency section from `get_financial_analysis`. If unavailable, note: `[Solvency assessment unavailable — tool error]`.

### 4. **Key Flags** (bulleted list)
List every RED and AMBER flag with one-line explanation:
- 🔴 RED: Debt/EBITDA 5.2x exceeds peer 75th percentile (3.8x) and absolute threshold (5.0x)
- 🟡 AMBER: Quality score down 14 pts over 52 weeks — monitor for further deterioration
- 🔴 RED: Interest Coverage 2.1x below absolute threshold (3.0x); limited debt service cushion

### 5. **Quality Trend** (one sentence)
[Quality score 52-week trajectory + interpretation from `get_score_analysis`]
Example: "Quality score deteriorated 14 points over the past 52 weeks, signaling a potential credit health decline."

### 6. **Macro Context** (one sentence)
[Market regime from `get_telemetry` + one sentence on credit implication]
Example: "Current market regime is recessionary — a challenging environment for credit quality; elevated default risk across all sectors."

### 7. **Branding Header** (only if `white_label_active` AND `client_name != ""`)
Single line at the very top of the rendered output: `**<client_name>** credit lens`. Logo handling per integration-pattern.md §5.

### 8. **Provenance** (always present)
One line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second Provenance line.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (Provenance) when composing the Output Format.

### 9. **Footer**

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

## Error Handling

- **Symbol not found**: Return error message with suggestion to check RIC format.
- **get_financial_analysis fails** (async timeout or error): Continue with remaining metrics; append `[Solvency assessment unavailable]` to output.
- **Peer median unavailable** (peer group too small): Degrade gracefully — show absolute thresholds only, note peer comparison unavailable.
- **Market cap unavailable** (Altman X4): Compute Z' (book equity variant) and note substitution in Altman section.

## Gotchas & Callouts

- **Quality score is a credit proxy**: A deteriorating Quality score (especially >10 pts decline) is an early warning of credit stress and should be flagged as RED even if other metrics are healthy.
- **Altman Z thresholds shift by industry**: Manufacturing thresholds may differ from retail/financial. The fixed thresholds are generic — note industry caveats in output if appropriate.
- **Peer comparisons assume comparable size/structure**: A mega-cap's peer medians may not be relevant to an analyst evaluating a small-cap. Call this out if significant size mismatch is detected.
- **Palepu solvency assessment includes accruals quality**: High accruals (earnings not backed by cash) is a red flag independent of traditional credit metrics.
