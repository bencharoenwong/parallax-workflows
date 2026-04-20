# Parallax Workflows

AI-powered equity research workflows for [Parallax](https://chicago.global/parallax), built for [Claude Code](https://claude.ai/code).

**Who this is for:**
- **Fund managers** — morning briefs, scenario analysis, rebalancing decisions
- **Relationship managers (RMs)** — client meeting prep, portfolio reviews with talk tracks
- **Research analysts** — due diligence, peer comparison, earnings forensics
- **Wealth advisors** — portfolio health checks, plain-language recommendations for clients
- **Individual investors** — quick stock evaluations, thematic screening, watchlist monitoring

Run commands like `/parallax-should-i-buy AAPL` or `/parallax-client-review [holdings]` and get a structured research report. Each workflow orchestrates Parallax MCP tools in parallel — company data, factor scores, macro analysis, news — so you get comprehensive output from a single command.

## Prerequisites

These workflows require an active Parallax subscription from [Chicago Global Capital](https://chicago.global). API credentials and MCP connection details are provided to clients upon onboarding. If you are not yet a client, contact us at [chicago.global](https://chicago.global) to get started.

## Setup

### 1. Connect the Parallax MCP server

Add the Parallax MCP server to Claude Code. Connection details are provided during client onboarding. The server should appear as `claude_ai_Parallax` in your MCP configuration.

### 2. Install the workflows

```bash
git clone https://github.com/bencharoenwong/parallax-workflows.git
cd parallax-workflows
./install.sh
```

This copies all workflows and shared conventions into `~/.claude/skills/`. Restart Claude Code after installing.

To install a single workflow:
```bash
cp -r skills/should-i-buy ~/.claude/skills/parallax-should-i-buy
cp -r skills/_parallax ~/.claude/skills/_parallax
```

The `_parallax` directory contains shared conventions, token-cost reference, and the AI-profiles framework (required by the `AI-*` skills). Always copy it alongside any individual workflow.

### 3. Verify

```
/parallax-should-i-buy AAPL
```

If you see "tool not found" errors, the MCP server is not connected.

## Workflows

### Concierge

| Command | What it does |
|---|---|
| `Hi Parallax` (case-insensitive) | Friendly concierge that asks 1-2 questions and routes you to the right `/parallax-*` workflow. The magic front door for everyday users. |

### Single Stock

| Command | What it does |
|---|---|
| `/parallax-should-i-buy AAPL` | Quick evaluation — scores, macro, dividends, news, outlook |
| `/parallax-deep-dive AAPL.O` | Full analysis with technicals and AI assessment |
| `/parallax-due-diligence AAPL.O` | All financials, Palepu framework, Parallax research report |
| `/parallax-earnings-quality AAPL.O` | Accruals, revenue quality, manipulation risk |
| `/parallax-score-explainer AAPL.O "why is value low?"` | Plain-language methodology explanation |
| `/parallax-peer-comparison AAPL.O` | Factor scores and price performance vs peers |

### Portfolio

All portfolio workflows take holdings as JSON: `[{"symbol":"AAPL.O","weight":0.25}, ...]`

| Command | What it does |
|---|---|
| `/parallax-portfolio-checkup [holdings]` | Health flags, scores, plain-language recommendations |
| `/parallax-explain-portfolio [holdings] "down 4%"` | Attribution — regime vs factor vs stock-specific |
| `/parallax-client-review [holdings]` | Full analysis, talk tracks, meeting prep |
| `/parallax-morning-brief [holdings]` | Market regime, macro, portfolio health, news |
| `/parallax-rebalance [holdings]` | Prioritized trades with health flags and score rationale |
| `/parallax-scenario-analysis "event" portfolio=[holdings]` | Exposure assessment and rotation candidates |

### Market & Discovery

| Command | What it does |
|---|---|
| `/parallax-macro-outlook "United States"` | Regime, macro analysis, factor implications |
| `/parallax-country-deep-dive Japan` | Macro environment and equity opportunities |
| `/parallax-thematic-screen "AI infrastructure"` | Discover stocks by theme |
| `/parallax-portfolio-builder "defensive dividend Asian equities"` | Build allocation from thesis |
| `/parallax-watchlist-monitor AAPL.O MSFT.O NVDA.O` | Flag score changes across a list |
| `/parallax-halal-screen AAPL.O` | Shariah compliance check |

### Parallax AI Investor Profiles

A family of standalone skills that apply famous investors' workflow shapes (not just rubric thresholds) to current Parallax data, each anchored in published academic or biographical sources. Output is third-person ("Buffett-style"), always cites the source, and uses only public information.

| Command | Workflow | Anchor |
|---|---|---|
| `/parallax-AI-buffett <ticker>` | Bottom-up single-stock; Quality + Value + Defensive factor profile | Frazzini-Kabiller-Pedersen (2018), *FAJ*; reconciled for 21st-century intangibles via Lev-Srivastava (2022) |
| `/parallax-AI-greenblatt [ticker]` | Magic Formula: ROC + earnings yield → top-decile basket | Greenblatt (2006); Gray-Carlisle (2012) |
| `/parallax-AI-klarman <ticker>` | Balance-sheet-first margin-of-safety checks (incl. "no position warranted; cash is valid") | Klarman, *Margin of Safety* (1991) |
| `/parallax-AI-soros [ticker]` | Top-down macro → regime themes → dual-channel ticker exposure | Soros, *Alchemy of Finance* (1987); Drobny (2006) |
| `/parallax-AI-consensus <ticker or basket>` | Runs all 4 profiles in parallel; surfaces super-majority + factor-level agreement | Meta-skill |

**Framing and legal posture:**
- All profiles framed in third person ("Buffett-style," never "Buffett says")
- Each output cites its academic/book source and includes a mandatory non-advice disclaimer
- AI-inferred from publicly available information only — no proprietary endpoints
- Not financial advice, not personalized, not endorsed by any named investor
- See `skills/_parallax/AI-profiles/README.md` for inclusion criteria, v2 candidates, and design rationale

### Symbol Format

Symbols use Reuters Instrument Code (RIC) format. `/parallax-should-i-buy` auto-resolves plain tickers (AAPL); other workflows require RIC format (AAPL.O).

| Exchange | Suffix | Example |
|---|---|---|
| NASDAQ | `.O` | AAPL.O |
| NYSE | `.N` | JPM.N |
| Tokyo | `.T` | 7203.T |
| Hong Kong | `.HK` | 0700.HK |
| London | `.L` | SHEL.L |
| Singapore | `.SI` | D05.SI |

Full exchange table in `skills/_parallax/parallax-conventions.md`.

## Token Costs

Each Parallax API call consumes tokens. Quick reference:

| Workflow type | Typical tokens | Example |
|---|---|---|
| Quick stock check | 2–24 | `/parallax-should-i-buy` ~24 |
| Deep analysis | 31–45 | `/parallax-due-diligence` ~31 |
| Portfolio (10 holdings) | 36–105 | `/parallax-portfolio-checkup` ~36 |

Full breakdown in `skills/_parallax/token-costs.md`.

## What's Inside

```
skills/
├── _parallax/                  # Shared conventions, token costs, AI profile framework
│   ├── parallax-conventions.md # RIC resolution, parallel execution, fallbacks
│   ├── token-costs.md          # Per-tool and per-workflow token estimates
│   └── AI-profiles/            # Schema, output template, and profile specs for AI-* skills
├── should-i-buy/               # Quick stock evaluation
│   └── SKILL.md
├── deep-dive/                  # Full single-stock analysis
│   └── SKILL.md
├── client-review/              # RIA client meeting prep
│   ├── SKILL.md
│   └── references/
│       └── recommendation-matrix.md
├── portfolio-checkup/          # Individual investor health check
│   ├── SKILL.md
│   └── references/
│       └── health-flags.md
├── AI-buffett/                 # Buffett-style factor profile dispatcher
│   └── SKILL.md
├── AI-consensus/               # Multi-profile super-majority meta-skill
│   └── SKILL.md
└── ... (18 more workflows)
```

Each `SKILL.md` is a self-contained instruction set. Claude reads it when you invoke the command, then orchestrates the Parallax MCP tools accordingly. No code execution — just structured API orchestration.

## Known Limitations

- **Publicly traded equities only** — no mutual funds, ETFs, or private assets
- **RIC format required** for most workflows (except `/parallax-should-i-buy`)
- **`build_stock_universe` uses keyword matching** — use sector-level queries ("US large cap consumer staples"), not abstract concepts ("pricing power in stagflation")
- **Peer groups are industry-based** — mega-caps may be compared to smaller industry peers
- **`check_macro_health` costs 5 tokens** — known issue, fix planned

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

These workflows are analytical tools that automate data retrieval and presentation from the Parallax platform. They do not constitute financial advice, investment recommendations, or solicitations to buy or sell securities. All outputs are informational only and should be independently verified and reviewed by qualified professionals before any investment decisions. Chicago Global Capital Pte Ltd. assumes no liability for decisions made based on these outputs.
