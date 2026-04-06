---
profile_id: greenblatt
display_name: Greenblatt-style
status: active
public_anchor:
  type: book
  citation: "Greenblatt, J. (2006). The Little Book That Beats the Market. John Wiley & Sons. ISBN 978-0471733065."
  doi_or_url: "N/A — book source. Academic replication: Gray, W., Carlisle, T. (2012). Quantitative Value. John Wiley & Sons."
  retrieved: 2026-04-06
  notes: "Greenblatt's Magic Formula: rank stocks by return on capital (ROC) and earnings yield (EY), sum the ranks, take top decile. Greenblatt published the exact formula. Academic replication: Gray & Carlisle 2012."
secondary_anchor:
  citation: "Gray, W., Carlisle, T. (2012). Quantitative Value: A Practitioner's Guide to Automating Intelligent Investment and Eliminating Behavioral Errors. John Wiley & Sons."
  doi_or_url: "N/A — book source."
  notes: "Academic replication and extension of Greenblatt's Magic Formula on US equities 1974-2011. Documents persistent outperformance and confirms the combination (ROC + EY) is stronger than either alone."
direction: bottom_up
asset_class: equity
factor_tilts: {}
factor_tilts_notes: "Greenblatt is not characterized by Parallax factor loadings — it's a mechanical two-metric rank screen. Parallax Value sub-score is loosely correlated with EY but NOT a substitute for the formula."
leverage_overlay: null
output_shape: ranked_basket
output_shape_single_ticker: ticker_rank_check
tool_sequence_universe:
  - build_stock_universe
  - get_financials:statement=ratios
  - get_peer_snapshot
tool_sequence_single_ticker:
  - get_company_info
  - build_stock_universe
  - get_financials:statement=ratios
  - get_peer_snapshot
required_factors_present: []
thresholds:
  roc_rank_percentile: "top decile of queried universe"
  earnings_yield_rank_percentile: "top decile of queried universe"
  combined_rank_percentile_for_match: "top 10% of queried universe"
  combined_rank_percentile_for_partial: "top 25% but outside top 10%"
owner: cg-quant-team
last_legal_review: PENDING
last_anchor_test: 2026-04-06
anchor_test_notes: "Formula computation verified on CSCO.O (ROIC 11.06%, EY 4.14%), MSFT.O (ROIC 23.55%, EY 3.46%), NVDA.O (ROIC 89.54%, EY 2.89%). Parallax ROIC accessible via get_financials(ratios); EY = 1/enterprise_value_ebit reciprocal. Full universe-mode anchor test deferred — build_stock_universe timed out during initial test, requires longer timeout in production. Mega-cap tech exhibits low EY (2.89-4.14%) due to 21st-century premium multiples — same intangibles-era issue as Buffett profile, Lev-Srivastava 2022 caveat applies."
---

# Greenblatt-style profile

## What the anchor documents

Joel Greenblatt's 2006 book *The Little Book That Beats the Market* documents an exact mechanical screen called the "Magic Formula." Rank stocks by (1) return on capital (ROC) — EBIT divided by net working capital plus net fixed assets, and (2) earnings yield (EY) — EBIT divided by enterprise value. Sum each stock's two ranks. Sort by combined rank. Take the top decile. That's the Magic Formula basket. Greenblatt's original framing excludes financials and utilities due to incompatible capital-structure metrics.

Gray & Carlisle's 2012 *Quantitative Value* provides academic replication on US equities 1974-2011, documenting persistent outperformance and confirming that the combination of the two metrics delivers meaningfully stronger results than either alone.

## What this profile does

Two modes:

**Universe mode** — runs the Magic Formula against a defined equity universe. Uses `build_stock_universe` to get candidates, `get_financials(ratios)` to pull ROC and EY (substituting Parallax's closest available ratios where the exact metrics aren't directly exposed), ranks each candidate on both dimensions, combines ranks, and returns the top decile as a ranked basket.

**Single-ticker mode** — takes one ticker and reports where it ranks in its sector peer universe on combined Greenblatt rank. Verdict: `match` (top decile), `partial_match` (top quartile but outside top decile), or `no_match` (below top quartile).

Because the formula is explicitly mechanical, this profile has zero discretion — every decision is codified. The output is the formula's current ranking, nothing more.

## What this profile does NOT capture

- **Greenblatt's discretionary judgment.** Greenblatt runs Gotham Capital as a discretionary value investor; the Magic Formula is his simplified systematic version for retail. Not a full replica.
- **Intangibles-adjusted EY.** Per Lev & Srivastava (2022), traditional earnings yield understates intangibles-heavy firms. The formula is applied as published — not intangibles-adjusted — so high-quality compounders may rank lower than a modernized version would place them.
- **Small-cap premium.** Gray & Carlisle (2012) show the outperformance is stronger in small-caps. This profile runs on whatever universe is queried; default is mid-to-large-cap US equities.
- **Sector exclusions enforcement.** Greenblatt's book excludes financials and utilities. Default universe build excludes them; custom queries may not.
- **Holding period / rebalancing.** Formula implies annual rebalance; profile is stateless (current ranks only).

## How to interpret the output

**Universe mode:** a ranked list of top-decile names with ROC rank, EY rank, combined rank, and sector. This is what the formula says passes the screen today.

**Single-ticker mode:** a verdict (`match` / `partial_match` / `no_match`) plus the ticker's percentile ranks on ROC, EY, and combined, within the peer universe.

A `match` means the ticker is in the top 10% of the queried peer universe by combined Greenblatt rank. It does NOT mean the ticker is a current Gotham Capital position, does NOT mean the formula is "correct" for this moment in the market, and is NOT investment advice.

## Anchor test plan

Greenblatt's Magic Formula has public replication sites. Expected behavior:
1. Universe mode should surface mature, profitable, moderately-valued names — not high-multiple growth, not deeply distressed
2. Spot-check against a public Magic Formula replication site — substantial overlap expected (not exact)
3. Known value names should cluster near the top; high-multiple growth names should cluster near the bottom

## Thresholds (to be tuned during anchor test)

The ROC and EY percentiles are computed within the queried universe. The thresholds above are the formula itself — they aren't adjustable. What IS adjustable is the universe definition (market cap cutoffs, sector exclusions, geography). Task 4 anchor test will establish a sensible default.
