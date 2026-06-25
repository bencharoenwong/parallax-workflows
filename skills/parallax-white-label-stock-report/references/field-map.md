# get_stock_report JSON field map

Verbatim field paths the renderer depends on, observed from a live `get_stock_report` response. The committed fixture `references/sample-acme.synthetic.json` is a de-identified synthetic response (fictional company) with the same structure; real report data is kept out of this public repo.

## Wrapper

The MCP response is a plain JSON object:

    { success: bool, symbol: str, pdf_url: str, html_url: str, report: {...32 keys...} }

The renderer reads `response["report"]`. `pdf_url` and `html_url` point to the official CG-branded renders. `report.images` has three chart PNG URLs (price_chart, technical_plot, analyst_chart): out of scope for v1.

## Cover / summary

| Field | Path |
|---|---|
| Company name | report.company.name (and report.company_profile.title) |
| RIC / market / sector / industry | report.company.ric / .market / .sector / .industry |
| Rating | report.company.recommendation (e.g. "HOLD") |
| Factor scores (0-10) | report.company.value / .quality / .momentum / .defensive / .tactical / .total  (strings; total IS Overall) |
| Score bar widths (score x 10, 0-100) | report.score_widths.value/quality/momentum/defensive/tactical/total |
| Cover price target (peer-P/E) | report.dcf_valuation.target_value + report.dcf_valuation.target_footnote (method line) |
| Reconciliation chip / state / body | report.dcf_valuation.reconciliation_chip / .reconciliation_state / .reconciliation_body |
| Current price | report.vital_stats.current_price (use this cluster, not dcf_valuation.current_price) |
| Market cap | report.company.mktcap (string of raw value); convenience report.peers[0].mktcap_b (in billions) |
| Currency | report.company.currency / report.financial_statement_currency ("USD") |
| Investment thesis | report.investment_thesis.title / .hook / .para1 / .para2 / .para3 / .para4 |
| Recent Development (dated) | report.news_analysis.title / .bullet1 / .bullet2 / .bullet3 |
| Returns strip (1M/3M/YTD/1Y/5Y/10Y) | report.period_returns.ret_1m / .ret_3m / .ret_ytd / .ret_1yr / .ret_5yr / .ret_10yr |
| Key Statistics | report.current_ratios.price_to_earnings / .price_to_book / .earnings_per_share / .return_on_equity / .return_on_assets / .return_on_investment / .price_to_fcf / .ev_ebitda / .ev_revenue / .net_income_5y_growth / .revenue_per_share_5y_growth |
| Data-basis notes | report.data_basis_note / report.ratio_snapshot_note |
| Generated date | report.generated_date |

Two different price targets: cover uses the peer-P/E target (dcf_valuation), the Analyst Ratings section uses the sell-side consensus (price_target.target_mean). Do not conflate.

## Company analysis

| Field | Path |
|---|---|
| Company profile | report.company_profile.para1 / .para2 / .para3 |
| Score analysis | report.score_analysis (single string) |
| Peers analysis | report.peers_analysis (single string) |
| Peer table | report.peers (list of 8; row 0 = subject). Per row: company_name, market, recommendation, mktcap_b, mtd, ytd, pe, ev_ebitda, roe, de (+ ric, sector, industry, value, quality, momentum, defensive, tactical, total) |

## Technical

| Field | Path |
|---|---|
| Tactical read | report.technical_analysis.executive_summary |
| Trend / momentum / volume / price action / volatility | report.technical_analysis.technical_analysis.trend_analysis / .momentum_indicators / .volume_analysis / .price_action / .volatility_assessment |
| Risk assessment | report.technical_analysis.risk_assessment.volatility_level / .risk_factors |

## Financial analysis

| Field | Path |
|---|---|
| Highlights | report.financial_analysis.executivesummary.keyhighlights (list) |
| Business strategy | report.financial_analysis.detailedanalysis.businessstrategy.industryposition / .competitiveadvantage / .businessmodel / .keyrisks (list) |
| Accounting quality | report.financial_analysis.detailedanalysis.accountingquality.earningsquality / .conservatismlevel / .keypolicies (list) / .accountingredflags (list) |
| Prospective | report.financial_analysis.detailedanalysis.prospectiveanalysis.futureearnings / .growthprospects / .valuationassessment / .scenarioanalysis (list of 3: Bull/Base/Bear) |
| Intro summary | report.financial_summary (string) |

## Financial statements (each list of 4 FY)

- report.income_statement, report.balance_sheet, report.cash_flow
- Fiscal label per row: perenddt (e.g. 2025-09-27). pertypecode 1 = annual. unitsconvtocode "M". Values are raw integers in the statement currency.
- report.key_ratios (list of 4): fiscal label = year (2025/2024/2023/2022).

Statement row field names are long but stable; see sample-acme.synthetic.json for the full per-row key list (income_statement 45 keys, balance_sheet 46, cash_flow 33, key_ratios 34).

## Analyst ratings

| Field | Path |
|---|---|
| Consensus prose | report.analyst_analysis (single string; the "49 analysts / 67.4% Buy" numbers live ONLY here, not as structured fields) |
| Consensus target | report.price_target.target_mean |
| Expected change pct | report.price_target.exp_pct_change |
| Close used for target | report.price_target.price_close |
| Target calc date | report.price_target.target_calc_date |

## Disclosures (NOT in the JSON)

The MAS regulatory disclosure, AI analyst certification, conflict-management policy, and rating definitions are NOT returned in the JSON. They are boilerplate the official renderer templates in. The skill bundles its own pinned verbatim copy (inlined in render_stock_report.py), sourced from the official report. Re-sync from response.html_url if CGC updates the wording.

## Type / value gotchas

1. report.company.* numeric fields are strings; report.peers[].* and report.score_widths.* are numeric. Normalize on read.
2. Two price targets (cover peer-P/E vs analyst consensus). Two current-price snapshots (use vital_stats). Two return sets (use period_returns for the strip, current_ratios for Key Statistics).
3. Statement values are raw units (e.g. revenue 416161000000 with unitsconvtocode "M"); divide to millions for display to match the official report.
