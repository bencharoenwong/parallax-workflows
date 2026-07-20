# Token Cost Reference

Parallax uses token-based pricing. All tools consume the same number of tokens whether accessed via API, MCP, or the web platform.

## Tool Token Costs

### 0 tokens (free)
| Tool | Description |
|---|---|
| `explain_methodology` | Scoring methodology explanations |
| `get_docs` / `list_docs` | Documentation access |
| `search_stocks` / `search_etfs` | Symbol search (fuzzy) |
| `export_price_series` | Daily price data export. Its own MCP tool description states "FREE" (verified live 2026-07-20; the whole tool suite marks free tools "FREE" and omits the marker on billable ones). Was previously listed under "1 token each" — reclassified to match the vendor's stated contract. **Reversible:** if operator billing shows this is metered (e.g. free only within plan limits), move it back and revise dependent skill estimates. |

### Unverified costs
| Tool | Description |
|---|---|
| `etf_profile` | ETF profile/classification probe. Cost UNVERIFIED in this environment; measure before publishing numeric desk-call-list probe cost. |
| `etf_daily_price` | ETF daily price series. Cost UNVERIFIED in this environment; measure before publishing numeric desk-call-list scan cost. |

### 1 token each
| Tool | Description |
|---|---|
| `get_company_info` | Company profile, sector, market cap |
| `get_peer_snapshot` | Factor scores + peer ranking |
| `export_peer_comparison` | Structured peer data export |
| `get_financials` | Financial statements (1 token per statement type: income, balance_sheet, cash_flow, ratios, summary) |
| `get_stock_outlook` | Analyst data (1 token per aspect: analyst_targets, recommendations, risk_return, dividends) |
| `get_score_analysis` | Historical factor score trajectory |
| `list_macro_countries` | Available macro market coverage |
| `get_telemetry` | Market regime signals and divergences |

### 1 token per holding (fan-out)
| Tool | Description | 10-holding portfolio |
|---|---|---|
| `quick_portfolio_scores` | Portfolio factor scores | 10 tokens |
| `check_portfolio_redundancy` | Overlap detection | 10 tokens |

> **Tip:** For large portfolios (15+ holdings), `analyze_portfolio` at 5 tokens flat may be more cost-effective than `quick_portfolio_scores` at 1 token per holding.

### 5 tokens each
| Tool | Description |
|---|---|
| `build_stock_universe` | Semantic stock discovery (~65K descriptions) |
| `get_news_synthesis` | AI-curated news analysis (async, 30-90s) |
| `get_technical_analysis` | Trend, momentum, support/resistance |
| `get_financial_analysis` | Palepu framework analysis (async, 2-5 min) |
| `analyze_portfolio` | Portfolio risk/concentration analysis (flat fee) |
| `macro_analyst` | Country macro analysis |
| `check_macro_health` | Macro data freshness check (known bug: routes through macro-report endpoint instead of a dedicated 0-token health endpoint) |

### 10 tokens each
| Tool | Description |
|---|---|
| `get_stock_report` | Full Parallax research report with PDF (async, 1-2 min) |
| `get_assessment` | AI deep-research synthesis (MCP uses deep model) |

---

## Estimated Cost Per Workflow

Based on a **10-holding portfolio** baseline. Actual cost depends on the number of holdings, markets, and conditional branches (flagged symbols, stress regime, etc.).

### Single Stock Workflows

| Workflow | Tokens (typical) | Key cost drivers |
|---|---|---|
| `/parallax-score-explainer` | **0-2** | Free if methodology-only; 2 if score data needed |
| `/parallax-peer-comparison` | **5 known billable + UNVERIFIED classification/ETF-price costs** | Peer snapshot + peer comparison export + 3 score histories = 5. Equity price series are free; 3 mandatory `etf_profile` probes and any `etf_daily_price` branches have UNVERIFIED costs. |
| `/parallax-halal-screen` | **4** single stock (~4-5/holding portfolio) | company_info + balance_sheet (merged debt + interest-bearing check) + ratios + score_analysis = 4; +5 optional Palepu; portfolio mode adds redundancy fan-out + alternatives |
| `/parallax-should-i-buy` | **29** | 4 outlook aspects + 2 macro markets + news + technicals (5) |
| `/parallax-earnings-quality` | **24** | Palepu (5) + assessment (10) + news (5) |
| `/parallax-due-diligence` | **31** | 4 financials + Palepu + stock report (10) |
| `/parallax-country-deep-dive` | **29** | 1 macro summary call (SKILL.md mandates summary mode, not per-component) + universe build + 5 peer snapshots + 5 company-info ground-truth checks + 3 score trends |
| `/parallax-deep-dive` | **45** | Assessment (10) + technicals (5) + 3 macro markets |
| `/parallax-macro-outlook` | **46** | 4 macro calls + telemetry (1) + 5 company-info ground-truth checks in equities mode; without equities (28) |

### Portfolio Workflows (10 holdings)

| Workflow | Tokens (typical) | Key cost drivers |
|---|---|---|
| `/parallax-thematic-screen` | **~19** (default) / **~14** (`--no-macro`) | Universe build + 5 snapshots + 3 financials + `list_macro_countries` + `macro_analyst` × up to 3 markets + `get_telemetry` regime signal. `--no-macro` reverts to the prior ~14-token baseline. |
| `/parallax-portfolio-builder` | **36** | Universe + 10 snapshots + redundancy + validation |
| `/parallax-portfolio-checkup` | **36** | 2x fan-out (20) + 3 macro markets (15) |
| `/parallax-morning-brief` | **50** | Telemetry + macro + 2x fan-out + 3 news |
| `/parallax-watchlist-monitor` | **54** | 10 score scans + news/tech/analyst for ~4 flagged |
| `/parallax-explain-portfolio` | **60 known billable + UNVERIFIED classification/ETF-price costs** | 10 company-info checks + 10 primary scoring calls + 10 score trends + telemetry + country listing + 2 macro + 3 news + 3 detractor snapshots = 60. Equity price series are free; 10 mandatory `etf_profile` probes and any `etf_daily_price` branches have UNVERIFIED costs. |
| `/parallax-scenario-analysis` | **68 known billable + UNVERIFIED classification costs** | The 10-holding equity subtotal includes 10 company-info checks, 10 score scans, portfolio analysis, universe/beneficiary scoring, macro/news, financial checks, and 2 assessments. The 10 mandatory `etf_profile` probes have UNVERIFIED costs; ETFs reduce the billable equity score fan-out. |
| `/parallax-rebalance` | **76** | 10 score trends + replacements + validation re-score |
| `/parallax-client-review` | **105** | 8 drill-downs + 5 news + assessment + 2x analyze |
| `/parallax-desk-call-list` | **~1 + 3\|M\| + 5·min(\|M\|,K) for an equity desk; + UNVERIFIED ETF costs** | 1 telemetry. The wide equity price scan is `export_price_series`, now FREE (above), so it adds nothing — the earlier `1×\|U\|` term is gone and an equity desk is materially cheaper than the first estimate. Per equity mover: company_info + peer_snapshot + score_analysis (3) + news (5, cap K). Equity-desk formula: `1 + 3\|M_equity\| + 5·min(\|M_equity\|,K)` (e.g. 6 movers → ~49). ETF holdings add UNVERIFIED `etf_profile` / `etf_daily_price` calls (not published by the vendor; see Unverified costs). Cost scales with movers, not client count. |

> **Broad-selloff guard:** on a market-wide morning the mover set `M` can approach
> `U`, and news + enrichment dominate the bill. `/parallax-desk-call-list`
> deterministically raises its move threshold to cap `|M|` at 40 and states the
> auto-raise in the report. A numeric worst case cannot be published until
> `etf_daily_price` and `etf_profile` costs are measured.

### House View Workflows

| Workflow | Tokens (typical) | Key cost drivers |
|---|---|---|
| `/parallax-load-house-view` | **0** | File I/O only — no chargeable MCP calls |
| `/parallax-house-view-diff` | **2× child** | Runs the target skill twice (Leg A without view, Leg B with view) — no additional Parallax tokens beyond the child, but total cost doubles: e.g. 2 × 36 = **72 tokens** with `/parallax-portfolio-builder`. |
| `/parallax-stress-house-view` | **~30** (scales with tilted markets) | `check_macro_health` (5) + `get_telemetry` (1) + `macro_analyst` × tilted markets (5 each); cap 12 markets |
| `/parallax-judge-house-view` | **~282** | Same recipe as make: 14 markets × 4 components + telemetry |
| `/parallax-make-house-view` | **~282** (scales with `--markets`) | `list_macro_countries` (0) + `get_telemetry` (1) + `macro_analyst` × 14 markets × 4 components (280); `--markets` flag reduces the market set and scales cost proportionally |

> **Cost gotcha:** `/parallax-make-house-view` and `/parallax-judge-house-view` are the costliest workflows in the library at ~$56 each at Standard plan overage rates ($0.20/token). Run them intentionally — not as part of a routine check. For lightweight view assessment without full re-synthesis, prefer `/parallax-stress-house-view`.

> **Auto-trigger surcharge:** the auto-on-load drift check (fired by `/parallax-portfolio-builder`, `/parallax-rebalance`, and `/parallax-thematic-screen` when the loaded view is older than 30 days) invokes `/parallax-judge-house-view --dry`. `--dry` skips the LLM synthesis step but still incurs the full macro fan-out (~280 tokens) — this surcharge lands on the consuming workflow's bill, not a separate line item. Run intentionally; the 30-day age gate is what bounds how often it fires.

### Cost Context

With the **Standard plan** ($2,000/month, 2,000 included tokens, $0.20 overage):
- A daily morning brief (~50 tokens) = ~1,100 tokens/month (22 trading days)
- A daily desk call list has no publishable numeric estimate until `etf_daily_price` and `etf_profile` costs are measured
- 5 should-i-buy checks/week (~29 each) = ~580 tokens/month
- 2 client reviews/week (~105 each) = ~840 tokens/month
- **Typical active RM usage:** 2,000-3,000 tokens/month

With the **Family Office plan** ($500/seat/month, 500 included tokens):
- Selective usage: a few should-i-buy + one portfolio-checkup/week fits comfortably
- Heavy usage (daily briefs + stock checks) may exceed the included allocation
