# Parallax Workflows

AI-powered equity research workflows for [Parallax](https://chicago.global/parallax), built for [Claude Code](https://claude.ai/code).

**Who this is for:**
- **Fund managers** — morning briefs, scenario analysis, rebalancing decisions
- **Relationship managers (RMs)** — client meeting prep, portfolio reviews with talk tracks
- **Research analysts** — due diligence, peer comparison, earnings forensics
- **Wealth advisors** — portfolio health checks, plain-language recommendations for clients
- **Individual investors** — quick stock evaluations, thematic screening, watchlist monitoring
- **Engineering teams** — embedding Parallax into internal research tools, B-CIO synthesis layers, white-label investment products. Workflows are reference implementations under MIT — fork them, modify the prompts, swap the inputs, ship in your own harness.

Run commands like `/parallax-should-i-buy AAPL` or `/parallax-client-review [holdings]` and get a structured research report. Each workflow orchestrates Parallax MCP tools in parallel — company data, factor scores, macro analysis, news — so you get comprehensive output from a single command.

## Quick Start

If you have Parallax connected and want to try it now, three commands cover 80% of usage:

| If you want to… | Run |
|---|---|
| Be guided to the right workflow | `Hi Parallax` (or `/parallax-concierge`) |
| Evaluate a single stock | `/parallax-should-i-buy AAPL` |
| Run a portfolio health check | `/parallax-portfolio-checkup [{"symbol":"AAPL.O","weight":0.4},{"symbol":"MSFT.O","weight":0.6}]` |

Everything below is the full catalog. The concierge is the recommended entry point for first-time users — it asks one clarifying question and routes you.

## What's in this repo

The repo is open-source. Two layers:

1. **Framework (free, public, MIT):** skill prompts, YAML schemas, validators, extraction logic, regression corpus. Includes the [house-view ingestion framework](skills/load-house-view/) — a schema + loader + extraction pipeline for codifying CIO investment views into structured tilts that any equity scoring engine can consume. Swap out the MCP layer and it works with any scoring provider.
2. **Parallax MCP (paid, required for the workflows to return data):** the quantitative scoring engine — factor scores, peer comparisons, macro analysis, news synthesis. The framework above is the prompt/schema layer; Parallax is the data layer.

You can run the framework's validation, regression tests, and schema tooling without a Parallax subscription. To get actual portfolio output, you need Parallax connected.

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

## Forking and Customizing

Every workflow is a `SKILL.md` file — a structured prompt the model orchestrates. To customize:

```bash
# Develop against the repo directly. install.sh symlinks each skill, so edits
# in the repo propagate live without re-installing.
git clone https://github.com/bencharoenwong/parallax-workflows.git
cd parallax-workflows
./install.sh

# Fork a workflow
cp -r skills/should-i-buy skills/my-should-i-buy
$EDITOR skills/my-should-i-buy/SKILL.md   # change behavior, output format, MCP tool sequence
./install.sh                              # picks up the new skill on next Claude Code restart
```

A few common customizations:
- **Different output format.** Edit the "Output Format" section of `SKILL.md`. The model follows it verbatim.
- **Different tool sequence.** Add or remove `mcp__claude_ai_Parallax__*` calls in the workflow steps.
- **Different scoring backend.** The schema and loader under `skills/_parallax/house-view/` are scoring-engine-agnostic; the SKILL.md files are the layer that's coupled to Parallax MCP. Replace those calls with your own data source and the rest keeps working.
- **Different storage path.** House-view artifacts default to `~/.parallax/active-house-view/`. The path is referenced in `SKILL.md` and the Python helpers under `_parallax/house-view/`.

The Python modules (`audit_chain`, `chain_emit`, `manifest_verify`, `gap_detect`, `gap_suggest`) are pure functions with no MCP coupling — they import cleanly into any harness.

## Audit & Compliance

For compliance, vendor risk, and information security reviews:

- **Documented methodology.** Six-factor framework with academic foundations (Markowitz, Fama). Not a black-box ML model labeled as a factor model. See `skills/_parallax/house-view/loader.md`.
- **Hash-chained audit log.** Every house-view save and every consume appends an entry to `~/.parallax/active-house-view/audit.jsonl` with `prev_entry_hash` linking. Tampering with any entry breaks the chain on next verification.
- **Ed25519-signed reasoning chains.** Every consume writes a structured reasoning chain to `~/.parallax/reasoning-chains/` capturing the inputs, the manifest reference, and the output. Designed for 7-year replay against pinned tool versions.
- **Regulator-grade export.** `/parallax-load-house-view --export <view_id>` packages view + prose + provenance + full hash-chained audit trail into a tarball. Refuses to ship if the chain is broken.
- **Per-tilt provenance.** Every non-neutral tilt carries a derivation record: prose-extraction (with source span), macro-regime rule (with rule reference and trigger), or manual edit (with prior value and edit notes). `--why <tilt-path>` reconstructs the answer.
- **Local-only by default.** No telemetry. No external calls during ingest beyond the LLM the operator chose. Files are written with restrictive permissions.

Implementation lives in `skills/_parallax/house-view/audit_chain.py`, `chain_emit.py`, `manifest_verify.py`, `manifest_cache.py`, and `audit_export.py`. Test coverage is in the adjacent `tests/` directory; the test signing key and fixtures are deliberately public so auditors can verify round-trip on a fresh clone.

## Workflows

### Concierge

| Command | What it does |
|---|---|
| `Hi Parallax` or `/parallax-concierge` | Friendly concierge that opens a four-branch menu (Stock / Portfolio / Discovery / Investor profile), asks one clarifying question, then routes you to the right `/parallax-*` workflow. The magic front door for everyday users. Also triggers on "what can Parallax do" and similar exploratory phrasings. |

### Single Stock

| Command | What it does |
|---|---|
| `/parallax-should-i-buy AAPL` | Quick evaluation — scores, macro, dividends, news, outlook |
| `/parallax-deep-dive AAPL.O` | Full analysis with technicals and AI assessment |
| `/parallax-due-diligence AAPL.O` | All financials, Palepu framework, Parallax research report |
| `/parallax-earnings-quality AAPL.O` | Accruals, revenue quality, manipulation risk |
| `/parallax-score-explainer AAPL.O "why is value low?"` | Plain-language methodology explanation |
| `/parallax-peer-comparison AAPL.O` | Factor scores and price performance vs peers |
| `/parallax-pair-finder NVDA.O long` (or `short`, or `long=X short=Y`) | Long/short pair construction — find the other leg from peers, or evaluate a pair you have, with full residual-exposure decomposition |

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

### House View — flagship complex workflow

Bring your own house view. The CIO memo, IC strategy doc, or macro-desk PDF that anchors your book becomes a first-class object every portfolio workflow auto-loads.

> **For users:** load it once, every portfolio command picks it up. Skip to the table.
> **For builders:** this is the most involved skill in the repo — schema, validation, hash-chained audit log, Ed25519-signed reasoning chains, calibration manifest verifier, regulator-grade export. If you're studying how a complex `/parallax-*` skill is structured, **start here**. The implementation under `skills/_parallax/house-view/` is authored by load-house-view but its `loader.md` and `render_helpers.md` are deliberately shared — the consuming portfolio and single-stock skills JIT-load them when surfacing view conflicts.

| Command | What it does |
|---|---|
| `/parallax-load-house-view <pdf or .md or url>` | Ingest, extract structured tilts, confirm with uploader, save as active view |
| `/parallax-load-house-view` | Wizard mode for guided manual entry |
| `/parallax-load-house-view --status` | Show active view summary |
| `/parallax-load-house-view --extend <date>` | Push `valid_through` forward |
| `/parallax-load-house-view --re-pair` | Re-pair after manual prose edit |
| `/parallax-load-house-view --why <tilt-path>` | Trace any tilt to the source span that generated it |
| `/parallax-load-house-view --export <view_id>` | Export regulator-grade compliance bundle |
| `/parallax-load-house-view --clear` | Remove active view |

**Three design choices worth knowing about:**

1. **Your LLM, your prompt.** Extraction runs in your harness, against your model. Documents do not leave your machine.
2. **Local by default.** The view lives at `~/.parallax/active-house-view/` — `view.yaml`, `prose.md`, `provenance.yaml`, `audit.jsonl`. Files are written `0600`, the directory is `0700`. We do not host it.
3. **Audit was a design input.** Every save writes a hash-chained audit entry, an Ed25519-signed reasoning chain, and a per-tilt provenance record. `--export` produces a regulator-grade bundle. `--why tilts.factors.momentum` traces any tilt back to the source span (or rule, or manual edit) that generated it.

Active view is consumed by: `portfolio-builder`, `rebalance`, `thematic-screen`, `morning-brief`, `client-review`, `explain-portfolio`. Conflict-flag-only by: `should-i-buy`, `deep-dive`. See `skills/load-house-view/samples/` for sample CIO views, `skills/_parallax/house-view/loader.md` for the multiplier mapping and conflict-resolution rules, and `skills/_parallax/house-view/README.md` for the module reference.

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

**Where things live:**
- `skills/<workflow>/SKILL.md` — the user-invocable workflows
- `skills/_parallax/parallax-conventions.md`, `token-costs.md`, `AI-profiles/` — genuinely shared across many skills (RIC resolution, parallel-call patterns, AI profile framework)
- `skills/_parallax/house-view/` — house-view subsystem. Authored by `/parallax-load-house-view` (schema, audit chain, signed reasoning chains, calibration manifest verifier); also consumed by the portfolio and single-stock skills that surface view conflicts (`portfolio-builder`, `rebalance`, `client-review`, `morning-brief`, `explain-portfolio`, `thematic-screen`, `deep-dive`, `should-i-buy`). `loader.md` and `render_helpers.md` are the shared interface; `gap_detect` / `gap_suggest` are loaded by `portfolio-builder --augment-silent` only.

**Reference templates.** The newer skills (`credit-lens`, `load-house-view`, `white-label-onboard`) carry typed dataclasses, comprehensive test suites, and explicit reference modules. If you're authoring or upgrading a skill, model on those.

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
