---
name: parallax-credit-lens
description: "Credit risk assessment for publicly traded companies: leverage, coverage, liquidity, solvency (Palepu), Altman Z-score, and credit health signals vs. peer medians. Symbol in RIC format (AAPL.O, JPM.N). NOT for portfolio credit risk (use /parallax-scenario-analysis), not for private companies (requires document ingestion; not covered)."
---

<!-- white-label: integration-pattern.md -->

# Credit Lens

## When not to use

- Private company credit analysis (requires document ingestion) → not covered; this skill needs a publicly traded issuer
- Portfolio credit concentration → use /parallax-scenario-analysis
- Single stock fundamental analysis → use /parallax-deep-dive

## Gotchas

- RIC format required (AAPL.O, not AAPL). Exchange suffix is critical.
- `credit_lens_logic.py` is the pure arithmetic layer. Do not put MCP calls or local file writes in it. Every flag, the Altman Z-score and the overall traffic-light are computed there, not re-derived in prose — see Batch C.
- `assemble_report()` in that module is a reference renderer for its own tests. It omits the §9.1 disclaimer and the §9.2 disclosure, so it must not produce client-facing output.
- JIT-load _parallax/parallax-conventions.md for parallel execution patterns and RIC resolution.
- get_financial_analysis is async (2-5 min) — do not block on other calls.
- Quality factor is a credit health proxy — deteriorating Quality score is an early warning signal for credit stress.
- Altman Z-score computed using market-cap-based formula for public companies (Z, not Z'). Thresholds: >2.99 Safe, 1.81–2.99 Grey, <1.81 Distress.
- `get_financial_analysis` returns both a solvency and a liquidity read. Render both — see Output Format §3 and §3a. One call, one cost, two sections.
- The Liquidity row in the Metrics Dashboard and the §3a liquidity narrative are different things and both belong in the output. The row is the quantitative flag from `ratios`; the narrative is the Palepu read that explains why the ratio sits where it does.
- If the Palepu sections are unavailable (tool error), degrade gracefully — output remaining metrics and flag **both** §3 and §3a as unavailable, since one call supplies both.
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (7-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (About This Report) in Output Format.

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

1. Verify input symbol is in RIC format (ticker.exchange) via `validate_ric()` in `credit_lens_logic.py`. If plain ticker provided (AAPL), resolve to RIC using parallax-conventions.md suffix table (→ AAPL.O), then re-validate.
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
get_financial_analysis(symbol=<RIC>)   # Palepu solvency AND liquidity read (5 tokens, async)
get_score_analysis(symbol=<RIC>)       # Quality score 52-week trajectory
get_telemetry()                        # Market regime tag (no symbol parameter)
```

From these:
- Solvency (Palepu): accruals quality, profitability and leverage assessment → Output Format §3
- Liquidity (Palepu): the qualitative liquidity read from the same response → Output Format §3a. Extract it alongside solvency; it is already paid for by this call
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

Compute this via `compute_altman_z()` in `credit_lens_logic.py`, which returns the score, the variant label and the zone flag together. The formula above documents what it computes.

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
| Quality Score Change (52w, 0-10 scale) | change ≤ -0.5 pts | change ≤ -1.5 pts |

Quality score deterioration is a primary credit health warning signal.

Bands sit on the 0-10 per-security scale that `get_score_analysis` returns. Do not restate them on a 0-100 basis.

### Batch C — Flag computation

Zero tool calls. Use `credit_lens_logic.py` to compute every flag, the Altman Z-score and its zone, and the overall traffic-light. The tables above and the Altman formula are the documentation of the bands; the module is what applies them.

| Quantity | Call |
|---|---|
| Per-metric flag (peer-relative and absolute, more conservative wins) | `flag_metric(value, peer_median, peer_p75, metric_key)` |
| Altman Z-score, variant label (`Z` or `Z'`) and zone flag | `compute_altman_z(AltmanInputs(...))` |
| 52-week Quality change, then its flag | `quality_change_pts(current, prior)` → `flag_quality_change(change_pts)` |
| Overall traffic-light across all flags | `overall_traffic_light(flags)` |

`metric_key` selects the direction and any absolute band. Pass one of the registered keys below for every dashboard row:

The Metrics Dashboard groups these ten metrics into the four category rows of §2; the table below is keyed by metric, not by rendered row.

| Metric | `metric_key` | Direction | Absolute band |
|---|---|---|---|
| Leverage — Debt/EBITDA | `debt_ebitda` | higher is worse | yes |
| Leverage — Debt/Equity | `debt_equity` | higher is worse | peer-relative only |
| Leverage — Debt/Assets | `debt_assets` | higher is worse | peer-relative only |
| Coverage — Interest Coverage | `interest_coverage` | lower is worse | yes |
| Coverage — EBITDA/Interest | `ebitda_interest_coverage` | lower is worse | peer-relative only |
| Liquidity — Current Ratio | `current_ratio` | lower is worse | yes |
| Liquidity — Quick Ratio | `quick_ratio` | lower is worse | peer-relative only |
| Profitability — EBITDA Margin | `ebitda_margin` | lower is worse | peer-relative only |
| Profitability — EBIT Margin | `ebit_margin` | lower is worse | peer-relative only |
| Profitability — FCF Margin | `fcf_margin` | lower is worse | peer-relative only |

`flag_metric` raises `ValueError` on a key outside this table, so a typo stops the run instead of scoring the row. Never invent a key. To flag a metric that is not in the table, add it to `METRIC_DIRECTIONS` in `credit_lens_logic.py` first.

The `peer-relative only` rows have no absolute band, and the `ratios` response carries `peer_median` / `peer_p75` for only five metrics — `debt_to_equity`, `debt_to_ebitda`, `interest_coverage`, `current_ratio`, `ebitda_margin`. When a row has neither a peer pair nor a band, `flag_metric` returns UNAVAILABLE rather than GREEN: nothing can judge it, so it must not read as healthy. Render those rows as `➖ UNAVAILABLE` and leave them out of the traffic-light count, which `overall_traffic_light()` already does.

Three rules that a hand-computation gets wrong:

- Pass the Quality change through `quality_change_pts()` rather than subtracting the two scores inline. The bands are one-decimal and the raw subtraction is not exact, so a true −0.5 can compute as −0.4999999999999996 and flag GREEN.
- `peer_p75` always carries the **adverse** tail, in both directions: numerically above `peer_median` when higher is worse, below it when lower is worse. The `ratios` field literally named `peer_p75` already holds it either way (`interest_coverage`: `peer_p75` 8.5 against `peer_median` 18.2). So pass `peer_p75` through unchanged. Do not go looking for a 25th-percentile field; none is returned, and do not recompute or invert the value yourself. `flag_metric` raises `ValueError` on an inverted pair in **either** direction rather than silently inverting the bands. Treat the raise as a peer-data error and fall back to the absolute rule by passing `None` for both peer arguments — but note the `peer-relative only` rows have no absolute rule, so they degrade to UNAVAILABLE rather than to a band.
- `compute_altman_z` raises on zero `total_assets` or zero `total_liabilities`, and raises if neither `market_cap` nor `book_equity` is supplied. Treat the raise as the Altman leg being unavailable; do not substitute a zero.

## Output Format

Structure output in markdown with the following sections:

### 1. **Header** (1 line)
```
## Credit Risk Assessment: [Company] ([RIC]) | Traffic-Light: 🟢/🟡/🔴
```
Overall traffic-light determined by: count of RED flags (→ Red), count of AMBER flags (→ Amber), count of GREEN (→ Green). Majority color wins. If two or more colors tie for the highest count, render the most conservative tied color (Red > Amber > Green) — e.g., a 2-2-2 split renders Red. Compute via `overall_traffic_light(flags)`, which also drops UNAVAILABLE legs from the count and returns UNAVAILABLE when every leg is missing.

### 2. **Metrics Dashboard** (table)
```
| Category      | Signal | Metric Value | Peer Median | Interpretation |
|---------------|--------|--------------|-------------|-----------------|
| Leverage      | 🔴 RED  | D/E 2.1x     | Peer 1.2x   | 75% above peer |
| Coverage      | 🟢 GREEN| Int Cov 5.2x | Peer 3.1x   | Top quartile |
| Liquidity     | 🟡 AMBER| Curr Ratio 1.3x | Peer 1.8x | Below median |
| Profitability | 🟢 GREEN| EBITDA Margin 28% | Peer 22% | Above peer |
| Altman Z      | 🟡 AMBER| Z = 2.1      | —           | Grey Zone |
| Quality Trend | 🔴 RED  | –1.8 pts (52w) | —         | Deteriorating |
```

### 2a. **Verdict sensitivity** (one line)
State the Altman Z-score's nearest band boundary (2.99 Safe/Grey or 1.81 Grey/Distress) and the arithmetic flip condition, per `parallax-conventions.md` §11. Example: "Altman Z = 2.85 is within the Grey Zone, 0.14 below the 2.99 Safe threshold; a Z rise above 2.99 would move this leg to Safe." Applies only to the Altman Z band — the overall traffic-light header is a multi-metric majority vote, not a single published numeric cutoff, and is out of scope for this line.

### 3. **Solvency Assessment** (narrative)
Output the Palepu solvency section from `get_financial_analysis`. If unavailable, note: `[Solvency assessment unavailable — tool error]`.

### 3a. **Liquidity Assessment** (narrative)
Output the Palepu liquidity section from the same `get_financial_analysis` response. This explains *why* the Liquidity row in the Metrics Dashboard reads as it does — working-capital cycle, cash conversion, near-term obligations — and is not a restatement of the current/quick ratio. Do not omit it because the ratio already appears above. If unavailable, note: `[Liquidity assessment unavailable — tool error]`.

### 4. **Key Flags** (bulleted list)
List every RED and AMBER flag with one-line explanation:
- 🔴 RED: Debt/EBITDA 5.2x exceeds peer 75th percentile (3.8x) and absolute threshold (5.0x)
- 🟡 AMBER: Quality score down 1.4 pts over 52 weeks — monitor for further deterioration
- 🔴 RED: Interest Coverage 2.1x below absolute threshold (3.0x); limited debt service cushion

### 5. **Quality Trend** (one sentence)
[Quality score 52-week trajectory + interpretation from `get_score_analysis`]
Example: "Quality score deteriorated 1.4 points over the past 52 weeks, signaling a potential credit health decline."

### 6. **Macro Context** (one sentence)
[Market regime from `get_telemetry` + one sentence on credit implication]
Example: "Current market regime is recessionary — a challenging environment for credit quality; elevated default risk across all sectors."

### 7. **Branding Header** (only if `white_label_active` AND `client_name != ""`)
Single line at the very top of the rendered output: `**<client_name>** credit lens`. Logo handling per integration-pattern.md §5.

### 8. **About This Report** (always present)
One line stating branding state per integration-pattern.md §7, plus the unconditional §7 currency line: `Currency: figures as reported by source data; no base-currency conversion applied.` If a logo was skipped, append `Logo on file: <basename>` as a further About This Report line.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format.

### 9. **Footer**

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

## Error Handling

- **Symbol not found**: Return error message with suggestion to check RIC format.
- **get_financial_analysis fails** (async timeout or error): Continue with remaining metrics. One call supplies both Palepu sections, so mark **both**: `[Solvency assessment unavailable]` in §3 and `[Liquidity assessment unavailable]` in §3a. The quantitative Liquidity row in the Metrics Dashboard is unaffected — it comes from `ratios`, a different call.
- **Peer median unavailable** (peer group too small): Degrade gracefully — show absolute thresholds only, note peer comparison unavailable.
- **Market cap unavailable** (Altman X4): Compute Z' (book equity variant) and note substitution in Altman section.

## Gotchas & Callouts

- **Quality score is a credit proxy**: A deteriorating Quality score (a 52-week change of -1.5 pts or worse on the 0-10 scale) is an early warning of credit stress and should be flagged as RED even if other metrics are healthy.
- **Altman Z thresholds shift by industry**: Manufacturing thresholds may differ from retail/financial. The fixed thresholds are generic — note industry caveats in output if appropriate.
- **Peer comparisons assume comparable size/structure**: A mega-cap's peer medians may not be relevant to an analyst evaluating a small-cap. Call this out if significant size mismatch is detected.
- **Palepu solvency assessment includes accruals quality**: High accruals (earnings not backed by cash) is a red flag independent of traditional credit metrics.
