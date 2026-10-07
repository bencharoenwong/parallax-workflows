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
- The thresholds below are this skill's own fixed values (commonly used screening ratios), not a claim of conformance to any named standard; they are also the published cutoffs that conventions §11 sensitivity lines rely on. No helper computes them: the arithmetic is three ratios from two `get_financials` calls (`balance_sheet` supplies Ratios 1–2, `income` supplies Ratio 3), stated explicitly so a reader can check it. Five worked cases for Ratio 3 (missing-input, lower-bound FAIL, UNVERIFIED, both-present PASS, negative-field-floored FAIL), plus two Verdict sensitivity cases with more than one failing ratio, are in `references/ratio-3-worked-examples.md` — documentation only, not an executable test.
- Parallax has no field for "non-permissible revenue" (haram-segment revenue) under any statement — confirmed absent from `ratios`, `income`, and `balance_sheet`. Ratio 3 and the purification percentage are interest-and-investment income only; this is permanent, not a per-run gap, and never resolves with a retry.
- `interest_investment_income_operating` and `interest_investment_income_non_operating` are observed absent or null in the live `income` response rather than returned as `0` — treat absent and null the same way, never as a silent `0` (confirmed: a live AAPL.O probe returned neither field as present). Live probes also confirm the present field's sign is not fixed: F.N FY2025 returned `interest_investment_income_non_operating = -1,308,000,000` (USD, negative) with `interest_investment_income_operating` absent; 7203.T FY2026-03 returned `interest_investment_income_non_operating = +1,391,126,000,000` (JPY, positive), also with `interest_investment_income_operating` absent. Because a negative value here is a loss, not negative interest-and-investment income, **floor each component at 0 before summing** — a loss must never offset or reduce the other component's contribution. This also means a field absent or null on a routine run is common, not an anomaly, so Ratio 3 renders `UNVERIFIED` on many names by design. A missing Ratio 3 never masks a proven failure: a name that fails Ratio 1 or 2, or whose one present interest-and-investment income field — floored at 0 — alone is ≥ 5% of `total_revenue`, is NON-COMPLIANT (Step 3) whether or not the other field is present.
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
| Interest-and-investment income / Total revenue | < 5% | Negligible income from interest-bearing and investment activities |

Debt and interest-bearing-asset ratios are measured against **total assets**, not against market capitalization. Published Shariah screening standards differ from one another on the denominator, on the exact cutoffs, and on the set of ratios screened, so a verdict from this skill is not interchangeable with any named index provider's or standards body's screen. The 33% and 5% cutoffs are this skill's own fixed values; they are not maintained to conform to any published standard.

**Ratio 2's numerator is a single field, not a sum.** `get_financials(balance_sheet)` returns one combined `cash_and_short_term_investments` figure; there is no separate interest-bearing-securities field to add to it. That field is the full numerator — there is nothing else to fetch.

**Ratio 3's numerator is interest-and-investment income (`interest_investment_income_operating` + `interest_investment_income_non_operating`), not pure interest income** (Parallax has no haram-segment revenue field — see Gotchas). The numerator may include permissible investment income alongside interest income, so a Ratio 3 FAIL means interest-and-investment income ≥ 5% of `total_revenue`, not interest income alone — render it that way rather than calling it "interest income." Ratio 3 and the purification percentage below are narrower than a published standard that also nets off haram-segment revenue (e.g. impermissible-business income on an otherwise-compliant company); the rendered Key Ratios and the Shariah note must say so.

**Each component is floored at 0 before summing (fail-closed)** — rationale and evidence in Gotchas. Because of the floor, a single present field that alone is ≥ 5% of `total_revenue` proves the ratio is at least 5% whether or not the other field is present; a present field below 5% with the other absent proves nothing and Ratio 3 stays `UNVERIFIED` (Step 3).

**Business activity screen (qualitative):** The company's primary business must not be in prohibited industries (conventional banking/insurance, alcohol, tobacco, gambling, pork, weapons, adult entertainment). This is assessed from `get_company_info` sector/industry data.

**Purification ratio:** If a stock passes all quantitative screens but has non-zero interest-and-investment income (floored at 0 per component, summed), the purification percentage = (interest-and-investment income / `total_revenue`) — the same denominator as Ratio 3, not total income. Shareholders should donate that percentage of dividends received. Because Parallax carries no haram-revenue field (see above), this percentage reflects interest-and-investment income only and may understate what some Shariah boards would require purified on a company with impermissible-business income.

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

For every name that passed Step 1, `call-tool` together: `get_financials(statement="balance_sheet", periods=1)` (most recent annual period: total debt, total assets, `cash_and_short_term_investments` — one combined field, not two); `get_financials(statement="income", periods=1)` (most recent annual period: `interest_investment_income_operating` + `interest_investment_income_non_operating` for interest-and-investment income, `total_revenue`); `get_score_analysis` (quality trajectory). Optional, on request only: `get_financial_analysis` (async 2–5 min).

**Period alignment.** `periods=1` returns the single most recent period from each call. Every input to every ratio for a given name must come from the same `perenddt` and the same period type (annual) — never pair an annual figure from one call with a quarterly or older-period figure from another. A field absent or null in that most-recent period is missing for this screen; do not reach back into an older row to backfill it, even if the same response happens to carry one — that would mix periods within a single ratio.

`statement="ratios"` carries no non-permissible-revenue field either (Gotchas) — don't call it looking for one. Ratio 3's numerator is interest-and-investment income, floored at 0 per component (see Screening Thresholds above).

### Step 3 — Verify

**This screen is a gate — it fails closed per `parallax-conventions.md` §4.0.** If either `get_financials` call errors, returns empty, or returns null/missing values for any threshold input (total debt, total assets, `cash_and_short_term_investments`, `interest_investment_income_operating`, `interest_investment_income_non_operating`, `total_revenue`) after the §0.1 retry, every ratio that depends on it is **`UNVERIFIED`**, and so is the name's verdict unless a computed ratio fails (see below) — not compliant, not non-compliant. **A denominator at or below 0 is also a failure to verify, never a divide:** `total_assets ≤ 0` makes Ratios 1 and 2 `UNVERIFIED`; `total_revenue ≤ 0` makes Ratio 3 `UNVERIFIED`. Record which field, call, or denominator was unavailable. "Non-permissible revenue" is never a threshold input here (see Gotchas), so it never triggers `UNVERIFIED` on its own. An `UNVERIFIED` name is excluded from the Compliant Subset and from every aggregate over compliant holdings, and is never dropped silently. **Never estimate a missing ratio input** from sector, peers, a comparable company, or narrative text. A partial result is reportable: the computed ratios render and the missing one reads `UNVERIFIED`. **A proven failure wins over a missing input:** if any ratio that could be computed is at or above its cutoff, the overall verdict is NON-COMPLIANT whatever the state of the other inputs. For Ratio 3, floor each present field at 0, then: if one interest-and-investment income field is present and — after flooring — alone is ≥ 5% of `total_revenue`, that lower bound proves the FAIL whether or not the other field is present, negative, or absent; a present field below 5% proves nothing when the other field is absent and Ratio 3 stays `UNVERIFIED`. **Ratio 3 can only PASS (render a value below 5%, not `UNVERIFIED`) when both fields are present** for that period — if `interest_investment_income_operating` is absent, a present `interest_investment_income_non_operating` below 5% is still `UNVERIFIED`, never COMPLIANT, because the absent field's true value is unknown and could push the sum to or above the cutoff. The overall verdict is `UNVERIFIED` only when no computed ratio fails and at least one threshold could not be checked. A NON-COMPLIANT name with an unchecked ratio still names the missing field in its reason. The Step 1 business-activity FAIL is unaffected: a prohibited-industry name is NON-COMPLIANT even if its ratios would have been unverifiable.

### Step 4 — Compute

Per name, from the Step 2 responses, with `total_assets > 0` and `total_revenue > 0` required (Step 3) before dividing: total debt / total assets (**FAIL if ≥ 33%**); `cash_and_short_term_investments` / total assets (**FAIL if ≥ 33%**); (max(`interest_investment_income_operating`, 0) + max(`interest_investment_income_non_operating`, 0)) / `total_revenue` (**FAIL if ≥ 5%**; if > 0% and < 5% — both fields present per Step 3 — purification ratio = floored interest-and-investment income / `total_revenue`, same denominator). Verdict, in this order: NON-COMPLIANT if any computed ratio (including the single-field Ratio 3 lower bound from Step 3) is at or above its cutoff; otherwise `UNVERIFIED` if any ratio could not be computed; otherwise COMPLIANT.

**Portfolio mode additions.** `call-tool` `check_portfolio_redundancy` on **verified-compliant holdings only** (`UNVERIFIED` is not compliant); weights renormalise over that set and the report says so. Sanity check (only when compliant N ≥ 8): >60% in one sector with `sector_concentration: {}` and "well-diversified" returned means the tool's detection failed — compute concentration client-side and flag the tool bug; for N < 8 skip it (at N=8 a >60% share needs ≥5 names in one sector, unlikely from natural Shariah filtering; at N ≤ 7 four names can do it and that is a screening outcome, not a defect). For NON-COMPLIANT holdings (including a name proven NON-COMPLIANT while another ratio was unchecked), `build_stock_universe("[sector]")`, screen the alternatives through Steps 1–4, and `get_peer_snapshot` the compliant ones. **Never source alternatives for `UNVERIFIED` holdings** — an unscreened name has not been rejected; recommend a re-screen instead.

### Step 5 — Compose

Fill **Output Format** below in order: Branding Header per integration-pattern.md §5; audience mode per §13 (the Unverified Names section and every `UNVERIFIED` state are non-suppressible per §4.0); §11 sensitivity per the Verdict sensitivity rule below (internal_analyst); §12 framing for Alternatives and Compliant Subset; `parallax-conventions.md §9.2` disclosure; standard disclaimer `parallax-conventions.md §9.1`; the bespoke Shariah note last.

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
- **Compliance Results** (table: symbol, status ∈ `COMPLIANT` / `NON-COMPLIANT` / `UNVERIFIED`, reason if non-compliant or unverified). `UNVERIFIED` is a rendered state, never an omission: give the reason as the field or call that was unavailable (e.g. `UNVERIFIED — total_revenue unavailable from get_financials(income)`). A Ratio 3 lower-bound FAIL (one field present and ≥ 5%, the other absent) is `NON-COMPLIANT`, not `UNVERIFIED`, with a reason naming both the proving field and the missing one, e.g. `NON-COMPLIANT — interest_investment_income_non_operating alone is 6.0% of total_revenue (≥ 5%); interest_investment_income_operating unavailable`. This reason must never contradict the Key Ratios row below it. Do not collapse the three states into a binary Y/N column, and never leave a screened symbol out of this table.
- **Unverified Names** (render only if any row is `UNVERIFIED`): one line per name stating what was missing and that the name is excluded from the Compliant Subset pending a re-screen. Per `parallax-conventions.md` §4.0 this is a data-integrity warning and is **not suppressible under `audience=client_safe`** — a client reading a compliant list must be able to tell "screened and cleared" from "could not be screened."
- **Key Ratios** (debt/assets %, cash-and-short-term-investments/assets %, interest-and-investment-income/revenue %; render each unavailable ratio as `UNVERIFIED`, not as a blank, a dash, or an estimate). **A Ratio 3 lower-bound FAIL renders as a lower bound, never as an exact value or as `UNVERIFIED`**: `≥ 6.0% (lower bound; interest_investment_income_operating unavailable)` — name the missing field, matching the Compliance Results reason for the same name.
- **Verdict sensitivity**: the arithmetic flip condition per `parallax-conventions.md` §11 (internal_analyst mode only per conventions §13.2). Applies only to the three quantitative ratios above (cutoffs 33% debt/assets, 33% cash-and-short-term-investments/assets, 5% interest-and-investment-income/revenue) — never to the qualitative business-activity screen. The line must describe what would flip the name's actual verdict. An `UNVERIFIED` ratio has no distance to its cutoff and is never surfaced; a name whose overall verdict is `UNVERIFIED` renders no sensitivity line at all (per §11.2, omitting it is the compliant behavior — never infer a flip number from a missing input). A Ratio 3 lower-bound FAIL has no exact distance (its true value could be higher), so it is never ranked by distance or given one. **COMPLIANT name**: surface the computed ratio nearest its cutoff; the verdict flips to NON-COMPLIANT at that cutoff. **NON-COMPLIANT name**: the verdict flips only if every failing ratio falls below its cutoff; a passing ratio cannot flip it. With one failing ratio, state its distance to its cutoff — or, if it is a Ratio 3 lower bound, state that the verdict rests on a lower bound, that the full Ratio 3 is unknown because the named field is unavailable, and that the verdict would change only if the measured interest-and-investment income fell below 5% of `total_revenue`. With two or more failing ratios, state that all of them would need to fall below their cutoffs and list each with its distance, marking any Ratio 3 lower bound as a bound with unknown full value. **Flip target**: `COMPLIANT` only if no ratio is unchecked and no failing ratio is a Ratio 3 lower bound (clearing a lower bound leaves an interest field absent, so Ratio 3 becomes unchecked); otherwise `UNVERIFIED`, never `COMPLIANT`.
- **Purification Amount** (if applicable — percentage of dividends requiring purification)
- **Alternatives** (for non-compliant holdings: scored compliant replacements in same sector — informational candidates, not replacement instructions)
- **Compliant Subset** (if portfolio mode: the screened-compliant holdings and their current weights — an informational screen result per conventions §12, not a rebalancing instruction; for construction use /parallax-portfolio-builder then re-screen). Contains **verified-compliant names only** — `UNVERIFIED` holdings are excluded per conventions §4.0. If any were excluded, state the count and that weights were renormalised over verified-compliant names, so the subset is never mistaken for a full screen of the portfolio.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top: `**<client_name>** Shariah screen`. Logo handling per integration-pattern.md §5.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

> These are analytical outputs based on commonly used Shariah screening ratios (debt and interest-bearing-asset thresholds measured against total assets) applied to Parallax financial data, not investment advice or a fatwa. The non-permissible-income ratio and purification percentage reflect interest-and-investment income only — Parallax has no field for haram-segment revenue — so this screen is narrower on that dimension than a standard that nets off impermissible-business revenue as well. Consult a qualified Shariah advisor for binding rulings.


## Failure modes

- Any threshold input unavailable after the retry, and no computed ratio fails: that name is `UNVERIFIED` with the missing field named; it is excluded from the Compliant Subset and its alternatives are not sourced. If a computed ratio fails, the name is NON-COMPLIANT and gets alternatives.
- `total_assets ≤ 0` or `total_revenue ≤ 0`: the ratios that denominator feeds (1 and 2, or 3 respectively) are `UNVERIFIED`, never divided by a non-positive number.
- Ratio 3 lower-bound FAIL (one field present and ≥ 5%, the other absent): NON-COMPLIANT, not `UNVERIFIED` — see Step 3 and the Key Ratios / Verdict sensitivity rendering rules in Output Format.
- Prohibited industry: NON-COMPLIANT without financial calls.
- `check_portfolio_redundancy` coverage or detection failure: client-side concentration with the tool bug flagged (N ≥ 8 only).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- First line is `## Screening Criteria` or the Branding Header; Compliance Results lists every screened symbol with one of the three states and a reason for every non-compliant or unverified row.
- Unverified Names renders whenever any row is `UNVERIFIED`, in both audience modes; the Plain-Language Summary states all three counts.
- Compliant Subset (portfolio mode) contains verified-compliant names only and states any renormalisation.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure, the §9.1 disclaimer, and the Shariah note are present; expected spend stated (Gotchas).
