---
profile_id: ptj
display_name: PTJ-style
status: draft
public_anchor:
  type: book
  citation: "Schwager, J. D. (1989). Market Wizards: Interviews with Top Traders. John Wiley & Sons. ISBN 978-0471128014."
  doi_or_url: "N/A — book source."
  retrieved: 2026-05-01
  notes: "Schwager's extensive interviews with Paul Tudor Jones, documenting his philosophy in Jones's own words: five-to-one risk/reward discipline, trend-following via 200-day moving average, never averaging losing trades, macro overlay on technical signals."
secondary_anchor:
  citation: "Covel, M. (2004). Trend Following: How Great Traders Make Millions in Up or Down Markets. Prentice Hall."
  doi_or_url: "N/A — book source."
  notes: "Documents systematic trend-following framework and historical evidence of persistence across market regimes, providing academic-adjacent validation of PTJ's technical-macro composite."
direction: top_down
asset_class: multi_asset
factor_tilts: {}
factor_tilts_notes: "PTJ-style is not characterized by Parallax factor loadings. It is characterized by technical trend identification, macroeconomic regime context, and an analyst-upside/Momentum proxy; no volatility-based sizing is implemented."
leverage_overlay: null
output_shape: inferred_exposure_verdict
tool_sequence:
  - list_macro_countries
  - macro_analyst:component=tactical
  - get_company_info
  - get_score_analysis
  - get_technical_analysis
  - get_stock_outlook:aspect=analyst_targets
  - get_peer_snapshot
required_factors_present: []
thresholds:
  # Interpret technical prose qualitatively; no machine trend enum is required.
  channel_t_technical: "get_technical_analysis reads as a bullish trend (qualitative prose, not a required machine enum) AND get_score_analysis Momentum sub-trend positive"
  channel_t_partial: "exactly one of: a bullish technical read OR momentum sub-trend positive (not both); OR get_technical_analysis unavailable and Momentum score >= 6 with trend upward"
  channel_m_macro: "macro_analyst tactical view compatible with home market or sector tailwind"
  channel_m_partial: "macro view is neutral, or mixed across exposure markets (some favor, others do not)"
  # aspect=risk_return maps to trailing return/volatility, NOT an analyst
  # price target -- confirmed live, 2026-10-05. Analyst upside needs
  # aspect=analyst_targets (current/high/low/mean/median); compute
  # upside = (mean - current) / current.
  channel_v_volatility: "get_stock_outlook(aspect=analyst_targets) upside = (mean - current) / current >= 15% AND Momentum factor score >= 5"
  channel_v_partial: "analyst upside 8-15% OR Momentum >= 5 but upside < 8%"
  channels_for_match: 3
  channels_for_partial: 2
owner: parallax-workflows
last_legal_review: PENDING
last_anchor_test: PENDING
anchor_test_notes: "Validation pending against historical regime shifts (2008, 2020, 2022, SVB 2023). Test fixtures: JPM.N (expect match/partial during trending), XLE.N (macro-sensitive, conditional), NVDA.O (strong technical trend, expect T flagged), KO.N (negative control, expect no_match)."
---

# PTJ-style profile

## What the anchor documents

Paul Tudor Jones's philosophy, documented at length in Jack Schwager's 1989 *Market Wizards*, centers on three inseparable principles: **(1) strict technical trend-following via the 200-day moving average**, **(2) macroeconomic regime overlay to validate that trends are substantive rather than noise**, and **(3) aggressive risk/reward discipline enforcing a 5:1 payoff ratio**. Jones explicitly refuses to average losing trades and operates within a volatility-responsive position-sizing framework. Covel's 2004 *Trend Following* supplies context on trend-following; neither citation validates this product's analyst-upside/Momentum proxy.

## What this profile does

Single equity ticker only; three related channels share inputs and provide a descriptive rubric, not independent conviction signals.

- **Channel T — Technical:** bullish technical prose AND upward Momentum sub-trend → `FLAGGED`. Exactly one positive without a conflicting bearish/down predicate → `PARTIAL`; clearly negative evidence → `NOT_FLAGGED`. If original positive/partial and bearish/down predicates overlap, use `UNAVAILABLE — ambiguous profile rules`, never invent precedence. Technical timeout permits the existing Momentum ≥ 6 AND upward-trend proxy, capped at `PARTIAL`; missing/nonqualifying proxy leaves T `UNAVAILABLE`. Label the proxy explicitly.
- **Channel M — Macro:** risk-on/home-market compatibility or sector tailwind → `FLAGGED`; neutral/mixed → `PARTIAL`; risk-off without favorable exposure → `NOT_FLAGGED`. Missing macro evidence is `UNAVAILABLE`.
- **Channel V — Analyst-upside/Momentum proxy:** the legacy volatility label does not measure volatility. Require finite analyst mean/current and Momentum, with current > 0; upside = (mean − current) / current. Preserve original predicates: `FLAGGED` upside ≥ 15% AND Momentum ≥ 5; `PARTIAL` upside 8–15% OR Momentum ≥ 5 with upside < 8%; `NOT_FLAGGED` upside < 8% OR Momentum < 5. Overlaps, including the 15% boundary, yield `UNAVAILABLE — ambiguous profile rules`. Do not retune thresholds or select a winner. Missing/invalid evidence is `UNAVAILABLE`.

**Verdict:** any required channel unavailable → `skipped`, retaining verified observations. With all three evaluable: 3 FLAGGED → `match`, 2 → `partial_match`, 0–1 → `no_match`. PARTIAL channels do not count as FLAGGED. Omit conflicting legacy letter grades.

## What this profile does NOT capture

Analyst upside does not measure downside distribution, realized/implied volatility, 5:1 risk/reward or payoff asymmetry. T and V share Momentum evidence. Macro commentary does not validate a causal trend explanation or distinguish noise from signal. This rubric does not implement execution, entry timing, stops, leverage, position sizing or multi-asset FX/rates trading. Those concepts may be discussed by the cited sources; they are not verified properties of this implementation.

## How to interpret the output

A `match` reports three evaluable channels flagged under the documented rubric, not high conviction, an entry instruction, capital protection or an assurance of investment quality. A `partial_match` reports exactly two flagged channels with the remaining evaluated status shown. A `no_match` reports 0–1 flagged channels only when all required channels are evaluable; unknown evidence yields `skipped`, not a negative conclusion.

## Anchor test plan

Validation remains pending. Historical regime labels alone cannot establish the rubric's behavior or profitability; tests require timestamped inputs and the unchanged numerical predicates. Include explicit witnesses for technical proxy PARTIAL, missing channels and overlapping V predicates, preserving ambiguous cases as unavailable rather than fitting rules to desired historical trades.
