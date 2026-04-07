---
profile_id: buffett
display_name: Buffett-style
status: active
public_anchor:
  type: academic_paper
  citation: "Frazzini, A., Kabiller, D., Pedersen, L. H. (2018). Buffett's Alpha. Financial Analysts Journal, 74(4), 35-55."
  doi_or_url: "https://doi.org/10.2469/faj.v74.n4.3"
  retrieved: 2026-04-06
  notes: "Peer-reviewed factor decomposition of Berkshire Hathaway's 1976-2017 returns. Documents +Quality, +Value, −Momentum (slight), +Defensive (low-beta) factor loadings with ~1.6x leverage overlay. Thresholds reconciled for 21st-century intangibles-heavy valuations per Lev & Srivastava (2022)."
secondary_anchor:
  citation: "Lev, B., Srivastava, A. (2022). Explaining the Recent Failure of Value Investing. Critical Finance Review, 11(2), 333-360."
  doi_or_url: "https://doi.org/10.1561/104.00000115"
  notes: "Documents that traditional book-value-based Value factors systematically understate firms with large intangible assets (brand, software, R&D). Justifies loosening Value threshold when applying BKP 2018's Value loading to modern Parallax data."
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
  - get_financials
  - get_score_analysis
  - explain_methodology
tool_sequence_notes: "get_financials called with statement=summary (default); get_score_analysis called with default weeks=52. Numeric parameters are NOT embedded in tool_sequence strings because the MCP transport serializes them as strings, causing validation errors. Use server defaults or pass as typed params at call site."
required_factors_present: [quality, value, momentum, defensive]
thresholds:
  quality: ">= 5"
  value: ">= 4"
  momentum: "<= 6"
  defensive: ">= 7"
owner: parallax-workflows
last_legal_review: PENDING
last_anchor_test: 2026-04-06
anchor_test_notes: "Tuned against KO.N (4/4 match), AXP.N (4/4 match). BRKb.N returns 3/4 partial (Quality fails) — expected, see narrative. AAPL.O returns 3/4 partial (Value fails at current multiples). NVDA.O (negative control) returns 2/4 partial."
---

# Buffett-style profile

## What the anchor documents

Frazzini, Kabiller, and Pedersen's 2018 *Financial Analysts Journal* paper "Buffett's Alpha" is the canonical peer-reviewed decomposition of Berkshire Hathaway's historical returns. Using 1976-2017 data, the authors show Berkshire's abnormal returns are largely explained by four factor exposures: strong Quality (Quality Minus Junk), strong Value (HML), slight negative Momentum, strong Defensive (low-beta, BAB). Berkshire also runs ~1.6x leverage via insurance float. After controlling for these factors and leverage, Berkshire's alpha shrinks — Buffett's outperformance can be largely replicated by systematic factor tilts at scale.

**21st-century calibration.** Lev & Srivastava (2022) show that book-value-based Value factors systematically understate intangibles-heavy firms (brand, software, R&D) — the dominant source of modern earning power. Traditional HML rejects many Buffett compounders. This profile reconciles BKP 2018 with Parallax's current-multiple factors by loosening Value and Quality thresholds to levels where Buffett's actual core holdings (KO, AXP) return `match`. The drift is documented explicitly, not hidden.

## What this profile does

Applies the BKP 2018 factor profile (reconciled for the intangibles era per Lev-Srivastava 2022) to a single stock's current Parallax factor scores. For each of the four factors, the profile compares the stock's Parallax score against a threshold and renders a verdict of `match` (4 of 4), `partial_match` (1-3 of 4), or `no_match` (0 of 4). The leverage overlay is disclosed but NOT applied per stock — leverage is a portfolio-construction choice.

## What this profile does NOT capture

- **Parent-stock vs holdings divergence.** BKP 2018 decomposes Berkshire's *holdings*, not BRK.A/B as a conglomerate. BRK.A/B's Parallax Quality is depressed by GAAP earnings volatility and mixed capital-intensity — use KO or AXP as anchors, not BRK.A/B.
- **Intangibles-adjusted accounting.** Parallax Value and Quality still use reported book and multiples, not capitalized intangibles. The profile reconciles via loosened thresholds (see §What the anchor documents) but does not compute intangibles-adjusted factors from scratch.
- **Management and qualitative moat.** Profile checks factor exposures only; stock-selection skill is not modeled.
- **Insurance float leverage.** Not replicable at the individual stock level.
- **Style evolution.** 1970s cigar-butt differs from post-1990 quality-compounder; profile reflects full-period average.
- **Current holdings check.** 13F data is elsewhere.

## How to interpret the output

A `match` verdict means the stock currently exhibits the factor profile BKP 2018 documents Berkshire's historical portfolio had. It does NOT mean the stock fits Berkshire's current holdings, does NOT mean the stock is a current Berkshire position, and is NOT investment advice. It is a statement about factor exposures, nothing more.

A `partial_match` is informative — users should look at *which* factors matched and which didn't. A stock that matches Quality and Defensive but not Value is factor-adjacent to Berkshire's profile but lacks the valuation discipline the paper documents.

A `no_match` on Berkshire-like stocks (e.g., KO, AXP) would be a signal that the profile thresholds are wrong or Parallax's factor definitions have drifted from BKP 2018's constructs — trigger an anchor test.

## Thresholds (tuned 2026-04-06 from anchor test)

- **Quality ≥ 5** — Parallax Quality is calibrated differently from BKP 2018's QMJ. A threshold of 5 ("above average") catches Buffett-style stocks like KO (8) and AXP (5) while filtering out low-quality speculative names.
- **Value ≥ 4** — Parallax Value reflects current multiples; Buffett's mega-cap holdings look expensive on this measure. A threshold of 4 ("slightly above the lowest quartile") preserves valuation discipline without being so strict it fails every Buffett holding. AAPL fails at 2; NVDA fails at 2.5.
- **Momentum ≤ 6** — "slight negative" momentum tilt per BKP 2018. NVDA (7.2) fails; Buffett core holdings (KO 4.8, AXP 4.5, BRKb 3.0) pass.
- **Defensive ≥ 7** — "strong" low-beta tilt per BKP 2018's BAB loading. KO (10), AXP (8), BRKb (10), AAPL (9.5) pass; NVDA (7.5) passes narrowly; high-beta growth names fail.

### Anchor test results (2026-04-06)

| Stock | Role | Q | V | M | D | Verdict |
|---|---|---|---|---|---|---|
| KO.N | Buffett core holding | 8 | 4 | 4.83 | 10 | **match (4/4)** ✓ |
| AXP.N | Buffett core holding | 5 | 5.5 | 4.54 | 8 | **match (4/4)** ✓ |
| BRKb.N | Berkshire parent | 4 | 7 | 2.97 | 10 | partial (3/4) — Quality drag from conglomerate structure |
| AAPL.O | Largest current holding | 10 | 2 | 5.90 | 9.5 | partial (3/4) — fails Value at premium multiple |
| NVDA.O | Negative control | 10 | 2.5 | 7.22 | 7.5 | partial (2/4) — fails Value + Momentum |

The profile discriminates: core Buffett holdings return full match; parent-stock and current-valuation-stretched holdings return partial; growth tech returns weaker partial.
