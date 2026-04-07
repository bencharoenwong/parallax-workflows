# Token Cost Reference

Parallax uses token-based pricing. All tools consume the same number of tokens whether accessed via API, MCP, or the web platform.

## Tool Token Costs

### 0 tokens (free)
| Tool | Description |
|---|---|
| `explain_methodology` | Scoring methodology explanations |
| `get_docs` / `list_docs` | Documentation access |

### 1 token each
| Tool | Description |
|---|---|
| `get_company_info` | Company profile, sector, market cap |
| `get_peer_snapshot` | Factor scores + peer ranking |
| `export_peer_comparison` | Structured peer data export |
| `get_financials` | Financial statements (1 token per statement type: income, balance_sheet, cash_flow, ratios, summary) |
| `get_stock_outlook` | Analyst data (1 token per aspect: analyst_targets, recommendations, risk_return, dividends) |
| `get_score_analysis` | Historical factor score trajectory |
| `export_price_series` | Daily price data export |
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
| `/parallax-peer-comparison` | **8** | 3 score histories + 3 price series |
| `/parallax-halal-screen` | **8** | 2 financials + Palepu |
| `/parallax-should-i-buy` | **24** | 4 outlook aspects + 2 macro markets + news |
| `/parallax-earnings-quality` | **24** | Palepu (5) + assessment (10) + news (5) |
| `/parallax-due-diligence` | **31** | 4 financials + Palepu + stock report (10) |
| `/parallax-country-deep-dive` | **34** | 3 macro calls + universe build + 5 peer snapshots |
| `/parallax-deep-dive` | **45** | Assessment (10) + technicals (5) + 3 macro markets |
| `/parallax-macro-outlook` | **41** | 4 macro calls + telemetry (1); less without equities (28) |

### Portfolio Workflows (10 holdings)

| Workflow | Tokens (typical) | Key cost drivers |
|---|---|---|
| `/parallax-thematic-screen` | **14** | Universe build + 5 snapshots + 3 financials |
| `/parallax-portfolio-builder` | **36** | Universe + 10 snapshots + redundancy + validation |
| `/parallax-portfolio-checkup` | **36** | 2x fan-out (20) + 3 macro markets (15) |
| `/parallax-morning-brief` | **50** | Telemetry + macro + 2x fan-out + 3 news |
| `/parallax-watchlist-monitor` | **54** | 10 score scans + news/tech/analyst for ~4 flagged |
| `/parallax-explain-portfolio` | **60** | 10 price series + 10 score trends + telemetry + 2 macro + 3 news + 3 snapshots |
| `/parallax-scenario-analysis` | **68** | 2x assessment (20) + 10 score scans + universe |
| `/parallax-rebalance` | **76** | 10 score trends + replacements + validation re-score |
| `/parallax-client-review` | **105** | 8 drill-downs + 5 news + assessment + 2x analyze |

### Cost Context

With the **Standard plan** ($2,000/month, 2,000 included tokens, $0.20 overage):
- A daily morning brief (~50 tokens) = ~1,100 tokens/month (22 trading days)
- 5 should-i-buy checks/week (~24 each) = ~480 tokens/month
- 2 client reviews/week (~105 each) = ~840 tokens/month
- **Typical active RM usage:** 2,000-3,000 tokens/month

With the **Family Office plan** ($500/seat/month, 500 included tokens):
- Selective usage: a few should-i-buy + one portfolio-checkup/week fits comfortably
- Heavy usage (daily briefs + stock checks) may exceed the included allocation
