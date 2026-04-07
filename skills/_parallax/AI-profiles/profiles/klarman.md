---
profile_id: klarman
display_name: Klarman-style
status: active
public_anchor:
  type: book
  citation: "Klarman, S. (1991). Margin of Safety: Risk-Averse Value Investing Strategies for the Thoughtful Investor. HarperBusiness. ISBN 978-0887305108."
  doi_or_url: "N/A — out of print. Widely cited in academic value-investing literature and available through major libraries."
  retrieved: 2026-04-07
  notes: "Klarman's own published book articulating his investment philosophy. Core tenets: margin of safety (buy well below intrinsic value), balance-sheet strength (can the company survive?), willingness to hold cash when nothing qualifies, patient holding through drawdowns, focus on special situations (spin-offs, distressed debt, risk arbitrage)."
direction: bottom_up
asset_class: equity
factor_tilts:
  value: positive_strong
  quality: positive
factor_tilts_notes: "Klarman's approach is dominated by balance-sheet quality and valuation discount, not factor loadings. Parallax Value and Quality sub-scores are used as backup sanity checks, not primary criteria."
leverage_overlay: null
output_shape: single_stock_verdict
tool_sequence:
  - get_company_info
  - get_peer_snapshot
  - get_financials:statement=balance_sheet
  - get_financials:statement=cash_flow
  - get_financials:statement=ratios
tool_sequence_notes: "get_financials defaults to periods=4. Numeric parameters (periods=4) are NOT embedded in tool_sequence strings because the MCP transport serializes them as strings, causing validation errors. Rely on server defaults or pass as typed params at call site."
required_factors_present: []
thresholds:
  net_cash_to_market_cap: ">= -0.2"
  debt_to_equity_vs_peers: "<= peer median × 1.1"
  fcf_positive_periods: ">= 3 of 4"
  pe_discount_to_peers: "<= peer median × 1.0"
  value_score_backup: ">= 4"
owner: parallax-workflows
last_legal_review: PENDING
last_anchor_test: 2026-04-07
anchor_test_notes: "Tested against BRKb.N (parent conglomerate) and NVDA.O (negative control). BRKb: 2 of 4 partial — PASS on D/E 0.18 and FCF stability (4/4 periods positive); FAIL on net cash (−21% due to BNSF/BHE consolidated debt) and valuation (P/E 15.38 vs insurance peer median ~11.58, 33% premium). NVDA: 3 of 4 partial — PASS on net cash (+$54B), D/E 0.054, FCF stability (4/4); FAIL on valuation (P/E 36 vs semis median ~38, at-peer). NVDA falls to partial_match because Value backup (2.5) falls below ≥4 threshold. Framework discriminates qualitatively: BRKb fails on balance sheet (parent problem per Buffett profile caveat), NVDA fails on valuation (intangibles era per Lev-Srivastava 2022). Examining WHICH checks failed is the actionable signal."
---

# Klarman-style profile

## What the anchor documents

Seth Klarman's 1991 *Margin of Safety: Risk-Averse Value Investing Strategies for the Thoughtful Investor* is his own articulation of a deep-value, downside-protected investment philosophy. The book is out of print but widely cited in academic value-investing literature and available through major libraries. Core principles from the book:

1. **Margin of safety** — buy at a meaningful discount to intrinsic value, so that even imperfect analysis limits downside
2. **Balance-sheet strength** — survival comes before growth or returns
3. **Willingness to hold cash** — when nothing qualifies, do not force trades
4. **Patience** — positions held through drawdowns; turnover is expensive
5. **Special situations** — spin-offs, distressed debt, risk arbitrage, catalyst-driven opportunities

## What this profile does

Applies a balance-sheet-first four-check test to a single stock: (1) net cash position, (2) debt versus peer median, (3) free-cash-flow stability across four periods, (4) valuation discount to peer median. A Parallax Value score ≥ 4 is used as a backup sanity check (loose threshold per Lev-Srivastava 2022 intangibles caveat). A stock `match`es if it passes ≥ 3 of the 4 balance-sheet checks AND the Value backup. 2 of 4 → `partial_match`. ≤ 1 of 4 → `no_match`.

## Distinctive output: "no position warranted"

If a stock passes 0 of 4 checks AND has low Parallax Value, the output adds: *"No position warranted on this ticker per margin-of-safety principles. Cash is a valid stance."* This is the only v1 profile where "do nothing" is an explicit positive output. It reflects Klarman's own published view that holding cash when nothing qualifies is a disciplined stance, not a failure.

## What this profile does NOT capture

- **Intrinsic-value estimation.** Klarman's actual process involves DCF, liquidation value, sum-of-parts. This profile uses peer-relative valuation as a tractable proxy.
- **Special situations.** Spin-offs, distressed debt, risk arbitrage are central to Klarman but not flagged here. This profile is bottom-up valuation + balance sheet only.
- **Qualitative judgment.** Klarman writes extensively about management skepticism and industry structure. Profile uses numeric checks as proxy.
- **Position sizing.** Klarman runs concentrated positions; this profile is per-ticker only.
- **Intangibles-adjusted valuation.** Per Lev & Srivastava (2022), traditional P/E and P/B understate intangibles-heavy firms. Value threshold loosened to ≥ 4 to reconcile.

## How to interpret the output

A `match` means the stock currently passes the balance-sheet and valuation screen — eligible for deeper diligence per Klarman's framework. It does NOT mean Baupost holds the stock, and it is NOT investment advice.

A `partial_match` is informative — which checks passed matters. A stock with a strong balance sheet trading at peer median is balance-sheet-defensible but lacks the valuation discount Klarman's framework requires.

A `no_match` with the "no position warranted" footer is itself useful: the framework does not flag this stock regardless of narrative interest.

## Anchor test plan

Baupost's 13F filings are public via SEC EDGAR. Expected: historical Baupost equity holdings return `match` or strong `partial_match`; high-multiple growth names return `no_match` with the cash-is-valid footer.
