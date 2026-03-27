# Parallax Workflows

AI-powered equity research workflows for [Parallax](https://chicago.global/parallax) by Chicago Global. Fund managers, wealth advisors, and individual investors use these to run structured equity research directly from Claude Code using plain-language commands like `/parallax-should-i-buy AAPL` or `/parallax-client-review [holdings]`.

## How It Works

These are Claude Code skills — structured instruction sets that tell Claude how to orchestrate Parallax MCP tools. When you run a command, Claude fires a coordinated sequence of Parallax API calls (company data, factor scores, macro analysis, news) in parallel, synthesizes the results, and returns a formatted report. The Parallax MCP server is the data layer; these workflows are the research logic on top of it.

## Prerequisites

Two things must be in place before any workflow will run:

**1. Connect the Parallax MCP server to Claude Code**

Open Claude Code settings (gear icon or `/config`) and navigate to MCP Servers. Add a new server with the connection details provided by Chicago Global. The server name should appear as `claude_ai_Parallax` in the configuration. If the workflows produce "tool not found" errors, the MCP server is not connected.

Contact Chicago Global at [chicago.global](https://chicago.global) to obtain API credentials and MCP connection details.

**2. Install the workflows**

```bash
git clone https://github.com/bencharoenwong/parallax-workflows.git
cd parallax-workflows
./install.sh
```

The installer copies all 18 workflows and the shared conventions file into your Claude Code skills directory (`~/.claude/skills/`). Restart Claude Code after installing.

To install a single workflow manually:
```bash
cp -r skills/should-i-buy ~/.claude/skills/parallax-should-i-buy
cp skills/_parallax/parallax-conventions.md ~/.claude/skills/_parallax/parallax-conventions.md
```

## Quick Start

Once the MCP server is connected and the workflows are installed:

```
/parallax-should-i-buy AAPL
```

This runs a full stock evaluation — company overview, factor scores, financial health, macro context, dividends, analyst outlook, and recent news. Plain tickers (AAPL) and RIC codes (AAPL.O) both work.

For a portfolio:
```
/parallax-portfolio-checkup [{"symbol":"AAPL.O","weight":0.25},{"symbol":"JPM.N","weight":0.20},{"symbol":"MSFT.O","weight":0.30},{"symbol":"JNJ.N","weight":0.25}]
```

## Workflow Ladder

Choose the right workflow for your task:

### Single Stock
| Depth | Workflow | Usage | Time |
|---|---|---|---|
| Quick check | `/parallax-should-i-buy AAPL` | Plain-language evaluation with scores, macro, dividends | ~30s |
| Research deep dive | `/parallax-deep-dive AAPL.O` | Full analysis with technicals + AI assessment | ~2min |
| Full due diligence | `/parallax-due-diligence AAPL.O` | All financials, Palepu framework, CG research report | ~5min |
| Earnings forensics | `/parallax-earnings-quality AAPL.O` | Accruals, revenue quality, manipulation risk | ~3min |
| Score explanation | `/parallax-score-explainer AAPL.O "why is value low?"` | Plain-language methodology explanation | ~15s |
| Peer comparison | `/parallax-peer-comparison AAPL.O` | Factor scores + price performance vs peers | ~1min |

### Portfolio
| Task | Workflow | Usage |
|---|---|---|
| Health check (plain language) | `/parallax-portfolio-checkup [holdings]` | Health flags, scores, plain-language recommendations |
| Explain performance | `/parallax-explain-portfolio [holdings] "down 4%"` | Attribution: regime vs factor vs stock-specific; noise or signal? |
| Client review + meeting prep | `/parallax-client-review [holdings]` | Full analysis, talk tracks, anticipated questions, meeting agenda |
| Morning brief | `/parallax-morning-brief [holdings]` | Market regime, macro outlook, portfolio health, news |
| Rebalancing | `/parallax-rebalance [holdings]` | Prioritized trade recommendations with health flags |
| Scenario analysis | `/parallax-scenario-analysis "event" portfolio=[holdings]` | Exposure assessment + rotation candidates |

### Market & Discovery
| Task | Workflow | Usage |
|---|---|---|
| Macro outlook | `/parallax-macro-outlook "United States"` | Regime, macro analysis, factor implications |
| Country deep dive | `/parallax-country-deep-dive Japan` | Macro + equity opportunity analysis |
| Thematic screen | `/parallax-thematic-screen "AI infrastructure"` | Discover stocks by theme |
| Portfolio builder | `/parallax-portfolio-builder "defensive dividend Asian equities"` | Build allocation from thesis |
| Watchlist monitor | `/parallax-watchlist-monitor AAPL.O MSFT.O NVDA.O` | Flag score changes across a list |
| Halal screen | `/parallax-halal-screen AAPL.O` | Shariah compliance check |

### Holdings Format

All portfolio workflows accept holdings as JSON:
```json
[{"symbol":"AAPL.O","weight":0.25},{"symbol":"JPM.N","weight":0.20},{"symbol":"MSFT.O","weight":0.30},{"symbol":"JNJ.N","weight":0.25}]
```

Symbols use Reuters Instrument Code (RIC) format. See `skills/_parallax/parallax-conventions.md` for the exchange suffix table.

## Token Costs

Each Parallax API call consumes tokens. See `skills/_parallax/token-costs.md` for the full breakdown. Quick reference:

| Workflow type | Token range | Example |
|---|---|---|
| Quick stock check | 2-24 | `/parallax-should-i-buy` = ~24 tokens |
| Deep analysis | 31-45 | `/parallax-due-diligence` = ~31 tokens |
| Portfolio health (10 holdings) | 36-50 | `/parallax-portfolio-checkup` = ~36 tokens |
| Full portfolio review (10 holdings) | 68-105 | `/parallax-client-review` = ~105 tokens |

Standard plan: $2,000/month with 2,000 included tokens. Overage: $0.20/token. Contact Chicago Global for pricing details.

## Shared Conventions

All workflows reference `skills/_parallax/parallax-conventions.md` for:
- **RIC resolution** — Exchange suffix table for 10+ markets
- **Parallel execution** — Independent API calls fire simultaneously
- **Graceful fallbacks** — Retry logic and "unavailable" handling
- **HK ambiguity protocol** — Cross-check for numeric exchange codes
- **Macro reasoning** — How to identify relevant markets for a stock

## Known Limitations

- **No mutual fund or private asset support** — Only publicly traded equities with RIC identifiers
- **RIC-based tickers required** — Must use Reuters Instrument Codes (e.g., AAPL.O not AAPL). The `should-i-buy` workflow auto-resolves plain tickers; others require RIC format.
- **USD only** — Multi-currency reporting is in development
- **Peer groups are industry-based** — Mega-cap stocks (e.g., Apple) may be compared to smaller industry peers rather than market-cap-tier peers
- **ETFs are not in the scoring universe** — `get_score_analysis` does not support ETF symbols (SPY, QQQ, etc.)
- **`build_stock_universe` uses keyword matching** — Abstract queries ("pricing power in stagflation") return literal keyword matches. Use sector-level queries ("US large cap consumer staples") for better results.
- **`check_portfolio_redundancy` checks pair-level overlap only** — May miss sector-level concentration. Portfolio workflows supplement with manual sector weight checks.
- **`check_macro_health` costs 5 tokens** — Known backend issue; should be a 0-token health endpoint. Planned fix.
- **No portfolio editing after save** — Once saved via the platform, portfolios cannot be modified
- **Scoring tool may occasionally map to wrong company** — Cross-validation step (Convention #2) catches this, but verify company names when results seem unexpected

## Disclaimer

These workflows produce informational analysis, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions.

## License

MIT
