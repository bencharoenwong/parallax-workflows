---
profile_id: buffett
display_name: Buffett-style
status: active
public_anchor:
  type: academic_paper
  citation: "Frazzini, A., Kabiller, D., Pedersen, L. H. (2018). Buffett's Alpha. Financial Analysts Journal, 74(4), 35-55."
  doi_or_url: "https://doi.org/10.2469/faj.v74.n4.3"
  retrieved: 2026-04-06
  notes: "Peer-reviewed factor decomposition of Berkshire Hathaway's 1976-2017 returns. Documents +Quality, +Value, −Momentum (slight), +Defensive (low-beta) factor loadings with ~1.6x leverage overlay."
direction: bottom_up
asset_class: equity
factor_tilts:
  quality: positive_strong
  value: positive_strong
  momentum: negative
  defensive: positive
leverage_overlay: 1.6
output_shape: single_stock_verdict
tool_sequence:
  - get_company_info
  - get_peer_snapshot
  - get_financials:statement=summary
  - get_score_analysis:weeks=52
  - explain_methodology
required_factors_present: [quality, value, momentum, defensive]
thresholds:
  quality: ">= 7"
  value: ">= 6"
  momentum: "<= 6"
  defensive: ">= 6"
owner: cg-quant-team
last_legal_review: PENDING
last_anchor_test: PENDING
---

# Buffett-style profile

## What the anchor documents

Frazzini, Kabiller, and Pedersen's 2018 *Financial Analysts Journal* paper "Buffett's Alpha" is the canonical peer-reviewed decomposition of Berkshire Hathaway's historical returns. Using 1976-2017 data, the authors show that Berkshire's abnormal returns are largely explained by four factor exposures: strong Quality (per their Quality Minus Junk factor), strong Value (HML), slight negative Momentum, and strong Defensive (low-beta, per Betting Against Beta). On top of these exposures, Berkshire runs approximately 1.6x leverage via insurance float. After controlling for these factors and the leverage overlay, Berkshire's alpha is significantly reduced — meaning Buffett's outperformance can be largely replicated by systematically tilting toward these factors and levering up.

## What this profile does

Applies the BKP 2018 factor profile to a single stock's current Parallax factor scores. For each of the four factors documented in the paper, the profile compares the stock's Parallax score against a threshold representing the "strong" or "slight" tilt the paper describes. The verdict is a count of how many of the four factor criteria are met, rendered as `match` (4 of 4), `partial_match` (1-3 of 4), or `no_match` (0 of 4).

The profile does NOT apply the leverage overlay at the stock level — leverage is a portfolio-construction choice, not a stock attribute. The leverage value is disclosed in the output footer for transparency but does not affect any individual stock's verdict.

## What this profile does NOT capture

- **Qualitative moat assessment beyond the Quality factor.** BKP 2018 uses the Quality Minus Junk factor as a proxy for Buffett's "economic moat" selection. Parallax's Quality sub-score is a close analog but may not fully capture every dimension of moat quality that Buffett discusses in shareholder letters. Users seeking a deeper moat analysis should cross-reference with Parallax's financial-analysis tools.
- **Management quality.** BKP 2018 implicitly attributes some of Buffett's alpha to stock selection skill within the factor framework. The profile does not attempt to replicate selection skill — it only checks factor exposures.
- **Insurance float advantage.** Berkshire's structural access to cheap leverage via insurance float is not replicable at the individual stock level.
- **Buffett's evolving style.** BKP 2018 decomposes returns over a 40-year window. Buffett's approach in the 1970s (cigar-butts) differs from his approach post-1990 (quality compounders). The profile reflects the full-period factor profile, which leans more toward the latter.
- **Current Berkshire-specific holdings.** The profile does not check whether a stock is currently held by Berkshire. 13F data is available elsewhere but is not part of this profile.

## How to interpret the output

A `match` verdict means the stock currently exhibits the factor profile BKP 2018 documents Berkshire's historical portfolio had. It does NOT mean Buffett would buy the stock today, does NOT mean Berkshire holds the stock, and is NOT investment advice. It is a statement about factor exposures, nothing more.

A `partial_match` is informative — users should look at *which* factors matched and which didn't. A stock that matches Quality and Defensive but not Value is factor-adjacent to Berkshire's profile but lacks the valuation discipline the paper documents.

A `no_match` on Berkshire-like stocks (e.g., KO, AXP) would be a signal that the profile thresholds are wrong or Parallax's factor definitions have drifted from BKP 2018's constructs — trigger an anchor test.

## Thresholds (initial, tuned during anchor test)

- **Quality ≥ 7** — "strong" quality tilt per BKP 2018
- **Value ≥ 6** — "strong" value tilt (slightly lower threshold than Quality because Buffett's valuation discipline varies by era)
- **Momentum ≤ 6** — "slight negative" momentum tilt (threshold is an inverted "not-too-high" constraint)
- **Defensive ≥ 6** — "strong" low-beta tilt per BKP 2018's BAB loading

These thresholds are initial guesses based on a 0-10 Parallax score scale. Task 8 (anchor test) tunes them by running the profile against known Berkshire core holdings (BRK.B, KO, AXP) and adjusting until those names return `match` or strong `partial_match`.
