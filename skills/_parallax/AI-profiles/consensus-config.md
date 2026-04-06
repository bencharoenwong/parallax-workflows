# Parallax AI Investor Profile — Consensus Config

Consumed by `skills/AI-consensus/SKILL.md` (Phase 3). Defines the super-majority threshold and minimum-applicable-count floor for the cross-profile consensus calculation.

## Default configuration

```yaml
super_majority_threshold: 0.75      # 75% of applicable profiles must return match
minimum_applicable_count: 3         # consensus meaningless below this floor
rounding: ceiling                   # required_matches = ceil(threshold * applicable_count)
```

## How the math works

Let `A` = number of applicable profiles (profiles that successfully ran their tool_sequence and returned a verdict of `match`, `partial_match`, or `no_match`; excludes `skipped`).

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
| 2 | 2 | 3 | INSUFFICIENT_PROFILES |
| 1 | 1 | 3 | INSUFFICIENT_PROFILES |

## Why these defaults

- **75% super-majority** — High enough to be informative (random-chance consensus is ~25% with 4 independent binary verdicts), low enough to survive one profile disagreeing in a structurally different way.
- **Minimum 3 applicable** — With only 2 profiles returning verdicts, "consensus" is just agreement between 2 sources, which is not informative. 3 is the lowest count where structural diversity can meaningfully be observed.
- **Ceiling rounding** — Rounds UP the required matches. This makes the threshold strictly conservative: 75% of 3 = 2.25 rounds to 3 (unanimity), not 2. Prevents the threshold from silently weakening when the applicable count is small.

## Partial matches

`partial_match` verdicts are NOT counted toward `M`. Only full `match` verdicts count. Partial matches are surfaced in the consensus output matrix but do not contribute to the super-majority signal.

This is intentional: if a stock is "partially Buffett-like and partially Klarman-like," that's not the same signal as "fully matches both Buffett and Klarman."

## Factor-level agreement surfacing

Separately from the super-majority math, the meta-skill surfaces a "shared factor signal" section listing factors/criteria that were flagged by multiple profiles (match OR partial_match). See design spec §3.5.1. The shared factor signal is informative regardless of whether the super-majority threshold is met.

## Tuning notes

Do NOT tune these defaults without rerunning all anchor tests across all profiles. If the threshold changes, the meaning of "consensus signal: YES" changes with it.

If future experience shows the threshold is too strict (nothing ever hits YES) or too loose (everything hits YES), the tuning conversation should start with: "What's the base rate of YES across a sample of 50 large-cap stocks over the last quarter?" Target ~10-20% of stocks hitting the signal. If it's 0% or 80%, the threshold is wrong.
