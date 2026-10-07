# Ratio 3 worked examples

Documentation only — there is no executable test harness for this prose skill. These five cases illustrate Step 3 (Verify) and Step 4 (Compute) of `parallax-halal-screen/SKILL.md` for `interest_investment_income_operating` (`op`), `interest_investment_income_non_operating` (`non_op`), and `total_revenue`. Each component is floored at `max(x, 0)` before summing, per Gotchas and Screening Thresholds in SKILL.md. Figures below are illustrative inputs chosen to exercise the rule, not live Parallax responses (the live-probe evidence cited in SKILL.md — F.N FY2025, 7203.T FY2026-03 — is the basis for the flooring rule itself).

## 1. Ratio 1 fails; Ratio 3 missing

Inputs: total debt = 45, total assets = 100 → Ratio 1 = 45% (≥ 33%, FAIL). `cash_and_short_term_investments` = 10, total assets = 100 → Ratio 2 = 10% (< 33%, PASS). `op` absent, `non_op` absent, `total_revenue` = 500 → Ratio 3 `UNVERIFIED` (no field present to floor or sum).

Per Step 3's precedence ("a proven failure wins over a missing input"), the name is **NON-COMPLIANT** on Ratio 1. Ratio 3 still renders as `UNVERIFIED — interest_investment_income_operating and interest_investment_income_non_operating both unavailable` in Compliance Results and Key Ratios; it is not silently dropped. Verdict sensitivity selects among Ratios 1 and 2 (the two computed ratios) — Ratio 1 is nearer its cutoff (45% vs. 33%, against Ratio 2's 10% vs. 33%) — and states the overall verdict would move to `UNVERIFIED`, not `COMPLIANT`, if Ratio 1 fell below 33%, because Ratio 3 remains unchecked.

## 2. Single field ≥ 5%, other absent → lower-bound FAIL

Inputs: `op` = 30, `non_op` absent, `total_revenue` = 500. Floored `op` = 30. 30 / 500 = 6.0% ≥ 5%.

The known field alone already clears the cutoff, so the ratio is at least 6.0% regardless of the absent field's true value (it can only add after flooring, never subtract). Verdict: **NON-COMPLIANT**.

- Compliance Results: `NON-COMPLIANT — interest_investment_income_operating alone is 6.0% of total_revenue (≥ 5%); interest_investment_income_non_operating unavailable`
- Key Ratios: `Interest-and-investment income / Total revenue: ≥ 6.0% (lower bound; interest_investment_income_non_operating unavailable)`
- Verdict sensitivity: excluded — a lower bound has no exact distance to the cutoff.

## 3. Single field < 5%, other absent → UNVERIFIED

Inputs: `op` absent, `non_op` = 10, `total_revenue` = 500. Floored `non_op` = 10. 10 / 500 = 2.0% < 5%.

The known field alone does not clear the cutoff, and the absent field's true value is unknown — it could be large enough to push the true sum to or above 5%. Per the owner decision that Ratio 3 PASS requires both fields present, this case proves neither a pass nor a fail. Verdict: Ratio 3 **`UNVERIFIED`** — `interest_investment_income_operating unavailable; interest_investment_income_non_operating alone is 2.0% (< 5%), not sufficient to confirm either outcome`. Overall verdict is `UNVERIFIED` unless Ratio 1 or 2 independently fails.

## 4. Both fields present → Ratio 3 computed normally

Inputs: `op` = 8, `non_op` = 12, `total_revenue` = 500. Floored sum = 20. 20 / 500 = 4.0% < 5%, and both fields are present, so this is a genuine **PASS** on Ratio 3 (not `UNVERIFIED`). If Ratios 1 and 2 also pass, overall verdict: **COMPLIANT**. Because the floored sum is non-zero (> 0% and < 5%, both fields present), the purification ratio applies: purification = 20 / 500 = 4.0% of dividends received — the same denominator as Ratio 3.

## 5. One field ≥ 5%, other present and negative → still FAIL after flooring

Inputs: `op` = 28 (positive), `non_op` = -10 (negative — a loss, per the live-probe evidence that this field can be negative), `total_revenue` = 500.

Without flooring, a naive sum would be 28 + (-10) = 18, and 18 / 500 = 3.6% < 5% — which would wrongly let a loss in one field offset income in the other. With the required floor, `max(non_op, 0)` = 0, so the sum is 28 + 0 = 28, and 28 / 500 = 5.6% ≥ 5%.

Verdict: **NON-COMPLIANT** — the floored `op` field alone already proves the FAIL (case 2's logic), and the negative `non_op` field cannot rescue it. Compliance Results: `NON-COMPLIANT — interest_investment_income_operating alone is 5.6% of total_revenue (≥ 5%); interest_investment_income_non_operating is present but negative (-10) and floored at 0, not netted against the operating field`.
