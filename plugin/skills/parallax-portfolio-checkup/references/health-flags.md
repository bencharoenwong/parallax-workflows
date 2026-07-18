# Portfolio Health Flag System

## Health Flags

5 flags evaluated against portfolio data. Each flag is binary (triggered or not). The portfolio-level (verified-holdings weighted-average) definitions below are the canon used by `parallax-portfolio-checkup`. `parallax-client-review` and `parallax-rebalance` apply the same taxonomy and threshold values at **holding level** — their binding holding-level conditions live in `parallax-client-review/references/recommendation-matrix.md`; keep the two files in sync when changing any threshold value.

| Flag | Condition | Source (V2 primary / V1 fallback) | Threshold |
|---|---|---|---|
| **Low Score** | Portfolio overall score is weak | `get_peer_snapshot` aggregate (V2) / `quick_portfolio_scores` (V1) — verified-holdings weighted average | Overall ≤ 5.0 |
| **Concentration** | Single holding too large or top-3 dominate | Holdings weights (computed over original holdings, not just verified) | Any single >15% OR top-3 >45% |
| **Redundancy** | Multiple overlapping positions | `check_portfolio_redundancy` | ≥ 2 redundant pairs |
| **Value Trap** | Portfolio-weighted value score is low | `get_peer_snapshot.value` aggregate (V2) / `quick_portfolio_scores` (V1) — verified-holdings weighted average | Portfolio value score ≤ 3.0 |
| **Macro Misalignment** | Overweight in sectors with negative tactical outlook | `macro_analyst` (tactical), evaluated against verified-holdings sector weights | Holdings overweight in unfavourable sectors |

## Threshold calibration scope

The 15% single-holding / 45% top-3 concentration cutoffs (and the <7-holding structural caveat in `parallax-conventions.md`) are calibrated for concentrated advisor/retail-scale books; on institutional-scale books they rarely trigger. Scale-aware (percentile/HHI) thresholds and per-mandate overrides are a documented roadmap item — until then, state this calibration scope in output when the book exceeds ~30 holdings.

## Health Status Labels

| Status | Flag Count | Plain-Language Frame |
|---|---|---|
| **Healthy** | 0 flags | "Your portfolio looks solid." |
| **Monitor** | 1-2 flags | "A couple of items to keep an eye on." |
| **Attention** | 3+ flags | "Some areas need a closer look." |

## Verdict sensitivity

Per `parallax-conventions.md` §11: report the 1-2 numeric flags nearest a Health Status boundary and the arithmetic condition that would move the portfolio toward the adjacent status tier. All four numeric flags below qualify. **Macro Misalignment does not** — it is a qualitative sector / tactical-view match, not a numeric cutoff, so it is never a candidate for this line.

| Flag | Cutoff | Distance computation |
|---|---|---|
| Low Score | Overall ≤ 5.0 | `5.0 − overall_score` (triggered) or `overall_score − 5.0` (not triggered) |
| Value Trap | Portfolio value score ≤ 3.0 | `3.0 − value_score` or `value_score − 3.0` |
| Concentration | Single > 15% OR top-3 > 45% | `15% − largest_single_weight` and `45% − top3_weight`; report whichever sub-condition is closer |
| Redundancy | ≥ 2 redundant pairs | `2 − pair_count` (a portfolio at exactly 1 pair is 1 pair from triggering) |

Rank all four (excluding Macro Misalignment) by absolute distance, then surface the 1-2 closest boundary-relevant candidates. A flag already triggered and a flag not yet triggered are both eligible, but the line must not imply a Health Status flip unless the flag-count boundary actually changes:

- Healthy (0 flags): state the nearest untriggered numeric flag and the condition that would move Health Status to Monitor.
- Monitor (1 flag): state the triggered numeric flag whose clearing would move Health Status to Healthy. If the only triggered flag is Macro Misalignment, state that no numeric flag can move the status to Healthy and optionally show the nearest untriggered numeric flag that would add a second Monitor flag.
- Monitor (2 flags): state the nearest untriggered numeric flag whose triggering would move Health Status to Attention.
- Attention (3+ flags): state the triggered numeric flag(s) nearest clearing and how many total flags must clear to return to Monitor. If more than two flags must clear, show the two closest numeric clearing candidates and explicitly state that both alone are insufficient.

A score sitting exactly on its cutoff (distance 0) is reported explicitly per §11.3, not rounded away.

## Mixed-Exchange Fallback

This is **tier 3** of the fallback ladder defined in the SKILL.md Step A.5 — invoked only when V2 (`get_peer_snapshot` per-holding) AND V1 (`quick_portfolio_scores`) both return coverage <50% by weight.

When triggered:

1. Split holdings by exchange suffix (group `.O`/`.N` together as US, `.L` as UK, etc.).
2. Call `quick_portfolio_scores` for each exchange group separately.
3. Merge results into portfolio-weighted scores.
4. Note in output: "Scoring used split-and-merge due to partial coverage for [X, Y] symbols."

If coverage remains below 50% after split-and-merge, report available scores but flag: "Scoring coverage is limited — health flags may not reflect the full portfolio."

## Coverage Reliability Flags

- **Redundancy**: If `check_portfolio_redundancy` covers <60% of holdings, flag redundancy results as **"Low confidence — limited coverage."** Do not present redundancy pairs as definitive findings.
- **Scoring**: If any holding could not be scored after fallback, list unscored symbols explicitly.

## Macro Misalignment Check

Derive home markets from RIC suffixes across all holdings:
- `.O`, `.N` → United States
- `.L` → United Kingdom
- `.T` → Japan
- `.HK` → China/Hong Kong
- `.DE` → Germany
- `.PA` → France
- `.AX` → Australia
- `.OL` → Norway
- `.TW` → Taiwan
- `.KS` → South Korea

Call `list_macro_countries` to check coverage, then `macro_analyst` with component="tactical" for each unique covered market (cap at 3). Compare sector weights against tactical sector tilts to identify misalignment.
