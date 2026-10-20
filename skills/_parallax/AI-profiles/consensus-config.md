# Parallax AI Investor Profile — Consensus Config

<!-- authority: contract -->
<!-- verified: 2026-09-05 -->
<!-- overrides: none -->

Consumed by `skills/parallax-ai-consensus/SKILL.md` (Phase 3). Defines the super-majority threshold and minimum-applicable-count floor for the cross-profile consensus calculation.

## Default configuration

```yaml
super_majority_threshold: 0.75      # 75% of applicable profiles must return match
minimum_applicable_count: 3         # consensus meaningless below this floor
rounding: ceiling                   # required_matches = ceil(threshold * applicable_count)
```

## How the math works

Let `A` = number of applicable profiles (profiles with verified identity and all required criteria evaluated, which returned a verdict of `match`, `partial_match`, or `no_match`; excludes `skipped`).

Let `M` = number of applicable profiles that returned `match` (NOT `partial_match`).

The super-majority signal is `YES` if and only if:
- `A >= minimum_applicable_count` AND
- `M >= ceil(super_majority_threshold * A)`

If `A < minimum_applicable_count`, the signal is `INSUFFICIENT_PROFILES` (not `NO`).

## Worked examples (v1 launch set: 4 profiles)

| Applicable (A) | Matches (M) | required_matches = ceil(0.75 × A) | Signal |
|---|---|---|---|
| 4 | 4 | 3 | YES |
| 4 | 3 | 3 | YES |
| 4 | 2 | 3 | NO |
| 4 | 1 | 3 | NO |
| 3 | 3 | 3 | YES (effectively unanimous for 3-profile case) |
| 3 | 2 | 3 | NO |
| 2 | 2 | 2 | INSUFFICIENT_PROFILES |
| 1 | 1 | 1 | INSUFFICIENT_PROFILES |

## Worked examples (v2: 5 profiles with PTJ)

| Applicable (A) | Matches (M) | required_matches = ceil(0.75 × A) | Signal |
|---|---|---|---|
| 5 | 5 | 4 | YES |
| 5 | 4 | 4 | YES |
| 5 | 3 | 4 | NO |
| 4 | 4 | 3 | YES |
| 4 | 3 | 3 | YES |
| 4 | 2 | 3 | NO |
| 3 | 3 | 3 | YES (effectively unanimous for 3-profile case) |
| 3 | 2 | 3 | NO |

**Note:** The 75% super-majority rule and ceiling rounding remain unchanged. With 5 profiles, a `YES` signal requires 4 matches (ceil(0.75 × 5) = 4). If one profile skips due to data unavailability, the calculation reverts to the 4-profile math (ceil(0.75 × 4) = 3 required).

## Why these defaults

- **75% super-majority** — A configured heuristic agreement threshold, not a probability or independent corroboration guarantee. Profiles reuse scores, financials, macro and Momentum inputs; no random-chance probability, statistical significance or investment-quality assurance follows from agreement.
- **Minimum 3 applicable** — The configured eligibility floor remains 3. A smaller evaluated set yields `INSUFFICIENT_PROFILES`; three related rubrics do not establish independent evidence.
- **Ceiling rounding** — Rounds UP the required matches. This makes the threshold strictly conservative: 75% of 3 = 2.25 rounds to 3 (unanimity), not 2. Prevents the threshold from silently weakening when the applicable count is small.

## Partial matches

`partial_match` verdicts are NOT counted toward `M`. Only full `match` verdicts count. Partial matches are surfaced in the consensus output matrix but do not contribute to the super-majority signal.

This is intentional: if a stock is "partially Buffett-like and partially Klarman-like," that's not the same signal as "fully matches both Buffett and Klarman."

## Factor-level agreement surfacing

Separately from the super-majority math, the meta-skill surfaces a "shared factor signal" section listing factors/criteria that were flagged by multiple profiles (match OR partial_match). See design spec §3.5.1. For each criterion, show the denominator of eligible matching/partial profiles that actually evaluated that criterion, and name excluded/unavailable profiles. Separate shared flags (≥2), single-profile flags (1), evaluated but not flagged, and unavailable/not applicable. Untested or missing criteria are not negative observations or demonstrated blind spots. The full-consensus denominator A includes only profiles with all required criteria evaluated; optional-context gaps do not exclude an otherwise complete profile. This is an agreement summary regardless of whether the super-majority threshold is met.

## Tuning notes

Do NOT tune these defaults without rerunning all anchor tests across all profiles. If the threshold changes, the meaning of "consensus signal: YES" changes with it.

If future experience shows the threshold is too strict (nothing ever hits YES) or too loose (everything hits YES), the tuning conversation should start with: "What's the base rate of YES across a sample of 50 large-cap stocks over the last quarter?" Target ~10-20% of stocks hitting the signal. If it's 0% or 80%, the threshold is wrong.
