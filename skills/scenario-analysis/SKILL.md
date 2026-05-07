---
name: parallax-scenario-analysis
description: "React to a news event or scenario: assess portfolio exposure, macro regime shift, sector impact, identify most-exposed holdings, find rotation candidates, and output a concrete action plan via Parallax MCP tools. Also surfaces under PM/RIA vocabulary: 'stress book', 'scenario suite', 'stress test' (e.g., rates +100bps, USD shock, 2008 / 2020 / 2022 replays). Requires a portfolio and a scenario description. NOT for routine morning briefs (use /parallax-morning-brief), not for macro outlook without a triggering event (use /parallax-macro-outlook)."
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

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call. Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, and fallback patterns.

### Phase 1: Understand the Event (parallel)

Fire all three simultaneously:

| Tool | Parameters | Notes |
|---|---|---|
| `get_news_synthesis` | 2-3 most affected sectors | What market already knows |
| `get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Starting macro environment |
| `macro_analyst` | relevant countries/regions; component "tactical" if macro event | Positioning implications |

### Phase 2: Assess Portfolio Exposure

Phase 2 is staged into two parallel turns: **2a classification + ground-truth** must complete before **2b per-equity scoring + sector** can fire, because the asset-class decision in 2a determines which holdings are eligible for 2b's `get_score_analysis` (factor scores are equity-only). Within each sub-phase every call is independent and parallel-safe per `_parallax/parallax-conventions.md` §3.

#### Phase 2a — Classification + ground-truth (parallel, single tool-call turn)

| Tool | Parameters | Notes |
|---|---|---|
| `analyze_portfolio` | holdings, lens "concentration" | Sector/factor exposures. WARNING: may exceed 180K chars — fall back to `check_portfolio_redundancy` if truncated. Server-side ETF handling: ETFs included here without per-skill branching. |
| `etf_profile` | per holding, plain ticker — **all N calls fan out in parallel within 2a** | **Asset-class oracle.** Non-error response → ETF; error response (`{"error": "No profile data found"}`) → equity. Free / instant per `_parallax/token-costs.md`. Mirrors `explain-portfolio` Step 1a. |
| `get_company_info` | per holding — **all N calls fan out in parallel within 2a** | **Ground-truth name oracle** for cross-validation per conventions §2. Per-holding only — do NOT use comma-joined: comma-joined calls fail-empty on partial coverage, which is risky for arbitrary user-supplied portfolios where any single unresolved RIC silently zeroes the entire batch. |

**Gate between 2a and 2b** — perform the following checks on 2a results before firing 2b:

1. **Asset-class routing**: partition holdings into `equities` (etf_profile error) and `etfs` (etf_profile non-error). Phase 2b's `get_score_analysis` runs ONLY on the `equities` set.
2. **Name cross-validation** (per conventions §2): for each holding, compare `get_company_info.name` against any name field surfaced in `analyze_portfolio` peer rollups. Mismatches are flagged ⚠ MISMATCH and the holding is **fully excluded** from downstream analysis — both from 2b's `get_score_analysis` and from Phase 3's `get_assessment` prompt construction. Do not include mismatched holdings with empty profiles; that produces hallucinated factor profiles in the assessor's output.

#### Phase 2b — Per-equity score trajectories (parallel, single tool-call turn)

| Tool | Parameters | Notes |
|---|---|---|
| `get_score_analysis` | per **equity** holding (excluding ETFs from 2a and ⚠ MISMATCH holdings), 4-8 weeks — **all N calls fan out in parallel within 2b** | Current factor trajectories. Skipped holdings are surfaced explicitly in output (see Output Format). |

Then call `get_assessment` with a prompt that:
   - Describes the scenario
   - Lists each **equity, non-mismatched** holding with its sector and factor profile
   - For ETF holdings: lists symbol + sector exposure from `analyze_portfolio` only (no per-holding factor profile)
   - Explicitly excludes ⚠ MISMATCH holdings from the prompt entirely
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
- **Ground-truth Integrity** *(only render if Phase 2a flagged any mismatches OR ETFs were excluded from per-position trajectory)* — table: `symbol`, `returned_name`, `expected_name`, status (⚠ MISMATCH / ETF — sector exposure only / TRUSTED). Mismatched holdings were fully excluded from the assessment prompt; ETF holdings are present in `analyze_portfolio` sector exposure but not in per-position factor trajectories.
- **Macro Regime Impact** (how this shifts the current regime, which factors are affected)
- **Exposure Heat Map** (table: each equity holding ranked by exposure level — High/Medium/Low — with transmission mechanism. ETF holdings appear with sector-level exposure only; mismatched holdings are excluded.)
- **Most Exposed** (the 2-3 holdings at greatest risk, with specific reasoning)
- **Least Affected** (safe positions — brief explanation why)
- **Sector Rotation Thesis** (what benefits from this scenario)
- **Replacement Candidates** (table: symbol, name, sector, total score, why it fits)
- **Action Plan** (prioritized list: what to trim/sell, what to add, what to hold — with specific weight suggestions)
- **What to Watch** (2-3 signals that would confirm or invalidate this thesis)
- **Confidence & Caveats** (how certain is this analysis, what could go wrong with the rotation)

*"This is scenario-based analysis, not investment advice. Forward-looking assessments are inherently uncertain."*
