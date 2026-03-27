# Parallax Workflows

AI-powered equity research workflows for [Parallax](https://chicago.global/parallax) by Chicago Global.

## Prerequisites

Before using any workflow, ensure:
1. **Parallax MCP is connected** — These workflows use `mcp__claude_ai_Parallax__*` tools. If you see "tool not found" errors, the Parallax MCP server is not configured.
2. **Valid API credentials** — Contact Chicago Global for API access.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/bencharoenwong/parallax-workflows.git
cd parallax-workflows

# Install all workflows into Claude Code
./install.sh
```

To install a single workflow manually:
```bash
cp -r skills/should-i-buy ~/.claude/skills/parallax-should-i-buy
cp skills/_parallax/parallax-conventions.md ~/.claude/skills/_parallax/parallax-conventions.md
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
| Client review (presentation-ready) | `/parallax-client-review [holdings]` | Full analysis with drill-down + priority matrix |
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

## Disclaimer

These workflows produce informational analysis, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions.

## License

MIT
