---
name: parallax-halal-screen
description: "Shariah-compliant stock screening: filter for halal investments, check compliance flags, explain screening criteria, and suggest compliant alternatives via Parallax MCP tools. NOT for general thematic screening (use /parallax-thematic-screen), not for portfolio construction (use /parallax-portfolio-builder)."
---

<!-- white-label: integration-pattern.md -->

# Halal / Shariah Screen

## When not to use

- General thematic screening → use /parallax-thematic-screen
- Portfolio construction → use /parallax-portfolio-builder
- Non-compliance screening → use /parallax-earnings-quality

## Gotchas

- JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
- explain_methodology does NOT support shariah/halal — valid concepts are value, quality, momentum, defensive, tactical, overall, factor_weighting, scoring
- Shariah thresholds are hardcoded in this skill (AAOIFI/DJIM standards) — derive compliance from get_financials data
- get_financial_analysis (Palepu framework) is async ~2-5 min — warn user before calling
- Financial ratios from get_financials help verify debt/revenue compliance thresholds
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (6-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (Provenance) in Output Format.

Screen stocks and portfolios for Shariah compliance using AAOIFI/DJIM screening thresholds applied to Parallax financial data.

## AAOIFI / DJIM Screening Thresholds

These are the standard Shariah compliance thresholds used in this skill. They are applied to data retrieved from `get_financials`.

| Ratio | Threshold | Pass condition |
|-------|-----------|----------------|
| Total debt / Total assets | < 33% | Low leverage — no excessive interest-bearing debt |
| (Cash + interest-bearing securities) / Total assets | < 33% | Limited exposure to interest-bearing instruments |
| (Interest income + non-permissible revenue) / Total revenue | < 5% | Negligible income from haram activities |

**Business activity screen (qualitative):** The company's primary business must not be in prohibited industries (conventional banking/insurance, alcohol, tobacco, gambling, pork, weapons, adult entertainment). This is assessed from `get_company_info` sector/industry data.

**Purification ratio:** If a stock passes all quantitative screens but has non-zero non-permissible income, the purification percentage = (non-permissible income / total income). Shareholders should donate that percentage of dividends received.

## Usage

```
/parallax-halal-screen AAPL.O
/parallax-halal-screen [{"symbol":"AAPL.O","weight":0.25},{"symbol":"JPM.N","weight":0.25},{"symbol":"JNJ.N","weight":0.25},{"symbol":"XOM.N","weight":0.25}]
/parallax-halal-screen "build halal portfolio in Southeast Asian equities"
```

## Workflow

JIT-load `_parallax/parallax-conventions.md` for RIC resolution, parallel execution, and fallback patterns.

### Step 0 — Tool loading

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call. Without this step, all Parallax tool calls below fail with "tool not found."

**For single stock compliance check:**
1. Call `get_company_info` to retrieve sector/industry — check against prohibited industries (banking, alcohol, tobacco, gambling, pork, weapons, adult entertainment).
2. Call `get_financials` with statement "balance_sheet" to retrieve total debt and total assets. Compute: total debt / total assets. **FAIL if >= 33%.**
3. Call `get_financials` with statement "balance_sheet" to retrieve cash and interest-bearing securities. Compute: (cash + interest-bearing securities) / total assets. **FAIL if >= 33%.**
4. Call `get_financials` with statement "ratios" to retrieve interest income and revenue figures. Compute: (interest income + non-permissible revenue) / total revenue. **FAIL if >= 5%.** If >0% but <5%, compute purification ratio.
5. Optionally call `get_financial_analysis` for deeper profitability decomposition (warn user: async ~2-5 min).
6. Call `get_score_analysis` for quality trajectory.
7. Present compliance verdict with all three ratio values and pass/fail per threshold.

**For portfolio screening:**
1. For each holding, run the single-stock compliance check (steps 1-7 above).
2. Call `check_portfolio_redundancy` on compliant holdings only. **Sanity-check the response** (apply only when compliant holdings count N≥8 to avoid false-positives on small compliant sets where natural concentration is expected): if compliant holdings have >60% concentration in a single sector but `sector_concentration: {}` is empty and `"well-diversified"` is returned, the tool's concentration detection has silently failed — compute concentration client-side from per-holding sectors and flag the tool bug in output. For N<8, skip the sanity-check entirely; small concentrated halal subsets are an expected screening outcome, not a tool bug. **Rationale for N=8 cutoff:** at N=8 a >60% single-sector share requires ≥5 holdings clustered in one sector, which is unlikely from natural Shariah filtering (which typically excludes ~3 sectors broadly, leaving the residual spread across ≥4–5 sectors); at N≤7 the same share can result from 4 holdings and is consistent with screening outcome, not a tool defect. Tune the cutoff only if production data shows the false-positive rate diverging from this assumption.
3. For non-compliant holdings, call `build_stock_universe` with "[sector]" to find alternatives, then screen those alternatives through the same compliance check.
4. Call `get_peer_snapshot` on compliant alternatives to score them.

## Output Format

- **Screening Criteria** (AAOIFI/DJIM thresholds as listed above)
- **Compliance Results** (table: symbol, compliant Y/N, reason if non-compliant)
- **Key Ratios** (debt/assets %, interest-bearing/assets %, non-permissible revenue %)
- **Purification Amount** (if applicable — percentage of dividends requiring purification)
- **Alternatives** (for non-compliant holdings: scored compliant replacements in same sector)
- **Compliant Portfolio** (if portfolio mode: restructured allocation with only halal holdings)
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top: `**<client_name>** Shariah screen`. Logo handling per integration-pattern.md §5.
- **Provenance** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second Provenance line.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (Provenance) when composing the Output Format.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

> *"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*

> These are analytical outputs based on AAOIFI/DJIM screening thresholds applied to Parallax financial data, not investment advice or a fatwa. Consult a qualified Shariah advisor for binding rulings.
