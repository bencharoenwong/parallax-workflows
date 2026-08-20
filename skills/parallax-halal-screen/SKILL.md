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
- Shariah thresholds are hardcoded in this skill (commonly used screening ratios) — derive compliance from get_financials data
- get_financial_analysis (Palepu framework) is async ~2-5 min — warn user before calling
- Financial ratios from get_financials help verify debt/revenue compliance thresholds
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (7-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (About This Report) in Output Format.
- Cost: ~4 tokens single-stock, +5 optional if Palepu is called; ~4-5/holding in portfolio mode. Breakdown in `_parallax/token-costs.md`.

Screen stocks and portfolios for Shariah compliance using commonly used screening ratios applied to Parallax financial data.

## Screening Thresholds

These are the Shariah compliance thresholds applied by this skill. They are commonly used screening ratios, not a claim of conformance to any named published standard. They are applied to data retrieved from `get_financials`.

| Ratio | Threshold | Pass condition |
|-------|-----------|----------------|
| Total debt / Total assets | < 33% | Low leverage — no excessive interest-bearing debt |
| (Cash + interest-bearing securities) / Total assets | < 33% | Limited exposure to interest-bearing instruments |
| (Interest income + non-permissible revenue) / Total revenue | < 5% | Negligible income from haram activities |

Debt and interest-bearing-asset ratios are measured against **total assets**, not against market capitalization. Published Shariah screening standards differ from one another on the denominator, on the exact cutoffs, and on the set of ratios screened, so a verdict from this skill is not interchangeable with any named index provider's or standards body's screen. The 33% and 5% cutoffs are this skill's own fixed values; they are not maintained to conform to any published standard.

**Business activity screen (qualitative):** The company's primary business must not be in prohibited industries (conventional banking/insurance, alcohol, tobacco, gambling, pork, weapons, adult entertainment). This is assessed from `get_company_info` sector/industry data.

**Purification ratio:** If a stock passes all quantitative screens but has non-zero non-permissible income, the purification percentage = (non-permissible income / total income). Shareholders should donate that percentage of dividends received.

## Usage

```
/parallax-halal-screen AAPL.O
/parallax-halal-screen [{"symbol":"AAPL.O","weight":0.25},{"symbol":"JPM.N","weight":0.25},{"symbol":"JNJ.N","weight":0.25},{"symbol":"XOM.N","weight":0.25}]
/parallax-halal-screen AAPL.O audience=client_safe
```

Two modes: single-stock compliance check, or screening of existing holdings. Building a compliant portfolio from a universe is not a mode of this skill — use `/parallax-portfolio-builder` with a halal constraint, then screen the result here.
Optional `audience=` argument: `client_safe | internal_analyst`; precedence follows `parallax-conventions.md` §13.1.

## Workflow

JIT-load `_parallax/parallax-conventions.md` for RIC resolution, parallel execution, and fallback patterns.

### Step 0 — Tool loading

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call. Without this step, all Parallax tool calls below fail with "tool not found."

**For single stock compliance check:**
1. Call `get_company_info` to retrieve sector/industry — check against prohibited industries (banking, alcohol, tobacco, gambling, pork, weapons, adult entertainment). **If this screen FAILs, mark the stock non-compliant and skip steps 2-3 (financial calls) for that name** — a prohibited business activity is decisive regardless of financial ratios.
2. Call `get_financials` ONCE with statement "balance_sheet" to retrieve total debt, total assets, cash, and interest-bearing securities. Compute both ratios from the single response: total debt / total assets (**FAIL if >= 33%**) and (cash + interest-bearing securities) / total assets (**FAIL if >= 33%**).
3. Call `get_financials` with statement "ratios" to retrieve interest income and revenue figures. Compute: (interest income + non-permissible revenue) / total revenue. **FAIL if >= 5%.** If >0% but <5%, compute purification ratio.

   **This screen is a gate — it fails closed per `parallax-conventions.md` §4.0.** If either `get_financials` call in steps 2-3 errors, returns empty, or returns null/missing values for any input to a threshold (total debt, total assets, cash, interest-bearing securities, interest income, non-permissible revenue, total revenue) after the §4 retry, the name's verdict is **`UNVERIFIED`**, not compliant and not non-compliant. Record which field or call was unavailable. An `UNVERIFIED` name is excluded from the Compliant Subset and from any portfolio aggregate computed over compliant holdings, and it is never dropped silently. **Never estimate a missing ratio input** from sector, peers, a comparable company, or narrative text — an unavailable input stays unavailable. A partial result is reportable: if step 2 succeeds and step 3 fails, render the two computed ratios and mark the third `UNVERIFIED`; the overall verdict is still `UNVERIFIED` because a threshold went unchecked.

   The step-1 business-activity FAIL is decisive and unaffected: a prohibited-industry name is non-compliant even if steps 2-3 would have been unverifiable, because the qualitative screen already settled it.
4. Optionally call `get_financial_analysis` for deeper profitability decomposition (warn user: async ~2-5 min).
5. Call `get_score_analysis` for quality trajectory.
6. Present compliance verdict with all three ratio values and pass/fail per threshold — or `UNVERIFIED` with the unavailable field named, per step 3.

**For portfolio screening:**
1. For each holding, run the single-stock compliance check (steps 1-6 above; the business-activity short-circuit applies here too — prohibited names skip financial calls, saving ~3 tokens per prohibited holding). The step-3 gate rule applies per holding: a holding whose `get_financials` data is unavailable is `UNVERIFIED`, and one unverifiable holding never blocks the rest of the screen.
2. Call `check_portfolio_redundancy` on compliant holdings only. **`UNVERIFIED` holdings are not "compliant"** — exclude them here, from the Compliant Subset, and from every aggregate over compliant holdings. Weights renormalise over verified-compliant names only, and the report states that they were renormalised.
3. **Sanity-check the `check_portfolio_redundancy` response** (apply only when compliant holdings count N≥8 to avoid false-positives on small compliant sets where natural concentration is expected): if compliant holdings have >60% concentration in a single sector but `sector_concentration: {}` is empty and `"well-diversified"` is returned, the tool's concentration detection has silently failed — compute concentration client-side from per-holding sectors and flag the tool bug in output. For N<8, skip the sanity-check entirely; small concentrated halal subsets are an expected screening outcome, not a tool bug. **Rationale for N=8 cutoff:** at N=8 a >60% single-sector share requires ≥5 holdings clustered in one sector, which is unlikely from natural Shariah filtering (which typically excludes ~3 sectors broadly, leaving the residual spread across ≥4–5 sectors); at N≤7 the same share can result from 4 holdings and is consistent with screening outcome, not a tool defect. Tune the cutoff only if production data shows the false-positive rate diverging from this assumption.
4. For non-compliant holdings, call `build_stock_universe` with "[sector]" to find alternatives, then screen those alternatives through the same compliance check. **Do not source alternatives for `UNVERIFIED` holdings** — an unscreened name has not been rejected, so proposing replacements would present a data gap as a compliance finding. Recommend re-running the screen for those names instead.
5. Call `get_peer_snapshot` on compliant alternatives to score them.

## Output Format

- **Screening Criteria** (commonly used screening ratios as listed above)
- **Plain-Language Summary** (under `audience=client_safe` only): 2-3 sentences stating the screen outcome counts in plain terms for a non-specialist reader; factor names carry the §13.3 gloss if used, no cutoff arithmetic, framed per §12 as informational with no directives. **State all three counts whenever any name is `UNVERIFIED`** — compliant, non-compliant, and unverified — in plain words (e.g. "2 holdings could not be screened because financial data was unavailable"). A summary reporting only "18 of 20 compliant" while 2 went unscreened is the §4.0 failure this skill exists to prevent, and it is the first line the client reads.
- **Compliance Results** (table: symbol, status ∈ `COMPLIANT` / `NON-COMPLIANT` / `UNVERIFIED`, reason if non-compliant or unverified). `UNVERIFIED` is a rendered state, never an omission: give the reason as the field or call that was unavailable (e.g. `UNVERIFIED — total revenue unavailable from get_financials(ratios)`). Do not collapse the three states into a binary Y/N column, and never leave a screened symbol out of this table.
- **Unverified Names** (render only if any row is `UNVERIFIED`): one line per name stating what was missing and that the name is excluded from the Compliant Subset pending a re-screen. Per `parallax-conventions.md` §4.0 this is a data-integrity warning and is **not suppressible under `audience=client_safe`** — a client reading a compliant list must be able to tell "screened and cleared" from "could not be screened."
- **Key Ratios** (debt/assets %, interest-bearing/assets %, non-permissible revenue %; render each unavailable ratio as `UNVERIFIED`, not as a blank, a dash, or an estimate)
- **Verdict sensitivity**: the ratio nearest its cutoff (33% debt/assets, 33% interest-bearing/assets, or 5% non-permissible-revenue) and the arithmetic flip condition, per `parallax-conventions.md` §11 (internal_analyst mode only per conventions §13.2). Applies only to the three quantitative ratios above — never to the qualitative business-activity screen. **Select only among ratios that were actually computed**: an `UNVERIFIED` ratio has no distance to its cutoff, so it can never be the surfaced input, and a name whose overall verdict is `UNVERIFIED` renders no sensitivity line at all (per §11.2, omitting it is the compliant behavior — never infer a flip number from a missing input).
- **Purification Amount** (if applicable — percentage of dividends requiring purification)
- **Alternatives** (for non-compliant holdings: scored compliant replacements in same sector — informational candidates, not replacement instructions)
- **Compliant Subset** (if portfolio mode: the screened-compliant holdings and their current weights — an informational screen result per conventions §12, not a rebalancing instruction; for construction use /parallax-portfolio-builder then re-screen). Contains **verified-compliant names only** — `UNVERIFIED` holdings are excluded per conventions §4.0. If any were excluded, state the count and that weights were renormalised over verified-compliant names, so the subset is never mistaken for a full screen of the portfolio.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top: `**<client_name>** Shariah screen`. Logo handling per integration-pattern.md §5.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second About This Report line.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

> These are analytical outputs based on commonly used Shariah screening ratios (debt and interest-bearing-asset thresholds measured against total assets) applied to Parallax financial data, not investment advice or a fatwa. Consult a qualified Shariah advisor for binding rulings.
