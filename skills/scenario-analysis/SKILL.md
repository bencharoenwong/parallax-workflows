---
name: parallax-scenario-analysis
description: "React to a news event or scenario: assess portfolio exposure, macro regime shift, sector impact, identify most-exposed holdings, find rotation candidates, and output a concrete action plan via Parallax MCP tools. Requires a portfolio and a scenario description. NOT for routine morning briefs (use /parallax-morning-brief), not for macro outlook without a triggering event (use /parallax-macro-outlook)."
user-invocable: true
negative-triggers:
  - Routine morning brief → use /parallax-morning-brief
  - General macro outlook → use /parallax-macro-outlook
  - Single stock analysis → use /parallax-deep-dive
  - Portfolio rebalancing without a trigger event → use /parallax-rebalance
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - get_assessment with a scenario-focused prompt is the core analytical engine — feed it everything from prior steps
  - get_news_synthesis may already surface the event — check before assuming the user's framing is complete
  - Score changes haven't happened yet if the event is breaking — use get_assessment for forward-looking analysis
  - For historical events, get_score_analysis can show what actually moved
  - This skill produces FORWARD-LOOKING analysis — always caveat uncertainty
---

# Scenario Analysis

Something happened (or might happen). What's exposed? What shifts? What do I do?

## Usage

```
/parallax-scenario-analysis "China announces 25% tariff on US semiconductors" portfolio=[{"symbol":"NVDA.O","weight":0.15},{"symbol":"AAPL.O","weight":0.20},{"symbol":"TSM.N","weight":0.10},{"symbol":"JPM.N","weight":0.15},{"symbol":"XOM.N","weight":0.20},{"symbol":"JNJ.N","weight":0.20}]
/parallax-scenario-analysis "Fed cuts rates 50bps emergency" portfolio=[holdings]
/parallax-scenario-analysis "Oil spikes to $120 on Middle East escalation" portfolio=[holdings]
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, and fallback patterns.

### Phase 1: Understand the Event (parallel)

Fire all three simultaneously:

| Tool | Parameters | Notes |
|---|---|---|
| `get_news_synthesis` | 2-3 most affected sectors | What market already knows |
| `get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Starting macro environment |
| `macro_analyst` | relevant countries/regions; component "tactical" if macro event | Positioning implications |

### Phase 2: Assess Portfolio Exposure (parallel after Phase 1)

Fire 4-5 simultaneously:

| Tool | Parameters | Notes |
|---|---|---|
| `analyze_portfolio` | holdings, lens "concentration" | Sector/factor exposures |
| `get_score_analysis` | each holding, 4-8 weeks | Current trajectories |

Then call `get_assessment` with a prompt that:
   - Describes the scenario
   - Lists each holding with its sector and factor profile
   - Asks: "Rank these holdings from most-exposed to least-exposed to this scenario. For each, explain the transmission mechanism (direct revenue impact, supply chain, regulatory, sentiment)."

### Phase 3: Sector Rotation & Replacement Candidates
7. **Identify Beneficiaries** — Call `build_stock_universe` with a theme describing what benefits from this scenario (e.g., "domestic US semiconductor manufacturers" if China tariffs hit imports).
8. **Score Beneficiaries** — Call `get_peer_snapshot` for top 5 candidates from the universe build.
9. **Compare Replacements** — For the top 2-3 replacement candidates, call `get_financials` with statement "summary" to verify they're fundamentally sound, not just thematically relevant.

### Phase 4: Action Plan
10. **Synthesize** — Call `get_assessment` with a comprehensive prompt incorporating:
    - The scenario and its transmission mechanisms
    - Portfolio exposure ranking from step 6
    - Macro regime and tactical outlook
    - Replacement candidates and their scores
    - Ask: "Given this scenario, what specific portfolio adjustments should be considered? Prioritize by urgency and magnitude of exposure."

## Output Format

- **Scenario Summary** (what happened, why it matters — 2-3 sentences)
- **Macro Regime Impact** (how this shifts the current regime, which factors are affected)
- **Exposure Heat Map** (table: each holding ranked by exposure level — High/Medium/Low — with transmission mechanism)
- **Most Exposed** (the 2-3 holdings at greatest risk, with specific reasoning)
- **Least Affected** (safe positions — brief explanation why)
- **Sector Rotation Thesis** (what benefits from this scenario)
- **Replacement Candidates** (table: symbol, name, sector, total score, why it fits)
- **Action Plan** (prioritized list: what to trim/sell, what to add, what to hold — with specific weight suggestions)
- **What to Watch** (2-3 signals that would confirm or invalidate this thesis)
- **Confidence & Caveats** (how certain is this analysis, what could go wrong with the rotation)

Always end with: *"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*
