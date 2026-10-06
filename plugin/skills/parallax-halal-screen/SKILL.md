---
name: parallax-halal-screen
description: "Shariah-compliant stock screening: filter for halal investments, check compliance flags, explain screening criteria, and suggest compliant alternatives via Parallax MCP tools. Single stock or an existing holdings list. NOT for general thematic screening (use /parallax-thematic-screen), not for portfolio construction (use /parallax-portfolio-builder), not for accounting-quality screening (use /parallax-earnings-quality)."
---

<!-- white-label: integration-pattern.md -->

# Halal / Shariah Screen

## When not to use

- General thematic screening → use /parallax-thematic-screen
- Portfolio construction → use /parallax-portfolio-builder
- Accounting-quality (non-compliance) screening → use /parallax-earnings-quality

## Gotchas

- Expected Parallax spend: ~4 tokens single stock (+5 with the optional Palepu call); ~4–5 per holding in portfolio mode (`_parallax/token-costs.md`).
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §1 RIC resolution, §3 parallel execution, §4 and **§4.0** (this screen is a gate: it fails closed to `UNVERIFIED`), §11 sensitivity, §12 framing, §13 audience mode, §14 host primitives.
- The thresholds below are this skill's own fixed values (commonly used screening ratios), not a claim of conformance to any named standard; they are also the published cutoffs that conventions §11 sensitivity lines rely on. No helper computes them: the arithmetic is three ratios from two `get_financials` calls (`balance_sheet` supplies Ratios 1–2, `income` supplies Ratio 3), stated explicitly so a reader can check it.
- Parallax has no field for "non-permissible revenue" (haram-segment revenue) under any statement — confirmed absent from `ratios`, `income`, and `balance_sheet`. Ratio 3 and the purification percentage are interest income only; this is permanent, not a per-run gap, and never resolves with a retry.
- `interest_investment_income_operating` and `interest_investment_income_non_operating` are frequently null in the live `income` response and are dropped entirely rather than returned as `0` (confirmed: a live AAPL.O probe returned neither field). Treat an absent field the same as a null one — `UNVERIFIED`, never a silent `0` — so Ratio 3 renders `UNVERIFIED` on a routine run for many names, not as an anomaly.
- `explain_methodology` does NOT support shariah/halal — its valid concepts are value, quality, momentum, defensive, tactical, overall, factor_weighting, scoring.
- `get_financial_analysis` (Palepu) is async ~2–5 min — say so before calling it.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).
- Not a house-view consumer: no loader step, no audit row.

Screen stocks and portfolios for Shariah compliance using commonly used screening ratios applied to Parallax financial data.

## Screening Thresholds

These are the Shariah compliance thresholds applied by this skill. They are commonly used screening ratios, not a claim of conformance to any named published standard. They are applied to data retrieved from `get_financials`.

| Ratio | Threshold | Pass condition |
|-------|-----------|----------------|
| Total debt / Total assets | < 33% | Low leverage — no excessive interest-bearing debt |
| Cash and short-term investments / Total assets | < 33% | Limited exposure to interest-bearing instruments |
| Interest income / Total revenue | < 5% | Negligible income from interest-bearing activities |

Debt and interest-bearing-asset ratios are measured against **total assets**, not against market capitalization. Published Shariah screening standards differ from one another on the denominator, on the exact cutoffs, and on the set of ratios screened, so a verdict from this skill is not interchangeable with any named index provider's or standards body's screen. The 33% and 5% cutoffs are this skill's own fixed values; they are not maintained to conform to any published standard.

**Ratio 2's numerator is a single field, not a sum.** `get_financials(balance_sheet)` returns one combined `cash_and_short_term_investments` figure; there is no separate interest-bearing-securities field to add to it. That field is the full numerator — there is nothing else to fetch.

**Ratio 3 is interest income only — Parallax has no field for haram-segment ("non-permissible") revenue, under any statement, for any company.** No vendor in this data model reports a halal/haram revenue split. This is a permanent scope limitation of the screen, not a per-run data gap: Ratio 3 and the purification percentage below are narrower than a published standard that also nets off haram-segment revenue (e.g. impermissible-business income on an otherwise-compliant company), and the rendered Key Ratios and the bespoke Shariah note must say so plainly rather than implying a broader figure was computed.

**Business activity screen (qualitative):** The company's primary business must not be in prohibited industries (conventional banking/insurance, alcohol, tobacco, gambling, pork, weapons, adult entertainment). This is assessed from `get_company_info` sector/industry data.

**Purification ratio:** If a stock passes all quantitative screens but has non-zero interest income, the purification percentage = (interest income / total income). Shareholders should donate that percentage of dividends received. Because Parallax carries no haram-revenue field (see above), this percentage reflects interest income only and may understate what some Shariah boards would require purified on a company with impermissible-business income.

## Usage

```
/parallax-halal-screen AAPL.O
/parallax-halal-screen [{"symbol":"AAPL.O","weight":0.25},{"symbol":"JPM.N","weight":0.25},{"symbol":"JNJ.N","weight":0.25},{"symbol":"XOM.N","weight":0.25}]
/parallax-halal-screen AAPL.O audience=client_safe
```

Two modes: single-stock compliance check, or screening of existing holdings. Building a compliant portfolio from a universe is not a mode of this skill — use `/parallax-portfolio-builder` with a halal constraint, then screen the result here. Optional `audience=` argument: `client_safe | internal_analyst`; precedence follows `parallax-conventions.md` §13.1.

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1). Portfolio mode runs Steps 1–4 per holding, then the portfolio additions in Step 4.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Steps 1–4) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: one symbol, or a holdings list; `audience=`.
4. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Symbols in RIC form (plain tickers → conventions §1). `call-tool` `get_company_info` per name (in parallel for a portfolio): the sector/industry drives the business-activity screen. **A prohibited industry (conventional banking/insurance, alcohol, tobacco, gambling, pork, weapons, adult entertainment) is decisive: mark the name NON-COMPLIANT and skip Step 2 for it** — no financial ratio can override it.

### Step 2 — Fetch (parallel batches)

For every name that passed Step 1, `call-tool` together: `get_financials(statement="balance_sheet")` (total debt, total assets, `cash_and_short_term_investments` — one combined field, not two); `get_financials(statement="income")` (`interest_investment_income_operating` + `interest_investment_income_non_operating` for interest income, `total_revenue`); `get_score_analysis` (quality trajectory). Optional, on request only: `get_financial_analysis` (async 2–5 min).

There is no field for "non-permissible revenue" anywhere in the Parallax data model — do not call `statement="ratios"` looking for it; it is not there either. Ratio 3's numerator is interest income alone (see Screening Thresholds above).

### Step 3 — Verify

**This screen is a gate — it fails closed per `parallax-conventions.md` §4.0.** If either `get_financials` call errors, returns empty, or returns null/missing values for any threshold input (total debt, total assets, `cash_and_short_term_investments`, `interest_investment_income_operating`, `interest_investment_income_non_operating`, `total_revenue`) after the §0.1 retry, the name's verdict is **`UNVERIFIED`** — not compliant, not non-compliant. Record which field or call was unavailable. "Non-permissible revenue" is never a threshold input here — it is permanently absent from the Parallax data model (see Gotchas), so it is excluded from Ratio 3 by design and never triggers `UNVERIFIED` on its own. An `UNVERIFIED` name is excluded from the Compliant Subset and from every aggregate over compliant holdings, and is never dropped silently. **Never estimate a missing ratio input** from sector, peers, a comparable company, or narrative text. A partial result is reportable: the computed ratios render, the missing one reads `UNVERIFIED`, and the overall verdict is `UNVERIFIED` because a threshold went unchecked. The Step 1 business-activity FAIL is unaffected: a prohibited-industry name is NON-COMPLIANT even if its ratios would have been unverifiable.

### Step 4 — Compute

Per name, from the Step 2 responses: total debt / total assets (**FAIL if ≥ 33%**); `cash_and_short_term_investments` / total assets (**FAIL if ≥ 33%**); (`interest_investment_income_operating` + `interest_investment_income_non_operating`) / `total_revenue` (**FAIL if ≥ 5%**; if > 0% and < 5%, purification ratio = interest income / total income — interest income only, since Parallax has no non-permissible-revenue field to add). Verdict: COMPLIANT / NON-COMPLIANT / UNVERIFIED.

**Portfolio mode additions.** `call-tool` `check_portfolio_redundancy` on **verified-compliant holdings only** (`UNVERIFIED` is not compliant); weights renormalise over that set and the report says so. Sanity check (only when compliant N ≥ 8): >60% in one sector with `sector_concentration: {}` and "well-diversified" returned means the tool's detection failed — compute concentration client-side and flag the tool bug; for N < 8 skip it (at N=8 a >60% share needs ≥5 names in one sector, unlikely from natural Shariah filtering; at N ≤ 7 four names can do it and that is a screening outcome, not a defect). For NON-COMPLIANT holdings, `build_stock_universe("[sector]")`, screen the alternatives through Steps 1–4, and `get_peer_snapshot` the compliant ones. **Never source alternatives for `UNVERIFIED` holdings** — an unscreened name has not been rejected; recommend a re-screen instead.

### Step 5 — Compose

Fill **Output Format** below in order: Branding Header per integration-pattern.md §5; audience mode per §13 (the Unverified Names section and every `UNVERIFIED` state are non-suppressible per §4.0); §11 sensitivity among computed ratios only (internal_analyst); §12 framing for Alternatives and Compliant Subset; `parallax-conventions.md §9.2` disclosure; standard disclaimer `parallax-conventions.md §9.1`; the bespoke Shariah note last.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/halal.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill halal-screen < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. If `run-shell` is absent, apply conventions §14.3 (render-gate row); the ratios themselves need no shell. No Step 7.

## Output Format

**Begin the response immediately with the rendered report — no preamble.** The first expected line is `## Screening Criteria`, or the Branding Header when active.

- **Screening Criteria** (commonly used screening ratios as listed above)
- **Plain-Language Summary** (under `audience=client_safe` only): 2-3 sentences stating the screen outcome counts in plain terms for a non-specialist reader; factor names carry the §13.3 gloss if used, no cutoff arithmetic, framed per §12 as informational with no directives. **State all three counts whenever any name is `UNVERIFIED`** — compliant, non-compliant, and unverified — in plain words (e.g. "2 holdings could not be screened because financial data was unavailable"). A summary reporting only "18 of 20 compliant" while 2 went unscreened is the §4.0 failure this skill exists to prevent, and it is the first line the client reads.
- **Compliance Results** (table: symbol, status ∈ `COMPLIANT` / `NON-COMPLIANT` / `UNVERIFIED`, reason if non-compliant or unverified). `UNVERIFIED` is a rendered state, never an omission: give the reason as the field or call that was unavailable (e.g. `UNVERIFIED — total_revenue unavailable from get_financials(income)`). Do not collapse the three states into a binary Y/N column, and never leave a screened symbol out of this table.
- **Unverified Names** (render only if any row is `UNVERIFIED`): one line per name stating what was missing and that the name is excluded from the Compliant Subset pending a re-screen. Per `parallax-conventions.md` §4.0 this is a data-integrity warning and is **not suppressible under `audience=client_safe`** — a client reading a compliant list must be able to tell "screened and cleared" from "could not be screened."
- **Key Ratios** (debt/assets %, cash-and-short-term-investments/assets %, interest-income/revenue %; render each unavailable ratio as `UNVERIFIED`, not as a blank, a dash, or an estimate). The third ratio is interest income only — state plainly that Parallax has no non-permissible-revenue field, rather than labeling it as if a broader figure were computed.
- **Verdict sensitivity**: the ratio nearest its cutoff (33% debt/assets, 33% cash-and-short-term-investments/assets, or 5% interest-income/revenue) and the arithmetic flip condition, per `parallax-conventions.md` §11 (internal_analyst mode only per conventions §13.2). Applies only to the three quantitative ratios above — never to the qualitative business-activity screen. **Select only among ratios that were actually computed**: an `UNVERIFIED` ratio has no distance to its cutoff, so it can never be the surfaced input, and a name whose overall verdict is `UNVERIFIED` renders no sensitivity line at all (per §11.2, omitting it is the compliant behavior — never infer a flip number from a missing input).
- **Purification Amount** (if applicable — percentage of dividends requiring purification)
- **Alternatives** (for non-compliant holdings: scored compliant replacements in same sector — informational candidates, not replacement instructions)
- **Compliant Subset** (if portfolio mode: the screened-compliant holdings and their current weights — an informational screen result per conventions §12, not a rebalancing instruction; for construction use /parallax-portfolio-builder then re-screen). Contains **verified-compliant names only** — `UNVERIFIED` holdings are excluded per conventions §4.0. If any were excluded, state the count and that weights were renormalised over verified-compliant names, so the subset is never mistaken for a full screen of the portfolio.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top: `**<client_name>** Shariah screen`. Logo handling per integration-pattern.md §5.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

> These are analytical outputs based on commonly used Shariah screening ratios (debt and interest-bearing-asset thresholds measured against total assets) applied to Parallax financial data, not investment advice or a fatwa. The non-permissible-income ratio and purification percentage reflect interest income only — Parallax has no field for haram-segment revenue — so this screen is narrower on that dimension than a standard that nets off impermissible-business revenue as well. Consult a qualified Shariah advisor for binding rulings.


## Failure modes

- Any threshold input unavailable after the retry: that name is `UNVERIFIED` with the missing field named; it is excluded from the Compliant Subset and its alternatives are not sourced.
- Prohibited industry: NON-COMPLIANT without financial calls.
- `check_portfolio_redundancy` coverage or detection failure: client-side concentration with the tool bug flagged (N ≥ 8 only).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- First line is `## Screening Criteria` or the Branding Header; Compliance Results lists every screened symbol with one of the three states and a reason for every non-compliant or unverified row.
- Unverified Names renders whenever any row is `UNVERIFIED`, in both audience modes; the Plain-Language Summary states all three counts.
- Compliant Subset (portfolio mode) contains verified-compliant names only and states any renormalisation.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure, the §9.1 disclaimer, and the Shariah note are present; expected spend stated (Gotchas).
