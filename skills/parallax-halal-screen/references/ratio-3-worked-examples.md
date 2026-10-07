# Ratio 3 worked examples

Documentation only — there is no executable test harness for this prose skill. These five cases illustrate Step 3 (Verify) and Step 4 (Compute) of `parallax-halal-screen/SKILL.md` for `interest_investment_income_operating` (`op`), `interest_investment_income_non_operating` (`non_op`), and `total_revenue`. Each component is floored at `max(x, 0)` before summing, per Gotchas and Screening Thresholds in SKILL.md. Figures below are illustrative inputs chosen to exercise the rule, not live Parallax responses (the live-probe evidence cited in SKILL.md — F.N FY2025, 7203.T FY2026-03 — is the basis for the flooring rule itself).

## 1. Ratio 1 fails; Ratio 3 missing

Inputs: total debt = 45, total assets = 100 → Ratio 1 = 45% (≥ 33%, FAIL). `cash_and_short_term_investments` = 10, total assets = 100 → Ratio 2 = 10% (< 33%, PASS). `op` absent, `non_op` absent, `total_revenue` = 500 → Ratio 3 `UNVERIFIED` (no field present to floor or sum).

Per Step 3's precedence ("a proven failure wins over a missing input"), the name is **NON-COMPLIANT** on Ratio 1. Ratio 3 still renders as `UNVERIFIED — interest_investment_income_operating and interest_investment_income_non_operating both unavailable` in Compliance Results and Key Ratios; it is not silently dropped. Verdict sensitivity selects among the failing ratios only, so it surfaces Ratio 1 (45% vs. its 33% cutoff); the passing Ratio 2 cannot flip a NON-COMPLIANT verdict. The line states the overall verdict would move to `UNVERIFIED`, not `COMPLIANT`, if Ratio 1 fell below 33%, because Ratio 3 remains unchecked.

## 2. Single field ≥ 5%, other absent → lower-bound FAIL

Inputs: `op` = 30, `non_op` absent, `total_revenue` = 500. Floored `op` = 30. 30 / 500 = 6.0% ≥ 5%.

The known field alone already clears the cutoff, so the ratio is at least 6.0% regardless of the absent field's true value (it can only add after flooring, never subtract). Verdict: **NON-COMPLIANT**.

- Compliance Results: `NON-COMPLIANT — interest_investment_income_operating alone is 6.0% of total_revenue (≥ 5%); interest_investment_income_non_operating unavailable`
- Key Ratios: `Interest-and-investment income / Total revenue: ≥ 6.0% (lower bound; interest_investment_income_non_operating unavailable)`
- Verdict sensitivity: Ratio 3 gets no exact distance — a lower bound has none. If Ratios 1 and 2 pass, Ratio 3 is the only failing ratio, so no passing ratio is named either: the line states that the verdict rests on a lower bound, that the full Ratio 3 is unknown because `interest_investment_income_non_operating` is unavailable, and that the verdict would change only if the measured interest-and-investment income fell below 5% of `total_revenue`.

## 3. Single field < 5%, other absent → UNVERIFIED

Inputs: `op` absent, `non_op` = 10, `total_revenue` = 500. Floored `non_op` = 10. 10 / 500 = 2.0% < 5%.

The known field alone does not clear the cutoff, and the absent field's true value is unknown — it could be large enough to push the true sum to or above 5%. Per the owner decision that Ratio 3 PASS requires both fields present, this case proves neither a pass nor a fail. Verdict: Ratio 3 **`UNVERIFIED`** — `interest_investment_income_operating unavailable; interest_investment_income_non_operating alone is 2.0% (< 5%), not sufficient to confirm either outcome`. Overall verdict is `UNVERIFIED` unless Ratio 1 or 2 independently fails.

## 4. Both fields present → Ratio 3 computed normally

Inputs: `op` = 8, `non_op` = 12, `total_revenue` = 500. Floored sum = 20. 20 / 500 = 4.0% < 5%, and both fields are present, so this is a genuine **PASS** on Ratio 3 (not `UNVERIFIED`). If Ratios 1 and 2 also pass, overall verdict: **COMPLIANT**. Because the floored sum is non-zero (> 0% and < 5%, both fields present), the purification ratio applies: purification = 20 / 500 = 4.0% of dividends received — the same denominator as Ratio 3.

## 5. One field ≥ 5%, other present and negative → still FAIL after flooring

Inputs: `op` = 28 (positive), `non_op` = -10 (negative — a loss, per the live-probe evidence that this field can be negative), `total_revenue` = 500.

Without flooring, a naive sum would be 28 + (-10) = 18, and 18 / 500 = 3.6% < 5% — which would wrongly let a loss in one field offset income in the other. With the required floor, `max(non_op, 0)` = 0, so the sum is 28 + 0 = 28, and 28 / 500 = 5.6% ≥ 5%.

Verdict: **NON-COMPLIANT** — the floored `op` field alone already proves the FAIL (case 2's logic), and the negative `non_op` field cannot rescue it. Compliance Results: `NON-COMPLIANT — interest_investment_income_operating alone is 5.6% of total_revenue (≥ 5%); interest_investment_income_non_operating is present but negative (-10) and floored at 0, not netted against the operating field`.

## Verdict sensitivity with more than one failing ratio

A NON-COMPLIANT verdict flips only if every failing ratio falls below its cutoff, so the sensitivity line lists every failing ratio, not just one.

### 6. Ratio 1 fails exactly; Ratio 3 fails on a lower bound

Inputs: total debt = 40, total assets = 100 → Ratio 1 = 40% (FAIL). `cash_and_short_term_investments` = 10 → Ratio 2 = 10% (PASS). `op` = 30, `non_op` absent, `total_revenue` = 500 → Ratio 3 ≥ 6.0% (lower-bound FAIL, as in case 2). Verdict: **NON-COMPLIANT**.

Verdict sensitivity: both Ratio 1 and Ratio 3 would need to fall below their cutoffs. Ratio 1 is 7pp above 33%. Ratio 3 is a lower bound (≥ 6.0%, full value unknown because `interest_investment_income_non_operating` is unavailable), so it has no exact distance. Moving Ratio 1 below 33% alone leaves the name NON-COMPLIANT. Even if both cleared, the overall verdict could reach only `UNVERIFIED`: a Ratio 3 below 5% with `non_op` still absent is unchecked, per case 3.

### 7. Ratios 1 and 2 both fail exactly

Inputs: total debt = 45, `cash_and_short_term_investments` = 40, total assets = 100 → Ratio 1 = 45%, Ratio 2 = 40% (both FAIL). `op` = 8, `non_op` = 12, `total_revenue` = 500 → Ratio 3 = 4.0% (PASS, both fields present). Verdict: **NON-COMPLIANT**.

Verdict sensitivity: both Ratio 1 (12pp above 33%) and Ratio 2 (7pp above 33%) would need to fall below 33%. Moving either one alone leaves the name NON-COMPLIANT. No ratio is unchecked, so the flip target is `COMPLIANT`.
