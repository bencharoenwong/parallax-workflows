# Parallax Workflows

AI-powered equity research workflows for [Parallax](https://chicago.global/parallax) by Chicago Global.

## Prerequisites

Before using any workflow, ensure:
1. **Parallax MCP is connected** — These workflows use `mcp__claude_ai_Parallax__*` tools. If you see "tool not found" errors, the Parallax MCP server is not configured.
2. **Valid API credentials** — Contact Chicago Global for API access.

## Quick Start

```bash
# Clone into your Claude Code skills directory
git clone https://github.com/bencharoenwong/parallax-workflows.git
# Symlink skills into Claude Code
ln -s $(pwd)/parallax-workflows/skills/* ~/.claude/skills/
```

Or copy individual skills you need:
```bash
cp -r parallax-workflows/skills/should-i-buy ~/.claude/skills/parallax-should-i-buy
```

## Workflow Ladder

Choose the right workflow for your task:

### Single Stock
| Depth | Workflow | Usage | Time |
|---|---|---|---|
| Quick check | `/should-i-buy AAPL` | Plain-language evaluation with scores, macro, dividends | ~30s |
| Research deep dive | `/deep-dive AAPL.O` | Full analysis with technicals + AI assessment | ~2min |
| Full due diligence | `/due-diligence AAPL.O` | All financials, Palepu framework, CG research report | ~5min |
| Earnings forensics | `/earnings-quality AAPL.O` | Accruals, revenue quality, manipulation risk | ~3min |
| Score explanation | `/score-explainer AAPL.O "why is value low?"` | Plain-language methodology explanation | ~15s |
| Peer comparison | `/peer-comparison AAPL.O` | Factor scores + price performance vs peers | ~1min |

### Portfolio
| Task | Workflow | Usage |
|---|---|---|
| Health check (plain language) | `/portfolio-checkup [holdings]` | Health flags, scores, plain-language recommendations |
| Client review (presentation-ready) | `/client-review [holdings]` | Full analysis with drill-down + priority matrix |
| Morning brief | `/morning-brief [holdings]` | Market regime, macro outlook, portfolio health, news |
| Rebalancing | `/rebalance [holdings]` | Prioritized trade recommendations with health flags |
| Scenario analysis | `/scenario-analysis "event" portfolio=[holdings]` | Exposure assessment + rotation candidates |

### Market & Discovery
| Task | Workflow | Usage |
|---|---|---|
| Macro outlook | `/macro-outlook "United States"` | Regime, macro analysis, factor implications |
| Country deep dive | `/country-deep-dive Japan` | Macro + equity opportunity analysis |
| Thematic screen | `/thematic-screen "AI infrastructure"` | Discover stocks by theme |
| Portfolio builder | `/portfolio-builder "defensive dividend Asian equities"` | Build allocation from thesis |
| Watchlist monitor | `/watchlist-monitor AAPL.O MSFT.O NVDA.O` | Flag score changes across a list |
| Halal screen | `/halal-screen AAPL.O` | Shariah compliance check |

### Holdings Format

All portfolio workflows accept holdings as JSON:
```json
[{"symbol":"AAPL.O","weight":0.25},{"symbol":"JPM.N","weight":0.20},{"symbol":"MSFT.O","weight":0.30},{"symbol":"JNJ.N","weight":0.25}]
```

Symbols use Reuters Instrument Code (RIC) format. See `skills/_shared/parallax-conventions.md` for the exchange suffix table.

## Shared Conventions

All workflows reference `skills/_shared/parallax-conventions.md` for:
- **RIC resolution** — Exchange suffix table for 10+ markets
- **Parallel execution** — Independent API calls fire simultaneously
- **Graceful fallbacks** — Retry logic and "unavailable" handling
- **HK ambiguity protocol** — Cross-check for numeric exchange codes
- **Macro reasoning** — How to identify relevant markets for a stock

## Disclaimer

These workflows produce informational analysis, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions.

## License

MIT
