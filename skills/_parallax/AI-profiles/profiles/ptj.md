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
factor_tilts_notes: "PTJ-style is not characterized by Parallax factor loadings. It is characterized by technical trend identification, macroeconomic regime positioning, and volatility-based asymmetric sizing."
leverage_overlay: null
output_shape: inferred_exposure_verdict
tool_sequence:
  - list_macro_countries
  - macro_analyst:component=tactical
  - get_company_info
  - get_score_analysis
  - get_technical_analysis
  - get_stock_outlook:aspect=risk_return
  - get_peer_snapshot
required_factors_present: []
thresholds:
  channel_t_technical: "get_technical_analysis trend direction POSITIVE or STRONG_POSITIVE AND get_score_analysis Momentum sub-trend positive"
  channel_t_partial: "exactly one of: trend direction POSITIVE/STRONG_POSITIVE OR momentum sub-trend positive (not both); OR get_technical_analysis unavailable and Momentum score >= 6 with trend upward"
  channel_m_macro: "macro_analyst tactical view compatible with home market or sector tailwind"
  channel_m_partial: "macro view is neutral, or mixed across exposure markets (some favor, others do not)"
  channel_v_volatility: "get_stock_outlook risk_return analyst upside target >= 15% AND Momentum factor score >= 5"
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

Paul Tudor Jones's philosophy, documented at length in Jack Schwager's 1989 *Market Wizards*, centers on three inseparable principles: **(1) strict technical trend-following via the 200-day moving average**, **(2) macroeconomic regime overlay to validate that trends are substantive rather than noise**, and **(3) aggressive risk/reward discipline enforcing a 5:1 payoff ratio**. Jones explicitly refuses to average losing trades and operates within a volatility-responsive position-sizing framework. Michael Covel's 2004 *Trend Following* provides historical evidence that this composite approach—technical momentum filtered through macro regime clarity—persists as a rewarding anomaly across 150+ years of financial data, surviving multiple market paradigm shifts.

## What this profile does

PTJ-style operates in single-ticker mode only: the user provides one equity ticker, and the profile evaluates it across three independent **conviction channels**:

- **Channel T — Technical setup:** Does the stock exhibit positive or strong-positive trend direction (via `get_technical_analysis`) AND upward momentum in the score-analysis 52-week trend? This channel captures whether the asset's price action aligns with PTJ's primary signal source.
- **Channel M — Macro regime:** Is the stock's home market's macroeconomic backdrop (from `macro_analyst`) currently favorable to risk-on positioning or sector-aligned to a tactical theme? This channel validates that the technical move is backed by fundamental macro momentum, not merely noise.
- **Channel V — Volatility and asymmetry:** Does the analyst price target show meaningful upside (>= 15% to target) AND does the stock exhibit established momentum (factor score >= 5) that supports the volatility regime? This channel enforces the 5:1 risk-reward principle and ensures capital is deployed only during asymmetric windows.

**Verdict logic:**
- All 3 channels flagged → `match` (high-conviction tri-channel alignment)
- Exactly 2 channels flagged → `partial_match` (two of three signals present; tactical entry possible)
- 0-1 channels flagged → `no_match` (insufficient confluence; capital preservation)

## What this profile does NOT capture

- **Trade execution and entry timing.** PTJ's actual trades involve intraday order-book reading, microstructure optimization, and precise entry/exit mechanics. Profile identifies regime + trend confluence; it does not time the exact market open or specify stops.
- **Position sizing and leverage.** PTJ runs concentrated, sized positions scaled by volatility. Profile is a tri-channel signal, not a position-sizing recommendation. Capital allocation is the user's responsibility.
- **Stop-loss and trailing logic.** The 200-day moving average acts as a structural capital-preservation gate in live trading. Profile identifies setups; actual stop placement and trade management require discretion.
- **Multi-asset FX and commodity positioning.** PTJ trades currencies, rates, and commodities alongside equities. Parallax is equity-centric; this profile cites macro context but does not recommend FX or rate trades.
- **Conviction timing and regime-break anticipation.** Soros-style "reflexivity loop" timing—predicting when a narrative-fundamentals divergence resolves—is beyond the scope. Profile surfaces current signals but cannot predict resolution dates.

## How to interpret the output

A `match` verdict means the stock currently exhibits three independently validated signals: established technical momentum, favorable macro regime context, and compelling risk/reward asymmetry. This is a PTJ-style high-conviction setup.

A `partial_match` verdict means two of the three channels align. This is sufficient for tactical positioning but carries higher regime-break risk; a missing macro validation or weak technical confirmation leaves room for whipsaws.

A `no_match` verdict is informative, not negative. It means the top-down lens currently finds insufficient confluence. Capital preservation is the priority; wait for regime shift or improved technical setup.

The **setup quality** rating (Grade A-D) provides an intuitive summary: Grade A (all channels) represents maximum alignment; Grade B/C represent degrading confluence; Grade D suggests the framework sees no actionable signal.

## Anchor test plan

Test the profile against known regime shifts where PTJ-style (technical+macro confluence) should have performed well or should have avoided false trades:
- **2008 GFC:** Expect matches during equity breakdown phases (technical negative, macro risk-off); expect no_match on false "value traps" (fundamental quality but no technical confirmation of continued selling).
- **2020 COVID:** Expect matches during March recovery (technical bounce, macro emergency policy, volatility opportunities); expect partial_matches during whipsaws (mixed signals).
- **2022 rate hike cycle:** Expect matches in defensive sectors (technicals + macro tightening alignment); expect no_match on "momentum traps" (positive sentiment but deteriorating macro backdrop).
- **SVB crisis March 2023:** Expect reduced conviction (partial_match or no_match) during crowded-trade unwind to test whether macro filter prevents catching knives.
